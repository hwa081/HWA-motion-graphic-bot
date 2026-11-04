"""mgl.gemini - tiny Gemini REST client (standard library only).

* auth via the x-goog-api-key header (key is never put in a URL, so it does not show up in logs)
* model names change often -> the client asks the API which models this key can use and falls back automatically
* free-tier limits (HTTP 429) -> waits and retries, then tries the next model
"""
import base64, json, os, re, time, urllib.request, urllib.error

API = os.environ.get('GEMINI_API_BASE', 'https://generativelanguage.googleapis.com/v1beta').rstrip('/')    # override only for tests
FALLBACK_MODELS = ['gemini-flash-latest', 'gemini-2.5-flash', 'gemini-2.5-flash-lite']
SKIP_WORDS = ('image', 'tts', 'live', 'audio', 'embed', 'exp', 'robotics', 'computer', 'native', 'learnlm', 'vision', 'aqa', 'gemma')


class GeminiError(Exception):
    pass


def _http(method, url, key, body=None, timeout=240):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={'Content-Type': 'application/json', 'x-goog-api-key': key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try: return e.code, json.loads(raw)
        except Exception: return e.code, {'error': {'message': raw[:500]}}
    except Exception as ex:
        raise GeminiError('network error: %s' % ex)


def _err_msg(j):
    try: return str(j['error'].get('message', j))[:400]
    except Exception: return str(j)[:400]


def list_models(key):
    """names of models that support generateContent"""
    st, j = _http('GET', API + '/models?pageSize=200', key, timeout=60)
    if st != 200:
        raise GeminiError('listing models failed (HTTP %s): %s' % (st, _err_msg(j)))
    out = []
    for m in j.get('models', []):
        if 'generateContent' in m.get('supportedGenerationMethods', []):
            out.append(m['name'].split('/', 1)[-1])
    return out


def _version_key(name):
    nums = re.findall(r'\d+(?:\.\d+)?', name)
    return [float(n) for n in nums] or [0.0]


def choose_models(key):
    """GEMINI_MODEL (comma separated) wins; otherwise discovered flash models, newest stable first"""
    env = os.environ.get('GEMINI_MODEL', '').strip()
    if env:
        return [m.strip() for m in env.split(',') if m.strip()]
    try:
        names = list_models(key)
    except GeminiError as ex:
        print('  (could not list models: %s) -> using built-in list' % ex)
        return list(FALLBACK_MODELS)
    flash = [n for n in names if 'flash' in n and not any(w in n for w in SKIP_WORDS)]
    stable = sorted([n for n in flash if 'preview' not in n and 'lite' not in n and 'latest' not in n], key=_version_key, reverse=True)
    preview = sorted([n for n in flash if 'preview' in n and 'lite' not in n], key=_version_key, reverse=True)
    lite = sorted([n for n in flash if 'lite' in n and 'preview' not in n], key=_version_key, reverse=True)
    out = []
    if 'gemini-flash-latest' in flash: out.append('gemini-flash-latest')
    out += stable + preview + lite
    seen = []
    for n in out:
        if n not in seen: seen.append(n)
    return seen[:6] or list(FALLBACK_MODELS)


def text_part(s): return {'text': s}
def image_part(png_bytes): return {'inlineData': {'mimeType': 'image/png', 'data': base64.b64encode(png_bytes).decode('ascii')}}


def _extract_text(j):
    cands = j.get('candidates') or []
    if not cands:
        fb = j.get('promptFeedback', {})
        raise GeminiError('no answer returned (%s)' % (fb or 'empty candidates'))
    parts = (cands[0].get('content') or {}).get('parts') or []
    txt = ''.join(p.get('text', '') for p in parts if not p.get('thought'))
    if not txt.strip():
        raise GeminiError('empty answer (finishReason=%s)' % cands[0].get('finishReason'))
    return txt


def generate(key, model, system, contents, json_mode=True, temperature=0.8, max_tokens=24000):
    """one call; returns text. Raises GeminiError(with .status) on failure"""
    body = {'contents': contents,
            'generationConfig': {'temperature': temperature, 'maxOutputTokens': max_tokens}}
    if system: body['systemInstruction'] = {'parts': [{'text': system}]}
    if json_mode: body['generationConfig']['responseMimeType'] = 'application/json'
    url = '%s/models/%s:generateContent' % (API, model)
    st, j = _http('POST', url, key, body)
    for _ in range(2):                                   # tolerate models without JSON mode / with a smaller output limit
        if st != 400: break
        msg = _err_msg(j).lower()
        cfg = body['generationConfig']
        if 'responseMimeType' in cfg and 'mime' in msg:
            cfg.pop('responseMimeType')
        elif cfg['maxOutputTokens'] > 8192 and 'token' in msg and 'output' in msg:
            cfg['maxOutputTokens'] = 8192
        else:
            break
        st, j = _http('POST', url, key, body)
    if st == 200:
        return _extract_text(j)
    ex = GeminiError('HTTP %s from %s: %s' % (st, model, _err_msg(j)))
    ex.status = st
    ex.retry_after = None
    for d in (j.get('error', {}).get('details') or []):
        m = re.fullmatch(r'(\d+(?:\.\d+)?)s', str(d.get('retryDelay', '')))
        if m: ex.retry_after = float(m.group(1))
    raise ex


TRANSIENT = (None, 408, 425, 429, 500, 502, 503, 504)      # None = network error: worth waiting for


def _patience():
    try: return max(0.0, float(os.environ.get('AI_PATIENCE_MIN', '12') or 12)) * 60.0
    except ValueError: return 720.0


def ask_once(key, models, system, contents, json_mode=True, temperature=0.8, log=print, max_wait=90):
    """try each model (with a few retries on rate limits) until one answers. Raises GeminiError; .transient = every failure was a wait-and-retry kind"""
    problems, transient = [], True
    for model in models:
        for attempt in range(3):
            try:
                log('  -> %s (try %d)' % (model, attempt + 1))
                txt = generate(key, model, system, contents, json_mode, temperature)
                return txt, model
            except GeminiError as ex:
                st = getattr(ex, 'status', None)
                problems.append('%s: %s' % (model, ex))
                if st in TRANSIENT and attempt < 2:
                    wait = min(max_wait, ex.retry_after or (8 * (attempt + 1)) if st is not None else 6 * (attempt + 1))
                    log('     %s - waiting %.0fs then retrying' % (st or 'network problem', wait))
                    time.sleep(wait)
                    continue
                if st in (401,) or (st == 400 and 'api key' in str(ex).lower()):
                    e2 = GeminiError('API key rejected: %s' % ex); e2.transient = False; raise e2
                if st not in TRANSIENT: transient = False
                break   # next model
    e = GeminiError('all models failed:\n  ' + '\n  '.join(problems[-8:]))
    e.transient = transient
    raise e


def ask(key, models, system, contents, json_mode=True, temperature=0.8, log=print, max_wait=90, patience=None):
    """like ask_once, but when every model is only busy / rate limited / unreachable it keeps waiting (up to AI_PATIENCE_MIN minutes, default 12)
    instead of failing: a slow video is better than a failed one."""
    patience = _patience() if patience is None else patience
    t0, rnd = time.time(), 0
    while True:
        try:
            return ask_once(key, models, system, contents, json_mode, temperature, log, max_wait)
        except GeminiError as ex:
            left = patience - (time.time() - t0)
            if not getattr(ex, 'transient', False) or left <= 5:
                raise
            rnd += 1
            wait = min(left, 30 * rnd, 150)
            log('     the AI is busy or unreachable - waiting %.0fs, then trying again (%.0f min of patience left)' % (wait, left / 60))
            time.sleep(wait)


def extract_json(text):
    """parse JSON even if the model wrapped it in ``` fences or added chatter"""
    t = text.strip()
    t = re.sub(r'^```(?:json)?\s*|\s*```$', '', t, flags=re.I)
    try:
        return json.loads(t)
    except Exception:
        a, b = t.find('{'), t.rfind('}')
        if a != -1 and b > a:
            return json.loads(t[a:b + 1])
        raise
