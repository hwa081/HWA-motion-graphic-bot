#!/usr/bin/env python3
"""Entry point used by the GitHub workflow (and handy locally).

    python run.py --mode demo                          # no AI, no key: renders examples/saas_intro.json
    python run.py --mode spec --files my.json          # render your own JSON spec (image "search" layers are resolved too)
    python run.py --mode qa --files my.json            # automatic quality report for a spec (no key needed)
    python run.py --mode reference                     # renders the 14 s reference intro recipe
    python run.py --mode check                         # tests your Gemini key
    python run.py --mode assets-check                  # tests Pixabay / Pexels / Iconify live
    python run.py --mode ai --prompt "..." --duration 10 --size 9:16 --files "assets/shot.png,reference/promo.mp4"
    python run.py --mode code --prompt "..." --duration 12      # Code Studio: the AI writes, runs, looks at and fixes Python scene code
    python run.py --mode learn --files reference       # analyse reference videos in a folder and remember their design
    python run.py --mode compare --files reference/example.mp4,out/video.mp4    # how close is my video to the example? (numbers + AI), the bot learns from the gaps
    python run.py --mode remix --prompt "..." --duration 12                      # invent a NEW design plan from old designs (no key needed)
    python run.py --mode study --prompt "text or URL about a technique"          # teach the bot a new technique (saved in memory/notebook.json)
    python run.py --mode evolve                                                  # build the most wanted missing effect with Code Studio (custom/)
    python run.py --mode feedback --rating 4 --prompt "loved the cards, too fast at the end" [--design-id d-...]
    python run.py --mode index-canva                   # let the AI tag your Canva exports in assets/canva/
    python run.py --mode export --files out/video.mp4 --formats all      # make .wfp / .fcpxml / .xml / gif ... from an existing video
    python run.py --mode lighten --files projects/my.wfp --level 3       # make a .wfp lighter (project data stays identical)

Every video mode also writes the formats listed in --formats (default: wfp,fcpxml,xml; "all", "none" or any list of
wfp, fcpxml, xml, srt, gif, webm, poster, frames, mp4-light). --media-dir is where the MP4 will live on YOUR PC.
"""
import json, argparse, json, os, runpy, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
VIDEO_EXT = ('.mp4', '.mov', '.webm', '.mkv', '.m4v', '.avi', '.gif')
IMAGE_EXT = ('.png', '.jpg', '.jpeg', '.webp')


def get_key():
    return os.environ.get('GEMINI_API_KEY', '').strip().strip('"\'')


def get_providers():
    """Gemini + every OpenAI-compatible AI added in the Studio page (keys come from repository secrets)"""
    from mgl import llm
    llm.absorb_secrets()
    return llm.providers_from_env()


def make_ask(required=True, budget=None):
    import agent
    from mgl import llm
    provs = get_providers()
    if not provs:
        if required:
            print('No AI key found. Add GEMINI_API_KEY as a repository secret (Settings -> Secrets and variables -> Actions), or add an AI key in the Studio page -> Settings.')
        return None
    wanted = (os.environ.get('AI') or os.environ.get('AI_PROVIDER') or 'gemini').strip()
    fallback = os.environ.get('AI_FALLBACK', 'true').strip().lower() not in ('false', '0', 'no', 'off')
    chain = llm.order(provs, wanted, fallback)
    if len(chain) == 1 and chain[0].kind == 'gemini':
        return agent.make_ask(chain[0].key, budget=budget)           # the classic path (Gemini only)
    if budget is None:
        budget = int(os.environ.get('MAX_REQUESTS', agent.DEFAULT_BUDGET) or agent.DEFAULT_BUDGET)
    print('AI order: %s' % ' -> '.join('%s%s' % (p.name, ' (%s)' % p.model if p.model else '') for p in chain))
    return llm.make_multi_ask(chain, budget, budget_error=agent.BudgetError)


def E_norm(size):
    from mgl import engine as E
    return E.norm_size(size) or '16:9'


def split_files(s):
    return [x.strip() for x in (s or '').replace('\n', ',').split(',') if x.strip()]


def slug(text, default='motion_graphic'):
    import re
    t = re.sub(r'[^A-Za-z0-9]+', '_', (text or '')).strip('_')[:40]
    return t or default


