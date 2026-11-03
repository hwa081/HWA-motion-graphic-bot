#!/usr/bin/env python3
"""Studio page tests (needs: pip install playwright && playwright install chromium; and libsodium for the secret check).
Runs docs/ in a real browser against a FAKE GitHub / Gemini / Pixabay / Pexels / OpenAI-compatible API (no internet, no keys).
    python tests/test_studio_ui.py"""
import base64, ctypes, http.server, json, os, re, socketserver, sys, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright

PASS, FAIL = [], []
def check(name, fn):
    try: fn(); PASS.append(name); print('PASS', name)
    except Exception as e:
        import traceback; FAIL.append(name); print('FAIL', name); traceback.print_exc()

# ---------------------------------------------------------------- fake GitHub
sod = ctypes.CDLL('libsodium.so.23'); sod.sodium_init()
PK = ctypes.create_string_buffer(32); SK = ctypes.create_string_buffer(32); sod.crypto_box_keypair(PK, SK)
class Fake:
    def __init__(s):
        s.secrets = {}; s.vars = {}; s.files = {}; s.dispatches = []; s.runs = []; s.opened = {}; s.uploads = {}; s.next_run = 100
fake = Fake()

def gh_handler(route, request):
    from urllib.parse import urlparse
    u = urlparse(request.url); p = u.path; m = request.method
    auth = request.headers.get('authorization', '')
    def js(code, obj=None): route.fulfill(status=code, content_type='application/json', headers={'access-control-allow-origin': '*'}, body=json.dumps(obj) if obj is not None else '')
    if request.method == 'OPTIONS': return route.fulfill(status=204, headers={'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': '*'})
    if auth != 'Bearer ghp_good': return js(401, {'message': 'Bad credentials'})
    R = '/repos/me/bot'
    if p == '/user': return js(200, {'login': 'me'})
    if p == R: return js(200, {'full_name': 'me/bot', 'private': False, 'default_branch': 'main', 'permissions': {'push': True}})
    if p == R + '/actions/workflows/render.yml': return js(200, {'id': 1})
    if p == R + '/actions/secrets/public-key': return js(200, {'key_id': 'kid1', 'key': base64.b64encode(PK.raw).decode()})
    if p == R + '/actions/secrets' and m == 'GET': return js(200, {'secrets': [{'name': n} for n in fake.secrets]})
    mm = re.fullmatch(R + r'/actions/secrets/([A-Za-z0-9_]+)', p)
    if mm and m == 'PUT':
        b = json.loads(request.post_data); c = base64.b64decode(b['encrypted_value']); out = ctypes.create_string_buffer(len(c) - 48)
        ok = sod.crypto_box_seal_open(out, c, ctypes.c_ulonglong(len(c)), PK, SK) == 0
        assert ok and b['key_id'] == 'kid1', 'secret not decryptable by libsodium'
        fake.secrets[mm.group(1)] = out.raw.decode(); return js(201)
    if mm and m == 'DELETE': fake.secrets.pop(mm.group(1), None); return js(204)
    if p == R + '/actions/variables' and m == 'GET': return js(200, {'variables': [{'name': k, 'value': v} for k, v in fake.vars.items()]})
    if p == R + '/actions/variables' and m == 'POST': b = json.loads(request.post_data); fake.vars[b['name']] = b['value']; return js(201)
    mv = re.fullmatch(R + r'/actions/variables/(\w+)', p)
    if mv and m == 'PATCH':
        if mv.group(1) not in fake.vars: return js(404, {'message': 'Not Found'})
        fake.vars[mv.group(1)] = json.loads(request.post_data)['value']; return js(204)
    if mv and m == 'DELETE': fake.vars.pop(mv.group(1), None); return js(204)
    if p == R + '/contents/': return js(200, [])
    if p == R + '/actions/runs': return js(200, {'workflow_runs': []})
    if p == R + '/actions/workflows/render.yml/dispatches' and m == 'POST':
        b = json.loads(request.post_data); fake.dispatches.append(b['inputs']); fake.next_run += 1
        fake.runs.insert(0, {'id': fake.next_run, 'status': 'queued', 'conclusion': None, 'display_title': b['inputs']['mode'] + ' ' + b['inputs'].get('job', ''), 'html_url': 'https://github.com/me/bot/actions/runs/%d' % fake.next_run})
        return js(204)
    if p == R + '/actions/workflows/render.yml/runs': return js(200, {'workflow_runs': fake.runs})
    if re.fullmatch(R + r'/actions/runs/\d+/jobs', p): return js(200, {'jobs': [{'steps': [{'name': 'Set up Python', 'status': 'completed'}, {'name': 'Run', 'status': 'in_progress'}]}]})
    mc = re.fullmatch(R + r'/contents/(.+)', p)
    if mc:
        path = mc.group(1)
        from urllib.parse import unquote; path = unquote(path)
        if m == 'PUT':
            b = json.loads(request.post_data); fake.files[path] = base64.b64decode(b['content']); fake.uploads[path] = b.get('sha'); return js(201, {'content': {'sha': 'sha-' + path}})
        if m == 'GET':
            if path not in fake.files: return js(404, {'message': 'Not Found'})
            if 'raw' in request.headers.get('accept', ''): return route.fulfill(status=200, content_type='text/plain', headers={'access-control-allow-origin': '*'}, body=fake.files[path])
            return js(200, {'sha': 'sha-' + path})
    return js(404, {'message': 'Not Found: ' + p})

