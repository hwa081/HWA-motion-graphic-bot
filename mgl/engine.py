"""mgl.engine - low level drawing for 1920x1080 motion graphics (numpy + OpenCV + Pillow only).

Everything draws onto a float32 RGB frame (H x W x 3, values 0..1).
"""
import math, os, json
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
SIZES = {'16:9': (1920, 1080), '9:16': (1080, 1920), '1:1': (1080, 1080)}
SIZE_ALIASES = {'landscape': '16:9', 'horizontal': '16:9', 'youtube': '16:9', 'portrait': '9:16', 'vertical': '9:16', 'shorts': '9:16',
                'reels': '9:16', 'tiktok': '9:16', 'story': '9:16', 'square': '1:1', 'instagram': '1:1',
                '1920:1080': '16:9', '1080:1920': '9:16', '1080:1080': '1:1'}

def norm_size(name):
    """'16:9' | '9:16' | '1:1' (or landscape / portrait / square ...) -> canonical key, or None"""
    if isinstance(name, str):
        k = name.strip().lower().replace('x', ':').replace('/', ':') if ':' in name or 'x' in name or '/' in name else name.strip().lower()
        k = SIZE_ALIASES.get(k, k)
        if k in SIZES: return k
        if name.strip() in SIZES: return name.strip()
    return None

def set_size(name):
    """switch the canvas (module-wide). Returns (W, H)."""
    global W, H
    key = norm_size(name) or '16:9'
    W, H = SIZES[key]
    _bgcache.clear()
    return W, H

def canvas_key():
    for k, v in SIZES.items():
        if v == (W, H): return k
    return '16:9'

# ------------------------------------------------------------------ fonts
_HERE = os.path.dirname(os.path.abspath(__file__))
_FONT_DIRS = [os.path.join(_HERE, '..', 'fonts'), '/usr/share/fonts/truetype/google-fonts']

def _find(name):
    for d in _FONT_DIRS:
        p = os.path.normpath(os.path.join(d, name))
        if os.path.exists(p):
            return p
    raise FileNotFoundError('Font not found: %s (looked in %s)' % (name, _FONT_DIRS))

FONTS = {
    'bold_italic': 'Poppins-BoldItalic.ttf', 'medium_italic': 'Poppins-MediumItalic.ttf',
    'italic': 'Poppins-Italic.ttf', 'bold': 'Poppins-Bold.ttf', 'medium': 'Poppins-Medium.ttf',
    'regular': 'Poppins-Regular.ttf',
}

def font_path(key):
    return _find(FONTS[key])

F_BI = font_path('bold_italic'); F_MI = font_path('medium_italic'); F_I = font_path('italic')

_EMOJI_CANDIDATES = ['/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf',
                     '/usr/share/fonts/noto/NotoColorEmoji.ttf',
                     '/usr/share/fonts/google-noto-emoji/NotoColorEmoji.ttf',
                     '/usr/share/fonts/truetype/noto-color-emoji/NotoColorEmoji.ttf',
                     os.path.normpath(os.path.join(_HERE, '..', 'fonts', 'NotoColorEmoji.ttf'))]
F_EMOJI = next((p for p in _EMOJI_CANDIDATES if os.path.exists(p)), None)

# ------------------------------------------------------------------ helpers
def clamp(x, a=0.0, b=1.0): return a if x < a else (b if x > b else x)
def seg(t, a, b): return 0.0 if b == a else clamp((t - a) / (b - a))
def sm(x): x = clamp(x); return x * x * (3 - 2 * x)
def eo3(x): x = clamp(x); return 1 - (1 - x) ** 3
def ei3(x): x = clamp(x); return x ** 3
def eio(x): x = clamp(x); return 0.5 - 0.5 * math.cos(math.pi * x)
def eob(x, s=1.6): x = clamp(x); return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2
def lerp(a, b, x): return a + (b - a) * x
def lerpc(c1, c2, x): return tuple(lerp(a, b, x) for a, b in zip(c1, c2))

