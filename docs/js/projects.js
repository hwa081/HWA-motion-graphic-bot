/* Projects: separate folders for your videos. The list lives in the repository (outputs/projects.json); every video remembers its project (outputs/index.json). */
(function () {
  'use strict';
  const S = window.Studio, G = S.gh, $ = S.$, st = S.state, esc = S.esc, store = S.store;
  const DEFAULT = { id: 'default', name: 'My project' };
  S.projects = store.get('projects', [DEFAULT]);
  if (!S.projects.some(p => p.id === 'default')) S.projects.unshift(DEFAULT);
  const b64 = str => btoa(unescape(encodeURIComponent(str)));

  const find = id => S.projects.find(p => p.id === id);
  S.currentProject = () => (st.project === '*' ? 'default' : (find(st.project) ? st.project : 'default'));   // where new videos go
  function label() { $('#projName').textContent = st.project === '*' ? 'All projects' : (find(st.project) || DEFAULT).name; }
  function setCurrent(id) { st.project = id; store.set('project', id); label(); renderMenu(); S.renderGrid(); }
  S.setProject = setCurrent;

  S.setProjects = function (list) {              // called after outputs/projects.json was read
    if (!Array.isArray(list) || !list.length) return;
    const ok = list.filter(p => p && p.id && p.name);
    if (!ok.some(p => p.id === 'default')) ok.unshift(DEFAULT);
    S.projects = ok; store.set('projects', ok);
    if (st.project !== '*' && !find(st.project)) { st.project = 'default'; store.set('project', 'default'); }
    label(); renderMenu();
  };
  async function save() {
    store.set('projects', S.projects);
    if (!G.ready()) return;
    try { await G.putFile('outputs/projects.json', b64(JSON.stringify(S.projects, null, 1)), 'projects'); }
    catch (e) { S.toast('Could not save the project list: ' + e.message, true); }
  }

  function renderMenu() {
    const m = $('#projMenu');
    const count = id => st.media.filter(x => x.kind === 'video' && !x.trashed && (id === '*' || (x.project || 'default') === id)).length;
    m.innerHTML = '<div class="pm-h">Projects</div>' +
      [{ id: '*', name: 'All projects' }].concat(S.projects).map(p => `<button class="pm-item ${st.project === p.id ? 'on' : ''}" data-p="${esc(p.id)}"><span>${esc(p.name)}</span><small>${count(p.id)}</small></button>`).join('') +
      '<hr><button class="pm-act" id="pmNew">+ New project</button>' +
      (st.project !== '*' ? '<button class="pm-act" id="pmRename">Rename this project</button>' : '') +
      (st.project !== '*' && st.project !== 'default' ? '<button class="pm-act danger" id="pmDelete">Delete this project</button>' : '');
    m.querySelectorAll('.pm-item').forEach(b => b.onclick = () => { setCurrent(b.dataset.p); m.hidden = true; });
    $('#pmNew').onclick = async () => {
      const name = (prompt('Name of the new project:') || '').trim().slice(0, 40); if (!name) return;
      const id = 'p' + Date.now().toString(36); S.projects.push({ id, name }); setCurrent(id); m.hidden = true; await save(); S.toast('Project "' + name + '" created');
    };
    const rn = $('#pmRename'); if (rn) rn.onclick = async () => {
      const p = find(st.project); const name = (prompt('New name:', p.name) || '').trim().slice(0, 40); if (!name) return;
      p.name = name; label(); renderMenu(); m.hidden = true; await save();
    };
    const dl = $('#pmDelete'); if (dl) dl.onclick = async () => {
      const p = find(st.project); if (!confirm('Delete project "' + p.name + '"?\n\nIts videos are not deleted: they move to "My project".')) return;
      S.projects = S.projects.filter(x => x.id !== p.id); st.media.forEach(x => { if (x.project === p.id) x.project = 'default'; });
      m.hidden = true; setCurrent('default'); await save(); if (S.hooks.moveProject) await S.hooks.moveProject(p.id, 'default');
    };
  }
  S.renderProjMenu = renderMenu;

  S.boot = (S.boot || []).concat([() => {
    label(); renderMenu();
    const toggle = e => { e.stopPropagation(); const m = $('#projMenu'); renderMenu(); m.hidden = !m.hidden; };
    $('#projName').onclick = toggle; $('#btnProjMenu').onclick = toggle;
    $('#projMenu').onclick = e => e.stopPropagation();
    document.addEventListener('click', () => { $('#projMenu').hidden = true; });
  }]);
})();
