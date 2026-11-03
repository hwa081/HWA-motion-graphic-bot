#!/usr/bin/env python3
"""Reference recipe: the 14.4 s UI-style intro (typing prompt, 3D cards, chips, gradient text, glass panel).

Hand-written in Python on top of mgl.engine. Run:   python recipes/reference_intro.py out/reference.mp4
Use it as a pattern for 'code mode' scenes; for normal use prefer JSON specs (see LIBRARY.md).
"""
import os, sys, math, time, subprocess
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import numpy as np, cv2
from mgl import engine as E
from mgl.engine import *   # noqa: F401,F403  (drawing helpers, W, H, fonts, easing)

FPS = 30
DUR = 14.433

def lightness(t):
    if t < 7.7: return 0.0
    if t < 8.0: return sm(seg(t, 7.7, 8.0))
    if t < 9.35: return 1.0
    if t < 9.6: return 1 - sm(seg(t, 9.35, 9.6))
    if t < 10.7: return 0.0
    if t < 11.1: return sm(seg(t, 10.7, 11.1))
    if t < 13.2: return 1.0
    if t < 13.5: return 1 - sm(seg(t, 13.2, 13.5))
    return 0.0

def background(t):
    L = lightness(t)
    if L <= 0.002: return E.blobfield('dark_aurora', t)
    if L >= 0.998: return E.blobfield('light_pastel', t)
    return E.blobfield('dark_aurora', t) * (1 - L) + E.blobfield('light_pastel', t) * L

# ---------------------------------------------------------------- camera
CAM_KEYS = None
def cam(t):
    keys = CAM_KEYS
    if t <= keys[0][0]: return keys[0][1:]
    for i in range(len(keys) - 1):
        a, b = keys[i], keys[i + 1]
        if a[0] <= t <= b[0]:
            u = sm((t - a[0]) / (b[0] - a[0]))
            return tuple(lerp(x, y, u) for x, y in zip(a[1:], b[1:]))
    return keys[-1][1:]

SENT = ['Can', 'you', 'help', 'me', 'plan', 'my', 'day?']
SENT_T = [1.40, 1.75, 2.10, 2.34, 2.64, 2.84, 3.00]
FULL = ' '.join(SENT)
TS = 54
TXT_X0 = 330.0
PILL = (960.0, 860.0, 1400.0, 150.0)
SEND = (1768.0, 860.0, 52.0)

def init_cam():
    global CAM_KEYS
    wf = text_w(FULL, F_BI, TS)
    cx0 = TXT_X0 + wf / 2
    CAM_KEYS = [(0, 1.55, cx0, 860), (3.3, 1.55, cx0, 860), (4.25, 0.95, 960, 735), (5.0, 1.05, 960, 700),
                (5.6, 1.55, 900, 640), (6.15, 1.85, 1250, 735), (6.7, 1.08, 960, 700), (7.4, 1.0, 960, 690),
                (8.1, 0.92, 960, 690), (20, 0.92, 960, 690)]

# ---------------------------------------------------------------- scenes
CARDS = [  # kind, world cx, cy, yaw, roll, spawn
    ('image', 600, 585, -21, -1.5, 4.35),
    ('note', 835, 555, -7, 0.0, 4.47),
    ('event', 1085, 540, 5, 0.0, 4.59),
    ('voice', 1345, 585, 21, 1.5, 5.10)]