_fc = {}
def font(path, size):
    k = (path, int(round(size)))
    if k not in _fc: _fc[k] = ImageFont.truetype(path, max(4, int(round(size))))
    return _fc[k]

def over(frame, prgb, a, x0, y0, op=1.0):
    """premultiplied patch over frame (float32), clipped to the frame"""
    if op <= 0.001: return
    h, w = a.shape
    x0 = int(round(x0)); y0 = int(round(y0))
    xa, ya = max(0, x0), max(0, y0)
    xb, yb = min(W, x0 + w), min(H, y0 + h)
    if xa >= xb or ya >= yb: return
    pa = a[ya - y0:yb - y0, xa - x0:xb - x0, None] * op
    pc = prgb[ya - y0:yb - y0, xa - x0:xb - x0] * op
    frame[ya:yb, xa:xb] = frame[ya:yb, xa:xb] * (1 - pa) + pc

# ------------------------------------------------------------------ backgrounds
# each blob: (colour, cx, cy, rx, ry, strength) ; coordinates in a 1.778 x 1 box
BG_STYLES = {
    'dark_aurora': dict(light=0.0, base=(0.060, 0.066, 0.080), blobs=[
        ((0.07, 0.22, 0.30), 1.25, 0.55, 0.75, 0.80, 0.70),
        ((0.06, 0.62, 0.60), 1.70, 0.05, 0.62, 0.70, 0.90),
        ((0.05, 0.78, 0.66), 1.95, -0.05, 0.40, 0.45, 0.80),
        ((0.26, 0.74, 0.10), 0.15, 1.00, 0.70, 0.55, 0.85),
        ((0.36, 0.82, 0.14), 0.55, 1.12, 0.40, 0.40, 0.80)]),
    'light_pastel': dict(light=1.0, base=(0.905, 0.905, 0.925), blobs=[
        ((0.93, 0.70, 0.93), 0.40, 0.02, 0.85, 0.50, 0.85),
        ((0.74, 0.94, 0.90), 1.65, 0.12, 0.62, 0.65, 0.85),
        ((0.77, 0.95, 0.74), 0.20, 1.02, 0.75, 0.45, 0.85)]),
    'neon_night': dict(light=0.0, base=(0.045, 0.040, 0.085), blobs=[
        ((0.30, 0.10, 0.55), 0.30, 0.20, 0.80, 0.70, 0.85),
        ((0.85, 0.15, 0.55), 1.60, 0.90, 0.75, 0.60, 0.80),
        ((0.10, 0.35, 0.80), 1.55, 0.05, 0.60, 0.60, 0.75)]),
    'ocean': dict(light=0.0, base=(0.030, 0.075, 0.130), blobs=[
        ((0.05, 0.35, 0.65), 0.35, 0.35, 0.90, 0.80, 0.85),
        ((0.10, 0.70, 0.80), 1.55, 0.95, 0.80, 0.60, 0.80),
        ((0.20, 0.85, 0.75), 1.80, 0.05, 0.45, 0.45, 0.70)]),
    'sunset': dict(light=0.35, base=(0.16, 0.08, 0.20), blobs=[
        ((0.98, 0.45, 0.25), 0.30, 1.00, 0.95, 0.65, 0.90),
        ((0.95, 0.30, 0.55), 1.40, 0.70, 0.80, 0.60, 0.85),
        ((0.45, 0.20, 0.70), 1.50, 0.00, 0.80, 0.60, 0.85)]),
    'mono_dark': dict(light=0.0, base=(0.050, 0.052, 0.058), blobs=[
        ((0.16, 0.17, 0.20), 0.60, 0.30, 0.90, 0.70, 0.9),
        ((0.11, 0.12, 0.14), 1.50, 0.90, 0.80, 0.60, 0.9)]),
    'mono_light': dict(light=1.0, base=(0.95, 0.95, 0.96), blobs=[
        ((0.88, 0.89, 0.92), 0.50, 0.30, 0.90, 0.70, 0.9),
        ((0.92, 0.93, 0.95), 1.50, 0.90, 0.80, 0.60, 0.9)]),
}

