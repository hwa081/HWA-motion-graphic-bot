"""Documentary archetypes. Each function: f(d) -> Sc  (d = variant data). Script = narration lines timed to the reveals."""
from libgen.kit import *

def _beats(s, d, times):
    for t, line in zip(times, d.get('n', [])): s.say(t, line)

def title_hero(d):
    s = Sc(7, d['th']); s.deco(d.get('deco', 1))
    s.img(d['img'], 960, 540, 1920, 1080, 0, r=0, anim='fade', zoom=(1.0, 1.18), pan=(-0.3, 0.3))
    s.rr(960, 540, 1920, 1080, 0, r=0, fill=[0, 0, 0], fo=0.52, anim='none')
    s.text(d['kicker'].upper(), 960, 330, 44, 0.4, font='medium', color=s.th.c, anim='fade')
    s.line([[760, 385], [1160, 385]], 0.7, width=5, color=s.th.a)
    s.text(d['t1'], 960, 520, 140, 1.0, anim='slide_up', shadow=0.5)
    s.text(d['t2'], 960, 680, 140, 1.4, anim='slide_up', gradient={'from': s.th.a, 'to': s.th.b})
    s.text(d['sub'], 960, 850, 50, 3.0, font='medium', color=s.th.fg2, anim='fade')
    _beats(s, d, [0.5, 1.6, 3.4]); return s

def archival_photo(d):
    s = Sc(7.5, d['th']); s.deco(d.get('deco', 2))
    s.img(d['img'], 640, 500, 1060, 700, 0.2, anim='rise', zoom=(1.0, 1.3), pan=(-0.5, 0.5), border=WH)
    s.glass(640, 800, 900, 130, 1.2, r=28, anim='slide_up')
    s.text(d['name'], 640, 780, 54, 1.6, anim='fade')
    s.text(d['cap'], 640, 830, 32, 2.0, font='medium', color=s.th.fg2, anim='fade')
    s.text('{n}', 1440, 400, 210, 1.0, gradient={'from': s.th.a, 'to': s.th.b}, count={'from': d['y0'], 'to': d['y1'], 'start': 1.0, 'dur': 1.8, 'format': '{:d}'})
    for i, f in enumerate(d['facts']):
        s.rr(1440, 590 + i * 120, 620, 90, 2.8 + i * 0.5, r=45, fill=s.th.a, fo=0.2, border=s.th.a, bo=0.6, anim='slide_left')
        s.text(f, 1440, 590 + i * 120, 36, 3.0 + i * 0.5, font='bold', anim='fade')
    _beats(s, d, [0.4, 1.8, 3.2, 5.2]); return s

def timeline(d):
    s = Sc(9.5, d['th']); s.deco(d.get('deco', 2))
    s.text(d['head'], 960, 150, 84, 0.3, gradient={'from': s.th.a, 'to': s.th.b})
    s.line([[240, 560], [1680, 560]], 0.9, width=8, color=s.th.fg2, anim='wipe_right', adur=1.6)
    ev = d['ev']; n = len(ev); xs = [240 + i * (1440 / (n - 1)) for i in range(n)]
    for i, (yr, lab) in enumerate(ev):
        t = 1.8 + i * 1.6; up = i % 2 == 0
        s.circle(xs[i], 560, 26, t, fill=[s.th.a, s.th.b, s.th.c, s.th.a][i % 4], anim='pop')
        s.circle(xs[i], 560, 26, t + 0.1, fill=WH, fo=0, border=s.th.fg, border_w=3, border_opacity=0.6, anim='none', end=t + 0.9, keys={'scale': [[t + 0.1, 1], [t + 0.9, 2.6, 'out']], 'opacity': [[t + 0.1, 0.9], [t + 0.9, 0, 'linear']]})
        s.line([[xs[i], 560 - 40 if up else 600], [xs[i], 430 if up else 690]], t, width=4, color=s.th.fg2, anim='wipe_up' if up else 'wipe_down')
        s.text(str(yr), xs[i], 360 if up else 770, 76, t + 0.2, color=[s.th.a, s.th.b, s.th.c, s.th.a][i % 4], anim='slide_up' if up else 'slide_down')
        s.text(lab, xs[i], 430 + 0 if False else (300 if up else 850), 40, t + 0.45, font='medium', color=s.th.fg, anim='fade')
        s.say(t + 0.1, d['n'][i] if i < len(d.get('n', [])) else '')
    s.script = [x for x in s.script if x[1]]; return s