def ui_scene(f, t):
    z, ccx, ccy = cam(t)
    S = lambda x, y: ((x - ccx) * z + W / 2, (y - ccy) * z + H / 2)
    # whole-UI fade out into the light scene
    ui_op = 1 - sm(seg(t, 7.45, 7.95))
    if ui_op <= 0: return
    # cards (behind pill)
    for kind, wx, wy, yaw, roll, ts in CARDS:
        u = seg(t, ts, ts + 0.75)
        if u <= 0: continue
        sc = lerp(0.35, 1.0, eob(u, 1.4))
        rise = (1 - eob(u, 1.2)) * 190
        sx, sy = S(wx, wy + rise)
        num = 0
        if kind == 'event':
            num = int(round(lerp(1, 12, sm(seg(t, 4.85, 5.55)))))
        op = sm(seg(t, ts, ts + 0.22)) * ui_op
        draw_card(f, kind, num, sx, sy, sc * z, yaw * (1 - 0.2 * (1 - u)), roll, op)
    # pill
    pu = sm(seg(t, 3.15, 3.9))
    cx, cy = S(PILL[0], PILL[1])
    if pu > 0:
        w, h = PILL[2] * z, PILL[3] * z
        draw_rr(f, cx, cy, w, h, h / 2, fill=(0.03, 0.04, 0.05), fa=0.34, fill2=(0.0, 0.0, 0.0), border=(1, 1, 1), ba=0.30,
                bw=max(2, 2 * z), op=pu * ui_op, shadow=0.0)
        draw_rr(f, cx, cy, w, h, h / 2, fill=(1, 1, 1), fa=0.06, op=pu * ui_op)
    # typed text
    scroll = -150 * sm(seg(t, 7.1, 7.7))
    for i, wd in enumerate(SENT):
        ts = SENT_T[i]
        u = seg(t, ts, ts + 0.28)
        if u <= 0: continue
        pre = ' '.join(SENT[:i]) + (' ' if i else '')
        wx = TXT_X0 + text_w(pre, F_BI, TS) + scroll
        sx, sy = S(wx, 860)
        col = lerpc((0.55, 0.57, 0.58), (1, 1, 1), sm(seg(t, ts + 0.1, ts + 0.5))) if wd == 'day?' else (1, 1, 1)
        draw_text(f, wd, F_BI, TS * z, sx, sy, 'l', col, op=sm(u) * ui_op, blur=(1 - u) * 6 * z)
    # right-hand controls
    cu = sm(seg(t, 5.6, 6.2))
    if cu > 0:
        px, py = S(1470, 860); circle_plus(f, px, py, 17 * z, 0.85 * cu * ui_op)
        mx, my = S(1555, 860); mic_icon(f, mx, my, 34 * z, (1, 1, 1), max(2, 2.4 * z), 0.55 * cu * ui_op)
        sx, sy = S(SEND[0], SEND[1])
        press = sm(seg(t, 6.85, 7.15))
        r = SEND[2] * z * (1 + 0.12 * press)
        su = eob(seg(t, 5.8, 6.4), 1.5)
        circle(f, (sx, sy), r * su, (1, 1, 1), max(2, 3.2 * z), ui_op * cu)
        ang = math.radians(-45 * press)
        ln = 22 * z * su
        c, s_ = math.cos(ang), math.sin(ang)
        def rot(x, y): return (sx + x * c - y * s_, sy + x * s_ + y * c)
        poly(f, [rot(0, ln), rot(0, -ln)], (1, 1, 1), max(2, 3.4 * z), False, ui_op * cu)
        poly(f, [rot(-0.55 * ln, -0.1 * ln), rot(0, -ln), rot(0.55 * ln, -0.1 * ln)], (1, 1, 1), max(2, 3.4 * z), False, ui_op * cu)

def circle_plus(f, x, y, r, op):
    aaline(f, (x - r, y), (x + r, y), (1, 1, 1), max(2, r * 0.16), op)
    aaline(f, (x, y - r), (x, y + r), (1, 1, 1), max(2, r * 0.16), op)

def hey_scene(f, t):
    if t > 1.5: return
    u = seg(t, 0.0, 0.55)
    sc = lerp(1.22, 1.0, eo3(u)) * lerp(1, 0.55, sm(seg(t, 0.75, 1.3)))
    op = sm(seg(t, 0.0, 0.5)) * (1 - sm(seg(t, 1.12, 1.42)))
    blur = (1 - eo3(u)) * 16 + sm(seg(t, 1.0, 1.4)) * 6
    draw_text(f, 'Hey', F_BI, 150 * sc, 960, 540, 'c', (1, 1, 1), op=op, blur=blur)

