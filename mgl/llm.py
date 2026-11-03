"""mgl.llm - more than one AI.

Gemini stays the default (it has its own client in mgl.gemini). On top of it, ANY service with an OpenAI-compatible API can be added from the Studio page
(OpenAI, OpenRouter, Groq, DeepSeek, Mistral, Together, your own URL). Settings come from the environment (set by the GitHub workflow):

    GEMINI_API_KEY            secret
    AI_PROVIDERS              variable, JSON list [{"id","name","base_url","model"}]   (no keys inside)
    AI_KEY_<ID>               secret per provider (id upper-cased, non letters/digits -> _)
    AI_ALL_SECRETS            all secrets as JSON (workflow toJSON(secrets)); only the AI_KEY_* entries are used and the variable is removed at once
    AI_PROVIDER / AI          which one first (run input "ai" wins over the variable)
    AI_FALLBACK               "false" = never switch to another AI when the chosen one fails

ask = make_multi_ask(providers, ...) has the same shape as agent.make_ask(): ask(system, contents, json_mode) -> text.
The contents are Gemini-shaped ({'role', 'parts': [{'text'} | {'inlineData'}]}); they are converted for OpenAI-style services (text + images).
"""
import json, os, re, time, urllib.request, urllib.error
from . import gemini

GeminiError = gemini.GeminiError


class Provider:
    def __init__(self, pid, name, kind, key, base_url='', model=''):
        self.id, self.name, self.kind, self.key, self.base_url, self.model = pid, name, kind, key, base_url.rstrip('/'), model

    def __repr__(self): return 'Provider(%s,%s,%s)' % (self.id, self.kind, self.model)


def secret_name(pid): return 'AI_KEY_' + re.sub(r'[^A-Z0-9]', '_', pid.upper())


def absorb_secrets(env=None):
    """move AI_KEY_* out of the AI_ALL_SECRETS JSON into plain env vars and delete the JSON (so no other secret stays in the environment)"""
    env = os.environ if env is None else env
    raw = env.pop('AI_ALL_SECRETS', '') if hasattr(env, 'pop') else ''
    if not raw: return 0
    n = 0
    try:
        for k, v in (json.loads(raw) or {}).items():
            if k.startswith('AI_KEY_') and isinstance(v, str) and v.strip() and not env.get(k):
                env[k] = v; n += 1
    except Exception:
        pass
    return n


def providers_from_env(env=None):
    env = os.environ if env is None else env
    out = []
    gk = (env.get('GEMINI_API_KEY') or '').strip().strip('"\'')
    if gk: out.append(Provider('gemini', 'Gemini', 'gemini', gk, '', (env.get('GEMINI_MODEL') or '').strip()))
    try:
        items = json.loads(env.get('AI_PROVIDERS') or '[]')
    except Exception:
        items = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict) or not it.get('id') or not it.get('base_url') or not it.get('model'): continue
        key = (env.get(secret_name(str(it['id']))) or '').strip()
        if key: out.append(Provider(str(it['id']), str(it.get('name') or it['id']), 'openai', key, str(it['base_url']), str(it['model'])))
    return out


def order(providers, wanted='', fallback=True):
    """chosen provider first; the others after it unless fallback is off"""
    wanted = (wanted or '').strip().lower()
    first = [p for p in providers if p.id.lower() == wanted] or providers[:1]
    rest = [p for p in providers if p not in first]
    return first + (rest if fallback else [])


# ------------------------------------------------------------------ OpenAI-compatible client
def to_messages(system, contents):
    msgs = []
    if system: msgs.append({'role': 'system', 'content': system})
    for c in contents:
        role = 'assistant' if c.get('role') == 'model' else 'user'
        parts = []
        for p in c.get('parts', []):
            if 'text' in p: parts.append({'type': 'text', 'text': p['text']})
            elif 'inlineData' in p:
                d = p['inlineData']; parts.append({'type': 'image_url', 'image_url': {'url': 'data:%s;base64,%s' % (d.get('mimeType', 'image/png'), d.get('data', ''))}})
        if role == 'assistant': msgs.append({'role': 'assistant', 'content': ''.join(x['text'] for x in parts if x['type'] == 'text')})
        elif all(x['type'] == 'text' for x in parts): msgs.append({'role': 'user', 'content': '\n'.join(x['text'] for x in parts)})
        else: msgs.append({'role': 'user', 'content': parts})
    return msgs


def _http(url, key, body, timeout=240):
    req = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'), method='POST', headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key, 'User-Agent': 'motion-graphic-bot'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode('utf-8')), r.headers
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try: return e.code, json.loads(raw), e.headers
        except Exception: return e.code, {'error': {'message': raw[:400]}}, e.headers
    except Exception as ex:
        raise GeminiError('network error: %s' % ex)


