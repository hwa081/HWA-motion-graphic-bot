"""mgl.remix - invent NEW designs from old ones (no AI, no API quota).

  fingerprint(spec)            what a design is made of (backgrounds, animations, transitions, layout, colours, texts)
  similarity(fpA, fpB)         0..1, how alike two designs look
  novelty(spec, root, mem)     is this spec too close to a library / remembered design? (so the bot never just copies)
  make_recipe(prompt, ...)     a REMIX RECIPE: ideas borrowed from 2-3 old designs + deliberate mutations
                               (new backgrounds, animation family, transitions, layout twist, pacing) that the
                               designs of the last videos did NOT use. The AI gets it in its prompt.
"""
import hashlib, json, math, os, random, re
from collections import Counter

from . import library as LB
from . import spec as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FP_CACHE = {}

TOO_CLOSE = 0.80          # similarity at which a design counts as a copy
MIN_LAYERS_FOR_GATE = 6   # tiny specs are never flagged

LAYOUT_TWISTS = [
    'mirror the layout: if the old one put text left and visual right, do the opposite',
    'replace the row of items by a vertical stack (or the stack by a row)',
    'make ONE hero element 2x bigger and shrink everything else to supporting size',
    'use a 3-item grid instead of a fan / list, with a different item entering first',
    'centre everything on one axis and let a single accent element break the symmetry',
    'push the main text to the lower third and give the visual the whole frame',
    'split the frame in two halves (before/after or text/visual) with a moving divider',
    'start extremely close (macro) and pull back to reveal the whole layout',
    'stagger items on a diagonal instead of a straight line',
]
PACING_TWISTS = [
    'faster: shorter scenes (about 2-3 s) with a transition on every cut',
    'calmer: fewer, longer scenes (5-7 s) with slow camera drift and big empty space',
    'rhythmic: alternate one fast scene and one slow scene',
    'build-up: start slow and add speed and density towards the end, finish with one calm closing frame',
]
CAMERAS = ['slow push-in during every scene', 'pull-out reveal at the start', 'small push-in + a bigger move at scene changes', 'gentle drift (pan) with a final push-in']


def _tok(s): return re.findall(r'[a-z0-9]+', str(s).lower())


def _bg_styles(spec):
    bg = spec.get('background', 'dark_aurora')
    if isinstance(bg, str): return {bg}
    return {k.get('style') for k in (bg if isinstance(bg, list) else [bg]) if isinstance(k, dict) and k.get('style')}


def _anim(L):
    v = L.get('in')
    a = v if isinstance(v, str) else (v.get('anim') if isinstance(v, dict) else None)
    return a if a and a != 'none' else None


def _hue_bucket(c):
    r, g, b = c
    mx, mn = max(c), min(c)
    d = mx - mn
    light = 'dark' if mx < 0.35 else ('light' if mn > 0.75 else 'mid')
    if d < 0.12: return 'gray-' + light
    if mx == r: h = ((g - b) / d) % 6
    elif mx == g: h = (b - r) / d + 2
    else: h = (r - g) / d + 4
    return 'h%d-%s' % (int(h * 2) % 12, light)


def fingerprint(spec):
    layers = [L for L in (spec.get('layers') or []) if isinstance(L, dict)]
    types, anims, trans, pal, texts = Counter(), Counter(), set(), Counter(), set()
    for L in layers:
        ty = L.get('type')
        if ty == 'transition':
            if L.get('style'): trans.add(L['style'])
            continue
        types[ty + (':' + str(L['kind']) if L.get('kind') and ty in ('card', 'chart', 'device', 'progress') else '')] += 1
        a = _anim(L)
        if a: anims[a] += 1
        for key in ('color', 'color2', 'grad_from', 'grad_to', 'fill'):
            if key in L:
                c = S.parse_color(L[key])
                if c: pal[_hue_bucket(c)] += 1
        if ty == 'text' and isinstance(L.get('text'), str):
            t = ' '.join(_tok(L['text']))
            if len(t) >= 6: texts.add(t)
    return {'bg': _bg_styles(spec), 'anims': anims, 'trans': trans, 'types': types, 'pal': pal, 'texts': texts,
            'camera': bool(spec.get('camera')), 'n': len(layers), 'dur': float(spec.get('duration') or 0)}