# ---- light scene: task card
def task_scene(f, t):
    a_in = sm(seg(t, 7.95, 8.3))
    a_out = 1 - sm(seg(t, 9.28, 9.55))
    op = a_in * a_out
    g_out = 1 - sm(seg(t, 9.85, 10.1))
    if op <= 0.003 and g_out <= 0.003: return
    # label
    draw_text(f, "here\u2019s what I have to do", F_I, 36, 960, 268, 'c', (0.2, 0.2, 0.23), op=sm(seg(t, 8.0, 8.25)) * a_out,
              blur=(1 - sm(seg(t, 8.0, 8.25))) * 6)
    u = eob(seg(t, 8.0, 8.55), 1.5)
    sc = lerp(0.55, 1.0, u) * lerp(1.0, 0.88, sm(seg(t, 9.28, 9.55)))
    cx, cy = 960, 585
    w, h = 340 * sc, 330 * sc
    # peeking sheets behind
    rise = sm(seg(t, 8.35, 9.2))
    sheets = [((0.55, 0.78, 0.80), -70, -190, 105, 120, -9), ((0.84, 0.60, 0.82), -10, -200, 105, 118, 5),
              ((0.50, 0.62, 0.92), 55, -188, 100, 112, 11)]
    for col, ox, oy, sw, sh, rot in (sheets if op > 0.003 else []):
        yy = cy + (oy * 0.62 + (1 - rise) * 55 - rise * 8) * sc
        draw_rr(f, cx + ox * sc, yy, sw * sc, sh * sc, 10 * sc, fill=col, fa=1.0, rot=rot, op=op, shadow=0.15, sh_blur=8)
        for i in range(3):
            ln = yy - sh * sc * 0.25 + i * 20 * sc
            aaline(f, (cx + ox * sc - sw * sc * 0.32, ln), (cx + ox * sc + sw * sc * 0.28, ln), (1, 1, 1), max(1, 2 * sc), 0.65 * op)
    # gold note rising
    gy = cy - (120 + rise * 78) * sc
    fly = sm(seg(t, 9.15, 9.55))
    gy = lerp(gy, 120, fly); gs = max(sc, 0.9) * lerp(1.0, 0.55, fly)
    draw_rr(f, cx + 8 * sc, gy, 150 * gs, 175 * gs, 14 * gs, fill=(0.90, 0.76, 0.36), fa=1.0, fill2=(0.62, 0.50, 0.20), rot=-5, op=a_in * g_out, shadow=0.25, sh_blur=10 * gs)
    for i in range(6):
        ln = gy - 70 * gs + i * 22 * gs
        aaline(f, (cx + 8 * gs - 50 * gs, ln), (cx + 8 * gs + 52 * gs, ln + 2 * gs), (0.98, 0.9, 0.62), max(1, 3 * gs), 0.8 * a_in * g_out)
    if op <= 0.003: return
    # folder body
    draw_rr(f, cx, cy, w, h, 34 * sc, fill=(0.33, 0.78, 0.22), fa=1.0, op=op)           # green back
    draw_rr(f, cx, cy + 8 * sc, w - 6 * sc, h - 14 * sc, 30 * sc, fill=(0.13, 0.14, 0.16), fa=1.0, fill2=(0.55, 0.55, 0.57), op=op,
            shadow=0.35, sh_dy=18, sh_blur=22 * sc)
    lx = cx - w / 2 + 34 * sc
    draw_text(f, 'Invalid works', F_BI, 30 * sc, lx, cy - h / 2 + 118 * sc, 'l', (1, 1, 1), op=op)
    draw_text(f, 'task and assignment', F_I, 16 * sc, lx, cy - h / 2 + 156 * sc, 'l', (0.72, 0.72, 0.74), op=op)
    draw_text(f, '27 Feb', F_I, 14 * sc, lx, cy + h / 2 - 40 * sc, 'l', (0.8, 0.8, 0.82), op=op * 0.8)
    for i in range(3):
        circle(f, (cx + w / 2 - 70 * sc + i * 14 * sc, cy - h / 2 + 62 * sc), 3.2 * sc, (1, 1, 1), -1, 0.8 * op)
    # orbiting dots
    d_op = sm(seg(t, 8.0, 8.25)) * (1 - sm(seg(t, 8.5, 8.9)))
    if d_op > 0:
        circle(f, (770 - 20 * seg(t, 8, 8.9), 470 + 25 * seg(t, 8, 8.9)), 9, (0.55, 0.28, 0.72), -1, d_op)
        circle(f, (1370 + 25 * seg(t, 8, 8.9), 492 - 20 * seg(t, 8, 8.9)), 7, (0.28, 0.45, 0.92), -1, d_op)

