/* Library (what the bot remembers) and Tools (compare, remix, study, learn, evolve) */
(function () {
  'use strict';
  const S = window.Studio, G = S.gh, $ = S.$, $$ = S.$$, esc = S.esc, st = S.state;
  const MEM = { designs: 'memory/designs.json', lessons: 'memory/lessons.json', techniques: 'memory/notebook.json', wishes: 'memory/notebook.json' };
  const cache = {};
  async function readJson(path) {
    const t = await G.readText(path); try { return t ? JSON.parse(t) : null; } catch (e) { return null; }
  }
  const card = (h, p, meta, extra) => `<div class="card"><h3>${esc(h)}</h3>${p ? `<p>${esc(p)}</p>` : ''}${meta ? `<div class="meta">${esc(meta)}</div>` : ''}${extra || ''}</div>`;

  S.hooks.renderLibrary = async function () {
    const body = $('#libBody');
    $$('#libTabs .tab').forEach(t => { t.classList.toggle('active', t.dataset.lib === st.libTab); t.onclick = () => { st.libTab = t.dataset.lib; S.hooks.renderLibrary(); }; });
    if (!G.ready()) { body.innerHTML = card('Not connected', 'Connect GitHub in Settings to see what the bot has learned.'); return; }
    body.innerHTML = card('Loading…', '');
    try {
      const data = await readJson(MEM[st.libTab]); cache[st.libTab] = data;
      let html = '';
      if (st.libTab === 'designs') {
        const ds = (data || []).slice().reverse();
        html = ds.map(d => card(d.prompt || d.id, '', [d.size, d.review_score != null ? 'AI review ' + d.review_score + '/10' : '', d.rating ? 'your rating ' + d.rating + '/5' : '', d.fidelity != null ? 'fidelity ' + Math.round(d.fidelity) + '/100' : ''].filter(Boolean).join(' · '),
          d.plan ? `<p>${esc(d.plan.signature || d.plan.concept || '')}</p>` : '')).join('');
      } else if (st.libTab === 'lessons') {
        html = (data || []).slice().sort((a, b) => (b.weight || 1) - (a.weight || 1)).map(l => card((l.kind === 'do' ? 'DO' : "DON'T") + ' · weight ' + (l.weight || 1), l.text, 'seen ' + (l.count || 1) + '× · ' + (l.source || ''))).join('');
      } else if (st.libTab === 'techniques') {
        html = ((data && data.techniques) || []).slice().sort((a, b) => (b.weight || 1) - (a.weight || 1)).map(t => card(t.name, t.how, (t.when ? 'when: ' + t.when + ' · ' : '') + (t.source || ''))).join('');
      } else {
        html = ((data && data.wishes) || []).filter(w => !w.done).sort((a, b) => (b.count || 1) - (a.count || 1)).map(w => card(w.text, '', 'wanted ' + (w.count || 1) + '× · ' + (w.source || ''))).join('');
        const done = ((data && data.wishes) || []).filter(w => w.done).length;
        if (done) html += card('Built so far', done + ' effect(s) were built by the bot (Tools → Evolve).');
      }
      body.innerHTML = html || card('Nothing yet', 'The bot fills this after your first videos' + (st.libTab === 'techniques' ? ', after Study, or after it learns from a reference video.' : '.'));
    } catch (e) { body.innerHTML = card('Could not load', e.message); }
  };

  /* ---------------- tools ---------------- */
  function vidOptions(sel) { return st.media.filter(m => m.video && !m.trashed).map(m => `<option value="${esc(m.video)}">${esc((m.title || m.id).slice(0, 50))}</option>`).join(''); }
  S.hooks.renderTools = function () {
    const box = $('#toolCards'); const vids = vidOptions();
    const keep = {}; $$('#toolCards [data-keep]').forEach(i => { keep[i.dataset.keep] = i.value; });
    box.innerHTML = `
      <div class="card"><h3>Compare with an example</h3><p>Measures how close your video is to an example (colours, pace, cuts, motion, layout) and learns from the gap.</p>
        <select data-keep="cmpA" id="cmpA"><option value="">Example video…</option>${vids}</select>
        <select data-keep="cmpB" id="cmpB"><option value="">Your video…</option>${vids}</select>
        <div class="meta">Or <button class="btn" id="cmpUp" style="height:30px">upload an example video</button> <span id="cmpUpName"></span></div>
        <button class="btn primary" id="cmpGo">Compare</button></div>
      <div class="card"><h3>Remix: a new design from old ones</h3><p>A new design plan made from the library and your liked videos (no AI quota).</p>
        <input data-keep="rmx" id="rmxIn" class="in" placeholder="Topic, e.g. documentary about the ocean"><button class="btn primary" id="rmxGo">Make a plan</button></div>
      <div class="card"><h3>Study: teach it a technique</h3><p>Paste a tutorial text or a link. The bot turns it into reusable techniques.</p>
        <textarea data-keep="std" id="stdIn" class="in" rows="3" placeholder="Text or https://… link"></textarea><button class="btn primary" id="stdGo">Study</button></div>
      <div class="card"><h3>Learn from reference videos</h3><p>Analyses the videos in the repository's <b>reference/</b> folder and remembers their style.</p><button class="btn primary" id="lrnGo">Learn</button></div>
      <div class="card"><h3>Evolve: build a missing effect</h3><p>Builds the most wanted effect from the wishlist with Code Studio and adds it to the library.</p><button class="btn primary" id="evoGo">Build it</button></div>
      <div class="card"><h3>Test all keys in the cloud</h3><p>Checks every saved key from inside GitHub.</p><button class="btn primary" id="ckGo">Test keys</button></div>
      <div class="card" style="grid-column:1/-1"><h3>Recent results</h3><div id="repList"></div></div>`;
    $$('#toolCards [data-keep]').forEach(i => { if (keep[i.dataset.keep] != null) i.value = keep[i.dataset.keep]; });
    $$('#toolCards .in, #toolCards select').forEach(i => { i.style.cssText = 'background:var(--bg2);border:1px solid var(--line);border-radius:10px;padding:10px 12px;color:var(--text);width:100%;font:inherit'; });
    let upPath = '';
    $('#cmpUp').onclick = () => { const f = document.createElement('input'); f.type = 'file'; f.accept = 'video/*'; f.onchange = async () => { const file = f.files[0]; if (!file) return; if (file.size > 25 * 1024 * 1024) return S.toast('Max 25 MB', true);
      try { S.toast('Uploading…'); upPath = 'reference/' + Date.now().toString(36) + '_' + file.name.replace(/[^A-Za-z0-9._-]+/g, '_'); await G.putFile(upPath, await G.fileToB64(file), 'upload example from studio'); $('#cmpUpName').textContent = file.name; S.toast('Uploaded'); } catch (e) { S.toast(e.message, true); } }; f.click(); };
    $('#cmpGo').onclick = () => { const a = upPath || $('#cmpA').value, b = $('#cmpB').value; if (!a || !b) return S.toast('Pick the example and your video', true); S.tool('compare', '', a + ',' + b, 'Comparing'); };
    $('#rmxGo').onclick = () => { const t = $('#rmxIn').value.trim(); if (!t) return S.toast('Write a topic', true); S.tool('remix', t, '', 'Making a remix plan', { duration: String(st.cfg.dur), size: st.cfg.size }); };
    $('#stdGo').onclick = () => { const t = $('#stdIn').value.trim(); if (!t) return S.toast('Paste a text or link', true); S.tool('study', t, '', 'Studying'); };
    $('#lrnGo').onclick = () => S.tool('learn', '', 'reference', 'Learning from references');
    $('#evoGo').onclick = () => S.tool('evolve', '', '', 'Building a new effect');
    $('#ckGo').onclick = () => S.hooks.cloudCheck();
    const reps = S.reports();
    $('#repList').innerHTML = reps.length ? reps.slice(0, 12).map((m, i) => `<div class="row" style="margin:4px 0"><button class="btn" data-r="${i}" style="flex:1;justify-content:flex-start">${esc(m.mode)} · ${esc((m.title || '').slice(0, 70))}</button><span class="status">${m.date ? esc(new Date(m.date).toLocaleString()) : ''}</span></div>`).join('') : '<div class="status">Nothing yet. Results of these tools appear here.</div>';
    $$('#repList [data-r]').forEach(b => b.onclick = () => S.openViewer(reps[+b.dataset.r]));
  };
})();
