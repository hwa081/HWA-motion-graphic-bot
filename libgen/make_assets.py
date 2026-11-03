"""Procedural stand-in pictures for the design library (so the library renders offline, no copyright).
In real videos the bot uses image "search" for real photos; these are only placeholders that show the layout."""
import os, numpy as np
from PIL import Image, ImageFilter, ImageDraw
W, H = 1600, 900
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'designlib')
rng = np.random.default_rng(42)

def save(a, name):
    Image.fromarray(np.clip(a, 0, 255).astype('uint8')).save(os.path.join(OUT, name + '.jpg'), quality=86)

def grad(c1, c2, vertical=True):
    t = np.linspace(0, 1, H if vertical else W)[:, None, None] if vertical else np.linspace(0, 1, W)[None, :, None]
    a = np.array(c1, float) * (1 - t) + np.array(c2, float) * t
    return np.broadcast_to(a, (H, W, 3)).copy()

def noise(scale, seed):
    r = np.random.default_rng(seed); n = r.random((H // scale + 2, W // scale + 2))
    return np.asarray(Image.fromarray((n * 255).astype('uint8')).resize((W, H), Image.BICUBIC), float) / 255

def stars(a, n=900, seed=1):
    r = np.random.default_rng(seed)
    for _ in range(n):
        x, y = r.integers(0, W), r.integers(0, H); b = r.random() ** 3 * 255
        a[y, x] = np.maximum(a[y, x], b)
        if r.random() < 0.07 and 1 < x < W - 2 and 1 < y < H - 2: a[y, x - 1:x + 2] = np.maximum(a[y, x - 1:x + 2], b * .6); a[y - 1:y + 2, x] = np.maximum(a[y - 1:y + 2, x], b * .6)
    return a

def sphere(a, cx, cy, R, color_fn, light=(-0.5, -0.5, 0.7)):
    ys, xs = np.mgrid[0:H, 0:W]; dx, dy = (xs - cx) / R, (ys - cy) / R; r2 = dx ** 2 + dy ** 2; m = r2 < 1
    z = np.sqrt(np.clip(1 - r2, 0, 1)); l = np.array(light) / np.linalg.norm(light)
    d = np.clip(dx * l[0] + dy * l[1] + z * l[2], 0, 1) ** 1.1 * 1.0 + 0.04
    col = color_fn(dx, dy, z)
    shaded = col * d[..., None]
    edge = np.clip((1 - r2) * R / 3, 0, 1)[..., None]
    a[m] = (shaded * edge + a * (1 - edge))[m]
    glow = np.clip(1.15 - np.sqrt(r2), 0, 1) ** 4 * (~m)
    return a

def build():
    os.makedirs(OUT, exist_ok=True)
    # starfield
    a = grad((4, 5, 18), (12, 8, 30)); a += noise(120, 3)[..., None] * np.array([6, 4, 14]); save(stars(a, 1400, 1), 'starfield')
    # nebula
    n1, n2, n3 = noise(220, 5), noise(110, 6), noise(60, 7); a = grad((6, 4, 20), (10, 4, 28))
    a += (n1 ** 2 * 1.6)[..., None] * np.array([120, 30, 150]) + (n2 * n1)[..., None] * np.array([30, 90, 160]) + (n3 * n1 ** 2)[..., None] * np.array([160, 60, 90]); save(stars(a, 1000, 2), 'nebula')
    # planet (banded gas giant) on stars
    a = stars(grad((3, 4, 14), (8, 6, 24)), 900, 3)
    band = lambda dx, dy, z: np.stack([210 + 40 * np.sin(dy * 14 + dx), 150 + 60 * np.sin(dy * 14 + 1), 90 + 50 * np.sin(dy * 9)], -1)
    save(sphere(a, 1000, 430, 330, band), 'planet')
    # earth
    a = stars(grad((2, 4, 12), (6, 8, 20)), 700, 4)
    land = noise(70, 9)
    def earth(dx, dy, z):
        h = np.sin(dx * 6 + 3 * np.sin(dy * 4)) * np.cos(dy * 5 + 2) + 0.3 * np.sin(dx * 15 + dy * 9)
        isl = (h > 0.35)[..., None]; ocean = np.array([20, 70, 170]); ground = np.array([50, 140, 70]); cloud = (noise(40, 11) > 0.62)[..., None] * 0.5
        c = np.where(isl, ground, ocean) * (1 - cloud) + 255 * cloud
        return c
    save(sphere(a, 800, 450, 360, earth), 'earth')
    # moon
    a = stars(grad((2, 2, 8), (6, 6, 14)), 800, 5)
    def moon(dx, dy, z):
        base = 170 + 40 * (noise(30, 12) - 0.5) * 2; cr = np.zeros_like(dx)
        r = np.random.default_rng(8)
        for _ in range(26):
            cx, cy, rr = r.uniform(-.8, .8), r.uniform(-.8, .8), r.uniform(.05, .17); d = np.sqrt((dx - cx) ** 2 + (dy - cy) ** 2); cr += np.exp(-((d - rr) / .015) ** 2) * -30 + (d < rr) * -14
        v = base + cr; return np.stack([v, v, v * 0.97], -1)
    save(sphere(a, 1050, 450, 320, moon), 'moon')
    # parchment with map lines
    n = noise(8, 13) * 0.5 + noise(50, 14) * 0.5; a = np.stack([228 - 50 * n, 205 - 55 * n, 160 - 60 * n], -1)
    im = Image.fromarray(np.clip(a, 0, 255).astype('uint8')); d = ImageDraw.Draw(im); r = np.random.default_rng(15)
    pts = [(int(300 + 1000 * t), int(450 + 180 * np.sin(t * 9) + 120 * np.sin(t * 3))) for t in np.linspace(0, 1, 60)]
    d.line(pts, fill=(90, 60, 30), width=5); d.line([(x, y + 120) for x, y in pts], fill=(120, 90, 50), width=3)
    for _ in range(14): x, y = r.integers(200, 1400), r.integers(150, 750); d.ellipse([x, y, x + 14, y + 14], outline=(80, 40, 20), width=3)
    d.line([(300, 300), (1300, 620)], fill=(150, 30, 20), width=4)
    arr = np.asarray(im, float); yy, xx = np.mgrid[0:H, 0:W]; v = 1 - 0.55 * (((xx - W / 2) / (W / 1.6)) ** 2 + ((yy - H / 2) / (H / 1.6)) ** 2); save(arr * v[..., None], 'parchment')
    # blueprint
    a = grad((14, 50, 110), (8, 34, 84)); a[::50] += 40; a[:, ::50] += 40; a[::10] += 8; a[:, ::10] += 8
    im = Image.fromarray(np.clip(a, 0, 255).astype('uint8')); d = ImageDraw.Draw(im)
    d.ellipse([560, 220, 1040, 700], outline=(200, 230, 255), width=4); d.rectangle([380, 340, 1220, 580], outline=(200, 230, 255), width=4); d.line([(300, 450), (1300, 450)], fill=(200, 230, 255), width=2); d.line([(800, 150), (800, 760)], fill=(200, 230, 255), width=2)
    save(np.asarray(im, float), 'blueprint')
    # layered landscapes helper
    def layers(sky, cols, seeds, amp, base):
        a = grad(*sky); yy = np.arange(H)[:, None]
        for c, s, am, b in zip(cols, seeds, amp, base):
            r = np.random.default_rng(s); x = np.arange(W); prof = b + sum(am / (k + 1) * np.sin(x / (160 / (k + 1)) + r.uniform(0, 6)) for k in range(4))
            m = (yy > prof[None, :]); a[np.broadcast_to(m, (H, W))] = np.array(c, float)
        return a
    save(layers(((255, 170, 90), (60, 40, 110)), [(120, 70, 110), (80, 50, 100), (40, 28, 70), (18, 14, 40)], [20, 21, 22, 23], [60, 50, 40, 30], [420, 520, 620, 720]), 'mountains')
    save(layers(((255, 200, 120), (255, 120, 80)), [(235, 160, 90), (200, 120, 70), (150, 80, 50)], [31, 32, 33], [30, 25, 20], [520, 640, 760]), 'desert')
    save(layers(((120, 190, 255), (210, 235, 255)), [(30, 120, 190), (20, 90, 160), (10, 60, 130)], [41, 42, 43], [18, 22, 26], [430, 560, 700]) , 'ocean')
    # city skyline at dusk
    a = grad((255, 140, 90), (30, 20, 70)); im = Image.fromarray(np.clip(a, 0, 255).astype('uint8')); d = ImageDraw.Draw(im); r = np.random.default_rng(51); x = 0
    while x < W:
        w = int(r.integers(60, 170)); h = int(r.integers(180, 620)); d.rectangle([x, H - h, x + w, H], fill=(14, 10, 30))
        for yy in range(H - h + 20, H - 10, 34):
            for xx in range(x + 12, x + w - 14, 26):
                if r.random() < 0.45: d.rectangle([xx, yy, xx + 10, yy + 16], fill=(255, 215, 120))
        x += w + int(r.integers(0, 14))
    save(np.asarray(im, float), 'skyline')
    # forest
    a = grad((180, 220, 190), (40, 90, 80)); im = Image.fromarray(np.clip(a, 0, 255).astype('uint8')); d = ImageDraw.Draw(im); r = np.random.default_rng(61)
    for k, col in enumerate([(60, 120, 90), (34, 90, 70), (16, 56, 48)]):
        for _ in range(26 - k * 4):
            x = int(r.integers(0, W)); h = int(r.integers(180, 420)) + 60 * k; w = int(h * 0.38); y0 = H - 120 + 70 * k
            d.polygon([(x, y0 - h), (x - w // 2, y0), (x + w // 2, y0)], fill=col)
    save(np.asarray(im, float), 'forest')
    # vintage archive photo (sepia, grain, vignette, silhouettes)
    a = grad((190, 170, 140), (110, 92, 72)); im = Image.fromarray(np.clip(a, 0, 255).astype('uint8')); d = ImageDraw.Draw(im); r = np.random.default_rng(71)
    for i in range(9): x = 160 + i * 150; h = int(r.integers(300, 520)); d.ellipse([x, 380 - h // 3, x + 70, 380 - h // 3 + 80], fill=(50, 40, 32)); d.rounded_rectangle([x - 20, 450 - h // 3, x + 90, H], radius=30, fill=(46, 36, 30))
    arr = np.asarray(im.filter(ImageFilter.GaussianBlur(1.6)), float); arr += (rng.random((H, W, 1)) - 0.5) * 36; yy, xx = np.mgrid[0:H, 0:W]; v = 1 - 0.7 * (((xx - W / 2) / (W / 1.5)) ** 2 + ((yy - H / 2) / (H / 1.5)) ** 2); save(arr * v[..., None], 'archive')
    # circuit / tech
    a = grad((6, 18, 30), (4, 30, 44)); im = Image.fromarray(np.clip(a, 0, 255).astype('uint8')); d = ImageDraw.Draw(im); r = np.random.default_rng(81)
    for _ in range(60):
        x, y = int(r.integers(0, W // 40)) * 40, int(r.integers(0, H // 40)) * 40; pts = [(x, y)]
        for _ in range(int(r.integers(2, 6))): x += int(r.choice([-1, 1])) * 40 * int(r.integers(1, 5)); pts.append((x, y)); y += int(r.choice([-1, 1])) * 40 * int(r.integers(1, 4)); pts.append((x, y))
        d.line(pts, fill=(40, 200, 190), width=3); d.ellipse([pts[-1][0] - 7, pts[-1][1] - 7, pts[-1][0] + 7, pts[-1][1] + 7], outline=(120, 255, 235), width=3)
    save(np.asarray(im.filter(ImageFilter.GaussianBlur(0.6)), float), 'circuit')
    # sun
    a = stars(grad((8, 4, 10), (20, 6, 8)), 500, 9)
    def sun(dx, dy, z): g = noise(26, 91); return np.stack([255 * np.ones_like(dx), 170 + 60 * g, 40 + 50 * g], -1) * 1.0
    a = sphere(a, 800, 450, 300, sun, light=(0, 0, 1)); save(a, 'sun')
    # abstract data / cells (science)
    a = grad((10, 20, 40), (30, 10, 50)); im = Image.fromarray(np.clip(a, 0, 255).astype('uint8')); d = ImageDraw.Draw(im, 'RGBA'); r = np.random.default_rng(101)
    for _ in range(46): x, y, rr = int(r.integers(0, W)), int(r.integers(0, H)), int(r.integers(20, 120)); d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(int(r.integers(80, 255)), int(r.integers(60, 200)), 255, 40), outline=(200, 220, 255, 90), width=3)
    save(np.asarray(im.filter(ImageFilter.GaussianBlur(1.2)), float), 'cells')

if __name__ == '__main__':
    build(); print(sorted(os.listdir(OUT)))
