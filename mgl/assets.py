"""mgl.assets - find and choose images, illustrations, vectors and icons for a video.

Sections (like the tabs of a design library):
    photo         Pixabay (needs PIXABAY_API_KEY) and Pexels (needs PEXELS_API_KEY)
    illustration  Pixabay
    vector        Pixabay
    icon          Iconify (no key needed; 200k open-source icons, mono or colour sets)
    canva         your own Canva exports placed in assets/canva/ (Canva's API has no library search)

A spec layer may contain  {"type":"image","search":{"section":"icon","query":"rocket"},"w":200}
resolve_spec() searches every section's providers, shows the candidates to Gemini as a numbered sheet,
downloads the best one into assets/library/, writes its path into the layer and remembers the decision in memory/assets.json.
"""
import json, os, re, urllib.parse, urllib.request, urllib.error, hashlib, datetime
import cv2, numpy as np

SECTIONS = ['photo', 'illustration', 'vector', 'icon', 'canva']
MONO_SETS = ['lucide', 'tabler', 'ph', 'solar', 'mdi', 'heroicons', 'material-symbols', 'iconoir', 'carbon', 'fluent', 'ri', 'bi', 'uil', 'majesticons', 'akar-icons']
COLOR_SETS = ['fluent-emoji-flat', 'fluent-emoji', 'noto', 'twemoji', 'openmoji', 'flat-color-icons', 'emojione', 'streamline-emojis', 'logos']
UA = 'motion-graphic-bot/1.0 (+https://github.com)'


class AssetError(Exception):
    pass


def http_get(url, headers=None, timeout=30, max_bytes=25_000_000):
    req = urllib.request.Request(url, headers=dict({'User-Agent': UA}, **(headers or {})))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(max_bytes + 1)
    except urllib.error.HTTPError as e:
        raise AssetError('HTTP %s for %s' % (e.code, url.split('?')[0]))
    except Exception as ex:
        raise AssetError('network error for %s: %s' % (url.split('?')[0], ex))
    if len(data) > max_bytes: raise AssetError('file too large: %s' % url.split('?')[0])
    return data


def http_json(url, headers=None):
    try:
        return json.loads(http_get(url, headers).decode('utf-8'))
    except AssetError:
        raise
    except Exception as ex:
        raise AssetError('bad JSON from %s: %s' % (url.split('?')[0], ex))


def svg_to_png(svg_text, size=512):
    """SVG markup -> PNG bytes with transparency (resvg-py first, cairosvg as fallback)"""
    try:
        import resvg_py
        return bytes(resvg_py.svg_to_bytes(svg_string=svg_text, width=size, height=size))
    except ImportError:
        pass
    except Exception as ex:
        raise AssetError('svg render failed: %s' % ex)
    try:
        import cairosvg
        return cairosvg.svg2png(bytestring=svg_text.encode('utf-8'), output_width=size, output_height=size)
    except ImportError:
        raise AssetError('no SVG renderer installed (pip install resvg-py)')
    except Exception as ex:
        raise AssetError('svg render failed: %s' % ex)


def _slug(s, n=28):
    return re.sub(r'[^a-z0-9]+', '-', str(s).lower()).strip('-')[:n] or 'x'


def _hex(c):
    if c is None: return '#ffffff'
    c = [int(round(max(0, min(1, v)) * 255)) for v in c[:3]]
    return '#%02x%02x%02x' % tuple(c)


# ------------------------------------------------------------------ providers
class Candidate(dict):
    """dict with: id, provider, section, label, thumb (bytes, filled lazily), license, author, page"""


class Pixabay:
    name = 'pixabay'
    sections = ('photo', 'illustration', 'vector')

    def __init__(self, key): self.key = key

    def search(self, query, section, orient=None, n=8, **kw):
        p = {'key': self.key, 'q': query[:100], 'image_type': section, 'per_page': 20, 'safesearch': 'true', 'order': 'popular', 'lang': 'en',
             'min_width': 900 if section == 'photo' else 400}
        if orient in ('horizontal', 'vertical'): p['orientation'] = orient
        data = http_json('https://pixabay.com/api/?' + urllib.parse.urlencode(p))
        out = []
        for h in (data.get('hits') or [])[:n]:
            full = h.get('largeImageURL') or h.get('webformatURL')
            if not full: continue
            out.append(Candidate(id=str(h.get('id')), provider=self.name, section=section, label=str(h.get('tags', ''))[:80], thumb_url=h.get('webformatURL') or full,
                                 full_url=full, w=h.get('imageWidth'), h=h.get('imageHeight'), license='Pixabay Content License', author=str(h.get('user', '')), page=h.get('pageURL', '')))
        return out

    def download(self, c, **kw):
        return http_get(c['full_url']), os.path.splitext(urllib.parse.urlparse(c['full_url']).path)[1].lower() or '.jpg'