def _jac(a, b):
    a, b = set(a), set(b)
    if not a and not b: return 1.0
    return len(a & b) / len(a | b)


def _cos(a, b):
    if not a and not b: return 1.0
    if not a or not b: return 0.0
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    na = math.sqrt(sum(v * v for v in a.values())); nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def similarity(a, b):
    s = (0.20 * _jac(a['bg'], b['bg']) + 0.20 * _cos(a['anims'], b['anims']) + 0.10 * _jac(a['trans'], b['trans'])
         + 0.25 * _cos(a['types'], b['types']) + 0.15 * _cos(a['pal'], b['pal']) + 0.10 * (1.0 if a['camera'] == b['camera'] else 0.0))
    return round(s, 3)


def library_fingerprints(root=ROOT):
    """fingerprints of all library designs: {id: fp}"""
    if root in _FP_CACHE: return _FP_CACHE[root]
    out = {}
    d = os.path.join(root, 'library', 'specs')
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            if fn.endswith('.json'):
                try: out[fn[:-5]] = fingerprint(json.load(open(os.path.join(d, fn), encoding='utf-8')))
                except Exception: pass
    _FP_CACHE[root] = out
    return out


def _memory_fingerprints(mem, n=30):
    out = {}
    if mem is None: return out
    for d in mem.designs[-n:]:
        sp = mem.spec_of(d['id'])
        if isinstance(sp, dict): out[d['id']] = fingerprint(sp)
    return out


def novelty(spec, root=ROOT, mem=None):
    """how original is this spec? -> dict(nearest, similarity, copied_texts, too_close, problems[])"""
    fp = fingerprint(spec)
    best = (None, 0.0, None)
    for src, pool in (('library', library_fingerprints(root)), ('memory', _memory_fingerprints(mem))):
        for did, f in pool.items():
            s = similarity(fp, f)
            if s > best[1]: best = (did, s, src)
    copied = []
    nearest_fp = (library_fingerprints(root).get(best[0]) or _memory_fingerprints(mem).get(best[0])) if best[0] else None
    pools = list(library_fingerprints(root).items()) + list(_memory_fingerprints(mem).items())
    shared_best, shared_id = [], None
    for did, f in pools:
        sh = sorted(fp['texts'] & f['texts'])
        if len(sh) > len(shared_best): shared_best, shared_id = sh, did
    copied = shared_best if len(shared_best) >= 3 else []
    gate = fp['n'] >= MIN_LAYERS_FOR_GATE
    too_close = bool(gate and best[0] and best[1] >= TOO_CLOSE)
    problems = []
    if too_close:
        nf = nearest_fp or {}
        keep_bg = ', '.join(sorted(fp['bg'] & nf.get('bg', set())))
        problems.append('Originality: this design is %.0f%% identical to %s design "%s" (same%s layout mix and animations). Do not copy: change the background styles%s, '
                        'use a different animation family, different transitions, and rebuild the layout (swap layout, scale hierarchy, camera move).' % (
                            best[1] * 100, best[2], best[0], ' backgrounds (%s),' % keep_bg if keep_bg else '', ' (not %s)' % keep_bg if keep_bg else ''))
    if gate and copied:
        problems.append('Originality: %d text lines are copied word for word from design "%s" (%s). Write new text for this brief.' % (
            len(copied), shared_id, '; '.join(c[:30] for c in copied[:3])))
    return {'nearest': best[0], 'source': best[2], 'similarity': best[1], 'copied_texts': copied, 'too_close': too_close or bool(gate and copied), 'problems': problems}


# ------------------------------------------------------------------ recipes
def _recent_choices(mem, n=3):
    bgs, anims, trans = Counter(), Counter(), Counter()
    for d in (mem.designs[-n:] if mem is not None else []):
        sm = d.get('summary') or {}
        for b in sm.get('backgrounds') or []:
            if b: bgs[b] += 1
        for a in (sm.get('entrance_anims') or {}): anims[a] += 1
        for t in sm.get('transitions') or []: trans[t] += 1
    return bgs, anims, trans


