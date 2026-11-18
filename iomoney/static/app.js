/* ioMoney web app: one module, no build step. The overview (net worth, its history, the accounts by kind); one
   account with its history, transactions, holdings or values; transactions to search and correct; spending by
   category and month; the portfolio with its quotes; the house and the cars with their loans; and settings (account,
   display, and for admins Money and Server, and for suite admins security and global settings), laid out as in the
   other ioThing apps. */
import { client, h } from '../api/auth/ui.js';  // the suite's shared helpers (iosuite-shared static/account-panel.js)
const api = client(document.baseURI, { signIn: () => showSignIn() });
// ------------------------------------------------------------------ helpers
const $ = (s, el = document) => el.querySelector(s);
/** replaceChildren that leaves out null and false (as h() does) and flattens lists. */
const fill = (el, ...kids) => el.replaceChildren(...kids.flat(9).filter((k) => k != null && k !== false));
/** append with the same manners. */
const put = (el, ...kids) => el.append(...kids.flat(9).filter((k) => k != null && k !== false));
const ICONS = {
  dashboard: 'M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z',
  receipt: 'M18 17H6v-2h12v2zm0-4H6v-2h12v2zm0-4H6V7h12v2zM3 22l1.5-1.5L6 22l1.5-1.5L9 22l1.5-1.5L12 22l1.5-1.5L15 22l1.5-1.5L18 22l1.5-1.5L21 22V2l-1.5 1.5L18 2l-1.5 1.5L15 2l-1.5 1.5L12 2l-1.5 1.5L9 2 7.5 3.5 6 2 4.5 3.5 3 2v20z',
  pie: 'M11 2v20c-5.07-.5-9-4.79-9-10s3.93-9.5 9-10zm2.03 0v8.99H22c-.47-4.74-4.24-8.52-8.97-8.99zm0 11.01V22c4.74-.47 8.5-4.25 8.97-8.99h-8.97z',
  trend: 'M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6z',
  car: 'M18.92 6.01C18.72 5.42 18.16 5 17.5 5h-11c-.66 0-1.21.42-1.42 1.01L3 12v8c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h12v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-8l-2.08-5.99zM6.5 16c-.83 0-1.5-.67-1.5-1.5S5.67 13 6.5 13s1.5.67 1.5 1.5S7.33 16 6.5 16zm11 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zM5 11l1.5-4.5h11L19 11H5z',
  bank: 'M4 10v7h3v-7H4zm6 0v7h3v-7h-3zM2 22h19v-3H2v3zm14-12v7h3v-7h-3zm-4.5-9L2 6v2h19V6l-9.5-5z',
  card: 'M20 4H4c-1.11 0-1.99.89-1.99 2L2 18c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V6c0-1.11-.89-2-2-2zm0 14H4v-6h16v6zm0-10H4V6h16v2z',
  attach: 'M16.5 6v11.5c0 2.21-1.79 4-4 4s-4-1.79-4-4V5a2.5 2.5 0 0 1 5 0v10.5c0 .55-.45 1-1 1s-1-.45-1-1V6H10v9.5a2.5 2.5 0 0 0 5 0V5c0-2.21-1.79-4-4-4S7 2.79 7 5v12.5c0 3.04 2.46 5.5 5.5 5.5s5.5-2.46 5.5-5.5V6h-1.5z',
  split: 'M14 4l2.29 2.29-2.88 2.88 1.42 1.42 2.88-2.88L20 10V4h-6zm-4 0H4v6l2.29-2.29 4.71 4.7V20h2v-8.41l-5.29-5.3L10 4z',
  loan: 'M19 14V6c0-1.1-.9-2-2-2H3c-1.1 0-2 .9-2 2v8c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zm-9-1c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm13-6v11c0 1.1-.9 2-2 2H4v-2h17V7h2z',
  gem: 'M12 2 2 9l10 13L22 9 12 2zm0 3.2L18.6 9H5.4L12 5.2z',
  sync: 'M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46A7.93 7.93 0 0 0 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74A7.93 7.93 0 0 0 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z',
  warning: 'M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z',
  list: 'M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z',
  menuOpen: 'M3 18h13v-2H3v2zm0-5h10v-2H3v2zm0-7v2h13V6H3zm18 9.59L17.42 12 21 8.41 19.59 7l-5 5 5 5L21 15.59z',
  pin: 'M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3z',
  menu: 'M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z',
  search: 'M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z',
  add: 'M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z',
  link: 'M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z',
  upload: 'M9 16h6v-6h4l-7-7-7 7h4zm-4 2h14v2H5z',
  download: 'M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z',
  settings: 'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z',
  edit: 'M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a.996.996 0 0 0 0-1.41l-2.34-2.34a.996.996 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z',
  delete: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z',
  close: 'M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z',
  logout: 'M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z',
  more: 'M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  check: 'M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z',
  tune: 'M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 4v-2H11v2h10zm-6-4h2V7h4V5h-4V3h-2v6z',
  theme: 'M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.389 5.389 0 0 1-4.4 2.26 5.403 5.403 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z',
  home: 'M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z',
  lock: 'M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z',
  prev: 'M15.41 7.41 14 6l-6 6 6 6 1.41-1.41L10.83 12z',
  next: 'M10 6 8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z',
  minus: 'M19 13H5v-2h14v2z',
  play: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z',
  repeat: 'M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z',
  eye: 'M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z',
  copy: 'M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z',
  tidy: 'M20 3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM10 17H5v-2h5v2zm0-4H5v-2h5v2zm0-4H5V7h5v2zm4.82 6L12 12.16l1.41-1.41 1.41 1.42L17.99 9l1.42 1.42L14.82 15z',
  label: 'M17.63 5.84C17.27 5.33 16.67 5 16 5L5 5.01C3.9 5.01 3 5.9 3 7v10c0 1.1.9 1.99 2 1.99L16 19c.67 0 1.27-.33 1.63-.84L22 12l-4.37-6.16z',
  history: 'M13 3a9 9 0 0 0-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42A8.954 8.954 0 0 0 13 21a9 9 0 0 0 0-18zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z',
  undo: 'M12.5 8c-2.65 0-5.05.99-6.9 2.6L2 7v9h9l-3.62-3.62c1.39-1.16 3.16-1.88 5.12-1.88 3.54 0 6.55 2.31 7.6 5.5l2.37-.78C21.08 11.03 17.15 8 12.5 8z',
  store: 'M20 4H4v2h16V4zm1 10v-2l-1-5H4l-1 5v2h1v6h10v-6h4v6h2v-6h1zm-9 4H6v-4h6v4z',
  bookmark: 'M17 3H7c-1.1 0-1.99.9-1.99 2L5 21l7-3 7 3V5c0-1.1-.9-2-2-2z',
  scale: 'M13 7.83c.85-.3 1.53-.98 1.83-1.83H18l-3 7c0 1.66 1.57 3 3.5 3s3.5-1.34 3.5-3l-3-7h2V4h-6.17c-.41-1.17-1.52-2-2.83-2s-2.42.83-2.83 2H3v2h2l-3 7c0 1.66 1.57 3 3.5 3S9 14.66 9 13L6 6h3.17c.3.85.98 1.53 1.83 1.83V19H2v2h20v-2h-9V7.83zM20.37 13h-3.74l1.87-4.36L20.37 13zm-13 0H3.63L5.5 8.64 7.37 13zM12 6c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1z',
  doneAll: 'M18 7l-1.41-1.41-6.34 6.34 1.41 1.41L18 7zm4.24-1.41L11.66 16.17 7.48 12l-1.41 1.41L11.66 19l12-12-1.42-1.41zM.41 13.41L6 19l1.41-1.41L1.83 12 .41 13.41z',
  phone: 'M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z',
};
const icon = (n, cls = '') => { const s = document.createElement('span'); s.className = 'ic ' + cls; s.innerHTML = `<svg viewBox="0 0 24 24"><path d="${ICONS[n] || ''}"/></svg>`; return s; };

let toastTimer;
/** A note at the foot of the page; act: [label, what it does], a way back shown beside it for a while (Undo). */
function toast(msg, act) {
  const t = $('#toast');
  t.replaceChildren(msg, ...(act ? [h('button', { class: 'undo', onclick: () => { t.hidden = true; act[1](); } }, act[0])] : []));
  t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, act ? 9000 : 3500);
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

const store = { get: (k) => { try { return localStorage.getItem(`iomoney.${k}`); } catch { return null; } }, set: (k, v) => { try { localStorage.setItem(`iomoney.${k}`, v); } catch { /* private mode */ } } };

// ------------------------------------------------------------------ state
const S = { status: {}, user: null, suite: [], settings: {}, sum: null, accounts: [], cats: [], searches: [], tags: null };
const RANK = { none: 0, viewer: 1, member: 2, editor: 3, admin: 4 };
const roleAtLeast = (r) => (RANK[S.user && S.user.role] || 0) >= RANK[r];
const may = (k) => !!(S.sum && S.sum.may && S.sum.may[k]);
const canAdd = () => may('own') || may('household');
const CUR = () => (S.sum && S.sum.currency) || 'USD';
async function refreshSummary() {
  try { S.sum = await api('api/summary'); } catch { /* the page says so */ }
  try { S.accounts = (await api('api/accounts?hidden=true')).items || []; } catch { S.accounts = []; }
  try { S.searches = may('read') ? (await api('api/searches')).items || [] : []; } catch { S.searches = []; }
  drawNav();
}
async function saveSettings(changes) {
  Object.assign(S.settings, changes);
  try { await api('api/auth/settings', { method: 'POST', json: changes }); } catch { /* kept for this visit */ }
}

// ------------------------------------------------------------------ numbers and dates
const fmts = {};
/** An amount in a currency, as the browser's language writes it: $1,234.50, -€12.00. */
function money(v, cur = CUR(), opts = {}) {
  if (v == null || Number.isNaN(+v)) return '—';
  const key = `${cur}:${opts.whole ? 1 : 0}:${opts.sign ? 1 : 0}`;
  try {
    fmts[key] = fmts[key] || new Intl.NumberFormat(undefined, { style: 'currency', currency: cur, minimumFractionDigits: opts.whole ? 0 : 2, maximumFractionDigits: opts.whole ? 0 : 2, signDisplay: opts.sign ? 'exceptZero' : 'auto' });
    return fmts[key].format(+v);
  } catch { return `${(+v).toFixed(opts.whole ? 0 : 2)} ${cur}`; }
}
const pct = (v, sign = true) => (v == null ? '' : `${sign && v > 0 ? '+' : ''}${(+v).toFixed(2)}%`);
const qty = (v) => (v == null ? '' : (+v).toLocaleString(undefined, { maximumFractionDigits: 6 }));
const tone = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '');
const amt = (v, cur, opts) => h('span', { class: `num ${opts && opts.plain ? '' : tone(v)}` }, money(v, cur, opts));
const today = () => new Date().toLocaleDateString('sv');  // YYYY-MM-DD in the viewer's time zone
const thisMonth = () => today().slice(0, 7);
const dateOf = (s) => new Date(`${s}T12:00:00`);
const fmtDay = (s, long = false) => (s ? dateOf(s).toLocaleDateString(undefined, long ? { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' } : { day: 'numeric', month: 'short' }) : '');
const fmtMonth = (m) => new Date(`${m}-15T12:00:00`).toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
const shiftMonth = (m, n) => { const d = new Date(`${m}-15T12:00:00`); d.setMonth(d.getMonth() + n); return d.toISOString().slice(0, 7); };
const ago = (iso) => {
  if (!iso) return 'never';
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  return s < 90 ? 'just now' : s < 5400 ? `${Math.round(s / 60)} minutes ago` : s < 129600 ? `${Math.round(s / 3600)} hours ago` : `${Math.round(s / 86400)} days ago`;
};

// the kinds of accounts: icon and colour
const KIND_LOOK = { cash: ['bank', '--c-green'], investment: ['trend', '--c-indigo'], property: ['home', '--c-orange'], vehicle: ['car', '--c-teal'],
  other_asset: ['gem', '--c-purple'], credit: ['card', '--c-rose'], loan: ['loan', '--c-amber'], other_liability: ['loan', '--c-slate'] };
const kindLabel = (k) => ((S.sum && S.sum.kinds) || []).find((x) => x.kind === k)?.label || k;
/* The accounts are shown in five groups, in this order: Cash, Investments, Credit cards, Loans, Assets (the house, the
   cars, other things of value). The names and the kinds in each come from the server (api/summary). */
const GROUP_LOOK = { cash: ['bank', '--c-green'], investment: ['trend', '--c-indigo'], credit: ['card', '--c-rose'], loan: ['loan', '--c-amber'], asset: ['home', '--c-orange'] };
const groups = () => (S.sum && S.sum.groups) || [];
const groupOf = (kind) => (groups().find((g) => g.kinds.includes(kind)) || { group: 'asset' }).group;
const byGroup = (accts) => groups().map((g) => ({ ...g, list: accts.filter((a) => g.kinds.includes(a.kind)) })).filter((g) => g.list.length);
const followsTx = (a) => a.track === 'transactions';
const THINGS = ['property', 'vehicle', 'other_asset'];
const HOLDING_LABEL = { stock: 'Stocks', etf: 'ETFs', fund: 'Funds', bond: 'Bonds', crypto: 'Crypto', cash: 'Cash', option: 'Options', other: 'Other' };

// ------------------------------------------------------------------ charts: inline SVG
/** A line of values over days ([{day, value}]), with the area under it, a few gridlines and a tip that follows the
    pointer. */
function lineChart(points, { height = 220, cur = CUR() } = {}) {
  const box = h('div', { class: 'chart' });
  if (!points || points.length < 2) { put(box, h('p', { class: 'muted small' }, 'Not enough history yet: it grows with every day ioMoney runs.')); return box; }
  const W = 800, H = height, padL = 4, padR = 4, padT = 12, padB = 22;
  const vals = points.map((p) => p.value);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (lo === hi) { lo -= Math.abs(lo) * 0.05 || 1; hi += Math.abs(hi) * 0.05 || 1; }
  const span = hi - lo; lo -= span * 0.08; hi += span * 0.08;
  const x = (i) => padL + (i / (points.length - 1)) * (W - padL - padR);
  const y = (v) => padT + (1 - (v - lo) / (hi - lo)) * (H - padT - padB);
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join('');
  const ns = 'http://www.w3.org/2000/svg';
  const el = (n, a = {}) => { const e = document.createElementNS(ns, n); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); return e; };
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none', role: 'img', 'aria-label': 'Chart' });
  const g = el('g', { class: 'grid' });
  for (let i = 0; i <= 3; i++) { const yy = padT + i * (H - padT - padB) / 3; put(g, el('line', { x1: 0, x2: W, y1: yy, y2: yy })); }
  put(svg, g);
  if (lo < 0 && hi > 0) put(svg, el('line', { class: 'zero', x1: 0, x2: W, y1: y(0), y2: y(0) }));
  put(svg, el('path', { class: 'area', d: `${d}L${x(points.length - 1)},${H - padB}L${x(0)},${H - padB}Z` }), el('path', { class: 'line', d }));
  const t1 = el('text', { x: padL, y: H - 6 }); t1.textContent = fmtDay(points[0].day);
  const t2 = el('text', { x: W - padR, y: H - 6, 'text-anchor': 'end' }); t2.textContent = fmtDay(points[points.length - 1].day);
  put(svg, t1, t2);
  const hair = el('line', { class: 'hairline', y1: padT, y2: H - padB, visibility: 'hidden' });
  const dot = el('circle', { class: 'dot', r: 4, visibility: 'hidden' });
  put(svg, hair, dot);
  const tip = h('div', { class: 'tip', hidden: true });
  const hi2 = h('div', { class: 'tip', style: { left: '0', top: '-4px', transform: 'none', boxShadow: 'none', border: '0', background: 'none', padding: '0' } });
  hi2.textContent = money(hi - span * 0.08, cur, { whole: true });
  put(box, svg, tip, hi2);
  const move = (e) => {
    const r = svg.getBoundingClientRect();
    const i = Math.max(0, Math.min(points.length - 1, Math.round(((e.clientX - r.left) / r.width * W - padL) / (W - padL - padR) * (points.length - 1))));
    const px = x(i), py = y(points[i].value);
    hair.setAttribute('x1', px); hair.setAttribute('x2', px); hair.setAttribute('visibility', 'visible');
    dot.setAttribute('cx', px); dot.setAttribute('cy', py); dot.setAttribute('visibility', 'visible');
    tip.hidden = false; tip.style.left = `${(px / W) * 100}%`; tip.style.top = `${Math.max(0, (py / H) * r.height - 40)}px`;
    tip.replaceChildren(h('b', null, money(points[i].value, cur)), ' · ', fmtDay(points[i].day, true));
  };
  const leave = () => { tip.hidden = true; hair.setAttribute('visibility', 'hidden'); dot.setAttribute('visibility', 'hidden'); };
  svg.addEventListener('pointermove', move); svg.addEventListener('pointerleave', leave);
  return box;
}

/** Money in and out, month by month: two bars a month. */
function flowChart(items, { height = 200, cur = CUR() } = {}) {
  const box = h('div', { class: 'chart' });
  if (!items.length) return box;
  const W = 800, H = height, padB = 22, padT = 8;
  const top = Math.max(1, ...items.map((m) => Math.max(m.income, m.spent)));
  const slot = W / items.length, bw = Math.max(2, Math.min(26, slot / 3));
  const ns = 'http://www.w3.org/2000/svg';
  const el = (n, a = {}) => { const e = document.createElementNS(ns, n); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); return e; };
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none', role: 'img', 'aria-label': 'Money in and out by month' });
  const y = (v) => padT + (1 - v / top) * (H - padT - padB);
  const tip = h('div', { class: 'tip', hidden: true });
  items.forEach((m, i) => {
    const cx = slot * i + slot / 2;
    const r1 = el('rect', { class: 'bar-in', x: cx - bw - 1, y: y(m.income), width: bw, height: H - padB - y(m.income), rx: 2 });
    const r2 = el('rect', { class: 'bar-out', x: cx + 1, y: y(m.spent), width: bw, height: H - padB - y(m.spent), rx: 2 });
    const hit = el('rect', { x: slot * i, y: 0, width: slot, height: H, fill: 'transparent' });
    hit.addEventListener('pointerenter', () => { tip.hidden = false; tip.style.left = `${(cx / W) * 100}%`; tip.replaceChildren(h('b', null, fmtMonth(m.month)), h('br'), `In ${money(m.income, cur, { whole: true })} · Out ${money(m.spent, cur, { whole: true })}`); });
    hit.addEventListener('pointerleave', () => { tip.hidden = true; });
    hit.addEventListener('click', () => { location.hash = `#/spending/${m.month}`; });
    const t = el('text', { x: cx, y: H - 6, 'text-anchor': 'middle' }); t.textContent = new Date(`${m.month}-15T12:00:00`).toLocaleDateString(undefined, { month: 'short' });
    put(svg, r1, r2, t, hit);
  });
  put(box, svg, tip);
  return box;
}

function bar(label, value, max, { href, hueVar, cur, sub } = {}) {
  const w = max ? Math.max(1, Math.round(Math.abs(value) / max * 100)) : 0;
  const kids = [h('span', { class: 'barname' }, label, sub ? h('small', { class: 'muted' }, ` ${sub}`) : null),
    h('span', { class: 'bartrack' }, h('span', { class: `barfill ${value < 0 ? 'neg' : ''}`, style: { width: `${w}%`, '--hue': hueVar ? `var(${hueVar})` : null } })),
    h('span', { class: 'num' }, money(value, cur, { whole: Math.abs(value) >= 1000 }))];
  return href ? h('a', { class: 'barrow', href }, kids) : h('div', { class: 'barrow' }, kids);
}

/* The sidebar, as in the other io apps: the name on top, the pages (overview, transactions, spending, portfolio,
   house and cars), the accounts by kind, Settings at the foot. It docks beside the page on a wide screen unless its
   button put it away (remembered); otherwise it slides over the page. Phones get a bottom bar instead. */
const DOCK_MIN = 1100;
const VIEWS = { overview: ['Overview', 'dashboard', '--c-amber'], transactions: ['Transactions', 'receipt', '--c-blue'],
  spending: ['Spending', 'pie', '--c-rose'], portfolio: ['Portfolio', 'trend', '--c-indigo'], assets: ['Assets', 'home', '--c-orange'],
  recurring: ['Recurring', 'repeat', '--c-green'], tidy: ['Tidy up', 'tidy', '--c-purple'], rules: ['Rules', 'tune', '--c-teal'] };
/** A search as its address has it, whatever the order of its filters: to tell whether two are the same. */
const sameSearch = (a, b) => { const n = (x) => [...new URLSearchParams(x)].filter(([k, v]) => k !== 'offset' && v).map(([k, v]) => `${k}=${v}`).sort().join('&'); return n(a) === n(b); };
const TIDY_VIEWS = ['tidy', 'review', 'payees', 'duplicates', 'balance', 'changes', 'transfers'];
function drawNav() {
  const nav = $('#nav'); const r = route();
  const link = (v, href, ic, label, n, on, hueVar) => h('a', { href, 'data-v': v, class: on ? 'on' : null, style: hueVar ? { '--hue': `var(${hueVar})` } : null },
    icon(ic), h('span', { class: 'nl' }, label), n != null ? h('span', { class: 'n' }, n) : null);
  const sec = (label, btn) => h('div', { class: 'navsec' }, h('span', null, label), btn || null);
  const brandName = () => [h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Money')];
  const shown = S.accounts.filter((a) => !a.hidden && !a.closed);
  nav.replaceChildren(...[
    h('div', { class: 'navhead' },
      S.suite.length
        ? h('div', { class: 'brand' },
          h('button', { class: 'suitebtn', title: 'ioThing apps', 'aria-label': 'ioThing apps', 'aria-haspopup': 'menu', onclick: (e) => toggleSuite(e.currentTarget) },
            h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' })),
          h('a', { class: 'brand-name', href: '#/', title: 'Overview' }, brandName()))
        : h('a', { class: 'brand', href: '#/', title: 'Overview' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }),
          h('span', { class: 'brand-name' }, brandName())),
      h('button', { id: 'sidebtn', class: 'iconbtn', onclick: sidebarButton })),
    Object.entries(VIEWS).filter(([k]) => k !== 'assets' || shown.some((a) => THINGS.includes(a.kind)) || canAdd())
      .map(([k, [label, ic, hv]]) => [link(k, k === 'overview' ? '#/' : `#/${k}`, ic, label,
        k === 'recurring' && S.sum && S.sum.recurringFlags ? S.sum.recurringFlags : k === 'tidy' && S.sum && S.sum.review ? S.sum.review : null,
        r.view === k || (k === 'tidy' && TIDY_VIEWS.includes(r.view)), hv),
      // a person's saved searches, under Transactions
      k === 'transactions' ? S.searches.map((x) => link('acct', `#/transactions?${x.query}`, 'bookmark', x.name, null, r.view === 'transactions' && sameSearch(x.query, new URLSearchParams(r.q || {})), '--c-blue')) : null]),
    h('button', { class: 'navmore', 'data-v': 'more', title: 'More', onclick: moreSheet }, icon('more'), h('span', { class: 'nl' }, 'More')),
    byGroup(shown).map((g) => [h('div', { class: 'navgap' }), sec(g.label),
      g.list.map((a) => behindMark(link('acct', `#/account/${a.id}`, a.household ? KIND_LOOK[a.kind][0] : 'lock', a.name, null, r.view === 'account' && r.id === a.id, KIND_LOOK[a.kind][1]), a))]),
    canAdd() ? [h('div', { class: 'navgap' }), link('acct', '#/accounts/new', 'add', 'Add an account', null, false, '--c-green')] : null,
    h('div', { class: 'navfoot' }, link('settings', '#/settings', 'settings', 'Settings', null, r.view === 'settings')),
  ].flat(4).filter(Boolean));
  nav.querySelector('a[href="#/accounts/new"]')?.addEventListener('click', (e) => { e.preventDefault(); accountDialog(); });
  applySidebar();
  $('.navmore')?.classList.toggle('on', ['assets', 'rules', 'account', 'settings', 'categories', ...TIDY_VIEWS].includes(r.view));
}
/** An account whose link to its bank Monarch Money reports as cut, needing its sign-in fixed or over two days behind:
    a warning mark (with why) on its row. */
const behind = (a) => (a.bank && a.bank.stale ? a.bank : null);
function behindMark(el, a) {
  const b = behind(a);
  if (b) { el.classList.add('behind'); el.title = `${a.name}: ${b.why}`; el.append(h('span', { class: 'bwarn', 'aria-label': b.why }, icon('warning', 'xs'))); }
  return el;
}
function behindText(b) {
  if (b.stale === 'disconnected') return `Monarch Money's link to the bank was cut${b.disconnectedAt ? ` ${ago(b.disconnectedAt)}` : ''}`;
  if (b.stale === 'update') return 'Monarch Money needs the bank sign-in fixed';
  return `Monarch Money last heard from the bank ${ago(b.refreshedAt)}`;
}
/** Phones: what the bottom bar has no room for (the assets, the rules, the accounts, settings). */
function moreSheet() {
  const r = route();
  const tile = (href, ic, label, hueV, on) => h('a', { href, class: on ? 'on' : null, style: { '--hue': hueV } }, h('span', { class: 'sic' }, icon(ic)), h('span', null, label));
  const grid = h('div', { class: 'sheetgrid' },
    tile('#/assets', 'home', 'Assets', 'var(--c-orange)', r.view === 'assets'),
    tile('#/recurring', 'repeat', 'Recurring', 'var(--c-green)', r.view === 'recurring'),
    tile('#/tidy', 'tidy', 'Tidy up', 'var(--c-purple)', TIDY_VIEWS.includes(r.view)),
    tile('#/rules', 'tune', 'Rules', 'var(--c-teal)', r.view === 'rules'),
    tile('#/categories', 'list', 'Categories', 'var(--c-purple)', r.view === 'categories'),
    tile('#/settings', 'settings', 'Settings', 'var(--c-slate)', r.view === 'settings'),
    S.accounts.filter((a) => !a.hidden && !a.closed).map((a) => tile(`#/account/${a.id}`, KIND_LOOK[a.kind][0], a.name, `var(${KIND_LOOK[a.kind][1]})`, r.view === 'account' && r.id === a.id)));
  const p = dialog('More', grid, [{ label: 'Close', value: null }]);
  grid.addEventListener('click', (e) => { if (e.target.closest('a')) closeDialogs(); });
  return p;
}

// ------------------------------------------------------------------ routing
function route() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [path, query] = raw.split('?');
  const p = path.split('/').map((x) => { try { return decodeURIComponent(x); } catch { return x; } });
  const q = Object.fromEntries(new URLSearchParams(query || ''));
  const [a, b, c] = p;
  if (!a) return { view: 'overview' };
  if (a === 'transactions') return { view: 'transactions', q };
  if (a === 'transaction' && +b) return { view: 'transaction', id: +b };
  if (a === 'spending') return { view: 'spending', month: /^\d{4}-\d{2}$/.test(b || '') ? b : thisMonth() };
  if (a === 'portfolio') return { view: 'portfolio' };
  if (a === 'assets') return { view: 'assets' };
  if (a === 'rules') return { view: 'rules' };
  if (a === 'recurring') return { view: 'recurring' };
  if (a === 'categories') return { view: 'categories' };
  if (a === 'transfers') return { view: 'transfers', q };
  if (['tidy', 'review', 'payees', 'duplicates', 'balance', 'changes'].includes(a)) return { view: a, q };
  if (a === 'account' && b) return { view: 'account', id: +b, tab: c };
  if (a === 'settings') return { view: 'settings', tab: b || 'account', sub: c };
  return { view: 'overview' };
}

async function onRoute() {
  const r = route();
  const main = $('#main');
  closeMenu();
  try {
    const page = h('div', { class: 'page wide' });
    if (!may('read') && r.view !== 'settings') noRole(page);
    else await ({ overview: showOverview, transactions: showTransactions, spending: showSpending, portfolio: showPortfolio,
      assets: showAssets, rules: showRules, transaction: showTransaction, transfers: showTransfers, recurring: showRecurring, categories: showCategories, account: showAccount, settings: showSettings,
      tidy: showTidy, review: showReview, payees: showPayees, duplicates: showDuplicates, balance: showBalance, changes: showChanges })[r.view](page, r);
    main.replaceChildren(page);
    if (!r.keepScroll) main.scrollTop = 0;
  } catch (e) { main.replaceChildren(h('div', { class: 'page' }, h('div', { class: 'empty' }, icon('warning'), h('p', null, e.message || String(e)), h('p', null, h('a', { class: 'lnk', href: '#/' }, 'Overview'))))); }
  drawNav();
}
function noRole(page) {
  put(page, h('div', { class: 'empty' }, icon('lock'), h('p', null, 'You have no role in ioMoney yet.'),
    h('p', { class: 'muted' }, 'The household’s finances are shown only to the people given a role here: a suite admin gives one in Settings › Security › Roles.')));
}

// ------------------------------------------------------------------ overview: the net worth, its history, the accounts
const RANGES = [['30', '1M'], ['91', '3M'], ['365', '1Y'], ['1825', '5Y']];
async function showOverview(page) {
  const days = store.get('range') || '365';
  const nw = await api(`api/networth?days=${days}`);
  const hist = nw.history || [];
  const first = hist.length ? hist[0].value : null;
  const change = first != null ? nw.netWorth - first : null;
  const segs = h('div', { class: 'segs' }, RANGES.map(([d, l]) => h('button', { class: d === days ? 'on' : null, onclick: () => { store.set('range', d); onRoute(); } }, l)));
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Overview'), h('span', { class: 'grow' }), segs,
    canAdd() ? h('button', { class: 'pillbtn addacct', onclick: () => accountDialog() }, icon('add'), h('span', null, 'Account')) : null));
  put(page, flagNote());
  put(page, await lowNote());
  put(page, syncNote());
  put(page, h('div', { class: 'hero' },
    h('div', null, h('div', { class: 'lbl' }, 'Net worth'), h('div', { class: 'big num' }, money(nw.netWorth, nw.currency))),
    change != null ? h('div', { class: `chg num ${tone(change)}` }, `${money(change, nw.currency, { sign: true })} ${first ? `(${pct(change / Math.abs(first) * 100)})` : ''}`, h('small', { class: 'muted' }, ` over ${RANGES.find(([d]) => d === days)[1]}`)) : null));
  put(page, lineChart(hist));
  put(page, h('div', { class: 'cards' },
    h('div', { class: 'stat' }, h('div', { class: 'lbl' }, 'Assets'), h('div', { class: 'val num' }, money(nw.assets, nw.currency))),
    h('div', { class: 'stat' }, h('div', { class: 'lbl' }, 'Owed'), h('div', { class: 'val num neg' }, money(nw.liabilities, nw.currency)))));
  const max = Math.max(1, ...nw.byGroup.map((g) => Math.abs(g.value)));
  if (nw.byGroup.length) put(page, h('div', { class: 'box' }, h('h2', null, icon('pie'), 'By group'), h('div', { class: 'bars' }, nw.byGroup.map((g) => bar(g.label, g.value, max, { hueVar: GROUP_LOOK[g.group][1], cur: nw.currency })))));
  const accts = S.accounts.filter((a) => !a.hidden);
  if (!accts.length) {
    put(page, h('div', { class: 'empty' }, icon('bank'), h('p', null, 'No accounts yet.'),
      h('p', { class: 'muted' }, S.user.role === 'admin' ? 'Connect Monarch Money in Settings › Money, or add an account by hand.' : 'They come from Monarch Money, or are added by hand.')));
    return;
  }
  put(page, h('div', { class: 'groups' }, byGroup(accts).map((g) => {
    const total = g.list.filter((a) => a.inNetWorth && !a.closed).reduce((s, a) => s + (a.estimate != null ? (a.isAsset ? a.estimate : -a.estimate) : a.value), 0);
    return h('section', { class: 'group', style: { '--hue': `var(${GROUP_LOOK[g.group][1]})` } },
      h('header', null, icon(GROUP_LOOK[g.group][0]), h('span', { class: 'grow' }, g.label), amt(total, CUR(), { plain: true })),
      h('ul', { class: 'rows' }, g.list.map(acctRow)));
  })));
}
function acctRow(a) {
  const shown = a.estimate != null ? a.estimate : a.balance;
  return h('li', { class: a.closed || !a.inNetWorth ? 'off' : null }, h('a', { href: `#/account/${a.id}` },
    h('span', { class: 'main' }, h('b', null, a.name), h('small', null, [a.institution, a.subtype, a.mask ? `…${a.mask}` : null].filter(Boolean).join(' · ') || kindLabel(a.kind))),
    !a.household ? h('span', { class: 'tag priv', title: 'Yours alone' }, 'Private') : null,
    behind(a) ? h('span', { class: 'tag warn', title: behindText(a.bank) }, icon('warning', 'xs'), a.bank.stale === 'old' ? 'Behind' : 'Link broken') : null,
    a.estimate != null ? h('span', { class: 'tag est', title: 'Estimated from the last value and its yearly change' }, 'Est.') : null,
    !followsTx(a) && !THINGS.includes(a.kind) && a.kind !== 'investment' ? h('span', { class: 'tag', title: 'Its value alone is followed, not its transactions' }, 'Value') : null,
    h('span', { class: 'end' }, h('span', { class: `num ${a.isAsset ? '' : 'neg'}` }, money(a.isAsset ? shown : -Math.abs(shown), a.currency)),
      a.currency !== CUR() ? h('small', { class: 'muted num' }, money(a.value, CUR())) : a.equity != null ? h('small', { class: 'muted num' }, `Equity ${money(a.equity)}`) : null)));
}
function flagNote() {
  const n = S.sum && S.sum.recurringFlags;
  if (!n) return null;
  return h('div', { class: 'note warnnote' }, icon('warning', 's'),
    h('span', { class: 'grow' }, n === 1 ? 'A recurring transaction needs a look: a payment that did not come, or an amount that changed.'
      : `${n} recurring transactions need a look: payments that did not come, or amounts that changed.`),
    h('a', { class: 'pillbtn primary', href: '#/recurring' }, 'Review'));
}
function syncNote() {
  const m = S.sum && S.sum.monarch;
  if (!m || !m.configured) return null;
  const admin = S.user.role === 'admin';
  const out = [];
  if (m.newAccounts && admin) {
    out.push(h('div', { class: 'note warnnote' }, icon('warning', 's'),
      h('span', { class: 'grow' }, m.newAccounts === 1 ? 'Monarch Money reports an account ioMoney does not know. Is it new, or one you have that was made again in Monarch?'
        : `Monarch Money reports ${m.newAccounts} accounts ioMoney does not know. Are they new, or ones you have that were made again in Monarch?`),
      h('button', { class: 'pillbtn primary', onclick: () => newAccountsDialog() }, 'Review')));
  }
  if (m.stale && m.stale.length) {
    const one = m.stale.length === 1;
    out.push(h('div', { class: 'note warnnote behindnote' }, icon('warning', 's'),
      h('div', { class: 'grow' },
        h('div', null, one ? 'Monarch Money may have lost its link to the bank for this account:' : `Monarch Money may have lost its link to the bank for ${m.stale.length} accounts:`),
        h('ul', null, m.stale.map((x) => h('li', null, h('a', { class: 'lnk', href: `#/account/${x.id}` }, x.name), x.institution ? ` (${x.institution})` : '', `: ${behindText(x)}`))),
        h('small', { class: 'muted' }, `Check ${one ? 'its' : 'their'} connection in Monarch Money (Settings › Institutions); the next sync here picks up the change.`))));
  }
  if (m.running) {
    if (admin) watchSync();
    out.push(h('p', { class: 'muted small syncing', style: { margin: '-8px 0 12px' } }, h('span', { class: 'spin' }), ' Syncing with Monarch Money: ', h('span', { 'data-syncstage': '' }, 'under way')));
  } else {
    const stale = m.lastGood && (Date.now() - new Date(m.lastGood).getTime()) > 2 * 86400e3;
    out.push(h('p', { class: `muted small ${stale ? 'warn' : ''}`, style: { margin: '-8px 0 12px' } }, icon('sync', 'xs'), ` Monarch Money synced ${ago(m.lastGood)}`,
      admin ? [' · ', h('a', { class: 'lnk', href: '#/settings/money' }, 'Settings')] : null));
  }
  return out;
}

