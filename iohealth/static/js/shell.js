import { $, TZ, h, route } from './core.js';
import { authApi, dialog, signIn } from './accounts.js';

// ---------- the menu: a sidebar with the pages in groups, Settings at the foot (as in iopix) ----------

export const ICONS = {
  dashboard: 'M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z',
  calendar: 'M19 4h-1V2h-2v2H8V2H6v2H5c-1.11 0-1.99.9-1.99 2L3 20a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V9h14v11z',
  chart: 'M3.5 18.49l6-6.01 4 4L22 6.92l-1.41-1.41-7.09 7.97-4-4L2 16.99z',
  scatter: 'M7 10c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3zm8.01 3c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm-.01-3c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4z',
  run: 'M13.49 5.48c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm-3.6 13.9l1-4.4 2.1 2v6h2v-7.5l-2.1-2 .6-3c1.3 1.5 3.3 2.5 5.5 2.5v-2c-1.9 0-3.5-1-4.3-2.4l-1-1.6c-.4-.6-1-1-1.7-1-.3 0-.5.1-.8.1l-5.2 2.2v4.7h2v-3.4l1.8-.7-1.6 8.1-4.9-1-.4 2 7 1.4z',
  map: 'M20.5 3l-.16.03L15 5.1 9 3 3.36 4.9c-.21.07-.36.25-.36.48V20.5c0 .28.22.5.5.5l.16-.03L9 18.9l6 2.1 5.64-1.9c.21-.07.36-.25.36-.48V3.5c0-.28-.22-.5-.5-.5zM15 19l-6-2.11V5l6 2.11V19z',
  trophy: 'M19 5h-2V3H7v2H5c-1.1 0-2 .9-2 2v1c0 2.55 1.92 4.63 4.39 4.94.63 1.5 1.98 2.63 3.61 2.96V19H7v2h10v-2h-4v-3.1c1.63-.33 2.98-1.46 3.61-2.96C19.08 12.63 21 10.55 21 8V7c0-1.1-.9-2-2-2zM5 8V7h2v3.82C5.84 10.4 5 9.3 5 8zm14 0c0 1.3-.84 2.4-2 2.82V7h2v1z',
  bed: 'M7 13c1.66 0 3-1.34 3-3S8.66 7 7 7s-3 1.34-3 3 1.34 3 3 3zm12-6h-8v7H3V5H1v15h2v-3h18v3h2v-9c0-2.21-1.79-4-4-4z',
  drop: 'M12 2c-5.33 4.55-8 8.48-8 11.8 0 4.98 3.8 8.2 8 8.2s8-3.22 8-8.2c0-3.32-2.67-7.25-8-11.8z',
  gear: 'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z',
  menu: 'M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z',
  menuOpen: 'M3 18h13v-2H3v2zm0-5h10v-2H3v2zm0-7v2h13V6H3zm18 9.59L17.42 12 21 8.41 19.59 7l-5 5 5 5L21 15.59z',
  pin: 'M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3z',
  close: 'M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z',
  more: 'M6 10a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm6 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm6 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4z',
  print: 'M19 8H5c-1.66 0-3 1.34-3 3v6h4v4h12v-4h4v-6c0-1.66-1.34-3-3-3zm-3 11H8v-5h8v5zm3-7c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm-1-9H6v4h12V3z',
};
export function icon(name) {
  const el = h('span', { class: 'ic' });
  el.innerHTML = `<svg viewBox="0 0 24 24"><path d="${ICONS[name] || ''}"/></svg>`;
  return el;
}
for (const el of document.querySelectorAll('.ic[data-ic]')) el.innerHTML = icon(el.dataset.ic).innerHTML;

