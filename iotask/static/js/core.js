import { drawNav, showSignIn } from './shell.js';
import { onRoute, refresh } from './main.js';
import { client, h, safeUrl } from '../../api/auth/ui.js';  // the suite's shared helpers (iosuite-shared static/account-panel.js)
export { h, safeUrl };
export const api = client(document.baseURI, { signIn: () => showSignIn() });

// The helpers every page uses (api, h, icon, drag to sort), dates and repeat rules, and the app's state.

// ------------------------------------------------------------------ helpers
export const $ = (s, el = document) => el.querySelector(s);
/** replaceChildren that leaves out null and false (as h() does) and flattens lists. */
export const fill = (el, ...kids) => el.replaceChildren(...kids.flat(9).filter((k) => k != null && k !== false));
/** append with the same manners. */
export const put = (el, ...kids) => el.append(...kids.flat(9).filter((k) => k != null && k !== false));
export const ICONS = {
  today: 'M19 3h-1V1h-2v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM7 10h5v5H7z',
  event: 'M17 12h-5v5h5v-5zM16 1v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2h-1V1h-2zm3 18H5V8h14v11z',
  inbox: 'M19 3H4.99C3.88 3 3 3.9 3 5v14c0 1.1.88 2 1.99 2H19c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 12h-4c0 1.66-1.35 3-3 3s-3-1.34-3-3H4.99V5H19v10z',
  done: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z',
  list: 'M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z',
  repeat: 'M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z',
  bell: 'M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z',
  flag: 'M14.4 6 14 4H5v17h2v-7h5.6l.4 2h7V6z',
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
  devices: 'M4 6h18V4H4c-1.1 0-2 .9-2 2v11H0v3h14v-3H4V6zm19 2h-6c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h6c.55 0 1-.45 1-1V9c0-.55-.45-1-1-1zm-1 9h-4v-7h4v7z',
  more: 'M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  check: 'M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z',
  chevR: 'M10 6 8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z',
  tune: 'M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 4v-2H11v2h10zm-6-4h2V7h4V5h-4V3h-2v6z',
  ai: 'M19 9l1.25-2.75L23 5l-2.75-1.25L19 1l-1.25 2.75L15 5l2.75 1.25L19 9zm-7.5.5L9 4 6.5 9.5 1 12l5.5 2.5L9 20l2.5-5.5L17 12l-5.5-2.5zM19 15l-1.25 2.75L15 19l2.75 1.25L19 23l1.25-2.75L23 19l-2.75-1.25L19 15z',
  theme: 'M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.389 5.389 0 0 1-4.4 2.26 5.403 5.403 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z',
  subtask: 'M19 15l-6 6-1.42-1.42L15.17 16H4V4h2v10h9.17l-3.59-3.58L13 9l6 6z',
  history: 'M13 3a9 9 0 0 0-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42A8.954 8.954 0 0 0 13 21a9 9 0 0 0 0-18zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z',
  later: 'M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z',
  grip: 'M11 18c0 1.1-.9 2-2 2s-2-.9-2-2 .9-2 2-2 2 .9 2 2zm-2-8c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0-6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm6 4c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  print: 'M19 8H5c-1.66 0-3 1.34-3 3v6h4v4h12v-4h4v-6c0-1.66-1.34-3-3-3zm-3 11H8v-5h8v5zm3-7c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm-1-9H6v4h12V3z',
  template: 'M19 3h-4.18C14.4 1.84 13.3 1 12 1s-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm-2 14-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z',
  sort: 'M3 18h6v-2H3v2zM3 6v2h18V6H3zm0 7h12v-2H3v2z',
};
export const icon = (n, cls = '') => { const s = document.createElement('span'); s.className = 'ic ' + cls; s.innerHTML = `<svg viewBox="0 0 24 24"><path d="${ICONS[n] || ''}"/></svg>`; return s; };

export let toastTimer;
/** A note at the foot of the page. With undo (the step a change answered with): an Undo button, for ten seconds. */
export function toast(msg, undo) {
  const t = $('#toast');
  fill(t, h('span', null, msg), undo ? h('button', { class: 'undo', onclick: () => { t.hidden = true; undoStep(undo); } }, 'Undo') : null);
  t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, undo ? 10000 : 3500);
}
export async function undoStep(batch) {
  try { await api(`api/undo/${batch}`, { method: 'POST' }); await refresh(); toast('Undone'); } catch (e) { fail(e); }
}
export const fail = (e) => toast(e.message || String(e));

