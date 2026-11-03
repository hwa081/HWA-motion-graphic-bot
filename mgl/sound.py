"""Background music + sound effects for a video plan - made from scratch with numpy (no samples, no internet, no copyright).

    from mgl import sound
    sound.compose(spec, 'out/music.wav', style='uplift')     # stereo 48 kHz WAV, exactly spec['duration'] long

* Music: pad chords + bass + plucked arpeggio + drums. It starts soft, grows with every scene (scene = background
  change) and settles in the last scene. Styles: uplift (A minor, 112 bpm), calm (C major, 84 bpm), tech (D minor, 124 bpm).
* Style **kinetic** = NO music, only kinetic-typography sound effects: a stamp for every pop/zoom headline, a click per word,
  typewriter ticks per letter, directional whooshes for slides/wipes (panned to where the text is), soft reverse-swish when text
  leaves, counter ticks + ding, and whoosh/riser/impact on transitions.
* Style **ui** = NO music, UI / SaaS animation sounds: soft clicks, toggle on/off, notification bells, swipes for sliding
  panels, a landing "drop" for cards and device mockups, keyboard keys for typing, rising ticks for charts and progress bars,
  a success chime for check icons and counters, light whooshes for transitions. Text hardly gets any sound.
* SFX are placed from the plan itself: whoosh + riser + impact for every transition, pop for pop/bounce/spin entrances,
  typing ticks for letter/char reveals, counting ticks + ding for counters, rising sweep for charts, soft swish for big
  slide/wipe entrances, low hit for hero headlines, chime in the closing scene.
Same plan -> same sound (seeded by the title), so a re-render sounds the same.
"""
import hashlib, math
import numpy as np
from scipy import signal

SR = 48000
STYLES = {
    'uplift': {'bpm': 112, 'root': 57, 'minor': True,  'prog': [0, 5, 3, 4]},     # Am F C G (as scale degrees of A minor: i VI III VII)
    'calm':   {'bpm': 84,  'root': 48, 'minor': False, 'prog': [0, 5, 3, 4]},     # C Am F G
    'tech':   {'bpm': 124, 'root': 50, 'minor': True,  'prog': [0, 5, 6, 4]},     # Dm Bb C A-ish
}
MINOR = [0, 2, 3, 5, 7, 8, 10]
MAJOR = [0, 2, 4, 5, 7, 9, 11]


def mtof(m): return 440.0 * 2.0 ** ((np.asarray(m, dtype=float) - 69.0) / 12.0)


class Track:
    """A stereo float buffer with helpers to drop mono sounds in at a time with a pan."""
    def __init__(self, dur):
        self.n = int(round(dur * SR)); self.b = np.zeros((self.n, 2), dtype=np.float64)

    def add(self, t, x, gain=1.0, pan=0.0):
        i = int(round(t * SR))
        if i >= self.n or i + len(x) <= 0: return
        a = max(0, -i); e = min(len(x), self.n - i)
        seg = x[a:e] * gain
        l, r = math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)
        self.b[i + a:i + e, 0] += seg * l * 1.414
        self.b[i + a:i + e, 1] += seg * r * 1.414


def tt(d): return np.arange(int(d * SR)) / SR


def lp(x, f, order=2): return signal.lfilter(*signal.butter(order, min(f, 20000) / (SR / 2), 'low'), x)
def hp(x, f, order=2): return signal.lfilter(*signal.butter(order, f / (SR / 2), 'high'), x)
def bp(x, f1, f2): return signal.lfilter(*signal.butter(2, [f1 / (SR / 2), min(f2, 20000) / (SR / 2)], 'band'), x)


def adsr(n, a=0.01, tau=0.2, hold=0.0):
    t = np.arange(n) / SR
    e = np.exp(-np.maximum(t - a - hold, 0) / tau)
    return e * np.minimum(1.0, t / max(a, 1e-4))


def saw(f, t, harm=8):
    return sum(np.sin(2 * np.pi * f * k * t) / k for k in range(1, harm + 1) if f * k < 12000) * 0.6


def reverb(x, rng, secs=1.4, wet=0.25):
    n = int(secs * SR); ir = rng.standard_normal(n) * np.exp(-np.arange(n) / (SR * secs / 4.5)); ir = lp(ir, 5000)
    ir[:int(0.012 * SR)] *= np.linspace(0, 1, int(0.012 * SR))
    y = np.stack([signal.fftconvolve(x[:, c], ir * (1 if c == 0 else -1), mode='full')[:len(x)] for c in range(2)], 1)
    y /= max(1e-9, np.abs(ir).sum() ** 0.5) * 6
    return x * (1 - wet * 0.5) + y * wet * 3


# ---------------------------------------------------------------- instruments
def kick(vol=1.0):
    t = tt(0.45); f = 48 + 90 * np.exp(-t / 0.035); ph = 2 * np.pi * np.cumsum(f) / SR
    return (np.sin(ph) * np.exp(-t / 0.13) + 0.25 * np.sin(2 * ph) * np.exp(-t / 0.02)) * vol