class Pexels:
    name = 'pexels'
    sections = ('photo',)

    def __init__(self, key): self.key = key

    def search(self, query, section, orient=None, n=8, **kw):
        p = {'query': query[:100], 'per_page': 15}
        if orient: p['orientation'] = {'horizontal': 'landscape', 'vertical': 'portrait', 'square': 'square'}.get(orient, 'landscape')
        data = http_json('https://api.pexels.com/v1/search?' + urllib.parse.urlencode(p), {'Authorization': self.key})
        out = []
        for h in (data.get('photos') or [])[:n]:
            src = h.get('src') or {}
            full = src.get('large2x') or src.get('large') or src.get('original')
            if not full: continue
            out.append(Candidate(id=str(h.get('id')), provider=self.name, section='photo', label=str(h.get('alt', ''))[:80], thumb_url=src.get('medium') or full, full_url=full,
                                 w=h.get('width'), h=h.get('height'), license='Pexels License', author=str(h.get('photographer', '')), page=h.get('url', '')))
        return out

    def download(self, c, **kw):
        return http_get(c['full_url']), '.jpg'


class Iconify:
    name = 'iconify'
    sections = ('icon',)

    def search(self, query, section, orient=None, n=8, style='mono', **kw):
        data = http_json('https://api.iconify.design/search?' + urllib.parse.urlencode({'query': query[:60], 'limit': 64}))
        names = [x for x in (data.get('icons') or []) if isinstance(x, str) and ':' in x]
        colls = data.get('collections') or {}
        pref = COLOR_SETS if style == 'color' else MONO_SETS
        per_set, ranked = {}, []
        def rank(nm):
            pre = nm.split(':')[0]
            return (pref.index(pre) if pre in pref else len(pref) + 1, nm)
        for nm in sorted(names, key=rank):
            pre = nm.split(':')[0]
            if style == 'color' and pre not in COLOR_SETS: continue
            if style != 'color' and pre in COLOR_SETS: continue
            if per_set.get(pre, 0) >= 3: continue
            per_set[pre] = per_set.get(pre, 0) + 1; ranked.append(nm)
        out = []
        for nm in ranked[:n]:
            pre, name = nm.split(':', 1)
            info = colls.get(pre, {}) if isinstance(colls, dict) else {}
            lic = (info.get('license') or {}).get('title', '') if isinstance(info.get('license'), dict) else ''
            out.append(Candidate(id=nm, provider=self.name, section='icon', label=nm, svg_url='https://api.iconify.design/%s/%s.svg' % (pre, name), style=style,
                                 license=lic or 'see iconify.design', author=str(info.get('author', {}).get('name', '') if isinstance(info.get('author'), dict) else info.get('author', '')), page='https://icon-sets.iconify.design/%s/%s/' % (pre, name)))
        return out

    def _svg(self, c, size, color):
        q = {'height': size}
        if c.get('style') != 'color': q['color'] = color
        return http_get(c['svg_url'] + '?' + urllib.parse.urlencode(q)).decode('utf-8', 'replace')

    def thumb(self, c):
        return svg_to_png(self._svg(c, 160, '#ffffff'), 160)

    def download(self, c, color='#ffffff', **kw):
        return svg_to_png(self._svg(c, 512, color), 512), '.png'