def do_exports(out, formats, media_dir, split, audio='', sound='kinetic'):
    """Music + sfx (from the plan), then the editor/project formats next to out/video.mp4 (never stops the run if one of them fails)."""
    from mgl import export as X
    audio_done = False
    sp0 = os.path.join(out, 'spec.json')
    sound = (sound or 'none').strip().lower()
    if audio and not os.path.isfile(audio):
        print('audio file not found: %s (upload it into the repo first)' % audio); audio = ''
    if os.path.isfile(os.path.join(out, 'video.mp4')) and (audio or (sound != 'none' and os.path.isfile(sp0))):
        try:
            from mgl import sound as SND
            wav = audio
            if not wav:
                spec0 = json.load(open(sp0, encoding='utf-8'))
                wav = os.path.join(out, 'music_sfx.wav')
                info = SND.compose(spec0, wav, style=sound)
                print('sound (%s): %d sound effects %s' % (info['style'], info['sfx_count'], dict(info['sfx'])))
            nm = slug(json.load(open(sp0, encoding='utf-8')).get('title', '')) if os.path.isfile(sp0) else 'motion_graphic'
            X.add_audio(os.path.join(out, 'video.mp4'), wav, os.path.join(out, nm + '_with_sound.mp4'))
            print('video with sound -> %s_with_sound.mp4 (picture is copied untouched)' % nm)
            audio_done = True
        except Exception as ex:
            print('sound failed (the silent video is still there): %s' % ((getattr(ex, 'stderr', b'') or b'').decode('utf-8', 'ignore')[-300:] or ex))
    audio = ''
    try:
        fm = X.parse_formats(formats)
    except ValueError as ex:
        print('formats: %s' % ex); return
    if not fm:
        return
    spec = None
    sp = os.path.join(out, 'spec.json')
    if os.path.isfile(sp):
        try: spec = json.load(open(sp, encoding='utf-8'))
        except Exception: spec = None
    name = slug((spec or {}).get('title', ''))
    cuts = X.cuts_from_spec(spec) if (spec and str(split).lower() in ('auto', 'true', '1', 'yes')) else []
    print('\nExporting: %s' % ', '.join(fm))
    if audio and not os.path.isfile(audio):
        print('audio file not found: %s (upload it into the repo first)' % audio); audio = ''
    vid = os.path.join(out, name + '_with_sound.mp4') if audio_done and os.path.isfile(os.path.join(out, name + '_with_sound.mp4')) else None
    files, problems = X.export_all(out, fm, media_dir, video=vid, name=name, cuts=cuts, spec=spec)
    for pr in problems: print('export problem:', pr)


def mode_export(files, out, formats, media_dir, split, audio='', sound='none'):
    if not files or not os.path.isfile(files[0]):
        print('Give the video: --files out/video.mp4 (an MP4 inside the repo)'); return 1
    spec_next = os.path.join(os.path.dirname(files[0]), 'spec.json')
    if audio or (sound not in ('', 'none') and os.path.isfile(spec_next)):
        import shutil
        shutil.copy(files[0], os.path.join(out, 'video.mp4'))
        if os.path.isfile(spec_next): shutil.copy(spec_next, os.path.join(out, 'spec.json'))
        do_exports(out, formats or 'default', media_dir, split, audio, sound)
        return 0
    from mgl import export as X
    video = files[0]
    work = out
    if os.path.abspath(os.path.dirname(video)) != os.path.abspath(out):
        import shutil
        shutil.copy(video, os.path.join(out, os.path.basename(video)))
        video = os.path.join(out, os.path.basename(video))
    fm = X.parse_formats(formats if formats.strip() not in ('', 'none') else 'default')
    spec = None
    sp = os.path.join(os.path.dirname(files[0]), 'spec.json')
    if os.path.isfile(sp):
        try: spec = json.load(open(sp, encoding='utf-8'))
        except Exception: spec = None
    cuts = X.cuts_from_spec(spec) if (spec and str(split).lower() in ('auto', 'true', '1', 'yes')) else []
    got, problems = X.export_all(work, fm, media_dir, video=video, name=slug(os.path.splitext(os.path.basename(video))[0]), cuts=cuts, spec=spec)
    for pr in problems: print('export problem:', pr)
    return 0 if got and not problems else 1