def clap(rng, vol=1.0):
    t = tt(0.3); n = bp(rng.standard_normal(len(t)), 1200, 6000)
    e = sum(np.exp(-np.maximum(t - o, 0) / 0.012) * (t >= o) for o in (0, 0.011, 0.022)) * 0.5 + np.exp(-t / 0.09) * (t >= 0.03)
    return n * e * vol * 0.6


def hat(rng, vol=1.0, open_=False):
    t = tt(0.25 if open_ else 0.06); return hp(rng.standard_normal(len(t)), 7000) * np.exp(-t / (0.09 if open_ else 0.012)) * vol * 0.35


def bass_note(f, d):
    t = tt(d); e = adsr(len(t), 0.008, d * 0.55)
    return lp(0.7 * np.sin(2 * np.pi * f * t) + 0.35 * saw(f, t, 6), 700) * e


def pluck(f, d=0.5):
    t = tt(d); x = saw(f, t, 10) * 0.5 + 0.5 * np.sin(2 * np.pi * f * t)
    c = 2400 + 3000 * np.exp(-t / 0.08)
    y = signal.lfilter(*signal.butter(1, 3500 / (SR / 2), 'low'), x)
    return y * adsr(len(t), 0.004, 0.16)


def pad_chord(notes, d):
    t = tt(d); x = np.zeros_like(t)
    for m in notes:
        f = mtof(m)
        for det in (-0.07, 0.0, 0.07):
            x += saw(f * 2 ** (det / 12), t, 7) * (0.5 if det else 0.8)
        x += 0.4 * np.sin(2 * np.pi * f * t)
    x = lp(x, 2200)
    a, r = min(1.2, d * 0.35), min(0.9, d * 0.3)
    e = np.minimum(1, t / a) * np.minimum(1, (d - t) / r)
    return x * e / max(1, len(notes)) * 0.8


# ---------------------------------------------------------------- sound effects
def sfx_pop(rng, pitch=1.0):
    t = tt(0.22); f = (380 + 520 * np.exp(-t / 0.03)) * pitch
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.05) * 0.8 + hp(rng.standard_normal(len(t)), 3000) * np.exp(-t / 0.01) * 0.12


def sfx_tick(rng, pitch=1.0):
    t = tt(0.05); return (np.sin(2 * np.pi * 1900 * pitch * t) * 0.5 + bp(rng.standard_normal(len(t)), 2500, 7000) * 0.5) * np.exp(-t / 0.008) * 0.6


def sfx_swish(rng, d=0.45, up=True):
    t = tt(d); n = rng.standard_normal(len(t)); c = np.linspace(500, 5200, len(t)) if up else np.linspace(5200, 500, len(t))
    y = np.zeros_like(n); out = np.zeros_like(n)
    chunks = 24; L = len(t) // chunks
    for i in range(chunks):
        s = slice(i * L, (i + 1) * L if i < chunks - 1 else len(t)); fc = c[i * L]
        out[s] = bp(n[max(0, i * L - 200):(i + 1) * L], fc * 0.75, fc * 1.25)[-(s.stop - s.start):]
    env = np.sin(np.pi * np.minimum(1, t / d)) ** 1.6
    return out * env * 2.2


def sfx_whoosh(rng, d=1.0):
    return sfx_swish(rng, d, True) * 1.3


def sfx_riser(rng, d=0.9):
    t = tt(d); f = 180 * 2 ** (t / d * 2.6); tone = np.sin(2 * np.pi * np.cumsum(f) / SR)
    n = hp(rng.standard_normal(len(t)), 1500) * (t / d) ** 2
    return (tone * 0.25 + n * 0.5) * (t / d) ** 1.5 * np.minimum(1, (d - t) / 0.03)


def sfx_boom(rng, vol=1.0):
    t = tt(1.1); f = 90 * np.exp(-t / 0.25) + 32; ph = 2 * np.pi * np.cumsum(f) / SR
    return (np.sin(ph) * np.exp(-t / 0.3) + lp(rng.standard_normal(len(t)), 900) * np.exp(-t / 0.12) * 0.5) * vol


def sfx_hit(rng, vol=1.0):
    t = tt(0.6); f = 70 * np.exp(-t / 0.08) + 42; return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.16) + hp(rng.standard_normal(len(t)), 2500) * np.exp(-t / 0.02) * 0.25) * vol


def sfx_ding(f=1318.5, d=1.2):
    t = tt(d); return (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t / 0.2) + 0.2 * np.sin(2 * np.pi * f * 4.2 * t) * np.exp(-t / 0.08)) * np.exp(-t / 0.35) * 0.5


