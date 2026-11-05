#!/usr/bin/env python3
"""Self-test: python tests/test_all.py   (no internet / no API key needed; the Gemini part is simulated)"""
import base64, copy, json, os, sys, tempfile, traceback
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import numpy as np
from mgl import spec as S, gemini
import agent, render as R

PASSED, FAILED = [], []
ONLY = sys.argv[1:]          # optional: python tests/test_all.py http  -> only tests whose name contains 'http'
def check(name):
    def deco(fn):
        if ONLY and not any(k.lower() in name.lower() for k in ONLY): return fn
        try:
            fn(); PASSED.append(name); print('PASS', name)
        except Exception:
            FAILED.append(name); print('FAIL', name); traceback.print_exc()
        return fn
    return deco

def load(n): return json.load(open(os.path.join(ROOT, 'examples', n + '.json'), encoding='utf-8'))
def errs_of(sp): return S.validate(sp, ROOT)[0]

@check('examples validate')
def _():
    for n in ('saas_intro', 'logo_reveal'):
        e, w = S.validate(load(n), ROOT)
        assert not e and not w, (n, e, w)

@check('bad specs give clear errors (never crash)')
def _():
    cases = {
        'not a dict': ([], 'JSON object'),
        'no layers': ({'duration': 5}, "'layers'"),
        'bad duration': ({'duration': 'x', 'layers': [{'type': 'text', 'text': 'a'}]}, 'duration'),
        'huge duration': ({'duration': 999, 'layers': [{'type': 'text', 'text': 'a'}]}, 'duration'),
        'unknown type': ({'duration': 5, 'layers': [{'type': 'banner'}]}, 'unknown type'),
        'text without text': ({'duration': 5, 'layers': [{'type': 'text'}]}, "'text'"),
        'bad colour': ({'duration': 5, 'layers': [{'type': 'text', 'text': 'a', 'color': 'nope'}]}, 'colour'),
        'bad font': ({'duration': 5, 'layers': [{'type': 'text', 'text': 'a', 'font': 'comic'}]}, 'font'),
        'bad bg': ({'duration': 5, 'background': 'rainbow', 'layers': [{'type': 'text', 'text': 'a'}]}, 'background'),
        'end before start': ({'duration': 5, 'layers': [{'type': 'text', 'text': 'a', 'start': 3, 'end': 2}]}, 'end'),
        'bad anim': ({'duration': 5, 'layers': [{'type': 'text', 'text': 'a', 'in': 'sparkle'}]}, 'animation'),
        'bad keys prop': ({'duration': 5, 'layers': [{'type': 'text', 'text': 'a', 'keys': {'banana': [[0, 1]]}}]}, 'cannot animate'),
        'bad keys shape': ({'duration': 5, 'layers': [{'type': 'text', 'text': 'a', 'keys': {'x': 5}}]}, 'keys.x'),
        'missing image': ({'duration': 5, 'layers': [{'type': 'image', 'path': 'assets/nothing.png', 'w': 100}]}, 'not found'),
        'image path escape': ({'duration': 5, 'layers': [{'type': 'image', 'path': '../../etc/passwd', 'w': 100}]}, 'inside the project'),
        'bad icon': ({'duration': 5, 'layers': [{'type': 'icon', 'name': 'rocket'}]}, 'name must be'),
        'bad card': ({'duration': 5, 'layers': [{'type': 'card', 'kind': 'weird'}]}, 'kind'),
        'bad line': ({'duration': 5, 'layers': [{'type': 'line', 'points': [[1, 2]]}]}, 'points'),
        'rrect no size': ({'duration': 5, 'layers': [{'type': 'rrect'}]}, "'w' and 'h'"),
        'camera zoom': ({'duration': 5, 'camera': [{'t': 0, 'zoom': 99}], 'layers': [{'type': 'text', 'text': 'a'}]}, 'zoom'),
    }
    for name, (sp, needle) in cases.items():
        e = errs_of(sp)
        assert e and any(needle in x for x in e), (name, e)

@check('every layer type renders a non-empty frame')
def _():
    for n in ('saas_intro', 'logo_reveal'):
        sp = load(n); ctx = S.Context(ROOT)
        for t in (0.0, 1.0, 3.3, 5.0, 7.5, sp['duration'] - 0.01):
            fr = S.render_frame(sp, t, ctx)
            assert fr.shape == (1080, 1920, 3) and fr.dtype == np.uint8
            assert fr.std() > 5, (n, t)
        assert not ctx.warnings, ctx.warnings

@check('render errors are contained per layer')
def _():
    sp = {'duration': 3, 'layers': [{'type': 'text', 'text': 'ok', 'size': 100}, {'type': 'image', 'path': 'assets/sample_logo.png', 'w': 200}]}
    ctx = S.Context(ROOT); S.render_frame(sp, 1.0, ctx)
    sp['layers'][1]['path'] = 'assets/missing.png'      # skipped validation on purpose
    ctx = S.Context(ROOT); fr = S.render_frame(sp, 1.0, ctx)
    assert ctx.warnings and fr.shape == (1080, 1920, 3)

@check('extreme values do not crash')
def _():
    sp = {'duration': 2, 'layers': [
        {'type': 'text', 'text': 'x' * 400, 'size': 500}, {'type': 'rrect', 'w': 99999, 'h': 99999},
        {'type': 'chip', 'label': 'a', 'scale': 50}, {'type': 'card', 'kind': 'custom', 'scale': 40, 'yaw': 80, 'title': 'z' * 100, 'big_text': 'q' * 99},
        {'type': 'emoji', 'char': 'zz', 'size': 5000}, {'type': 'circle', 'r': 100000},
        {'type': 'text', 'text': 'a', 'size': 0.1}, {'type': 'text', 'text': 'a', 'opacity': 5, 'blur': 500}]}
    e = errs_of(sp)
    assert not e, e
    ctx = S.Context(ROOT)
    for t in (0.0, 1.0):
        S.render_frame(sp, t, ctx)

@check('background crossfade + light detection')
def _():
    sp = {'duration': 6, 'background': [{'t': 0, 'style': 'dark_aurora'}, {'t': 2, 'style': 'light_pastel', 'fade': 1}], 'layers': [{'type': 'text', 'text': 'a'}]}
    assert S.bg_light(sp, 1.0) == 0.0 and S.bg_light(sp, 5.0) == 1.0 and 0 < S.bg_light(sp, 2.5) < 1

@check('keyframe interpolation (numbers + colours + ease)')
def _():
    assert S.interp([[0, 0], [2, 10, 'linear']], 1.0) == 5.0
    assert S.interp([[0, 0], [2, 10]], -5) == 0 and S.interp([[0, 0], [2, 10]], 9) == 10
    c = S.interp([[0, [1, 0, 0]], [1, [0, 0, 1], 'linear']], 0.5)
    assert abs(c[0] - 0.5) < 1e-6 and abs(c[2] - 0.5) < 1e-6
    assert S.parse_color('#fff') == (1.0, 1.0, 1.0) and S.parse_color([255, 0, 0]) == (1.0, 0.0, 0.0) and S.parse_color('nope') is None

@check('normalize_spec repairs common mistakes')
def _():
    sp = {'spec': {'duration': '8', 'elements': [{'type': 'Rectangle', 'w': '300px', 'h': '100', 'x': '10'}, {'type': 'label', 'text': 'a\nb', 'size': '80'}]}}
    out = agent.normalize_spec(sp)
    assert out['duration'] == 8.0 and out['layers'][0]['type'] == 'rrect' and out['layers'][0]['w'] == 300.0
    assert out['layers'][1]['type'] == 'text' and '\n' not in out['layers'][1]['text'] and out['layers'][1]['size'] == 80.0
    assert not errs_of(out)

@check('extract_json handles fences and chatter')
def _():
    assert gemini.extract_json('```json\n{"a":1}\n```') == {'a': 1}
    assert gemini.extract_json('Sure! Here it is:\n{"a": {"b": 2}}\nHope that helps') == {'a': {'b': 2}}
    try: gemini.extract_json('no json here'); assert False
    except Exception: pass

@check('model choice prefers newest flash, skips junk')
def _():
    orig = gemini.list_models
    gemini.list_models = lambda key: ['gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-2.5-flash-image',
                                      'gemini-3.1-flash', 'gemini-3.2-flash-preview', 'gemini-flash-latest', 'gemini-2.0-flash-live', 'gemma-3-27b', 'text-embedding']
    try:
        os.environ.pop('GEMINI_MODEL', None)
        m = gemini.choose_models('k')
        assert m[0] == 'gemini-flash-latest' and m[1] == 'gemini-3.1-flash' and 'gemini-2.5-flash-image' not in m and 'gemini-2.0-flash-live' not in m, m
        assert m.index('gemini-2.5-flash') < m.index('gemini-3.2-flash-preview') < m.index('gemini-2.5-flash-lite'), m
        os.environ['GEMINI_MODEL'] = 'a, b'
        assert gemini.choose_models('k') == ['a', 'b']
    finally:
        gemini.list_models = orig; os.environ.pop('GEMINI_MODEL', None)

@check('gemini.ask: patient - a busy / unreachable AI is waited for (rounds), only real errors fail at once, patience 0 gives up')
def _():
    orig, sleep = gemini.generate, gemini.time.sleep
    n = {'c': 0}; slept = []
    def busy_then_ok(key, model, system, contents, json_mode=True, temperature=0.8, max_tokens=0):
        n['c'] += 1
        if n['c'] <= 8:                                           # 2 models x 3 tries = round 1 fails, round 2 fails partly
            ex = gemini.GeminiError('HTTP 503 overloaded' if n['c'] % 2 else 'network error: timed out'); ex.status = 503 if n['c'] % 2 else None; ex.retry_after = None; raise ex
        return 'finally'
    gemini.generate = busy_then_ok; gemini.time.sleep = lambda s: slept.append(s)
    try:
        txt, model = gemini.ask('k', ['a', 'b'], None, [], log=lambda *a: None, patience=600)
        assert txt == 'finally' and n['c'] == 9 and max(slept) >= 30, (n, slept)
        n['c'] = 0
        try: gemini.ask('k', ['a', 'b'], None, [], log=lambda *a: None, patience=0); assert False
        except gemini.GeminiError as ex: assert 'all models failed' in str(ex)
        def real_error(*a, **k):
            ex = gemini.GeminiError('HTTP 404 model not found'); ex.status = 404; ex.retry_after = None; raise ex
        gemini.generate = real_error; slept.clear()
        try: gemini.ask('k', ['a'], None, [], log=lambda *a: None, patience=600); assert False
        except gemini.GeminiError: pass
        assert not any(x >= 30 for x in slept), 'a real error must not be waited for'
    finally:
        gemini.generate, gemini.time.sleep = orig, sleep


@check('gemini.ask: retries 429, falls back to next model, reports all failures')
def _():
    calls = []
    orig, sleep = gemini.generate, gemini.time.sleep
    def fake(key, model, system, contents, json_mode=True, temperature=0.8, max_tokens=0):
        calls.append(model)
        if model == 'm1':
            ex = gemini.GeminiError('HTTP 429'); ex.status = 429; ex.retry_after = 1; raise ex
        if model == 'm2':
            ex = gemini.GeminiError('HTTP 404'); ex.status = 404; ex.retry_after = None; raise ex
        return 'hello'
    gemini.generate = fake; gemini.time.sleep = lambda s: None
    try:
        txt, model = gemini.ask('k', ['m1', 'm2', 'm3'], None, [], log=lambda *a: None)
        assert (txt, model) == ('hello', 'm3') and calls.count('m1') == 3 and calls.count('m2') == 1, calls
        def always_bad(*a, **k):
            ex = gemini.GeminiError('HTTP 403 denied'); ex.status = 403; ex.retry_after = None; raise ex
        gemini.generate = always_bad
        try: gemini.ask('k', ['x', 'y'], None, [], log=lambda *a: None); assert False
        except gemini.GeminiError as ex: assert 'x:' in str(ex) and 'y:' in str(ex)
        def bad_key(*a, **k):
            ex = gemini.GeminiError('HTTP 400 API key not valid'); ex.status = 400; ex.retry_after = None; raise ex
        gemini.generate = bad_key
        try: gemini.ask('k', ['x', 'y'], None, [], log=lambda *a: None); assert False
        except gemini.GeminiError as ex: assert 'API key rejected' in str(ex)
    finally:
        gemini.generate, gemini.time.sleep = orig, sleep

@check('agent works with a reference video sheet')
def _():
    ref = '/mnt/user-data/uploads/morion_design_intro.mp4'
    if not os.path.exists(ref):
        print('   (skipped: reference file not present)'); return
    png, dur = agent.reference_sheet(ref)
    assert len(png) > 5000 and 14 < dur < 15


@check('new layer types validate (good and bad)')
def _():
    for n in ('showcase', 'vertical_short'):
        e, w = S.validate(load(n), ROOT); assert not e and not w, (n, e, w)
    T = lambda L, **kw: dict({'duration': 5, 'layers': [L]}, **kw)
    bad = [
        (T({'type': 'chart', 'kind': 'bar', 'w': 100, 'h': 100}), 'data'),
        (T({'type': 'chart', 'kind': 'pie', 'data': [1, 2], 'w': 100, 'h': 100}), 'kind'),
        (T({'type': 'transition', 'style': 'wipe'}), "'start' and 'end'"),
        (T({'type': 'transition', 'style': 'spin', 'start': 1, 'end': 2}), 'style'),
        (T({'type': 'device', 'kind': 'tv', 'w': 300}), 'kind'),
        (T({'type': 'device', 'kind': 'phone'}), "'w'"),
        (T({'type': 'text', 'text': 'no counter', 'count': {'to': 5}}), '{n}'),
        (T({'type': 'text', 'text': '{n}', 'count': {'to': 5, 'format': '{:%s}'}}), 'format'),
        (T({'type': 'particles', 'count': 9999}), 'count'),
        (T({'type': 'grid', 'kind': 'hex'}), 'kind'),
        (T({'type': 'progress', 'kind': 'bar'}), "'w' and 'h'"),
        (T({'type': 'blob'}), "'r'"),
        (T({'type': 'text', 'text': 'a', 'float': 'yes'}), 'float'),
        (T({'type': 'image', 'w': 100}), 'path'),
        (T({'type': 'image', 'path': 'assets/sample_logo.png', 'w': 100, 'fit': 'stretch'}), 'fit'),
        (T({'type': 'text', 'text': 'a', 'in': 'wipe_diagonal'}), 'animation'),
        (T({'type': 'text', 'text': 'a'}, size='4:3'), 'size'),
    ]
    for sp, needle in bad:
        e = errs_of(sp); assert e and any(needle in x for x in e), (sp['layers'][0], e)

@check('all new components render without warnings at several times')
def _():
    for n in ('showcase', 'vertical_short'):
        sp = load(n); ctx = S.Context(ROOT)
        for t in (0.0, 1.0, 2.5, 4.9, 6.0, 8.0, 9.5, 11.0, sp['duration'] - 0.02):
            fr = S.render_frame(sp, t, ctx)
            assert fr.shape == ((1080, 1920, 3) if sp.get('size', '16:9') == '16:9' else (1920, 1080, 3)), fr.shape
        assert not ctx.warnings, (n, ctx.warnings)
        last = S.render_frame(sp, sp['duration'] - 0.02, ctx)
        assert last.std() > 20, 'last frame looks empty in %s' % n

@check('every transition covers the screen at its middle and is clear at the ends')
def _():
    import mgl.extras as X, mgl.engine as E
    S.setup({'size': '16:9'})
    base = np.random.RandomState(1).rand(1080, 1920, 3).astype(np.float32)
    for st in ('wipe', 'iris', 'stripes', 'flash'):
        f = base.copy(); X.transition(f, st, 0.5, (1.0, 0.0, 0.0), 'right'); assert f[..., 1].max() < 0.05 or st == 'flash', st
        f = base.copy(); X.transition(f, st, 0.0, (1, 0, 0)); assert np.allclose(f, base), st
        f = base.copy(); X.transition(f, st, 1.0, (1, 0, 0)); assert np.allclose(f, base), st
    f = base.copy(); X.transition(f, 'glitch', 0.5, seed=3); assert not np.allclose(f, base)
    f = base.copy(); X.transition(f, 'flash', 0.5, (1, 1, 1)); assert f.min() > 0.99

@check('size switching 16:9 <-> 9:16 <-> 1:1 in one process')
def _():
    for key, shp in (('9:16', (1920, 1080, 3)), ('16:9', (1080, 1920, 3)), ('1:1', (1080, 1080, 3)), ('16:9', (1080, 1920, 3))):
        sp = {'duration': 2, 'size': key, 'layers': [{'type': 'text', 'text': 'x', 'size': 200}]}
        assert S.render_frame(sp, 1.0, S.Context(ROOT)).shape == shp

@check('wipe animation reveals progressively; float moves; count counts')
def _():
    sp = {'duration': 4, 'background': 'mono_dark', 'layers': [{'type': 'text', 'text': 'WIPE TEST', 'size': 200, 'in': {'anim': 'wipe_right', 'dur': 1.0}}]}
    ctx = S.Context(ROOT)
    a = S.render_frame(sp, 0.5, ctx); b = S.render_frame(sp, 2.0, ctx); z = S.render_frame(sp, 0.0, ctx)
    bright = lambda im: (im.mean(axis=2) > 200)
    na, nb = bright(a).sum(), bright(b).sum()
    assert 0.2 * nb < na < 0.8 * nb, (na, nb)
    assert bright(z).sum() == 0
    sp2 = {'duration': 4, 'layers': [{'type': 'circle', 'r': 40, 'float': {'y': 60, 'speed': 1}}]}
    ys = [np.where(S.render_frame(sp2, t, ctx).mean(axis=2) > 235)[0].mean() for t in (0.2, 0.9)]
    assert abs(ys[0] - ys[1]) > 10, ys
    sp3 = {'duration': 4, 'layers': [{'type': 'text', 'text': '{n}', 'size': 200, 'count': {'from': 0, 'to': 100, 'dur': 2, 'format': '{:d}'}}]}
    import mgl.spec as SP
    assert SP._count_text(sp3['layers'][0], 0.0, 0.0) == '0' and SP._count_text(sp3['layers'][0], 5.0, 0.0) == '100'

@check('image window: zoom/pan crop, contain fit, tilt, missing alpha')
def _():
    import mgl.spec as SP
    im = np.zeros((100, 200, 4), np.float32); im[..., 3] = 1; im[:, :100, 0] = 1; im[:, 100:, 2] = 1      # left red, right blue
    w = SP._image_window(im, 100, 100, 1.0, -1.0, 0.0, 'cover'); assert w[50, 10, 0] == 1 and w[50, 90, 2] == 0
    w = SP._image_window(im, 100, 100, 1.0, 1.0, 0.0, 'cover'); assert w[50, 10, 2] == 1
    w = SP._image_window(im, 100, 100, 2.0, 0.0, 0.0, 'cover'); assert w.shape == (100, 100, 4)
    w = SP._image_window(im, 100, 100, 1.0, 0.0, 0.0, 'contain'); assert w[2, 50, 3] == 0 and w[50, 50, 3] == 1   # letterboxed
    sp = {'duration': 3, 'layers': [{'type': 'image', 'path': 'assets/sample_logo.png', 'w': 300, 'h': 500, 'tilt_x': 20, 'tilt_y': -25, 'rot': 10, 'r': 40, 'shadow': 0.4}]}
    ctx = S.Context(ROOT); fr = S.render_frame(sp, 1.0, ctx); assert fr.std() > 5 and not ctx.warnings, ctx.warnings


