/* ioTask web app: one module, no build step. The smart lists (Today, Scheduled, All, Completed) and the lists to
   pick in the sidebar; a list of tasks with a box to tick each off, a new-task line that reads plain English, subtasks
   under their task, postponing, the order by hand (drag); the task form (due date and time, repeat, alert, priority,
   the family members it is for, notes, link); the activity log with undo, templates, a print view; search, import,
   and settings (account, display, apps and devices, lists, and for admins family and server, and for suite admins
   security and global settings), laid out as in the other ioThing apps. */

// ------------------------------------------------------------------ helpers
const $ = (s, el = document) => el.querySelector(s);
/** replaceChildren that leaves out null and false (as h() does) and flattens lists. */
const fill = (el, ...kids) => el.replaceChildren(...kids.flat(9).filter((k) => k != null && k !== false));
/** append with the same manners. */
const put = (el, ...kids) => el.append(...kids.flat(9).filter((k) => k != null && k !== false));
const ICONS = {
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
  update: 'M21 10.12h-6.78l2.74-2.82c-2.73-2.7-7.15-2.8-9.88-.1a6.875 6.875 0 0 0 0 9.79 7.02 7.02 0 0 0 9.88 0C18.32 15.65 19 14.08 19 12.1h2c0 1.98-.88 4.55-2.64 6.29-3.51 3.48-9.21 3.48-12.72 0-3.5-3.47-3.53-9.11-.02-12.58a8.987 8.987 0 0 1 12.65 0L21 3v7.12z',
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
/** A note at the foot of the page. With undo (the step a change answered with): an Undo button, for ten seconds. */
function toast(msg, undo) {
  const t = $('#toast');
  fill(t, h('span', null, msg), undo ? h('button', { class: 'undo', onclick: () => { t.hidden = true; undoStep(undo); } }, 'Undo') : null);
  t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, undo ? 10000 : 3500);
}
async function undoStep(batch) {
  try { await api(`/api/undo/${batch}`, { method: 'POST' }); await refresh(); toast('Undone'); } catch (e) { fail(e); }
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

/** Drag to reorder: the children of `box` that match `item` change places among themselves, taken by the `grip` inside
    one (mouse or finger) or, without a grip, by the whole item (mouse only, once it moved a little, so a click stays a
    click). The item moves as the pointer passes its neighbours; done(ids) gets the new order of their data-id. */
function dragSort(box, item, grip, done) {
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

const hue = (s) => { let x = 0; for (const c of s || '') x = (x * 31 + c.charCodeAt(0)) % 360; return x; };
const initials = (fn) => { const p = (fn || '?').trim().split(/\s+/); return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase(); };
async function copyText(t) { try { await navigator.clipboard.writeText(t); toast('Copied'); } catch { toast(t); } }
const copyRow = (v) => h('div', { class: 'copy' }, h('code', null, v), h('button', { class: 'iconbtn', title: 'Copy', onclick: () => copyText(v) }, icon('copy', 's')));
const safeUrl = (u) => /^(https?:\/\/|mailto:)/i.test(u || '');  // a link that is a link (never javascript:)
const store = { get: (k) => { try { return localStorage.getItem(`iotask.${k}`); } catch { return null; } }, set: (k, v) => { try { localStorage.setItem(`iotask.${k}`, v); } catch { /* private mode */ } } };

// ------------------------------------------------------------------ dates
const pad2 = (n) => String(n).padStart(2, '0');
const ymd = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
const hm = (d) => `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
const parseDay = (s) => { const [y, m, d] = s.slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d); };
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const dayStart = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const sameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
const fmtTime = (d) => d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
const LOCAL_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
const TZQ = `tz=${encodeURIComponent(LOCAL_TZ)}`;  // whose "today" the server counts with
const DOW = (i, style = 'short') => new Date(2026, 1, 1 + i).toLocaleDateString([], { weekday: style }); // 1 Feb 2026 is a Sunday
const RDAY = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'];

/** A task's due as a Date (all-day: local midnight), or null. */
const dueOf = (t) => (t.due ? (t.dueAllDay ? parseDay(t.due) : new Date(t.due)) : null);
/** Open and past its time (a timed task) or its day (an all-day one). */
function isLate(t) {
  const d = dueOf(t);
  if (!d || t.done) return false;
  return t.dueAllDay ? d < dayStart(new Date()) : d < new Date();
}
/** A day in words: Today, Tomorrow, Yesterday, a weekday this week, else the date. */
function dayWords(d) {
  const t = dayStart(new Date()), n = Math.round((dayStart(d) - t) / 864e5);
  if (n === 0) return 'Today';
  if (n === 1) return 'Tomorrow';
  if (n === -1) return 'Yesterday';
  if (n > 1 && n < 7) return d.toLocaleDateString([], { weekday: 'long' });
  return d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric', year: d.getFullYear() !== t.getFullYear() ? 'numeric' : undefined });
}
const dueText = (t) => { const d = dueOf(t); return d ? dayWords(d) + (t.dueAllDay ? '' : `, ${fmtTime(d)}`) : ''; };
const ordinal = (n) => ({ 1: 'first', 2: 'second', 3: 'third', 4: 'fourth', 5: 'fifth', '-1': 'last' })[n] || `${n}th`;

/** A repeat rule (RRULE) in words. */
function describeRule(rule, day) {
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
const AFTER_UNIT = { D: 'DAILY', W: 'WEEKLY', M: 'MONTHLY', Y: 'YEARLY' };
const afterParts = (p) => { const m = /^P(\d+)([DWMY])$/.exec(p || ''); return m ? [+m[1], m[2]] : null; };
const afterRule = (p) => { const a = afterParts(p); return a ? `FREQ=${AFTER_UNIT[a[1]]}${a[0] > 1 ? `;INTERVAL=${a[0]}` : ''}` : ''; };
/** A rule that is only "every n days, weeks, months or years" as such a duration (null: it says more than that). */
function afterOf(rule) {
  const p = Object.fromEntries((rule || '').split(';').map((x) => x.split('=')));
  const u = Object.keys(AFTER_UNIT).find((k) => AFTER_UNIT[k] === p.FREQ);
  return u && Object.keys(p).every((k) => k === 'FREQ' || k === 'INTERVAL') ? `P${+p.INTERVAL || 1}${u}` : null;
}
function describeAfter(p) {
  const a = afterParts(p);
  if (!a) return '';
  const unit = { D: 'day', W: 'week', M: 'month', Y: 'year' }[a[1]];
  return `${a[0] === 1 ? `A ${unit}` : `${a[0]} ${unit}s`} after it is ticked off`;
}
/** Where a task can be put off to: [label, day]; Today only for what is overdue. */
function laterDays(withToday) {
  const t = dayStart(new Date()), wd = t.getDay();
  return [withToday ? ['Today', t] : null, ['Tomorrow', addDays(t, 1)], ['This weekend', addDays(t, (6 - wd + 7) % 7 || 7)],
    ['Next week', addDays(t, (8 - wd) % 7 || 7)]].filter(Boolean);
}

// ------------------------------------------------------------------ state
const S = { status: {}, user: null, suite: [], settings: {}, lists: [], counts: {}, members: [], who: new Set(), q: '' };
// the suite's roles, each able to do what the one before can: a viewer only looks, a member keeps their own lists,
// an editor changes the shared ones too
const RANK = { none: 0, viewer: 1, member: 2, editor: 3, admin: 4 };
const roleAtLeast = (r) => (RANK[S.user && S.user.role] || 0) >= RANK[r];
const canOwn = () => roleAtLeast('member');
const canShared = () => roleAtLeast('editor');
const listOf = (id) => S.lists.find((c) => c.id === id) || {};
const colorOf = (id) => listOf(id).color || 'var(--brand)';
const writable = () => S.lists.filter((c) => c.writable);
/** Where a new task goes when no list is open: the one chosen in Settings › Display, else your own first list. */
function defaultList() {
  const w = writable();
  return w.find((c) => c.id === +S.settings.defaultList) || w.find((c) => c.mine) || w[0] || null;
}
const memberOf = (id) => S.members.find((m) => m.id === id);
/** Each family member's colour, initials and face are the suite's (Settings › Security › Family), the same in every io app. */
const memberColor = (m) => m.color || '#5f6b7a';
/** A member's badge: their initials on their colour; `face`: their face (ioPix, else their ioContact card) when they have one. */
const memberBadge = (m, face = false) => h('span', { class: `mem${face && m.hasFace ? ' face' : ''}`, title: m.displayName, style: { '--mc': memberColor(m) } }, m.initials || initials(m.displayName),
  face && m.hasFace ? h('img', { src: `api/auth/family/${m.id}/face`, alt: '', loading: 'lazy', onerror: (e) => { e.currentTarget.parentNode.classList.remove('face'); e.currentTarget.remove(); } }) : null);
function toggleWho(id) {
  if (id == null) S.who.clear(); else if (S.who.has(id)) S.who.delete(id); else S.who.add(id);
  saveSettings({ memberFilter: [...S.who].join(',') });
  onRoute();
}

async function loadLists() {
  const [lists, fam, counts] = await Promise.all([api(`/api/lists?${TZQ}`), api('/api/members').catch(() => ({ items: S.members })), api(`/api/counts?${TZQ}`).catch(() => S.counts)]);
  S.lists = lists.items;
  S.members = fam.items || [];
  S.counts = counts || {};
  for (const id of [...S.who]) if (!memberOf(id)) S.who.delete(id);
  $('#newbtn').hidden = !writable().length;
  drawNav();
}
async function saveSettings(changes) {
  Object.assign(S.settings, changes);
  try { await api('/api/auth/settings', { method: 'POST', json: changes }); } catch { /* kept for this visit */ }
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
   the top bar on a phone) opens a menu of them, each a link to that app. Alone, the mark stays the link to Today. */
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

/* The sidebar, as in the other io apps: the name on top, the smart lists, the shared lists, the family, your own lists,
   Settings at the foot. It docks beside the page on a wide screen unless its button put it away (remembered); otherwise
   it slides over the page. Phones get a bottom bar instead. */
const DOCK_MIN = 1100;
const SMART = { today: ['Today', 'today', '--c-blue'], scheduled: ['Scheduled', 'event', '--c-rose'], all: ['All', 'inbox', '--c-slate'], done: ['Completed', 'done', '--c-green'] };
function drawNav() {
  const nav = $('#nav'); const r = route();
  const link = (v, href, ic, label, n, on, hueVar) => h('a', { href, 'data-v': v, class: on ? 'on' : null, style: hueVar ? { '--hue': `var(${hueVar})` } : null },
    icon(ic), h('span', { class: 'nl' }, label), n ? h('span', { class: 'n' }, n) : null);
  const sec = (label, btn) => h('div', { class: 'navsec' }, h('span', null, label), btn || null);
  const listRow = (c) => h('a', { href: `#/list/${c.id}`, 'data-v': 'list', 'data-id': c.id, class: r.view === 'list' && r.id === c.id ? 'on' : null, style: { '--hue': c.color } },
    h('span', { class: 'ldot' }), h('span', { class: 'nl' }, c.name),
    h('span', { class: `n ${c.overdue ? 'late' : ''}`, title: c.overdue ? `${c.overdue} overdue` : null }, c.count || ''));
  const whoRow = (m) => h('a', { href: '#', 'data-v': 'who', class: `who ${S.who.has(m.id) ? 'picked' : ''}`, style: { '--mc': memberColor(m) },
    title: S.who.has(m.id) ? `Stop showing only ${m.displayName}'s tasks` : `Show only ${m.displayName}'s tasks`,
    onclick: (e) => { e.preventDefault(); toggleWho(m.id); } }, memberBadge(m, true), h('span', { class: 'nl' }, m.displayName));
  const shared = S.lists.filter((c) => c.shared), mine = S.lists.filter((c) => !c.shared);
  // the lists of a kind, in the order they were put in: drag one (with a mouse) to move it
  const group = (lists, can) => {
    const g = h('div', { class: 'navgrp' }, lists.map(listRow));
    if (can && lists.length > 1) dragSort(g, 'a', null, orderLists);
    return g;
  };
  const brandName = () => [h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Task')];
  nav.replaceChildren(...[
    h('div', { class: 'navhead' },
      S.suite.length
        ? h('div', { class: 'brand' },
          h('button', { class: 'suitebtn', title: 'ioThing apps', 'aria-label': 'ioThing apps', 'aria-haspopup': 'menu', onclick: (e) => toggleSuite(e.currentTarget) },
            h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' })),
          h('a', { class: 'brand-name', href: '#/', title: 'Today' }, brandName()))
        : h('a', { class: 'brand', href: '#/', title: 'Today' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }),
          h('span', { class: 'brand-name' }, brandName())),
      h('button', { id: 'sidebtn', class: 'iconbtn', onclick: sidebarButton })),
    Object.entries(SMART).map(([k, [label, ic, hv]]) => link(k, `#/${k}`, ic, label, k === 'done' ? null : (k === 'today' ? S.counts.today : S.counts[k]) || null, r.view === k, hv)),
    h('button', { class: 'navmore', 'data-v': 'more', title: 'More', onclick: moreSheet }, icon('more'), h('span', { class: 'nl' }, 'More')),
    h('div', { class: 'navgap' }),
    sec('Shared', canShared() ? h('button', { class: 'iconbtn', title: 'New shared list', onclick: () => newList(true) }, icon('add', 's')) : null),
    group(shared, canShared()),
    S.members.length > 1 ? [h('div', { class: 'navgap' }),
      sec('Family', S.who.size ? h('button', { class: 'pillbtn noic tiny', title: 'Show everyone again', onclick: () => toggleWho(null) }, 'Everyone') : null),
      S.members.map(whoRow)] : null,
    h('div', { class: 'navgap' }),
    canOwn() || mine.length ? sec('Mine', canOwn() ? h('button', { class: 'iconbtn', title: 'New private list', onclick: () => newList(false) }, icon('add', 's')) : null) : null,
    group(mine, canOwn()),
    h('div', { class: 'navgap' }), sec('Manage'),
    link('activity', '#/activity', 'history', 'Activity', null, r.view === 'activity', '--c-slate'),
    writable().length ? link('import', '#/import', 'upload', 'Import', null, r.view === 'import', '--c-teal') : null,
    h('div', { class: 'navfoot' }, link('settings', '#/settings', 'settings', 'Settings', null, r.view === 'settings')),
  ].flat(3).filter(Boolean));
  applySidebar();
  $('.navmore')?.classList.toggle('on', ['list', 'import', 'settings', 'search', 'activity'].includes(r.view));
}
async function orderLists(ids) {
  try { await api('/api/lists/order', { method: 'POST', json: { ids } }); await loadLists(); } catch (e) { fail(e); drawNav(); }
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
/** Phones: what the bottom bar has no room for (the lists, the family filter, import, settings). */
function moreSheet() {
  const r = route();
  const tile = (href, ic, label, hueV, on, click) => h('a', { href, class: on ? 'on' : null, style: { '--hue': hueV }, onclick: click || null }, h('span', { class: 'sic' }, icon(ic)), h('span', null, label));
  const grid = h('div', { class: 'sheetgrid' },
    S.lists.map((c) => tile(`#/list/${c.id}`, 'list', c.name, c.color, r.view === 'list' && r.id === c.id)),
    S.members.length > 1 ? S.members.map((m) => tile('#', 'person', S.who.has(m.id) ? `Only ${m.displayName}` : m.displayName, memberColor(m), S.who.has(m.id),
      (e) => { e.preventDefault(); e.stopPropagation(); closeDialogs(); toggleWho(m.id); moreSheet(); })) : null,
    tile('#/activity', 'history', 'Activity', 'var(--c-slate)', r.view === 'activity'),
    writable().length ? tile('#/import', 'upload', 'Import', 'var(--c-teal)', r.view === 'import') : null,
    tile('#/settings', 'settings', 'Settings', 'var(--c-slate)', r.view === 'settings'));
  const p = dialog('More', grid, [{ label: 'Close', value: null }]);
  grid.addEventListener('click', (e) => { const a = e.target.closest('a'); if (a && a.getAttribute('href') !== '#') closeDialogs(); });
  return p;
}

const SWATCHES = ['#146b5e', '#1a73e8', '#e0426a', '#e8710a', '#8e44d6', '#1e8e3e', '#e8a100', '#b5452f', '#4b53c7', '#5f6b7a'];
function colorPicker(value, onPick) {
  let cur = value || SWATCHES[0];
  const own = h('input', { type: 'color', value: cur, title: 'Another colour' });
  const row = h('div', { class: 'colors' });
  const draw = () => row.replaceChildren(...SWATCHES.map((c) => h('button', { type: 'button', class: c === cur ? 'on' : '', style: { '--c': c }, title: c, onclick: () => { cur = c; own.value = c; draw(); if (onPick) onPick(c); } })), own);
  own.oninput = () => { cur = own.value; draw(); };
  own.onchange = () => { if (onPick) onPick(cur); };
  draw();
  row.get = () => cur;
  return row;
}
async function newList(shared) {
  const name = h('input', { class: 't', placeholder: shared ? 'Name, e.g. Groceries or Chores' : 'Name, e.g. Work' });
  const col = colorPicker(SWATCHES[S.lists.length % SWATCHES.length]);
  const tpls = (await api('/api/templates').catch(() => ({ items: [] }))).items;
  const from = h('select', { class: 't' }, h('option', { value: '' }, 'An empty list'), tpls.map((t) => h('option', { value: t.id }, `The template ${t.name} (${t.count} tasks)`)));
  const body = h('div', { style: { display: 'grid', gap: '12px' } }, name, col, tpls.length ? h('label', { class: 'field' }, h('span', null, 'Start with'), from) : null,
    h('p', { class: 'muted small', style: { margin: 0 } }, shared ? 'Everyone in the family sees it and ticks tasks off; editors change it.' : 'Only you see it.'));
  if (!await dialog(shared ? 'New shared list' : 'New private list', body, [{ label: 'Cancel', value: false }, { label: 'Create', value: true, primary: true }])) return;
  try {
    const picked = tpls.find((t) => t.id === +from.value);
    const r = await api('/api/lists', { method: 'POST', json: { name: name.value || (picked ? picked.name : ''), shared, color: col.get() } });
    if (picked) await api(`/api/templates/${picked.id}/apply`, { method: 'POST', json: { listId: r.list.id } });
    await loadLists();
    location.hash = `#/list/${r.list.id}`;
  } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ routing
function route() {
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
const TASK_VIEWS = ['today', 'scheduled', 'all', 'done', 'list', 'search'];

async function onRoute() {
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
async function redraw() {
  const r = route();
  if (!TASK_VIEWS.includes(r.view)) return;
  const top = $('#main').scrollTop;
  const page = h('div', { class: 'page' });
  try { await drawTasks(page, r); } catch (e) { fail(e); return; }
  $('#main').replaceChildren(page);
  $('#main').scrollTop = top;
}
async function refresh() { await loadLists(); if (route().view === 'activity') await onRoute(); else await redraw(); }

// ------------------------------------------------------------------ the task lists
const showDone = (lid) => (S.settings.showCompleted || '').split(',').includes(String(lid));
function setShowDone(lid, on) {
  const s = new Set((S.settings.showCompleted || '').split(',').filter(Boolean));
  if (on) s.add(String(lid)); else s.delete(String(lid));
  saveSettings({ showCompleted: [...s].join(',') });
}

/** A list is in the order its tasks were put in by hand (the ⋯ menu of the list), or by due date. */
const byHand = (lid) => (S.settings.manualSort || '').split(',').includes(String(lid));
function setByHand(lid, on) {
  const s = new Set((S.settings.manualSort || '').split(',').filter(Boolean));
  if (on) s.add(String(lid)); else s.delete(String(lid));
  saveSettings({ manualSort: [...s].join(',') });
}

/** The tasks the view shows, from the server: [rows, title, colour, the list (list view only)]. */
async function fetchTasks(r) {
  const who = `&${TZQ}${S.who.size ? `&member=${[...S.who].join(',')}` : ''}`;
  if (r.view === 'list') {
    const c = listOf(r.id);
    if (!c.id) throw new Error('That list is not here (any more)');
    const items = (await api(`/api/tasks?list=${c.id}&status=${showDone(c.id) ? 'all' : 'open'}&limit=2000${byHand(c.id) ? '&sort=manual' : ''}${who}`)).items;
    return [items, c.name, c.color, c];
  }
  if (r.view === 'search') {
    S.q = r.q;
    if ($('#q').value !== r.q) $('#q').value = r.q;
    if (!r.q) return [[], 'Search', null, null];
    return [(await api(`/api/tasks?q=${encodeURIComponent(r.q)}&status=all&limit=300${who}`)).items, `“${r.q}”`, null, null];
  }
  const qs = { today: 'status=open&due=today', scheduled: 'status=open&due=scheduled', all: 'status=open', done: 'status=done&limit=300' }[r.view];
  return [(await api(`/api/tasks?${qs}${who}`)).items, SMART[r.view][0], `var(${SMART[r.view][2]})`, null];
}

/** The tasks without a parent among them, in the server's order, and a function that gives a task's subtasks. */
function tree(items) {
  const byUid = new Map(items.map((t) => [`${t.listId}|${t.uid}`, t]));
  const kids = new Map(), roots = [];
  for (const t of items) {
    const k = t.parent && byUid.has(`${t.listId}|${t.parent}`) ? `${t.listId}|${t.parent}` : null;
    if (k) { if (!kids.has(k)) kids.set(k, []); kids.get(k).push(t); } else roots.push(t);
  }
  return [roots, (t) => kids.get(`${t.listId}|${t.uid}`) || []];
}
/** A task with its subtasks under it (indented): one block, which is what moves when the task is dragged. */
function taskGroup(t, kidsOf, depth, o) {
  const kids = kidsOf(t);
  return h('div', { class: 'tgrp', 'data-id': t.id }, taskRow(t, { ...o, depth }),
    kids.length ? h('div', { class: 'tkids' }, kids.map((k) => taskGroup(k, kidsOf, depth + 1, o))) : null);
}
/** Put tasks off to a day (each keeps its time; the alerts follow), with Undo. */
async function postpone(ids, day) {
  try {
    const r = await api('/api/tasks/postpone', { method: 'POST', json: { ids, due: ymd(day), tz: LOCAL_TZ } });
    await refresh();
    const w = dayWords(day);
    toast(`${r.moved === 1 ? 'Now due' : `${r.moved} tasks now due`} ${/^(Today|Tomorrow)$/.test(w) ? w.toLowerCase() : w}`, r.undo);
  } catch (e) { fail(e); }
}

async function drawTasks(page, r) {
  const [items, title, color, list] = await fetchTasks(r);
  const smart = r.view !== 'list';
  const head = h('div', { class: 'pagehead tasks-head', style: color ? { '--c': color } : null },
    h('h1', null, title), h('span', { class: 'count' }, items.filter((t) => !t.done).length || ''), h('span', { class: 'grow' }),
    S.who.size ? h('button', { class: 'pillbtn noic', title: 'Show everyone’s tasks again', onclick: () => toggleWho(null) },
      `Only ${[...S.who].map(memberOf).filter(Boolean).map((m) => m.displayName).join(', ')}`) : null,
    list ? listMenu(list) : null);
  page.classList.add('taskpage');
  page.append(head);
  if (r.view === 'search' && !r.q) { page.append(h('p', { class: 'muted' }, 'Type in the search box: words from the title or the notes.')); return; }
  const canAdd = list ? list.writable : (['today', 'all', 'scheduled'].includes(r.view) && !!defaultList());
  const rows = h('div', { class: 'tasks' });
  const section = (label, cls) => h('div', { class: `tsec ${cls || ''}` }, label);
  // Overdue, with one button to put all of it (that you may change) off to today
  const overdue = () => {
    const mine = items.filter((t) => isLate(t) && listOf(t.listId).writable).map((t) => t.id);
    return h('div', { class: 'tsec late' }, h('span', null, 'Overdue'),
      mine.length ? h('button', { class: 'pillbtn noic tiny', title: 'Each keeps its time of day', onclick: () => postpone(mine, dayStart(new Date())) }, mine.length > 1 ? 'Move all to today' : 'Move to today') : null);
  };
  if (r.view === 'list') {
    const [roots, kidsOf] = tree(items);
    const hand = byHand(list.id) && list.writable;
    roots.forEach((t) => rows.append(taskGroup(t, kidsOf, 0, { grip: hand })));
    if (hand) {
      const order = (ids) => api(`/api/lists/${list.id}/order`, { method: 'POST', json: { ids } }).catch((e) => { fail(e); redraw(); });
      [rows, ...rows.querySelectorAll('.tkids')].forEach((box) => dragSort(box, '.tgrp', '.grip', order));
    }
  } else if (r.view === 'today') {
    const late = items.filter(isLate), now = items.filter((t) => !isLate(t));
    if (late.length) put(rows, overdue(), late.map((t) => taskRow(t, { showList: true })));
    if (now.length) put(rows, late.length ? section('Today') : null, now.map((t) => taskRow(t, { showList: true, noDay: true })));
  } else if (r.view === 'scheduled') {
    let last = null;
    for (const t of items) {
      const d = dueOf(t), label = isLate(t) ? 'Overdue' : dayWords(d);
      if (label !== last) { rows.append(label === 'Overdue' ? overdue() : section(label)); last = label; }
      rows.append(taskRow(t, { showList: true, noDay: label !== 'Overdue' }));
    }
  } else {
    // All, Completed and search: grouped by list, in the sidebar's order
    for (const c of S.lists) {
      const mine = items.filter((t) => t.listId === c.id);
      if (!mine.length) continue;
      rows.append(h('div', { class: 'tsec', style: { '--c': c.color } }, h('a', { href: `#/list/${c.id}` }, c.name)));
      if (r.view === 'all') { const [roots, kidsOf] = tree(mine); roots.forEach((t) => rows.append(taskGroup(t, kidsOf, 0, {}))); }
      else mine.forEach((t) => rows.append(taskRow(t, {})));
    }
  }
  if (canAdd) page.append(quickAdd(r, list));
  page.append(rows);
  if (!items.length) page.append(h('div', { class: 'empty' }, icon(r.view === 'search' ? 'search' : 'done'),
    h('p', null, r.view === 'search' ? 'Nothing matches.' : r.view === 'done' ? 'Nothing ticked off yet.' : list && showDone(list.id) ? 'No tasks.' : 'All done.')));
  if (list && !showDone(list.id)) {
    page.append(h('p', { class: 'center' }, h('button', { class: 'pillbtn noic', onclick: () => { setShowDone(list.id, true); redraw(); } }, 'Show completed')));
  } else if (list && items.some((t) => t.done)) {
    page.append(h('p', { class: 'center' }, h('button', { class: 'pillbtn noic', onclick: () => { setShowDone(list.id, false); redraw(); } }, 'Hide completed'),
      list.writable ? [' ', h('button', { class: 'pillbtn noic danger', onclick: () => clearCompleted(list) }, 'Clear completed')] : null));
  }
}

/** The ⋯ menu of a list: show completed, the order, templates, activity, print, export, import, clear completed, the
    list's settings. */
function listMenu(c) {
  return h('button', { class: 'iconbtn', title: 'More', 'aria-haspopup': 'menu', onclick: (e) => {
    const on = showDone(c.id), hand = byHand(c.id);
    popMenu(e.currentTarget, [
      ['done', on ? 'Hide completed' : 'Show completed', () => { setShowDone(c.id, !on); redraw(); }],
      ['sort', hand ? 'Sort by due date' : 'Sort by hand (drag)', () => { setByHand(c.id, !hand); redraw(); }],
      c.writable ? ['template', 'Add from a template…', () => addFromTemplate(c)] : null,
      ['template', 'Save as a template…', () => saveTemplate(c)],
      ['history', 'Activity', `#/activity?list=${c.id}`],
      ['print', 'Print', () => window.print()],
      ['download', 'Export (.ics)', `/api/lists/${c.id}/export`],
      c.writable ? ['upload', 'Import', `#/import?list=${c.id}`] : null,
      c.writable ? ['delete', 'Clear completed', () => clearCompleted(c)] : null,
      ['settings', 'List settings', `#/settings/lists/${c.id}`]]);
  } }, icon('more'));
}

/** Templates: a list's tasks kept to add again (a packing list, the weekly shop). */
async function saveTemplate(c) {
  const name = h('input', { class: 't', value: c.name });
  const shared = h('input', { type: 'checkbox', checked: c.shared && canShared() });
  const body = h('div', { style: { display: 'grid', gap: '12px' } }, h('label', { class: 'field' }, h('span', null, 'Name'), name),
    canShared() ? h('label', { class: 'check' }, shared, ' Everyone in the family can use it') : null,
    h('p', { class: 'muted small', style: { margin: 0 } }, 'Every task of the list with its notes, priority, link, people and subtasks. Due dates, repeats and what is ticked off are left out.'));
  if (!await dialog('Save as a template', body, [{ label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }])) return;
  try {
    const r = await api('/api/templates', { method: 'POST', json: { name: name.value, listId: c.id, shared: shared.checked } });
    toast(`Template ${r.template.name} saved (${r.template.count} tasks)`);
  } catch (e) { fail(e); }
}
async function addFromTemplate(c) {
  const tpls = (await api('/api/templates')).items;
  if (!tpls.length) { await dialog('Templates', h('p', null, 'There are no templates yet. Make one of a list with “Save as a template…” in its ⋯ menu.')); return; }
  const sel = h('select', { class: 't' }, tpls.map((t) => h('option', { value: t.id }, `${t.name} (${t.count} tasks)`)));
  const hasDue = h('input', { type: 'checkbox' });
  const date = h('input', { class: 't', type: 'date', value: ymd(new Date()), hidden: true });
  hasDue.onchange = () => { date.hidden = !hasDue.checked; };
  const body = h('div', { style: { display: 'grid', gap: '12px' } }, h('label', { class: 'field' }, h('span', null, 'Template'), sel),
    h('div', { class: 'when-row' }, h('label', { class: 'check' }, hasDue, ' All due on'), date));
  if (!await dialog(`Add to ${c.name}`, body, [{ label: 'Cancel', value: false }, { label: 'Add', value: true, primary: true }])) return;
  try {
    const r = await api(`/api/templates/${sel.value}/apply`, { method: 'POST', json: { listId: c.id, due: hasDue.checked ? date.value : null } });
    await refresh();
    toast(`${r.created} tasks added`, r.undo);
  } catch (e) { fail(e); }
}
async function clearCompleted(c) {
  if (!await confirmDialog('Clear completed', `Delete the completed tasks of ${c.name}? Apps that sync the list lose them too.`, 'Delete', true)) return;
  try { const r = await api(`/api/lists/${c.id}/clear-completed`, { method: 'POST' }); await refresh(); toast(`${r.deleted} deleted`, r.undo); } catch (e) { fail(e); }
}

/** The new-task line reads plain English unless that is switched off (Settings › Display). */
const smartAdd = () => S.settings.quickAdd !== 'off';
/** What the server made of a line, as chips: [[icon or mark, words]]. */
function quickChips(p) {
  const due = { due: p.due, dueAllDay: !!p.due && !p.due.includes('T') };
  const c = listOf(p.listId);
  return [
    p.due ? [icon('today', 'xs'), dueText(due)] : null,
    p.rrule ? [icon('repeat', 'xs'), describeRule(p.rrule, dueOf(due))] : null,
    p.repeatAfter ? [icon('repeat', 'xs'), describeAfter(p.repeatAfter)] : null,
    p.priority ? [icon('flag', 'xs'), `${p.priority[0].toUpperCase()}${p.priority.slice(1)} priority`] : null,
    c.id ? [h('span', { class: 'ldot', style: { '--hue': c.color } }), c.name] : null,
    ...(p.members || []).map(memberOf).filter(Boolean).map((m) => [memberBadge(m), m.displayName]),
  ].filter(Boolean);
}

/** The "New task" line on top of a list: Enter adds it and leaves the line ready for the next one. What it says about
    when, how often, how important, which list and for whom becomes the task's fields, shown under the line while
    typing ("Pay rent every month on the 1st 9am !high"). On Today and Scheduled a new task is due today unless the
    line says when. */
function quickAdd(r, list) {
  const target = list || defaultList();
  const input = h('input', { class: 'qadd', id: 'qadd', placeholder: list ? `New task in ${list.name}` : `New task (${target.name}${['today', 'scheduled'].includes(r.view) ? ', due today' : ''})`,
    title: smartAdd() ? 'Understands dates, repeats and priorities: “Call the bank tomorrow 5pm”, “Pay rent every month on the 1st !high”' : null,
    autocomplete: 'off', enterkeyhint: 'done', 'aria-label': 'New task' });
  const hint = h('div', { class: 'qhint', hidden: true });
  let seq = 0, timer;
  input.addEventListener('input', () => {
    clearTimeout(timer);
    const text = input.value.trim();
    const my = ++seq;
    if (!smartAdd() || !text) { hint.hidden = true; return; }
    timer = setTimeout(async () => {
      try {
        const p = await api(`/api/quick?text=${encodeURIComponent(text)}&${TZQ}`);
        if (my !== seq) return;
        const chips = quickChips(p);
        fill(hint, h('span', { class: 'qt' }, p.title), chips.map((c) => h('span', { class: 'qchip' }, c)));
        hint.hidden = !chips.length;
      } catch { hint.hidden = true; }
    }, 150);
  });
  input.addEventListener('keydown', async (e) => {
    if (e.key !== 'Enter' || !input.value.trim()) return;
    e.preventDefault();
    const text = input.value.trim();
    const data = smartAdd() ? { text, timezone: LOCAL_TZ, listId: target.id } : { title: text, listId: target.id };
    if (['today', 'scheduled'].includes(r.view)) data.due = ymd(new Date());
    if (S.who.size) data.members = [...S.who];
    input.disabled = true;
    try {
      const t = await api('/api/tasks', { method: 'POST', json: data });
      input.value = ''; seq += 1; hint.hidden = true;
      await refresh();
      if (t.title !== text) toast(`Added “${t.title}”${t.due ? `, ${dueText(t).toLowerCase()}` : ''}${t.listId !== target.id ? ` to ${listOf(t.listId).name}` : ''}`, t.undo);
    } catch (err) { fail(err); }
    input.disabled = false;
    $('#qadd')?.focus();
  });
  return h('div', { class: 'qwrap' }, h('div', { class: 'qrow', style: { '--c': target.color } }, h('span', { class: 'tick ghost' }, icon('add', 's')), input,
    h('button', { class: 'iconbtn', title: 'More details', onclick: () => { location.hash = `#/new?list=${target.id}`; } }, icon('edit', 's'))), hint);
}

const PRIO_MARK = { high: '!!!', medium: '!!', low: '!' };
function taskRow(t, o = {}) {
  const c = listOf(t.listId), canTick = !!c.writable;
  const tick = h('button', { class: `tick ${t.done ? 'on' : ''}`, style: { '--c': c.color || 'var(--brand)' }, title: t.done ? 'Not done after all' : 'Done', 'aria-pressed': t.done ? 'true' : 'false', disabled: canTick ? null : true });
  tick.innerHTML = `<svg viewBox="0 0 24 24"><path d="${ICONS.check}"/></svg>`;
  const late = isLate(t);
  const meta = [
    t.due && !(o.noDay && t.dueAllDay) ? h('span', { class: late ? 'late' : '' }, o.noDay ? fmtTime(dueOf(t)) : dueText(t)) : null,
    t.rrule || t.repeatAfter ? h('span', { title: t.rrule ? describeRule(t.rrule, dueOf(t)) : describeAfter(t.repeatAfter) }, icon('repeat', 'xs')) : null,
    t.alarms && t.alarms.length && !t.done ? h('span', { title: t.alarms.map((a) => new Date(a).toLocaleString()).join('\n') }, icon('bell', 'xs')) : null,
    o.showList ? h('span', { class: 'lname', style: { '--c': c.color } }, c.name) : null,
    t.subtasks && t.subtasks.total ? h('span', null, icon('subtask', 'xs'), `${t.subtasks.total - t.subtasks.open}/${t.subtasks.total}`) : null,
    t.url && safeUrl(t.url) ? h('a', { href: t.url, target: '_blank', rel: 'noopener', onclick: (e) => e.stopPropagation(), title: t.url }, icon('link', 'xs')) : null,
    t.done && t.completedAt ? h('span', null, `Done ${dayWords(new Date(t.completedAt)).toLowerCase().replace(/^(mon|tue|wed|thu|fri|sat|sun)/i, (x) => x[0].toUpperCase() + x.slice(1))}`) : null,
  ].filter(Boolean);
  // put off: a button on the tasks that are overdue or due today (the others show it under the mouse)
  const d0 = dueOf(t), soon = !!d0 && dayStart(d0) <= dayStart(new Date());
  const later = canTick && !t.done && d0 ? h('button', { class: `iconbtn later ${soon ? 'soon' : ''}`, title: 'Postpone', 'aria-haspopup': 'menu', onclick: (e) => {
    popMenu(e.currentTarget, [...laterDays(dayStart(d0) < dayStart(new Date())).map(([label, day]) => ['later', label, () => postpone([t.id], day)]),
      ['event', 'Another day…', () => openTask(t.id)]]);
  } }, icon('later', 's')) : null;
  const row = h('div', { class: `trow ${t.done ? 'done' : ''}`, style: { '--depth': o.depth || 0 }, 'data-id': t.id },
    o.grip ? h('span', { class: 'grip', title: 'Drag to move' }, icon('grip', 's')) : null,
    tick,
    h('div', { class: 'tbody', onclick: () => openTask(t.id) },
      h('div', { class: 'ttl' }, t.priority ? h('span', { class: 'prio' }, PRIO_MARK[t.priority] + ' ') : null, t.title || '(no title)'),
      t.notes ? h('div', { class: 'tnotes' }, t.notes) : null,
      meta.length ? h('div', { class: 'tmeta' }, meta) : null),
    (t.members || []).map((m) => memberOf(m.id) || m).map(memberBadge),
    later,
    h('button', { class: 'iconbtn info', title: 'Details', onclick: () => openTask(t.id) }, icon('chevR', 's')));
  tick.onclick = async () => {
    const done = !t.done;
    tick.classList.toggle('on', done); row.classList.toggle('done', done);
    try {
      const res = await api(`/api/tasks/${t.id}/complete`, { method: 'POST', json: { done, tz: LOCAL_TZ } });
      if (done) toast(res.moved ? `Done. Next: ${dueText(res) || 'again'}` : 'Done', res.undo);
      // a moment to see the tick before the row leaves a list of open tasks
      setTimeout(() => refresh().catch(fail), done && !res.moved ? 700 : 0);
    } catch (e) { tick.classList.toggle('on', !done); row.classList.toggle('done', !done); fail(e); }
  };
  return row;
}

// ------------------------------------------------------------------ one task: the form
const TIMED_ALERTS = [[0, 'At the time'], [5, '5 minutes before'], [15, '15 minutes before'], [30, '30 minutes before'], [60, '1 hour before'], [120, '2 hours before'], [1440, '1 day before']];
const ALLDAY_ALERTS = [[-540, 'On the day at 9:00'], [900, 'The day before at 9:00'], [9540, 'A week before at 9:00']];
const REPEATS = [['', 'Never'], ['FREQ=DAILY', 'Daily'], ['FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR', 'Weekdays'], ['FREQ=WEEKLY', 'Weekly'], ['FREQ=WEEKLY;INTERVAL=2', 'Every 2 weeks'], ['FREQ=MONTHLY', 'Monthly'], ['FREQ=YEARLY', 'Yearly'], ['every', 'Every…']];

/** Wide screens: the task opens in a sheet over the list; phones: as a page of its own. */
function openTask(id) {
  if (innerWidth < 700) { location.hash = `#/task/${id}`; return; }
  const back = h('div', { class: 'dialog-back' });
  const box = h('div', { class: 'dialog wide taskdlg', role: 'dialog' });
  back.append(box);
  back.addEventListener('click', (e) => { if (e.target === back) back.remove(); });
  document.body.append(back);
  taskForm(box, { id }, () => { back.remove(); refresh().catch(fail); }).catch((e) => { back.remove(); fail(e); });
}
async function showTaskPage(page, r) {
  page.classList.add('form');
  const backTo = () => { if (history.length > 1) history.back(); else location.hash = '#/'; };
  await taskForm(page, r.view === 'task' ? { id: r.id } : { list: r.list, parent: r.parent }, backTo);
}

/** The task form: everything a task has, saved with Save (or Enter in the title). opts: {id} or {list, parent}. */
async function taskForm(el, opts, done) {
  const t = opts.id ? await api(`/api/tasks/${opts.id}`) : null;
  const lid = t ? t.listId : (opts.list || defaultList()?.id);
  const c = listOf(lid);
  const ro = t ? !c.writable : false;
  const parent = !t && opts.parent ? await api(`/api/tasks/${opts.parent}`).catch(() => null) : null;
  const dd = t ? dueOf(t) : null;

  const title = h('input', { class: 't big', value: t ? t.title : '', placeholder: 'Title', disabled: ro || null });
  const notes = h('textarea', { class: 't', placeholder: 'Notes', disabled: ro || null }, t && t.notes ? t.notes : '');
  const list = h('select', { class: 't', disabled: ro || (parent ? true : null) },
    writable().concat(ro ? [c] : []).map((x) => h('option', { value: x.id, selected: x.id === lid ? true : null }, `${x.name}${x.shared ? ' (shared)' : ''}`)));
  const hasDue = h('input', { type: 'checkbox', checked: !!dd, disabled: ro || null });
  const date = h('input', { class: 't', type: 'date', value: ymd(dd || new Date()), disabled: ro || null });
  const hasTime = h('input', { type: 'checkbox', checked: !!(dd && !t.dueAllDay), disabled: ro || null });
  const time = h('input', { class: 't', type: 'time', value: dd && !t.dueAllDay ? hm(dd) : '09:00', disabled: ro || null });
  const repeat = h('select', { class: 't', disabled: ro || null });
  const alert = h('select', { class: 't', disabled: ro || null });
  const prio = h('select', { class: 't', disabled: ro || null }, [['', 'None'], ['low', 'Low'], ['medium', 'Medium'], ['high', 'High']].map(([v, l]) => h('option', { value: v, selected: (t ? t.priority || '' : '') === v ? true : null }, l)));
  const url = h('input', { class: 't', type: 'url', value: t && t.url ? t.url : '', placeholder: 'https://…', disabled: ro || null });
  const picked = new Set(t ? (t.members || []).map((m) => m.id) : [...S.who]);

  // repeat: the usual ones, "Every…" with a number of days, weeks, months or years, and the task's own rule when it
  // is yet another; counted from the due date, or from the day the task is ticked off (repeat after completion)
  const curRule = t ? t.rrule || afterRule(t.repeatAfter) : '';
  const reps = REPEATS.slice();
  const plain = afterParts(afterOf(curRule));  // [n, unit] when the rule is only "every n days / weeks / months / years"
  const listed = reps.some(([v]) => v === curRule);
  if (curRule && !listed && !plain) reps.splice(-1, 0, [curRule, describeRule(curRule, dd)]);
  const repValue = listed || !plain ? curRule : 'every';
  fill(repeat, reps.map(([v, l]) => h('option', { value: v, selected: v === repValue ? true : null }, l)));
  const every = h('input', { class: 't', type: 'number', min: 1, max: 999, value: plain ? plain[0] : 2, disabled: ro || null, 'aria-label': 'How many' });
  const unit = h('select', { class: 't', disabled: ro || null, 'aria-label': 'Days, weeks, months or years' },
    [['D', 'days'], ['W', 'weeks'], ['M', 'months'], ['Y', 'years']].map(([v, l]) => h('option', { value: v, selected: plain && plain[1] === v ? true : null }, l)));
  const from = h('select', { class: 't', disabled: ro || null }, [['due', 'The due date'], ['done', 'The day it is ticked off']].map(([v, l]) => h('option', { value: v, selected: (t && t.repeatAfter ? 'done' : 'due') === v ? true : null }, l)));
  const rule = () => (repeat.value === 'every' ? afterRule(`P${Math.max(1, Math.min(999, +every.value || 1))}${unit.value}`) : repeat.value);
  const everyBox = h('span', { class: 'everybox' }, every, unit);
  const drawRepeat = () => {
    everyBox.hidden = repeat.value !== 'every';
    repeat.closest('.field')?.classList.toggle('wide', repeat.value === 'every');  // room for the number and the unit
    from.closest('.field')?.toggleAttribute('hidden', !hasDue.checked || !afterOf(rule()));
  };
  repeat.onchange = drawRepeat;
  // alert: minutes before the due time (all-day: before its midnight), worked out from the task's first alert
  const alertMins = () => {
    if (!t || !t.alarms || !t.alarms.length || !dd) return null;
    return Math.round((dd - new Date(t.alarms[0])) / 6e4);
  };
  const drawAlerts = (keep) => {
    const opts2 = hasTime.checked ? TIMED_ALERTS : ALLDAY_ALERTS;
    const cur = keep ? alertMins() : null;
    const known = opts2.some(([m]) => m === cur);
    fill(alert, h('option', { value: '' }, 'None'), opts2.map(([m, l]) => h('option', { value: m, selected: m === cur ? true : null }, l)),
      cur != null && !known ? h('option', { value: 'keep', selected: true }, t.alarms.map((a) => new Date(a).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })).join(', ')) : null);
  };
  drawAlerts(true);
  const whenRow = h('div', { class: 'when-row' });
  const drawWhen = () => {
    fill(whenRow, h('label', { class: 'check' }, hasDue, ' Due'), hasDue.checked ? [date, h('label', { class: 'check' }, hasTime, ' At a time'), hasTime.checked ? time : null] : null);
    repeat.closest('.field')?.toggleAttribute('hidden', !hasDue.checked);
    alert.closest('.field')?.toggleAttribute('hidden', !hasDue.checked);
    drawRepeat();
  };
  // the days a task is usually put off to, one click each
  const laterRow = ro ? null : h('div', { class: 'chiprow laterrow' }, laterDays(true).map(([label, day]) => h('button', { type: 'button', class: 'chip toggle',
    onclick: () => { hasDue.checked = true; date.value = ymd(day); drawWhen(); } }, label)));
  hasDue.onchange = drawWhen;
  hasTime.onchange = () => { drawWhen(); drawAlerts(false); };

  const who = h('div', { class: 'chiprow' });
  const drawWho = () => fill(who, S.members.map((m) => h('button', { type: 'button', class: `chip toggle mchip ${picked.has(m.id) ? 'on' : ''}`, disabled: ro || null,
    onclick: () => { if (picked.has(m.id)) picked.delete(m.id); else picked.add(m.id); drawWho(); } }, memberBadge(m, true), m.displayName)));
  drawWho();

  const subs = h('div', { class: 'subs' });
  const drawSubs = async () => {
    if (!t) return;
    const j = await api(`/api/tasks/${t.id}`);
    fill(subs, h('div', { class: 'fsec' }, icon('subtask'), 'Subtasks'), h('div', { class: 'tasks' }, j.children.map((x) => {
      const row = taskRow(x, {});
      row.querySelector('.tbody').onclick = () => { closeDialogs(); openTask(x.id); };
      row.querySelector('.info').onclick = () => { closeDialogs(); openTask(x.id); };
      return row;
    })),
    ro ? null : h('input', { class: 'qadd', placeholder: 'Add a subtask', onkeydown: async (e) => {
      if (e.key !== 'Enter' || !e.target.value.trim()) return;
      e.preventDefault();
      try { await api('/api/tasks', { method: 'POST', json: { title: e.target.value.trim(), parent: t.id, listId: t.listId } }); await drawSubs(); subs.querySelector('.qadd')?.focus(); } catch (err) { fail(err); }
    } }));
  };

  /** The fields as the API takes them. */
  const collect = () => {
    const data = { title: title.value.trim(), notes: notes.value, priority: prio.value || 'none', url: url.value.trim(), members: [...picked] };
    if (!hasDue.checked) { data.due = null; data.rrule = null; data.repeatAfter = null; data.alarms = []; return data; }
    data.due = hasTime.checked ? `${date.value}T${time.value || '09:00'}` : date.value;
    data.timezone = LOCAL_TZ;
    const after = from.value === 'done' ? afterOf(rule()) : null;
    data.rrule = after ? null : rule() || null;
    data.repeatAfter = after;
    if (alert.value !== 'keep') {
      const due = hasTime.checked ? new Date(`${date.value}T${time.value || '09:00'}`) : parseDay(date.value);
      data.alarms = alert.value === '' ? [] : [new Date(+due - +alert.value * 6e4).toISOString()];
    }
    return data;
  };
  const save = async () => {
    const data = collect();
    if (!data.title) { toast('A title, please'); title.focus(); return; }
    try {
      if (t) {
        if (+list.value !== t.listId) data.listId = +list.value;
        const r = await api(`/api/tasks/${t.id}`, { method: 'PATCH', json: data });
        toast('Saved', r.undo);
      } else {
        data.listId = +list.value;
        if (parent) { data.parent = parent.id; data.listId = parent.listId; }
        await api('/api/tasks', { method: 'POST', json: data });
        toast('Saved');
      }
      done();
    } catch (e) { fail(e); }
  };
  const del = async () => {
    const n = t.subtasks ? t.subtasks.total : 0;
    if (!await confirmDialog('Delete task', `Delete “${t.title || 'this task'}”${n ? ` and its ${n} subtask${n > 1 ? 's' : ''}` : ''}?`, 'Delete', true)) return;
    try { const r = await api(`/api/tasks/${t.id}`, { method: 'DELETE' }); toast('Deleted', r.undo); done(); } catch (e) { fail(e); }
  };
  title.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); save(); } });
  const fld = (l, e, cls) => h('label', { class: `field ${cls || ''}` }, h('span', null, l), e);

  fill(el,
    h('div', { class: 'taskhead', style: { '--c': listOf(+list.value).color || 'var(--brand)' } },
      t ? h('button', { class: `tick big ${t.done ? 'on' : ''}`, title: t.done ? 'Not done after all' : 'Done', disabled: ro || null, onclick: async (e) => {
        try { const res = await api(`/api/tasks/${t.id}/complete`, { method: 'POST', json: { done: !t.done, tz: LOCAL_TZ } }); toast(res.moved ? `Done. Next: ${dueText(res)}` : res.done ? 'Done' : 'Open again', res.undo); done(); } catch (err) { fail(err); }
        e.stopPropagation();
      } }) : null,
      title),
    parent ? h('p', { class: 'muted small' }, `Subtask of “${parent.title}”`) : null,
    ro ? h('p', { class: 'muted small' }, 'Read-only: editors and admins change shared lists.') : null,
    notes,
    h('div', { class: 'fsec' }, icon('today'), 'When'), whenRow, laterRow,
    h('div', { class: 'grid', style: { marginTop: '10px' } }, fld('Repeat', h('div', { class: 'reprow' }, repeat, everyBox)), fld('Counted from', from), fld('Alert', alert)),
    t && t.rrule ? h('p', { class: 'muted small' }, `${describeRule(t.rrule, dd)}. Ticking it off moves it to the next date.`) : null,
    t && t.repeatAfter ? h('p', { class: 'muted small' }, `Ticking it off brings it back ${describeAfter(t.repeatAfter).replace(/^A /, 'a ')}.`) : null,
    h('div', { class: 'fsec' }, icon('tune'), 'Details'),
    h('div', { class: 'grid' }, fld('List', list), fld('Priority', prio), fld('Link', url, 'wide')),
    S.members.length > 1 ? [h('div', { class: 'fsec' }, icon('people'), 'For'), who] : null,
    subs,
    t ? h('p', { class: 'muted small' }, [t.created ? `Added ${new Date(t.created).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}` : null, t.done && t.completedAt ? `done ${new Date(t.completedAt).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}` : null].filter(Boolean).join(', ')) : null,
    h('div', { class: 'formbar' },
      ro ? null : h('button', { class: 'pillbtn primary noic', onclick: save }, 'Save'),
      h('button', { class: 'pillbtn noic', onclick: done }, ro ? 'Close' : 'Cancel'),
      t && !ro && !t.parent ? h('button', { class: 'pillbtn noic', title: 'A new subtask', onclick: () => { closeDialogs(); location.hash = `#/new?parent=${t.id}`; } }, 'Add subtask') : null,
      h('span', { class: 'grow' }),
      t && !ro ? h('button', { class: 'pillbtn noic danger', onclick: del }, 'Delete') : null));
  list.onchange = () => el.querySelector('.taskhead').style.setProperty('--c', listOf(+list.value).color || 'var(--brand)');
  drawWhen();
  await drawSubs();
  if (!t) title.focus();
}