// ------------------------------------------------------------------ the Monarch sync: in the background, followed here
let syncPoll = null;
const syncLabel = (p) => (p && p.stage ? `${p.stage}${p.count ? ` (${p.count.toLocaleString()})` : ''}` : 'under way');
/** Follow a running sync (admins): its stage on the page every two seconds, and how it went at the end. A first sync
    of two years takes minutes, longer than a request waits, so it runs on in the server and is followed from here. */
function watchSync() {
  if (syncPoll) return;
  const tick = async () => {
    let st;
    try { st = await api('api/monarch'); } catch { syncPoll = setTimeout(tick, 5000); return; }
    document.querySelectorAll('[data-syncstage]').forEach((el) => { el.textContent = syncLabel(st.progress); });
    if (st.running) { syncPoll = setTimeout(tick, 2000); return; }
    syncPoll = null;
    if (st.last) toast(st.last.ok ? `Synced: ${st.last.message}` : `The sync did not work: ${st.last.message}`);
    await refreshSummary();
    if (!document.querySelector('.dialog-back')) onRoute();
  };
  syncPoll = setTimeout(tick, 1500);
}
async function startSync(full, btn) {
  if (btn) { btn.disabled = true; btn.lastChild.textContent = 'Starting…'; }
  try {
    const r = await api('api/monarch/sync', { method: 'POST', json: { full, wait: 5 } });
    if (r.running) toast('Syncing in the background: this page shows how it goes');
    else toast(r.ok ? `Synced: ${r.message}` : r.message);
  } catch (e) { fail(e); }
  await refreshSummary(); onRoute();
}

/** One Monarch account's two years of transactions (and its history, its holdings) fetched again; what was changed
    here stays, what Monarch no longer has (or hides) goes. */
async function resyncAccount(a) {
  const back = h('select', { class: 't' }, h('option', { value: '2' }, 'The past 2 years'), h('option', { value: '5' }, 'The past 5 years'), h('option', { value: '0' }, 'Everything Monarch has'));
  const body = h('div', null, h('p', null, `Fetch ${a.name}’s transactions from Monarch Money again. Your changes here (categories, notes, payees) stay; what Monarch no longer has, or hides, is removed here.`),
    fld('How far back', back));
  if (!await dialog('Sync this account again', body, [{ label: 'Cancel', value: false }, { label: 'Sync it', value: true, primary: true }])) return;
  try {
    const r = await api('api/monarch/sync', { method: 'POST', json: { accountId: a.id, years: +back.value, wait: 20 } });
    if (r.running) toast('Syncing in the background: Settings › Money shows how it goes');
    else toast(r.message);
  } catch (e) { fail(e); }
  await refreshSummary(); onRoute();
}
/** The accounts Monarch reported that ioMoney did not know: one at a time, new or an account here (the likeliest
    chosen); "Later" leaves the rest waiting. */
async function newAccountsDialog() {
  let items;
  try { items = (await api('api/monarch/new')).items || []; } catch (e) { fail(e); return; }
  for (const [i, x] of items.entries()) {
    const name = `pick-${x.externalId}`;
    const radio = (value, checked, ...label) => h('label', { class: 'pick' }, h('input', { type: 'radio', name, value, checked: checked ? true : null }), h('span', null, ...label));
    const desc = (a) => [a.institution, a.kind ? kindLabel(a.kind) : null, a.mask ? `…${a.mask}` : null].filter(Boolean).join(' · ');
    const body = h('div', { class: 'newacct' },
      h('div', { class: 'box', style: { margin: '0 0 14px' } }, h('b', null, x.name), h('div', { class: 'muted small' }, desc(x), x.closed ? ' · closed in Monarch' : ''),
        h('div', { class: 'num' }, money(x.balance))),
      h('p', { class: 'muted small' }, 'When a bank’s link breaks, an account is often deleted and made again in Monarch Money, with a new id. Say which it is, so its account and transactions are not here twice. Its transactions wait until then.'),
      h('div', { class: 'picks' }, radio('new', !x.likely, h('b', null, 'A new account'), h('small', null, 'Added here with its history and transactions')),
        x.candidates.map((c) => radio(String(c.id), c.id === x.likely, h('b', null, c.name), h('small', null, [desc(c), money(c.balance), c.gone ? 'no longer in Monarch' : c.source === 'manual' ? 'added by hand' : null].filter(Boolean).join(' · '))))));
    const ok = await dialog(items.length > 1 ? `New in Monarch Money (${i + 1} of ${items.length})` : 'New in Monarch Money', body,
      [{ label: 'Later', value: false }, { label: 'Save', value: true, primary: true }], 'wide');
    if (!ok) break;
    const v = body.querySelector(`input[name="${name}"]:checked`).value;
    try {
      await api(`api/monarch/new/${encodeURIComponent(x.externalId)}`, { method: 'POST', json: v === 'new' ? { as: 'new' } : { as: 'existing', accountId: +v } });
      toast(v === 'new' ? `${x.name} comes in with this sync` : 'Its transactions are matched with this sync, none twice');
    } catch (e) { fail(e); break; }
  }
  await refreshSummary(); onRoute();
}

// ------------------------------------------------------------------ one account
async function showAccount(page, r) {
  const a = await api(`api/accounts/${r.id}`);
  document.title = `${a.name} · ioMoney`;
  if (r.tab === 'reconcile') { await showReconcile(page, a); return; }
  const thing = THINGS.includes(a.kind);
  const tx = followsTx(a);
  const valued = thing || (!tx && a.kind !== 'investment');  // a value now and then, not transactions
  const shown = a.estimate != null ? a.estimate : a.balance;
  const menu = h('button', { class: 'iconbtn', title: 'More', 'aria-label': 'More', onclick: (e) => popMenu(e.currentTarget, [
    a.writable ? ['edit', 'Rename', () => renameAccount(a)] : null,
    a.writable ? ['tune', 'Edit', () => accountDialog(a)] : null,
    a.writable && !thing ? ['bank', 'Bank details', () => infoDialog(a)] : null,
    a.writable && a.source === 'manual' && valued ? ['add', 'Add a value', () => valueDialog(a)] : null,
    a.writable && a.source === 'manual' && a.kind === 'investment' ? ['add', 'Add a holding', () => holdingDialog(null, a.id)] : null,
    a.writable && tx ? ['add', 'Add a transaction', () => txDialog(null, a)] : null,
    tx ? ['receipt', 'Its transactions', `#/transactions?account=${a.id}`] : null,
    tx && a.writable ? ['check', 'Reconcile with a statement', `#/account/${a.id}/reconcile`] : null,
    tx && a.writable && a.source === 'manual' ? ['upload', 'Import a bank file', () => importDialog(a)] : null,
    a.source === 'monarch' && may('admin') ? ['sync', 'Sync this account again', () => resyncAccount(a)] : null,
    a.writable && a.bank && a.bank.linked && !a.closed ? (a.bank.quiet ? ['warning', 'Flag it when the bank link is behind', () => quietBank(a, false)]
      : ['warning', 'Don’t flag its bank link', () => quietBank(a, true)]) : null,
    a.writable && a.source === 'manual' ? ['delete', 'Delete', () => removeAccount(a)] : null,
  ]) }, icon('more'));
  put(page, h('div', { class: 'pagehead' }, h('span', { class: 'sic', style: { '--hue': `var(${KIND_LOOK[a.kind][1]})`, color: 'var(--hue)' } }, icon(KIND_LOOK[a.kind][0])),
    h('h1', null, a.name), a.writable ? h('button', { class: 'iconbtn rename', title: 'Rename', 'aria-label': 'Rename', onclick: () => renameAccount(a) }, icon('edit', 's')) : null, !a.household ? h('span', { class: 'tag priv' }, 'Private') : null, a.hidden ? h('span', { class: 'tag' }, 'Hidden') : null,
    a.closed ? h('span', { class: 'tag' }, 'Closed') : null,
    !tx && !thing ? h('span', { class: 'tag', title: 'Its value alone is followed, not its transactions (Edit to change)' }, 'Value only') : null,
    h('span', { class: 'grow' }), menu));
  put(page, h('div', { class: 'hero' },
    h('div', null, h('div', { class: 'lbl' }, [kindLabel(a.kind), a.institution, a.subtype].filter(Boolean).join(' · ')),
      h('div', { class: `big num ${a.isAsset ? '' : 'neg'}` }, money(a.isAsset ? shown : -Math.abs(shown), a.currency))),
    a.estimate != null ? h('div', { class: 'chg muted' }, h('span', { class: 'tag est' }, 'Estimated'), ` from ${money(a.balance, a.currency)} and ${a.details.yearlyRate}% a year`) : null,
    a.equity != null ? h('div', { class: 'chg' }, 'Equity ', amt(a.equity), h('small', { class: 'muted' }, ` after ${a.loan.name} (${money(a.loan.balance, a.loan.currency)})`)) : null,
    a.currency !== CUR() ? h('div', { class: 'chg muted num' }, money(a.value, CUR())) : null));
  if (a.source === 'monarch') {
    const b = a.bank;
    if (behind(a)) put(page, h('div', { class: 'note warnnote' }, icon('warning', 's'), h('span', { class: 'grow' }, `${behindText(b)}. Its balance and transactions may be out of date: check its connection in Monarch Money (Settings › Institutions).`)));
    put(page, h('p', { class: 'muted small', style: { margin: '-6px 0 12px' } }, icon('sync', 'xs'), ` From Monarch Money, updated ${ago(a.balanceAt)}`,
      b && b.linked && b.refreshedAt && !behind(a) ? ` · Monarch last heard from the bank ${ago(b.refreshedAt)}` : null,
      b && b.quiet ? ' · not flagged when behind' : null));
  }
  const days = store.get('range') || '365';
  const hist = await api(`api/accounts/${a.id}/history?days=${days}`);
  put(page, lineChart((hist.items || []).map((p) => ({ ...p, value: a.isAsset ? p.value : -p.value }))));
  if (thing) {
    const d = a.details || {};
    const facts = [['Address', d.address], ['Year', d.year], ['Make', d.make], ['Model', d.model], ['VIN', d.vin], ['Mileage', d.mileage],
      ['Bought on', d.boughtOn ? fmtDay(d.boughtOn, true) : null], ['Bought for', d.boughtFor != null ? money(d.boughtFor, a.currency) : null],
      ['Yearly change', d.yearlyRate != null ? `${d.yearlyRate}%` : null], ['Loan', a.loan ? h('a', { class: 'lnk', href: `#/account/${a.loan.id}` }, a.loan.name) : null]].filter(([, v]) => v != null && v !== '');
    if (facts.length || d.notes) put(page, h('div', { class: 'box' }, h('h2', null, icon('tune'), 'Details'), h('div', { class: 'kvs' }, facts.flatMap(([k, v]) => [h('span', null, k), h('span', null, v)])), d.notes ? h('p', { class: 'notes' }, d.notes) : null));
  }
  if (a.kind === 'cash' && tx && !a.closed) put(page, await forecastBox(a));
  if (a.kind === 'loan' && !a.closed) put(page, await payoffBox(a));
  if (!thing) put(page, await infoBox(a));
  if (a.kind === 'investment') await drawHoldings(page, a.id, a);
  if (valued) {
    const vals = (await api(`api/accounts/${a.id}/values`)).items || [];
    put(page, h('div', { class: 'box' }, h('h2', null, icon('trend'), 'Values', h('span', { class: 'grow' }),
      a.writable && a.source === 'manual' ? h('button', { class: 'pillbtn tiny', onclick: () => valueDialog(a) }, icon('add', 'xs'), 'Add') : null),
      vals.length ? h('ul', { class: 'rows' }, vals.filter((v) => v.source !== 'estimate' || v === vals[0]).slice(0, 40).map((v) => h('li', null, h('div', { class: 'r' },
        h('span', { class: 'day' }, fmtDay(v.day)), h('span', { class: 'main' }, h('b', null, v.note || { manual: 'Typed in', sync: a.source === 'monarch' ? 'From Monarch Money' : 'Its holdings', estimate: 'Estimate' }[v.source] || v.source), h('small', null, new Date(`${v.day}T12:00:00`).getFullYear())),
        h('span', { class: 'num' }, money(v.value, a.currency)),
        a.writable && a.source === 'manual' && v.source !== 'sync' ? h('button', { class: 'iconbtn', title: 'Remove this value', onclick: async () => { if (await confirmDialog('Remove the value', `Remove the value of ${fmtDay(v.day, true)}?`, 'Remove', true)) { await api(`api/accounts/${a.id}/values/${v.day}`, { method: 'DELETE' }); onRoute(); } } }, icon('delete', 's')) : null)))) : h('p', { class: 'muted' }, 'No values kept yet.')));
  }
  if (thing) put(page, linkedBox(a.id));
  if (tx) {
    const t = await api(`api/transactions?account=${a.id}&limit=50`);
    put(page, h('h2', null, 'Recent transactions'), txList(t.items, false),
      t.total > t.items.length ? h('div', { class: 'more' }, h('a', { class: 'pillbtn', href: `#/transactions?account=${a.id}` }, `All ${t.total}`)) : null);
  }
}
/** "Forecast" on a cash account's page: where its balance goes over the coming weeks from its recurring transactions
    and steady transfers, the lowest point against the balance it should not go under, and what is to come. */
async function forecastBox(a) {
  const days = store.get('fcdays') || '60';
  let f;
  try { f = await api(`api/accounts/${a.id}/forecast?days=${days}`); } catch { return null; }
  const segs = h('div', { class: 'segs' }, [['30', '30 days'], ['60', '60 days'], ['90', '90 days']].map(([d, l]) => h('button', { class: d === days ? 'on' : null, onclick: () => { store.set('fcdays', d); onRoute(); } }, l)));
  const floorBtn = a.writable ? h('button', { class: 'pillbtn tiny', onclick: () => floorDialog(a) }, icon('edit', 'xs'), f.floor != null ? `Keep above ${money(f.floor, f.currency)}` : 'Set a lowest balance') : (f.floor != null ? h('span', { class: 'muted small' }, `Keep above ${money(f.floor, f.currency)}`) : null);
  const head = h('h2', null, icon('trend'), 'Forecast', h('span', { class: 'grow' }), floorBtn, segs);
  if (!f.events.length) {
    return h('div', { class: 'box forecast' }, head, h('p', { class: 'muted' }, 'Nothing known to come: the forecast uses the recurring transactions kept for this account (Recurring page) and the transfers it makes at a steady pace.',
      f.leftOut.length ? ` Left out, as ${f.leftOut.length === 1 ? 'its' : 'their'} last payment did not come: ${f.leftOut.join(', ')}.` : '',
      f.unassigned ? ` ${f.unassigned} recurring transaction${f.unassigned === 1 ? ' is' : 's are'} kept for any account: give ${f.unassigned === 1 ? 'it' : 'them'} this account to count ${f.unassigned === 1 ? 'it' : 'them'}.` : ''));
  }
  const under = f.floor != null ? `under ${money(f.floor, f.currency)}` : 'under zero';
  const lowLine = f.below
    ? h('div', { class: 'note warnnote' }, icon('warning', 's'), h('span', { class: 'grow' }, `${f.belowOn === today() ? `It is ${under} now` : `It would go ${under} on ${fmtDay(f.belowOn, true)}`}; the lowest point is ${money(f.low.value, f.currency)} on ${fmtDay(f.low.day, true)}.`))
    : h('p', { class: 'muted small' }, `Lowest point: ${money(f.low.value, f.currency)} on ${fmtDay(f.low.day, true)} · ${money(f.end, f.currency)} after ${f.days} days`);
  const row = (e) => h('li', null, h('div', { class: 'r' }, h('span', { class: 'day' }, fmtDay(e.day)),
    h('span', { class: 'main' }, h('b', null, e.name, e.late ? h('span', { class: 'tag warn', title: 'It was due a few days ago and has not been seen yet: expected now' }, 'Late') : null),
      h('small', null, { recurring: 'Recurring', subscription: 'Subscription', transfer: 'Transfer at a steady pace' }[e.kind])),
    h('span', { class: `num ${e.amount < 0 ? '' : 'pos'}` }, `${e.approximate ? '≈ ' : ''}${money(e.amount, f.currency)}`),
    h('span', { class: `num bal ${e.balance < (f.floor != null ? f.floor : 0) ? 'neg' : 'muted'}` }, money(e.balance, f.currency))));
  return h('div', { class: 'box forecast' }, head, lowLine, lineChart(f.points, { height: 160, cur: f.currency }),
    h('ul', { class: 'rows fc' }, h('li', { class: 'fchead' }, h('div', { class: 'r' }, h('span', { class: 'day' }, 'Day'), h('span', { class: 'main' }, 'To come'), h('span', { class: 'num' }, 'Amount'), h('span', { class: 'num bal' }, 'Balance'))), f.events.map(row)),
    h('p', { class: 'muted small' }, 'Everyday spending is not counted: this is the most the account will hold.',
      f.leftOut.length ? ` Left out, as ${f.leftOut.length === 1 ? 'its' : 'their'} last payment did not come: ${f.leftOut.join(', ')}.` : '',
      f.unassigned ? ` ${f.unassigned} recurring transaction${f.unassigned === 1 ? '' : 's'} kept for any account ${f.unassigned === 1 ? 'is' : 'are'} left out.` : ''));
}
/** "Payoff" on a loan's page: from its interest rate and monthly payment, when it is paid off and the interest
    still to pay; with more paid a month, what that saves. */
async function payoffBox(a) {
  let p;
  try { p = await api(`api/accounts/${a.id}/payoff`); } catch { return null; }
  const edit = a.writable ? h('button', { class: 'pillbtn tiny', onclick: () => loanDialog(a, p) }, icon('edit', 'xs'), 'Rate and payment') : null;
  const head = h('h2', null, icon('loan'), 'Payoff', h('span', { class: 'grow' }), edit);
  if (p.needs.length) {
    return h('div', { class: 'box payoff' }, head, h('p', { class: 'muted' }, p.needs[0] === 'rate' ? 'Give the loan’s interest rate to see when it is paid off and the interest still to pay.'
      : 'Give what is paid a month: its balance has no history yet to work it out from.'));
  }
  const span = (m) => (m >= 12 ? `${Math.floor(m / 12)} year${m >= 24 ? 's' : ''}${m % 12 ? ` ${m % 12} month${m % 12 === 1 ? '' : 's'}` : ''}` : `${m} month${m === 1 ? '' : 's'}`);
  const monthOf = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
  const stat = (l, v, sub) => h('div', { class: 'stat' }, h('div', { class: 'lbl' }, l), h('div', { class: 'val num' }, v), sub ? h('small', { class: 'muted' }, sub) : null);
  const cards = h('div', { class: 'cards' },
    stat('Rate', `${p.rate}%`, 'a year'),
    stat('Payment', `${p.paymentEstimated ? '≈ ' : ''}${money(p.payment, p.currency)}`, p.paymentEstimated ? 'a month, from how the balance went down' : 'a month'),
    p.never ? stat('Paid off', 'Never', 'the payment does not cover the interest') : stat('Paid off', monthOf(p.payoff), `in ${span(p.months)}`),
    p.never ? null : stat('Interest left', money(p.interest, p.currency), `${money(p.total, p.currency)} in all`));
  const extra = inp(store.get(`extra${a.id}`) || '', { inputmode: 'decimal', placeholder: '100', style: { maxWidth: '120px' } });
  const result = h('p', { class: 'extraout' });
  const run = async () => {
    const v = extra.value.trim();
    store.set(`extra${a.id}`, v);
    if (!v || !(parseFloat(v) > 0)) { result.replaceChildren(); return; }
    try {
      const x = (await api(`api/accounts/${a.id}/payoff?extra=${encodeURIComponent(v)}`)).extra;
      if (!x || x.never) { result.textContent = 'Even so, the payment does not cover the interest.'; return; }
      put(result, h('b', null, `Paid off ${monthOf(x.payoff)}`), p.never ? ` (in ${span(x.months)}), with ${money(x.interest, p.currency)} of interest.`
        : [` · ${span(x.savedMonths)} sooner · `, h('span', { class: 'num pos' }, money(x.savedInterest, p.currency)), ' less interest']);
    } catch (e) { result.textContent = e.message || String(e); }
  };
  let timer = null;
  extra.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => { result.replaceChildren(); run(); }, 350); });
  if (extra.value) run();
  return h('div', { class: 'box payoff' }, head, cards,
    h('div', { class: 'extrarow' }, h('label', null, 'Paying', extra, 'more a month'), result));
}
async function loanDialog(a, p) {
  const d = a.details || {};
  const rate = inp(d.rate != null ? d.rate : '', { inputmode: 'decimal', placeholder: '6.25' });
  const pay = inp(d.payment != null ? d.payment : '', { inputmode: 'decimal', placeholder: p && p.paymentEstimated ? `about ${p.payment}` : '' });
  const body = h('div', null, h('div', { class: 'grid' }, fld('Interest rate (% a year)', rate), fld('Monthly payment', pay)),
    h('p', { class: 'muted small' }, 'The payment without what goes to escrow (taxes, insurance). Left empty, it is worked out from how the balance went down over the past three months.'));
  setTimeout(() => rate.focus(), 50);
  if (!await dialog(`${a.name}: rate and payment`, body, [{ label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }])) return;
  try { await api(`api/accounts/${a.id}`, { method: 'PATCH', json: { details: { rate: rate.value.trim(), payment: pay.value.trim() } } }); await refreshSummary(); toast('Saved'); onRoute(); } catch (e) { fail(e); }
}
async function floorDialog(a) {
  const v = inp(a.details && a.details.floor != null ? a.details.floor : '', { inputmode: 'decimal', placeholder: '500' });
  const body = h('div', null, fld('Lowest balance', v, true), h('p', { class: 'muted small' }, 'The forecast warns, here and on the overview, when the balance would go under it. Left empty: under zero.'));
  setTimeout(() => v.focus(), 50);
  if (!await dialog(`${a.name}: keep above`, body, [{ label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }])) return;
  try { await api(`api/accounts/${a.id}`, { method: 'PATCH', json: { details: { floor: v.value.trim() } } }); await refreshSummary(); toast('Saved'); onRoute(); } catch (e) { fail(e); }
}
/** The overview: the cash accounts that would go under their lowest balance in the next 30 days. */
async function lowNote() {
  let w = [];
  try { w = (await api('api/forecast?days=30')).items || []; } catch { return null; }
  return w.map((x) => h('div', { class: 'note warnnote' }, icon('warning', 's'),
    h('span', { class: 'grow' }, h('a', { class: 'lnk', href: `#/account/${x.accountId}` }, x.name), `${x.belowOn === today() ? ' is under' : ' would go under'} ${x.floor != null ? money(x.floor, x.currency) : 'zero'}${x.belowOn === today() ? ' now' : ` on ${fmtDay(x.belowOn, true)}`} (lowest: ${money(x.low.value, x.currency)} on ${fmtDay(x.low.day, true)}), counting what is known to come.`)));
}
async function quietBank(a, quiet) {
  try { await api(`api/accounts/${a.id}`, { method: 'PATCH', json: { flagStale: !quiet } }); await refreshSummary(); toast(quiet ? 'It won’t be flagged' : 'It will be flagged when behind'); onRoute(); } catch (e) { fail(e); }
}
// what is kept to deal with the account's bank: [field, label, how it is typed in]; the numbers are shown hidden
const INFO = [['accountNumber', 'Account number', { autocomplete: 'off', spellcheck: 'false' }], ['routingNumber', 'Routing number', { inputmode: 'numeric', autocomplete: 'off' }],
  ['iban', 'IBAN', { autocomplete: 'off', spellcheck: 'false' }], ['swift', 'SWIFT / BIC', { maxlength: 11, autocomplete: 'off' }],
  ['phone', 'Customer service', { type: 'tel', placeholder: '1-800-…' }], ['phoneAbroad', 'From abroad', { type: 'tel' }],
  ['website', 'Website', { type: 'url', placeholder: 'https://…' }], ['email', 'Email', { type: 'email' }], ['username', 'Sign-in name', { autocomplete: 'off' }],
  ['openedOn', 'Opened on', { type: 'date' }], ['address', 'Mailing address', null], ['notes', 'Notes', null]];
