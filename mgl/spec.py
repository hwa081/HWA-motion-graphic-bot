import json
"""mgl.spec - turns a JSON scene description into frames.

Public API:
    errors, warnings = validate(spec, root)      # errors == [] means the spec can be rendered
    frame = render_frame(spec, t, ctx)           # uint8 RGB (1080,1920,3)
    ctx = Context(root)                          # caches + collected render warnings
"""
import math, os, re
import numpy as np, cv2
from . import engine as E
from . import extras as X
from .engine import clamp, seg, sm, eo3, eio, eob, lerp, lerpc

MAX_LAYERS = 300
MAX_DURATION = 60.0
LAYER_TYPES = ['text', 'rrect', 'circle', 'line', 'icon', 'emoji', 'chip', 'card', 'image',
               'transition', 'blob', 'chart', 'device', 'particles', 'grid', 'progress']
TRANSITIONS = ['wipe', 'iris', 'stripes', 'flash', 'glitch']
DIRECTIONS = ['right', 'left', 'up', 'down']
CHART_KINDS = ['bar', 'line', 'donut']
DEVICES = ['phone', 'laptop', 'browser']
GRID_KINDS = ['dots', 'lines', 'crosses']
PROGRESS_KINDS = ['bar', 'ring']
REVEAL_MODES = ['words', 'chars', 'letters']
ICONS = ['plus', 'mic', 'send', 'arrow_up', 'check', 'cross', 'star']
CARD_KINDS = ['image', 'note', 'event', 'voice', 'custom']
ANIMS = ['none', 'fade', 'blur', 'pop', 'slide_up', 'slide_down', 'slide_left', 'slide_right', 'zoom',
         'spin', 'bounce', 'tilt', 'rise', 'wipe_right', 'wipe_left', 'wipe_up', 'wipe_down']
EASES = {
    'linear': lambda x: clamp(x), 'smooth': sm, 'out': eo3, 'in': lambda x: clamp(x) ** 3,
    'inout': eio, 'back': lambda x: eob(x, 1.4),
}
COMMON_KEYS = ['x', 'y', 'scale', 'rot', 'opacity', 'blur']
TYPE_KEYS = {
    'text': ['size', 'color', 'grad_from', 'grad_to'],
    'rrect': ['w', 'h', 'r'], 'circle': ['r'], 'line': ['width'], 'icon': ['size', 'color', 'angle'],
    'emoji': ['size'], 'chip': ['w', 'h'], 'card': ['yaw', 'roll', 'number'], 'image': ['w', 'h', 'zoom', 'pan_x', 'pan_y', 'tilt_x', 'tilt_y'],
    'blob': ['r', 'color', 'color2'], 'chart': ['progress', 'w', 'h'], 'device': ['w'], 'particles': [], 'grid': [],
    'progress': ['value', 'w', 'h'], 'transition': [],
}
COLOR_KEYS = {'color', 'color2', 'grad_from', 'grad_to'}
NAMED = {
    'white': (1, 1, 1), 'black': (0, 0, 0), 'red': (0.9, 0.1, 0.2), 'green': (0.2, 0.75, 0.3), 'blue': (0.15, 0.4, 0.95),
    'yellow': (0.97, 0.78, 0.15), 'orange': (0.98, 0.55, 0.15), 'pink': (0.95, 0.4, 0.7), 'purple': (0.55, 0.3, 0.85),
    'teal': (0.1, 0.7, 0.65), 'cyan': (0.2, 0.85, 0.95), 'gray': (0.5, 0.5, 0.52), 'grey': (0.5, 0.5, 0.52),
}

def _isnum(v): return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)

def parse_color(v):
    """accepts [r,g,b] in 0..1 or 0..255, '#rgb', '#rrggbb' or a colour name -> (r,g,b) floats 0..1; None if invalid"""
    if isinstance(v, str):
        s = v.strip().lower()
        if s in NAMED: return NAMED[s]
        m = re.fullmatch(r'#?([0-9a-f]{6})', s)
        if m: return tuple(int(m.group(1)[i:i + 2], 16) / 255 for i in (0, 2, 4))
        m = re.fullmatch(r'#?([0-9a-f]{3})', s)
        if m: return tuple(int(c * 2, 16) / 255 for c in m.group(1))
        return None
    if isinstance(v, (list, tuple)) and len(v) >= 3 and all(_isnum(c) for c in v[:3]):
        c = [float(x) for x in v[:3]]
        if max(c) > 1.0: c = [x / 255 for x in c]
        return tuple(clamp(x) for x in c)
    return None

# ------------------------------------------------------------------ validation
def validate(spec, root='.'):
    errs, warns = [], []
    if not isinstance(spec, dict):
        return ['spec must be a JSON object'], warns
    dur = spec.get('duration')
    if not _isnum(dur) or not (0.5 <= dur <= MAX_DURATION):
        errs.append("'duration' must be a number between 0.5 and %d (seconds)" % MAX_DURATION)
        dur = 5.0
    if 'size' in spec and E.norm_size(spec['size']) is None:
        errs.append("'size' must be '16:9' (1920x1080), '9:16' (1080x1920) or '1:1' (1080x1080) - got %r" % (spec['size'],))
    fps = spec.get('fps', 30)
    if fps not in (24, 25, 30, 60):
        errs.append("'fps' must be one of 24, 25, 30, 60 (or omitted)")
    bg = spec.get('background', 'dark_aurora')
    for k in (_bg_keys_raw(bg)):
        if not isinstance(k, dict) or k.get('style') not in E.BG_STYLES:
            errs.append("background style must be one of %s (got %r)" % (sorted(E.BG_STYLES), k.get('style') if isinstance(k, dict) else k))
        elif not _isnum(k.get('t', 0)) or (k.get('fade') is not None and not _isnum(k.get('fade'))):
            errs.append("background keys need numeric 't' and optional numeric 'fade'")
    cam = spec.get('camera')
    if cam is not None:
        if not isinstance(cam, list) or not cam:
            errs.append("'camera' must be a non-empty list of {t, zoom, x, y}")
        else:
            for i, k in enumerate(cam):
                if not isinstance(k, dict) or not _isnum(k.get('t')):
                    errs.append('camera[%d] needs a numeric t' % i); continue
                for p in ('zoom', 'x', 'y'):
                    if p in k and not _isnum(k[p]): errs.append('camera[%d].%s must be a number' % (i, p))
                if _isnum(k.get('zoom')) and not (0.2 <= k['zoom'] <= 6): errs.append('camera[%d].zoom must be between 0.2 and 6' % i)
    layers = spec.get('layers')
    if not isinstance(layers, list) or not layers:
        errs.append("'layers' must be a non-empty list")
        return errs, warns
    if len(layers) > MAX_LAYERS:
        errs.append('too many layers (%d, max %d)' % (len(layers), MAX_LAYERS))
    for i, L in enumerate(layers[:MAX_LAYERS]):
        errs.extend(_validate_layer(i, L, dur, root, warns))
    return errs, warns

