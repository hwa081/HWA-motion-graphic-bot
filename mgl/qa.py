"""mgl.qa - automatic quality checks (no AI, no API quota).

analyze(spec) renders sample frames and reports problems a human editor would flag:
text cut off / too small / low contrast / overlapping, empty stretches, crowded frames,
repeated animations, missing variety. Every message says what, when and how to fix it.
"""
import math
from collections import Counter
import numpy as np
from . import engine as E
from . import spec as S

def _lum(c):
    def ch(v):
        v = max(0.0, min(1.0, v))
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])

def contrast(c1, c2):
    a, b = _lum(c1), _lum(c2)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)

def _short(s, n=34):
    s = str(s).strip().replace('\n', ' ')
    return s if len(s) <= n else s[:n - 1] + '...'

def lint_variety(spec):
    """checks that need no rendering: repeated animations, one background, no transitions ..."""
    out = []
    dur = float(spec.get('duration', 0))
    layers = [L for L in spec.get('layers', []) if isinstance(L, dict)]
    ins = []
    for L in layers:
        v = L.get('in')
        a = v if isinstance(v, str) else (v.get('anim') if isinstance(v, dict) else None)
        if a and a != 'none' and L.get('type') not in ('transition', 'grid', 'particles', 'blob'): ins.append(a)
    cnt = Counter(ins)
    if dur >= 8 and len(ins) >= 6 and len(cnt) < 4:
        out.append('Variety: only %d different entrance animations are used (%s). Use at least 4 different ones (blur, pop, slide_up, rise, bounce, spin, wipe_right, zoom ...) and change style from scene to scene.' % (len(cnt), ', '.join(sorted(cnt)) or 'none'))
    if len(ins) >= 6 and cnt and cnt.most_common(1)[0][1] / len(ins) > 0.6:
        out.append('Variety: %d of %d entrances use "%s". Mix different animations for different elements.' % (cnt.most_common(1)[0][1], len(ins), cnt.most_common(1)[0][0]))
    bg = spec.get('background', 'dark_aurora')
    styles = {bg} if isinstance(bg, str) else {k.get('style') for k in (bg if isinstance(bg, list) else [bg]) if isinstance(k, dict)}
    if dur >= 10 and len(styles) < 2:
        out.append('Variety: the whole video uses one background style. Change the background style between scenes (with a fade).')
    if dur >= 10 and not any(L.get('type') == 'transition' for L in layers) and len(styles) < 2:
        out.append('Variety: no transitions. Add a transition layer (wipe, iris, stripes, flash or glitch) between scenes.')
    if dur >= 6 and not spec.get('camera'):
        out.append('Motion: no camera movement. Add a slow push-in (zoom 1 -> 1.1) or a camera move between scenes.')
    starts = Counter(round(float(L.get('start', 0)), 1) for L in layers if L.get('type') not in ('transition',))
    for t0, n in starts.items():
        if n > 5 and t0 > 0:
            out.append('Timing: %d layers start at exactly %.1fs. Stagger them by 0.1-0.25 s each.' % (n, t0))
    if dur >= 8 and layers and max(float(L.get('start', 0)) for L in layers) < 0.55 * dur:
        out.append('Pacing: no new layer starts after %.1fs of a %.0fs video, so the second half has nothing new. Add later scenes.' % (max(float(L.get('start', 0)) for L in layers), dur))
    # scenes = intervals between boundaries (transition middles, background changes, clusters of layers ending together)
    bounds = set()
    for L in layers:
        if L.get('type') == 'transition' and S._isnum(L.get('start')) and S._isnum(L.get('end')): bounds.add(round((L['start'] + L['end']) / 2, 2))
    if isinstance(bg, list):
        for k in bg:
            if isinstance(k, dict) and S._isnum(k.get('t', 0)) and k.get('t', 0) > 0.5: bounds.add(round(k['t'] + (k.get('fade') or 0) / 2, 2))
    ends = Counter(round(float(L.get('end', dur)) / 0.4) * 0.4 for L in layers if float(L.get('end', dur)) < dur - 0.1 and L.get('type') not in ('grid', 'particles', 'blob', 'transition'))
    for t_end, n in ends.items():
        if n >= 3: bounds.add(round(t_end, 2))
    cuts = []
    for b_ in sorted(bounds):
        if 0.8 < b_ < dur - 0.8 and (not cuts or b_ - cuts[-1] > 1.0): cuts.append(b_)
    edges = [0.0] + cuts + [dur]
    sigs = []
    for i in range(len(edges) - 1):
        mid = (edges[i] + edges[i + 1]) / 2
        types = set()
        for L in layers:
            if float(L.get('start', 0)) <= edges[i + 1] - 0.2 and float(L.get('end', dur)) >= edges[i] + 0.2 and L.get('type') not in ('grid', 'particles', 'blob', 'transition', 'line'):
                types.add(L['type'] + (':' + str(L.get('kind')) if L.get('kind') else ''))
        sigs.append((edges[i], frozenset(types)))
    for i in range(len(sigs) - 1):
        if len(sigs[i][1]) >= 2 and sigs[i][1] == sigs[i + 1][1]:
            out.append('Variety: the scenes starting at %.1fs and %.1fs are built from the same kinds of layers (%s). Give each scene a different layout archetype (typographic hero, card fan, chip cluster, device mockup, chart, big number, image feature ...).' % (sigs[i][0], sigs[i + 1][0], ', '.join(sorted(sigs[i][1]))))
            break
    return out

