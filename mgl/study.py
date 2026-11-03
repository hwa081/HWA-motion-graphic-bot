"""mgl.study - teach the bot something NEW.

You give it text (a tutorial, a description of an effect, notes), a web page URL, a .txt/.md file in the repo, or a video.
The AI turns it into TECHNIQUE cards (name, when to use, how to build it with this library, optional working spec snippet).
Spec snippets are validated by the real validator, so the notebook never keeps a recipe that cannot render.
Techniques are read in every later prompt when they match the brief (memory/notebook.json).
"""
import json, os, re, urllib.request
from . import gemini, spec as S

STUDY_SYSTEM = 'You turn learning material into reusable motion-design techniques for a bot with a fixed library. Answer with JSON only.'
MAX_TEXT = 12000


def fetch_url(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent': 'motion-graphic-bot/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(1_500_000).decode('utf-8', 'replace')
    raw = re.sub(r'(?is)<(script|style|noscript|svg).*?</\1>', ' ', raw)
    raw = re.sub(r'(?s)<[^>]+>', ' ', raw)
    raw = re.sub(r'&nbsp;|&amp;|&lt;|&gt;|&quot;', ' ', raw)
    return re.sub(r'\s+', ' ', raw).strip()


def material(prompt, files, root='.', log=print):
    """-> (text, source label). Order: url in prompt, text file, prompt text itself."""
    m = re.search(r'https?://\S+', prompt or '')
    if m:
        url = m.group(0).rstrip('.,)')
        log('   reading %s' % url)
        return fetch_url(url)[:MAX_TEXT], url
    for f in files or []:
        if f.lower().endswith(('.txt', '.md')) and os.path.isfile(f):
            return open(f, encoding='utf-8', errors='replace').read()[:MAX_TEXT], os.path.basename(f)
    if (prompt or '').strip():
        return prompt.strip()[:MAX_TEXT], 'typed note'
    raise ValueError('nothing to study: write the text (or a URL) in the prompt, or give a .txt/.md file in files')


def study_prompt(text):
    return ('Study this material and extract up to 5 REUSABLE techniques a motion-graphics bot could use with its library '
            '(layer types text, card, chip, chart, device, image, progress, blob, particles, grid, line, rrect, circle; entrance animations %s; transitions %s; camera moves; background styles).\n'
            'Only keep techniques that can really be built with those ingredients (translate the idea into library terms). Skip theory, tools and software menus.\n'
            'Return JSON: {"techniques": [{"name": "short name", "when": "when it fits", "how": "step by step in library terms with timing", '
            '"spec": OPTIONAL {"duration": 3, "layers": [ ...2-6 layers... ]} a tiny working example}]}\n\nMATERIAL:\n%s' % (', '.join(a for a in S.ANIMS if a != 'none'), ', '.join(S.TRANSITIONS), text))


def _valid_snippet(spec, root):
    if not isinstance(spec, dict) or not isinstance(spec.get('layers'), list) or not spec['layers']: return None
    sp = {'duration': float(spec.get('duration') or 3), 'layers': spec['layers'][:8]}
    if spec.get('background'): sp['background'] = spec['background']
    errs, _ = S.validate(sp, root)
    return None if errs else sp


def study(ask, text, mem, root='.', source='typed note', log=print):
    """-> (new_count, cards). Techniques go to mem.notebook."""
    data = gemini.extract_json(ask(STUDY_SYSTEM, [{'role': 'user', 'parts': [gemini.text_part(study_prompt(text))]}]))
    items = data.get('techniques') if isinstance(data, dict) else data
    if not isinstance(items, list): raise ValueError('the answer had no technique list')
    new, cards = 0, []
    for it in items[:5]:
        if not isinstance(it, dict): continue
        t = {'name': it.get('name', ''), 'when': it.get('when', ''), 'how': it.get('how', '')}
        snip = _valid_snippet(it.get('spec'), root)
        if snip: t['spec'] = snip
        elif it.get('spec'): log('   snippet of "%s" dropped (it does not validate)' % str(it.get('name'))[:40])
        if mem.add_technique(t, source='study: ' + source[:40]):
            new += 1; cards.append(t)
    return new, cards
