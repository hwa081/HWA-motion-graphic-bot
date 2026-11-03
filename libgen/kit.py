"""Tiny helpers to write scene specs for the design library."""
WH = [1, 1, 1]; INK = [0.07, 0.08, 0.18]; VI = [0.52, 0.38, 1]; PK = [1, 0.35, 0.68]; CY = [0.3, 0.86, 1]; GR = [0.2, 0.85, 0.56]
YL = [1, 0.82, 0.25]; OR = [1, 0.58, 0.25]; BL = [0.28, 0.45, 1]; RD = [1, 0.32, 0.36]; TL = [0.1, 0.78, 0.74]

class Theme:
    def __init__(s, bg, fg, fg2, a, b, c, light=False, card_head=None):
        s.bg, s.fg, s.fg2, s.a, s.b, s.c, s.light = bg, fg, fg2, a, b, c, light
THEMES = {
    'neon':   Theme('neon_night', WH, [0.78, 0.88, 1], VI, PK, CY),
    'aurora': Theme('dark_aurora', WH, [0.8, 1, 0.92], GR, CY, YL),
    'ocean':  Theme('ocean', WH, [0.8, 0.93, 1], CY, YL, PK),
    'sunset': Theme('sunset', WH, [1, 0.93, 0.8], YL, PK, OR),
    'mono':   Theme('mono_dark', WH, [0.75, 0.78, 0.85], YL, PK, CY),
    'pastel': Theme('light_pastel', INK, [0.35, 0.3, 0.55], VI, PK, GR, True),
    'clean':  Theme('mono_light', INK, [0.35, 0.38, 0.5], BL, PK, GR, True),
}

def bgpair(a, b): return a, b