// ------------------------------------------------------------------ activity
/** What an entry of the log says, as the parts of a sentence. */
function activityWords(a) {
  const who = a.user || 'Someone', more = a.count > 1 ? ` and ${a.count - 1} more` : '';
  const title = h('b', null, `“${a.title || '(no title)'}”`);
  const undo = a.detail === 'undo';
  const d = a.detail && !undo ? a.detail : '';
  switch (a.action) {
    case 'added': return [who, undo ? ' brought back ' : ' added ', title, more, d === 'import' ? ' (import)' : d.startsWith('template ') ? ` from the template ${d.slice(9)}` : d.startsWith('from ') ? ` (moved here ${d})` : ''];
    case 'done': return [who, ' ticked off ', title, more, d.startsWith('next ') ? ` (it repeats: next ${dayWords(parseDay(d.slice(5)))})` : ''];
    case 'reopened': return [who, ' opened ', title, ' again', more];
    case 'moved': return [who, ' moved ', title, more, d ? ` ${d}` : ''];
    case 'deleted': return [who, undo ? ' took back adding ' : ' deleted ', title, more];
    default: return [who, d === 'postponed' ? ' postponed ' : undo ? ' put back ' : ' changed ', title, more, d && d !== 'postponed' ? ` (${d})` : ''];
  }
}
/** Who did what, newest first (all the lists you see, or one), each step with Undo while the task is still as that
    step left it. */
