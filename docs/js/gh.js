/* GitHub API + key tests (everything runs in your browser; the token never leaves it except to api.github.com) */
(function () {
  'use strict';
  const S = window.Studio, store = S.store;
  const G = S.gh = {};
  const WORKFLOW = 'render.yml';

  G.cfg = () => store.get('gh', { token: '', repo: '', branch: '' });
  G.setCfg = c => store.set('gh', Object.assign(G.cfg(), c));
  G.ready = () => { const c = G.cfg(); return !!(c.token && /^[\w.-]+\/[\w.-]+$/.test(c.repo)); };

  async function req(method, url, body, headers) {
    const c = G.cfg();
    const h = Object.assign({ 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' }, headers || {});
    if (c.token) h.Authorization = 'Bearer ' + c.token;
    if (body !== undefined && !(body instanceof Blob)) h['Content-Type'] = 'application/json';
    let r;
    try { r = await fetch(url.startsWith('http') ? url : 'https://api.github.com' + url, { method, headers: h, body: body === undefined ? undefined : (body instanceof Blob ? body : JSON.stringify(body)), cache: 'no-store' }); }
    catch (e) { throw new Error('Network error (' + (e.message || e) + '). Check your internet connection.'); }
    let json = null, text = '';
    const ct = r.headers.get('content-type') || '';
    if (r.status !== 204) { text = await r.text(); if (ct.includes('json')) { try { json = JSON.parse(text); } catch (e) {} } }
    return { status: r.status, ok: r.ok, json, text };
  }
  G.req = req;
  const repoPath = p => '/repos/' + G.cfg().repo + p;
  function errText(r) { return (r.json && r.json.message) ? r.json.message : ('HTTP ' + r.status); }

  /* ------------ connection checks ------------ */
  G.testGithub = async function () {
    const c = G.cfg(); const out = [];
    if (!c.token) return [{ name: 'Token', ok: false, msg: 'Paste your GitHub token' }];
    if (!/^[\w.-]+\/[\w.-]+$/.test(c.repo)) return [{ name: 'Repository', ok: false, msg: 'Write the repository as owner/name' }];
    const me = await req('GET', '/user');
    if (!me.ok) return [{ name: 'Token', ok: false, msg: me.status === 401 ? 'Token is wrong or expired' : errText(me) }];
    out.push({ name: 'Token', ok: true, msg: 'signed in as ' + me.json.login });
    const rp = await req('GET', repoPath(''));
    if (!rp.ok) { out.push({ name: 'Repository', ok: false, msg: rp.status === 404 ? 'Not found - check the name, and that the token can access this repository' : errText(rp) }); return out; }
    G.setCfg({ branch: rp.json.default_branch });
    out.push({ name: 'Repository', ok: true, msg: rp.json.full_name + (rp.json.private ? ' (private)' : ' (public)') + ', branch ' + rp.json.default_branch });
    const wf = await req('GET', repoPath('/actions/workflows/' + WORKFLOW));
    out.push({ name: 'Bot workflow', ok: wf.ok, msg: wf.ok ? 'render.yml found' : 'render.yml not found in .github/workflows - upload the bot files first' });
    const sk = await req('GET', repoPath('/actions/secrets/public-key'));
    out.push({ name: 'Secrets (keys)', ok: sk.ok, msg: sk.ok ? 'can store keys' : 'no access - give the token "Secrets: Read and write"' });
    const vr = await req('GET', repoPath('/actions/variables'));
    out.push({ name: 'Variables (options)', ok: vr.ok, msg: vr.ok ? 'can store options' : 'no access - give the token "Variables: Read and write"' });
    const ct = await req('GET', repoPath('/contents/'));
    const canPush = !!(rp.json.permissions && rp.json.permissions.push);
    out.push({ name: 'Files (upload/outputs)', ok: ct.ok && canPush, msg: canPush ? 'can read and write files' : 'no write access - give the token "Contents: Read and write"' });
    const ac = await req('GET', repoPath('/actions/runs?per_page=1'));
    out.push({ name: 'Run workflow', ok: ac.ok, msg: ac.ok ? 'can start and watch runs' : 'no access - give the token "Actions: Read and write"' });
    return out;
  };

  /* ------------ secrets + variables ------------ */
  G.listSecrets = async function () {
    const r = await req('GET', repoPath('/actions/secrets?per_page=100'));
    if (!r.ok) throw new Error(errText(r));
    return (r.json.secrets || []).map(s => s.name);
  };
  G.putSecret = async function (name, value) {
    const k = await req('GET', repoPath('/actions/secrets/public-key'));
    if (!k.ok) throw new Error('Cannot read the repository key: ' + errText(k));
    const enc = window.HwaCrypto.sealedBox(value, k.json.key);
    const r = await req('PUT', repoPath('/actions/secrets/' + encodeURIComponent(name)), { encrypted_value: enc, key_id: k.json.key_id });
    if (!r.ok) throw new Error('Saving failed: ' + errText(r));
    return true;
  };
  G.delSecret = async function (name) {
    const r = await req('DELETE', repoPath('/actions/secrets/' + encodeURIComponent(name)));
    if (!r.ok && r.status !== 404) throw new Error(errText(r));
  };
  G.listVars = async function () {
    const r = await req('GET', repoPath('/actions/variables?per_page=100'));
    if (!r.ok) throw new Error(errText(r));
    const o = {}; (r.json.variables || []).forEach(v => { o[v.name] = v.value; }); return o;
  };
  G.setVar = async function (name, value) {
    let r = await req('PATCH', repoPath('/actions/variables/' + encodeURIComponent(name)), { name, value: String(value) });
    if (r.status === 404) r = await req('POST', repoPath('/actions/variables'), { name, value: String(value) });
    if (!r.ok) throw new Error('Saving failed: ' + errText(r));
  };
  G.delVar = async function (name) { await req('DELETE', repoPath('/actions/variables/' + encodeURIComponent(name))); };

  /* ------------ files ------------ */
  G.branch = () => G.cfg().branch || 'main';
  G.readText = async function (path) {
    const r = await req('GET', repoPath('/contents/' + path.split('/').map(encodeURIComponent).join('/') + '?ref=' + encodeURIComponent(G.branch())), undefined, { Accept: 'application/vnd.github.raw+json' });
    if (r.status === 404) return null;
    if (!r.ok) throw new Error(errText(r));
    return r.text;
  };
  G.readRef = async function (path, ref) {      // a file on another branch (live progress lives on "bot-progress")
    const r = await req('GET', repoPath('/contents/' + path.split('/').map(encodeURIComponent).join('/') + '?ref=' + encodeURIComponent(ref)), undefined, { Accept: 'application/vnd.github.raw+json' });
    return r.ok ? r.text : null;
  };
  G.rawUrl = path => { const c = G.cfg(); return 'https://raw.githubusercontent.com/' + c.repo + '/' + G.branch() + '/' + path.split('/').map(encodeURIComponent).join('/'); };
  G.putFile = async function (path, b64, message) {
    const p = '/contents/' + path.split('/').map(encodeURIComponent).join('/');
    const ex = await req('GET', repoPath(p + '?ref=' + encodeURIComponent(G.branch())));
    const body = { message: message || 'upload from studio', content: b64, branch: G.branch() };
    if (ex.ok && ex.json && ex.json.sha) body.sha = ex.json.sha;
    const r = await req('PUT', repoPath(p), body);
    if (!r.ok) throw new Error('Upload failed: ' + errText(r));
    return r.json;
  };
  G.fileToB64 = file => new Promise((res, rej) => { const fr = new FileReader(); fr.onload = () => res(String(fr.result).split(',')[1]); fr.onerror = () => rej(new Error('Cannot read the file')); fr.readAsDataURL(file); });

  /* ------------ workflow ------------ */
  G.dispatch = async function (inputs) {
    const r = await req('POST', repoPath('/actions/workflows/' + WORKFLOW + '/dispatches'), { ref: G.branch(), inputs });
    if (r.status !== 204) throw new Error('Could not start the bot: ' + errText(r) + (r.status === 422 ? ' (the workflow does not have this input - upload the newest bot files)' : ''));
  };
  G.runs = async function (n) {
    const r = await req('GET', repoPath('/actions/workflows/' + WORKFLOW + '/runs?per_page=' + (n || 20)));
    if (!r.ok) throw new Error(errText(r));
    return r.json.workflow_runs || [];
  };

  /* ------------ key tests (browser -> provider directly) ------------ */
  async function tryFetch(url, opt) {
    try { const r = await fetch(url, opt); let j = null; try { j = await r.json(); } catch (e) {} return { status: r.status, json: j }; }
    catch (e) { return { status: 0, json: null }; }
  }
  const unknown = 'Could not test from the browser (the service blocks browser calls). Save it and use "Test in cloud".';
  G.testGemini = async function (key, model) {
    const r = await tryFetch('https://generativelanguage.googleapis.com/v1beta/models?pageSize=100', { headers: { 'x-goog-api-key': key } });
    if (r.status === 0) return { ok: null, msg: unknown };
    if (r.status !== 200) return { ok: false, msg: (r.json && r.json.error && r.json.error.message || 'HTTP ' + r.status).slice(0, 160) };
    const names = (r.json.models || []).filter(m => (m.supportedGenerationMethods || []).includes('generateContent')).map(m => m.name.replace('models/', ''));
    return { ok: true, msg: 'works - ' + names.length + ' models available', models: names };
  };
  G.testPixabay = async function (key) {
    const r = await tryFetch('https://pixabay.com/api/?key=' + encodeURIComponent(key) + '&q=nature&per_page=3');
    if (r.status === 0) return { ok: null, msg: unknown };
    if (r.status === 200 && r.json && r.json.hits) return { ok: true, msg: 'works - ' + (r.json.totalHits || 0) + ' photos found for "nature"' };
    return { ok: false, msg: r.status === 400 || r.status === 401 ? 'key rejected' : 'HTTP ' + r.status };
  };
  G.testPexels = async function (key) {
    const r = await tryFetch('https://api.pexels.com/v1/search?query=nature&per_page=1', { headers: { Authorization: key } });
    if (r.status === 0) return { ok: null, msg: unknown };
    if (r.status === 200) return { ok: true, msg: 'works' };
    return { ok: false, msg: r.status === 401 ? 'key rejected' : 'HTTP ' + r.status };
  };
  G.testOpenAI = async function (base, key, model) {
    base = String(base || '').replace(/\/+$/, '');
    if (!/^https:\/\//.test(base)) return { ok: false, msg: 'Base URL must start with https://' };
    const h = { Authorization: 'Bearer ' + key };
    const r = await tryFetch(base + '/models', { headers: h });
    if (r.status === 200) {
      const ids = ((r.json && (r.json.data || r.json.models)) || []).map(m => m.id || m.name).filter(Boolean);
      if (model && ids.length && !ids.includes(model)) return { ok: true, msg: 'key works, but model "' + model + '" is not in the list (' + ids.slice(0, 4).join(', ') + '...)', models: ids };
      return { ok: true, msg: 'works' + (ids.length ? ' - ' + ids.length + ' models' : ''), models: ids };
    }
    if (r.status === 401 || r.status === 403) return { ok: false, msg: 'key rejected (HTTP ' + r.status + ')' };
    if (model) {                                    // some services have no /models: try a 5 token chat
      const c = await tryFetch(base + '/chat/completions', { method: 'POST', headers: Object.assign({ 'Content-Type': 'application/json' }, h), body: JSON.stringify({ model, max_tokens: 5, messages: [{ role: 'user', content: 'Say OK' }] }) });
      if (c.status === 200) return { ok: true, msg: 'works (chat reply received)' };
      if (c.status === 0) return { ok: null, msg: unknown };
      return { ok: false, msg: (c.json && c.json.error && (c.json.error.message || c.json.error) || 'HTTP ' + c.status).toString().slice(0, 160) };
    }
    return r.status === 0 ? { ok: null, msg: unknown } : { ok: false, msg: 'HTTP ' + r.status + ' - check the Base URL (it usually ends with /v1)' };
  };
})();
