/** Start-up and routing: #/notes (the list and the open note), #/note/<id>, #/settings[/tab], #/maintenance[/tab], #/changes. Pasting or
 *  dropping a picture makes a note of it; N makes a new note; / goes to the search box. */
import { $, h, api, state, icon, paintIcons, toast, fail, canWrite, confirmIt, debounce } from './core.js';
import { runUpdate } from './update.js';
import { loadMe, renderUserMenu, signIn } from './auth.js';
import { loadSuite } from './suite.js';
import { view, viewFromHash, go, loadMeta, renderNav, loadList, setOpenHandler, refresh, markSelected, setStatus } from './notes.js';
import { openNote, flush, uploadPicture, currentNote } from './editor.js';
import { renderSettings, renderMaintenance, renderChanges } from './settings.js';

let lastList = '';

/** The "a newer version is out" card, for admins, when the daily check found one (as iopix shows it): Update now runs
 *  update.sh from here and the page reloads with the new version; dismissed per version in this browser. */
const DISMISSED = 'ionotes.updateDismissed';
function updateBanner(u) {
  let b = $('#updbanner');
  let gone = ''; try { gone = localStorage.getItem(DISMISSED) || ''; } catch (e) { /* private mode */ }
  if (!u || gone === u.remote) { if (b) b.remove(); return; }
  if (b && b.dataset.remote === u.remote) return;
  if (b) b.remove();
  const text = h('div', h('b', u.version ? `Version ${u.version} is available` : 'A newer build is available'),
    h('div.muted', `You have v${state.version || '?'}. ${(u.message || '').replace(/^v\d+\.\d+\.\d+:\s*/, '').slice(0, 140)}`));
  const more = h('a.pillbtn', { href: '#/maintenance/updates', onclick: () => b.remove() }, 'Details');
  const run = u.canRun ? h('button.pillbtn.primary', { onclick: async () => {
    if (!await confirmIt('Update ioNotes', `Fetch ${u.version ? 'version ' + u.version : 'the latest version'}, refresh the packages and restart ioNotes? The page reloads when the new version is up.`, 'Update')) return;
    runUpdate((msg, failed) => {
      run.hidden = more.hidden = true;
      text.textContent = '';
      text.append(h('b', failed ? 'The update did not finish' : 'Updating…'), h('div.muted', msg));
    });
  } }, 'Update now') : null;
  b = h('div#updbanner', { 'data-remote': u.remote }, h('span.icwrap', icon('spark')), text, run, more,
    h('button.iconbtn', { title: 'Not now (hidden until the next version)', onclick: () => { try { localStorage.setItem(DISMISSED, u.remote); } catch (e) {} b.remove(); } }, icon('close')));
  document.body.append(b);
}

/** The sidebar docks beside the page on a wide screen, unless its button put it away (remembered in this browser).
 *  Put away, or on a narrower screen, it hides off the left edge and the menu button in the top bar slides it over the
 *  page; choosing a destination, the dimmed page or Escape puts it away again. Phones keep the bottom bar instead.
 *  The same as iopix. */
const DOCK_MIN = 1100, SIDEBAR = 'ionotes.sidebar';
function initSidebar() {
  const body = document.body, btn = $('#sidebtn');
  const canDock = () => innerWidth >= DOCK_MIN;
  const pref = () => { try { return localStorage.getItem(SIDEBAR) || '1'; } catch (e) { return '1'; } };
  const setPref = (v) => { try { localStorage.setItem(SIDEBAR, v); } catch (e) { /* private mode */ } };
  const setOpen = (on) => { body.classList.toggle('side-open', on); $('#navscrim').hidden = !on; };
  const apply = () => {
    const docked = canDock() && pref() === '1';
    body.classList.toggle('side-docked', docked);
    if (docked) setOpen(false);
    const [ic, title] = docked ? ['menuOpen', 'Hide the sidebar'] : canDock() ? ['pin', 'Keep the sidebar open'] : ['close', 'Close the sidebar'];
    btn.replaceChildren(icon(ic)); btn.title = title; btn.setAttribute('aria-label', title);
  };
  btn.onclick = () => {
    if (body.classList.contains('side-docked')) setPref('0');
    else if (canDock()) setPref('1');
    else { setOpen(false); return; }
    apply();
  };
  $('#menubtn').onclick = () => setOpen(true);
  $('#navscrim').onclick = () => setOpen(false);
  $('#nav').addEventListener('click', (e) => { if (e.target.closest('a') && !body.classList.contains('side-docked')) setOpen(false); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && body.classList.contains('side-open')) { setOpen(false); e.stopPropagation(); } }, true);
  addEventListener('resize', apply);
  apply();
}

function notesLayout() {
  const main = $('#main');
  if (!$('#list')) { main.textContent = ''; main.append(h('section#list', { 'aria-label': 'Notes' }), h('section#note', { 'aria-label': 'Note' })); lastList = ''; }
}