async function showActivity(page, r) {
  const c = r.list ? listOf(r.list) : null;
  const rows = h('div', { class: 'acts' });
  const more = h('p', { class: 'center' });
  let last = null, lastDay = null;
  const load = async () => {
    const items = (await api(`/api/activity?limit=60${c && c.id ? `&list=${c.id}` : ''}${last ? `&before=${last}` : ''}`)).items;
    for (const a of items) {
      const at = new Date(a.at), day = dayWords(at);
      if (day !== lastDay) { rows.append(h('div', { class: 'tsec' }, day)); lastDay = day; }
      const l = listOf(a.listId);
      rows.append(h('div', { class: `act ${a.undone ? 'undone' : ''}` },
        h('span', { class: 'av', style: { '--h': hue(a.user || '') } }, a.user ? initials(a.user) : '?'),
        h('div', { class: 'abody' }, h('div', null, activityWords(a)),
          h('div', { class: 'tmeta' }, h('span', null, fmtTime(at)), l.id && !(c && c.id) ? h('span', { class: 'lname', style: { '--c': l.color } }, l.name) : null,
            a.via === 'caldav' ? h('span', null, 'in a reminders app') : a.via === 'mcp' ? h('span', null, 'through an assistant') : null,
            a.undone ? h('span', null, 'undone') : null)),
        a.canUndo ? h('button', { class: 'pillbtn noic', onclick: () => undoStep(a.batch) }, 'Undo') : null));
    }
    last = items.length ? items[items.length - 1].id : last;
    fill(more, items.length === 60 ? h('button', { class: 'pillbtn noic', onclick: () => load().catch(fail) }, 'Earlier') : null);
    if (!rows.children.length) rows.append(h('div', { class: 'empty' }, icon('history'), h('p', null, 'Nothing has happened yet.')));
  };
  page.classList.add('taskpage');
  page.append(h('div', { class: 'pagehead tasks-head', style: c && c.id ? { '--c': c.color } : null }, h('h1', null, c && c.id ? `Activity: ${c.name}` : 'Activity'), h('span', { class: 'grow' }),
    c && c.id ? h('a', { class: 'pillbtn noic', href: '#/activity' }, 'All lists') : null), rows, more);
  await load();
}

