"""mgl.memory - what the bot remembers between runs (plain JSON files in the repo's memory/ folder).

memory/brand.json       brand kit written by the user (name, colours, logo ...)
memory/designs.json     one card per generated video (what was used, scores, rating, notes)
memory/specs/<id>.json  the full spec of recent / well-rated designs
memory/lessons.json     distilled rules: DO / DON'T with weights ("what was better, what was wrong")
memory/styles.json      style cards learned from reference videos
memory/style_guide.md   synthesis written after analysing several reference videos
memory/assets.json      which library image / icon was chosen for which search (and why)
memory/notebook.json    techniques the bot learned (from references, comparisons, studied text) and a wishlist of effects it lacks
memory/learning_log.md  human-readable history, newest last
The GitHub workflow commits this folder back to the repo after every run.
"""
import datetime, hashlib, json, os, re, random
from collections import Counter

MAX_DESIGNS = 80
MAX_SPECS = 30
MAX_STYLES = 40
MAX_LESSONS = 60
MAX_TECHNIQUES = 60
MAX_WISHES = 30
BRAND_TEMPLATE = {
    "name": "", "tagline": "",
    "colors": {"primary": "", "secondary": "", "accent": "", "dark": "", "light": ""},
    "fonts": {"headline": "bold_italic", "body": "medium_italic"},
    "logo": "", "voice": "", "always": [], "never": []
}


def now_iso():
    return datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


def _words(s):
    return {w for w in re.findall(r'[a-z0-9]+', str(s).lower()) if len(w) > 3}


def _norm(s):
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', str(s).lower())).strip()


def _jacc(a, b):
    a, b = _words(a), _words(b)
    return len(a & b) / max(1, len(a | b))


def summarize_spec(spec):
    """compact description of the design choices in a spec (no AI needed)"""
    layers = [L for L in spec.get('layers', []) if isinstance(L, dict)]
    bg = spec.get('background', 'dark_aurora')
    styles = [bg] if isinstance(bg, str) else [k.get('style') for k in (bg if isinstance(bg, list) else [bg]) if isinstance(k, dict)]
    ins = Counter()
    for L in layers:
        v = L.get('in')
        a = v if isinstance(v, str) else (v.get('anim') if isinstance(v, dict) else None)
        if a and a != 'none': ins[a] += 1
    types = Counter(L.get('type') for L in layers)
    kinds = sorted({str(L.get('kind')) for L in layers if L.get('kind') and L.get('type') in ('card', 'chart', 'device', 'progress')})
    trans = sorted({L.get('style') for L in layers if L.get('type') == 'transition'})
    heads = [L['text'] for L in sorted(layers, key=lambda L: -float(L.get('size', 0) or 0)) if L.get('type') == 'text' and isinstance(L.get('text'), str)][:4]
    return {
        'backgrounds': styles, 'entrance_anims': dict(ins.most_common(8)), 'layer_types': dict(types.most_common(10)), 'kinds': kinds,
        'transitions': trans, 'camera': bool(spec.get('camera')), 'headlines': heads, 'layers': len(layers),
        'duration': spec.get('duration'), 'size': spec.get('size', '16:9')}


