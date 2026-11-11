/* ioRecipe web app: one module, no build step. The recipes as cards (all of them, the family's, your own, by tag,
   found by words); one recipe with its photo, ingredients to tick off while cooking and numbered steps; the form to
   add or change one, with a photo to upload; import from a web page; a print view; and settings (account, display,
   and for admins server, and for suite admins security and global settings), laid out as in the other ioThing apps. */

// ------------------------------------------------------------------ helpers
const $ = (s, el = document) => el.querySelector(s);
/** replaceChildren that leaves out null and false (as h() does) and flattens lists. */
const fill = (el, ...kids) => el.replaceChildren(...kids.flat(9).filter((k) => k != null && k !== false));
/** append with the same manners. */
const put = (el, ...kids) => el.append(...kids.flat(9).filter((k) => k != null && k !== false));
const ICONS = {
  list: 'M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z',
  menuOpen: 'M3 18h13v-2H3v2zm0-5h10v-2H3v2zm0-7v2h13V6H3zm18 9.59L17.42 12 21 8.41 19.59 7l-5 5 5 5L21 15.59z',
  pin: 'M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3z',
  menu: 'M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z',
  search: 'M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z',
  add: 'M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z',
  person: 'M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z',
  people: 'M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z',
  link: 'M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z',
  upload: 'M9 16h6v-6h4l-7-7-7 7h4zm-4 2h14v2H5z',
  download: 'M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z',
  settings: 'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z',
  edit: 'M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a.996.996 0 0 0 0-1.41l-2.34-2.34a.996.996 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z',
  delete: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z',
  close: 'M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z',
  logout: 'M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z',
  copy: 'M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z',
  more: 'M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  check: 'M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z',
  update: 'M21 10.12h-6.78l2.74-2.82c-2.73-2.7-7.15-2.8-9.88-.1a6.875 6.875 0 0 0 0 9.79 7.02 7.02 0 0 0 9.88 0C18.32 15.65 19 14.08 19 12.1h2c0 1.98-.88 4.55-2.64 6.29-3.51 3.48-9.21 3.48-12.72 0-3.5-3.47-3.53-9.11-.02-12.58a8.987 8.987 0 0 1 12.65 0L21 3v7.12z',
  tune: 'M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 4v-2H11v2h10zm-6-4h2V7h4V5h-4V3h-2v6z',
  ai: 'M19 9l1.25-2.75L23 5l-2.75-1.25L19 1l-1.25 2.75L15 5l2.75 1.25L19 9zm-7.5.5L9 4 6.5 9.5 1 12l5.5 2.5L9 20l2.5-5.5L17 12l-5.5-2.5zM19 15l-1.25 2.75L15 19l2.75 1.25L19 23l1.25-2.75L23 19l-2.75-1.25L19 15z',
  theme: 'M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.389 5.389 0 0 1-4.4 2.26 5.403 5.403 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z',
  print: 'M19 8H5c-1.66 0-3 1.34-3 3v6h4v4h12v-4h4v-6c0-1.66-1.34-3-3-3zm-3 11H8v-5h8v5zm3-7c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm-1-9H6v4h12V3z',
  book: 'M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z',
  home: 'M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z',
  lock: 'M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z',
  tag: 'M21.41 11.58l-9-9C12.05 2.22 11.55 2 11 2H4c-1.1 0-2 .9-2 2v7c0 .55.22 1.05.59 1.42l9 9c.36.36.86.58 1.41.58.55 0 1.05-.22 1.41-.59l7-7c.37-.36.59-.86.59-1.41 0-.55-.23-1.06-.59-1.42zM5.5 7C4.67 7 4 6.33 4 5.5S4.67 4 5.5 4 7 4.67 7 5.5 6.33 7 5.5 7z',
  timer: 'M15 1H9v2h6V1zm-4 13h2V8h-2v6zm8.03-6.61 1.42-1.42c-.43-.51-.9-.99-1.41-1.41l-1.42 1.42A8.962 8.962 0 0 0 12 4c-4.97 0-9 4.03-9 9s4.02 9 9 9a8.994 8.994 0 0 0 7.03-14.61zM12 20c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z',
  dish: 'M8.1 13.34l2.83-2.83L3.91 3.5a4.008 4.008 0 0 0 0 5.66l4.19 4.18zm6.78-1.81c1.53.71 3.68.21 5.27-1.38 1.91-1.91 2.28-4.65.81-6.12-1.46-1.46-4.2-1.1-6.12.81-1.59 1.59-2.09 3.74-1.38 5.27L3.7 19.87l1.41 1.41L12 14.41l6.88 6.88 1.41-1.41L13.41 13l1.47-1.47z',
  photo: 'M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z',
  globe: 'M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zm6.93 6h-2.95a15.65 15.65 0 0 0-1.38-3.56A8.03 8.03 0 0 1 18.92 8zM12 4.04c.83 1.2 1.48 2.53 1.91 3.96h-3.82c.43-1.43 1.08-2.76 1.91-3.96zM4.26 14C4.1 13.36 4 12.69 4 12s.1-1.36.26-2h3.38c-.08.66-.14 1.32-.14 2s.06 1.34.14 2H4.26zm.82 2h2.95c.32 1.25.78 2.45 1.38 3.56A7.987 7.987 0 0 1 5.08 16zm2.95-8H5.08a7.987 7.987 0 0 1 4.33-3.56A15.65 15.65 0 0 0 8.03 8zM12 19.96c-.83-1.2-1.48-2.53-1.91-3.96h3.82c-.43 1.43-1.08 2.76-1.91 3.96zM14.34 14H9.66c-.09-.66-.16-1.32-.16-2s.07-1.35.16-2h4.68c.09.65.16 1.32.16 2s-.07 1.34-.16 2zm.25 5.56c.6-1.11 1.06-2.31 1.38-3.56h2.95a8.03 8.03 0 0 1-4.33 3.56zM16.36 14c.08-.66.14-1.32.14-2s-.06-1.34-.14-2h3.38c.16.64.26 1.31.26 2s-.1 1.36-.26 2h-3.38z',
};
const icon = (n, cls = '') => { const s = document.createElement('span'); s.className = 'ic ' + cls; s.innerHTML = `<svg viewBox="0 0 24 24"><path d="${ICONS[n] || ''}"/></svg>`; return s; };

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'style' && typeof v === 'object') for (const [sk, sv] of Object.entries(v)) { if (sk.startsWith('--')) el.style.setProperty(sk, sv); else el.style[sk] = sv; }
    else if (k === 'value') el.value = v;
    else if (k === 'checked') el.checked = !!v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  const add = (k) => { if (k == null || k === false) return; if (Array.isArray(k)) k.forEach(add); else el.append(k instanceof Node ? k : String(k)); };
  kids.forEach(add);
  return el;
}