// ------------------------------------------------------------------ import
async function showImport(page, r) {
  const w = writable();
  const sel = h('select', { class: 't', style: { maxWidth: '320px' } }, w.map((c) => h('option', { value: c.id, selected: c.id === r.list ? true : null }, `${c.name}${c.shared ? ' (shared)' : ''}`)));
  const file = h('input', { type: 'file', accept: '.ics,.ical,text/calendar', multiple: true });
  const replace = h('input', { type: 'checkbox', checked: true });
  const out = h('div');
  const run = async () => {
    if (!file.files.length) { toast('Pick a file first'); return; }
    const tot = { created: 0, updated: 0, skipped: 0, errors: [] };
    for (const f of file.files) {
      const fd = new FormData(); fd.append('file', f);
      try {
        const res = await api(`/api/lists/${sel.value}/import?replace=${replace.checked}`, { method: 'POST', body: fd });
        tot.created += res.created; tot.updated += res.updated; tot.skipped += res.skipped; tot.errors.push(...res.errors);
      } catch (e) { tot.errors.push(`${f.name}: ${e.message}`); }
    }
    fill(out, h('p', null, `${tot.created} added, ${tot.updated} updated${tot.skipped ? `, ${tot.skipped} left as they were` : ''}.`),
      tot.errors.length ? h('details', null, h('summary', { class: 'lnk' }, `${tot.errors.length} could not be read`), h('ul', null, tot.errors.slice(0, 50).map((x) => h('li', null, x)))) : null);
    await loadLists();
  };
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Import')),
    w.length ? h('div', { class: 'box' }, h('h2', null, icon('upload'), 'Import'),
      h('p', null, 'An iCalendar file (.ics) with to-dos, from another tasks app or another ioTask. Due dates, repeats, alerts, priorities and subtasks come along; events in the file are left out.'),
      h('div', { class: 'pform' }, h('label', { class: 'field' }, h('span', null, 'Into the list'), sel), file,
        h('label', { class: 'check' }, replace, ' Update tasks that are already here (same UID)'),
        h('p', null, h('button', { class: 'pillbtn primary', onclick: run }, icon('upload', 's'), 'Import'))), out) : h('p', { class: 'muted' }, 'You cannot add tasks to any list.'));
}