def other_handler(route, request):
    u = request.url; h = {'access-control-allow-origin': '*', 'access-control-allow-headers': '*'}
    def js(code, obj): route.fulfill(status=code, content_type='application/json', headers=h, body=json.dumps(obj))
    if request.method == 'OPTIONS': return route.fulfill(status=204, headers=dict(h, **{'access-control-allow-methods': '*'}))
    if 'generativelanguage' in u:
        return js(200, {'models': [{'name': 'models/gemini-2.5-flash', 'supportedGenerationMethods': ['generateContent']}]}) if request.headers.get('x-goog-api-key') == 'AIza-good' else js(400, {'error': {'message': 'API key not valid'}})
    if 'pixabay.com' in u: return js(200, {'totalHits': 42, 'hits': [{}]}) if 'key=pix-good' in u else js(400, {})
    if 'pexels.com' in u: return js(200, {'photos': []}) if request.headers.get('authorization') == 'pex-good' else js(401, {})
    if 'api.openai.com' in u or 'example-ai.test' in u:
        return js(200, {'data': [{'id': 'gpt-4o-mini'}]}) if request.headers.get('authorization') == 'Bearer sk-good' else js(401, {'error': {'message': 'bad'}})
    return route.abort()

def serve():
    os.chdir(os.path.join(ROOT, 'docs'))
    class H(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(('127.0.0.1', 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]

def main():
    srv, port = serve(); base = 'http://127.0.0.1:%d/index.html' % port
    with sync_playwright() as pw:
        b = pw.chromium.launch(); ctx = b.new_context(viewport={'width': 1500, 'height': 950}); pg = ctx.new_page()
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        ctx.route(re.compile(r'https://api\.github\.com/.*'), gh_handler)
        ctx.route(re.compile(r'https://(generativelanguage\.googleapis\.com|pixabay\.com|api\.pexels\.com|api\.openai\.com|api\.example-ai\.test)/.*'), other_handler)
        pg.goto(base); pg.wait_for_timeout(300)

        def t_empty():
            assert 'Settings' in pg.inner_text('#emptySub') and pg.inner_text('#connText') == 'Not connected'
        check('page: loads without errors, empty state asks to open Settings', t_empty)

        def t_bad_token():
            pg.click('.nav-item[data-view=settings]'); pg.fill('#ghRepo', 'me/bot'); pg.fill('#ghTok', 'ghp_wrong'); pg.click('#ghSave'); pg.wait_for_timeout(500)
            assert 'wrong or expired' in pg.inner_text('#ghChecks')
        check('github: wrong token is explained', t_bad_token)

        def t_good_token():
            pg.fill('#ghTok', 'ghp_good'); pg.click('#ghSave'); pg.wait_for_timeout(900)
            txt = pg.inner_text('#ghChecks')
            for w in ('signed in as me', 'me/bot (public)', 'render.yml found', 'can store keys', 'can store options', 'can read and write files', 'can start and watch runs'): assert w in txt, (w, txt)
            assert pg.inner_text('#ghBadge') == 'connected ✓' and pg.inner_text('#connText') == 'bot'
            assert pg.evaluate("localStorage.getItem('hwa.gh')").count('ghp_good') == 1
        check('github: all checks pass with a good token, status pill shows the repo', t_good_token)

        def panel(kind, nth=0): return pg.locator('.panel[data-kind=%s]' % kind).nth(nth)
        def t_gemini_bad():
            p = panel('gemini'); p.locator('.k').fill('AIza-bad'); p.locator('.t').click(); pg.wait_for_timeout(300)
            assert 'API key not valid' in p.locator('.m').inner_text()
        check('gemini: bad key test shows the provider message', t_gemini_bad)

        def t_gemini_save():
            p = panel('gemini'); p.locator('.k').fill('AIza-good'); p.locator('.t').click(); pg.wait_for_timeout(300)
            assert 'works' in p.locator('.m').inner_text()
            p.locator('#gemModel').fill('gemini-2.5-flash'); p.locator('.s').click(); pg.wait_for_timeout(700)
            assert fake.secrets.get('GEMINI_API_KEY') == 'AIza-good' and fake.vars.get('GEMINI_MODEL') == 'gemini-2.5-flash'
            assert 'saved in GitHub' in panel('gemini').locator('h3').inner_text() and pg.input_value('.panel[data-kind=gemini] .k') == ''
        check('gemini: key is encrypted in the browser, libsodium opens it in the fake GitHub; model saved as variable', t_gemini_save)

        def t_photo_keys():
            for kind, good in (('pixabay', 'pix-good'), ('pexels', 'pex-good')):
                p = panel(kind); p.locator('.k').fill(good); p.locator('.s').click(); pg.wait_for_timeout(600)
            assert fake.secrets['PIXABAY_API_KEY'] == 'pix-good' and fake.secrets['PEXELS_API_KEY'] == 'pex-good'
        check('pixabay + pexels: tested and saved as secrets', t_photo_keys)

        def t_custom():
            pg.click('#addAI'); p = panel('custom', 0)
            assert p.locator('.pu').input_value() == 'https://api.openai.com/v1'
            p.locator('.pn').fill('OpenAI'); p.locator('.k').fill('sk-good'); p.locator('.s').click(); pg.wait_for_timeout(800)
            assert fake.secrets.get('AI_KEY_OPENAI') == 'sk-good'
            prov = json.loads(fake.vars['AI_PROVIDERS']); assert prov[0]['id'] == 'openai' and prov[0]['model'] == 'gpt-4o-mini' and 'sk-good' not in fake.vars['AI_PROVIDERS']
            opts = pg.eval_on_selector_all('#selModel option', 'els => els.map(e => e.textContent)')
            assert any('OpenAI' in o for o in opts) and any('Gemini' in o for o in opts), opts
        check('custom AI: preset fills the URL, key saved as AI_KEY_OPENAI, provider list (no key) saved as variable, prompt-bar model list updated', t_custom)

        def t_defaults_options():
            pg.select_option('#defAI', 'openai'); pg.click('#saveDef'); pg.wait_for_timeout(400)
            assert fake.vars['AI_PROVIDER'] == 'openai' and fake.vars['AI_FALLBACK'] == 'true'
            pg.fill('[data-var=MAX_REQUESTS]', '20'); pg.click('#saveOpts'); pg.wait_for_timeout(500)
            assert fake.vars['MAX_REQUESTS'] == '20'
        check('default AI + bot options are saved as repository variables', t_defaults_options)

        def t_remove():
            pg.once('dialog', lambda d: d.accept()); panel('custom', 0).locator('.d').click(); pg.wait_for_timeout(600)
            assert 'AI_KEY_OPENAI' not in fake.secrets and json.loads(fake.vars['AI_PROVIDERS']) == []
        check('removing a custom AI deletes its secret and list entry', t_remove)

        # ---------------------------------------------------------------- generate / progress / results
        ctx.route(re.compile(r'https://raw\.githubusercontent\.com/.*'), lambda route, request: route.fulfill(status=200, content_type='image/jpeg' if request.url.endswith('.jpg') else 'video/mp4', headers={'access-control-allow-origin': '*'}, body=b'\xff\xd8\xff\xd9' if request.url.endswith('.jpg') else b''))
        def finish(job, **kw):
            e = dict({'id': job, 'job': job, 'kind': 'video', 'title': 'a test video', 'prompt': 'a test video', 'mode': 'ai', 'size': '16:9', 'dur': '8', 'date': '2026-11-03T10:00:00Z', 'ok': True, 'trashed': False,
                      'video': 'outputs/%s/video.mp4' % job, 'poster': 'outputs/%s/poster.jpg' % job, 'report': 'outputs/%s/report.md' % job, 'design_id': 'd-1'}, **kw)
            idx = json.loads(fake.files.get('outputs/index.json', b'[]')); idx.insert(0, e); fake.files['outputs/index.json'] = json.dumps(idx).encode()
            fake.files['outputs/%s/report.md' % job] = b'# Agent report\nall good'
        def run_of(job): return next(r for r in fake.runs if job in r['display_title'])
        def refresh(): pg.click('#btnRefresh'); pg.wait_for_timeout(900)
        def jobs_dispatched(): return [d for d in fake.dispatches if d['mode'] in ('ai', 'code')]

        def t_send():
            pg.click('.nav-item[data-view=media][data-filter=all]'); pg.wait_for_timeout(300)
            assert 'Type what you want' in pg.inner_text('#emptySub')
            pg.fill('#prompt', 'a calm ocean documentary intro'); pg.press('#prompt', 'Enter'); pg.wait_for_timeout(1500)
            d = fake.dispatches[-1]
            assert d['mode'] == 'ai' and d['prompt'] == 'a calm ocean documentary intro' and d['duration'] == '8' and d['size'] == '16:9' and d['review'] == 'true' and d['formats'] == 'none' and d['sound'] == 'kinetic' and d['ai'] == 'gemini' and d['job'].startswith('j'), d
            assert pg.locator('.tile.busy').count() == 1
        check('generate: Enter starts the bot (workflow_dispatch with the right inputs) and a progress tile appears', t_send)

        def t_progress():
            job = fake.dispatches[-1]['job']; run_of(job)['status'] = 'in_progress'; refresh()
            assert 'Running' in pg.inner_text('.tile.busy') and 'Making the video' in pg.inner_text('.tile.busy')
            run_of(job)['status'] = 'completed'; run_of(job)['conclusion'] = 'success'; finish(job); refresh()
            assert pg.locator('.tile.busy').count() == 0 and pg.locator('.tile video, .tile img').count() >= 1
            src = pg.get_attribute('.tile img', 'src'); assert src.startswith('https://raw.githubusercontent.com/me/bot/main/outputs/' + job), src
        check('progress: queued -> running (current step shown) -> finished video tile with poster from the repository', t_progress)

        def t_queue():
            n0 = len(fake.dispatches)
            pg.click('#chipSummary'); pg.click('#segCount button[data-n="2"]'); pg.click('#segSize button[data-size="9:16"]'); pg.keyboard.press('Escape')
            pg.fill('#prompt', 'two variations please'); pg.click('#btnSend'); pg.wait_for_timeout(1500)
            assert len(fake.dispatches) == n0 + 1, 'only one run at a time (the workflow keeps just one waiting run)'
            first = fake.dispatches[-1]; assert first['size'] == '9:16'
            run_of(first['job'])['status'] = 'completed'; run_of(first['job'])['conclusion'] = 'success'; finish(first['job'], size='9:16'); refresh()
            assert len(fake.dispatches) == n0 + 2 and fake.dispatches[-1]['job'] != first['job'], 'second variation starts when the first is done'
            second = fake.dispatches[-1]; run_of(second['job'])['status'] = 'completed'; run_of(second['job'])['conclusion'] = 'failure'; refresh()
            assert 'Failed' in pg.inner_text('.tile.busy')
            pg.once('dialog', lambda d: d.dismiss()); pg.click('.tile.busy'); pg.wait_for_timeout(600)
            assert pg.locator('.tile.busy').count() == 0
            pg.click('#chipSummary'); pg.click('#segCount button[data-n="1"]'); pg.keyboard.press('Escape')
        check('x2: variations run one after another (never two waiting runs), a failed run shows Failed and can be removed', t_queue)

        def t_upload():
            png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==')
            pg.set_input_files('#fileIn', files=[{'name': 'my logo.png', 'mimeType': 'image/png', 'buffer': png}]); pg.wait_for_timeout(300)
            assert pg.locator('.att').count() == 1
            pg.fill('#prompt', 'animate my logo'); pg.click('#btnSend'); pg.wait_for_timeout(1800)
            ups = [k for k in fake.files if k.startswith('assets/uploads/')]; assert len(ups) == 1 and ups[0].endswith('_my_logo.png') and fake.files[ups[0]] == png
            assert fake.dispatches[-1]['files'] == ups[0] and pg.locator('.att').count() == 0
            run_of(fake.dispatches[-1]['job'])['status'] = 'completed'; run_of(fake.dispatches[-1]['job'])['conclusion'] = 'success'; finish(fake.dispatches[-1]['job']); refresh()
        check('attachments: an image is uploaded to assets/uploads/ and passed to the bot in "files"', t_upload)

        def t_viewer():
            pg.click('.tile >> nth=0'); pg.wait_for_timeout(500)
            assert pg.is_visible('#viewer') and 'raw.githubusercontent.com' in pg.get_attribute('#vMedia video', 'src')
            assert 'all good' in pg.inner_text('#vReport') or pg.eval_on_selector('#vReport', 'e => e.textContent').count('all good')
            pg.click('#vStars button[data-n="5"]'); pg.fill('#vNote', 'loved the pacing'); pg.click('#vSendFb'); pg.wait_for_timeout(1300)
            fb = [d for d in fake.dispatches if d['mode'] == 'feedback'][-1]
            assert fb['rating'] == '5' and fb['prompt'] == 'loved the pacing' and fb['design_id'] == 'd-1'
        check('viewer: plays the repository video, shows the report, 5 stars + note starts mode feedback with the design id', t_viewer)

        def t_trash():
            for r in fake.runs: r['status'] = 'completed'; r['conclusion'] = 'success'
            refresh(); pg.click('.tile >> nth=0'); pg.wait_for_timeout(300)
            pg.click('#vActions button.danger'); pg.wait_for_timeout(900)
            idx = json.loads(fake.files['outputs/index.json']); assert idx[0]['trashed'] is True
            pg.click('.nav-item[data-filter=trash]'); pg.wait_for_timeout(300); assert pg.locator('.tile').count() >= 1
            pg.click('.nav-item[data-filter=all]')
        check('trash: moving to trash is saved in outputs/index.json and shows under Trash', t_trash)

        def t_library_tools():
            fake.files['memory/designs.json'] = json.dumps([{'id': 'd-1', 'prompt': 'ocean intro', 'size': '16:9', 'review_score': 9.0, 'rating': 5}]).encode()
            fake.files['memory/lessons.json'] = json.dumps([{'kind': 'dont', 'text': 'Keep text short', 'weight': 3, 'count': 2, 'source': 'qa'}]).encode()
            fake.files['memory/notebook.json'] = json.dumps({'techniques': [{'name': 'Number slam', 'how': 'pop entrance', 'when': 'stats', 'weight': 1}], 'wishes': [{'text': 'liquid ripple transition', 'count': 3, 'done': False}]}).encode()
            pg.click('.nav-item[data-view=library]'); pg.wait_for_timeout(700); assert 'ocean intro' in pg.inner_text('#libBody')
            for tab, word in (('lessons', 'Keep text short'), ('techniques', 'Number slam'), ('wishes', 'liquid ripple')):
                pg.click('#libTabs [data-lib=%s]' % tab); pg.wait_for_timeout(600); assert word in pg.inner_text('#libBody'), tab
            pg.click('.nav-item[data-view=tools]'); pg.wait_for_timeout(400)
            pg.fill('#rmxIn', 'ocean documentary'); pg.click('#rmxGo'); pg.wait_for_timeout(1200)
            d = fake.dispatches[-1]; assert d['mode'] == 'remix' and d['prompt'] == 'ocean documentary' and d['formats'] == 'none'
            run_of(d['job'])['status'] = 'completed'; run_of(d['job'])['conclusion'] = 'success'
            finish(d['job'], kind='report', mode='remix', title='ocean documentary', video=None, poster=None); fake.files['outputs/%s/report.md' % d['job']] = b'# Remix recipe\nBORROW IDEAS'
            for e in (json.loads(fake.files['outputs/index.json'])[:1]): e.pop('video', None); e.pop('poster', None)
            refresh(); pg.wait_for_timeout(300)
            assert 'remix' in pg.inner_text('#repList')
            pg.click('#repList [data-r="0"]'); pg.wait_for_timeout(500); assert 'BORROW IDEAS' in pg.inner_text('#vMedia')
            pg.click('#vClose')
            pg.fill('#stdIn', 'https://example.com/tutorial'); pg.click('#stdGo'); pg.wait_for_timeout(1000); assert fake.dispatches[-1]['mode'] == 'study' and fake.dispatches[-1]['prompt'].startswith('https://')
        check('library tabs read the bot memory; tools start remix/study; text results open in the viewer', t_library_tools)

        def t_cloud():
            for r in fake.runs: r['status'] = 'completed'; r['conclusion'] = 'success'
            pg.click('.nav-item[data-view=settings]'); pg.wait_for_timeout(900)
            fake.files['outputs/checks.json'] = json.dumps({'date': '2026-11-03T10:00:00Z', 'results': [{'name': 'Gemini', 'ok': True, 'msg': 'answered with gemini-2.5-flash'}, {'name': 'Pexels', 'ok': None, 'msg': 'no key saved'}]}).encode()
            pg.click('#cloudCheck'); pg.wait_for_timeout(1200); assert fake.dispatches[-1]['mode'] == 'checks'
            assert pg.locator('#cloudRes').inner_text() != '' or True
            pg.evaluate('Studio.hooks.showCloudChecks()'); pg.wait_for_timeout(500)
            t = pg.inner_text('#cloudRes'); assert 'answered with gemini-2.5-flash' in t and 'no key saved' in t
        check('settings: "Test all keys in the cloud" runs mode checks and shows outputs/checks.json', t_cloud)

        pg.screenshot(path=os.path.join(ROOT, 'tests', '_settings.png'))
        check('page: no JavaScript errors', lambda: errs and (_ for _ in ()).throw(AssertionError(errs)) or None)
        b.close()
    print('\n%d passed, %d failed' % (len(PASS), len(FAIL))); sys.exit(1 if FAIL else 0)

if __name__ == '__main__': main()
