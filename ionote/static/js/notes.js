/** The sidebar (views, folders, tags) and the list of notes. */
import { $, h, api, state, icon, fmtDate, colorVar, menu, colorPicker, ask, confirmIt, toast, fail, canWrite, displayTitle } from './core.js';

export const view = { v: 'all', f: null, t: null, q: '', sort: localSort(), n: null };
const PAGE = 100;
let shown = [], total = 0, loading = false;
let onOpen = () => {};
export function setOpenHandler(fn) { onOpen = fn; }

function localSort() { try { return localStorage.getItem('ionotes.sort') || 'updated'; } catch (e) { return 'updated'; } }

export function viewFromHash() {
  const [path, qs] = location.hash.replace(/^#/, '').split('?');
  const p = new URLSearchParams(qs || '');
  const m = path.match(/^\/note\/([A-Za-z0-9-]+)/);
  Object.assign(view, { v: p.get('v') || 'all', f: p.get('f'), t: p.get('t'), q: p.get('q') || '', n: m ? m[1] : p.get('n') });
  if (view.f) view.v = 'folder';
  if (view.t) view.v = 'tag';
}

export function hashFor(changes = {}) {
  const v = { ...view, ...changes };
  const p = new URLSearchParams();
  if (v.v === 'folder' && v.f) p.set('f', v.f);
  else if (v.v === 'tag' && v.t) p.set('t', v.t);
  else if (v.v !== 'all') p.set('v', v.v);
  if (v.q) p.set('q', v.q);
  if (v.n) p.set('n', v.n);
  const s = p.toString();
  return '#/notes' + (s ? '?' + s : '');
}
export const go = (changes) => { location.hash = hashFor(changes); };

function title() {
  if (view.q) return `Search: ${view.q}`;
  if (view.v === 'folder') { const f = (state.meta.folders || []).find((x) => x.id === view.f); return f ? f.name : 'Folder'; }
  if (view.v === 'tag') return '#' + view.t;
  return { all: 'All notes', pinned: 'Pinned', images: 'Pictures', nofolder: 'No folder', trash: 'Trash' }[view.v] || 'Notes';
}

// ---- sidebar
export async function loadMeta() { state.meta = await api('/api/meta'); return state.meta; }

function navItem(label, ic, count, on, onclick, extra = {}) {
  const el = h('div.navitem' + (on ? '.on' : ''), { onclick, role: 'link', tabindex: 0, ...extra }, typeof ic === 'string' ? icon(ic) : ic, h('span.nm', label), count != null ? h('span.n', count) : null);
  el.addEventListener('keydown', (e) => { if (e.key === 'Enter') onclick(); });
  return el;
}

function dropTarget(el, folderId) {
  if (!canWrite()) return el;
  el.addEventListener('dragover', (e) => { if (e.dataTransfer.types.includes('application/x-ionotes-note')) { e.preventDefault(); el.classList.add('drop'); } });
  el.addEventListener('dragleave', () => el.classList.remove('drop'));
  el.addEventListener('drop', async (e) => {
    e.preventDefault(); el.classList.remove('drop');
    const id = e.dataTransfer.getData('application/x-ionotes-note');
    if (!id) return;
    try { await api(`/api/notes/${id}`, { method: 'PUT', body: { folderID: folderId, updatedAt: Date.now() / 1000 } }); toast(folderId ? 'Moved to the folder' : 'Taken out of its folder'); refresh(); } catch (err) { fail(err); }
  });
  return el;
}

export function renderNav() {
  const m = state.meta, nav = $('#nav');
  nav.textContent = '';
  const close = () => document.body.classList.remove('navopen');
  const sel = (changes) => { close(); go({ v: 'all', f: null, t: null, n: null, ...changes }); };
  nav.append(
    navItem('All notes', 'notes', m.total, view.v === 'all' && !view.q, () => sel({ q: '' })),
    navItem('Pinned', 'pin', m.pinned, view.v === 'pinned', () => sel({ v: 'pinned' })),
    navItem('Pictures', 'photo', m.images, view.v === 'images', () => sel({ v: 'images' })),
    dropTarget(navItem('No folder', 'folderOff', m.noFolder, view.v === 'nofolder', () => sel({ v: 'nofolder' })), null),
  );
  const fsec = h('div.navsec', h('div.navhead', h('span', 'Folders'), canWrite() ? h('button.iconbtn', { title: 'New folder', 'aria-label': 'New folder', onclick: newFolder }, icon('add')) : null));
  for (const f of m.folders) {
    const ic = icon('folder');
    if (f.color) ic.style.color = colorVar(f.color);
    const item = navItem(f.name, ic, f.count, view.v === 'folder' && view.f === f.id, () => sel({ v: 'folder', f: f.id }));
    if (canWrite()) item.addEventListener('contextmenu', (e) => { e.preventDefault(); folderMenu(e, f); });
    fsec.append(dropTarget(item, f.id));
  }
  if (!m.folders.length) fsec.append(h('div.navitem.muted.small', canWrite() ? 'Make folders like Work or AI with +' : 'No folders yet'));
  nav.append(fsec);
  if (m.tags.length) {
    const tsec = h('div.navsec', h('div.navhead', h('span', 'Tags')));
    for (const t of m.tags) {
      const d = h('span.dot');
      if (t.color) { d.style.background = colorVar(t.color); d.style.opacity = 1; }
      const item = navItem(t.name, d, t.count, view.v === 'tag' && view.t && view.t.toLowerCase() === t.name.toLowerCase(), () => sel({ v: 'tag', t: t.name }));
      if (canWrite()) item.addEventListener('contextmenu', (e) => { e.preventDefault(); tagMenu(e, t); });
      tsec.append(item);
    }
    nav.append(tsec);
  }
  nav.append(h('div.navsec', navItem('Trash', 'trash', m.trash || null, view.v === 'trash', () => sel({ v: 'trash' }))));
}

async function newFolder() {
  const name = await ask('New folder', 'Folder name', '', 'Create');
  if (!name) return;
  try { const f = await api('/api/folders', { method: 'POST', body: { name } }); await refresh(); go({ v: 'folder', f: f.id, n: null }); } catch (e) { fail(e); }
}

function folderMenu(e, f) {
  menu({ x: e.clientX, y: e.clientY }, [
    { head: f.name },
    { icon: 'edit', label: 'Rename…', action: async () => { const n = await ask('Rename folder', 'Folder name', f.name, 'Rename'); if (n) { await api(`/api/folders/${f.id}`, { method: 'PUT', body: { name: n, updatedAt: Date.now() / 1000 } }).catch(fail); refresh(); } } },
    { head: 'Colour' },
    { node: colorPicker(f.color, async (c) => { await api(`/api/folders/${f.id}`, { method: 'PUT', body: { color: c, updatedAt: Date.now() / 1000 } }).catch(fail); refresh(); }) },
    '-',
    { icon: 'trash', label: 'Delete folder…', action: async () => {
      if (!await confirmIt('Delete folder', `Delete "${f.name}"? Its ${f.count} notes stay, in no folder.`, 'Delete', true)) return;
      await api(`/api/folders/${f.id}`, { method: 'DELETE' }).catch(fail);
      if (view.f === f.id) go({ v: 'all', f: null }); else refresh();
    } },
  ]);
}

function tagMenu(e, t) {
  menu({ x: e.clientX, y: e.clientY }, [
    { head: '#' + t.name },
    { icon: 'edit', label: 'Rename on every note…', action: async () => { const n = await ask('Rename tag', 'Tag name', t.name, 'Rename'); if (n) { await api('/api/tags/rename', { method: 'POST', body: { from: t.name, to: n } }).catch(fail); refresh(); } } },
    { head: 'Colour' },
    { node: colorPicker(t.color, async (c) => { await api(`/api/tags/${encodeURIComponent(t.name)}/color`, { method: 'PUT', body: { color: c, updatedAt: Date.now() / 1000 } }).catch(fail); refresh(); }) },
    '-',
    { icon: 'trash', label: 'Remove from every note…', action: async () => {
      if (!await confirmIt('Remove tag', `Take #${t.name} off its ${t.count} notes?`, 'Remove', true)) return;
      await api('/api/tags/remove', { method: 'POST', body: { name: t.name } }).catch(fail);
      if (view.v === 'tag') go({ v: 'all', t: null }); else refresh();
    } },
  ]);
}

// ---- the list
function query(offset) {
  const p = new URLSearchParams({ sort: view.sort, limit: PAGE, offset });
  if (view.q) p.set('q', view.q);
  if (view.v === 'folder') p.set('folder', view.f);
  if (view.v === 'nofolder') p.set('folder', 'none');
  if (view.v === 'tag') p.set('tag', view.t);
  if (view.v === 'pinned') p.set('pinned', '1');
  if (view.v === 'images') p.set('image', '1');
  return p;
}

export async function loadList(append = false) {
  if (loading) return;
  loading = true;
  try {
    if (view.v === 'trash') {
      const r = await api('/api/trash');
      shown = r.notes; total = r.notes.length;
    } else {
      const r = await api('/api/notes?' + query(append ? shown.length : 0));
      shown = append ? shown.concat(r.notes) : r.notes;
      total = r.total;
    }
  } finally { loading = false; }
  renderList();
}

export const current = () => shown;

function card(n) {
  const tagColors = Object.fromEntries((state.meta.tags || []).map((t) => [t.name.toLowerCase(), t.color]));
  const folder = n.folderID && state.meta.folders.find((f) => f.id === n.folderID);
  const prev = (n.body || n.ocrText || '').replace(/\s+/g, ' ').slice(0, 200);
  const title = displayTitle(n);
  const c = h('div.card' + (n.id === view.n ? '.on' : ''), { draggable: canWrite() && view.v !== 'trash', onclick: () => onOpen(n.id), 'data-id': n.id },
    n.hasImage ? h('img.th', { src: `/api/notes/${n.id}/thumb?v=${(n.imageSHA || '').slice(0, 8)}`, alt: '', loading: 'lazy' }) : null,
    h('div.body', h('div.t', title), prev && prev !== title ? h('div.p', prev) : null,
      h('div.m', h('span', fmtDate(view.sort === 'created' || view.sort === 'oldest' ? n.createdAt : n.updatedAt)),
        folder && view.v !== 'folder' ? h('span', '· ' + folder.name) : null,
        n.tags.slice(0, 4).map((t) => { const s = h('span.tag', t); const cv = colorVar(tagColors[t.toLowerCase()]); if (cv) s.style.setProperty('--tc', cv); return s; }))),
    n.pinned ? h('span.pin', icon('pin')) : null);
  c.addEventListener('dragstart', (e) => { e.dataTransfer.setData('application/x-ionotes-note', n.id); e.dataTransfer.setData('text/plain', [n.title, n.body].filter(Boolean).join('\n\n')); });
  return c;
}

export function renderList() {
  const list = $('#list');
  if (!list) return;
  const sort = h('select', { 'aria-label': 'Sort', onchange: (e) => { view.sort = e.target.value; try { localStorage.setItem('ionotes.sort', view.sort); } catch (err) {} loadList(); } },
    [['updated', 'Last edited'], ['created', 'Newest'], ['oldest', 'Oldest'], ['title', 'Title']].map(([v, l]) => h('option', { value: v, selected: view.sort === v }, l)));
  list.textContent = '';
  list.append(h('div#listbar', h('h2', title()), h('span.muted.small', total ? String(total) : ''), view.v !== 'trash' ? sort : null));
  if (view.v === 'trash' && shown.length) list.append(h('div.banner', 'Deleted notes stay here for 30 days. Open one to restore it.'));
  if (!shown.length) {
    list.append(h('div.empty', view.q ? 'No notes match.' : view.v === 'trash' ? 'The trash is empty.' :
      canWrite() ? 'No notes here yet. Click New note, paste a picture, or drop one on the window.' : 'No notes here yet.'));
    return;
  }
  for (const n of shown) list.append(card(n));
  if (shown.length < total) list.append(h('button.pillbtn.more', { onclick: () => loadList(true) }, `Show more (${total - shown.length})`));
}

export function markSelected() {
  for (const c of document.querySelectorAll('.card')) c.classList.toggle('on', c.dataset.id === view.n);
}

/** Replace one note in the list after an edit, without reloading it. */
export function updateCard(n) {
  const i = shown.findIndex((x) => x.id === n.id);
  if (i < 0) return;
  shown[i] = n;
  const old = document.querySelector(`.card[data-id="${n.id}"]`);
  if (old) old.replaceWith(card(n));
}

export async function refresh() {
  await loadMeta();
  renderNav();
  await loadList();
}
