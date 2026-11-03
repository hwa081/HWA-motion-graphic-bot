"""studio.codeagent - the "Code Studio" agent: Gemini works like a coding agent.

It writes scene.py (Python), runs it in the sandbox, LOOKS at the rendered frames, reads error messages and QA reports,
fixes its code over several turns, can write and register new reusable components (custom/*.py), and finishes with the final MP4.
Every turn is one Gemini request that returns JSON: {"say": "...", "actions": [{"tool": ...}, ...]}.
"""
import json, os, re, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from mgl import gemini, engine as E, learn as LN, reference as RF
from mgl.memory import Memory
from studio.sandbox import Sandbox
import agent as AG

TOOLS = ('write_file', 'read_file', 'check', 'preview', 'frame', 'qa', 'register', 'finish')

SYSTEM = """You are a senior motion-graphics programmer working like a coding agent inside a sandbox. You build a video by writing Python scene code (scene.py), rendering previews, LOOKING at the frames, fixing what is wrong, and iterating - then finishing.

EVERY answer is ONE JSON object and nothing else:
{"say": "one or two sentences: what you saw / what you will do", "actions": [ up to 4 action objects, executed in order ]}

Actions (each is an object with a "tool" key):
  {"tool":"write_file","path":"scene.py","content":"<the COMPLETE file>"}     also allowed: parts/<name>.py (helper modules) and custom/<name>.py (reusable components)
  {"tool":"read_file","path":"docs/CODE_API.md","start":0}                  docs/CODE_API.md, docs/LIBRARY.md, examples/code_scene.py, custom/INDEX.md, mgl/*.py ...
  {"tool":"check"}                          import scene.py, render 3 frames, report errors and speed
  {"tool":"preview","times":[0.5,2,3.5]}    contact sheet image of up to 12 frames (you will SEE it)
  {"tool":"frame","t":3.2}                  one larger frame to inspect details
  {"tool":"qa"}                             automatic checks: text cut off / overlapping / low contrast / too small, blank or static video
  {"tool":"register","name":"ripples"}      smoke-test custom/<name>.py and save it for all future videos
  {"tool":"finish","notes":"what you built and why"}   renders the final MP4. Only when previews look professional and qa has no errors.

How to work:
1. Read the reference below (docs and example are included). Plan scenes with DIFFERENT layouts and animations; follow the brand kit and the lessons.
2. Write the complete scene.py, then in the SAME turn add check and preview so you immediately see the result.
3. Look at the frames critically (hierarchy, spacing, colours, overlaps, motion variety, professional feel). Fix specific problems with specific edits; always send the complete file.
4. Use layer(...) for things the JSON library already does well and numpy/OpenCV code for custom effects. If an effect should be reusable, put it in custom/<name>.py and register it.
5. Run qa before finish and fix every error. Do not waste turns: batch write + check + preview + qa when you are confident.
6. You have a limited number of turns (shown in each message). Finish before they run out."""


def build_system(size_key, root=ROOT):
    api = open(os.path.join(root, 'studio', 'CODE_API.md'), encoding='utf-8').read()
    lib = open(os.path.join(root, 'LIBRARY.md'), encoding='utf-8').read().replace('{{CANVAS}}', AG.canvas_text(size_key))
    ex = open(os.path.join(root, 'examples', 'code_scene.py'), encoding='utf-8').read()
    idx_p = os.path.join(root, 'custom', 'INDEX.md')
    idx = open(idx_p, encoding='utf-8').read() if os.path.exists(idx_p) else '(no custom components yet)'
    return (SYSTEM + '\n\n=== CODE SCENE REFERENCE ===\n' + api + '\n\n=== EXAMPLE scene.py (works; study it) ===\n' + ex +
            '\n\n=== CUSTOM COMPONENTS ALREADY WRITTEN (reuse them: from custom.<name> import *) ===\n' + idx[:3500] +
            '\n\n=== JSON LIBRARY (what layer(...) accepts) ===\n' + lib)