// ------------------------------------------------------------------ settings
async function showSettings(page, r) {
  const adm = S.user.role === 'admin';
  const tabs = [['account', 'Account'], ['display', 'Display'], ['devices', 'Apps and devices'], ['lists', 'Lists'],
    ...(adm ? [['server', 'Server']] : []),
    ...(S.user.suiteAdmin ? [['security', SUITE_TABS.security], ['global', SUITE_TABS.global]] : [])];
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Settings')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/settings/${k}`; } }, l))));
  const body = h('div'); page.append(body);
  await ({ account: setAccount, display: setDisplay, devices: setDevices, lists: setLists, server: setServer,
    security: setSuite, global: setSuite }[r.tab] || setAccount)(body, r);
}
const fld = (l, e) => h('label', { class: 'field' }, h('span', null, l), e);
const kv = (k, v) => h('div', { class: 'kv' }, h('div', { class: 'k' }, k), h('div', { class: 'v', style: { flex: 1 } }, typeof v === 'string' ? copyRow(v) : v));

const accountUi = () => import(new URL('api/auth/ui.js', document.baseURI).href);
/** Settings › Account: display name, email and password, then the app passwords: iosuite-shared's panels (the same in every io app). */
async function setAccount(el) {
  const ui = await accountUi();
  const pw = h('div');
  await ui.mountAccount(el, { toast, onSaved: (u) => { Object.assign(S.user, u); drawUser(); } });
  el.append(pw);
  await ui.mountAppPasswords(pw, { toast, syncOnly: 'Reminders apps only (CalDAV)' });
}