const INFO_SECRET = ['accountNumber', 'routingNumber', 'iban'];
async function copyText(v) { try { await navigator.clipboard.writeText(v); toast('Copied'); } catch { toast('Could not copy'); } }
/** "Bank details" on an account's page: its numbers (hidden until shown), customer service and the rest. */
async function infoBox(a) {
  let info = {};
  try { info = await api(`api/accounts/${a.id}/info`); } catch { return null; }
  const have = INFO.filter(([k]) => info[k]);
  if (!have.length && !a.writable) return null;
  const val = (k, v) => {
    if (INFO_SECRET.includes(k)) {
      const tail = v.replace(/\s/g, '').slice(-4);
      const shown = h('span', { class: 'num' }, `•••• ${tail}`);
      let open = false;
      return h('span', { class: 'secret' }, shown,
        h('button', { class: 'iconbtn', title: 'Show', 'aria-label': 'Show', onclick: (e) => { open = !open; shown.textContent = open ? v : `•••• ${tail}`; e.currentTarget.title = open ? 'Hide' : 'Show'; } }, icon('eye', 's')),
        h('button', { class: 'iconbtn', title: 'Copy', 'aria-label': 'Copy', onclick: () => copyText(v.replace(/\s/g, '')) }, icon('copy', 's')));
    }
    if (k === 'phone' || k === 'phoneAbroad') return h('a', { class: 'lnk', href: `tel:${v.replace(/[^0-9+]/g, '')}` }, v);
    if (k === 'website') return h('a', { class: 'lnk', href: v, target: '_blank', rel: 'noopener noreferrer' }, v.replace(/^https?:\/\//i, '').replace(/\/$/, ''));
    if (k === 'email') return h('a', { class: 'lnk', href: `mailto:${v}` }, v);
    if (k === 'openedOn') return fmtDay(v, true);
    if (k === 'swift' || k === 'username') return h('span', { class: 'secret' }, v, h('button', { class: 'iconbtn', title: 'Copy', 'aria-label': 'Copy', onclick: () => copyText(v) }, icon('copy', 's')));
    return v;
  };
  return h('div', { class: 'box' }, h('h2', null, icon('bank'), 'Bank details', h('span', { class: 'grow' }),
    a.writable ? h('button', { class: 'pillbtn tiny', onclick: () => infoDialog(a, info) }, icon(have.length ? 'edit' : 'add', 'xs'), have.length ? 'Edit' : 'Add') : null),
  have.length ? h('div', { class: 'kvs info' }, have.filter(([k]) => k !== 'notes' && k !== 'address').flatMap(([k, l]) => [h('span', null, l), h('span', null, val(k, info[k]))]),
    info.address ? [h('span', null, 'Mailing address'), h('span', { class: 'pre' }, info.address)] : null) : h('p', { class: 'muted small' }, 'Account and routing numbers, customer service and the like, to have at hand.'),
  info.notes ? h('p', { class: 'notes' }, info.notes) : null);
}
/** Change the bank details of an account (one from Monarch Money too: they are kept here alone). */
async function infoDialog(a, info) {
  if (!info) { try { info = await api(`api/accounts/${a.id}/info`); } catch (e) { fail(e); return; } }
  const f = Object.fromEntries(INFO.map(([k, , attrs]) => [k, k === 'address' || k === 'notes'
    ? h('textarea', { class: 't', rows: k === 'notes' ? 3 : 2 }, info[k] || '') : inp(info[k], attrs || {})]));
  const body = h('div', null, h('div', { class: 'grid' }, INFO.map(([k, l]) => fld(l, f[k], k === 'address' || k === 'notes' || k === 'website'))),
    h('p', { class: 'muted small' }, 'Seen by whoever sees this account; the numbers stay hidden until shown, and are never given to AI assistants (MCP). Keep passwords in a password manager, not here.'));
  if (!await dialog(`Bank details: ${a.name}`, body, [{ label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }], 'wide')) return;
  const b = Object.fromEntries(INFO.map(([k]) => [k, f[k].value.trim()]).filter(([k, v]) => v !== (info[k] || '')));
  if (!Object.keys(b).length) return;
  try { await api(`api/accounts/${a.id}/info`, { method: 'PUT', json: b }); toast('Saved'); onRoute(); } catch (e) { fail(e); }
}
let linkUi = null;
/** "Linked" under a house or a car: the events, tasks, notes, contacts and photos of the other apps linked to it. */
/** A new name for an account (one from Monarch Money too: the name here stays through the syncs). */
async function renameAccount(a) {
  const name = inp(a.name, { maxlength: 255 });
  const body = h('div', null, fld('Name', name, true), a.source === 'monarch' ? h('p', { class: 'muted small' }, 'Monarch Money keeps its own name; this one stays here through the syncs.') : null);
  setTimeout(() => { name.focus(); name.select(); }, 50);
  name.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); name.closest('.dialog')?.querySelector('button.primary')?.click(); } });
  if (!await dialog('Rename the account', body, [{ label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }])) return;
  try { await api(`api/accounts/${a.id}`, { method: 'PATCH', json: { name: name.value } }); await refreshSummary(); toast('Renamed'); onRoute(); } catch (e) { fail(e); }
}
function linkedBox(id) {
  const el = h('div', { class: 'linked' });
  (async () => {
    try { linkUi = linkUi || await import(new URL('api/related/ui.js', document.baseURI).href); } catch { return; }
    linkUi.mount(el, { kind: 'asset', id, toast });
  })();
  return el;
}
async function removeAccount(a) {
  if (!await confirmDialog('Delete the account', `Delete ${a.name} with its transactions, holdings and values? It cannot be brought back.`, 'Delete', true)) return;
  try { await api(`api/accounts/${a.id}`, { method: 'DELETE' }); toast('Deleted'); await refreshSummary(); location.hash = '#/'; } catch (e) { fail(e); }
}

const fld = (l, e, wide) => h('label', { class: `field ${wide ? 'wide' : ''}` }, h('span', null, l), e);
const inp = (v, attrs = {}) => h('input', { class: 't', value: v == null ? '' : v, ...attrs });
/** Add an account, or change one: what an account from Monarch takes is its name, hidden, in the net worth, its
    details and its loan. */
async function accountDialog(a) {
  const isNew = !a;
  a = a || { kind: 'cash', currency: CUR(), inNetWorth: true, household: may('household'), details: {}, source: 'manual' };
  const monarch = a.source === 'monarch';
  const f = {
    name: inp(a.name, { placeholder: 'Checking, Our house, Honda Civic' }),
    kind: h('select', { class: 't', disabled: monarch ? true : null }, groups().map((g) => h('optgroup', { label: g.label },
      (S.sum.kinds || []).filter((k) => g.kinds.includes(k.kind)).map((k) => h('option', { value: k.kind, selected: k.kind === a.kind ? true : null }, k.label))))),
    track: h('select', { class: 't' }, h('option', { value: 'transactions' }, 'Its transactions'), h('option', { value: 'value' }, 'Its value only')),
    balance: inp(a.balance, { inputmode: 'decimal', disabled: monarch ? true : null }),
    currency: inp(a.currency, { maxlength: 3, style: { textTransform: 'uppercase' }, disabled: monarch ? true : null }),
    institution: inp(a.institution, { disabled: monarch ? true : null }),
    inNetWorth: h('input', { type: 'checkbox', checked: a.inNetWorth ? true : null }),
    hidden: h('input', { type: 'checkbox', checked: a.hidden ? true : null }),
    household: h('input', { type: 'checkbox', checked: a.household ? true : null, disabled: !may('household') ? true : null }),
  };
  const d = a.details || {};
  const det = { address: inp(d.address), year: inp(d.year, { inputmode: 'numeric', maxlength: 4 }), make: inp(d.make), model: inp(d.model), vin: inp(d.vin),
    mileage: inp(d.mileage, { inputmode: 'numeric' }), boughtOn: inp(d.boughtOn, { type: 'date' }), boughtFor: inp(d.boughtFor, { inputmode: 'decimal' }),
    yearlyRate: inp(d.yearlyRate, { inputmode: 'decimal', placeholder: '3 (a house), -15 (a car)' }), notes: h('textarea', { class: 't', rows: 2 }, d.notes || '') };
  const loans = S.accounts.filter((x) => ['loan', 'other_liability'].includes(x.kind));
  const loan = h('select', { class: 't' }, h('option', { value: '' }, 'None'), loans.map((l) => h('option', { value: l.id, selected: a.loan && a.loan.id === l.id ? true : null }, l.name)));
  const thingBox = h('div', { class: 'grid' });
  const drawThing = () => {
    const k = f.kind.value;
    thingBox.replaceChildren(...(THINGS.includes(k) ? [
      k === 'property' ? fld('Address', det.address, true) : null,
      k === 'vehicle' ? [fld('Year', det.year), fld('Make', det.make), fld('Model', det.model), fld('VIN', det.vin), fld('Mileage', det.mileage)] : null,
      fld('Bought on', det.boughtOn), fld('Bought for', det.boughtFor),
      !monarch ? fld('Yearly change (%)', det.yearlyRate) : null, fld('Loan against it', loan), fld('Notes', det.notes, true)] : []).flat().filter(Boolean));
  };
  const balLabel = fld('Balance', f.balance);
  // what is followed: the kind's usual (transactions for a bank account or a card, the value for the rest) until chosen
  const usualTrack = () => ((S.sum.kinds || []).find((k) => k.kind === f.kind.value) || {}).track || 'value';
  let trackChosen = !isNew;
  f.track.value = a.track || usualTrack();
  f.track.onchange = () => { trackChosen = true; };
  const trackNote = h('p', { class: 'muted small', style: { margin: '4px 0 0' } });
  const drawTrack = () => {
    if (!trackChosen) f.track.value = usualTrack();
    trackNote.textContent = f.track.value === 'value'
      ? 'Only its balance or value is kept, as you type it in now and then (or as Monarch Money has it); its transactions stay out of the lists and the spending.'
      : monarch ? 'Its transactions come from Monarch Money and count in the spending.' : 'You add its transactions, and each one moves its balance.';
  };
  f.track.addEventListener('change', drawTrack);
  const drawKind = () => { drawThing(); drawTrack(); balLabel.firstChild.textContent = THINGS.includes(f.kind.value) ? 'Value' : f.kind.value === 'investment' ? 'Balance (or what its holdings are worth)' : 'Balance'; };
  f.kind.onchange = drawKind; drawKind();
  const body = h('div', null, h('div', { class: 'grid' },
    fld('Name', f.name, true), fld('Kind', f.kind), balLabel, fld('Currency', f.currency), fld('Institution', f.institution),
    h('label', { class: 'field wide' }, h('span', null, 'Follow'), f.track, trackNote)),
  thingBox,
  h('div', { class: 'chiprow', style: { marginTop: '12px', gap: '16px' } },
    h('label', { class: 'check' }, f.inNetWorth, 'Counts in the net worth'), h('label', { class: 'check' }, f.hidden, 'Hidden'),
    may('household') && (isNew ? may('own') : true) ? h('label', { class: 'check' }, f.household, 'The household’s (unticked: yours alone)') : null),
  monarch ? h('p', { class: 'muted small' }, 'This account comes from Monarch Money, which keeps its balance and transactions up to date.') : null);
  const ok = await dialog(isNew ? 'Add an account' : 'Edit the account', body, [{ label: 'Cancel', value: false }, { label: isNew ? 'Add' : 'Save', value: true, primary: true }], 'wide');
  if (!ok) return;
  const b = { name: f.name.value, inNetWorth: f.inNetWorth.checked, hidden: f.hidden.checked, track: f.track.value };
  if (!monarch) Object.assign(b, { kind: f.kind.value, balance: f.balance.value || 0, currency: f.currency.value.toUpperCase(), institution: f.institution.value });
  if (may('household')) b.household = f.household.checked;
  if (THINGS.includes(f.kind.value)) {
    b.details = Object.fromEntries(Object.entries(det).filter(([k]) => !(monarch && k === 'yearlyRate')).map(([k, e]) => [k, e.value.trim()]));
    b.loanId = loan.value ? +loan.value : null;
  }
  try {
    const r = await api(isNew ? 'api/accounts' : `api/accounts/${a.id}`, { method: isNew ? 'POST' : 'PATCH', json: b });
    toast(isNew ? 'Added' : 'Saved'); await refreshSummary();
    if (isNew) location.hash = `#/account/${r.id}`; else onRoute();
  } catch (e) { fail(e); }
}
async function valueDialog(a) {
  const v = inp('', { inputmode: 'decimal', placeholder: money(a.estimate != null ? a.estimate : a.balance, a.currency) });
  const d = inp(today(), { type: 'date', max: today() });
  const n = inp('', { placeholder: 'Appraisal, Zillow, KBB, sale price of a neighbour…' });
  const ok = await dialog(`What ${a.name} is worth`, h('div', { class: 'grid' }, fld('Value', v), fld('On', d), fld('Where it comes from', n, true)), [{ label: 'Cancel', value: false }, { label: 'Add', value: true, primary: true }]);
  if (!ok) return;
  try { await api(`api/accounts/${a.id}/values`, { method: 'POST', json: { value: v.value, day: d.value, note: n.value } }); toast('Added'); await refreshSummary(); onRoute(); } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ recurring: bills and money coming in regularly
/** The household's recurring transactions (what ioCalendar shows on their days), and what ioMoney found in the
    transactions that looks recurring: Add, or Not recurring. */
async function showRecurring(page) {
  const d = await api('api/recurring');
  const w = d.writable;
  S.freqs = d.frequencies;
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Recurring'), h('span', { class: 'grow' }),
    w ? h('button', { class: 'pillbtn', onclick: () => recurringDialog() }, icon('add'), h('span', null, 'Recurring')) : null));
  put(page, h('p', { class: 'muted' }, 'Bills, subscriptions and paychecks: what comes back at a steady pace. ioCalendar shows each on the day it is due, ticked once paid. ',
    'ioMoney looks for them in the transactions; add the ones that are, or add one by hand.'));
  const money2 = (x) => h('span', { class: `num ${x.amount < 0 ? '' : 'pos'}` }, `${x.approximate ? '≈ ' : ''}${money(x.amount, x.currency)}`);
  const row = (x) => h('li', null, h('div', { class: 'r', role: w ? 'button' : null, tabindex: w ? 0 : null, onclick: w ? () => recurringDialog(x) : null },
    h('span', { class: 'main' }, h('b', null, x.name, x.flag ? h('span', { class: 'tag warn', title: flagText(x) }, icon('warning', 'xs'), x.flag.kind === 'missed' ? (x.flow === 'out' ? 'Not paid' : 'Missing') : 'Amount changed') : null), h('small', null, [x.frequencyLabel, x.account || 'Any account', x.category, x.last ? `last ${fmtDay(x.last.day, x.last.day.slice(0, 4) !== today().slice(0, 4))} ${money(x.last.amount, x.currency)}` : 'not seen yet'].filter(Boolean).join(' · '))),
    h('span', { class: 'when' }, x.next ? `next ${fmtDay(x.next, true)}` : ''),
    h('span', { class: 'amt' }, money2(x))));
  const monthly = (xs) => xs.reduce((s, x) => s + Math.abs(x.perMonth), 0);
  const subs = d.items.filter((x) => x.subscription);
  const bills = d.items.filter((x) => !x.subscription && x.flow === 'out');
  const income = d.items.filter((x) => !x.subscription && x.flow === 'in');
  if (!d.items.length) put(page, h('div', { class: 'empty' }, icon('repeat'), h('p', null, 'None in the list yet.'), h('p', { class: 'muted' }, d.found.length ? 'Add the ones found below.' : 'Add one by hand.')));
  else put(page, h('p', { class: 'sumline' }, `${d.items.length} recurring · out about `, h('span', { class: 'num' }, money(monthly(subs) + monthly(bills), CUR())), ' a month · in about ', h('span', { class: 'num pos' }, money(monthly(income), CUR())), ' a month'));
  const section = (title, ic, xs, note, empty) => {
    if (!xs.length && !empty) return;
    put(page, h('h2', { class: 'recurhead' }, icon(ic), h('span', null, `${title} (${xs.length})`), h('span', { class: 'grow' }), xs.length ? note : null));
    put(page, xs.length ? h('ul', { class: 'rows recur' }, xs.map(row)) : h('p', { class: 'muted' }, empty));
  };
  // what is off: a payment that did not come, an amount that changed
  const flagged = d.items.filter((x) => x.flag);
  if (flagged.length) {
    put(page, h('h2', { class: 'recurhead' }, icon('warning'), h('span', null, `To check (${flagged.length})`)));
    put(page, h('ul', { class: 'rows recur flagged' }, flagged.map((x) => {
      const f = x.flag;
      const act = (label, fn, cls) => h('button', { class: `pillbtn tiny ${cls || ''}`, onclick: async (e) => { e.stopPropagation(); try { await fn(); await refreshSummary(); onRoute(); } catch (er) { fail(er); } } }, label);
      const ok = () => api(`api/recurring/${x.id}/ok`, { method: 'POST', json: { kind: f.kind, day: f.day } });
      const acts = !x.writable ? null : f.kind === 'changed'
        ? [act(`Use ${money(Math.abs(f.to), x.currency)}`, () => api(`api/recurring/${x.id}`, { method: 'PATCH', json: { amount: Math.abs(f.to) } }), 'primary'), act('Dismiss', ok)]
        : [act('Dismiss', ok), act('It stopped', async () => { if (await confirmDialog('Remove it', `Remove ${x.name} from the recurring transactions?`, 'Remove', true)) await api(`api/recurring/${x.id}`, { method: 'DELETE' }); })];
      return h('li', null, h('div', { class: 'r' },
        h('span', { class: 'main' }, h('b', null, x.name), h('small', null, flagText(x))),
        h('span', { class: 'amt' }, money2(x)), acts ? h('span', { class: 'end acts', style: { flexDirection: 'row', gap: '6px' } }, acts) : null));
    })));
  }
  const subsFound = d.found.filter((x) => x.subscription).length;
  section('Subscriptions', 'play', subs, h('span', { class: 'muted small' }, h('span', { class: 'num' }, money(monthly(subs), CUR())), ' a month · ', h('span', { class: 'num' }, money(monthly(subs) * 12, CUR())), ' a year'),
    subsFound ? `None yet. ${subsFound} found in the transactions below ${subsFound === 1 ? 'is' : 'are'} marked Subscription: Add ${subsFound === 1 ? 'it' : 'them'} here.`
      : 'None yet. Netflix, Spotify, iCloud and the like land here once added; mark any recurring one as a subscription, or open a transaction and choose Make recurring.');
  section('Bills', 'repeat', bills, h('span', { class: 'muted small' }, h('span', { class: 'num' }, money(monthly(bills), CUR())), ' a month'));
  section('Money coming in', 'download', income, h('span', { class: 'muted small' }, h('span', { class: 'num pos' }, money(monthly(income), CUR())), ' a month'));
  if (d.found.length) {
    put(page, h('h2', { class: 'recurhead' }, icon('search'), h('span', null, `Found in the transactions (${d.found.length})`)));
    put(page, h('ul', { class: 'rows recur found' }, d.found.map((x) => {
      const add = h('button', { class: 'pillbtn primary tiny' }, icon('add', 'xs'), 'Add');
      const not = h('button', { class: 'pillbtn tiny' }, 'Not recurring');
      add.onclick = async () => { try { await api('api/recurring', { method: 'POST', json: { found: x.key } }); toast('Added'); onRoute(); } catch (e) { fail(e); } };
      not.onclick = async () => { try { await api('api/recurring/not', { method: 'POST', json: { key: x.key } }); add.closest('li').remove(); } catch (e) { fail(e); } };
      return h('li', null, h('div', { class: 'r' },
        h('span', { class: 'main' }, h('b', null, x.name, x.subscription ? h('span', { class: 'tag' }, 'Subscription') : null), h('small', null, [x.frequencyLabel, x.account, x.category, `${x.count} times, last ${fmtDay(x.day, true)}`].filter(Boolean).join(' · '))),
        h('span', { class: 'when' }, x.next ? `next ${fmtDay(x.next, true)}` : ''),
        h('span', { class: 'amt' }, money2(x)), w ? h('span', { class: 'end acts', style: { flexDirection: 'row', gap: '6px' } }, add, not) : null));
    })));
  }
}
/** What a recurring transaction's flag says: the payment that did not come, or the amount that changed. */
function flagText(x) {
  const f = x.flag;
  if (f.kind === 'changed') {
    const up = Math.abs(f.to) > Math.abs(f.from);
    return `${x.flow === 'out' ? (up ? 'Went up' : 'Came down') : (up ? 'More than usual' : 'Less than usual')}: ${money(Math.abs(f.to), x.currency)} on ${fmtDay(f.day, true)}, ${x.approximate ? 'usually about' : 'was'} ${money(Math.abs(f.from), x.currency)}`;
  }
  return `${x.flow === 'out' ? 'Not paid' : 'Did not come'}: expected about ${fmtDay(f.expected, true)}, last seen ${fmtDay(f.since, true)}`;
}
/** Add a recurring transaction by hand, or change or remove one. */
async function recurringDialog(x, preset) {
  const isNew = !x;
  x = x || preset || { flow: 'out', frequency: 'monthly', day: today(), approximate: false };
  const cats = await categories();
  const freqs = S.freqs || [];
  const f = { name: inp(x.name, { placeholder: 'Power bill, Netflix, Paycheck' }), pattern: inp(x.pattern, { placeholder: 'the payee’s name or words of the bank’s text' }),
    account: h('select', { class: 't' }, h('option', { value: '' }, 'Any account'), S.accounts.filter(followsTx).map((a) => h('option', { value: a.id, selected: a.id === x.accountId ? true : null }, a.name))),
    flow: h('select', { class: 't' }, h('option', { value: 'out', selected: x.flow === 'out' ? true : null }, 'Money out (a bill)'), h('option', { value: 'in', selected: x.flow === 'in' ? true : null }, 'Money in (a paycheck)')),
    amount: inp(x.amount != null ? Math.abs(x.amount) : '', { inputmode: 'decimal' }), approximate: h('input', { type: 'checkbox', checked: x.approximate ? true : null }),
    subscription: h('input', { type: 'checkbox', checked: x.subscription ? true : null }),
    frequency: h('select', { class: 't' }, freqs.map((q) => h('option', { value: q.value, selected: q.value === x.frequency ? true : null }, q.label))),
    day: inp(x.day, { type: 'date' }), category: inp(x.category, { list: 'reccats' }) };
  const body = h('div', null, h('datalist', { id: 'reccats' }, cats.map((c) => h('option', { value: c.category }))),
    h('div', { class: 'grid' }, fld('Name', f.name, true), fld('Its payee or bank’s text has', f.pattern, true), fld('Account', f.account), fld('Way', f.flow),
      fld('Usual amount', f.amount), fld('How often', f.frequency), fld('A day it falls on', f.day), fld('Category', f.category)),
    h('label', { class: 'check', style: { marginTop: '10px' } }, f.approximate, 'The amount varies (a payment within a third of it counts)'),
    h('label', { class: 'check', style: { marginTop: '6px' } }, f.subscription, isNew ? 'A subscription to a service (Netflix, Spotify, iCloud…; a known one is marked on its own)' : 'A subscription to a service (shown under Subscriptions)'));
  const btns = [!isNew ? { label: 'Remove', value: 'delete', danger: true } : null, { label: 'Cancel', value: false }, { label: isNew ? 'Add' : 'Save', value: true, primary: true }].filter(Boolean);
  if (isNew && preset) body.prepend(h('p', { class: 'muted small', style: { marginTop: 0 } }, preset.count > 1
    ? `From this transaction and the ${preset.count - 1} other${preset.count === 2 ? '' : 's'} like it in the past year: check how often and the amount.`
    : 'From this transaction, the only one like it in the past year: check how often it comes back.'));
  const ok = await dialog(isNew ? (preset ? 'Make it recurring' : 'Add a recurring transaction') : x.name, body, btns, 'wide');
  if (ok === 'delete') {
    if (!await confirmDialog('Remove it', `Remove ${x.name} from the recurring transactions? Its transactions stay.`, 'Remove', true)) return;
    try { await api(`api/recurring/${x.id}`, { method: 'DELETE' }); toast('Removed'); onRoute(); } catch (e) { fail(e); } return;
  }
  if (!ok) return;
  const b = { name: f.name.value, pattern: f.pattern.value || f.name.value, accountId: f.account.value ? +f.account.value : null, flow: f.flow.value,
    amount: f.amount.value, approximate: f.approximate.checked, frequency: f.frequency.value, day: f.day.value, category: f.category.value };
  if (!isNew || preset || f.subscription.checked) b.subscription = f.subscription.checked;
  try { await api(isNew ? 'api/recurring' : `api/recurring/${x.id}`, { method: isNew ? 'POST' : 'PATCH', json: b }); toast(isNew ? 'Added' : 'Saved'); onRoute(); } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ categories
/** Every category by group: add one, rename it (into another: merged), move it to another group, delete it (its
    transactions moved to another or left without one). What Monarch sends later follows. */
async function showCategories(page) {
  const d = await api('api/categories');
  const w = d.writable;
  S.cats = d.items;
  put(page, h('div', { class: 'pagehead' }, h('a', { class: 'iconbtn', href: '#/transactions', title: 'Transactions', 'aria-label': 'Transactions' }, icon('prev')),
    h('h1', null, 'Categories'), h('span', { class: 'grow' }),
    w ? h('button', { class: 'pillbtn', onclick: () => categoryDialog(null, d.items) }, icon('add'), h('span', null, 'Category')) : null));
  put(page, h('p', { class: 'muted' }, 'The categories of the transactions, by group. A category renamed, merged into another or deleted here stays so: what Monarch Money sends later under the old name comes in under the new one.'));
  const groups = new Map();
  for (const c of d.items) { const g = c.group || 'No group'; if (!groups.has(g)) groups.set(g, []); groups.get(g).push(c); }
  for (const [g, list] of groups) {
    put(page, h('div', { class: 'catgrp' }, h('h3', null, g), h('ul', { class: 'rows' }, list.map((c) => h('li', null,
      h('div', { class: 'r', role: w ? 'button' : null, tabindex: w ? 0 : null, onclick: w ? () => categoryDialog(c, d.items) : null },
        h('span', { class: 'main' }, h('b', null, c.category)),
        h('a', { class: 'lnk small', href: `#/transactions?${new URLSearchParams({ category: c.category })}`, onclick: (e) => e.stopPropagation() }, `${c.count} transaction${c.count === 1 ? '' : 's'}`)))))));
  }
  await drawTags(page);
}
async function categoryDialog(c, all) {
  const isNew = !c;
  const groups = [...new Set(all.map((x) => x.group).filter(Boolean))].sort();
  const f = { name: inp(c ? c.category : '', { maxlength: 128, list: isNew ? null : 'catnames' }), group: inp(c ? c.group : '', { list: 'catgroups', placeholder: 'Food & Dining, Bills & Utilities…' }) };
  const body = h('div', null, h('datalist', { id: 'catgroups' }, groups.map((g) => h('option', { value: g }))),
    h('datalist', { id: 'catnames' }, all.filter((x) => !c || x.category !== c.category).map((x) => h('option', { value: x.category }))),
    h('div', { class: 'grid' }, fld('Name', f.name), fld('Group', f.group)),
    !isNew ? h('p', { class: 'muted small' }, `${c.count} transaction${c.count === 1 ? '' : 's'}. Give it the name of another category to merge the two.`) : null);
  const btns = [!isNew ? { label: 'Delete', value: 'delete', danger: true } : null, { label: 'Cancel', value: false }, { label: isNew ? 'Add' : 'Save', value: true, primary: true }].filter(Boolean);
  const ok = await dialog(isNew ? 'Add a category' : c.category, body, btns);
  if (ok === 'delete') {
    const to = h('select', { class: 't' }, h('option', { value: '' }, 'No category'), all.filter((x) => x.category !== c.category).map((x) => h('option', { value: x.category }, x.category)));
    const go = await dialog(`Delete ${c.category}`, h('div', null, h('p', null, `Its ${c.count} transaction${c.count === 1 ? '' : 's'} (and the rules and recurring transactions that set it) move to:`), fld('Category', to)),
      [{ label: 'Cancel', value: false }, { label: 'Delete', value: true, danger: true }]);
    if (!go) return;
    try { const r = await api('api/categories/delete', { method: 'POST', json: { name: c.category, moveTo: to.value || null } }); S.cats = []; toast(`Deleted; ${r.moved} moved`); onRoute(); } catch (e) { fail(e); }
    return;
  }
  if (!ok) return;
  try {
    if (isNew) await api('api/categories', { method: 'POST', json: { name: f.name.value, group: f.group.value } });
    else {
      const merge = all.some((x) => x.category === f.name.value.trim() && x.category !== c.category);
      if (merge && !await confirmDialog('Merge the categories', `Merge ${c.category} into ${f.name.value.trim()}? Its ${c.count} transactions move there.`, 'Merge')) return;
      await api('api/categories', { method: 'PUT', json: { name: c.category, newName: f.name.value, group: f.group.value } });
    }
    S.cats = []; toast(isNew ? 'Added' : 'Saved'); onRoute();
  } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ transactions
async function categories() {
  if (!S.cats.length) { try { S.cats = (await api('api/categories')).items || []; } catch { S.cats = []; } }
  return S.cats;
}
/** #/transaction/12 (a link from another app's item, say): the transactions of its account and month, with it open. */
async function showTransaction(page, r) {
  const t = await api(`api/transactions/${r.id}`);
  const q = { account: String(t.accountId), month: t.day.slice(0, 7) };
  history.replaceState(null, '', `#/transactions?${new URLSearchParams(q)}`);
  await showTransactions(page, { view: 'transactions', q });
  txDialog(t);
}
/** The transactions, one row each: date, payee, notes, category (or where a transfer went) and amount (and the
    account, where the list mixes them). On a phone the notes and the account give way, the category goes under the payee. */
const fmtTxDay = (s) => { const d = dateOf(s); return d.toLocaleDateString(undefined, d.getFullYear() === new Date().getFullYear() ? { day: 'numeric', month: 'short' } : { day: 'numeric', month: 'short', year: '2-digit' }); };
function txCat(t) {
  if (t.transfer) return h('span', { class: 'xfer', title: `A transfer ${t.amount < 0 ? 'to' : 'from'} ${t.transfer.account}${t.transfer.how === 'hand' ? ' (linked by hand)' : ''}` }, icon('link', 'xs'), `${t.amount < 0 ? 'To' : 'From'} ${t.transfer.account}`);
  if (t.splits && t.splits.length) return h('span', { class: 'split', title: t.splits.map((p) => `${p.category || 'Uncategorized'} ${money(p.amount, t.currency)}`).join(' · ') }, icon('split', 'xs'), [...new Set(t.splits.map((p) => p.category || 'Uncategorized'))].join(', '));
  return t.category ? h('span', null, t.category) : h('span', { class: 'muted' }, 'Uncategorized');
}
function txList(items, showAccount = true, showBank = store.get('txbank') === '1', opt = {}) {
  if (!items.length) return h('p', { class: 'muted' }, 'No transactions.');
  const cls = `rows flat txs ${showAccount ? 'withacct' : ''} ${showBank ? 'withbank' : ''} ${opt.picked ? 'sel' : ''}`;
  const boxes = [];
  const pick = (t) => {  // a tick to change several at once (opt.picked: the ids ticked; opt.onPick: after each change)
    if (!opt.picked) return null;
    if (!t.writable) return h('span', { class: 's' });
    const b = h('input', { type: 'checkbox', 'aria-label': 'Select', checked: opt.picked.has(t.id) ? true : null, onclick: (e) => e.stopPropagation(),
      onchange: () => { if (b.checked) opt.picked.add(t.id); else opt.picked.delete(t.id); b.closest('li').classList.toggle('picked', b.checked); opt.onPick(); } });
    boxes.push([t, b]);
    return h('span', { class: 's', onclick: (e) => e.stopPropagation() }, b);
  };
  const all = opt.picked ? h('input', { type: 'checkbox', title: 'Select all shown', 'aria-label': 'Select all shown', onchange: (e) => {
    for (const [t, b] of boxes) { b.checked = e.target.checked; b.closest('li').classList.toggle('picked', b.checked); if (b.checked) opt.picked.add(t.id); else opt.picked.delete(t.id); }
    opt.onPick();
  } }) : null;
  return h('ul', { class: cls },
    h('li', { class: 'txhead' }, h('div', { class: 'r tx' }, opt.picked ? h('span', { class: 's' }, all) : null, h('span', { class: 'd' }, 'Date'), h('span', { class: 'p' }, 'Payee'),
      showBank ? h('span', { class: 'b' }, 'At the bank') : null, h('span', { class: 'n' }, 'Notes'), h('span', { class: 'c' }, 'Category'), showAccount ? h('span', { class: 'a' }, 'Account') : null, h('span', { class: 'm' }, 'Amount'), h('span', { class: 'rc', title: opt.review ? 'Reviewed' : 'Reconciled' }, '✓'))),
    items.map((t) => h('li', { class: t.hidden ? 'off' : null }, h('div', { class: 'r tx', role: 'button', tabindex: 0, onclick: () => txDialog(t),
      onkeydown: (e) => { if (e.key === 'Enter' && e.target === e.currentTarget) txDialog(t); } },
      pick(t),
      h('span', { class: 'd' }, fmtTxDay(t.day)),
      h('span', { class: 'p' }, h('b', null, t.merchant || t.description || '(no payee)'), t.pending ? h('span', { class: 'tag' }, 'Pending') : null,
        t.recurring ? h('span', { class: 'rec', title: `Recurring: ${t.recurring.name}${t.recurring.subscription ? ' (a subscription)' : ''}` }, icon(t.recurring.subscription ? 'play' : 'repeat', 'xs')) : null,
        t.receipts && t.receipts.length ? h('span', { class: 'rcp', title: t.receipts.length === 1 ? 'A receipt is kept with it' : `${t.receipts.length} receipts are kept with it` }, icon('attach', 'xs')) : null,
        (t.tags || []).map((x) => h('span', { class: 'tag tg' }, x)),
        h('small', { class: 'cs' }, txCat(t))),
      showBank ? h('span', { class: 'b', title: t.description || null }, t.description || '') : null,
      h('span', { class: 'n', title: t.notes || null }, t.notes || ''),
      h('span', { class: 'c' }, txCat(t)),
      showAccount ? h('span', { class: 'a' }, t.account) : null,
      h('span', { class: 'm' }, amt(t.amount, t.currency)),
      h('span', { class: 'rc' }, opt.review ? reviewTick(t, opt) : recTick(t))))));
}
/** On the Needs a look page: the tick that says a transaction was looked at; it leaves the list. */
function reviewTick(t, opt) {
  const b = h('button', { class: 'tick', title: 'Looked at: take it off this list', 'aria-label': 'Reviewed', disabled: t.writable ? null : true }, icon('check', 's'));
  b.onclick = async (e) => {
    e.stopPropagation();
    try {
      const r = await api('api/transactions/review', { method: 'POST', json: { ids: [t.id] } });
      if (opt.picked) opt.picked.delete(t.id);
      b.closest('li').remove();
      if (S.sum) S.sum.review = r.left;
      drawNav();
      if (opt.onReviewed) opt.onReviewed(r.left);
    } catch (x) { fail(x); }
  };
  return b;
}
/** The reconciled tick of a transaction: a click marks it (or unmarks it) without opening it. */
function recTick(t) {
  const b = h('button', { class: `tick ${t.reconciled ? 'on' : ''}`, title: t.reconciled ? 'Reconciled (click to undo)' : 'Not reconciled (click to mark)',
    'aria-label': 'Reconciled', 'aria-pressed': t.reconciled ? 'true' : 'false', disabled: t.writable ? null : true }, icon('check', 's'));
  b.onclick = async (e) => {
    e.stopPropagation();
    try {
      await api('api/transactions/reconcile', { method: 'POST', json: { ids: [t.id], reconciled: !t.reconciled } });
      t.reconciled = !t.reconciled; b.classList.toggle('on', t.reconciled); b.setAttribute('aria-pressed', String(t.reconciled));
      b.title = t.reconciled ? 'Reconciled (click to undo)' : 'Not reconciled (click to mark)';
    } catch (x) { fail(x); }
  };
  return b;
}
async function showTransactions(page, r) {
  const q = r.q || {};
  const limit = 100, offset = +(q.offset || 0);
  const params = new URLSearchParams({ limit, offset });
  for (const k of ['q', 'account', 'category', 'month', 'flow']) if (q[k]) params.set(k, q[k]);
  if (q.rec) params.set('reconciled', q.rec);
  if (q.rcp) params.set('receipt', q.rcp);
  if (q.amt) params.set('amount', q.amt);
  if (q.hid) params.set('hidden', 'true');
  if (q.tag) params.set('tag', q.tag);
  if (q.rev) params.set('review', q.rev);
  const [d, cats, tags] = await Promise.all([api(`api/transactions?${params}`), categories(), tagList()]);
  const go = (changes) => { const n = { ...q, ...changes }; delete n.offset; for (const k of Object.keys(n)) if (!n[k]) delete n[k]; location.hash = `#/transactions?${new URLSearchParams(n)}`; };
  const search = h('input', { class: 't', type: 'search', placeholder: 'Payee, category, notes, $amount…', value: q.q || '' });
  let tm; search.oninput = () => { clearTimeout(tm); tm = setTimeout(() => go({ q: search.value.trim() }), 350); };
  const amount = h('input', { class: 't amtq', type: 'search', inputmode: 'decimal', placeholder: 'Amount: 280 or 100-200', 'aria-label': 'Amount (exact, or a range like 100-200, >500, <20)',
    title: 'Money out or in alike: 280 exactly, 100-200, >500 or <20', value: q.amt || '' });
  let tma; amount.oninput = () => { clearTimeout(tma); tma = setTimeout(() => go({ amt: amount.value.trim() }), 500); };
  const sel = (k, opts, label) => h('select', { class: 't', 'aria-label': label, onchange: (e) => go({ [k]: e.target.value }) }, opts.map(([v, l]) => h('option', { value: v, selected: String(q[k] || '') === String(v) ? true : null }, l)));
  const months = [['', 'Any time']]; for (let i = 0; i < 24; i++) { const m = shiftMonth(thisMonth(), -i); months.push([m, fmtMonth(m)]); }
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Transactions'), h('span', { class: 'grow' }),
    h('a', { class: 'pillbtn', href: '#/categories', title: 'Add, rename, regroup or delete categories' }, icon('list'), h('span', null, 'Categories')),
    h('a', { class: 'pillbtn', href: '#/rules', title: 'Rules that rename and categorize transactions' }, icon('tune'), h('span', null, 'Rules')),
    S.accounts.some((a) => a.writable && followsTx(a)) ? h('button', { class: 'pillbtn', onclick: () => txDialog() }, icon('add'), h('span', null, 'Transaction')) : null));
  put(page, savedRow(q));
  put(page, h('div', { class: 'filters' }, search, amount,
    sel('account', [['', 'Every account'], ...S.accounts.filter(followsTx).map((a) => [a.id, a.name])], 'Account'),
    sel('category', [['', 'Every category'], ['-', 'Uncategorized'], ...cats.map((c) => [c.category, c.category])], 'Category'),
    sel('month', months, 'Month'), sel('flow', [['', 'In and out'], ['out', 'Money out'], ['in', 'Money in']], 'Direction'),
    sel('rec', [['', 'Reconciled or not'], ['no', 'Not reconciled'], ['yes', 'Reconciled']], 'Reconciled'),
    sel('rcp', [['', 'With or without a receipt'], ['yes', 'With a receipt'], ['no', 'Without a receipt']], 'Receipts'),
    sel('hid', [['', 'Without the hidden'], ['1', 'With the hidden (dimmed)']], 'Hidden transactions'),
    tags.length || q.tag ? sel('tag', [['', 'Any tag'], ...[...new Set([...tags.map((x) => x.tag), q.tag].filter(Boolean))].map((x) => [x, `Tag: ${x}`])], 'Tag') : null,
    sel('rev', [['', 'Looked at or not'], ['yes', 'Needs a look']], 'Needs a look'),
    h('label', { class: 'check', title: 'Show the bank’s own text for each transaction' },
      h('input', { type: 'checkbox', checked: store.get('txbank') === '1' ? true : null, onchange: (e) => { store.set('txbank', e.target.checked ? '1' : '0'); onRoute(); } }), 'At the bank column')));
  const markable = d.items.filter((t) => t.writable && !t.reconciled);
  const markAll = async () => {
    if (!await confirmDialog('Mark them reconciled', `Mark the ${markable.length} transaction${markable.length === 1 ? '' : 's'} shown here as reconciled?`, 'Mark')) return;
    try { const r = await api('api/transactions/reconcile', { method: 'POST', json: { ids: markable.map((t) => t.id), reconciled: true } }); toast(`${r.changed} marked reconciled`); onRoute(); } catch (e) { fail(e); }
  };
  put(page, h('p', { class: 'sumline' }, `${d.total} transaction${d.total === 1 ? '' : 's'} · `, amt(d.sum),
    q.rec === 'no' && markable.length ? [' · ', h('button', { class: 'lnk', onclick: markAll }, `Mark these ${markable.length} reconciled`)] : null));
  const picked = new Set();
  const bar = h('div', { class: 'bulkbar', hidden: true });
  put(page, txList(d.items, true, undefined, { picked, onPick: () => drawBulk(bar, picked, d.items, !!q.rev) }), bar);
  if (d.total > offset + limit || offset) {
    put(page, h('div', { class: 'more' }, offset ? h('a', { class: 'pillbtn', href: `#/transactions?${new URLSearchParams({ ...q, offset: Math.max(0, offset - limit) })}` }, 'Newer') : null,
      d.total > offset + limit ? h('a', { class: 'pillbtn', href: `#/transactions?${new URLSearchParams({ ...q, offset: offset + limit })}` }, 'Older') : null));
  }
}
/** One transaction: its category, payee, notes and hidden (and in a manual account its date and amount); or a new
    one in a manual account. */