class Sc:
    def __init__(s, dur, th, bg=None):
        s.dur = float(dur); s.th = THEMES[th] if isinstance(th, str) else th; s.L = []; s.script = []; s.bg = bg or s.th.bg; s.cam = True; s.sound = 'ui'
    # ---- generic
    def add(s, **k):
        if 'anim' in k or 'adur' in k:
            a = k.pop('anim', None); d = k.pop('adur', 0.5)
            if a: k['in'] = {'anim': a, 'dur': d}
        o = k.pop('out', 'fade')
        end = k.get('end', s.dur)
        if o and end < s.dur - 0.05: k['out'] = {'anim': o, 'dur': 0.3}
        if 'end' not in k: k['end'] = s.dur
        s.L.append(k); return k
    def say(s, t, text): s.script.append([round(t, 2), text])
    # ---- layers
    def text(s, text, x, y, size, start, font='bold_italic', color=None, anim='slide_up', end=None, **k):
        d = dict(type='text', text=text, x=x, y=y, size=size, font=font, color=color or s.th.fg, start=start, anim=anim, fixed=True, **k)
        if end is not None: d['end'] = end
        return s.add(**d)
    def rr(s, x, y, w, h, start, r=None, fill=WH, fo=0.12, border=None, bo=0.35, anim='fade', end=None, **k):
        d = dict(type='rrect', x=x, y=y, w=w, h=h, r=r if r is not None else min(h, w) // 2 if h < 120 else 36, fill=fill, fill_opacity=fo, start=start, anim=anim, **k)
        if border is not None: d.update(border=border, border_opacity=bo, border_w=2)
        if end is not None: d['end'] = end
        return s.add(**d)
    def glass(s, x, y, w, h, start, r=36, anim='zoom', end=None, **k):
        lt = s.th.light
        bd = k.pop('border', None)
        return s.rr(x, y, w, h, start, r=r, fill=WH, fo=0.14 if not lt else 0.7, border=bd or (WH if not lt else [0.7, 0.7, 0.9]), bo=0.35 if bd is None else 0.8, shadow=0.35 if not lt else 0.18, anim=anim, end=end, **k)
    def circle(s, x, y, r, start, fill=WH, fo=1.0, anim='pop', end=None, **k):
        d = dict(type='circle', x=x, y=y, r=r, fill=fill, fill_opacity=fo, start=start, anim=anim, **k)
        if end is not None: d['end'] = end
        return s.add(**d)
    def icon(s, name, x, y, size, start, color=None, anim='pop', end=None, **k):
        d = dict(type='icon', name=name, x=x, y=y, size=size, color=color or s.th.fg, width=max(4, size // 14), start=start, anim=anim, **k)
        if end is not None: d['end'] = end
        return s.add(**d)
    def emoji(s, ch, x, y, size, start, anim='pop', end=None, **k):
        d = dict(type='emoji', char=ch, x=x, y=y, size=size, start=start, anim=anim, **k)
        if end is not None: d['end'] = end
        return s.add(**d)
    def chip(s, emo, label, x, y, start, scale=0.85, anim='pop', end=None, **k):
        d = dict(type='chip', emoji=emo, label=label, x=x, y=y, scale=scale, start=start, anim=anim, **k)
        if s.th.light: d['light'] = 1
        elif 'light' not in k: d['light'] = 0
        if end is not None: d['end'] = end
        return s.add(**d)
    def card(s, title, big, x, y, start, head=None, emoji='📊', sub='', scale=1.1, yaw=0, roll=0, count=None, anim='pop', end=None, **k):
        d = dict(type='card', kind='custom', title=title, big_text=big, subtitle=sub, emoji=emoji, header=head or s.th.a, body=[0.1, 0.11, 0.22], body2=[0.16, 0.18, 0.32],
                 x=x, y=y, scale=scale, yaw=yaw, roll=roll, start=start, anim=anim, **k)
        if count is not None: d['keys'] = {'number': [[start + 0.25, 0], [start + 1.8, count, 'out']]}
        if end is not None: d['end'] = end
        return s.add(**d)
    def chart(s, kind, data, x, y, w, h, start, labels=None, grow=1.4, colors=None, center=None, end=None, anim='fade', **k):
        d = dict(type='chart', kind=kind, data=data, x=x, y=y, w=w, h=h, start=start - 0.2, colors=colors or [s.th.a, s.th.b, s.th.c], text_color=s.th.fg, grow={'start': start, 'dur': grow}, anim=anim, **k)
        if labels: d['labels'] = labels
        if center: d['center_text'] = center
        if end is not None: d['end'] = end
        return s.add(**d)
    def prog(s, kind, x, y, w, h, start, color=None, label=None, grow=1.3, end=None, anim='fade', **k):
        d = dict(type='progress', kind=kind, x=x, y=y, w=w, h=h, color=color or s.th.a, track=[0.82, 0.84, 0.92] if s.th.light else [0.2, 0.22, 0.34], grow={'start': start, 'dur': grow}, start=max(0, start - 0.2), anim=anim, **k)
        if label: d['label'] = label
        if end is not None: d['end'] = end
        return s.add(**d)
    def dev(s, kind, x, y, w, start, path='assets/sample_screenshot.png', anim='rise', end=None, **k):
        d = dict(type='device', kind=kind, path=path, x=x, y=y, w=w, start=start, anim=anim, adur=0.8, **k)
        d.setdefault('float', {'y': 10, 'speed': 0.7})
        if end is not None: d['end'] = end
        return s.add(**d)
    def img(s, path, x, y, w, h, start, r=30, anim='zoom', end=None, zoom=(1.0, 1.25), pan=(-0.4, 0.4), raw=None, **k):
        d = dict(type='image', path=raw or 'assets/designlib/%s.jpg' % path, x=x, y=y, w=w, h=h, r=r, start=start, anim=anim, adur=0.7, shadow=0.45, shadow_blur=34, fit='cover', **k)
        e = end if end is not None else s.dur
        d['keys'] = {'zoom': [[start, zoom[0]], [e, zoom[1], 'linear']], 'pan_x': [[start, pan[0]], [e, pan[1], 'linear']]}
        if end is not None: d['end'] = end
        return s.add(**d)
    def blob(s, x, y, r, c1, c2, fo=0.45, start=0, **k): return s.add(type='blob', x=x, y=y, r=r, color=c1, color2=c2, fill_opacity=fo, softness=0.9, start=start, **k)
    def grid(s, kind='dots', fo=0.1, sp=70, color=WH, **k): return s.add(type='grid', kind=kind, spacing=sp, color=color, fill_opacity=fo, scroll={'x': 10, 'y': 6}, vignette=0.85, start=0, **k)
    def particles(s, n=60, seed=3, color=WH, **k): return s.add(type='particles', count=n, color=color, size=3, speed=0.9, seed=seed, start=0, **k)
    def line(s, pts, start, width=5, color=None, anim='wipe_right', end=None, **k):
        d = dict(type='line', points=pts, width=width, color=color or s.th.a, start=start, anim=anim, **k)
        if end is not None: d['end'] = end
        return s.add(**d)
    def trans(s, style, start, color=None, direction='right', dur=0.9): return s.add(type='transition', style=style, direction=direction, color=color or s.th.a, start=start, end=start + dur, out=None)
    def deco(s, kind=0):
        """background decoration that gives depth: kind 0 grid+blobs, 1 blobs+particles, 2 lines grid, 3 crosses, 4 nothing"""
        th = s.th
        if kind == 0: s.grid('dots', 0.10 if not th.light else 0.14, color=WH if not th.light else INK); s.blob(380, 260, 520, th.a, th.b, 0.4 if not th.light else 0.5); s.blob(1560, 820, 460, th.c, th.a, 0.35 if not th.light else 0.45)
        elif kind == 1: s.blob(960, 540, 640, th.a, th.c, 0.35 if not th.light else 0.45); s.particles(60, 5, color=WH if not th.light else VI)
        elif kind == 2: s.grid('lines', 0.08, 90, color=th.c if not th.light else INK); s.blob(300, 880, 460, th.b, th.a, 0.35 if not th.light else 0.45)
        elif kind == 3: s.grid('crosses', 0.09, 90, color=WH if not th.light else INK); s.blob(1500, 220, 480, th.a, th.b, 0.38 if not th.light else 0.45)
    def spec(s, title, camera=True):
        sp = {'title': title, 'duration': s.dur, 'size': '16:9', 'fps': 30, 'background': s.bg, 'layers': s.L}
        if camera: sp['camera'] = [{'t': 0, 'zoom': 1, 'x': 960, 'y': 540}, {'t': s.dur, 'zoom': 1.06, 'x': 960, 'y': 540}]
        return sp