/** Settings › Display: the theme (saved with the account) and where the app opens and new tasks go. */
async function setDisplay(el) {
  const ui = await accountUi();
  const save = async (changes) => { await saveSettings(changes); drawNav(); toast('Saved'); };
  const sv = h('select', { class: 't', onchange: (e) => save({ startView: e.target.value }) },
    Object.entries(SMART).slice(0, 3).map(([v, [l]]) => h('option', { value: v, selected: v === (S.settings.startView || 'today') ? true : null }, l)));
  const dl = h('select', { class: 't', onchange: (e) => save({ defaultList: +e.target.value }) },
    writable().map((c) => h('option', { value: c.id, selected: c.id === defaultList()?.id ? true : null }, `${c.name}${c.shared ? ' (shared)' : ''}`)));
  const qa = h('input', { type: 'checkbox', checked: smartAdd(), onchange: (e) => save({ quickAdd: e.target.checked ? 'on' : 'off' }) });
  el.append(ui.box('theme', 'Appearance', ui.themeRow(S.settings.theme || store.get('theme') || 'system', (t) => { S.settings.theme = t; applyTheme(t); })),
    h('div', { class: 'box' }, h('h2', null, icon('tune'), 'Tasks'), h('div', { class: 'grid' }, fld('Open on', sv), fld('New tasks go to', dl)),
      h('p', null, h('label', { class: 'check' }, qa, ' The new-task line understands what is typed')),
      h('p', { class: 'muted small' }, 'When (tomorrow 5pm, friday, 15 nov, in 2 weeks), how often (every monday, monthly, every 2 weeks after done), how important (!high), which list (#groceries) and for whom (@emma) become the task’s fields: “Pay rent every month on the 1st 9am !high”. What was understood shows under the line while you type; the rest is the title.')));
}