def big_stat(d):
    s = Sc(6.5, d['th']); s.deco(d.get('deco', 1))
    suf = d['suf']; short = len(suf.strip()) <= 1
    unit = d['unit'] if short else (suf.strip() + ' ' + d['unit'])
    s.prog('ring', 960, 500, 820, 820, 0.5, color=s.th.a, grow=2.4)
    s.emoji(d['emo'], 960, 250, 110, 0.8, float={'y': 10, 'speed': 0.8})
    s.text(d['pre'] + '{n}' + (suf if short else ''), 960, 490, 150, 0.9, gradient={'from': s.th.a, 'to': s.th.b}, count={'from': 0, 'to': d['val'], 'start': 1.0, 'dur': 2.2, 'format': d.get('fmt', '{:,}')})
    s.text(unit, 960, 640, 48, 2.2, font='bold', anim='slide_up')
    s.text(d['cap'], 960, 975, 42, 3.2, font='medium', color=s.th.fg2, anim='fade')
    _beats(s, d, [0.6, 2.8, 4.0]); return s

def ping_map(d):
    s = Sc(8.5, d['th']); s.grid('lines', 0.12, 80, color=s.th.c if not s.th.light else INK); s.blob(960, 540, 700, s.th.a, s.th.c, 0.3); s.particles(40, 4)
    s.text(d['head'], 960, 130, 76, 0.3, gradient={'from': s.th.a, 'to': s.th.c})
    pts = d['pts']
    for i in range(len(pts) - 1):
        s.line([[pts[i][1], pts[i][2]], [pts[i + 1][1], pts[i + 1][2]]], 2.0 + i * 1.3 + 0.5, width=4, color=s.th.fg2, anim='wipe_right', adur=0.9)
    for i, (lab, x, y) in enumerate(pts):
        t = 1.6 + i * 1.3
        s.circle(x, y, 22, t, fill=s.th.b)
        for j in range(2):
            s.circle(x, y, 22, t + 0.2 + j * 0.5, fill=WH, fo=0, border=s.th.b, border_w=4, border_opacity=0.8, anim='none', end=t + 1.4 + j * 0.5, keys={'scale': [[t + 0.2 + j * 0.5, 1], [t + 1.4 + j * 0.5, 4.5, 'out']], 'opacity': [[t + 0.2 + j * 0.5, 0.9], [t + 1.4 + j * 0.5, 0, 'linear']]})
        s.chip('📍', lab, x, y - 90, t + 0.3, scale=0.8)
        s.say(t + 0.1, d['n'][i] if i < len(d.get('n', [])) else '')
    s.script = [x for x in s.script if x[1]]; return s

def quote_card(d):
    s = Sc(7.5, d['th']); s.deco(d.get('deco', 1))
    s.text('“', 400, 330, 420, 0.3, color=s.th.a, anim='zoom', opacity=0.55)
    for i, l in enumerate(d['q']):
        s.text(l, 960, 440 + i * 110, 84, 0.9 + i * 0.9, font='bold_italic', anim='slide_up', adur=0.7)
    s.line([[760, 440 + len(d['q']) * 110 + 30], [1160, 440 + len(d['q']) * 110 + 30]], 3.6, width=5, color=s.th.b)
    s.text('— ' + d['who'], 960, 440 + len(d['q']) * 110 + 100, 50, 4.0, font='medium', color=s.th.c, anim='fade')
    s.script = [[0.5, d.get('lead', '')], [1.0, ' '.join(d['q'])], [5.0, d['n'][-1] if d.get('n') else '']]
    s.script = [x for x in s.script if x[1]]; return s

def split_compare(d):
    s = Sc(8.5, d['th']); s.deco(d.get('deco', 0))
    s.text(d['head'], 960, 130, 76, 0.3, gradient={'from': s.th.a, 'to': s.th.b})
    for i, side in enumerate(d['sides']):
        x = 520 if i == 0 else 1400; c = s.th.a if i == 0 else s.th.b; t = 1.0 + i * 1.6
        s.glass(x, 560, 700, 640, t, r=44, anim='slide_right' if i == 0 else 'slide_left', border=c)
        s.emoji(side['emo'], x, 330, 110, t + 0.3)
        s.text(side['name'], x, 450, 62, t + 0.4, font='bold', color=c)
        s.text('{n}' + side.get('suf', ''), x, 610, 150, t + 0.5, gradient={'from': c, 'to': s.th.fg}, count={'from': 0, 'to': side['val'], 'start': t + 0.6, 'dur': 1.6, 'format': side.get('fmt', '{:,}')})
        s.text(side['lab'], x, 740, 40, t + 1.0, font='medium', color=s.th.fg2)
        s.text(side['note'], x, 830, 36, t + 1.5, font='regular', color=s.th.fg)
    s.circle(960, 560, 70, 3.8, fill=s.th.c, anim='pop'); s.text('VS', 960, 560, 56, 3.9, color=INK, anim='pop')
    _beats(s, d, [1.0, 2.6, 4.6, 6.4]); return s

