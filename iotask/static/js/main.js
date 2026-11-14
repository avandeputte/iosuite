import { $, S, api, closeDialogs, closeMenu, fail, h, icon, listOf, loadLists, openMenu } from './core.js';
import { SMART, applySidebar, applyTheme, closeNav, drawNav, drawUser, loadSuite, openNav, showSignIn } from './shell.js';
import { showActivity, showImport } from './activity.js';
import { drawTasks } from './lists.js';
import { showSettings } from './settings.js';
import { showTaskPage } from './task.js';

// ------------------------------------------------------------------ routing
export function route() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [path, query] = raw.split('?');
  const p = path.split('/').map(decodeURIComponent);
  const qs = new URLSearchParams(query || '');
  const [a, b] = p;
  if (!a) return { view: S.settings.startView || 'today' };
  if (SMART[a]) return { view: a };
  if (a === 'list' && b) return { view: 'list', id: +b };
  if (a === 'task' && b) return { view: 'task', id: +b };
  if (a === 'new') return { view: 'new', list: +qs.get('list') || null, parent: +qs.get('parent') || null };
  if (a === 'search') return { view: 'search', q: b || '' };
  if (a === 'import') return { view: 'import', list: +qs.get('list') || null };
  if (a === 'activity') return { view: 'activity', list: +qs.get('list') || null };
  if (a === 'settings') return { view: 'settings', tab: b || 'account', sub: p[2] };
  return { view: 'today' };
}
export const TASK_VIEWS = ['today', 'scheduled', 'all', 'done', 'list', 'search'];

export async function onRoute() {
  const r = route();
  const main = $('#main');
  closeMenu();
  try {
    const page = h('div', { class: 'page' });
    main.replaceChildren(page);
    if (TASK_VIEWS.includes(r.view)) await drawTasks(page, r);
    else await ({ task: showTaskPage, new: showTaskPage, import: showImport, activity: showActivity, settings: showSettings })[r.view](page, r);
  } catch (e) { fail(e); }
  drawNav();
}
/** Draw the open view again, keeping where the page was scrolled to. */
export async function redraw() {
  const r = route();
  if (!TASK_VIEWS.includes(r.view)) return;
  const top = $('#main').scrollTop;
  const page = h('div', { class: 'page' });
  try { await drawTasks(page, r); } catch (e) { fail(e); return; }
  $('#main').replaceChildren(page);
  $('#main').scrollTop = top;
}
export async function refresh() { await loadLists(); if (route().view === 'activity') await onRoute(); else await redraw(); }

// ------------------------------------------------------------------ start
export async function start() {
  applyTheme();
  document.querySelectorAll('[data-ic]').forEach((el) => el.replaceWith(icon(el.dataset.ic)));
  S.status = await api('api/status');
  if (!S.status.user) { showSignIn(); return; }
  S.user = S.status.user;
  try { S.settings = (await api('api/auth/me')).settings || {}; } catch { S.settings = {}; }
  if (S.settings.theme) applyTheme(S.settings.theme);
  S.who = new Set(String(S.settings.memberFilter || '').split(',').filter(Boolean).map(Number));
  drawUser();
  await loadLists();
  $('#newbtn').onclick = () => {
    const q = $('#qadd');
    if (q) { q.focus(); return; }
    const r = route();
    location.hash = r.view === 'list' && listOf(r.id).writable ? `#/new?list=${r.id}` : '#/new';
  };
  $('#menubtn').onclick = openNav;
  $('#navscrim').onclick = closeNav;
  $('#nav').addEventListener('click', (e) => { if (e.target.closest('a:not(.who)') && !document.body.classList.contains('side-docked')) closeNav(); });
  addEventListener('resize', applySidebar);
  let t;
  $('#q').addEventListener('input', (e) => {
    clearTimeout(t);
    t = setTimeout(() => {
      const q = e.target.value.trim();
      if (q) location.hash = `#/search/${encodeURIComponent(q)}`;
      else if (route().view === 'search') location.hash = '#/';
    }, 250);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { if (openMenu) closeMenu(); else if (document.querySelector('.dialog-back')) closeDialogs(); else if (document.body.classList.contains('side-open')) closeNav(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) || document.querySelector('.signin, .dialog-back')) return;
    const k = e.key;
    if (k === '/') { e.preventDefault(); $('#q').focus(); }
    else if (k === 'n') { e.preventDefault(); $('#newbtn').click(); }
    else if (k === 't') location.hash = '#/today';
    else if (k === 's') location.hash = '#/scheduled';
    else if (k === 'a') location.hash = '#/all';
  });
  addEventListener('hashchange', onRoute);
  await onRoute();
  loadSuite();
  // come back to the tab: show what changed elsewhere (a phone, another person)
  let away = Date.now();
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { away = Date.now(); return; }
    if (Date.now() - away > 60000 && !document.querySelector('.dialog-back')) refresh().catch(() => {});
  });
}
start().catch(fail);
