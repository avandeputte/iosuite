/* ioContacts web app: one module, no build step. Pages: the contact list with a detail pane, the edit form, upcoming
   birthdays, the family tree, ioPix people, import/export, settings (account, display, apps and devices, address books,
   connected apps, users and sign-in, server) and maintenance (duplicates, data quality, suggestions, merge history, and for
   admins storage and backups, updates and logs), laid out as in the other ioThing apps. */

// ------------------------------------------------------------------ helpers
const $ = (s, el = document) => el.querySelector(s);
const ICONS = {
  menuOpen: 'M3 18h13v-2H3v2zm0-5h10v-2H3v2zm0-7v2h13V6H3zm18 9.59L17.42 12 21 8.41 19.59 7l-5 5 5 5L21 15.59z',
  pin: 'M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3z',
  wrench: 'M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6 6 9 1.6 4.7C.4 7.1.9 10.1 2.9 12.1c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.3-2.3c.5-.4.5-1.1.1-1.4z',
  menu: 'M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z',
  search: 'M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z',
  add: 'M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z',
  person: 'M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z',
  people: 'M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z',
  star: 'M12 17.27 18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z',
  starO: 'M22 9.24l-7.19-.62L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21 12 17.27 18.18 21l-1.63-7.03L22 9.24zM12 15.4l-3.76 2.27 1-4.28-3.32-2.88 4.38-.38L12 6.1l1.71 4.04 4.38.38-3.32 2.88 1 4.28L12 15.4z',
  cake: 'M12 6c1.11 0 2-.9 2-2 0-.38-.1-.73-.29-1.03L12 0l-1.71 2.97c-.19.3-.29.65-.29 1.03 0 1.1.9 2 2 2zm4.6 9.99-1.07-1.07-1.08 1.07c-1.3 1.3-3.58 1.31-4.89 0l-1.07-1.07-1.09 1.07C6.75 16.64 5.88 17 4.96 17c-.73 0-1.4-.23-1.96-.61V21c0 .55.45 1 1 1h16c.55 0 1-.45 1-1v-4.61c-.56.38-1.23.61-1.96.61-.92 0-1.79-.36-2.44-1.01zM18 9h-5V7h-2v2H6c-1.66 0-3 1.34-3 3v1.54c0 1.08.88 1.96 1.96 1.96.52 0 1.02-.2 1.38-.57l2.14-2.13 2.13 2.13c.74.74 2.03.74 2.77 0l2.14-2.13 2.13 2.13c.37.37.86.57 1.38.57 1.08 0 1.96-.88 1.96-1.96V12C21 10.34 19.66 9 18 9z',
  mail: 'M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4-8 5-8-5V6l8 5 8-5v2z',
  phone: 'M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z',
  place: 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z',
  link: 'M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z',
  tag: 'M17.63 5.84C17.27 5.33 16.67 5 16 5L5 5.01C3.9 5.01 3 5.9 3 7v10c0 1.1.9 1.99 2 1.99L16 19c.67 0 1.27-.33 1.63-.84L22 12l-4.37-6.16z',
  book: 'M20 0H4v2h16V0zM4 24h16v-2H4v2zM20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm-8 2.75c1.24 0 2.25 1.01 2.25 2.25s-1.01 2.25-2.25 2.25S9.75 10.24 9.75 9 10.76 6.75 12 6.75zM17 17H7v-1.5c0-1.67 3.33-2.5 5-2.5s5 .83 5 2.5V17z',
  upload: 'M9 16h6v-6h4l-7-7-7 7h4zm-4 2h14v2H5z',
  download: 'M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z',
  settings: 'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z',
  edit: 'M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a.996.996 0 0 0 0-1.41l-2.34-2.34a.996.996 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z',
  delete: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z',
  close: 'M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z',
  back: 'M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z',
  tree: 'M22 11V3h-7v3H9V3H2v8h7V8h2v10h4v3h7v-8h-7v3h-2V8h2v3z',
  merge: 'M17 20.41 18.41 19 15 15.59 13.59 17 17 20.41zM7.5 8H11v5.59L5.59 19 7 20.41l6-6V8h3.5L12 3.5 7.5 8z',
  camera: 'M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4zM9 2 7.17 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2h-3.17L15 2H9zm3 15c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5z',
  key: 'M12.65 10C11.83 7.67 9.61 6 7 6c-3.31 0-6 2.69-6 6s2.69 6 6 6c2.61 0 4.83-1.67 5.65-4H17v4h4v-4h2v-4H12.65zM7 14c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
  event: 'M17 12h-5v5h5v-5zM16 1v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2h-1V1h-2zm3 18H5V8h14v11z',
  logout: 'M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z',
  copy: 'M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z',
  open: 'M19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z',
  work: 'M20 6h-4V4c0-1.11-.89-2-2-2h-4c-1.11 0-2 .89-2 2v2H4c-1.11 0-1.99.89-1.99 2L2 19c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V8c0-1.11-.89-2-2-2zm-6 0h-4V4h4v2z',
  note: 'M3 18h12v-2H3v2zM3 6v2h18V6H3zm0 7h18v-2H3v2z',
  devices: 'M4 6h18V4H4c-1.1 0-2 .9-2 2v11H0v3h14v-3H4V6zm19 2h-6c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h6c.55 0 1-.45 1-1V9c0-.55-.45-1-1-1zm-1 9h-4v-7h4v7z',
  image: 'M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z',
  more: 'M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  check: 'M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z',
  update: 'M21 10.12h-6.78l2.74-2.82c-2.73-2.7-7.15-2.8-9.88-.1a6.875 6.875 0 0 0 0 9.79 7.02 7.02 0 0 0 9.88 0C18.32 15.65 19 14.08 19 12.1h2c0 1.98-.88 4.55-2.64 6.29-3.51 3.48-9.21 3.48-12.72 0-3.5-3.47-3.53-9.11-.02-12.58a8.987 8.987 0 0 1 12.65 0L21 3v7.12z',
  tune: 'M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 4v-2H11v2h10zm-6-4h2V7h4V5h-4V3h-2v6z',
  bulb: 'M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7z',
  ai: 'M19 9l1.25-2.75L23 5l-2.75-1.25L19 1l-1.25 2.75L15 5l2.75 1.25L19 9zm-7.5.5L9 4 6.5 9.5 1 12l5.5 2.5L9 20l2.5-5.5L17 12l-5.5-2.5zM19 15l-1.25 2.75L15 19l2.75 1.25L19 23l1.25-2.75L23 19l-2.75-1.25L19 15z',
  server: 'M20 13H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1v-6c0-.55-.45-1-1-1zM7 19c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zM20 3H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1V4c0-.55-.45-1-1-1zM7 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
  theme: 'M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.389 5.389 0 0 1-4.4 2.26 5.403 5.403 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z',
  org: 'M12 7V3H2v18h20V7H12zM6 19H4v-2h2v2zm0-4H4v-2h2v2zm0-4H4V9h2v2zm0-4H4V5h2v2zm4 12H8v-2h2v2zm0-4H8v-2h2v2zm0-4H8V9h2v2zm0-4H8V5h2v2zm10 12h-8v-2h2v-2h-2v-2h2v-2h-2V9h8v10zm-2-8h-2v2h2v-2zm0 4h-2v2h2v-2z',
  select: 'M3 5h2V3c-1.1 0-2 .9-2 2zm0 8h2v-2H3v2zm4 8h2v-2H7v2zM3 9h2V7H3v2zm10-6h-2v2h2V3zm6 0v2h2c0-1.1-.9-2-2-2zM5 21v-2H3c0 1.1.9 2 2 2zm-2-4h2v-2H3v2zM9 3H7v2h2V3zm2 18h2v-2h-2v2zm8-8h2v-2h-2v2zm0 8c1.1 0 2-.9 2-2h-2v2zm0-12h2V7h-2v2zm0 8h2v-2h-2v2zm-4 4h2v-2h-2v2zm0-16h2V3h-2v2zM7 17h10V7H7v10zm2-8h6v6H9V9z',
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
function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 3500);
}
const fail = (e) => toast(e.message || String(e));

function dialog(title, body, buttons) {
  return new Promise((resolve) => {
    const back = h('div', { class: 'dialog-back' });
    const close = (v) => { back.remove(); resolve(v); };
    back.addEventListener('click', (e) => { if (e.target === back) close(null); });
    const btns = (buttons || [{ label: 'OK', value: true, primary: true }]).map((b) =>
      h('button', { class: `pillbtn noic ${b.primary ? 'primary' : ''} ${b.danger ? 'danger' : ''}`, onclick: () => close(typeof b.value === 'function' ? b.value() : b.value) }, b.label));
    back.append(h('div', { class: 'dialog', role: 'dialog' }, h('h2', null, title), body, h('div', { class: 'btns' }, btns)));
    document.body.append(back);
    const f = back.querySelector('input,select,textarea'); if (f) f.focus();
  });
}
const confirmDialog = (title, text, ok = 'OK', danger = false) => dialog(title, h('p', null, text), [{ label: 'Cancel', value: false }, { label: ok, value: true, primary: !danger, danger }]);

const MONTHS = Array.from({ length: 12 }, (_, i) => new Date(2000, i, 1).toLocaleString(undefined, { month: 'long' }));
function fmtDate(d) {
  if (!d) return '';
  const dt = new Date(d.year || 2000, d.month - 1, d.day);
  return d.year ? dt.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' }) : dt.toLocaleDateString(undefined, { month: 'long', day: 'numeric' });
}
function age(b) {
  if (!b || !b.year) return null;
  const t = new Date(); let a = t.getFullYear() - b.year;
  if (t.getMonth() + 1 < b.month || (t.getMonth() + 1 === b.month && t.getDate() < b.day)) a -= 1;
  return a;
}
const hue = (s) => { let x = 0; for (const c of s || '') x = (x * 31 + c.charCodeAt(0)) % 360; return x; };
const initials = (fn) => { const p = (fn || '?').trim().split(/\s+/); return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase(); };
function avatar(c, size = '') {
  const el = h('span', { class: `av ${size}`, style: { '--h': hue(c.fn) } });
  const ver = encodeURIComponent(c.updated || c.etag || '');
  if (c.hasPhoto) el.append(h('img', { src: `/api/contacts/${c.id}/photo?v=${ver}`, alt: '', loading: 'lazy', onerror: (e) => { e.target.remove(); el.textContent = initials(c.fn); } }));
  else if ((c.iopixPersonId || (c.iopix && c.iopix.personId)) && S.status.iopix) {
    const pid = c.iopixPersonId || c.iopix.personId;
    el.append(h('img', { src: `/api/iopix/face/${pid}`, alt: '', loading: 'lazy', onerror: (e) => { e.target.remove(); el.textContent = initials(c.fn); } }));
  } else el.textContent = initials(c.fn);
  return el;
}
async function copyText(t) { try { await navigator.clipboard.writeText(t); toast('Copied'); } catch { toast(t); } }
const copyRow = (v) => h('div', { class: 'copy' }, h('code', null, v), h('button', { class: 'iconbtn', title: 'Copy', onclick: () => copyText(v) }, icon('copy', 's')));

const SOCIAL_COLORS = { linkedin: ['#0a66c2', 'in'], facebook: ['#1877f2', 'f'], instagram: ['#d62976', 'IG'], x: ['#111', 'X'], threads: ['#111', '@'],
  bluesky: ['#1185fe', 'bs'], mastodon: ['#6364ff', 'M'], tiktok: ['#111', 'TT'], youtube: ['#ff0000', '▶'], snapchat: ['#e6c700', 'S'], pinterest: ['#e60023', 'P'],
  github: ['#24292f', 'GH'], reddit: ['#ff4500', 'r'], flickr: ['#0063dc', 'fl'], whatsapp: ['#25d366', 'W'], telegram: ['#229ed9', 'T'], signal: ['#3a76f0', 'S'], skype: ['#00aff0', 'S'], other: ['#888', '•'] };
const LABELS = { phone: ['mobile', 'home', 'work', 'main', 'iPhone', 'home fax', 'work fax', 'pager', 'other'], email: ['home', 'work', 'school', 'other'],
  address: ['home', 'work', 'school', 'other'], url: ['homepage', 'blog', 'work', 'home', 'other'], date: ['anniversary', 'wedding', 'graduation', 'memorial', 'other'] };

// ------------------------------------------------------------------ state
const S = { status: {}, user: null, suite: [], books: [], tags: [], rel: null, social: [], list: [], total: 0, scope: { kind: 'all' }, q: '', current: null,
  selecting: false, sel: new Set(), all: null };

function scopeParams() {
  const p = new URLSearchParams();
  if (S.q) p.set('q', S.q);
  if (S.scope.kind === 'fav') p.set('favorite', 'true');
  if (S.scope.kind === 'book') p.set('book', S.scope.id);
  if (S.scope.kind === 'tag') p.set('tag', S.scope.name);
  if (S.scope.kind === 'iopix') p.set('iopix_linked', 'true');
  p.set('order', localStorage.getItem('ioc.order') || 'given');
  return p;
}
const scopeHash = () => S.scope.kind === 'fav' ? '#/fav' : S.scope.kind === 'book' ? `#/book/${S.scope.id}` : S.scope.kind === 'tag' ? `#/tag/${encodeURIComponent(S.scope.name)}` : '#/';
const scopeTitle = () => S.scope.kind === 'fav' ? 'Favorites' : S.scope.kind === 'book' ? (S.books.find((b) => b.id === +S.scope.id) || {}).name || 'Address book'
  : S.scope.kind === 'tag' ? S.scope.name : 'All contacts';

async function loadMeta() {
  const [b, t] = await Promise.all([api('/api/books'), api('/api/tags')]);
  S.books = b.items; S.tags = t.items;
  if (!S.rel) { S.rel = await api('/api/relation-types'); S.social = (await api('/api/social-services')).items; }
  drawNav();
}
async function loadList() {
  const r = await api('/api/contacts?' + scopeParams());
  S.list = r.items; S.total = r.total;
}
async function allContacts() {
  if (!S.all) S.all = (await api('/api/contacts?limit=20000')).items;
  return S.all;
}
// Case- and accent-insensitive matching ("celia" finds "Célia"), like the server's search.
const FOLD_EXTRA = { ø: 'o', đ: 'd', ð: 'd', ł: 'l', ħ: 'h', ŧ: 't', ı: 'i', æ: 'ae', œ: 'oe', þ: 'th', ß: 'ss' };
const fold = (s) => (s || '').toLowerCase().normalize('NFKD').replace(/\p{M}/gu, '').replace(/[øđðłħŧıæœþß]/g, (ch) => FOLD_EXTRA[ch]);
const writableBooks = () => S.books.filter((b) => b.writable);

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
    const theme = localStorage.getItem('ioc.theme') || 'system';
    menu = h('div', { class: 'menu' },
      h('div', { class: 'who' }, h('b', null, S.user.displayName), h('div', { class: 'muted small' }, `${S.user.name} · ${S.user.role}`)),
      h('a', { class: 'mi', href: '#/settings/account', onclick: closeMenu }, icon('person', 's'), 'Account'),
      h('a', { class: 'mi', href: '#/settings/devices', onclick: closeMenu }, icon('devices', 's'), 'Connect apps and devices'),
      h('button', { class: 'mi', onclick: () => { const n = { system: 'light', light: 'dark', dark: 'system' }[theme]; localStorage.setItem('ioc.theme', n); applyTheme(); closeMenu(); toast(`Appearance: ${n}`); } },
        icon('theme', 's'), `Appearance: ${theme}`),
      h('a', { class: 'mi', href: '#/settings', onclick: closeMenu }, icon('settings', 's'), 'Settings'),
      h('a', { class: 'mi', href: '#/maintenance', onclick: closeMenu }, icon('wrench', 's'), 'Maintenance'),
      h('button', { class: 'mi', onclick: async () => { closeMenu(); if (await signOutElsewhere()) toast('Signed out elsewhere'); } }, icon('devices', 's'), 'Sign out everywhere else'),
      h('button', { class: 'mi', onclick: async () => { await api('/api/auth/logout', { method: 'POST' }); location.reload(); } }, icon('logout', 's'), 'Sign out'));
    m.append(menu);
    setTimeout(() => document.addEventListener('click', outside), 0);
  };
  m.append(btn);
}
/* The suite (iosuite-shared's suite_apps): when other ioThing apps are registered, the app mark top left (in the sidebar; in
   the top bar on a phone) opens a menu of them, each a link to that app. Alone, the mark stays the link to All contacts. */