def steps_list(d):
    s = Sc(9, d['th']); s.deco(d.get('deco', 3))
    s.text(d['head'], 960, 130, 80, 0.3, gradient={'from': s.th.a, 'to': s.th.c})
    for i, (emo, txt) in enumerate(d['steps']):
        t = 1.0 + i * 1.7; y = 330 + i * 170
        s.glass(960, y, 1300, 130, t, r=65, anim='slide_right')
        s.circle(400, y, 48, t + 0.15, fill=[s.th.a, s.th.b, s.th.c, s.th.a][i % 4]); s.text(str(i + 1), 400, y, 56, t + 0.25, color=INK if not s.th.light else WH, anim='pop')
        s.emoji(emo, 1450, y, 78, t + 0.4)
        s.text(txt, 930, y, 50, t + 0.3, font='bold', anim='fade')
        if i < len(d.get('n', [])): s.say(t + 0.1, d['n'][i])
    return s

def chart_reveal(d):
    s = Sc(8, d['th']); s.deco(d.get('deco', 2))
    s.text(d['head'], 960, 130, 76, 0.3, gradient={'from': s.th.a, 'to': s.th.b})
    s.glass(700, 600, 1060, 700, 0.8, r=44, anim='zoom')
    s.chart(d['kind'], d['data'], 700, 600, 920, 580, 1.4, labels=d.get('labels'), grow=2.2, center=d.get('center'))
    s.glass(1560, 600, 560, 700, 1.4, r=44, anim='slide_left')
    s.text('{n}' + d.get('suf', ''), 1560, 520, 120, 2.2, gradient={'from': s.th.a, 'to': s.th.b}, count={'from': 0, 'to': d['hi'], 'start': 2.2, 'dur': 1.8, 'format': d.get('fmt', '{:,}')})
    s.text(d['hl'], 1560, 640, 40, 3.0, font='bold')
    s.text(d['hl2'], 1560, 710, 28, 3.4, font='medium', color=s.th.fg2)
    _beats(s, d, [0.6, 2.4, 4.6]); return s

def process_flow(d):
    s = Sc(8.5, d['th']); s.deco(d.get('deco', 0))
    s.text(d['head'], 960, 140, 76, 0.3, gradient={'from': s.th.a, 'to': s.th.c})
    nodes = d['nodes']; n = len(nodes); xs = [300 + i * (1320 / (n - 1)) for i in range(n)]
    for i, (emo, lab) in enumerate(nodes):
        t = 1.0 + i * 1.5
        if i > 0: s.line([[xs[i - 1] + 150, 560], [xs[i] - 150, 560]], t - 0.6, width=6, color=s.th.fg2, anim='wipe_right', adur=0.7)
        s.glass(xs[i], 560, 290, 330, t, r=40, anim='pop', border=[s.th.a, s.th.b, s.th.c, s.th.a][i % 4])
        s.emoji(emo, xs[i], 500, 120, t + 0.25)
        s.text(lab, xs[i], 660, 40, t + 0.4, font='bold')
        s.text('0%d' % (i + 1), xs[i], 350, 44, t + 0.3, font='medium', color=s.th.c)
        if i < len(d.get('n', [])): s.say(t + 0.1, d['n'][i])
    s.text(d['foot'], 960, 900, 46, 1.0 + n * 1.5, font='medium', color=s.th.fg2); return s