def first_message(prompt, duration, size_key, assets, mem_ctx, has_reference, style_card, images, turns):
    t = ('TASK: make this video with code.\nBRIEF: %s\nDURATION: %s seconds (DURATION = %s in scene.py)\n%s\n' % (prompt.strip(), duration, duration, AG.canvas_text(size_key)))
    t += 'You have %d turns.\n' % turns
    if assets: t += '\nUploaded assets (load with image(path)):\n- ' + '\n- '.join(assets) + '\n'
    else: t += '\nNo uploaded assets. Draw everything yourself or use layer(...) with image "search" layers (photo/icon/vector search).\n'
    if images: t += '\nAnimate and feature these uploaded images: %s (the attached pictures show them).\n' % ', '.join(images)
    if has_reference:
        t += ('\nREFERENCE VIDEO: the attached contact sheets show a reference video. Recreate its structure, pacing, layouts, motion and transitions with the content of the brief; do not copy its text.\n')
        if style_card: t += 'Analysis: ' + json.dumps({k: v for k, v in style_card.items() if k not in ('sha', 'source', 'date', 'id')}, ensure_ascii=False)[:2200] + '\n'
    if mem_ctx: t += '\n=== MEMORY (follow it) ===\n' + mem_ctx + '\n'
    t += '\nStart now. Answer with the JSON object only.'
    return t


def _fmt_err(r):
    return '%s\n%s' % (r.get('error', 'error'), (r.get('traceback') or '').strip()[-1400:])