async function route() {
  const path = location.hash.replace(/^#/, '').split('?')[0] || '/notes';
  const [, page, tab] = path.split('/');
  document.body.classList.remove('reading');
  if (page === 'settings') { await flush(); renderNav(); return renderSettings(tab); }
  if (page === 'maintenance') { await flush(); renderNav(); return renderMaintenance(tab); }
  if (page === 'changes') { await flush(); renderNav(); return renderChanges(); }
  viewFromHash();
  $('#q').value = view.q;
  notesLayout();
  renderNav();
  const key = JSON.stringify([view.v, view.f, view.t, view.q]);
  if (key !== lastList) { lastList = key; await loadList(); }
  markSelected();
  document.body.classList.toggle('reading', !!view.n);
  if (!currentNote() || currentNote().id !== view.n) await openNote(view.n);
}

setOpenHandler((id) => go({ n: id }));

async function newNote(extra = {}) {
  if (!canWrite()) { if (!state.me.user) signIn(); else toast('Your account can only read notes'); return null; }
  try {
    const body = { title: '', body: '', ...extra };
    if (view.v === 'folder') body.folderID = view.f;
    if (view.v === 'tag') body.tags = [view.t];
    if (view.v === 'pinned') body.pinned = true;
    const n = await api('/api/notes', { method: 'POST', body });
    await refresh();
    go({ n: n.id, v: view.v === 'trash' || view.v === 'images' ? 'all' : view.v, q: '' });
    return n;
  } catch (e) { fail(e); return null; }
}

async function pictureNote(file) {
  const n = await newNote({ title: file.name && !/^image\.\w+$/.test(file.name) ? file.name.replace(/\.\w+$/, '') : '' });
  if (n) await uploadPicture(n.id, file);
}

function wire() {
  $('#newbtn').addEventListener('click', () => newNote());
  const search = debounce(() => go({ q: $('#q').value.trim(), n: null }), 300);
  $('#q').addEventListener('input', search);
  $('#q').addEventListener('keydown', (e) => { if (e.key === 'Escape') { $('#q').value = ''; search.flush(); } });
  window.addEventListener('hashchange', () => route().catch(fail));
  document.addEventListener('keydown', (e) => {
    const typing = e.target.closest('input, textarea, select, [contenteditable]');
    if (typing) return;
    if (e.key === '/') { e.preventDefault(); $('#q').focus(); }
    else if (e.key === 'n' && !e.metaKey && !e.ctrlKey) { e.preventDefault(); newNote(); }
    else if ((e.metaKey || e.ctrlKey) && e.key === 'c' && !String(window.getSelection())) {
      const n = currentNote(); if (n) { navigator.clipboard.writeText([n.title, n.body].filter(Boolean).join('\n\n') || n.ocrText).then(() => toast('Copied')); }
    }
  });
  // a picture pasted anywhere (but into a text field) becomes a note
  document.addEventListener('paste', (e) => {
    if (e.target.closest('input, textarea')) return;
    const f = [...(e.clipboardData ? e.clipboardData.files : [])].find((x) => x.type.startsWith('image/'));
    if (f) { e.preventDefault(); pictureNote(f); return; }
    const text = e.clipboardData && e.clipboardData.getData('text/plain');
    if (text && text.trim()) { e.preventDefault(); newNote({ body: text }); }
  });
  let depth = 0;
  const hasFiles = (e) => e.dataTransfer && [...e.dataTransfer.types].includes('Files');
  document.addEventListener('dragenter', (e) => { if (hasFiles(e) && canWrite()) { depth++; $('#drop').hidden = false; } });
  document.addEventListener('dragleave', (e) => { if (hasFiles(e)) { depth = Math.max(0, depth - 1); if (!depth) $('#drop').hidden = true; } });
  document.addEventListener('dragover', (e) => { if (hasFiles(e)) e.preventDefault(); });
  document.addEventListener('drop', async (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault(); depth = 0; $('#drop').hidden = true;
    for (const f of [...e.dataTransfer.files].filter((x) => x.type.startsWith('image/'))) await pictureNote(f);
  });
  // other devices' changes show up: the list reloads when the server's rev moves on
  let rev = null;
  setInterval(async () => {
    if (document.hidden) return;
    try {
      const s = await api('/api/status');
      setStatus(`ionotes ${s.version || ''}`.trim());
      updateBanner(s.update);
      if (!$('#list')) return;
      if (rev !== null && s.rev !== undefined && s.rev !== rev && !document.activeElement.closest('.editor')) { lastList = ''; await loadMeta(); renderNav(); await loadList(); markSelected(); }
      rev = s.rev;
    } catch (e) { setStatus('Cannot reach the server'); }
  }, 15000);
}

async function start() {
  paintIcons();
  initSidebar();
  state.onSignedOut = () => { if (state.me && state.me.user) location.reload(); };
  try { state.settings = await api('/api/settings'); } catch (e) { state.settings = {}; }
  await loadMe();
  renderUserMenu();
  // notes are private to each account: once accounts exist, nothing shows until someone signs in
  if (!state.me.user && (state.me.requireLogin || state.me.usersExist)) { document.body.classList.add('locked'); signIn(true); return; }
  if (state.me.user && state.me.settings && state.me.settings.theme) {
    try { if (!localStorage.getItem('ionotes.theme')) { localStorage.setItem('ionotes.theme', state.me.settings.theme); location.reload(); return; } } catch (e) {}
  }
  if (state.settings.app_name && state.settings.app_name !== 'ionotes') document.title = state.settings.app_name;
  await loadMeta();
  loadSuite();
  wire();
  api('/api/status').then((s) => { state.version = s.version; setStatus(`ioNotes ${s.version}`); updateBanner(s.update); }).catch(() => {});
  if (!location.hash) history.replaceState(null, '', '#/notes');
  await route();
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
}

start().catch((e) => { $('#main').textContent = ''; $('#main').append(h('div.noteempty', h('div', 'ionotes could not start: ' + e.message))); });