// The pages, in the sidebar's order: [page, label, icon, hue]. A gap and a heading start each group; Settings and
// sits at the foot. On phones the bottom bar shows the first four and the rest open from More.
export const NAV = [
  ['dashboard', 'Dashboard', 'dashboard', 'purple'], ['day', 'Day', 'calendar', 'amber'], ['metrics', 'Metrics', 'chart', 'blue'], ['workouts', 'Workouts', 'run', 'orange'],
  ['correlations', 'Correlations', 'scatter', 'teal'], ['map', 'Map', 'map', 'cyan'], ['records', 'Records', 'trophy', 'green'],
  ['sleep', 'Sleep', 'bed', 'indigo'], ['glucose', 'Glucose', 'drop', 'rose'],
];
export const NAV_GROUPS = { correlations: 'Analysis', sleep: 'Health' };  // the first page of each group after the first
export const NAV_FOOT = [['settings', 'Settings', 'gear', 'slate']];
export const PHONE_BAR = ['dashboard', 'day', 'metrics', 'workouts'];
export const navLink = ([page, label, ic]) => h('a', { href: page === 'dashboard' ? '#/' : `#/${page}`, 'data-page': page }, icon(ic), h('span', { class: 'nl' }, label));
export const pageTitle = (ic, hue, ...kids) => h('h1', { class: 'ptitle', style: { '--hue': `var(--c-${hue})` } }, h('span', { class: 'pic' }, icon(ic)), ...kids);

export function buildNav() {
  const nav = $('#nav');
  nav.replaceChildren(
    h('div', { class: 'navhead' }, brand('brand'), h('button', { id: 'sidebtn', class: 'iconbtn' })),
    ...NAV.flatMap(n => [NAV_GROUPS[n[0]] ? [h('div', { class: 'navgap' }), h('div', { class: 'navsec' }, NAV_GROUPS[n[0]])] : null, navLink(n)]).flat().filter(Boolean),
    h('button', { class: 'navmore', 'data-page': 'more', title: 'More', onclick: moreSheet }, icon('more'), 'More'),
    h('div', { class: 'navfoot' }, ...NAV_FOOT.map(navLink), h('div', { class: 'ver', id: 'nav-version' })));
  initSidebar();
}

/** The app mark and name, top left (in the sidebar, and in the top bar while the sidebar is put away or on a phone).
 *  Alone, it is the link to the Dashboard. When other ioThing apps are registered in the suite (iosuite-shared's
 *  suite_apps), the mark opens a menu of them, each a link to that app, and the name stays the link to the Dashboard. */