def _msg(j):
    e = j.get('error') if isinstance(j, dict) else None
    if isinstance(e, dict): return str(e.get('message') or e)[:300]
    return str(e or j)[:300]


def openai_generate(p, system, contents, json_mode=True, temperature=0.8, max_tokens=8000):
    body = {'model': p.model, 'messages': to_messages(system, contents), 'temperature': temperature, 'max_tokens': max_tokens}
    if json_mode: body['response_format'] = {'type': 'json_object'}
    url = p.base_url + '/chat/completions'
    st, j, hd = _http(url, p.key, body)
    for _ in range(3):                      # services differ: drop options they reject
        if st != 400: break
        m = _msg(j).lower()
        if 'response_format' in body and ('response_format' in m or 'json' in m): body.pop('response_format')
        elif 'max_tokens' in body and ('max_tokens' in m or 'max_completion_tokens' in m):
            body['max_completion_tokens'] = body.pop('max_tokens')
        elif 'temperature' in body and 'temperature' in m: body.pop('temperature')
        else: break
        st, j, hd = _http(url, p.key, body)
    if st == 200:
        try: txt = j['choices'][0]['message']['content']
        except Exception: raise GeminiError('%s: unexpected answer %s' % (p.name, str(j)[:200]))
        if isinstance(txt, list): txt = ''.join(x.get('text', '') for x in txt if isinstance(x, dict))
        txt = re.sub(r'(?is)<think>.*?</think>', '', txt or '').strip()
        if not txt: raise GeminiError('%s: empty answer' % p.name)
        return txt
    ex = GeminiError('HTTP %s from %s (%s): %s' % (st, p.name, p.model, _msg(j)))
    ex.status = st
    try: ex.retry_after = float(hd.get('retry-after')) if hd and hd.get('retry-after') else None
    except Exception: ex.retry_after = None
    raise ex


def openai_ask(p, system, contents, json_mode=True, temperature=0.8, log=print, max_wait=90):
    last = None
    for attempt in range(3):
        try:
            log('  -> %s / %s (try %d)' % (p.name, p.model, attempt + 1))
            return openai_generate(p, system, contents, json_mode, temperature)
        except GeminiError as ex:
            last = ex; st = getattr(ex, 'status', None)
            if st in (429, 500, 502, 503, 504) and attempt < 2:
                wait = min(max_wait, getattr(ex, 'retry_after', None) or 8 * (attempt + 1)); log('     %s - waiting %.0fs then retrying' % (st, wait)); time.sleep(wait); continue
            if st in (401, 403): raise GeminiError('%s: API key rejected (%s)' % (p.name, _msg({'error': str(ex)})))
            break
    raise last


# ------------------------------------------------------------------ the multi-provider ask()
def make_multi_ask(providers, budget, log=print, budget_error=None):
    """providers: ordered list. Same interface as agent.make_ask(). The provider that answered moves to the front for the next request."""
    chain = list(providers)
    gem_models = {}
    used = []
    BudgetError = budget_error or GeminiError

    def ask(system, contents, json_mode=True):
        if ask.calls >= ask.budget:
            raise BudgetError('request budget of %d reached for this run (protects the free quota; raise it with the MAX_REQUESTS variable)' % ask.budget)
        ask.calls += 1
        problems = []
        for p in list(chain):
            try:
                if p.kind == 'gemini':
                    if p.id not in gem_models:
                        gem_models[p.id] = [m.strip() for m in p.model.split(',') if m.strip()] or gemini.choose_models(p.key)
                    txt, model = gemini.ask(p.key, gem_models[p.id], system, contents, json_mode=json_mode, log=log)
                    label = 'gemini/' + model
                else:
                    txt = openai_ask(p, system, contents, json_mode=json_mode, log=log); label = p.id + '/' + p.model
                if label not in used: used.append(label)
                if chain[0] is not p: chain.remove(p); chain.insert(0, p)
                return txt
            except GeminiError as ex:
                problems.append('%s: %s' % (p.name, ex))
                if len(chain) > 1: log('   %s failed - trying the next AI' % p.name)
        raise GeminiError('every AI failed:\n  ' + '\n  '.join(problems[-6:]))
    ask.used, ask.calls, ask.budget = used, 0, budget
    ask.providers = chain
    return ask


# ------------------------------------------------------------------ connection test (for mode "checks")
def test_provider(p):
    try:
        if p.kind == 'gemini':
            models = gemini.choose_models(p.key)
            txt, model = gemini.ask(p.key, models, None, [{'role': 'user', 'parts': [gemini.text_part('Reply with the single word OK')]}], json_mode=False, log=lambda *a: None)
            return True, 'answered with %s' % model
        txt = openai_ask(p, None, [{'role': 'user', 'parts': [{'text': 'Reply with the single word OK'}]}], json_mode=False, log=lambda *a: None)
        return True, 'answered: %s' % txt.strip()[:40]
    except GeminiError as ex:
        return False, str(ex)[:240]