async function loadSuite() {
  try {
    const r = await api('/api/auth/suite');
    S.suite = (r.items || []).filter((a) => a.app !== r.app && a.url);
  } catch { S.suite = []; }
  const b = $('#suitebtn');
  if (b) { b.hidden = !S.suite.length; b.onclick = () => toggleSuite(b); }
  if (!S.suite.length) closeSuite();
  drawNav();
}
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
  return h('a', { class: 'apptile', href: a.url, role: 'menuitem', title: a.description || a.name, onclick: closeSuite },
    ic, h('span', { class: 'appnm' }, a.name || a.app));
}
function toggleSuite(btn) {
  if (suitePop) { closeSuite(); return; }
  if (!S.suite.length) return;
  suitePop = h('div', { class: 'suitepop', role: 'menu', 'aria-label': 'ioThing apps', style: { '--cols': String(Math.min(3, S.suite.length)) } }, S.suite.map(appTile));
  document.body.append(suitePop);
  const r = btn.getBoundingClientRect();
  suitePop.style.top = `${Math.round(r.bottom + 6)}px`;
  suitePop.style.left = `${Math.round(Math.max(8, Math.min(r.left - 6, innerWidth - suitePop.offsetWidth - 8)))}px`;
  setTimeout(() => { document.addEventListener('click', suiteOutside, true); document.addEventListener('keydown', suiteKey); addEventListener('resize', closeSuite); }, 0);
}
function applyTheme() {
  const t = localStorage.getItem('ioc.theme') || 'system';
  if (t === 'system') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
}

/* The sidebar, as in ioPix: the name on top, the destinations in groups, Settings and Maintenance at the foot. It docks
   beside the page on a wide screen unless its button put it away (remembered); otherwise it slides over the page from the
   menu button. Phones get a bottom bar instead: four destinations and More. */