export let suiteApps = [];
export function brand(cls) {
  const mark = () => h('img', { src: 'static/icons/mark.svg', alt: '', width: 24, height: 24, class: 'brand-mark' });
  const name = (tag, attrs) => h(tag, attrs, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Health'));
  if (!suiteApps.length) return h('a', { class: cls, href: '#/', title: 'Dashboard' }, mark(), name('span', { class: 'brand-name' }));
  return h('div', { class: cls },
    h('button', { class: 'suitebtn', title: 'ioThing apps', 'aria-label': 'ioThing apps', 'aria-haspopup': 'menu', onclick: e => toggleSuite(e.currentTarget) }, mark()),
    name('a', { class: 'brand-name', href: '#/', title: 'Dashboard' }));
}
export function drawBrands() {
  $('#nav .navhead > .brand')?.replaceWith(brand('brand'));
  $('#topbar > .topbrand')?.replaceWith(brand('brand topbrand'));
}
export async function loadSuite() {
  try {
    const r = await authApi('api/auth/suite');
    suiteApps = (r.items || []).filter((a) => a.url); suiteSelf = r.app;  // in the suite's one order, this app too
    if (!suiteApps.some((a) => a.app !== r.app)) suiteApps = [];  // only this app: no menu
  } catch { suiteApps = []; }
  if (!suiteApps.length) closeSuite();
  drawBrands();
}
export let suiteSelf = null;  // this app's key, marked in the menu
export let suitePop = null;
export function closeSuite() {
  if (!suitePop) return;
  suitePop.remove(); suitePop = null;
  document.removeEventListener('click', suiteOutside, true);
  document.removeEventListener('keydown', suiteKey, true);
  removeEventListener('resize', closeSuite);
}
export function suiteOutside(e) { if (suitePop && !suitePop.contains(e.target) && !e.target.closest('.suitebtn')) closeSuite(); }
export function suiteKey(e) { if (e.key === 'Escape' && suitePop) { closeSuite(); e.stopPropagation(); } }
export function appTile(a) {
  const letter = (a.name || a.app).replace(/^io(?=[A-Z])/, '').slice(0, 1).toUpperCase();
  const fallback = () => h('span', { class: 'appic fb', style: { background: a.color || 'var(--accent)' } }, letter);
  const ic = a.icon ? h('img', { class: 'appic', src: a.icon, alt: '', onerror: e => e.currentTarget.replaceWith(fallback()) }) : fallback();
  const el = h('a', { class: 'apptile', href: a.url, role: 'menuitem', title: a.description || a.name, onclick: closeSuite },
    ic, h('span', { class: 'appnm' }, a.name || a.app));
  el.classList.toggle('tool', !!a.adminTool);  // admin tools: a smaller icon
  if (a.app === suiteSelf) { el.classList.add('cur'); el.setAttribute('aria-current', 'page'); }
  return el;
}
export function toggleSuite(btn) {
  if (suitePop) { closeSuite(); return; }
  if (!suiteApps.length) return;
  // the apps, then the admin tools (ioDNS…) in a section of their own: the server sends those to their admins only
  const apps = suiteApps.filter((a) => !a.adminTool), tools = suiteApps.filter((a) => a.adminTool);
  suitePop = h('div', { class: 'suitepop', role: 'menu', 'aria-label': 'ioThing apps', style: { '--cols': String(Math.min(3, Math.max(apps.length, tools.length))) } },
    ...apps.map(appTile), ...(tools.length ? [h('div', { class: 'suitesec' }, 'Admin tools'), ...tools.map(appTile)] : []));
  document.body.append(suitePop);
  const r = btn.getBoundingClientRect();
  suitePop.style.top = `${Math.round(r.bottom + 6)}px`;
  suitePop.style.left = `${Math.round(Math.max(8, Math.min(r.left - 6, innerWidth - suitePop.offsetWidth - 8)))}px`;
  setTimeout(() => { document.addEventListener('click', suiteOutside, true); document.addEventListener('keydown', suiteKey, true); addEventListener('resize', closeSuite); }, 0);
}

/** The sidebar docks beside the page on a wide screen, unless its button put it away (remembered). Put away, or on
 *  a narrower screen, it hides off the left edge and the menu button in the top bar slides it over the page; choosing
 *  a page, the dimmed page or Escape puts it away again. Phones keep the bottom bar instead. */
export function initSidebar() {
  const body = document.body, btn = $('#sidebtn'), DOCK_MIN = 1100, KEY = 'iohealth.sidebar';
  const pref = () => { try { return localStorage.getItem(KEY) || '1'; } catch { return '1'; } };
  const canDock = () => innerWidth >= DOCK_MIN;
  const setOpen = on => { body.classList.toggle('side-open', on); $('#navscrim').hidden = !on; };
  const apply = () => {
    const docked = canDock() && pref() === '1';
    body.classList.toggle('side-docked', docked);
    if (docked) setOpen(false);
    const [ic, title] = docked ? ['menuOpen', 'Hide the sidebar'] : canDock() ? ['pin', 'Keep the sidebar open'] : ['close', 'Close the sidebar'];
    btn.replaceChildren(icon(ic)); btn.title = title; btn.setAttribute('aria-label', title);
  };
  btn.onclick = () => {
    try { if (body.classList.contains('side-docked')) localStorage.setItem(KEY, '0'); else if (canDock()) localStorage.setItem(KEY, '1'); else { setOpen(false); return; } } catch { /* private mode */ }
    apply();
  };
  $('#menubtn').onclick = () => setOpen(true);
  $('#navscrim').onclick = () => setOpen(false);
  $('#nav').addEventListener('click', e => { if (e.target.closest('a') && !body.classList.contains('side-docked')) setOpen(false); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && body.classList.contains('side-open')) { setOpen(false); e.stopPropagation(); } }, true);
  addEventListener('resize', apply);
  apply();
}