def analyze(spec, root='.', samples=20):
    """returns dict(errors=[...], warnings=[...], stats={...}); errors should always be fixed"""
    S.setup(spec)
    W, H = E.W, E.H
    ctx = S.Context(root)
    dur = float(spec['duration'])
    errors, warnings = [], []
    seen = set()
    def add(lst, key, msg):
        if key in seen: return
        seen.add(key); lst.append(msg)
    times = [dur * (i + 0.5) / samples for i in range(samples)]
    empty_run, flat = [], []
    E.QA_SINK = []
    try:
        for ti, t in enumerate(times):
            E.QA_SINK.clear()
            fr = S.render_frame(spec, t, ctx)
            recs = list(E.QA_SINK)
            bg = np.clip(S.background(spec, t), 0, 1)
            frac = float((np.abs(fr.astype(np.float32) / 255 - bg).max(axis=2) > 0.06).mean())
            if frac < 0.0015: empty_run.append(t)
            layers_vis = sum(1 for L in spec['layers'] if float(L.get('start', 0)) <= t <= float(L.get('end', dur)) and L.get('type') not in ('grid', 'particles', 'blob'))
            if layers_vis > 16: add(warnings, ('crowd', int(t // 3)), 'Crowded: %d layers are visible at %.1fs. Remove or stagger some so one idea is clear.' % (layers_vis, t))
            for r in recs:
                x0, y0, w, h = r['box']
                li = r['layer']; txt = _short(r['text']); sz = r['size']
                margin = 0.01
                if x0 < -margin * W or x0 + w > W * (1 + margin) or y0 < -margin * H or y0 + h > H * (1 + margin):
                    maxw = max(100, W * 0.9)
                    fit = int(sz * maxw / max(w, 1)) if w > W * 0.9 else None
                    add(errors, ('cut', li), 'Text cut off: at %.1fs layer %d "%s" extends beyond the %dx%d canvas (text is %dpx wide at size %d)%s.' % (
                        t, li, txt, W, H, w, sz, ' - reduce its size to about %d, shorten it, or split it into two text layers' % fit if fit else ' - move it inside the canvas (x %d..%d)' % (int(W * 0.06), int(W * 0.94))))
                if H > W and (y0 + h > 0.80 * H or y0 < 0.07 * H) and not (x0 < -margin * W):
                    add(warnings, ('safe', li), 'Safe area: at %.1fs layer %d "%s" sits in the area covered by app buttons on vertical video (keep text between y %d and y %d).' % (t, li, txt, int(0.08 * H), int(0.78 * H)))
                min_px = 0.026 * H if H <= W else 0.021 * H
                if sz < min_px and len(r['text']) > 2:
                    add(warnings, ('small', li), 'Text too small to read on a phone: layer %d "%s" is about %dpx tall at %.1fs (use size >= %d).' % (li, txt, int(sz), t, int(min_px)))
                if r['color'] is not None and r['bg'] is not None and sz >= 28:
                    cr = contrast(r['color'], r['bg'])
                    if cr < 2.6:
                        add(warnings, ('contrast', li), 'Low contrast: layer %d "%s" at %.1fs is hard to read (contrast %.1f:1 against the background). Use %s text here.' % (
                            li, txt, t, cr, 'darker' if _lum(r['bg']) > 0.4 else 'lighter'))
            # overlaps between different layers
            for a in range(len(recs)):
                for b in range(a + 1, len(recs)):
                    ra, rb = recs[a], recs[b]
                    if ra['layer'] == rb['layer']: continue
                    ax, ay, aw, ah = ra['box']; bx, by, bw, bh = rb['box']
                    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx)); iy = max(0, min(ay + ah, by + bh) - max(ay, by))
                    inter = ix * iy
                    if inter > 0.3 * min(aw * ah, bw * bh):
                        add(errors, ('ov', ra['layer'], rb['layer']), 'Text overlap: at %.1fs "%s" (layer %d) and "%s" (layer %d) cover each other. Move one (e.g. y by %d px) or time them apart.' % (
                            t, _short(ra['text'], 22), ra['layer'], _short(rb['text'], 22), rb['layer'], int(max(ah, bh) * 1.1)))
    finally:
        E.QA_SINK = None
    for w in ctx.warnings: add(errors, ('render', w), 'Render problem: ' + w)
    if empty_run:
        idx = [times.index(t) for t in empty_run]
        runs, cur = [], [idx[0]]
        for i in idx[1:]:
            if i == cur[-1] + 1: cur.append(i)
            else: runs.append(cur); cur = [i]
        runs.append(cur)
        for r in runs:
            t0, t1 = times[r[0]], times[r[-1]]
            if r[-1] == len(times) - 1:
                add(errors, 'empty_end', 'The video ends on an empty background (nothing visible from %.1fs). Keep the closing scene visible until the end (set its "end" to the video duration and give it no "out" animation).' % t0)
            elif r[0] == 0 and len(r) >= 2:
                add(warnings, 'empty_start', 'The video starts with about %.1fs of empty background. Start the first scene earlier.' % (t1 + 0.25 * dur / samples))
            elif len(r) >= 2:
                add(errors, ('empty_mid', r[0]), 'Empty stretch: nothing but the background is visible from %.1fs to %.1fs. Fill it with the next scene or close the gap.' % (t0, t1))
    warnings.extend(lint_variety(spec))
    return dict(errors=errors, warnings=warnings, stats=dict(samples=samples, empty=len(empty_run)))

def analyze_frames(render, duration, size_key='16:9', samples=16):
    """QA for code scenes. render(t) -> uint8 RGB frame (the scene must have set E.W/E.H). Same text checks as analyze()
    (cut off, overlap, contrast, small) plus: flat/blank frames and a video where nothing moves."""
    W, H = E.W, E.H
    errors, warnings, seen = [], [], set()
    def add(lst, key, msg):
        if key in seen: return
        seen.add(key); lst.append(msg)
    times = [duration * (i + 0.5) / samples for i in range(samples)]
    frames, E.QA_SINK = [], []
    try:
        for t in times:
            E.QA_SINK.clear(); E.QA_LAYER = -1
            fr = render(t)
            recs = list(E.QA_SINK)
            frames.append(cv2_small(fr))
            if float(fr.std()) < 4.0:
                add(errors, ('flat', round(t, 1)), 'Frame at %.1fs is almost one flat colour (nothing drawn?).' % t)
            for r in recs:
                x0, y0, w, h = r['box']; sz = r['size']; txt = _short(r['text'])
                if x0 < -0.01 * W or x0 + w > 1.01 * W or y0 < -0.01 * H or y0 + h > 1.01 * H:
                    fit = int(sz * W * 0.9 / max(w, 1)) if w > W * 0.9 else None
                    add(errors, ('cut', r['text']), 'Text cut off: at %.1fs "%s" extends beyond the %dx%d canvas (%dpx wide at size %d)%s.' % (
                        t, txt, W, H, w, sz, ' - use size about %d or shorten it' % fit if fit else ' - move it inside the canvas'))
                if H > W and (y0 + h > 0.80 * H or y0 < 0.07 * H):
                    add(warnings, ('safe', r['text']), 'Safe area: at %.1fs "%s" is where app buttons cover vertical video (keep text between y %d and %d).' % (t, txt, int(0.08 * H), int(0.78 * H)))
                if sz < (0.026 * H if H <= W else 0.021 * H) and len(r['text']) > 2:
                    add(warnings, ('small', r['text']), 'Text too small for a phone: "%s" at %.1fs is %dpx.' % (txt, t, int(sz)))
                if r['color'] is not None and r['bg'] is not None and sz >= 28 and contrast(r['color'], r['bg']) < 2.6:
                    add(warnings, ('contrast', r['text']), 'Low contrast: "%s" at %.1fs is hard to read (%.1f:1).' % (txt, t, contrast(r['color'], r['bg'])))
            for a in range(len(recs)):
                for b in range(a + 1, len(recs)):
                    ra, rb = recs[a], recs[b]
                    if ra['text'] == rb['text']: continue
                    ax, ay, aw, ah = ra['box']; bx, by, bw, bh = rb['box']
                    inter = max(0, min(ax + aw, bx + bw) - max(ax, bx)) * max(0, min(ay + ah, by + bh) - max(ay, by))
                    if inter > 0.3 * min(aw * ah, bw * bh):
                        add(errors, ('ov', ra['text'], rb['text']), 'Text overlap at %.1fs: "%s" and "%s".' % (t, _short(ra['text'], 22), _short(rb['text'], 22)))
    finally:
        E.QA_SINK = None
    if len(frames) >= 4:
        d = max(float(np.abs(frames[i].astype(np.float32) - frames[0].astype(np.float32)).mean()) for i in range(1, len(frames)))
        if d < 1.0: add(errors, 'static', 'Nothing changes over time: all sampled frames look the same. Add motion.')
        last = float(np.abs(frames[-1].astype(np.float32) - frames[-2].astype(np.float32)).mean())
        if float(frames[-1].std()) < 12 and float(frames[0].std()) > 20: add(warnings, 'ends_blank', 'The last frames look blank; keep the closing scene visible until the end.')
    return dict(errors=errors, warnings=warnings, stats=dict(samples=samples))

def cv2_small(fr):
    import cv2
    return cv2.resize(fr, (160, int(160 * fr.shape[0] / fr.shape[1])), interpolation=cv2.INTER_AREA)

def problems(report, limit=12):
    """errors first, then warnings (what the agent should fix)"""
    return (report['errors'] + report['warnings'])[:limit]
