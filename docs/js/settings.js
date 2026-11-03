/* Settings page: GitHub connection, AI keys (Gemini + any OpenAI-compatible service), photo keys, bot options, connection tests */
(function () {
  'use strict';
  const S = window.Studio, G = S.gh, $ = S.$, $$ = S.$$, esc = S.esc;
  const PRESETS = [
    ['OpenAI', 'https://api.openai.com/v1', 'gpt-4o-mini'], ['OpenRouter', 'https://openrouter.ai/api/v1', 'google/gemini-2.5-flash'], ['Groq', 'https://api.groq.com/openai/v1', 'llama-3.3-70b-versatile'],
    ['DeepSeek', 'https://api.deepseek.com/v1', 'deepseek-chat'], ['Mistral', 'https://api.mistral.ai/v1', 'mistral-large-latest'], ['Together', 'https://api.together.xyz/v1', 'meta-llama/Llama-3.3-70B-Instruct-Turbo'],
    ['Custom', '', '']
  ];
  const OPTIONS = [
    ['MAX_REQUESTS', 'Max AI requests per video', '14', 'Protects your free quota.'],
    ['PLAN', 'Director plan before building', 'true', 'true / false. Costs 1 extra request, makes better videos.'],
    ['CODE_TURNS', 'Code Studio turns', '16', 'More turns = better code, more quota.'],
    ['LEARN_LIMIT', 'Reference videos learned per run', '5', ''],
    ['OUTPUT_KEEP', 'Videos kept in the repository', '30', 'Older ones are deleted so the repository stays small.']
  ];
  const st = { secrets: [], vars: {}, providers: [], loaded: false, checks: null };
  const slug = n => String(n || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 20) || 'ai';
  const secretName = id => 'AI_KEY_' + id.toUpperCase().replace(/[^A-Z0-9]/g, '_');
  const has = n => st.secrets.includes(n);

  S.hooks.connected = () => G.ready();

  async function load() {
    if (!G.ready()) { st.loaded = false; return; }
    try {
      st.secrets = await G.listSecrets(); st.vars = await G.listVars();
      try { st.providers = JSON.parse(st.vars.AI_PROVIDERS || '[]'); } catch (e) { st.providers = []; }
      st.loaded = true; st.err = '';
    } catch (e) { st.loaded = false; st.err = e.message; }
    refreshModels();
  }
  function refreshModels() {
    const list = [{ id: 'gemini', label: 'Gemini' + (st.vars.GEMINI_MODEL ? ' · ' + st.vars.GEMINI_MODEL : '') }].concat(st.providers.map(p => ({ id: p.id, label: p.name + ' · ' + p.model })));
    S.setModels(list);
  }
  S.settingsLoad = load;
  S.settings = st;

  const stat = (el, kind, msg) => { const m = el.classList.contains('m'); el.className = 'status ' + (kind || '') + (m ? ' m' : ''); el.textContent = msg; };
  const statusIcon = ok => ok === true ? '✓' : (ok === false ? '✕' : '•');

  function keyPanel(o) {
    const saved = has(o.secret);
    return `<div class="panel" data-secret="${o.secret}" data-kind="${o.kind}">
      <h3>${esc(o.title)} <span class="badge-s ${saved ? 'ok' : ''}">${saved ? 'saved in GitHub ✓' : 'not saved'}</span></h3>
      <div class="sub">${o.help}</div>
      ${o.extra || ''}
      <div class="row"><label>API key</label><input type="password" class="k" autocomplete="off" spellcheck="false" placeholder="${saved ? '•••••••• (saved) - paste a new one to replace' : 'paste your key'}"></div>
      <div class="row"><button class="btn t">Test</button><button class="btn primary s">Save to GitHub</button>${saved ? '<button class="btn danger d">Remove</button>' : ''}<span class="status m"></span></div>
    </div>`;
  }

  S.hooks.renderSettings = async function () {
    const root = $('#settingsBody');
    const c = G.cfg();
    root.innerHTML = `<div class="panel"><h3>GitHub connection <span class="badge-s ${G.ready() ? 'ok' : ''}" id="ghBadge">${G.ready() ? 'token saved in this browser' : 'not connected'}</span></h3>
      <div class="sub">The page runs the bot inside <b>your</b> GitHub repository (GitHub Actions). Create a <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener">fine-grained token</a>: only your bot repository, permissions <b>Actions, Secrets, Variables, Contents → Read and write</b>. The token stays in this browser only.</div>
      <div class="row"><label>Repository</label><input id="ghRepo" placeholder="owner/repository" value="${esc(c.repo)}"></div>
      <div class="row"><label>Token</label><input id="ghTok" type="password" autocomplete="off" spellcheck="false" placeholder="${c.token ? '•••••••• (saved)' : 'github_pat_…'}"></div>
      <div class="row"><button class="btn primary" id="ghSave">Save &amp; test connection</button>${c.token ? '<button class="btn danger" id="ghOut">Disconnect</button>' : ''}</div>
      <div id="ghChecks" class="kv" style="margin-top:8px"></div></div>
      <div id="rest"></div>`;
    $('#ghSave').onclick = saveGh;
    if ($('#ghOut')) $('#ghOut').onclick = () => { G.setCfg({ token: '' }); st.loaded = false; S.hooks.renderSettings(); S.toast('Disconnected'); updatePill(); };
    if (G.ready()) { await load(); }
    renderRest();
    if (G.ready()) runGhChecks();
  };

  async function saveGh() {
    const repo = $('#ghRepo').value.trim().replace(/^https?:\/\/github\.com\//, '').replace(/\.git$/, '').replace(/\/$/, '');
    const tok = $('#ghTok').value.trim();
    G.setCfg({ repo }); if (tok) G.setCfg({ token: tok });
    await runGhChecks(true); await load(); renderRest(); updatePill();
    if (S.hooks.refresh) S.hooks.refresh(true);
  }
  async function runGhChecks(toast) {
    const box = $('#ghChecks'); if (!box) return;
    box.innerHTML = '<div></div><div class="status busy">Testing…</div>';
    let res; try { res = await G.testGithub(); } catch (e) { res = [{ name: 'Connection', ok: false, msg: e.message }]; }
    box.innerHTML = res.map(r => `<div>${esc(r.name)}</div><div class="status ${r.ok ? 'ok' : 'bad'}">${statusIcon(r.ok)} ${esc(r.msg)}</div>`).join('');
    const all = res.every(r => r.ok);
    $('#ghBadge').className = 'badge-s ' + (all ? 'ok' : ''); $('#ghBadge').textContent = all ? 'connected ✓' : (G.cfg().token ? 'check the items below' : 'not connected');
    if (toast) S.toast(all ? 'GitHub connected' : 'Some checks failed - see the list', !all);
    updatePill(all);
  }
  function updatePill(ok) {
    const d = $('#connDot'), t = $('#connText');
    if (!G.ready()) { d.className = 'dot'; t.textContent = 'Not connected'; return; }
    d.className = 'dot ' + (ok === false ? 'bad' : 'ok'); t.textContent = ok === false ? 'Check settings' : G.cfg().repo.split('/')[1];
    $('#avatar').textContent = (G.cfg().repo[0] || 'H').toUpperCase();
  }
  S.updatePill = updatePill;

  function renderRest() {
    const root = $('#rest'); if (!root) return;
    if (!G.ready()) { root.innerHTML = '<div class="panel"><div class="sub">Connect GitHub first. Then you can add your API keys here.</div></div>'; return; }
    if (!st.loaded) { root.innerHTML = `<div class="panel"><div class="sub status bad">${esc(st.err || 'Could not load settings')}</div></div>`; return; }
    const defAI = st.vars.AI_PROVIDER || 'gemini';
    const aiOpts = [['gemini', 'Gemini']].concat(st.providers.map(p => [p.id, p.name])).map(([id, n]) => `<option value="${esc(id)}" ${id === defAI ? 'selected' : ''}>${esc(n)}</option>`).join('');
    root.innerHTML = `
      <h2>AI</h2>
      <div class="panel"><h3>Default AI</h3><div class="sub">The bot uses this AI unless you pick another one in the prompt bar. If it fails or runs out of quota the bot can try the others.</div>
        <div class="row"><label>Use</label><select id="defAI">${aiOpts}</select><label style="width:auto"><input type="checkbox" id="aiFallback" ${st.vars.AI_FALLBACK === 'false' ? '' : 'checked'}> try the other AIs if it fails</label></div>
        <div class="row"><button class="btn" id="saveDef">Save</button></div></div>
      ${keyPanel({ kind: 'gemini', secret: 'GEMINI_API_KEY', title: 'Gemini', help: 'Free key: <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">aistudio.google.com/apikey</a>.',
        extra: `<div class="row"><label>Model (optional)</label><input id="gemModel" placeholder="gemini-2.5-flash  (empty = automatic)" value="${esc(st.vars.GEMINI_MODEL || '')}"></div>` })}
      <div id="customList">${st.providers.map(customPanel).join('')}</div>
      <div class="row"><button class="btn" id="addAI">+ Add another AI (OpenAI, OpenRouter, Groq, DeepSeek, any OpenAI-compatible URL)</button></div>
      <h2>Photos &amp; icons</h2>
      ${keyPanel({ kind: 'pixabay', secret: 'PIXABAY_API_KEY', title: 'Pixabay', help: 'Photos, illustrations, vectors. Free: <a href="https://pixabay.com/api/docs/" target="_blank" rel="noopener">pixabay.com/api/docs</a>.' })}
      ${keyPanel({ kind: 'pexels', secret: 'PEXELS_API_KEY', title: 'Pexels', help: 'More photos. Free: <a href="https://www.pexels.com/api/" target="_blank" rel="noopener">pexels.com/api</a>. Icons (Iconify) need no key.' })}
      <h2>Bot options</h2>
      <div class="panel"><div class="sub">Saved as repository variables.</div>
        ${OPTIONS.map(o => `<div class="row"><label style="width:230px">${esc(o[1])}</label><input data-var="${o[0]}" placeholder="${o[2]}" value="${esc(st.vars[o[0]] || '')}"><span class="status" style="flex:1 1 100%">${esc(o[3])}</span></div>`).join('')}
        <div class="row"><button class="btn primary" id="saveOpts">Save options</button><span class="status" id="optMsg"></span></div></div>
      <h2>Check everything in the cloud</h2>
      <div class="panel"><div class="sub">Runs the bot once to test every saved key from inside GitHub (this is the real test, because it uses the saved keys). Takes about a minute.</div>
        <div class="row"><button class="btn primary" id="cloudCheck">Test all keys in the cloud</button><span class="status" id="cloudMsg"></span></div>
        <div id="cloudRes" class="kv" style="margin-top:8px"></div></div>`;
    wireRest();
    if (S.hooks.showCloudChecks) S.hooks.showCloudChecks();
  }

  function customPanel(p) {
    const preset = PRESETS.map(x => `<option ${x[0] === (p.preset || 'Custom') ? 'selected' : ''}>${x[0]}</option>`).join('');
    return keyPanel({ kind: 'custom', secret: secretName(p.id), title: p.name || 'AI', help: 'Any service with an OpenAI-compatible API.',
      extra: `<div data-pid="${esc(p.id)}">
        <div class="row"><label>Service</label><select class="pp">${preset}</select><input class="pn" placeholder="Name" value="${esc(p.name || '')}"></div>
        <div class="row"><label>Base URL</label><input class="pu" placeholder="https://api.example.com/v1" value="${esc(p.base_url || '')}"></div>
        <div class="row"><label>Model</label><input class="pm" placeholder="model name" value="${esc(p.model || '')}"></div></div>` });
  }

  function wireRest() {
    $('#saveDef').onclick = async () => {
      try { await G.setVar('AI_PROVIDER', $('#defAI').value); await G.setVar('AI_FALLBACK', $('#aiFallback').checked ? 'true' : 'false'); st.vars.AI_PROVIDER = $('#defAI').value; S.toast('Saved'); }
      catch (e) { S.toast(e.message, true); }
    };
    $('#addAI').onclick = () => { st.providers.push({ id: 'new' + Date.now().toString(36), name: 'OpenAI', preset: 'OpenAI', base_url: PRESETS[0][1], model: PRESETS[0][2], isNew: true }); $('#customList').innerHTML = st.providers.map(customPanel).join(''); wirePanels(); };
    $('#saveOpts').onclick = async () => {
      const m = $('#optMsg'); stat(m, 'busy', 'Saving…');
      try { for (const i of $$('[data-var]')) { const v = i.value.trim(); if (v) { await G.setVar(i.dataset.var, v); st.vars[i.dataset.var] = v; } else if (st.vars[i.dataset.var] != null) { await G.delVar(i.dataset.var); delete st.vars[i.dataset.var]; } }
        stat(m, 'ok', '✓ saved'); } catch (e) { stat(m, 'bad', e.message); }
    };
    $('#cloudCheck').onclick = () => S.hooks.cloudCheck && S.hooks.cloudCheck();
    wirePanels();
  }

  function wirePanels() {
    $$('.panel[data-secret]').forEach(p => {
      const kind = p.dataset.kind, secret = p.dataset.secret, msg = $('.m', p), keyIn = $('.k', p);
      const wrap = $('[data-pid]', p); const pid = wrap && wrap.dataset.pid;
      if (wrap) {
        $('.pp', p).onchange = e => { const pr = PRESETS.find(x => x[0] === e.target.value); if (pr && pr[1]) { $('.pu', p).value = pr[1]; $('.pm', p).value = pr[2]; $('.pn', p).value = pr[0]; } };
      }
      const test = async () => {
        const k = keyIn.value.trim();
        if (!k) { stat(msg, '', has(secret) ? 'Type the key to test it here, or use "Test all keys in the cloud" below.' : 'Paste the key first'); return null; }
        stat(msg, 'busy', 'Testing…'); let r;
        if (kind === 'gemini') r = await G.testGemini(k);
        else if (kind === 'pixabay') r = await G.testPixabay(k);
        else if (kind === 'pexels') r = await G.testPexels(k);
        else r = await G.testOpenAI($('.pu', p).value.trim(), k, $('.pm', p).value.trim());
        stat(msg, r.ok === true ? 'ok' : (r.ok === false ? 'bad' : 'busy'), statusIcon(r.ok) + ' ' + r.msg); return r;
      };
      $('.t', p).onclick = test;
      $('.s', p).onclick = async () => {
        try {
          const k = keyIn.value.trim();
          if (kind === 'custom') {
            const name = $('.pn', p).value.trim(), base = $('.pu', p).value.trim().replace(/\/+$/, ''), model = $('.pm', p).value.trim();
            if (!name || !/^https:\/\//.test(base) || !model) return stat(msg, 'bad', 'Fill name, Base URL (https://…) and model');
            const entry = st.providers.find(x => x.id === pid); const oldSecret = secret;
            if (entry.isNew) { let id = slug(name), n = 2; while (st.providers.some(x => x !== entry && x.id === id)) id = slug(name) + n++; entry.id = id; delete entry.isNew; }
            Object.assign(entry, { name, base_url: base, model, preset: $('.pp', p).value });
            if (!k && !has(secretName(entry.id)) && !has(oldSecret)) return stat(msg, 'bad', 'Paste the key');
            if (k) { const r = await test(); if (r && r.ok === false && !confirm('The test failed: ' + r.msg + '\n\nSave anyway?')) return; await G.putSecret(secretName(entry.id), k); if (!st.secrets.includes(secretName(entry.id))) st.secrets.push(secretName(entry.id)); }
            await G.setVar('AI_PROVIDERS', JSON.stringify(st.providers.map(x => ({ id: x.id, name: x.name, base_url: x.base_url, model: x.model, preset: x.preset })))); st.vars.AI_PROVIDERS = 'saved';
          } else {
            if (!k && kind === 'gemini' && $('#gemModel')) { /* only the model changes */ }
            else if (!k) return stat(msg, 'bad', 'Paste the key');
            if (k) { const r = await test(); if (r && r.ok === false && !confirm('The test failed: ' + r.msg + '\n\nSave anyway?')) return; await G.putSecret(secret, k); if (!st.secrets.includes(secret)) st.secrets.push(secret); }
            if (kind === 'gemini') { const m = $('#gemModel').value.trim(); if (m) { await G.setVar('GEMINI_MODEL', m); st.vars.GEMINI_MODEL = m; } else if (st.vars.GEMINI_MODEL) { await G.delVar('GEMINI_MODEL'); delete st.vars.GEMINI_MODEL; } }
          }
          S.toast('Saved in GitHub'); refreshModels(); renderRest();
        } catch (e) { stat(msg, 'bad', e.message); }
      };
      const d = $('.d', p);
      if (d) d.onclick = async () => {
        if (!confirm('Remove this key from GitHub?')) return;
        try {
          await G.delSecret(secret); st.secrets = st.secrets.filter(x => x !== secret);
          if (kind === 'custom') { st.providers = st.providers.filter(x => x.id !== pid); await G.setVar('AI_PROVIDERS', JSON.stringify(st.providers)); }
          refreshModels(); renderRest(); S.toast('Removed');
        } catch (e) { stat(msg, 'bad', e.message); }
      };
    });
  }

  S.boot = (S.boot || []).concat([async () => { updatePill(); if (G.ready()) { await load(); updatePill(); } }]);
})();