def _pick(rng, pool, avoid, k):
    fresh = [x for x in pool if x not in avoid]
    rng.shuffle(fresh)
    out = fresh[:k]
    if len(out) < k:
        rest = [x for x in pool if x not in out]; rng.shuffle(rest); out += rest[:k - len(out)]
    return out


def make_recipe(prompt, root=ROOT, mem=None, duration=10, size='16:9', k_sources=3, seed=None):
    """-> dict(sources=[design ids], mutations={...}, text=str). Deterministic for the same (prompt, memory state, seed)."""
    from . import engine as E
    n_mem = len(mem.designs) if mem is not None else 0
    s = seed if seed is not None else int(hashlib.sha1(('%s|%d' % (prompt, n_mem)).encode()).hexdigest()[:8], 16)
    rng = random.Random(s)
    srcs = LB.search(prompt, max(k_sources + 2, 5), root)
    rng.shuffle(srcs)
    chosen, seen = [], set()
    for d in sorted(srcs[:k_sources + 2], key=lambda d: d['archetype']):
        if d['archetype'] in seen: continue
        seen.add(d['archetype']); chosen.append(d)
        if len(chosen) >= k_sources: break
    bgs_recent, anims_recent, trans_recent = _recent_choices(mem)
    bgs = _pick(rng, sorted(E.BG_STYLES), set(bgs_recent), 2)
    anim_pool = [a for a in S.ANIMS if a not in ('none', 'fade')]
    anims = _pick(rng, anim_pool, set(anims_recent), 4)
    trans = _pick(rng, list(S.TRANSITIONS), set(trans_recent), 2)
    twists = rng.sample(LAYOUT_TWISTS, 2)
    pacing = rng.choice(PACING_TWISTS)
    camera = rng.choice(CAMERAS)
    scenes = max(2, int(round(float(duration) / (2.5 if 'faster' in pacing else (6 if 'calmer' in pacing else 4)))))
    liked = []
    if mem is not None:
        liked = [d for d in mem.designs if (d.get('rating') or 0) >= 4][-1:]
    lines = ['=== REMIX RECIPE (an invention plan made from old designs; follow it so this video is NEW, not a copy) ===']
    lines.append('BORROW IDEAS (structure and feeling only, never their text or exact layout):')
    for d in chosen:
        lines.append('- %s "%s": take its %s idea - %s' % (d['id'], d['title'], d['archetype'].replace('_', ' '), d['idea']))
    for d in liked:
        sm = d.get('summary') or {}
        lines.append('- a video the user rated highly ("%s"): keep what made it good (%s)' % (d['prompt'][:70], ', '.join(str(x) for x in (sm.get('kinds') or sm.get('transitions') or ['its pacing']))[:80]))
    lines.append('MUTATE (these choices differ from your last videos on purpose):')
    lines.append('- background styles: %s (change between scenes with a fade)' % ' -> '.join(bgs))
    lines.append('- entrance animation family: %s' % ', '.join(anims))
    lines.append('- transitions at scene changes: %s' % ', '.join(trans))
    lines.append('- layout twist 1: %s' % twists[0])
    lines.append('- layout twist 2: %s' % twists[1])
    lines.append('- pacing: %s (about %d scenes for %ss)' % (pacing, scenes, duration))
    lines.append('- camera: %s' % camera)
    lines.append('Combine the borrowed ideas into ONE coherent new story; write all text fresh for the brief. If the brand kit or a reference video fixes colours, backgrounds or pacing, those win over this recipe.')
    return {'sources': [d['id'] for d in chosen], 'mutations': {'backgrounds': bgs, 'anims': anims, 'transitions': trans, 'twists': twists, 'pacing': pacing, 'camera': camera, 'scenes': scenes},
            'text': '\n'.join(lines) + '\n'}


def describe(recipe):
    return recipe['text']