# ---- chips
CHIPS = [('\U0001F310', 'website', 134, -184, 0.0, 9.66), ('\U0001F3CB', 'gym', -134, 0, -7.0, 9.73),
         ('\U0001F3AC', 'Video', 250, 32, -5.0, 9.80), ('\U0001F3C3', 'running', -173, 151, 7.0, 9.87)]
CHIP_C = (1018.0, 600.0)

def draw_chip(f, emo, label, cx, cy, s, rot, light, op):
    w, h = 400 * s, 150 * s
    if light > 0.01:
        draw_rr(f, cx, cy, w, h, h / 2, fill=(1, 1, 1), fa=0.97 * light, rot=rot, op=op, shadow=0.20 * light, sh_dy=10 * s, sh_blur=14 * s)
    if light < 0.99:
        draw_rr(f, cx, cy, w, h, h / 2, fill=(1, 1, 1), fa=0.14 * (1 - light), border=(1, 1, 1), ba=0.35 * (1 - light), bw=max(1.5, 2 * s), rot=rot, op=op)
    cr, sr = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    ex, ey = -w * 0.27, 0
    draw_emoji(f, emo, cx + ex * cr - ey * sr, cy + ex * sr + ey * cr, 96 * s, op)
    tx, ty = w * 0.06, 0
    col = lerpc((1, 1, 1), (0.05, 0.05, 0.06), light)
    draw_text(f, label, F_BI, 62 * s, cx + tx * cr - ty * sr, cy + tx * sr + ty * cr + 3 * s, 'l', col, op=op, rot=-rot)

def chips_scene(f, t):
    if t < 9.7 or t > 11.6: return
    light = lightness(t)
    out = 1 - sm(seg(t, 11.12, 11.38))
    g = sm(seg(t, 9.85, 11.0))
    for emo, label, ox, oy, rot, ts in CHIPS:
        u = eob(seg(t, ts, ts + 0.55), 1.2)
        if u <= 0: continue
        s = lerp(0.40, 1.0, g) * lerp(0.5, 1.0, u)
        tx, ty = CHIP_C[0] + ox * lerp(0.55, 1.0, g), CHIP_C[1] + oy * lerp(0.55, 1.0, g)
        sx, sy = 960, 90
        cx, cy = lerp(sx, tx, u), lerp(sy, ty, u)
        wob = math.sin(t * 2.1 + ox) * 3 * (1 - g)
        draw_chip(f, emo, label, cx, cy + wob, s, rot * u, light, sm(seg(t, ts, ts + 0.2)) * out)

# ---- big gradient text
CKEYS = [  # t, left colour, right colour
    (11.30, (0.52, 0.38, 0.24), (0.44, 0.33, 0.20)),
    (11.90, (0.55, 0.46, 0.22), (0.42, 0.31, 0.19)),
    (12.05, (0.16, 0.62, 0.20), (0.15, 0.45, 0.86)),
    (12.30, (0.40, 0.55, 0.55), (0.60, 0.30, 0.55)),
    (12.55, (0.92, 0.26, 0.52), (0.30, 0.07, 0.11)),
    (13.00, (0.58, 0.52, 0.20), (0.27, 0.16, 0.20)),
    (13.60, (0.58, 0.52, 0.20), (0.27, 0.16, 0.20))]
def ckey(t):
    if t <= CKEYS[0][0]: return CKEYS[0][1], CKEYS[0][2]
    for i in range(len(CKEYS) - 1):
        a, b = CKEYS[i], CKEYS[i + 1]
        if a[0] <= t <= b[0]:
            u = sm((t - a[0]) / (b[0] - a[0]))
            return lerpc(a[1], b[1], u), lerpc(a[2], b[2], u)
    return CKEYS[-1][1], CKEYS[-1][2]