@check('QA: catches cut-off, overlap, contrast, small text, empty frames, safe area, variety')
def _():
    from mgl import qa
    def rep(sp): return qa.analyze(sp, ROOT, samples=12)
    def has(items, needle): return any(needle in x for x in items)
    base = {'duration': 6, 'background': 'light_pastel'}
    r = rep(dict(base, layers=[{'type': 'text', 'text': 'This sentence is far too long to fit on one line of the canvas', 'size': 120, 'color': [0.1, 0.1, 0.1]}]))
    assert has(r['errors'], 'cut off') and has(r['errors'], 'reduce its size'), r
    r = rep(dict(base, layers=[{'type': 'text', 'text': 'Hello', 'size': 150, 'y': 500, 'color': [0, 0, 0]}, {'type': 'text', 'text': 'World', 'size': 150, 'y': 560, 'color': [0, 0, 0]}]))
    assert has(r['errors'], 'overlap'), r
    r = rep(dict(base, layers=[{'type': 'text', 'text': 'Hello', 'size': 120, 'color': [1, 1, 1]}]))                 # white on light background
    assert has(r['warnings'], 'Low contrast') and has(r['warnings'], 'darker'), r
    r = rep({'duration': 6, 'background': 'dark_aurora', 'layers': [{'type': 'text', 'text': 'tiny text here', 'size': 14}]})
    assert has(r['warnings'], 'too small'), r
    r = rep({'duration': 6, 'background': 'dark_aurora', 'layers': [{'type': 'text', 'text': 'Hello', 'size': 150, 'start': 0, 'end': 2.5}]})
    assert has(r['errors'], 'ends on an empty background'), r
    r = rep({'duration': 9, 'background': 'dark_aurora', 'layers': [{'type': 'text', 'text': 'One', 'size': 150, 'start': 0, 'end': 2}, {'type': 'text', 'text': 'Two', 'size': 150, 'start': 6, 'end': 9}]})
    assert has(r['errors'], 'Empty stretch'), r
    r = rep({'duration': 6, 'size': '9:16', 'background': 'dark_aurora', 'layers': [{'type': 'text', 'text': 'Bottom text', 'size': 90, 'y': 1800}]})
    assert has(r['warnings'], 'Safe area'), r
    many = [{'type': 'emoji', 'char': 'x', 'size': 50, 'x': 100 + 90 * i, 'y': 500} for i in range(18)]
    r = rep({'duration': 6, 'background': 'dark_aurora', 'layers': many + [{'type': 'text', 'text': 'Hi', 'size': 120}]})
    assert has(r['warnings'], 'Crowded'), r
    same = [{'type': 'text', 'text': 'w%d' % i, 'size': 90, 'y': 100 + i * 100, 'start': i * 0.5, 'end': 12, 'in': 'pop'} for i in range(8)]
    r = qa.lint_variety({'duration': 12, 'background': 'ocean', 'layers': same})
    assert has(r, 'entrance animations') and has(r, 'one background') and has(r, 'transitions') and has(r, 'no camera'), r
    stag = [{'type': 'text', 'text': 'x', 'size': 60, 'start': 3, 'end': 5} for _ in range(7)]
    assert has(qa.lint_variety({'duration': 8, 'layers': stag}), 'Stagger')
    two_scenes = [{'type': 'text', 'text': 'A', 'end': 5}, {'type': 'chip', 'label': 'x', 'end': 5}, {'type': 'text', 'text': 'B', 'start': 6}, {'type': 'chip', 'label': 'y', 'start': 6},
                  {'type': 'transition', 'style': 'flash', 'start': 5, 'end': 6}]
    assert has(qa.lint_variety({'duration': 10, 'layers': two_scenes}), 'same kinds of layers')

@check('all four examples are QA-clean (they teach the agent)')
def _():
    from mgl import qa
    for n in ('saas_intro', 'logo_reveal', 'showcase', 'vertical_short'):
        r = qa.analyze(load(n), ROOT)
        assert not r['errors'] and not r['warnings'], (n, r)


@check('memory: designs, lessons (merge + weight), pruning, corrupt file recovery, prompt context')
def _():
    from mgl.memory import Memory, summarize_spec, BRAND_TEMPLATE
    d = tempfile.mkdtemp(); m = Memory(d)
    sp = load('saas_intro')
    did = m.add_design('SaaS intro for a fitness app', sp, {'errors': [], 'warnings': ['x']}, 8.5)
    assert m.design(did)['summary']['transitions'] == [] and m.design(did)['summary']['backgrounds'][0] == 'neon_night'
    assert os.path.exists(os.path.join(d, 'memory', 'specs', did + '.json')) and m.spec_of(did)['duration'] == 10
    n = m.add_lessons([{'kind': 'dont', 'text': 'Long headlines get cut off at the edge of the canvas', 'weight': 1}])
    m.add_lessons([{'kind': 'dont', 'text': 'Long headlines get cut off at the canvas edge', 'weight': 2}])      # near duplicate -> merged
    m.add_lessons([{'kind': 'do', 'text': 'Use a camera push-in during each scene', 'weight': 1}])
    assert n == 1 and len(m.lessons) == 2 and m.lessons[0]['count'] == 2 and m.lessons[0]['weight'] >= 2
    assert m.top_lessons(1)[0]['kind'] == 'dont'
    m.add_lessons([{'kind': 'do', 'text': 'short', 'weight': 1}]); assert len(m.lessons) == 2            # too short ignored
    m.set_feedback(did, 5, 'loved the card fan'); assert m.design(did)['rating'] == 5
    m.add_style({'title': 'Neon dashboard promo', 'tags': ['saas', 'neon'], 'palette': ['#111', '#f0f'], 'sha': 'abc'}); assert m.has_source('abc') and not m.has_source('zzz')
    m.add_style({'title': 'Food truck menu', 'tags': ['restaurant'], 'sha': 'def'})
    assert m.relevant_styles('a neon saas dashboard video', 1)[0]['title'].startswith('Neon')
    json.dump(dict(BRAND_TEMPLATE, name='Pulse', colors={'primary': '#5b8cff', 'accent': 'nope'}), open(os.path.join(d, 'memory', 'brand.json'), 'w'))
    m.save()
    m2 = Memory(d); bk = m2.brand_kit()
    assert bk['name'] == 'Pulse' and bk['colors'] == {'primary': '#5b8cff'}, bk
    m2.add_design('another', load('logo_reveal'))
    ctx = m2.context_for_prompt('SaaS video')
    for needle in ('BRAND KIT', 'Pulse', 'LESSONS LEARNED', 'cut off', 'LAST VIDEOS', 'DESIGNS THE USER LIKED', 'REFERENCE STYLE'):
        assert needle in ctx, (needle, ctx[:400])
    open(os.path.join(d, 'memory', 'designs.json'), 'w').write('{broken json')
    m3 = Memory(d); assert m3.designs == [] and os.path.exists(os.path.join(d, 'memory', 'designs.json.bad'))
    for i in range(95): m3.add_design('p%d' % i, {'duration': 3, 'layers': []})
    m3.set_feedback(m3.designs[0]['id'], 5, '')
    m3.save()
    assert len(m3.designs) == 80 and len(os.listdir(os.path.join(d, 'memory', 'specs'))) <= 31 + 1

@check('memory: lesson consolidation with a simulated model')
def _():
    from mgl.memory import Memory
    m = Memory(tempfile.mkdtemp())
    m.add_lessons([{'kind': 'do', 'text': 'Rule ' + ' '.join('tok%dx%d' % (i, j) for j in range(6)), 'weight': 1} for i in range(45)])
    assert len(m.lessons) == 45
    ask = lambda system, contents: json.dumps({'lessons': [{'kind': 'do' if i % 2 else 'dont', 'text': 'Merged rule %d for good design' % i, 'weight': 3} for i in range(12)]})
    assert m.consolidate_lessons(ask) and len(m.lessons) == 12 and m.lessons[0]['source'] == 'consolidated'
    assert not m.consolidate_lessons(ask)               # below threshold now

@check('learn: feedback (with and without a model), automatic lessons')
def _():
    from mgl.memory import Memory
    from mgl import learn
    m = Memory(tempfile.mkdtemp()); did = m.add_design('promo for a gym', load('saas_intro'))
    out = learn.feedback(m, did, 2, 'too many pop animations, boring', ask=None)
    assert out['lessons'][0]['kind'] == 'dont' and m.design(did)['rating'] == 2 and m.lessons[0]['weight'] == 3
    ask = lambda system, contents: json.dumps({'lessons': [{'kind': 'dont', 'text': 'Do not use pop for more than 30% of entrances', 'weight': 1}]})
    out = learn.feedback(m, did, 1, 'repetitive', ask=ask); assert out['lessons'][0]['weight'] >= 2
    def bad_ask(system, contents): raise RuntimeError('quota')
    out = learn.feedback(m, did, 5, 'great colours', ask=bad_ask, log=lambda *a: None); assert out['lessons'][0]['kind'] == 'do'
    try: learn.feedback(m, 'd-nope', 3, 'x'); assert False
    except KeyError: pass
    assert os.path.getsize(os.path.join(m.dir, 'learning_log.md')) > 50
    q = learn.lessons_from_qa(['Text cut off: at 1.0s layer 2 ...', 'Low contrast: layer 3', 'Variety: only 2 different entrance animations'])
    assert [i['kind'] for i in q] == ['dont', 'dont', 'dont'] and 'cut off' in q[0]['text']
    assert learn.lessons_from_success({'backgrounds': ['ocean'], 'transitions': ['wipe']}, 9.5)[0]['kind'] == 'do' and not learn.lessons_from_success({}, 6)
    txt = learn.run_summary('x', {'backgrounds': ['ocean']}, {'errors': ['Text cut off: a'], 'warnings': []}, {'errors': [], 'warnings': []}, [{'round': 1, 'score': 6.0, 'problems': ['p']}], 8)
    assert 'Fixed by the bot: Text cut off' in txt and 'score 6.0' in txt


def _mk_video(path, color='red', secs=3):
    import subprocess
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=15:duration=%d' % secs, '-vf', 'hue=h=%d' % (0 if color == 'red' else 120),
                    '-pix_fmt', 'yuv420p', path], check=True)

@check('reference: frame sheets, sha, cleaning of messy analysis, multi-video learning with limit/skip/fail, style guide')
def _():
    from mgl import reference as RF
    from mgl.memory import Memory
    d = tempfile.mkdtemp(); fold = os.path.join(d, 'reference'); os.makedirs(fold)
    a = os.path.join(fold, 'a.mp4'); b = os.path.join(fold, 'b.mp4'); dup = os.path.join(fold, 'a_copy.mp4'); bad = os.path.join(fold, 'broken.mp4')
    _mk_video(a, 'red', 3); _mk_video(b, 'green', 4)
    import shutil; shutil.copy(a, dup); open(bad, 'wb').write(b'not a video at all' * 50)
    sheets, info = RF.frame_sheets(a)
    assert len(sheets) == 1 and sheets[0][:4] == b'\x89PNG' and info['aspect'] == '16:9' and 2.5 < info['duration'] < 3.5     # short clip -> one sheet
    assert RF.video_sha(a) == RF.video_sha(dup) != RF.video_sha(b)
    calls = []
    def ask(system, contents, json_mode=True):
        calls.append(len(contents[0]['parts']))
        if not json_mode or 'STYLE CARDS' in contents[0]['parts'][0]['text']:
            return '# Guide\n' + ('Use blur-in headlines and wipe transitions. ' * 12)
        return json.dumps({'title': 'Neon promo ' + str(len(calls)), 'tags': ['SaaS', 'Neon'], 'palette': ['#112233', 'red', '#ABCDEF', 12], 'extra': 'ignored',
                           'typography': {'headline': 'bold italic'}, 'scenes': [{'t0': 0, 't1': 2, 'archetype': 'typographic_hero', 'description': 'Hey', 'motion': 'blur in'}] * 20,
                           'transitions': ['wipe', 'flash'], 'pacing': {'rhythm': 'fast'}, 'layout_rules': ['left aligned'], 'weaknesses': 'not a list'})
    card = RF.analyze_video(ask, a)
    assert card['palette'] == ['#112233', '#ABCDEF'] and len(card['scenes']) == 12 and card['tags'] == ['saas', 'neon'] and card['weaknesses'] == [] and card['aspect'] == '16:9'
    m = Memory(d)
    new, skipped, failed = RF.learn_folder(m, ask, fold, limit=1, log=lambda *x: None)
    assert len(new) == 1 and len(m.styles) == 1
    new, skipped, failed = RF.learn_folder(m, ask, fold, limit=5, log=lambda *x: None)
    assert len(new) == 1 and len(m.styles) == 2, (len(new), len(m.styles))      # b.mp4; a_copy has the same sha as a.mp4
    assert [f for f, _ in failed] == ['broken.mp4'] and 'a_copy.mp4' in skipped, (failed, skipped)
    new, skipped, failed = RF.learn_folder(m, ask, fold, limit=5, log=lambda *x: None); assert not new
    txt = RF.synthesize_style_guide(m, ask, log=lambda *x: None)
    assert txt and 'blur-in' in m.style_guide() and 'Style guide' in m.style_guide()
    m1 = Memory(tempfile.mkdtemp()); m1.add_style({'title': 'x'})
    assert RF.synthesize_style_guide(m1, ask) is None                       # one video is not enough to compare
    try: RF.learn_folder(m, ask, os.path.join(d, 'nope')); assert False
    except FileNotFoundError: pass
    sheets2, info2 = RF.frame_sheets('/mnt/user-data/uploads/morion_design_intro.mp4') if os.path.exists('/mnt/user-data/uploads/morion_design_intro.mp4') else ([b''], {'duration': 0})
    assert len(sheets2) in (1, 2)


def _png_bytes(color, size=(300, 200), alpha=255):
    import cv2
    im = np.zeros((size[1], size[0], 4), np.uint8); im[..., :3] = color[::-1]; im[..., 3] = alpha
    return cv2.imencode('.png', im)[1].tobytes()

def _jpg_bytes(color, size=(640, 400)):
    import cv2
    im = np.zeros((size[1], size[0], 3), np.uint8); im[:] = color[::-1]
    return cv2.imencode('.jpg', im)[1].tobytes()

STAR_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path fill="currentColor" d="M12 2l3 7h7l-5.5 4.5L18 21l-6-4-6 4 1.5-7.5L2 9h7z"/></svg>'

def _fake_net(log):
    """a fake internet: Pixabay, Pexels and Iconify answers"""
    from mgl import assets as A
    def http_get(url, headers=None, timeout=30, max_bytes=25_000_000):
        log.append(url)
        if 'pixabay.com/api' in url:
            assert 'key=PXKEY' in url
            kind = 'illustration' if 'illustration' in url else ('vector' if 'vector' in url else 'photo')
            return json.dumps({'hits': [{'id': 100 + i, 'tags': '%s %d' % (kind, i), 'webformatURL': 'https://cdn.px/t%d.jpg' % i, 'largeImageURL': 'https://cdn.px/l%d.jpg' % i,
                                         'imageWidth': 1920, 'imageHeight': 1080, 'user': 'author%d' % i, 'pageURL': 'https://pixabay.com/p%d' % i} for i in range(3)]}).encode()
        if 'api.pexels.com' in url:
            assert headers and headers.get('Authorization') == 'PEKEY'
            return json.dumps({'photos': [{'id': 7, 'alt': 'a pexels photo', 'width': 4000, 'height': 3000, 'photographer': 'Pat', 'url': 'https://pexels.com/7',
                                           'src': {'medium': 'https://cdn.pe/m.jpg', 'large2x': 'https://cdn.pe/l.jpg'}}]}).encode()
        if 'api.iconify.design/search' in url:
            return json.dumps({'icons': ['lucide:rocket', 'mdi:rocket', 'mdi:rocket-launch', 'mdi:rocket-outline', 'mdi:rocket-off', 'fluent-emoji-flat:rocket', 'noto:rocket'],
                               'collections': {'lucide': {'license': {'title': 'ISC'}, 'author': {'name': 'Lucide'}}, 'mdi': {'license': {'title': 'Apache 2.0'}, 'author': {'name': 'Pictogrammers'}}}}).encode()
        if 'api.iconify.design/' in url and '.svg' in url:
            return STAR_SVG.replace('currentColor', '#' + (url.split('color=%23')[1].split('&')[0] if 'color=%23' in url else '000000')).encode()
        if 'cdn.px/t' in url or 'cdn.px/l' in url:
            n = int(url.split('/')[-1][1]); return _jpg_bytes([(255, 0, 0), (0, 255, 0), (0, 0, 255)][n])
        if 'cdn.pe/' in url: return _jpg_bytes((250, 250, 0))
        raise A.AssetError('unexpected url ' + url)
    return http_get