def _bg_keys_raw(bg):
    if isinstance(bg, str): return [{'style': bg, 't': 0}]
    if isinstance(bg, list) and bg: return bg
    if isinstance(bg, dict): return [bg]
    return [{'style': None}]

SEARCH_SECTIONS = ['photo', 'illustration', 'vector', 'icon', 'canva']
_FMT_OK = re.compile(r'^\{:,?(\.\d+)?[df]?\}$')

def _check_image_path(tag, p, root):
    if not isinstance(p, str) or not p:
        return ["%s: needs 'path' like assets/logo.png" % tag]
    full = os.path.normpath(os.path.join(root, p))
    if not os.path.abspath(full).startswith(os.path.abspath(root)):
        return ['%s: path must stay inside the project' % tag]
    if not os.path.isfile(full):
        have = []
        for dp, _, fs in os.walk(os.path.join(root, 'assets')):
            have += [os.path.relpath(os.path.join(dp, f), root) for f in fs if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
        return ["%s: image %r not found. Files available: %s" % (tag, p, sorted(have)[:25] or 'none')]
    return []

def _validate_layer(i, L, dur, root, warns):
    e = []
    tag = 'layers[%d]' % i
    if not isinstance(L, dict): return [tag + ' must be an object']
    ty = L.get('type')
    if ty not in LAYER_TYPES:
        return ["%s: unknown type %r (allowed: %s)" % (tag, ty, ', '.join(LAYER_TYPES))]
    tag += ' (%s)' % ty
    for p in ('start', 'end', 'x', 'y', 'scale', 'rot', 'opacity', 'blur', 'size', 'w', 'h', 'r', 'width', 'yaw', 'roll',
              'number', 'shadow', 'fill_opacity', 'border_opacity', 'border_w', 'shadow_blur', 'shadow_dy', 'light', 'angle', 'softness', 'progress',
              'value', 'spacing', 'speed', 'twinkle', 'vignette', 'thickness', 'zoom', 'pan_x', 'pan_y', 'tilt_x', 'tilt_y', 'seed', 'n'):
        if p in L and not _isnum(L[p]): e.append('%s: %r must be a number' % (tag, p))
    for p in ('color', 'color2', 'fill', 'fill2', 'border', 'shadow_color', 'track', 'body', 'screen_color', 'tint'):
        if p in L and parse_color(L[p]) is None: e.append('%s: %r is not a valid colour (use [r,g,b] or "#rrggbb")' % (tag, p))
    if _isnum(L.get('start')) and _isnum(L.get('end')) and L['end'] <= L['start']:
        e.append('%s: end must be greater than start' % tag)
    for io in ('in', 'out'):
        v = L.get(io)
        if v is not None:
            a = v if isinstance(v, str) else (v.get('anim') if isinstance(v, dict) else None)
            if a not in ANIMS: e.append('%s: %r animation must be one of %s' % (tag, io, ', '.join(ANIMS)))
            if isinstance(v, dict) and 'dur' in v and not (_isnum(v['dur']) and v['dur'] > 0): e.append('%s: %s.dur must be > 0' % (tag, io))
    keys = L.get('keys')
    if keys is not None:
        if not isinstance(keys, dict): e.append('%s: keys must be an object {property: [[t, value], ...]}' % tag)
        else:
            allowed = COMMON_KEYS + TYPE_KEYS.get(ty, [])
            for prop, pts in keys.items():
                if prop not in allowed:
                    e.append('%s: cannot animate %r (allowed: %s)' % (tag, prop, ', '.join(allowed))); continue
                if not isinstance(pts, list) or not pts:
                    e.append('%s: keys.%s must be a non-empty list of [t, value] or [t, value, ease]' % (tag, prop)); continue
                for j, p in enumerate(pts):
                    if not isinstance(p, list) or len(p) < 2 or not _isnum(p[0]):
                        e.append('%s: keys.%s[%d] must look like [time, value]' % (tag, prop, j)); break
                    if prop in COLOR_KEYS:
                        if parse_color(p[1]) is None: e.append('%s: keys.%s[%d] value is not a colour' % (tag, prop, j)); break
                    elif not _isnum(p[1]): e.append('%s: keys.%s[%d] value must be a number' % (tag, prop, j)); break
                    if len(p) > 2 and p[2] not in EASES: e.append('%s: ease must be one of %s' % (tag, ', '.join(EASES))); break
    if ty == 'text':
        if not isinstance(L.get('text'), str) or not L.get('text'): e.append("%s: needs non-empty 'text'" % tag)
        if L.get('font', 'bold_italic') not in E.FONTS: e.append('%s: font must be one of %s' % (tag, ', '.join(E.FONTS)))
        if L.get('anchor', 'c') not in ('c', 'l', 'r'): e.append("%s: anchor must be 'c', 'l' or 'r'" % tag)
        g = L.get('gradient')
        if g is not None and (not isinstance(g, dict) or parse_color(g.get('from')) is None or parse_color(g.get('to')) is None):
            e.append("%s: gradient needs {'from': colour, 'to': colour}" % tag)
        rv = L.get('reveal')
        if rv is not None:
            if not isinstance(rv, dict) or rv.get('mode', 'words') not in REVEAL_MODES: e.append("%s: reveal.mode must be one of %s" % (tag, ', '.join(REVEAL_MODES)))
            elif 'times' in rv and not (isinstance(rv['times'], list) and all(_isnum(x) for x in rv['times'])): e.append('%s: reveal.times must be a list of numbers' % tag)
    elif ty == 'rrect':
        if not _isnum(L.get('w')) or not _isnum(L.get('h')) or L.get('w', 0) <= 0 or L.get('h', 0) <= 0: e.append("%s: needs positive 'w' and 'h'" % tag)
    elif ty == 'circle':
        if not _isnum(L.get('r')) or L.get('r', 0) <= 0: e.append("%s: needs positive 'r'" % tag)
    elif ty == 'line':
        pts = L.get('points')
        if not (isinstance(pts, list) and len(pts) >= 2 and all(isinstance(p, list) and len(p) == 2 and all(_isnum(c) for c in p) for p in pts)):
            e.append("%s: 'points' must be a list of at least two [x, y] pairs" % tag)
    elif ty == 'icon':
        if L.get('name') not in ICONS: e.append("%s: name must be one of %s" % (tag, ', '.join(ICONS)))
    elif ty == 'emoji':
        if not isinstance(L.get('char'), str) or not L.get('char'): e.append("%s: needs 'char' (one emoji)" % tag)
    elif ty == 'chip':
        if not isinstance(L.get('label'), str) or not L.get('label'): e.append("%s: needs 'label'" % tag)
    elif ty == 'card':
        if L.get('kind') not in CARD_KINDS: e.append('%s: kind must be one of %s' % (tag, ', '.join(CARD_KINDS)))
    elif ty == 'image':
        if 'search' in L and 'path' not in L:
            sr = L['search']
            if not (isinstance(sr, dict) and isinstance(sr.get('query'), str) and sr.get('query').strip() and sr.get('section') in SEARCH_SECTIONS
                    and sr.get('style', 'mono') in ('mono', 'color')):
                e.append("%s: search must be {\"section\": one of %s, \"query\": \"what to find\"}" % (tag, ', '.join(SEARCH_SECTIONS)))
        else:
            e.extend(_check_image_path(tag, L.get('path'), root))
        if not _isnum(L.get('w')) and not _isnum(L.get('h')): e.append("%s: needs 'w' or 'h' (pixels)" % tag)
    fl = L.get('float')
    if fl is not None and (not isinstance(fl, dict) or not all(_isnum(v) for v in fl.values())):
        e.append("%s: float must be like {\"y\": 14, \"x\": 0, \"speed\": 1} (numbers only)" % tag)
    if ty == 'text':
        cnt = L.get('count')
        if cnt is not None:
            if not isinstance(cnt, dict) or not _isnum(cnt.get('to')):
                e.append("%s: count needs {\"from\": number, \"to\": number, optional \"start\", \"dur\", \"format\"}" % tag)
            elif '{n}' not in str(L.get('text', '')):
                e.append("%s: text must contain {n} where the counting number goes (e.g. \"${n}k\")" % tag)
            elif 'format' in cnt and not _FMT_OK.match(str(cnt['format'])):
                e.append("%s: count.format must look like {:,} or {:.1f} or {:d}" % tag)
    elif ty == 'transition':
        if L.get('style') not in TRANSITIONS: e.append('%s: style must be one of %s' % (tag, ', '.join(TRANSITIONS)))
        if L.get('direction', 'right') not in DIRECTIONS: e.append('%s: direction must be one of %s' % (tag, ', '.join(DIRECTIONS)))
        if not _isnum(L.get('start')) or not _isnum(L.get('end')): e.append("%s: needs both 'start' and 'end' (the sweep lasts 0.5-1.2 s; scenes switch at the middle)" % tag)
    elif ty == 'blob':
        if not _isnum(L.get('r')) or L.get('r', 0) <= 0: e.append("%s: needs positive 'r' (radius px)" % tag)
    elif ty == 'chart':
        if L.get('kind') not in CHART_KINDS: e.append('%s: kind must be one of %s' % (tag, ', '.join(CHART_KINDS)))
        d = L.get('data')
        if not (isinstance(d, list) and 2 <= len(d) <= 12 and all(_isnum(v) and v >= 0 for v in d)): e.append("%s: 'data' must be 2-12 non-negative numbers" % tag)
        if not _isnum(L.get('w')) or not _isnum(L.get('h')) or L.get('w', 0) <= 0 or L.get('h', 0) <= 0: e.append("%s: needs positive 'w' and 'h'" % tag)
        if 'colors' in L and not (isinstance(L['colors'], list) and L['colors'] and all(parse_color(c) is not None for c in L['colors'])): e.append("%s: 'colors' must be a list of colours" % tag)
        if 'labels' in L and not (isinstance(L['labels'], list) and all(isinstance(v, (str, int, float)) for v in L['labels'])): e.append("%s: 'labels' must be a list of short strings" % tag)
    elif ty == 'device':
        if L.get('kind') not in DEVICES: e.append('%s: kind must be one of %s' % (tag, ', '.join(DEVICES)))
        if not _isnum(L.get('w')) or L.get('w', 0) <= 0: e.append("%s: needs positive 'w' (device width px)" % tag)
        if 'path' in L: e.extend(_check_image_path(tag, L.get('path'), root))
    elif ty == 'particles':
        if 'count' in L and not (_isnum(L['count']) and 1 <= L['count'] <= 250): e.append("%s: count must be 1-250" % tag)
        a = L.get('area')
        if a is not None and not (isinstance(a, dict) and all(_isnum(a.get(k)) for k in ('x', 'y', 'w', 'h'))): e.append("%s: area must be {x, y, w, h}" % tag)
    elif ty == 'grid':
        if L.get('kind', 'dots') not in GRID_KINDS: e.append('%s: kind must be one of %s' % (tag, ', '.join(GRID_KINDS)))
    elif ty == 'progress':
        if L.get('kind', 'bar') not in PROGRESS_KINDS: e.append('%s: kind must be one of %s' % (tag, ', '.join(PROGRESS_KINDS)))
        if not _isnum(L.get('w')) or not _isnum(L.get('h')): e.append("%s: needs 'w' and 'h'" % tag)
    if ty in ('image',) and L.get('fit', 'cover') not in ('cover', 'contain'): e.append("%s: fit must be 'cover' or 'contain'" % tag)
    known = {'type', 'start', 'end', 'in', 'out', 'keys', 'fixed', 'x', 'y', 'scale', 'rot', 'opacity', 'blur', 'size', 'w', 'h', 'r',
             'text', 'font', 'color', 'anchor', 'gradient', 'reveal', 'shadow', 'fill', 'fill2', 'fill_opacity', 'border', 'border_opacity',
             'border_w', 'shadow_blur', 'shadow_dy', 'points', 'width', 'closed', 'name', 'angle', 'char', 'label', 'emoji', 'light',
             'kind', 'number', 'yaw', 'roll', 'title', 'subtitle', 'big_text', 'header', 'header_h', 'body', 'body2', 'body_opacity',
             'text_color', 'path', 'name', 'float', 'count', 'style', 'direction', 'n', 'seed', 'softness', 'color2', 'data', 'labels',
             'colors', 'progress', 'grow', 'center_text', 'grid', 'body', 'screen_color', 'area', 'speed', 'twinkle', 'spacing', 'scroll',
             'vignette', 'thickness', 'value', 'track', 'fit', 'zoom', 'pan_x', 'pan_y', 'tilt_x', 'tilt_y', 'shadow_color', 'search', 'tint'}
    extra = sorted(set(L) - known)
    if extra: warns.append('%s: ignored unknown fields %s' % (tag, extra))
    return e

# ------------------------------------------------------------------ evaluation helpers
class Context:
    def __init__(self, root='.'):
        self.root = root
        self.images = {}
        self.warnings = []

    def warn(self, msg):
        if msg not in self.warnings and len(self.warnings) < 40:
            self.warnings.append(msg)

def interp(points, t, default=None):
    """points: [[t, v], [t, v, ease], ...] with numeric or colour values"""
    if not points: return default
    pts = sorted(points, key=lambda p: p[0])
    def val(p): return parse_color(p[1]) if isinstance(p[1], (str, list)) else p[1]
    if t <= pts[0][0]: return val(pts[0])
    for a, b in zip(pts, pts[1:]):
        if a[0] <= t <= b[0]:
            ease = EASES.get(b[2] if len(b) > 2 else 'smooth', sm)
            u = ease(seg(t, a[0], b[0]))
            va, vb = val(a), val(b)
            if isinstance(va, tuple): return lerpc(va, vb, u)
            return lerp(va, vb, u)
    return val(pts[-1])

def prop(L, name, t, default):
    k = (L.get('keys') or {}).get(name)
    if k:
        v = interp(k, t, None)
        if v is not None: return v
    v = L.get(name, default)
    if name in COLOR_KEYS and v is not None and not isinstance(v, tuple): v = parse_color(v)
    return v

def _bg_keys(spec):
    ks = _bg_keys_raw(spec.get('background', 'dark_aurora'))
    ks = sorted(({'t': float(k.get('t', 0)), 'style': k['style'], 'fade': float(k.get('fade') or 0)} for k in ks), key=lambda k: k['t'])
    ks[0]['t'] = min(ks[0]['t'], 0.0)
    return ks

def bg_state(spec, t):
    """(style_a, style_b, mix) for crossfades"""
    ks = _bg_keys(spec)
    cur = 0
    for i, k in enumerate(ks):
        if t >= k['t']: cur = i
    k = ks[cur]
    if cur > 0 and k['fade'] > 0 and t < k['t'] + k['fade']:
        return ks[cur - 1]['style'], k['style'], sm(seg(t, k['t'], k['t'] + k['fade']))
    return k['style'], k['style'], 0.0

def bg_light(spec, t):
    a, b, m = bg_state(spec, t)
    return lerp(E.BG_STYLES[a]['light'], E.BG_STYLES[b]['light'], m)

def background(spec, t):
    a, b, m = bg_state(spec, t)
    if m <= 0.002 or a == b: return E.blobfield(b if m > 0.5 else a, t)
    if m >= 0.998: return E.blobfield(b, t)
    return E.blobfield(a, t) * (1 - m) + E.blobfield(b, t) * m

def camera_at(spec, t):
    cam = spec.get('camera')
    if not cam: return (1.0, E.W / 2, E.H / 2)
    ks = sorted(cam, key=lambda k: k['t'])
    def g(k): return (float(k.get('zoom', 1.0)), float(k.get('x', E.W / 2)), float(k.get('y', E.H / 2)))
    if t <= ks[0]['t']: return g(ks[0])
    for a, b in zip(ks, ks[1:]):
        if a['t'] <= t <= b['t']:
            ease = EASES.get(b.get('ease', 'smooth'), sm)
            u = ease(seg(t, a['t'], b['t']))
            return tuple(lerp(x, y, u) for x, y in zip(g(a), g(b)))
    return g(ks[-1])

def _anim(v):
    if v is None: return None
    if isinstance(v, str): return (v, 0.4)
    return (v.get('anim', 'fade'), float(v.get('dur', 0.4)))

def _apply_anim(kind, p):
    """p = visibility progress 0..1 -> modifiers"""
    m = dict(a=1.0, s=1.0, dx=0.0, dy=0.0, bl=0.0, rot=0.0, wipe=None)
    if kind == 'fade': m['a'] = sm(p)
    elif kind == 'blur': m['a'] = sm(p); m['bl'] = (1 - p) * 16
    elif kind == 'pop': m['a'] = sm(min(1.0, p * 1.8)); m['s'] = lerp(0.6, 1.0, eob(p, 1.4))
    elif kind == 'slide_up': m['a'] = sm(p); m['dy'] = (1 - eo3(p)) * 70
    elif kind == 'slide_down': m['a'] = sm(p); m['dy'] = -(1 - eo3(p)) * 70
    elif kind == 'slide_left': m['a'] = sm(p); m['dx'] = (1 - eo3(p)) * 90
    elif kind == 'slide_right': m['a'] = sm(p); m['dx'] = -(1 - eo3(p)) * 90
    elif kind == 'zoom': m['a'] = sm(p); m['s'] = lerp(1.25, 1.0, eo3(p))
    elif kind == 'spin': m['a'] = sm(min(1.0, p * 1.6)); m['s'] = lerp(0.4, 1.0, eo3(p)); m['rot'] = -(1 - eo3(p)) * 120
    elif kind == 'bounce': m['a'] = sm(min(1.0, p * 2.5)); m['dy'] = -(1 - eob(p, 2.4)) * 170
    elif kind == 'tilt': m['a'] = sm(p); m['rot'] = -(1 - eo3(p)) * 10; m['dy'] = (1 - eo3(p)) * 50
    elif kind == 'rise': m['a'] = sm(p); m['dy'] = (1 - eo3(p)) * 190
    elif kind.startswith('wipe_'): m['wipe'] = (kind[5:], p)
    return m

def inout(L, t, start, end):
    tot = dict(a=1.0, s=1.0, dx=0.0, dy=0.0, bl=0.0, rot=0.0, wipe=None)
    def merge(r):
        tot['a'] *= r['a']; tot['s'] *= r['s']
        for k in ('dx', 'dy', 'bl', 'rot'): tot[k] += r[k]
        if r['wipe'] and r['wipe'][1] < 0.999: tot['wipe'] = r['wipe']
    i = _anim(L.get('in'))
    if i and i[0] != 'none':
        merge(_apply_anim(i[0], seg(t, start, start + max(i[1], 1e-3))))
    o = _anim(L.get('out'))
    if o and o[0] != 'none':
        merge(_apply_anim(o[0], 1 - seg(t, end - max(o[1], 1e-3), end)))
    return tot

SCREEN_SPACE = ('transition', 'particles', 'grid')

def draw_layer(f, spec, L, t, cam, light, ctx, dur):
    start = float(L.get('start', 0)); end = float(L.get('end', dur))
    if t < start or t > end: return
    m = inout(L, t, start, end)
    op = clamp(prop(L, 'opacity', t, 1.0)) * m['a']
    if op <= 0.003: return
    ty = L['type']
    z, cx, cy = (1.0, E.W / 2, E.H / 2) if (L.get('fixed') or ty in SCREEN_SPACE) else cam
    x = prop(L, 'x', t, E.W / 2) + m['dx']; y = prop(L, 'y', t, E.H / 2) + m['dy']
    fl = L.get('float')
    if fl:
        sp = fl.get('speed', 1.0); ph = fl.get('phase', 0.0)
        x += fl.get('x', 0.0) * math.sin(t * sp * 2.0 + ph); y += fl.get('y', 14.0) * math.sin(t * sp * 2.0 + ph + 1.3)
    sx, sy = (x - cx) * z + E.W / 2, (y - cy) * z + E.H / 2
    sc = prop(L, 'scale', t, 1.0) * m['s']
    rot = prop(L, 'rot', t, 0.0) + m['rot']
    blur = (prop(L, 'blur', t, 0.0) + m['bl']) * z
    k = sc * z
    def paint(g):
        _paint(g, spec, L, t, ty, sx, sy, k, rot, op, blur, light, ctx, z, cx, cy, m, start, end, dur)
    if m['wipe']:
        _paint_wipe(f, paint, m['wipe'][0], m['wipe'][1])
    else:
        paint(f)

def _paint_wipe(f, paint, direction, p):
    if p <= 0.001: return
    g = f.copy(); paint(g)
    diff = (np.abs(g - f).max(axis=2) > 1e-4)
    rows, cols = np.where(diff.any(1))[0], np.where(diff.any(0))[0]
    if rows.size == 0: return
    y0, y1, x0, x1 = rows[0], rows[-1] + 1, cols[0], cols[-1] + 1
    fe = 28.0
    if direction in ('right', 'left'):
        idx = np.arange(x0, x1, dtype=np.float32) - x0
        span = float(x1 - x0)
        if direction == 'left': idx = span - 1 - idx
        a = np.clip((lerp(-fe, span + fe, p) - idx) / fe, 0, 1)[None, :]
    else:
        idx = np.arange(y0, y1, dtype=np.float32) - y0
        span = float(y1 - y0)
        if direction == 'up': idx = span - 1 - idx
        a = np.clip((lerp(-fe, span + fe, p) - idx) / fe, 0, 1)[:, None]
    a = a[..., None]
    f[y0:y1, x0:x1] = f[y0:y1, x0:x1] * (1 - a) + g[y0:y1, x0:x1] * a

DEFAULT_PALETTE = [(0.36, 0.55, 1.0), (0.95, 0.35, 0.65), (0.2, 0.85, 0.7), (1.0, 0.75, 0.25), (0.65, 0.45, 1.0), (0.4, 0.8, 1.0)]

def _auto_progress(L, t, start, dur_default=1.4):
    g = L.get('grow') if isinstance(L.get('grow'), dict) else {}
    s0 = float(g.get('start', start + 0.25)); d = max(float(g.get('dur', dur_default)), 1e-3)
    return eo3(seg(t, s0, s0 + d))

def _paint(f, spec, L, t, ty, sx, sy, k, rot, op, blur, light, ctx, z, cx, cy, m, start, end, dur):
    if ty == 'text':
        _draw_text_layer(f, L, t, sx, sy, k, op, blur, start, rot)
    elif ty == 'rrect':
        w = prop(L, 'w', t, 100) * k; h = prop(L, 'h', t, 100) * k
        r = prop(L, 'r', t, min(w, h) / 2 / max(k, 1e-6)) * k
        fill = parse_color(L.get('fill', 'white')) or (1, 1, 1)
        fill2 = parse_color(L['fill2']) if 'fill2' in L else None
        border = parse_color(L['border']) if 'border' in L else None
        E.draw_rr(f, sx, sy, w, h, r, fill, L.get('fill_opacity', 1.0), fill2, border, L.get('border_opacity', 0.5 if border else 0),
                  max(1.0, L.get('border_w', 2.0) * z), rot, op, L.get('shadow', 0.0), L.get('shadow_dy', 12) * z,
                  max(1.0, L.get('shadow_blur', 20) * z), parse_color(L.get('shadow_color', 'black')) or (0, 0, 0))
    elif ty == 'circle':
        r = prop(L, 'r', t, 50) * k
        fill = parse_color(L.get('fill', 'white')) or (1, 1, 1)
        border = parse_color(L['border']) if 'border' in L else None
        E.draw_rr(f, sx, sy, 2 * r, 2 * r, r, fill, L.get('fill_opacity', 1.0), None, border, L.get('border_opacity', 0.5 if border else 0),
                  max(1.0, L.get('border_w', 2.0) * z), 0, op, L.get('shadow', 0.0), L.get('shadow_dy', 12) * z,
                  max(1.0, L.get('shadow_blur', 20) * z), parse_color(L.get('shadow_color', 'black')) or (0, 0, 0))
    elif ty == 'line':
        col = parse_color(L.get('color', 'white')) or (1, 1, 1)
        pts = [((px - cx) * z + E.W / 2, (py - cy) * z + E.H / 2) for px, py in L['points']]
        E.poly(f, pts, col, max(1.0, prop(L, 'width', t, 4) * z), bool(L.get('closed', False)), op)
    elif ty == 'icon':
        col = prop(L, 'color', t, None) or (1, 1, 1)
        size = prop(L, 'size', t, 60) * k
        th = max(1.5, L.get('width', 4) * z)
        nm = L['name']
        if nm == 'plus': E.plus_icon(f, sx, sy, size * 0.5, col, th, op)
        elif nm == 'mic': E.mic_icon(f, sx, sy, size, col, th, op)
        elif nm == 'send':
            E.circle(f, (sx, sy), size * 0.5, col, th, op)
            E.arrow_icon(f, sx, sy, size * 0.22, col, th, op, prop(L, 'angle', t, 0.0))
        elif nm == 'arrow_up': E.arrow_icon(f, sx, sy, size * 0.5, col, th, op, prop(L, 'angle', t, 0.0))
        elif nm == 'check': E.poly(f, [(sx - 0.35 * size, sy), (sx - 0.1 * size, sy + 0.28 * size), (sx + 0.4 * size, sy - 0.3 * size)], col, th, False, op)
        elif nm == 'cross':
            E.aaline(f, (sx - 0.3 * size, sy - 0.3 * size), (sx + 0.3 * size, sy + 0.3 * size), col, th, op)
            E.aaline(f, (sx - 0.3 * size, sy + 0.3 * size), (sx + 0.3 * size, sy - 0.3 * size), col, th, op)
        elif nm == 'star': E.star_icon(f, sx, sy, size * 0.5, col, th, op)
    elif ty == 'emoji':
        E.draw_emoji(f, L['char'], sx, sy, prop(L, 'size', t, 100) * k, op)
    elif ty == 'chip':
        lt = L['light'] if 'light' in L else light
        E.draw_chip(f, L.get('emoji', ''), L['label'], sx, sy, k, rot, clamp(lt), op, prop(L, 'w', t, 400), prop(L, 'h', t, 150))
    elif ty == 'card':
        num = int(round(prop(L, 'number', t, 0)))
        params = {kk: L[kk] for kk in ('title', 'subtitle', 'header', 'header_h', 'body', 'body2', 'body_opacity', 'text_color', 'emoji', 'border') if kk in L}
        if 'big_text' in L: params['big_text'] = str(L['big_text']).replace('{n}', str(num))
        E.draw_card(f, L['kind'], num, sx, sy, k, prop(L, 'yaw', t, 0.0), prop(L, 'roll', t, 0.0) + rot, op, params)
    elif ty == 'image':
        _draw_image(f, L, t, sx, sy, k, rot, op, blur, ctx, z)
    elif ty == 'transition':
        col = parse_color(L.get('color', 'white')) or (1, 1, 1)
        X.transition(f, L['style'], seg(t, start, end), col, L.get('direction', 'right'),
                     sx if 'x' in L else None, sy if 'y' in L else None, int(L.get('n', 6)), int(L.get('seed', 0)))
    elif ty == 'blob':
        c1 = prop(L, 'color', t, None) or (0.5, 0.4, 1.0)
        c2 = prop(L, 'color2', t, None) or c1
        X.blob(f, sx, sy, prop(L, 'r', t, 200) * k, c1, c2, op * clamp(L.get('fill_opacity', 1.0)), L.get('softness', 0.6))
    elif ty == 'chart':
        cols = [parse_color(c) for c in L.get('colors', [])] or DEFAULT_PALETTE
        prog = clamp(prop(L, 'progress', t, None)) if (L.get('keys') or {}).get('progress') else _auto_progress(L, t, start)
        X.chart(f, L['kind'], sx, sy, prop(L, 'w', t, 600) * k, prop(L, 'h', t, 360) * k, L['data'], cols, prog, op, L.get('labels'),
                parse_color(L.get('text_color', 'white')) or (1, 1, 1), E.font_path(L.get('font', 'medium_italic')),
                bool(L.get('grid', True)), L.get('center_text'))
    elif ty == 'device':
        img = _load_image(ctx, L['path']) if L.get('path') else None
        X.device(f, L['kind'], sx, sy, prop(L, 'w', t, 400) * k, img, parse_color(L.get('body', '#121217')) or (0.07, 0.07, 0.09),
                 parse_color(L.get('screen_color', '#2a2e40')) or (0.16, 0.18, 0.25), op, rot, L.get('shadow', 0.45))
    elif ty == 'particles':
        a = L.get('area') or {'x': 0, 'y': 0, 'w': E.W, 'h': E.H}
        X.particles(f, t, L.get('count', 60), parse_color(L.get('color', 'white')) or (1, 1, 1), L.get('size', 4) * z, L.get('speed', 1.0),
                    (a['x'], a['y'], a['w'], a['h']), L.get('seed', 1), L.get('twinkle', 0.5), op)
    elif ty == 'grid':
        sc_ = L.get('scroll') or {}
        X.grid(f, t, L.get('kind', 'dots'), L.get('spacing', 70), parse_color(L.get('color', 'white')) or (1, 1, 1), op * clamp(L.get('fill_opacity', 0.18)),
               (sc_.get('x', 0), sc_.get('y', 0)), L.get('vignette', 0.0), L.get('thickness', 2.0))
    elif ty == 'progress':
        val = prop(L, 'value', t, None) if (L.get('keys') or {}).get('value') or 'value' in L else _auto_progress(L, t, start, 1.2)
        lab = L['label'].replace('{p}', str(int(round(clamp(val) * 100)))) if isinstance(L.get('label'), str) else None
        X.progress(f, L.get('kind', 'bar'), sx, sy, prop(L, 'w', t, 600) * k, prop(L, 'h', t, 26) * k, val,
                   parse_color(L.get('color', '#5b8cff')) or (0.36, 0.55, 1), parse_color(L.get('track', 'white')) or (1, 1, 1), op,
                   parse_color(L.get('text_color', 'white')) or (1, 1, 1), lab, E.font_path(L.get('font', 'bold_italic')))

def _count_text(L, t, start):
    c = L.get('count')
    txt = L['text']
    if not c: return txt
    s0 = float(c.get('start', start)); d = max(float(c.get('dur', 1.5)), 1e-3)
    v = lerp(float(c.get('from', 0)), float(c['to']), EASES.get(c.get('ease', 'out'), eo3)(seg(t, s0, s0 + d)))
    fmt = str(c.get('format', '{:,.0f}'))
    try:
        s = fmt.format(v if 'f' in fmt else int(round(v)))
    except Exception:
        s = str(int(round(v)))
    return txt.replace('{n}', s)

def _draw_text_layer(f, L, t, sx, sy, k, op, blur, start, rot=0.0):
    fp = E.font_path(L.get('font', 'bold_italic'))
    size = prop(L, 'size', t, 80) * k
    anchor = L.get('anchor', 'c')
    txt = _count_text(L, t, start)
    color = prop(L, 'color', t, None) or (1, 1, 1)
    grad = None; gm = 'abs'
    g = L.get('gradient')
    if g:
        c0 = prop(L, 'grad_from', t, None) or parse_color(g['from'])
        c1 = prop(L, 'grad_to', t, None) or parse_color(g['to'])
        cm = parse_color(g['mid']) if g.get('mid') is not None else None
        c0, c1 = np.array(c0, np.float32), np.array(c1, np.float32)
        def grad(u, c0=c0, c1=c1, cm=cm):
            u = np.clip(np.asarray(u, np.float32), 0, 1)[:, None]
            if cm is None: return c0 * (1 - u) + c1 * u
            cmid = np.array(cm, np.float32)
            return np.where(u < 0.5, c0 * (1 - 2 * u) + cmid * 2 * u, cmid * (2 - 2 * u) + c1 * (2 * u - 1))
        gm = 'rel'
    shadow = L.get('shadow', 0.0)
    rv = L.get('reveal')
    if not rv:
        E.draw_text(f, txt, fp, size, sx, sy, anchor, color, op, blur, grad, -rot, shadow, gm)
        return
    wfull = E.text_w(txt, fp, size)
    xl = sx if anchor == 'l' else (sx - wfull / 2 if anchor == 'c' else sx - wfull)
    t0 = float(rv.get('start', start))
    mode = rv.get('mode', 'words')
    if mode == 'chars':
        step = float(rv.get('step', 0.05))
        n = int(max(0, (t - t0) / max(step, 1e-3)) + 1) if t >= t0 else 0
        if n > 0:
            E.draw_text(f, txt[:n], fp, size, xl, sy, 'l', color, op, blur, grad, 0.0, shadow, gm)
        return
    if mode == 'letters':
        step = float(rv.get('step', 0.045)); wd = max(float(rv.get('dur', 0.4)), 1e-3)
        for i, ch in enumerate(txt):
            if ch == ' ': continue
            ts = t0 + i * step
            u = seg(t, ts, ts + wd)
            if u <= 0: continue
            x = xl + E.text_w(txt[:i], fp, size)
            E.draw_text(f, ch, fp, size, x, sy + (1 - eo3(u)) * size * 0.35, 'l', color, op * sm(u), blur + (1 - u) * 4 * (size / 80.0), None, 0.0, shadow, gm)
        return
    words = txt.split(' ')
    step = float(rv.get('step', 0.3)); wd = max(float(rv.get('dur', 0.28)), 1e-3)
    times = rv.get('times') or []
    for i, w in enumerate(words):
        ts = times[i] if i < len(times) else t0 + i * step
        u = seg(t, ts, ts + wd)
        if u <= 0: continue
        pre = ' '.join(words[:i]) + (' ' if i else '')
        E.draw_text(f, w, fp, size, xl + E.text_w(pre, fp, size), sy, 'l', color, op * sm(u),
                    blur + (1 - u) * 6 * (size / 80.0), grad, 0.0, shadow, gm)

def _load_image(ctx, path):
    if path not in ctx.images:
        full = os.path.normpath(os.path.join(ctx.root, path))
        im = cv2.imread(full, cv2.IMREAD_UNCHANGED)
        if im is None: raise ValueError('cannot read image %s' % path)
        if im.dtype != np.uint8: im = (np.clip(im.astype(np.float32) / (65535.0 if im.dtype == np.uint16 else 1.0), 0, 1) * 255).astype(np.uint8)
        if im.ndim == 2: im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGRA)
        elif im.shape[2] == 3: im = cv2.cvtColor(im, cv2.COLOR_BGR2BGRA)
        im = cv2.cvtColor(im, cv2.COLOR_BGRA2RGBA).astype(np.float32) / 255
        ctx.images[path] = im
    return ctx.images[path]