/** The profile through a short-lived link instead of the form post: the app on the Home Screen opens a download in a
 * separate sheet without its cookies, which a link opens by itself (the form post stays the fallback without script). */
async function downloadProfile(e) {
  e.preventDefault();
  const f = e.target;
  const btn = f.querySelector('button[type=submit]');
  if (btn) btn.disabled = true;
  try {
    const all = f.elements.scope && f.elements.scope.value === 'suite';
    const res = await api(all ? '/api/apple-profile/suite/link' : '/api/apple-profile/link', { method: 'POST', json: { label: f.elements.label.value, password: f.elements.password.value } });
    location.href = res.url;
  } catch (err) {
    toast(err.message);
  } finally {
    if (btn) setTimeout(() => { btn.disabled = false; }, 1500);
  }
}

/** The "Set up" choice of the profile box: this app only, or every app that syncs (iosuite-shared's suite profile),
 * offered when the account may use two or more of them. Fields marked data-own belong to this app's own profile. */
function profileScope(apps, own) {
  if (!apps || apps.length < 2) return null;
  const names = apps.map((a) => a.name);
  const pick = (e) => {
    const f = e.target.form, all = e.target.value === 'suite';
    f.action = all ? '/api/apple-profile/suite' : '/api/apple-profile';
    f.querySelectorAll('[data-own]').forEach((x) => { x.hidden = all; });
  };
  return fld('Set up', h('select', { class: 't', name: 'scope', onchange: pick },
    h('option', { value: 'app' }, `${own} only`),
    h('option', { value: 'suite' }, `All apps: ${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`)));
}