class CanvaInbox:
    """files you exported from Canva into assets/canva/ (png / jpg / webp)"""
    name = 'canva'
    sections = ('canva',)

    def __init__(self, root, mem=None):
        self.dir = os.path.join(root, 'assets', 'canva'); self.root = root; self.mem = mem

    def files(self):
        if not os.path.isdir(self.dir): return []
        return sorted(f for f in os.listdir(self.dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')))

    def search(self, query, section, orient=None, n=8, **kw):
        qw = set(re.findall(r'[a-z0-9]+', query.lower()))
        idx = (self.mem.assets.get('canva_index', {}) if self.mem else {})
        scored = []
        for f in self.files():
            rel = 'assets/canva/' + f
            tags = ' '.join(idx.get(rel, {}).get('tags', []))
            words = set(re.findall(r'[a-z0-9]+', (os.path.splitext(f)[0] + ' ' + tags).lower()))
            scored.append((len(qw & words), f))
        scored.sort(key=lambda x: (-x[0], x[1]))
        pool = [x for x in scored if x[0] > 0] or scored        # nothing matches -> let the AI look at the newest few
        out = []
        for sc, f in pool[:n]:
            out.append(Candidate(id=f, provider='canva', section='canva', label=os.path.splitext(f)[0], local=os.path.join(self.dir, f), license='your Canva design', author='you', page=''))
        return out

    def download(self, c, **kw):
        ext = os.path.splitext(c['local'])[1].lower() or '.png'
        return open(c['local'], 'rb').read(), ext


def make_providers(root, mem=None, env=None):
    env = os.environ if env is None else env
    provs = [Iconify(), CanvaInbox(root, mem)]
    if env.get('PIXABAY_API_KEY', '').strip(): provs.insert(0, Pixabay(env['PIXABAY_API_KEY'].strip()))
    if env.get('PEXELS_API_KEY', '').strip(): provs.append(Pexels(env['PEXELS_API_KEY'].strip()))
    return provs


def providers_for(provs, section):
    return [p for p in provs if section in p.sections]


# ------------------------------------------------------------------ candidate sheet + choice
def _thumb(prov, c):
    if hasattr(prov, 'thumb'):
        data = prov.thumb(c)
    elif c.get('local'):
        data = open(c['local'], 'rb').read()
    else:
        data = http_get(c['thumb_url'], max_bytes=6_000_000)
    im = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    if im is None: raise AssetError('cannot decode thumbnail of %s' % c.get('id'))
    return im


def candidate_sheet(provs_by_name, cands, tile=300, cols=4):
    tiles, ok = [], []
    for i, c in enumerate(cands):
        try:
            im = _thumb(provs_by_name[c['provider']], c)
        except Exception:
            continue
        if im.ndim == 2: im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGRA)
        if im.shape[2] == 3: im = cv2.cvtColor(im, cv2.COLOR_BGR2BGRA)
        h, w = im.shape[:2]; s = min(tile / w, tile / h)
        im = cv2.resize(im, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
        bg = np.zeros((tile, tile, 3), np.uint8); bg[:] = (44, 36, 32)                  # dark grey so white icons stay visible
        a = im[..., 3:4].astype(np.float32) / 255
        y0, x0 = (tile - im.shape[0]) // 2, (tile - im.shape[1]) // 2
        region = bg[y0:y0 + im.shape[0], x0:x0 + im.shape[1]].astype(np.float32)
        bg[y0:y0 + im.shape[0], x0:x0 + im.shape[1]] = (region * (1 - a) + im[..., :3].astype(np.float32) * a).astype(np.uint8)
        n = len(ok) + 1
        cv2.rectangle(bg, (0, 0), (44, 38), (0, 0, 0), -1)
        cv2.putText(bg, str(n), (6, 29), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2, cv2.LINE_AA)
        tiles.append(bg); ok.append(c)
    if not tiles: return None, []
    while len(tiles) % cols: tiles.append(np.zeros_like(tiles[0]))
    sheet = np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)])
    return cv2.imencode('.png', sheet)[1].tobytes(), ok


CHOOSE_SYSTEM = 'You are an art director choosing one asset for a motion-graphics video. Answer with JSON only.'


def choose(ask, provs_by_name, cands, query, purpose, bg_hint='', log=print):
    """returns (candidate, reason). Uses Gemini vision when `ask` is given, else the first usable candidate."""
    if not cands: return None, 'no candidates'
    if ask is None:
        return cands[0], 'first result (no AI chooser)'
    sheet, shown = candidate_sheet(provs_by_name, cands)
    if sheet is None:
        return cands[0], 'thumbnails unavailable - took the first result'
    from . import gemini
    prompt = ('Pick the BEST candidate for this use.\nSearch: "%s"\nUse in the video: %s\n%s\n'
              'The picture shows %d numbered candidates (number in the yellow box). Prefer: clear single subject, clean composition, no text or watermark, '
              'matches the search meaning exactly, modern professional look, consistent with the video style, good quality, enough empty space for the layout. '
              'Reject candidates that are wrong, cluttered, low quality or off-style.\n'
              'Return JSON: {"best": <number 1-%d, or 0 if none is good>, "reason": "short reason", "scores": [<1-10 for each candidate in order>]}'
              % (query, purpose or 'decorative element', ('Video look: ' + bg_hint) if bg_hint else '', len(shown), len(shown)))
    try:
        txt = ask(CHOOSE_SYSTEM, [{'role': 'user', 'parts': [{'text': prompt}, gemini.image_part(sheet)]}])
        data = gemini.extract_json(txt)
        k = int(data.get('best', 0))
        if 1 <= k <= len(shown): return shown[k - 1], str(data.get('reason', ''))[:200]
        if k == 0:
            return None, 'AI rejected all candidates: ' + str(data.get('reason', ''))[:160]
    except Exception as ex:
        log('   chooser failed (%s) - taking the first result' % ex)
    return shown[0], 'first result (chooser failed)'