async function txDialog(t, account) {
  const isNew = !t;
  const cats = await categories();
  const manualAccts = S.accounts.filter((a) => a.writable && followsTx(a));  // any account that follows its transactions
  t = t || { day: today(), source: 'manual', writable: true, accountId: (account || manualAccts[0] || {}).id };
  const ro = !t.writable;
  const manual = t.source === 'manual';
  const dl = h('datalist', { id: 'catlist' }, cats.map((c) => h('option', { value: c.category })));
  const f = { merchant: inp(t.merchant, { disabled: ro ? true : null }), category: inp(t.category, { list: 'catlist', disabled: ro ? true : null }),
    notes: h('textarea', { class: 't', rows: 2, disabled: ro ? true : null }, t.notes || ''), hidden: h('input', { type: 'checkbox', checked: t.hidden ? true : null, disabled: ro ? true : null }),
    reconciled: h('input', { type: 'checkbox', checked: t.reconciled ? true : null, disabled: ro ? true : null }),
    day: inp(t.day, { type: 'date', disabled: ro || !manual ? true : null }), amount: inp(t.amount, { inputmode: 'decimal', placeholder: '-12.50 out, 100 in', disabled: ro || !manual ? true : null }),
    account: h('select', { class: 't', disabled: !isNew ? true : null }, (isNew ? manualAccts : S.accounts).map((a) => h('option', { value: a.id, selected: a.id === t.accountId ? true : null }, a.name))),
    tags: inp((t.ownTags || []).join(', '), { placeholder: 'trip, reimbursable, tax', disabled: ro ? true : null }) };
  // its tags: the household's own, typed here; the ones Monarch Money sends are shown beside them
  const theirs = (t.tags || []).filter((x) => !(t.ownTags || []).some((o) => o.toLowerCase() === x.toLowerCase()));
  const known = ro ? [] : (await tagList()).filter((x) => x.own && !(t.tags || []).some((y) => y.toLowerCase() === x.tag.toLowerCase())).sort((a, b) => b.count - a.count).slice(0, 8);
  const tagsNow = () => [...new Set(f.tags.value.split(',').map((x) => x.trim().replace(/^#/, '')).filter(Boolean))];
  const tagHints = h('div', { class: 'taghints' }, theirs.length ? h('span', { class: 'muted small' }, 'From Monarch Money: ', theirs.map((x) => h('span', { class: 'tag tg' }, x))) : null,
    known.map((x) => h('button', { class: 'tag tg add', title: 'Add this tag', onclick: () => { if (!tagsNow().some((y) => y.toLowerCase() === x.tag.toLowerCase())) f.tags.value = [...tagsNow(), x.tag].join(', '); } }, icon('add', 'xs'), x.tag)));
  // split over categories: its parts, or the way to split it
  const parts = t.splits || [];
  const sbox = isNew ? null : parts.length
    ? h('div', { class: 'splitbox' }, h('div', { class: 'splithead' }, icon('split', 's'), h('b', null, 'Split over categories'), h('span', { class: 'grow' }),
      !ro ? h('button', { class: 'pillbtn tiny', onclick: () => { closeDialogs(); splitDialog(t); } }, 'Change') : null),
      h('ul', null, parts.map((p) => h('li', null, h('span', null, p.category || 'Uncategorized', p.notes ? h('small', { class: 'muted' }, ` ${p.notes}`) : null), h('span', { class: 'num' }, money(p.amount, t.currency))))),
      Math.abs(parts.reduce((x, p) => x + p.amount, 0) - t.amount) > 0.004 ? h('p', { class: 'muted small warn' }, `The parts no longer add up to ${money(t.amount, t.currency)}: the rest counts under ${t.category || 'no category'}.`) : null)
    : (!ro && t.amount ? h('button', { class: 'lnkbtn', onclick: () => { closeDialogs(); splitDialog(t); } }, icon('split', 'xs'), 'Split over categories') : null);
  const xbox = isNew ? null : h('div', { class: 'xferbox' });
  let moved = false;
  if (xbox) drawTransfer(xbox, t, () => { moved = true; });
  const rbox = isNew ? null : h('div', { class: 'rcbox' });
  if (rbox) drawReceipts(rbox, t, () => { moved = true; });
  const lbox = isNew ? null : linkedTx(t);
  const body = h('div', null, dl, h('div', { class: 'grid' }, fld('Payee', f.merchant, true), fld('Amount', f.amount), fld('Date', f.day), fld('Category', f.category), fld('Account', f.account), fld('Notes', f.notes, true), fld('Tags', f.tags, true)), tagHints,
    h('div', { class: 'chiprow', style: { marginTop: '10px', gap: '18px' } }, h('label', { class: 'check' }, f.hidden, 'Hidden: left out of the sums'),
      !isNew ? h('label', { class: 'check' }, f.reconciled, 'Reconciled with the statement') : null), sbox, xbox, rbox, lbox, isNew ? null : historyBox(t),
    t.description && t.description !== t.merchant ? h('p', { class: 'muted small' }, 'At the bank: ', t.description) : null,
    t.source === 'monarch' ? h('p', { class: 'muted small' }, 'From Monarch Money. A change here stays here: Monarch itself is not changed.') : null,
    isNew ? h('p', { class: 'muted small' }, 'Added here, by hand. In an account from Monarch Money it stays beside Monarch’s own transactions, and the balance stays Monarch’s.') : null);
  const btns = ro ? [{ label: 'Close', value: false }] : [
    !isNew && manual ? { label: 'Delete', value: 'delete', danger: true } : null,
    !isNew && may('household') ? { label: 'Make a rule', value: 'rule' } : null,
    !isNew ? { label: t.recurring ? 'Recurring…' : 'Make recurring', value: 'recur' } : null, { label: 'Cancel', value: false }, { label: isNew ? 'Add' : 'Save', value: true, primary: true }].filter(Boolean);
  const ok = await dialog(isNew ? 'Add a transaction' : (t.merchant || 'Transaction'), body, btns, 'wide');
  if (ok === 'delete') { try { await api(`api/transactions/${t.id}`, { method: 'DELETE' }); toast('Deleted'); onRoute(); } catch (e) { fail(e); } return; }
  if (ok === 'recur') {  // the recurring one it is, or one to add from it (how often and the amount from those like it)
    try {
      const d = await api(`api/transactions/${t.id}/recurring`);
      S.freqs = d.frequencies;
      if (d.item) recurringDialog(d.item);
      else if (!d.writable) toast('Only editors add the household’s recurring transactions');
      else recurringDialog(null, d.suggestion);
    } catch (e) { fail(e); }
    return;
  }
  if (ok === 'rule') {  // the same payee next time: what was typed here, for every transaction like this one
    const name = t.merchant || t.description || '';
    ruleDialog(null, { pattern: name, field: t.merchant ? 'merchant' : 'description',
      setMerchant: f.merchant.value.trim() !== name ? f.merchant.value.trim() : null, setCategory: f.category.value.trim() || t.category });
    return;
  }
  if (!ok) { if (moved) onRoute(); return; }
  const b = { merchant: f.merchant.value, category: f.category.value, notes: f.notes.value, hidden: f.hidden.checked };
  if (!isNew && f.reconciled.checked !== !!t.reconciled) b.reconciled = f.reconciled.checked;
  if (manual) Object.assign(b, { day: f.day.value, amount: f.amount.value });
  const low = (xs) => xs.map((x) => x.toLowerCase()).sort().join('|');
  if (isNew ? tagsNow().length : low(tagsNow()) !== low(t.ownTags || [])) { b.tags = tagsNow(); S.tags = null; }
  try {
    await api(isNew ? `api/accounts/${f.account.value}/transactions` : `api/transactions/${t.id}`, { method: isNew ? 'POST' : 'PATCH', json: b });
    S.cats = []; toast(isNew ? 'Added' : 'Saved'); if (route().view === 'review') await refreshSummary(); onRoute();
  } catch (e) { fail(e); }
}

/** A picture from a phone's camera is far larger than a receipt needs: one over a megabyte is made smaller (its
    long side 2000 points, a JPEG) before it is sent; anything else, and a picture the browser cannot draw, goes as it is. */
async function shrunk(f) {
  if (!/^image\/(jpeg|png|webp)$/.test(f.type) || f.size < 1200000) return { body: f, name: f.name };
  try {
    const bmp = await createImageBitmap(f, { imageOrientation: 'from-image' });
    const k = Math.min(1, 2000 / Math.max(bmp.width, bmp.height));
    const c = h('canvas', { width: Math.round(bmp.width * k), height: Math.round(bmp.height * k) });
    const g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height); g.drawImage(bmp, 0, 0, c.width, c.height);
    const blob = await new Promise((done) => c.toBlob(done, 'image/jpeg', 0.82));
    if (blob && blob.size < f.size) return { body: blob, name: f.name.replace(/\.[^.]*$/, '') + '.jpg' };
  } catch { /* sent as it is */ }
  return { body: f, name: f.name };
}
const fmtSize = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
/** In a transaction's dialog: its receipts (pictures and PDFs), each opened with a click; whoever may change the
    transaction adds one (picked, taken with the phone, or dropped here) and removes one. */
function drawReceipts(box, t, changed) {
  const list = t.receipts || [];
  const can = !!t.writable;
  const send = async (files) => {
    let n = 0;
    box.classList.add('busy');
    for (const f of files) {
      try {
        const { body, name } = await shrunk(f);
        const r = await api(`api/transactions/${t.id}/receipts?name=${encodeURIComponent(name)}`, { method: 'POST', body, headers: { 'Content-Type': 'application/octet-stream' } });
        t.receipts = [...(t.receipts || []), r]; n += 1;
      } catch (e) { fail(e); }
    }
    box.classList.remove('busy');
    if (n) { changed(); toast(n === 1 ? 'Receipt kept' : `${n} receipts kept`); }
    drawReceipts(box, t, changed);
  };
  const pick = h('input', { type: 'file', accept: 'image/*,application/pdf', multiple: true, hidden: true, onchange: (e) => { if (e.target.files.length) send([...e.target.files]); } });
  const remove = async (r) => {
    if (!await confirmDialog('Remove the receipt', `Remove ${r.name}? It cannot be brought back.`, 'Remove', true)) return;
    try { await api(`api/receipts/${r.id}`, { method: 'DELETE' }); t.receipts = t.receipts.filter((x) => x.id !== r.id); changed(); drawReceipts(box, t, changed); } catch (e) { fail(e); }
  };
  if (!list.length && !can) { box.replaceChildren(); return; }
  box.replaceChildren(h('div', { class: 'splithead' }, icon('attach', 's'), h('b', null, list.length > 1 ? 'Receipts' : 'Receipt'), h('span', { class: 'grow' }),
    can ? h('button', { class: 'pillbtn tiny', title: 'A picture or a PDF, up to 20 MB', onclick: () => pick.click() }, icon('add', 'xs'), 'Add') : null, pick),
    list.length ? h('ul', { class: 'rcps' }, list.map((r) => h('li', null,
      h('a', { class: 'rcpfile', href: r.url, target: '_blank', rel: 'noopener', title: `Open ${r.name}` },
        /^image\/(jpeg|png|gif|webp)$/.test(r.mime) ? h('img', { src: r.url, alt: '', loading: 'lazy' }) : h('span', { class: 'rcpic' }, icon(r.mime === 'application/pdf' ? 'receipt' : 'attach')),
        h('span', { class: 'rcpname' }, h('b', null, r.name), h('small', { class: 'muted' }, fmtSize(r.size)))),
      can ? h('button', { class: 'iconbtn', title: 'Remove this receipt', 'aria-label': `Remove ${r.name}`, onclick: () => remove(r) }, icon('delete', 's')) : null)))
      : h('p', { class: 'muted small' }, 'None kept yet: add a picture of the receipt or the PDF of the invoice, or drop it here.'));
  if (can && !box.ondragover) {
    box.ondragover = (e) => { if ([...(e.dataTransfer?.types || [])].includes('Files')) { e.preventDefault(); box.classList.add('drop'); } };
    box.ondragleave = () => box.classList.remove('drop');
    box.ondrop = (e) => { e.preventDefault(); box.classList.remove('drop'); if (e.dataTransfer.files.length) send([...e.dataTransfer.files]); };
  }
}
/** In a transaction's dialog: what it is linked to in the suite (the thing it paid for in ioThings, with its
    warranty; a note, a contact…), and the picker that links another, opening on the things. */
function linkedTx(t) {
  const el = h('div', { class: 'linked' });
  (async () => {
    try { linkUi = linkUi || await import(new URL('api/related/ui.js', document.baseURI).href); } catch { return; }
    linkUi.mount(el, { kind: 'transaction', id: t.id, toast, first: 'item', canEdit: !!t.writable, onOpen: closeDialogs,
      empty: 'Nothing linked yet. Link the thing this paid for, so its price and warranty sit together; or a note, a contact…' });
  })();
  return el;
}

/** Split a transaction over categories: its parts, each with its share, a category and a note; what is left to
    give out is shown as the amounts are typed, and it saves once nothing is. */
async function splitDialog(t) {
  const cats = await categories();
  const total = Math.abs(t.amount);
  const cents = (v) => Math.round((parseFloat(String(v).replace(/[,$\s]/g, '')) || 0) * 100);
  const list = h('div', { class: 'splitrows' });
  const left = h('p', { class: 'splitleft' });
  const rows = [];
  const update = () => {
    const rest = Math.round(total * 100) - rows.reduce((x, r) => x + Math.abs(cents(r.amount.value)), 0);
    left.textContent = rest === 0 ? 'Everything is given out.' : rest > 0 ? `${money(rest / 100, t.currency)} left to give out` : `${money(-rest / 100, t.currency)} too much`;
    left.classList.toggle('warn', rest !== 0);
    return rest;
  };
  const addRow = (p = {}) => {
    const r = { amount: inp(p.amount != null ? Math.abs(p.amount).toFixed(2) : '', { inputmode: 'decimal', placeholder: '0.00', 'aria-label': 'Amount' }),
      category: inp(p.category, { list: 'splitcats', placeholder: 'Category', 'aria-label': 'Category' }), notes: inp(p.notes, { placeholder: 'Note', maxlength: 255, 'aria-label': 'Note' }) };
    r.el = h('div', { class: 'splitrow' }, r.amount, r.category, r.notes,
      h('button', { class: 'iconbtn', title: 'Remove this part', 'aria-label': 'Remove this part', onclick: () => { rows.splice(rows.indexOf(r), 1); r.el.remove(); update(); } }, icon('delete', 's')));
    r.amount.addEventListener('input', update);
    // the last part takes what is left when its amount is entered empty
    r.amount.addEventListener('focus', () => { if (!r.amount.value) { const rest = update(); if (rest > 0) { r.amount.value = (rest / 100).toFixed(2); r.amount.select(); update(); } } });
    rows.push(r); list.append(r.el);
  };
  if (t.splits && t.splits.length) t.splits.forEach(addRow);
  else { addRow({ amount: total, category: t.category }); addRow(); }
  update();
  const body = h('div', null, h('datalist', { id: 'splitcats' }, cats.map((c) => h('option', { value: c.category }))),
    h('p', { class: 'muted small' }, `${t.merchant || t.description || 'This transaction'}, ${fmtDay(t.day, true)}: ${money(t.amount, t.currency)}. The spending by category counts the parts in its place.`),
    list, h('div', { class: 'splitfoot' }, h('button', { class: 'pillbtn tiny', onclick: () => { addRow(); update(); } }, icon('add', 'xs'), 'Part'), left));
  const had = t.splits && t.splits.length;
  const ok = await dialog('Split over categories', body, [had ? { label: 'Make it whole', value: 'whole', danger: true } : null, { label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }].filter(Boolean), 'wide');
  if (!ok) return;
  const items = ok === 'whole' ? [] : rows.filter((r) => cents(r.amount.value)).map((r) => ({ amount: Math.abs(cents(r.amount.value)) / 100, category: r.category.value.trim() || null, notes: r.notes.value.trim() || null }));
  try {
    const n = await api(`api/transactions/${t.id}/splits`, { method: 'PUT', json: { items } });
    S.cats = []; toast(n.splits.length ? 'Split' : 'Whole again'); onRoute();
  } catch (e) { fail(e); Object.assign(t, { splits: ok === 'whole' ? t.splits : items.map((p) => ({ ...p, amount: (t.amount < 0 ? -1 : 1) * p.amount })) }); splitDialog(t); }
}

/** In a transaction's dialog: the other half of its transfer (with Unlink), or the transactions that could be it
    (the same amount the other way in another account, within two weeks), each with Link. */
async function drawTransfer(box, t, changed) {
  let d;
  try { d = await api(`api/transactions/${t.id}/transfer`); } catch { return; }
  const w = t.writable;
  const act = async (fn) => { try { await fn(); changed(); drawTransfer(box, t, changed); } catch (e) { fail(e); } };
  if (d.other) {
    const o = d.other;
    fill(box, h('h3', { class: 'sub' }, icon('link', 's'), 'Transfer'),
      h('div', { class: 'xferline' }, h('span', { class: 'grow' }, `${t.amount < 0 ? 'To' : 'From'} `, h('b', null, o.account || 'an account you do not see'), ` on ${fmtDay(o.day, true)}`,
        h('small', { class: 'muted' }, o.how === 'hand' ? ' · linked by hand' : o.how === 'rule' ? ' · linked by a transfer rule' : ' · found by ioMoney')),
        w ? h('button', { class: 'pillbtn', onclick: () => act(() => api(`api/transactions/${t.id}/transfer`, { method: 'DELETE' })) }, 'Unlink') : null),
      h('p', { class: 'muted small' }, 'A transfer between your own accounts is left out of the spending and the cash flow.'));
    return;
  }
  if (!d.candidates.length || !w) { fill(box); return; }
  fill(box, h('h3', { class: 'sub' }, icon('link', 's'), 'Is it a transfer?'),
    h('p', { class: 'muted small' }, 'These are the same amount the other way, in another account. Link the one that is the other half:'),
    h('ul', { class: 'rows flat' }, d.candidates.map((c) => h('li', null, h('div', { class: 'r' }, h('span', { class: 'day' }, fmtDay(c.day)),
      h('span', { class: 'main' }, h('b', null, c.account), h('small', null, [c.merchant || c.description, c.category].filter(Boolean).join(' · '))),
      h('span', { class: 'end' }, amt(c.amount, c.currency)),
      h('button', { class: 'pillbtn', onclick: () => act(() => api(`api/transactions/${t.id}/transfer`, { method: 'PUT', json: { with: c.id } })) }, 'Link'))))));
}

// ------------------------------------------------------------------ rules: rename and categorize as they come in
const RULE_FIELD = { either: 'The payee or the bank’s text', merchant: 'The payee', description: 'The bank’s text' };
const RULE_HOW = { contains: 'contains', is: 'is', starts: 'starts with' };
function ruleWhen(x) {
  const bits = [`${RULE_FIELD[x.field]} ${RULE_HOW[x.how]} “${x.pattern}”`];
  if (x.account) bits.push(`in ${x.account}`);
  if (x.flow) bits.push(x.flow === 'out' ? 'money out' : 'money in');
  if (x.amountMin != null && x.amountMax != null) bits.push(`${money(x.amountMin)} to ${money(x.amountMax)}`);
  else if (x.amountMin != null) bits.push(`${money(x.amountMin)} or more`);
  else if (x.amountMax != null) bits.push(`up to ${money(x.amountMax)}`);
  return bits.join(' · ');
}
function ruleThen(x) {
  return [x.setMerchant ? `Rename to “${x.setMerchant}”` : null, x.setCategory ? `Category ${x.setCategory}` : null,
    x.setHidden === true ? 'Hide it' : x.setHidden === false ? 'Show it' : null].filter(Boolean).join(' · ');
}
async function showRules(page) {
  const d = await api('api/rules');
  const items = d.items || [];
  const w = d.writable;
  const apply = async () => { try { const r = await api('api/rules/apply', { method: 'POST' }); toast(`${r.changed} transaction${r.changed === 1 ? '' : 's'} changed`); } catch (e) { fail(e); } };
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Rules'), h('span', { class: 'grow' }),
    w && items.length ? h('button', { class: 'pillbtn', onclick: apply, title: 'Run every rule over the transactions there are now' }, icon('sync'), h('span', null, 'Apply now')) : null,
    w ? h('button', { class: 'pillbtn', onclick: () => ruleDialog() }, icon('add'), h('span', null, 'Rule')) : null));
  put(page, h('p', { class: 'muted' }, 'Rules rename the payee, set the category or hide a transaction when it comes in from Monarch Money or is added here. ',
    'They are tried from the top: for each of the three, the first rule that matches wins. A transaction you changed by hand stays as you left it.'));
  if (!items.length) {
    put(page, h('div', { class: 'empty' }, icon('tune'), h('p', null, 'No rules yet.'),
      h('p', { class: 'muted' }, w ? 'Add one here, or open a transaction and choose Make a rule.' : 'Editors add them.')));
  }
  const move = async (i, by) => {
    const ids = items.map((x) => x.id); const [x] = ids.splice(i, 1); ids.splice(i + by, 0, x);
    try { await api('api/rules/order', { method: 'PUT', json: { ids } }); onRoute(); } catch (e) { fail(e); }
  };
  const sug = h('div');
  put(page, sug);
  put(page, h('ul', { class: 'rows rules' }, items.map((x, i) => h('li', { class: x.enabled ? null : 'off', 'data-rule': x.id }, h('div', { class: 'r' },
    h('span', { class: 'n' }, i + 1),
    h('span', { class: 'main' }, h('b', null, ruleThen(x)), h('small', null, ruleWhen(x), h('span', { class: 'upk' }))),
    !x.enabled ? h('span', { class: 'tag' }, 'Off') : null,
    w ? h('span', { class: 'end acts' },
      h('button', { class: 'iconbtn', title: 'Tried earlier', disabled: i === 0 ? true : null, onclick: () => move(i, -1) }, icon('prev', 's up')),
      h('button', { class: 'iconbtn', title: 'Tried later', disabled: i === items.length - 1 ? true : null, onclick: () => move(i, 1) }, icon('next', 's down')),
      h('button', { class: 'iconbtn', title: 'Edit', onclick: () => ruleDialog(x) }, icon('edit', 's'))) : null)))));
  api('api/rules/upkeep').then((u) => drawUpkeep(page, sug, u)).catch(() => {});  // what each rule does: counted apart, it takes a moment
  await drawTransferRules(page);
}
/** The transfer rules: in this account, a payee like this is a transfer with that account. ioMoney learns one each
    time it finds a transfer by itself; editors add, change and delete them. */
async function drawTransferRules(page) {
  const d = await api('api/transfer-rules');
  const items = d.items || [];
  const w = d.writable;
  const linkNow = () => transferMaintenance();
  put(page, h('div', { class: 'pagehead', style: { marginTop: '28px' } }, h('h2', { class: 'h1ish' }, icon('link'), 'Transfers'), h('span', { class: 'grow' }),
    w ? h('button', { class: 'pillbtn', onclick: linkNow, title: 'Look for transfers among every transaction not linked yet' }, icon('sync'), h('span', null, 'Link transfers now')) : null,
    w ? h('button', { class: 'pillbtn', onclick: () => transferRuleDialog() }, icon('add'), h('span', null, 'Transfer rule')) : null));
  put(page, h('p', { class: 'muted' }, 'Money that leaves one of your accounts and arrives in another (to savings, a card’s payment, a loan’s payment) is one transfer, linked and left out of the spending. ',
    'ioMoney links the two halves when the amounts match, the days are close and the payee or category says it is a transfer; each one it finds teaches it a rule, so the next is found even a few days later. ',
    'Open a transaction to link or unlink it by hand.'));
  if (!items.length) { put(page, h('p', { class: 'muted small' }, 'No transfer rules yet.')); return; }
  put(page, h('ul', { class: 'rows rules' }, items.map((x) => h('li', null, h('div', { class: 'r' },
    h('span', { class: 'main' }, h('b', null, `${x.account || '?'} ⇄ ${x.other || '?'}`),
      h('small', null, `In ${x.account || '?'}, the payee “${x.pattern}”, up to ${x.days} day${x.days === 1 ? '' : 's'} apart`)),
    x.source === 'learned' ? h('span', { class: 'tag', title: 'Learned from a transfer ioMoney found' }, 'Learned') : null,
    w ? h('span', { class: 'end acts' }, h('button', { class: 'iconbtn', title: 'Edit', onclick: () => transferRuleDialog(x) }, icon('edit', 's'))) : null)))));
}
/** The maintenance: go through every transaction and link the transfers (card, bank and loan payments), then show
    what still looks like one but was not linked on its own page, to check. */
function transferMaintenance() { location.hash = '#/transfers?run=1'; }
const WHY = [['', 'Any reason'], ['as likely', 'As likely as another'], ['nothing says', 'Nothing says it is a transfer'], ['days apart', 'Too many days apart']];
/** Transfers to check: the same amount out of one account and into another within two weeks, not linked: each with
    both sides in full, why it was not linked, and Link or Not a transfer. ?run=1 first links what it can. */
async function showTransfers(page, r) {
  let ran = null;
  if (r.q.run) {
    toast('Going through every transaction…');
    ran = await api('api/transfers/link', { method: 'POST' });
    history.replaceState(null, '', '#/transfers');
  }
  const items = ran ? ran.possible : ((await api('api/transfers/possible')).items || []);
  const f = { why: store.get('tfWhy') || '', acct: store.get('tfAcct') || '', q: '', sort: store.get('tfSort') || 'day' };
  put(page, h('div', { class: 'pagehead' }, h('a', { class: 'iconbtn', href: '#/rules', title: 'Rules', 'aria-label': 'Rules' }, icon('prev')),
    h('h1', null, 'Transfers to check'), h('span', { class: 'grow' }),
    may('write') ? h('button', { class: 'pillbtn', onclick: () => { location.hash = '#/transfers?run=1'; }, title: 'Go through every transaction not linked yet' }, icon('sync'), h('span', null, 'Link transfers now')) : null));
  if (ran) put(page, h('p', { class: 'banner ok' }, icon('check', 's'), ` ${ran.linked} transfer${ran.linked === 1 ? '' : 's'} linked`, ran.learned ? `, ${ran.learned} transfer rule${ran.learned === 1 ? '' : 's'} learned` : '', '.'));
  put(page, h('p', { class: 'muted' }, 'The same amount out of one account and into another, within two weeks, that ioMoney did not link by itself. ',
    'Link the ones that are one transfer; Not a transfer takes a pair off this list for good.'));
  if (!items.length) { put(page, h('div', { class: 'empty' }, icon('link'), h('p', null, 'Nothing left to check.'))); return; }
  const accts = [...new Map(items.flatMap((p) => [p.out, p.in]).filter((t) => t.accountId).map((t) => [t.accountId, t.account])).entries()].sort((a, b) => a[1].localeCompare(b[1]));
  const sel = (opts, v, on) => { const e = h('select', { class: 't' }, opts.map(([k, l]) => h('option', { value: k, selected: k === v ? true : null }, l))); e.onchange = () => on(e.value); return e; };
  const count = h('span', { class: 'muted small' });
  const list = h('div', { class: 'tfx' });
  const gone = new Set();  // transactions linked or set aside here: their other pairs leave the list
  const side = (t) => h('div', { class: 'side' },
    h('div', { class: 'acct' }, t.accountId ? h('a', { class: 'lnk', href: `#/account/${t.accountId}` }, t.account) : (t.account || 'Someone’s private account')),
    h('div', { class: 'meta' }, fmtDay(t.day, true), t.category ? h('span', { class: 'tag' }, t.category) : null),
    h('button', { class: 'payee', title: 'Open the transaction', onclick: () => txDialog(t) }, t.merchant || t.description || '—'),
    t.description && t.description !== t.merchant ? h('div', { class: 'bank' }, t.description) : null);
  const draw = () => {
    const q = f.q.trim().toLowerCase();
    let shown = items.filter((p) => !gone.has(p.out.id) && !gone.has(p.in.id) && (!f.why || p.why.includes(f.why))
      && (!f.acct || String(p.out.accountId) === f.acct || String(p.in.accountId) === f.acct)
      && (!q || [p.out, p.in].some((t) => [t.merchant, t.description, t.account, t.category].some((x) => (x || '').toLowerCase().includes(q))) || String(Math.abs(p.out.amount)).includes(q)));
    // pairs that share a transaction are one choice (a tie): kept together, the choice said once
    const root = new Map();
    const find = (x) => { while (root.get(x) !== x) x = root.get(x); return x; };
    for (const p of shown) {
      for (const k of [`o${p.out.id}`, `i${p.in.id}`]) if (!root.has(k)) root.set(k, k);
      root.set(find(`o${p.out.id}`), find(`i${p.in.id}`));
    }
    const groups = new Map();
    for (const p of shown) { const g = find(`o${p.out.id}`); if (!groups.has(g)) groups.set(g, []); groups.get(g).push(p); }
    const day = (p) => (p.out.day > p.in.day ? p.out.day : p.in.day);
    const gday = (g) => g.map(day).sort().pop();
    const gamt = (g) => Math.abs(g[0].out.amount);
    const sorted = [...groups.values()].sort(f.sort === 'amount' ? (a, b) => gamt(b) - gamt(a) || gday(b).localeCompare(gday(a))
      : (a, b) => gday(b).localeCompare(gday(a)) || gamt(b) - gamt(a));
    count.textContent = `${shown.length} of ${items.length - [...items].filter((p) => gone.has(p.out.id) || gone.has(p.in.id)).length}`;
    const same = (a, b) => a.accountId === b.accountId && a.day === b.day && a.amount === b.amount && (a.merchant || '') === (b.merchant || '') && (a.description || '') === (b.description || '');
    const twins = (g) => {  // the same transaction twice on one side: a duplicate from the bank or Monarch Money
      const seen = (side) => [...new Map(g.map((p) => [p[side].id, p[side]])).values()];
      return ['out', 'in'].map((sd) => seen(sd)).find((ts) => ts.length > 1 && ts.every((t) => same(t, ts[0])));
    };
    const tieNote = (g) => {
      const dup = twins(g);
      if (dup) return h('div', { class: 'tfnote' }, icon('warning', 'xs'), ` ${dup.length} identical transactions in ${dup[0].account || 'one account'} on ${fmtDay(dup[0].day, true)} (“${dup[0].merchant || dup[0].description || ''}”): most likely a duplicate from the bank or Monarch Money. Link one; then open the other to check it.`);
      return h('div', { class: 'tfnote' }, `${g.length} ways to pair these, each as likely: link the right one.`);
    };
    const rowOf = (p) => {
      const apart = Math.round(Math.abs(new Date(p.out.day) - new Date(p.in.day)) / 864e5);
      const can = p.out.writable && p.in.writable;
      const link = h('button', { class: 'pillbtn primary' }, icon('link', 'xs'), 'Link');
      const not = h('button', { class: 'pillbtn' }, 'Not a transfer');
      link.onclick = async () => { try { await api(`api/transactions/${p.out.id}/transfer`, { method: 'PUT', json: { with: p.in.id } }); gone.add(p.out.id); gone.add(p.in.id); toast('Linked'); draw(); } catch (e) { fail(e); } };
      not.onclick = async () => { try { await api('api/transfers/not', { method: 'POST', json: { outId: p.out.id, inId: p.in.id } }); items.splice(items.indexOf(p), 1); draw(); } catch (e) { fail(e); } };
      return h('div', { class: 'tfr' }, h('div', { class: 'amt num' }, money(Math.abs(p.out.amount), p.out.currency)),
        side(p.out), side(p.in), h('div', { class: 'apart' }, apart === 0 ? 'Same day' : `${apart} day${apart === 1 ? '' : 's'}`),
        h('div', { class: 'why' }, p.why), h('div', { class: 'acts' }, can ? [link, not] : null));
    };
    list.replaceChildren(h('div', { class: 'tfh' }, h('span', null, 'Amount'), h('span', null, 'Out of'), h('span', null, 'Into'), h('span', null, 'Apart'), h('span', null, 'Not linked because'), h('span')),
      ...sorted.map((g) => (g.length > 1 ? h('div', { class: 'tfg' }, tieNote(g), g.map(rowOf)) : rowOf(g[0]))));
  };
  const search = inp('', { type: 'search', placeholder: 'Payee, account, amount…' });
  search.oninput = () => { f.q = search.value; draw(); };
  put(page, h('div', { class: 'filters tff' }, search,
    sel([['', 'Every account'], ...accts.map(([id, n]) => [String(id), n])], f.acct, (v) => { f.acct = v; store.set('tfAcct', v); draw(); }),
    sel(WHY, f.why, (v) => { f.why = v; store.set('tfWhy', v); draw(); }),
    sel([['day', 'Newest first'], ['amount', 'Largest first']], f.sort, (v) => { f.sort = v; store.set('tfSort', v); draw(); }), count), list);
  draw();
}
async function transferRuleDialog(x) {
  const isNew = !x;
  x = x || { days: 5 };
  const acctSel = (v) => h('select', { class: 't' }, h('option', { value: '' }, 'Choose…'), S.accounts.filter(followsTx).map((a) => h('option', { value: a.id, selected: a.id === v ? true : null }, a.name)));
  const f = { account: acctSel(x.accountId), pattern: inp(x.pattern, { placeholder: 'ally bank, payment thank you' }), other: acctSel(x.otherId),
    days: inp(x.days, { type: 'number', min: 0, max: 31, style: { width: '90px' } }) };
  const body = h('div', null, h('div', { class: 'grid' }, fld('In the account', f.account), fld('A payee or bank’s text with', f.pattern),
    fld('Is a transfer with', f.other), fld('At most this many days apart', f.days)));
  const btns = [!isNew ? { label: 'Delete', value: 'delete', danger: true } : null, { label: 'Cancel', value: false }, { label: isNew ? 'Add' : 'Save', value: true, primary: true }].filter(Boolean);
  const ok = await dialog(isNew ? 'Add a transfer rule' : 'Edit the transfer rule', body, btns, 'wide');
  if (ok === 'delete') { try { await api(`api/transfer-rules/${x.id}`, { method: 'DELETE' }); toast('Deleted'); onRoute(); } catch (e) { fail(e); } return; }
  if (!ok) return;
  const b = { accountId: +f.account.value || null, pattern: f.pattern.value, otherId: +f.other.value || null, days: f.days.value };
  try {
    const r = await api(isNew ? 'api/transfer-rules' : `api/transfer-rules/${x.id}`, { method: isNew ? 'POST' : 'PATCH', json: b });
    toast(`${isNew ? 'Added' : 'Saved'}${r.linked ? `: ${r.linked} transfer${r.linked === 1 ? '' : 's'} linked` : ''}`); onRoute();
  } catch (e) { fail(e); }
}
/** Add a rule, or change one. As it is typed, the transactions it matches are counted, with the newest few. */
async function ruleDialog(x, preset) {
  const isNew = !x;
  x = x || { field: 'either', how: 'contains', enabled: true, ...(preset || {}) };
  const cats = await categories();
  const sel = (opts, v) => h('select', { class: 't' }, Object.entries(opts).map(([k, l]) => h('option', { value: k, selected: k === (v || '') ? true : null }, l)));
  const f = {
    field: sel(RULE_FIELD, x.field), how: sel(RULE_HOW, x.how), pattern: inp(x.pattern, { placeholder: 'AMZN, Shell, PAYPAL *NETFLIX' }),
    account: h('select', { class: 't' }, h('option', { value: '' }, 'Any account'), S.accounts.filter(followsTx).map((a) => h('option', { value: a.id, selected: a.id === x.accountId ? true : null }, a.name))),
    flow: sel({ '': 'In or out', out: 'Money out', in: 'Money in' }, x.flow), amountMin: inp(x.amountMin, { inputmode: 'decimal', placeholder: 'Any' }),
    amountMax: inp(x.amountMax, { inputmode: 'decimal', placeholder: 'Any' }),
    setMerchant: inp(x.setMerchant, { placeholder: 'Leave the payee as it is' }), setCategory: inp(x.setCategory, { list: 'rulecats', placeholder: 'Leave the category as it is' }),
    setHidden: sel({ '': 'Leave it as it is', true: 'Hide it (left out of the sums)', false: 'Show it' }, x.setHidden == null ? '' : String(x.setHidden)),
    enabled: h('input', { type: 'checkbox', checked: x.enabled ? true : null }), apply: h('input', { type: 'checkbox', checked: true }),
  };
  const found = h('div', { class: 'rulefound muted small' });
  const when = () => ({ field: f.field.value, how: f.how.value, pattern: f.pattern.value, accountId: f.account.value ? +f.account.value : null,
    flow: f.flow.value || null, amountMin: f.amountMin.value || null, amountMax: f.amountMax.value || null });
  let tm, seq = 0;
  const look = () => {
    clearTimeout(tm);
    tm = setTimeout(async () => {
      const n = ++seq;
      if (!f.pattern.value.trim()) { found.replaceChildren(); return; }
      try {
        const r = await api('api/rules/test', { method: 'POST', json: when() });
        if (n !== seq) return;
        found.replaceChildren(h('p', null, r.count ? `Matches ${r.count} transaction${r.count === 1 ? '' : 's'}${r.edited ? ` (${r.edited} changed by hand stay as they are)` : ''}:` : 'Matches no transaction yet.'),
          r.sample.length ? h('ul', { class: 'rows flat' }, r.sample.map((t) => h('li', null, h('div', { class: 'r' }, h('span', { class: 'day' }, fmtDay(t.day)),
            h('span', { class: 'main' }, h('b', null, t.merchant || t.description || '(no payee)'), h('small', null, [t.description !== t.merchant ? t.description : null, t.category, t.account].filter(Boolean).join(' · '))),
            h('span', { class: 'end' }, amt(t.amount, t.currency)))))) : null);
      } catch (e) { if (n === seq) found.replaceChildren(h('p', { class: 'warn' }, e.message || String(e))); }
    }, 300);
  };
  for (const k of ['field', 'how', 'pattern', 'account', 'flow', 'amountMin', 'amountMax']) f[k].addEventListener(f[k].tagName === 'SELECT' ? 'change' : 'input', look);
  look();
  const body = h('div', null, h('datalist', { id: 'rulecats' }, cats.map((c) => h('option', { value: c.category }))),
    h('h3', { class: 'sub' }, 'When'),
    h('div', { class: 'grid' }, fld('Look in', f.field), fld('Match', f.how), fld('The words', f.pattern, true),
      fld('Account', f.account), fld('Direction', f.flow), fld('From (amount)', f.amountMin), fld('Up to', f.amountMax)),
    found,
    h('h3', { class: 'sub' }, 'Then'),
    h('div', { class: 'grid' }, fld('Rename the payee to', f.setMerchant, true), fld('Set the category to', f.setCategory), fld('Hidden', f.setHidden)),
    h('div', { class: 'chiprow', style: { marginTop: '12px', gap: '16px' } }, h('label', { class: 'check' }, f.enabled, 'On'),
      h('label', { class: 'check' }, f.apply, 'Also change the transactions there are now')));
  const btns = [!isNew ? { label: 'Delete', value: 'delete', danger: true } : null, { label: 'Cancel', value: false }, { label: isNew ? 'Add' : 'Save', value: true, primary: true }].filter(Boolean);
  const ok = await dialog(isNew ? 'Add a rule' : 'Edit the rule', body, btns, 'wide');
  clearTimeout(tm); seq++;
  if (ok === 'delete') {
    if (!await confirmDialog('Delete the rule', 'The transactions it changed keep their payee and category until Monarch Money sends them again.', 'Delete', true)) return;
    try { await api(`api/rules/${x.id}`, { method: 'DELETE' }); toast('Deleted'); onRoute(); } catch (e) { fail(e); }
    return;
  }
  if (!ok) return;
  const b = { ...when(), setMerchant: f.setMerchant.value, setCategory: f.setCategory.value,
    setHidden: f.setHidden.value === '' ? null : f.setHidden.value === 'true', enabled: f.enabled.checked, apply: f.apply.checked };
  try {
    const r = await api(isNew ? 'api/rules' : `api/rules/${x.id}`, { method: isNew ? 'POST' : 'PATCH', json: b });
    S.cats = [];
    toast(r.changed != null ? `${isNew ? 'Added' : 'Saved'}: ${r.changed} transaction${r.changed === 1 ? '' : 's'} changed` : (isNew ? 'Added' : 'Saved'));
    if (route().view === 'rules' || route().view === 'transactions' || route().view === 'account') onRoute(); else location.hash = '#/rules';
  } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ putting the data in order
/** Every tag the transactions have (Monarch's and the household's own), kept until one changes. */
async function tagList() {
  if (!S.tags) { try { S.tags = (await api('api/tags')).items || []; } catch { S.tags = []; } }
  return S.tags;
}
const plural = (n, one, many) => `${n.toLocaleString()} ${n === 1 ? one : (many || `${one}s`)}`;
const agoSec = (s) => (s == null ? '' : s < 90 ? 'just now' : s < 5400 ? `${Math.round(s / 60)} minutes ago` : s < 129600 ? `${Math.round(s / 3600)} hours ago` : `${Math.round(s / 86400)} days ago`);
const tidyBack = () => h('a', { class: 'iconbtn', href: '#/tidy', title: 'Tidy up', 'aria-label': 'Tidy up' }, icon('prev'));

/** Above the filters: this person's saved searches (the one shown now marked, with the way to forget it), and "Save
    this search" when filters are set that no saved search has. */
function savedRow(q) {
  const now = new URLSearchParams(Object.entries(q).filter(([k, v]) => k !== 'offset' && v));
  const has = [...now].length > 0;
  if (!S.searches.length && !has) return null;
  const mine = S.searches.find((x) => sameSearch(x.query, now));
  const save = async () => {
    const name = inp('', { maxlength: 64, placeholder: 'Reimbursable, Card over $500…', list: 'savednames' });
    const ok = await dialog('Save this search', h('div', null, h('datalist', { id: 'savednames' }, S.searches.map((x) => h('option', { value: x.name }))),
      h('div', { class: 'grid' }, fld('Name', name, true)),
      h('p', { class: 'muted small' }, 'Kept for you alone, in the sidebar under Transactions: the filters, not what they found. A name you already use takes this search instead.')),
    [{ label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }]);
    if (!ok) return;
    try { await api('api/searches', { method: 'POST', json: { name: name.value, query: String(now) } }); await refreshSummary(); toast('Saved'); onRoute(); } catch (e) { fail(e); }
  };
  const forget = async (x) => {
    if (!await confirmDialog('Forget the search', `Forget “${x.name}”? The transactions stay.`, 'Forget', true)) return;
    try { await api(`api/searches/${x.id}`, { method: 'DELETE' }); await refreshSummary(); onRoute(); } catch (e) { fail(e); }
  };
  return h('div', { class: 'saved' }, S.searches.map((x) => h('span', { class: `schip ${x === mine ? 'on' : ''}` },
    h('a', { href: `#/transactions?${x.query}` }, icon('bookmark', 'xs'), x.name),
    x === mine ? h('button', { title: 'Forget this search', 'aria-label': 'Forget this search', onclick: () => forget(x) }, icon('close', 'xs')) : null)),
  has && !mine ? h('button', { class: 'schip new', onclick: save }, icon('add', 'xs'), 'Save this search') : null,
  has ? h('a', { class: 'lnk small', href: '#/transactions' }, 'Clear the filters') : null);
}

/** The bar that comes up once transactions are ticked: the same change to all of them (category, payee, tags, hidden,
    reconciled, looked at), with Undo right after. review: on the Needs a look page. */
function drawBulk(bar, picked, items, review) {
  const n = picked.size;
  bar.hidden = !n;
  if (!n) { bar.replaceChildren(); return; }
  const rows = items.filter((t) => picked.has(t.id));
  const run = async (set, done) => {
    try {
      const r = await api('api/transactions/bulk', { method: 'POST', json: { ids: [...picked], set } });
      S.cats = []; S.tags = null;
      await refreshSummary();
      const kept = Object.keys(set).some((k) => !['reconciled', 'reviewed'].includes(k));  // those two are no change to the transaction itself
      toast(`${plural(r.changed, 'transaction')} ${done}`, kept && r.changed ? ['Undo', async () => {
        try { const b = await api('api/changes/undo', { method: 'POST', json: { batch: r.batch } }); S.cats = []; S.tags = null; toast(`${plural(b.undone, 'transaction')} put back`); await refreshSummary(); onRoute(); } catch (e) { fail(e); }
      }] : null);
      onRoute();
    } catch (e) { fail(e); }
  };
  const ask = async (title, label, field, ok = 'Change') => (await dialog(title, h('div', null, h('div', { class: 'grid' }, fld(label, field, true)),
    h('p', { class: 'muted small' }, `For the ${plural(n, 'transaction')} ticked. Undo takes it back.`)), [{ label: 'Cancel', value: false }, { label: ok, value: true, primary: true }])) === true;
  const category = async () => {
    const cats = await categories();
    const f = inp('', { list: 'bulkcats', placeholder: 'Groceries' });
    const dl = h('datalist', { id: 'bulkcats' }, cats.map((c) => h('option', { value: c.category })));
    if (!await ask('Set the category', 'Category', h('span', null, dl, f)) || !f.value.trim()) return;
    run({ category: f.value.trim() }, 'categorized');
  };
  const payee = async () => {
    const f = inp('', { maxlength: 255, placeholder: 'The payee’s name' });
    if (!await ask('Set the payee', 'Payee', f) || !f.value.trim()) return;
    run({ merchant: f.value.trim() }, 'renamed');
  };
  const tag = async () => {
    const known = (await tagList()).filter((x) => x.own);
    const own = [...new Map(rows.flatMap((t) => t.ownTags || []).map((x) => [x.toLowerCase(), x])).values()].sort((a, b) => a.localeCompare(b));
    const add = inp('', { list: 'bulktags', placeholder: 'trip, reimbursable' });
    const off = h('select', { class: 't' }, h('option', { value: '' }, 'None'), own.map((x) => h('option', { value: x }, x)));
    const ok = await dialog('Tag them', h('div', null, h('datalist', { id: 'bulktags' }, known.map((x) => h('option', { value: x.tag }))),
      h('div', { class: 'grid' }, fld('Add the tags', add, true), own.length ? fld('Take off the tag', off, true) : null),
      h('p', { class: 'muted small' }, `For the ${plural(n, 'transaction')} ticked. Undo takes it back.`)), [{ label: 'Cancel', value: false }, { label: 'Change', value: true, primary: true }]);
    const tags = add.value.split(',').map((x) => x.trim().replace(/^#/, '')).filter(Boolean);
    if (!ok || (!tags.length && !off.value)) return;
    run({ ...(tags.length ? { addTags: tags } : {}), ...(off.value ? { removeTags: [off.value] } : {}) }, 'tagged');
  };
  const allHidden = rows.length && rows.every((t) => t.hidden);
  const allRec = rows.length && rows.every((t) => t.reconciled);
  const btn = (ic, label, fn, title) => h('button', { class: 'pillbtn tiny', onclick: fn, title: title || null }, icon(ic, 'xs'), label);
  fill(bar, h('b', null, `${n} ticked`),
    btn('list', 'Category', category), btn('store', 'Payee', payee), btn('label', 'Tags', tag),
    btn('eye', allHidden ? 'Show' : 'Hide', () => run({ hidden: !allHidden }, allHidden ? 'shown' : 'hidden'), 'A hidden transaction is left out of the sums'),
    btn('check', allRec ? 'Not reconciled' : 'Reconciled', () => run({ reconciled: !allRec }, allRec ? 'no longer reconciled' : 'marked reconciled')),
    review ? btn('doneAll', 'Looked at', () => run({ reviewed: true }, 'looked at'), 'Take them off this list as they are') : null,
    h('span', { class: 'grow' }),
    h('button', { class: 'iconbtn', title: 'Untick them', 'aria-label': 'Untick them', onclick: () => { picked.clear(); onRoute(); } }, icon('close', 's')));
}

/** A change kept for a transaction, as words: "category: Shopping, was Groceries". */
const histVal = (f, v) => (v == null || v === '' || (Array.isArray(v) && !v.length) ? 'nothing' : f === 'hidden' ? (v ? 'yes' : 'no')
  : Array.isArray(v) ? v.join(', ') : f === 'date' ? fmtDay(v, true) : String(v));
const histFields = (c) => c.fields.map((x) => h('span', { class: 'hf' }, h('i', null, x.field), ' ', h('b', null, histVal(x.field, x.after)), h('small', null, ` was ${histVal(x.field, x.before)}`)));
const HIST_WHAT = { hand: 'Changed', bulk: 'Changed with others', undo: 'Taken back', reset: 'Back to Monarch’s own' };
/** "History" in a transaction's dialog: what was changed on it by hand, by whom and when, each with its way back; and
    for one from Monarch Money that was changed here, the way back to Monarch's own. Fetched when opened. */
function historyBox(t) {
  const list = h('div', { class: 'hist' });
  const box = h('details', { class: 'histbox' }, h('summary', null, icon('history', 'xs'), 'History'), list);
  const after = async (fn, done) => { try { await fn(); S.cats = []; S.tags = null; toast(done); closeDialogs(); await refreshSummary(); onRoute(); } catch (e) { fail(e); } };
  const reset = t.writable && t.source === 'monarch' && t.edited ? h('button', { class: 'lnkbtn', onclick: async () => {
    if (!await confirmDialog('Back to Monarch’s own', 'Undo everything changed here on this transaction (its payee, category, notes, tags and split)? The rules apply to it again, and the next sync refreshes it from Monarch Money.', 'Put it back')) return;
    after(() => api(`api/transactions/${t.id}/reset`, { method: 'POST' }), 'Back to Monarch’s own');
  } }, icon('undo', 'xs'), 'Back to Monarch’s own') : null;
  let got = false;
  box.addEventListener('toggle', async () => {
    if (!box.open || got) return;
    got = true;
    try {
      const items = (await api(`api/transactions/${t.id}/changes`)).items || [];
      fill(list, items.length ? h('ul', null, items.map((c) => h('li', { class: c.undone ? 'undone' : null },
        h('div', { class: 'hw' }, h('span', null, [HIST_WHAT[c.what] || c.what, c.by, agoSec(c.secondsAgo)].filter(Boolean).join(' · ')), c.undone ? h('span', { class: 'tag' }, 'Taken back') : null,
          t.writable && !c.undone && c.what !== 'undo' ? h('button', { class: 'lnk small', onclick: () => after(() => api('api/changes/undo', { method: 'POST', json: { id: c.id } }), 'Taken back') }, 'Undo') : null),
        h('div', { class: 'hfs' }, histFields(c)))))
        : h('p', { class: 'muted small' }, t.edited ? 'Changed here before changes were kept.' : 'Not changed by hand.'), reset);
    } catch (e) { fill(list, h('p', { class: 'muted small' }, e.message || String(e))); }
  });
  return box;
}

/** Choose one of the accounts (for the statement to reconcile, the file to import). */
async function pickAccount(title, accts, text) {
  if (!accts.length) { toast(text); return null; }
  if (accts.length === 1) return accts[0];
  const sel = h('select', { class: 't' }, accts.map((a) => h('option', { value: a.id }, a.name)));
  const ok = await dialog(title, h('div', { class: 'grid' }, fld('Account', sel, true)), [{ label: 'Cancel', value: false }, { label: 'Next', value: true, primary: true }]);
  return ok ? accts.find((a) => a.id === +sel.value) : null;
}

/** Tidy up: everything that keeps the transactions right, each with how much there is to do. */
async function showTidy(page) {
  const d = await api('api/tidy');
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Tidy up')));
  put(page, h('p', { class: 'muted' }, 'What keeps the transactions right: the ones to look at, the ones kept twice, the accounts that do not add up, and the lists behind them.'));
  const tile = (to, ic, hueVar, title, text, n, warn) => {
    const kids = [h('span', { class: 'sic' }, icon(ic)), h('span', { class: 'tt' }, h('b', null, title, n ? h('span', { class: `n ${warn ? 'warn' : ''}` }, n.toLocaleString()) : null), h('small', null, text))];
    return typeof to === 'string' ? h('a', { class: 'tidytile', href: to, style: { '--hue': `var(${hueVar})` } }, kids)
      : h('button', { class: 'tidytile', onclick: to, style: { '--hue': `var(${hueVar})` } }, kids);
  };
  const txAccts = S.accounts.filter((a) => followsTx(a) && a.writable && !a.closed);
  const reconcile = async () => { const a = await pickAccount('Reconcile with a statement', txAccts, 'No account of yours follows its transactions'); if (a) location.hash = `#/account/${a.id}/reconcile`; };
  const imp = async () => { const a = await pickAccount('Import a bank file', txAccts.filter((x) => x.source === 'manual'), 'A bank file goes into an account kept by hand: add one first'); if (a) importDialog(a); };
  put(page, h('h2', { class: 'recurhead' }, icon('warning'), h('span', null, 'To check')), h('div', { class: 'tidygrid' },
    tile('#/review', 'doneAll', '--c-blue', 'Needs a look', 'New transactions, and the ones without a category', d.review, true),
    tile('#/duplicates', 'copy', '--c-rose', 'Likely duplicates', 'The same transaction kept twice', d.duplicates, true),
    tile('#/transfers', 'link', '--c-teal', 'Transfers to check', 'The same amount out of one account and into another, not linked', d.transfers, true),
    tile('#/balance', 'scale', '--c-amber', 'Balance check', 'Does each account’s balance agree with its transactions?', d.balanceGaps, true)));
  put(page, h('h2', { class: 'recurhead' }, icon('list'), h('span', null, 'The lists')), h('div', { class: 'tidygrid' },
    tile('#/payees', 'store', '--c-indigo', 'Payees', 'Rename or merge them, give each its usual category', d.payees),
    tile('#/categories', 'label', '--c-purple', 'Categories and tags', 'Add, rename, merge or delete them', d.tags),
    tile('#/rules', 'tune', '--c-teal', 'Rules', 'What each rule does, the ones that do nothing, the ones missing'),
    tile('#/changes', 'history', '--c-slate', 'Recent changes', 'What was changed by hand, each with its way back')));
  put(page, h('h2', { class: 'recurhead' }, icon('bank'), h('span', null, 'Against the bank')), h('div', { class: 'tidygrid' },
    tile(reconcile, 'check', '--c-green', 'Reconcile with a statement', 'Tick an account’s transactions off against the bank’s statement, by hand or from its PDF or CSV file'),
    tile(imp, 'upload', '--c-orange', 'Import a bank file', 'CSV, OFX or QFX into an account kept by hand')));
}

/** Needs a look: what came in since someone last looked, and what has no category. A tick takes one off as it is;
    saving a change does too; several ticked are changed together. */
async function showReview(page) {
  const d = await api('api/transactions?review=yes&limit=300');
  const can = d.items.some((t) => t.writable);
  const sum = h('p', { class: 'sumline' });
  const say = (n) => { sum.textContent = n ? `${plural(n, 'transaction')} to look at${n > d.items.length ? `, the latest ${d.items.length} shown` : ''}` : ''; };
  const markAll = async () => {
    if (!await confirmDialog('Mark all looked at', `Take all ${plural(d.total, 'transaction')} off this list as they are?`, 'Mark them')) return;
    try { const r = await api('api/transactions/review', { method: 'POST', json: { all: true } }); toast(`${plural(r.changed, 'transaction')} looked at`); await refreshSummary(); onRoute(); } catch (e) { fail(e); }
  };
  put(page, h('div', { class: 'pagehead' }, tidyBack(), h('h1', null, 'Needs a look'), h('span', { class: 'grow' }),
    can ? h('button', { class: 'pillbtn', onclick: markAll }, icon('doneAll'), h('span', null, 'All looked at')) : null));
  put(page, h('p', { class: 'muted' }, 'The transactions that came in since this list was first opened and nobody looked at yet, and the ones without a category. ',
    'Open one to correct it (saving takes it off the list), tick it at the right as it is, or tick several at the left and change them together.'));
  if (!d.items.length) { put(page, h('div', { class: 'empty' }, icon('doneAll'), h('p', null, 'Nothing needs a look.'))); return; }
  say(d.total);
  const picked = new Set();
  const bar = h('div', { class: 'bulkbar', hidden: true });
  put(page, sum, txList(d.items, true, undefined, { picked, onPick: () => drawBulk(bar, picked, d.items, true), review: true,
    onReviewed: (left) => { say(left); drawBulk(bar, picked, d.items, true); if (!left) onRoute(); } }), bar);
}

/** The payees: how many transactions and how much each, its usual category; editors rename one (into another: the two
    are one) and give it its category, kept as rules. */
async function showPayees(page) {
  const [d, cats] = await Promise.all([api('api/payees?limit=2000'), categories()]);
  const w = d.writable;
  const f = { q: '', sort: store.get('paySort') || 'count' };
  put(page, h('div', { class: 'pagehead' }, tidyBack(), h('h1', null, 'Payees')));
  put(page, h('p', { class: 'muted' }, 'Everyone the transactions were paid to or came from. ',
    w ? 'Rename a payee, or give it the name of another to make the two one; give it its usual category. Both are kept as rules, so what comes in later follows.' : 'Editors rename and merge them and set their usual category.'));
  if (!d.items.length) { put(page, h('div', { class: 'empty' }, icon('store'), h('p', null, 'No payees yet.'))); return; }
  const count = h('span', { class: 'muted small' });
  const list = h('ul', { class: 'rows flat payees' });
  const SHOWN = 400;
  const sorts = { count: (a, b) => b.count - a.count || a.payee.localeCompare(b.payee), name: (a, b) => a.payee.localeCompare(b.payee),
    total: (a, b) => Math.abs(b.total) - Math.abs(a.total), mixed: (a, b) => b.categories - a.categories || b.count - a.count, last: (a, b) => b.last.localeCompare(a.last) };
  const draw = () => {
    const q = f.q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const shown = d.items.filter((p) => q.every((x) => p.payee.toLowerCase().includes(x) || (p.category || '').toLowerCase().includes(x))).sort(sorts[f.sort]);
    count.textContent = `${shown.length.toLocaleString()} of ${d.total.toLocaleString()}${shown.length > SHOWN ? `, the first ${SHOWN} shown` : ''}`;
    fill(list, shown.slice(0, SHOWN).map((p) => h('li', null, h('div', { class: 'r', role: w ? 'button' : null, tabindex: w ? 0 : null, onclick: w ? () => payeeDialog(p, d.items, cats) : null },
      h('span', { class: 'main' }, h('b', null, p.payee), h('small', null, h('span', { class: 'pcn' }, `${p.count} · `), `last ${fmtDay(p.last, p.last.slice(0, 4) !== today().slice(0, 4))}`)),
      h('span', { class: 'pc' }, p.rule ? h('span', { title: 'A rule gives it this category' }, icon('tune', 'xs'), p.rule.category) : (p.category || h('span', { class: 'muted' }, 'Uncategorized')),
        p.categories > 1 ? h('span', { class: 'tag warn', title: 'Its transactions are in several categories' }, `${p.categories} categories`) : null),
      h('a', { class: 'lnk small pn', href: `#/transactions?${new URLSearchParams({ q: p.payee })}`, onclick: (e) => e.stopPropagation() }, plural(p.count, 'transaction')),
      h('span', { class: 'pt' }, amt(p.total))))));
  };
  const search = inp('', { type: 'search', placeholder: 'Payee or category…' });
  let tm; search.oninput = () => { clearTimeout(tm); tm = setTimeout(() => { f.q = search.value; draw(); }, 150); };
  const sort = h('select', { class: 't', 'aria-label': 'Order', onchange: (e) => { f.sort = e.target.value; store.set('paySort', f.sort); draw(); } },
    [['count', 'Most used first'], ['name', 'By name'], ['total', 'Largest total first'], ['last', 'Latest first'], ['mixed', 'Several categories first']].map(([v, l]) => h('option', { value: v, selected: v === f.sort ? true : null }, l)));
  put(page, h('div', { class: 'filters' }, search, sort, count), list);
  draw();
}
async function payeeDialog(p, all, cats) {
  const f = { name: inp(p.payee, { maxlength: 255, list: 'payeenames' }), category: inp(p.rule ? p.rule.category : '', { list: 'payeecats', placeholder: p.category ? `Mostly ${p.category} now` : 'Groceries' }),
    all: h('input', { type: 'checkbox' }) };
  const body = h('div', null, h('datalist', { id: 'payeenames' }, all.filter((x) => x !== p).slice(0, 1500).map((x) => h('option', { value: x.payee }))),
    h('datalist', { id: 'payeecats' }, cats.map((c) => h('option', { value: c.category }))),
    h('div', { class: 'grid' }, fld('Name', f.name, true), fld('Its usual category', f.category, true)),
    h('label', { class: 'check', style: { marginTop: '10px' } }, f.all, 'Give the category to the ones categorized by hand too'),
    h('p', { class: 'muted small' }, `${plural(p.count, 'transaction')}, ${money(p.total)} in all. Give it the name of another payee to make the two one. The name and the category are kept as rules (on the Rules page).`));
  if (!await dialog(p.payee, body, [{ label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }], 'wide')) return;
  const name = f.name.value.trim(), cat = f.category.value.trim();
  try {
    let said = 'Nothing changed';
    if (name && name !== p.payee) {
      const other = all.find((x) => x !== p && x.payee.toLowerCase() === name.toLowerCase());
      if (other && !await confirmDialog('Make the two one', `Rename ${p.payee} to ${other.payee}? Its ${plural(p.count, 'transaction')} join the ${other.count} there, now and from here on.`, 'Merge')) return;
      const r = await api('api/payees/rename', { method: 'POST', json: { name: p.payee, newName: other ? other.payee : name } });
      said = `${plural(r.changed, 'transaction')} renamed`;
    }
    if (cat && (f.all.checked || !p.rule || p.rule.category !== cat)) {
      const r = await api('api/payees/category', { method: 'POST', json: { name: name || p.payee, category: cat, all: f.all.checked } });
      said = `${said === 'Nothing changed' ? '' : `${said}; `}${plural(r.changed, 'transaction')} categorized`;
    }
    S.cats = []; toast(said); onRoute();
  } catch (e) { fail(e); }
}

/** The tags, under the categories: each with how many transactions and how much; editors rename (or merge) and delete
    the household's own. */
async function drawTags(page) {
  let d; try { d = await api('api/tags'); } catch { return; }
  S.tags = d.items;
  put(page, h('div', { class: 'pagehead', style: { marginTop: '28px' } }, h('h2', { class: 'h1ish' }, icon('label'), 'Tags')));
  put(page, h('p', { class: 'muted' }, 'A tag says what a transaction is part of, whatever its category: a trip, what is to be paid back, what counts for the taxes. ',
    'Type them on a transaction, or tick several transactions and tag them together. The tags Monarch Money sends are shown too; those are changed in Monarch.'));
  if (!d.items.length) { put(page, h('p', { class: 'muted small' }, 'No tags yet.')); return; }
  put(page, h('ul', { class: 'rows flat tagrows' }, d.items.map((x) => {
    const edit = d.writable && x.own;
    return h('li', null, h('div', { class: 'r', role: edit ? 'button' : null, tabindex: edit ? 0 : null, onclick: edit ? () => tagDialog(x, d.items) : null },
      h('span', { class: 'main' }, h('b', null, h('span', { class: 'tag tg' }, x.tag), !x.own ? h('span', { class: 'tag', title: 'Sent by Monarch Money: changed there' }, 'Monarch') : null)),
      h('a', { class: 'lnk small', href: `#/transactions?${new URLSearchParams({ tag: x.tag })}`, onclick: (e) => e.stopPropagation() }, plural(x.count, 'transaction')),
      h('span', { class: 'pt' }, amt(x.total))));
  })));
}
async function tagDialog(x, all) {
  const name = inp(x.tag, { maxlength: 64, list: 'tagnames' });
  const body = h('div', null, h('datalist', { id: 'tagnames' }, all.filter((y) => y.own && y !== x).map((y) => h('option', { value: y.tag }))),
    h('div', { class: 'grid' }, fld('Name', name, true)), h('p', { class: 'muted small' }, `On ${plural(x.count, 'transaction')}. Give it the name of another tag to make the two one.`));
  const ok = await dialog(`Tag ${x.tag}`, body, [{ label: 'Delete', value: 'delete', danger: true }, { label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }]);
  try {
    if (ok === 'delete') {
      if (!await confirmDialog('Delete the tag', `Take “${x.tag}” off its ${plural(x.count, 'transaction')}? The transactions stay.`, 'Delete', true)) return;
      await api('api/tags/delete', { method: 'POST', json: { name: x.tag } });
    } else if (ok && name.value.trim() && name.value.trim() !== x.tag) await api('api/tags', { method: 'PUT', json: { name: x.tag, newName: name.value } });
    else return;
    S.tags = null; toast(ok === 'delete' ? 'Deleted' : 'Saved'); onRoute();
  } catch (e) { fail(e); }
}

/** Likely duplicates: the same account and amount, at most three days apart, and alike. Keep one and hide (or, added
    here, delete) the other, or say they are two. */
async function showDuplicates(page) {
  const d = await api('api/duplicates');
  put(page, h('div', { class: 'pagehead' }, tidyBack(), h('h1', null, 'Likely duplicates')));
  put(page, h('p', { class: 'muted' }, 'Transactions in one account, of the same amount, at most three days apart, that look like one kept twice. ',
    'Keep one and hide the other (a hidden transaction is left out of every sum; one added here can be deleted), or say they are different: those are not shown again.'));
  if (!d.items.length) { put(page, h('div', { class: 'empty' }, icon('copy'), h('p', null, 'No likely duplicates.'))); return; }
  const count = h('p', { class: 'sumline' });
  const list = h('div', { class: 'dups' });
  const say = () => {
    const n = list.children.length;
    count.textContent = n ? `${plural(n, 'likely duplicate')} to check` : '';
    if (S.sum && !n) refreshSummary();
    if (!n) fill(list, h('div', { class: 'empty' }, icon('check'), h('p', null, 'All checked.')));
  };
  const group = (g) => {
    const el = h('div', { class: 'dupg' });
    const left = () => { if (el.querySelectorAll('.dupr').length < 2) { el.remove(); say(); } };
    const row = (t) => {
      const r = h('div', { class: 'dupr' });
      const act = (label, fn, cls) => h('button', { class: `pillbtn tiny ${cls || ''}`, onclick: async (e) => { e.stopPropagation(); try { if (await fn() === false) return; r.remove(); left(); } catch (x) { fail(x); } } }, label);
      put(r, h('span', { class: 'd' }, fmtDay(t.day, true)),
        h('button', { class: 'p', title: 'Open the transaction', onclick: () => txDialog(t) }, h('b', null, t.merchant || t.description || '(no payee)'),
          t.description && t.description !== t.merchant ? h('small', null, t.description) : null),
        h('span', { class: 'k' }, h('span', { class: 'tag' }, t.source === 'manual' ? 'Added here' : 'Monarch'), t.pending ? h('span', { class: 'tag' }, 'Pending') : null,
          t.reconciled ? h('span', { class: 'tag', title: 'Checked against a statement' }, 'Reconciled') : null, t.edited ? h('span', { class: 'tag' }, 'Changed here') : null,
          t.transfer ? h('span', { class: 'tag' }, 'Transfer') : null, t.category ? h('span', { class: 'muted small' }, t.category) : null),
        h('span', { class: 'm' }, amt(t.amount, t.currency)),
        h('span', { class: 'acts' }, !t.writable ? null : [act('Hide', () => api(`api/transactions/${t.id}`, { method: 'PATCH', json: { hidden: true } })),
          t.source === 'manual' ? act('Delete', async () => { if (!await confirmDialog('Delete it', 'Delete this transaction? This cannot be undone.', 'Delete', true)) return false; await api(`api/transactions/${t.id}`, { method: 'DELETE' }); }, 'danger') : null]));
      return r;
    };
    put(el, h('div', { class: 'duph' }, h('b', null, g.items[0].account), h('span', { class: 'muted small' }, g.whyText), h('span', { class: 'grow' }),
      g.items.every((t) => t.writable) ? h('button', { class: 'pillbtn tiny', onclick: async () => {
        try { await api('api/duplicates/not', { method: 'POST', json: { ids: g.items.map((t) => t.id) } }); el.remove(); say(); } catch (x) { fail(x); }
      } }, 'They are different') : null), g.items.map(row));
    return el;
  };
  put(list, d.items.map(group));
  put(page, count, list);
  say();
}

/** #/account/3/reconcile: an account against the bank's statement. The statement's days and its two balances; the
    transactions of those days to tick off; done when the ticked ones add up to what the balance moved by. */
async function showReconcile(page, a) {
  const d = await api(`api/accounts/${a.id}/statements`);
  const w = d.writable;
  const iso = (x) => x.toLocaleDateString('sv');
  let end = today();
  if (d.next.start) { const e = dateOf(d.next.start); e.setMonth(e.getMonth() + 1); e.setDate(e.getDate() - 1); if (iso(e) < end) end = iso(e); }
  const f = { start: inp(d.next.start || '', { type: 'date' }), end: inp(end, { type: 'date' }), opening: inp(d.next.opening == null ? '' : d.next.opening, { inputmode: 'decimal' }),
    closing: inp('', { inputmode: 'decimal', placeholder: 'as the statement says' }) };
  const num = (v) => { const x = parseFloat(String(v).replace(/[^0-9.-]/g, '')); return Number.isNaN(x) ? null : x; };
  const cents = (v) => Math.round(v * 100);
  put(page, h('div', { class: 'pagehead' }, h('a', { class: 'iconbtn', href: `#/account/${a.id}`, title: a.name, 'aria-label': a.name }, icon('prev')), h('h1', null, `Reconcile ${a.name}`)));
  put(page, h('p', { class: 'muted' }, 'Take the bank’s statement: its first and last day, and the balance at its start and at its end. Tick each transaction the statement shows. ',
    'When the ticked ones add up to what the balance moved by, the account agrees with the bank up to that day.',
    d.isAsset ? null : ' What is owed counts as a positive balance here, so a purchase makes it go up.'));
  // the bank's own file held against the account: the statement's PDF, or a CSV, OFX or QFX file from its website
  let cmp = null, found = new Set(), extra = new Set();
  const cmpbox = h('div', { class: 'cmpbox' });
  const pick = h('input', { type: 'file', accept: '.pdf,.csv,.ofx,.qfx,.qbo,.txt,application/pdf,text/csv', hidden: true,
    onchange: (e) => { const x = e.target.files[0]; e.target.value = ''; if (x) read({ aid: a.id, file: x }); } });
  const pickBtn = h('button', { class: 'pillbtn', onclick: () => pick.click() }, icon('upload', 'xs'), 'Compare with the bank’s file');
  put(page, h('div', { class: 'box' }, h('div', { class: 'grid' }, fld('First day', f.start), fld('Last day', f.end), fld(d.isAsset ? 'Balance at the start' : 'Owed at the start', f.opening), fld(d.isAsset ? 'Balance at the end' : 'Owed at the end', f.closing)),
    h('div', { class: 'cmppick' }, pickBtn, pick, h('span', { class: 'muted small' }, 'The statement’s PDF, or a CSV, OFX or QFX file from the bank’s website: its days and balances are filled in, what it shows is ticked, and what differs is listed. The file is read and not kept.'))), cmpbox);
  const lines = h('div');
  const bar = h('div', { class: 'bulkbar recbar' });
  put(page, lines, bar);
  let items = [], sign = 1; const ticked = new Set();
  const summary = () => {
    const sum = items.filter((t) => ticked.has(t.id)).reduce((s, t) => s + cents(t.amount), 0);
    const o = num(f.opening.value), c = num(f.closing.value);
    const moved = o == null || c == null ? null : cents(c) - cents(o);
    const diff = moved == null ? null : moved - sign * sum;
    const finish = async () => {
      if (diff && !await confirmDialog('Finish with a difference', `The transactions ticked do not add up to the statement: ${money(Math.abs(diff) / 100, a.currency)} is left. Keep the statement as it is anyway?`, 'Finish anyway')) return;
      try {
        const r = await api(`api/accounts/${a.id}/statements`, { method: 'POST', json: { start: f.start.value, end: f.end.value, opening: o, closing: c, ids: [...ticked], anyway: !!diff } });
        S.recFile = null; toast(`${plural(r.reconciled, 'transaction')} reconciled`); onRoute();
      } catch (e) { fail(e); }
    };
    fill(bar, h('span', null, `${ticked.size} of ${items.length} ticked: `, h('b', { class: 'num' }, money(sum / 100, a.currency))),
      h('span', null, 'The statement moved by ', h('b', { class: 'num' }, moved == null ? '…' : money(sign * moved / 100, a.currency))),
      h('span', { class: diff === 0 ? 'ok' : 'off' }, 'Difference ', h('b', { class: 'num' }, diff == null ? '…' : money((sign * diff || 0) / 100, a.currency))),
      h('span', { class: 'grow' }),
      w ? h('button', { class: `pillbtn ${diff === 0 ? 'primary' : ''}`, disabled: diff == null || !items.length ? true : null, onclick: finish }, icon('check', 'xs'), diff ? 'Finish anyway' : 'Finish') : null);
  };
  const load = async () => {
    ticked.clear(); items = [];
    if (!f.start.value || !f.end.value) { fill(lines, h('p', { class: 'muted' }, 'Give the statement’s first and last day.')); summary(); return; }
    try {
      const got = await api(`api/accounts/${a.id}/statement?${new URLSearchParams({ start: f.start.value, end: f.end.value })}`);
      items = got.items; sign = got.sign;
      for (const t of items) if (cmp ? found.has(t.id) : t.reconciled && !t.earlier) ticked.add(t.id);  // with the bank's file: what it shows
      const boxes = [];
      const row = (t) => {
        const b = h('input', { type: 'checkbox', checked: ticked.has(t.id) ? true : null, disabled: w ? null : true, 'aria-label': 'On the statement' });
        const li = h('li', { class: ticked.has(t.id) ? 'picked' : null });
        b.onchange = () => { if (b.checked) ticked.add(t.id); else ticked.delete(t.id); li.classList.toggle('picked', b.checked); summary(); };
        boxes.push([t, b, li]);
        put(li, h('label', { class: 'r' }, b, h('span', { class: 'day' }, fmtDay(t.day)),
          h('span', { class: 'main' }, h('b', null, t.merchant || t.description || '(no payee)', t.earlier ? h('span', { class: 'tag', title: 'From before this statement, not ticked off on the one before' }, 'Earlier') : null,
            t.hidden ? h('span', { class: 'tag' }, 'Hidden') : null,
            cmp && extra.has(t.id) ? h('span', { class: 'tag warn', title: 'In the account in these days, but the bank’s file does not show it' }, cmp.kind === 'pdf' ? 'Not on the statement' : 'Not in the file') : null), h('small', null, [t.transfer ? `Transfer ${t.amount < 0 ? 'to' : 'from'} ${t.transfer.account}` : t.category, t.description && t.description !== t.merchant ? t.description : null].filter(Boolean).join(' · '))),
          h('span', { class: 'pt' }, amt(t.amount, t.currency))));
        return li;
      };
      const all = (on) => { for (const [t, b, li] of boxes) { b.checked = on; li.classList.toggle('picked', on); if (on) ticked.add(t.id); else ticked.delete(t.id); } summary(); };
      fill(lines, items.length ? [h('p', { class: 'sumline', style: { marginTop: '4px' } }, `${plural(items.length, 'transaction')} to tick off`,
        w ? [' · ', h('button', { class: 'lnk', onclick: () => all(true) }, 'Tick all'), ' · ', h('button', { class: 'lnk', onclick: () => all(false) }, 'Untick all')] : null),
      h('ul', { class: 'rows flat recon' }, items.map(row))] : h('p', { class: 'muted' }, 'No transactions in these days.'));
    } catch (e) { fill(lines, h('p', { class: 'muted' }, e.message || String(e))); }
    summary();
  };
  /** What the file and the account do not agree on, above the list: the lines the account does not have (to add, or
      with the transaction of another amount that looks like it), the ones it has under another day, and how many
      of its own the file does not show (marked in the list). */
  const drawCmp = () => {
    const r = cmp;
    if (!r) { fill(cmpbox); return; }
    const it = r.kind === 'pdf' ? 'statement' : 'file', onIt = r.kind === 'pdf' ? 'on the statement' : 'in the file';
    const can = w && followsTx(a);
    const again = () => read(S.recFile);
    const post = (x) => api(`api/accounts/${a.id}/transactions`, { method: 'POST', json: x });
    const addOne = async (x) => {
      const g = { merchant: inp(x.text), day: inp(x.day, { type: 'date' }), amount: inp(x.signed ? x.amount : -Math.abs(x.amount), { inputmode: 'decimal', placeholder: '-12.50 out, 100 in' }) };
      const ok = await dialog('Add the transaction', h('div', null, h('div', { class: 'grid' }, fld('Payee', g.merchant, true), fld('Amount', g.amount), fld('Date', g.day)),
        x.signed ? null : h('p', { class: 'muted small' }, 'The statement does not say which way the money went: it is put as money out. Take the minus away for money in.'),
        a.source === 'manual' ? null : h('p', { class: 'muted small' }, 'Added here, by hand, beside Monarch Money’s own. Should Monarch still bring it later, it shows under Likely duplicates.')),
      [{ label: 'Cancel', value: false }, { label: 'Add', value: true, primary: true }]);
      if (!ok) return;
      try { await post({ merchant: g.merchant.value, day: g.day.value, amount: g.amount.value }); toast('Added'); await again(); } catch (e) { fail(e); }
    };
    const addAll = async (xs) => {
      if (!await confirmDialog('Add them all', `Add the ${plural(xs.length, 'transaction')} the account does not have, as the ${it} gives them?`, 'Add them')) return;
      let n = 0;
      cmpbox.classList.add('busy');
      try { for (const x of xs) { await post({ merchant: x.text, day: x.day, amount: x.amount }); n += 1; } } catch (e) { fail(e); }
      if (n) toast(`${plural(n, 'transaction')} added`);
      await again();
    };
    const open = async (id) => { try { txDialog(await api(`api/transactions/${id}`)); } catch (e) { fail(e); } };
    const line = (x, note, ...right) => h('li', null, h('div', { class: 'r' }, h('span', { class: 'day' }, fmtDay(x.day)),
      h('span', { class: 'main' }, h('b', null, x.text || '(no text)'), note ? h('small', null, note) : null),
      h('span', { class: 'pt' }, x.signed ? amt(x.amount, a.currency) : h('span', { class: 'num' }, money(x.amount, a.currency))), right));
    const lone = r.missing.filter((x) => !x.differs);
    const here = [...extra].filter((id) => items.some((t) => t.id === id)).length;
    const notes = [
      r.total ? null : 'No lines could be read from it, only its days and balances: tick the transactions by hand.',
      r.adds === true ? 'Its lines add up to its two balances, so all of it was read.' : null,
      r.adds === false ? 'Its lines as read do not add up to its two balances: a line may have been missed or read wrong, so look over the ticks.' : null,
      r.kind === 'pdf' && r.total && r.closing == null ? 'Its balances were not found: type them from the statement.' : null,
      r.worked ? `The ${it} gives no balance: the one at the end is the account’s balance on the day before its first day plus its lines. Check it against the bank’s.` : null,
      r.kind !== 'pdf' && r.closing == null ? 'The file gives no balance, and none is kept for the day before its first day: type the two balances to finish.' : null,
      r.flipped ? 'The file writes money out as a positive number: it was turned around.' : null,
      r.problems ? `${plural(r.problems, 'row')} of the file could not be read.` : null];
    const order = r.guessed && r.dateOrder !== 'ymd' ? h('p', { class: 'muted small' }, `Its dates read both ways: they were taken as ${r.dateOrder === 'mdy' ? 'month, then day' : 'day, then month'}. `,
      h('button', { class: 'lnk', onclick: () => read({ ...S.recFile, order: r.dateOrder === 'mdy' ? 'dmy' : 'mdy' }) }, r.dateOrder === 'mdy' ? 'Read them as day, then month' : 'Read them as month, then day')) : null;
    const agree = r.total && !r.missingCount && !r.elsewhere.length && !here;
    fill(cmpbox, h('div', { class: 'box' },
      h('div', { class: 'cmphead' }, icon(agree ? 'check' : 'receipt', 's'),
        h('b', null, `${r.name || `The ${it}`}: ${plural(r.total, 'line')}, ${r.matched.length} found here and ticked`), h('span', { class: 'grow' }),
        h('button', { class: 'iconbtn', title: `Put the ${it} away`, 'aria-label': `Put the ${it} away`, onclick: () => { cmp = null; S.recFile = null; drawCmp(); load(); } }, icon('close', 's'))),
      agree ? h('p', { class: 'cmpok' }, `Everything ${onIt} is in the account, and everything in the account in these days is ${onIt}.`) : null,
      notes.filter(Boolean).map((x) => h('p', { class: 'muted small' }, x)), order,
      r.missingCount ? [h('h3', null, `${r.kind === 'pdf' ? 'On the statement' : 'In the file'}, not here (${r.missingCount})`, can && lone.length > 1 && lone.every((x) => x.signed) ? h('button', { class: 'pillbtn tiny', onclick: () => addAll(lone) }, icon('add', 'xs'), `Add the ${lone.length}`) : null),
        h('ul', { class: 'rows flat cmprows' }, r.missing.map((x) => (x.differs
          ? line(x, [`Here for ${money(x.differs.amount, a.currency)}: ${x.differs.name || '(no payee)'}, ${fmtDay(x.differs.day)}`], h('button', { class: 'pillbtn tiny', onclick: () => open(x.differs.id) }, 'Open'))
          : line(x, null, can ? h('button', { class: 'pillbtn tiny', onclick: () => addOne(x) }, icon('add', 'xs'), 'Add') : null)))),
        r.missingCount > r.missing.length ? h('p', { class: 'muted small' }, `The first ${r.missing.length} are shown.`) : null] : null,
      r.elsewhere.length ? [h('h3', null, `Here, outside these days (${r.elsewhere.length})`),
        h('ul', { class: 'rows flat cmprows' }, r.elsewhere.map((x) => line(x, x.why === 'pending' ? `Still pending here, ${fmtDay(x.at)}: it is ticked once it posts` : `Here on ${fmtDay(x.at)}, ${x.why} the ${it}’s ${x.why === 'before' ? 'first' : 'last'} day`,
          h('button', { class: 'pillbtn tiny', onclick: () => open(x.id) }, 'Open'))))] : null,
      here ? h('p', { class: 'cmpextra' }, h('span', { class: 'tag warn' }, r.kind === 'pdf' ? 'Not on the statement' : 'Not in the file'),
        ` ${plural(here, 'transaction')} of these days ${here === 1 ? 'is' : 'are'} in the account but not ${onIt}: marked below and left unticked.`) : null));
  };
  const read = async (src) => {
    S.recFile = src;
    pickBtn.disabled = true; cmpbox.classList.add('busy');
    try {
      const q = new URLSearchParams({ name: src.file.name });
      if (src.order) q.set('order', src.order);
      const r = await api(`api/accounts/${a.id}/statement/read?${q}`, { method: 'POST', body: src.file, headers: { 'Content-Type': 'application/octet-stream' } });
      cmp = r; found = new Set(r.matched); extra = new Set(r.extra);
      if (r.start) f.start.value = r.start;
      if (r.end) f.end.value = r.end;
      if (r.opening != null) f.opening.value = r.opening;
      if (r.closing != null) f.closing.value = r.closing;
      await load(); drawCmp();
    } catch (e) { S.recFile = null; fail(e); }
    pickBtn.disabled = false; cmpbox.classList.remove('busy');
  };
  f.start.onchange = load; f.end.onchange = load; f.opening.oninput = summary; f.closing.oninput = summary;
  await load();
  if (S.recFile && S.recFile.aid === a.id) await read(S.recFile);  // back from a transaction changed here: the file once more
  else S.recFile = null;
  if (d.items.length) {
    put(page, h('h2', { class: 'recurhead' }, icon('history'), h('span', null, 'Statements reconciled')), h('ul', { class: 'rows flat' }, d.items.map((s) => h('li', null, h('div', { class: 'r' },
      h('span', { class: 'main' }, h('b', null, `${fmtDay(s.start, true)} to ${fmtDay(s.end, true)}`),
        h('small', null, `${money(s.opening, a.currency)} to ${money(s.closing, a.currency)}`, s.difference ? ` · finished with ${money(Math.abs(s.difference), a.currency)} left` : '')),
      s.difference ? h('span', { class: 'tag warn' }, 'With a difference') : null,
      w ? h('button', { class: 'iconbtn', title: 'Forget this statement (its transactions stay reconciled)', onclick: async () => {
        if (!await confirmDialog('Forget the statement', 'Forget this statement? Its transactions stay reconciled.', 'Forget', true)) return;
        try { await api(`api/statements/${s.id}`, { method: 'DELETE' }); onRoute(); } catch (e) { fail(e); }
      } }, icon('delete', 's')) : null)))));
  }
}

/** The balance check: for each cash account and card from Monarch Money, whether its balance moved by what its
    transactions add up to; where it did not, by how much, which way, and in which days the gap appeared. */
async function showBalance(page) {
  const d = await api('api/balance-check');
  put(page, h('div', { class: 'pagehead' }, tidyBack(), h('h1', null, 'Balance check')));
  put(page, h('p', { class: 'muted' }, `Over the past ${d.days} days, each account’s balance at the bank should have moved by exactly what its transactions here add up to. `,
    'Where it did not, a transaction is missing here or kept twice. This looks at the cash accounts and cards Monarch Money keeps with a bank behind them.'));
  if (!d.items.length) { put(page, h('div', { class: 'empty' }, icon('scale'), h('p', null, 'No accounts to check.'))); return; }
  const post = async (x, gap) => { try { await api(`api/balance-check/${x.id}/ok`, { method: 'POST', json: { gap } }); await refreshSummary(); onRoute(); } catch (e) { fail(e); } };
  const TAGS = { ok: ['Agrees', 'ok'], pending: ['Agrees but for the pending ones', 'ok'], accepted: ['Accepted as it is', ''], unknown: ['Too little history yet', ''] };
  for (const x of d.items) {
    const acct = S.accounts.find((a) => a.id === x.id);
    const can = acct && acct.writable;
    const cur = x.currency;
    const head = h('div', { class: 'balh' }, h('a', { class: 'lnk', href: `#/account/${x.id}` }, h('b', null, x.name)), x.institution ? h('span', { class: 'muted small' }, x.institution) : null, h('span', { class: 'grow' }),
      x.status === 'gap' ? h('span', { class: 'tag warn' }, icon('warning', 'xs'), `Off by ${money(Math.abs(x.gap), cur)}`) : h('span', { class: `tag ${TAGS[x.status][1]}` }, TAGS[x.status][0]));
    const facts = x.status === 'unknown' ? h('p', { class: 'muted small' }, 'Monarch Money has not yet sent two balances for this account to compare.')
      : h('p', { class: 'muted small' }, `Since ${fmtDay(x.from, true)} the balance went from ${money(x.opening, cur)} to ${money(x.balance, cur)}; the ${plural(x.count, 'transaction')} here add up to ${money(x.moved, cur)}.`,
        x.status === 'pending' ? ` The pending ones (${money(x.pending, cur)}) explain the difference.` : x.status === 'accepted' ? ` Off by ${money(Math.abs(x.gap), cur)}, accepted as it is.` : '');
    const box = h('div', { class: `box balc ${x.status}` }, head, facts);
    if (x.status === 'gap') {
      const outMissing = x.isAsset ? x.gap < 0 : x.gap > 0;
      put(box, h('p', null, outMissing ? `About ${money(Math.abs(x.gap), cur)} of money out is missing here, or money in is kept twice.` : `About ${money(Math.abs(x.gap), cur)} of money in is missing here, or money out is kept twice.`,
        x.pending ? ` (${money(x.pending, cur)} is pending.)` : ''));
      if (x.weeks.length) {
        put(box, h('ul', { class: 'balw' }, x.weeks.map((k) => h('li', null, h('span', null, `${fmtDay(k.from)} to ${fmtDay(k.to, true)}`), h('span', { class: 'num' }, `${k.change > 0 ? '+' : ''}${money(k.change, cur)}`),
          h('a', { class: 'lnk small', href: `#/transactions?${new URLSearchParams({ account: x.id, month: k.to.slice(0, 7), hid: '1' })}` }, `The transactions of ${fmtMonth(k.to.slice(0, 7))}`)))));
      }
      put(box, h('p', { class: 'muted small' }, 'Things to try: look for it among the ', h('a', { class: 'lnk', href: '#/duplicates' }, 'likely duplicates'),
        '; a transaction hidden in Monarch Money is not kept here and shows as a gap; syncing the account again fetches what the bank link dropped.'));
    }
    const acts = [x.status === 'gap' && can ? h('button', { class: 'pillbtn tiny', onclick: () => post(x, x.gap), title: 'Not flagged again while the gap stays the same' }, 'It is fine as it is') : null,
      x.status === 'accepted' && can ? h('button', { class: 'pillbtn tiny', onclick: () => post(x, null) }, 'Flag it again') : null,
      x.status === 'gap' && acct && may('admin') ? h('button', { class: 'pillbtn tiny', onclick: () => resyncAccount(acct) }, icon('sync', 'xs'), 'Sync this account again') : null,
      x.status === 'gap' && can ? h('a', { class: 'pillbtn tiny', href: `#/account/${x.id}/reconcile` }, icon('check', 'xs'), 'Reconcile with a statement') : null].filter(Boolean);
    if (acts.length) put(box, h('div', { class: 'chiprow', style: { marginTop: '10px' } }, acts));
    put(page, box);
  }
}

/** Recent changes: what was changed by hand, the latest first, a change to many at once as one line; each with Undo. */
async function showChanges(page) {
  const d = await api('api/changes?limit=100');
  put(page, h('div', { class: 'pagehead' }, tidyBack(), h('h1', null, 'Recent changes')));
  put(page, h('p', { class: 'muted' }, 'What was changed by hand on the transactions, the latest first; a change to many at once is one line. Undo puts the fields back as they were. ',
    'Kept for 400 days. What the rules and the syncs change is not listed.'));
  if (!d.items.length) { put(page, h('div', { class: 'empty' }, icon('history'), h('p', null, 'No changes yet.'))); return; }
  const undo = async (g) => {
    try { const r = await api('api/changes/undo', { method: 'POST', json: g.batch ? { batch: g.batch } : { id: g.id } }); S.cats = []; S.tags = null; toast(`${plural(r.undone, 'transaction')} put back`); await refreshSummary(); onRoute(); } catch (e) { fail(e); }
  };
  put(page, h('ul', { class: 'rows flat changes' }, d.items.map((g) => {
    const c = g.changes[0], t = c.transaction;
    const title = g.count === 1 ? h('a', { class: 'lnk', href: `#/transaction/${t.id}` }, `${t.payee || '(no payee)'} · ${fmtDay(t.day, true)} · ${money(t.amount, t.currency)}`)
      : `${g.count} transactions at once: ${g.changes.map((x) => x.transaction.payee || '(no payee)').filter((x, i, xs) => xs.indexOf(x) === i).join(', ')}${g.count > g.changes.length ? '…' : ''}`;
    return h('li', { class: g.undone ? 'off' : null }, h('div', { class: 'r' },
      h('span', { class: 'main' }, h('b', null, title), h('small', null, [HIST_WHAT[g.what] || g.what, g.by, agoSec(g.secondsAgo), g.count === 1 ? t.account : null].filter(Boolean).join(' · ')),
        h('span', { class: 'hfs' }, histFields(c))),
      g.undone ? h('span', { class: 'tag' }, 'Taken back') : null,
      g.canUndo ? h('button', { class: 'pillbtn tiny', onclick: () => undo(g) }, icon('undo', 'xs'), 'Undo') : null));
  })));
}

/** On the Rules page: beside each rule what it did to the transactions of the past two years (and whether it does
    nothing), and above the list the rules that seem to be missing. */
function drawUpkeep(page, sug, u) {
  for (const r of u.rules) {
    const el = page.querySelector(`li[data-rule="${r.id}"] .upk`);
    if (!el) continue;
    if (r.note === 'never' || r.note === 'behind') fill(el, ' ', h('span', { class: 'tag warn', title: r.noteText }, icon('warning', 'xs'), r.note === 'never' ? 'Matches nothing' : 'Never decides'));
    else if (r.note !== 'off') fill(el, ` · ${plural(r.matched, 'transaction')}${r.last ? `, the last on ${fmtDay(r.last, true)}` : ''}`);
  }
  if (!u.suggestions.length) return;
  fill(sug, h('div', { class: 'box sugbox' }, h('h2', null, icon('tune'), 'Rules you seem to be missing'),
    h('p', { class: 'muted small' }, 'Payees you gave the same category by hand several times, with no rule that does it.'),
    h('ul', { class: 'rows' }, u.suggestions.map((x) => {
      const li = h('li');
      const add = async () => { try { const r = await api('api/payees/category', { method: 'POST', json: { name: x.payee, category: x.category } }); S.cats = []; toast(`Rule added; ${plural(r.changed, 'transaction')} changed`); onRoute(); } catch (e) { fail(e); } };
      const not = async () => { try { await api('api/rules/suggestions/not', { method: 'POST', json: { key: x.key } }); li.remove(); if (!sug.querySelector('li')) sug.replaceChildren(); } catch (e) { fail(e); } };
      put(li, h('div', { class: 'r' }, h('span', { class: 'main' }, h('b', null, `${x.payee}: ${x.category}`),
        h('small', null, `Set by hand ${x.count} times${x.wouldChange ? `; ${plural(x.wouldChange, 'more transaction')} would follow` : ''}`)),
      u.writable ? h('span', { class: 'end acts', style: { flexDirection: 'row', gap: '6px' } }, h('button', { class: 'pillbtn primary tiny', onclick: add }, icon('add', 'xs'), 'Add the rule'), h('button', { class: 'pillbtn tiny', onclick: not }, 'No thanks')) : null));
      return li;
    }))));
}

/** A bank's file (CSV, OFX, QFX) into an account kept by hand: choose it, see what it holds (for a CSV file which
    column is what), then bring in what the account does not have yet. */
const IMPORT_FIELDS = [['date', 'Date'], ['amount', 'Amount'], ['debit', 'Money out'], ['credit', 'Money in'], ['type', 'Debit or credit'], ['payee', 'Payee'], ['notes', 'Notes'], ['category', 'Category']];
async function importDialog(a) {
  const file = h('input', { type: 'file', accept: '.csv,.ofx,.qfx,.qbo,.txt,text/csv' });
  const ok = await dialog(`Import a bank file into ${a.name}`, h('div', null,
    h('p', { class: 'muted' }, 'A file of transactions from the bank’s website: CSV, OFX or QFX (Quicken). What the account has already is left out.'), file),
  [{ label: 'Cancel', value: false }, { label: 'Next', value: true, primary: true }]);
  if (!ok) return;
  const fl = file.files[0];
  if (!fl) { toast('Choose a file first'); return; }
  if (fl.size > 20 * 1048576) { toast('That file is over 20 MB'); return; }
  const buf = await fl.arrayBuffer();
  let text; try { text = new TextDecoder('utf-8', { fatal: true }).decode(buf); } catch { text = new TextDecoder('windows-1252').decode(buf); }
  const o = { mapping: null, dateOrder: null, flip: false, duplicates: false, balance: 'move', cols: false };
  const send = (preview) => api(`api/accounts/${a.id}/import`, { method: 'POST', json: { name: fl.name, text, preview, flip: o.flip, duplicates: o.duplicates, balance: o.balance,
    ...(o.mapping ? { mapping: o.mapping } : {}), ...(o.dateOrder ? { dateOrder: o.dateOrder } : {}) } });
  let p;
  try { p = await send(true); } catch (e) { fail(e); return; }
  const box = h('div', { class: 'impbox' });
  const again = async () => { try { p = await send(true); } catch (e) { fail(e); } draw(); };
  const draw = () => {
    const adds = o.duplicates ? p.total : p.new;
    const csv = p.kind === 'csv';
    const colSel = (k) => h('select', { class: 't', onchange: (e) => { o.mapping = { ...(o.mapping || p.mapping) }; if (e.target.value === '') delete o.mapping[k]; else o.mapping[k] = +e.target.value; again(); } },
      h('option', { value: '' }, 'Not in the file'), p.columns.map((c, i) => h('option', { value: i, selected: p.mapping[k] === i ? true : null }, `${c || `Column ${i + 1}`}${p.sample[0] && p.sample[0][i] ? ` (${String(p.sample[0][i]).slice(0, 18)})` : ''}`)));
    fill(box,
      p.needs ? h('p', { class: 'note warnnote' }, icon('warning', 's'), h('span', null, `${p.needs}.`))
        : h('p', null, `${plural(p.total, 'transaction')} in the file`, p.from ? `, ${fmtDay(p.from, true)} to ${fmtDay(p.to, true)}` : '', ': ', h('b', null, `${p.new} new`), p.duplicates ? `, ${p.duplicates} the account has already` : '', '.'),
      p.problemCount ? h('p', { class: 'muted small warn' }, `${plural(p.problemCount, 'line')} could not be read: `, p.problems.slice(0, 3).map((x) => `line ${x.line} (${x.why})`).join('; '), p.problemCount > 3 ? '…' : '') : null,
      csv ? h('details', { class: 'impcols', open: o.cols || p.needs ? true : null, ontoggle: (e) => { o.cols = e.target.open; } }, h('summary', null, 'Which column is what'),
        h('div', { class: 'grid' }, IMPORT_FIELDS.map(([k, l]) => fld(l, colSel(k))))) : null,
      csv ? h('div', { class: 'grid' }, fld(`Dates are written${p.guessed ? ' (a guess: check the first rows)' : ''}`, h('select', { class: 't', onchange: (e) => { o.dateOrder = e.target.value; again(); } },
        [['mdy', 'Month, day, year'], ['dmy', 'Day, month, year'], ['ymd', 'Year, month, day']].map(([v, l]) => h('option', { value: v, selected: p.dateOrder === v ? true : null }, l))), true)) : null,
      h('label', { class: 'check', style: { marginTop: '10px' } }, h('input', { type: 'checkbox', checked: o.flip ? true : null, onchange: (e) => { o.flip = e.target.checked; again(); } }), 'Money out is written as a positive number in this file (a card’s export often is)'),
      p.rows.length ? h('ul', { class: 'rows flat improws' }, p.rows.map((r) => h('li', { class: r.new ? null : 'off' }, h('div', { class: 'r' }, h('span', { class: 'day' }, fmtDay(r.day)),
        h('span', { class: 'main' }, h('b', null, r.payee || '(no payee)'), h('small', null, [r.category, r.notes].filter(Boolean).join(' · '))), r.new ? null : h('span', { class: 'tag' }, 'Already there'),
        h('span', { class: 'pt' }, amt(r.amount, a.currency)))))) : null,
      p.total > p.rows.length ? h('p', { class: 'muted small' }, `…and ${p.total - p.rows.length} more.`) : null,
      p.duplicates ? h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: o.duplicates ? true : null, onchange: (e) => { o.duplicates = e.target.checked; again(); } }), `Bring in the ${p.duplicates} the account has already too`) : null,
      !p.needs ? h('div', { class: 'grid', style: { marginTop: '10px' } }, fld(`The account’s balance (now ${money(a.balance, a.currency)})`, h('select', { class: 't', onchange: (e) => { o.balance = e.target.value; } },
        [['move', `Moves by what comes in (${money(p.sum, a.currency)})`], ['keep', 'Stays as it is'], p.fileBalance != null ? ['file', `Becomes the file’s balance (${money(p.fileBalance, a.currency)})`] : null].filter(Boolean)
          .map(([v, l]) => h('option', { value: v, selected: o.balance === v ? true : null }, l))), true)) : null,
      h('p', { class: 'muted small' }, adds ? `${plural(adds, 'transaction')} will come in. The rules apply to them, and transfers are linked.` : 'Nothing to bring in.'));
  };
  for (;;) {
    draw();
    if (!await dialog(`Import ${fl.name}`, box, [{ label: 'Cancel', value: false }, { label: 'Import', value: true, primary: true }], 'wide')) return;
    if (p.needs) { toast(p.needs); continue; }
    if (!(o.duplicates ? p.total : p.new)) { toast('Nothing to bring in'); return; }
    break;
  }
  try {
    const r = await send(false);
    S.cats = []; toast(`${plural(r.added, 'transaction')} imported`);
    await refreshSummary();
    if (location.hash === `#/account/${a.id}`) onRoute(); else location.hash = `#/account/${a.id}`;
  } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ spending: by category, and month by month
async function showSpending(page, r) {
  const m = r.month;
  const [s, cf] = await Promise.all([api(`api/spending?month=${m}`), api('api/cashflow?months=12')]);
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Spending'), h('span', { class: 'grow' }),
    h('a', { class: 'iconbtn', href: `#/spending/${shiftMonth(m, -1)}`, title: 'The month before' }, icon('prev')),
    h('b', { style: { minWidth: '140px', textAlign: 'center' } }, fmtMonth(m)),
    m < thisMonth() ? h('a', { class: 'iconbtn', href: `#/spending/${shiftMonth(m, 1)}`, title: 'The month after' }, icon('next')) : h('span', { class: 'iconbtn' })));
  put(page, h('div', { class: 'cards' },
    h('div', { class: 'stat' }, h('div', { class: 'lbl' }, 'Money out'), h('div', { class: 'val num neg' }, money(s.spent, s.currency))),
    h('div', { class: 'stat' }, h('div', { class: 'lbl' }, 'Money in'), h('div', { class: 'val num pos' }, money(s.income, s.currency))),
    h('div', { class: 'stat' }, h('div', { class: 'lbl' }, 'Left over'), h('div', { class: `val num ${tone(s.net)}` }, money(s.net, s.currency)))));
  const outs = s.categories.filter((c) => c.spent > c.income).map((c) => ({ ...c, v: c.spent - c.income }));
  const max = Math.max(1, ...outs.map((c) => c.v));
  put(page, h('div', { class: 'box' }, h('h2', null, icon('pie'), 'Where it went'),
    outs.length ? h('div', { class: 'bars' }, outs.map((c) => bar(c.category || 'Uncategorized', c.v, max, { cur: s.currency, sub: c.group && c.group !== c.category ? c.group : null, hueVar: '--c-rose',
      href: `#/transactions?${new URLSearchParams({ month: m, category: c.category || '-' })}` }))) : h('p', { class: 'muted' }, 'Nothing spent this month (transfers between your own accounts are left out).')));
  put(page, h('div', { class: 'box' }, h('h2', null, icon('trend'), 'The past twelve months'),
    h('div', { class: 'legend' }, h('span', null, h('i', { style: { background: 'var(--ok)' } }), 'In'), h('span', null, h('i', { style: { background: 'var(--danger)' } }), 'Out')),
    flowChart(cf.items, { cur: cf.currency })));
}

