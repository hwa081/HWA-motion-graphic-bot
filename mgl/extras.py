"""mgl.extras - higher level components used by the JSON spec (all draw onto the float32 frame)."""
import math
import numpy as np, cv2
from . import engine as E
from .engine import clamp, seg, sm, eo3, eio, lerp, lerpc


# ------------------------------------------------------------------ blob (soft gradient orb)
def blob(f, cx, cy, r, c1, c2=None, op=1.0, softness=0.6):
    if r < 2 or op <= 0.003: return
    c2 = c2 or c1
    size = int(r * 2.3)
    if size < 4 or size > 5000: return
    n = int(min(256, max(16, size // 3)))
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    c = (n - 1) / 2
    d = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / (c / 1.15)          # 1.0 at radius r
    s = max(0.05, min(1.0, softness))
    t = np.clip((1 - d) / s, 0, 1); a = t * t * (3 - 2 * t)
    g = ((xx + yy) / (2 * n))[..., None]
    col = np.array(c1, np.float32) * (1 - g) + np.array(c2, np.float32) * g
    a = cv2.resize(a, (size, size), interpolation=cv2.INTER_LINEAR)
    col = cv2.resize(col, (size, size), interpolation=cv2.INTER_LINEAR)
    E.over(f, col * a[..., None], a, cx - size / 2, cy - size / 2, op)


# ------------------------------------------------------------------ particles
def particles(f, t, count, color, size, speed, area, seed=1, twinkle=0.5, op=1.0):
    count = int(clamp(count, 1, 250))
    ax, ay, aw, ah = area
    rng = np.random.RandomState(int(seed) & 0x7fffffff)
    x0 = rng.rand(count); y0 = rng.rand(count); ph = rng.rand(count) * 6.283; sz = 0.5 + rng.rand(count); sp = 0.4 + rng.rand(count)
    m = np.zeros((E.H, E.W), np.float32)
    for i in range(count):
        x = ax + ((x0[i] + 0.04 * math.sin(t * 0.7 + ph[i])) % 1.0) * aw
        y = ay + ((y0[i] - speed * 0.05 * sp[i] * t) % 1.0) * ah
        a = (1 - twinkle) + twinkle * (0.5 + 0.5 * math.sin(t * 2.0 + ph[i]))
        r = max(1.0, size * sz[i])
        cv2.circle(m, (int(x * 16), int(y * 16)), int(r * 16), float(a), -1, cv2.LINE_AA, 4)
    col = np.broadcast_to(np.array(color, np.float32), (E.H, E.W, 3))
    E.over(f, col * m[..., None], m, 0, 0, op)


# ------------------------------------------------------------------ grid pattern
def grid(f, t, kind, spacing, color, op, scroll=(0, 0), vignette=0.0, thickness=2.0):
    spacing = max(16.0, float(spacing))
    ox = (scroll[0] * t) % spacing; oy = (scroll[1] * t) % spacing
    m = np.zeros((E.H, E.W), np.float32)
    nx = int(E.W / spacing) + 3; ny = int(E.H / spacing) + 3
    if kind == 'lines':
        for i in range(nx):
            x = i * spacing + ox - spacing
            cv2.line(m, (int(x * 16), 0), (int(x * 16), E.H * 16), 1.0, max(1, int(round(thickness))), cv2.LINE_AA, 4)
        for j in range(ny):
            y = j * spacing + oy - spacing
            cv2.line(m, (0, int(y * 16)), (E.W * 16, int(y * 16)), 1.0, max(1, int(round(thickness))), cv2.LINE_AA, 4)
    else:
        r = max(1.5, thickness * 1.2)
        for i in range(nx):
            for j in range(ny):
                x = i * spacing + ox - spacing; y = j * spacing + oy - spacing
                if kind == 'crosses':
                    cv2.line(m, (int((x - r * 2) * 16), int(y * 16)), (int((x + r * 2) * 16), int(y * 16)), 1.0, max(1, int(thickness)), cv2.LINE_AA, 4)
                    cv2.line(m, (int(x * 16), int((y - r * 2) * 16)), (int(x * 16), int((y + r * 2) * 16)), 1.0, max(1, int(thickness)), cv2.LINE_AA, 4)
                else:
                    cv2.circle(m, (int(x * 16), int(y * 16)), int(r * 16), 1.0, -1, cv2.LINE_AA, 4)
    if vignette > 0:
        yy, xx = np.mgrid[0:E.H:4, 0:E.W:4].astype(np.float32)
        d = np.sqrt(((xx - E.W / 2) / (E.W / 2)) ** 2 + ((yy - E.H / 2) / (E.H / 2)) ** 2)
        v = np.clip(1 - vignette * d, 0, 1)
        m *= cv2.resize(v, (E.W, E.H), interpolation=cv2.INTER_LINEAR)
    col = np.broadcast_to(np.array(color, np.float32), (E.H, E.W, 3))
    E.over(f, col * m[..., None], m, 0, 0, op)


# ------------------------------------------------------------------ progress bar / ring
def progress(f, kind, cx, cy, w, h, value, color, track, op, text_color=None, label=None, font=None):
    value = clamp(value)
    if kind == 'ring':
        r = min(w, h) / 2; th = max(4, r * 0.18)
        ov = None
        for col, frac, a in ((track, 1.0, 0.25), (color, value, 1.0)):
            if frac <= 0.001: continue
            m = np.zeros((E.H, E.W), np.float32)
            cv2.ellipse(m, (int(cx * 16), int(cy * 16)), (int((r - th / 2) * 16), int((r - th / 2) * 16)), 0, -90, -90 + 360 * frac,
                        1.0, int(th), cv2.LINE_AA, 4)
            E.over(f, np.broadcast_to(np.array(col, np.float32), (E.H, E.W, 3)) * (m * a)[..., None], m * a, 0, 0, op)
        if label is not None:
            E.draw_text(f, label, font, r * 0.6, cx, cy, 'c', text_color or (1, 1, 1), op)
    else:
        E.draw_rr(f, cx, cy, w, h, h / 2, fill=track, fa=0.28, op=op)
        if value > 0.004:
            fw = max(h, w * value)
            E.draw_rr(f, cx - w / 2 + fw / 2, cy, fw, h, h / 2, fill=color, fa=1.0, op=op)


# ------------------------------------------------------------------ charts
def chart(f, kind, cx, cy, w, h, data, colors, prog, op, labels=None, label_color=(1, 1, 1), font=None, grid_on=True, center_text=None):
    data = [max(0.0, float(v)) for v in data]
    n = len(data)
    if n == 0 or op <= 0.003: return
    vmax = max(data) or 1.0
    left, top = cx - w / 2, cy - h / 2
    def col(i): return colors[i % len(colors)]
    if kind == 'donut':
        r = min(w, h) / 2; th = r * 0.32
        total = sum(data) or 1.0
        ang = -90.0
        sweep_total = 360.0 * prog
        for i, v in enumerate(data):
            span = 360.0 * v / total
            use = max(0.0, min(span, sweep_total - (ang + 90.0)))
            if use > 0.2:
                m = np.zeros((E.H, E.W), np.float32)
                cv2.ellipse(m, (int(cx * 16), int(cy * 16)), (int((r - th / 2) * 16), int((r - th / 2) * 16)), 0, ang, ang + max(use - 1.0, 0.5),
                            1.0, int(th), cv2.LINE_AA, 4)
                E.over(f, np.broadcast_to(np.array(col(i), np.float32), (E.H, E.W, 3)) * m[..., None], m, 0, 0, op)
            ang += span
        if center_text:
            E.draw_text(f, str(center_text), font, r * 0.5, cx, cy, 'c', label_color, op * sm(prog))
        return
    plot_top = top + 0.04 * h; plot_h = h * (0.78 if labels else 0.92); base = plot_top + plot_h
    if grid_on:
        for k in range(5):
            y = plot_top + plot_h * k / 4
            E.aaline(f, (left, y), (left + w, y), label_color, max(1, h / 300), 0.10 * op)
    if kind == 'line':
        xs = [left + w * (i / max(1, n - 1)) * 0.96 + w * 0.02 for i in range(n)]
        ys = [base - plot_h * (v / vmax) for v in data]
        # progressive reveal along x
        reveal = prog * (n - 1)
        pts = []
        for i in range(n):
            if i <= reveal: pts.append((xs[i], ys[i]))
            elif i - 1 < reveal:
                u = reveal - (i - 1)
                pts.append((lerp(xs[i - 1], xs[i], u), lerp(ys[i - 1], ys[i], u)))
        if len(pts) >= 2:
            area = pts + [(pts[-1][0], base), (pts[0][0], base)]
            m = np.zeros((E.H, E.W), np.float32)
            cv2.fillPoly(m, [np.round(np.array(area) * 16).astype(np.int32)], 1.0, cv2.LINE_AA, 4)
            gy = np.clip((np.arange(E.H, dtype=np.float32) - plot_top) / max(plot_h, 1), 0, 1)[:, None]
            E.over(f, np.broadcast_to(np.array(col(0), np.float32), (E.H, E.W, 3)) * (m * 0.28 * (1 - 0.8 * gy))[..., None], m * 0.28 * (1 - 0.8 * gy), 0, 0, op)
            E.poly(f, pts, col(0), max(3, h * 0.012), False, op)
            for i, p in enumerate(pts):
                if i <= reveal:
                    E.circle(f, p, max(4, h * 0.02), col(0), -1, op); E.circle(f, p, max(2, h * 0.009), (1, 1, 1), -1, op)
    else:  # bar
        slot = w / n; bw = slot * 0.58
        for i, v in enumerate(data):
            p = eo3(seg(prog * (1 + 0.25 * n), i * 0.25, i * 0.25 + 1.0))
            bh = max(0.0, plot_h * (v / vmax) * p)
            if bh > 2:
                E.draw_rr(f, left + slot * (i + 0.5), base - bh / 2, bw, bh, min(bw * 0.28, bh / 2), fill=col(i), fa=1.0, op=op)
    if labels:
        for i, lb in enumerate(labels[:n]):
            x = (left + w * (i / max(1, n - 1)) * 0.96 + w * 0.02) if kind == 'line' else left + (w / n) * (i + 0.5)
            E.draw_text(f, str(lb)[:10], font, h * 0.06, x, base + h * 0.11, 'c', label_color, op * 0.8)


# ------------------------------------------------------------------ transitions (full-screen covers)
def _cover(f, a, color):
    """a: float array broadcastable to (H,W) with alpha 0..1"""
    c = np.array(color, np.float32)
    f[:] = f * (1 - a[..., None]) + c * a[..., None]

def transition(f, style, u, color=(1, 1, 1), direction='right', cx=None, cy=None, n=6, seed=0):
    """u = progress 0..1. cover happens during 0..0.5, uncover during 0.5..1. Switch scenes at u = 0.5."""
    W, H = E.W, E.H
    u = clamp(u)
    if u <= 0 or u >= 1: return
    if style == 'flash':
        _cover(f, np.full((H, W), (math.sin(math.pi * u) ** 2), np.float32), color); return
    p1 = eio(clamp(u * 2)); p2 = eio(clamp((u - 0.5) * 2))
    if style == 'wipe':
        horiz = direction in ('right', 'left')
        L = W if horiz else H
        fe = max(30.0, L * 0.04)
        idx = np.arange(L, dtype=np.float32)
        if direction in ('left', 'up'): idx = L - 1 - idx
        if u < 0.5: edge = lerp(-fe, L + fe, p1); a1 = np.clip((edge - idx) / fe, 0, 1)
        else: edge = lerp(-fe, L + fe, p2); a1 = np.clip((idx - edge) / fe, 0, 1)
        a = np.broadcast_to(a1[None, :], (H, W)) if horiz else np.broadcast_to(a1[:, None], (H, W))
        _cover(f, a, color)
    elif style == 'iris':
        cx = W / 2 if cx is None else cx; cy = H / 2 if cy is None else cy
        R = math.hypot(max(cx, W - cx), max(cy, H - cy)) * 1.03
        r = R * (p1 if u < 0.5 else 1 - p2)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        _cover(f, np.clip((r - d) / 8.0 + 0.5, 0, 1), color)
    elif style == 'stripes':
        n = int(clamp(n, 2, 24))
        bw = W / n
        a = np.zeros((H, W), np.float32)
        for i in range(n):
            d = 0.4 * i / max(1, n - 1)
            x0, x1 = int(i * bw), int(min(W, (i + 1) * bw + 1))
            if u < 0.5:
                p = eio(seg(u * 2, d, d + 0.6)); a[:int(H * p) + 1, x0:x1] = 1.0 if p > 0 else 0.0
            else:
                p = eio(seg((u - 0.5) * 2, d, d + 0.6)); a[int(H * p):, x0:x1] = 1.0
        _cover(f, a, color)
    elif style == 'glitch':
        rng = np.random.RandomState((int(seed) * 7919 + int(u * 240)) & 0x7fffffff)
        amp = int(W * 0.06 * math.sin(math.pi * u))
        if amp < 2: return
        src = f.copy()
        y = 0
        while y < H:
            hh = int(rng.randint(8, max(9, H // 9)))
            dx = int(rng.randint(-amp, amp + 1)) if rng.rand() < 0.65 else 0
            if dx: f[y:y + hh] = np.roll(src[y:y + hh], dx, axis=1)
            y += hh
        sh = max(1, amp // 3)
        f[..., 0] = np.roll(f[..., 0], sh, axis=1); f[..., 2] = np.roll(f[..., 2], -sh, axis=1)


# ------------------------------------------------------------------ device frames
def screen_patch(im, w, h, r):
    """cover-fit an RGBA float image into (w,h) with rounded corners -> (premult rgb, alpha)"""
    w, h = max(2, int(round(w))), max(2, int(round(h)))
    ih, iw = im.shape[:2]
    s = max(w / iw, h / ih)
    nw, nh = max(w, int(round(iw * s))), max(h, int(round(ih * s)))
    out = cv2.resize(im, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    x0, y0 = (nw - w) // 2, (nh - h) // 2
    out = out[y0:y0 + h, x0:x0 + w]
    a = out[..., 3]
    if r > 0:
        m, _, pw, ph = E.rr_alpha(w, h, r, 0.0, 0, pad=0)
        a = a * cv2.resize(m, (w, h))
    return out[..., :3] * a[..., None], a

def device(f, kind, cx, cy, w, screen_img, body=(0.07, 0.07, 0.09), screen_color=(0.15, 0.17, 0.25), op=1.0, rot=0.0, shadow=0.45, bar_color=None):
    """kind: phone | laptop | browser. w = width of the device in px. screen_img: RGBA float image or None"""
    if op <= 0.003 or w < 20: return
    if kind == 'phone':
        h = w * 2.05; r = w * 0.15; bez = w * 0.04
        E.draw_rr(f, cx, cy, w, h, r, fill=body, fa=1.0, border=(1, 1, 1), ba=0.25, bw=max(1.5, w * 0.008), op=op, shadow=shadow, sh_dy=w * 0.08, sh_blur=w * 0.12)
        sw, sh_ = w - 2 * bez, h - 2 * bez
        _screen(f, cx, cy, sw, sh_, r - bez, screen_img, screen_color, op)
        E.draw_rr(f, cx, cy - h / 2 + bez + w * 0.045, w * 0.28, w * 0.06, w * 0.03, fill=(0, 0, 0), fa=1.0, op=op)
    elif kind == 'laptop':
        sw_ = w * 0.84; sh_ = sw_ * 0.625; bez = w * 0.02
        total_h = sh_ + 2 * bez + w * 0.035
        top = cy - total_h / 2
        E.draw_rr(f, cx, top + (sh_ + 2 * bez) / 2, sw_ + 2 * bez, sh_ + 2 * bez, w * 0.025, fill=body, fa=1.0, border=(1, 1, 1), ba=0.22, bw=max(1.5, w * 0.005),
                  op=op, shadow=shadow, sh_dy=w * 0.05, sh_blur=w * 0.08)
        _screen(f, cx, top + (sh_ + 2 * bez) / 2, sw_, sh_, w * 0.012, screen_img, screen_color, op)
        E.draw_rr(f, cx, top + sh_ + 2 * bez + w * 0.0175, w, w * 0.035, w * 0.012, fill=(0.62, 0.64, 0.68), fa=1.0, fill2=(0.4, 0.42, 0.46), op=op)
        E.draw_rr(f, cx, top + sh_ + 2 * bez + w * 0.008, w * 0.14, w * 0.014, w * 0.006, fill=(0.3, 0.31, 0.34), fa=1.0, op=op)
    else:  # browser window
        h = w * 0.62; bar = w * 0.06; r = w * 0.025
        E.draw_rr(f, cx, cy, w, h, r, fill=body, fa=1.0, border=(1, 1, 1), ba=0.22, bw=max(1.5, w * 0.004), op=op, shadow=shadow, sh_dy=w * 0.04, sh_blur=w * 0.06)
        for i, c in enumerate(((1.0, 0.37, 0.34), (1.0, 0.74, 0.18), (0.16, 0.8, 0.25))):
            E.circle(f, (cx - w / 2 + bar * (0.6 + i * 0.55), cy - h / 2 + bar / 2), bar * 0.17, c, -1, op)
        E.draw_rr(f, cx + bar * 0.4, cy - h / 2 + bar / 2, w * 0.5, bar * 0.52, bar * 0.26, fill=(1, 1, 1), fa=0.12, op=op)
        _screen(f, cx, cy + bar / 2, w - w * 0.016, h - bar - w * 0.012, r * 0.6, screen_img, screen_color, op)

def _screen(f, cx, cy, w, h, r, img, color, op):
    if img is None:
        E.draw_rr(f, cx, cy, w, h, max(r, 1), fill=color, fa=1.0, fill2=tuple(c * 0.55 for c in color), op=op)
    else:
        p, a = screen_patch(img, w, h, max(r, 0))
        E.over(f, p, a, cx - a.shape[1] / 2, cy - a.shape[0] / 2, op)