_bgcache = {}
def blobfield(style, t):
    st = BG_STYLES[style]
    w, h = W // 10, H // 10
    if 'grid' not in _bgcache:
        _bgcache['grid'] = np.meshgrid(np.linspace(0, 1.778, w), np.linspace(0, 1, h))
    X, Y = _bgcache['grid']
    dx = 0.07 * np.sin(3.1 * Y + 0.55 * t) + 0.045 * np.sin(5.3 * X - 0.42 * t + 1.3)
    dy = 0.07 * np.sin(2.7 * X + 0.48 * t + 0.6) + 0.04 * np.sin(4.6 * Y + 0.37 * t)
    Xw, Yw = X + dx, Y + dy
    img = np.zeros((h, w, 3), np.float32) + np.array(st['base'], np.float32)
    for col, cx, cy, rx, ry, strength in st['blobs']:
        d = ((Xw - cx) / rx) ** 2 + ((Yw - cy) / ry) ** 2
        a = np.clip(1 - d, 0, 1) ** 1.35 * strength
        a = a * a * (3 - 2 * a)
        img = img * (1 - a[..., None]) + np.array(col, np.float32) * a[..., None]
    img = cv2.GaussianBlur(img, (0, 0), 1.2)
    return cv2.resize(img, (W, H), interpolation=cv2.INTER_CUBIC)

# ------------------------------------------------------------------ shapes
def rr_pts(x, y, w, h, r, n=14):
    r = min(r, w / 2, h / 2)
    pts = []
    for (cx, cy, a0) in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return np.array(pts, np.float64)

def rr_alpha(w, h, r, rot=0.0, border=0.0, pad=6):
    """returns (fill_alpha, border_alpha, patch_w, patch_h); the shape is centred in the patch"""
    cr, sr = abs(math.cos(math.radians(rot))), abs(math.sin(math.radians(rot)))
    pw = int(math.ceil(w * cr + h * sr)) + 2 * pad
    ph = int(math.ceil(w * sr + h * cr)) + 2 * pad
    cx, cy = pw / 2, ph / 2
    p = rr_pts(cx - w / 2, cy - h / 2, w, h, r)
    if rot:
        c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        d = p - [cx, cy]
        p = np.stack([d[:, 0] * c - d[:, 1] * s, d[:, 0] * s + d[:, 1] * c], 1) + [cx, cy]
    m = np.zeros((ph, pw), np.uint8)
    cv2.fillPoly(m, [np.round(p * 16).astype(np.int32)], 255, lineType=cv2.LINE_AA, shift=4)
    b = None
    if border > 0:
        b = np.zeros((ph, pw), np.uint8)
        cv2.polylines(b, [np.round(p * 16).astype(np.int32)], True, 255, thickness=max(1, int(round(border))),
                      lineType=cv2.LINE_AA, shift=4)
        b = b.astype(np.float32) / 255
    return m.astype(np.float32) / 255, b, pw, ph

def draw_rr(frame, cx, cy, w, h, r, fill=(1, 1, 1), fa=1.0, fill2=None, border=None, ba=0.0, bw=2.0,
            rot=0.0, op=1.0, shadow=0.0, sh_dy=0, sh_blur=20, shadow_color=(0, 0, 0)):
    if w < 2 or h < 2 or op <= 0.001: return
    if w > 6000 or h > 6000: return
    m, b, pw, ph = rr_alpha(w, h, r, rot, bw if border is not None else 0)
    x0, y0 = cx - pw / 2, cy - ph / 2
    if shadow > 0 and sh_blur > 0.5:
        pad = int(sh_blur * 3)
        sa = cv2.GaussianBlur(cv2.copyMakeBorder(m, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0), (0, 0), sh_blur) * shadow
        over(frame, np.broadcast_to(np.array(shadow_color, np.float32), sa.shape + (3,)) * sa[..., None], sa, x0 - pad, y0 - pad + sh_dy, op)
    if fill2 is not None:
        g = np.linspace(0, 1, ph, dtype=np.float32)[:, None, None]
        col = np.array(fill, np.float32) * (1 - g) + np.array(fill2, np.float32) * g
        col = np.broadcast_to(col, (ph, pw, 3))
    else:
        col = np.broadcast_to(np.array(fill, np.float32), (ph, pw, 3))
    a = m * fa
    over(frame, col * a[..., None], a, x0, y0, op)
    if b is not None and ba > 0:
        bb = b * ba
        over(frame, np.broadcast_to(np.array(border, np.float32), (ph, pw, 3)) * bb[..., None], bb, x0, y0, op)