def orbit_diagram(d):
    s = Sc(10, d['th']); s.grid('dots', 0.08, 70, color=WH if not s.th.light else INK); s.particles(90, 8); s.blob(960, 540, 560, s.th.a, s.th.b, 0.25)
    cx, cy = 780, 560
    s.text(d['head'], 960, 110, 70, 0.3, gradient={'from': s.th.a, 'to': s.th.c})
    s.circle(cx, cy, 70, 0.6, fill=d.get('core', YL), shadow=0.6, shadow_color=d.get('core', YL), shadow_blur=80, float={'y': 6, 'speed': 0.6})
    import math
    for i, (nm, rad, pr, col, per) in enumerate(d['bodies']):
        t = 1.0 + i * 0.7
        s.circle(cx, cy, rad, t, fill=WH, fo=0, border=s.th.fg2, border_w=2, border_opacity=0.35, anim='fade')
        xs, ys = [], []
        pts = 16
        for k in range(pts + 1):
            ang = math.radians(-90 + 360 * k / pts * (10 / per) + 70 * i)
            xs.append([round(t + 0.2 + (10 - t - 0.2) * k / pts, 2), round(cx + rad * math.cos(ang), 1)])
            ys.append([round(t + 0.2 + (10 - t - 0.2) * k / pts, 2), round(cy + rad * math.sin(ang), 1)])
        s.circle(cx, cy, pr, t + 0.2, fill=col, keys={'x': xs, 'y': ys})
        s.chip(d['emo'][i], nm, 1500, 330 + i * 120, t + 0.4, scale=0.8, anim='slide_left')
        if i < len(d.get('n', [])): s.say(t + 0.2, d['n'][i])
    return s

def chapter_opener(d):
    s = Sc(6.5, d['th']); s.deco(d.get('deco', 3))
    s.text('CHAPTER', 640, 330, 52, 0.4, font='medium', color=s.th.c, anim='fade')
    s.text(d['num'], 640, 560, 420, 0.7, gradient={'from': s.th.a, 'to': s.th.b}, anim='zoom', adur=0.8)
    s.line([[300, 760], [980, 760]], 1.6, width=6, color=s.th.fg2)
    s.text(d['t1'], 640, 850, 80, 1.9, anim='slide_up'); s.text(d['t2'], 640, 950, 80, 2.2, anim='slide_up', color=s.th.fg2)
    s.img(d['img'], 1460, 540, 800, 900, 0.9, r=44, anim='slide_left', zoom=(1.0, 1.25), pan=(-0.3, 0.5))
    _beats(s, d, [0.6, 2.0, 3.8]); return s

def fact_fan(d):
    s = Sc(8, d['th']); s.deco(d.get('deco', 1))
    s.text(d['head'], 960, 120, 76, 0.3, gradient={'from': s.th.a, 'to': s.th.b})
    for i, (title, big, sub, emo, cnt) in enumerate(d['cards']):
        t = 1.0 + i * 1.5
        s.card(title, big, 460 + i * 500, 600 + (0 if i == 1 else 20), t, emoji=emo, sub='', scale=1.6, yaw=[-14, 0, 14][i], roll=[-4, 0, 4][i], count=cnt, head=[s.th.a, s.th.b, s.th.c][i], float={'y': 8, 'speed': 0.8, 'phase': i})
        if i < len(d.get('n', [])): s.say(t + 0.1, d['n'][i])
    return s

def year_ticker(d):
    s = Sc(7, d['th']); s.deco(d.get('deco', 2))
    s.text(d['pre'], 960, 250, 56, 0.4, font='medium', color=s.th.c, anim='fade')
    s.text('{n}', 960, 520, 360, 0.7, gradient={'from': s.th.a, 'to': s.th.b}, count={'from': d['y0'], 'to': d['y1'], 'start': 0.9, 'dur': 3.0, 'format': '{:d}'})
    s.prog('bar', 960, 780, 1000, 22, 0.9, color=s.th.a, grow=3.0)
    s.text(d['y0label'], 460, 850, 38, 1.0, font='medium', color=s.th.fg2); s.text(d['y1label'], 1460, 850, 38, 1.0, font='medium', color=s.th.fg2)
    s.text(d['post'], 960, 940, 54, 4.4, font='bold', anim='slide_up')
    _beats(s, d, [0.8, 2.6, 4.6]); return s

def icon_grid(d):
    s = Sc(8, d['th']); s.deco(d.get('deco', 0))
    s.text(d['head'], 960, 130, 76, 0.3, gradient={'from': s.th.a, 'to': s.th.c})
    for i, (emo, lab) in enumerate(d['items']):
        x = [420, 960, 1500][i % 3]; y = 430 if i < 3 else 780; t = 0.9 + i * 0.7
        s.glass(x, y, 440, 290, t, r=40, anim='pop')
        s.emoji(emo, x, y - 40, 110, t + 0.2); s.text(lab, x, y + 80, 42, t + 0.35, font='bold')
    _beats(s, d, [0.9, 2.6, 5.0]); return s