# ------------------------------------------------------------------ resolver
def _orient(L):
    w, h = L.get('w'), L.get('h')
    if isinstance(w, (int, float)) and isinstance(h, (int, float)):
        return 'horizontal' if w > h * 1.15 else ('vertical' if h > w * 1.15 else None)
    return None


def _key(section, query, orient, style):
    return '%s|%s|%s|%s' % (section, re.sub(r'\s+', ' ', query.lower().strip()), orient or '-', style or '-')


def _credit(root, entry):
    p = os.path.join(root, 'assets', 'library', 'CREDITS.md')
    os.makedirs(os.path.dirname(p), exist_ok=True)
    line = '- %s: %s (%s, %s) %s\n' % (entry['file'], entry.get('label', ''), entry.get('provider'), entry.get('license', ''), entry.get('page', ''))
    old = open(p, encoding='utf-8').read() if os.path.exists(p) else '# Asset credits\n\n'
    if line not in old: open(p, 'w', encoding='utf-8').write(old + line)


def resolve_spec(spec, root, mem, ask=None, provs=None, bg_hint='', max_searches=6, log=print):
    """replaces every image layer's "search" by a real "path". Layers that cannot be resolved are removed.
    returns (spec, report) with report = list of dict(layer, query, section, chosen, reason, cached, provider)"""
    provs = provs if provs is not None else make_providers(root, mem)
    by_name = {p.name: p for p in provs}
    report, keep, searches = [], [], 0
    lib = os.path.join(root, 'assets', 'library')
    for i, L in enumerate(spec.get('layers', [])):
        if not (isinstance(L, dict) and L.get('type') == 'image' and 'search' in L and 'path' not in L):
            keep.append(L); continue
        s = L['search']; section, query = s['section'], s['query'].strip()
        style = s.get('style') if section == 'icon' else None
        orient = _orient(L)
        key = _key(section, query, orient, style)
        cached = mem.assets.get(key) if mem else None
        if cached and os.path.isfile(os.path.join(root, cached['file'])):
            L['path'] = cached['file']; L.pop('search', None)
            if section == 'icon' and L.get('tint') is None: pass
            report.append(dict(layer=i, query=query, section=section, chosen=cached['file'], reason='remembered from an earlier video: ' + cached.get('reason', ''), cached=True, provider=cached.get('provider')))
            keep.append(L); continue
        if searches >= max_searches:
            report.append(dict(layer=i, query=query, section=section, chosen=None, reason='skipped: more than %d searches in one video' % max_searches, cached=False)); continue
        searches += 1
        ps = providers_for(provs, section)
        if not ps:
            need = {'photo': 'PIXABAY_API_KEY or PEXELS_API_KEY', 'illustration': 'PIXABAY_API_KEY', 'vector': 'PIXABAY_API_KEY'}.get(section, 'files in assets/canva/')
            report.append(dict(layer=i, query=query, section=section, chosen=None, reason='no provider for section "%s" (needs %s)' % (section, need), cached=False)); continue
        cands, errs = [], []
        for p in ps:
            try:
                got = p.search(query, section, orient=orient, n=6, style=style or 'mono')
                cands += got[:6]
            except Exception as ex:
                errs.append('%s: %s' % (p.name, ex))
        cands = cands[:12]
        if not cands:
            report.append(dict(layer=i, query=query, section=section, chosen=None, reason='nothing found (%s)' % ('; '.join(errs) or 'no results'), cached=False)); continue
        purpose = '%s image layer %s%s' % (section, ('size %sx%s' % (L.get('w'), L.get('h'))) if L.get('w') or L.get('h') else '', (' ' + str(s.get('purpose'))) if s.get('purpose') else '')
        best, reason = choose(ask, by_name, cands, query, purpose, bg_hint, log)
        if best is None:
            report.append(dict(layer=i, query=query, section=section, chosen=None, reason=reason, cached=False)); continue
        try:
            color = _hex(L.get('tint')) if isinstance(L.get('tint'), (list, tuple)) else '#ffffff'
            data, ext = by_name[best['provider']].download(best, color=color)
            if best['provider'] == 'canva':
                rel = 'assets/canva/' + best['id']
            else:
                os.makedirs(lib, exist_ok=True)
                ext = ext if ext in ('.png', '.jpg', '.jpeg', '.webp') else '.jpg'
                rel = 'assets/library/%s_%s_%s%s' % (section, _slug(query, 20), _slug(best['id'], 14), ext)
                with open(os.path.join(root, rel), 'wb') as f: f.write(data)
                _credit(root, dict(file=os.path.basename(rel), label=best.get('label', ''), provider=best['provider'], license=best.get('license'), page=best.get('page')))
        except Exception as ex:
            report.append(dict(layer=i, query=query, section=section, chosen=None, reason='download failed: %s' % ex, cached=False)); continue
        L['path'] = rel; L.pop('search', None)
        if mem is not None:
            mem.assets[key] = dict(file=rel, provider=best['provider'], id=best['id'], reason=reason, label=best.get('label', ''), date=datetime.date.today().isoformat(),
                                   author=best.get('author', ''), license=best.get('license', ''), page=best.get('page', ''))
        report.append(dict(layer=i, query=query, section=section, chosen=rel, reason=reason, cached=False, provider=best['provider'], candidates=len(cands)))
        keep.append(L)
    spec['layers'] = keep
    return spec, report