class Memory:
    def __init__(self, root='.'):
        self.root = root
        self.dir = os.path.join(root, 'memory')
        os.makedirs(os.path.join(self.dir, 'specs'), exist_ok=True)
        self.brand = self._load('brand.json', None)
        self.designs = self._load('designs.json', [])
        self.lessons = self._load('lessons.json', [])
        self.styles = self._load('styles.json', [])
        self.assets = self._load('assets.json', {})
        self.notebook = self._load('notebook.json', {})
        if not isinstance(self.notebook, dict): self.notebook = {}
        self.notebook.setdefault('techniques', []); self.notebook.setdefault('wishes', [])
        if not isinstance(self.notebook['techniques'], list): self.notebook['techniques'] = []
        if not isinstance(self.notebook['wishes'], list): self.notebook['wishes'] = []
        if not isinstance(self.designs, list): self.designs = []
        if not isinstance(self.lessons, list): self.lessons = []
        if not isinstance(self.styles, list): self.styles = []
        if not isinstance(self.assets, dict): self.assets = {}

    # ---------------------------------------------------------------- io
    def _path(self, name): return os.path.join(self.dir, name)

    def _load(self, name, default):
        p = self._path(name)
        if not os.path.exists(p): return default
        try:
            with open(p, encoding='utf-8') as f: return json.load(f)
        except Exception:
            try: os.replace(p, p + '.bad')       # keep the broken file, start clean
            except OSError: pass
            return default

    def _dump(self, name, obj):
        tmp = self._path(name) + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f: json.dump(obj, f, indent=1, ensure_ascii=False)
        os.replace(tmp, self._path(name))

    def save(self):
        self._prune()
        self._dump('designs.json', self.designs)
        self._dump('lessons.json', self.lessons)
        self._dump('styles.json', self.styles)
        self._dump('assets.json', self.assets)
        if self.notebook['techniques'] or self.notebook['wishes'] or os.path.exists(self._path('notebook.json')):
            self._dump('notebook.json', self.notebook)
        if self.brand is None and not os.path.exists(self._path('brand.json')):
            self._dump('brand.json', BRAND_TEMPLATE)

    def _prune(self):
        if len(self.designs) > MAX_DESIGNS:
            self.designs = self.designs[-MAX_DESIGNS:]
        keep = {d['id'] for d in self.designs[-MAX_SPECS:]} | {d['id'] for d in self.designs if (d.get('rating') or 0) >= 4}
        sp_dir = os.path.join(self.dir, 'specs')
        for fn in os.listdir(sp_dir):
            if fn.endswith(('.json', '.py')) and fn.rsplit('.', 1)[0] not in keep:
                try: os.remove(os.path.join(sp_dir, fn))
                except OSError: pass
        if len(self.styles) > MAX_STYLES: self.styles = self.styles[-MAX_STYLES:]
        nb = self.notebook
        if len(nb['techniques']) > MAX_TECHNIQUES:
            nb['techniques'] = sorted(nb['techniques'], key=lambda t: t.get('weight', 1) * (1 + 0.3 * t.get('count', 1)), reverse=True)[:MAX_TECHNIQUES]
        if len(nb['wishes']) > MAX_WISHES:
            nb['wishes'] = sorted(nb['wishes'], key=lambda w: (w.get('done', False), -w.get('count', 1)))[:MAX_WISHES]
        if len(self.lessons) > MAX_LESSONS:
            self.lessons = sorted(self.lessons, key=lambda l: (l.get('weight', 1) * (1 + 0.3 * l.get('count', 1))), reverse=True)[:MAX_LESSONS]

    # ---------------------------------------------------------------- brand
    def brand_kit(self):
        b = self.brand if isinstance(self.brand, dict) else None
        if not b: return None
        colors = {k: v for k, v in (b.get('colors') or {}).items() if isinstance(v, str) and re.fullmatch(r'#?[0-9a-fA-F]{6}', v.strip())}
        out = {k: b.get(k) for k in ('name', 'tagline', 'logo', 'voice', 'always', 'never') if b.get(k)}
        if colors: out['colors'] = {k: ('#' + v.strip().lstrip('#')) for k, v in colors.items()}
        if isinstance(b.get('fonts'), dict) and b['fonts']: out['fonts'] = b['fonts']
        return out or None

    # ---------------------------------------------------------------- designs
    def add_design(self, prompt, spec, qa_report=None, review_score=None, extra=None):
        did = 'd-%s-%04x' % (datetime.datetime.utcnow().strftime('%Y%m%d-%H%M'), random.randrange(65536))
        card = {'id': did, 'date': now_iso(), 'prompt': prompt[:400], 'summary': summarize_spec(spec), 'review_score': review_score,
                'qa_errors': len((qa_report or {}).get('errors', [])), 'qa_warnings': len((qa_report or {}).get('warnings', [])),
                'rating': None, 'notes': []}
        if extra: card.update(extra)
        self.designs.append(card)
        with open(os.path.join(self.dir, 'specs', did + '.json'), 'w', encoding='utf-8') as f: json.dump(spec, f, indent=1, ensure_ascii=False)
        return did

    def add_code_design(self, prompt, scene_src, notes, size, duration, qa_report=None, extra=None):
        """a design made by code mode: the scene source is kept next to the card"""
        did = 'c-%s-%04x' % (datetime.datetime.utcnow().strftime('%Y%m%d-%H%M'), random.randrange(65536))
        card = {'id': did, 'date': now_iso(), 'prompt': prompt[:400], 'summary': {'mode': 'code', 'notes': str(notes)[:300], 'size': size, 'duration': duration, 'lines': scene_src.count('\n') + 1},
                'review_score': None, 'qa_errors': len((qa_report or {}).get('errors', [])), 'qa_warnings': len((qa_report or {}).get('warnings', [])), 'rating': None, 'notes': []}
        if extra: card.update(extra)
        self.designs.append(card)
        with open(os.path.join(self.dir, 'specs', did + '.py'), 'w', encoding='utf-8') as f: f.write(scene_src)
        return did

    def design(self, did):
        for d in self.designs:
            if d['id'] == did: return d
        return None

    def latest_design_id(self):
        return self.designs[-1]['id'] if self.designs else None

    def spec_of(self, did):
        p = os.path.join(self.dir, 'specs', did + '.json')
        if os.path.exists(p):
            try: return json.load(open(p, encoding='utf-8'))
            except Exception: return None
        return None

    def set_feedback(self, did, rating, note):
        d = self.design(did)
        if not d: raise KeyError('design %s not found' % did)
        if rating is not None: d['rating'] = int(rating)
        if note: d.setdefault('notes', []).append({'date': now_iso(), 'note': note[:500]})
        return d

    # ---------------------------------------------------------------- lessons
    def add_lessons(self, items, source='auto'):
        """items: list of {'kind': 'do'|'dont', 'text': str, 'weight': 1-3}; similar lessons are merged and gain weight"""
        added = 0
        for it in items or []:
            text = str(it.get('text', '')).strip()
            kind = 'dont' if str(it.get('kind', 'do')).lower().startswith('dont') or str(it.get('kind')).lower() in ("don't", 'avoid') else 'do'
            if len(text) < 8: continue
            w = max(1, min(3, int(it.get('weight', 1) or 1)))
            hit = next((l for l in self.lessons if l['kind'] == kind and (_norm(l['text']) == _norm(text) or _jacc(l['text'], text) > 0.7)), None)
            if hit:
                hit['count'] = hit.get('count', 1) + 1; hit['weight'] = min(5, max(hit.get('weight', 1), w) + (1 if hit['count'] % 3 == 0 else 0)); hit['last'] = now_iso()
            else:
                self.lessons.append({'id': 'l%d' % (len(self.lessons) + 1 + random.randrange(1000)), 'kind': kind, 'text': text[:300], 'weight': w, 'count': 1,
                                     'source': source, 'created': now_iso(), 'last': now_iso()}); added += 1
        return added

    def top_lessons(self, n=14):
        ranked = sorted(self.lessons, key=lambda l: l.get('weight', 1) * (1 + 0.3 * l.get('count', 1)), reverse=True)
        return ranked[:n]

    def consolidate_lessons(self, ask, target=25, threshold=40):
        """ask(system, contents) -> JSON text. Merges duplicates when the list grows too long. Returns True if rewritten."""
        if len(self.lessons) <= threshold: return False
        payload = json.dumps([{'kind': l['kind'], 'text': l['text'], 'weight': l.get('weight', 1)} for l in self.lessons], ensure_ascii=False)
        txt = ask('You maintain a list of design rules for a motion-graphics bot. Answer with JSON only.',
                  [{'role': 'user', 'parts': [{'text': 'Merge duplicates and near-duplicates, keep the most important and specific rules, drop vague ones. '
                                                        'Return JSON {"lessons":[{"kind":"do"|"dont","text":"...","weight":1-5}]} with at most %d items.\n%s' % (target, payload)}]}])
        from . import gemini
        data = gemini.extract_json(txt)
        items = data.get('lessons') if isinstance(data, dict) else None
        if not items: return False
        new = []
        for it in items[:target]:
            if isinstance(it, dict) and len(str(it.get('text', ''))) >= 8:
                new.append({'id': 'l%d' % (len(new) + 1), 'kind': 'dont' if str(it.get('kind', '')).startswith('dont') else 'do', 'text': str(it['text'])[:300],
                            'weight': max(1, min(5, int(it.get('weight', 1) or 1))), 'count': 1, 'source': 'consolidated', 'created': now_iso(), 'last': now_iso()})
        if len(new) < 5: return False
        self.lessons = new
        return True

    # ---------------------------------------------------------------- styles (from reference videos)
    def has_source(self, sha):
        return any(s.get('sha') == sha for s in self.styles)

    def add_style(self, card):
        card = dict(card); card.setdefault('id', 's-%04x' % random.randrange(65536)); card.setdefault('date', now_iso())
        for t in card.get('techniques') or []:                  # the tricks of a reference video go to the notebook
            if isinstance(t, dict): self.add_technique(t, source='reference: ' + str(card.get('title', ''))[:40])
        self.styles.append(card)
        return card['id']

    def relevant_styles(self, prompt, n=3):
        pw = _words(prompt)
        def score(s):
            tags = _words(' '.join([str(s.get('title', '')), ' '.join(map(str, s.get('tags', []))), str(s.get('notes', ''))]))
            return (len(pw & tags), (s.get('rating') or 0), s.get('date', ''))
        return sorted(self.styles, key=score, reverse=True)[:n]

    def style_guide(self):
        p = self._path('style_guide.md')
        if os.path.exists(p):
            try: return open(p, encoding='utf-8').read()
            except Exception: return ''
        return ''

    def write_style_guide(self, text):
        with open(self._path('style_guide.md'), 'w', encoding='utf-8') as f: f.write(text.strip() + '\n')

    # ---------------------------------------------------------------- notebook (techniques + wishlist)
    def add_technique(self, t, source='auto'):
        """t: {name, when, how, spec(optional dict with layers)}. Similar techniques are merged (weight grows). True if new."""
        name = str(t.get('name', '')).strip()[:60]; how = str(t.get('how', '')).strip()[:320]
        if len(name) < 3 or len(how) < 12: return False
        for x in self.notebook['techniques']:
            if _norm(x['name']) == _norm(name) or _jacc(x['name'] + ' ' + x['how'], name + ' ' + how) > 0.6:
                x['count'] = x.get('count', 1) + 1; x['weight'] = min(5, x.get('weight', 1) + (1 if x['count'] % 2 == 0 else 0)); x['last'] = now_iso()
                if t.get('spec') and not x.get('spec'): x['spec'] = t['spec']
                return False
        card = {'id': 't%d' % (len(self.notebook['techniques']) + 1 + random.randrange(1000)), 'name': name, 'when': str(t.get('when', ''))[:160], 'how': how,
                'source': str(source)[:60], 'weight': 1, 'count': 1, 'created': now_iso(), 'last': now_iso()}
        if isinstance(t.get('spec'), dict): card['spec'] = t['spec']
        self.notebook['techniques'].append(card)
        return True

    def techniques_for(self, prompt, n=4):
        pw = _words(prompt)
        def score(t):
            return (len(pw & _words(t['name'] + ' ' + t.get('when', '') + ' ' + t['how'])) * 2 + t.get('weight', 1), t.get('last', ''))
        return sorted(self.notebook['techniques'], key=score, reverse=True)[:n]

    def add_wish(self, text, source='planner'):
        """an effect / technique the bot wanted but the library cannot do. Counted, so the most wanted ones are built first."""
        text = str(text).strip()[:200]
        if len(text) < 6: return False
        for w in self.notebook['wishes']:
            if _norm(w['text']) == _norm(text) or _jacc(w['text'], text) > 0.6:
                w['count'] = w.get('count', 1) + 1; w['last'] = now_iso(); return False
        self.notebook['wishes'].append({'id': 'w%d' % (len(self.notebook['wishes']) + 1 + random.randrange(1000)), 'text': text, 'source': source, 'count': 1, 'done': False, 'created': now_iso(), 'last': now_iso()})
        return True

    def open_wishes(self, n=5):
        return sorted([w for w in self.notebook['wishes'] if not w.get('done')], key=lambda w: (-w.get('count', 1), w.get('created', '')))[:n]

    def finish_wish(self, wid, how=''):
        for w in self.notebook['wishes']:
            if w['id'] == wid: w['done'] = True; w['how'] = str(how)[:200]; w['finished'] = now_iso(); return True
        return False

    # ---------------------------------------------------------------- log
    def log(self, text):
        p = self._path('learning_log.md')
        with open(p, 'a', encoding='utf-8') as f: f.write('\n' + text.strip() + '\n')

    # ---------------------------------------------------------------- prompt context
    def context_for_prompt(self, prompt, max_chars=6500):
        parts = []
        bk = self.brand_kit()
        if bk:
            parts.append('BRAND KIT (the user\'s identity - use these colours, name, logo and tone; do not invent a different brand):\n' + json.dumps(bk, ensure_ascii=False))
        ls = self.top_lessons(14)
        if ls:
            parts.append('LESSONS LEARNED FROM EARLIER VIDEOS (follow them):\n' + '\n'.join('- %s: %s' % ('DO' if l['kind'] == 'do' else "DON'T", l['text']) for l in ls))
        sg = self.style_guide()
        if sg: parts.append('STYLE GUIDE learned from the reference videos the user collected:\n' + sg[:1800])
        sty = self.relevant_styles(prompt, 2)
        if sty:
            parts.append('REFERENCE STYLE CARDS (borrow structure and motion ideas, never copy content):\n' + '\n'.join(json.dumps({k: v for k, v in s.items() if k in ('title', 'palette', 'typography', 'motion', 'transitions', 'pacing', 'scenes', 'notes')}, ensure_ascii=False)[:900] for s in sty))
        liked = [d for d in self.designs if (d.get('rating') or 0) >= 4][-2:]
        if liked:
            parts.append('DESIGNS THE USER LIKED (what worked):\n' + '\n'.join(json.dumps({'prompt': d['prompt'][:120], **{k: d['summary'].get(k) for k in ('mode', 'notes', 'backgrounds', 'entrance_anims', 'transitions', 'kinds', 'camera') if d['summary'].get(k) is not None}}, ensure_ascii=False) for d in liked))
        disliked = [d for d in self.designs if d.get('rating') and d['rating'] <= 2][-2:]
        if disliked:
            parts.append('DESIGNS THE USER DID NOT LIKE (avoid repeating these choices):\n' + '\n'.join(json.dumps({'prompt': d['prompt'][:120], 'notes': [n['note'] for n in d.get('notes', [])][-2:], **{k: d['summary'].get(k) for k in ('mode', 'notes', 'backgrounds', 'entrance_anims', 'transitions') if d['summary'].get(k) is not None}}, ensure_ascii=False) for d in disliked))
        tq = self.techniques_for(prompt, 4)
        if tq:
            parts.append('TECHNIQUES YOU LEARNED (use one when it fits the brief; adapt, do not copy):\n' + '\n'.join(
                '- %s (when: %s): %s' % (t['name'], t.get('when') or 'any', t['how']) for t in tq))
        recent = self.designs[-3:]
        if recent:
            parts.append('THE LAST VIDEOS YOU MADE (make this one clearly DIFFERENT in background styles, entrance animations, layouts and transitions):\n' + '\n'.join(
                json.dumps({'backgrounds': d['summary'].get('backgrounds') or d['summary'].get('notes'), 'entrances': list(d['summary'].get('entrance_anims') or [])[:4], 'transitions': d['summary'].get('transitions'), 'kinds': d['summary'].get('kinds')}, ensure_ascii=False) for d in recent))
        text = '\n\n'.join(parts)
        return text[:max_chars]