def run_code_agent(prompt, duration, out_dir, ask, size='16:9', images=None, reference=None, mem=None, root=ROOT, max_turns=16,
                   log=print, update_memory=True, sandbox_timeout=150, final_timeout=None):
    os.makedirs(out_dir, exist_ok=True)
    size_key = E.norm_size(size) or '16:9'
    mem = mem or Memory(root)
    images = [p for p in (images or []) if os.path.isfile(os.path.join(root, p))]
    for p in AG.list_assets(root):
        rel = p.split(' (')[0]
        if os.path.basename(rel).lower() in prompt.lower() and rel not in images: images.append(rel)
    sb = Sandbox(root, log)
    report = ['# Code Studio report', '', 'Brief: %s' % prompt, 'Size: %s   Duration: %ss' % (size_key, duration), '']
    parts, style_card = [], None
    try:
        if reference:
            sheets, rinfo = RF.frame_sheets(reference, per_sheet=12, sheets=2)
            sha = RF.video_sha(reference)
            style_card = next((s for s in mem.styles if s.get('sha') == sha), None)
            parts += [gemini.image_part(png) for png in sheets]
            report.append('Reference video: %s' % os.path.basename(reference))
        parts += AG.attach_images(images, root)
        msg0 = {'role': 'user', 'parts': [gemini.text_part(first_message(prompt, duration, size_key, AG.list_assets(root), mem.context_for_prompt(prompt),
                                                                           bool(reference), style_card, images, max_turns))] + parts}
        system = build_system(size_key, root)
        pairs = []                      # [(model_msg, user_msg)] of finished turns
        state = {'previewed': False, 'qa_clean': False, 'qa_seen': None, 'qa_first': None, 'registered': [], 'errors': [], 'finished': False, 'turns': 0, 'wrote': False}
        notes = ''

        def invalidate():
            state['previewed'] = False; state['qa_clean'] = False

        for turn in range(1, max_turns + 1):
            state['turns'] = turn
            left = max_turns - turn
            hist = [msg0] + [m for pair in pairs[-3:] for m in pair]          # first message + the last 3 (model answer, results) pairs
            log('[turn %d/%d]' % (turn, max_turns))
            txt = ask(system, hist)
            model_msg = {'role': 'model', 'parts': [gemini.text_part(txt)]}
            lines, imgs = [], []
            try:
                obj = gemini.extract_json(txt)
                actions = obj.get('actions') if isinstance(obj, dict) else None
                if not isinstance(actions, list): raise ValueError('JSON must be {"say": ..., "actions": [...]}')
                say = str(obj.get('say', ''))[:300]
                if say: log('   ' + say)
            except Exception as ex:
                actions = []
                lines.append('Your answer was not the required JSON object (%s). Answer with {"say": "...", "actions": [...]} only.' % ex)
            write_failed = False
            if len(actions) > 4: lines.append('Only the first 4 actions of a turn are executed; %d extra action(s) were ignored - send them next turn.' % (len(actions) - 4))
            for ai, a in enumerate(actions[:4]):
                tool = a.get('tool') if isinstance(a, dict) else None
                if tool not in TOOLS:
                    lines.append('[%s] unknown tool. Tools: %s' % (tool, ', '.join(TOOLS))); continue
                if write_failed and tool in ('check', 'preview', 'frame', 'qa', 'finish'):
                    lines.append('[%s] skipped because the write_file before it failed' % tool); continue
                if tool == 'write_file':
                    ok, m = sb.write(a.get('path', ''), a.get('content', ''))
                    lines.append('[write_file] ' + m)
                    if ok: invalidate(); state['wrote'] = True
                    else: write_failed = True; state['errors'].append(m.splitlines()[0][:140])
                elif tool == 'read_file':
                    txt_, err = sb.read(a.get('path', ''), a.get('start', 0))
                    lines.append('[read_file %s]\n%s' % (a.get('path'), txt_ if err is None else err))
                elif tool == 'check':
                    r = sb.run('check', {}, sandbox_timeout)
                    if r['ok']: lines.append('[check] OK  (%.2f s per frame)%s' % (r.get('seconds_per_frame', 0), ('  WARNING: ' + r['warning']) if r.get('warning') else ''))
                    else: lines.append('[check] FAILED: ' + _fmt_err(r)); state['errors'].append(r.get('error', '')[:140])
                elif tool == 'preview':
                    times = [float(x) for x in (a.get('times') or []) if isinstance(x, (int, float))][:12] or None
                    r = sb.run('frames', {'times': times} if times else {}, sandbox_timeout)
                    if r['ok']:
                        p = sb.out_file('preview.png'); imgs.append(gemini.image_part(open(p, 'rb').read())); state['previewed'] = True
                        lines.append('[preview] contact sheet attached for times %s (%.2f s per frame)' % ([round(x, 1) for x in r.get('times', [])], r.get('seconds_per_frame', 0)))
                    else: lines.append('[preview] FAILED: ' + _fmt_err(r)); state['errors'].append(r.get('error', '')[:140])
                elif tool == 'frame':
                    r = sb.run('frame', {'t': a.get('t', 0)}, sandbox_timeout)
                    if r['ok']: imgs.append(gemini.image_part(open(sb.out_file('frame.png'), 'rb').read())); lines.append('[frame] t=%.2f attached' % r.get('t', 0))
                    else: lines.append('[frame] FAILED: ' + _fmt_err(r)); state['errors'].append(r.get('error', '')[:140])
                elif tool == 'qa':
                    r = sb.run('qa', {}, sandbox_timeout * 2)
                    if r['ok']:
                        state['qa_clean'] = not r['errors']; state['qa_seen'] = r
                        if state['qa_first'] is None: state['qa_first'] = r
                        lines.append('[qa] %d error(s), %d warning(s)\n%s' % (len(r['errors']), len(r['warnings']), '\n'.join('ERROR: ' + x for x in r['errors']) + '\n' + '\n'.join('warning: ' + x for x in r['warnings'])))
                    else: lines.append('[qa] FAILED: ' + _fmt_err(r)); state['errors'].append(r.get('error', '')[:140])
                elif tool == 'register':
                    name = re.sub(r'[^a-z0-9_]', '', str(a.get('name', '')).lower())
                    ok, m = sb.register_custom(name, root, size_key)
                    lines.append('[register] ' + m)
                    if ok and name not in state['registered']: state['registered'].append(name)
                elif tool == 'finish':
                    if (not state['wrote']):
                        lines.append('[finish] REFUSED: you have not written scene.py yet.'); continue
                    if (not state['previewed'] or not state['qa_clean']) and left >= 1:
                        lines.append('[finish] NOT YET: %s. Run preview and qa (fix every qa error) in this scene version, then finish.' %
                                     ('no preview of the current scene' if not state['previewed'] else 'qa has not passed for the current scene'))
                        continue
                    notes = str(a.get('notes', ''))[:400]
                    chk = sb.run('check', {}, sandbox_timeout)
                    if not chk['ok']:
                        lines.append('[finish] FAILED: scene does not run: ' + _fmt_err(chk)); continue
                    state['finished'] = True
                    break
            if state['finished']: break
            lines.append('Turns left: %d.%s' % (left, ' This is your LAST turn: finish now (the scene must pass check).' if left == 0 else ''))
            src = sb.scene_source()
            body = '\n'.join(lines)
            if src: body += '\n\nCURRENT scene.py (%d lines):\n```python\n%s\n```' % (src.count('\n') + 1, src[:16000])
            pairs.append((model_msg, {'role': 'user', 'parts': [gemini.text_part(body)] + imgs}))
        # ---------------------------------------------------------------- after the loop
        if not state['finished']:
            if state['wrote']:
                chk = sb.run('check', {}, sandbox_timeout)
                if chk['ok']:
                    log('turn limit reached - rendering the current scene')
                    state['finished'] = True; report.append('Turn limit reached; rendered the last working scene.')
                else:
                    raise AG.AgentError('ran out of turns and scene.py does not run: %s' % chk.get('error'))
            else:
                raise AG.AgentError('ran out of turns before a scene was written')
        src = sb.scene_source()
        dur = float(duration)
        log('[render] final video ...')
        r = sb.run('video', {}, final_timeout or max(400, int(dur * 30 * 2.5)))
        if not r['ok']: raise AG.AgentError('final render failed: ' + _fmt_err(r))
        shutil.copy(sb.out_file('video.mp4'), os.path.join(out_dir, 'video.mp4'))
        pr = sb.run('frames', {'times': [dur * (0.03 + 0.94 * i / 11) for i in range(12)]}, sandbox_timeout)
        if pr['ok']: shutil.copy(sb.out_file('preview.png'), os.path.join(out_dir, 'preview.png'))
        open(os.path.join(out_dir, 'scene.py'), 'w', encoding='utf-8').write(src)
        for f in sorted(os.listdir(os.path.join(sb.root, 'parts'))):
            shutil.copy(os.path.join(sb.root, 'parts', f), os.path.join(out_dir, 'parts_' + f))
        qa_final = state['qa_seen'] or {'errors': [], 'warnings': []}
        did = None
        if update_memory:
            try:
                did = mem.add_code_design(prompt, src, notes, size_key, duration, qa_final)
                first = state['qa_first'] or qa_final
                new = mem.add_lessons(LN.lessons_from_qa(first['errors'] + first['warnings']), 'qa')
                new += mem.add_lessons([{'kind': 'dont', 'text': 'Code scenes: avoid this error seen earlier - %s' % e[:150], 'weight': 1} for e in list(dict.fromkeys(state['errors']))[:3] if len(e) > 12], 'code')
                mem.log('## %s - code mode %s\nBrief: %s\nTurns used: %d. QA at first check: %d error(s), %d warning(s); at the end: %d / %d. Errors met: %s. New components: %s.\nNotes: %s' % (
                    did, size_key, prompt[:140], state['turns'], len(first['errors']), len(first['warnings']), len(qa_final['errors']), len(qa_final['warnings']),
                    '; '.join(dict.fromkeys(state['errors'])) or 'none', ', '.join(state['registered']) or 'none', notes or '-'))
                mem.save()
                report += ['## What I learned this time', 'Turns used: %d of %d. Errors met on the way: %s' % (state['turns'], max_turns, '; '.join(dict.fromkeys(state['errors'])) or 'none'),
                           'QA at the end: %d error(s), %d warning(s). New reusable components: %s.' % (len(qa_final['errors']), len(qa_final['warnings']), ', '.join(state['registered']) or 'none'),
                           'Notes from the bot: %s' % (notes or '-'), 'Design id: `%s`. Rate it with the workflow mode "feedback".' % did]
            except Exception as ex:
                log('   memory update failed: %s' % ex); report.append('Memory update failed: %s' % ex)
        report += ['', 'Gemini requests used: %s of %s. Models: %s' % (getattr(ask, 'calls', '?'), getattr(ask, 'budget', '?'), ', '.join(getattr(ask, 'used', []) or ['(n/a)']))]
        open(os.path.join(out_dir, 'report.md'), 'w', encoding='utf-8').write('\n'.join(report))
        return {'scene': src, 'design_id': did, 'turns': state['turns'], 'registered': state['registered'], 'qa': qa_final}
    finally:
        sb.cleanup()