# ------------------------------------------------------------------ text
QA_SINK = None      # list while mgl.qa is analysing, else None
QA_LAYER = -1       # index of the layer currently being drawn (set by mgl.spec)

def draw_text(frame, txt, fpath, size, x, y, anchor='c', color=(1, 1, 1), op=1.0, blur=0.0, grad=None,
              rot=0.0, shadow=0.0, grad_mode='abs'):
    """Fixed-baseline text. y = centre of the font line box, so words never jump.
    grad: callable(x_array)->(n,3) colours. grad_mode 'abs' = screen x, 'rel' = 0..1 along the text."""
    if op <= 0.003 or size < 4 or not txt: return 0
    f = font(fpath, size)
    asc, desc = f.getmetrics()
    tw = f.getlength(txt)
    pad = int(size * 0.3 + blur * 3 + 8)
    w = int(math.ceil(tw + size * 0.25)) + 2 * pad
    h = asc + desc + 2 * pad
    if w > 8000 or h > 4000: return tw
    im = Image.new('L', (w, h), 0)
    ImageDraw.Draw(im).text((pad, pad + asc), txt, font=f, fill=255, anchor='ls')
    a = np.asarray(im, np.float32) / 255
    if blur > 0.2: a = cv2.GaussianBlur(a, (0, 0), blur)
    if rot:
        M = cv2.getRotationMatrix2D((w / 2, h / 2), rot, 1)
        a = cv2.warpAffine(a, M, (w, h))
    if anchor == 'c': x0 = x - (tw + size * 0.25) / 2 - pad
    elif anchor == 'l': x0 = x - pad
    else: x0 = x - tw - pad
    y0 = y - h / 2
    if QA_SINK is not None and op >= 0.85:
        il, it, ir, ib = f.getbbox(txt, anchor='ls')            # ink box relative to the baseline origin
        bx0, by0 = int(round(x0 + pad + il)), int(round(y0 + pad + asc + it))
        bw_, bh_ = max(1, int(ir - il)), max(1, int(ib - it))
        ya, yb, xa, xb = max(0, by0), min(H, by0 + bh_), max(0, bx0), min(W, bx0 + bw_)
        bgc = frame[ya:yb:3, xa:xb:3].reshape(-1, 3).mean(axis=0) if (yb > ya and xb > xa) else None
        QA_SINK.append(dict(layer=QA_LAYER, text=txt, size=float(size), box=(bx0, by0, bw_, bh_),
                            color=None if grad is not None else tuple(float(c) for c in color), bg=None if bgc is None else tuple(float(c) for c in bgc)))
    if grad is not None:
        gx = np.arange(w, dtype=np.float32)
        gx = gx + x0 if grad_mode == 'abs' else np.clip((gx - pad) / max(tw, 1.0), 0, 1)
        col = np.broadcast_to(np.asarray(grad(gx), np.float32)[None, :, :], (h, w, 3))
    else:
        col = np.broadcast_to(np.array(color, np.float32), (h, w, 3))
    if shadow > 0:
        sa = cv2.GaussianBlur(a, (0, 0), size * 0.08) * shadow
        over(frame, np.zeros((h, w, 3), np.float32), sa, x0, y0 + size * 0.06, op)
    over(frame, col * a[..., None], a, x0, y0, op)
    return tw