def index_canva_inbox(mem, root, ask, log=print, batch=8):
    """let Gemini write search tags for new files in assets/canva/ (stored in memory/assets.json). returns number indexed"""
    inbox = CanvaInbox(root, mem)
    idx = mem.assets.setdefault('canva_index', {})
    todo = [f for f in inbox.files() if 'assets/canva/' + f not in idx]
    done = 0
    from . import gemini
    for k in range(0, len(todo), batch):
        chunk = todo[k:k + batch]
        cands = [Candidate(id=f, provider='canva', section='canva', label=f, local=os.path.join(inbox.dir, f)) for f in chunk]
        sheet, shown = candidate_sheet({'canva': inbox}, cands)
        if sheet is None: continue
        names = [c['id'] for c in shown]
        try:
            txt = ask('You label design assets so they can be found later. Answer with JSON only.',
                      [{'role': 'user', 'parts': [{'text': 'The picture shows %d numbered assets exported from Canva (file names in order: %s). For each, write 4-8 lowercase search tags (subject, style, colour, use) and a one-line description. '
                                                           'Return JSON {"items":[{"n":1,"tags":["..."],"description":"..."}]}' % (len(shown), ', '.join(names))}, gemini.image_part(sheet)]}])
            for it in (gemini.extract_json(txt).get('items') or []):
                n = int(it.get('n', 0))
                if 1 <= n <= len(shown):
                    idx['assets/canva/' + shown[n - 1]['id']] = {'tags': [str(t).lower()[:24] for t in (it.get('tags') or [])][:8], 'description': str(it.get('description', ''))[:140]}
                    done += 1
        except Exception as ex:
            log('   canva indexing failed for a batch: %s' % ex)
    return done


def check_providers(root, mem=None, env=None, log=print):
    """live smoke test used by the workflow mode 'assets-check'. returns True when every available provider works"""
    ok = True
    provs = make_providers(root, mem, env)
    for p in provs:
        sec = p.sections[0]
        q = {'icon': 'rocket', 'canva': 'logo'}.get(sec, 'mountain')
        try:
            c = p.search(q, sec, n=3)
            if p.name == 'canva':
                log('canva inbox: %d file(s) in assets/canva/' % len(p.files())); continue
            if not c: raise AssetError('no results for "%s"' % q)
            data, ext = p.download(c[0]) if p.name == 'iconify' else (http_get(c[0]['thumb_url'], max_bytes=3_000_000), '.jpg')
            im = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
            if im is None: raise AssetError('downloaded file is not an image')
            log('%s OK: %d results for "%s", first = %s, image %dx%d' % (p.name, len(c), q, c[0].get('label'), im.shape[1], im.shape[0]))
        except Exception as ex:
            ok = False; log('%s FAILED: %s' % (p.name, ex))
    for name, var in (('pixabay', 'PIXABAY_API_KEY'), ('pexels', 'PEXELS_API_KEY')):
        if not (os.environ if env is None else env).get(var, '').strip():
            log('%s: not configured (secret %s missing) - photo/illustration/vector search from this provider is off' % (name, var))
    return ok