async function api(path, opts = {}) {
  const o = { credentials: 'same-origin', ...opts, headers: { ...(opts.headers || {}) } };
  if (o.json !== undefined) { o.body = JSON.stringify(o.json); o.headers['Content-Type'] = 'application/json'; delete o.json; }
  const r = await fetch(path, o);
  if (r.status === 401 && !path.startsWith('/api/auth') && path !== '/api/status') { showSignIn(); throw new Error('Sign in first'); }
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch { /* not JSON */ }
    throw new Error(msg || `Error ${r.status}`);
  }
  const ct = r.headers.get('content-type') || '';
  return ct.includes('json') ? r.json() : r.text();
}

let toastTimer;
/** A note at the foot of the page. */
function toast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 3500);
}
const fail = (e) => toast(e.message || String(e));

function dialog(title, body, buttons, cls = '') {
  return new Promise((resolve) => {
    const back = h('div', { class: 'dialog-back' });
    const close = (v) => { back.remove(); resolve(v); };
    back.addEventListener('click', (e) => { if (e.target === back) close(null); });
    const btns = (buttons || [{ label: 'OK', value: true, primary: true }]).map((b) =>
      h('button', { class: `pillbtn noic ${b.primary ? 'primary' : ''} ${b.danger ? 'danger' : ''}`, onclick: () => close(typeof b.value === 'function' ? b.value() : b.value) }, b.label));
    back.append(h('div', { class: `dialog ${cls}`, role: 'dialog' }, h('h2', null, title), body, h('div', { class: 'btns' }, btns)));
    document.body.append(back);
    const f = back.querySelector('input,select,textarea'); if (f) f.focus();
  });
}
const confirmDialog = (title, text, ok = 'OK', danger = false) => dialog(title, h('p', null, text), [{ label: 'Cancel', value: false }, { label: ok, value: true, primary: !danger, danger }]);
function closeDialogs() { document.querySelectorAll('.dialog-back').forEach((d) => d.remove()); }

/** A menu that drops from a button: items are [icon, label, what it does (a function, or an address)]; a second click
    on the button, a click elsewhere, Escape or scrolling puts it away. */
let openMenu = null;
function closeMenu() {
  if (!openMenu) return;
  openMenu.el.remove(); document.removeEventListener('click', openMenu.outside); openMenu = null;
}
function popMenu(btn, items) {
  const mine = openMenu && openMenu.btn === btn;
  closeMenu();
  if (mine) return;
  const el = h('div', { class: 'menu pop', role: 'menu' }, items.filter(Boolean).map(([ic, label, act]) => (typeof act === 'string'
    ? h('a', { class: 'mi', role: 'menuitem', href: act, onclick: closeMenu }, icon(ic, 's'), label)
    : h('button', { class: 'mi', role: 'menuitem', onclick: () => { closeMenu(); act(); } }, icon(ic, 's'), label))));
  document.body.append(el);
  const r = btn.getBoundingClientRect();
  el.style.left = `${Math.round(Math.max(8, Math.min(r.right - el.offsetWidth, innerWidth - el.offsetWidth - 8)))}px`;
  el.style.top = `${Math.round(r.bottom + 4 + el.offsetHeight > innerHeight - 8 ? Math.max(8, r.top - el.offsetHeight - 4) : r.bottom + 4)}px`;
  const outside = (e) => { if (!el.contains(e.target) && !btn.contains(e.target)) closeMenu(); };
  openMenu = { el, btn, outside };
  setTimeout(() => document.addEventListener('click', outside), 0);
  $('#main').addEventListener('scroll', closeMenu, { once: true });
}

const hue = (s) => { let x = 0; for (const c of s || '') x = (x * 31 + c.charCodeAt(0)) % 360; return x; };
const initials = (fn) => { const p = (fn || '?').trim().split(/\s+/); return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase(); };
const safeUrl = (u) => /^(https?:\/\/|mailto:)/i.test(u || '');  // a link that is a link (never javascript:)
const store = { get: (k) => { try { return localStorage.getItem(`iorecipe.${k}`); } catch { return null; } }, set: (k, v) => { try { localStorage.setItem(`iorecipe.${k}`, v); } catch { /* private mode */ } } };

// ------------------------------------------------------------------ state
const S = { status: {}, user: null, suite: [], settings: {}, counts: {}, tags: [] };
// the suite's roles, each able to do what the one before can: a viewer only looks, a member keeps recipes of their
// own, an editor changes the family's too
const RANK = { none: 0, viewer: 1, member: 2, editor: 3, admin: 4 };
const roleAtLeast = (r) => (RANK[S.user && S.user.role] || 0) >= RANK[r];
const canOwn = () => roleAtLeast('member');
const canFamily = () => roleAtLeast('editor');
const canAdd = () => canOwn() || canFamily();
async function saveSettings(changes) {
  Object.assign(S.settings, changes);
  try { await api('/api/auth/settings', { method: 'POST', json: changes }); } catch { /* kept for this visit */ }
}
/** Minutes as people say them: 45 min, 1 h, 1 h 35 min. */
function fmtMin(n) {
  if (!n) return '';
  const hh = Math.floor(n / 60), mm = n % 60;
  return [hh ? `${hh} h` : '', mm ? `${mm} min` : ''].filter(Boolean).join(' ');
}