// ------------------------------------------------------------------ the portfolio
async function drawHoldings(page, accountId, account) {
  const p = await api(`api/portfolio${accountId ? `?account=${accountId}` : ''}`);
  if (!accountId) {
    put(page, h('div', { class: 'hero' },
      h('div', null, h('div', { class: 'lbl' }, 'Portfolio'), h('div', { class: 'big num' }, money(p.value, p.currency))),
      p.dayChange != null ? h('div', { class: `chg num ${tone(p.dayChange)}` }, `${money(p.dayChange, p.currency, { sign: true })} (${pct(p.dayChangePct)})`, h('small', { class: 'muted' }, ' today')) : null,
      p.gain != null ? h('div', { class: `chg num ${tone(p.gain)}` }, `${money(p.gain, p.currency, { sign: true })}`, h('small', { class: 'muted' }, ' over cost')) : null));
    const days = store.get('range') || '365';
    const hist = await api(`api/networth?days=${days}&kind=investment`);
    put(page, lineChart(hist.history));
    const max = Math.max(1, ...p.allocation.map((a) => a.value));
    if (p.allocation.length > 1) put(page, h('div', { class: 'box' }, h('h2', null, icon('pie'), 'Allocation'), h('div', { class: 'bars' }, p.allocation.map((a) => bar(HOLDING_LABEL[a.kind] || a.kind, a.value, max, { cur: p.currency, hueVar: '--c-indigo', sub: p.value ? `${(a.value / p.value * 100).toFixed(1)}%` : null })))));
  }
  const byAccount = !accountId && store.get('bysymbol') !== '1';
  const rows = accountId || byAccount ? p.items : p.bySymbol;
  const head = h('div', { class: 'pagehead' }, h('h2', { style: { margin: 0 } }, 'Holdings'), h('span', { class: 'grow' }),
    !accountId ? h('div', { class: 'segs' }, h('button', { class: byAccount ? 'on' : null, onclick: () => { store.set('bysymbol', '0'); onRoute(); } }, 'By account'), h('button', { class: !byAccount ? 'on' : null, onclick: () => { store.set('bysymbol', '1'); onRoute(); } }, 'By symbol')) : null,
    h('button', { class: 'pillbtn tiny', onclick: refreshQuotes }, icon('sync', 'xs'), 'Quotes'),
    (account ? account.writable && account.source === 'manual' : S.accounts.some((a) => a.kind === 'investment' && a.source === 'manual' && a.writable)) ? h('button', { class: 'pillbtn tiny', onclick: () => holdingDialog(null, accountId) }, icon('add', 'xs'), 'Holding') : null);
  put(page, head);
  if (!rows.length) { put(page, h('p', { class: 'muted' }, accountId ? 'Nothing held here.' : 'No holdings yet: they come with Monarch Money’s investment accounts, or add a manual investment account and what it holds.')); return; }
  const th = (l, r) => h('th', { class: r ? 'r' : null }, l);
  const table = h('table', { class: 't' }, h('thead', null, h('tr', null, th('Symbol'), th('Name'), !accountId && byAccount ? th('Account') : null, th('Shares', 1), th('Price', 1), th('Today', 1), th('Value', 1), accountId || byAccount ? th('Gain', 1) : null)),
    h('tbody', null, rows.map((x) => h('tr', { class: x.id && x.writable ? 'click' : null, onclick: x.id && x.writable ? () => holdingDialog(x) : null, title: x.quoteError ? `No quote: ${x.quoteError}` : null },
      h('td', { class: 'sym' }, x.symbol || '—', x.quoteError ? [' ', icon('warning', 'xs warn')] : null), h('td', { class: 'nm' }, x.name || ''),
      !accountId && byAccount ? h('td', null, x.account) : null,
      h('td', { class: 'r num' }, qty(x.shares)), h('td', { class: 'r num' }, x.price != null ? money(x.price, x.currency) : '—'),
      h('td', { class: `r num ${tone(x.dayChangePct)}` }, x.dayChangePct != null ? pct(x.dayChangePct) : ''),
      h('td', { class: 'r num' }, money(x.homeValue, CUR())),
      accountId || byAccount ? h('td', { class: `r num ${tone(x.gain)}` }, x.gain != null ? money(x.gain, CUR(), { sign: true }) : '') : null))));
  put(page, h('div', { class: 'tablewrap' }, table));
}
async function showPortfolio(page) {
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Portfolio')));
  await drawHoldings(page, null);
}
async function refreshQuotes() {
  toast('Asking for the latest quotes…');
  try { const r = await api('api/quotes/refresh', { method: 'POST' }); toast(r.failed ? `${r.asked} quotes asked, ${r.failed} not found` : 'Quotes up to date'); onRoute(); } catch (e) { fail(e); }
}
async function holdingDialog(x, accountId) {
  const isNew = !x;
  const accts = S.accounts.filter((a) => a.kind === 'investment' && a.source === 'manual' && a.writable);
  if (isNew && !accts.length) { toast('Add a manual investment account first (Add an account, kind Investments)'); return; }
  x = x || { kind: 'stock', accountId: accountId || accts[0].id };
  const f = { account: h('select', { class: 't', disabled: !isNew ? true : null }, accts.map((a) => h('option', { value: a.id, selected: a.id === x.accountId ? true : null }, a.name))),
    symbol: inp(x.symbol, { placeholder: 'AAPL, VWCE.DE, BTC-USD', style: { textTransform: 'uppercase' }, disabled: !isNew ? true : null }),
    shares: inp(x.shares, { inputmode: 'decimal' }), costBasis: inp(x.costBasis, { inputmode: 'decimal', placeholder: 'What you paid for all of them' }),
    kind: h('select', { class: 't', disabled: !isNew ? true : null }, (S.sum.holdingKinds || []).map((k) => h('option', { value: k, selected: k === x.kind ? true : null }, HOLDING_LABEL[k] || k))),
    name: inp(x.name, { placeholder: 'For something without a symbol' }), price: inp(x.quoted ? '' : x.price, { inputmode: 'decimal', placeholder: 'Without a symbol: its price' }) };
  const body = h('div', null, h('div', { class: 'grid' }, fld('Account', f.account, true), fld('Symbol', f.symbol), fld('Kind', f.kind), fld('Shares', f.shares), fld('Cost basis', f.costBasis), fld('Name', f.name), fld('Price', f.price)),
    h('p', { class: 'muted small' }, 'A symbol as Yahoo Finance writes it: AAPL on Nasdaq, VWCE.DE on Xetra, VOD.L in London, BTC-USD for bitcoin. Quotes follow on their own.'));
  const ok = await dialog(isNew ? 'Add a holding' : (x.symbol || x.name), body, [!isNew ? { label: 'Delete', value: 'delete', danger: true } : null, { label: 'Cancel', value: false }, { label: isNew ? 'Add' : 'Save', value: true, primary: true }].filter(Boolean), 'wide');
  if (ok === 'delete') { if (await confirmDialog('Delete the holding', `Delete ${x.symbol || x.name}?`, 'Delete', true)) { try { await api(`api/holdings/${x.id}`, { method: 'DELETE' }); toast('Deleted'); onRoute(); } catch (e) { fail(e); } } return; }
  if (!ok) return;
  const b = { shares: f.shares.value, costBasis: f.costBasis.value, name: f.name.value };
  if (f.price.value.trim()) b.price = f.price.value;
  if (isNew) Object.assign(b, { symbol: f.symbol.value, kind: f.kind.value });
  try {
    await api(isNew ? `api/accounts/${f.account.value}/holdings` : `api/holdings/${x.id}`, { method: isNew ? 'POST' : 'PATCH', json: b });
    toast(isNew ? 'Added' : 'Saved'); await refreshSummary(); onRoute();
  } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ house and cars
async function showAssets(page) {
  const things = (await api('api/accounts?things=true')).items || [];
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Assets'), h('span', { class: 'grow' }),
    canAdd() ? h('button', { class: 'pillbtn', onclick: () => accountDialog(null) }, icon('add'), h('span', null, 'Add')) : null));
  if (!things.length) {
    put(page, h('div', { class: 'empty' }, icon('home'), h('p', null, 'No real estate or vehicles here yet.'),
      h('p', { class: 'muted' }, 'Add them in Monarch Money (real estate from Zillow, vehicles) and they come along with the next sync, or add them here by hand with their value.')));
    return;
  }
  const total = things.filter((a) => a.inNetWorth && !a.closed).reduce((s, a) => s + (a.equity != null ? a.equity : (a.estimate != null ? a.estimate : a.balance) * (a.value / (a.balance || 1) || 1)), 0);
  put(page, h('div', { class: 'hero' }, h('div', null, h('div', { class: 'lbl' }, 'Worth, after their loans'), h('div', { class: 'big num' }, money(total)))));
  put(page, h('div', { class: 'things' }, things.map((a) => {
    const d = a.details || {};
    const v = a.estimate != null ? a.estimate : a.balance;
    return h('a', { class: 'thing', href: `#/account/${a.id}`, style: { '--hue': `var(${KIND_LOOK[a.kind][1]})` } },
      h('div', { class: 'top' }, h('span', { class: 'sic' }, icon(KIND_LOOK[a.kind][0])), h('h3', null, a.name),
        a.source === 'monarch' ? h('span', { class: 'tag', title: 'Its value comes from Monarch Money' }, 'Monarch') : a.estimate != null ? h('span', { class: 'tag est' }, 'Est.') : null),
      h('div', { class: 'val num' }, money(v, a.currency)),
      h('div', { class: 'kvs' },
        d.address ? [h('span', null, 'Address'), h('span', null, d.address)] : null,
        d.make || d.model ? [h('span', null, 'Car'), h('span', null, [d.year, d.make, d.model].filter(Boolean).join(' '))] : null,
        a.loan ? [h('span', null, a.loan.name), h('span', { class: 'num neg' }, money(-Math.abs(a.loan.balance), a.loan.currency))] : null,
        a.equity != null ? [h('span', null, 'Equity'), h('span', { class: `num ${tone(a.equity)}` }, money(a.equity))] : null,
        d.boughtFor != null ? [h('span', null, 'Bought for'), h('span', { class: 'num' }, money(d.boughtFor, a.currency), d.boughtOn ? ` in ${d.boughtOn.slice(0, 4)}` : '')] : null,
        [h('span', null, 'Updated'), h('span', null, ago(a.balanceAt))]));
  })));
}

