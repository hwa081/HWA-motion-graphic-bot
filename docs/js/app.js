/* HWA Studio - UI core (Flow-style page). Other files add features through window.Studio:
   gh.js (GitHub + crypto + provider tests), settings.js, jobs.js (generate / progress / outputs), library.js (library + tools) */
(function () {
  'use strict';
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const store = {
    get(k, d) { try { const v = localStorage.getItem('hwa.' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('hwa.' + k, JSON.stringify(v)); } catch (e) {} },
    del(k) { try { localStorage.removeItem('hwa.' + k); } catch (e) {} }
  };
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const S = window.Studio = {
    $, $$, store, esc,
    state: {
      view: 'media', filter: 'all', query: '', media: [], jobs: [],
      cfg: Object.assign({ mode: 'ai', input: 'ingredients', size: '16:9', dur: 8, n: 1, model: 'gemini', review: true, sound: true, quality: 'draft', formats: [] }, store.get('composer', {})),
      attach: [],           // {file, kind:'image'|'video', url}
      libTab: 'designs', project: store.get('project', 'default')
    },
    hooks: {}             // onSend, renderSettings, renderLibrary, renderTools, onOpen, refresh
  };
  const st = S.state;

  S.toast = function (msg, bad) {
    const t = $('#toast'); t.textContent = msg; t.className = 'toast' + (bad ? ' bad' : ''); t.hidden = false;
    clearTimeout(S._tt); S._tt = setTimeout(() => { t.hidden = true; }, bad ? 6000 : 3200);
  };

  /* ---------------- views ---------------- */
  S.show = function (view, filter) {
    st.view = view; if (filter) st.filter = filter;
    $$('.view').forEach(v => v.classList.toggle('show', v.id === 'view-' + view));
    $$('#nav .nav-item, .side-bottom .nav-item[data-view]').forEach(b => {
      const on = b.dataset.view === view && (view !== 'media' || b.dataset.filter === st.filter);
      b.classList.toggle('active', on);
    });
    $('#composerWrap').style.display = (view === 'media' || view === 'tools') ? '' : 'none';
    if (view === 'media') S.renderGrid();
    if (view === 'settings' && S.hooks.renderSettings) S.hooks.renderSettings();
    if (view === 'library' && S.hooks.renderLibrary) S.hooks.renderLibrary();
    if (view === 'tools' && S.hooks.renderTools) S.hooks.renderTools();
    if (view === 'activity' && S.hooks.renderActivity) S.hooks.renderActivity();
    document.getElementById('app').classList.remove('showside');
  };

  /* ---------------- media grid ---------------- */
  function sizeClass(s) { return s === '16:9' ? 'h' : (s === '1:1' ? 'sq' : ''); }
  const PLAY = '<svg viewBox="0 0 24 24"><path d="M7 4l13 8-13 8z"/></svg>';
  S.items = function () {
    const q = st.query.trim().toLowerCase();
    let all = st.jobs.map(j => Object.assign({ kind: 'job' }, j)).concat(st.media.filter(m => m.kind !== 'report'));
    if (st.project && st.project !== '*') all = all.filter(m => (m.project || 'default') === st.project);
    const replaced = new Set(st.media.filter(m => m.parent && !m.trashed).map(m => m.parent));
    all = all.filter(m => !(m.kind === 'video' && replaced.has(m.id)));
    if (st.filter === 'trash') all = all.filter(m => m.trashed);
    else all = all.filter(m => !m.trashed);
    if (st.filter === 'video') all = all.filter(m => m.kind === 'video' || m.kind === 'job');
    if (st.filter === 'draft') all = all.filter(m => m.kind === 'video' && m.quality === 'draft');
    if (st.filter === 'long') all = all.filter(m => m.kind === 'video' && m.long);
    if (q) all = all.filter(m => (m.title || '').toLowerCase().includes(q) || (m.prompt || '').toLowerCase().includes(q));
    return all;
  };
  const fmtEta = s => s == null ? '' : (s >= 90 ? Math.round(s / 60) + ' min' : Math.max(1, Math.round(s)) + ' s') + ' left';
  function jobHtml(m) {
    const label = esc(m.label || (m.failed ? 'Failed' : 'Working'));
    const pr = m.prog;
    if (!m.failed && pr && typeof pr.pct === 'number') {
      const stages = pr.stages || [], cur = Math.min(stages.length - 1, pr.stage || 0);
      const frames = pr.frames && pr.frames[1] && !String(pr.detail || '').includes(pr.frames[1]) ? ` · ${pr.frames[0]}/${pr.frames[1]} frames` : '';
      return `<div class="pct">${Math.round(pr.pct)}%</div><div class="bar"><i style="width:${Math.max(2, Math.min(100, pr.pct))}%"></i></div>
        <div class="stg">${esc(stages[cur] || label)} <span>(${cur + 1}/${stages.length})</span></div>
        <div class="st">${esc(pr.detail || m.detail || '')}${esc(frames)}</div>
        <div class="eta">${esc(fmtEta(pr.eta))}${pr.eta == null && pr.elapsed ? esc(Math.round(pr.elapsed / 60 * 10) / 10 + ' min so far') : ''}</div>`;
    }
    if (m.failed) {
      const resumable = m.canResume;
      return `<div class="failmark">!</div><div>${label}</div><div class="st">${esc(m.detail || '')}</div>
        <div class="jobbtns"><button class="jb primary" data-act="continue" data-job="${esc(m.jobId)}">${resumable ? 'Continue' : 'Try again'}</button>${m.runUrl ? `<button class="jb" data-act="log" data-job="${esc(m.jobId)}">Log</button>` : ''}<button class="jb" data-act="remove" data-job="${esc(m.jobId)}">Remove</button></div>`;
    }
    return `<div class="spin"></div><div>${label}</div><div class="st">${esc(m.detail || '')}</div>`;
  }
  S.jobHtml = jobHtml;
  S.renderGrid = function () {
    const g = $('#grid'); const items = S.items();
    g.innerHTML = items.map((m, i) => {
      const sc = sizeClass(m.size);
      if (m.kind === 'job') {
        return `<div class="tile busy ${sc} ${m.failed ? 'fail' : ''}" data-i="${i}"><div class="jobbox">${jobHtml(m)}</div></div>`;
      }
      const poster = m.poster ? `<img loading="lazy" src="${esc(m.poster)}" alt="">` : '<div class="ph"></div>';
      const badge = m.kind === 'video' ? `<span class="play">${PLAY}</span><span class="tag">${esc(m.size || '')} · ${esc(m.dur || '')}s</span>` : `<span class="tag">${esc(m.size || 'image')}</span>`;
      return `<div class="tile ${sc}" data-i="${i}" title="${esc(m.prompt || m.title)}">${poster}<div class="badge">${badge}</div><div class="cap"><span>${esc(m.title || m.prompt || '')}</span></div></div>`;
    }).join('');
    const empty = items.length === 0;
    $('#empty').hidden = !empty;
    if (empty) {
      const conn = S.hooks.connected && S.hooks.connected();
      $('#emptySub').innerHTML = conn ? 'Type what you want to create in the bar below.' : 'Open <b>Settings</b> to connect GitHub and add your API keys, then type what you want to create below.';
      const ideas = [
        ['YouTube intro, 8 s', 'A punchy 8 second YouTube channel intro: bold kinetic typography, neon glow, quick logo reveal at the end', { dur: 8, size: '16:9' }],
        ['Shorts / Reels hook, 10 s', 'A vertical 10 second hook for Shorts: one big claim, three animated stat counters, strong final call to action', { dur: 10, size: '9:16' }],
        ['Product promo, 30 s', 'A 30 second product promo for a smart watch: hero shot, three feature cards, price reveal, clean modern light theme', { dur: 30, size: '16:9' }],
        ['Explainer, 1 min', 'A 1 minute explainer: how solar panels turn sunlight into electricity, simple diagrams, step by step', { dur: 60, size: '16:9' }],
        ['Documentary, 5 min', 'A 5 minute calm documentary about the deep ocean: five chapters, big titles, slow camera moves, facts as animated cards', { dur: 300, size: '16:9' }]
      ];
      $('#ideas').innerHTML = '<div class="ideas-h">Ideas to start with</div>' + ideas.map((x, i) => `<button class="idea" data-i="${i}">${esc(x[0])}</button>`).join('');
      $$('#ideas .idea').forEach(b => b.onclick = () => { const x = ideas[+b.dataset.i]; Object.assign(st.cfg, x[2], { mode: 'ai' }); save(); $('#prompt').value = x[1]; syncSend(); $('#prompt').focus(); });
    }
    $$('.tile', g).forEach(t => t.onclick = e => { const jb = e.target.closest('.jb'); if (jb) { e.stopPropagation(); if (S.hooks.onJobAction) S.hooks.onJobAction(jb.dataset.job, jb.dataset.act); return; } const m = items[+t.dataset.i]; if (m && m.kind !== 'job') S.openViewer(m); });
  };

  /* ---------------- viewer ---------------- */
  let cur = null, stars = 0;
  S.openViewer = function (m) {
    cur = m; stars = 0;
    $('#vMedia').innerHTML = m.kind === 'report' ? '<pre style="width:100%;max-height:76vh;margin:0">Loading…</pre>' : m.kind === 'video' ? `<video src="${esc(m.url)}" controls autoplay loop playsinline poster="${esc(m.poster || '')}"></video>` : `<img src="${esc(m.url || m.poster)}" alt="">`;
    $('#vTitle').textContent = m.prompt || m.title || '';
    $('#vMeta').textContent = [m.quality === 'draft' ? 'DRAFT' : '', m.size, m.dur ? m.dur + 's' : '', m.mode, m.date ? new Date(m.date).toLocaleString() : ''].filter(Boolean).join(' · ');
    const vf = $('#vFiles'); vf.innerHTML = '';
    if (m.kind === 'video') {
      const files = m.files || [];
      if (files.length) {
        vf.innerHTML = '<div class="vf-h">Files</div>';
        files.forEach(f => { const b = document.createElement('button'); b.className = 'btn small'; b.textContent = f.name.replace(/^.*\./, '.') + ' · ' + f.name + ' · ' + (f.size > 1e6 ? (f.size / 1e6).toFixed(1) + ' MB' : Math.max(1, Math.round(f.size / 1e3)) + ' KB'); b.onclick = () => S.download(S.hooks.rawUrl ? S.hooks.rawUrl(f.path) : f.path, f.name); vf.appendChild(b); });
      }
      const heavy = String(m.formats || '').split(',').filter(x => ['wfp', 'fcpxml', 'xml'].includes(x.trim()));
      if (m.quality === 'draft' && heavy.length) { const n = document.createElement('div'); n.className = 'vf-note'; n.textContent = 'Editor files (' + heavy.join(', ') + ') are made when you press "Make final".'; vf.appendChild(n); }
      else if (heavy.length && (m.files || []).some(f => /\.(wfp|xml|fcpxml)$/.test(f.name)) && m.video_name) { const n = document.createElement('div'); n.className = 'vf-note'; n.textContent = 'Put ' + m.video_name + ' (Download video) in your media folder, then open the project file.'; vf.appendChild(n); }
    }
    $('#vNote').value = ''; renderStars(); $('#vReport').textContent = 'Loading…';
    const a = $('#vActions'); a.innerHTML = '';
    const mk = (label, fn, cls) => { const b = document.createElement('button'); b.className = 'btn ' + (cls || ''); b.textContent = label; b.onclick = fn; a.appendChild(b); };
    $('.v-rate').style.display = m.kind === 'report' ? 'none' : '';
    if (m.kind === 'report') { /* text result: no media actions */ } else {
    if (m.url) mk('Download video', () => S.download(m.url, m.video_name || ((m.id || 'video') + '.mp4')), 'primary');
    if (S.hooks.viewerExtra) S.hooks.viewerExtra(m, mk);
    mk('Use as reference', () => { if (S.hooks.useAsReference) S.hooks.useAsReference(m); });
    mk('Make a variation', () => { $('#prompt').value = m.prompt || ''; syncSend(); S.closeViewer(); $('#prompt').focus(); });
    mk(m.trashed ? 'Restore' : 'Move to trash', () => { if (S.hooks.trash) S.hooks.trash(m, !m.trashed); S.closeViewer(); }, 'danger');
    }
    $('#viewer').hidden = false;
    if (S.hooks.onOpen) S.hooks.onOpen(m);
  };
  S.download = async function (url, name) {
    try {
      const r = await fetch(url); if (!r.ok) throw new Error('HTTP ' + r.status);
      const b = await r.blob(); const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = name || 'file'; document.body.appendChild(a); a.click();
      setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 4000);
    } catch (e) { window.open(url, '_blank', 'noopener'); }
  };
  S.closeViewer = function () { $('#viewer').hidden = true; $('#vMedia').innerHTML = ''; cur = null; };
  function renderStars() {
    $('#vStars').innerHTML = [1, 2, 3, 4, 5].map(n => `<button data-n="${n}" class="${n <= stars ? 'on' : ''}" aria-label="${n} stars">★</button>`).join('');
    $$('#vStars button').forEach(b => b.onclick = () => { stars = +b.dataset.n; renderStars(); });
  }
  S.setReport = t => { $('#vReport').textContent = t; };

  /* ---------------- composer ---------------- */
  function summary() {
    const c = st.cfg;
    const dl = c.dur >= 60 ? (c.dur % 60 ? Math.floor(c.dur / 60) + 'm' + (c.dur % 60) + 's' : (c.dur / 60) + ' min') : c.dur + 's';
    $('#chipSummary').textContent = `${c.mode === 'code' ? 'Code' : (c.dur > 60 ? 'Long video' : 'Video')} · ${c.size} · ${dl} · x${c.n}`;
    S.estimate();
  }
  S.estimate = function () {
    const c = st.cfg; let req = c.mode === 'code' ? 22 : (c.review ? 6 : 4);
    if (st.attach.some(a => a.kind === 'video')) req += 1;
    if (c.mode !== 'code' && c.dur > 60) {
      const parts = Math.ceil(c.dur / 30); req = parts * 3 + 2;
      $('#cost').textContent = `Long video: about ${parts} parts, ~${req * c.n} AI requests. If the free quota ends, press Continue later - finished parts are saved.`; return;
    }
    $('#cost').textContent = `Generating will use about ${req * c.n} AI request${req * c.n > 1 ? 's' : ''} (${c.n} run${c.n > 1 ? 's' : ''})`;
  };
  function syncSeg() {
    const c = st.cfg;
    $$('#segMode button').forEach(b => b.classList.toggle('on', b.dataset.mode === c.mode));
    $$('#segInput button').forEach(b => b.classList.toggle('on', b.dataset.input === c.input));
    $$('#segSize button, #segSize2 button').forEach(b => b.classList.toggle('on', b.dataset.size === c.size));
    $$('#segDur button, #segDur2 button').forEach(b => b.classList.toggle('on', +b.dataset.dur === c.dur));
    $$('#segCount button').forEach(b => b.classList.toggle('on', +b.dataset.n === c.n));
    $('#optReview').checked = !!c.review; $('#optSound').checked = !!c.sound;
    $$('#fmtRow .fchip[data-f]').forEach(b => b.classList.toggle('on', (c.formats || []).includes(b.dataset.f)));
    const q = c.mode === 'code' ? 'final' : (c.quality || 'draft');
    $$('#qual button').forEach(b => { b.classList.toggle('on', b.dataset.q === q); b.disabled = c.mode === 'code' && b.dataset.q === 'draft'; });
    $('#qual').title = c.mode === 'code' ? 'Code Studio always makes the full-quality video' : 'Draft = fast small preview (half size). Final = full quality + the editor files.';
    $('#durCustom').value = [4, 6, 8, 10, 30, 60, 180, 300].includes(c.dur) ? '' : c.dur;
    summary();
  }
  function save() { store.set('composer', st.cfg); syncSeg(); }
  function syncSend() {
    const ta = $('#prompt'); ta.style.height = 'auto'; ta.style.height = Math.min(180, ta.scrollHeight) + 'px';
    $('#btnSend').classList.toggle('ready', ta.value.trim().length > 0);
  }
  S.setModels = function (list) {   // [{id,label}]
    const sel = $('#selModel'); const keep = st.cfg.model;
    sel.innerHTML = list.map(m => `<option value="${esc(m.id)}">${esc(m.label)}</option>`).join('');
    sel.value = list.some(m => m.id === keep) ? keep : (list[0] && list[0].id); st.cfg.model = sel.value;
  };
  S.renderAttach = function () {
    const r = $('#attachRow'); r.hidden = st.attach.length === 0;
    r.innerHTML = st.attach.map((a, i) => a.kind === 'image'
      ? `<div class="att"><img src="${esc(a.url)}" alt=""><button data-i="${i}" aria-label="Remove">✕</button></div>`
      : `<div class="att ref">🎞 ${esc(a.file.name.slice(0, 18))}<button data-i="${i}" aria-label="Remove" style="position:static;margin-left:6px">✕</button></div>`).join('');
    $$('button', r).forEach(b => b.onclick = () => { URL.revokeObjectURL(st.attach[+b.dataset.i].url); st.attach.splice(+b.dataset.i, 1); S.renderAttach(); S.estimate(); });
    S.estimate();
  };
  S.addFiles = function (files) {
    for (const f of files) {
      const kind = f.type.startsWith('video') ? 'video' : (f.type.startsWith('image') ? 'image' : null);
      if (!kind) { S.toast('Only images and videos can be added', true); continue; }
      if (f.size > 25 * 1024 * 1024) { S.toast(f.name + ' is bigger than 25 MB (GitHub upload limit in the browser)', true); continue; }
      if (kind === 'video') st.attach = st.attach.filter(a => a.kind !== 'video');   // one reference video
      st.attach.push({ file: f, kind, url: URL.createObjectURL(f) });
    }
    S.renderAttach();
  };

  function wire() {
    // nav
    $$('#nav .nav-item[data-view], .side-bottom .nav-item[data-view], .top-right [data-view]').forEach(b => b.onclick = () => S.show(b.dataset.view, b.dataset.filter));
    $('#btnHome').onclick = () => S.show('media', 'all');
    $('#btnCollapse').onclick = () => $('#app').classList.toggle('collapsed');
    $('#btnRefresh').onclick = () => { if (S.hooks.refresh) S.hooks.refresh(true); };
    $('#btnHelp').onclick = () => S.toast('Settings → connect GitHub → add keys → type a prompt below.');
    $('#btnFilter').onclick = () => { const order = ['all', 'video', 'draft', 'long']; S.show('media', order[(order.indexOf(st.filter) + 1) % order.length]); S.toast('Showing: ' + st.filter); };
    $('#search').oninput = e => { st.query = e.target.value; if (st.view !== 'media') S.show('media'); else S.renderGrid(); };
    // viewer
    $('#vClose').onclick = S.closeViewer;
    $('#viewer').onclick = e => { if (e.target.id === 'viewer') S.closeViewer(); };
    document.addEventListener('keydown', e => { if (e.key === 'Escape') { S.closeViewer(); $('#popup').hidden = true; } });
    $('#vSendFb').onclick = () => { if (!cur) return; if (!stars) return S.toast('Pick 1-5 stars first', true); if (S.hooks.feedback) S.hooks.feedback(cur, stars, $('#vNote').value.trim()); };
    // composer
    const ta = $('#prompt'); ta.oninput = syncSend;
    ta.onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };
    $('#btnSend').onclick = send;
    const togglePop = e => { e.stopPropagation(); const h = !$('#popup').hidden; $('#popup').hidden = h; $('#btnTune').classList.toggle('open', !h); };
    $('#chipSummary').onclick = togglePop; $('#btnTune').onclick = togglePop;
    $('#popClose').onclick = e => { e.stopPropagation(); $('#popup').hidden = true; $('#btnTune').classList.remove('open'); };
    $('#popup').onclick = e => e.stopPropagation();
    document.addEventListener('click', () => { $('#popup').hidden = true; $('#btnTune').classList.remove('open'); });
    $('#chipAgent').onclick = () => { const on = !$('#chipAgent').classList.contains('on'); $('#chipAgent').classList.toggle('on', on); st.cfg.mode = on ? 'code' : 'ai'; save(); };
    $$('#segMode button').forEach(b => b.onclick = () => { st.cfg.mode = b.dataset.mode; $('#chipAgent').classList.toggle('on', st.cfg.mode === 'code'); save(); });
    $$('#segInput button').forEach(b => b.onclick = () => { st.cfg.input = b.dataset.input; save(); $('#fileIn').accept = b.dataset.input === 'reference' ? 'video/mp4,video/webm,video/quicktime' : 'image/*'; $('#fileIn').click(); });
    $$('#segSize button, #segSize2 button').forEach(b => b.onclick = () => { st.cfg.size = b.dataset.size; save(); });
    $$('#segDur button, #segDur2 button').forEach(b => b.onclick = () => { st.cfg.dur = +b.dataset.dur; save(); });
    $$('#segCount button').forEach(b => b.onclick = () => { st.cfg.n = +b.dataset.n; save(); });
    $('#durCustom').onchange = e => { const v = parseFloat(e.target.value); if (v >= 3 && v <= 600) { st.cfg.dur = v; save(); } else if (e.target.value) S.toast('Length must be 3 to 600 seconds (10 minutes)', true); };
    $('#selModel').onchange = e => { st.cfg.model = e.target.value; save(); };
    $$('#fmtRow .fchip[data-f]').forEach(b => b.onclick = () => { const f = b.dataset.f, a = st.cfg.formats || []; st.cfg.formats = a.includes(f) ? a.filter(x => x !== f) : a.concat(f); save(); });
    $$('#qual button').forEach(b => b.onclick = () => { st.cfg.quality = b.dataset.q; save(); });
    $('#optReview').onchange = e => { st.cfg.review = e.target.checked; save(); };
    $('#optSound').onchange = e => { st.cfg.sound = e.target.checked; save(); };
    $('#btnAttach').onclick = () => { $('#fileIn').accept = 'image/*,video/mp4,video/webm,video/quicktime'; $('#fileIn').click(); };
    $('#fileIn').onchange = e => { S.addFiles(Array.from(e.target.files)); e.target.value = ''; };
    const cw = $('#composer');
    ['dragover', 'drop'].forEach(ev => cw.addEventListener(ev, e => { e.preventDefault(); if (ev === 'drop') S.addFiles(Array.from(e.dataTransfer.files)); }));
    ta.addEventListener('paste', e => { const fs = Array.from(e.clipboardData.files || []); if (fs.length) { e.preventDefault(); S.addFiles(fs); } });
    window.addEventListener('resize', () => {});
  }
  function send() {
    const text = $('#prompt').value.trim();
    if (!text) return;
    if (!S.hooks.onSend) return S.toast('Not ready yet', true);
    Promise.resolve(S.hooks.onSend(text, Object.assign({}, st.cfg), st.attach.slice())).then(ok => {
      if (ok !== false) { $('#prompt').value = ''; st.attach = []; S.renderAttach(); syncSend(); }
    }).catch(e => S.toast(String(e && e.message || e), true));
  }

  S.init = function () {
    wire(); S.setModels([{ id: 'gemini', label: 'Gemini' }]); syncSeg(); syncSend();
    $('#chipAgent').classList.toggle('on', st.cfg.mode === 'code');
    const q = new URLSearchParams(location.search);
    if (q.has('demo')) S.loadDemo();
    S.show('media', 'all');
    (S.boot || []).forEach(fn => { try { fn(); } catch (e) { console.error(e); } });
  };

  /* ---------------- demo data (?demo) so the page can be seen without GitHub ---------------- */
  function poster(a, b, label) {
    const c = document.createElement('canvas'); c.width = 270; c.height = 480; const x = c.getContext('2d');
    const g = x.createLinearGradient(0, 0, 270, 480); g.addColorStop(0, a); g.addColorStop(1, b); x.fillStyle = g; x.fillRect(0, 0, 270, 480);
    x.fillStyle = 'rgba(255,255,255,.12)'; x.beginPath(); x.arc(135, 220, 80, 0, 7); x.fill();
    x.fillStyle = '#fff'; x.font = 'bold 26px sans-serif'; x.textAlign = 'center'; x.fillText(label, 135, 232);
    return c.toDataURL('image/jpeg', .8);
  }
  S.loadDemo = function () {
    const mk = (i, a, b, l, size, dur, kind) => ({ id: 'demo' + i, kind, size, dur, title: l, prompt: l + ' - demo prompt', poster: poster(a, b, l), url: '', mode: 'ai', date: Date.now() - i * 3600e3 });
    st.media = [mk(1, '#243b55', '#141e30', 'Pen macro', '9:16', 8, 'video'), mk(2, '#8e2de2', '#4a00e0', 'Nebula', '9:16', 6, 'video'), mk(3, '#0f2027', '#2c5364', 'Energy ring', '9:16', 8, 'video'),
      mk(4, '#434343', '#000', 'Fibers', '9:16', 10, 'video'), mk(5, '#355c7d', '#c06c84', 'Sunset intro', '16:9', 8, 'video'), mk(6, '#11998e', '#38ef7d', 'Logo reveal', '1:1', 4, 'video'), mk(7, '#fc4a1a', '#f7b733', 'Poster', '9:16', 0, 'image')];
    st.jobs = [{ id: 'j1', label: 'Running', detail: 'planning scenes…', size: '9:16' }];
    S.hooks.connected = () => true;
    const p = $('#connPill'); $('#connDot').className = 'dot ok'; $('#connText').textContent = 'demo';
  };

  document.addEventListener('DOMContentLoaded', S.init);
})();