// ------------------------------------------------------------------ chrome
function drawUser() {
  const m = $('#usermenu'); m.replaceChildren();
  if (!S.user) return;
  const btn = h('button', { class: 'avatarbtn', title: S.user.displayName, style: { background: `hsl(${hue(S.user.name)} 45% 45%)` } }, initials(S.user.displayName));
  let menu = null;
  const closeMenu = () => { if (menu) { menu.remove(); menu = null; document.removeEventListener('click', outside); } };
  const outside = (e) => { if (menu && !menu.contains(e.target) && e.target !== btn) closeMenu(); };
  btn.onclick = () => {
    if (menu) return closeMenu();
    menu = h('div', { class: 'menu' },
      h('div', { class: 'who' }, h('b', null, S.user.displayName), h('div', { class: 'muted small' }, `${S.user.name} · ${S.user.role}`)),
      h('a', { class: 'mi', href: '#/settings', onclick: closeMenu }, icon('settings', 's'), 'Settings'),
      h('button', { class: 'mi', onclick: async () => { const r = await api('/api/auth/logout', { method: 'POST' }); if (r && r.cloudflareLogout) location.href = r.cloudflareLogout; else location.reload(); } }, icon('logout', 's'), 'Sign out'));
    m.append(menu);
    setTimeout(() => document.addEventListener('click', outside), 0);
  };
  m.append(btn);
}
/* The suite (iosuite-shared's suite_apps): when other ioThing apps are registered, the app mark top left (in the sidebar; in
   the top bar on a phone) opens a menu of them, each a link to that app. Alone, the mark stays the link to all the recipes. */
async function loadSuite() {
  try {
    const r = await api('/api/auth/suite');
    S.suite = (r.items || []).filter((a) => a.url); suiteSelf = r.app;  // in the suite's one order, this app too
    if (!S.suite.some((a) => a.app !== r.app)) S.suite = [];  // only this app: no menu
  } catch { S.suite = []; }
  const b = $('#suitebtn');
  if (b) { b.hidden = !S.suite.length; b.onclick = () => toggleSuite(b); }
  if (!S.suite.length) closeSuite();
  drawNav();
}
let suiteSelf = null;  // this app's key, marked in the menu
let suitePop = null;
function closeSuite() {
  if (!suitePop) return;
  suitePop.remove(); suitePop = null;
  document.removeEventListener('click', suiteOutside, true);
  document.removeEventListener('keydown', suiteKey);
  removeEventListener('resize', closeSuite);
}
function suiteOutside(e) { if (suitePop && !suitePop.contains(e.target) && !e.target.closest('.suitebtn')) closeSuite(); }
function suiteKey(e) { if (e.key === 'Escape') closeSuite(); }
function appTile(a) {
  const mark = (a.name || a.app).replace(/^io(?=[A-Z])/, '').slice(0, 1).toUpperCase();
  const fallback = () => h('span', { class: 'appic fb', style: { background: a.color || 'var(--brand)' } }, mark);
  const ic = a.icon ? h('img', { class: 'appic', src: a.icon, alt: '', onerror: (e) => e.currentTarget.replaceWith(fallback()) }) : fallback();
  const el = h('a', { class: 'apptile', href: a.url, role: 'menuitem', title: a.description || a.name, onclick: closeSuite },
    ic, h('span', { class: 'appnm' }, a.name || a.app));
  el.classList.toggle('tool', !!a.adminTool);  // admin tools: a smaller icon
  if (a.app === suiteSelf) { el.classList.add('cur'); el.setAttribute('aria-current', 'page'); }
  return el;
}
function toggleSuite(btn) {
  if (suitePop) { closeSuite(); return; }
  if (!S.suite.length) return;
  // the apps, then the admin tools in a section of their own: the server sends those to their admins only
  const apps = S.suite.filter((a) => !a.adminTool), tools = S.suite.filter((a) => a.adminTool);
  suitePop = h('div', { class: 'suitepop', role: 'menu', 'aria-label': 'ioThing apps', style: { '--cols': String(Math.min(3, Math.max(apps.length, tools.length))) } },
    ...apps.map(appTile), ...(tools.length ? [h('div', { class: 'suitesec' }, 'Admin tools'), ...tools.map(appTile)] : []));
  document.body.append(suitePop);
  const r = btn.getBoundingClientRect();
  suitePop.style.top = `${Math.round(r.bottom + 6)}px`;
  suitePop.style.left = `${Math.round(Math.max(8, Math.min(r.left - 6, innerWidth - suitePop.offsetWidth - 8)))}px`;
  setTimeout(() => { document.addEventListener('click', suiteOutside, true); document.addEventListener('keydown', suiteKey); addEventListener('resize', closeSuite); }, 0);
}
/** The theme: the account's (Settings › Display), remembered in this browser too so the sign-in page has it. */
function applyTheme(choice) {
  if (choice) store.set('theme', choice);
  const t = choice || store.get('theme') || 'system';
  if (t === 'system') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
}


/* The sidebar, as in the other io apps: the name on top, the recipes (all, the family's, your own), the tags, import,
   Settings at the foot. It docks beside the page on a wide screen unless its button put it away (remembered);
   otherwise it slides over the page. Phones get a bottom bar instead. */
