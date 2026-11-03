"""SaaS / UI motion archetypes."""
from libgen.kit import *
from libgen.arch_doc import _beats

def device_showcase(d):
    s = Sc(7.5, d['th']); s.deco(d.get('deco', 0))
    s.text(d['t1'], 960, 130, 84, 0.3, gradient={'from': s.th.a, 'to': s.th.b})
    s.text(d['sub'], 960, 230, 40, 0.9, font='medium', color=s.th.fg2, anim='fade')
    kind = d['kind']; w = {'laptop': 900, 'browser': 940, 'phone': 360}[kind]
    s.dev(kind, 960, 640 if kind != 'phone' else 640, w, 0.9)
    chips = d['chips']; pos = [(290, 450), (1630, 520), (300, 800), (1620, 840)]
    for i, (e, l) in enumerate(chips[:4]):
        s.chip(e, l, pos[i][0], pos[i][1], 2.2 + i * 0.6, scale=0.55, float={'y': 12, 'speed': 0.8, 'phase': i})
    _beats(s, d, [0.5, 1.8, 3.8, 5.4]); return s

def settings_toggles(d):
    s = Sc(7.5, d['th']); s.deco(d.get('deco', 0))
    s.text(d['head'], 960, 130, 80, 0.3, gradient={'from': s.th.a, 'to': s.th.c})
    s.glass(960, 590, 1100, 720, 0.7, r=48)
    for i, (emo, lab) in enumerate(d['rows']):
        y = 340 + i * 160; t = 1.2 + i * 0.9
        s.rr(960, y, 960, 120, t, r=30, fill=WH, fo=0.12 if not s.th.light else 0.55, anim='slide_right')
        s.emoji(emo, 540, y, 64, t + 0.1); s.text(lab, 700, y, 44, t + 0.1, font='bold', anchor='l', anim='fade')
        on = t + 0.8
        s.rr(1300, y, 130, 64, t + 0.1, r=32, fill=[0.55, 0.57, 0.65], fo=0.9, anim='fade')
        s.rr(1300, y, 130, 64, on, r=32, fill=GR, fo=1.0, anim='fade', shadow=0.4, shadow_color=GR)
        s.circle(1270, y, 24, t + 0.1, fill=WH, anim='fade', keys={'x': [[on, 1270], [on + 0.35, 1330, 'back']]})
        if i < len(d.get('n', [])): s.say(on, d['n'][i])
    return s

def toast_notifications(d):
    s = Sc(8, d['th']); s.deco(d.get('deco', 1))
    s.text(d['head'], 500, 500, 72, 0.4, anim='slide_up', gradient={'from': s.th.a, 'to': s.th.b}, anchor='c')
    s.text(d['sub'], 500, 600, 38, 1.0, font='medium', color=s.th.fg2)
    for i, (emo, t1, t2) in enumerate(d['toasts']):
        t = 1.2 + i * 1.3; y = 260 + i * 170
        s.glass(1340, y, 780, 140, t, r=36, anim='slide_left', border=[s.th.a, s.th.b, s.th.c, s.th.a][i % 4])
        s.circle(1060, y, 44, t + 0.1, fill=[s.th.a, s.th.b, s.th.c, s.th.a][i % 4]); s.emoji(emo, 1060, y, 52, t + 0.2)
        s.text(t1, 1130, y - 22, 40, t + 0.2, font='bold', anchor='l', anim='fade'); s.text(t2, 1130, y + 28, 30, t + 0.35, font='medium', color=s.th.fg2, anchor='l', anim='fade')
        if i < len(d.get('n', [])): s.say(t + 0.1, d['n'][i])
    return s

def kpi_dashboard(d):
    s = Sc(8.5, d['th']); s.deco(d.get('deco', 2))
    s.text(d['head'], 960, 110, 72, 0.3, gradient={'from': s.th.a, 'to': s.th.b})
    for i, (title, big, sub, emo, cnt) in enumerate(d['kpis']):
        t = 0.9 + i * 0.6
        s.card(title, big, 410 + i * 550, 385, t, emoji=emo, sub='', scale=1.1, count=cnt, head=[s.th.a, s.th.b, s.th.c][i], float={'y': 6, 'speed': 0.8, 'phase': i})
    s.glass(960, 790, 1620, 380, 2.4, r=40, anim='rise')
    s.chart('line', d['series'], 840, 790, 1100, 280, 3.0, labels=d['labels'], grow=2.0)
    s.prog('ring', 1560, 790, 220, 220, 3.4, color=s.th.c, label='{p}%', grow=1.6)
    _beats(s, d, [0.9, 2.5, 3.2, 5.0]); return s

