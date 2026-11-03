"""Design library: 100+ ready designs (narration script + storyboard + working spec) that the bot studies before it designs.

  load()                      all designs (library/designs.json)
  search(text, k)             the k most relevant, varied designs for a brief
  relevant_block(text)        text for the AI prompt: few-shot designs (script + storyboard + compact spec)
  rules()                     how to INVENT a new design from what the library teaches
  catalog()                   one line per design (so the AI knows what exists)
  spec_of(id)                 the renderable spec of a design
"""
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE = {}
SYN = {
    'space': ['space', 'cosmos', 'galaxy', 'planet', 'planets', 'moon', 'mars', 'star', 'stars', 'rocket', 'universe', 'nasa', 'orbit', 'solar', 'astronomy'],
    'history': ['history', 'historical', 'ancient', 'empire', 'rome', 'roman', 'king', 'war', 'civilization', 'silk', 'egypt', 'pyramid', 'medieval', 'past'],
    'ocean': ['ocean', 'sea', 'marine', 'whale', 'deep', 'water', 'fish', 'wave'],
    'nature': ['nature', 'forest', 'animal', 'plant', 'wildlife', 'earth', 'climate', 'amazon', 'seed', 'tree'],
    'science': ['science', 'biology', 'cell', 'atom', 'body', 'physics', 'chemistry', 'dna', 'evolution'],
    'technology': ['technology', 'tech', 'computer', 'chip', 'internet', 'ai', 'robot', 'code', 'web'],
    'economy': ['economy', 'money', 'trade', 'market', 'energy', 'business', 'finance'],
    'saas': ['saas', 'app', 'software', 'dashboard', 'ui', 'product', 'startup', 'website', 'landing', 'pricing', 'feature', 'notification', 'settings', 'onboarding', 'chat'],
}
DOC_WORDS = {'documentary', 'documentry', 'story', 'history', 'explainer', 'educational', 'narration', 'voiceover', 'script', 'episode'}

def _tok(s): return re.findall(r'[a-z0-9]+', (s or '').lower())

def load(root=ROOT):
    if root in _CACHE: return _CACHE[root]
    p = os.path.join(root, 'library', 'designs.json')
    ds = json.load(open(p, encoding='utf-8'))['designs'] if os.path.exists(p) else []
    _CACHE[root] = ds; return ds

def spec_of(did, root=ROOT):
    p = os.path.join(root, 'library', 'specs', did + '.json')
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else None

def _score(d, words):
    hay = set(_tok(' '.join([d['title'], d['topic'], ' '.join(d['tags']), d['idea'], d['when'], d['archetype'], d['category']] + [x['text'] for x in d['script']])))
    sc = 0.0
    for w in words:
        if w in hay: sc += 1.0
    for grp, ws in SYN.items():
        if words & set(ws):
            if d['topic'] == grp or grp in d['tags']: sc += 2.0
            if grp == 'saas' and d['category'] == 'saas': sc += 2.0
    if words & DOC_WORDS and d['category'] == 'documentary': sc += 1.5
    return sc

def search(text, k=4, root=ROOT, category=None):
    ds = load(root)
    if not ds: return []
    words = set(_tok(text))
    ranked = sorted(ds, key=lambda d: (-_score(d, words), d['id']))
    out, seen = [], set()
    for d in ranked:                              # variety: one design per archetype first
        if category and d['category'] != category: continue
        if d['archetype'] in seen: continue
        seen.add(d['archetype']); out.append(d)
        if len(out) >= k: break
    return out

def compact(spec):
    return json.dumps(spec, separators=(',', ':'), ensure_ascii=False)

def story_text(d):
    lines = ['DESIGN "%s" (%s | %s | %.1fs | sound: %s)' % (d['id'], d['title'], d['category'], d['duration'], d['sound']),
             'IDEA: %s. USE WHEN: %s.' % (d['idea'], d['when']),
             'NARRATION (time -> what the voice says; the visuals appear exactly then):']
    lines += ['  %.1fs  "%s"' % (x['t'], x['text']) for x in d['script']]
    lines.append('STORYBOARD (time -> what appears):')
    for sh in d['storyboard']:
        lines.append('  %.1fs  ' % sh['t'] + '; '.join('%s [%s]' % (i['what'], i['anim']) for i in sh['items']))
    return '\n'.join(lines)

def relevant_block(text, k=3, root=ROOT, with_spec=True):
    ds = search(text, k, root)
    if not ds: return ''
    parts = []
    for d in ds:
        s = story_text(d)
        if with_spec:
            sp = spec_of(d['id'], root)
            if sp: s += '\nSPEC:\n' + compact(sp)
        parts.append(s)
    return ('\n=== DESIGN LIBRARY: %d ready designs similar to this brief (study how the narration, the storyboard and the layers match in time; '
            'do NOT copy them - design something NEW in their spirit) ===\n' % len(ds) + '\n\n'.join(parts) + '\n')

def catalog(root=ROOT):
    ds = load(root)
    return '\n'.join('%s | %s | %s' % (d['id'], d['title'], d['topic']) for d in ds)

def rules():
    return ('\n=== HOW TO USE THE DESIGN LIBRARY AND INVENT NEW DESIGNS ===\n'
            '1. A documentary or explainer is a chain of SCENES (about 5-9 seconds each). Each scene has one idea, one narrated sentence group and one visual pattern '
            '(title hero, archival photo, timeline, big stat, map pings, quote, compare, steps, chart, flow, orbit, chapter, fact cards, year ticker, icon grid, glitch jump, outro, kinetic statement; '
            'for SaaS: device showcase, toggles, toasts, KPI dashboard, AI prompt bar, pricing, loading-success, onboarding, command palette, chat, feature trio).\n'
            '2. Narration and visuals are locked together: whatever the voice names appears on that second (the number counts up while it is said, the pin pings when the place is named).\n'
            '3. To make a NEW design, do not copy one: combine two or three patterns, change the layout (left/right, grid/row), the colour theme, the background style, the animation family '
            '(slide / pop / zoom / wipe / rise), the camera drift and the transition, and rewrite everything for the topic. Never reuse the same pattern twice in a row.\n'
            '4. Alternate dense scenes (cards, charts) with calm scenes (one photo, one number, one sentence). Use transitions (wipe, iris, stripes, flash, glitch) only on scene changes.\n'
            '5. Keep text short, big and inside the canvas; keep at least 120 px margins; one focal point per moment.\n'
            '6. Only state well-known facts for documentaries; when unsure, stay general instead of inventing numbers.\n'
            '7. Return the spec JSON; if the brief is a documentary, also put the narration in "script": [{"t": seconds, "text": sentence}] (extra field, ignored by the renderer).\n')
