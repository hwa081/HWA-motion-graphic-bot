"""mgl.api - everything a *code scene* (scene.py written by the AI) may use. `from mgl.api import *`

A code scene defines   DURATION (s), SIZE ('16:9' | '9:16' | '1:1'), optional FPS,  and  draw(f, t)
where f is a float32 RGB frame (H, W, 3) with values 0..1 and t is the time in seconds. draw must paint every pixel
(start with `f[:] = bg('dark_aurora', t)`) and must be a pure function of t.
"""
import math, os, random
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont
from . import engine as E
from . import extras as X
from . import spec as S
from .engine import (clamp, seg, sm, eo3, ei3, eio, eob, lerp, lerpc, over, draw_rr, draw_text, text_w, draw_emoji, aaline, poly, circle,
                     mic_icon, plus_icon, arrow_icon, star_icon, draw_card, draw_chip, font_path, BG_STYLES)

_ctx = None

def canvas():
    """(W, H) of the current canvas"""
    return E.W, E.H

def center():
    return E.W / 2, E.H / 2

def new_frame():
    return np.zeros((E.H, E.W, 3), np.float32)

def bg(style, t):
    """animated background (same styles as the JSON library) -> float32 (H, W, 3)"""
    return E.blobfield(style, t)

def mix(a, b, m):
    return a * (1 - m) + b * m

def gradient(c1, c2, angle=90.0, w=None, h=None):
    """linear gradient image (h, w, 3); angle 90 = top to bottom"""
    w = w or E.W; h = h or E.H
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    a = math.radians(angle)
    u = ((xx - w / 2) * math.cos(a) + (yy - h / 2) * math.sin(a)) / (abs(w * math.cos(a)) + abs(h * math.sin(a)) + 1e-6) + 0.5
    u = np.clip(u, 0, 1)[..., None]
    return np.array(c1, np.float32) * (1 - u) + np.array(c2, np.float32) * u

def glow(f, x, y, r, color, op=1.0, softness=0.9):
    """soft glowing orb"""
    X.blob(f, x, y, r, color, color, op, softness)

def noise2(x, y, t=0.0, seed=0):
    """smooth value noise in 0..1; x, y numpy arrays or floats"""
    def h(ix, iy):
        n = np.sin(ix * 127.1 + iy * 311.7 + seed * 74.7) * 43758.5453
        return n - np.floor(n)
    x = np.asarray(x, np.float32) + t * 0.3; y = np.asarray(y, np.float32) + t * 0.2
    x0, y0 = np.floor(x), np.floor(y); fx, fy = x - x0, y - y0
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    return (h(x0, y0) * (1 - fx) + h(x0 + 1, y0) * fx) * (1 - fy) + (h(x0, y0 + 1) * (1 - fx) + h(x0 + 1, y0 + 1) * fx) * fy

def image(path):
    """load an image from assets/ as float32 RGBA (h, w, 4)"""
    global _ctx
    if _ctx is None: _ctx = S.Context(os.getcwd())
    return S._load_image(_ctx, path)

def paste(f, rgba, x, y, w=None, h=None, op=1.0, rot=0.0):
    """draw an RGBA float image centred at (x, y), optionally resized to w x h"""
    im = rgba
    if w or h:
        ih, iw = im.shape[:2]; w = w or h * iw / ih; h = h or w * ih / iw
        im = cv2.resize(im, (max(2, int(w)), max(2, int(h))), interpolation=cv2.INTER_AREA if w < iw else cv2.INTER_LINEAR)
    a = im[..., 3]
    prgb = im[..., :3] * a[..., None]
    if rot:
        hh, ww = a.shape
        M = cv2.getRotationMatrix2D((ww / 2, hh / 2), -rot, 1.0)
        nw = int(abs(ww * M[0, 0]) + abs(hh * M[0, 1])) + 2; nh = int(abs(ww * M[1, 0]) + abs(hh * M[1, 1])) + 2
        M[0, 2] += nw / 2 - ww / 2; M[1, 2] += nh / 2 - hh / 2
        pa = cv2.warpAffine(np.dstack([prgb, a]), M, (nw, nh)); prgb, a = pa[..., :3], pa[..., 3]
    over(f, np.ascontiguousarray(prgb), np.ascontiguousarray(a), x - a.shape[1] / 2, y - a.shape[0] / 2, op)

def layer(f, t, L, duration=None):
    """draw ONE layer written exactly like a JSON-library layer (see LIBRARY.md), e.g.
       layer(f, t, {"type":"chip","emoji":"🚀","label":"Go","x":960,"y":600,"start":0,"in":"pop"})  -> times are scene times"""
    global _ctx
    if _ctx is None: _ctx = S.Context(os.getcwd())
    dur = float(duration or L.get('end', 0) or 600.0)
    errs, _ = S.validate({'duration': max(dur, 1.0), 'layers': [L]}, os.getcwd())
    if errs: raise ValueError('layer() problem: ' + '; '.join(errs))
    lum = float(f[::8, ::8].mean(axis=2).mean())               # how bright is what is already drawn? (chips switch between glass and white)
    S.draw_layer(f, {}, L, t, (1.0, E.W / 2, E.H / 2), clamp((lum - 0.30) / 0.35), _ctx, dur)
    if _ctx.warnings: raise ValueError('layer() failed: ' + _ctx.warnings.pop())

def spec_frame(spec, t):
    """render a complete JSON scene spec at time t -> float32 frame (use as a background or a sub-scene)"""
    global _ctx
    if _ctx is None: _ctx = S.Context(os.getcwd())
    return S.render_frame(spec, t, _ctx).astype(np.float32) / 255.0