def ai_prompt_bar(d):
    s = Sc(9, d['th']); s.deco(d.get('deco', 1))
    s.text(d['head'], 960, 200, 90, 0.3, gradient={'from': s.th.a, 'to': s.th.b})
    s.glass(960, 460, 1400, 140, 0.8, r=70, anim='zoom', border=s.th.a)
    s.circle(330, 460, 44, 1.0, fill=s.th.a); s.icon('mic', 330, 460, 44, 1.1, color=WH)
    s.text(d['prompt'], 960, 460, 44, 1.6, font='medium', anim='none', reveal={'mode': 'chars'})
    s.circle(1500, 460, 44, 4.0, fill=s.th.b); s.icon('arrow_up', 1500, 460, 44, 4.1, color=WH)
    s.circle(1500, 460, 44, 4.2, fill=WH, fo=0, border=s.th.b, border_w=4, border_opacity=0.8, anim='none', end=5.0, keys={'scale': [[4.2, 1], [5.0, 2.6, 'out']], 'opacity': [[4.2, 0.9], [5.0, 0, 'linear']]})
    for i, (emo, lab) in enumerate(d['results']):
        t = 4.8 + i * 0.6
        s.glass(560 + i * 400, 760, 360, 260, t, r=36, anim='slide_up')
        s.emoji(emo, 560 + i * 400, 710, 90, t + 0.2); s.text(lab, 560 + i * 400, 830, 38, t + 0.3, font='bold')
    _beats(s, d, [0.8, 1.8, 4.2, 5.4]); return s

def pricing_cards(d):
    s = Sc(8.5, d['th']); s.deco(d.get('deco', 0))
    s.text(d['head'], 960, 105, 76, 0.3, gradient={'from': s.th.a, 'to': s.th.b})
    for i, (plan, price, perks) in enumerate(d['plans']):
        x = 500 + i * 460; pop = (i == 1); t = 0.9 + i * 0.6
        s.glass(x, 650 - (20 if pop else 0), 420, 700 + (40 if pop else 0), t, r=44, anim='slide_up')
        s.text(plan, x, 350, 48, t + 0.3, font='bold', color=s.th.c)
        s.text('$' + '{n}', x, 470, 130, t + 0.4, gradient={'from': s.th.a, 'to': s.th.b}, count={'from': 0, 'to': price, 'start': t + 0.5, 'dur': 1.2, 'format': '{:d}'})
        for j, pk in enumerate(perks):
            s.emoji('✅', x - 165, 610 + j * 85, 34, t + 0.9 + j * 0.25); s.text(pk, x - 125, 610 + j * 85, 28, t + 0.9 + j * 0.25, font='medium', anchor='l', anim='fade')
        if pop: s.chip('⭐', 'Most popular', x, 262, 3.0, scale=0.7)
    _beats(s, d, [0.9, 2.2, 3.2, 5.5]); return s

def loading_success(d):
    s = Sc(6.5, d['th']); s.deco(d.get('deco', 1))
    s.prog('ring', 960, 470, 360, 360, 0.5, color=s.th.a, label='{p}%', grow=2.8, end=3.6)
    s.text(d['load'], 960, 740, 56, 0.8, font='bold', end=3.5, color=s.th.fg2)
    s.circle(960, 470, 170, 3.4, fill=GR, anim='pop', shadow=0.6, shadow_color=GR, shadow_blur=80); s.icon('check', 960, 470, 150, 3.7, color=WH)
    for j in range(2): s.circle(960, 470, 170, 3.5 + j * 0.3, fill=WH, fo=0, border=GR, border_w=5, border_opacity=0.8, anim='none', end=4.8 + j * 0.3, keys={'scale': [[3.5 + j * 0.3, 1], [4.8 + j * 0.3, 2.4, 'out']], 'opacity': [[3.5 + j * 0.3, 0.9], [4.8 + j * 0.3, 0, 'linear']]})
    s.text(d['done'], 960, 800, 80, 3.8, gradient={'from': GR, 'to': s.th.c}); s.text(d['sub'], 960, 905, 42, 4.3, font='medium', color=s.th.fg2)
    _beats(s, d, [0.6, 3.5, 4.4]); return s