def sfx_sweep(d=1.4):
    t = tt(d); f = 330 * 2 ** (t / d * 2.0); return np.sin(2 * np.pi * np.cumsum(f) / SR) * (t / d) ** 1.2 * np.minimum(1, (d - t) / 0.06) * 0.4


def sfx_shimmer(rng, d=2.4):
    t = tt(d); x = np.zeros_like(t)
    for k, m in enumerate((81, 84, 88, 91, 93)):
        x += np.sin(2 * np.pi * mtof(m) * t) * np.exp(-np.maximum(t - k * 0.09, 0) / 0.7) * (t >= k * 0.09)
    return x * 0.18


# ---------------------------------------------------------------- reading the plan
def _num(v, d=0.0):
    try: return float(v)
    except (TypeError, ValueError): return d


def scene_times(spec):
    D = _num(spec.get('duration'), 10)
    bg = spec.get('background')
    ts = [0.0]
    if isinstance(bg, list):
        ts += [_num(b.get('t')) for b in bg if isinstance(b, dict) and _num(b.get('t')) > 0.5]
    else:
        # no background changes: use the transitions as scene borders
        ts += [(_num(L.get('start')) + _num(L.get('end'))) / 2 for L in spec.get('layers', []) if isinstance(L, dict) and L.get('type') == 'transition']
    ts = sorted({round(t, 3) for t in ts if t < D - 1.0})
    return ts + [D]


def _anim(L, key='in'):
    a = L.get(key)
    if isinstance(a, dict): return a.get('anim'), _num(a.get('dur'), 0.5)
    if isinstance(a, str): return a, 0.5
    return None, 0


def events(spec):
    """[(time, kind, strength)] sound effects derived from the plan."""
    D = _num(spec.get('duration'), 10); ev = []; first_hero = set()
    sc = scene_times(spec)
    def scene_of(t): return max(i for i, s in enumerate(sc[:-1]) if s <= t + 1e-6) if sc[:-1] else 0
    for L in spec.get('layers', []):
        if not isinstance(L, dict): continue
        ty = L.get('type'); st = _num(L.get('start'), 0.0); en = _num(L.get('end'), D)
        a, dur = _anim(L)
        if ty == 'transition':
            mid = (st + en) / 2
            ev += [(max(0, mid - 0.9), 'riser', 1.0), (st, 'whoosh', 1.0), (mid, 'boom' if L.get('style') in ('flash', 'iris', 'glitch') else 'hit', 1.0)]
            continue
        if ty in ('blob', 'particles', 'grid', 'line', 'circle') and not L.get('count'):
            if ty == 'line' and st > 0: ev.append((st, 'swish', 0.6))
            continue
        big = ty in ('card', 'chart', 'chip', 'device', 'image') or (ty == 'text' and _num(L.get('size'), 60) >= 90) or ty == 'rrect'
        r = L.get('reveal')
        if ty == 'text' and isinstance(r, dict) and r.get('mode') in ('letters', 'chars'):
            step = max(0.03, _num(r.get('step'), 0.05)); txt = str(L.get('text', '')); n = len(txt.replace(' ', ''))
            stride = 1 if step >= 0.08 else 2
            for i in range(0, min(n, 40), stride): ev.append((st + a_off(i, step), 'tick', 0.6 + 0.4 * (i % 3 == 0)))
        elif ty == 'text' and isinstance(L.get('count'), dict):
            c = L['count']; cd = max(0.4, _num(c.get('dur'), 1.5)); k = int(cd / 0.07)
            for i in range(k): ev.append((st + i * 0.07, 'count', i / max(1, k)))
            ev.append((st + cd, 'ding', 1.0))
        elif a in ('pop', 'bounce', 'spin') and big:
            ev.append((st, 'pop', 1.0))
        elif a in ('slide_up', 'slide_down', 'slide_left', 'slide_right', 'rise', 'wipe_right', 'wipe_left', 'wipe_up', 'wipe_down', 'zoom', 'tilt', 'blur') and big:
            ev.append((st, 'swish', 0.55 if ty != 'text' else 0.7))
        if ty == 'chart' and isinstance(L.get('grow'), dict): ev.append((_num(L['grow'].get('start'), st), 'sweep', 0.8))
        if ty == 'text' and _num(L.get('size'), 0) >= 150:
            s = scene_of(st)
            if s not in first_hero: first_hero.add(s); ev.append((st + 0.05, 'hit', 0.9))
        if ty == 'emoji' and a == 'pop' and st > D * 0.6: ev.append((st, 'shimmer', 1.0))
    # remove clutter: same kind within 70 ms keeps only the first
    ev = [e for e in ev if 0 <= e[0] < D - 0.05]; ev.sort(key=lambda e: e[0]); out = []; last = {}
    for t, k, v in ev:
        if k not in ('count', 'tick') and t - last.get(k, -9) < 0.07: continue
        last[k] = t; out.append((t, k, v))
    return out


def a_off(i, step): return i * step