/** Settings › Apps and devices: how to connect each kind of app (the app passwords themselves are on Settings › Account). */
async function setDevices(el) {
  const info = await api('/api/connect');
  const suiteApps = S.user.passwordless ? [] : (await api('/api/apple-profile/suite').catch(() => ({ apps: [] }))).apps;
  const canPw = !S.user.passwordless;
  const isApple = /iPhone|iPad|Macintosh/.test(navigator.userAgent);
  const plabel = h('input', { class: 't', name: 'label', value: /iPad/.test(navigator.userAgent) ? 'iPad' : /Macintosh/.test(navigator.userAgent) ? 'Mac' : 'iPhone', style: 'max-width:200px' });
  const how = (summary, ...kids) => h('details', null, h('summary', { class: 'lnk' }, summary), ...kids);
  el.append(...[
    canPw ? h('div', { class: 'box' }, h('h2', null, icon('devices'), 'iPhone, iPad and Mac'),
      h('p', null, 'A profile that adds your lists to Apple Reminders in one step. Tasks you add or tick off there show up here, and the other way round.'),
      h('form', { method: 'POST', action: '/api/apple-profile', class: 'pform', onsubmit: downloadProfile },
        profileScope(suiteApps, 'ioTask'),
        fld('Device name', plabel),
        fld('Password', h('select', { class: 't', name: 'password' }, h('option', { value: 'new' }, 'Include a new app password'), h('option', { value: 'ask' }, 'Ask on the device'))),
        h('p', null, h('button', { class: 'pillbtn primary', type: 'submit' }, icon('download', 's'), 'Download the profile'))),
      how('How to install', h('p', { class: 'muted small' }, isApple ? 'Open the download, then Settings › Profile Downloaded › Install.' : 'Download it in Safari on the iPhone or iPad, then Settings › Profile Downloaded › Install. On a Mac: open the file, then System Settings › Privacy & Security › Profiles.',
        ' iOS shows the profile as “Not Verified”: that is expected. Revoke its app password under Settings › Account if the device is lost.',
        suiteApps.length > 1 ? ' A profile for all apps holds one app password per app; revoke each one in its own app.' : null),
      h('p', { class: 'muted small' }, 'The lists appear in Reminders under the account “ioTask”. Lists made there are made here too.'))) : null,
    h('div', { class: 'box' }, h('h2', null, icon('list'), 'Reminders and tasks apps (CalDAV)'),
      h('p', null, 'Two-way sync with your user name and an app password (Settings › Account).'),
      kv('Server', info.server), kv('User name', info.user), kv('CalDAV', info.caldav),
      how('Address of each list', info.lists.map((c) => kv(c.name, c.caldav))),
      how('How to connect', h('p', { class: 'muted small' }, 'Apple Reminders: iPhone Settings › Apps › Reminders › Reminders Accounts › Add Account › Other › Add CalDAV Account (Mac: System Settings › Internet Accounts › Add Other Account › CalDAV account). Android: DAVx⁵ with jtx Board, Tasks.org or OpenTasks. Also Thunderbird and Evolution.'),
        h('p', { class: 'muted small' }, 'Behind Cloudflare Access, add a Bypass policy for /dav/*, /.well-known/caldav and /profile/* (and /mcp).'))),
    S.status.mcp ? h('div', { class: 'box' }, h('h2', null, icon('ai'), 'AI assistants (MCP)'),
      h('p', null, 'Give the assistant its own app password (not “Reminders apps only”), sent as a Bearer token.'),
      kv('MCP address', info.mcp),
      how('Setup for Claude Code and JSON-configured apps',
        copyRow(`claude mcp add --transport http iotask ${info.mcp} --header "Authorization: Bearer APP-PASSWORD"`),
        copyRow(JSON.stringify({ mcpServers: { iotask: { command: 'npx', args: ['-y', 'mcp-remote', info.mcp, '--header', 'Authorization: Bearer APP-PASSWORD'] } } }))))
      : (S.user.role === 'admin' ? h('div', { class: 'box' }, h('h2', null, icon('ai'), 'AI assistants (MCP)'), h('p', { class: 'muted' }, 'Off. Turn it on in ', h('a', { class: 'lnk', href: '#/settings/server' }, 'Settings › Server'), '.')) : null),
    h('div', { class: 'box' }, h('h2', null, icon('link'), 'Other apps (REST API)'),
      h('p', null, 'JSON or iCalendar with your user name and an app password. ', h('a', { class: 'lnk', href: info.api, target: '_blank' }, 'API documentation')),
      copyRow(`curl -u ${info.user}:APP-PASSWORD "${info.server}/api/tasks?due=today"`))].filter(Boolean));
}

async function setLists(el, r) {
  await loadLists();
  const tpls = (await api('/api/templates').catch(() => ({ items: [] }))).items;
  const box = (c) => {
    const save = async (body) => { try { await api(`/api/lists/${c.id}`, { method: 'PATCH', json: body }); await loadLists(); toast('Saved'); } catch (e) { fail(e); } };
    const name = h('input', { class: 't', value: c.name, onchange: (e) => save({ name: e.target.value }) });
    const desc = h('input', { class: 't', value: c.description || '', placeholder: 'What it is for', onchange: (e) => save({ description: e.target.value }) });
    const col = colorPicker(c.color, (v) => save({ color: v }));
    return h('div', { class: 'box', id: `list-${c.id}`, 'data-id': c.id, style: { '--c': c.color } },
      h('h2', null, c.writable ? h('span', { class: 'grip', title: 'Drag to move the list' }, icon('grip', 's')) : null, h('span', { class: 'ldot', style: { '--hue': c.color } }), c.name,
        h('span', { class: 'muted small', style: { fontWeight: 400 } }, c.shared ? 'shared with everyone' : 'only you')),
      c.writable ? [h('div', { class: 'grid' }, fld('Name', name), fld('Description', desc)), h('div', { style: { margin: '10px 0' } }, col),
        h('p', null, h('a', { class: 'pillbtn noic', href: `/api/lists/${c.id}/export` }, 'Export (.ics)'), ' ',
          h('button', { class: 'pillbtn noic', onclick: () => saveTemplate(c).then(() => onRoute()) }, 'Save as a template…'), ' ',
          !c.shared || S.user.role === 'admin' ? h('button', { class: 'pillbtn noic danger', onclick: async () => {
            if (!await confirmDialog('Delete list', `Delete ${c.name} and its tasks? Apps that sync it lose it too.`, 'Delete', true)) return;
            try { await api(`/api/lists/${c.id}`, { method: 'DELETE' }); await loadLists(); onRoute(); } catch (e) { fail(e); }
          } }, 'Delete') : null)]
        : h('p', { class: 'muted' }, `${c.count || 0} open tasks. Editors and admins change shared lists.`));
  };
  // the lists of a kind, in their order: a list moves by its grip (the sidebar follows)
  const group = (lists) => {
    const g = h('div', { class: `listboxes ${lists.length > 1 ? '' : 'one'}` }, lists.map(box));
    dragSort(g, '.box', '.grip', orderLists);
    return g;
  };
  const tplRow = (t) => h('tr', null,
    h('td', null, t.writable ? h('input', { class: 't', value: t.name, 'aria-label': 'Name', onchange: async (e) => { try { await api(`/api/templates/${t.id}`, { method: 'PATCH', json: { name: e.target.value } }); toast('Saved'); } catch (x) { fail(x); } } }) : t.name),
    h('td', { class: 'muted' }, `${t.count} tasks`), h('td', { class: 'muted' }, t.shared ? 'shared with everyone' : 'only you'),
    h('td', { style: { textAlign: 'right' } }, t.writable ? h('button', { class: 'pillbtn noic danger', onclick: async () => {
      if (!await confirmDialog('Delete template', `Delete the template ${t.name}? The lists made from it stay.`, 'Delete', true)) return;
      try { await api(`/api/templates/${t.id}`, { method: 'DELETE' }); onRoute(); } catch (x) { fail(x); }
    } }, 'Delete') : null));
  el.append(h('p', null, canShared() ? h('button', { class: 'pillbtn', onclick: () => newList(true) }, icon('add', 's'), 'New shared list') : null, ' ',
    canOwn() ? h('button', { class: 'pillbtn', onclick: () => newList(false) }, icon('add', 's'), 'New private list') : null),
  group(S.lists.filter((c) => c.shared)), group(S.lists.filter((c) => !c.shared)),
  h('div', { class: 'box' }, h('h2', null, icon('template'), 'Templates'),
    h('p', { class: 'muted' }, 'A list’s tasks kept to add again: a packing list, the weekly shop. Save one from a list (here, or in the list’s ⋯ menu); add its tasks with “Add from a template…” in a list’s ⋯ menu, or start a new list with it.'),
    tpls.length ? h('table', { class: 't' }, tpls.map(tplRow)) : null));
  if (r.sub) setTimeout(() => $(`#list-${r.sub}`)?.scrollIntoView({ block: 'start' }), 0);
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
    (iosuite-shared's panel, the same in every io app), then Export: each list as an .ics file. */
async function setServer(el) {
  let ui;
  const panel = h('div');
  el.append(panel);
  try { ui = await serverUi(); } catch (e) { panel.append(h('p', { class: 'warn' }, `The Server panel did not load: ${e.message}`)); return; }
  await ui.mount(panel, { toast });
  await loadLists();
  el.append(h('div', { class: 'box' }, h('h2', null, icon('download'), 'Export'),
    h('p', null, 'Each list as an .ics file.'),
    h('table', { class: 't' }, S.lists.map((c) => h('tr', null, h('td', null, h('span', { class: 'ldot', style: { '--hue': c.color } }), ' ', c.name),
      h('td', { class: 'muted' }, `${c.count || 0} open tasks`),
      h('td', { style: { textAlign: 'right' } }, h('a', { class: 'pillbtn noic', href: `/api/lists/${c.id}/export` }, 'Download')))))));
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
    try { await api(first ? '/api/auth/setup' : '/api/auth/login', { method: 'POST', json: { name: n, password: p } }); location.reload(); } catch (x) { err.textContent = x.message; }
  };
  const submit = (e) => { e.preventDefault(); login(name.value.trim(), pw.value); };
  document.body.append(h('div', { class: 'signin' }, h('form', { class: 'dialog', onsubmit: submit },
    h('div', { class: 'brand' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }), h('span', { class: 'brand-name', style: { display: 'inline' } }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Task'))),
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