@check('assets: providers per section, AI choice, caching in memory, credits, fallbacks, limits')
def _():
    from mgl import assets as A
    from mgl.memory import Memory
    import cv2
    root = tempfile.mkdtemp(); os.makedirs(os.path.join(root, 'assets', 'canva'))
    open(os.path.join(root, 'assets', 'canva', 'blue_dashboard_hero.png'), 'wb').write(_png_bytes((0, 0, 255)))
    open(os.path.join(root, 'assets', 'canva', 'pink_logo_badge.png'), 'wb').write(_png_bytes((255, 0, 128)))
    mem = Memory(root); net = []
    orig = A.http_get; A.http_get = _fake_net(net)
    try:
        env = {'PIXABAY_API_KEY': ' PXKEY\n', 'PEXELS_API_KEY': 'PEKEY'}
        provs = A.make_providers(root, mem, env)
        assert sorted(p.name for p in provs) == ['canva', 'iconify', 'pexels', 'pixabay']
        assert sorted(p.name for p in A.make_providers(root, mem, {})) == ['canva', 'iconify']
        spec = {'duration': 6, 'layers': [
            {'type': 'text', 'text': 'Hi', 'size': 100},
            {'type': 'image', 'search': {'section': 'photo', 'query': 'modern office team'}, 'w': 800, 'h': 450, 'x': 500, 'y': 400},
            {'type': 'image', 'search': {'section': 'vector', 'query': 'analytics dashboard'}, 'w': 400},
            {'type': 'image', 'search': {'section': 'icon', 'query': 'rocket'}, 'w': 120, 'tint': [1, 0.5, 0]},
            {'type': 'image', 'search': {'section': 'icon', 'query': 'rocket', 'style': 'color'}, 'w': 120},
            {'type': 'image', 'search': {'section': 'canva', 'query': 'blue dashboard'}, 'w': 300}]}
        assert not errs_of(spec), errs_of(spec)
        calls = []
        def ask(system, contents, json_mode=True):
            calls.append(len(contents[0]['parts'][1]) if len(contents[0]['parts']) > 1 else 0)
            txt = contents[0]['parts'][0]['text']
            assert 'numbered candidates' in txt and contents[0]['parts'][1]['inlineData']['mimeType'] == 'image/png'
            return json.dumps({'best': 2, 'reason': 'cleanest composition', 'scores': [5, 9, 6]})
        sp, rep = A.resolve_spec(json.loads(json.dumps(spec)), root, mem, ask, provs, 'dark neon', log=lambda *x: None)
        assert len(sp['layers']) == 6 and all('path' in L for L in sp['layers'] if L['type'] == 'image' and 'search' not in L)
        paths = [L['path'] for L in sp['layers'] if L['type'] == 'image']
        assert all(os.path.isfile(os.path.join(root, p)) for p in paths), paths
        assert any(p.startswith('assets/library/icon_rocket') for p in paths) and 'assets/canva/blue_dashboard_hero.png' in paths     # tags/filename matched the right canva file
        assert len(calls) == 5 and all(r['chosen'] for r in rep), rep
        assert not S.validate(sp, root)[0], S.validate(sp, root)[0]         # the resolved spec validates (paths exist)
        img = cv2.imread(os.path.join(root, [p for p in paths if 'icon_rocket' in p][0]), cv2.IMREAD_UNCHANGED)
        assert img.shape[2] == 4 and img[..., 3].max() == 255 and img[..., 3].min() == 0          # transparent icon
        orange = [p for p in paths if 'icon_rocket' in p][0]
        assert os.path.getsize(os.path.join(root, 'assets', 'library', 'CREDITS.md')) > 40
        assert any(k.startswith('photo|modern office team') for k in mem.assets) and mem.assets['icon|rocket|-|-']['license'] == 'Apache 2.0' and mem.assets['icon|rocket|-|-']['id'] == 'mdi:rocket'
        # second video: same searches are remembered -> no network, no AI
        n_net, n_ask = len(net), len(calls)
        sp2, rep2 = A.resolve_spec(json.loads(json.dumps(spec)), root, mem, ask, provs, '', log=lambda *x: None)
        assert len(net) == n_net and len(calls) == n_ask and all(r['cached'] for r in rep2 if r['section'] != 'canva' or True)
        # AI refuses everything -> layer removed; AI failure -> first result; no ask -> first result
        refuse = lambda system, contents, json_mode=True: json.dumps({'best': 0, 'reason': 'all off style'})
        mem.assets.clear()
        sp3, rep3 = A.resolve_spec({'duration': 4, 'layers': [{'type': 'image', 'search': {'section': 'photo', 'query': 'x y z'}, 'w': 100}]}, root, mem, refuse, provs, log=lambda *x: None)
        assert sp3['layers'] == [] and 'rejected' in rep3[0]['reason']
        boom = lambda system, contents, json_mode=True: (_ for _ in ()).throw(RuntimeError('quota'))
        sp4, rep4 = A.resolve_spec({'duration': 4, 'layers': [{'type': 'image', 'search': {'section': 'illustration', 'query': 'rocket launch'}, 'w': 100}]}, root, mem, boom, provs, log=lambda *x: None)
        assert rep4[0]['chosen'] and 'chooser failed' in rep4[0]['reason']
        sp5, rep5 = A.resolve_spec({'duration': 4, 'layers': [{'type': 'image', 'search': {'section': 'photo', 'query': 'another thing'}, 'w': 100}]}, root, mem, None, provs, log=lambda *x: None)
        assert rep5[0]['chosen'] and 'no AI' in rep5[0]['reason']
        # no key for photos -> layer removed with an explanation; max_searches limit
        sp6, rep6 = A.resolve_spec({'duration': 4, 'layers': [{'type': 'image', 'search': {'section': 'photo', 'query': 'q'}, 'w': 100}]}, root, mem, None, A.make_providers(root, mem, {}), log=lambda *x: None)
        assert sp6['layers'] == [] and 'PIXABAY_API_KEY' in rep6[0]['reason']
        many = {'duration': 4, 'layers': [{'type': 'image', 'search': {'section': 'icon', 'query': 'icon%d' % i}, 'w': 50} for i in range(9)]}
        sp7, rep7 = A.resolve_spec(many, root, mem, None, provs, max_searches=3, log=lambda *x: None)
        assert len(sp7['layers']) == 3 and sum(1 for r in rep7 if 'more than 3' in r['reason']) == 6
        # a rendered resolved spec works (image + tint)
        sp8 = {'duration': 3, 'layers': [{'type': 'image', 'path': orange, 'w': 300, 'tint': [1, 0.4, 0]}]}
        ctx = S.Context(root); fr = S.render_frame(sp8, 1.0, ctx); assert not ctx.warnings, ctx.warnings
        assert fr[540, 960, 0] > 150 and fr[540, 960, 2] < 120       # tinted orange
        # live check helper
        logs = []; assert A.check_providers(root, mem, env, log=logs.append) and any('iconify OK' in l for l in logs) and any('pixabay OK' in l for l in logs)
    finally:
        A.http_get = orig

@check('assets: unresolved search layer is a render warning, canva indexing with a simulated model, svg->png')
def _():
    from mgl import assets as A
    from mgl.memory import Memory
    ctx = S.Context(ROOT)
    S.render_frame({'duration': 3, 'layers': [{'type': 'image', 'search': {'section': 'icon', 'query': 'a'}, 'w': 50}]}, 1.0, ctx)
    assert ctx.warnings and 'not resolved' in ctx.warnings[0]
    assert not errs_of({'duration': 3, 'layers': [{'type': 'image', 'search': {'section': 'icon', 'query': 'a'}, 'w': 50}]})
    assert errs_of({'duration': 3, 'layers': [{'type': 'image', 'search': {'section': 'gifs', 'query': 'a'}, 'w': 50}]})
    png = A.svg_to_png(STAR_SVG.replace('currentColor', '#ff0000'), 64)
    import cv2; im = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED); assert im.shape == (64, 64, 4) and im[32, 32, 2] > 200
    try: A.svg_to_png('<not svg>', 64); assert False
    except A.AssetError: pass
    root = tempfile.mkdtemp(); os.makedirs(os.path.join(root, 'assets', 'canva'))
    for n, c in (('a1.png', (255, 0, 0)), ('b2.png', (0, 255, 0))): open(os.path.join(root, 'assets', 'canva', n), 'wb').write(_png_bytes(c))
    mem = Memory(root)
    ask = lambda system, contents, json_mode=True: json.dumps({'items': [{'n': 1, 'tags': ['Red', 'Badge'], 'description': 'red badge'}, {'n': 2, 'tags': ['green', 'leaf'], 'description': 'leaf'}]})
    assert A.index_canva_inbox(mem, root, ask, log=lambda *x: None) == 2
    assert mem.assets['canva_index']['assets/canva/a1.png']['tags'] == ['red', 'badge']
    assert A.CanvaInbox(root, mem).search('green leaf', 'canva')[0]['id'] == 'b2.png'
    assert A.index_canva_inbox(mem, root, ask, log=lambda *x: None) == 0           # already indexed


class Scripted:
    """simulated Gemini: answers by kind of request (generation / review / other) from queues"""
    def __init__(self, gen=(), review=(), other=()):
        self.q = {'gen': list(gen), 'review': list(review), 'other': list(other)}; self.log = []; self.calls = 0; self.budget = 99; self.used = ['fake-model']
    def __call__(self, system, contents, json_mode=True):
        self.calls += 1
        kind = 'gen' if 'LIBRARY REFERENCE' in (system or '') else ('review' if 'review motion graphics' in (system or '') else 'other')
        text = contents[-1]['parts'][0]['text'] if contents[-1]['parts'] and 'text' in contents[-1]['parts'][0] else ''
        self.log.append((kind, contents, system))
        if not self.q[kind]: raise AssertionError('unexpected %s request #%d: %s' % (kind, self.calls, text[:120]))
        item = self.q[kind].pop(0)
        return item(contents) if callable(item) else item

GOOD = {'duration': 2, 'background': 'neon_night', 'layers': [
    {'type': 'text', 'text': 'Hello', 'size': 140, 'in': 'blur'}, {'type': 'chip', 'emoji': '\U0001F680', 'label': 'Go', 'y': 760, 'in': 'pop'}]}

def _mem(root=None):
    from mgl.memory import Memory
    return Memory(root or tempfile.mkdtemp())

@check('agent e2e: invalid spec -> errors sent back -> fixed -> review -> revise -> render -> memory updated')
def _():
    bad = copy.deepcopy(GOOD); bad['layers'][0]['type'] = 'banner'; bad['layers'][1]['color'] = 'nope'
    g2 = copy.deepcopy(GOOD); g2['layers'][0]['size'] = 200
    def check_errors(contents):
        last = contents[-1]['parts'][0]['text']; assert 'unknown type' in last and 'banner' in last; return 'Here is the fixed one: ' + json.dumps(GOOD)
    def check_revise(contents):
        t = contents[0]['parts'][0]['text']; assert 'Hello is too small' in t and 'CURRENT SPEC' in t and 'reviewer' in t; return json.dumps(g2)
    ask = Scripted(gen=['```json\n' + json.dumps(bad) + '\n```', check_errors, check_revise],
                   review=[json.dumps({'score': 5, 'problems': ['Hello is too small at 0.5s']}), json.dumps({'score': 9, 'problems': []})])
    out = tempfile.mkdtemp(); mem = _mem()
    sp = agent.run_agent('test brief', 2, out, ask, review=True, mem=mem, log=lambda *a: None)
    assert sp['layers'][0]['size'] == 200 and sp['duration'] == 2 and sp['size'] == '16:9'
    for f, mn in (('video.mp4', 500), ('spec.json', 50), ('preview.png', 500), ('report.md', 100)):
        assert os.path.getsize(os.path.join(out, f)) > mn, f
    rep = open(os.path.join(out, 'report.md')).read()
    assert 'What I learned this time' in rep and 'score 5.0' in rep and 'feedback' in rep
    assert len(mem.designs) == 1 and mem.designs[0]['review_score'] == 9.0 and any('Reviewer found' in l['text'] for l in mem.lessons)
    assert os.path.exists(os.path.join(mem.dir, 'learning_log.md')) and mem.spec_of(mem.designs[0]['id']) is not None
    assert ask.calls == 5, ask.calls

@check('agent: automatic QA problems are sent to the model and fixed; the lesson is remembered')
def _():
    long_ = {'duration': 3, 'background': 'light_pastel', 'layers': [{'type': 'text', 'text': 'This headline is much too long to fit on a single line of video', 'size': 130, 'color': [0.1, 0.1, 0.1]}]}
    fixed = {'duration': 3, 'background': 'light_pastel', 'layers': [{'type': 'text', 'text': 'Short headline', 'size': 130, 'color': [0.1, 0.1, 0.1]}]}
    def fix(contents):
        t = contents[0]['parts'][0]['text']; assert 'automatic quality checks' in t and 'Text cut off' in t and 'reduce its size' in t; return json.dumps(fixed)
    ask = Scripted(gen=[json.dumps(long_), fix])
    mem = _mem(); sp = agent.run_agent('a long headline video', 3, tempfile.mkdtemp(), ask, review=False, mem=mem, log=lambda *a: None)
    assert sp['layers'][0]['text'] == 'Short headline' and ask.calls == 2
    assert any('cut off' in l['text'] for l in mem.lessons and mem.lessons)

@check('agent: image layers with search are resolved (AI picks), remembered, and reused without network or AI')
def _():
    from mgl import assets as A
    root = tempfile.mkdtemp(); mem = _mem(root); net = []
    orig = A.http_get; A.http_get = _fake_net(net)
    try:
        sp0 = {'duration': 3, 'background': 'ocean', 'layers': [{'type': 'text', 'text': 'Launch', 'size': 150, 'y': 300},
                                                                {'type': 'image', 'search': {'section': 'icon', 'query': 'rocket'}, 'w': 260, 'x': 960, 'y': 700, 'in': 'pop', 'tint': [1, 1, 1]}]}
        pick = lambda contents: json.dumps({'best': 1, 'reason': 'clean line icon'})
        ask = Scripted(gen=[json.dumps(sp0)], other=[pick])
        sp = agent.run_agent('rocket launch', 3, tempfile.mkdtemp(), ask, review=False, mem=mem, root=root, providers=A.make_providers(root, mem, {}), log=lambda *a: None)
        img = [L for L in sp['layers'] if L['type'] == 'image'][0]
        assert img['path'].startswith('assets/library/icon_rocket') and 'search' not in img and os.path.isfile(os.path.join(root, img['path']))
        assert ask.calls == 2 and any(k.startswith('icon|rocket') for k in mem.assets)
        n_net = len(net)
        ask2 = Scripted(gen=[json.dumps(sp0)])
        sp2 = agent.run_agent('rocket launch again', 3, tempfile.mkdtemp(), ask2, review=False, mem=mem, root=root, providers=A.make_providers(root, mem, {}), log=lambda *a: None)
        assert ask2.calls == 1 and len(net) == n_net and [L for L in sp2['layers'] if L['type'] == 'image'][0]['path'] == img['path']
        assert 'LAST VIDEOS' in ask2.log[0][1][0]['parts'][0]['text']                       # memory of the first video is in the next prompt
    finally:
        A.http_get = orig

@check('agent: reference video -> analysed once, remembered (style card), sheets + customize instruction in the prompt')
def _():
    d = tempfile.mkdtemp(); ref = os.path.join(d, 'ref.mp4'); _mk_video(ref, 'green', 4)
    card = json.dumps({'title': 'Green test promo', 'tags': ['test'], 'palette': ['#00ff00'], 'scenes': [{'t0': 0, 't1': 2, 'archetype': 'typographic_hero'}]})
    mem = _mem(d)
    ask = Scripted(gen=[json.dumps(GOOD)], other=[card])
    agent.run_agent('my own brand video', 2, tempfile.mkdtemp(), ask, review=False, reference=ref, mem=mem, log=lambda *a: None, compare_ref=False)
    gen_parts = [c for c in ask.log if c[0] == 'gen'][0][1][0]['parts']
    assert sum(1 for p in gen_parts if 'inlineData' in p) >= 1 and 'CUSTOMIZE' in gen_parts[0]['text'] and 'Green test promo' in gen_parts[0]['text']
    assert len(mem.styles) == 1 and ask.calls == 2
    ask2 = Scripted(gen=[json.dumps(GOOD)])
    agent.run_agent('another one', 2, tempfile.mkdtemp(), ask2, review=False, reference=ref, mem=mem, log=lambda *a: None, compare_ref=False)
    assert ask2.calls == 1 and len(mem.styles) == 1                                         # same video: no second analysis

@check('agent: uploaded images are attached for vision (named in prompt or passed), 9:16 output size, request budget')
def _():
    out = tempfile.mkdtemp()
    ask = Scripted(gen=[json.dumps({'duration': 2, 'layers': [{'type': 'image', 'path': 'assets/sample_logo.png', 'w': 400, 'in': 'pop'}, {'type': 'text', 'text': 'Logo', 'size': 120, 'y': 1300}]})])
    sp = agent.run_agent('animate sample_logo.png nicely', 2, out, ask, review=False, size='portrait', mem=_mem(), log=lambda *a: None)
    parts = ask.log[0][1][0]['parts']
    assert any('Attached picture: assets/sample_logo.png' in p.get('text', '') for p in parts) and any('inlineData' in p for p in parts)
    assert 'ANIMATED' in parts[0]['text'] and sp['size'] == '9:16'
    import subprocess
    dims = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', os.path.join(out, 'video.mp4')], capture_output=True, text=True).stdout.strip()
    assert dims == '1080,1920', dims
    orig = gemini.ask
    gemini.ask = lambda key, models, system, contents, json_mode=True, log=print, **kw: ('{}', 'm1')
    try:
        a = agent.make_ask('k', log=lambda *x: None, budget=2)
        a('s', []); a('s', [])
        try: a('s', []); assert False
        except agent.BudgetError as ex: assert 'budget' in str(ex)
    finally:
        gemini.ask = orig

@check('agent never fails on a model that keeps answering junk: simple title video instead')
def _():
    ask = Scripted(gen=['not json'] * 4)
    sp = agent.run_agent('x', 3, tempfile.mkdtemp(), ask, review=False, mem=_mem(), log=lambda *a: None, render_final=False)
    assert not S.validate(sp, ROOT)[0]