def sfx_stamp(rng, vol=1.0):
    t = tt(0.5); f = 160 * np.exp(-t / 0.05) + 55; ph = 2 * np.pi * np.cumsum(f) / SR
    return (np.sin(ph) * np.exp(-t / 0.11) + hp(rng.standard_normal(len(t)), 1800) * np.exp(-t / 0.015) * 0.35 + 0.3 * np.sin(2 * np.pi * 900 * t) * np.exp(-t / 0.01)) * vol


def sfx_click(rng, pitch=1.0):
    t = tt(0.09); return (np.sin(2 * np.pi * 1250 * pitch * t) * np.exp(-t / 0.012) * 0.55 + bp(rng.standard_normal(len(t)), 1500, 6500) * np.exp(-t / 0.006) * 0.5)


def sfx_air(rng, d=0.5):
    t = tt(d); n = bp(rng.standard_normal(len(t)), 900, 4200); return n * np.sin(np.pi * np.minimum(1, t / d)) ** 2 * 0.9


def sfx_reverse(rng, d=0.4):
    return sfx_swish(rng, d, False)[::-1] * 0.8


def sfx_glitch(rng):
    t = tt(0.16); x = np.sign(np.sin(2 * np.pi * (700 + 2400 * rng.random()) * t)) * 0.25 * (np.arange(len(t)) // 600 % 2) + hp(rng.standard_normal(len(t)), 2500) * 0.3
    return x * np.exp(-t / 0.07)


def kinetic_events(spec):
    """[(time, kind, strength, pan)] - only typography related sounds (plus the transitions that carry the text)."""
    D = _num(spec.get('duration'), 10); W = 1920.0; ev = []; hero = set(); sc = scene_times(spec)
    def scene_of(t): return max(i for i, x in enumerate(sc[:-1]) if x <= t + 1e-6) if sc[:-1] else 0
    for L in spec.get('layers', []):
        if not isinstance(L, dict): continue
        ty = L.get('type'); st = _num(L.get('start'), 0.0); en = _num(L.get('end'), D)
        if ty == 'transition':
            mid = (st + en) / 2
            ev += [(max(0, mid - 0.9), 'riser', 0.8, 0.0), (st, 'whoosh', 1.0, 0.0),
                   (mid, 'glitch' if L.get('style') == 'glitch' else ('boom' if L.get('style') in ('flash', 'iris') else 'stamp'), 1.0, 0.0)]
            continue
        if ty != 'text': continue
        txt = str(L.get('text', '')); size = _num(L.get('size'), 60); pan = max(-0.8, min(0.8, (_num(L.get('x'), W / 2) / W - 0.5) * 1.6))
        a, dur = _anim(L); o, odur = _anim(L, 'out'); r = L.get('reveal')
        if isinstance(L.get('count'), dict):
            c = L['count']; cd = max(0.4, _num(c.get('dur'), 1.5)); k = int(cd / 0.07)
            ev += [(st + i * 0.07, 'count', i / max(1, k), pan) for i in range(k)] + [(st + cd, 'ding', 1.0, pan)]
        elif isinstance(r, dict) and r.get('mode') == 'words':
            step = max(0.08, _num(r.get('step'), 0.3))
            for i, _w in enumerate(txt.split()[:24]): ev.append((st + i * step, 'click', 1.0, pan))
        elif isinstance(r, dict) and r.get('mode') in ('letters', 'chars'):
            step = max(0.03, _num(r.get('step'), 0.05)); n = len(txt.replace(' ', '')); stride = 1 if step >= 0.08 else 2
            for i in range(0, min(n, 40), stride): ev.append((st + i * step, 'tick', 0.6 + 0.4 * (i % 3 == 0), pan))
            if size >= 120: ev.append((st + n * step, 'stamp', 0.55, pan))
        elif a in ('pop', 'bounce', 'spin', 'zoom', 'tilt'):
            ev.append((st, 'stamp', 0.6 + 0.4 * min(1, size / 150.0), pan))
        elif a in ('slide_up', 'slide_down', 'slide_left', 'slide_right', 'rise', 'wipe_right', 'wipe_left', 'wipe_up', 'wipe_down'):
            p2 = {'slide_left': 0.6, 'wipe_left': 0.6, 'slide_right': -0.6, 'wipe_right': -0.6}.get(a, pan)
            ev.append((st, 'swish', 0.9 if size >= 90 else 0.55, p2))
        elif a in ('blur', 'fade'):
            ev.append((st, 'air', 0.7, pan))
        if size >= 150 and not isinstance(L.get('count'), dict):
            s = scene_of(st)
            if s not in hero: hero.add(s); ev.append((st + 0.04, 'hit', 0.8, 0.0))
        if o and odur >= 0.25 and en < D - 0.2 and size >= 70: ev.append((en - odur, 'reverse', 0.5, pan))
    ev = [e for e in ev if 0 <= e[0] < D - 0.05]; ev.sort(key=lambda e: e[0]); out = []; last = {}
    for t, k, v, pn in ev:
        if k not in ('count', 'tick', 'click') and t - last.get(k, -9) < 0.09: continue
        last[k] = t; out.append((t, k, v, pn))
    return out


# ---------------------------------------------------------------- composing
def _seed(spec, style):
    return int(hashlib.md5((str(spec.get('title', '')) + style + str(spec.get('duration'))).encode()).hexdigest()[:8], 16)


def music(spec, style='uplift', seed=1):
    S = STYLES.get(style, STYLES['uplift']); rng = np.random.default_rng(seed)
    D = _num(spec.get('duration'), 10); beat = 60.0 / S['bpm']; bar = beat * 4
    scale = MINOR if S['minor'] else MAJOR
    sc = scene_times(spec); ns = len(sc) - 1
    def level(t):            # 0..1 intensity by scene: soft start, build, fuller middle, settle at the end
        i = max(j for j, s in enumerate(sc[:-1]) if s <= t + 1e-6) if ns else 0
        if ns <= 1: return 0.8
        base = [0.35, 0.65, 0.9, 1.0, 0.55]
        return base[min(i, len(base) - 1)] if i < ns - 1 else 0.55
    T = Track(D); nb = int(D / beat) + 2
    def chord(bar_i):
        deg = S['prog'][bar_i // 2 % len(S['prog'])]
        r = [S['root'] + scale[(deg + k) % 7] + 12 * ((deg + k) // 7) for k in (0, 2, 4)]
        return r
    # pads: 2 bars per chord
    for ci in range(int(D / (bar * 2)) + 1):
        t0 = ci * bar * 2
        if t0 >= D: break
        ch = chord(ci * 2); d = min(bar * 2 + 0.6, D - t0 + 0.5)
        T.add(t0, pad_chord([m + 12 for m in ch], d), 0.36 * (0.5 + level(t0 + 0.1) * 0.5), 0.0)
        T.add(t0, pad_chord([ch[0] - 12], d) * 0.8, 0.30, 0.0)
    last_scene_start = sc[-2] if ns > 1 else D
    for b in range(nb):
        t = b * beat
        if t >= D - 0.2: break
        lv = level(t); ch = chord(int(t / bar)); root = ch[0] - 12; step_in_bar = b % 4
        in_final = t >= last_scene_start and ns > 1
        # drums
        if lv >= 0.6 and not (in_final and t > last_scene_start + bar):
            if step_in_bar in (0, 2) or lv > 0.95 and step_in_bar == 3 and (int(t / bar) % 2): T.add(t, kick(), 0.85, 0)
            if step_in_bar in (1, 3) and lv >= 0.85: T.add(t, clap(rng), 0.45, 0.1)
            if lv >= 0.65: T.add(t + beat / 2, hat(rng, 1.0, open_=(step_in_bar == 3 and lv > 0.85)), 0.5 * lv, 0.35 if b % 2 else -0.35)
            if lv >= 0.85: T.add(t + beat / 4 * 3 if False else t + beat / 4, hat(rng, 0.6), 0.25, -0.2)
        elif lv >= 0.3 and step_in_bar == 0 and not in_final: T.add(t, kick(0.6), 0.6, 0)
        # bass (eighths with an octave jump)
        if lv >= 0.6:
            for k, off in enumerate((0, 0.5)):
                note = root + (12 if (k == 1 and step_in_bar % 2) else 0)
                T.add(t + off * beat, bass_note(mtof(note), beat * 0.48), 0.42 * lv, 0)
        # arpeggio
        if lv >= 0.6:
            order = [0, 1, 2, 1, 2, 1, 0, 1]
            for k in range(2):
                n_i = order[(b * 2 + k) % 8]; m = ch[n_i] + 12 + (12 if (b * 2 + k) % 8 in (4, 5) else 0)
                T.add(t + k * beat / 2, pluck(mtof(m), 0.5), 0.17 * lv, (-0.5 + ((b * 2 + k) % 6) / 6.0))
        elif lv >= 0.3 and step_in_bar in (0, 2):
            T.add(t, pluck(mtof(ch[(b // 2) % 3] + 12), 0.7), 0.12, 0.3)
    return T.b


def compose(spec, out_wav, style='uplift', music_level=0.55, sfx_level=0.9, with_music=True, with_sfx=True):
    """Write music + sfx for `spec` to out_wav. Returns a small dict (what was placed)."""
    import wave
    kinetic = (style == 'kinetic'); ui = (style == 'ui')
    style = style if (style in STYLES or kinetic or ui) else 'uplift'
    if kinetic or ui: with_music = False
    D = _num(spec.get('duration'), 10); seed = _seed(spec, style); rng = np.random.default_rng(seed)
    mus = music(spec, style, seed) if with_music else np.zeros((int(D * SR), 2))
    sx = Track(D)
    ev = ([e for e in kinetic_events(spec)] if kinetic else ui_events(spec) if ui else [(t, k, v, None) for t, k, v in events(spec)]) if with_sfx else []
    kinds = {}
    for t, k, v, pan0 in ev:
        kinds[k] = kinds.get(k, 0) + 1
        pan = float(np.clip(rng.uniform(-0.35, 0.35), -1, 1)) if pan0 is None else pan0
        if k == 'click': sx.add(t, (ui_click(rng, rng.uniform(0.95, 1.1)) if ui else sfx_click(rng, rng.uniform(0.92, 1.12))), 0.5 * v, pan); continue
        if k == 'toggle': sx.add(t, ui_toggle(rng, True), 0.5 * v, pan); continue
        if k == 'notify': sx.add(t, ui_notify(rng), 0.42 * v, pan); continue
        if k == 'swipe': sx.add(t, ui_swipe(rng, 0.32, True), 0.26 * v, pan); continue
        if k == 'drop': sx.add(t, ui_drop(rng), 0.5 * v, pan); continue
        if k == 'key': sx.add(t, ui_key(rng, rng.uniform(0.9, 1.15)), 0.3 * v, pan); continue
        if k == 'success': sx.add(t, ui_success(rng), 0.5 * v, pan); continue
        if k == 'fill': sx.add(t, ui_fill(rng), 0.32 * v, pan); continue
        if k == 'stamp': sx.add(t, sfx_stamp(rng, 1.0), 0.62 * v, pan); continue
        if k == 'air': sx.add(t, sfx_air(rng, 0.5), 0.26 * v, pan); continue
        if k == 'reverse': sx.add(t, sfx_reverse(rng, 0.4), 0.24 * v, pan); continue
        if k == 'glitch': sx.add(t, sfx_glitch(rng), 0.5, 0.0); continue
        if k == 'pop': sx.add(t, sfx_pop(rng, rng.uniform(0.9, 1.25)), 0.55 * v, pan)
        elif k == 'tick': sx.add(t, sfx_tick(rng, rng.uniform(0.9, 1.15)), 0.32 * v, pan)
        elif k == 'count': sx.add(t, (ui_click(rng, 0.7 + 0.9 * v) if ui else sfx_tick(rng, 0.8 + 0.9 * v)), 0.2 if ui else 0.24, 0.0)
        elif k == 'swish': sx.add(t, sfx_swish(rng, 0.42, True), 0.19 * v, pan)
        elif k == 'whoosh': sx.add(t, sfx_whoosh(rng, 1.0), 0.30, 0.0)
        elif k == 'riser': sx.add(t, sfx_riser(rng, 0.9), 0.27, 0.0)
        elif k == 'boom': sx.add(t, sfx_boom(rng), 0.8, 0.0)
        elif k == 'hit': sx.add(t, sfx_hit(rng, 1.0), 0.65 * v, 0.0)
        elif k == 'ding': sx.add(t, sfx_ding(), 0.5, 0.15)
        elif k == 'sweep': sx.add(t, sfx_sweep(), 0.4, 0.0)
        elif k == 'shimmer': sx.add(t, sfx_shimmer(rng), 0.8, 0.0)
    sfxb = sx.b
    if with_sfx and len(ev):
        sfxb = reverb(sfxb, rng, 1.0, 0.18)
    if with_music:
        mus = reverb(mus, rng, 1.6, 0.22)
        # make room: music dips ~4 dB while a big effect plays
        duck = np.ones(len(mus))
        for t, k, v, _p in ev:
            if k in ('boom', 'hit', 'whoosh', 'pop', 'ding'):
                i = int(t * SR); j = min(len(duck), i + int(0.35 * SR)); dd = np.linspace(0.62, 1.0, j - i) if j > i else []
                if j > i: duck[i:j] = np.minimum(duck[i:j], dd)
        duck = lp(duck, 40, 1)
        mus = mus * duck[:, None]
    mix = mus * music_level + sfxb * sfx_level
    n = len(mix); t = np.arange(n) / SR
    mix *= np.minimum(1, t / 0.25)[:, None] * np.minimum(1, np.maximum(0, (D - t)) / 1.4)[:, None]   # fade in / out
    mix = np.tanh(mix * 1.1) / np.tanh(1.1)                                                              # gentle glue, no clipping
    peak = np.abs(mix).max(); mix = mix / peak * 0.89 if peak > 0 else mix                               # peak about -1 dBFS
    pcm = (np.clip(mix, -1, 1) * 32767).astype('<i2')
    with wave.open(out_wav, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
    return {'style': style, 'duration': D, 'sfx': kinds, 'sfx_count': len(ev), 'scenes': scene_times(spec)}


# ---------------------------------------------------------------- UI sounds
def ui_click(rng, pitch=1.0):
    t = tt(0.12)
    a = np.sin(2 * np.pi * 2100 * pitch * t) * np.exp(-t / 0.006) * 0.5
    b = np.sin(2 * np.pi * 1300 * pitch * t) * np.exp(-t / 0.018) * (t > 0.012) * 0.35
    return a + b + bp(rng.standard_normal(len(t)), 2000, 8000) * np.exp(-t / 0.004) * 0.25


def ui_toggle(rng, on=True):
    t = tt(0.2); f1, f2 = (900, 1350) if on else (1350, 880)
    return (np.sin(2 * np.pi * f1 * t) * np.exp(-t / 0.02) * 0.5 + np.sin(2 * np.pi * f2 * t) * np.exp(-t / 0.04) * (t > 0.05) * 0.5) * 0.8


def ui_notify(rng):
    t = tt(0.9); x = np.zeros_like(t)
    for f, d, a in ((1568, 0.0, 0.5), (2093, 0.11, 0.45)):
        m = t >= d; x += np.sin(2 * np.pi * f * (t - d)) * np.exp(-np.maximum(t - d, 0) / 0.18) * m * a + np.sin(2 * np.pi * f * 2.01 * (t - d)) * np.exp(-np.maximum(t - d, 0) / 0.05) * m * a * 0.2
    return x


def ui_swipe(rng, d=0.32, up=True):
    t = tt(d); n = rng.standard_normal(len(t)); out = np.zeros_like(n); chunks = 16; L = len(t) // chunks
    for i in range(chunks):
        fc = (700 + 2800 * (i / chunks)) if up else (3500 - 2800 * (i / chunks)); s = slice(i * L, (i + 1) * L if i < chunks - 1 else len(t))
        out[s] = bp(n[max(0, i * L - 150):(i + 1) * L], fc * 0.8, fc * 1.25)[-(s.stop - s.start):]
    return out * np.sin(np.pi * np.minimum(1, t / d)) ** 2 * 1.6


def ui_drop(rng, vol=1.0):
    t = tt(0.35); f = 120 * np.exp(-t / 0.03) + 70
    thud = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.07)
    glass = np.sin(2 * np.pi * 3200 * t) * np.exp(-t / 0.012) * 0.25 + bp(rng.standard_normal(len(t)), 3000, 9000) * np.exp(-t / 0.008) * 0.2
    return (thud * 0.9 + glass) * vol


def ui_key(rng, pitch=1.0):
    t = tt(0.1); return (np.sin(2 * np.pi * 180 * pitch * t) * np.exp(-t / 0.018) * 0.6 + bp(rng.standard_normal(len(t)), 1800, 6500) * np.exp(-t / 0.005) * 0.55)


def ui_success(rng):
    t = tt(1.1); x = np.zeros_like(t)
    for k, f in enumerate((784, 988, 1175, 1568)):
        d = k * 0.07; m = t >= d; x += np.sin(2 * np.pi * f * (t - d)) * np.exp(-np.maximum(t - d, 0) / 0.28) * m * 0.3
    return x


def ui_fill(rng, d=1.4):
    n = int(d / 0.06); out = np.zeros(int(d * SR) + int(0.1 * SR))
    for i in range(n):
        f = 700 * 2 ** (i / n * 1.6); tk = tt(0.06); out[int(i * 0.06 * SR):int(i * 0.06 * SR) + len(tk)] += np.sin(2 * np.pi * f * tk) * np.exp(-tk / 0.012) * (0.25 + 0.25 * i / n)
    return out[:int(d * SR)]


def ui_events(spec):
    """[(time, kind, strength, pan)] - sounds for UI / SaaS animation. Text is nearly silent on purpose."""
    D = _num(spec.get('duration'), 10); W = 1920.0; ev = []
    for L in spec.get('layers', []):
        if not isinstance(L, dict): continue
        ty = L.get('type'); st = _num(L.get('start'), 0.0); en = _num(L.get('end'), D); a, dur = _anim(L)
        pan = max(-0.8, min(0.8, (_num(L.get('x'), W / 2) / W - 0.5) * 1.6))
        if ty == 'transition':
            mid = (st + en) / 2; ev += [(st + 0.05, 'swipe', 1.0, 0.0), (mid, 'drop' if L.get('style') != 'flash' else 'boom', 0.7, 0.0)]
        elif ty in ('card', 'device', 'image'):
            if a in ('slide_left', 'slide_right', 'slide_up', 'slide_down', 'rise', 'wipe_right', 'wipe_left'): ev += [(st, 'swipe', 0.8, pan), (st + dur * 0.8, 'drop', 0.7, pan)]
            else: ev.append((st + dur * 0.6, 'drop', 0.85, pan))
        elif ty in ('rrect', 'chip'):
            if ty == 'rrect' and (_num(L.get('h'), 999) < 100 or (_num(L.get('w'), 0) > 900 and _num(L.get('h'), 0) > 500)): continue      # skeleton lines, toggle tracks, big backdrops stay silent
            if a in ('slide_left', 'slide_right'): ev += [(st, 'swipe', 0.55, pan), (st + dur * 0.8, 'notify' if ty == 'rrect' and _num(L.get('h'), 999) < 200 and 400 < _num(L.get('w'), 0) <= 760 else 'click', 0.8, pan)]
            elif a: ev.append((st + dur * 0.5, 'click' if ty == 'chip' else 'drop', 0.55, pan))
        elif ty == 'icon':
            if L.get('name') == 'check': ev.append((st + 0.1, 'success', 1.0, pan))
            elif a: ev.append((st + dur * 0.5, 'click', 0.7, pan))
        elif ty == 'chart':
            g = L.get('grow') if isinstance(L.get('grow'), dict) else {}; ev.append((_num(g.get('start'), st), 'fill', 0.8, pan))
        elif ty == 'progress':
            g = L.get('grow') if isinstance(L.get('grow'), dict) else {}; ev.append((_num(g.get('start'), st), 'fill', 0.7, pan))
        elif ty == 'text':
            r = L.get('reveal')
            if isinstance(L.get('count'), dict):
                c = L['count']; cd = max(0.4, _num(c.get('dur'), 1.5)); ev += [(st + i * 0.08, 'count', i / max(1, int(cd / 0.08)), pan) for i in range(int(cd / 0.08))] + [(st + cd, 'success', 0.7, pan)]
            elif isinstance(r, dict) and r.get('mode') in ('chars', 'letters'):
                step = max(0.03, _num(r.get('step'), 0.05)); n = len(str(L.get('text', '')).replace(' ', ''))
                ev += [(st + i * step, 'key', 0.6 + 0.4 * (i % 3 == 0), pan) for i in range(min(n, 40))]
        elif ty in ('circle',) and isinstance(L.get('keys'), dict) and 'x' in L['keys']:       # toggle knob: moves along x -> toggle sound
            ks = L['keys']['x']
            if len(ks) >= 2: ev.append((_num(ks[1][0]) - 0.1, 'toggle', 0.9, pan))
        elif ty == 'emoji' and a == 'pop': ev.append((st + 0.1, 'click', 0.5, pan))
    for L in spec.get('layers', []):          # a cursor (arrow icon that moves): it clicks every time it arrives at a key
        if isinstance(L, dict) and L.get('type') == 'icon' and L.get('name') == 'arrow_up' and isinstance(L.get('keys'), dict) and 'x' in L['keys']:
            for k in L['keys']['x'][1:]: ev.append((_num(k[0]), 'click', 1.0, 0.0))
    ev = [e for e in ev if 0 <= e[0] < D - 0.05]; ev.sort(key=lambda e: e[0]); out = []; last = {}
    for t, k, v, pn in ev:
        if k not in ('count', 'key') and t - last.get(k, -9) < 0.08: continue
        last[k] = t; out.append((t, k, v, pn))
    return out


def sfx_pack(out_dir, seed=7):
    """Individual kinetic-typography sound effects as WAV files, to drop into any editor."""
    import os, wave
    rng = np.random.default_rng(seed); os.makedirs(out_dir, exist_ok=True)
    items = {'stamp_hit': sfx_stamp(rng), 'stamp_soft': sfx_stamp(rng, 0.6), 'word_click': sfx_click(rng), 'letter_tick': sfx_tick(rng), 'pop': sfx_pop(rng),
             'whoosh_short': sfx_swish(rng, 0.4, True), 'whoosh_long': sfx_whoosh(rng, 1.0), 'whoosh_reverse': sfx_reverse(rng, 0.5), 'air_soft': sfx_air(rng, 0.6),
             'riser': sfx_riser(rng, 1.2), 'impact_boom': sfx_boom(rng), 'low_hit': sfx_hit(rng), 'glitch': sfx_glitch(rng), 'ding': sfx_ding(), 'sweep_up': sfx_sweep(1.2),
             'ui_click': ui_click(rng), 'ui_toggle_on': ui_toggle(rng, True), 'ui_toggle_off': ui_toggle(rng, False), 'ui_notification': ui_notify(rng), 'ui_swipe': ui_swipe(rng),
             'ui_card_drop': ui_drop(rng), 'ui_key': ui_key(rng), 'ui_success': ui_success(rng), 'ui_progress_fill': ui_fill(rng)}
    paths = []
    for name, x in items.items():
        x = np.asarray(x, dtype=float); x = x / max(1e-9, np.abs(x).max()) * 0.85
        n = int(0.004 * SR); x[:n] *= np.linspace(0, 1, n); x[-n:] *= np.linspace(1, 0, n)
        p = os.path.join(out_dir, name + '.wav')
        with wave.open(p, 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((np.clip(x, -1, 1) * 32767).astype('<i2').tobytes())
        paths.append(p)
    return paths