def mode_lighten(files, out, level):
    from mgl import wfp_light as W
    if not files:
        print('Give the project: --files projects/my.wfp (upload the .wfp into the repo first)'); return 1
    try:
        lv = int(float(level or 3))
    except ValueError:
        print('level must be 1, 2 or 3'); return 1
    rc, lines = 0, ['# Lighter project files', '']
    for f in files:
        if not os.path.isfile(f) or not f.lower().endswith('.wfp'):
            print('not a .wfp file: %s' % f); rc = 1; continue
        dst = os.path.join(out, os.path.splitext(os.path.basename(f))[0] + '_light.wfp')
        try:
            line = W.report(W.lighten(f, dst, lv))
        except Exception as ex:
            line = '%s: FAILED (%s)' % (f, ex); rc = 1
        print(line); lines.append('- ' + line)
    lines += ['', 'Level 1 = repack + whitespace only. 2 = + lossless PNG re-encode. 3 = + smaller media-bin thumbnails (render always uses your real files).',
              'Your original file is never touched.']
    open(os.path.join(out, 'lighten_report.md'), 'w', encoding='utf-8').write('\n'.join(lines))
    return rc


def mode_design(design_id, prompt, out, a):
    """render a ready design from the library (by id), or list the best matches for --prompt"""
    from mgl import library as LB
    if not LB.load(ROOT):
        print('library/designs.json missing'); return 1
    did = design_id.strip()
    if not did:
        hits = LB.search(prompt or 'documentary', 8, ROOT)
        lines = ['Best matches (use --design-id <id> to render one):'] + ['- %s | %s | %s' % (d['id'], d['title'], d['topic']) for d in hits]
        print('\n'.join(lines)); open(os.path.join(out, 'design_matches.md'), 'w', encoding='utf-8').write('\n'.join(lines)); return 0
    sp = LB.spec_of(did, ROOT)
    if sp is None:
        print('unknown design id: %s' % did); return 1
    path = os.path.join(out, did + '.json'); json.dump(sp, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    d = [x for x in LB.load(ROOT) if x['id'] == did][0]
    open(os.path.join(out, did + '_narration.txt'), 'w', encoding='utf-8').write('\n'.join('%.1fs  %s' % (x['t'], x['text']) for x in d['script']))
    return render_spec_file(path, out, a.formats, a.media_dir, a.split, a.audio, d['sound'] if a.sound == 'kinetic' and d['sound'] == 'ui' else a.sound)


def mode_native(files, out):
    """native Filmora project: shapes + text as real editable layers (no video). --files my_scene.json, or the built-in demo scene"""
    from mgl import native_wfp as N
    scene = N.demo_scene() if not files else json.load(open(files[0], encoding='utf-8'))
    name = slug(scene.get('title', ''), 'MotionBot_Native')
    res = N.build(os.path.join(out, name + '.wfp'), name, scene)
    print('native wfp: %s (%d clips, %d timelines) problems: %s' % (res['path'], res['clips'], res['timelines'], res['problems'] or 'none'))
    return 1 if res['problems'] else 0


def mode_designs_pdf(out):
    try:
        from libgen import pdf as P
    except Exception as ex:
        print('PDF builder not available: %s' % ex); return 1
    return P.build(os.path.join(out, 'design_library.pdf'))


def mode_checks(out):
    """test every saved key from inside GitHub (the real test: it uses the stored secrets). Writes outputs/checks.json for the Studio page"""
    import datetime, urllib.request, urllib.error
    from mgl import llm
    res = []
    def add(pid, name, group, ok, msg):
        res.append({'id': pid, 'name': name, 'group': group, 'ok': ok, 'msg': msg}); print('%s %-12s %s' % ('OK    ' if ok else ('SKIP  ' if ok is None else 'FAILED'), name, msg))
    def get(url, headers=None):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=dict({'User-Agent': 'motion-graphic-bot'}, **(headers or {}))), timeout=25) as r:
                return r.status, json.loads(r.read().decode('utf-8', 'replace') or '{}')
        except urllib.error.HTTPError as e: return e.code, {}
        except Exception as ex: return 0, {'error': str(ex)}
    for p in get_providers():
        ok, msg = llm.test_provider(p); add(p.id, p.name, 'ai', ok, msg)
    if not any(r['group'] == 'ai' for r in res): add('gemini', 'Gemini', 'ai', None, 'no AI key saved yet')
    k = os.environ.get('PIXABAY_API_KEY', '').strip()
    if k:
        st, j = get('https://pixabay.com/api/?key=%s&q=nature&per_page=3' % k); add('pixabay', 'Pixabay', 'photos', st == 200 and bool(j.get('hits')), 'works (%s photos)' % j.get('totalHits') if st == 200 else 'HTTP %s - key rejected or blocked' % st)
    else: add('pixabay', 'Pixabay', 'photos', None, 'no key saved')
    k = os.environ.get('PEXELS_API_KEY', '').strip()
    if k:
        st, j = get('https://api.pexels.com/v1/search?query=nature&per_page=1', {'Authorization': k}); add('pexels', 'Pexels', 'photos', st == 200, 'works' if st == 200 else 'HTTP %s - key rejected or blocked' % st)
    else: add('pexels', 'Pexels', 'photos', None, 'no key saved')
    st, j = get('https://api.iconify.design/search?query=home&limit=1'); add('iconify', 'Iconify', 'icons', st == 200, 'works (no key needed)' if st == 200 else 'HTTP %s' % st)
    os.makedirs(os.path.join(ROOT, 'outputs'), exist_ok=True)
    doc = {'date': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'), 'job': os.environ.get('JOB', ''), 'results': res}
    json.dump(doc, open(os.path.join(ROOT, 'outputs', 'checks.json'), 'w'), indent=1)
    open(os.path.join(out, 'checks_report.md'), 'w', encoding='utf-8').write('# Key checks\n\n' + '\n'.join('- %s: %s - %s' % (r['name'], {True: 'OK', False: 'FAILED', None: 'not set'}[r['ok']], r['msg']) for r in res))
    return 0 if all(r['ok'] is not False for r in res) else 1


def mode_check():
    from mgl import gemini, llm
    key = get_key()
    if not key and get_providers():
        for p in get_providers():
            ok, msg = llm.test_provider(p); print('%s: %s - %s' % (p.name, 'KEY WORKS' if ok else 'KEY TEST FAILED', msg))
        return 0
    if not key:
        print('NO KEY: the secret GEMINI_API_KEY is empty or missing.\n'
              'Repository -> Settings -> Secrets and variables -> Actions -> New repository secret -> Name: GEMINI_API_KEY')
        return 1
    print('key found (%d characters)' % len(key))
    try:
        models = gemini.choose_models(key)
        print('models that will be tried:', ', '.join(models))
        txt, model = gemini.ask(key, models, None, [{'role': 'user', 'parts': [gemini.text_part('Reply with the single word OK')]}], json_mode=False)
        print('Gemini (%s) answered: %s' % (model, txt.strip()[:80]))
        print('KEY WORKS')
        return 0
    except gemini.GeminiError as ex:
        print('KEY TEST FAILED:', ex)
        print('Hints: 400/401/403 -> key wrong, copied with spaces, or not allowed in your country/project; '
              '429 -> free limit reached, try again later; 404 -> model name not available (set the GEMINI_MODEL variable).')
        return 1


def render_spec_file(path, out, formats='', media_dir='', split='auto', audio='', sound='kinetic'):
    import render as R
    from mgl import spec as S, qa as QA, assets as A
    from mgl.memory import Memory
    if not os.path.isfile(path):
        print('spec file not found: %s' % path); return 1
    sp = R.load_spec(path)
    errs, warns = S.validate(sp, ROOT)
    for w in warns: print('warning:', w)
    if errs:
        print('SPEC ERRORS:'); [print(' -', e) for e in errs]; return 1
    mem = Memory(ROOT)
    if any(isinstance(L, dict) and L.get('type') == 'image' and 'search' in L and 'path' not in L for L in sp['layers']):
        ask = make_ask(required=False, budget=8)
        sp, rep = A.resolve_spec(sp, ROOT, mem, ask, A.make_providers(ROOT, mem), '')
        for r in rep: print('asset %s "%s": %s (%s)' % (r['section'], r['query'], r['chosen'] or 'NOT USED', r['reason']))
        mem.save()
        errs, _ = S.validate(sp, ROOT)
        if errs:
            print('SPEC ERRORS after asset search:'); [print(' -', e) for e in errs]; return 1
    rep = QA.analyze(sp, ROOT)
    lines = ['# Automatic quality report', ''] + ['ERROR: ' + x for x in rep['errors']] + ['warning: ' + x for x in rep['warnings']]
    if len(lines) == 2: lines.append('No problems found.')
    open(os.path.join(out, 'qa.md'), 'w', encoding='utf-8').write('\n'.join(lines))
    print('\n'.join(lines))
    ctx = S.Context(ROOT)
    R.preview_sheet(sp, os.path.join(out, 'preview.png'), ctx)
    R.render_video(sp, os.path.join(out, 'video.mp4'), ctx)
    for w in ctx.warnings: print('render warning:', w)
    json.dump(sp, open(os.path.join(out, 'spec.json'), 'w'), indent=1, ensure_ascii=False)
    do_exports(out, formats, media_dir, split, audio, sound)
    print('done ->', out)
    return 0


def mode_qa(path):
    from mgl import spec as S, qa as QA
    import render as R
    if not os.path.isfile(path):
        print('spec file not found: %s' % path); return 1
    sp = R.load_spec(path)
    errs, warns = S.validate(sp, ROOT)
    if errs:
        print('SPEC ERRORS:'); [print(' -', e) for e in errs]; return 1
    rep = QA.analyze(sp, ROOT)
    for x in rep['errors']: print('ERROR  :', x)
    for x in rep['warnings']: print('warning:', x)
    if not rep['errors'] and not rep['warnings']: print('No problems found.')
    return 1 if rep['errors'] else 0


def mode_learn(folder, out):
    from mgl import reference as RF
    from mgl.memory import Memory
    ask = make_ask(budget=int(os.environ.get('LEARN_REQUESTS', '14') or 14))
    if ask is None: return 1
    mem = Memory(ROOT)
    limit = int(os.environ.get('LEARN_LIMIT', '5') or 5)
    try:
        new, skipped, failed = RF.learn_folder(mem, ask, folder, limit=limit)
    except FileNotFoundError as ex:
        print(ex); print('Create the folder in the repo (Add file -> Upload files) and put the reference videos in it.'); return 1
    guide = None
    if len(mem.styles) >= 2 and (new or not mem.style_guide()):
        try:
            guide = RF.synthesize_style_guide(mem, ask)
            print('style guide written (%d characters)' % len(guide or ''))
        except Exception as ex:
            print('style guide skipped: %s' % ex)
    mem.save()
    lines = ['# Learning report', '', 'Folder: %s' % folder, 'Newly analysed (%d): %s' % (len(new), ', '.join(c['source'] + ' -> ' + c['title'] for c in new) or '-'),
             'Already known (%d): %s' % (len(skipped), ', '.join(skipped) or '-'), 'Failed (%d): %s' % (len(failed), '; '.join('%s: %s' % f for f in failed) or '-'),
             'Total remembered styles: %d' % len(mem.styles), 'Gemini requests used: %d' % ask.calls]
    open(os.path.join(out, 'learn_report.md'), 'w', encoding='utf-8').write('\n'.join(lines))
    print('\n'.join(lines))
    if not new and not skipped:
        print('No reference videos could be analysed.' if failed else 'The folder has no video files (%s).' % ', '.join(VIDEO_EXT))
        return 1
    return 0



def mode_compare(files, out, prompt=''):
    """example video  vs  your video (or a JSON spec): measured fidelity + side-by-side sheet; the bot learns from the gaps"""
    from mgl import compare as CP
    from mgl.memory import Memory
    if len(files) < 2 or not os.path.isfile(files[0]) or not os.path.isfile(files[1]):
        print('Give two files: --files <example video>,<your video or spec.json>   (both must be inside the repo)'); return 1
    ref_path, other = files[0], files[1]
    try:
        dur = CP.video_frames(ref_path, 3)[1]['duration']
        if other.lower().endswith('.json'):
            sp = json.load(open(other, encoding='utf-8')); dur = max(dur, float(sp.get('duration', dur)))
        else:
            dur = max(dur, CP.video_frames(other, 3)[1]['duration'])
        n = CP.n_samples(dur)
        rf, ri = CP.video_frames(ref_path, n)
        if other.lower().endswith('.json'): of, oi = CP.spec_frames(sp, ROOT, n)
        else: of, oi = CP.video_frames(other, n)
    except Exception as ex:
        print('could not read the files: %s' % ex); return 1
    res = CP.compare(CP.profile(rf, ri), CP.profile(of, oi))
    sheet = CP.side_by_side(rf, of, os.path.join(out, 'compare.png'))
    ai = None
    mem = Memory(ROOT)
    ask = make_ask(required=False, budget=3)
    if ask is not None:
        try:
            ai = CP.ai_compare(ask, sheet, res, prompt)
        except Exception as ex:
            print('AI judgement skipped: %s' % ex)
    else:
        print('(no GEMINI_API_KEY: only the measured comparison; add the key for the AI judgement and for learning new techniques)')
    nl, nt = CP.learn_from(mem, res, ai, source='compare')
    mem.save()
    rep = CP.report_md(os.path.basename(ref_path), os.path.basename(other), res, ai, 'Learned: %d new lesson(s), %d new technique(s).' % (nl, nt))
    open(os.path.join(out, 'compare_report.md'), 'w', encoding='utf-8').write(rep)
    print(rep)
    return 0


def mode_remix(prompt, duration, size, out):
    """a new design plan made from old designs (library + memory); no AI, no key"""
    from mgl import remix as RX, library as LB
    from mgl.memory import Memory
    if not prompt.strip():
        print('Write a prompt (the topic of the video).'); return 1
    mem = Memory(ROOT)
    try: d = float(duration)
    except ValueError: d = 10.0
    rc = RX.make_recipe(prompt, ROOT, mem, int(d) if d.is_integer() else d, size)
    lines = ['# Remix recipe', '', 'Brief: %s' % prompt, '', rc['text']]
    tq = mem.techniques_for(prompt, 3)
    if tq: lines += ['', '## Techniques from the notebook that fit'] + ['- **%s**: %s' % (t['name'], t['how']) for t in tq]
    lines += ['', 'Run mode **ai** with this prompt to let the bot build it (the recipe is added automatically, a different one each time).']
    open(os.path.join(out, 'remix.md'), 'w', encoding='utf-8').write('\n'.join(lines))
    print('\n'.join(lines))
    return 0


def mode_study(prompt, files, out):
    """teach the bot a technique from text / a URL / a .txt file; saved in memory/notebook.json"""
    from mgl import study as ST
    from mgl.memory import Memory
    try:
        text, label = ST.material(prompt, files, ROOT)
    except Exception as ex:
        print('%s' % ex); return 1
    ask = make_ask(budget=3)
    if ask is None: return 1
    mem = Memory(ROOT)
    try:
        new, cards = ST.study(ask, text, mem, ROOT, label)
    except Exception as ex:
        print('study failed: %s' % ex); return 1
    mem.save()
    lines = ['# Study report', '', 'Source: %s (%d characters)' % (label, len(text)), 'New techniques: %d' % new, ''] + [
        '- **%s**: %s%s' % (c['name'], c['how'], ' (with a tested example spec)' if c.get('spec') else '') for c in cards]
    if not cards: lines.append('- nothing new (the techniques were already known or could not be built with the library)')
    lines += ['', 'Total techniques in the notebook: %d' % len(mem.notebook['techniques'])]
    open(os.path.join(out, 'study_report.md'), 'w', encoding='utf-8').write('\n'.join(lines))
    print('\n'.join(lines))
    return 0


def mode_evolve(out, size='16:9'):
    """build the most wanted missing effect (from the wishlist) as a reusable custom component with Code Studio"""
    import re as _re
    from mgl.memory import Memory
    mem = Memory(ROOT)
    wishes = mem.open_wishes(1)
    if not wishes:
        print('The wishlist is empty. Wishes are added when the planner wants an effect the library cannot do (mode ai with PLAN on).'); return 0
    w = wishes[0]
    turns = int(os.environ.get('CODE_TURNS', '16') or 16)
    ask = make_ask(budget=int(os.environ.get('CODE_REQUESTS', str(turns + 6)) or (turns + 6)))
    if ask is None: return 1
    from studio import codeagent
    prompt = ('Extend the library: build a NEW reusable effect for this wish: "%s". Write it as a custom component (custom/<name>.py with a DOC string and a smoke() that draws it), '
              'register it, and show it in a short scene. Make it look professional and fast.' % w['text'])
    try:
        res = codeagent.run_code_agent(prompt, 6, out, ask, size=size, images=[], reference=None, max_turns=turns)
    except Exception as ex:
        print('evolve failed: %s' % ex); return 1
    done = bool(res.get('registered'))
    if done: mem.finish_wish(w['id'], ', '.join(res['registered']))
    mem.save()
    lines = ['# Evolve report', '', 'Wish: %s' % w['text'], 'Built and registered: %s' % (', '.join(res.get('registered') or []) or 'nothing (try again, or raise CODE_TURNS)')]
    open(os.path.join(out, 'evolve_report.md'), 'w', encoding='utf-8').write('\n'.join(lines))
    print('\n'.join(lines))
    return 0 if done else 1


def mode_feedback(rating, note, design_id, out):
    from mgl import learn as LN
    from mgl.memory import Memory
    mem = Memory(ROOT)
    did = design_id or mem.latest_design_id()
    if not did:
        print('No design in memory yet. Make a video with mode "ai" first.'); return 1
    try:
        r = int(float(rating))
        assert 1 <= r <= 5
    except Exception:
        print('rating must be a number from 1 to 5'); return 1
    ask = make_ask(required=False, budget=3)
    try:
        res = LN.feedback(mem, did, r, note, ask=ask)
    except KeyError as ex:
        print(ex.args[0] if ex.args else ex); return 1
    mem.save()
    lines = ['# Feedback stored', '', 'Design: %s  (%s)' % (did, res['design']['prompt'][:100]), 'Rating: %s/5' % r, 'Note: %s' % (note or '-'), '',
             'Lessons learned:'] + ['- %s: %s' % (i['kind'].upper(), i['text']) for i in res['lessons']]
    if not res['lessons']: lines.append('- (none - write a note to teach the bot something concrete)')
    open(os.path.join(out, 'feedback_report.md'), 'w', encoding='utf-8').write('\n'.join(lines))
    print('\n'.join(lines))
    return 0


def make_parser():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', default='demo', choices=['demo', 'spec', 'qa', 'reference', 'check', 'ai', 'code', 'learn', 'feedback', 'assets-check', 'index-canva', 'export', 'lighten', 'design', 'designs-pdf', 'native',
                                                'compare', 'remix', 'study', 'evolve', 'checks'])
    ap.add_argument('--prompt', default='')
    ap.add_argument('--duration', default='10')
    ap.add_argument('--size', default='16:9')
    ap.add_argument('--review', default='true')
    ap.add_argument('--files', default='')
    ap.add_argument('--rating', default='')
    ap.add_argument('--design-id', default='')
    ap.add_argument('--out', default='out')
    ap.add_argument('--formats', default=os.environ.get('FORMATS', 'wfp,fcpxml,xml'), help='wfp,fcpxml,xml,gif,webm,poster,frames,mp4-light | all | none')
    ap.add_argument('--media-dir', default=os.environ.get('MEDIA_DIR', ''), help='folder on your PC where the MP4 will be kept (used inside the project files)')
    ap.add_argument('--audio', default=os.environ.get('AUDIO', ''), help='music/voice file in the repo (mp3/wav/m4a) added under the video')
    ap.add_argument('--sound', default=os.environ.get('SOUND', 'kinetic'), help='generated sound from the plan: kinetic (typography SFX only, no music) | ui (UI / SaaS animation SFX, no music) | uplift | calm | tech (music + SFX) | none')
    ap.add_argument('--split', default='auto', help='auto = cut the timeline at scene changes; none = one clip')
    ap.add_argument('--level', default='3', help='lighten: 1 safe, 2 + png, 3 + small thumbnails')
    return ap


