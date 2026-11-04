#!/usr/bin/env python3
"""The motion-graphics agent (v2).

    prompt (+ images, + reference video, + size)
      -> memory context (brand kit, lessons, liked designs, style guide, last videos)
      -> Gemini writes a JSON scene spec -> validator (errors go back to the model)
      -> asset search (photos / illustrations / vectors / icons / your Canva exports) with AI choice, remembered
      -> automatic QA (cut-off text, overlap, contrast, empty frames, variety ...) -> model fixes them
      -> preview frames -> Gemini reviews them -> fixes
      -> final MP4 + report + memory update (design card, lessons, learning log)

Run directly:   python agent.py --prompt "10 second intro for a fitness app" --duration 10 --size 16:9
"""
import argparse, glob, json, os, re, sys, traceback
import cv2, numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from mgl import gemini, spec as S, engine as E, qa as QA, assets as A, learn as LN, reference as RF
from mgl import remix as RX, planner as PL, compare as CP, judge as JD
from mgl.memory import Memory, summarize_spec
import render as R

DEFAULT_BUDGET = 14        # max Gemini requests per run (protects the free quota)
NO_NOV = {'too_close': False, 'problems': [], 'similarity': 0.0, 'nearest': None, 'copied_texts': []}
REFERENCE_FIDELITY_TARGET = 72      # below this (0-100) the bot fixes the video towards the example


class AgentError(Exception):
    pass


class BudgetError(gemini.GeminiError):
    pass