def _image_window(im, w, h, zoom, pan_x, pan_y, fit):
    """crop/scale an image into a w x h window (Ken Burns style). returns RGBA float (h, w, 4)"""
    ih, iw = im.shape[:2]
    w, h = max(2, int(round(w))), max(2, int(round(h)))
    if fit == 'contain':
        s = min(w / iw, h / ih)
        nw, nh = max(2, int(round(iw * s))), max(2, int(round(ih * s)))
        out = np.zeros((h, w, 4), np.float32)
        rs = cv2.resize(im, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
        y0, x0 = (h - nh) // 2, (w - nw) // 2
        out[y0:y0 + nh, x0:x0 + nw] = rs
        return out
    s = max(w / iw, h / ih) * max(1.0, zoom)                  # source->window scale (>= cover)
    cw, ch = w / s, h / s                                       # crop size in source pixels
    ox, oy = max(0.0, iw - cw), max(0.0, ih - ch)
    x0 = ox * (0.5 + 0.5 * clamp(pan_x, -1, 1)); y0 = oy * (0.5 + 0.5 * clamp(pan_y, -1, 1))
    M = np.float32([[s, 0, -x0 * s], [0, s, -y0 * s]])
    return cv2.warpAffine(im, M, (w, h), flags=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

def _draw_image(f, L, t, sx, sy, k, rot, op, blur, ctx, z):
    if 'path' not in L:
        raise ValueError('image has no path (its search was not resolved)')
    im = _load_image(ctx, L['path'])
    h0, w0 = im.shape[:2]
    w = prop(L, 'w', t, None); h = prop(L, 'h', t, None)
    if w is None: w = h * w0 / h0
    if h is None: h = w * h0 / w0
    w, h = w * k, h * k
    if w < 2 or h < 2 or w > 6000 or h > 6000: return
    win = _image_window(im, w, h, prop(L, 'zoom', t, 1.0), prop(L, 'pan_x', t, 0.0), prop(L, 'pan_y', t, 0.0), L.get('fit', 'cover'))
    a = win[..., 3]
    r = L.get('r')
    if _isnum(r) and r > 0:
        m, _, pw, ph = E.rr_alpha(win.shape[1], win.shape[0], r * k, 0.0, 0, pad=0)
        a = a * cv2.resize(m, (win.shape[1], win.shape[0]))
    tint = parse_color(L['tint']) if 'tint' in L else None
    prgb = (np.array(tint, np.float32) if tint else win[..., :3]) * a[..., None]
    txx, tyy = prop(L, 'tilt_x', t, 0.0), prop(L, 'tilt_y', t, 0.0)
    pa = np.dstack([prgb, a])
    if abs(txx) > 0.1 or abs(tyy) > 0.1 or rot:
        hh, ww = a.shape
        cyw, syw = math.cos(math.radians(tyy)), math.sin(math.radians(tyy))
        cxw, sxw = math.cos(math.radians(txx)), math.sin(math.radians(txx))
        hl, hr = hh / 2 * (1 - 0.11 * syw) * cxw, hh / 2 * (1 + 0.11 * syw) * cxw
        wt, wb = ww / 2 * cyw * (1 - 0.11 * sxw), ww / 2 * cyw * (1 + 0.11 * sxw)
        quad = np.float32([[-wt, -hl], [wt, -hr], [wb, hr], [-wb, hl]])
        cr, sr = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        quad = np.float32([[px * cr - py * sr, px * sr + py * cr] for px, py in quad])
        bx0, by0 = int(np.floor(quad[:, 0].min())) - 4, int(np.floor(quad[:, 1].min())) - 4
        bw_, bh_ = int(np.ceil(quad[:, 0].max())) + 4 - bx0, int(np.ceil(quad[:, 1].max())) + 4 - by0
        if bw_ < 2 or bh_ < 2 or bw_ > 6000 or bh_ > 6000: return
        src = np.float32([[0, 0], [ww, 0], [ww, hh], [0, hh]])
        Mx = cv2.getPerspectiveTransform(src, (quad - np.float32([bx0, by0])).astype(np.float32))
        pa = cv2.warpPerspective(pa, Mx, (bw_, bh_), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        off_x, off_y = bx0 + 0.0, by0 + 0.0
        ox0, oy0 = sx + off_x, sy + off_y
    else:
        ox0, oy0 = sx - pa.shape[1] / 2, sy - pa.shape[0] / 2
    prgb, a = np.ascontiguousarray(pa[..., :3]), np.ascontiguousarray(pa[..., 3])
    if blur > 0.3:
        pb = cv2.GaussianBlur(np.dstack([prgb, a]), (0, 0), blur)
        prgb, a = np.ascontiguousarray(pb[..., :3]), np.ascontiguousarray(pb[..., 3])
    if L.get('shadow', 0) > 0:
        sb = L.get('shadow_blur', 24) * z
        pad = int(sb * 3)
        sa = cv2.GaussianBlur(cv2.copyMakeBorder(a, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0), (0, 0), max(sb, 0.5)) * L['shadow']
        E.over(f, np.zeros(sa.shape + (3,), np.float32), sa, ox0 - pad, oy0 - pad + L.get('shadow_dy', 14) * z, op)
    E.over(f, prgb, a, ox0, oy0, op)

def setup(spec):
    """select the canvas size named in the spec (module-wide)"""
    key = E.norm_size(spec.get('size', '16:9')) or '16:9'
    if E.canvas_key() != key: E.set_size(key)
    return E.W, E.H

def render_frame(spec, t, ctx):
    setup(spec)
    f = background(spec, t).astype(np.float32)
    cam = camera_at(spec, t)
    light = bg_light(spec, t)
    dur = float(spec['duration'])
    for i, L in enumerate(spec['layers'][:MAX_LAYERS]):
        E.QA_LAYER = i
        try:
            draw_layer(f, spec, L, t, cam, light, ctx, dur)
        except Exception as ex:   # never kill the whole render because of one layer
            ctx.warn('layers[%d] (%s) failed: %s: %s' % (i, L.get('type'), type(ex).__name__, ex))
    return (np.clip(f, 0, 1) * 255 + 0.5).astype(np.uint8)


# ------------------------------------------------------------------ never fail: repair or replace
def salvage(spec, root='.'):
    """Repair what can be repaired: drop layers that do not validate, reset a bad background / camera / fps / size.
    -> (spec, notes) or (None, notes) when nothing usable is left."""
    notes = []
    if not isinstance(spec, dict): return None, ['not an object']
    sp = json.loads(json.dumps(spec))
    if not _isnum(sp.get('duration')) or not (0.5 <= sp['duration'] <= MAX_DURATION): sp['duration'] = 8.0; notes.append('duration reset')
    if 'size' in sp and E.norm_size(sp['size']) is None: sp.pop('size'); notes.append('size removed')
    if sp.get('fps', 30) not in (24, 25, 30, 60): sp.pop('fps', None); notes.append('fps removed')
    bg = sp.get('background', 'dark_aurora')
    if any((not isinstance(k, dict) or k.get('style') not in E.BG_STYLES or not _isnum(k.get('t', 0))) for k in _bg_keys_raw(bg)):
        sp['background'] = 'dark_aurora'; notes.append('background reset')
    errs, _ = validate(sp, root)
    if any('camera' in e for e in errs): sp.pop('camera', None); notes.append('camera removed')
    layers = sp.get('layers') if isinstance(sp.get('layers'), list) else []
    layers = layers[:MAX_LAYERS]
    keep = []
    for i, L in enumerate(layers):
        if _validate_layer(i, L, sp['duration'], root, []): notes.append('layer %d dropped' % i)
        else: keep.append(L)
    if not keep: return None, notes + ['no valid layer left']
    sp['layers'] = keep
    errs, _ = validate(sp, root)
    if errs: return None, notes + errs[:3]
    return sp, notes


def fallback_spec(title, duration=8.0, size='16:9'):
    """a simple, always valid title video (used only when the AI never produced a usable design)"""
    W, H = E.SIZES[E.norm_size(size) or '16:9']
    d = float(duration)
    txt = re.sub(r'\s+', ' ', str(title or 'Video')).strip()[:60] or 'Video'
    sp = {'title': txt, 'duration': d, 'size': E.norm_size(size) or '16:9', 'fps': 30, 'background': 'dark_aurora',
          'layers': [{'type': 'particles', 'count': 60, 'color': [1, 1, 1], 'size': 3, 'speed': 0.9, 'seed': 5, 'start': 0, 'end': d},
                     {'type': 'text', 'text': txt, 'x': W // 2, 'y': H // 2, 'size': 96 if W >= H else 80, 'color': '#FFFFFF', 'start': 0.3, 'end': d}]}
    errs, _ = validate(sp, '.')
    if errs: raise ValueError('fallback spec invalid: ' + '; '.join(errs[:3]))
    return sp