export function dialog(title, body, buttons, cls = '') {
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
export const confirmDialog = (title, text, ok = 'OK', danger = false) => dialog(title, h('p', null, text), [{ label: 'Cancel', value: false }, { label: ok, value: true, primary: !danger, danger }]);
export function closeDialogs() { document.querySelectorAll('.dialog-back').forEach((d) => d.remove()); }

/** A menu that drops from a button: items are [icon, label, what it does (a function, or an address)]; a second click
    on the button, a click elsewhere, Escape or scrolling puts it away. */
export let openMenu = null;
export function closeMenu() {
  if (!openMenu) return;
  openMenu.el.remove(); document.removeEventListener('click', openMenu.outside); openMenu = null;
}
export function popMenu(btn, items) {
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

/** Drag to reorder: the children of `box` that match `item` change places among themselves, taken by the `grip` inside
    one (mouse or finger) or, without a grip, by the whole item (mouse only, once it moved a little, so a click stays a
    click). The item moves as the pointer passes its neighbours; done(ids) gets the new order of their data-id. */
export function dragSort(box, item, grip, done) {
  const items = () => [...box.children].filter((x) => x.matches(item));
  box.addEventListener('click', (e) => { if (e.target.closest('[data-dragged]')) { e.preventDefault(); e.stopPropagation(); } }, true);
  box.addEventListener('dragstart', (e) => e.preventDefault());  // a link or a picture would be dragged off as itself
  box.addEventListener('pointerdown', (e) => {
    if (e.button) return;
    const g = grip ? e.target.closest(grip) : (e.pointerType === 'mouse' ? e.target.closest(item) : null);
    const it = g && g.closest(item);
    if (!it || it.parentElement !== box) return;
    const before = items().map((x) => x.dataset.id).join();
    const y0 = e.clientY;
    let on = false;
    const start = () => { on = true; it.classList.add('dragging'); document.body.classList.add('sorting'); };
    if (grip) { e.preventDefault(); start(); }
    const move = (ev) => {
      if (!on) { if (Math.abs(ev.clientY - y0) < 6) return; start(); }
      ev.preventDefault();
      const others = items().filter((x) => x !== it);
      const next = others.find((x) => { const r = x.getBoundingClientRect(); return ev.clientY < r.top + r.height / 2; });
      if (next) { if (it.nextElementSibling !== next) box.insertBefore(it, next); }
      else if (others.length && others[others.length - 1].nextElementSibling !== it) others[others.length - 1].after(it);
    };
    const up = () => {
      removeEventListener('pointermove', move); removeEventListener('pointerup', up); removeEventListener('pointercancel', up);
      if (!on) return;
      it.classList.remove('dragging'); document.body.classList.remove('sorting');
      it.dataset.dragged = '1'; setTimeout(() => { delete it.dataset.dragged; }, 60);
      const after = items().map((x) => x.dataset.id);
      if (after.join() !== before) done(after.map(Number));
    };
    addEventListener('pointermove', move, { passive: false }); addEventListener('pointerup', up); addEventListener('pointercancel', up);
  });
}

export const hue = (s) => { let x = 0; for (const c of s || '') x = (x * 31 + c.charCodeAt(0)) % 360; return x; };
export const initials = (fn) => { const p = (fn || '?').trim().split(/\s+/); return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase(); };
export async function copyText(t) { try { await navigator.clipboard.writeText(t); toast('Copied'); } catch { toast(t); } }
export const copyRow = (v) => h('div', { class: 'copy' }, h('code', null, v), h('button', { class: 'iconbtn', title: 'Copy', onclick: () => copyText(v) }, icon('copy', 's')));
export const store = { get: (k) => { try { return localStorage.getItem(`iotask.${k}`); } catch { return null; } }, set: (k, v) => { try { localStorage.setItem(`iotask.${k}`, v); } catch { /* private mode */ } } };

// ------------------------------------------------------------------ dates
export const pad2 = (n) => String(n).padStart(2, '0');
export const ymd = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
export const hm = (d) => `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
export const parseDay = (s) => { const [y, m, d] = s.slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d); };
export const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
export const dayStart = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
export const fmtTime = (d) => d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
export const LOCAL_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
export const TZQ = `tz=${encodeURIComponent(LOCAL_TZ)}`;  // whose "today" the server counts with
export const DOW = (i, style = 'short') => new Date(2026, 1, 1 + i).toLocaleDateString([], { weekday: style }); // 1 Feb 2026 is a Sunday
export const RDAY = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'];

/** A task's due as a Date (all-day: local midnight), or null. */
export const dueOf = (t) => (t.due ? (t.dueAllDay ? parseDay(t.due) : new Date(t.due)) : null);
/** Open and past its time (a timed task) or its day (an all-day one). */
export function isLate(t) {
  const d = dueOf(t);
  if (!d || t.done) return false;
  return t.dueAllDay ? d < dayStart(new Date()) : d < new Date();
}
/** A day in words: Today, Tomorrow, Yesterday, a weekday this week, else the date. */
export function dayWords(d) {
  const t = dayStart(new Date()), n = Math.round((dayStart(d) - t) / 864e5);
  if (n === 0) return 'Today';
  if (n === 1) return 'Tomorrow';
  if (n === -1) return 'Yesterday';
  if (n > 1 && n < 7) return d.toLocaleDateString([], { weekday: 'long' });
  return d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric', year: d.getFullYear() !== t.getFullYear() ? 'numeric' : undefined });
}
export const dueText = (t) => { const d = dueOf(t); return d ? dayWords(d) + (t.dueAllDay ? '' : `, ${fmtTime(d)}`) : ''; };
export const ordinal = (n) => ({ 1: 'first', 2: 'second', 3: 'third', 4: 'fourth', 5: 'fifth', '-1': 'last' })[n] || `${n}th`;

/** A repeat rule (RRULE) in words. */
export function describeRule(rule, day) {
  if (!rule) return '';
  const p = Object.fromEntries(rule.split(';').map((x) => x.split('=')));
  const n = +(p.INTERVAL || 1);
  const unit = { DAILY: 'day', WEEKLY: 'week', MONTHLY: 'month', YEARLY: 'year', HOURLY: 'hour' }[p.FREQ] || (p.FREQ || '').toLowerCase();
  let s = n === 1 ? `Every ${unit}` : `Every ${n} ${unit}s`;
  if (p.FREQ === 'DAILY' && n === 1) s = 'Daily';
  if (p.FREQ === 'WEEKLY' && p.BYDAY) {
    const days = p.BYDAY.split(',');
    if (days.length === 5 && ['MO', 'TU', 'WE', 'TH', 'FR'].every((d) => days.includes(d))) s = n === 1 ? 'Every weekday' : `${s} on weekdays`;
    else s += ' on ' + days.map((d) => DOW(RDAY.indexOf(d), 'long')).join(', ');
  }
  if (p.FREQ === 'MONTHLY') {
    if (p.BYDAY) { const m = p.BYDAY.match(/^(-?\d)?([A-Z]{2})$/); if (m) s += ` on the ${ordinal(m[1] || 1)} ${DOW(RDAY.indexOf(m[2]), 'long')}`; }
    else if (p.BYMONTHDAY) s += ` on day ${p.BYMONTHDAY}`;
    else if (day) s += ` on day ${day.getDate()}`;
  }
  if (p.COUNT) s += `, ${p.COUNT} more times`;
  if (p.UNTIL) { const u = p.UNTIL; s += `, until ${parseDay(`${u.slice(0, 4)}-${u.slice(4, 6)}-${u.slice(6, 8)}`).toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' })}`; }
  return s;
}

/* A task that repeats after completion comes back some time after the day it is ticked off: "P2W" (an ISO 8601
   duration of days, weeks, months or years) is two weeks. The form shows it as the repeat rule of that length. */
export const AFTER_UNIT = { D: 'DAILY', W: 'WEEKLY', M: 'MONTHLY', Y: 'YEARLY' };
export const afterParts = (p) => { const m = /^P(\d+)([DWMY])$/.exec(p || ''); return m ? [+m[1], m[2]] : null; };
export const afterRule = (p) => { const a = afterParts(p); return a ? `FREQ=${AFTER_UNIT[a[1]]}${a[0] > 1 ? `;INTERVAL=${a[0]}` : ''}` : ''; };
/** A rule that is only "every n days, weeks, months or years" as such a duration (null: it says more than that). */
export function afterOf(rule) {
  const p = Object.fromEntries((rule || '').split(';').map((x) => x.split('=')));
  const u = Object.keys(AFTER_UNIT).find((k) => AFTER_UNIT[k] === p.FREQ);
  return u && Object.keys(p).every((k) => k === 'FREQ' || k === 'INTERVAL') ? `P${+p.INTERVAL || 1}${u}` : null;
}
export function describeAfter(p) {
  const a = afterParts(p);
  if (!a) return '';
  const unit = { D: 'day', W: 'week', M: 'month', Y: 'year' }[a[1]];
  return `${a[0] === 1 ? `A ${unit}` : `${a[0]} ${unit}s`} after it is ticked off`;
}
/** Where a task can be put off to: [label, day]; Today only for what is overdue. */
export function laterDays(withToday) {
  const t = dayStart(new Date()), wd = t.getDay();
  return [withToday ? ['Today', t] : null, ['Tomorrow', addDays(t, 1)], ['This weekend', addDays(t, (6 - wd + 7) % 7 || 7)],
    ['Next week', addDays(t, (8 - wd) % 7 || 7)]].filter(Boolean);
}

// ------------------------------------------------------------------ state
export const S = { status: {}, user: null, suite: [], settings: {}, lists: [], counts: {}, members: [], who: new Set(), q: '' };
// the suite's roles, each able to do what the one before can: a viewer only looks, a member keeps their own lists,
// an editor changes the shared ones too
export const RANK = { none: 0, viewer: 1, member: 2, editor: 3, admin: 4 };
export const roleAtLeast = (r) => (RANK[S.user && S.user.role] || 0) >= RANK[r];
export const canOwn = () => roleAtLeast('member');
export const canShared = () => roleAtLeast('editor');
export const listOf = (id) => S.lists.find((c) => c.id === id) || {};
export const writable = () => S.lists.filter((c) => c.writable);
/** Where a new task goes when no list is open: the one chosen in Settings › Display, else your own first list. */
export function defaultList() {
  const w = writable();
  return w.find((c) => c.id === +S.settings.defaultList) || w.find((c) => c.mine) || w[0] || null;
}
export const memberOf = (id) => S.members.find((m) => m.id === id);
/** Each family member's colour, initials and face are the suite's (Settings › Security › Family), the same in every io app. */
export const memberColor = (m) => m.color || '#5f6b7a';
/** A member's badge: their initials on their colour; `face`: their face (ioPix, else their ioContact card) when they have one. */
export const memberBadge = (m, face = false) => h('span', { class: `mem${face && m.hasFace ? ' face' : ''}`, title: m.displayName, style: { '--mc': memberColor(m) } }, m.initials || initials(m.displayName),
  face && m.hasFace ? h('img', { src: `api/auth/family/${m.id}/face`, alt: '', loading: 'lazy', onerror: (e) => { e.currentTarget.parentNode.classList.remove('face'); e.currentTarget.remove(); } }) : null);
export function toggleWho(id) {
  if (id == null) S.who.clear(); else if (S.who.has(id)) S.who.delete(id); else S.who.add(id);
  saveSettings({ memberFilter: [...S.who].join(',') });
  onRoute();
}

export async function loadLists() {
  const [lists, fam, counts] = await Promise.all([api(`api/lists?${TZQ}`), api('api/members').catch(() => ({ items: S.members })), api(`api/counts?${TZQ}`).catch(() => S.counts)]);
  S.lists = lists.items;
  S.members = fam.items || [];
  S.counts = counts || {};
  for (const id of [...S.who]) if (!memberOf(id)) S.who.delete(id);
  $('#newbtn').hidden = !writable().length;
  drawNav();
}
export async function saveSettings(changes) {
  Object.assign(S.settings, changes);
  try { await api('api/auth/settings', { method: 'POST', json: changes }); } catch { /* kept for this visit */ }
}
