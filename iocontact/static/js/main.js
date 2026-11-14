import { $, S, api, fail, h, icon, loadList, loadMeta } from './core.js';
import { applySidebar, applyTheme, closeNav, drawNav, drawUser, loadSuite, openNav, showSignIn } from './shell.js';
import { showCleanup, showImport, showIopix } from './cleanup.js';
import { showContact } from './contact.js';
import { showEdit } from './edit.js';
import { drawList } from './list.js';
import { showSettings } from './settings.js';
import { showTree } from './tree.js';
import { showUpcoming } from './upcoming.js';

// ------------------------------------------------------------------ routing
export function route() {
  const p = location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
  const [a, b, c] = p;
  if (!a) return { view: 'list' };
  if (a === 'c' && b) return c === 'edit' ? { view: 'edit', id: +b } : { view: 'contact', id: +b };
  if (a === 'new') return { view: 'new' };
  if (a === 'fav') return { view: 'list', scope: { kind: 'fav' } };
  if (a === 'book') return { view: 'list', scope: { kind: 'book', id: +b } };
  if (a === 'tag') return { view: 'list', scope: { kind: 'tag', name: b } };
  if (a === 'tree' && b) return { view: 'tree', id: +b };
  if (a === 'cleanup') return { view: 'cleanup', tab: b || 'dups' };
  if (['upcoming', 'import', 'iopix'].includes(a)) return { view: a };
  if (a === 'settings') return { view: 'settings', tab: b || 'account', sub: p[2] };
  return { view: 'list' };
}

export async function onRoute() {
  const r = route();
  const main = $('#main');
  try {
    if (r.view === 'list' || r.view === 'contact' || r.view === 'edit' || r.view === 'new') {
      if (r.scope && JSON.stringify(r.scope) !== JSON.stringify(S.scope)) { S.scope = r.scope; S.sel.clear(); S.selecting = false; }
      if (r.view === 'list' && !r.scope && S.scope.kind !== 'all') { S.scope = { kind: 'all' }; S.sel.clear(); }
      if (!main.querySelector('.listpane')) main.replaceChildren(h('div', { class: 'listpane' }), h('div', { class: 'detailpane' }));
      await loadList();
      drawList();
      main.classList.toggle('showdetail', r.view !== 'list');
      const pane = main.querySelector('.detailpane');
      if (r.view === 'contact') await showContact(r.id, pane);
      else if (r.view === 'edit') await showEdit(r.id, pane);
      else if (r.view === 'new') await showEdit(null, pane);
      else pane.replaceChildren(emptyDetail());
    } else {
      main.classList.remove('showdetail');
      const page = h('div', { class: 'page' });
      main.replaceChildren(page);
      await ({ upcoming: showUpcoming, cleanup: showCleanup, import: showImport, iopix: showIopix, settings: showSettings, tree: showTree })[r.view](page, r);
    }
  } catch (e) { fail(e); }
  drawNav();
}

export function emptyDetail() {
  return h('div', { class: 'empty' }, icon('book'), h('p', null, S.total ? 'Pick a contact on the left.' : 'No contacts here yet.'),
    h('p', null, h('a', { class: 'lnk', href: '#/new' }, 'New contact'), ' · ', h('a', { class: 'lnk', href: '#/import' }, 'Import from a file')));
}

// ------------------------------------------------------------------ start
export async function start() {
  applyTheme();
  document.querySelectorAll('[data-ic]').forEach((el) => el.replaceWith(icon(el.dataset.ic)));
  S.status = await api('api/status');
  if (!S.status.user) { showSignIn(); return; }
  S.user = S.status.user;
  try { S.settings = (await api('api/auth/me')).settings || {}; } catch { S.settings = {}; }
  if (S.settings.theme) applyTheme(S.settings.theme);
  drawUser();
  await loadMeta();
  $('#newbtn').onclick = () => { location.hash = '#/new'; };
  $('#menubtn').onclick = openNav;
  $('#navscrim').onclick = closeNav;
  $('#nav').addEventListener('click', (e) => { if (e.target.closest('a') && !document.body.classList.contains('side-docked')) closeNav(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && document.body.classList.contains('side-open')) closeNav(); });
  addEventListener('resize', applySidebar);
  let t;
  $('#q').addEventListener('input', (e) => {
    clearTimeout(t);
    t = setTimeout(async () => {
      S.q = e.target.value.trim();
      const r = route();
      if (!['list', 'contact', 'edit', 'new'].includes(r.view)) { location.hash = '#/'; return; }
      await loadList(); drawList();
    }, 180);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) { e.preventDefault(); $('#q').focus(); }
  });
  window.addEventListener('hashchange', onRoute);
  onRoute();
  loadSuite();
}
start().catch(fail);