def glitch_transition(d):
    s = Sc(7.5, d['th']); s.deco(d.get('deco', 1)); sw = 3.4
    s.img(d['img'], 960, 540, 1920, 1080, 0, r=0, anim='fade', end=sw + 0.05, zoom=(1, 1.2))
    s.rr(960, 540, 1920, 1080, 0, r=0, fill=[0, 0, 0], fo=0.5, anim='none', end=sw + 0.05)
    s.text(d['a1'], 960, 480, 130, 0.5, end=sw); s.text(d['a2'], 960, 640, 60, 1.4, font='medium', color=s.th.c, end=sw)
    s.trans('glitch', 2.9, color=s.th.a, dur=1.0)
    s.text(d['b1'], 960, 400, 70, sw + 0.3, font='medium', color=s.th.c)
    s.text('{n}' + d['suf'], 960, 600, 260, sw + 0.5, gradient={'from': s.th.a, 'to': s.th.b}, count={'from': 0, 'to': d['val'], 'start': sw + 0.7, 'dur': 1.6, 'format': d.get('fmt', '{:,}')})
    s.text(d['b2'], 960, 810, 50, sw + 1.6, font='bold')
    _beats(s, d, [0.6, 2.2, 4.0, 5.4]); return s

def outro_logo(d):
    s = Sc(6.5, d['th']); s.deco(d.get('deco', 1))
    for j in range(3):
        s.circle(960, 450, 160, 0.4 + j * 0.35, fill=WH, fo=0, border=s.th.a, border_w=4, border_opacity=0.7, anim='none', end=2.2 + j * 0.35, keys={'scale': [[0.4 + j * 0.35, 0.6], [2.2 + j * 0.35, 3.2, 'out']], 'opacity': [[0.4 + j * 0.35, 0.8], [2.2 + j * 0.35, 0, 'linear']]})
    s.img('', 960, 450, 300, 300, 0.7, r=70, anim='pop', raw='assets/sample_logo.png', zoom=(1, 1.02), pan=(0, 0), float={'y': 8, 'speed': 0.9})
    s.text(d['name'], 960, 680, 100, 1.5, gradient={'from': s.th.a, 'to': s.th.b})
    s.text(d['tag'], 960, 790, 46, 2.2, font='medium', color=s.th.fg2, anim='fade')
    s.chip('▶', d['cta'], 960, 910, 3.0, scale=0.95)
    _beats(s, d, [0.8, 2.4, 3.4]); return s

def kinetic_statement(d):
    s = Sc(6.5, d['th']); s.deco(d.get('deco', 3))
    ys = [330, 500, 670]
    for i, (w, hl) in enumerate(d['lines']):
        t = 0.5 + i * 1.1
        if hl: s.text(w, 960, ys[i], 150, t, anim='zoom', gradient={'from': s.th.a, 'to': s.th.b})
        else: s.text(w, 960, ys[i], 130 if i < 2 else 110, t, anim='slide_up', adur=0.6)
    s.circle(260, 860, 50, 1.4, fill=s.th.a, float={'y': 14, 'speed': 1.0}); s.rr(1640, 880, 220, 54, 1.8, fill=s.th.b, fo=0.9, float={'y': 10, 'speed': 1.2}); s.circle(1500, 230, 28, 2.0, fill=s.th.c, float={'y': 12, 'speed': 1.3})
    s.text(d['foot'], 960, 900, 46, 3.4, font='medium', color=s.th.fg2, anim='fade')
    _beats(s, d, [0.5, 1.6, 2.7, 3.8]); return s

DOC = {k: v for k, v in dict(title_hero=title_hero, archival_photo=archival_photo, timeline=timeline, big_stat=big_stat, ping_map=ping_map, quote_card=quote_card, split_compare=split_compare,
          steps_list=steps_list, chart_reveal=chart_reveal, process_flow=process_flow, orbit_diagram=orbit_diagram, chapter_opener=chapter_opener, fact_fan=fact_fan, year_ticker=year_ticker,
          icon_grid=icon_grid, glitch_transition=glitch_transition, outro_logo=outro_logo, kinetic_statement=kinetic_statement).items()}