/** Phones: the bottom bar shows four pages; the rest, with Settings, open from More. */
export function moreSheet() {
  const current = route().page === 'workout' ? 'workouts' : route().page;
  const rest = [...NAV.filter(n => !PHONE_BAR.includes(n[0]) && !$(`#nav a[data-page="${n[0]}"]`)?.hidden), ...NAV_FOOT];
  let close;
  const grid = h('div', { class: 'sheetgrid' }, rest.map(([page, label, ic, hue]) => h('a', { href: `#/${page}`, class: current === page ? 'on' : '', style: { '--hue': `var(--c-${hue})` }, onclick: () => close() },
    h('span', { class: 'sic' }, icon(ic)), label)));
  const d = dialog('More', grid, [{ label: 'Close' }]);
  close = () => document.querySelector('.scrim:last-of-type')?.remove();
  return d;
}

export function setNavOn(page) {
  const inBar = !!$(`#nav a[data-page="${page}"]`);
  for (const a of document.querySelectorAll('#nav a')) a.classList.toggle('on', a.dataset.page === page);
  $('#nav .navmore')?.classList.toggle('on', !inBar || (!PHONE_BAR.includes(page) && innerWidth <= 800));
}

export const settings = (() => {
  const defaults = { units: 'auto', maxHr: '', theme: 'auto', glucoseUnit: '', glucoseLow: '70', glucoseHigh: '180', hiddenSections: [], hiddenTypes: [] };
  try { return Object.assign(defaults, JSON.parse(localStorage.getItem('iohealth.settings') || '{}')); } catch { return defaults; }
})();
// Settings live in the database (hlt_user_settings), shared by every browser; the copy in localStorage only makes the
// theme right before the server answers.
export let settingsTimer;
export function saveSettings() {
  try { localStorage.setItem('iohealth.settings', JSON.stringify(settings)); } catch { /* private mode */ }
  clearTimeout(settingsTimer);
  settingsTimer = setTimeout(() => fetch('api/settings', { method: 'PUT', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings) }).catch(e => console.error('saving settings', e)), 300);
}
export async function loadSettings() {
  try {
    const r = await fetch('api/settings', { credentials: 'same-origin' });
    if (r.status === 401) { signIn(true); return; }
    const stored = await r.json();
    if (Object.keys(stored).length) Object.assign(settings, stored);
    else saveSettings(); // first run: keep what this browser had
  } catch (e) { console.error('loading settings', e); }
}
export function applyTheme() {
  if (settings.theme === 'auto') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme', settings.theme);
}
applyTheme();

export const apiCache = new Map();
export let inflight = 0;
// whenIdle resolves once no API request has been running for a moment (the page has drawn what it loads).
export async function whenIdle(quiet = 400, max = 15000) {
  const end = Date.now() + max;
  let calm = 0;
  while (Date.now() < end && calm < quiet) { await new Promise(r => setTimeout(r, 50)); calm = inflight ? 0 : calm + 50; }
}
export async function api(path, params = {}, { cache = true } = {}) {
  const q = new URLSearchParams({ ...params, tz: TZ });
  if (settings.maxHr) q.set('maxHr', settings.maxHr);
  const url = 'api/' + path + '?' + q;
  if (cache && apiCache.has(url)) {
    const hit = apiCache.get(url);
    if (Date.now() - hit.at < 60000) return hit.promise;
  }
  inflight++;
  const promise = fetch(url, { credentials: 'same-origin' }).then(async r => {
    if (r.status === 401) { signIn(true); throw new Error('not signed in'); }
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.error || body.detail || r.statusText);
    return body;
  }).finally(() => { inflight--; });
  apiCache.set(url, { at: Date.now(), promise });
  promise.catch(() => apiCache.delete(url));
  return promise;
}