# ------------------------------------------------------------------ prompts
def canvas_text(size_key):
    W, H = E.SIZES[size_key]
    extra = {'16:9': 'Landscape (YouTube). Keep key content inside x 120..1800, y 80..1000.',
             '9:16': 'Vertical (Shorts / Reels / TikTok). Phones cover the top ~8% and bottom ~22%: keep text between y 150 and y 1500. Use big, short text; stack things vertically.',
             '1:1': 'Square (Instagram feed). Keep key content inside x 100..980, y 100..980.'}[size_key]
    return 'CANVAS FOR THIS VIDEO: size "%s" = %dx%d pixels, centre (%d, %d). %s Set "size": "%s" in the spec.' % (size_key, W, H, W // 2, H // 2, extra, size_key)


def _design_rules():
    try:
        from mgl import library as LB
        if not LB.load(ROOT): return ''
        return LB.rules() + '\nDesigns in the library (id | title | topic):\n' + LB.catalog(ROOT) + '\n'
    except Exception:
        return ''


def _design_block(prompt):
    try:
        from mgl import library as LB
        return LB.relevant_block(prompt, 3, ROOT)
    except Exception:
        return ''


def build_system_prompt(size_key='16:9', examples=('saas_intro', 'showcase', 'vertical_short', 'logo_reveal')):
    lib = open(os.path.join(ROOT, 'LIBRARY.md'), encoding='utf-8').read().replace('{{CANVAS}}', canvas_text(size_key))
    ex = []
    for name in examples:
        p = os.path.join(ROOT, 'examples', name + '.json')
        if os.path.exists(p):
            ex.append('EXAMPLE "%s":\n%s' % (name, json.dumps(json.load(open(p, encoding='utf-8')), separators=(',', ':'), ensure_ascii=False)))
    return ('You are a senior motion designer who writes scene specs for a custom renderer.\n'
            'Follow the library reference exactly: only use the layer types, fields and values it documents.\n'
            'Your whole answer must be one valid JSON object (no markdown fences, no comments, no trailing commas).\n'
            'Every video you make must look professional and DIFFERENT from the previous ones: vary colours, background styles, layouts, animations and transitions.\n\n'
            '=== LIBRARY REFERENCE ===\n' + lib + '\n\n=== WORKING EXAMPLES (study structure, timing and variety; do not copy their content) ===\n' + '\n\n'.join(ex)
            + _design_rules())


def list_assets(root=ROOT):
    out = []
    for dp, _, fs in os.walk(os.path.join(root, 'assets')):
        for fn in sorted(fs):
            if fn.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                p = os.path.join(dp, fn)
                if os.sep + 'library' + os.sep in p or os.sep + 'canva' + os.sep in p or os.sep + 'designlib' + os.sep in p: continue     # found through "search"
                im = cv2.imread(p, cv2.IMREAD_UNCHANGED)
                if im is not None:
                    out.append('%s (%dx%d px)' % (os.path.relpath(p, root).replace(os.sep, '/'), im.shape[1], im.shape[0]))
    return out


def attach_images(paths, root=ROOT, max_side=768, limit=4):
    """downscaled PNG parts for Gemini vision"""
    parts = []
    for p in paths[:limit]:
        full = os.path.join(root, p)
        im = cv2.imread(full, cv2.IMREAD_UNCHANGED)
        if im is None: continue
        if im.ndim == 3 and im.shape[2] == 4:
            a = im[..., 3:4].astype(np.float32) / 255
            im = (im[..., :3].astype(np.float32) * a + 60 * (1 - a)).astype(np.uint8)
        h, w = im.shape[:2]; s = min(1.0, max_side / max(h, w))
        if s < 1: im = cv2.resize(im, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode('.png', im)
        if ok:
            parts.append(gemini.text_part('Attached picture: %s' % p)); parts.append(gemini.image_part(buf.tobytes()))
    return parts


def build_user_prompt(prompt, duration, size_key, assets, mem_ctx, has_reference, style_card, user_images, extra_blocks=''):
    t = 'Create a scene spec for this video.\n\nBRIEF: %s\n\nDURATION: exactly %s seconds (set "duration": %s).\n%s\n' % (prompt.strip(), duration, duration, canvas_text(size_key))
    t += _design_block(prompt)
    if extra_blocks:
        t += '\n' + extra_blocks
    if assets:
        t += '\nAssets available (use these exact paths in "image" layers):\n- ' + '\n- '.join(assets) + '\n'
    else:
        t += '\nNo uploaded assets. For pictures, photos, illustrations or icons use an image layer with a "search" (see the library reference); never invent file paths.\n'
    if user_images:
        t += ('\nThe user wants these uploaded images ANIMATED and featured: %s. Look at the attached pictures and choose animations that suit their content '
              '(Ken Burns zoom/pan for photos, 3D tilt and device frames for screenshots, pop/float for logos and cut-outs).\n' % ', '.join(user_images))
    if has_reference:
        t += ('\nREFERENCE VIDEO: the attached pictures are contact sheets of a reference video (time stamps in yellow).\n'
              'CUSTOMIZE it: keep its scene structure, order, pacing, layout archetypes, motion and transitions, but replace ALL content with the content of the brief, '
              'the brand kit and the uploaded images. Do not copy its text.\n')
        if style_card: t += 'Analysis of the reference: ' + json.dumps({k: v for k, v in style_card.items() if k not in ('sha', 'source', 'date', 'id')}, ensure_ascii=False)[:2400] + '\n'
    if mem_ctx:
        t += '\n=== MEMORY (what you learned from earlier videos; follow it) ===\n' + mem_ctx + '\n'
    t += '\nReturn ONLY the JSON object.'
    return t


REVIEW_PROMPT = (
    'You are a strict motion-design reviewer. The picture is a contact sheet of 12 frames of a generated video '
    '(time stamps in yellow). The brief was:\n"%s"\n\n'
    'Check: (1) text readable, not cut off or overlapping, (2) contrast, (3) nothing important off-screen, (4) no empty stretches, closing scene visible at the end, '
    '(5) variety and pacing - do the scenes look different from each other? (6) professional look: hierarchy, spacing, colour harmony, (7) matches the brief.\n'
    'Reply with JSON only: {"score": <1-10>, "problems": ["specific fix, mention the text or layer type and the time"]}. '
    'Give an empty problems list if the video is good (score 8 or more).')


# ------------------------------------------------------------------ spec repair
ALIASES = {'rect': 'rrect', 'rectangle': 'rrect', 'rounded_rect': 'rrect', 'roundrect': 'rrect', 'rounded_rectangle': 'rrect',
           'box': 'rrect', 'pill': 'rrect', 'panel': 'rrect', 'button': 'rrect', 'shape': 'rrect',
           'label': 'text', 'title': 'text', 'heading': 'text', 'caption': 'text', 'subtitle': 'text',
           'picture': 'image', 'photo': 'image', 'logo': 'image', 'img': 'image', 'ellipse': 'circle', 'dot': 'circle',
           'bar_chart': 'chart', 'graph': 'chart', 'phone': 'device', 'mockup': 'device', 'sparkles': 'particles', 'orb': 'blob', 'glow': 'blob'}
NUMERIC = ('start', 'end', 'x', 'y', 'scale', 'rot', 'opacity', 'blur', 'size', 'w', 'h', 'r', 'width', 'yaw', 'roll', 'number',
           'shadow', 'fill_opacity', 'border_opacity', 'border_w', 'shadow_blur', 'shadow_dy', 'light', 'angle', 'softness', 'progress',
           'value', 'spacing', 'speed', 'twinkle', 'vignette', 'thickness', 'zoom', 'pan_x', 'pan_y', 'tilt_x', 'tilt_y', 'seed', 'n')


def _num(v):
    if isinstance(v, str):
        try: return float(v.strip().rstrip('pxs%'))
        except Exception: return v
    return v


def normalize_spec(sp, duration=None, size=None):
    """fix the usual small mistakes of language models without changing the meaning"""
    if isinstance(sp, dict) and 'spec' in sp and isinstance(sp['spec'], dict) and 'layers' not in sp:
        sp = sp['spec']
    if not isinstance(sp, dict): return sp
    for alt in ('elements', 'objects', 'items'):
        if 'layers' not in sp and isinstance(sp.get(alt), list): sp['layers'] = sp.pop(alt)
    if duration is not None: sp['duration'] = duration
    elif 'duration' in sp: sp['duration'] = _num(sp['duration'])
    if size is not None: sp['size'] = size
    if 'fps' in sp:
        f = _num(sp['fps']); sp['fps'] = int(f) if isinstance(f, (int, float)) else sp['fps']
    for L in (sp.get('layers') or []):
        if not isinstance(L, dict): continue
        ty = L.get('type')
        if isinstance(ty, str):
            ty = ty.strip().lower().replace('-', '_')
            L['type'] = ALIASES.get(ty, ty)
        for k in NUMERIC:
            if k in L: L[k] = _num(L[k])
        for key in ('in', 'out'):
            if isinstance(L.get(key), dict) and 'dur' in L[key]: L[key]['dur'] = _num(L[key]['dur'])
        if L.get('type') == 'text' and isinstance(L.get('text'), str): L['text'] = L['text'].replace('\n', ' ')
        if isinstance(L.get('search'), dict) and isinstance(L['search'].get('section'), str):
            sec = L['search']['section'].strip().lower()
            L['search']['section'] = {'photos': 'photo', 'icons': 'icon', 'illustrations': 'illustration', 'vectors': 'vector', 'graphics': 'vector', 'graphic': 'vector'}.get(sec, sec)
    return sp


# ------------------------------------------------------------------ llm plumbing
def make_ask(key, log=print, budget=None):
    models = gemini.choose_models(key)
    log('models to try: %s' % ', '.join(models))
    used = []
    budget = int(os.environ.get('MAX_REQUESTS', DEFAULT_BUDGET) or DEFAULT_BUDGET) if budget is None else budget

    def ask(system, contents, json_mode=True):
        if ask.calls >= ask.budget:
            raise BudgetError('request budget of %d reached for this run (protects the free quota; raise it with the MAX_REQUESTS variable)' % ask.budget)
        ask.calls += 1
        txt, model = gemini.ask(key, models, system, contents, json_mode=json_mode, log=log)
        if model not in used: used.append(model)
        if model in models: models.insert(0, models.pop(models.index(model)))
        return txt
    ask.used, ask.calls, ask.budget = used, 0, budget
    return ask


def budget_left(ask):
    return getattr(ask, 'budget', 10 ** 6) - getattr(ask, 'calls', 0)


def reference_sheet(path, n=12, cols=4, tile_w=480):
    sheets, info = RF.frame_sheets(path, per_sheet=n, sheets=1, cols=cols, tile_w=tile_w)
    return sheets[0], info['duration']


# ------------------------------------------------------------------ the loop
def obtain_spec(ask, system, history, duration, size_key, log, root=ROOT, max_tries=4, title=None):
    last_errors = []; last_sp = None
    for attempt in range(1, max_tries + 1):
        log('[spec] attempt %d/%d' % (attempt, max_tries))
        txt = ask(system, history)
        history.append({'role': 'model', 'parts': [gemini.text_part(txt)]})
        try:
            sp = normalize_spec(gemini.extract_json(txt), duration, size_key)
        except Exception as ex:
            last_errors = ['The answer was not valid JSON (%s). Return one complete JSON object only.' % ex]
            sp = None
        if sp is not None:
            last_sp = sp
            errs, warns = S.validate(sp, root)
            for w in warns: log('   warning: %s' % w)
            if not errs:
                return sp
            last_errors = errs
        log('   %d problem(s): %s' % (len(last_errors), '; '.join(last_errors[:3])))
        history.append({'role': 'user', 'parts': [gemini.text_part(
            'The spec has problems:\n- ' + '\n- '.join(last_errors[:25]) + '\n\nFix them and return the COMPLETE corrected JSON object only.')]})
    fixed, notes = S.salvage(last_sp, root) if last_sp is not None else (None, [])
    if fixed is not None:
        log('[spec] repaired the last design instead of failing (%s)' % ', '.join(notes[:6]))
        fixed['duration'] = duration; fixed['size'] = size_key
        if not S.validate(fixed, root)[0]: return fixed
    if title:
        log('[spec] the AI gave no usable design - using a simple title video so the run does not fail')
        return S.fallback_spec(title, duration, size_key)
    raise AgentError('could not get a valid spec after %d tries. Last problems:\n- %s' % (max_tries, '\n- '.join(last_errors[:10])))


def _need_fix(rep, nov=None):
    return bool(rep['errors']) or len(rep['warnings']) >= 2 or bool(nov and nov.get('too_close'))


def run_agent(prompt, duration, out_dir, ask, review=True, max_review=2, max_qa=2, size='16:9', reference=None, images=None,
              mem=None, root=ROOT, providers=None, log=print, render_final=True, update_memory=True,
              plan=False, remix=True, compare_ref=True):
    os.makedirs(out_dir, exist_ok=True)
    size_key = E.norm_size(size) or '16:9'
    mem = mem or Memory(root)
    images = [p for p in (images or []) if os.path.isfile(os.path.join(root, p))]
    for p in list_assets(root):                                     # assets named in the prompt are attached too
        rel = p.split(' (')[0]
        if os.path.basename(rel).lower() in prompt.lower() and rel not in images: images.append(rel)
    report = ['# Agent report', '', 'Brief: %s' % prompt, 'Size: %s   Duration: %ss' % (size_key, duration), '']
    system = build_system_prompt(size_key)

    parts, style_card = [], None
    if reference:
        sheets, rinfo = RF.frame_sheets(reference, per_sheet=12, sheets=2)
        sha = RF.video_sha(reference)
        style_card = next((s for s in mem.styles if s.get('sha') == sha), None)
        if style_card is None and budget_left(ask) > 6:
            try:
                style_card = RF.analyze_video(ask, reference, log); mem.add_style(style_card)
                log('reference analysed and remembered: %s' % style_card['title'])
            except Exception as ex:
                log('   reference analysis skipped (%s)' % ex)
        parts += [gemini.image_part(png) for png in sheets]
        log('reference video read (%.1fs)' % rinfo['duration'])
        report.append('Reference video: %s (%s)' % (os.path.basename(reference), style_card['title'] if style_card else 'not analysed'))
    parts += attach_images(images, root)
    mem_ctx = mem.context_for_prompt(prompt)
    extra, plan_txt, recipe, plan_info = '', '', None, None
    if remix and not reference:                      # a reference video fixes the structure; otherwise invent from old designs
        try:
            recipe = RX.make_recipe(prompt, root, mem, duration, size_key)
            extra += recipe['text']
            mt = recipe['mutations']
            report.append('Remix recipe: ideas from %s; new backgrounds %s, transitions %s, %s' % (', '.join(recipe['sources']) or '(no library)', ' -> '.join(mt['backgrounds']), ', '.join(mt['transitions']), mt['pacing']))
            log('[remix] ideas from %s' % (', '.join(recipe['sources']) or 'nothing (empty library)'))
        except Exception as ex:
            log('   remix recipe skipped (%s)' % ex)
    if plan and budget_left(ask) > 5:
        try:
            note = json.dumps({k: v for k, v in (style_card or {}).items() if k in ('title', 'scenes', 'transitions', 'pacing', 'motion')}, ensure_ascii=False)[:1100] if style_card else ''
            plan_info, plan_txt = PL.make_plan(ask, prompt, duration, size_key, mem_ctx, recipe['text'] if recipe else '', note, mem, log)
            extra += '\n' + plan_txt
            log('[plan] %s' % plan_info['concept'][:120])
            report.append('Director\'s plan: %s | signature: %s | %d scenes' % (plan_info['concept'], plan_info['signature'], len(plan_info['scenes'])))
        except Exception as ex:
            log('   planning skipped (%s) - building directly' % ex); report.append('Planning skipped: %s' % ex)
    user_text = build_user_prompt(prompt, duration, size_key, list_assets(root), mem_ctx, bool(reference), style_card, images, extra)
    history = [{'role': 'user', 'parts': [gemini.text_part(user_text)] + parts}]
    provs = providers if providers is not None else A.make_providers(root, mem)
    assets_report, review_rounds = [], []

    def resolve(sp):
        if not any(isinstance(L, dict) and L.get('type') == 'image' and 'search' in L and 'path' not in L for L in sp.get('layers', [])):
            return sp
        bg = sp.get('background')
        bg_hint = bg if isinstance(bg, str) else ', '.join(str(k.get('style')) for k in (bg or []) if isinstance(k, dict))
        sp, rep = A.resolve_spec(sp, root, mem, ask if budget_left(ask) > 3 else None, provs, bg_hint, log=log)
        for r in rep:
            line = '- %s "%s": %s%s' % (r['section'], r['query'], r['chosen'] or 'NOT USED', ' (%s)' % r['reason'] if r.get('reason') else '')
            log('   asset ' + line[2:]); assets_report.append(line)
        return sp

    def improve(sp, problems, who):
        fix_hist = [{'role': 'user', 'parts': [gemini.text_part(
            build_user_prompt(prompt, duration, size_key, list_assets(root), '', False, None, [], plan_txt) +
            '\n\nCURRENT SPEC (image layers already contain their chosen "path"; keep them):\n' + json.dumps(sp, separators=(',', ':'), ensure_ascii=False) +
            '\n\n%s found these problems:\n- ' % who + '\n- '.join(problems[:12]) +
            '\n\nReturn the COMPLETE improved JSON spec: keep what works, fix the problems, keep the overall idea and the brand.')]}]
        return resolve(obtain_spec(ask, system, fix_hist, duration, size_key, log, root, max_tries=3))

    ref_prof, ref_frames, cmp_n = None, None, CP.n_samples(duration)
    if reference and compare_ref:
        try:
            ref_frames, rinf = CP.video_frames(reference, cmp_n)
            ref_prof = CP.profile(ref_frames, rinf)
        except Exception as ex:
            log('   reference comparison disabled (%s)' % ex)

    def evaluate(spec):
        """(qa report, originality, reference comparison or None, one quality number)"""
        qa_ = QA.analyze(spec, root)
        nov_ = RX.novelty(spec, root, mem) if remix else NO_NOV
        res_ = None
        if ref_prof is not None:
            try:
                fr, inf = CP.spec_frames(spec, root, cmp_n)
                res_ = CP.compare(ref_prof, CP.profile(fr, inf))
            except Exception as ex:
                log('   comparison failed (%s)' % ex)
        return qa_, nov_, res_, JD.quality(qa_, nov_, res_['score'] if res_ else None)

    best = JD.Best()

    def adopt(cand, tag):
        """take the candidate only if it is not clearly worse than the best version so far"""
        nonlocal sp, qa_now, nov, cur_res
        ev = evaluate(cand)
        if best.offer(cand, ev[3], tag, ev):
            sp, qa_now, nov, cur_res = cand, ev[0], ev[1], ev[2]
            return True
        log('   %s made the video worse (quality %.1f < %.1f) - keeping the previous version' % (tag, ev[3], best.score))
        report.append('A revision (%s) scored lower (%.1f vs %.1f) and was thrown away.' % (tag, ev[3], best.score))
        return False

    sp = resolve(obtain_spec(ask, system, history, duration, size_key, log, root, title=prompt[:60]))
    qa_now, nov, cur_res, q0 = evaluate(sp)
    qa_first, nov_first, res_first = qa_now, nov, cur_res
    best.offer(sp, q0, 'first draft', (qa_now, nov, cur_res, q0))
    log('[qa] %d error(s), %d warning(s)%s' % (len(qa_now['errors']), len(qa_now['warnings']), ('; originality: %.0f%% like %s' % (nov['similarity'] * 100, nov['nearest'])) if nov['nearest'] else ''))
    if cur_res: log('[compare] fidelity to the reference: %.0f/100' % cur_res['score'])
    rounds = 0
    while rounds < max_qa and _need_fix(qa_now, nov) and budget_left(ask) > 1:
        rounds += 1
        issues = QA.problems(qa_now) + nov['problems']
        log('[qa] fix round %d: %s' % (rounds, '; '.join(issues[:3])[:200]))
        try:
            if not adopt(improve(sp, issues, 'The automatic quality checks'), 'QA fix %d' % rounds): break
        except (AgentError, gemini.GeminiError) as ex:
            log('   fix failed (%s) - keeping the previous spec' % ex); report.append('QA fix failed: %s' % ex); break
    if cur_res and cur_res['score'] < REFERENCE_FIDELITY_TARGET and cur_res['gaps'] and budget_left(ask) > 2:
        log('[compare] below %d - fixing towards the reference: %s' % (REFERENCE_FIDELITY_TARGET, '; '.join(cur_res['gaps'][:2])[:180]))
        try:
            adopt(improve(sp, cur_res['gaps'][:6], 'A measured comparison with the reference video (numbers from its frames)'), 'reference fix')
        except (AgentError, gemini.GeminiError) as ex:
            log('   reference fix failed (%s)' % ex); report.append('Reference fix failed: %s' % ex)

    preview = os.path.join(out_dir, 'preview.png')
    for rnd in range(max_review + 1):
        ctx = S.Context(root)
        R.preview_sheet(sp, preview, ctx)
        if ctx.warnings: report.append('Render warnings (round %d): %s' % (rnd, '; '.join(ctx.warnings)))
        if not review or rnd == max_review or budget_left(ask) < 2: break
        log('[review] round %d' % (rnd + 1))
        try:
            png = open(preview, 'rb').read()
            txt = ask('You review motion graphics. Answer with JSON only.',
                      [{'role': 'user', 'parts': [gemini.text_part(REVIEW_PROMPT % prompt), gemini.image_part(png)]}])
            rv = gemini.extract_json(txt)
            score = float(rv.get('score', 0)); problems = [str(p) for p in (rv.get('problems') or [])]
        except Exception as ex:
            log('   review skipped (%s)' % ex); report.append('Review skipped: %s' % ex); break
        review_rounds.append({'round': rnd + 1, 'score': score, 'problems': problems})
        log('   score %.1f, %d problem(s)' % (score, len(problems)))
        if score >= 8 or not problems or budget_left(ask) < 2: break
        try:
            if not adopt(improve(sp, problems, 'A reviewer who looked at the rendered frames'), 'review fix %d' % (rnd + 1)): break
            if qa_now['errors'] and budget_left(ask) > 1:
                if not adopt(improve(sp, QA.problems(qa_now), 'The automatic quality checks'), 'QA fix after review'): break
        except (AgentError, gemini.GeminiError) as ex:
            log('   revision failed (%s) - keeping the previous spec' % ex); report.append('Revision failed: %s' % ex); break

    if ref_prof is not None:                         # the evidence: example above, yours below
        try:
            fr, inf = CP.spec_frames(sp, root, cmp_n)
            res_final = CP.compare(ref_prof, CP.profile(fr, inf))
            CP.side_by_side(ref_frames, fr, os.path.join(out_dir, 'compare.png'))
            open(os.path.join(out_dir, 'compare.md'), 'w', encoding='utf-8').write(CP.report_md(os.path.basename(reference), 'this video', res_final))
            report.append('Fidelity to the reference: %.0f/100 (first draft %.0f). Details: compare.md, compare.png' % (res_final['score'], res_first['score'] if res_first else res_final['score']))
            cur_res = res_final
        except Exception as ex:
            log('   final comparison skipped (%s)' % ex)

    with open(os.path.join(out_dir, 'spec.json'), 'w', encoding='utf-8') as f:
        json.dump(sp, f, indent=1, ensure_ascii=False)
    if render_final:
        log('[render] final video ...')
        ctx = S.Context(root)
        R.render_video(sp, os.path.join(out_dir, 'video.mp4'), ctx, quiet=False)
        if ctx.warnings: report.append('Final render warnings: %s' % '; '.join(ctx.warnings))

    # ---------------------------------------------------------------- learning
    last_score = review_rounds[-1]['score'] if review_rounds else None
    summary = summarize_spec(sp)
    did = None
    if update_memory:
        try:
            extra_card = {'size': size_key, 'assets': len(assets_report)}
            if recipe: extra_card['remix'] = {'sources': recipe['sources'], 'backgrounds': recipe['mutations']['backgrounds'], 'transitions': recipe['mutations']['transitions']}
            if plan_info: extra_card['plan'] = {'concept': plan_info['concept'], 'signature': plan_info['signature']}
            if cur_res: extra_card['fidelity'] = cur_res['score']
            if nov.get('nearest'): extra_card['originality'] = {'nearest': nov['nearest'], 'similarity': nov['similarity']}
            did = mem.add_design(prompt, sp, qa_now, last_score, extra=extra_card)
            new = mem.add_lessons(LN.lessons_from_qa(qa_first['errors'] + qa_first['warnings']), 'qa')
            for rv in review_rounds: new += mem.add_lessons(LN.lessons_from_review(rv['problems'], rv['score']), 'review')
            new += mem.add_lessons(LN.lessons_from_success(summary, last_score), 'success')
            if nov_first.get('too_close'):
                new += mem.add_lessons([{'kind': 'dont', 'text': 'A draft was almost a copy of an existing design (%s, %.0f%% alike). Always change backgrounds, animation family, transitions and layout when borrowing ideas.' % (nov_first['nearest'], nov_first['similarity'] * 100), 'weight': 1}], 'originality')
            if cur_res and ref_prof is not None:
                CP.learn_from(mem, cur_res, None, source='reference compare')
            if len(mem.lessons) > 40 and budget_left(ask) > 1:
                try:
                    if mem.consolidate_lessons(ask): log('   lessons consolidated')
                except Exception as ex:
                    log('   consolidation skipped (%s)' % ex)
            text = LN.run_summary(prompt, summary, qa_first, qa_now, review_rounds, last_score)
            mem.log('## %s - %s (%s)\n%s' % (did, size_key, os.path.basename(out_dir), text))
            mem.save()
            report += ['', '## What I learned this time', text, '', 'New lessons stored: %d. Design id: `%s`' % (new, did),
                       'To rate this video run the workflow with mode "feedback", design_id %s, a rating 1-5 and your note in the prompt box - the bot will learn from it.' % did]
        except Exception as ex:
            log('   memory update failed: %s' % ex); report.append('Memory update failed: %s' % ex)
    if assets_report: report += ['', '## Assets chosen'] + assets_report
    if best.reverted: report += ['', 'Regression guard: %d revision(s) were rejected because they made the video worse.' % best.reverted]
    if nov.get('nearest'): report += ['', 'Originality: closest existing design is %s (%.0f%% alike)%s.' % (nov['nearest'], nov['similarity'] * 100, ' - too close' if nov.get('too_close') else '')]
    report += ['', 'Gemini requests used: %s of %s. Models: %s' % (getattr(ask, 'calls', '?'), getattr(ask, 'budget', '?'), ', '.join(getattr(ask, 'used', []) or ['(n/a)']))]
    open(os.path.join(out_dir, 'report.md'), 'w', encoding='utf-8').write('\n'.join(report))
    return sp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--prompt', required=True)
    ap.add_argument('--duration', type=float, default=10)
    ap.add_argument('--size', default='16:9')
    ap.add_argument('--out', default='out')
    ap.add_argument('--no-review', action='store_true')
    ap.add_argument('--reference', default=None, help='path of a reference video to customize')
    ap.add_argument('--image', action='append', default=[], help='uploaded image (assets/...) to animate; repeatable')
    a = ap.parse_args()
    key = os.environ.get('GEMINI_API_KEY', '').strip().strip('"\'')
    if not key:
        raise SystemExit('GEMINI_API_KEY is not set. Create a free key at https://aistudio.google.com/apikey and add it as a repository secret.')
    d = int(a.duration) if float(a.duration).is_integer() else a.duration
    run_agent(a.prompt, d, a.out, make_ask(key), review=not a.no_review, size=a.size, reference=a.reference, images=a.image)
    print('done ->', a.out)


if __name__ == '__main__':
    try:
        main()
    except (AgentError, gemini.GeminiError) as ex:
        print('\nERROR: %s' % ex)
        sys.exit(1)
