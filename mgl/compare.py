"""mgl.compare - put the bot's video next to an example (reference) video and measure how close it is.

Two layers, so it works with or without the AI:
  1. NUMBERS (no quota): palette, pacing (cuts per second, scene length), cut timing, motion curve, brightness curve,
     visual complexity, where the screen energy sits. -> fidelity score 0-100 + concrete gaps ("reference cuts every 1.8 s, yours every 4.1 s").
  2. AI (optional, 1 request): looks at the side-by-side sheet (reference row above, yours below) and says what is the same, what is different, how to fix it,
     and which reusable techniques the bot should learn from the example.

Content is allowed to differ (your brand, your words): this measures STRUCTURE and FEEL.
"""
import json, math, os
import cv2, numpy as np

from . import gemini

SAMPLE_W = 192                       # frames are shrunk to this width before measuring
CURVE_N = 40                         # curves are compared at this many points (normalised time 0..1)
WEIGHTS = {'palette': 0.18, 'pacing': 0.14, 'cuts': 0.14, 'motion': 0.20, 'brightness': 0.06, 'complexity': 0.10, 'layout': 0.18}


def n_samples(duration):
    return int(min(96, max(48, round(duration * 5))))


# ------------------------------------------------------------------ frames
def _shrink(fr):
    h, w = fr.shape[:2]
    return cv2.resize(fr, (SAMPLE_W, max(8, int(round(SAMPLE_W * h / w)))), interpolation=cv2.INTER_AREA)


def video_frames(path, n):
    """n evenly spaced RGB frames (shrunk) of a video file, and its info"""
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if total <= 0 or w <= 0:
        cap.release(); raise ValueError('cannot read video %s' % path)
    dur = total / fps
    out = []
    for i in range(n):
        idx = min(total - 1, int(total * (i + 0.5) / n))
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, fr = cap.read()
        if not ok:
            if out: out.append(out[-1])
            continue
        out.append(_shrink(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)))
    cap.release()
    if len(out) < 3: raise ValueError('too few frames could be read from %s' % path)
    return out, {'duration': dur, 'fps': fps, 'width': w, 'height': h, 'aspect': '16:9' if w > h * 1.3 else ('9:16' if h > w * 1.3 else '1:1')}


def spec_frames(spec, root, n):
    """n evenly spaced frames rendered from a JSON spec (fast preview of the plan, no MP4 needed)"""
    from . import spec as S, engine as E
    S.setup(spec)
    ctx = S.Context(root)
    dur = float(spec['duration'])
    out = []
    for i in range(n):
        out.append(_shrink(S.render_frame(spec, dur * (i + 0.5) / n, ctx)))
    return out, {'duration': dur, 'fps': int(spec.get('fps', 30)), 'width': E.W, 'height': E.H, 'aspect': E.canvas_key()}


# ------------------------------------------------------------------ profile
def _hex(rgb): return '#%02x%02x%02x' % tuple(int(max(0, min(255, v))) for v in rgb)