def sched_scene(f, t):
    if t < 11.3 or t > 13.5: return
    op = sm(seg(t, 11.32, 11.5)) * (1 - sm(seg(t, 13.15, 13.42)))
    base = 'Organise your schedule'
    dots = ' ...'
    k = sm(seg(t, 11.55, 12.0))
    size = lerp(100, 190, k) + 62 * sm(seg(t, 12.0, 13.2))
    show_dots = t > 11.75
    txt = base + (dots if show_dots else '')
    wfull = text_w(txt, F_BI, size)
    xend = lerp(960 + text_w(base, F_BI, 100) / 2, 1500, k) + 190 * sm(seg(t, 12.0, 13.2))
    if not show_dots: xend = 960 + text_w(base, F_BI, size) / 2
    x0 = xend - wfull
    lc, rc = ckey(t)
    lc, rc = np.array(lc, np.float32), np.array(rc, np.float32)
    def grad(gx):
        u = np.clip((gx - 0.0) / (W * 0.85), 0, 1)[:, None].astype(np.float32)
        return lc * (1 - u) + rc * u
    sc_blur = (1 - sm(seg(t, 11.32, 11.5))) * 10 + sm(seg(t, 13.15, 13.42)) * 14
    draw_text(f, txt, F_BI, size, x0, 540, 'l', (1, 1, 1), op=op, blur=sc_blur, grad=grad)

# ---- final glass panel with chip grid
GRID = [('\U0001F3C3', 'running'), ('\U0001F3AC', 'Video'), ('\U0001F3CB', 'gym'), ('\U0001F310', 'website'),
        ('\U0001F3C3', 'running'), ('\U0001F3AC', 'Video'), ('\U0001F310', 'website'), ('\U0001F3CB', 'gym'),
        ('\U0001F3CB', 'gym'), ('\U0001F3C3', 'running'), ('\U0001F3AC', 'Video'), ('\U0001F310', 'website')]

def panel_scene(f, t):
    if t < 13.3: return
    u = eob(seg(t, 13.3, 13.85), 1.3)
    op = sm(seg(t, 13.3, 13.6))
    grow = 1 + 0.30 * sm(seg(t, 13.5, 14.43))
    w, h = 470 * grow * lerp(0.6, 1, u), 560 * grow * lerp(0.6, 1, u)
    rot = 2.5 * sm(seg(t, 13.5, 14.43)) * 0
    draw_rr(f, 960, 540, w, h, 62 * grow, fill=(1, 1, 1), fa=0.10, border=(1, 1, 1), ba=0.28, bw=2.5, op=op, shadow=0.35, sh_blur=30)
    cw, ch = w * 0.42, h * 0.115
    for i, (emo, lab) in enumerate(GRID):
        r, c = divmod(i, 2)
        ts = 13.45 + i * 0.045
        cu = eob(seg(t, ts, ts + 0.4), 1.3)
        if cu <= 0: continue
        cx = 960 + (c - 0.5) * (cw + w * 0.04)
        cy = 540 + (r - 2.5) * (ch + h * 0.036)
        s = cu * grow * lerp(0.6, 1, u)
        draw_rr(f, cx, cy, cw * cu, ch * cu, ch * cu / 2, fill=(1, 1, 1), fa=0.20, border=(1, 1, 1), ba=0.35, bw=1.5, op=op)
        draw_emoji(f, emo, cx - cw * 0.30 * cu, cy, ch * 0.62 * cu, op * cu)
        draw_text(f, lab, F_BI, ch * 0.44 * cu, cx - cw * 0.14 * cu, cy + 1, 'l', (1, 1, 1), op=op * sm(seg(t, ts + 0.1, ts + 0.35)))

# ---------------------------------------------------------------- main render
def render(t):
    f = background(t).astype(np.float32)
    hey_scene(f, t)
    ui_scene(f, t)
    task_scene(f, t)
    chips_scene(f, t)
    sched_scene(f, t)
    panel_scene(f, t)
    return (np.clip(f, 0, 1) * 255 + 0.5).astype(np.uint8)

def main():
    init_cam()
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'out', 'reference.mp4')
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    n = int(round(DUR * FPS))
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '%dx%d' % (W, H),
                          '-r', str(FPS), '-i', '-', '-an', '-c:v', 'libx264', '-preset', 'medium', '-crf', '16',
                          '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out], stdin=subprocess.PIPE)
    t0 = time.time()
    for i in range(n):
        p.stdin.write(render(i / FPS).tobytes())
        if i % 30 == 0: print('  frame %d/%d (%.0fs)' % (i, n, time.time() - t0), flush=True)
    p.stdin.close()
    if p.wait() != 0: raise SystemExit('ffmpeg failed')
    print('video ->', out)

if __name__ == '__main__':
    main()