// ------------------------------------------------------------------ settings
async function showSettings(page, r) {
  const adm = S.user.role === 'admin';
  const tabs = [['account', 'Account'], ['display', 'Display'],
    ...(adm ? [['money', 'Money'], ['server', 'Server']] : []),
    ...(S.user.suiteAdmin ? [['security', SUITE_TABS.security], ['global', SUITE_TABS.global]] : [])];
  put(page, h('div', { class: 'pagehead' }, h('h1', null, 'Settings')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/settings/${k}`; } }, l))));
  const body = h('div', { style: { maxWidth: '900px' } }); put(page, body);
  await ({ account: setAccount, display: setDisplay, money: setMoney, server: setServer, security: setSuite, global: setSuite }[r.tab] || setAccount)(body, r);
}

/** Settings › Money (admins): the household's currency, and Monarch Money: whether its sign-in is kept (in the
    suite's keys and tokens: never here), the last syncs, Sync now, a code by hand, the automatic sync. */
async function setMoney(el) {
  const [st, set] = await Promise.all([api('api/monarch'), api('api/settings')]);
  const cur = inp(set.currency, { maxlength: 3, style: { textTransform: 'uppercase', width: '90px' } });
  cur.onchange = async () => { try { await api('api/settings', { method: 'PUT', json: { currency: cur.value } }); fmts.length = 0; Object.keys(fmts).forEach((k) => delete fmts[k]); await refreshSummary(); toast('Saved'); } catch (e) { fail(e); } };
  put(el, h('div', { class: 'box' }, h('h2', null, icon('bank'), 'The household’s currency'),
    h('p', { class: 'muted' }, 'The net worth and every total are in this currency; an account or a holding in another is converted at the day’s rate (Yahoo Finance).'),
    fld('Currency (USD, EUR, GBP…)', cur)));
  const keysLink = S.user.suiteAdmin ? h('a', { class: 'lnk', href: '#/settings/global/keys' }, 'Global settings › Keys and tokens') : 'Global settings › Keys and tokens (a suite admin)';
  const K = st.keys || {};
  const keyRow = (k, l) => h('li', null, icon(K[k] ? 'check' : 'close', K[k] ? 'ok' : 'warn'), l, K[k] ? '' : ': not set');
  const last = st.last;
  const code = inp('', { inputmode: 'numeric', maxlength: 6, placeholder: '123456', style: { width: '110px' } });
  const auto = h('input', { type: 'checkbox', checked: set.monarchAuto ? true : null, onchange: async (e) => { try { await api('api/settings', { method: 'PUT', json: { monarchAuto: e.target.checked } }); toast('Saved'); } catch (x) { fail(x); } } });
  if (st.running) watchSync();
  put(el, h('div', { class: 'box' }, h('h2', null, icon('sync'), 'Monarch Money'),
    h('p', { class: 'muted' }, 'ioMoney copies in Monarch Money’s accounts, balances, transactions, holdings and bills (houses from Zillow and vehicles included) every ', st.every, ' hours. It only reads: nothing is changed in Monarch. The sign-in is kept with the suite’s keys and tokens, in ', keysLink, ':'),
    h('ul', { class: 'keylist' }, keyRow('monarch_email', 'Monarch Money email'), keyRow('monarch_password', 'Monarch Money password'),
      keyRow('monarch_mfa_secret', 'Monarch Money authenticator key (the text under the QR code when you set up the authenticator app in Monarch)'),
      h('li', null, icon(K.monarch_token ? 'check' : 'close', K.monarch_token ? 'ok' : 'muted'), K.monarch_token ? 'Signed in (a session is kept)' : 'Not signed in yet')),
    st.running ? h('p', { class: 'note syncing' }, h('span', { class: 'spin' }), ' Syncing: ', h('span', { 'data-syncstage': '' }, syncLabel(st.progress)),
      h('small', null, ` · started ${ago(st.progress && st.progress.started)}. It goes on if you leave this page.`))
      : last ? h('p', { class: `note ${last.ok ? '' : 'bad'}` }, last.ok ? `Last sync ${ago(last.finished || last.started)}: ${last.message}` : `The last sync (${ago(last.started)}) did not work: ${last.message}`) : null,
    S.sum.monarch && S.sum.monarch.newAccounts ? h('p', { class: 'note warnnote' }, icon('warning', 's'), h('span', { class: 'grow' }, `${S.sum.monarch.newAccounts} account${S.sum.monarch.newAccounts === 1 ? '' : 's'} from Monarch wait${S.sum.monarch.newAccounts === 1 ? 's' : ''} for you to say whether ${S.sum.monarch.newAccounts === 1 ? 'it is' : 'they are'} new.`),
      h('button', { class: 'pillbtn primary', onclick: () => newAccountsDialog() }, 'Review')) : null,
    h('div', { class: 'chiprow' },
      h('button', { class: 'pillbtn primary', disabled: st.running || !st.configured ? true : null, onclick: (e) => startSync(false, e.currentTarget) }, icon('sync'), h('span', null, st.running ? 'Syncing…' : 'Sync now')),
      h('button', { class: 'pillbtn', disabled: st.running || !st.configured ? true : null, onclick: (e) => startSync(true, e.currentTarget) }, h('span', null, 'Sync two years again')),
      K.monarch_token ? h('button', { class: 'pillbtn', onclick: async () => { await api('api/monarch/session', { method: 'DELETE' }); toast('The next sync signs in again'); onRoute(); } }, 'Sign in again') : null),
    h('label', { class: 'check', style: { marginTop: '12px' } }, auto, `Sync every ${st.every} hours on its own`),
    !K.monarch_mfa_secret && K.monarch_email ? h('div', { style: { marginTop: '14px' } }, h('p', { class: 'muted small' }, 'No authenticator key kept: sign in once with the code your authenticator app shows now.'),
      h('div', { class: 'chiprow' }, code, h('button', { class: 'pillbtn', onclick: async () => { try { await api('api/monarch/code', { method: 'POST', json: { code: code.value } }); toast('Signed in'); onRoute(); } catch (e) { fail(e); } } }, 'Sign in with the code'))) : null,
    st.history && st.history.length > 1 ? h('details', { style: { marginTop: '14px' } }, h('summary', { class: 'muted small' }, 'The last syncs'),
      h('ul', { class: 'keylist' }, st.history.map((x) => h('li', null, icon(x.ok ? 'check' : 'close', x.ok ? 'ok' : 'warn'), `${new Date(x.started).toLocaleString()}: ${x.message || ''}`)))) : null));
  put(el, h('div', { class: 'box' }, h('h2', null, icon('link'), 'Maintenance'),
    h('p', { class: 'muted' }, 'Go through every transaction and link the transfers between your own accounts (card payments, bank transfers, loan payments), then see what still looks like one, with why it was not linked.'),
    h('div', { class: 'chiprow' }, h('button', { class: 'pillbtn', onclick: () => transferMaintenance() }, icon('link'), h('span', null, 'Link transfers')))));
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
      h('button', { class: 'mi', onclick: async () => { const r = await api('api/auth/logout', { method: 'POST' }); if (r && r.cloudflareLogout) location.href = r.cloudflareLogout; else location.reload(); } }, icon('logout', 's'), 'Sign out'));
    put(m, menu);
    setTimeout(() => document.addEventListener('click', outside), 0);
  };
  put(m, btn);
}
/* The suite (iosuite-shared's suite_apps): when other ioThing apps are registered, the app mark top left (in the sidebar; in
   the top bar on a phone) opens a menu of them, each a link to that app. Alone, the mark stays the link to the overview. */
async function loadSuite() {
  try {
    const r = await api('api/auth/suite');
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
  put(document.body, suitePop);
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

/* The sidebar docks beside the page on a wide screen unless its button put it away (remembered); otherwise it slides
   over the page. */
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

const accountUi = () => import(new URL('api/auth/ui.js', document.baseURI).href);
/** Settings › Account: display name, email and password, then the app passwords: iosuite-shared's panels (the same in every io app). */
async function setAccount(el) {
  const ui = await accountUi();
  const pw = h('div');
  await ui.mountAccount(el, { toast, onSaved: (u) => { Object.assign(S.user, u); drawUser(); } });
  put(el, pw);
  await ui.mountAppPasswords(pw, { toast });
}

/** Settings › Display: the theme, saved with the account. */
async function setDisplay(el) {
  const ui = await accountUi();
  put(el, ui.box('theme', 'Appearance', ui.themeRow(S.settings.theme || store.get('theme') || 'system', (t) => { S.settings.theme = t; applyTheme(t); })));
}

/** Settings › Security and Global settings (suite admins): the people, their role in every app, app
    passwords, sign-in at the proxy; the apps, keys and tokens. The same panel in every io app, served by iosuite-shared. */
const SUITE_TABS = { security: 'Security', global: 'Global settings' };
async function setSuite(el, r) {
  let ui;
  try { ui = await import(new URL('api/suite-admin/ui.js', document.baseURI).href); } catch (e) { put(el, h('p', { class: 'warn' }, `The panel did not load: ${e.message}`)); return; }
  await ui.mount(el, { tab: r.tab, sub: r.sub, toast, onSub: (x) => history.replaceState(null, '', `#/settings/${r.tab}/${x}`) });
}

/** Settings › Server (admins): the MCP switch, the version and its updates, the server log and Restart
    (iosuite-shared's panel, the same in every io app). */
async function setServer(el) {
  let ui;
  try { ui = await serverUi(); } catch (e) { put(el, h('p', { class: 'warn' }, `The Server panel did not load: ${e.message}`)); return; }
  await ui.mount(el, { toast });
}
const serverUi = () => import(new URL('api/server/ui.js', document.baseURI).href);

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
    try { await api(first ? 'api/auth/setup' : 'api/auth/login', { method: 'POST', json: { name: n, password: p } }); location.reload(); } catch (x) { err.textContent = x.message; }
  };
  const submit = (e) => { e.preventDefault(); login(name.value.trim(), pw.value); };
  put(document.body, h('div', { class: 'signin' }, h('form', { class: 'dialog', onsubmit: submit },
    h('div', { class: 'brand' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }), h('span', { class: 'brand-name', style: { display: 'inline' } }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Money'))),
    first ? h('p', { class: 'muted' }, 'Welcome. Make the first account: it is the admin, who gives the rest of the household a role in Settings. (Already use another io app? Sign in there first, or use the same name and password here once the apps share their accounts.)') : h('h2', null, 'Sign in'),
    tiles, form, err, h('div', { class: 'btns' }, btn))));
  if (first) { name.focus(); return; }
  const pick = (t) => tiles.querySelectorAll('.account').forEach((x) => x.classList.toggle('on', x === t));
  api('api/auth/accounts').then((d) => {
    if (!d.accounts.length) { name.focus(); return; }
    form.hidden = true; btn.hidden = true;
    put(tiles, ...d.accounts.map((a) => {
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
  S.status = await api('api/status');
  if (!S.status.user) { showSignIn(); return; }
  S.user = S.status.user;
  try { S.settings = (await api('api/auth/me')).settings || {}; } catch { S.settings = {}; }
  if (S.settings.theme) applyTheme(S.settings.theme);
  drawUser();
  await refreshSummary();
  const nb = $('#newbtn');
  nb.hidden = !canAdd();
  nb.onclick = () => popMenu(nb, [['bank', 'An account', accountDialog],
    S.accounts.some((a) => a.writable && followsTx(a)) ? ['receipt', 'A transaction', () => txDialog()] : null,
    S.accounts.some((a) => a.kind === 'investment' && a.source === 'manual' && a.writable) ? ['trend', 'A holding', () => holdingDialog(null)] : null]);
  $('#menubtn').onclick = openNav;
  $('#navscrim').onclick = closeNav;
  $('#nav').addEventListener('click', (e) => { if (e.target.closest('a') && !document.body.classList.contains('side-docked')) closeNav(); });
  addEventListener('resize', applySidebar);
  const q = $('#q');
  q.hidden = !may('read'); $('#search').hidden = !may('read');
  let t;
  q.addEventListener('input', (e) => {
    clearTimeout(t);
    t = setTimeout(() => {
      const v = e.target.value.trim();
      if (v) location.hash = `#/transactions?${new URLSearchParams({ q: v })}`;
      else if (route().view === 'transactions') location.hash = '#/transactions';
    }, 300);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { if (openMenu) closeMenu(); else if (document.querySelector('.dialog-back')) closeDialogs(); else if (document.body.classList.contains('side-open')) closeNav(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) || document.querySelector('.signin, .dialog-back')) return;
    if (e.key === '/') { e.preventDefault(); q.focus(); }
  });
  addEventListener('hashchange', () => { document.title = 'ioMoney'; closeDialogs(); onRoute(); });
  await onRoute();
  loadSuite();
}
start().catch(fail);
