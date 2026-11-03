/* Generate, progress, results. The page starts the bot (GitHub Actions), watches the run and shows outputs/index.json from the repository. */
(function () {
  'use strict';
  const S = window.Studio, G = S.gh, $ = S.$, st = S.state, store = S.store;
  let pend = store.get('pending', []);       // {job, label, prompt, size, dur, mode, inputs, dispatched, t0, run}
  let rawIndex = [], timer = null, busy = false, again = false;
  const jid = () => 'j' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
  const savePend = () => store.set('pending', pend);
  const safe = n => String(n).replace(/[^A-Za-z0-9._-]+/g, '_').slice(-60);
  const b64 = str => btoa(unescape(encodeURIComponent(str)));
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  function toItem(e) {
    const it = { id: e.id, job: e.job, kind: e.kind === 'video' ? 'video' : 'report', title: e.title, prompt: e.prompt, mode: e.mode, size: e.size, dur: e.dur, date: Date.parse(e.date) || 0,
      trashed: !!e.trashed, design_id: e.design_id, ai: e.ai, report: e.report, spec: e.spec, video: e.video, note: e.note };
    if (e.video) it.url = G.rawUrl(e.video);
    if (e.poster) it.poster = G.rawUrl(e.poster);
    return it;
  }

  /* ---------------- refresh ---------------- */
  S.hooks.refresh = async function (force) {
    if (busy) { if (force) again = true; return; } busy = true;
    try {
      if (!G.ready()) { st.media = []; st.jobs = []; S.renderGrid(); return; }
      const txt = await G.readText('outputs/index.json');
      try { rawIndex = txt ? JSON.parse(txt) : []; } catch (e) { rawIndex = []; }
      st.media = rawIndex.map(toItem);
      await syncRuns();
      st.jobs = pend.map(p => ({ id: p.job, label: p.failed ? 'Failed' : (p.label || 'Working'), detail: p.detail || '', size: p.size, failed: !!p.failed, runUrl: p.runUrl, jobId: p.job }));
      if (st.view === 'media') S.renderGrid();
      if (st.view === 'tools' && S.hooks.renderTools) S.hooks.renderTools();
    } catch (e) { if (force) S.toast(e.message, true); }
    finally { busy = false; if (again) { again = false; return S.hooks.refresh(true); } schedule(); }
  };
  function schedule() {
    clearTimeout(timer);
    if (!G.ready()) return;
    timer = setTimeout(() => S.hooks.refresh(), pend.some(p => !p.failed) ? 6000 : 45000);
  }

  async function syncRuns() {
    if (!pend.length) return;
    const runs = await G.runs(25);
    for (const p of pend) {
      if (p.failed) continue;
      const run = runs.find(r => (r.display_title || r.name || '').includes(p.job));
      const indexed = rawIndex.find(e => e.id === p.job);
      if (run) {
        p.run = run.id; p.runUrl = run.html_url;
        if (run.status === 'completed') {
          if (run.conclusion === 'success') { p.ok = true; if (!p.doneAt) p.doneAt = Date.now(); p.label = 'Finishing'; p.detail = 'saving the result'; }
          else { p.failed = true; p.label = 'Failed'; p.detail = run.conclusion + ' - click to open the log'; }
        } else {
          p.label = run.status === 'queued' ? 'Queued' : 'Running';
          if (run.status === 'in_progress') { try { const jr = await G.req('GET', '/repos/' + G.cfg().repo + '/actions/runs/' + run.id + '/jobs'); const stp = ((jr.json && jr.json.jobs && jr.json.jobs[0] && jr.json.jobs[0].steps) || []); const cur = stp.find(x => x.status === 'in_progress') || stp.filter(x => x.status === 'completed').pop(); p.detail = cur ? cur.name.replace(/^Run$/, 'Making the video') : ''; } catch (e) {} }
        }
      } else if (p.dispatched) {
        if (Date.now() - p.dispatched > 4 * 60000) { p.failed = true; p.label = 'Failed'; p.detail = 'the run did not start - is the bot workflow in the repository?'; }
        else { p.label = 'Starting'; p.detail = 'waiting for GitHub'; }
      }
    }
    // finished jobs leave the list
    const done = pend.filter(p => !p.failed && (rawIndex.find(e => e.id === p.job) || (p.ok && (!p.expectOutput || Date.now() - p.doneAt > 20000))));
    if (done.length) {
      pend = pend.filter(p => !done.includes(p)); 
      for (const p of done) { if (p.onDone) S.toast(p.onDone); if (p.mode === 'checks' && S.hooks.showCloudChecks) setTimeout(S.hooks.showCloudChecks, 300); }
    }
    // client-side queue: the workflow runs one at a time, so start the next one only when nothing is active
    const active = pend.some(p => p.dispatched && !p.failed);
    if (!active) {
      const next = pend.find(p => !p.dispatched && !p.failed);
      if (next) {
        try { await G.dispatch(next.inputs); next.dispatched = Date.now(); next.label = 'Starting'; }
        catch (e) { next.failed = true; next.label = 'Failed'; next.detail = e.message; S.toast(e.message, true); }
      }
    } else pend.filter(p => !p.dispatched && !p.failed).forEach(p => { p.label = 'Waiting'; p.detail = 'in the queue'; });
    savePend();
  }
  S.hooks.onJobClick = function (m) {
    const p = pend.find(x => x.job === m.jobId);
    if (!p) return;
    if (p.runUrl && confirm('Open the log of this failed run in GitHub?\n\n(Cancel = remove it from the list)')) window.open(p.runUrl, '_blank', 'noopener');
    else { pend = pend.filter(x => x !== p); savePend(); S.hooks.refresh(true); }
  };

  /* ---------------- start something ---------------- */
  S.queue = function (p) {
    pend.push(Object.assign({ job: jid(), t0: Date.now(), dispatched: 0 }, p)); savePend();
    st.jobs = pend.map(x => ({ id: x.job, label: x.label || 'Queued', detail: x.detail || '', size: x.size, failed: x.failed, jobId: x.job }));
    if (st.view === 'media') S.renderGrid();
    clearTimeout(timer); S.hooks.refresh(true);
  };
  async function ensureKeys() {
    if (!S.settings.loaded) await S.settingsLoad();
    const sec = S.settings.secrets || [];
    return sec.includes('GEMINI_API_KEY') || sec.some(x => x.startsWith('AI_KEY_'));
  }
  S.tool = async function (mode, prompt, files, label, extra) {
    if (!G.ready()) { S.toast('Connect GitHub in Settings first', true); S.show('settings'); return false; }
    if (['study', 'ai', 'code', 'compare', 'evolve', 'learn'].includes(mode) && mode !== 'compare' && !(await ensureKeys())) { S.toast('Add an AI key in Settings first', true); S.show('settings'); return false; }
    const job = jid();
    const inputs = Object.assign({ mode, prompt: prompt || '', files: files || '', formats: 'none', sound: 'none', ai: st.cfg.model === 'gemini' ? 'gemini' : st.cfg.model, job }, extra || {});
    S.queue(Object.assign({ job, label: label || 'Queued', mode, prompt, inputs, expectOutput: false }));
    S.toast((label || mode) + ' - started'); return true;
  };

  S.hooks.onSend = async function (text, cfg, attach) {
    if (!G.ready()) { S.toast('Connect GitHub in Settings first', true); S.show('settings'); return false; }
    if (!(await ensureKeys())) { S.toast('Add an AI key (Gemini or another) in Settings first', true); S.show('settings'); return false; }
    const files = [];
    try {
      let i = 0;
      for (const a of attach) {
        if (a.repoPath) { files.push(a.repoPath); continue; }
        S.toast('Uploading ' + a.file.name + '…');
        const path = (a.kind === 'video' ? 'reference/' : 'assets/uploads/') + Date.now().toString(36) + (i++) + '_' + safe(a.file.name);
        await G.putFile(path, await G.fileToB64(a.file), 'upload from studio'); files.push(path);
      }
    } catch (e) { S.toast(e.message, true); return false; }
    const n = Math.max(1, cfg.n | 0);
    for (let k = 0; k < n; k++) {
      const job = jid();
      const inputs = { mode: cfg.mode, prompt: text, duration: String(cfg.dur), size: cfg.size, review: String(!!cfg.review), files: files.join(','), formats: 'none', sound: cfg.sound ? 'kinetic' : 'none', ai: cfg.model === 'gemini' ? 'gemini' : cfg.model, job };
      S.queue({ job, label: 'Queued', prompt: text, size: cfg.size, dur: cfg.dur, mode: cfg.mode, inputs, expectOutput: true });
    }
    S.toast(n > 1 ? n + ' videos queued (they run one after another)' : 'Started - it will appear here when it is ready');
    return true;
  };

  S.hooks.useAsReference = function (m) {
    if (!m.video) return;
    st.attach = st.attach.filter(a => a.kind !== 'video'); st.attach.push({ kind: 'video', repoPath: m.video, file: { name: (m.title || 'reference') }, url: '' });
    S.renderAttach(); S.closeViewer(); S.toast('Added as the reference video - now describe your own video');
  };
  S.hooks.feedback = async function (m, stars, note) {
    if (!m.design_id) { S.toast('This video has no design id (feedback works for AI plan / Code videos)', true); return; }
    const ok = await S.tool('feedback', note || '(rating only)', '', 'Learning from your feedback', { rating: String(stars), design_id: m.design_id });
    if (ok) S.closeViewer();
  };
  S.hooks.trash = async function (m, flag) {
    try {
      const e = rawIndex.find(x => x.id === m.id); if (!e) return;
      e.trashed = flag; m.trashed = flag;
      await G.putFile('outputs/index.json', b64(JSON.stringify(rawIndex, null, 1)), (flag ? 'trash ' : 'restore ') + m.id);
      S.renderGrid(); S.toast(flag ? 'Moved to trash' : 'Restored');
    } catch (err) { S.toast(err.message, true); }
  };
  S.hooks.onOpen = async function (m) {
    try {
      const t = m.report ? await G.readText(m.report) : null;
      const txt = t || (m.note || 'No report for this item.');
      S.setReport(txt);
      if (m.kind === 'report') { const pre = $('#vMedia pre'); if (pre) pre.textContent = txt; }
    } catch (e) { S.setReport(e.message); }
  };
  S.reports = () => st.media.filter(m => m.kind === 'report' && !m.trashed);

  S.hooks.cloudCheck = async function () {
    const ok = await S.tool('checks', '', '', 'Testing your keys', {});
    if (ok) { const m = $('#cloudMsg'); if (m) { m.className = 'status busy'; m.textContent = 'Started - the result appears below in about a minute'; } }
  };
  S.hooks.showCloudChecks = async function () {
    const box = $('#cloudRes'); if (!box || !G.ready()) return;
    try {
      const t = await G.readText('outputs/checks.json'); if (!t) { box.innerHTML = ''; return; }
      const d = JSON.parse(t);
      box.innerHTML = '<div>Last test</div><div class="status">' + S.esc(new Date(d.date).toLocaleString()) + '</div>' + d.results.map(r => `<div>${S.esc(r.name)}</div><div class="status ${r.ok === true ? 'ok' : (r.ok === false ? 'bad' : '')}">${r.ok === true ? '✓' : (r.ok === false ? '✕' : '•')} ${S.esc(r.msg)}</div>`).join('');
    } catch (e) { box.innerHTML = ''; }
  };

  S.boot = (S.boot || []).concat([() => { if (G.ready()) S.hooks.refresh(true); }]);
  document.addEventListener('visibilitychange', () => { if (!document.hidden && G.ready()) S.hooks.refresh(true); });
})();