def onboarding_steps(d):
    s = Sc(9, d['th']); s.deco(d.get('deco', 0))
    s.text(d['head'], 960, 120, 76, 0.3, gradient={'from': s.th.a, 'to': s.th.c})
    steps = d['steps']; n = len(steps); xs = [360 + i * (1200 / (n - 1)) for i in range(n)]
    s.line([[xs[0], 260], [xs[-1], 260]], 0.7, width=6, color=s.th.fg2, anim='wipe_right', adur=1.0)
    s.prog('bar', 960, 260, 1200, 12, 1.0, color=s.th.a, grow=n * 1.8 - 0.5)
    for i, (emo, lab, body) in enumerate(steps):
        t = 1.0 + i * 1.9; e = t + 1.9 if i < n - 1 else 9
        s.circle(xs[i], 260, 34, t, fill=[s.th.a, s.th.b, s.th.c, GR][i % 4]); s.text(str(i + 1), xs[i], 260, 36, t + 0.1, color=WH if True else INK, anim='pop')
        s.text(lab, xs[i], 340, 34, t + 0.15, font='bold', anim='fade')
        s.glass(960, 700, 1100, 520, t + 0.2, r=48, anim='zoom', end=e)
        s.emoji(emo, 960, 580, 150, t + 0.5, end=e); s.text(body, 960, 790, 52, t + 0.7, font='bold', end=e)
        if i < len(d.get('n', [])): s.say(t + 0.2, d['n'][i])
    return s

def command_palette(d):
    s = Sc(7.5, d['th']); s.deco(d.get('deco', 1))
    s.glass(960, 540, 1150, 760, 0.4, r=44, anim='zoom', border=s.th.a)
    s.text('Ctrl K', 430, 280, 36, 0.8, font='bold', color=s.th.c, anchor='l')
    s.text(d['q'], 960, 280, 50, 1.0, font='medium', anim='none', reveal={'mode': 'chars'})
    for i, (emo, lab, key) in enumerate(d['items']):
        t = 2.6 + i * 0.6; y = 410 + i * 130
        s.rr(960, y, 1050, 100, t, r=26, fill=s.th.a if i == 1 else WH, fo=0.35 if i == 1 else 0.1, anim='slide_up')
        s.emoji(emo, 470, y, 56, t + 0.1); s.text(lab, 560, y, 40, t + 0.1, font='bold', anchor='l', anim='fade'); s.chip('⚡', key, 1380, y, t + 0.2, scale=0.55)
    s.circle(960, 540, 100, 5.0, fill=WH, fo=0, anim='none', end=5.1)
    _beats(s, d, [0.6, 2.4, 4.0]); return s

def chat_bubbles(d):
    s = Sc(8, d['th']); s.deco(d.get('deco', 1))
    s.text(d['head'], 960, 110, 72, 0.3, gradient={'from': s.th.a, 'to': s.th.b})
    for i, (me, txt, emo) in enumerate(d['msgs']):
        t = 1.0 + i * 1.5; y = 290 + i * 190; x = 1230 if me else 690
        s.rr(x, y, 780, 140, t, r=60, fill=s.th.a if me else WH, fo=0.9 if me else (0.16 if not s.th.light else 0.8), anim='slide_left' if me else 'slide_right', shadow=0.3)
        s.emoji(emo, x - 330 if not me else x + 330, y, 56, t + 0.2)
        s.text(txt, x, y, 38, t + 0.2, font='bold' if me else 'medium', color=WH if me else s.th.fg, anim='fade')
        if i < len(d.get('n', [])): s.say(t + 0.1, d['n'][i])
    return s

def feature_trio(d):
    s = Sc(8, d['th']); s.deco(d.get('deco', 0))
    s.text(d['head'], 960, 130, 84, 0.3, gradient={'from': s.th.a, 'to': s.th.b})
    for i, (emo, t1, t2) in enumerate(d['f']):
        x = 400 + i * 560; t = 0.9 + i * 0.8; c = [s.th.a, s.th.b, s.th.c][i]
        s.glass(x, 600, 480, 640, t, r=48, anim='slide_up')
        s.circle(x, 400, 90, t + 0.2, fill=c, shadow=0.5, shadow_color=c, shadow_blur=50); s.emoji(emo, x, 400, 90, t + 0.35)
        s.text(t1, x, 580, 52, t + 0.5, font='bold'); s.text(t2, x, 680, 32, t + 0.7, font='medium', color=s.th.fg2)
        s.rr(x, 800, 300, 18, t + 0.9, r=9, fill=c, fo=0.9, anim='wipe_right')
        if i < len(d.get('n', [])): s.say(t + 0.1, d['n'][i])
    return s

SAAS = dict(device_showcase=device_showcase, settings_toggles=settings_toggles, toast_notifications=toast_notifications, kpi_dashboard=kpi_dashboard,
            ai_prompt_bar=ai_prompt_bar, pricing_cards=pricing_cards, loading_success=loading_success, onboarding_steps=onboarding_steps,
            command_palette=command_palette, chat_bubbles=chat_bubbles, feature_trio=feature_trio)