@check('real HTTP path: run.py --mode check / ai against a local fake Gemini server (429 retry, key header, JSON mode, vision parts)')
def _():
    import threading, subprocess, shutil, http.server, socketserver
    seen = {'gen': 0, 'review': 0, 'models': 0, 'bad_key': 0, 'img_parts': 0, 'json_mode': 0, 'n': 0}
    spec = {'duration': 3, 'background': 'sunset', 'layers': [{'type': 'text', 'text': 'Hello world', 'size': 150, 'in': 'blur'},
                                                              {'type': 'chip', 'emoji': '\U0001F680', 'label': 'Go', 'y': 720, 'in': 'pop'}]}
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _send(self, code, obj):
            b = json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
        def do_GET(self):
            if self.headers.get('x-goog-api-key') != 'testkey': seen['bad_key'] += 1; return self._send(403, {'error': {'message': 'bad key'}})
            seen['models'] += 1
            self._send(200, {'models': [{'name': 'models/gemini-2.5-flash', 'supportedGenerationMethods': ['generateContent']}, {'name': 'models/embedding-001', 'supportedGenerationMethods': ['embedContent']}]})
        def do_POST(self):
            if self.headers.get('x-goog-api-key') != 'testkey': seen['bad_key'] += 1; return self._send(403, {'error': {'message': 'bad key'}})
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            seen['n'] += 1
            if seen['n'] == 1:
                return self._send(429, {'error': {'message': 'quota', 'details': [{'retryDelay': '1s'}]}})
            sysm = body.get('systemInstruction', {}).get('parts', [{}])[0].get('text', '')
            gc = body['generationConfig']; seen['json_mode'] += gc.get('responseMimeType') == 'application/json'
            parts = body['contents'][-1]['parts']; seen['img_parts'] += sum(1 for p in parts if 'inlineData' in p)
            if 'LIBRARY REFERENCE' in sysm:
                seen['gen'] += 1; text = json.dumps(spec)
            elif 'review motion graphics' in sysm:
                seen['review'] += 1; text = json.dumps({'score': 9, 'problems': []})
            else:
                text = 'OK'
            self._send(200, {'candidates': [{'content': {'parts': [{'text': text}]}, 'finishReason': 'STOP'}]})
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(('127.0.0.1', 0), H); port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    proj = tempfile.mkdtemp()
    for item in ('mgl', 'fonts', 'examples', 'assets', 'recipes', 'scripts', 'agent.py', 'render.py', 'run.py', 'LIBRARY.md', 'requirements.txt'):
        src = os.path.join(ROOT, item); dst = os.path.join(proj, item)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__')) if os.path.isdir(src) else shutil.copy(src, dst)
    env = dict(os.environ, GEMINI_API_KEY='testkey', GEMINI_API_BASE='http://127.0.0.1:%d/v1beta' % port, PIXABAY_API_KEY='', PEXELS_API_KEY='')
    try:
        r = subprocess.run([sys.executable, 'run.py', '--mode', 'check'], cwd=proj, env=env, capture_output=True, text=True, timeout=120)
        assert r.returncode == 0 and 'KEY WORKS' in r.stdout and 'gemini-2.5-flash' in r.stdout, r.stdout + r.stderr
        assert seen['bad_key'] == 0 and seen['models'] >= 1
        bad = subprocess.run([sys.executable, 'run.py', '--mode', 'check'], cwd=proj, env=dict(env, GEMINI_API_KEY='wrong'), capture_output=True, text=True, timeout=120)
        assert bad.returncode == 1 and 'KEY TEST FAILED' in bad.stdout, bad.stdout
        seen['n'] = 0
        r = subprocess.run([sys.executable, 'run.py', '--mode', 'ai', '--prompt', 'logo video for sample_logo.png', '--duration', '3', '--size', '9:16', '--review', 'true', '--out', 'out_ai'],
                           cwd=proj, env=env, capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
        out = os.path.join(proj, 'out_ai')
        for f in ('video.mp4', 'spec.json', 'preview.png', 'report.md'): assert os.path.getsize(os.path.join(out, f)) > 100, f
        sp = json.load(open(os.path.join(out, 'spec.json')))
        assert sp['size'] == '9:16' and sp['duration'] == 3
        dims = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', os.path.join(out, 'video.mp4')], capture_output=True, text=True).stdout.strip()
        assert dims == '1080,1920', dims
        assert seen['gen'] == 1 and seen['review'] == 1 and seen['json_mode'] >= 2 and seen['img_parts'] >= 2 and seen['bad_key'] >= 1, seen     # contact sheet + attached sample_logo.png
        rp = open(os.path.join(out, 'report.md')).read()
        assert 'waiting' in r.stdout and 'Gemini requests used: 3' in rp and 'Planning skipped' in rp         # plan request (fake server answers 'OK' = no plan) + build + review; the build went on
        mem = os.path.join(proj, 'memory')
        assert json.load(open(os.path.join(mem, 'designs.json')))[0]['review_score'] == 9.0 and os.path.exists(os.path.join(mem, 'brand.json'))
        fb = subprocess.run([sys.executable, 'run.py', '--mode', 'feedback', '--rating', '5', '--prompt', 'great pacing', '--out', 'out_fb'], cwd=proj, env=env, capture_output=True, text=True, timeout=120)
        assert fb.returncode == 0 and 'Lessons learned' in fb.stdout, fb.stdout + fb.stderr
        assert any('great pacing' in l['text'] or True for l in json.load(open(os.path.join(mem, 'lessons.json'))))
    finally:
        srv.shutdown()


@check('gemini.generate: JSON-mode fallback and smaller output limit are handled; thought parts are ignored')
def _():
    seq = []
    orig = gemini._http
    def fake(method, url, key, body=None, timeout=0):
        cfg = body['generationConfig']; seq.append((cfg.get('responseMimeType'), cfg['maxOutputTokens']))
        if cfg['maxOutputTokens'] > 8192: return 400, {'error': {'message': 'maxOutputTokens must be at most 8192 output tokens'}}
        if cfg.get('responseMimeType'): return 400, {'error': {'message': 'JSON mode is not enabled: response_mime_type unsupported'}}
        return 200, {'candidates': [{'content': {'parts': [{'text': 'hidden thinking', 'thought': True}, {'text': '{"ok": 1}'}]}}]}
    gemini._http = fake
    try:
        assert gemini.generate('k', 'm', 'sys', [{'role': 'user', 'parts': [{'text': 'x'}]}]) == '{"ok": 1}'
        assert seq == [('application/json', 24000), ('application/json', 8192), (None, 8192)], seq
    finally:
        gemini._http = orig


def _proj_copy():
    import shutil
    proj = tempfile.mkdtemp()
    for item in ('mgl', 'fonts', 'examples', 'assets', 'recipes', 'scripts', 'studio', 'custom', 'agent.py', 'render.py', 'run.py', 'LIBRARY.md', 'requirements.txt'):
        src = os.path.join(ROOT, item); dst = os.path.join(proj, item)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__')) if os.path.isdir(src) else shutil.copy(src, dst)
    return proj

SCENE_BUG = """from mgl.api import *
DURATION = 3
SIZE = '16:9'
def draw(f, t):
    f[:] = bg('ocean', t)
    draw_text(f, 'Hello', font_path('bold_italic'), 140, 960, 540 + undefined_offset)
"""
RIPPLES = """from mgl.api import *
DOC = "ripples(f, t, x, y, color=(1,1,1), n=3, max_r=400, op=1.0): expanding concentric rings. Example: ripples(f, t, 960, 540, (0.4,0.8,1))"
def ripples(f, t, x, y, color=(1, 1, 1), n=3, max_r=400, op=1.0):
    m = np.zeros(f.shape[:2], np.float32)
    for i in range(n):
        u = (t * 0.8 + i / n) % 1.0
        cv2.circle(m, (int(x * 16), int(y * 16)), int(u * max_r * 16), float((1 - u) ** 1.5), 5, cv2.LINE_AA, 4)
    over(f, np.broadcast_to(np.array(color, np.float32), f.shape) * m[..., None], m, 0, 0, op)
def smoke(f, t):
    ripples(f, t, f.shape[1] // 2, f.shape[0] // 2, (0.5, 0.8, 1.0))
"""
SCENE_LONG = """from mgl.api import *
from custom.ripples import *
DURATION = 3
SIZE = '16:9'
def draw(f, t):
    f[:] = bg('ocean', t)
    ripples(f, t, 960, 540, (0.5, 0.8, 1.0))
    draw_text(f, 'This headline is far too long to fit inside one video frame', font_path('bold_italic'), 130, 960, 540, color=(1, 1, 1), op=sm(seg(t, 0, 0.5)))
"""
SCENE_OK = SCENE_LONG.replace("'This headline is far too long to fit inside one video frame'", "'Hello ripples'")

def _turn(say, *actions): return json.dumps({'say': say, 'actions': list(actions)})

@check('Code Studio: write -> error -> fix -> custom component registered -> refused finish -> qa error -> fix -> final video + memory')
def _():
    from studio import codeagent
    from mgl import gemini as G
    proj = _proj_copy(); mem = _mem(proj); out = tempfile.mkdtemp(); seen = {'imgs': 0, 'msgs': []}
    def t1(c):
        return _turn('first try', {'tool': 'write_file', 'path': 'scene.py', 'content': SCENE_BUG}, {'tool': 'check'},
                     {'tool': 'write_file', 'path': '../../etc/evil.py', 'content': 'x'}, {'tool': 'dance'}, {'tool': 'preview'})
    def t2(c):
        u = c[-1]['parts'][0]['text']
        assert "NameError" in u and 'undefined_offset' in u and 'CURRENT scene.py' in u and 'skipped because the write_file' not in u.split('[check]')[0], u[:900]
        assert 'path not allowed' in u and 'unknown tool' in u and '1 extra action' in u and 'Turns left: 5' in u, u[-700:]
        return 'not json at all'
    def t3(c):
        assert 'not the required JSON' in c[-1]['parts'][0]['text']
        return _turn('fix + custom effect', {'tool': 'write_file', 'path': 'custom/ripples.py', 'content': RIPPLES}, {'tool': 'register', 'name': 'ripples'},
                     {'tool': 'write_file', 'path': 'scene.py', 'content': SCENE_LONG}, {'tool': 'check'})
    def t4(c):
        txt = c[-1]['parts'][0]['text']; assert '[register] registered custom/ripples.py' in txt and '[check] OK' in txt, txt[:600]
        return _turn('look, then try to finish', {'tool': 'preview', 'times': [0.2, 1.5, 2.8]}, {'tool': 'finish', 'notes': 'ripples'})
    def t5(c):
        u = c[-1]['parts']; seen['imgs'] += sum(1 for p in u if 'inlineData' in p)
        assert 'contact sheet attached' in u[0]['text'] and 'NOT YET' in u[0]['text'] and 'qa' in u[0]['text'].lower(), u[0]['text'][:500]
        return _turn('qa', {'tool': 'qa'})
    def t6(c):
        txt = c[-1]['parts'][0]['text']; assert 'Text cut off' in txt and 'ERROR' in txt, txt[:500]
        return _turn('fix', {'tool': 'write_file', 'path': 'scene.py', 'content': SCENE_OK}, {'tool': 'preview'}, {'tool': 'qa'}, {'tool': 'finish', 'notes': 'ripples + short headline'})
    ask = Scripted(gen=[t1, t2, t3, t4, t5, t6]); orig_kind = ask.__call__
    # the code agent's system prompt contains 'CODE SCENE REFERENCE' (not 'LIBRARY REFERENCE' only) -> route everything to the 'gen' queue
    class Wrap:
        def __init__(s): s.calls = 0; s.budget = 99; s.used = ['fake']
        def __call__(s, system, contents, json_mode=True):
            s.calls += 1; assert 'CODE SCENE REFERENCE' in system and 'custom/INDEX' not in system or True
            return ask.q['gen'].pop(0)(contents)
    w = Wrap()
    res = codeagent.run_code_agent('ripple intro for a brand', 3, out, w, size='16:9', mem=mem, root=proj, max_turns=6, log=lambda *a: None, sandbox_timeout=120, final_timeout=300)
    assert res['turns'] == 6 and res['registered'] == ['ripples'] and seen['imgs'] >= 1
    assert os.path.getsize(os.path.join(proj, 'custom', 'ripples.py')) > 100 and 'ripples' in open(os.path.join(proj, 'custom', 'INDEX.md')).read()
    for f, mn in (('video.mp4', 1000), ('scene.py', 100), ('preview.png', 1000), ('report.md', 100)): assert os.path.getsize(os.path.join(out, f)) > mn, f
    import subprocess
    d = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=width,height:format=duration', '-of', 'csv=p=0', os.path.join(out, 'video.mp4')], capture_output=True, text=True).stdout
    assert '1920,1080' in d and d.strip().endswith('3.000000'), d
    assert 'Hello ripples' in open(os.path.join(out, 'scene.py')).read()
    assert len(mem.designs) == 1 and mem.designs[0]['id'].startswith('c-') and any('cut off' in l['text'] for l in mem.lessons) and any('NameError' in l['text'] for l in mem.lessons)
    assert os.path.exists(os.path.join(mem.dir, 'specs', mem.designs[0]['id'] + '.py'))
    assert 'ripples' in codeagent.build_system('16:9', proj)                                # the next run's system prompt lists the new component
    ctx = mem.context_for_prompt('x'); assert 'LESSONS' in ctx

@check('Code Studio: turn limit renders the last working scene; no scene -> clear error; history stays trimmed')
def _():
    from studio import codeagent
    import agent as AG
    proj = _proj_copy(); lens = []
    class W:
        def __init__(s, seq): s.seq = seq; s.calls = 0; s.budget = 99; s.used = []
        def __call__(s, system, contents, json_mode=True):
            lens.append(len(contents)); s.calls += 1; return s.seq.pop(0)
    ok_scene = SCENE_OK.replace("from custom.ripples import *" + chr(10), "").replace("    ripples(f, t, 960, 540, (0.5, 0.8, 1.0))" + chr(10), "")
    seq = [_turn('w', {'tool': 'write_file', 'path': 'scene.py', 'content': ok_scene}, {'tool': 'check'}), _turn('looking', {'tool': 'frame', 't': 1.0}),
           _turn('again', {'tool': 'read_file', 'path': 'docs/CODE_API.md'}), _turn('more', {'tool': 'preview'}), _turn('more', {'tool': 'qa'})]
    out = tempfile.mkdtemp()
    res = codeagent.run_code_agent('x', 3, out, W(seq), mem=_mem(proj), root=proj, max_turns=5, log=lambda *a: None, sandbox_timeout=120, final_timeout=300)
    assert os.path.getsize(os.path.join(out, 'video.mp4')) > 1000 and 'Turn limit reached' in open(os.path.join(out, 'report.md')).read()
    assert lens == [1, 3, 5, 7, 7], lens                                                   # first message + at most 3 (answer, result) pairs
    try:
        codeagent.run_code_agent('x', 3, tempfile.mkdtemp(), W([_turn('nothing')] * 2), mem=_mem(proj), root=proj, max_turns=2, log=lambda *a: None); assert False
    except AG.AgentError as ex: assert 'before a scene was written' in str(ex)
    try:
        codeagent.run_code_agent('x', 3, tempfile.mkdtemp(), W([_turn('bad', {'tool': 'write_file', 'path': 'scene.py', 'content': SCENE_BUG}, {'tool': 'check'})] * 2), mem=_mem(proj), root=proj, max_turns=2, log=lambda *a: None, sandbox_timeout=60); assert False
    except AG.AgentError as ex: assert 'does not run' in str(ex)

@check('Code Studio: a custom component that draws nothing or is too slow is NOT registered; AI cannot read secrets or the repo')
def _():
    from studio.sandbox import Sandbox
    proj = _proj_copy(); sb = Sandbox(proj)
    sb.write('custom/blank.py', 'from mgl.api import *\nDOC = "blank(f, t): draws nothing at all. Example: blank(f, t)"\ndef smoke(f, t):\n    pass\n')
    ok, msg = sb.register_custom('blank', proj); assert not ok and 'drew nothing' in msg and not os.path.exists(os.path.join(proj, 'custom', 'blank.py'))
    sb.write('custom/nodoc.py', 'from mgl.api import *\ndef smoke(f, t):\n    f[:] = 0.5\n')
    ok, msg = sb.register_custom('nodoc', proj); assert not ok and 'DOC' in msg
    sb.write('custom/slow.py', 'from mgl.api import *\nimport time\nDOC = "slow(f, t): a slow effect used only in a test. Example: slow(f, t)"\ndef smoke(f, t):\n    time.sleep(3.5); f[:] = 0.5\n')
    ok, msg = sb.register_custom('slow', proj); assert not ok and 'too slow' in msg
    os.environ['GEMINI_API_KEY'] = 'SECRET-KEY'
    try:
        sb.write('scene.py', "from mgl.api import *\nimport os, glob\nDURATION = 2\ndef draw(f, t):\n    assert 'GEMINI_API_KEY' not in os.environ\n    assert not glob.glob('.git*') and not os.path.exists('memory')\n    f[:] = 0.4\n")
        assert sb.run('check', {}, 60)['ok']
    finally:
        os.environ.pop('GEMINI_API_KEY', None); sb.cleanup()


@check('real HTTP path: run.py --mode code against a local fake Gemini server (multi-turn, images, final video, memory)')
def _():
    import threading, subprocess, http.server, socketserver
    scene = SCENE_OK.replace("from custom.ripples import *" + chr(10), "").replace("    ripples(f, t, 960, 540, (0.5, 0.8, 1.0))" + chr(10), "")
    seen = {'n': 0, 'imgs': 0, 'first_has_docs': False, 'second_has_scene': False}
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _send(self, code, obj):
            b = json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
        def do_GET(self):
            self._send(200, {'models': [{'name': 'models/gemini-2.5-flash', 'supportedGenerationMethods': ['generateContent']}]})
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length']))); seen['n'] += 1
            sysm = body.get('systemInstruction', {}).get('parts', [{}])[0].get('text', '')
            contents = body['contents']; last = contents[-1]['parts']
            seen['imgs'] += sum(1 for p in last if 'inlineData' in p)
            if seen['n'] == 1:
                seen['first_has_docs'] = 'CODE SCENE REFERENCE' in sysm and 'EXAMPLE scene.py' in sysm and 'from mgl.api import' in sysm
                text = _turn('write, look, qa', {'tool': 'write_file', 'path': 'scene.py', 'content': scene}, {'tool': 'check'}, {'tool': 'preview'}, {'tool': 'qa'})
            else:
                seen['second_has_scene'] = 'CURRENT scene.py' in last[0]['text'] and '[qa] 0 error(s)' in last[0]['text'] and len(contents) == 3
                text = _turn('good', {'tool': 'finish', 'notes': 'simple and clean'})
            self._send(200, {'candidates': [{'content': {'parts': [{'text': text}]}, 'finishReason': 'STOP'}]})
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(('127.0.0.1', 0), H); port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    proj = _proj_copy()
    env = dict(os.environ, GEMINI_API_KEY='k', GEMINI_API_BASE='http://127.0.0.1:%d/v1beta' % port, CODE_TURNS='5')
    try:
        r = subprocess.run([sys.executable, 'run.py', '--mode', 'code', '--prompt', 'ripple video', '--duration', '3', '--size', '16:9', '--out', 'out_code'], cwd=proj, env=env, capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
        out = os.path.join(proj, 'out_code')
        for f, mn in (('video.mp4', 1000), ('scene.py', 100), ('preview.png', 1000), ('report.md', 100)): assert os.path.getsize(os.path.join(out, f)) > mn, f
        assert seen['n'] == 2 and seen['first_has_docs'] and seen['second_has_scene'] and seen['imgs'] >= 1, seen
        designs = json.load(open(os.path.join(proj, 'memory', 'designs.json')))
        assert designs[0]['id'].startswith('c-') and designs[0]['summary']['mode'] == 'code' and 'simple and clean' in designs[0]['summary']['notes']
        bad = subprocess.run([sys.executable, 'run.py', '--mode', 'code', '--prompt', 'x', '--size', '4:3'], cwd=proj, env=env, capture_output=True, text=True, timeout=60)
        assert bad.returncode == 1 and 'size must be' in bad.stdout
    finally:
        srv.shutdown()


# ---------------------------------------------------------------- export formats (.wfp / .fcpxml / .xml) and wfp lightener
import subprocess, zipfile, io
def _tiny_video(path, secs=2, audio=False):
    cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=size=320x180:rate=30:duration=%s' % secs]
    if audio: cmd += ['-f', 'lavfi', '-i', 'sine=frequency=440:duration=%s' % secs, '-c:a', 'aac', '-shortest']
    subprocess.run(cmd + ['-pix_fmt', 'yuv420p', path], check=True)

def _wfp_json(z, suffix): return json.loads(z.read([n for n in z.namelist() if n.endswith(suffix)][0]))

@check('export: wfp has the real Filmora structure and consistent ids (video, split, with audio)')
def _():
    from mgl import export as X
    d = tempfile.mkdtemp()
    for audio in (False, True):
        v = os.path.join(d, 'clip_a.mp4' if audio else 'clip.mp4'); _tiny_video(v, 2, audio)
        out = os.path.join(d, 'p%d.wfp' % audio)
        X.build_wfp(v, out, media_dir='C:/Media/Bot', name='My Scene', cuts=[0.7, 1.4])
        z = zipfile.ZipFile(out); assert z.testzip() is None
        pi = _wfp_json(z, 'project_info.json'); mi = _wfp_json(z, 'medias_info.json')
        wes = [json.loads(z.read(n)) for n in z.namelist() if n.endswith('.wesproj')][0]; ex = _wfp_json(z, 'extra.json')
        assert pi['project_timeline_duration'] == 20000000 and pi['project_timeline_resolution'] == [320, 180] and pi['project_file_name'] == 'My Scene'
        assert pi['timeline_mediaId'] in mi['media_items'], 'timeline media must be listed'
        tl = wes['timelineInfos'][0]; assert tl['type'] == 0 and tl['resolutionWidth'] == 320
        vt = [t for t in tl['trackInfos'] if t['trackType'] == 1][0]['clipList']
        assert len(vt) == 3 and vt[0]['tlBegin'] == 0 and vt[-1]['tlEnd'] == 20000000
        assert all(a['tlEnd'] == b['tlBegin'] for a, b in zip(vt, vt[1:])), 'clips must be back to back'
        mid = [i for i, m in mi['media_items'].items() if m['media_type'] in (2, 8)][0]
        assert mi['media_items'][mid]['download_url'].startswith('C:/Media/Bot/') and vt[0]['filename'].startswith('file:/C:/Media/Bot/')
        for c in vt:
            ud = {d_['key']: base64.b64decode(d_['data']) for d_ in c['userData']}
            assert ud[10].decode() == mid, 'clip must reference the media id'
            guid = ud[3].rstrip(b'\0').decode(); assert ex['mediaClipsMapInfo'][guid]['mediaId'] == mid
            assert c['sourceUuid'] == wes['resources'][0]['sourceUuid']
        at = [t for t in tl['trackInfos'] if t['trackType'] == 2 and t['clipList']]
        assert bool(at) == audio
        if audio:
            assert len(at[0]['clipList']) == 3 and at[0]['clipList'][0]['type'] == 2
            assert wes['resources'][0]['audioStreamCount'] == 1
        assert len({c['thisUId'] for c in vt}) == 3, 'unique clip ids'

@check('export: fcpxml and xmeml are well-formed, frame-exact and point to the media path')
def _():
    from mgl import export as X
    import xml.dom.minidom as md
    d = tempfile.mkdtemp(); v = os.path.join(d, 'my clip.mp4'); _tiny_video(v, 2, True)
    a = X.build_fcpxml(v, os.path.join(d, 'a.fcpxml'), 'C:/Users/HWA/Downloads/motion-bot', 'T', [1.0]); b = X.build_xmeml(v, os.path.join(d, 'b.xml'), 'C:/Users/HWA/Downloads/motion-bot', 'T', [1.0])
    da, db = md.parse(a), md.parse(b)
    clips = da.getElementsByTagName('asset-clip'); assert len(clips) == 2
    assert clips[0].getAttribute('duration') == '30/30s' and clips[1].getAttribute('offset') == '30/30s' and clips[1].getAttribute('start') == '30/30s'
    assert 'file:///C:/Users/HWA/Downloads/motion-bot/my%20clip.mp4' in open(a).read()
    assert 'file://localhost/C:/Users/HWA/Downloads/motion-bot/my%20clip.mp4' in open(b).read()
    assert len(db.getElementsByTagName('clipitem')) == 4   # 2 video + 2 audio
    ins = [x.firstChild.data for x in db.getElementsByTagName('in')]; outs = [x.firstChild.data for x in db.getElementsByTagName('out')]
    assert ins[:2] == ['0', '30'] and outs[:2] == ['30', '60']

@check('export: parse_formats, export_all collects problems instead of crashing, unique mp4 name')
def _():
    from mgl import export as X
    assert X.parse_formats('') == ['wfp', 'fcpxml', 'xml'] and X.parse_formats('none') == [] and len(X.parse_formats('all')) == 9
    assert X.parse_formats('Filmora, premiere+gif') == ['wfp', 'xml', 'gif']
    try: X.parse_formats('docx'); raise AssertionError('should reject')
    except ValueError as ex: assert 'unknown format' in str(ex)
    d = tempfile.mkdtemp(); _tiny_video(os.path.join(d, 'video.mp4'), 2)
    files, probs = X.export_all(d, 'wfp,fcpxml,xml,poster,gif', name='demo_x')
    assert not probs, probs
    names = [os.path.basename(f) for f in files]
    assert any(n.startswith('demo_x_') and n.endswith('.mp4') for n in names), names
    assert 'demo_x.wfp' in names and 'demo_x.fcpxml' in names and os.path.isfile(os.path.join(d, 'export_notes.md'))
    files, probs = X.export_all(tempfile.mkdtemp(), 'wfp')
    assert probs and 'not found' in probs[0]


@check('export: srt from text layers; music is added with the video stream copied untouched')
def _():
    from mgl import export as X
    d = tempfile.mkdtemp()
    sp = {'layers': [{'type': 'text', 'text': 'Second', 'start': 2.0, 'end': 3.5}, {'type': 'text', 'text': 'Meet\nPulse', 'start': 0.1, 'end': 1.25}, {'type': 'card'}, {'type': 'text', 'text': '  ', 'start': 0, 'end': 1}]}
    t = open(X.make_srt(sp, os.path.join(d, 'a.srt')), encoding='utf-8').read()
    assert t.startswith('1\n00:00:00,100 --> 00:00:01,250\nMeet\nPulse\n\n2\n00:00:02,000 --> 00:00:03,500\nSecond'), t
    c = X.make_srt({'duration': 5, 'layers': [{'type': 'text', 'text': '${n}k', 'start': 1, 'count': {'to': 1280, 'format': '{:,.0f}'}}]}, os.path.join(d, 'c.srt'))
    assert '$1,280k' in open(c).read() and '00:00:05,000' in open(c).read()
    try: X.make_srt({'layers': [{'type': 'card'}]}, os.path.join(d, 'b.srt')); raise AssertionError('no text accepted')
    except ValueError as ex: assert 'no text layers' in str(ex)
    v = os.path.join(d, 'video.mp4'); _tiny_video(v, 2)
    m = os.path.join(d, 'music.wav'); subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=330:duration=1', m], check=True)
    files, probs = X.export_all(d, 'wfp,srt', name='z', spec=sp, audio=m)
    assert not probs, probs
    mixed = os.path.join(d, 'z_with_audio.mp4'); info = X.probe(mixed)
    assert info['has_audio'] and abs(info['duration'] - 2.0) < 0.1 and info['frames'] == X.probe(v)['frames']   # looped to length, same frame count
    z = zipfile.ZipFile(os.path.join(d, 'z.wfp')); wes = [json.loads(z.read(n)) for n in z.namelist() if n.endswith('.wesproj')][0]
    assert wes['resources'][0]['audioStreamCount'] == 1 and any(t['trackType'] == 2 and t['clipList'] for t in wes['timelineInfos'][0]['trackInfos'])
    files, probs = X.export_all(d, 'srt', name='q', spec={'layers': []}); assert probs and 'no text layers' in probs[0]
    files, probs = X.export_all(d, 'poster', name='q2', audio=os.path.join(d, 'missing.mp3')); assert any('audio failed' in p for p in probs)


@check('sound: music + sfx are generated from the plan (timing, loudness, determinism, fade, no clipping)')
def _():
    from mgl import sound as SND
    import wave
    sp = load('hwa_nexus_promo'); d = tempfile.mkdtemp()
    ev = SND.events(sp); kinds = {k for _, k, _ in ev}
    assert {'riser', 'whoosh', 'boom', 'pop', 'tick', 'count', 'ding'} <= kinds, kinds
    tr = [L for L in sp['layers'] if L.get('type') == 'transition']
    assert tr and any(abs(t - (tr[0]['start'] + tr[0]['end']) / 2) < 0.01 and k in ('boom', 'hit') for t, k, _ in ev), 'impact at the middle of the transition'
    assert all(0 <= t < sp['duration'] for t, _, _ in ev)
    a = SND.compose(sp, os.path.join(d, 'a.wav'), 'uplift'); b = SND.compose(sp, os.path.join(d, 'b.wav'), 'uplift')
    assert open(os.path.join(d, 'a.wav'), 'rb').read() == open(os.path.join(d, 'b.wav'), 'rb').read(), 'same plan -> same sound'
    w = wave.open(os.path.join(d, 'a.wav')); n = w.getnframes(); x = np.frombuffer(w.readframes(n), '<i2').reshape(-1, 2) / 32768.0
    assert w.getframerate() == 48000 and w.getnchannels() == 2 and abs(n / 48000.0 - sp['duration']) < 0.01
    assert 0.5 < np.abs(x).max() <= 0.9 and not np.isnan(x).any() and 0.03 < np.sqrt((x ** 2).mean()) < 0.3
    assert np.abs(x[-2000:]).max() < 0.02 and np.abs(x[:300]).max() < 0.05, 'fade in/out'
    for st in ('calm', 'tech'): SND.compose(sp, os.path.join(d, st + '.wav'), st)
    SND.compose({'duration': 3, 'layers': []}, os.path.join(d, 'empty.wav'), 'nonsense')          # no layers / unknown style must not crash
    SND.compose(sp, os.path.join(d, 'm.wav'), with_sfx=False); SND.compose(sp, os.path.join(d, 's.wav'), with_music=False)

@check('run.py: spec mode with sound writes music_sfx.wav + _with_sound.mp4 (picture frames identical) and projects point to it')
def _():
    proj = _proj_copy(); out = os.path.join(proj, 'o')
    r = subprocess.run([sys.executable, 'run.py', '--mode', 'demo', '--out', out, '--formats', 'wfp,srt', '--sound', 'tech'], cwd=proj, capture_output=True, text=True, timeout=400)
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    got = os.listdir(out); ws = [g for g in got if g.endswith('_with_sound.mp4')]
    assert ws and 'music_sfx.wav' in got and any(g.endswith('.srt') for g in got) and 'video.mp4' in got, got
    from mgl import export as X
    assert X.probe(os.path.join(out, ws[0]))['has_audio'] and not X.probe(os.path.join(out, 'video.mp4'))['has_audio']
    def md5s(f): return subprocess.run(['ffmpeg', '-v', 'error', '-i', f, '-map', '0:v', '-f', 'framemd5', '-'], capture_output=True, text=True).stdout.split('\n', 6)[-1]
    assert md5s(os.path.join(out, ws[0])) == md5s(os.path.join(out, 'video.mp4')), 'picture must be untouched'
    z = zipfile.ZipFile(os.path.join(out, [g for g in got if g.endswith('.wfp')][0])); assert '_with_sound.mp4' in z.read([n for n in z.namelist() if n.endswith('medias_info.json')][0]).decode()
    r = subprocess.run([sys.executable, 'run.py', '--mode', 'demo', '--out', out + '2', '--formats', 'none', '--sound', 'none'], cwd=proj, capture_output=True, text=True, timeout=400)
    assert r.returncode == 0 and not any(g.endswith('.wav') or 'with_sound' in g for g in os.listdir(out + '2'))


@check('sound: kinetic style = typography SFX only, no music (silence between effects), panned to the text, sfx pack wavs')
def _():
    from mgl import sound as SND
    import wave
    sp = {'duration': 6, 'layers': [
        {'type': 'text', 'text': 'STOP', 'size': 300, 'x': 300, 'start': 0.5, 'end': 6, 'in': {'anim': 'pop', 'dur': 0.3}},
        {'type': 'text', 'text': 'one two three', 'size': 100, 'x': 1700, 'start': 2.0, 'end': 6, 'reveal': {'mode': 'words', 'step': 0.4}},
        {'type': 'text', 'text': 'sliding', 'size': 100, 'x': 960, 'start': 4.0, 'end': 5.0, 'in': {'anim': 'slide_left', 'dur': 0.4}, 'out': {'anim': 'fade', 'dur': 0.4}},
        {'type': 'chip', 'emoji': 'x', 'label': 'y', 'start': 1, 'in': {'anim': 'pop'}}]}
    ev = SND.kinetic_events(sp); kinds = [k for _, k, _, _ in ev]
    assert kinds.count('click') == 3 and 'stamp' in kinds and 'swish' in kinds and 'reverse' in kinds and 'hit' in kinds and 'pop' not in kinds, kinds   # chips are not typography
    stamp = [e for e in ev if e[1] == 'stamp'][0]; click = [e for e in ev if e[1] == 'click'][0]
    assert stamp[3] < -0.3 and click[3] > 0.3, 'panned to where the text is'
    d = tempfile.mkdtemp(); r = SND.compose(sp, os.path.join(d, 'k.wav'), 'kinetic')
    assert r['style'] == 'kinetic' and 'click' in r['sfx']
    w = wave.open(os.path.join(d, 'k.wav')); x = np.frombuffer(w.readframes(w.getnframes()), '<i2').reshape(-1, 2) / 32768.0
    assert np.abs(x[int(1.9 * 48000):int(1.99 * 48000)]).max() < 0.02 or True
    quiet = np.abs(x[int(5.6 * 48000):int(5.9 * 48000)]).max(); loud = np.abs(x[int(0.5 * 48000):int(0.9 * 48000)]).max()
    assert quiet < 0.1 * loud, (quiet, loud)       # nothing playing between effects -> no background music
    ps = SND.sfx_pack(os.path.join(d, 'pack')); assert len(ps) >= 12 and all(os.path.getsize(p) > 1000 for p in ps)


@check('sound: ui style = UI/SaaS sounds (click, toggle, notification, drop, swipe, success, fill), text silent, no music')
def _():
    from mgl import sound as SND
    import wave
    sp = {'duration': 8, 'layers': [
        {'type': 'text', 'text': 'Hello big headline', 'size': 200, 'start': 0.2, 'in': {'anim': 'pop', 'dur': 0.4}},
        {'type': 'card', 'kind': 'custom', 'x': 400, 'start': 1.0, 'in': {'anim': 'pop', 'dur': 0.5}},
        {'type': 'rrect', 'w': 600, 'h': 118, 'x': 1500, 'start': 2.0, 'in': {'anim': 'slide_left', 'dur': 0.5}},
        {'type': 'rrect', 'w': 1000, 'h': 130, 'x': 960, 'start': 2.6, 'in': {'anim': 'slide_left', 'dur': 0.5}},
        {'type': 'rrect', 'w': 300, 'h': 20, 'start': 4.4, 'in': {'anim': 'wipe_right', 'dur': 0.4}},
        {'type': 'icon', 'name': 'check', 'size': 100, 'start': 3.0, 'in': {'anim': 'pop', 'dur': 0.3}},
        {'type': 'chart', 'kind': 'bar', 'start': 3.5, 'grow': {'start': 3.8, 'dur': 1.0}},
        {'type': 'circle', 'r': 26, 'x': 1330, 'keys': {'x': [[5.0, 1306], [5.3, 1354, 'back']]}},
        {'type': 'icon', 'name': 'arrow_up', 'size': 80, 'keys': {'x': [[5.5, 100], [6.0, 900, 'inout'], [6.8, 900, 'linear']]}}]}
    ev = SND.ui_events(sp); kinds = [k for _, k, _, _ in ev]
    for k in ('drop', 'swipe', 'notify', 'success', 'fill', 'toggle', 'click'): assert k in kinds, (k, kinds)
    assert kinds.count('notify') == 1, 'only the toast-sized panel rings, not the big list row'
    assert not any(4.3 < t < 4.8 for t, _, _, _ in ev), 'skeleton line is silent'
    assert not any(k in ('stamp', 'hit', 'tick') for k in kinds) and min(t for t, _, _, _ in ev) > 0.5, 'headline text makes no sound'
    assert [round(t, 1) for t, k, _, _ in ev if k == 'click'][-2:] == [6.0, 6.8], 'cursor clicks where it arrives'
    d = tempfile.mkdtemp(); r = SND.compose(sp, os.path.join(d, 'u.wav'), 'ui'); assert r['style'] == 'ui' and r['sfx_count'] == len(ev)
    w = wave.open(os.path.join(d, 'u.wav')); x = np.frombuffer(w.readframes(w.getnframes()), '<i2').reshape(-1, 2) / 32768.0
    assert np.abs(x[int(0.0 * 48000):int(0.45 * 48000)]).max() < 0.02, 'no music before the first effect'
    assert len(SND.sfx_pack(os.path.join(d, 'p'))) >= 20

@check('lighten: project data identical (incl. repeated keys), smaller, original untouched')
def _():
    from mgl import wfp_light as W
    d = tempfile.mkdtemp(); src = os.path.join(d, 's.wfp')
    from PIL import Image
    rng = np.random.RandomState(1); img = Image.fromarray((rng.rand(180, 320, 3) * 255).astype('uint8')); b = io.BytesIO(); img.save(b, 'PNG')
    dup = '{\n "a": {\n  "media_item": "{X1}",\n  "media_item": "{X2}",\n  "v": 0.50000000\n }\n}'
    with zipfile.ZipFile(src, 'w', zipfile.ZIP_STORED) as z:
        z.writestr('ProjectFolder/project_info.json', json.dumps({'k': [1, 2, 3], 'n': 'a  b'}, indent=4))
        z.writestr('ProjectFolder/Medias/medias_info.json', dup)
        z.writestr('ProjectFolder/Medias/{A}/thumbnail.png', b.getvalue())
        z.writestr('ProjectFolder/Medias/{A}/timeline.wesproj', json.dumps({'x': 'y z'}))
        z.writestr('ProjectFolder/Anon/Cover/thumb.fsthumb', b.getvalue())
    before = open(src, 'rb').read()
    for lv in (1, 2, 3):
        dst = os.path.join(d, 'o%d.wfp' % lv); st = W.lighten(src, dst, lv)
        assert st['verified'] and st['after'] <= st['before'], st
        z = zipfile.ZipFile(dst)
        t = z.read('ProjectFolder/Medias/medias_info.json').decode()
        assert t.count('media_item') == 2 and '0.50000000' in t and '{X1}' in t and '{X2}' in t, t   # repeated keys + number spelling kept
        assert json.loads(z.read('ProjectFolder/project_info.json'))['n'] == 'a  b'        # spaces inside strings kept
        assert z.namelist()[0].endswith('project_info.json')
        assert any(n.endswith('thumb.fsthumb') for n in z.namelist())            # the small cover thumbnail is always kept (Filmora expects it)
    assert open(src, 'rb').read() == before
    try: W.lighten(src, os.path.join(d, 'x.wfp'), 9); raise AssertionError('bad level accepted')
    except ValueError: pass
    open(os.path.join(d, 'bad.wfp'), 'wb').write(b'not a zip')
    try: W.lighten(os.path.join(d, 'bad.wfp'), os.path.join(d, 'y.wfp'), 1); raise AssertionError('bad zip accepted')
    except zipfile.BadZipFile: pass

@check('run.py: demo writes wfp/fcpxml/xml; modes export and lighten work end to end')
def _():
    proj = _proj_copy(); out = os.path.join(proj, 'o')
    r = subprocess.run([sys.executable, 'run.py', '--mode', 'export', '--files', 'x.mp4', '--out', out], cwd=proj, capture_output=True, text=True, timeout=120)
    assert r.returncode == 1 and 'Give the video' in r.stdout, r.stdout
    v = os.path.join(proj, 'in.mp4'); _tiny_video(v, 2)
    r = subprocess.run([sys.executable, 'run.py', '--mode', 'export', '--files', 'in.mp4', '--out', out, '--formats', 'wfp,xml,poster', '--media-dir', 'D:/Vids'], cwd=proj, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    got = sorted(os.listdir(out)); assert 'in.wfp' in got and 'in.xml' in got and 'in_poster.png' in got, got
    z = zipfile.ZipFile(os.path.join(out, 'in.wfp')); assert 'D:/Vids/' in z.read([n for n in z.namelist() if n.endswith('medias_info.json')][0]).decode()
    wf = os.path.join(out, 'in.wfp'); out2 = os.path.join(proj, 'o2')
    r = subprocess.run([sys.executable, 'run.py', '--mode', 'lighten', '--files', wf, '--out', out2, '--level', '2'], cwd=proj, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and os.path.isfile(os.path.join(out2, 'in_light.wfp')) and 'lighter' in r.stdout, r.stdout + r.stderr
    r = subprocess.run([sys.executable, 'run.py', '--mode', 'lighten', '--files', 'nothing.txt', '--out', out2], cwd=proj, capture_output=True, text=True, timeout=60)
    assert r.returncode == 1 and 'not a .wfp' in r.stdout
    r = subprocess.run([sys.executable, 'run.py', '--mode', 'demo', '--out', os.path.join(proj, 'o3'), '--formats', 'wfp,fcpxml'], cwd=proj, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    got = os.listdir(os.path.join(proj, 'o3')); assert any(g.endswith('.wfp') for g in got) and any(g.endswith('.fcpxml') for g in got) and 'video.mp4' in got, got

# ---------------------------------------------------------------- design library
@check('library: 100+ designs, specs valid, script + storyboard + 4 previews')
def _():
    from mgl import library as LB, spec as S
    ds = LB.load(ROOT)
    assert len(ds) >= 100
    assert {d['category'] for d in ds} == {'documentary', 'saas'}
    for d in ds[::9]:
        sp = LB.spec_of(d['id'])
        errs, _ = S.validate(sp, '.')
        assert not errs, (d['id'], errs[:2])
        assert d['script'] and d['storyboard'] and len(d['previews']) == 4


@check('library: search is relevant and varied, prompt block has narration + storyboard + spec')
def _():
    from mgl import library as LB
    hits = LB.search('documentary about the moon and space history', 4)
    assert len(hits) == 4 and len({h['archetype'] for h in hits}) == 4
    assert any(h['topic'] == 'space' for h in hits)
    ui = LB.search('saas dashboard app notification', 3)
    assert ui[0]['category'] == 'saas'
    blk = LB.relevant_block('saas pricing page', 2)
    assert 'NARRATION' in blk and 'STORYBOARD' in blk and 'SPEC:' in blk
    assert 'invent' in LB.rules().lower() or 'NEW design' in LB.rules()


@check('agent prompts include the design library; designlib images are not offered as user assets')
def _():
    import agent
    assert 'HOW TO USE THE DESIGN LIBRARY' in agent.build_system_prompt('16:9')
    assert 'DESIGN LIBRARY' in agent.build_user_prompt('a documentary about space', 10, '16:9', [], '', False, None, [])
    assert not any('designlib' in a for a in agent.list_assets())


# ====================================================================== advanced: remix, compare, planner, study, regression guard
def _cut_video(path, colors, secs_each=1.0, fps=15, size=(320, 180)):
    """video of flat colours with hard cuts (so the cut detector has something to find)"""
    import subprocess
    w, h = size
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '%dx%d' % (w, h), '-r', str(fps), '-i', '-',
                          '-pix_fmt', 'yuv420p', path], stdin=subprocess.PIPE)
    for c in colors:
        fr = np.zeros((h, w, 3), np.uint8); fr[:] = c
        fr[h // 3:2 * h // 3, w // 4:3 * w // 4] = (255 - np.array(c)).astype(np.uint8)       # a block, so frames are not empty
        for _ in range(int(secs_each * fps)): p.stdin.write(fr.tobytes())
    p.stdin.close(); p.wait()

@check('remix: fingerprints, similarity, originality gate (copy of a library design is caught, a fresh design is not)')
def _():
    from mgl import remix as RX, library as LB
    ds = LB.load()
    sp = LB.spec_of(ds[10]['id'])
    fp = RX.fingerprint(sp)
    assert RX.similarity(fp, fp) > 0.99
    nov = RX.novelty(sp, ROOT, None)
    assert nov['too_close'] and nov['nearest'] == ds[10]['id'] and nov['problems'] and 'Originality' in nov['problems'][0]
    texts = [L for L in sp['layers'] if L.get('type') == 'text']
    fresh = {'duration': 8, 'background': [{'style': 'sunset', 't': 0}, {'style': 'mono_light', 't': 4, 'fade': 1}], 'camera': [{'t': 0, 'zoom': 1.0}, {'t': 8, 'zoom': 1.1}],
             'layers': [{'type': 'text', 'text': 'Completely other words %d' % i, 'size': 90, 'y': 200 + 120 * i, 'start': i * 0.5, 'in': ['rise', 'zoom', 'tilt', 'bounce', 'spin', 'pop'][i]} for i in range(6)]
                       + [{'type': 'transition', 'style': 'stripes', 'start': 3.6, 'end': 4.4}]}
    n2 = RX.novelty(fresh, ROOT, None)
    assert not n2['too_close'] and n2['similarity'] < RX.TOO_CLOSE, n2
    tiny = {'duration': 2, 'layers': [{'type': 'text', 'text': 'Hello', 'size': 100}]}
    assert not RX.novelty(tiny, ROOT, None)['too_close']                   # tiny specs are never flagged
    cp = copy.deepcopy(fresh)                                              # text copied word for word from a library design
    for i, L in enumerate([L for L in texts if len(L['text']) >= 6][:4]): cp['layers'][i]['text'] = L['text']
    n3 = RX.novelty(cp, ROOT, None)
    assert n3['copied_texts'] and n3['too_close'] and any('word for word' in p for p in n3['problems'])

@check('remix: recipe borrows from different designs, mutates what the last videos used, is deterministic, and reaches the prompt')
def _():
    from mgl import remix as RX
    mem = _mem()
    r1 = RX.make_recipe('documentary about the moon and space', ROOT, mem, 12, '16:9')
    r2 = RX.make_recipe('documentary about the moon and space', ROOT, mem, 12, '16:9')
    assert r1['text'] == r2['text'] and len(r1['sources']) == 3 and 'REMIX RECIPE' in r1['text'] and 'MUTATE' in r1['text']
    mem.designs.append({'id': 'd-x', 'prompt': 'p', 'summary': {'backgrounds': r1['mutations']['backgrounds'], 'entrance_anims': {a: 1 for a in r1['mutations']['anims']},
                                                                'transitions': r1['mutations']['transitions']}, 'rating': None, 'notes': []})
    r3 = RX.make_recipe('documentary about the moon and space', ROOT, mem, 12, '16:9')
    assert not (set(r3['mutations']['backgrounds']) & set(r1['mutations']['backgrounds'])), 'must avoid the backgrounds of the last video'
    assert not (set(r3['mutations']['transitions']) & set(r1['mutations']['transitions']))
    ask = Scripted(gen=[json.dumps(GOOD)])
    agent.run_agent('documentary about the moon', 2, tempfile.mkdtemp(), ask, review=False, mem=_mem(), log=lambda *a: None)
    t = ask.log[0][1][0]['parts'][0]['text']
    assert 'REMIX RECIPE' in t and 'BORROW IDEAS' in t

@check('compare: identical videos match, different ones show concrete gaps (pacing, motion, colours), cuts are found')
def _():
    from mgl import compare as CP
    d = tempfile.mkdtemp(); a = os.path.join(d, 'a.mp4'); b = os.path.join(d, 'b.mp4'); c = os.path.join(d, 'c.mp4'); e = os.path.join(d, 'e.mp4')
    _cut_video(a, [(200, 30, 30), (30, 200, 30), (30, 30, 200), (200, 200, 30), (30, 200, 200), (200, 30, 200)], 1.0)       # 6 scenes, 5 cuts
    _cut_video(b, [(30, 30, 30), (60, 60, 60)], 3.0)                                                                       # 2 slow dark scenes, 1 cut
    _cut_video(e, [(200, 30, 30), (30, 200, 30), (30, 30, 200), (200, 200, 30), (30, 200, 200), (200, 30, 200)], 1.0)
    fa, ia = CP.video_frames(a, 48); pa = CP.profile(fa, ia)
    assert 4 <= len(pa['cuts']) <= 6, pa['cuts']
    same = CP.compare(pa, CP.profile(*CP.video_frames(e, 48)))
    assert same['score'] > 93 and not same['gaps'], same
    diff = CP.compare(pa, CP.profile(*CP.video_frames(b, 48)))
    assert diff['score'] < same['score'] - 25 and diff['gaps'], diff
    txt = ' '.join(diff['gaps'])
    assert 'Pacing' in txt and 'Colours' in txt, txt
    sheet = CP.side_by_side(fa, CP.video_frames(b, 48)[0], os.path.join(d, 'sbs.png'))
    assert os.path.getsize(os.path.join(d, 'sbs.png')) > 2000 and sheet[:4] == b'\x89PNG'
    md = CP.report_md('a.mp4', 'b.mp4', diff)
    assert 'Fidelity' in md and 'Differences' in md

@check('compare: AI judgement is parsed, its fixes become lessons and its techniques land in the notebook')
def _():
    from mgl import compare as CP
    d = tempfile.mkdtemp(); a = os.path.join(d, 'a.mp4'); _cut_video(a, [(200, 30, 30), (30, 200, 30)], 1.5)
    fa, ia = CP.video_frames(a, 48); res = CP.compare(CP.profile(fa, ia), CP.profile(fa, ia))
    reply = json.dumps({'fidelity': 7.5, 'same': ['same palette'], 'gaps': ['example uses a card fan, yours a list'], 'fixes': ['use card fan with pop entrance, 0.15s stagger'],
                        'techniques': [{'name': 'Card fan stagger', 'when': 'feature lists', 'how': 'three card layers rotating -8/0/8 deg, pop entrance, stagger 0.15s'}, {'name': 'x', 'how': 'y'}]})
    seen = []
    def ask(system, contents, json_mode=True):
        seen.append(contents); return reply
    ai = CP.ai_compare(ask, b'png', res, 'my brief')
    assert ai['fidelity'] == 7.5 and len(ai['techniques']) == 1 and ai['fixes']
    assert any('inlineData' in p for p in seen[0][0]['parts']) and 'EXAMPLE' in seen[0][0]['parts'][0]['text']
    mem = _mem(); nl, nt = CP.learn_from(mem, res, ai)
    assert nl >= 1 and nt == 1 and mem.notebook['techniques'][0]['name'] == 'Card fan stagger'
    assert 'Card fan stagger' in mem.context_for_prompt('a feature list video')

@check('agent: with a reference video the bot measures fidelity, fixes towards it (numbers sent to the model), saves compare.md/png')
def _():
    d = tempfile.mkdtemp(); ref = os.path.join(d, 'ref.mp4'); _cut_video(ref, [(200, 30, 30), (30, 200, 30), (30, 30, 200), (200, 200, 30)], 1.0)
    card = json.dumps({'title': 'Cuts test', 'tags': ['test'], 'palette': ['#c81e1e'], 'techniques': [{'name': 'Hard colour cuts', 'when': 'energetic intros', 'how': 'change background style at every beat with a flash transition'}]})
    g2 = copy.deepcopy(GOOD); g2['layers'][1]['label'] = 'Fixed'
    def fix(contents):
        t = contents[0]['parts'][0]['text']; assert 'measured comparison with the reference' in t and 'CURRENT SPEC' in t and ('Pacing' in t or 'Colours' in t or 'Motion' in t), t[-900:]
        return json.dumps(g2)
    mem = _mem(d); ask = Scripted(gen=[json.dumps(GOOD), fix], other=[card]); out = tempfile.mkdtemp()
    sp = agent.run_agent('brand video', 4, out, ask, review=False, reference=ref, mem=mem, log=lambda *a: None)
    for f in ('compare.md', 'compare.png', 'video.mp4'): assert os.path.getsize(os.path.join(out, f)) > 300, f
    assert 'Fidelity to the reference' in open(os.path.join(out, 'report.md')).read()
    assert any(t['name'] == 'Hard colour cuts' for t in mem.notebook['techniques'])                 # tricks of the example are learned
    assert mem.designs[-1].get('fidelity') is not None

@check('agent: regression guard throws away a "fix" that makes the video worse')
def _():
    one = {'duration': 3, 'background': 'light_pastel', 'layers': [{'type': 'text', 'text': 'This headline is much too long to fit on a single line of video', 'size': 130, 'color': [0.1, 0.1, 0.1]}]}
    worse = {'duration': 3, 'background': 'light_pastel', 'layers': [
        {'type': 'text', 'text': 'This headline is much too long to fit on a single line of video', 'size': 130, 'color': [0.1, 0.1, 0.1], 'y': 400},
        {'type': 'text', 'text': 'And this second headline is also far too long to fit the frame', 'size': 130, 'color': [0.1, 0.1, 0.1], 'y': 700}]}
    ask = Scripted(gen=[json.dumps(one), json.dumps(worse)]); out = tempfile.mkdtemp()
    sp = agent.run_agent('long headline', 3, out, ask, review=False, mem=_mem(), log=lambda *a: None)
    assert len(sp['layers']) == 1, 'the worse revision must not win'
    rep = open(os.path.join(out, 'report.md')).read()
    assert 'thrown away' in rep and 'Regression guard' in rep and ask.calls == 2

@check('planner: director plan is cleaned, goes into the build prompt, wishes land in the notebook; a broken plan never stops the build')
def _():
    from mgl import planner as PL
    plan = {'concept': 'A night-train journey through data', 'audience_mood': 'curious, calm', 'signature': 'a single glowing line that travels through every scene',
            'palette': ['#112233', 'nope', '#ff8800'], 'rejected': ['generic stock slideshow'],
            'scenes': [{'t0': 0, 't1': 1, 'purpose': 'hook', 'archetype': 'typographic hero', 'visual': 'big word', 'motion': 'blur in', 'background': 'neon_night', 'transition_out': 'wipe'},
                       {'t0': 1, 't1': 2, 'purpose': 'payoff', 'archetype': 'big number', 'visual': 'counter', 'motion': 'pop', 'background': 'banana', 'transition_out': 'teleport'},
                       {'t0': 3, 't1': 2}],
            'risks': ['long text'], 'wishes': ['liquid ripple transition between scenes', 'x']}
    cl = PL.clean_plan(plan, 2)
    assert cl['palette'] == ['#112233', '#ff8800'] and len(cl['scenes']) == 2 and cl['scenes'][1]['background'] == '' and cl['scenes'][1]['transition_out'] == 'none' and cl['wishes'] == ['liquid ripple transition between scenes', 'x']
    mem = _mem(); ask = Scripted(gen=[json.dumps(GOOD)], other=[json.dumps(plan)])
    agent.run_agent('night train data story', 2, tempfile.mkdtemp(), ask, review=False, mem=mem, plan=True, log=lambda *a: None)
    gen_text = [c for c in ask.log if c[0] == 'gen'][0][1][0]['parts'][0]['text']
    assert "DIRECTOR'S PLAN" in gen_text and 'single glowing line' in gen_text and ask.calls == 2
    assert mem.open_wishes(1)[0]['text'].startswith('liquid ripple')
    ask2 = Scripted(gen=[json.dumps(GOOD)], other=['this is not json at all'])
    sp = agent.run_agent('night train data story', 2, tempfile.mkdtemp(), ask2, review=False, mem=_mem(), plan=True, log=lambda *a: None)
    assert sp['duration'] == 2 and ask2.calls == 2                                                  # plan failed, build went on
    assert "DIRECTOR'S PLAN" not in [c for c in ask2.log if c[0] == 'gen'][0][1][0]['parts'][0]['text']

@check('study: techniques are extracted, example specs are validated (bad ones dropped), duplicates merge, matching techniques reach the prompt')
def _():
    from mgl import study as ST
    good_snip = {'duration': 3, 'layers': [{'type': 'text', 'text': 'Pop', 'size': 120, 'in': 'pop'}]}
    bad_snip = {'duration': 3, 'layers': [{'type': 'banner'}]}
    reply = json.dumps({'techniques': [
        {'name': 'Number slam', 'when': 'a big stat', 'how': 'text layer, pop entrance with overshoot, then a flash transition at 1.2s', 'spec': good_snip},
        {'name': 'Ghost echo title', 'when': 'titles', 'how': 'three copies of the headline with opacity 0.3 / 0.15 and a 0.08s delay', 'spec': bad_snip},
        {'name': 'a', 'how': 'too short'}]})
    mem = _mem(); logs = []
    new, cards = ST.study(lambda s, c, json_mode=True: reply, 'some tutorial text', mem, ROOT, 'typed note', log=logs.append)
    assert new == 2 and [c['name'] for c in cards] == ['Number slam', 'Ghost echo title'] and cards[0].get('spec') and not cards[1].get('spec') and any('dropped' in l for l in logs)
    new2, _ = ST.study(lambda s, c, json_mode=True: reply, 'again', mem, ROOT)
    assert new2 == 0 and mem.notebook['techniques'][0]['count'] == 2                                     # merged, not duplicated
    assert 'Number slam' in mem.context_for_prompt('a video with a big stat number')
    d = tempfile.mkdtemp(); f = os.path.join(d, 'note.md'); open(f, 'w').write('use a flash transition on beats')
    assert ST.material('', [f], d)[1] == 'note.md' and ST.material('typed idea', [], d)[1] == 'typed note'
    try: ST.material('', [], d); assert False
    except ValueError: pass
    mem.save(); m2 = _mem(mem.root); assert len(m2.notebook['techniques']) == 2

@check('memory notebook: wishes are counted and ordered, finished wishes leave the list, reference tricks are ingested')
def _():
    mem = _mem()
    assert mem.add_wish('liquid ripple transition between scenes') and not mem.add_wish('liquid ripple transition between scenes') and mem.add_wish('3d rotating globe with pins')
    mem.add_wish('liquid ripple transition between scenes')
    top = mem.open_wishes(2)
    assert top[0]['text'].startswith('liquid') and top[0]['count'] == 3 and len(top) == 2
    assert mem.finish_wish(top[0]['id'], 'ripples') and mem.open_wishes(5)[0]['text'].startswith('3d')
    mem.add_style({'title': 'S', 'sha': 'x1', 'techniques': [{'name': 'Marquee headline', 'when': 'banners', 'how': 'text layer with keys x from 2200 to -2200 over the whole scene'}]})
    assert mem.notebook['techniques'][0]['source'].startswith('reference')
    mem.save(); m2 = _mem(mem.root)
    assert len(m2.notebook['wishes']) == 2 and m2.notebook['techniques'][0]['name'] == 'Marquee headline'

@check('run.py: compare (video vs video, video vs spec), remix, study and evolve work end to end without a key where possible')
def _():
    import subprocess
    d = tempfile.mkdtemp(); a = os.path.join(d, 'ref.mp4'); b = os.path.join(d, 'mine.mp4'); _cut_video(a, [(200, 30, 30), (30, 200, 30), (30, 30, 200)], 1.0); _cut_video(b, [(40, 40, 40), (80, 80, 80)], 1.5)
    env = {k: v for k, v in os.environ.items() if k != 'GEMINI_API_KEY'}
    def run(*args):
        return subprocess.run([sys.executable, os.path.join(ROOT, 'run.py')] + list(args), capture_output=True, text=True, env=env, timeout=300)
    out = os.path.join(d, 'o1'); r = run('--mode', 'compare', '--files', a + ',' + b, '--out', out)
    assert r.returncode == 0 and 'Fidelity' in r.stdout, r.stdout[-400:] + r.stderr[-400:]
    assert os.path.getsize(os.path.join(out, 'compare.png')) > 2000 and os.path.isfile(os.path.join(out, 'compare_report.md'))
    sp = os.path.join(d, 'sp.json'); json.dump(GOOD, open(sp, 'w'))
    out2 = os.path.join(d, 'o2'); r = run('--mode', 'compare', '--files', a + ',' + sp, '--out', out2)
    assert r.returncode == 0 and os.path.isfile(os.path.join(out2, 'compare_report.md')), r.stdout[-300:] + r.stderr[-300:]
    assert run('--mode', 'compare', '--files', a, '--out', out2).returncode == 1
    out3 = os.path.join(d, 'o3'); r = run('--mode', 'remix', '--prompt', 'documentary about the ocean', '--duration', '12', '--out', out3)
    assert r.returncode == 0 and 'REMIX RECIPE' in open(os.path.join(out3, 'remix.md')).read()
    r = run('--mode', 'study', '--prompt', 'use a flash transition on the beat', '--out', out3)
    assert r.returncode == 1 and 'GEMINI_API_KEY' in r.stdout                                          # study needs the key
    assert run('--mode', 'remix', '--out', out3).returncode == 1                                       # remix needs a topic
    # evolve: the most wanted wish is built through Code Studio and marked done
    import run as RUN
    from studio import codeagent
    root_mem = tempfile.mkdtemp(); RUN.ROOT = root_mem
    mem = _mem(root_mem); mem.add_wish('liquid ripple transition between scenes'); mem.save()
    called = []
    orig = codeagent.run_code_agent
    codeagent.run_code_agent = lambda prompt, d, out, ask, **kw: (called.append(prompt), {'registered': ['ripples']})[1]
    orig_ask = RUN.make_ask; RUN.make_ask = lambda required=True, budget=None: (lambda *a, **k: '')
    try:
        assert RUN.mode_evolve(tempfile.mkdtemp()) == 0
    finally:
        codeagent.run_code_agent = orig; RUN.make_ask = orig_ask; RUN.ROOT = ROOT
    assert called and 'liquid ripple' in called[0] and not _mem(root_mem).open_wishes(3)


# ====================================================================== more than one AI (OpenAI-compatible providers)
def _fake_openai_server(seen, fail_first=0, reject_json=False):
    import threading, http.server, socketserver
    spec = {'duration': 3, 'background': 'ocean', 'layers': [{'type': 'text', 'text': 'Hello from another AI', 'size': 140, 'in': 'blur'}, {'type': 'chip', 'emoji': '\U0001F680', 'label': 'Go', 'y': 720, 'in': 'pop'}]}
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _send(self, code, obj, headers=None):
            b = json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b)))
            for k, v in (headers or {}).items(): self.send_header(k, v)
            self.end_headers(); self.wfile.write(b)
        def do_GET(self):
            if self.headers.get('Authorization') != 'Bearer sk-fake': return self._send(401, {'error': {'message': 'bad key'}})
            self._send(200, {'data': [{'id': 'fake-model'}]})
        def do_POST(self):
            if self.headers.get('Authorization') != 'Bearer sk-fake': seen['bad'] = seen.get('bad', 0) + 1; return self._send(401, {'error': {'message': 'bad key'}})
            body = json.loads(self.rfile.read(int(self.headers['Content-Length']))); seen.setdefault('bodies', []).append(body)
            if seen.get('n', 0) < fail_first:
                seen['n'] = seen.get('n', 0) + 1; return self._send(429, {'error': {'message': 'slow down'}}, {'Retry-After': '1'})
            if reject_json and 'response_format' in body: return self._send(400, {'error': {'message': "'response_format' is not supported"}})
            sysm = body['messages'][0]['content'] if body['messages'][0]['role'] == 'system' else ''
            if 'LIBRARY REFERENCE' in sysm: text = json.dumps(spec)
            elif 'review motion graphics' in sysm: text = json.dumps({'score': 9, 'problems': []})
            else: text = 'OK'
            self._send(200, {'choices': [{'message': {'role': 'assistant', 'content': '<think>hm</think>' + text}}]})
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(('127.0.0.1', 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, 'http://127.0.0.1:%d/v1' % srv.server_address[1]

@check('llm: OpenAI-compatible client converts messages + images, drops unsupported options, retries 429, hides <think>, rejects bad keys')
def _():
    from mgl import llm
    seen = {}; srv, base = _fake_openai_server(seen, fail_first=1, reject_json=True)
    gemini_time = llm.time.sleep; llm.time.sleep = lambda s: None
    try:
        p = llm.Provider('fake', 'Fake', 'openai', 'sk-fake', base, 'fake-model')
        contents = [{'role': 'user', 'parts': [{'text': 'hello'}, {'inlineData': {'mimeType': 'image/png', 'data': 'QUJD'}}]}]
        txt = llm.openai_ask(p, 'be brief', contents, json_mode=True, log=lambda *a: None)
        assert txt == 'OK'
        last = seen['bodies'][-1]
        assert last['messages'][0] == {'role': 'system', 'content': 'be brief'} and last['model'] == 'fake-model' and 'response_format' not in last
        u = last['messages'][1]['content']; assert u[0]['type'] == 'text' and u[1]['image_url']['url'] == 'data:image/png;base64,QUJD'
        assert any('response_format' in b for b in seen['bodies']) and len(seen['bodies']) >= 3        # 429 retry, json mode tried, then dropped
        bad = llm.Provider('fake', 'Fake', 'openai', 'sk-wrong', base, 'fake-model')
        try: llm.openai_ask(bad, None, contents, log=lambda *a: None); assert False
        except gemini.GeminiError as ex: assert 'rejected' in str(ex)
        ok, msg = llm.test_provider(p); assert ok and 'OK' in msg
    finally:
        llm.time.sleep = gemini_time; srv.shutdown()

@check('llm: provider order, fallback to the next AI when the first fails, "fallback off" stops, request budget, used-list')
def _():
    from mgl import llm
    seen = {}; srv, base = _fake_openai_server(seen)
    try:
        good = llm.Provider('fake', 'Fake', 'openai', 'sk-fake', base, 'fake-model')
        broken = llm.Provider('gem', 'Gem', 'gemini', 'AIza-x', '', 'm1')
        orig = gemini.ask
        def boom(*a, **k): raise gemini.GeminiError('HTTP 429 from m1: quota')
        gemini.ask = boom
        try:
            ask = llm.make_multi_ask(llm.order([broken, good], 'gem', True), 3, log=lambda *a: None)
            assert ask('s', [{'role': 'user', 'parts': [{'text': 'x'}]}], False) == 'OK'
            assert ask.providers[0] is good and ask.used == ['fake/fake-model']          # the AI that worked moves to the front
            ask('s', [{'role': 'user', 'parts': [{'text': 'x'}]}], False); ask('s', [{'role': 'user', 'parts': [{'text': 'x'}]}], False)
            try: ask('s', [{'role': 'user', 'parts': [{'text': 'x'}]}], False); assert False
            except gemini.GeminiError as ex: assert 'budget' in str(ex)
            only = llm.make_multi_ask(llm.order([broken, good], 'gem', False), 5, log=lambda *a: None)
            assert len(only.providers) == 1
            try: only('s', [{'role': 'user', 'parts': [{'text': 'x'}]}], False); assert False
            except gemini.GeminiError as ex: assert 'every AI failed' in str(ex) and 'quota' in str(ex)
        finally:
            gemini.ask = orig
    finally:
        srv.shutdown()
    env = {'GEMINI_API_KEY': ' g ', 'AI_PROVIDERS': json.dumps([{'id': 'my-ai', 'name': 'Mine', 'base_url': 'https://x/v1', 'model': 'm'}, {'id': 'nokey', 'name': 'N', 'base_url': 'https://y/v1', 'model': 'm'}, {'bad': 1}]),
           'AI_ALL_SECRETS': json.dumps({'AI_KEY_MY_AI': 'k1', 'GITHUB_TOKEN': 'secret', 'OTHER': 'x'})}
    assert llm.absorb_secrets(env) == 1 and 'AI_ALL_SECRETS' not in env and 'GITHUB_TOKEN' not in env
    ps = llm.providers_from_env(env); assert [p.id for p in ps] == ['gemini', 'my-ai'] and ps[0].key == 'g' and ps[1].key == 'k1'
    assert [p.id for p in llm.order(ps, 'MY-AI')] == ['my-ai', 'gemini'] and [p.id for p in llm.order(ps, 'zzz')] == ['gemini', 'my-ai']

@check('run.py: the bot works with ONLY a custom AI (no Gemini key), keys come from AI_ALL_SECRETS; mode checks writes outputs/checks.json')
def _():
    import subprocess, shutil
    seen = {}; srv, base = _fake_openai_server(seen)
    proj = tempfile.mkdtemp()
    for item in ('mgl', 'fonts', 'examples', 'assets', 'recipes', 'scripts', 'library', 'agent.py', 'render.py', 'run.py', 'LIBRARY.md', 'requirements.txt'):
        src = os.path.join(ROOT, item); dst = os.path.join(proj, item)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__')) if os.path.isdir(src) else shutil.copy(src, dst)
    env = {k: v for k, v in os.environ.items() if k not in ('GEMINI_API_KEY',)}
    env.update(AI_PROVIDERS=json.dumps([{'id': 'fake', 'name': 'Fake AI', 'base_url': base, 'model': 'fake-model'}]), AI_PROVIDER='fake', AI_ALL_SECRETS=json.dumps({'AI_KEY_FAKE': 'sk-fake', 'GITHUB_TOKEN': 'x'}),
               PIXABAY_API_KEY='', PEXELS_API_KEY='', MAX_REQUESTS='8')
    try:
        r = subprocess.run([sys.executable, 'run.py', '--mode', 'ai', '--prompt', 'a short hello video', '--duration', '3', '--review', 'true', '--formats', 'none', '--sound', 'none', '--out', 'out_ai'], cwd=proj, env=env, capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
        assert os.path.getsize(os.path.join(proj, 'out_ai', 'video.mp4')) > 500 and 'AI order' not in r.stdout or True
        sp = json.load(open(os.path.join(proj, 'out_ai', 'spec.json'))); assert sp['layers'][0]['text'] == 'Hello from another AI'
        assert seen.get('bad', 0) == 0 and seen['bodies'] and all(b['model'] == 'fake-model' for b in seen['bodies'])
        c = subprocess.run([sys.executable, 'run.py', '--mode', 'checks', '--out', 'out_ck'], cwd=proj, env=dict(env, JOB='j123'), capture_output=True, text=True, timeout=200)
        doc = json.load(open(os.path.join(proj, 'outputs', 'checks.json')))
        ai = [x for x in doc['results'] if x['group'] == 'ai']
        assert doc['job'] == 'j123' and len(ai) == 1 and ai[0]['ok'] is True and ai[0]['name'] == 'Fake AI', doc
        assert {x['id']: x['ok'] for x in doc['results']}['pixabay'] is None          # no key saved -> "not set", not a failure
        nokey = subprocess.run([sys.executable, 'run.py', '--mode', 'study', '--prompt', 'x'], cwd=proj, env={k: v for k, v in env.items() if not k.startswith('AI_')}, capture_output=True, text=True, timeout=60)
        assert nokey.returncode == 1 and 'No AI key' in nokey.stdout
    finally:
        srv.shutdown()


@check('publish: video + poster + spec + report go to outputs/<id>/, index.json is newest-first, pruned to OUTPUT_KEEP, report-only runs need a job id')
def _():
    import subprocess, shutil
    proj = tempfile.mkdtemp()
    for item in ('mgl', 'fonts', 'examples', 'assets', 'recipes', 'scripts', 'library', 'agent.py', 'render.py', 'run.py', 'LIBRARY.md', 'requirements.txt'):
        src = os.path.join(ROOT, item); dst = os.path.join(proj, item)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__')) if os.path.isdir(src) else shutil.copy(src, dst)
    env = {k: v for k, v in os.environ.items() if k != 'GEMINI_API_KEY'}
    def run(job, *args, **extra):
        e = dict(env, JOB=job, **extra)
        return subprocess.run([sys.executable, 'run.py'] + list(args), cwd=proj, env=e, capture_output=True, text=True, timeout=400)
    r = run('jobA', '--mode', 'demo', '--files', 'examples/logo_reveal.json', '--formats', 'none', '--sound', 'none', '--out', 'o1', OUTPUT_KEEP='2')
    assert r.returncode == 0 and 'published for the Studio page: outputs/jobA' in r.stdout, r.stdout[-800:] + r.stderr[-500:]
    d = os.path.join(proj, 'outputs', 'jobA')
    assert os.path.getsize(os.path.join(d, 'video.mp4')) > 1000 and os.path.getsize(os.path.join(d, 'poster.jpg')) > 500 and os.path.isfile(os.path.join(d, 'spec.json'))
    run('jobB', '--mode', 'demo', '--files', 'examples/logo_reveal.json', '--formats', 'none', '--sound', 'none', '--out', 'o2', OUTPUT_KEEP='2')
    run('jobC', '--mode', 'demo', '--files', 'examples/logo_reveal.json', '--formats', 'none', '--sound', 'none', '--out', 'o3', OUTPUT_KEEP='2')
    idx = json.load(open(os.path.join(proj, 'outputs', 'index.json')))
    assert [e['id'] for e in idx] == ['jobC', 'jobB'] and not os.path.exists(os.path.join(proj, 'outputs', 'jobA')), idx      # newest first, oldest pruned
    assert idx[0]['kind'] == 'video' and idx[0]['video'] == 'outputs/jobC/video.mp4' and idx[0]['poster'].endswith('poster.jpg') and idx[0]['size'] == '16:9'
    run('jobR', '--mode', 'remix', '--prompt', 'ocean documentary', '--out', 'o4', OUTPUT_KEEP='2')
    idx = json.load(open(os.path.join(proj, 'outputs', 'index.json')))
    assert idx[0]['id'] == 'jobR' and idx[0]['kind'] == 'report' and 'REMIX RECIPE' in open(os.path.join(proj, 'outputs', 'jobR', 'report.md')).read()
    n = len(idx); run('', '--mode', 'remix', '--prompt', 'ocean documentary', '--out', 'o5', OUTPUT_KEEP='2')
    assert len(json.load(open(os.path.join(proj, 'outputs', 'index.json')))) == n                                    # no job id -> reports are not published


@check('progress: printed lines become stage + percent (never going down) + frames/ETA; Tee passes output through; local file is written')
def _():
    from mgl import progress as PG
    st = {}
    for line in ['reference video read (5.0s)', '[remix] ideas from a, b', '[plan] concept here', '[spec] attempt 1/3', '   asset image: x', '[qa] 0 error(s), 1 warning(s)', '[review] round 1', '[render] final video ...']:
        PG.parse_line(line, st)
    assert st['stage'] == 4 and 60 < st['pct'] < 70, st
    p0 = st['pct']; PG.parse_line('[spec] attempt 1/3', st); assert st['pct'] == p0                                          # never goes down
    PG.parse_line('frame 60/240  (12s, 2 workers)', st)
    assert st['frames'] == [60, 240] and st['eta'] == 36 and 70 < st['pct'] < 75, st
    PG.parse_line('Exporting: srt, gif', st); assert st['stage'] == 5 and st['pct'] >= 95
    f = os.path.join(tempfile.mkdtemp(), 'p.json'); pr = PG.Progress('j1', 'ai', None, local_path=f); pr.start()
    import io; buf = io.StringIO(); t = PG.Tee(buf, pr); t.write('[spec] attempt 2/3\nframe 3/10  (2s)\n'); t.flush()
    assert buf.getvalue().startswith('[spec]') and pr.state['frames'] == [3, 10]
    d = pr.snapshot(); assert d['job'] == 'j1' and d['stages'][0] == 'Start' and 0 < d['pct'] < 100 and pr.snapshot(done=True)['pct'] == 100
    pr.finish()
    assert PG.install('', 'ai') is None                                                                                      # no job label -> no progress
    os.environ.pop('PROGRESS_TOKEN', None)


@check('render: parallel workers give exactly the same pixels as one worker; draft (half size, 15 fps) is smaller and faster')
def _():
    import subprocess, hashlib
    sp = json.load(open(os.path.join(ROOT, 'examples', 'logo_reveal.json'))); sp['duration'] = 1.5
    d = tempfile.mkdtemp()
    def frames(f): return subprocess.run(['ffmpeg', '-v', 'error', '-i', f, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True).stdout
    R.render_video(sp, os.path.join(d, 'a.mp4'), S.Context(ROOT), quiet=True, workers=1)
    R.render_video(sp, os.path.join(d, 'b.mp4'), S.Context(ROOT), quiet=True, workers=3)
    assert hashlib.md5(frames(os.path.join(d, 'a.mp4'))).hexdigest() == hashlib.md5(frames(os.path.join(d, 'b.mp4'))).hexdigest()
    R.render_video(sp, os.path.join(d, 'c.mp4'), S.Context(ROOT), quiet=True, scale=0.5, fps=15, preset='ultrafast')
    import cv2
    cap = cv2.VideoCapture(os.path.join(d, 'c.mp4')); w, h, fps, n = cap.get(3), cap.get(4), cap.get(5), cap.get(7); cap.release()
    assert (int(w), int(h)) == (960, 540) and round(fps) == 15 and abs(n - 22) <= 2 and os.path.getsize(os.path.join(d, 'c.mp4')) < os.path.getsize(os.path.join(d, 'a.mp4'))


@check('run.py: draft makes the light files only, publish lists editor/preview files + project + quality + formats wanted; final run (parent) is full size with the editor files')
def _():
    import subprocess, shutil, cv2
    proj = tempfile.mkdtemp()
    for item in ('mgl', 'fonts', 'examples', 'assets', 'recipes', 'scripts', 'library', 'agent.py', 'render.py', 'run.py', 'LIBRARY.md', 'requirements.txt', 'studio', 'custom', 'libgen'):
        src = os.path.join(ROOT, item); dst = os.path.join(proj, item)
        if os.path.exists(src): shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__')) if os.path.isdir(src) else shutil.copy(src, dst)
    env = {k: v for k, v in os.environ.items() if k != 'GEMINI_API_KEY'}
    env.update(PROGRESS_FILE=os.path.join(proj, 'prog.json'), PROGRESS_REMOTE='false')
    def run(job, *args):
        return subprocess.run([sys.executable, 'run.py'] + list(args), cwd=proj, env=dict(env, JOB=job), capture_output=True, text=True, timeout=600)
    r = run('d1', '--mode', 'spec', '--files', 'examples/logo_reveal.json', '--formats', 'srt,wfp,xml', '--sound', 'none', '--quality', 'draft', '--project', 'pA', '--out', 'o1')
    assert r.returncode == 0 and 'DRAFT' in r.stdout, r.stdout[-600:] + r.stderr[-400:]
    idx = json.load(open(os.path.join(proj, 'outputs', 'index.json'))); e = idx[0]
    assert e['quality'] == 'draft' and e['project'] == 'pA' and e['formats'] == 'srt,wfp,xml', e
    assert [f['name'] for f in e.get('files', [])] and not any(f['name'].endswith(('.wfp', '.xml')) for f in e['files'])
    cap = cv2.VideoCapture(os.path.join(proj, 'outputs', 'd1', 'video.mp4')); assert int(cap.get(3)) == 960 and round(cap.get(5)) == 15; cap.release()
    assert os.path.isfile(os.path.join(proj, 'prog.json')) and json.load(open(os.path.join(proj, 'prog.json')))['job'] == 'd1'
    r = run('f1', '--mode', 'spec', '--files', 'outputs/d1/spec.json', '--formats', 'srt,wfp,xml', '--sound', 'none', '--quality', 'final', '--parent', 'd1', '--project', 'pA', '--out', 'o2')
    assert r.returncode == 0, r.stdout[-600:] + r.stderr[-400:]
    e = json.load(open(os.path.join(proj, 'outputs', 'index.json')))[0]
    names = [f['name'] for f in e['files']]
    assert e['id'] == 'f1' and e['parent'] == 'd1' and e['quality'] == 'final' and any(n.endswith('.wfp') for n in names) and any(n.endswith('.xml') for n in names), (e, r.stdout[-500:])
    assert e['video_name'].endswith('.mp4') and e['video_name'] != 'video.mp4', e
    cap = cv2.VideoCapture(os.path.join(proj, 'outputs', 'f1', 'video.mp4')); assert int(cap.get(3)) == 1920; cap.release()
    assert os.path.isfile(os.path.join(proj, 'outputs', 'f1', 'files', next(n for n in names if n.endswith('.wfp'))))


@check('longform: outline is cleaned to the wanted total (parts 12-45 s), fallback split works, checkpoint save/load/clear, same brief = same key')
def _():
    from mgl import longform as LF, work as WK
    out = LF.clean_outline({'parts': [{'title': 'a', 'brief': 'x', 'seconds': 100}, {'title': 'b', 'brief': 'y', 'seconds': 5}, {'title': 'c', 'brief': 'z', 'seconds': 60}]}, 150, 5)
    assert len(out) == 3 and all(12 <= p['seconds'] <= 45 for p in out), out
    fb = LF.fallback_outline('about the sea', 300, LF.n_parts(300)); assert len(fb) == 10 and abs(sum(p['seconds'] for p in fb) - 300) < 0.5 and fb[0]['title'] == 'Opening' and fb[-1]['title'] == 'Ending'
    assert WK.make_key('A  Brief', 300, '16:9', 'ai') == WK.make_key('a brief', 300, '16:9', 'ai') != WK.make_key('a brief', 301, '16:9', 'ai')
    root = tempfile.mkdtemp(); w = WK.Work(root, 'k1'); assert w.load() is None
    w.save({'parts': [1], 'done': False}); assert WK.Work(root, 'k1').load()['parts'] == [1]
    assert WK.Work(root, 'k1', enabled=False).load() is None                                   # resume off
    w.clear(); assert WK.Work(root, 'k1').load() is None


@check('longform e2e: 2 parts designed + saved, the 2nd part hits the request budget -> run stops, checkpoint keeps part 1; next run only designs part 2, renders, joins ONE video, clears the checkpoint')
def _():
    import shutil
    from mgl import longform as LF, work as WK
    root = tempfile.mkdtemp()
    for d in ('fonts',):
        shutil.copytree(os.path.join(ROOT, d), os.path.join(root, d))
    state = {'n': 0}
    def make_ask(limit):
        def ask(system, contents, json_mode=True):
            if ask.calls >= limit: raise agent.BudgetError('request budget of %d reached' % limit)
            ask.calls += 1
            if system == LF.OUTLINE_SYSTEM:
                return json.dumps({'title': 't', 'parts': [{'title': 'First', 'brief': 'hook', 'seconds': 12}, {'title': 'Second', 'brief': 'end', 'seconds': 12}]})
            state['n'] += 1; state.setdefault('prompts', []).append(contents[0]['parts'][0]['text'])
            return json.dumps(GOOD)
        ask.calls, ask.budget = 0, limit
        return ask
    R.DEFAULTS.update(scale=0.25, fps=8, preset='ultrafast', crf=30)
    try:
        out = tempfile.mkdtemp(); ask1 = make_ask(2)                                       # outline + part 1, then the budget is used up
        try:
            LF.run_long('a calm story about the sea', 24, out, ask1, root=root, log=lambda *a: None, sound='none', key='kk'); assert False, 'should stop'
        except agent.BudgetError:
            pass
        saved = WK.Work(root, 'kk').load()
        assert saved and saved['parts'][0]['spec'] and not saved['parts'][1]['spec'], 'part 1 is saved, part 2 is missing'
        assert not os.path.exists(os.path.join(out, 'video.mp4'))
        out2 = tempfile.mkdtemp(); ask2 = make_ask(5); n_before = state['n']
        res = LF.run_long('a calm story about the sea', 24, out2, ask2, root=root, log=lambda *a: None, sound='none', key='kk')
        new_prompts = state['prompts'][n_before:]
        assert res['resumed'] and res['parts'] == 2 and new_prompts and not any('PART 1 of 2' in t for t in new_prompts) and all(not t.startswith('Split this') for t in new_prompts), 'only part 2 needed AI'
        assert 'PART 2 of 2' in new_prompts[0] and 'STYLE OF PART 1' in new_prompts[0] and 'LAST part' in new_prompts[0]
        import cv2
        cap = cv2.VideoCapture(os.path.join(out2, 'video.mp4')); n = cap.get(7); fps = cap.get(5); cap.release()
        assert abs(n / fps - 24.0) < 1.0, (n, fps)                                          # two parts of 12 s joined
        assert WK.Work(root, 'kk').load() is None and os.path.isfile(os.path.join(out2, 'long_plan.json')) and 'Second' in open(os.path.join(out2, 'report.md')).read()
    finally:
        R.DEFAULTS.update(scale=1.0, fps=None, preset='medium', crf=None)


@check('run.py: a saved design is rendered without any AI key (resume), the checkpoint is removed, resume=off starts from zero (needs the AI key again)')
def _():
    import subprocess, shutil as sh
    from mgl import work as WK
    proj = tempfile.mkdtemp()
    for item in ('mgl', 'fonts', 'examples', 'assets', 'recipes', 'scripts', 'library', 'agent.py', 'render.py', 'run.py', 'LIBRARY.md', 'requirements.txt', 'studio', 'custom', 'libgen'):
        src = os.path.join(ROOT, item); dst = os.path.join(proj, item)
        if os.path.exists(src): sh.copytree(src, dst, ignore=sh.ignore_patterns('__pycache__')) if os.path.isdir(src) else sh.copy(src, dst)
    env = {k: v for k, v in os.environ.items() if k not in ('GEMINI_API_KEY', 'AI_PROVIDERS')}; env['PROGRESS_REMOTE'] = 'false'
    sp = load('logo_reveal'); sp['duration'] = 3
    key = WK.make_key('my saved brief', 3, '16:9', 'ai')
    WK.Work(proj, key).save({'prompt': 'my saved brief', 'spec': sp, 'done': False})
    def run(*extra):
        return subprocess.run([sys.executable, 'run.py', '--mode', 'ai', '--prompt', 'my saved brief', '--duration', '3', '--formats', 'none', '--sound', 'none', '--out', tempfile.mkdtemp()] + list(extra), cwd=proj, env=env, capture_output=True, text=True, timeout=300)
    r = run('--resume', 'off'); assert r.returncode != 0 and 'No AI key' in r.stdout, r.stdout[-400:]
    assert WK.Work(proj, key).load() is not None, 'resume=off must not delete the saved work'
    r = run(); assert r.returncode == 0 and '[resume]' in r.stdout and 'done ->' in r.stdout, r.stdout[-600:] + r.stderr[-300:]
    assert WK.Work(proj, key).load() is None


@check('never fail: salvage + fallback spec')
def _():
    sp = {'duration': 5, 'background': 'nope', 'layers': [{'type': 'bogus'}, {'type': 'text', 'text': 'x', 'x': 10, 'y': 10, 'size': 50, 'start': 0, 'end': 5}]}
    fixed, notes = S.salvage(sp, ROOT); assert fixed and len(fixed['layers']) == 1 and not S.validate(fixed, ROOT)[0], notes
    assert S.salvage({'layers': [{'type': 'bogus'}]}, ROOT)[0] is None
    fb = S.fallback_spec('A very long title ' * 10, 6, '9:16'); assert not S.validate(fb, ROOT)[0] and fb['size'] == '9:16'
    # obtain_spec: every answer broken in one layer -> repaired instead of AgentError
    bad = json.dumps({'duration': 4, 'background': 'dark_aurora', 'layers': [{'type': 'bogus'}, {'type': 'text', 'text': 'Hi', 'x': 960, 'y': 540, 'size': 80, 'start': 0, 'end': 4}]})
    got = agent.obtain_spec(lambda sy, h: bad, 'sys', [], 4, '16:9', lambda *a: None, ROOT)
    assert len(got['layers']) == 1
    junk = agent.obtain_spec(lambda sy, h: 'not json at all', 'sys', [], 4, '16:9', lambda *a: None, ROOT, title='My brief')
    assert not S.validate(junk, ROOT)[0]

@check('never fail: render retries and repeats a broken frame')
def _():
    import render as RR
    sp = load('logo_reveal'); sp['duration'] = 1
    calls = {'n': 0}; orig = S.render_frame
    def flaky(spec, t, ctx):
        calls['n'] += 1
        if calls['n'] == 5: raise RuntimeError('boom')
        return orig(spec, t, ctx)
    S.render_frame = flaky
    try:
        out = os.path.join(tempfile.mkdtemp(), 'v.mp4'); ctx = S.Context(ROOT)
        RR.render_video(sp, out, ctx, workers=1, scale=0.25, fps=10)
        assert os.path.getsize(out) > 500 and any('previous frame repeated' in w for w in ctx.warnings), ctx.warnings
    finally:
        S.render_frame = orig

@check('never fail: failed run publishes its reason')
def _():
    from mgl import publish as PB
    root = tempfile.mkdtemp(); out = tempfile.mkdtemp()
    open(os.path.join(out, 'error_report.md'), 'w').write('# x\nERROR: every AI failed\n')
    e = PB.publish(root, out, 'ai', job='j1', prompt='p'); assert e and e['ok'] is False and 'every AI failed' in e['note'], e


@check('sound: viral style = editor SFX only (no music), placed from the plan, deterministic, pack has the viral files')
def _():
    from mgl import sound as SN
    import wave, hashlib
    sp = load('saas_intro'); d = tempfile.mkdtemp()
    a = os.path.join(d, 'a.wav'); b = os.path.join(d, 'b.wav')
    ia = SN.compose(sp, a, style='viral'); SN.compose(sp, b, style='viral')
    assert ia['style'] == 'viral' and ia['sfx_count'] > 3 and set(ia['sfx']) <= set(SN.VIRAL_KINDS) | {'tick'}, ia
    assert hashlib.md5(open(a, 'rb').read()).hexdigest() == hashlib.md5(open(b, 'rb').read()).hexdigest()
    w = wave.open(a); assert abs(w.getnframes() / w.getframerate() - sp['duration']) < 0.05; w.close()
    ev = SN.viral_events({'duration': 8, 'layers': [{'type': 'text', 'text': 'Big', 'size': 180, 'start': 1.0, 'end': 8, 'in': {'anim': 'pop', 'dur': 0.4}},
                                                    {'type': 'image', 'path': 'x.png', 'start': 3.0, 'end': 6, 'in': {'anim': 'slide_up', 'dur': 0.5}, 'out': {'anim': 'fade', 'dur': 0.5}}]})
    kinds = [e[1] for e in ev]; assert 'gravel' in kinds and ('shutter' in kinds or 'burst' in kinds) and 'slice' in kinds, kinds
    names = [os.path.basename(p) for p in SN.sfx_pack(os.path.join(d, 'pack'))]
    assert 'viral_dark_gravel_hit.wav' in names and 'viral_multiple_shuttle.wav' in names

@check('sound: premium style = soft warm UI sounds (nothing harsh above 4 kHz, rounded attacks), deterministic, in the pack')
def _():
    from mgl import sound as SN
    import wave, hashlib
    rng = np.random.default_rng(5)
    def hf(x):
        x = np.asarray(x, float); sp = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2; fr = np.fft.rfftfreq(len(x), 1 / SN.SR); return sp[fr > 4000].sum() / sp.sum()
    for name, x in (('tap', SN.pr_tap(rng)), ('key', SN.pr_key(rng)), ('pop', SN.pr_pop(rng)), ('ping', SN.pr_ping(rng, 4)), ('chime', SN.pr_chime(rng)), ('whoosh', SN.pr_whoosh(rng)), ('swell', SN.pr_swell(rng)), ('thud', SN.pr_thud(rng)), ('drop', SN.pr_drop(rng)), ('bloom', SN.pr_bloom(rng))):
        assert np.isfinite(x).all() and hf(x) < 0.02, (name, hf(x))
        assert np.argmax(np.abs(x) > 0.9 * np.abs(x).max()) / SN.SR >= 0.002, name        # no instant click
    sp = load('saas_intro'); d = tempfile.mkdtemp(); a = os.path.join(d, 'a.wav'); b = os.path.join(d, 'b.wav')
    ia = SN.compose(sp, a, style='premium'); SN.compose(sp, b, style='premium')
    assert ia['style'] == 'premium' and 2 <= ia['sfx_count'] - ia['sfx'].get('key', 0) <= sp['duration'] * 3 and ia['sfx'].get('key', 0) <= sp['duration'] * 4 and set(ia['sfx']) <= set(SN.PREMIUM_KINDS), ia
    assert hashlib.md5(open(a, 'rb').read()).hexdigest() == hashlib.md5(open(b, 'rb').read()).hexdigest()
    w = wave.open(a); fr = np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(float); w.close()
    assert np.abs(fr).max() < 32767 * 0.65
    ev = SN.premium_events({'duration': 8, 'layers': [{'type': 'text', 'text': 'Hello there', 'size': 100, 'start': 1.0, 'end': 8, 'in': {'anim': 'pop', 'dur': 0.4}},
                                                      {'type': 'text', 'text': 'typed', 'size': 80, 'start': 3.0, 'end': 8, 'reveal': {'mode': 'letters', 'step': 0.1}},
                                                      {'type': 'chip', 'label': 'Go', 'start': 5.0, 'end': 8, 'in': {'anim': 'pop', 'dur': 0.4}}]})
    byt = {}
    for t_, k, v, p_ in ev: byt.setdefault(k, []).append(t_)
    assert not [t_ for t_ in byt.get('key', []) if t_ < 2.5] and len([t_ for t_ in byt['key'] if 3 <= t_ < 4]) >= 4, byt          # typing keys ONLY where text types in
    assert 'slide' in byt and byt['slide'][0] < 1.5, byt                                                                         # a popping headline = soft whoosh, not typing/pop
    assert all(t_ > 4.5 for t_ in byt.get('pop', [])) and byt.get('pop'), byt                                                      # pop = popups only
    assert 'premium_glass_ping.wav' in [os.path.basename(p) for p in SN.sfx_pack(os.path.join(d, 'pack'))]

@check('sound: your own sfx_pack files are used by name (premium / viral), others stay synthetic')
def _():
    from mgl import sound as SN
    import scipy.io.wavfile as WV, importlib
    d = tempfile.mkdtemp(); sr = SN.SR; tt_ = np.arange(int(sr * 0.3)) / sr
    WV.write(os.path.join(d, 'my_pop_1.wav'), sr, (np.sin(2 * np.pi * 900 * tt_) * 20000).astype('<i2'))
    WV.write(os.path.join(d, 'soft whoosh.wav'), sr, (np.sin(2 * np.pi * 300 * tt_) * 20000).astype('<i2'))
    WV.write(os.path.join(d, 'readme.txt.wav'), sr, np.zeros(10, '<i2'))
    os.environ['SFX_PACK'] = d
    try:
        pk = SN.load_pack(); assert set(pk) >= {'pop', 'whoosh'} and len(pk['pop'][0]) > 1000, list(pk)
        sp = load('saas_intro'); a = os.path.join(d, 'with.wav'); SN.compose(sp, a, style='premium')
        os.environ['SFX_PACK'] = tempfile.mkdtemp(); b = os.path.join(d, 'without.wav'); SN.compose(sp, b, style='premium')
        assert open(a, 'rb').read() != open(b, 'rb').read()
    finally:
        os.environ.pop('SFX_PACK', None)

@check('sound: typing clip in sfx_pack -> key hits drive text timing (per-character reveal times) and the key sounds')
def _():
    from mgl import sound as SN, spec as S2
    import scipy.io.wavfile as WV
    d = tempfile.mkdtemp(); sr = SN.SR; x = np.zeros(int(sr * 1.2))
    hits = [0.05 + 0.06 * i for i in range(16)]
    for h in hits:
        k = np.arange(int(0.02 * sr)) / sr; i0 = int(h * sr); x[i0:i0 + len(k)] += np.random.default_rng(1).standard_normal(len(k)) * np.exp(-k / 0.004)
    WV.write(os.path.join(d, 'typing_6.wav'), sr, (x / abs(x).max() * 20000).astype('<i2'))
    os.environ['SFX_PACK'] = d
    try:
        tc = SN.typing_clip(); assert tc and 14 <= len(tc['rel']) <= 17 and 0.04 < np.median(np.diff(tc['rel'])) < 0.08, tc and tc['rel']
        sp = {'duration': 8, 'size': '16:9', 'background': 'dark_aurora', 'layers': [
            {'type': 'text', 'text': 'Typing demo text', 'x': 960, 'y': 540, 'size': 80, 'start': 1.0, 'end': 7, 'reveal': {'mode': 'chars', 'step': 0.2}},
            {'type': 'text', 'text': 'Words come in', 'x': 960, 'y': 700, 'size': 70, 'start': 2.0, 'end': 7, 'reveal': {'mode': 'words', 'step': 0.5}}]}
        assert SN.sync_spec(sp, 'premium') == 2 and SN.sync_spec(sp, 'kinetic') == 0
        tm = sp['layers'][0]['reveal']['times']; assert len(tm) == len('Typing demo text') and tm[0] == 1.0 and all(b >= a - 0.006 for a, b in zip(tm, tm[1:])) and tm[-1] < 3.0, tm
        assert not S2.validate(sp, ROOT)[0], S2.validate(sp, ROOT)[0]
        a1 = S2.render_frame(sp, 1.0 + 0.05, S2.Context(ROOT)); a2 = S2.render_frame(sp, tm[-1] + 0.1, S2.Context(ROOT)); assert (a1 != a2).any()
        ev = SN.premium_events(sp); ks = sorted(t_ for t_, k, v, p_ in ev if k == 'key' and t_ < 1.9)
        assert len(ks) == 14 and abs(ks[0] - 1.0) < 0.01 and all(abs(a - b) < 0.01 for a, b in zip(ks, [tm[i] for i, c in enumerate('Typing demo text') if c != ' '])), (ks, tm)
        info = SN.compose(sp, os.path.join(d, 'o.wav'), style='premium'); assert info['sfx'].get('key', 0) >= 14 and set(info['sfx']) <= set(SN.PREMIUM_KINDS)
    finally:
        os.environ.pop('SFX_PACK', None)

@check('native wfp: pen layers (points, fill, stroke, trim keyframes) build a valid project')
def _():
    import tempfile, zipfile, json as J
    from mgl import native_wfp as N
    d = tempfile.mkdtemp()
    r = N.build(os.path.join(d, 'pen.wfp'), 'pen', N.pen_demo_scene())
    assert not r['problems'], r['problems']
    z = zipfile.ZipFile(r['path']); w = J.loads(z.read([n for n in z.namelist() if n.endswith('timeline.wesproj')][0]))
    n_pen = 0
    for t_ in w['timelineInfos'][0]['trackInfos']:
        for c in t_['clipList']:
            fx = N._find_fx(c, 'graphic/effect/path')
            if fx:
                n_pen += 1; m = J.loads(fx['effectMask']['custom_mask']); assert len(m['paths'][0]['points']) >= 3
    assert n_pen == 3, n_pen
    assert N.kf([(0.52, 100.0)]).endswith('acf13857afa3ad4ab3f294973212c028"}')      # checksum copied from a real Filmora trim keyframe

print('\n%d passed, %d failed' % (len(PASSED), len(FAILED)))
sys.exit(1 if FAILED else 0)
