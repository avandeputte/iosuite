import { $, S, api, calOf, fail, h, icon, isAuto, loadCals, parseDay, sameDay, writable, ymd } from './core.js';
import { applySidebar, applyTheme, closeNav, drawNav, drawUser, loadSuite, openNav, showSignIn } from './shell.js';
import { showEdit } from './edit.js';
import { closeDialogs, showEventPage } from './event.js';
import { showImport, showSearch } from './search.js';
import { showSettings } from './settings.js';
import { drawView, moveNowLine, newAt, stepView } from './views.js';

// ------------------------------------------------------------------ routing
export function route() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [path, query] = raw.split('?');
  const p = path.split('/').map(decodeURIComponent);
  const qs = new URLSearchParams(query || '');
  const [a, b] = p;
  if (!a) return { view: S.settings.defaultView || 'month', date: null };
  if (['month', 'week', 'day'].includes(a)) return { view: a, date: b && /^\d{4}-\d{2}-\d{2}$/.test(b) ? parseDay(b) : null };
  if (a === 'agenda') return { view: 'agenda', date: b && /^\d{4}-\d{2}-\d{2}$/.test(b) ? parseDay(b) : null };
  if (a === 'search') return { view: 'search', q: b || '' };
  if (a === 'event' && b) return { view: 'event', id: +b, rid: qs.get('rid') };
  if (a === 'edit' && b) return { view: 'edit', id: +b, rid: qs.get('rid') };
  if (a === 'new') return { view: 'new', date: qs.get('date'), time: qs.get('time'), allDay: qs.get('allday') === '1', copy: qs.get('copy') };
  if (a === 'import') return { view: 'import' };
  if (a === 'settings') return { view: 'settings', tab: b || 'account', sub: p[2] };
  return { view: 'month' };
}
export function go(view, date) { location.hash = `#/${view}/${ymd(date || S.date)}`; }

export async function onRoute() {
  const r = route();
  const main = $('#main');
  try {
    if (['month', 'week', 'day', 'agenda'].includes(r.view)) {
      S.view = r.view;
      if (r.date) S.date = r.date;
      if (r.view !== 'agenda') { try { localStorage.setItem('iocalendar.view', r.view); } catch { /* */ } }
      S.mini = null;
      await drawView();
    } else {
      main.classList.remove('showdetail');
      const page = h('div', { class: 'page' });
      main.replaceChildren(page);
      await ({ search: showSearch, event: showEventPage, edit: showEdit, new: showEdit, import: showImport, settings: showSettings })[r.view](page, r);
    }
  } catch (e) { fail(e); }
  drawNav();
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
  S.hidden = new Set(String(S.settings.hiddenCalendars || '').split(',').filter(Boolean).map(Number));
  S.who = new Set(String(S.settings.memberFilter || '').split(',').filter(Boolean).map(Number));
  drawUser();
  await loadCals();
  $('#newbtn').onclick = () => { const v = route(); newAt(['month', 'week', 'day', 'agenda'].includes(v.view) && !sameDay(S.date, new Date()) ? S.date : new Date()); };
  if (!writable().some((c) => !isAuto(c))) $('#newbtn').hidden = true;
  $('#menubtn').onclick = openNav;
  $('#navscrim').onclick = closeNav;
  $('#nav').addEventListener('click', (e) => { if (e.target.closest('a:not(.cal)') && !document.body.classList.contains('side-docked')) closeNav(); });
  let rt;
  addEventListener('resize', () => { applySidebar(); clearTimeout(rt); rt = setTimeout(() => { if (S.view === 'month' && route().view === 'month') drawView(); }, 250); });
  let t;
  $('#q').addEventListener('input', (e) => {
    clearTimeout(t);
    t = setTimeout(() => {
      const q = e.target.value.trim();
      if (q) location.hash = `#/search/${encodeURIComponent(q)}`;
      else if (route().view === 'search') go(S.view, S.date);
    }, 250);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { if (document.querySelector('.dialog-back')) closeDialogs(); else if (document.body.classList.contains('side-open')) closeNav(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) || document.querySelector('.signin')) return;
    const cal = ['month', 'week', 'day', 'agenda'].includes(route().view);
    const k = e.key;
    if (k === '/') { e.preventDefault(); $('#q').focus(); }
    else if (k === 'n' || k === 'c') { e.preventDefault(); $('#newbtn').click(); }
    else if (k === 'e' && S.open && document.querySelector('.evd') && calOf(S.open.calendarId).writable) { closeDialogs(); location.hash = `#/edit/${S.open.id}${S.open.recurrenceId ? `?rid=${encodeURIComponent(S.open.recurrenceId)}` : ''}`; }
    else if (document.querySelector('.dialog-back')) return;
    else if (k === 't') go(cal ? S.view : (S.settings.defaultView || 'month'), new Date());
    else if (k === 'm') go('month', S.date);
    else if (k === 'w') go('week', S.date);
    else if (k === 'd') go('day', S.date);
    else if (k === 'a') go('agenda', S.date);
    else if (cal && (k === 'ArrowLeft' || k === 'j' || k === 'p')) stepView(-1);
    else if (cal && (k === 'ArrowRight' || k === 'k')) stepView(1);
  });
  addEventListener('hashchange', onRoute);
  await onRoute();
  loadSuite();
  setInterval(moveNowLine, 60000);
  // come back to the tab: show what changed elsewhere (a phone, another person)
  let away = Date.now();
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { away = Date.now(); return; }
    if (Date.now() - away > 60000 && ['month', 'week', 'day', 'agenda'].includes(route().view) && !document.querySelector('.dialog-back')) { loadCals().then(drawView).catch(() => {}); }
  });
}
start().catch(fail);