const DOCK_MIN = 1100;
const VIEWS = { all: ['All recipes', 'book', '--c-green'], family: ['Family', 'home', '--c-orange'], mine: ['Mine', 'lock', '--c-blue'] };
function drawNav() {
  const nav = $('#nav'); const r = route();
  const link = (v, href, ic, label, n, on, hueVar) => h('a', { href, 'data-v': v, class: on ? 'on' : null, style: hueVar ? { '--hue': `var(${hueVar})` } : null },
    icon(ic), h('span', { class: 'nl' }, label), n ? h('span', { class: 'n' }, n) : null);
  const sec = (label) => h('div', { class: 'navsec' }, h('span', null, label));
  const brandName = () => [h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Recipe')];
  const shown = Object.entries(VIEWS).filter(([k]) => k !== 'mine' || canOwn() || S.counts.mine);
  nav.replaceChildren(...[
    h('div', { class: 'navhead' },
      S.suite.length
        ? h('div', { class: 'brand' },
          h('button', { class: 'suitebtn', title: 'ioThing apps', 'aria-label': 'ioThing apps', 'aria-haspopup': 'menu', onclick: (e) => toggleSuite(e.currentTarget) },
            h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' })),
          h('a', { class: 'brand-name', href: '#/', title: 'All recipes' }, brandName()))
        : h('a', { class: 'brand', href: '#/', title: 'All recipes' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }),
          h('span', { class: 'brand-name' }, brandName())),
      h('button', { id: 'sidebtn', class: 'iconbtn', onclick: sidebarButton })),
    shown.map(([k, [label, ic, hv]]) => link(k, `#/${k}`, ic, label, S.counts[k] || null, r.view === k, hv)),
    h('button', { class: 'navmore', 'data-v': 'more', title: 'More', onclick: moreSheet }, icon('more'), h('span', { class: 'nl' }, 'More')),
    S.tags.length ? [h('div', { class: 'navgap' }), sec('Tags'),
      S.tags.slice(0, 14).map((t) => link('tag', `#/tag/${encodeURIComponent(t.tag)}`, 'tag', t.tag, t.count, r.view === 'tag' && r.tag.toLowerCase() === t.tag.toLowerCase(), '--c-slate'))] : null,
    canAdd() ? [h('div', { class: 'navgap' }), sec('Add'),
      link('new', '#/new', 'add', 'New recipe', null, r.view === 'new', '--c-green'),
      link('import', '#/import', 'globe', 'Import from the web', null, r.view === 'import', '--c-teal')] : null,
    h('div', { class: 'navfoot' }, link('settings', '#/settings', 'settings', 'Settings', null, r.view === 'settings')),
  ].flat(3).filter(Boolean));
  applySidebar();
  $('.navmore')?.classList.toggle('on', ['tag', 'import', 'new', 'settings', 'search'].includes(r.view));
}
function applySidebar() {
  const body = document.body, btn = $('#sidebtn');
  const docked = innerWidth >= DOCK_MIN && store.get('sidebar') !== '0';
  body.classList.toggle('side-docked', docked);
  if (docked) closeNav();
  if (!btn) return;
  const [ic, title] = docked ? ['menuOpen', 'Hide the sidebar'] : innerWidth >= DOCK_MIN ? ['pin', 'Keep the sidebar open'] : ['close', 'Close the sidebar'];
  btn.replaceChildren(icon(ic)); btn.title = title; btn.setAttribute('aria-label', title);
}
function sidebarButton() {
  if (document.body.classList.contains('side-docked')) store.set('sidebar', '0');
  else if (innerWidth >= DOCK_MIN) store.set('sidebar', '1');
  else { closeNav(); return; }
  applySidebar();
}
function openNav() { document.body.classList.add('side-open'); $('#navscrim').hidden = false; }
function closeNav() { document.body.classList.remove('side-open'); $('#navscrim').hidden = true; }

/** Phones: what the bottom bar has no room for (the tags, adding, settings). */
function moreSheet() {
  const r = route();
  const tile = (href, ic, label, hueV, on) => h('a', { href, class: on ? 'on' : null, style: { '--hue': hueV } }, h('span', { class: 'sic' }, icon(ic)), h('span', null, label));
  const grid = h('div', { class: 'sheetgrid' },
    canAdd() ? [tile('#/new', 'add', 'New recipe', 'var(--c-green)', r.view === 'new'), tile('#/import', 'globe', 'Import', 'var(--c-teal)', r.view === 'import')] : null,
    tile('#/settings', 'settings', 'Settings', 'var(--c-slate)', r.view === 'settings'),
    S.tags.slice(0, 18).map((t) => tile(`#/tag/${encodeURIComponent(t.tag)}`, 'tag', t.tag, 'var(--c-slate)', r.view === 'tag' && r.tag === t.tag)));
  const p = dialog('More', grid, [{ label: 'Close', value: null }]);
  grid.addEventListener('click', (e) => { if (e.target.closest('a')) closeDialogs(); });
  return p;
}

// ------------------------------------------------------------------ routing
function route() {
  const raw = location.hash.replace(/^#\/?/, '');
  const p = raw.split('?')[0].split('/').map((x) => { try { return decodeURIComponent(x); } catch { return x; } });
  const [a, b, c] = p;
  if (!a) return { view: VIEWS[S.settings.startView] ? S.settings.startView : 'all' };
  if (VIEWS[a]) return { view: a };
  if (a === 'tag' && b) return { view: 'tag', tag: b };
  if (a === 'search') return { view: 'search', q: b || '' };
  if (a === 'recipe' && b) return { view: c === 'edit' ? 'edit' : 'recipe', id: +b };
  if (a === 'new') return { view: 'new' };
  if (a === 'import') return { view: 'import' };
  if (a === 'settings') return { view: 'settings', tab: b || 'account', sub: c };
  return { view: 'all' };
}
const GRID_VIEWS = ['all', 'family', 'mine', 'tag', 'search'];

async function onRoute() {
  const r = route();
  const main = $('#main');
  closeMenu();
  try {
    const page = h('div', { class: 'page' });
    if (GRID_VIEWS.includes(r.view)) await drawRecipes(page, r);
    else await ({ recipe: showRecipe, edit: showForm, new: showForm, import: showImport, settings: showSettings })[r.view](page, r);
    main.replaceChildren(page);
    main.scrollTop = 0;
  } catch (e) { main.replaceChildren(h('div', { class: 'page' }, h('div', { class: 'empty' }, icon('dish'), h('p', null, e.message || String(e)), h('p', null, h('a', { class: 'lnk', href: '#/' }, 'All recipes'))))); }
  drawNav();
}

// ------------------------------------------------------------------ the recipes, as cards
async function fetchRecipes(r) {
  const q = new URLSearchParams();
  if (r.view === 'family' || r.view === 'mine') q.set('scope', r.view);
  if (r.view === 'tag') q.set('tag', r.tag);
  if (r.view === 'search') q.set('q', r.q);
  const d = await api(`/api/recipes?${q}`);
  S.counts = d.counts; S.tags = d.tags;
  return d.items;
}
function card(x) {
  const meta = [fmtMin(x.totalMinutes), x.servings ? (/^\d+$/.test(x.servings) ? `Serves ${x.servings}` : x.servings) : ''].filter(Boolean).join(' · ');
  return h('a', { class: 'rcard', href: `#/recipe/${x.id}` },
    x.photo ? h('img', { class: 'rpic', src: `${x.photo}&size=small`, alt: '', loading: 'lazy' })
      : h('span', { class: 'rpic none', style: { '--h': hue(x.title) } }, icon('dish')),
    h('span', { class: 'rbody' },
      h('span', { class: 'rtitle' }, x.title),
      h('span', { class: 'rmeta' }, x.family ? null : h('span', { class: 'priv', title: 'Private: only you see it' }, icon('lock', 'xs')), meta || (x.tags || []).slice(0, 3).join(' · ') || ' ')));
}
async function drawRecipes(page, r) {
  const items = await fetchRecipes(r);
  const title = r.view === 'tag' ? `#${r.tag}` : r.view === 'search' ? `“${r.q}”` : VIEWS[r.view][0];
  page.classList.add('wide');
  put(page, h('div', { class: 'pagehead' }, h('h1', null, title), h('span', { class: 'count' }, items.length || '')));
  if (!items.length) {
    const first = r.view !== 'search' && r.view !== 'tag';
    put(page, h('div', { class: 'empty' }, icon('dish'),
      h('p', null, r.view === 'search' ? 'No recipe has those words.' : r.view === 'tag' ? 'No recipe has that tag.' : r.view === 'mine' ? 'No private recipes yet.' : 'No recipes yet.'),
      first && canAdd() ? h('p', { class: 'emptybtns' }, h('a', { class: 'pillbtn primary', href: '#/new' }, icon('add', 's'), 'New recipe'),
        h('a', { class: 'pillbtn', href: '#/import' }, icon('globe', 's'), 'Import from the web')) : null));
    return;
  }
  put(page, h('div', { class: 'rgrid' }, items.map(card)));
}

// ------------------------------------------------------------------ one recipe
const isHeading = (line) => /:$/.test(line) && line.length < 80;
/** The lines of ingredients or steps as groups: [{heading, lines}], a heading being a line that ends with a colon. */
function groups(lines) {
  const out = [{ heading: null, lines: [] }];
  for (const l of lines || []) { if (isHeading(l)) out.push({ heading: l.replace(/:$/, ''), lines: [] }); else out[out.length - 1].lines.push(l); }
  return out.filter((g) => g.heading || g.lines.length);
}
async function showRecipe(page, r) {
  const x = await api(`/api/recipes/${r.id}`);
  document.title = `${x.title} · ioRecipe`;
  const more = h('button', { class: 'iconbtn', title: 'More', onclick: (e) => popMenu(e.currentTarget, [
    ['print', 'Print', () => print()],
    x.writable ? ['delete', 'Delete', () => removeRecipe(x)] : null]) }, icon('more'));
  const times = [['Prep', x.prepMinutes], ['Cook', x.cookMinutes], ['Total', x.totalMinutes]].filter(([, v]) => v);
  const facts = h('div', { class: 'facts' },
    times.map(([k, v]) => h('span', { class: 'fact' }, icon('timer', 's'), h('span', null, h('small', null, k), fmtMin(v)))),
    x.servings ? h('span', { class: 'fact' }, icon('people', 's'), h('span', null, h('small', null, 'Makes'), x.servings)) : null,
    h('span', { class: 'fact' }, icon(x.family ? 'home' : 'lock', 's'), h('span', null, h('small', null, 'Kept with'), x.family ? 'Family recipes' : 'My private recipes')));
  const ing = groups(x.ingredients).map((g) => [g.heading ? h('h3', null, g.heading) : null,
    h('ul', { class: 'ings' }, g.lines.map((l) => h('li', null, h('label', { class: 'check' }, h('input', { type: 'checkbox' }), h('span', null, l)))))]);
  let n = 0;
  const steps = groups(x.steps).map((g) => [g.heading ? h('h3', null, g.heading) : null,
    h('ol', { class: 'steps' }, g.lines.map((l) => { n += 1; return h('li', { onclick: (e) => e.currentTarget.classList.toggle('done') }, h('span', { class: 'num' }, n), h('span', null, l)); }))]);
  const host = x.sourceUrl ? (() => { try { return new URL(x.sourceUrl).hostname.replace(/^www\./, ''); } catch { return ''; } })() : '';
  page.classList.add('recipe');
  put(page, 
    h('div', { class: 'pagehead' }, h('h1', null, x.title), h('span', { class: 'grow' }),
      x.writable ? h('a', { class: 'pillbtn', href: `#/recipe/${x.id}/edit` }, icon('edit', 's'), 'Edit') : null, more),
    x.photo ? h('img', { class: 'hero', src: x.photo, alt: '' }) : null,
    x.description ? h('p', { class: 'desc notes' }, x.description) : null,
    facts,
    x.tags.length ? h('div', { class: 'chiprow tags' }, x.tags.map((t) => h('a', { class: 'chip', href: `#/tag/${encodeURIComponent(t)}` }, `#${t}`))) : null,
    h('div', { class: 'cols' },
      h('section', { class: 'ingcol' }, h('h2', null, 'Ingredients'), ing.length ? ing : h('p', { class: 'muted' }, 'None listed.')),
      h('section', { class: 'stepcol' }, h('h2', null, 'Steps'), steps.length ? steps : h('p', { class: 'muted' }, 'None listed.'),
        x.notes ? [h('h2', null, 'Notes'), h('p', { class: 'notes' }, x.notes)] : null)),
    x.sourceUrl || x.sourceName ? h('p', { class: 'muted source' }, 'From ',
      safeUrl(x.sourceUrl) ? h('a', { class: 'lnk', href: x.sourceUrl, target: '_blank', rel: 'noopener noreferrer' }, x.sourceName || host) : x.sourceName,
      x.sourceName && host && x.sourceName.toLowerCase() !== host ? ` (${host})` : '') : null);
}
async function removeRecipe(x) {
  if (!await confirmDialog('Delete this recipe?', `“${x.title}” and its photo go for good.`, 'Delete', true)) return;
  try { await api(`/api/recipes/${x.id}`, { method: 'DELETE' }); toast('Deleted'); location.hash = '#/'; } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ one recipe: the form
async function showForm(page, r) {
  const x = r.view === 'edit' ? await api(`/api/recipes/${r.id}`) : { ingredients: [], steps: [], tags: [], family: canFamily() };
  if (r.view === 'edit' && !x.writable) { location.hash = `#/recipe/${x.id}`; return; }
  if (r.view === 'new' && !canAdd()) throw new Error('A viewer only looks at the family’s recipes.');
  const back = x.id ? `#/recipe/${x.id}` : '#/';
  const inp = (v, attrs = {}) => h('input', { class: 't', value: v == null ? '' : v, ...attrs });
  const area = (v, attrs = {}) => h('textarea', { class: 't', ...attrs }, v || '');
  const title = inp(x.title, { class: 't big', placeholder: 'Title', maxlength: 255 });
  const desc = area(x.description, { rows: 2, placeholder: 'A line or two about it' });
  const servings = inp(x.servings, { placeholder: '4, or 24 cookies', maxlength: 64 });
  const mins = (v) => inp(v, { type: 'number', min: 0, inputmode: 'numeric', placeholder: 'minutes' });
  const prep = mins(x.prepMinutes), cook = mins(x.cookMinutes);
  const total = mins(x.prepMinutes || x.cookMinutes ? ((x.prepMinutes || 0) + (x.cookMinutes || 0) === x.totalMinutes ? null : x.totalMinutes) : x.totalMinutes);
  total.placeholder = 'prep + cook';
  const where = h('select', { class: 't' }, h('option', { value: '1', selected: x.family ? true : null }, 'Family recipes'),
    h('option', { value: '0', selected: x.family ? null : true }, 'My private recipes'));
  const tags = inp((x.tags || []).join(', '), { placeholder: 'dessert, cookies, quick', list: 'taglist' });
  const ings = area((x.ingredients || []).join('\n'), { rows: 10, placeholder: '200 g flour\n100 g butter\nFor the icing:\n150 g icing sugar' });
  const steps = area((x.steps || []).join('\n\n'), { rows: 12, placeholder: 'Heat the oven to 180 °C.\n\nMix the flour and the butter.' });
  const notes = area(x.notes, { rows: 3, placeholder: 'Tips, what to change next time' });
  const url = inp(x.sourceUrl, { type: 'url', placeholder: 'https://…' });
  const from = inp(x.sourceName, { placeholder: 'Grandma, a book, a website', maxlength: 255 });

  // the photo: what the recipe has, or the file just picked; taken away with the button
  let file = null, drop = false;
  const pick = h('input', { type: 'file', accept: 'image/*', hidden: true });
  const view = h('div', { class: 'photopick' });
  const drawPhoto = () => {
    const src = file ? URL.createObjectURL(file) : (!drop && x.photo) || null;
    fill(view,
      src ? h('img', { src, alt: '' }) : h('button', { type: 'button', class: 'none', onclick: () => pick.click() }, icon('photo'), h('span', null, 'Add a photo')),
      src ? h('div', { class: 'photobtns' }, h('button', { type: 'button', class: 'pillbtn', onclick: () => pick.click() }, icon('upload', 's'), 'Another photo'),
        h('button', { type: 'button', class: 'pillbtn danger', onclick: () => { file = null; drop = true; pick.value = ''; drawPhoto(); } }, icon('delete', 's'), 'Remove')) : null);
  };
  pick.onchange = () => { if (pick.files[0]) { file = pick.files[0]; drop = false; drawPhoto(); } };
  drawPhoto();

  const save = async (e) => {
    e.preventDefault();
    const body = { title: title.value, description: desc.value, servings: servings.value, prepMinutes: prep.value, cookMinutes: cook.value,
      totalMinutes: total.value, tags: tags.value, ingredients: ings.value, steps: steps.value, notes: notes.value, sourceUrl: url.value, sourceName: from.value };
    if (canFamily()) body.family = where.value === '1';
    const btn = $('.formbar .primary', page); btn.disabled = true;
    try {
      let got = await api(x.id ? `/api/recipes/${x.id}` : '/api/recipes', { method: x.id ? 'PATCH' : 'POST', json: body });
      try {
        if (file) got = await api(`/api/recipes/${got.id}/photo`, { method: 'PUT', body: file, headers: { 'Content-Type': file.type || 'application/octet-stream' } });
        else if (drop && x.photo) await api(`/api/recipes/${got.id}/photo`, { method: 'DELETE' });
      } catch (err) { toast(`Saved, but not the photo: ${err.message}`); location.hash = `#/recipe/${got.id}`; return; }
      toast('Saved');
      location.hash = `#/recipe/${got.id}`;
    } catch (err) { btn.disabled = false; fail(err); }
  };
  page.classList.add('form');
  put(page, h('form', { onsubmit: save },
    h('div', { class: 'pagehead' }, h('h1', null, x.id ? 'Edit recipe' : 'New recipe')),
    title, view, pick,
    h('div', { class: 'fsec' }, icon('dish'), 'About'),
    desc,
    h('div', { class: 'grid', style: { marginTop: '10px' } }, fld('Makes', servings), fld('Preparation', prep), fld('Cooking', cook), fld('Total, when it is more', total)),
    h('div', { class: 'grid', style: { marginTop: '10px' } }, fld('Tags, with commas between', tags), canFamily() ? fld('Kept with', where) : null),
    canFamily() ? h('p', { class: 'muted small hint', style: { marginTop: '6px' } }, 'Everyone sees the family’s recipes; a private one only you.') : null,
    h('datalist', { id: 'taglist' }, S.tags.map((t) => h('option', { value: t.tag }))),
    h('div', { class: 'fsec' }, icon('list'), 'Ingredients'),
    h('p', { class: 'muted small hint' }, 'One on each line. A line that ends with a colon (“For the icing:”) is a heading.'),
    ings,
    h('div', { class: 'fsec' }, icon('book'), 'Steps'),
    h('p', { class: 'muted small hint' }, 'One step on each line; empty lines between them are fine. A line that ends with a colon is a heading.'),
    steps,
    h('div', { class: 'fsec' }, icon('edit'), 'Notes'),
    notes,
    h('div', { class: 'fsec' }, icon('link'), 'Where it comes from'),
    h('div', { class: 'grid' }, fld('Source', from), fld('Link', url)),
    h('div', { class: 'formbar' }, h('button', { class: 'pillbtn primary noic', type: 'submit' }, 'Save'), h('a', { class: 'pillbtn noic', href: back }, 'Cancel'),
      h('span', { class: 'grow' }), x.id ? h('button', { type: 'button', class: 'pillbtn danger noic', onclick: () => removeRecipe(x) }, 'Delete') : null)));
  if (!x.id) setTimeout(() => title.focus(), 0);
}

// ------------------------------------------------------------------ import from the web
async function showImport(page) {
  if (!canAdd()) throw new Error('A viewer only looks at the family’s recipes.');
  const url = h('input', { class: 't', type: 'url', placeholder: 'https://www.example.com/recipes/oat-cookies', autocapitalize: 'none', spellcheck: 'false' });
  const where = h('select', { class: 't' }, h('option', { value: '1' }, 'Family recipes'), h('option', { value: '0' }, 'My private recipes'));
  const btn = h('button', { class: 'pillbtn primary', type: 'submit' }, icon('download', 's'), 'Import');
  const note = h('p', { class: 'err' });
  const go = async (e) => {
    e.preventDefault();
    if (!url.value.trim()) { url.focus(); return; }
    note.className = 'muted'; note.textContent = 'Fetching the page and reading the recipe…'; btn.disabled = true;
    try {
      const body = { url: url.value.trim() };
      if (canFamily()) body.family = where.value === '1';
      const got = await api('/api/import', { method: 'POST', json: body });
      toast(`Imported “${got.title}”. Have a look, and edit what needs it.`);
      location.hash = `#/recipe/${got.id}`;
    } catch (err) { note.className = 'err'; note.textContent = err.message.replace(/^Bad request: /, ''); btn.disabled = false; }
  };
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Import from the web')),
    h('form', { class: 'box importbox', onsubmit: go },
      h('h2', null, icon('globe'), 'A recipe’s web address'),
      h('p', { class: 'muted' }, 'Paste the address of a recipe page. ioRecipe fetches the page and keeps the recipe it describes (title, ingredients, steps, times, tags) with its picture and a link back to where it came from.'),
      h('div', { class: 'pform' }, url, canFamily() ? fld('Kept with', where) : null, h('div', null, btn), note),
      h('p', { class: 'muted small' }, 'This works on the many sites that describe their recipes for search engines (schema.org Recipe). Where a page does not, add the recipe by hand.')));
  setTimeout(() => url.focus(), 0);
}

// ------------------------------------------------------------------ settings
async function showSettings(page, r) {
  const adm = S.user.role === 'admin';
  const tabs = [['account', 'Account'], ['display', 'Display'],
    ...(adm ? [['server', 'Server']] : []),
    ...(S.user.suiteAdmin ? [['security', SUITE_TABS.security], ['global', SUITE_TABS.global]] : [])];
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Settings')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/settings/${k}`; } }, l))));
  const body = h('div'); page.append(body);
  await ({ account: setAccount, display: setDisplay, server: setServer, security: setSuite, global: setSuite }[r.tab] || setAccount)(body, r);
}
const fld = (l, e) => h('label', { class: 'field' }, h('span', null, l), e);

const accountUi = () => import(new URL('api/auth/ui.js', document.baseURI).href);
/** Settings › Account: display name, email and password, then the app passwords: iosuite-shared's panels (the same in every io app). */
async function setAccount(el) {
  const ui = await accountUi();
  const pw = h('div');
  await ui.mountAccount(el, { toast, onSaved: (u) => { Object.assign(S.user, u); drawUser(); } });
  el.append(pw);
  await ui.mountAppPasswords(pw, { toast });
}

/** Settings › Display: the theme (saved with the account) and what the app opens on. */
async function setDisplay(el) {
  const ui = await accountUi();
  const sv = h('select', { class: 't', onchange: async (e) => { await saveSettings({ startView: e.target.value }); toast('Saved'); } },
    Object.entries(VIEWS).filter(([k]) => k !== 'mine' || canOwn()).map(([v, [l]]) => h('option', { value: v, selected: v === (S.settings.startView || 'all') ? true : null }, l)));
  el.append(ui.box('theme', 'Appearance', ui.themeRow(S.settings.theme || store.get('theme') || 'system', (t) => { S.settings.theme = t; applyTheme(t); })),
    h('div', { class: 'box' }, h('h2', null, icon('tune'), 'Recipes'), h('div', { class: 'grid' }, fld('Open on', sv))));
}

/** Settings › Security and Global settings (suite admins): the people, their role in every app, app
    passwords, sign-in at the proxy; the apps, keys and tokens. The same panel in every io app, served by iosuite-shared. */
const SUITE_TABS = { security: 'Security', global: 'Global settings' };
async function setSuite(el, r) {
  let ui;
  try { ui = await import(new URL('api/suite-admin/ui.js', document.baseURI).href); } catch (e) { el.append(h('p', { class: 'warn' }, `The panel did not load: ${e.message}`)); return; }
  await ui.mount(el, { tab: r.tab, sub: r.sub, toast, onSub: (x) => history.replaceState(null, '', `#/settings/${r.tab}/${x}`) });
}

/** Settings › Server (admins): the MCP switch, the version and its updates, the server log and Restart
    (iosuite-shared's panel, the same in every io app). */
async function setServer(el) {
  let ui;
  try { ui = await serverUi(); } catch (e) { el.append(h('p', { class: 'warn' }, `The Server panel did not load: ${e.message}`)); return; }
  await ui.mount(el, { toast });
}
const serverUi = () => import(new URL('api/server/ui.js', document.baseURI).href);

/** Admins: a note when the daily check found a newer version, with Update now. Hidden until the next version when dismissed. */
function updateBanner() {
  $('#updbanner')?.remove();
  const u = S.status && S.status.update;
  if (!u || store.get('updateDismissed') === u.remote) return;
  const b = h('div', { id: 'updbanner', role: 'status' }, icon('update'),
    h('span', null, `ioRecipe ${u.version ? `v${u.version}` : 'update'} is available${u.message ? `: ${u.message.replace(/^v\d+\.\d+\.\d+:\s*/, '')}` : ''}`),
    h('button', { class: 'pillbtn primary noic', onclick: async () => { if (await confirmDialog('Update ioRecipe', 'Install the new version and restart? The page reloads when it is back.', 'Update now')) { b.remove(); (await serverUi()).runUpdate({ toast }); } } }, 'Update now'),
    h('a', { class: 'pillbtn noic', href: '#/settings/server', onclick: () => b.remove() }, 'Details'),
    h('button', { class: 'iconbtn', title: 'Not now (hidden until the next version)', onclick: () => { store.set('updateDismissed', u.remote); b.remove(); } }, icon('close', 's')));
  document.body.append(b);
}

// ------------------------------------------------------------------ sign-in
function showSignIn() {
  // as in the other io apps: a tile per account; one click for a passwordless account, a password for the others
  if (document.querySelector('.signin')) return;
  const first = !S.status.usersExist;
  const name = h('input', { class: 't', placeholder: 'User name', autocomplete: 'username', autocapitalize: 'none' });
  const pw = h('input', { class: 't', type: 'password', placeholder: first ? 'Password (8 or more)' : 'Password', autocomplete: first ? 'new-password' : 'current-password' });
  const err = h('div', { class: 'err' });
  const form = h('div', { class: 'signin-form' }, name, pw);
  const tiles = h('div', { class: 'accounts' });
  const btn = h('button', { class: 'pillbtn primary noic', type: 'submit' }, first ? 'Create the admin account' : 'Sign in');
  const login = async (n, p) => {
    err.textContent = '';
    try { await api(first ? '/api/auth/setup' : '/api/auth/login', { method: 'POST', json: { name: n, password: p } }); location.reload(); } catch (x) { err.textContent = x.message; }
  };
  const submit = (e) => { e.preventDefault(); login(name.value.trim(), pw.value); };
  document.body.append(h('div', { class: 'signin' }, h('form', { class: 'dialog', onsubmit: submit },
    h('div', { class: 'brand' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }), h('span', { class: 'brand-name', style: { display: 'inline' } }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Recipe'))),
    first ? h('p', { class: 'muted' }, 'Welcome. Make the first account: it is the admin, who adds the rest of the family in Settings. (Already use another io app? Sign in there first, or use the same name and password here once the apps share their accounts.)') : h('h2', null, 'Sign in'),
    tiles, form, err, h('div', { class: 'btns' }, btn))));
  if (first) { name.focus(); return; }
  const pick = (t) => tiles.querySelectorAll('.account').forEach((x) => x.classList.toggle('on', x === t));
  api('/api/auth/accounts').then((d) => {
    if (!d.accounts.length) { name.focus(); return; }
    form.hidden = true; btn.hidden = true;
    tiles.append(...d.accounts.map((a) => {
      const t = h('button', { type: 'button', class: 'account', title: a.passwordless ? `Sign in as ${a.name}` : `${a.name} (password)`, onclick: () => {
        pick(t);
        if (a.passwordless) { login(a.name, ''); return; }
        name.value = a.name; name.hidden = true; form.hidden = false; btn.hidden = false; pw.value = ''; pw.focus();
      } }, h('span', { class: 'av big', style: { '--h': hue(a.displayName || a.name) } }, initials(a.displayName || a.name)), h('span', { class: 'nm' }, a.displayName || a.name), a.passwordless ? null : h('span', { class: 'muted small' }, 'password'));
      return t;
    }), h('button', { type: 'button', class: 'account', title: 'Type a user name', onclick: (e) => {
      pick(e.currentTarget); name.value = ''; name.hidden = false; form.hidden = false; btn.hidden = false; name.focus();
    } }, h('span', { class: 'av big other' }, '…'), h('span', { class: 'nm' }, 'Other')));
  }).catch(() => name.focus());
}

// ------------------------------------------------------------------ start
async function start() {
  applyTheme();
  document.querySelectorAll('[data-ic]').forEach((el) => el.replaceWith(icon(el.dataset.ic)));
  S.status = await api('/api/status');
  if (!S.status.user) { showSignIn(); return; }
  S.user = S.status.user;
  try { S.settings = (await api('/api/auth/me')).settings || {}; } catch { S.settings = {}; }
  if (S.settings.theme) applyTheme(S.settings.theme);
  drawUser();
  const nb = $('#newbtn');
  nb.hidden = !canAdd();
  nb.onclick = () => popMenu(nb, [['edit', 'Write a recipe', '#/new'], ['globe', 'Import from the web', '#/import']]);
  $('#menubtn').onclick = openNav;
  $('#navscrim').onclick = closeNav;
  $('#nav').addEventListener('click', (e) => { if (e.target.closest('a') && !document.body.classList.contains('side-docked')) closeNav(); });
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
    if (e.key === '/') { e.preventDefault(); $('#q').focus(); }
    else if (e.key === 'n' && canAdd()) location.hash = '#/new';
  });
  addEventListener('hashchange', () => { document.title = 'ioRecipe'; onRoute(); });
  try { const d = await api('/api/summary'); S.counts = d.counts; S.tags = d.tags; } catch { /* the page says so */ }
  await onRoute();
  loadSuite();
  updateBanner();
  setInterval(async () => { try { S.status = await api('/api/status'); updateBanner(); } catch { /* restarting */ } }, 15 * 60 * 1000);
}
start().catch(fail);