const DOCK_MIN = 1100;
function drawNav() {
  const nav = $('#nav'); const r = route();
  const listView = ['list', 'contact', 'edit', 'new'].includes(r.view);
  const link = (v, href, ic, label, n, on, hue) => h('a', { href, 'data-v': v, class: on ? 'on' : null, style: hue ? { '--hue': `var(${hue})` } : null },
    icon(ic), h('span', { class: 'nl' }, label), n ? h('span', { class: 'n' }, n) : null);
  const sec = (label, btn) => h('div', { class: 'navsec' }, h('span', null, label), btn || null);
  const total = S.books.reduce((a, b) => a + (b.count || 0), 0);
  nav.replaceChildren(...[
    h('div', { class: 'navhead' },
      S.suite.length
        ? h('div', { class: 'brand' },
          h('button', { class: 'suitebtn', title: 'ioThing apps', 'aria-label': 'ioThing apps', 'aria-haspopup': 'menu', onclick: (e) => toggleSuite(e.currentTarget) },
            h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' })),
          h('a', { class: 'brand-name', href: '#/', title: 'All contacts' }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Contacts')))
        : h('a', { class: 'brand', href: '#/', title: 'All contacts' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }),
          h('span', { class: 'brand-name' }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Contacts'))),
      h('button', { id: 'sidebtn', class: 'iconbtn', onclick: sidebarButton })),
    link('all', '#/', 'people', 'All contacts', total, listView && S.scope.kind === 'all', '--c-purple'),
    link('fav', '#/fav', 'star', 'Favorites', null, listView && S.scope.kind === 'fav', '--c-amber'),
    link('upcoming', '#/upcoming', 'cake', 'Birthdays', null, r.view === 'upcoming', '--c-rose'),
    S.status.iopix ? link('iopix', '#/iopix', 'image', 'ioPix people', null, r.view === 'iopix', '--c-indigo') : null,
    h('button', { class: 'navmore', 'data-v': 'more', title: 'More', onclick: moreSheet }, icon('more'), h('span', { class: 'nl' }, 'More')),
    h('div', { class: 'navgap' }),
    sec('Address books', h('button', { class: 'iconbtn', title: 'New address book', onclick: newBook }, icon('add', 's'))),
    S.books.map((b) => h('a', { href: `#/book/${b.id}`, 'data-v': 'book', class: listView && S.scope.kind === 'book' && +S.scope.id === b.id ? 'on' : null,
      style: { '--hue': b.color || (b.shared ? 'var(--c-purple)' : 'var(--c-teal)') } },
      h('span', { class: 'ic dotic' }, h('span', { class: 'dot' })), h('span', { class: 'nl' }, b.name), h('span', { class: 'n' }, b.count))),
    S.tags.length ? [h('div', { class: 'navgap' }), sec('Labels'),
      S.tags.map((t) => h('a', { href: `#/tag/${encodeURIComponent(t.tag)}`, 'data-v': 'tag', class: listView && S.scope.kind === 'tag' && S.scope.name === t.tag ? 'on' : null, style: { '--hue': 'var(--c-orange)' } },
        icon('tag'), h('span', { class: 'nl' }, t.tag), h('span', { class: 'n' }, t.n)))] : null,
    h('div', { class: 'navgap' }), sec('Manage'),
    link('import', '#/import', 'upload', 'Import and export', null, r.view === 'import', '--c-green'),
    h('div', { class: 'navfoot' },
      link('settings', '#/settings', 'settings', 'Settings', null, r.view === 'settings'),
      link('maint', '#/maintenance', 'wrench', 'Maintenance', S.status.suggestions || null, r.view === 'maint')),
  ].flat(3).filter(Boolean));
  applySidebar();
  $('.navmore')?.classList.toggle('on', ['book', 'tag', 'import', 'settings', 'maint', 'iopix'].some((v) => (v === 'book' || v === 'tag') ? listView && S.scope.kind === v : r.view === v));
}
function sideDockedPref() { try { return localStorage.getItem('ioc.sidebar') !== '0'; } catch { return true; } }
function applySidebar() {
  const body = document.body, btn = $('#sidebtn');
  const docked = innerWidth >= DOCK_MIN && sideDockedPref();
  body.classList.toggle('side-docked', docked);
  if (docked) closeNav();
  if (!btn) return;
  const [ic, title] = docked ? ['menuOpen', 'Hide the sidebar'] : innerWidth >= DOCK_MIN ? ['pin', 'Keep the sidebar open'] : ['close', 'Close the sidebar'];
  btn.replaceChildren(icon(ic)); btn.title = title; btn.setAttribute('aria-label', title);
}
function sidebarButton() {
  if (document.body.classList.contains('side-docked')) { try { localStorage.setItem('ioc.sidebar', '0'); } catch { /* */ } }
  else if (innerWidth >= DOCK_MIN) { try { localStorage.setItem('ioc.sidebar', '1'); } catch { /* */ } }
  else { closeNav(); return; }
  applySidebar();
}
function openNav() { document.body.classList.add('side-open'); $('#navscrim').hidden = false; }
function closeNav() { document.body.classList.remove('side-open'); $('#navscrim').hidden = true; }
/** Phones: what the bottom bar has no room for. */
function moreSheet() {
  const r = route(); const listView = ['list', 'contact', 'edit', 'new'].includes(r.view);
  const tile = (href, ic, label, hue, on) => h('a', { href, class: on ? 'on' : null, style: { '--hue': hue } }, h('span', { class: 'sic' }, icon(ic)), h('span', null, label));
  const grid = h('div', { class: 'sheetgrid' },
    S.books.map((b) => tile(`#/book/${b.id}`, 'book', b.name, b.color || (b.shared ? 'var(--c-purple)' : 'var(--c-teal)'), listView && S.scope.kind === 'book' && +S.scope.id === b.id)),
    S.tags.map((t) => tile(`#/tag/${encodeURIComponent(t.tag)}`, 'tag', t.tag, 'var(--c-orange)', listView && S.scope.kind === 'tag' && S.scope.name === t.tag)),
    S.status.iopix ? tile('#/iopix', 'image', 'ioPix people', 'var(--c-indigo)', r.view === 'iopix') : null,
    tile('#/import', 'upload', 'Import and export', 'var(--c-green)', r.view === 'import'),
    tile('#/settings', 'settings', 'Settings', 'var(--c-slate)', r.view === 'settings'),
    tile('#/maintenance', 'wrench', 'Maintenance', 'var(--c-slate)', r.view === 'maint'));
  const p = dialog('More', grid, [{ label: 'Close', value: null }]);
  grid.addEventListener('click', (e) => { if (e.target.closest('a')) document.querySelector('.dialog-back')?.remove(); });
  return p;
}

async function newBook() {
  const name = h('input', { class: 't', placeholder: 'Name, e.g. Work or School friends' });
  const shared = h('input', { type: 'checkbox' });
  const body = h('div', null, name, S.user.role !== 'viewer' ? h('label', { class: 'prefck', style: { marginTop: '10px' } }, shared, 'Shared with the whole family') : null);
  if (!await dialog('New address book', body, [{ label: 'Cancel', value: false }, { label: 'Create', value: true, primary: true }])) return;
  try { const r = await api('/api/books', { method: 'POST', json: { name: name.value, shared: shared.checked } }); await loadMeta(); location.hash = `#/book/${r.book.id}`; } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ routing
function route() {
  const p = location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
  const [a, b, c] = p;
  if (!a) return { view: 'list' };
  if (a === 'c' && b) return c === 'edit' ? { view: 'edit', id: +b } : { view: 'contact', id: +b };
  if (a === 'new') return { view: 'new' };
  if (a === 'fav') return { view: 'list', scope: { kind: 'fav' } };
  if (a === 'book') return { view: 'list', scope: { kind: 'book', id: +b } };
  if (a === 'tag') return { view: 'list', scope: { kind: 'tag', name: b } };
  if (a === 'tree' && b) return { view: 'tree', id: +b };
  if (a === 'maintenance') return { view: 'maint', tab: b || 'dups' };
  if (['upcoming', 'import', 'iopix'].includes(a)) return { view: a };
  if (a === 'settings') return { view: 'settings', tab: b || 'account' };
  return { view: 'list' };
}

async function onRoute() {
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
      await ({ upcoming: showUpcoming, maint: showMaint, import: showImport, iopix: showIopix, settings: showSettings, tree: showTree })[r.view](page, r);
    }
  } catch (e) { fail(e); }
  drawNav();
}

function emptyDetail() {
  return h('div', { class: 'empty' }, icon('book'), h('p', null, S.total ? 'Pick a contact on the left.' : 'No contacts here yet.'),
    h('p', null, h('a', { class: 'lnk', href: '#/new' }, 'New contact'), ' · ', h('a', { class: 'lnk', href: '#/import' }, 'Import from a file')));
}

// ------------------------------------------------------------------ the list
function drawList() {
  const pane = $('#main .listpane'); if (!pane) return;
  const keep = pane.scrollTop;
  const r = route();
  const order = localStorage.getItem('ioc.order') || 'given';
  const head = h('div', { class: 'listhead' }, h('button', { class: 'iconbtn back', style: { display: 'none' } }),
    h('span', { class: 'title' }, scopeTitle()), h('span', { class: 'count' }, S.total),
    h('span', { class: 'tools' },
      h('button', { class: `iconbtn ${S.selecting ? 'on' : ''}`, title: 'Select', onclick: () => { S.selecting = !S.selecting; S.sel.clear(); drawList(); } }, icon('select', 's')),
      h('button', { class: 'iconbtn', title: `Sort by ${order === 'given' ? 'last name' : 'first name'}`, onclick: () => { localStorage.setItem('ioc.order', order === 'given' ? 'family' : 'given'); onRoute(); } },
        h('span', { class: 'small', style: { fontWeight: 600 } }, order === 'given' ? 'A·first' : 'A·last')),
      h('a', { class: 'iconbtn', title: 'Download these as vCards', href: `/api/contacts?${scopeParams()}&format=vcard` }, icon('download', 's'))));
  const kids = [head];
  if (S.selecting) kids.push(selBar());
  let last = null;
  for (const c of S.list) {
    const key = order === 'family' ? (c.family || c.fn) : (c.given || c.fn);
    const L = (key || '#').trim().charAt(0).toUpperCase();
    const letter = /[A-ZÀ-ɏ]/i.test(L) ? L : '#';
    if (!S.q && letter !== last && order !== 'updated') { kids.push(h('div', { class: 'letter' }, letter)); last = letter; }
    const sub = c.org && c.title ? `${c.title}, ${c.org}` : c.org || c.email || c.phone || '';
    const row = h('a', { class: `row ${r.id === c.id ? 'on' : ''}`, href: `#/c/${c.id}`, onclick: (e) => { if (S.selecting) { e.preventDefault(); toggleSel(c.id); } } },
      S.selecting ? h('input', { type: 'checkbox', checked: S.sel.has(c.id), onclick: (e) => { e.stopPropagation(); toggleSel(c.id); } }) : null,
      avatar(c), h('div', { class: 'who' }, h('div', { class: 'nm' }, c.fn), sub ? h('div', { class: 'sub' }, sub) : null),
      c.favorite ? icon('star', 's star') : null);
    kids.push(row);
  }
  if (!S.list.length) kids.push(h('div', { class: 'empty' }, S.q ? `Nothing matches “${S.q}”.` : 'No contacts here yet.'));
  pane.replaceChildren(...kids);
  pane.scrollTop = keep;
}
function toggleSel(id) { if (S.sel.has(id)) S.sel.delete(id); else S.sel.add(id); drawList(); }
function selBar() {
  const ids = [...S.sel];
  const act = async (action, extra = {}) => {
    if (!ids.length) return toast('Select some contacts first');
    if (action === 'delete' && !await confirmDialog('Delete contacts', `Delete ${ids.length} contact(s)? This cannot be undone.`, 'Delete', true)) return;
    try { await api('/api/contacts/bulk', { method: 'POST', json: { ids, action, ...extra } }); S.sel.clear(); S.all = null; await loadMeta(); onRoute(); toast('Done'); } catch (e) { fail(e); }
  };
  return h('div', { class: 'selbar' }, h('b', null, `${ids.length} selected`),
    h('button', { class: 'pillbtn noic', onclick: () => { S.list.forEach((c) => S.sel.add(c.id)); drawList(); } }, 'All'),
    h('button', { class: 'pillbtn noic', onclick: () => act('favorite') }, '★'),
    h('button', { class: 'pillbtn noic', onclick: async () => {
      const t = h('input', { class: 't', placeholder: 'Label', list: 'taglist' });
      const v = await dialog('Add a label', h('div', null, t, h('datalist', { id: 'taglist' }, S.tags.map((x) => h('option', { value: x.tag })))), [{ label: 'Cancel', value: null }, { label: 'Add', value: () => t.value, primary: true }]);
      if (v) act('tag', { tag: v });
    } }, 'Label'),
    h('button', { class: 'pillbtn noic', onclick: async () => {
      const sel = h('select', { class: 't' }, writableBooks().map((b) => h('option', { value: b.id }, b.name)));
      const v = await dialog('Move to', sel, [{ label: 'Cancel', value: null }, { label: 'Move', value: () => sel.value, primary: true }]);
      if (v) act('move', { book: +v });
    } }, 'Move'),
    h('a', { class: 'pillbtn noic', href: `/api/export?format=vcf&ids=${ids.join(',')}` }, 'Export'),
    h('button', { class: 'pillbtn noic danger', onclick: () => act('delete') }, 'Delete'));
}

// ------------------------------------------------------------------ a contact
async function showContact(id, pane) {
  const c = await api(`/api/contacts/${id}`);
  S.current = c;
  const book = S.books.find((b) => b.id === c.bookId);
  const canEdit = book && book.writable;
  const back = h('button', { class: 'iconbtn back', title: 'Back', onclick: () => { location.hash = scopeHash(); } }, icon('back'));
  const sub = [c.title, c.department, c.org].filter(Boolean).join(' · ');
  const fav = h('button', { class: `iconbtn ${c.favorite ? 'on' : ''}`, title: c.favorite ? 'Remove from favorites' : 'Add to favorites', disabled: !canEdit,
    onclick: async () => { try { await api(`/api/contacts/${id}`, { method: 'PATCH', json: { favorite: !c.favorite } }); onRoute(); } catch (e) { fail(e); } } }, icon(c.favorite ? 'star' : 'starO'));
  const a = age(c.birthday);
  const headChips = [c.nickname ? h('span', { class: 'chip' }, `“${c.nickname}”`) : null,
    book ? h('a', { class: 'chip', href: `#/book/${book.id}` }, h('span', { class: 'dot', style: { width: '8px', height: '8px', borderRadius: '50%', background: book.color || (book.shared ? 'var(--c-purple)' : 'var(--c-teal)') } }), book.name) : null,
    ...c.tags.map((t) => h('a', { class: 'chip', href: `#/tag/${encodeURIComponent(t)}` }, icon('tag', 's'), t))];
  const cards = [];
  const card = (ic, title, hueVar, ...body) => h('div', { class: 'card', style: { '--hue': `var(${hueVar})` } }, h('h3', null, icon(ic), title), ...body);
  const kv = (k, v, pref) => h('div', { class: 'kv' }, h('div', { class: 'k' }, k || ''), h('div', { class: 'v' }, v, pref ? h('span', { class: 'pref' }, '★') : null));
  if (c.phones.length) cards.push(card('phone', 'Phone', '--c-green', c.phones.map((p) => kv(p.label, h('a', { class: 'lnk', href: `tel:${p.value.replace(/[^\d+]/g, '')}` }, p.value), p.pref))));
  if (c.emails.length) cards.push(card('mail', 'Email', '--c-blue', c.emails.map((e) => kv(e.label, h('a', { class: 'lnk', href: `mailto:${e.value}` }, e.value), e.pref))));
  if (c.addresses.length) cards.push(card('place', 'Address', '--c-rose', c.addresses.map((ad) => {
    const lines = [ad.pobox && `PO Box ${ad.pobox}`, ad.ext, ad.street, [ad.postcode, ad.city].filter(Boolean).join(' '), ad.region, ad.country].filter(Boolean);
    const q = encodeURIComponent(lines.join(', '));
    return kv(ad.label, h('div', null, lines.map((l) => h('div', null, l)), h('a', { class: 'lnk small', href: `https://www.openstreetmap.org/search?query=${q}`, target: '_blank', rel: 'noopener' }, 'Map')));
  })));
  if (c.birthday || c.dates.length) cards.push(card('cake', 'Dates', '--c-amber',
    c.birthday ? kv('birthday', h('span', null, fmtDate(c.birthday), a != null ? h('span', { class: 'muted' }, ` · ${a} years old`) : null,
      c.birthdayRemind === false ? h('span', { class: 'muted', title: 'Left out of the birthday calendar, the start page and other apps' }, ' · no reminder') : null)) : null,
    c.dates.map((d) => kv(d.label, h('span', null, fmtDate(d), d.year ? h('span', { class: 'muted' }, ` · ${age(d)} years`) : null)))));
  if (c.relations.length) {
    const fam = new Set(S.rel.groups[0].types.map((t) => t.type));
    const chip = (r) => r.relatedId ? h('a', { class: 'chip rel', href: `#/c/${r.relatedId}` }, avatar({ id: r.relatedId, fn: r.relatedFn, hasPhoto: r.relatedHasPhoto, iopixPersonId: r.relatedIopixPersonId }, 's'), r.relatedFn, h('span', { class: 'lab' }, r.typeLabel))
      : h('span', { class: 'chip rel' }, avatar({ fn: r.relatedName }, 's'), r.relatedName, h('span', { class: 'lab' }, r.typeLabel));
    const famRels = c.relations.filter((r) => fam.has(r.type)), others = c.relations.filter((r) => !fam.has(r.type));
    cards.push(card('tree', 'Relations', '--c-purple',
      famRels.length ? h('div', null, famRels.map(chip)) : null, others.length ? h('div', null, others.map(chip)) : null,
      famRels.some((r) => r.relatedId) ? h('a', { class: 'lnk small', href: `#/tree/${c.id}` }, 'Family tree') : null));
  }
  if (c.social.length) cards.push(card('people', 'Social', '--c-indigo', h('div', null, c.social.map((s) => {
    const [col, ab] = SOCIAL_COLORS[s.service] || SOCIAL_COLORS.other;
    const name = (S.social.find((x) => x.service === s.service) || {}).name || s.service;
    const show = s.value.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '');
    return h('a', { class: 'social', href: s.url, target: '_blank', rel: 'noopener', title: name }, h('span', { class: 'badge', style: { background: col } }, ab), show);
  }))));
  if (c.urls.length) cards.push(card('link', 'Websites', '--c-cyan', c.urls.map((u) => kv(u.label, h('a', { class: 'lnk', href: /^[a-z]+:/i.test(u.value) ? u.value : `https://${u.value}`, target: '_blank', rel: 'noopener' }, u.value)))));
  if (c.iopix) cards.push(card('image', 'ioPix', '--c-indigo', h('div', { class: 'iopixcard' },
    h('img', { src: `/api/iopix/face/${c.iopix.personId}`, alt: '', onerror: (e) => { e.target.style.visibility = 'hidden'; } }),
    h('div', null, h('div', null, h('b', null, c.iopix.name || `Person ${c.iopix.personId}`)),
      c.iopix.url ? h('a', { class: 'lnk', href: c.iopix.url, target: '_blank', rel: 'noopener' }, 'Photos in ioPix ', icon('open', 's')) : null,
      canEdit ? h('div', { style: { marginTop: '6px', display: 'flex', gap: '6px', flexWrap: 'wrap' } },
        h('button', { class: 'pillbtn noic', onclick: async () => { try { await api(`/api/contacts/${id}/photo/from-iopix`, { method: 'POST' }); toast('Photo taken from ioPix'); onRoute(); } catch (e) { fail(e); } } }, 'Use as photo'),
        h('button', { class: 'pillbtn noic', onclick: async () => { await api(`/api/contacts/${id}`, { method: 'PATCH', json: { iopix: null } }); onRoute(); } }, 'Unlink')) : null))));
  if (c.notes) cards.push(card('note', 'Notes', '--c-slate', h('div', { class: 'notes' }, c.notes)));
  const meCard = S.user.meContactId === c.id;
  const tools = h('div', { class: 'dtools' },
    canEdit ? h('a', { class: 'pillbtn primary', href: `#/c/${id}/edit` }, icon('edit', 's'), 'Edit') : null,
    h('a', { class: 'pillbtn', href: `/api/contacts/${id}?format=vcard` }, icon('download', 's'), 'vCard'),
    S.status.iopix && !c.iopix && canEdit ? h('button', { class: 'pillbtn', onclick: () => pickIopix(c, true) }, icon('image', 's'), 'Link to ioPix') : null,
    !canEdit ? null : h('button', { class: 'pillbtn', title: 'Look this person up (Gravatar by email, and their GitHub, Mastodon and Bluesky profiles). What is found waits for you to accept it.', onclick: async (e) => {
      e.currentTarget.disabled = true;
      try { const r = await api(`/api/contacts/${id}/lookup`, { method: 'POST' }); toast(r.added ? `${r.added} suggestion${r.added === 1 ? '' : 's'} found` : r.errors.length ? `Nothing new (${r.errors[0]})` : 'Nothing new found'); await refreshStatus(); onRoute(); } catch (err) { fail(err); }
    } }, icon('bulb', 's'), 'Look up'),
    h('button', { class: 'pillbtn', title: 'Tell CardDAV apps that this card is you', onclick: async () => { await api('/api/auth/me', { method: 'PATCH', json: { meContactId: meCard ? null : c.id } }); S.user = (await api('/api/auth/me')).user; toast(meCard ? 'Not you any more' : 'This is now your own card'); onRoute(); } },
      icon('person', 's'), meCard ? 'This is me ✓' : 'This is me'),
    canEdit ? h('button', { class: 'pillbtn danger', onclick: async () => {
      if (!await confirmDialog('Delete contact', `Delete ${c.fn}? Apps synced over CardDAV will delete it too.`, 'Delete', true)) return;
      try { await api(`/api/contacts/${id}`, { method: 'DELETE' }); S.all = null; await loadMeta(); location.hash = scopeHash(); } catch (e) { fail(e); }
    } }, icon('delete', 's'), 'Delete') : null);
  let sugg = [];
  try { sugg = (await api(`/api/suggestions?contact=${id}`)).items; } catch { /* none */ }
  if (sugg.length) cards.unshift(h('div', { class: 'card sugg', style: { '--hue': 'var(--c-amber)' } }, h('h3', null, icon('bulb'), `Suggestions (${sugg.length})`),
    h('p', { class: 'muted small' }, 'Found by a lookup or an assistant. Nothing changes until you accept.'), suggList(sugg, canEdit, () => onRoute())));
  pane.replaceChildren(h('div', { class: 'detail' },
    h('div', { class: 'dhead' }, back, avatar(c, 'xl'), h('div', { style: { flex: 1, minWidth: '200px' } },
      h('h1', null, c.fn), sub ? h('div', { class: 'sub' }, sub) : null, c.maiden ? h('div', { class: 'sub' }, `née ${c.maiden}`) : null, h('div', { class: 'chips' }, headChips)), fav),
    tools, cards.length ? h('div', { class: 'cards' }, cards) : h('p', { class: 'muted' }, 'Nothing else is known about this contact yet.'),
    h('p', { class: 'muted small', style: { marginTop: '24px' } }, `Changed ${new Date(c.updated).toLocaleString()} · UID ${c.uid}`)));
  pane.scrollTop = 0;
}

// ------------------------------------------------------------------ the edit form
async function showEdit(id, pane) {
  const c = id ? await api(`/api/contacts/${id}`) : { name: {}, phones: [{ label: 'mobile', value: '' }], emails: [{ label: 'home', value: '' }], addresses: [], urls: [], social: [], dates: [], relations: [], tags: [],
    bookId: ((S.scope.kind === 'book' && writableBooks().find((b) => b.id === +S.scope.id)) || writableBooks().find((b) => b.shared) || writableBooks()[0] || {}).id, kind: 'individual' };
  const f = JSON.parse(JSON.stringify(c));
  f.name = f.name || {};
  let photoFile = null, dropPhoto = false;
  const inp = (obj, key, ph, attrs = {}) => h('input', { class: 't', value: obj[key] || '', placeholder: ph || '', oninput: (e) => { obj[key] = e.target.value; }, ...attrs });
  const fld = (label, el) => h('label', { class: 'field' }, h('span', null, label), el);
  const sel = (obj, key, opts, extra = {}) => h('select', { class: 't', onchange: (e) => { obj[key] = e.target.value; }, ...extra },
    opts.map((o) => { const [v, l] = Array.isArray(o) ? o : [o, o]; return h('option', { value: v, selected: (obj[key] || '') === v ? true : null }, l); }));
  const labelSel = (obj, kind) => {
    const opts = [...LABELS[kind]]; if (obj.label && !opts.includes(obj.label)) opts.push(obj.label);
    const s = h('select', { class: 't' }, h('option', { value: '' }, '—'), opts.map((o) => h('option', { value: o, selected: (obj.label || '') === o ? true : null }, o)), h('option', { value: '__custom' }, 'Custom…'));
    s.onchange = async () => {
      if (s.value === '__custom') {
        const t = h('input', { class: 't', placeholder: 'Label' });
        const v = await dialog('Custom label', t, [{ label: 'Cancel', value: null }, { label: 'OK', value: () => t.value.trim(), primary: true }]);
        if (v) { obj.label = v; s.insertBefore(h('option', { value: v }, v), s.lastChild); s.value = v; } else s.value = obj.label || '';
      } else obj.label = s.value || null;
    };
    return s;
  };
  const rm = (arr, x, redraw) => h('button', { class: 'iconbtn', title: 'Remove', type: 'button', onclick: () => { arr.splice(arr.indexOf(x), 1); redraw(); } }, icon('close', 's'));
  const prefBox = (obj) => h('label', { class: 'prefck', title: 'Preferred' }, h('input', { type: 'checkbox', checked: !!obj.pref, onchange: (e) => { obj.pref = e.target.checked ? 1 : 0; } }), '★');

  function multi(title, ic, arr, kind, rowFn, blank) {
    const box = h('div');
    const draw = () => {
      box.replaceChildren(...arr.map((x) => rowFn(x, draw)), h('button', { class: 'addbtn', type: 'button', onclick: () => { arr.push(blank()); draw(); const ins = box.querySelectorAll('input'); if (ins.length) ins[ins.length - 1].focus(); } }, icon('add', 's'), `Add ${kind}`));
    };
    draw();
    return [h('div', { class: 'fsec' }, icon(ic), title), box];
  }
  const phones = multi('Phone numbers', 'phone', f.phones, 'phone', (x, d) => h('div', { class: 'multi' }, labelSel(x, 'phone'), inp(x, 'value', 'Phone', { type: 'tel' }), prefBox(x), rm(f.phones, x, d)), () => ({ label: 'mobile', value: '' }));
  const emails = multi('Email addresses', 'mail', f.emails, 'email', (x, d) => h('div', { class: 'multi' }, labelSel(x, 'email'), inp(x, 'value', 'Email', { type: 'email' }), prefBox(x), rm(f.emails, x, d)), () => ({ label: 'home', value: '' }));
  const addrs = multi('Addresses', 'place', f.addresses, 'address', (x, d) => h('div', { class: 'multi' }, labelSel(x, 'address'),
    h('div', { class: 'addr' }, inp(x, 'street', 'Street', { style: 'grid-column: 1 / -1' }), inp(x, 'ext', 'Apartment, suite…'), inp(x, 'city', 'City'), inp(x, 'region', 'State / region'),
      inp(x, 'postcode', 'Postal code'), inp(x, 'country', 'Country'), inp(x, 'pobox', 'PO Box')), prefBox(x), rm(f.addresses, x, d)), () => ({ label: 'home' }));
  const social = multi('Social profiles', 'people', f.social, 'profile', (x, d) => h('div', { class: 'multi' },
    sel(x, 'service', S.social.map((s) => [s.service, s.name])), inp(x, 'value', 'Profile address or user name'), rm(f.social, x, d)), () => ({ service: 'linkedin', value: '' }));
  const urls = multi('Websites', 'link', f.urls, 'website', (x, d) => h('div', { class: 'multi' }, labelSel(x, 'url'), inp(x, 'value', 'https://…', { type: 'url' }), rm(f.urls, x, d)), () => ({ label: 'homepage', value: '' }));
  const dateInputs = (obj) => [
    h('select', { class: 't dt', style: 'width:130px', onchange: (e) => { obj.month = +e.target.value || null; } }, h('option', { value: '' }, 'Month'), MONTHS.map((m, i) => h('option', { value: i + 1, selected: obj.month === i + 1 ? true : null }, m))),
    h('input', { class: 't dt', style: 'width:80px', type: 'number', min: 1, max: 31, placeholder: 'Day', value: obj.day || '', oninput: (e) => { obj.day = +e.target.value || null; } }),
    h('input', { class: 't dt', style: 'width:100px', type: 'number', min: 1, max: 9999, placeholder: 'Year', value: obj.year || '', oninput: (e) => { obj.year = +e.target.value || null; } })];
  f.birthday = f.birthday || {};
  const dates = multi('Other dates', 'event', f.dates, 'date', (x, d) => h('div', { class: 'multi' }, labelSel(x, 'date'), ...dateInputs(x), rm(f.dates, x, d)), () => ({ label: 'anniversary' }));

  // relations: a type (gendered labels set the other person's gender when unknown) and a contact or a plain name
  const everyone = await allContacts();
  const relOpts = () => S.rel.groups.map((g) => h('optgroup', { label: g.name }, g.types.flatMap((t) => t.male !== t.female
    ? [h('option', { value: `${t.type}|` }, t.label), h('option', { value: `${t.type}|M` }, t.male), h('option', { value: `${t.type}|F` }, t.female)]
    : [h('option', { value: `${t.type}|` }, t.label)])));
  const rels = multi('Relations', 'tree', f.relations, 'relation', (x, d) => {
    const s = h('select', { class: 't', style: 'width:170px' }, relOpts());
    const g = x.gender || x.relatedGender || '';
    s.value = `${x.type}|${g}`; if (!s.value) s.value = `${x.type}|`;
    s.onchange = () => { const [t, gg] = s.value.split('|'); x.type = t; x.gender = gg || null; };
    const pick = h('div', { class: 'picker' });
    const box = h('input', { class: 't', placeholder: 'Contact or name', value: x.relatedFn || x.relatedName || '' });
    const drop = h('div', { class: 'drop', hidden: true });
    box.oninput = () => {
      x.relatedId = null; x.relatedName = box.value; x.relatedFn = null;
      const q = fold(box.value).trim();
      const hits = q ? everyone.filter((p) => p.id !== f.id && q.split(/\s+/).every((w) => fold(p.fn).includes(w))).slice(0, 12) : [];
      drop.replaceChildren(...hits.map((p) => h('div', { class: 'row', onmousedown: (e) => { e.preventDefault(); x.relatedId = p.id; x.relatedFn = p.fn; x.relatedName = null; box.value = p.fn; drop.hidden = true; } }, avatar(p, 's'), h('div', { class: 'who' }, h('div', { class: 'nm' }, p.fn)))));
      drop.hidden = !hits.length;
    };
    box.onblur = () => setTimeout(() => { drop.hidden = true; }, 150);
    pick.append(box, drop);
    return h('div', { class: 'multi' }, s, pick, x.relatedId ? h('span', { class: 'muted small', title: 'Linked to a contact' }, icon('link', 's')) : null, rm(f.relations, x, d));
  }, () => ({ type: 'sibling', relatedName: '' }));

  // ioPix
  const iopixBox = h('div');
  const drawIopix = () => iopixBox.replaceChildren(f.iopix && f.iopix.personId
    ? h('div', { class: 'iopixcard' }, h('img', { src: `/api/iopix/face/${f.iopix.personId}`, alt: '' }), h('b', null, f.iopix.name), h('button', { class: 'pillbtn noic', type: 'button', onclick: () => { f.iopix = null; drawIopix(); } }, 'Unlink'))
    : h('button', { class: 'pillbtn', type: 'button', onclick: async () => { const p = await pickIopix(f, false); if (p) { f.iopix = { personId: p.id, name: p.name }; drawIopix(); } } }, icon('image', 's'), 'Link to an ioPix person'));
  drawIopix();

  // photo
  const prev = h('span');
  const drawPhoto = () => prev.replaceChildren(photoFile ? h('span', { class: 'av xl' }, h('img', { src: URL.createObjectURL(photoFile), alt: '', onload: (e) => URL.revokeObjectURL(e.target.src) })) : dropPhoto ? avatar({ fn: f.fn || f.name.given || '?' }, 'xl') : avatar(c.id ? c : { fn: '?' }, 'xl'));
  drawPhoto();
  const file = h('input', { type: 'file', accept: 'image/jpeg,image/png,image/webp,image/gif', hidden: true, onchange: (e) => { photoFile = e.target.files[0] || null; dropPhoto = false; drawPhoto(); } });

  const tagIn = h('input', { class: 't', value: (f.tags || []).join(', '), placeholder: 'Family, Book club, Neighbors…', list: 'alltags' });
  const bookSel = h('select', { class: 't', onchange: (e) => { f.bookId = +e.target.value; } }, writableBooks().map((b) => h('option', { value: b.id, selected: b.id === f.bookId ? true : null }, b.name)));
  const kindSel = sel(f, 'kind', [['individual', 'Person'], ['org', 'Company or organization']]);
  const notes = h('textarea', { class: 't', placeholder: 'Anything worth remembering', oninput: (e) => { f.notes = e.target.value; } }); notes.value = f.notes || '';

  const save = async (e) => {
    e && e.preventDefault();
    f.tags = tagIn.value.split(',').map((t) => t.trim()).filter(Boolean);
    if (!(f.birthday && f.birthday.month && f.birthday.day)) f.birthday = null;
    f.relations = f.relations.map((r) => ({ type: r.type, relatedId: r.relatedId || null, relatedName: r.relatedId ? null : r.relatedName, gender: r.gender || null, label: r.label || null }));
    const payload = { ...f };
    delete payload.hasPhoto; delete payload.etag;
    try {
      const out = id ? await api(`/api/contacts/${id}`, { method: 'PUT', json: payload }) : await api(`/api/contacts?book=${f.bookId}`, { method: 'POST', json: payload });
      if (photoFile) { const fd = new FormData(); fd.append('file', photoFile); await api(`/api/contacts/${out.id}/photo`, { method: 'PUT', body: fd }); }
      else if (dropPhoto) await api(`/api/contacts/${out.id}/photo`, { method: 'DELETE' });
      S.all = null; await loadMeta();
      toast('Saved'); location.hash = `#/c/${out.id}`;
    } catch (err) { fail(err); }
  };
  const nm = f.name;
  const form = h('form', { class: 'form', onsubmit: save },
    h('div', { class: 'pagehead' }, h('button', { class: 'iconbtn back', type: 'button', onclick: () => history.back() }, icon('back')), h('h1', null, id ? `Edit ${c.fn}` : 'New contact')),
    h('div', { class: 'photoedit' }, prev, h('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } }, file,
      h('button', { class: 'pillbtn', type: 'button', onclick: () => file.click() }, icon('camera', 's'), 'Photo'),
      (c.hasPhoto || photoFile) ? h('button', { class: 'pillbtn noic', type: 'button', onclick: () => { photoFile = null; dropPhoto = true; drawPhoto(); } }, 'Remove photo') : null)),
    h('div', { class: 'fsec' }, icon('person'), 'Name'),
    h('div', { class: 'grid' }, fld('First name', inp(nm, 'given', '', { autofocus: !id })), fld('Middle name', inp(nm, 'additional')), fld('Last name', inp(nm, 'family')),
      fld('Prefix', inp(nm, 'prefix', 'Dr., Mrs.')), fld('Suffix', inp(nm, 'suffix', 'Jr., III')), fld('Nickname', inp(f, 'nickname')), fld('Maiden name', inp(f, 'maiden')),
      fld('Display as', inp(f, 'fn', 'From the name parts')), fld('Gender', sel(f, 'gender', [['', '—'], ['F', 'Female'], ['M', 'Male'], ['O', 'Other'], ['N', 'Not applicable']])),
      fld('Kind', kindSel), fld('Phonetic first', inp(f, 'phoneticGiven')), fld('Phonetic last', inp(f, 'phoneticFamily'))),
    h('div', { class: 'fsec' }, icon('work'), 'Work'),
    h('div', { class: 'grid' }, fld('Company', inp(f, 'org')), fld('Department', inp(f, 'department')), fld('Job title', inp(f, 'title')), fld('Role', inp(f, 'role'))),
    h('div', { class: 'fsec' }, icon('cake'), 'Birthday'), h('div', { class: 'multi' }, ...dateInputs(f.birthday),
      h('label', { class: 'check', title: 'Unchecked: the birthday stays on the contact but is left out of the birthday calendar, the start page and other apps' },
        h('input', { type: 'checkbox', checked: f.birthdayRemind !== false, onchange: (e) => { f.birthdayRemind = e.target.checked; } }), ' Remind me')),
    ...phones, ...emails, ...addrs, ...social, ...urls, ...dates, ...rels,
    S.status.iopix ? [h('div', { class: 'fsec' }, icon('image'), 'ioPix person'), iopixBox] : null,
    h('div', { class: 'fsec' }, icon('tag'), 'Labels and address book'),
    h('div', { class: 'grid' }, fld('Labels (comma separated)', tagIn), fld('Address book', bookSel)), h('datalist', { id: 'alltags' }, S.tags.map((t) => h('option', { value: t.tag }))),
    h('div', { class: 'fsec' }, icon('note'), 'Notes'), notes,
    h('div', { class: 'formbar' }, h('button', { class: 'pillbtn primary', type: 'submit' }, icon('check', 's'), 'Save'),
      h('button', { class: 'pillbtn noic', type: 'button', onclick: () => { location.hash = id ? `#/c/${id}` : scopeHash(); } }, 'Cancel')));
  pane.replaceChildren(form);
  pane.scrollTop = 0;
}

async function pickIopix(c, saveNow) {
  let ppl;
  try { ppl = (await api('/api/iopix/people')).items; } catch (e) { fail(e); return null; }
  const q = h('input', { class: 't', placeholder: 'Search people in ioPix', value: c.fn || '' });
  const list = h('div', { style: { maxHeight: '50vh', overflowY: 'auto', marginTop: '10px' } });
  let chosen = null, resolveFn;
  const draw = () => {
    const s = fold(q.value).trim();
    const hits = ppl.filter((p) => !s || s.split(/\s+/).every((w) => fold(p.name).includes(w))).slice(0, 80);
    list.replaceChildren(...hits.map((p) => h('div', { class: 'row', onclick: () => { chosen = p; resolveFn(); } },
      h('span', { class: 'av' }, h('img', { src: `/api/iopix/face/${p.id}`, alt: '', loading: 'lazy', onerror: (e) => { e.target.remove(); } })),
      h('div', { class: 'who' }, h('div', { class: 'nm' }, p.name), h('div', { class: 'sub' }, `${p.count} photos${p.contact ? ` · linked to ${p.contact.fn}` : ''}`)))));
    if (!hits.length) list.append(h('p', { class: 'muted' }, 'Nobody by that name in ioPix.'));
  };
  q.oninput = draw; draw();
  const body = h('div', null, q, list);
  const done = new Promise((r) => { resolveFn = r; });
  const dlg = dialog('Link to an ioPix person', body, [{ label: 'Cancel', value: null }]);
  await Promise.race([dlg, done]);
  document.querySelector('.dialog-back')?.remove();
  if (chosen && saveNow) {
    try { await api(`/api/contacts/${c.id}`, { method: 'PATCH', json: { iopix: { personId: chosen.id, name: chosen.name } } }); toast(`Linked to ${chosen.name} in ioPix`); onRoute(); } catch (e) { fail(e); }
  }
  return chosen;
}

// ------------------------------------------------------------------ pages
async function showUpcoming(page) {
  const days = +(localStorage.getItem('ioc.days') || 60);
  const r = await api(`/api/upcoming?days=${days}`);
  const range = h('select', { class: 't', style: 'width:auto', onchange: (e) => { localStorage.setItem('ioc.days', e.target.value); onRoute(); } },
    [14, 30, 60, 90, 180, 366].map((d) => h('option', { value: d, selected: d === days ? true : null }, d === 366 ? 'The next year' : `The next ${d} days`)));
  const when = (x) => x.inDays === 0 ? 'Today' : x.inDays === 1 ? 'Tomorrow' : `In ${x.inDays} days`;
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Birthdays and anniversaries'), range,
    h('a', { class: 'pillbtn', href: '#/settings/devices' }, icon('event', 's'), 'Subscribe in your calendar')),
  r.items.length ? h('div', null, r.items.map((x) => h('a', { class: 'upc', href: `#/c/${x.contactId}` }, avatar({ id: x.contactId, fn: x.fn, hasPhoto: x.hasPhoto, iopixPersonId: x.iopixPersonId }, 'm'),
    h('div', null, h('div', null, h('b', null, x.fn)), h('div', { class: 'muted' }, `${x.label === 'birthday' ? 'Birthday' : x.label.charAt(0).toUpperCase() + x.label.slice(1)}${x.turns != null ? (x.label === 'birthday' ? ` · turns ${x.turns}` : ` · ${x.turns} years`) : ''}`)),
    h('div', { class: 'when' }, h('div', { class: 'days' }, when(x)), h('div', { class: 'muted small' }, new Date(x.date + 'T12:00').toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' }))))))
    : h('div', { class: 'empty' }, icon('cake'), h('p', null, 'No birthdays or anniversaries in that time.')));
}

async function showTree(page, r) {
  const g = await api(`/api/contacts/${r.id}/family?depth=4`);
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  const UP = { parent: 1, step_parent: 1, parent_in_law: 1, grandparent: 2, great_grandparent: 3, aunt_uncle: 1, godparent: 1,
    child: -1, step_child: -1, child_in_law: -1, grandchild: -2, great_grandchild: -3, niece_nephew: -1, godchild: -1 };
  const famTypes = new Set(S.rel.groups[0].types.map((t) => t.type));
  const gen = new Map([[g.root, 0]]), how = new Map([[g.root, null]]);
  const queue = [g.root];
  while (queue.length) {
    const cur = queue.shift();
    for (const e of g.edges.filter((x) => x.from === cur && famTypes.has(x.type))) {
      if (gen.has(e.to)) continue;
      gen.set(e.to, gen.get(cur) + (UP[e.type] || 0));
      const lab = S.rel.groups[0].types.find((t) => t.type === e.type);
      const node = byId.get(e.to) || {};
      const word = lab ? (node.gender === 'M' ? lab.male : node.gender === 'F' ? lab.female : lab.label) : e.type;
      how.set(e.to, cur === g.root ? word : `${word} of ${(byId.get(cur) || {}).fn}`);
      queue.push(e.to);
    }
  }
  const rows = new Map();
  for (const [id, lvl] of gen) { if (!rows.has(lvl)) rows.set(lvl, []); rows.get(lvl).push(id); }
  const names = { 3: 'Great-grandparents', 2: 'Grandparents', 1: 'Parents, aunts and uncles', 0: 'Same generation', '-1': 'Children, nieces and nephews', '-2': 'Grandchildren', '-3': 'Great-grandchildren' };
  const root = byId.get(g.root);
  page.append(h('div', { class: 'pagehead' }, h('a', { class: 'iconbtn', href: `#/c/${g.root}` }, icon('back')), h('h1', null, `${root.fn}'s family`)),
    gen.size > 1 ? h('div', { class: 'tree' }, [...rows.keys()].sort((a, b) => b - a).map((lvl) => [h('div', { class: 'gen' }, names[lvl] || (lvl > 0 ? `${lvl} generations up` : `${-lvl} generations down`)),
      h('div', { class: 'genrow' }, rows.get(lvl).map((id) => { const n = byId.get(id); return h('a', { class: `tcard ${id === g.root ? 'root' : ''}`, href: id === g.root ? `#/c/${id}` : `#/tree/${id}`, title: id === g.root ? 'Open the contact' : 'Their family' }, avatar({ id, fn: n.fn, hasPhoto: n.hasPhoto, iopixPersonId: n.iopixPersonId }, 'm'),
        h('div', null, h('b', null, n.fn), h('div', { class: 'muted small' }, id === g.root ? 'This contact' : how.get(id)), n.birthday && n.birthday.year ? h('div', { class: 'muted small' }, `born ${n.birthday.year}`) : null)); }))]))
      : h('div', { class: 'empty' }, h('p', null, 'No family relations to other contacts yet. Edit the contact and add parents, siblings, children…')));
}

// ------------------------------------------------------------------ maintenance: duplicates, data quality, suggestions, merges
async function refreshStatus() { try { S.status = await api('/api/status'); drawNav(); } catch { /* */ } }
const bookName = (id) => (S.books.find((b) => b.id === id) || {}).name;
const LEVEL_HUE = { 'very likely': '--c-rose', likely: '--c-amber', possible: '--c-slate' };

async function showMaint(page, r) {
  const adm = S.user.role === 'admin';
  const tabs = [['dups', 'Duplicates'], ['quality', 'Data quality'], ['suggest', `Suggestions${S.status.suggestions ? ` (${S.status.suggestions})` : ''}`], ['merges', 'Merge history'],
    ...(adm ? [['storage', 'Storage and backups'], ['updates', 'Updates and logs']] : [])];
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Maintenance')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/maintenance/${k}`; } }, l))));
  const body = h('div'); page.append(body);
  body.append(h('div', { class: 'muted' }, 'Loading…'));
  const views = { dups: maintDups, quality: maintQuality, suggest: maintSuggest, merges: maintMerges, ...(adm ? { storage: maintStorage, updates: maintUpdates } : {}) };
  await (views[r.tab] || maintDups)(body);
}

async function maintStorage(el) {
  let s; try { s = await api('/api/server'); } catch (e) { el.replaceChildren(h('p', null, e.message)); return; }
  const n = S.books.reduce((t, b) => t + (b.count || 0), 0);
  el.replaceChildren(h('div', { class: 'box' }, h('h2', null, icon('server'), 'Database'),
    kv('MariaDB', h('span', null, s.database)), kv('Address books', h('span', null, `${S.books.length}${n ? `, ${n} contacts` : ''}`)),
    h('p', { class: 'muted small' }, 'Contacts, photos and the merge history are in the database: back it up with mysqldump (or the container’s backup) and nothing else is needed. The Shared ioSuite database (accounts, sessions) is backed up with the suite.')),
  h('div', { class: 'box' }, h('h2', null, icon('download'), 'Export'),
    h('p', null, 'Every address book can be downloaded as vCard or CSV and imported again later: ', h('a', { class: 'lnk', href: '#/import' }, 'Import and export'), '.')));
}

async function maintUpdates(el) {
  const draw = async () => {
    let s; try { s = await api('/api/server'); } catch (e) { el.replaceChildren(h('p', null, e.message)); return; }
    if (!el.isConnected) return;
    const c = s.check, p = s.progress, last = s.lastUpdate;
    const state = p.running ? 'Updating… ioContacts restarts when it is done, and this page reloads.'
      : p.error ? `The last update failed: ${p.error}`
      : !c ? `You have v${s.version}${s.installed !== 'unknown' ? ` (${s.installed.slice(0, 7)})` : ''}.`
      : c.status === 'current' ? `v${s.version} is the latest version.`
      : c.status === 'update' ? `You have v${s.version}; ${c.remoteVersion ? `v${c.remoteVersion}` : 'a newer build'} is available${c.remoteDate ? ` (${c.remoteDate})` : ''}${c.remoteMessage ? `: ${c.remoteMessage.replace(/^v\d+\.\d+\.\d+:\s*/, '')}` : ''}.`
      : `Could not check: ${c.error}`;
    const auto = h('input', { type: 'checkbox', checked: s.autoCheck, disabled: s.autoCheckLocked, onchange: async (e) => {
      try { await api('/api/server', { method: 'POST', json: { autoCheck: e.target.checked } }); S.status = await api('/api/status'); toast('Saved'); draw(); } catch (err) { e.target.checked = !e.target.checked; fail(err); }
    } });
    el.replaceChildren(
      h('div', { class: 'box' }, h('h2', null, icon('update'), 'ioContacts version'),
        h('p', null, state),
        !p.running && !p.error && last ? h('p', { class: last.ok ? 'muted small' : 'warn small' }, `Last update: ${last.text}`) : null,
        h('p', null,
          h('button', { class: 'pillbtn', onclick: async () => { el.querySelector('.box p').textContent = 'Checking…'; try { await api('/api/server', { method: 'POST', json: { action: 'check' } }); } catch (e) { fail(e); } draw(); } }, icon('update', 's'), 'Check for updates'), ' ',
          s.docker ? h('span', { class: 'muted' }, 'Docker: update by pulling the image (docker compose pull && docker compose up -d).')
            : s.canRun ? h('button', { class: `pillbtn ${c && c.status === 'update' ? 'primary' : ''}`, disabled: p.running, onclick: async () => {
              if (!await confirmDialog('Update ioContacts', 'Fetch the newest version, refresh its packages and restart ioContacts? Settings and contacts stay; the page reloads when the new version is up.', 'Update now')) return;
              if (await runUpdate()) setTimeout(draw, 2500);
            } }, icon('check', 's'), 'Update now')
            : h('span', { class: 'muted' }, 'This install cannot update itself from here (run ./update.sh in the app folder).')),
        h('p', null, h('label', { class: 'check' }, auto, ' Check for a new version once a day (only GitHub’s public list of changes is asked; nothing about this server is sent)')),
        s.autoCheckLocked ? h('p', { class: 'muted small' }, 'UPDATE_CHECK=0 in the environment keeps it off.') : null,
        h('p', { class: 'muted small' }, `Follows ${s.repo} (${s.branch}). `, h('a', { class: 'lnk', href: `https://github.com/${s.repo}/commits/${s.branch}`, target: '_blank', rel: 'noopener' }, 'Change log'), '.')),
      logCard(),
      h('div', { class: 'box' }, h('h2', null, icon('update'), 'Restart'),
        h('p', null, 'Stops ioContacts; the service manager (systemd, launchd or Docker) starts it again within seconds. Nothing is lost; the page reloads when it is back.'),
        h('p', null, h('button', { class: 'pillbtn', onclick: async () => {
          if (!await confirmDialog('Restart ioContacts', 'Restart the server now? Everyone is disconnected for a few seconds.', 'Restart')) return;
          try { await api('/api/server', { method: 'POST', json: { action: 'restart' } }); } catch (e) { fail(e); return; }
          toast('Restarting…');
          const until = Date.now() + 90000, gone = Date.now() + 3000;
          const look = async () => {
            try { const r = await fetch('/api/status', { credentials: 'same-origin' }); if (r.ok && Date.now() > gone) { location.reload(); return; } } catch { /* down */ }
            if (Date.now() < until) setTimeout(look, 2000); else toast('ioContacts did not come back; check the service.');
          };
          setTimeout(look, 3000);
        } }, 'Restart ioContacts'))));
    if (p.running) setTimeout(() => { if (el.isConnected) draw(); }, 4000);
  };
  await draw();
}

/** The tail of the server log (GET /api/log from iosuite-shared): a level filter, a search, Reload and Download. */
function logCard() {
  const level = h('select', { class: 't', style: 'width:auto' }, [['any', 'Everything'], ['warning', 'Warnings and errors'], ['error', 'Errors'], ['auth', 'Sign-ins']].map(([v, l]) => h('option', { value: v }, l)));
  const contains = h('input', { class: 't', placeholder: 'Contains…', style: 'max-width:220px' });
  const requests = h('input', { type: 'checkbox' });
  const out = h('pre', { class: 'log' }, 'Loading…'), note = h('p', { class: 'muted small' });
  const load = async () => {
    try {
      const r = await api(`/api/log?lines=300&level=${level.value}&contains=${encodeURIComponent(contains.value)}&requests=${requests.checked ? 1 : 0}`);
      out.textContent = r.lines.length ? r.lines.join('\n') : (r.note || 'Nothing matches.');
      note.textContent = r.note ? '' : `${r.file}: ${(r.size_bytes / 1024).toFixed(0)} kB, the last ${r.returned} lines.`;
      out.scrollTop = out.scrollHeight;
    } catch (e) { out.textContent = e.message; }
  };
  level.onchange = load; requests.onchange = load; contains.onchange = load;
  setTimeout(load, 0);
  return h('div', { class: 'box' }, h('h2', null, icon('note'), 'Server log'),
    h('div', { class: 'multi' }, level, contains, h('label', { class: 'check' }, requests, ' Requests too'),
      h('button', { class: 'pillbtn noic', onclick: load }, 'Reload'), h('a', { class: 'pillbtn', href: '/api/log/download' }, icon('download', 's'), 'Download')),
    out, note);
}

async function maintDups(el) {
  const r = await api('/api/duplicates');
  el.replaceChildren(h('p', { class: 'muted' }, 'Contacts that are probably the same person: the same email or phone, the same or a similar name, a nickname (Bob for Robert), the same birthday or company. Other birthdays, genders or a Sr./Jr. count against. The first name has to fit: people who only share a last name, an address, a home phone or a family email are never offered. Merging keeps everything (you choose where they disagree) and can be undone.'));
  if (!r.groups.length) { el.append(h('div', { class: 'empty' }, icon('check'), h('p', null, 'No duplicates found.'))); return; }
  for (const g of r.groups) {
    const reasons = g.pairs.length === 1 ? g.pairs[0].reasons : g.pairs.map((p) => `${g.contacts.find((c) => c.id === p.a).fn} / ${g.contacts.find((c) => c.id === p.b).fn}: ${p.reasons.join(', ')}`);
    const box = h('div', { class: 'dup' },
      h('div', { class: 'duphead' }, h('span', { class: 'lvl', style: { '--hue': `var(${LEVEL_HUE[g.level]})` } }, g.level), h('span', { class: 'muted small' }, `score ${g.score}`)),
      h('ul', { class: 'reasons' }, reasons.map((x) => h('li', null, x))),
      g.contacts.map((c) => h('div', { class: 'duprow' }, avatar(c), h('div', { style: { minWidth: 0 } }, h('a', { class: 'lnk', href: `#/c/${c.id}` }, c.fn),
        h('div', { class: 'muted small' }, [c.org, c.email, c.phone, c.birthday ? fmtDate(c.birthday) : null, bookName(c.bookId)].filter(Boolean).join(' · '))))),
      !g.contacts.every((c) => (S.books.find((b) => b.id === c.bookId) || {}).writable) ? null : h('div', { class: 'btns' },
        h('button', { class: 'pillbtn primary', onclick: () => mergeDialog(g.contacts.map((c) => c.id), () => onRoute()) }, icon('merge', 's'), 'Compare and merge…'),
        h('button', { class: 'pillbtn noic', title: 'They are different people: do not offer them again', onclick: async () => {
          await api('/api/duplicates/dismiss', { method: 'POST', json: { ids: g.contacts.map((c) => c.id) } }); box.remove(); toast('Kept apart');
        } }, 'Not duplicates')));
    el.append(box);
  }
}

function fmtValue(field, v) {
  if (v == null) return '';
  if (field === 'photo') return h('img', { class: 'sphoto', src: `data:${v.type};base64,${v.data}`, alt: '' });
  if (field === 'name') return v.fn || [v.prefix, v.given, v.additional, v.family, v.suffix].filter(Boolean).join(' ');
  if (field === 'birthday') return fmtDate(v);
  if (field === 'iopix') return v.name || `ioPix person ${v.personId}`;
  if (field === 'gender') return ({ M: 'Male', F: 'Female', O: 'Other', N: 'None', U: 'Unknown' })[v] || v;
  if (field === 'addresses') return [v.street, [v.postcode, v.city].filter(Boolean).join(' '), v.region, v.country].filter(Boolean).join(', ') + (v.label ? ` (${v.label})` : '');
  if (field === 'social') return `${(S.social.find((x) => x.service === v.service) || {}).name || v.service}: ${v.value}`;
  if (field === 'relations') return `${v.typeLabel || v.type}: ${v.relatedFn || v.relatedName}`;
  if (field === 'dates') return `${v.label}: ${fmtDate(v)}`;
  if (typeof v === 'object') return `${v.value}${v.label ? ` (${v.label})` : ''}`;
  return String(v);
}

const FIELD_LABEL = { name: 'Name', nickname: 'Nickname', maiden: 'Maiden name', gender: 'Gender', birthday: 'Birthday', org: 'Company', department: 'Department',
  title: 'Job title', role: 'Role', notes: 'Notes', iopix: 'ioPix person', phoneticGiven: 'Phonetic first name', phoneticFamily: 'Phonetic last name', photo: 'Photo',
  emails: 'Emails', phones: 'Phones', addresses: 'Addresses', urls: 'Websites', social: 'Social profiles', dates: 'Dates', tags: 'Labels', relations: 'Relations' };

async function mergeDialog(ids, done, keepId) {
  let pv; try { pv = await api(`/api/merge/preview?ids=${ids.join(',')}&keep=${keepId || ids[0]}`); } catch (e) { fail(e); return; }
  const byId = Object.fromEntries(pv.contacts.map((c) => [c.id, c]));
  const pick = {}; const keepLists = {};
  const body = h('div', { class: 'mergedlg' });
  body.append(h('div', { class: 'mrow' }, h('div', { class: 'mk' }, 'Keep'), h('div', { class: 'mv' }, pv.contacts.map((c) => h('label', { class: 'check' },
    h('input', { type: 'radio', name: 'mkeep', checked: c.id === pv.keep, onchange: () => { back.remove(); mergeDialog(ids, done, c.id); } }),
    `${c.fn} (${bookName(c.bookId) || 'book'})`))), h('p', { class: 'muted small' }, 'The kept contact stays in its address book and keeps its link in phones; the others are deleted.')));
  for (const [field, opts] of Object.entries(pv.choices)) {
    const name = `mf-${field}`;
    const current = field === 'photo' ? pv.photoFrom : (opts.find((o) => JSON.stringify(field === 'name' ? Object.fromEntries(Object.entries(pv.merged.name).filter(([, x]) => x)) : pv.merged[field]) === JSON.stringify(o.value)) || opts[0]).contactId;
    pick[field] = current;
    body.append(h('div', { class: 'mrow' }, h('div', { class: 'mk' }, FIELD_LABEL[field] || field), h('div', { class: 'mv' }, opts.map((o) => h('label', { class: 'check' },
      h('input', { type: 'radio', name, checked: o.contactId === current, onchange: () => { pick[field] = o.contactId; } }),
      field === 'photo' ? h('img', { class: 'sphoto', src: `/api/contacts/${o.contactId}/photo`, alt: '' }) : h('span', null, fmtValue(field, o.value)),
      h('span', { class: 'muted small' }, ` · ${byId[o.contactId].fn}`))))));
  }
  for (const field of ['phones', 'emails', 'addresses', 'urls', 'social', 'dates', 'tags', 'relations']) {
    const list = pv.merged[field] || [];
    if (!list.length) continue;
    keepLists[field] = list.map(() => true);
    body.append(h('div', { class: 'mrow' }, h('div', { class: 'mk' }, FIELD_LABEL[field]), h('div', { class: 'mv' }, list.map((x, i) => h('label', { class: 'check' },
      h('input', { type: 'checkbox', checked: true, onchange: (e) => { keepLists[field][i] = e.target.checked; } }), field === 'tags' ? x : fmtValue(field, x))))));
  }
  const back = h('div', { class: 'dialog-back' });
  const close = () => back.remove();
  back.addEventListener('click', (e) => { if (e.target === back) close(); });
  back.append(h('div', { class: 'dialog wide', role: 'dialog' }, h('h2', null, `Merge ${pv.contacts.length} contacts`), body,
    h('div', { class: 'btns' }, h('button', { class: 'pillbtn noic', onclick: close }, 'Cancel'),
      h('button', { class: 'pillbtn primary noic', onclick: async () => {
        const res = JSON.parse(JSON.stringify(pv.merged));
        for (const [field, cid] of Object.entries(pick)) {
          if (field === 'photo') continue;
          const src = byId[cid];
          if (field === 'name') { res.name = { ...src.name }; res.fn = src.fn; } else res[field] = src[field];
        }
        for (const [field, flags] of Object.entries(keepLists)) res[field] = (pv.merged[field] || []).filter((_, i) => flags[i]);
        try {
          await api('/api/contacts/merge', { method: 'POST', json: { keep: pv.keep, others: ids.filter((x) => x !== pv.keep), result: res, photoFrom: pick.photo ?? null } });
          close(); S.all = null; await loadMeta(); toast('Merged. Maintenance › Merge history can undo it.'); done && done(pv.keep);
        } catch (e) { fail(e); }
      } }, 'Merge'))));
  document.body.append(back);
}

async function maintQuality(el) {
  const r = await api('/api/quality');
  const found = r.checks.filter((c) => c.count), clear = r.checks.filter((c) => !c.count);
  el.replaceChildren(h('p', { class: 'muted' }, 'Checks for untidy or doubtful data. Where a fix is offered it changes only contacts you may change; everything else links to the contact to correct by hand.'));
  if (!found.length) el.append(h('div', { class: 'empty' }, icon('check'), h('p', null, 'Everything looks tidy.')));
  const SEV = { problem: '--c-rose', tidy: '--c-amber', info: '--c-slate' };
  for (const c of found) {
    const cc = h('input', { class: 't', placeholder: '+32', style: { width: '80px' }, value: (() => { try { return localStorage.getItem('ioc.cc') || ''; } catch { return ''; } })() });
    const fixBtn = c.fix ? h('button', { class: 'pillbtn', onclick: async () => {
      const json = { check: c.check };
      if (c.check === 'national_phone') { if (!cc.value.trim()) { toast('Type the country code first, such as +32'); cc.focus(); return; } json.countryCode = cc.value; try { localStorage.setItem('ioc.cc', cc.value); } catch { /* */ } }
      try { const res = await api('/api/quality/fix', { method: 'POST', json }); toast(`Fixed ${res.fixed.length}${res.skipped.length ? `, ${res.skipped.length} left (not yours to change, or nothing found)` : ''}`); S.all = null; onRoute(); } catch (e) { fail(e); }
    } }, icon('check', 's'), c.fix) : null;
    el.append(h('details', { class: 'qcheck' }, h('summary', null, h('span', { class: 'lvl', style: { '--hue': `var(${SEV[c.severity]})` } }, c.count), h('b', null, c.title)),
      h('div', { class: 'qbody' }, c.fix ? h('p', null, c.check === 'national_phone' ? [h('span', { class: 'muted' }, 'Country code to add: '), cc, ' '] : null, fixBtn) : null,
        h('table', { class: 't' }, c.items.slice(0, 300).map((x) => h('tr', null, h('td', null, h('a', { class: 'lnk', href: `#/c/${x.contactId}` }, x.fn)), h('td', { class: 'muted' }, x.detail || ''), h('td', { class: 'muted small' }, bookName(x.bookId) || '')))),
        c.items.length > 300 ? h('p', { class: 'muted small' }, `and ${c.items.length - 300} more`) : null)));
  }
  if (clear.length) el.append(h('p', { class: 'muted small', style: { marginTop: '16px' } }, icon('check', 's'), ' No findings: ', clear.map((c) => c.title.toLowerCase()).join('; '), '.'));
}

function suggList(items, canEdit, after) {
  const wrap = h('div', { class: 'slist' });
  for (const x of items) {
    const row = h('div', { class: 'srow' },
      h('div', { class: 'sk' }, x.fieldLabel),
      h('div', { class: 'sv' }, fmtValue(x.field, x.value),
        h('div', { class: 'muted small' }, x.source, x.by ? ` · via ${x.by}` : '', x.evidence && /^https?:\/\//i.test(x.evidence) ? [' · ', h('a', { class: 'lnk', href: x.evidence, target: '_blank', rel: 'noopener noreferrer' }, 'source ', icon('open', 's'))] : null, x.note ? ` · ${x.note}` : '')),
      h('div', { class: 'sb' },
        canEdit ? h('button', { class: 'pillbtn noic primary', onclick: async () => { try { await api(`/api/suggestions/${x.id}/accept`, { method: 'POST' }); row.remove(); await refreshStatus(); after && after(x); } catch (e) { fail(e); } } }, 'Accept') : null,
        canEdit ? h('button', { class: 'pillbtn noic', onclick: async () => { await api(`/api/suggestions/${x.id}/dismiss`, { method: 'POST' }); row.remove(); await refreshStatus(); } }, 'Dismiss') : null));
    wrap.append(row);
  }
  return wrap;
}

async function maintSuggest(el) {
  const r = await api('/api/suggestions');
  const prog = h('span', { class: 'muted' });
  const run = h('button', { class: 'pillbtn', onclick: async () => {
    run.disabled = true; let offset = 0, total = 1, added = 0;
    while (offset < total) {
      prog.textContent = `Looking up… ${offset} of ${total === 1 ? '?' : total}`;
      try { const res = await api('/api/lookup', { method: 'POST', json: { offset, limit: 20 } }); total = res.total; offset += Math.max(res.done, 1); added += res.added; } catch (e) { fail(e); break; }
    }
    prog.textContent = `${added} new suggestion${added === 1 ? '' : 's'}`; await refreshStatus(); setTimeout(onRoute, 800);
  } }, icon('bulb', 's'), 'Look up all contacts');
  el.replaceChildren(h('div', { class: 'box' }, h('h2', null, icon('bulb'), 'Enrichment'),
    h('p', null, 'Suggestions for your contacts, from public sources: Gravatar (looked up by email address, sent as a hash), and the GitHub, Mastodon and Bluesky profiles on a contact. LinkedIn, Facebook, Instagram and X offer no lookup that apps may use; an AI assistant connected over MCP can research people there and file what it finds here. Nothing changes until you accept it, and what you dismiss is not offered again.'),
    h('p', null, run, ' ', prog)));
  if (!r.items.length) { el.append(h('div', { class: 'empty' }, icon('check'), h('p', null, 'No suggestions waiting.'))); return; }
  const by = new Map();
  for (const x of r.items) { if (!by.has(x.contactId)) by.set(x.contactId, []); by.get(x.contactId).push(x); }
  for (const [cid, list] of by) {
    const book = S.books.find((b) => b.id === list[0].bookId); const canEdit = book && book.writable;
    const box = h('div', { class: 'dup' }, h('div', { class: 'duprow' }, avatar({ id: cid, fn: list[0].fn }), h('a', { class: 'lnk', href: `#/c/${cid}` }, h('b', null, list[0].fn)),
      h('span', { style: { flex: 1 } }),
      canEdit ? h('button', { class: 'pillbtn noic', onclick: async () => {
        for (const x of list) { try { await api(`/api/suggestions/${x.id}/accept`, { method: 'POST' }); } catch { /* a rival value already taken */ } }
        await refreshStatus(); onRoute();
      } }, 'Accept all') : null,
      canEdit ? h('button', { class: 'pillbtn noic', onclick: async () => { for (const x of list) await api(`/api/suggestions/${x.id}/dismiss`, { method: 'POST' }); await refreshStatus(); box.remove(); } }, 'Dismiss all') : null),
    suggList(list, canEdit, () => {}));
    el.append(box);
  }
}

async function maintMerges(el) {
  const r = await api('/api/merges');
  el.replaceChildren(h('p', { class: 'muted' }, 'Every merge is kept with the contacts as they were before it, so it can be undone: the merged contacts come back as they were, with their relations.'));
  if (!r.items.length) { el.append(h('div', { class: 'empty' }, h('p', null, 'No merges yet.'))); return; }
  el.append(h('table', { class: 't' }, h('tr', null, h('th', null, 'When'), h('th', null, 'Contacts'), h('th', null, 'By'), h('th')),
    r.items.map((m) => h('tr', null, h('td', null, new Date(m.at).toLocaleString()),
      h('td', null, m.names, m.keepName ? [h('br'), h('a', { class: 'lnk small', href: `#/c/${m.keepId}` }, `now ${m.keepName}`)] : null),
      h('td', null, m.by || ''),
      h('td', null, m.undone ? h('span', { class: 'muted' }, 'undone') : m.canUndo ? h('button', { class: 'pillbtn noic', onclick: async () => {
        if (!await confirmDialog('Undo merge', `Put ${m.names} back as they were before the merge?${m.changedSince ? ' Changes made to the merged contact since then are lost.' : ''}`, 'Undo merge')) return;
        try { await api(`/api/merges/${m.id}/undo`, { method: 'POST' }); S.all = null; await loadMeta(); toast('Merge undone'); onRoute(); } catch (e) { fail(e); }
      } }, 'Undo') : null)))));
}

async function showImport(page) {
  const wb = writableBooks();
  const book = h('select', { class: 't', style: 'width:auto' }, wb.map((b) => h('option', { value: b.id }, b.name)));
  const mode = h('select', { class: 't', style: 'width:auto' }, h('option', { value: 'update' }, 'Update contacts already here (same UID)'), h('option', { value: 'skip' }, 'Skip contacts already here'));
  const file = h('input', { type: 'file', accept: '.vcf,.vcard,.csv,.json,text/vcard,text/csv,application/json' });
  const out = h('div', { class: 'muted', style: { marginTop: '8px' } });
  const ebook = h('select', { class: 't', style: 'width:auto' }, h('option', { value: 'all' }, 'All address books'), S.books.map((b) => h('option', { value: b.id }, b.name)));
  const exp = (fmt) => { location.href = `/api/export?format=${fmt}&book=${ebook.value}`; };
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Import and export')),
    h('div', { class: 'box' }, h('h2', null, icon('upload'), 'Import'),
      h('p', { class: 'muted' }, 'vCard files (.vcf, from Apple Contacts, iPhone, Android, Outlook, Thunderbird, Google… vCard 2.1, 3.0 and 4.0; many contacts in one file), jCard (.json), or a CSV exported from Google Contacts or Outlook.'),
      h('div', { class: 'multi' }, h('span', null, 'Into'), book, mode), h('div', { class: 'multi' }, file,
        h('button', { class: 'pillbtn primary', onclick: async () => {
          if (!file.files[0]) return toast('Pick a file first');
          const fd = new FormData(); fd.append('file', file.files[0]); fd.append('book', book.value); fd.append('mode', mode.value);
          out.textContent = 'Importing…';
          try { const r = await api('/api/import', { method: 'POST', body: fd }); out.textContent = `Read ${r.read}: ${r.created} new, ${r.updated} updated, ${r.skipped} skipped.`; S.all = null; await loadMeta(); } catch (e) { out.textContent = ''; fail(e); }
        } }, icon('upload', 's'), 'Import')), out),
    h('div', { class: 'box' }, h('h2', null, icon('download'), 'Export'), h('div', { class: 'multi' }, h('span', null, 'From'), ebook),
      h('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } },
        h('button', { class: 'pillbtn noic', onclick: () => exp('vcf') }, 'vCard 3.0 (most apps)'), h('button', { class: 'pillbtn noic', onclick: () => exp('vcf4') }, 'vCard 4.0'),
        h('button', { class: 'pillbtn noic', onclick: () => exp('csv-google') }, 'Google CSV'), h('button', { class: 'pillbtn noic', onclick: () => exp('csv-outlook') }, 'Outlook CSV'),
        h('button', { class: 'pillbtn noic', onclick: () => exp('jcard') }, 'jCard (JSON)'))));
}

async function showIopix(page) {
  const r = await api('/api/iopix/people');
  const q = h('input', { class: 't', placeholder: 'Search', style: 'max-width:280px' });
  const grid = h('div', { class: 'ppl' });
  const draw = () => {
    const s = fold(q.value).trim();
    grid.replaceChildren(...r.items.filter((p) => !s || fold(p.name).includes(s)).map((p) => h('div', { class: 'pcard' },
      h('img', { src: `/api/iopix/face/${p.id}`, alt: '', loading: 'lazy', onerror: (e) => { e.target.style.visibility = 'hidden'; } }), h('div', { class: 'nm' }, p.name), h('div', { class: 'muted small' }, `${p.count} photos`),
      p.contact ? h('a', { class: 'lnk small', href: `#/c/${p.contact.id}` }, p.contact.fn)
        : h('button', { class: 'pillbtn noic', onclick: async () => {
          const parts = p.name.split(' ');
          try { const c = await api(`/api/contacts?book=${(writableBooks().find((b) => b.shared) || writableBooks()[0]).id}`, { method: 'POST', json: { name: { given: parts[0], family: parts.slice(1).join(' ') }, iopix: { personId: p.id, name: p.name } } });
            await api(`/api/contacts/${c.id}/photo/from-iopix`, { method: 'POST' }).catch(() => {}); S.all = null; await loadMeta(); location.hash = `#/c/${c.id}/edit`; } catch (e) { fail(e); }
        } }, 'Make a contact'))));
  };
  q.oninput = draw; draw();
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'ioPix people'), q,
    h('button', { class: 'pillbtn', onclick: async () => {
      const s = await api('/api/iopix/auto-link?dry=true', { method: 'POST' });
      if (!s.items.length) return toast('No unlinked contact has the exact name of an ioPix person');
      if (!await dialog('Link by name', h('div', null, h('p', null, `${s.items.length} contact(s) have the exact name of one ioPix person:`), h('ul', null, s.items.slice(0, 40).map((x) => h('li', null, x.fn)))), [{ label: 'Cancel', value: false }, { label: 'Link them', value: true, primary: true }])) return;
      await api('/api/iopix/auto-link?dry=false', { method: 'POST' }); toast('Linked'); onRoute();
    } }, icon('link', 's'), 'Link by name')),
  h('p', { class: 'muted' }, 'Everyone named in ioPix. A linked contact shows the face from ioPix and links to their photos.'), grid);
}

// ------------------------------------------------------------------ settings
async function showSettings(page, r) {
  const tabs = [['account', 'Account'], ['display', 'Display'], ['devices', 'Apps and devices'], ['books', 'Address books'],
    ...(S.user.role === 'admin' ? [['suite', 'Connected apps'], ['users', 'Users and sign-in'], ['server', 'Server']] : [])];
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Settings')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/settings/${k}`; } }, l))));
  const body = h('div'); page.append(body);
  await ({ account: setAccount, display: setDisplay, devices: setDevices, books: setBooks, suite: setIopix, users: setUsers, server: setServer }[r.tab] || setAccount)(body);
}
const fld = (l, e) => h('label', { class: 'field' }, h('span', null, l), e);
const kv = (k, v) => h('div', { class: 'kv' }, h('div', { class: 'k' }, k), h('div', { class: 'v', style: { flex: 1 } }, typeof v === 'string' ? copyRow(v) : v));
async function signOutElsewhere() {
  if (!await confirmDialog('Sign out everywhere', 'Sign out on every other browser and device? (Apps with an app password keep working.)', 'Sign out the others')) return false;
  try { await api('/api/auth/logout_all', { method: 'POST' }); return true; } catch (e) { fail(e); return false; }
}

async function setAccount(el) {
  const u = S.user;
  const dn = h('input', { class: 't', value: u.displayName || '' }), em = h('input', { class: 't', type: 'email', value: u.email || '' });
  const old = h('input', { class: 't', type: 'password', autocomplete: 'current-password' }), nw = h('input', { class: 't', type: 'password', autocomplete: 'new-password' });
  const fld = (l, e) => h('label', { class: 'field' }, h('span', null, l), e);
  el.append(h('div', { class: 'box' }, h('h2', null, icon('person'), 'You'), h('div', { class: 'grid' }, fld('Display name', dn), fld('Email (for sign-in at a proxy)', em)),
    h('p', null, h('button', { class: 'pillbtn primary', onclick: async () => { try { S.user = (await api('/api/auth/me', { method: 'PATCH', json: { displayName: dn.value, email: em.value } })).user; drawUser(); toast('Saved'); } catch (e) { fail(e); } } }, icon('check', 's'), 'Save'))),
  h('div', { class: 'box' }, h('h2', null, icon('key'), 'Password'), h('div', { class: 'grid' }, u.hasPassword ? fld('Current password', old) : null, fld('New password (8 or more)', nw)),
    h('p', null, h('button', { class: 'pillbtn', onclick: async () => { try { await api('/api/auth/password', { method: 'POST', json: { old: old.value, new: nw.value } }); old.value = nw.value = ''; toast('Password changed'); } catch (e) { fail(e); } } }, 'Change password'))),
  h('div', { class: 'box' }, h('h2', null, icon('devices'), 'Sessions'),
    h('p', { class: 'muted' }, 'You are signed in to every ioThing app at once. Signing out elsewhere ends your session on every other browser and device; apps with an app password keep working.'),
    h('p', null, h('button', { class: 'pillbtn noic', onclick: async () => { if (await signOutElsewhere()) toast('Signed out elsewhere'); } }, 'Sign out everywhere else'))));
}

async function setDisplay(el) {
  const theme = localStorage.getItem('ioc.theme') || 'system';
  const th = h('select', { class: 't' }, [['system', 'Same as the device'], ['light', 'Light'], ['dark', 'Dark']].map(([v, l]) => h('option', { value: v, selected: v === theme ? true : null }, l)));
  th.onchange = () => { localStorage.setItem('ioc.theme', th.value); applyTheme(); toast(`Appearance: ${th.value}`); };
  el.append(h('div', { class: 'box' }, h('h2', null, icon('theme'), 'Appearance'), h('div', { class: 'grid' }, fld('Light or dark', th)),
    h('p', { class: 'muted small' }, 'Kept in this browser. The sort order and the fields shown are set at the top of the contact list.')));
}

async function setDevices(el) {
  const info = await api('/api/connect');
  const pw = await api('/api/app-passwords');
  const label = h('input', { class: 't', placeholder: 'e.g. Alex’s iPhone', style: 'max-width:280px' });
  const shown = h('div');
  const isApple = /iPhone|iPad|Macintosh/.test(navigator.userAgent);
  const plabel = h('input', { class: 't', name: 'label', value: /iPad/.test(navigator.userAgent) ? 'iPad' : /iPhone/.test(navigator.userAgent) ? 'iPhone' : 'iPhone', style: 'max-width:200px' });
  el.append(...[
    h('div', { class: 'box' }, h('h2', null, icon('devices'), 'iPhone, iPad and Mac: set up in one step'),
      h('p', null, 'Download a configuration profile that adds your contacts (CardDAV) and, if you like, the family birthday calendar. ',
        isApple ? 'Tap Download here in Safari, then open Settings › Profile Downloaded › Install.' : 'Open this page on the iPhone or iPad in Safari and tap Download, then Settings › Profile Downloaded › Install. On a Mac, open the file, then System Settings › Privacy & Security › Profiles.'),
      h('form', { method: 'POST', action: '/api/apple-profile', class: 'pform', onsubmit: () => { setTimeout(async () => drawPw((await api('/api/app-passwords')).items), 1500); } },
        h('label', { class: 'field' }, h('span', null, 'Device name'), plabel),
        h('label', { class: 'field' }, h('span', null, 'Password'), h('select', { class: 't', name: 'password' },
          h('option', { value: 'new' }, 'Include a new app password for this device'), h('option', { value: 'ask' }, 'Leave it out (the device asks while installing)'))),
        h('label', { class: 'field' }, h('span', null, 'Birthday calendar'), h('select', { class: 't', name: 'calendar' },
          h('option', { value: 'family' }, 'Family birthdays'), h('option', { value: 'all' }, 'Birthdays from all my books'), h('option', { value: 'none' }, 'No calendar'))),
        info.ldap.enabled ? h('label', { class: 'check' }, h('input', { type: 'checkbox', name: 'ldap', value: 'true' }), ' Also the LDAP directory (for Mail on a Mac; plain LDAP, home network only)') : null,
        h('p', null, h('button', { class: 'pillbtn primary', type: 'submit' }, icon('download', 's'), 'Download the profile'))),
      h('p', { class: 'muted small' }, 'The profile holds the app password: install it and delete the file, and revoke that password below if the device is lost. The profile is not signed, so iOS shows it as “Not Verified”; that is expected.')),
    h('div', { class: 'box' }, h('h2', null, icon('key'), 'App passwords'),
      h('p', { class: 'muted' }, 'Give every app or device its own password instead of yours; you can revoke one without touching the others. Use your user name with it.'),
      h('div', { class: 'multi' }, label, h('button', { class: 'pillbtn primary', onclick: async () => {
        const r = await api('/api/app-passwords', { method: 'POST', json: { label: label.value || 'Device' } });
        shown.replaceChildren(h('p', null, h('b', null, 'Copy it now: '), 'it is shown only once.'), copyRow(r.password));
        label.value = ''; const list = await api('/api/app-passwords'); drawPw(list.items);
      } }, icon('add', 's'), 'New app password')), shown, h('div', { id: 'pwlist' })),
    h('div', { class: 'box' }, h('h2', null, icon('book'), 'Contacts apps (CardDAV)'),
      h('p', null, 'Apple Contacts (Mac, iPhone, iPad: Settings › Contacts › Accounts › Add Account › Other › Add CardDAV Account), DAVx⁵ on Android, Thunderbird, Evolution, GNOME Contacts, KDE: give the server, your user name and an app password.'),
      h('div', { class: 'kv' }, h('div', { class: 'k' }, 'Server'), h('div', { class: 'v', style: { flex: 1 } }, copyRow(info.server))),
      h('div', { class: 'kv' }, h('div', { class: 'k' }, 'User name'), h('div', { class: 'v', style: { flex: 1 } }, copyRow(info.user))),
      h('div', { class: 'kv' }, h('div', { class: 'k' }, 'CardDAV address'), h('div', { class: 'v', style: { flex: 1 } }, copyRow(info.carddav))),
      h('details', null, h('summary', { class: 'lnk' }, 'Address of each address book (for apps that want one)'), info.books.map((b) => h('div', { class: 'kv' }, h('div', { class: 'k' }, b.name), h('div', { class: 'v', style: { flex: 1 } }, copyRow(b.url)))))),
    h('div', { class: 'box' }, h('h2', null, icon('event'), 'Family birthday calendar'),
      h('p', null, 'Subscribe to birthdays and anniversaries in Apple Calendar (File › New Calendar Subscription), Google Calendar (Other calendars › From URL), Outlook (Add calendar › Subscribe from web) or Thunderbird (New Calendar › On the Network). The link is private to you: anyone who has it can read the dates.'),
      h('div', { class: 'kv' }, h('div', { class: 'k' }, 'Family'), h('div', { class: 'v', style: { flex: 1 } }, copyRow(info.calendar.family))),
      h('div', { class: 'kv' }, h('div', { class: 'k' }, 'All my books'), h('div', { class: 'v', style: { flex: 1 } }, copyRow(info.calendar.all))),
      h('p', null, h('a', { class: 'pillbtn', href: info.calendar.webcalFamily }, icon('event', 's'), 'Open in my calendar app'), ' ',
        h('button', { class: 'pillbtn noic', onclick: async () => { if (await confirmDialog('New calendar link', 'The old link stops working; subscribed calendars need the new one.', 'Make a new link')) { await api('/api/calendar/reset', { method: 'POST' }); onRoute(); } } }, 'New link'))),
    info.ldap.enabled ? h('div', { class: 'box' }, h('h2', null, icon('mail'), 'Mail apps (LDAP directory)'),
      h('p', null, 'Outlook (Account settings › Address books › LDAP), Thunderbird (Address Book › New › LDAP Directory), Apple Mail/Contacts (Settings › Accounts › LDAP) and many desk phones and printers can look addresses up here. Read-only.'),
      h('div', { class: 'kv' }, h('div', { class: 'k' }, 'Host'), h('div', { class: 'v', style: { flex: 1 } }, copyRow(info.ldap.host))),
      h('div', { class: 'kv' }, h('div', { class: 'k' }, 'Port'), h('div', { class: 'v', style: { flex: 1 } }, copyRow(String(info.ldap.port)))),
      h('div', { class: 'kv' }, h('div', { class: 'k' }, 'Base DN'), h('div', { class: 'v', style: { flex: 1 } }, copyRow(info.ldap.base))),
      h('div', { class: 'kv' }, h('div', { class: 'k' }, 'Bind DN'), h('div', { class: 'v', style: { flex: 1 } }, copyRow(info.ldap.bindDn))),
      h('p', { class: 'muted small' }, 'Sign in with an app password. The directory speaks plain LDAP: keep it on your own network, or put a TLS proxy in front for ldaps://.')) : null,
    S.status.mcp ? h('div', { class: 'box' }, h('h2', null, icon('ai'), 'AI assistants (MCP)'),
      h('p', null, 'Claude and other assistants that speak the Model Context Protocol can search, read and update the contacts you can see, as you. Give the assistant its own app password (above), sent as a Bearer token.'),
      h('div', { class: 'kv' }, h('div', { class: 'k' }, 'MCP address'), h('div', { class: 'v', style: { flex: 1 } }, copyRow(`${info.server}/mcp`))),
      h('p', { class: 'muted small' }, 'Claude Code:'),
      copyRow(`claude mcp add --transport http iocontacts ${info.server}/mcp --header "Authorization: Bearer APP-PASSWORD"`),
      h('p', { class: 'muted small' }, 'Apps configured with JSON (Claude Desktop through mcp-remote, Cursor, VS Code…):'),
      copyRow(JSON.stringify({ mcpServers: { iocontacts: { command: 'npx', args: ['-y', 'mcp-remote', `${info.server}/mcp`, '--header', 'Authorization: Bearer APP-PASSWORD'] } } })))
      : (S.user.role === 'admin' ? h('div', { class: 'box' }, h('h2', null, icon('ai'), 'AI assistants (MCP)'), h('p', { class: 'muted' }, 'The MCP server is off. Turn it on in ', h('a', { class: 'lnk', href: '#/settings/server' }, 'Settings › Server'), ' to let Claude and other assistants work with the contacts.')) : null),
    h('div', { class: 'box' }, h('h2', null, icon('link'), 'Other apps (REST API)'),
      h('p', null, 'JSON, vCard or jCard over HTTPS, with your user name and an app password (HTTP Basic) or the app password as a Bearer token. ', h('a', { class: 'lnk', href: '/api/docs', target: '_blank' }, 'API documentation')),
      copyRow(`curl -u ${info.user}:APP-PASSWORD -H 'Accept: application/vcard+json' ${info.server}/api/contacts?q=smith`))].filter(Boolean));
  const drawPw = (items) => {
    const box = el.querySelector('#pwlist');
    box.replaceChildren(items.length ? h('table', { class: 't' }, h('tr', null, h('th', null, 'Name'), h('th', null, 'Made'), h('th', null, 'Last used'), h('th')),
      items.map((p) => h('tr', null, h('td', null, p.label), h('td', null, new Date(p.created).toLocaleDateString()), h('td', null, p.lastUsed ? new Date(p.lastUsed).toLocaleString() : 'never'),
        h('td', null, h('button', { class: 'pillbtn noic danger', onclick: async () => { await api(`/api/app-passwords/${p.id}`, { method: 'DELETE' }); drawPw((await api('/api/app-passwords')).items); } }, 'Revoke'))))) : h('p', { class: 'muted' }, 'No app passwords yet.'));
  };
  drawPw(pw.items);
}

async function setBooks(el) {
  el.append(h('p', null, h('button', { class: 'pillbtn primary', onclick: newBook }, icon('add', 's'), 'New address book')),
    h('table', { class: 't' }, h('tr', null, h('th', null, 'Name'), h('th', null, 'Who sees it'), h('th', null, 'Contacts'), h('th', null, 'Colour'), h('th')),
      S.books.map((b) => {
        const name = h('input', { class: 't', value: b.name, disabled: !b.writable });
        const col = h('input', { type: 'color', value: b.color || (b.shared ? '#8e44d6' : '#0b8a9e'), disabled: !b.writable });
        return h('tr', null, h('td', null, name), h('td', null, b.shared ? 'Everyone' : 'Only you'), h('td', null, b.count), h('td', null, col),
          h('td', { style: { whiteSpace: 'nowrap' } }, b.writable ? h('button', { class: 'pillbtn noic', onclick: async () => { await api(`/api/books/${b.id}`, { method: 'PATCH', json: { name: name.value, color: col.value } }); await loadMeta(); toast('Saved'); } }, 'Save') : null, ' ',
            b.writable && (!b.shared || S.user.role === 'admin') ? h('button', { class: 'pillbtn noic danger', onclick: async () => {
              if (!await confirmDialog('Delete address book', `Delete ${b.name} and its ${b.count} contacts?`, 'Delete', true)) return;
              try { await api(`/api/books/${b.id}`, { method: 'DELETE' }); await loadMeta(); onRoute(); } catch (e) { fail(e); }
            } }, 'Delete') : null));
      })));
}

async function setUsers(el) {
  const r = await api('/api/users');
  const name = h('input', { class: 't', placeholder: 'User name' }), pw = h('input', { class: 't', type: 'password', placeholder: 'Password (8 or more)' });
  const role = h('select', { class: 't' }, ['viewer', 'editor', 'admin'].map((x) => h('option', { value: x, selected: x === 'editor' ? true : null }, x)));
  el.append(h('div', { class: 'box' }, h('h2', null, icon('people'), 'Family members'),
    h('p', { class: 'muted' }, 'Everyone shares the Family address book; each account also has a private Personal book that only they see. Viewers can read the shared books and change only their own; editors change shared contacts too; admins also manage users and settings.'),
    h('table', { class: 't' }, h('tr', null, h('th', null, 'Name'), h('th', null, 'Display name'), h('th', null, 'Role'), h('th')),
      r.items.map((u) => {
        const rs = h('select', { class: 't', style: 'width:auto' }, ['viewer', 'editor', 'admin'].map((x) => h('option', { value: x, selected: x === u.role ? true : null }, x)));
        rs.onchange = async () => { try { await api(`/api/users/${u.id}`, { method: 'PATCH', json: { role: rs.value } }); toast('Saved'); } catch (e) { fail(e); onRoute(); } };
        return h('tr', null, h('td', null, u.name), h('td', null, u.displayName), h('td', null, rs), h('td', { style: { whiteSpace: 'nowrap' } },
          h('button', { class: 'pillbtn noic', onclick: async () => { const p = h('input', { class: 't', type: 'password' }); const v = await dialog(`New password for ${u.name}`, p, [{ label: 'Cancel', value: null }, { label: 'Set', value: () => p.value, primary: true }]); if (v) { try { await api(`/api/users/${u.id}`, { method: 'PATCH', json: { password: v } }); toast('Password set'); } catch (e) { fail(e); } } } }, 'Password'), ' ',
          u.role === 'viewer' && u.hasPassword ? [h('button', { class: 'pillbtn noic', title: 'One-click sign-in from the account picker', onclick: async () => { if (await confirmDialog('Remove password', `Remove ${u.name}’s password? Anyone on your home network can then sign in as ${u.name} with one click (from outside, never).`, 'Remove')) { try { await api(`/api/users/${u.id}`, { method: 'PATCH', json: { password: '' } }); toast('Password removed'); onRoute(); } catch (e) { fail(e); } } } }, 'No password'), ' '] : null,
          u.id !== S.user.id ? h('button', { class: 'pillbtn noic danger', onclick: async () => { if (await confirmDialog('Delete account', `Delete ${u.name} and their private address book?`, 'Delete', true)) { await api(`/api/users/${u.id}`, { method: 'DELETE' }); onRoute(); } } }, 'Delete') : null));
      })),
    h('h2', { style: { marginTop: '16px' } }, 'Add someone'), h('div', { class: 'multi' }, name, pw, role,
      h('button', { class: 'pillbtn primary', onclick: async () => { try { await api('/api/users', { method: 'POST', json: { name: name.value, password: pw.value, role: role.value } }); toast('Account made'); onRoute(); } catch (e) { fail(e); } } }, icon('add', 's'), 'Add'))));
  el.append(await proxyCard());
}

/** Sign-in at the proxy (Cloudflare Access, Authelia…), saved for the whole suite through iosuite-shared; the same card in every app. */
async function proxyCard() {
  let st;
  try { st = await api('/api/auth/proxy'); } catch (e) { return h('div', { class: 'box' }, h('h2', null, icon('key'), 'Sign-in at the proxy'), h('p', { class: 'warn' }, e.message)); }
  const v = st.values || {}, fixed = new Set(st.fromEnv || []);
  const field = (k, ph) => h('input', { class: 't', value: v[k] || '', placeholder: ph, disabled: fixed.has(k) ? true : null, 'data-k': k });
  const sel = (k, opts) => h('select', { class: 't', 'data-k': k, disabled: fixed.has(k) ? true : null }, opts.map(([val, l]) => h('option', { value: val, selected: (v[k] || '') === val ? true : null }, l)));
  const fields = [sel('AUTH_PROXY', [['off', 'Off'], ['cloudflare', 'Cloudflare Access'], ['haproxy', 'HAProxy'], ['nginx', 'nginx'], ['caddy', 'Caddy'], ['traefik', 'Traefik'], ['header', 'Another proxy']]),
    field('CF_ACCESS_TEAM', 'myteam.cloudflareaccess.com'), field('CF_ACCESS_AUD', 'the Access application’s AUD tag'),
    field('AUTH_PROXY_HEADER', 'header(s) with the user (other proxies)'), field('AUTH_PROXY_TRUSTED', '127.0.0.1, ::1 (the proxy’s address)'),
    sel('AUTH_PROXY_CREATE', [['', 'show the sign-in screen'], ['deny', 'refuse them'], ['viewer', 'make them a viewer account'], ['editor', 'make them an editor account']])];
  if (!v.AUTH_PROXY) fields[0].value = 'off';
  const labels = ['Proxy', 'Cloudflare team', 'Cloudflare AUD', 'User header', 'Proxy address', 'Someone with no account'];
  const seen = st.seen && st.seen.aud ? h('p', { class: 'muted small' }, `Last Cloudflare Access request: team ${st.seen.iss || '?'}, AUD ${Array.isArray(st.seen.aud) ? st.seen.aud.join(', ') : st.seen.aud}, ${st.seen.email || ''}`) : null;
  return h('div', { class: 'box' }, h('h2', null, icon('key'), 'Sign-in at the proxy'),
    h('p', { class: 'muted' }, 'With Cloudflare Access (a Cloudflare Tunnel with an Access policy) or a proxy with Authelia, Authentik or oauth2-proxy in front, ioContacts takes that sign-in: the person is matched to an account by email, then by name. Saved for the whole suite, so every app follows. Settings in the server’s environment win.'),
    h('div', { class: 'grid' }, fields.map((f, i) => fld(labels[i], f))),
    seen, fixed.size ? h('p', { class: 'muted small' }, `Fixed in the environment: ${[...fixed].join(', ')}`) : null,
    h('p', null, h('button', { class: 'pillbtn primary', onclick: async () => {
      const body = {};
      for (const f of fields) if (!f.disabled) body[f.dataset.k] = f.value;
      try { await api('/api/auth/proxy', { method: 'POST', json: body }); toast('Saved'); } catch (e) { fail(e); }
    } }, icon('check', 's'), 'Save')));
}

async function setIopix(el) {
  const s = await api('/api/iopix/settings');
  const url = h('input', { class: 't', value: s.url, placeholder: 'https://iopix.example.com or http://192.168.1.10:8600', disabled: s.fromEnv });
  const user = h('input', { class: 't', value: s.user, placeholder: 'Only when Require sign-in is on in ioPix' });
  const pw = h('input', { class: 't', type: 'password', placeholder: s.hasPassword ? '(kept)' : '' });
  const cfId = h('input', { class: 't', value: s.cfId, placeholder: 'Only behind Cloudflare Access' });
  const cfSecret = h('input', { class: 't', type: 'password', placeholder: s.hasCfSecret ? '(kept)' : '' });
  const out = h('p');
  const fld = (l, e) => h('label', { class: 'field' }, h('span', null, l), e);
  el.append(h('div', { class: 'box' }, h('h2', null, icon('image'), 'ioPix'),
    h('p', { class: 'muted' }, 'Link contacts to people named in ioPix: their face becomes the avatar (or the contact photo) and the contact links to their photos. ioContacts talks to ioPix from the server; your browser never needs to reach it. On the home network, ioPix\'s LAN address is simplest. Through Cloudflare Access, create a service token (Zero Trust › Access › Service auth) and allow it in the ioPix application\'s policy.'),
    h('div', { class: 'grid' }, fld('ioPix address', url), fld('ioPix user', user), fld('ioPix password', pw), fld('Cloudflare client ID', cfId), fld('Cloudflare client secret', cfSecret)),
    h('p', null, h('button', { class: 'pillbtn primary', onclick: async () => {
      const body = { url: url.value, user: user.value, cfId: cfId.value };
      if (pw.value) body.password = pw.value; if (cfSecret.value) body.cfSecret = cfSecret.value;
      try { const r = await api('/api/iopix/settings', { method: 'POST', json: body }); S.status = await api('/api/status'); drawNav();
        out.textContent = r.test ? (r.test.ok ? `Connected: ${r.test.people} people in ioPix.` : `Saved, but ioPix did not answer: ${r.test.error}`) : 'Saved (ioPix link off).'; } catch (e) { fail(e); }
    } }, icon('check', 's'), 'Save and test')), out));
}

async function setServer(el) {
  let s; try { s = await api('/api/server'); } catch (e) { el.replaceChildren(h('p', null, e.message)); return; }
  const mcp = h('input', { type: 'checkbox', checked: s.mcpEnabled, disabled: s.mcpLocked, onchange: async (e) => {
    try { await api('/api/server', { method: 'POST', json: { mcpEnabled: e.target.checked } }); S.status = await api('/api/status'); toast('Saved'); setServer(el); } catch (err) { e.target.checked = !e.target.checked; fail(err); }
  } });
  el.replaceChildren(
    h('div', { class: 'box' }, h('h2', null, icon('ai'), 'MCP server'),
      h('p', null, 'The address /mcp that lets an AI assistant (Claude, for example) search, read and keep the contacts: look people up, add and correct contacts, link relatives, list birthdays, import and export, and for admins check for and install updates. Each assistant signs in with an app password and acts as that account, with its rights. Off: /mcp does not answer at all.'),
      h('p', null, h('label', { class: 'check' }, mcp, ' The MCP server is on')),
      s.mcpLocked ? h('p', { class: 'muted small' }, 'MCP=1 in the environment keeps it on.') : null,
      s.mcpEnabled ? [kv('Address', `${location.origin}/mcp`),
        h('p', { class: 'muted small' }, 'How to connect an assistant: ', h('a', { class: 'lnk', href: '#/settings/devices' }, 'Settings › Apps and devices'), '. On the server itself, `python -m app.mcp --user NAME` serves it over stdio.')] : null),
    h('div', { class: 'box' }, h('h2', null, icon('server'), 'This server'),
      kv('Version', h('span', null, `v${s.version}${s.installed !== 'unknown' ? ` (${s.installed.slice(0, 7)})` : ''}`, ' · ', h('a', { class: 'lnk', href: '#/maintenance/updates' }, 'Updates and logs'))),
      kv('Database', h('span', null, s.database)), kv('LDAP', h('span', null, s.ldap || 'off')),
      h('p', { class: 'muted small' }, 'The database, the LDAP directory, the public address and the ports are set in the server’s .env file, not here.')));
}

// ------------------------------------------------------------------ sign-in
/** Start update.sh on the server, then watch /api/status until another version or commit answers, and reload. */
async function runUpdate() {
  try { await api('/api/server', { method: 'POST', json: { action: 'update' } }); } catch (e) { fail(e); return false; }
  toast('Updating; ioContacts restarts when it is done, and the page reloads.');
  const was = `${S.status.version}|${S.status.commit || ''}`, until = Date.now() + 240000;
  const look = async () => {
    try { const s = await fetch('/api/status', { credentials: 'same-origin' }).then((r) => r.json()); if (s.version && `${s.version}|${s.commit || ''}` !== was) { location.reload(); return; } } catch { /* restarting */ }
    if (Date.now() < until) setTimeout(look, 4000); else toast('The update did not finish; see Maintenance › Updates and logs.');
  };
  setTimeout(look, 4000);
  return true;
}

/** Admins: a note when the daily check found a newer version, with Update now. Hidden until the next version when dismissed. */
function updateBanner() {
  $('#updbanner')?.remove();
  const u = S.status && S.status.updateAvailable;
  let dismissed = null; try { dismissed = localStorage.getItem('ioc.updateDismissed'); } catch { /* private mode */ }
  if (!u || dismissed === u.remote) return;
  const b = h('div', { id: 'updbanner', role: 'status' }, icon('update'),
    h('span', null, `ioContacts ${u.version ? `v${u.version}` : 'update'} is available${u.message ? `: ${u.message.replace(/^v\d+\.\d+\.\d+:\s*/, '')}` : ''}`),
    h('button', { class: 'pillbtn primary noic', onclick: async () => { if (await confirmDialog('Update ioContacts', 'Install the new version and restart? The page reloads when it is back.', 'Update now')) { b.remove(); runUpdate(); } } }, 'Update now'),
    h('a', { class: 'pillbtn noic', href: '#/maintenance/updates', onclick: () => b.remove() }, 'Details'),
    h('button', { class: 'iconbtn', title: 'Not now (hidden until the next version)', onclick: () => { try { localStorage.setItem('ioc.updateDismissed', u.remote); } catch { /* */ } b.remove(); } }, icon('close', 's')));
  document.body.append(b);
}

function showSignIn() {
  // like ioPix: a tile per account; one click for a passwordless viewer, a password for the others
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
  const go = (e) => { e.preventDefault(); login(name.value.trim(), pw.value); };
  document.body.append(h('div', { class: 'signin' }, h('form', { class: 'dialog', onsubmit: go },
    h('div', { class: 'brand' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }), h('span', { class: 'brand-name', style: { display: 'inline' } }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Contacts'))),
    first ? h('p', { class: 'muted' }, 'Welcome. Make the first account: it is the admin, who adds the rest of the family in Settings.') : h('h2', null, 'Sign in'),
    tiles, form, err, h('div', { class: 'btns' }, btn))));
  if (first) { name.focus(); return; }
  const pick = (t) => tiles.querySelectorAll('.account').forEach((x) => x.classList.toggle('on', x === t));
  api('/api/auth/accounts').then((d) => {
    if (!d.accounts.length) { name.focus(); return; }
    form.hidden = true; btn.hidden = true;
    const face = (a) => {
      const el = h('span', { class: 'av big', style: { '--h': hue(a.displayName || a.name) } }, initials(a.displayName || a.name));
      if (a.photo) { const img = h('img', { src: `/api/auth/accounts/${a.id}/photo`, alt: '', onerror: () => img.remove() }); el.append(img); }
      return el;
    };
    tiles.append(...d.accounts.map((a) => {
      const t = h('button', { type: 'button', class: 'account', title: a.passwordless ? `Sign in as ${a.name}` : `${a.name} (password)`, onclick: () => {
        pick(t);
        if (a.passwordless) { login(a.name, ''); return; }
        name.value = a.name; name.hidden = true; form.hidden = false; btn.hidden = false; pw.value = ''; pw.focus();
      } }, face(a), h('span', { class: 'nm' }, a.displayName || a.name), a.passwordless ? null : h('span', { class: 'muted small' }, 'password'));
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
  updateBanner();
  setInterval(async () => { try { S.status = await api('/api/status'); updateBanner(); } catch { /* restarting */ } }, 15 * 60 * 1000);
}
start().catch(fail);