def main():
    a = make_parser().parse_args()
    rc = run_mode(a)
    try:                                   # put the result where the Studio page can show it (outputs/ is committed by the workflow)
        from mgl import publish
        keep = int(os.environ.get('OUTPUT_KEEP', '30') or 30)
        e = publish.publish(ROOT, a.out, a.mode, os.environ.get('JOB', '').strip(), a.prompt.strip(), E_norm(a.size), a.duration, (os.environ.get('AI') or os.environ.get('AI_PROVIDER') or '').strip(), keep, only_if_job=True)
        if e: print('published for the Studio page: outputs/%s (%s)' % (e['id'], e['kind']))
    except Exception as ex:
        print('could not publish for the Studio page: %s' % ex)
    return rc


def run_mode(a):
    os.makedirs(a.out, exist_ok=True)
    files = split_files(a.files)

    if a.mode == 'check': return mode_check()
    if a.mode == 'checks': return mode_checks(a.out)
    if a.mode == 'reference':
        sys.argv = ['reference_intro.py', os.path.join(a.out, 'reference.mp4')]
        runpy.run_path(os.path.join(ROOT, 'recipes', 'reference_intro.py'), run_name='__main__')
        return 0
    if a.mode == 'assets-check':
        from mgl import assets as A
        from mgl.memory import Memory
        return 0 if A.check_providers(ROOT, Memory(ROOT)) else 1
    if a.mode == 'export':
        return mode_export(files, a.out, a.formats, a.media_dir, a.split, a.audio, a.sound if '--sound' in sys.argv else 'none')
    if a.mode == 'lighten':
        return mode_lighten(files, a.out, a.level)
    if a.mode == 'native':
        return mode_native(files, a.out)
    if a.mode == 'design':
        return mode_design(a.design_id, a.prompt, a.out, a)
    if a.mode == 'designs-pdf':
        return mode_designs_pdf(a.out)
    if a.mode in ('demo', 'spec'):
        return render_spec_file(files[0] if files else 'examples/saas_intro.json', a.out, a.formats, a.media_dir, a.split, a.audio, a.sound)
    if a.mode == 'qa':
        return mode_qa(files[0] if files else 'examples/saas_intro.json')
    if a.mode == 'learn':
        return mode_learn(files[0] if files else 'reference', a.out)
    if a.mode == 'compare':
        return mode_compare(files, a.out, a.prompt.strip())
    if a.mode == 'remix':
        return mode_remix(a.prompt, a.duration, E_norm(a.size), a.out)
    if a.mode == 'study':
        return mode_study(a.prompt, files, a.out)
    if a.mode == 'evolve':
        return mode_evolve(a.out, E_norm(a.size))
    if a.mode == 'feedback':
        return mode_feedback(a.rating or '3', a.prompt.strip(), a.design_id.strip(), a.out)
    if a.mode == 'index-canva':
        from mgl import assets as A
        from mgl.memory import Memory
        ask = make_ask(budget=10)
        if ask is None: return 1
        mem = Memory(ROOT); n = A.index_canva_inbox(mem, ROOT, ask); mem.save()
        print('indexed %d new Canva file(s). Files in assets/canva/: %d' % (n, len(A.CanvaInbox(ROOT, mem).files()))); return 0

    # ai / code
    import agent
    from mgl import gemini, engine as E
    if not a.prompt.strip():
        print('Write a prompt (what video should be made).'); return 1
    try:
        d = float(a.duration)
    except ValueError:
        print('duration must be a number of seconds'); return 1
    if not (3 <= d <= 60):
        print('duration must be between 3 and 60 seconds'); return 1
    d = int(d) if d.is_integer() else d
    size = E.norm_size(a.size)
    if size is None:
        print('size must be 16:9, 9:16 or 1:1'); return 1
    images = [f for f in files if f.lower().endswith(IMAGE_EXT)]
    videos = [f for f in files if f.lower().endswith(VIDEO_EXT)]
    for f in images + videos:
        if not os.path.isfile(f):
            print('file not found: %s (upload it into the repo first)' % f); return 1
    if a.mode == 'code':
        turns = int(os.environ.get('CODE_TURNS', '16') or 16)
        ask = make_ask(budget=int(os.environ.get('CODE_REQUESTS', str(turns + 6)) or (turns + 6)))
        if ask is None: return 1
        from studio import codeagent
        try:
            codeagent.run_code_agent(a.prompt, d, a.out, ask, size=size, images=images, reference=videos[0] if videos else None, max_turns=turns)
        except (agent.AgentError, gemini.GeminiError) as ex:
            print('\nERROR: %s' % ex); return 1
        do_exports(a.out, a.formats, a.media_dir, a.split, a.audio, a.sound)
        print('done ->', a.out)
        return 0
    ask = make_ask()
    if ask is None: return 1
    try:
        agent.run_agent(a.prompt, d, a.out, ask, review=(a.review.strip().lower() in ('true', '1', 'yes')), size=size,
                        reference=videos[0] if videos else None, images=images,
                        plan=os.environ.get('PLAN', 'true').strip().lower() not in ('false', '0', 'no', 'off'))
    except (agent.AgentError, gemini.GeminiError) as ex:
        print('\nERROR: %s' % ex); return 1
    do_exports(a.out, a.formats, a.media_dir, a.split, a.audio, a.sound)
    print('done ->', a.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