def _palette(frames, k=5):
    px = np.concatenate([cv2.resize(f, (24, 14), interpolation=cv2.INTER_AREA).reshape(-1, 3) for f in frames[::max(1, len(frames) // 24)]]).astype(np.uint8)
    lab = cv2.cvtColor(px.reshape(-1, 1, 3), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    k = min(k, len(lab))
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5)
    _, labels, centers = cv2.kmeans(lab, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.ravel(), minlength=k).astype(np.float32); counts /= counts.sum()
    order = np.argsort(-counts)
    out = []
    for i in order:
        rgb = cv2.cvtColor(np.uint8([[np.clip(centers[i], 0, 255)]]), cv2.COLOR_LAB2RGB)[0, 0]
        out.append({'hex': _hex(rgb), 'w': float(counts[i]), 'lab': [float(x) for x in centers[i]]})
    return out


def profile(frames, info):
    """numbers that describe a video's look and rhythm (works for a video file and for a spec preview alike)"""
    n = len(frames)
    gray = [cv2.cvtColor(f, cv2.COLOR_RGB2GRAY) for f in frames]
    hsv = [cv2.cvtColor(f, cv2.COLOR_RGB2HSV) for f in frames]
    bright = np.array([g.mean() / 255 for g in gray])
    sat = np.array([h[..., 1].mean() / 255 for h in hsv])
    motion = np.array([np.abs(frames[i].astype(np.float32) - frames[i - 1].astype(np.float32)).mean() / 255 for i in range(1, n)])     # colour change (a cut between two equally bright colours still counts)
    edges = [cv2.Canny(g, 80, 160) for g in gray]
    complexity = np.array([(e > 0).mean() for e in edges])
    grid = np.mean([cv2.resize(e.astype(np.float32) / 255, (8, 6), interpolation=cv2.INTER_AREA) for e in edges], axis=0).ravel()
    grid = grid / (grid.sum() or 1)
    # cuts = sudden jumps in motion (fast fades/zooms are smooth, hard changes are not)
    if len(motion):
        med = float(np.median(motion)); mad = float(np.median(np.abs(motion - med))) * 1.4826
        thr = max(0.09, med + 5 * mad)
    else:
        thr = 1
    cut_idx = []
    for i, m in enumerate(motion):
        if m >= thr and (not cut_idx or i - cut_idx[-1] > 2): cut_idx.append(i)
    dur = float(info['duration'])
    cuts_t = [round((i + 1) / n, 4) for i in cut_idx]                  # normalised time 0..1
    edges_t = [0.0] + cuts_t + [1.0]
    scene_len = float(np.mean(np.diff(edges_t))) * dur
    # still stretches (nothing changes for a while)
    still = []
    run0 = None
    for i, m in enumerate(motion):
        if m < 0.0015:
            run0 = i if run0 is None else run0
        else:
            if run0 is not None and (i - run0) * dur / n >= 1.4: still.append((round(run0 * dur / n, 1), round(i * dur / n, 1)))
            run0 = None
    if run0 is not None and (len(motion) - run0) * dur / n >= 1.4: still.append((round(run0 * dur / n, 1), round(dur, 1)))
    return {'n': n, 'duration': dur, 'aspect': info.get('aspect'), 'brightness': bright.tolist(), 'saturation': float(sat.mean()),
            'motion': motion.tolist(), 'motion_mean': float(motion.mean()) if len(motion) else 0.0, 'complexity': complexity.tolist(),
            'complexity_mean': float(complexity.mean()), 'grid': grid.tolist(), 'cuts': cuts_t, 'scene_len': scene_len,
            'cuts_per_s': len(cuts_t) / max(dur, 0.1), 'still': still, 'palette': _palette(frames)}


# ------------------------------------------------------------------ comparison
def _curve(v, n=CURVE_N):
    v = np.asarray(v, dtype=np.float64)
    if len(v) == 0: return np.zeros(n)
    x = np.linspace(0, 1, len(v)); xn = np.linspace(0, 1, n)
    return np.interp(xn, x, v)


def _corr01(a, b):
    a, b = _curve(a), _curve(b)
    if a.std() < 1e-6 and b.std() < 1e-6: return 1.0
    if a.std() < 1e-6 or b.std() < 1e-6: return 0.35
    return float((np.corrcoef(a, b)[0, 1] + 1) / 2)


def _ratio(a, b):
    a, b = abs(float(a)), abs(float(b))
    if a < 1e-9 and b < 1e-9: return 1.0
    return min(a, b) / max(a, b, 1e-9)


def _palette_score(p, q):
    """weighted mean colour distance (Lab) from each reference colour to the nearest colour of the other video"""
    tot = 0.0
    for c in p:
        d = min(math.sqrt(((c['lab'][0] - e['lab'][0]) * 100 / 255) ** 2 + (c['lab'][1] - e['lab'][1]) ** 2 + (c['lab'][2] - e['lab'][2]) ** 2) for e in q)
        tot += c['w'] * d
    return max(0.0, 1 - tot / 55.0), tot


def _cuts_score(a, b, tol=0.07):
    if not a and not b: return 1.0
    if not a or not b: return 0.15 if max(len(a), len(b)) >= 2 else 0.55
    hit = sum(1 for t in a if min(abs(t - u) for u in b) <= tol)
    hit2 = sum(1 for u in b if min(abs(t - u) for t in a) <= tol)
    prec, rec = hit2 / len(b), hit / len(a)
    return 0.0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)


def compare(ref, out):
    """ref / out = profile() dicts. -> dict(score 0..100, parts{name: 0..1}, gaps[], strengths[], numbers{})"""
    parts = {}
    parts['palette'], pal_dist = _palette_score(ref['palette'], out['palette'])
    cps_ratio = _ratio(ref['cuts_per_s'], out['cuts_per_s'])
    parts['pacing'] = 0.6 * _ratio(ref['scene_len'], out['scene_len']) + 0.4 * cps_ratio
    parts['cuts'] = _cuts_score(ref['cuts'], out['cuts'])
    parts['motion'] = 0.55 * _corr01(ref['motion'], out['motion']) + 0.45 * _ratio(ref['motion_mean'], out['motion_mean'])
    parts['brightness'] = 0.5 * _corr01(ref['brightness'], out['brightness']) + 0.5 * (1 - min(1, abs(np.mean(ref['brightness']) - np.mean(out['brightness'])) * 2.5))
    parts['complexity'] = _ratio(ref['complexity_mean'], out['complexity_mean'])
    same_aspect = ref.get('aspect') == out.get('aspect')
    cosv = float(np.dot(ref['grid'], out['grid']) / ((np.linalg.norm(ref['grid']) * np.linalg.norm(out['grid'])) or 1))
    parts['layout'] = max(0.0, min(1.0, (cosv - 0.5) / 0.5)) if same_aspect else None
    wts = dict(WEIGHTS)
    if parts['layout'] is None: wts.pop('layout')
    tw = sum(wts.values())
    score = 100 * sum(parts[k] * w for k, w in wts.items()) / tw
    gaps, strengths = [], []
    R, O = ref, out
    if parts['pacing'] < 0.65:
        faster = O['scene_len'] > R['scene_len']
        gaps.append('Pacing: the example changes scene about every %.1fs (%d cuts in %.0fs), yours about every %.1fs (%d cuts). %s' % (
            R['scene_len'], len(R['cuts']), R['duration'], O['scene_len'], len(O['cuts']),
            'Make scenes shorter and add scene changes.' if faster else 'Slow down: fewer, longer scenes.'))
    if parts['cuts'] < 0.5 and R['cuts']:
        gaps.append('Cut timing: the example cuts at %s of the video length; yours at %s. Put your scene changes near the same moments.' % (
            ', '.join('%d%%' % round(t * 100) for t in R['cuts'][:8]), ', '.join('%d%%' % round(t * 100) for t in O['cuts'][:8]) or 'no clear cuts'))
    if parts['motion'] < 0.6:
        slow = O['motion_mean'] < R['motion_mean']
        gaps.append('Motion: %s (movement energy %.3f vs %.3f in the example). %s' % (
            'yours is calmer and flatter than the example' if slow else 'yours is busier than the example', O['motion_mean'], R['motion_mean'],
            'Add camera movement, staggered entrances and a moving element in every scene.' if slow else 'Reduce simultaneous movement; let one thing move at a time.'))
    if O['still'] and R['motion_mean'] > 0.004:
        gaps.append('Still stretches: nothing changes at %s in yours while the example keeps moving. Add motion or the next scene there.' % ', '.join('%.1f-%.1fs' % s for s in O['still'][:3]))
    if parts['palette'] < 0.6:
        gaps.append('Colours: the example is dominated by %s; yours by %s. Move your background and accent colours closer (unless the brand kit says otherwise).' % (
            ', '.join(c['hex'] for c in R['palette'][:3]), ', '.join(c['hex'] for c in O['palette'][:3])))
    if parts['brightness'] < 0.55:
        gaps.append('Brightness: the example is %s on average (%.0f%% vs %.0f%%). Use a %s background style.' % (
            'lighter' if np.mean(R['brightness']) > np.mean(O['brightness']) else 'darker', np.mean(R['brightness']) * 100, np.mean(O['brightness']) * 100,
            'light' if np.mean(R['brightness']) > np.mean(O['brightness']) else 'dark'))
    if parts['complexity'] < 0.6:
        more = R['complexity_mean'] > O['complexity_mean']
        gaps.append('Visual density: the example has %s on screen (edge density %.3f vs %.3f). %s' % (
            'more detail' if more else 'less detail', R['complexity_mean'], O['complexity_mean'],
            'Add supporting elements (cards, chips, lines, charts) per scene.' if more else 'Remove clutter; fewer, bigger elements.'))
    if parts['layout'] is not None and parts['layout'] < 0.55:
        gaps.append('Layout: the screen energy sits in different places (the example is arranged differently). Study where the example puts its main text and visuals and use the same zones.')
    if not same_aspect:
        gaps.append('Aspect ratio differs (%s vs %s): layout was not compared.' % (R.get('aspect'), O.get('aspect')))
    for k, label in (('palette', 'colour palette'), ('pacing', 'pacing'), ('cuts', 'cut timing'), ('motion', 'motion'), ('complexity', 'visual density'), ('layout', 'layout')):
        if parts.get(k) is not None and parts[k] >= 0.8: strengths.append('%s matches well (%.0f%%)' % (label, parts[k] * 100))
    return {'score': round(score, 1), 'parts': {k: (round(float(v), 3) if v is not None else None) for k, v in parts.items()}, 'gaps': gaps, 'strengths': strengths,
            'numbers': {'palette_distance': round(pal_dist, 1), 'ref_cuts': len(R['cuts']), 'out_cuts': len(O['cuts']), 'ref_scene_len': round(R['scene_len'], 2), 'out_scene_len': round(O['scene_len'], 2)}}


# ------------------------------------------------------------------ side-by-side sheet
def side_by_side(frames_ref, frames_out, path, cols=6, tile_w=320):
    """one PNG: top row example, bottom row yours, at the same relative times (two rows per 6 moments)"""
    def pick(frames):
        idx = [int(len(frames) * (i + 0.5) / cols) for i in range(cols)]
        return [cv2.resize(frames[min(i, len(frames) - 1)], (tile_w, int(tile_w * frames[0].shape[0] / frames[0].shape[1]))) for i in idx]
    a, b = pick(frames_ref), pick(frames_out)
    h = max(max(x.shape[0] for x in a), max(x.shape[0] for x in b))
    def row(tiles, label):
        padded = []
        for i, x in enumerate(tiles):
            canvas = np.zeros((h, tile_w, 3), np.uint8); canvas[:x.shape[0]] = x
            t = '%s %d%%' % (label, round(100 * (i + 0.5) / cols))
            cv2.putText(canvas, t, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(canvas, t, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0) if label == 'EXAMPLE' else (0, 255, 255), 2, cv2.LINE_AA)
            padded.append(canvas)
        return np.hstack(padded)
    sheet = np.vstack([row(a, 'EXAMPLE'), np.full((6, tile_w * cols, 3), 255, np.uint8), row(b, 'YOURS')])
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    cv2.imwrite(path, cv2.cvtColor(sheet, cv2.COLOR_RGB2BGR))
    ok, buf = cv2.imencode('.png', cv2.cvtColor(sheet, cv2.COLOR_RGB2BGR))
    return buf.tobytes() if ok else b''


# ------------------------------------------------------------------ AI judgement
AI_SYSTEM = 'You are a senior motion-design director comparing a generated video with the example it should follow. Answer with JSON only.'


def ai_prompt(metrics, brief=''):
    return ('The picture shows 6 moments of two videos at the same relative times: the TOP row is the EXAMPLE (the target style), the BOTTOM row is YOURS (the bot\'s video).\n'
            'Content may differ on purpose (the bot used the user\'s brief%s); judge STRUCTURE and FEEL: scene archetypes, layout, hierarchy, typography, colour, motion style, pacing, transitions.\n'
            'Measured numbers: fidelity %.0f/100; %s\n\n'
            'Return JSON: {"fidelity": 1-10, "same": ["what matches"], "gaps": ["specific difference: what the example does, what yours does"], '
            '"fixes": ["concrete change in library terms (background style, entrance animation, transition, layer type, size, timing)"], '
            '"techniques": [{"name": "short name", "when": "when to use it", "how": "how to build it with the library (layer types, animations, timing)"}]}\n'
            'Techniques = things the example does that are worth REUSING in other videos (max 3). Be concrete, no generic advice.' % (
                (': "%s"' % brief[:160]) if brief else '', metrics['score'], '; '.join(metrics['gaps'][:5]) or 'no big numeric gaps'))


def ai_compare(ask, sheet_png, metrics, brief=''):
    txt = ask(AI_SYSTEM, [{'role': 'user', 'parts': [gemini.text_part(ai_prompt(metrics, brief)), gemini.image_part(sheet_png)]}])
    data = gemini.extract_json(txt)
    if not isinstance(data, dict): raise ValueError('comparison was not a JSON object')
    def lst(v, n=6, ln=260): return [str(x)[:ln] for x in v[:n]] if isinstance(v, list) else []
    try: fid = float(data.get('fidelity', 0))
    except Exception: fid = 0.0
    techs = []
    for t in (data.get('techniques') or [])[:3]:
        if isinstance(t, dict) and len(str(t.get('name', ''))) >= 3 and len(str(t.get('how', ''))) >= 12:
            techs.append({'name': str(t['name'])[:60], 'when': str(t.get('when', ''))[:160], 'how': str(t['how'])[:300]})
    return {'fidelity': max(0.0, min(10.0, fid)), 'same': lst(data.get('same')), 'gaps': lst(data.get('gaps')), 'fixes': lst(data.get('fixes')), 'techniques': techs}


def learn_from(mem, res, ai=None, source='compare'):
    """store the gaps as lessons and the example's tricks as techniques; returns (lessons added, techniques added)"""
    items = []
    for g in (ai['fixes'] if ai else [])[:4]:
        items.append({'kind': 'do', 'text': 'When following an example video: ' + g, 'weight': 2})
    for g in res['gaps'][:3]:
        if g.startswith(('Pacing', 'Motion', 'Still', 'Visual density')):
            items.append({'kind': 'dont', 'text': 'Compared with an example: ' + g[:200], 'weight': 1})
    nl = mem.add_lessons(items, source=source)
    nt = 0
    for t in (ai['techniques'] if ai else []):
        nt += 1 if mem.add_technique(t, source=source) else 0
    return nl, nt


def report_md(ref_name, out_name, res, ai=None, extra=''):
    p = res['parts']
    lines = ['# Comparison with the example video', '', 'Example: `%s`   Yours: `%s`' % (ref_name, out_name), '',
             '**Fidelity (numbers): %.0f / 100**%s' % (res['score'], ('   |   **AI judgement: %.0f / 10**' % ai['fidelity']) if ai else ''), '',
             '| measure | match |', '|---|---|'] + ['| %s | %s |' % (k, ('%.0f%%' % (v * 100)) if v is not None else 'not compared') for k, v in p.items()]
    lines += ['', '## What matches'] + (['- ' + s for s in res['strengths']] or ['- (nothing clearly matches yet)']) + (['- ' + s for s in ai['same']] if ai else [])
    lines += ['', '## Differences (measured)'] + (['- ' + g for g in res['gaps']] or ['- none worth fixing'])
    if ai:
        lines += ['', '## Differences (AI)'] + ['- ' + g for g in ai['gaps']] + ['', '## How to fix'] + ['- ' + g for g in ai['fixes']]
        if ai['techniques']: lines += ['', '## Techniques learned from the example'] + ['- **%s**: %s (%s)' % (t['name'], t['how'], t['when']) for t in ai['techniques']]
    if extra: lines += ['', extra]
    return '\n'.join(lines)