def text_w(txt, fpath, size):
    return font(fpath, size).getlength(txt)

_emo = {}
def emoji_patch(ch, px):
    """premultiplied RGB + alpha for an emoji, or (None, None) when no emoji font is installed"""
    if F_EMOJI is None: return None, None
    if ch not in _emo:
        f = ImageFont.truetype(F_EMOJI, 109)
        im = Image.new('RGBA', (136, 128), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((0, 0), ch, font=f, embedded_color=True)
        _emo[ch] = np.asarray(im, np.float32) / 255
    base = _emo[ch]
    s = max(px, 4) / 128.0
    im = cv2.resize(base, (max(2, int(136 * s)), max(2, int(128 * s))), interpolation=cv2.INTER_AREA)
    a = im[..., 3]
    return im[..., :3] * a[..., None], a

def draw_emoji(frame, ch, cx, cy, px, op=1.0):
    p, a = emoji_patch(ch, px)
    if p is None: return
    over(frame, p, a, cx - a.shape[1] / 2, cy - a.shape[0] / 2, op)

# ------------------------------------------------------------------ icons / lines (cv2 anti-aliased)
def _blend_op(frame, ov, op):
    if ov is not None: frame[:] = ov * (1 - op) + frame * op

def aaline(frame, p1, p2, col, th, op=1.0):
    ov = frame.copy() if op < 1 else None
    cv2.line(frame, (int(p1[0] * 16), int(p1[1] * 16)), (int(p2[0] * 16), int(p2[1] * 16)), tuple(float(c) for c in col),
             max(1, int(round(th))), cv2.LINE_AA, 4)
    _blend_op(frame, ov, op)

def poly(frame, pts, col, th, closed=True, op=1.0):
    ov = frame.copy() if op < 1 else None
    cv2.polylines(frame, [np.round(np.array(pts) * 16).astype(np.int32)], closed, tuple(float(c) for c in col),
                  max(1, int(round(th))), cv2.LINE_AA, 4)
    _blend_op(frame, ov, op)

def circle(frame, c, r, col, th=-1, op=1.0):
    ov = frame.copy() if op < 1 else None
    cv2.circle(frame, (int(c[0] * 16), int(c[1] * 16)), max(1, int(r * 16)), tuple(float(x) for x in col),
               th if th < 0 else max(1, int(round(th))), cv2.LINE_AA, 4)
    _blend_op(frame, ov, op)

def mic_icon(frame, cx, cy, s, col=(1, 1, 1), th=3, op=1.0):
    w, h = 0.55 * s, 1.0 * s
    top = cy - h * 0.62
    poly(frame, rr_pts(cx - w / 2, top, w, h, w / 2, 10), col, th, True, op)
    arc = [(cx + 0.55 * s * math.cos(math.radians(a)), cy - 0.02 * s + 0.55 * s * math.sin(math.radians(a))) for a in range(10, 171, 10)]
    poly(frame, arc, col, th, False, op)
    aaline(frame, (cx, cy + 0.53 * s), (cx, cy + 0.78 * s), col, th, op)
    aaline(frame, (cx - 0.25 * s, cy + 0.78 * s), (cx + 0.25 * s, cy + 0.78 * s), col, th, op)

def plus_icon(f, x, y, r, col=(1, 1, 1), th=3, op=1.0):
    aaline(f, (x - r, y), (x + r, y), col, th, op)
    aaline(f, (x, y - r), (x, y + r), col, th, op)

def arrow_icon(f, x, y, ln, col=(1, 1, 1), th=3, op=1.0, angle_deg=0.0):
    c, s_ = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
    rot = lambda px, py: (x + px * c - py * s_, y + px * s_ + py * c)
    poly(f, [rot(0, ln), rot(0, -ln)], col, th, False, op)
    poly(f, [rot(-0.55 * ln, -0.1 * ln), rot(0, -ln), rot(0.55 * ln, -0.1 * ln)], col, th, False, op)

def star_icon(f, cx, cy, ro, col=(1, 1, 1), th=3, op=1.0):
    ri = ro * 0.42
    pts = [(cx + (ro if i % 2 == 0 else ri) * math.cos(math.radians(-90 + 36 * i)),
            cy + (ro if i % 2 == 0 else ri) * math.sin(math.radians(-90 + 36 * i))) for i in range(10)]
    poly(f, pts, col, th, True, op)

# ------------------------------------------------------------------ flat cards (PIL, supersampled) + perspective warp
KC = 1.7
CW, CH = 260, 360
_cards = {}

def _emoji_pil(ch, px):
    p, a = emoji_patch(ch, px)
    if p is None: return None
    rgba = np.dstack([np.where(a[..., None] > 0, p / np.maximum(a[..., None], 1e-6), 0), a])
    return Image.fromarray((np.clip(rgba, 0, 1) * 255).astype(np.uint8), 'RGBA')

def _rgb255(c, default=(255, 255, 255)):
    if c is None: return default
    c = list(c)
    if max(c) <= 1.0: c = [v * 255 for v in c]
    return tuple(int(clamp(v, 0, 255)) for v in c[:3])

def flat_card(kind, num=0, params=None):
    params = params or {}
    key = (kind, num, json.dumps(params, sort_keys=True))
    if key in _cards: return _cards[key]
    k = KC; ss = 2
    w, h = int(CW * k * ss), int(CH * k * ss)
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    R = int(34 * k * ss)
    S = k * ss
    def rr(box, rad, fill=None, outline=None, width=1):
        d.rounded_rectangle(box, rad, fill=fill, outline=outline, width=width)
    def fnt(p, s): return ImageFont.truetype(p, max(4, int(s * S)))
    def vgrad(c1, c2, a1=255, a2=255):
        arr = np.zeros((h, w, 4), np.uint8)
        yy = np.linspace(0, 1, h)[:, None]
        for i in range(3):
            arr[..., i] = (c1[i] + (c2[i] - c1[i]) * yy).astype(np.uint8) * np.ones((1, w), np.uint8)
        arr[..., 3] = (a1 + (a2 - a1) * yy).astype(np.uint8) * np.ones((1, w), np.uint8)
        return Image.fromarray(arr, 'RGBA')
    def paste_rounded(img):
        mk = Image.new('L', (w, h), 0); ImageDraw.Draw(mk).rounded_rectangle((0, 0, w - 1, h - 1), R, fill=255)
        im.paste(img, (0, 0), mk)
    def band(color, hh):
        top = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(top).rounded_rectangle((0, 0, w - 1, h - 1), R, fill=color + (255,))
        m2 = Image.new('L', (w, h), 0); ImageDraw.Draw(m2).rectangle((0, 0, w, hh), fill=255)
        top.putalpha(Image.composite(top.getchannel('A'), Image.new('L', (w, h), 0), m2))
        im.alpha_composite(top)

    if kind == 'image':
        rr((0, 0, w - 1, h - 1), R, fill=(40, 44, 50, 150), outline=(255, 255, 255, 70), width=int(2 * S))
        t = Image.new('RGBA', (int(150 * S), int(40 * S)), (0, 0, 0, 0))
        ImageDraw.Draw(t).text((0, 0), 'create image', font=fnt(F_I, 20), fill=(255, 255, 255, 235))
        t = t.rotate(8, expand=True, resample=Image.BICUBIC)
        im.alpha_composite(t, (int(18 * S), int(48 * S)))
        cx, cy, ro, ri = 215 * S, 78 * S, 17 * S, 7 * S
        pts = [(cx + (ro if i % 2 == 0 else ri) * math.cos(math.radians(-90 + 36 * i)), cy + (ro if i % 2 == 0 else ri) * math.sin(math.radians(-90 + 36 * i))) for i in range(10)]
        d.line(pts + [pts[0]], fill=(255, 255, 255, 240), width=int(2.2 * S), joint='curve')
        lw = int(2.2 * S)
        d.line([(110 * S, 175 * S), (150 * S, 235 * S), (70 * S, 235 * S), (110 * S, 175 * S)], fill=(255, 255, 255, 235), width=lw, joint='curve')
        d.rounded_rectangle((38 * S, 255 * S, 98 * S, 315 * S), int(12 * S), outline=(255, 255, 255, 235), width=lw)
        d.ellipse((130 * S, 255 * S, 190 * S, 315 * S), outline=(255, 255, 255, 235), width=lw)
    elif kind == 'note':
        rr((0, 0, w - 1, h - 1), R, fill=(36, 38, 44, 235), outline=(255, 255, 255, 40), width=int(2 * S))
        hh = int(82 * S)
        band((244, 183, 32), hh)
        d.text((w / 2, hh + 34 * S), 'Add Note', font=fnt(F_I, 19), fill=(255, 255, 255, 235), anchor='mm')
        for i in range(3):
            y = hh + (80 + i * 34) * S
            d.line([(24 * S, y), (w - 24 * S, y)], fill=(255, 255, 255, 22), width=int(1.5 * S))
    elif kind == 'event':
        rr((0, 0, w - 1, h - 1), R, fill=(26, 30, 36, 235))
        paste_rounded(vgrad((30, 150, 150), (50, 220, 190)))
        hh = int(76 * S)
        band((229, 18, 82), hh)
        d.text((w / 2, hh + 30 * S), 'create event', font=fnt(F_I, 19), fill=(255, 255, 255, 240), anchor='mm')
        d.text((w / 2, hh + 112 * S), str(num), font=fnt(F_BI, 96), fill=(255, 255, 255, 255), anchor='mm')
    elif kind == 'voice':
        paste_rounded(vgrad((32, 180, 164), (22, 70, 74), 210, 170))
        d.rounded_rectangle((0, 0, w - 1, h - 1), R, outline=(255, 255, 255, 60), width=int(2 * S))
        d.text((w / 2, 66 * S), 'Voice mode', font=fnt(F_I, 20), fill=(255, 255, 255, 240), anchor='mm')
        cx, cy = w / 2, 190 * S
        d.rounded_rectangle((cx - 22 * S, cy - 58 * S, cx + 22 * S, cy + 20 * S), int(22 * S), outline=(255, 255, 255, 245), width=int(4 * S))
        d.arc((cx - 40 * S, cy - 36 * S, cx + 40 * S, cy + 44 * S), 0, 180, fill=(255, 255, 255, 245), width=int(4 * S))
        d.line([(cx, cy + 44 * S), (cx, cy + 66 * S)], fill=(255, 255, 255, 245), width=int(4 * S))
        d.line([(cx - 20 * S, cy + 66 * S), (cx + 20 * S, cy + 66 * S)], fill=(255, 255, 255, 245), width=int(4 * S))
        d.ellipse((cx + 40 * S, cy - 64 * S, cx + 52 * S, cy - 52 * S), fill=(255, 40, 60, 255))
    else:  # custom
        body = _rgb255(params.get('body'), (30, 34, 42)); body2 = _rgb255(params.get('body2'), body)
        paste_rounded(vgrad(body, body2, int(255 * params.get('body_opacity', 0.94)), int(255 * params.get('body_opacity', 0.94))))
        if params.get('border', True):
            d.rounded_rectangle((0, 0, w - 1, h - 1), R, outline=(255, 255, 255, 60), width=int(2 * S))
        tcol = _rgb255(params.get('text_color'), (255, 255, 255)) + (245,)
        top = 0
        if params.get('header'):
            hh = int(params.get('header_h', 70) * S)
            band(_rgb255(params['header']), hh); top = hh
        if params.get('title'):
            d.text((w / 2, top + 34 * S), str(params['title'])[:28], font=fnt(F_MI, 21), fill=tcol, anchor='mm')
        if params.get('emoji'):
            e = _emoji_pil(str(params['emoji']), int(110 * S))
            if e is not None:
                im.alpha_composite(e, (int(w / 2 - e.width / 2), int(top + 80 * S)))
        big = params.get('big_text')
        if big:
            size = 92 if len(str(big)) <= 4 else (64 if len(str(big)) <= 7 else 44)
            d.text((w / 2, top + (150 if not params.get('emoji') else 235) * S), str(big)[:14], font=fnt(F_BI, size), fill=tcol, anchor='mm')
        if params.get('subtitle'):
            d.text((w / 2, h - 52 * S), str(params['subtitle'])[:30], font=fnt(F_I, 17), fill=tcol[:3] + (190,), anchor='mm')
    im = im.resize((int(CW * k), int(CH * k)), Image.LANCZOS)
    arr = np.asarray(im, np.float32) / 255
    a = arr[..., 3]
    _cards[key] = (arr[..., :3] * a[..., None], a)
    return _cards[key]

def draw_card(frame, kind, num, cx, cy, sc, yaw, roll, op, params=None):
    """cx,cy screen centre; sc = overall scale (incl. camera zoom); yaw in degrees (+ = right edge farther)"""
    if op <= 0.004 or sc < 0.02: return
    prgb, a = flat_card(kind, num, params)
    h0, w0 = a.shape
    w, h = CW * sc, CH * sc
    cyaw = math.cos(math.radians(yaw)); syaw = math.sin(math.radians(yaw))
    wl = w / 2 * cyaw
    hl = h / 2 * (1 - 0.11 * syaw)
    hr = h / 2 * (1 + 0.11 * syaw)
    quad = np.float32([[-wl, -hl], [wl, -hr], [wl, hr], [-wl, hl]])
    cr, sr = math.cos(math.radians(roll)), math.sin(math.radians(roll))
    quad = np.float32([[x * cr - y * sr, x * sr + y * cr] for x, y in quad]) + np.float32([cx, cy])
    x0, y0 = int(np.floor(quad[:, 0].min())) - 3, int(np.floor(quad[:, 1].min())) - 3
    x1, y1 = int(np.ceil(quad[:, 0].max())) + 3, int(np.ceil(quad[:, 1].max())) + 3
    bw, bh = x1 - x0, y1 - y0
    if bw < 2 or bh < 2 or bw > 4000 or bh > 4000: return
    src = np.float32([[0, 0], [w0, 0], [w0, h0], [0, h0]])
    M = cv2.getPerspectiveTransform(src, (quad - np.float32([x0, y0])).astype(np.float32))
    pa = np.dstack([prgb, a])
    out = cv2.warpPerspective(pa, M, (bw, bh), flags=cv2.INTER_AREA if sc < KC * 0.8 else cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT)
    over(frame, np.ascontiguousarray(out[..., :3]), np.ascontiguousarray(out[..., 3]), x0, y0, op)

# ------------------------------------------------------------------ chips (emoji + label pill)
def draw_chip(f, emo, label, cx, cy, s, rot, light, op, w0=400, h0=150):
    w, h = w0 * s, h0 * s
    if light > 0.01:
        draw_rr(f, cx, cy, w, h, h / 2, fill=(1, 1, 1), fa=0.97 * light, rot=rot, op=op, shadow=0.20 * light, sh_dy=10 * s, sh_blur=14 * s)
    if light < 0.99:
        draw_rr(f, cx, cy, w, h, h / 2, fill=(1, 1, 1), fa=0.14 * (1 - light), border=(1, 1, 1), ba=0.35 * (1 - light),
                bw=max(1.5, 2 * s), rot=rot, op=op)
    cr, sr = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    if emo:
        ex = -w * 0.27
        draw_emoji(f, emo, cx + ex * cr, cy + ex * sr, 0.64 * h, op)
    tx = w * 0.06 if emo else 0
    col = lerpc((1, 1, 1), (0.05, 0.05, 0.06), light)
    draw_text(f, label, F_BI, 0.41 * h, cx + tx * cr, cy + tx * sr + 3 * s, 'l' if emo else 'c', col, op=op, rot=-rot)
