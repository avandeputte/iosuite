/* ioSuite web app: one module, no build step, as in the other io apps. The start page (the weather, a tile per app,
   the bookmarks in groups) and the settings (account, home page, Home Assistant, bookmarks, server, security, global settings). Each tile keeps a `.more` block under its name, where the app shows a glimpse of
   itself (photos from this day, the rest of today, steps and rings), filled from /api/widgets/<app>. */

// ------------------------------------------------------------------ helpers
const $ = (s, el = document) => el.querySelector(s);
const ICONS = {
  add: 'M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z',
  person: 'M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z',
  people: 'M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z',
  settings: 'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z',
  close: 'M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z',
  key: 'M12.65 10C11.83 7.67 9.61 6 7 6c-3.31 0-6 2.69-6 6s2.69 6 6 6c2.61 0 4.83-1.67 5.65-4H17v4h4v-4h2v-4H12.65zM7 14c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
  logout: 'M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z',
  copy: 'M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z',
  apps: 'M4 8h4V4H4v4zm6 12h4v-4h-4v4zm-6 0h4v-4H4v4zm0-6h4v-4H4v4zm6 0h4v-4h-4v4zm6-10v4h4V4h-4zm-6 4h4V4h-4v4zm6 6h4v-4h-4v4zm0 6h4v-4h-4v4z',
  check: 'M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z',
  update: 'M21 10.12h-6.78l2.74-2.82c-2.73-2.7-7.15-2.8-9.88-.1a6.875 6.875 0 0 0 0 9.79 7.02 7.02 0 0 0 9.88 0C18.32 15.65 19 14.08 19 12.1h2c0 1.98-.88 4.55-2.64 6.29-3.51 3.48-9.21 3.48-12.72 0-3.5-3.47-3.53-9.11-.02-12.58a8.987 8.987 0 0 1 12.65 0L21 3v7.12z',
  theme: 'M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.389 5.389 0 0 1-4.4 2.26 5.403 5.403 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z',
  link: 'M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z',
  cloud: 'M19.35 10.04A7.49 7.49 0 0 0 12 4C9.11 4 6.6 5.64 5.35 8.04A5.994 5.994 0 0 0 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96z',
  search: 'M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z',
  download: 'M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z',
  note: 'M3 18h12v-2H3v2zM3 6v2h18V6H3zm0 7h18v-2H3v2z',
  tune: 'M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 4v-2H11v2h10zm-6-4h2V7h4V5h-4V3h-2v6z',
  up: 'M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z',
  down: 'M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z',
  grip: 'M11 18c0 1.1-.9 2-2 2s-2-.9-2-2 .9-2 2-2 2 .9 2 2zm-2-8c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0-6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm6 4c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  edit: 'M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a.996.996 0 0 0 0-1.41l-2.34-2.34a.996.996 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z',
  delete: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z',
  wall: 'M21 3H3c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h5v2h8v-2h5c1.1 0 1.99-.9 1.99-2L23 5c0-1.1-.9-2-2-2zm0 14H3V5h18v12z',
  fullscreen: 'M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z',
  event: 'M17 12h-5v5h5v-5zM16 1v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2h-1V1h-2zm3 18H5V8h14v11z',
  web: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z',
  home: 'M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z',
  bulb: 'M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7z',
  power: 'M13 3h-2v10h2V3zm4.83 2.17-1.42 1.42A6.92 6.92 0 0 1 19 12c0 3.87-3.13 7-7 7A6.995 6.995 0 0 1 7.58 6.58L6.17 5.17A8.932 8.932 0 0 0 3 12a9 9 0 0 0 18 0c0-2.74-1.23-5.18-3.17-6.83z',
  lock: 'M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zM9 8V6c0-1.66 1.34-3 3-3s3 1.34 3 3v2H9z',
  unlock: 'M12 17c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm6-9h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6h1.9c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm0 12H6V10h12v10z',
  door: 'M19 19V4c0-1.1-.9-2-2-2H7c-1.1 0-2 .9-2 2v15H3v2h18v-2h-2zm-4-6h-2v-2h2v2z',
  thermo: 'M15 13V5c0-1.66-1.34-3-3-3S9 3.34 9 5v8c-1.21.91-2 2.37-2 4 0 2.76 2.24 5 5 5s5-2.24 5-5c0-1.63-.79-3.09-2-4zm-4-8c0-.55.45-1 1-1s1 .45 1 1h-1v1h1v2h-1v1h1v2h-2V5z',
  warn: 'M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z',
  play: 'M8 5v14l11-7z',
  blind: 'M20 19V3H4v16H2v2h20v-2h-2zM6 5h12v2H6V5zm0 4h12v2H6V9zm0 4h12v2H6v-2zm0 6v-2h12v2H6z',
  fan: 'M12 11a1 1 0 1 0 0 2 1 1 0 0 0 0-2zm0-9c-1.5 0-3 .9-3 3 0 1.7.9 3.4 2 5.3-1.9-1-3.6-1.3-5.3-1.3-2.1 0-3.7 1.5-3.7 3s1.6 3 3.7 3c1.7 0 3.4-.3 5.3-1.3-1.1 1.9-2 3.6-2 5.3 0 2.1 1.5 3 3 3s3-.9 3-3c0-1.7-.9-3.4-2-5.3 1.9 1 3.6 1.3 5.3 1.3 2.1 0 3.7-1.5 3.7-3s-1.6-3-3.7-3c-1.7 0-3.4.3-5.3 1.3 1.1-1.9 2-3.6 2-5.3 0-2.1-1.5-3-3-3z',
  bolt: 'M7 2v11h3v9l7-12h-4l4-8z',
  battery: 'M15.67 4H14V2h-4v2H8.33C7.6 4 7 4.6 7 5.33v15.33C7 21.4 7.6 22 8.33 22h7.33c.74 0 1.34-.6 1.34-1.33V5.33C17 4.6 16.4 4 15.67 4zM15 18H9v-6h6v6z',
  folder: 'M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z',
  phone: 'M15.5 1h-8A2.5 2.5 0 0 0 5 3.5v17A2.5 2.5 0 0 0 7.5 23h8a2.5 2.5 0 0 0 2.5-2.5v-17A2.5 2.5 0 0 0 15.5 1zm-4 21c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm4.5-4H7V4h9v14z',
  more: 'M6 10c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm12 0c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm-6 0c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  left: 'M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z',
  right: 'M8.59 16.59 13.17 12 8.59 7.41 10 6l6 6-6 6z',
  server: 'M20 13H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1v-6c0-.55-.45-1-1-1zM7 19c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zM20 3H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1V4c0-.55-.45-1-1-1zM7 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
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

const hue = (s) => { let x = 0; for (const c of s || '') x = (x * 31 + c.charCodeAt(0)) % 360; return x; };
const initials = (fn) => { const p = (fn || '?').trim().split(/\s+/); return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase(); };
/** A contact's face as ioContact shows it: its own photo, else its face in ioPix (when linked), else its initials. */
function contactFace(c, lazy = true) {
  const src = c.hasPhoto ? `/api/widgets/iocontact/photo/${c.id}` : c.iopixPersonId ? `/api/widgets/iocontact/face/${c.iopixPersonId}` : null;
  return h('span', { class: 'face' }, src ? h('img', { src, alt: '', loading: lazy ? 'lazy' : undefined, onerror: (e) => e.target.replaceWith(initials(c.name)) }) : initials(c.name));
}
/** An app's name as the apps write it: "io" in gold, the rest in the app's colour. */
/* The weather: AccuWeather's icon numbers (1-44) drawn with a handful of glyphs. */
const WX = {
  sun: '<circle cx="12" cy="12" r="4.2"/><g stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8"/></g>',
  moon: '<path d="M14.5 3.5a8.5 8.5 0 1 0 6 14.5 7 7 0 0 1-6-14.5z"/>',
  cloud: '<path d="M18.5 19H7a4.5 4.5 0 0 1-.7-8.95A6 6 0 0 1 17.8 9.5 4.75 4.75 0 0 1 18.5 19z"/>',
  partly: '<circle cx="8" cy="8" r="3.4"/><g stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M8 1.8v1.6M1.8 8h1.6M3.6 3.6l1.1 1.1M12.4 3.6l-1.1 1.1"/></g><path d="M19 20.5H9.5a3.8 3.8 0 0 1-.6-7.55A5 5 0 0 1 18.4 12 4 4 0 0 1 19 20.5z"/>',
  partlyNight: '<path d="M9.2 2.2a5.2 5.2 0 1 0 4.1 8.6 4.4 4.4 0 0 1-4.1-8.6z"/><path d="M19 20.5H9.5a3.8 3.8 0 0 1-.6-7.55A5 5 0 0 1 18.4 12 4 4 0 0 1 19 20.5z"/>',
  rain: '<path d="M18.5 15H7a4.5 4.5 0 0 1-.7-8.95A6 6 0 0 1 17.8 5.5 4.75 4.75 0 0 1 18.5 15z"/><g stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M8.5 17.5l-1 3M12.5 17.5l-1 3M16.5 17.5l-1 3"/></g>',
  storm: '<path d="M18.5 14H7a4.5 4.5 0 0 1-.7-8.95A6 6 0 0 1 17.8 4.5 4.75 4.75 0 0 1 18.5 14z"/><path d="M12.5 13.5 9 19h3l-1 4.5 4.5-6.5h-3l1.5-3.5z"/>',
  snow: '<path d="M18.5 14H7a4.5 4.5 0 0 1-.7-8.95A6 6 0 0 1 17.8 4.5 4.75 4.75 0 0 1 18.5 14z"/><g fill="currentColor"><circle cx="8.5" cy="18" r="1.3"/><circle cx="12.5" cy="20.5" r="1.3"/><circle cx="16.5" cy="18" r="1.3"/></g>',
  fog: '<g stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 9h16M3 13h18M5 17h14"/></g>',
  wind: '<g fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M3 9h11a2.5 2.5 0 1 0-2.5-2.5M3 14h15a2.5 2.5 0 1 1-2.5 2.5M3 19h7"/></g>',
  hot: '<circle cx="12" cy="12" r="4.2"/><g stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5"/></g>',
};
const WX_MAP = { 1: 'sun', 2: 'sun', 3: 'partly', 4: 'partly', 5: 'partly', 6: 'cloud', 7: 'cloud', 8: 'cloud', 11: 'fog', 12: 'rain', 13: 'rain', 14: 'partly', 15: 'storm', 16: 'storm', 17: 'partly',
  18: 'rain', 19: 'snow', 20: 'snow', 21: 'snow', 22: 'snow', 23: 'snow', 24: 'snow', 25: 'snow', 26: 'rain', 29: 'snow', 30: 'hot', 31: 'snow', 32: 'wind',
  33: 'moon', 34: 'moon', 35: 'partlyNight', 36: 'partlyNight', 37: 'fog', 38: 'cloud', 39: 'rain', 40: 'rain', 41: 'storm', 42: 'storm', 43: 'snow', 44: 'snow' };
const wxIcon = (n, cls = '') => { const s = document.createElement('span'); s.className = 'wx ' + cls; s.innerHTML = `<svg viewBox="0 0 24 24">${WX[WX_MAP[n] || 'cloud']}</svg>`; return s; };
const degF = (c) => (c == null ? null : c * 9 / 5 + 32);
const fmtTemp = (v) => (v == null ? '–' : `${Math.round(v)}°`);
/** A bookmark's icon as homepage reads it: a full address, or a file name from the dashboard-icons collection. */
const bmIconUrl = (icon) => { if (!icon) return ''; if (/^https?:\/\//.test(icon)) return icon; const m = icon.match(/^([\w.-]+)\.(png|svg|webp)$/); return m ? `https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/${m[2]}/${m[1]}.${m[2]}` : ''; };
/** What to show for a link: the icon uploaded for it (served by this page) wins over the icon field. */
const bmIcon = (l) => l.iconUrl || bmIconUrl(l.icon) || l.siteIcon || '';  // its own, else the site's (fetched by the server)
/** Links whose site icon the server is still fetching (iconPending): ask again shortly, a few times, and put the
 *  icons that arrived in place of the badges. `again` reads the links anew. */
function bmIconsLater(el, links, again, n = 0) {
  if (n >= 4 || !links.some((l) => l.iconPending)) return;
  setTimeout(async () => {
    if (!el.isConnected) return;
    let now; try { now = await again(); } catch { return; }
    if (!el.isConnected) return;
    for (const l of now) {
      const ic = l.siteIcon && !l.iconPending ? el.querySelector(`[data-id="${l.id}"] > .bmic`) : null;
      if (ic && !ic.querySelector('img')) ic.replaceChildren(h('img', { src: l.siteIcon, alt: '', onerror: (e) => { e.target.replaceWith(l.abbr); } }));
    }
    bmIconsLater(el, now, again, n + 1);
  }, 2500 + n * 2500);
}
const bmFlat = (items) => items.flatMap((x) => (x.type === 'folder' ? bmFlat(x.items) : [x]));

const appName = (name, color) => h('span', { class: 'nm', style: { '--c': color } }, h('span', { class: 'io' }, 'io'), h('span', { class: 'ap' }, name.replace(/^io/, '')));

// ------------------------------------------------------------------ state
const S = { status: {}, user: null, settings: {}, apps: [] };

/* The account menu lives in the top bar, or in the start page's first row (showHome moves it there). It is held by
   reference: when the page is drawn again the old page, and the menu inside it, are gone from the document, and
   looking it up by id would find nothing (the menu then vanished until a reload). */
const userMenu = () => (S.userMenu = S.userMenu || $('#usermenu'));
function drawUser() {
  const m = userMenu(); m.replaceChildren();
  if (!S.user) return;
  const btn = h('button', { class: 'iconbtn gear', title: `${S.user.displayName} · settings` }, icon('settings'));
  let menu = null;
  const closeMenu = () => { if (menu) { menu.remove(); menu = null; document.removeEventListener('click', outside); } };
  const outside = (e) => { if (menu && !menu.contains(e.target) && e.target !== btn) closeMenu(); };
  btn.onclick = () => {
    if (menu) return closeMenu();
    const theme = localStorage.getItem('iosuite.theme') || 'system';
    // the admin tools (ioDNS…: only their admins get them) are listed here, not on the start page
    const tools = h('div', { class: 'mtools', hidden: true });
    const listTools = (apps) => {
      const t = apps.filter((a) => a.adminTool);
      tools.hidden = !t.length;
      tools.replaceChildren(h('div', { class: 'mhead muted small' }, 'Admin tools'),
        ...t.map((a) => h('a', { class: 'mi', href: a.url, onclick: closeMenu }, h('img', { src: a.icon, alt: '' }), a.name)));
    };
    if (S.allApps) listTools(S.allApps);
    else api('/api/apps').then((got) => { S.allApps = got.items; listTools(got.items); }).catch(() => {});
    menu = h('div', { class: 'menu' },
      h('div', { class: 'who' }, h('b', null, S.user.displayName), h('div', { class: 'muted small' }, `${S.user.name} · ${S.user.role}`)),
      h('a', { class: 'mi', href: '#/settings/account', onclick: closeMenu }, icon('person', 's'), 'Account'),
      h('a', { class: 'mi', href: '#/bookmarks', onclick: closeMenu }, icon('link', 's'), 'Bookmarks'),
      h('button', { class: 'mi', onclick: () => { closeMenu(); customize(); } }, icon('tune', 's'), 'Customize the page'),
      h('button', { class: 'mi', onclick: () => { closeMenu(); enterWall(); } }, icon('wall', 's'), 'Wall display'),
      h('button', { class: 'mi', onclick: () => { const n = { system: 'light', light: 'dark', dark: 'system' }[theme]; setTheme(n); api('/api/auth/settings', { method: 'POST', json: { theme: n } }).catch(() => {}); closeMenu(); toast(`Appearance: ${n}`); } },
        icon('theme', 's'), `Appearance: ${theme}`),
      tools,
      h('a', { class: 'mi', href: '#/settings', onclick: closeMenu }, icon('settings', 's'), 'Settings'),
      h('button', { class: 'mi', onclick: async () => { const r = await api('/api/auth/logout', { method: 'POST' }); if (r && r.cloudflareLogout) location.href = r.cloudflareLogout; else location.reload(); } }, icon('logout', 's'), 'Sign out'));
    m.append(menu);
    setTimeout(() => document.addEventListener('click', outside), 0);
  };
  m.append(btn);
}
/** The theme: kept with the account (Settings › Display), and in this browser so the page draws in it at once. */
function setTheme(t) {
  try { localStorage.setItem('iosuite.theme', t); } catch { /* private mode */ }
  if (S.settings) S.settings.theme = t;
  applyTheme();
}
function applyTheme() {
  let t = 'system'; try { t = localStorage.getItem('iosuite.theme') || 'system'; } catch { /* private mode */ }
  if (t === 'system') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
}

// ------------------------------------------------------------------ routes
/* /bookmarks is the Bookmarks page as an app of its own (its own name, icon and manifest: "Add to Home Screen" on an
   iPhone, "Install" on a desktop): the same page, opening on the bookmarks, with the start page a tap on the brand away. */
const BM_APP = /\/bookmarks\/?$/.test(location.pathname);
function route() {
  const [a, b, c] = location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
  if (a === 'settings') return { view: 'settings', tab: b || 'account', sub: c };
  if (a === 'bookmarks' || (a === 'settings' && b === 'bookmarks')) return { view: 'bookmarks' };
  if (a === 'wall') return { view: 'wall' };
  if (BM_APP && !a) return { view: 'bookmarks' };  // the Bookmarks app opens on them
  return { view: 'home' };
}
async function onRoute() {
  const r = route();
  const page = h('div', { class: 'page' });
  // the start page has no top bar: the account menu sits in its first row instead (showHome moves it there)
  document.body.classList.toggle('home', r.view === 'home');
  document.body.classList.toggle('wall', r.view === 'wall');
  S.refresh = null; S.shownDay = null;  // the view drawn next says how it refreshes itself (liveRefresh)
  if (S.wallStop) { S.wallStop(); S.wallStop = null; }
  haStreamStop();  // the view opens its own stream of Home Assistant changes when it needs one
  $('#topbar').append(userMenu());  // out of the old page before it goes; showHome takes it into the new one
  $('#main').replaceChildren(page);
  try { await ({ home: showHome, settings: showSettings, wall: showWall, bookmarks: showBookmarks })[r.view](page, r); } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ the start page
const greeting = () => { const hr = new Date().getHours(); return hr < 5 ? 'Good night' : hr < 12 ? 'Good morning' : hr < 18 ? 'Good afternoon' : 'Good evening'; };

async function showHome(page) {
  const got = await api('/api/apps');
  // the viewer's own layout (Customize the page) on top of the admin's: tiles and cards hidden, tiles in their order
  const L = S.layout = got.layout || { hidden: [], order: [], cards: [], strip: null };
  S.photoStrip = got.photoStrip;  // the admin's choice, what Customize calls "as the admin set it"
  S.allApps = got.items;
  const rank = (a) => { const i = L.order.indexOf(a.key); return i < 0 ? 100 + got.items.indexOf(a) : i; };
  // the admin tools (ioDNS…) are not tiles: the gear menu lists them
  S.apps = got.items.filter((a) => !a.adminTool && !L.hidden.includes(a.key)).sort((a, b) => rank(a) - rank(b));
  const shows = (k) => !L.hidden.includes(k);
  const first = (S.user.displayName || S.user.name).split(/\s+/)[0];
  const wx = h('div', { class: 'weather' });
  page.append(h('div', { class: 'top' }, h('div', { class: 'hello' }, h('h1', { class: 'greet' }, `${greeting()}, ${first}`),
    h('div', { class: 'dateline' }, h('span', { class: 'muted' }, new Date().toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })), userMenu())), searchBox(), wx));
  // under the greeting: a column for the tiles and the cards and, on a wide screen, the bookmarks in a column of their
  // own on the right (when they come last, as by default); narrower, the side column simply follows the main one
  const col = h('div', { class: 'homecol' }), side = h('div', { class: 'homeside' });
  page.append(h('div', { class: 'homegrid' }, col, side));
  drawWeather(wx);  // fills in when AccuWeather (or the server's copy) answers
  // the tiles: an app with something to show gets a column of its own; the others go three to a column, a third of the height
  const tile = (a, small) => h('a', { class: `app${small ? ' small' : ''}`, href: a.url, 'data-app': a.key, title: a.url },
    h('img', { src: a.icon, alt: '' }), h('span', { class: 'who' }, h('span', { class: 'nmrow' }, appName(a.name, a.color), h('span', { class: 'st' }))),
    h('div', { class: 'more' }));  // what the app shows here: drawWidgets
  const big = S.apps.filter((a) => WIDGETS[a.key]), rest = S.apps.filter((a) => !WIDGETS[a.key]);
  const stacks = []; for (let i = 0; i < rest.length; i += 3) stacks.push(h('div', { class: 'stack' }, rest.slice(i, i + 3).map((a) => tile(a, true))));
  if (!S.apps.length) col.append(h('div', { class: 'empty' }, got.items.length ? 'Every tile is hidden. ' : 'No io app has registered itself in the Shared ioSuite database yet: each one appears here once it has started.',
    got.items.length ? h('button', { class: 'lnk', onclick: customize }, 'Customize the page') : null));
  else col.append(h('div', { class: 'apps', style: { '--cols': big.length + stacks.length } }, big.map((a) => tile(a, false)), stacks));
  drawWidgets(page);
  drawAppStatus(page);
  // the week ahead: birthdays from ioContact and the coming days' events from ioCalendar, a card each
  // the cards under the tiles, in the viewer's order (Customize); Birthdays and This week share a row when they follow
  // each other, else each stands on its own
  S.birthdaysCard = shows('birthdays') && S.apps.some((a) => a.key === 'iocontact');  // then the calendar leaves birthdays to it
  const stripKind = L.strip || got.photoStrip;
  const alerts = h('div', { class: 'alerts', hidden: true });  // what Home Assistant says needs attention (drawHomeCard fills it)
  col.append(alerts);
  const cards = {
    home: shows('home') ? () => { const c = h('div', { class: 'card homecard', hidden: true }); drawHomeCard(c, alerts); return c; } : null,
    birthdays: S.birthdaysCard ? () => { const c = h('div', { class: 'card capped birthdays' }); drawBirthdays(c); return c; } : null,
    week: shows('week') && S.apps.some((a) => a.key === 'iocalendar') ? () => { const c = h('div', { class: 'card capped week' }); drawWeek(c); return c; } : null,
    strip: shows('strip') && stripKind !== 'off' && S.apps.some((a) => a.key === 'iopix') ? () => { const c = h('div', { class: 'strip' }); drawStrip(c, stripKind); return c; } : null,
    bookmarks: shows('bookmarks') ? () => { const c = h('div', { class: 'bookmarks' }); drawBookmarks(c); return c; } : null,
  };
  let agenda = null;
  const order = cardOrder(L).filter((k) => cards[k]);
  for (const k of order) {
    if (k === 'bookmarks' && k === order[order.length - 1]) { side.append(cards[k]()); continue; }
    if (k === 'birthdays' || k === 'week') {
      if (!agenda || !agenda.isConnected || agenda !== col.lastElementChild) { agenda = h('div', { class: 'agenda' }); col.append(agenda); capAgenda(page.querySelector('.apps'), agenda); }
      agenda.append(cards[k]());
    } else col.append(cards[k]());
  }
  // live refresh: every few minutes, and on coming back to the tab, the page brings itself up to date in place
  S.shownDay = dayKey(); S.refreshedAt = Date.now();
  S.refresh = () => {
    const g = page.querySelector('.greet'); if (g) g.textContent = `${greeting()}, ${first}`;
    drawWidgets(page, true); drawAppStatus(page); drawWeather(wx, true);
    for (const c of page.querySelectorAll('.card.birthdays.capped')) drawBirthdays(c, true);
    for (const c of page.querySelectorAll('.card.week.capped')) drawWeek(c, true);
    const hc = page.querySelector('.homecard'); if (hc) drawHomeCard(hc, alerts, true);
    const bm = page.querySelector('.bookmarks'); if (bm) drawBookmarkStatus(bm);
  };
}

// ------------------------------------------------------------------ live refresh
/* A start page stays open all day: every five minutes (and when the tab is shown again) the view on screen brings
   itself up to date in place (S.refresh: the tiles' widgets, the weather, the cards, the dots), without a flicker; at
   midnight the whole page is drawn anew, for the new day's greeting, date, On this day and birthdays. Nothing runs
   while the tab is hidden, a dialog is open, or someone is typing in the search box. */
const REFRESH_EVERY = 5 * 60 * 1000;
const dayKey = () => new Date().toDateString();
function liveRefresh(force = false) {
  if (document.hidden || !S.refresh || document.querySelector('.dialog-back')) return;
  if (S.shownDay && S.shownDay !== dayKey()) { onRoute(); return; }
  const typing = document.activeElement && document.activeElement.matches('input, textarea, select');
  if (typing || (!force && Date.now() - (S.refreshedAt || 0) < REFRESH_EVERY)) return;
  S.refreshedAt = Date.now();
  try { S.refresh(); } catch { /* the next round */ }
}
const CARDS = ['home', 'birthdays', 'week', 'strip', 'bookmarks'];
/** The cards' order: the viewer's, then any the viewer's list does not name, in the usual order. */
const cardOrder = (L) => [...(L.cards || []), ...CARDS.filter((k) => !(L.cards || []).includes(k))];

// ------------------------------------------------------------------ the search box (⌘K / Ctrl-K)
/* Type, and the box lists the bookmarks that match, the contacts ioContact finds, and a row per app that searches
   itself (ioPix, ioCalendar, ioNote open on their own results). Arrows pick a row, Enter opens it, Escape clears. */
// Lower case without accents, so "celia" finds "Célia" (and "Celia" finds "célia"); a few letters NFD does not split.
const FOLD = { ß: 'ss', æ: 'ae', œ: 'oe', ø: 'o', ł: 'l', đ: 'd', ð: 'd', þ: 'th', ı: 'i' };
const fold = (s) => String(s || '').normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().replace(/[ßæœøłđðþı]/g, (c) => FOLD[c]);
const APP_SEARCH = { iopix: (q) => `#/photos?q=${encodeURIComponent(q)}`, iocalendar: (q) => `#/search/${encodeURIComponent(q)}`, ionote: (q) => `#/notes?q=${encodeURIComponent(q)}` };
function searchBox() {
  const inp = h('input', { class: 'q', type: 'search', placeholder: 'Search, or add an event', autocomplete: 'off', spellcheck: 'false', 'aria-label': 'Search bookmarks, contacts, the apps and the web, or add an event' });
  const list = h('div', { class: 'qlist', hidden: true });
  const box = h('div', { class: 'search' }, icon('search', 's'), inp, h('kbd', null, /Mac|iPhone|iPad/.test(navigator.platform) ? '⌘K' : 'Ctrl K'), list);
  let rows = [], sel = 0, timer = null, people = { q: '', items: [] }, things = { q: '', items: [] };
  const hide = () => { list.hidden = true; list.replaceChildren(); rows = []; };
  const row = (href, kids, ext) => { const a = h('a', { class: 'qrow', href, ...(ext ? { target: '_blank', rel: 'noreferrer' } : {}), onmousedown: (e) => e.preventDefault() }, kids); rows.push(a); return a; };
  const build = () => {
    const q = inp.value.trim(), ql = q.toLowerCase();
    rows = [];
    if (!q) return hide();
    const links = (S.bookmarks || []).filter((l) => fold(`${l.name} ${l.description || ''} ${l.href}`).includes(fold(q))).slice(0, 6);
    const contacts = S.apps.find((a) => a.key === 'iocontact');
    const bang = webBang(q), site = bang ? null : looksLikeSite(q), cal = !bang && S.apps.find((a) => a.key === 'iocalendar') && parseEvent(q);
    const eng = bang ? bang.engine : webEngine(), wq = bang ? bang.q : q;
    const webRow = () => row(eng.url(wq), [h('span', { class: 'bmic' }, icon('web', 's')), h('span', { class: 'qname' }, `“${wq}”`), h('span', { class: 'muted small' }, eng.name)], true);
    const found = links.length || (contacts && people.q === ql && people.items.length) || (things.q === ql && things.items.length);
    const kids = [
      // a site typed in full, or a prefix (g, w, yt…): that first, Enter goes there
      site ? [h('div', { class: 'qhead' }, 'Open'), row(site, [h('span', { class: 'bmic' }, icon('link', 's')), h('span', { class: 'qname' }, site.replace(/^https?:\/\//, '')), h('span', { class: 'muted small' }, 'New tab')], true)] : null,
      bang ? [h('div', { class: 'qhead' }, eng.name), webRow()] : null,
      links.length ? h('div', { class: 'qhead' }, 'Bookmarks') : null,
      links.map((l) => { const src = bmIcon(l); return row(l.href, [h('span', { class: 'bmic' }, src ? h('img', { src, alt: '' }) : l.abbr), h('span', { class: 'qname' }, l.name), h('span', { class: 'muted small' }, l.description || l.href)], true); }),
      contacts && people.q === ql && people.items.length ? h('div', { class: 'qhead' }, 'People') : null,
      contacts && people.q === ql ? people.items.map((c) => row(`${contacts.url}/#/c/${c.id}`, [contactFace(c, false), h('span', { class: 'qname' }, c.name), h('span', { class: 'muted small' }, c.org || '')])) : null,
      // Home Assistant: an entity's state, and a tap switches the ones the admin lets the page control
      things.q === ql && things.items.length ? h('div', { class: 'qhead' }, 'Home') : null,
      things.q === ql ? things.items.map((t) => { const a = row(t.control ? '#' : haLink(t), [h('span', { class: `bmic ha${t.on ? ' on' : ''}` }, icon(haIcon(t), 's')), h('span', { class: 'qname' }, t.name), h('span', { class: `muted small${t.control ? ' tap' : ''}` }, t.control ? `${t.text || t.state} · tap` : t.text || t.state)]);
        if (t.control && HA_POPUPS[t.domain]) a.onclick = (e) => { e.preventDefault(); inp.blur(); haPopup(t, (r) => Object.assign(t, r)); };
        else if (t.control) a.onclick = async (e) => { e.preventDefault(); const r = await haAct(t.id, 'toggle'); if (r) { Object.assign(t, r); build(); } const card = document.querySelector('.homecard'); if (card) setTimeout(() => drawHomeCard(card, document.querySelector('.alerts'), true), 4000); }; return a; }) : null,
      // "dinner fri 19:00": a new event in ioCalendar (a dialog to check it first)
      cal ? [h('div', { class: 'qhead' }, 'Add to the calendar'), (() => { const a = row('#', [h('span', { class: 'bmic' }, icon('event', 's')), h('span', { class: 'qname' }, cal.title || '(no title)'), h('span', { class: 'muted small' }, eventWhen(cal))]);
        a.onclick = (e) => { e.preventDefault(); inp.blur(); quickAdd(cal); }; return a; })()] : null,
      // nothing here matches: the web first, so Enter searches it
      !bang && !site && !found ? [h('div', { class: 'qhead' }, 'Web'), webRow()] : null,
      h('div', { class: 'qhead' }, 'Search in'),
      S.allApps.filter((a) => APP_SEARCH[a.key]).map((a) => row(`${a.url}/${APP_SEARCH[a.key](q)}`, [h('img', { class: 'qapp', src: a.icon, alt: '' }), h('span', { class: 'qname' }, appName(a.name, a.color)), h('span', { class: 'muted small' }, `“${q}”`)])),
      !bang && !site && found ? webRow() : null,
    ];
    sel = Math.min(sel, rows.length - 1);
    rows.forEach((r, i) => r.classList.toggle('on', i === sel));
    list.replaceChildren(...kids.flat().filter(Boolean)); list.hidden = false;
  };
  const askPeople = async () => {
    const q = inp.value.trim(), ql = q.toLowerCase();
    if (q.length < 2 || !S.apps.some((a) => a.key === 'iocontact')) return;
    const d = await widget('iocontact', { q });
    if (inp.value.trim().toLowerCase() !== ql) return;
    people = { q: ql, items: (d && d.items) || [] }; build();
  };
  const askThings = async () => {
    const q = inp.value.trim(), ql = q.toLowerCase();
    if (q.length < 2 || S.ha === false) return;
    let d = null;
    try { d = await api(`/api/ha/search?${new URLSearchParams({ q, n: 5 })}`); } catch { d = null; }
    if (inp.value.trim().toLowerCase() !== ql) return;
    things = { q: ql, items: (d && d.items) || [] }; build();
  };
  inp.oninput = () => { sel = 0; build(); clearTimeout(timer); timer = setTimeout(() => { askPeople(); askThings(); }, 250); };
  inp.onfocus = () => { if (inp.value.trim()) build(); };
  inp.onblur = () => setTimeout(hide, 150);
  inp.onkeydown = (e) => {
    if (e.key === 'Escape') { if (inp.value) { inp.value = ''; hide(); } else inp.blur(); e.preventDefault(); }
    else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { if (!rows.length) return; sel = (sel + (e.key === 'ArrowDown' ? 1 : rows.length - 1)) % rows.length; rows.forEach((r, i) => r.classList.toggle('on', i === sel)); rows[sel].scrollIntoView({ block: 'nearest' }); e.preventDefault(); }
    else if (e.key === 'Enter') { if (rows[sel]) { rows[sel].click(); e.preventDefault(); if (rows[sel] && rows[sel].target === '_blank') { inp.value = ''; hide(); } } }
  };
  S.focusSearch = () => { inp.focus(); inp.select(); };
  return box;
}

// ------------------------------------------------------------------ the web from the search box
/* Enter with nothing of the suite matching searches the web with the viewer's engine (Customize the page); a prefix
   picks a site instead: "g …" Google, "w …" Wikipedia, "yt …" YouTube… (also as "!g …"). A typed address opens. */
const engine = (name, base) => ({ name, url: (q) => base + encodeURIComponent(q) });
const ENGINES = {
  duckduckgo: engine('DuckDuckGo', 'https://duckduckgo.com/?q='), google: engine('Google', 'https://www.google.com/search?q='),
  bing: engine('Bing', 'https://www.bing.com/search?q='), startpage: engine('Startpage', 'https://www.startpage.com/do/search?q='),
  ecosia: engine('Ecosia', 'https://www.ecosia.org/search?q='), kagi: engine('Kagi', 'https://kagi.com/search?q='),
};
const wikiLang = () => ((navigator.language || 'en').slice(0, 2).toLowerCase().match(/^[a-z]{2}$/) || ['en'])[0];
const BANGS = {
  g: () => ENGINES.google, d: () => ENGINES.duckduckgo, ddg: () => ENGINES.duckduckgo, b: () => ENGINES.bing, sp: () => ENGINES.startpage, k: () => ENGINES.kagi,
  w: () => engine('Wikipedia', `https://${wikiLang()}.wikipedia.org/w/index.php?search=`), yt: () => engine('YouTube', 'https://www.youtube.com/results?search_query='),
  m: () => engine('Google Maps', 'https://www.google.com/maps/search/'), maps: () => engine('Google Maps', 'https://www.google.com/maps/search/'),
  gh: () => engine('GitHub', 'https://github.com/search?q='), r: () => engine('Reddit', 'https://www.reddit.com/search/?q='),
  i: () => engine('Google Images', 'https://www.google.com/search?tbm=isch&q='), tr: () => engine('Google Translate', 'https://translate.google.com/?sl=auto&op=translate&text='),
};
const BANG_HELP = 'g Google · d DuckDuckGo · b Bing · w Wikipedia · yt YouTube · m Maps · gh GitHub · r Reddit · i Images · tr Translate';
const webEngine = () => ENGINES[(S.layout && S.layout.search) || 'duckduckgo'] || ENGINES.duckduckgo;
/** {engine, q} for "g cats" or "!g cats", else null. */
function webBang(q) {
  const m = q.match(/^!?([a-z]{1,4})\s+(\S.*)$/i);
  return m && BANGS[m[1].toLowerCase()] ? { engine: BANGS[m[1].toLowerCase()](), q: m[2].trim() } : null;
}
/** An address typed in full ("github.com", "nas.local:5000/x", "https://…"): the address to open, else null. */
function looksLikeSite(q) {
  if (/\s/.test(q)) return null;
  if (/^https?:\/\/\S+$/i.test(q)) return q;
  return /^[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}(:\d+)?(\/\S*)?$/i.test(q) || /^[a-z0-9-]+\.local(:\d+)?(\/\S*)?$/i.test(q) ? `https://${q}` : null;
}

// ------------------------------------------------------------------ quick add: a new ioCalendar event from the search box
/* "dinner fri 19:00", "dentist tomorrow 9am", "trip 24 dec", "call mum 14:30-15:00": the words that say when (today,
   tomorrow, a weekday, "in 3 days", a date, a time or two) are taken out, the rest is the title. Nothing said about
   when: not an event. A time without a day: today, or tomorrow when that time has passed. A day without a time: all
   day. The dialog shows what was understood, to change before it is saved. */
const WEEKDAYS = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'];
const MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
const weekdayOf = (w) => { const m = w.match(/^(sun|mon|tue|wed|thu|fri|sat)(day|s|sday|nesday|rs|rsday|urday|t)?$/); return m ? WEEKDAYS.indexOf(m[1]) : -1; };
const monthOf = (w) => { const m = w.match(/^(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?$/); return m ? MONTHS.indexOf(m[1].slice(0, 3)) : -1; };
const ordinal = (w) => { const m = w.match(/^(\d{1,2})(st|nd|rd|th)?,?$/); return m && +m[1] >= 1 && +m[1] <= 31 ? +m[1] : 0; };
/** A time word: "19:00", "19h", "19h30", "7.30", "7pm", "7:30am", "noon", "midnight"; [h, m] or null. pm: the next word. */
function timeOf(w, next) {
  if (w === 'noon') return [12, 0];
  if (w === 'midnight') return [0, 0];
  let m = w.match(/^(\d{1,2})(?:[:.h](\d{2}))?\s*(am|pm|a|p)$/);
  if (!m && /^(am|pm)$/.test(next || '')) { m = w.match(/^(\d{1,2})(?:[:.h](\d{2}))?$/); if (m) m[3] = next; }
  if (m) { let hr = +m[1] % 12; if (m[3][0] === 'p') hr += 12; return +m[1] <= 12 && +(m[2] || 0) < 60 ? [hr, +(m[2] || 0)] : null; }
  m = w.match(/^(\d{1,2})(?::(\d{2})|h(\d{2})?)$/) || w.match(/^(\d{1,2})\.(\d{2})$/);
  if (m) { const hr = +m[1], mi = +(m[2] || m[3] || 0); return hr < 24 && mi < 60 ? [hr, mi] : null; }
  return null;
}
function parseEvent(text, now = new Date()) {
  const words = text.trim().split(/\s+/), lw = words.map((w) => w.toLowerCase());
  const used = new Array(words.length).fill(false);
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const plus = (n) => new Date(today.getFullYear(), today.getMonth(), today.getDate() + n);
  let date = null, start = null, end = null;
  const take = (...ix) => ix.forEach((i) => { used[i] = true; });
  const usOrder = /^en-us/i.test(navigator.language || '');
  for (let i = 0; i < lw.length; i++) {
    const w = lw[i].replace(/,$/, ''), nx = lw[i + 1], nx2 = lw[i + 2];
    if (used[i]) continue;
    if (!date && (w === 'today' || w === 'tonight')) { date = today; take(i); continue; }
    if (!date && /^(tomorrow|tmrw|tmr|tomorow)$/.test(w)) { date = plus(1); take(i); continue; }
    if (!date && w === 'in' && /^\d{1,3}$/.test(nx || '') && /^(day|days|week|weeks)$/.test(nx2 || '')) { date = plus(+nx * (nx2[0] === 'w' ? 7 : 1)); take(i, i + 1, i + 2); continue; }
    if (!date && weekdayOf(w) >= 0) {
      let n = (weekdayOf(w) - today.getDay() + 7) % 7;
      if (i > 0 && /^(next|on)$/.test(lw[i - 1]) && !used[i - 1]) { if (lw[i - 1] === 'next' && n === 0) n = 7; take(i - 1); }
      date = plus(n); take(i); continue;
    }
    let m = w.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!date && m) { date = new Date(+m[1], +m[2] - 1, +m[3]); take(i); continue; }
    m = w.match(/^(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?$/);
    if (!date && m && !(w.includes('.') && !m[3] && timeOf(w))) {  // 7.30 is a time; 24.12 and 24/12 are dates
      const [d, mo] = usOrder ? [+m[2], +m[1]] : [+m[1], +m[2]];
      if (mo >= 1 && mo <= 12 && d >= 1 && d <= 31) {
        let y = m[3] ? (+m[3] < 100 ? 2000 + +m[3] : +m[3]) : today.getFullYear();
        if (!m[3] && new Date(y, mo - 1, d) < today) y += 1;
        date = new Date(y, mo - 1, d); take(i); continue;
      }
    }
    if (!date && monthOf(w) >= 0) {  // "dec 24", "24 dec", "december 24th"
      let d = 0, j = -1;
      if (nx && ordinal(nx)) { d = ordinal(nx); j = i + 1; } else if (i > 0 && !used[i - 1] && ordinal(lw[i - 1])) { d = ordinal(lw[i - 1]); j = i - 1; }
      if (d) {
        const mo = monthOf(w);
        let y = today.getFullYear();
        if (new Date(y, mo, d) < today) y += 1;
        date = new Date(y, mo, d); take(i, j);
        if (i > 0 && lw[i - 1] === 'on' && !used[i - 1]) take(i - 1);
        if (j === i - 1 && i > 1 && lw[i - 2] === 'on' && !used[i - 2]) take(i - 2);
        continue;
      }
    }
    // a time, or a range: "19:00-21:00", "7-9pm", "19:00 - 21:00", "19:00 to 21:00"
    const rng = w.match(/^([^-–]+)[-–]([^-–]+)$/);
    if (!start && rng) {
      const b = timeOf(rng[2], nx), pm = /(pm|p)$/.test(rng[2]) && !/(am|pm|a|p)$/.test(rng[1]);
      const a = timeOf(rng[1] + (pm ? 'pm' : ''), null) || timeOf(rng[1], null);
      if (a && b) { start = a; end = b; take(i); if (/^(am|pm)$/.test(nx || '') && !/(am|pm|a|p)$/.test(rng[2])) take(i + 1); if (i > 0 && /^(at|@|from)$/.test(lw[i - 1])) take(i - 1); continue; }
    }
    const t = timeOf(w, nx) || (i > 0 && /^(at|@)$/.test(lw[i - 1]) && /^\d{1,2}$/.test(w) && +w < 24 ? [+w, 0] : null);
    if (t) {
      if (!start) start = t; else if (!end && i > 0 && /^(to|until|till|-|–)$/.test(lw[i - 1])) { end = t; take(i - 1); } else continue;
      take(i); if (/^(am|pm)$/.test(nx || '') && !/(am|pm|a|p)$/.test(w)) take(i + 1);
      if (i > 0 && /^(at|@|from)$/.test(lw[i - 1]) && !used[i - 1]) take(i - 1);
    }
  }
  if (!date && !start) return null;
  if (!date) date = start && (start[0] * 60 + start[1]) <= now.getHours() * 60 + now.getMinutes() ? plus(1) : today;
  const title = words.filter((_, i) => !used[i]).join(' ').replace(/\s+(on|at|@)$/i, '').trim();
  if (!title) return null;
  return { title: title[0].toUpperCase() + title.slice(1), date, start, end };
}
const pad2 = (n) => String(n).padStart(2, '0');
const ymdOf = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
/** A local date and time as ISO with its offset, as ioCalendar takes it: 2026-11-07T19:00:00+01:00. */
function isoLocal(d) {
  const off = -d.getTimezoneOffset(), sign = off >= 0 ? '+' : '-', a = Math.abs(off);
  return `${ymdOf(d)}T${pad2(d.getHours())}:${pad2(d.getMinutes())}:00${sign}${pad2(Math.floor(a / 60))}:${pad2(a % 60)}`;
}
function eventWhen(ev) {
  const day = (() => { const n = Math.round((ev.date - new Date(new Date().setHours(0, 0, 0, 0))) / 86400000);
    return n === 0 ? 'Today' : n === 1 ? 'Tomorrow' : ev.date.toLocaleDateString([], n < 7 ? { weekday: 'long' } : { weekday: 'short', month: 'short', day: 'numeric' }); })();
  const tm = (t) => new Date(2000, 0, 1, t[0], t[1]).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  return ev.start ? `${day} ${tm(ev.start)}${ev.end ? `–${tm(ev.end)}` : ''}` : `${day}, all day`;
}
async function quickAdd(ev) {
  const cal = S.apps.find((a) => a.key === 'iocalendar');
  let cals = [];
  try { cals = (await api('/api/widgets/iocalendar/calendars')).items || []; } catch (e) { fail(e); return; }
  if (!cals.length) { toast('ioCalendar has no calendar you may add events to'); return; }
  const title = h('input', { class: 't', value: ev.title });
  const date = h('input', { class: 't', type: 'date', value: ymdOf(ev.date) });
  const tm = (t) => (t ? `${pad2(t[0])}:${pad2(t[1])}` : '');
  const from = h('input', { class: 't', type: 'time', value: tm(ev.start) }), to = h('input', { class: 't', type: 'time', value: tm(ev.end) });
  const last = localStorage.getItem('iosuite.quickadd.calendar');
  const which = h('select', { class: 't' }, cals.map((c) => h('option', { value: c.id, selected: String(c.id) === last ? true : null }, c.name)));
  const body = h('div', null, h('div', { class: 'grid' }, fld('Title', title)), h('div', { class: 'qawhen' }, fld('Day', date), fld('From', from), fld('Until', to)),
    h('p', { class: 'muted small' }, 'No time: all day.'), h('div', { class: 'grid' }, fld('Calendar', which)));
  const ok = await dialog('Add to ioCalendar', body, [{ label: 'Cancel', value: false }, { label: 'Add', value: true, primary: true }]);
  if (!ok) return;
  const [y, mo, d] = date.value.split('-').map(Number);
  if (!title.value.trim() || !y) { toast('A title and a day, please'); return; }
  const at = (v) => { const [hh, mm] = v.split(':').map(Number); return new Date(y, mo - 1, d, hh, mm); };
  const json = { title: title.value.trim(), calendarId: which.value, timezone: viewerTz() };
  if (from.value) {
    const s = at(from.value); let e = to.value ? at(to.value) : null;
    if (e && e <= s) e = new Date(+e + 86400000);  // 22:00 until 01:00: the next night
    Object.assign(json, { allDay: false, start: isoLocal(s), ...(e ? { end: isoLocal(e) } : {}) });
  } else Object.assign(json, { allDay: true, start: date.value });
  try {
    await api('/api/widgets/iocalendar/events', { method: 'POST', json });
    localStorage.setItem('iosuite.quickadd.calendar', which.value);
    toast(`Added to ${cal ? cal.name : 'ioCalendar'}: ${json.title}`);
    $('.search .q') && ($('.search .q').value = '');
    S.refreshedAt = 0; liveRefresh(true);  // the tile and This week show it
  } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ is each app up? does one have an update?
/** A dot by each app's name (green: it answers; red: it does not), and "update" when the app says one is waiting. */
async function drawAppStatus(page) {
  let d;
  try { d = await api('/api/apps/status'); } catch { return; }
  if (!page.isConnected) return;
  for (const [key, s] of Object.entries(d.items || {})) {
    const st = page.querySelector(`.app[data-app="${key}"] .st`);
    if (!st) continue;
    st.replaceChildren(h('span', { class: `dot ${s.ok ? 'ok' : 'down'}`, title: s.ok ? `Up${s.version ? ` · v${s.version}` : ''}` : `Not reachable${s.why ? `: ${s.why}` : ''}` }));
    if (s.update) st.append(h('span', { class: 'upd', title: typeof s.update === 'string' ? `v${s.update} is out (now v${s.version || '?'})` : 'An update is waiting' }, 'update'));
  }
}
/** The bookmarks the server could not reach get a red dot and a tooltip. */
async function drawBookmarkStatus(el) {
  let d;
  try { d = await api('/api/bookmarks/status'); } catch { return; }
  if (!el.isConnected) return;
  for (const a of el.querySelectorAll('.bm[data-id]')) {
    const s = d.items[a.dataset.id];
    if (!s) continue;
    a.classList.toggle('down', s.ok === false);
    a.title = s.ok === false ? `${a.getAttribute('href')}\nNot reachable${s.status ? ` (${s.status})` : ''}` : a.getAttribute('href');  // set afresh: the live refresh draws this again and again
  }
}

// ------------------------------------------------------------------ customize the page (per account)
async function customize() {
  const L = S.layout || { hidden: [], order: [], cards: [], strip: null };
  const apps = (S.allApps || []).filter((a) => !a.adminTool);  // the admin tools are in the gear menu, not tiles
  const rank = (a) => { const i = L.order.indexOf(a.key); return i < 0 ? 100 + apps.indexOf(a) : i; };
  const tiles = apps.slice().sort((a, b) => rank(a) - rank(b)).map((a) => ({ key: a.key, on: !L.hidden.includes(a.key), label: [h('img', { src: a.icon, alt: '' }), appName(a.name, a.color)] }));
  const NAMES = { home: 'Home (Home Assistant)', birthdays: 'Birthdays (ioContact)', week: 'This week (ioCalendar)', strip: 'The photo strip (ioPix)', bookmarks: 'Bookmarks' };
  const cards = cardOrder(L).map((k) => ({ key: k, on: !L.hidden.includes(k), label: [NAMES[k]] }));
  // a list of rows with a drag handle and a tick box, for the tiles and for the cards alike (dragSort, as the bookmarks)
  const sortable = (items) => {
    const list = h('div', { class: 'lay' });
    const draw = () => {
      list.replaceChildren(...items.map((t) => h('div', { class: 'layrow', 'data-key': t.key },
        h('button', { class: 'iconbtn grip', title: 'Drag to reorder', 'aria-label': 'Drag to reorder' }, icon('grip', 's')),
        h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: t.on, onchange: (e) => { t.on = e.target.checked; } }), t.label))));
      for (const g of list.querySelectorAll('.grip')) dragSort(g, g.closest('.layrow'), { root: list, lists: () => [list], items: '.layrow', sorting: 'sorting-rows',
        done: () => { const by = Object.fromEntries(items.map((t) => [t.key, t])); items.splice(0, items.length, ...[...list.querySelectorAll('.layrow[data-key]')].map((r) => by[r.dataset.key]).filter(Boolean)); draw(); } });
    };
    draw();
    return list;
  };
  const adminStrip = { rediscover: 'Rediscover', onthisday: 'On this day', off: 'Off' }[S.photoStrip] || 'Rediscover';
  const strip = h('select', { class: 't', onchange: async () => { try { await api('/api/home/settings', { method: 'POST', json: { photoStrip: strip.value } }); toast('Saved'); } catch (e) { fail(e); } } }, [[null, `Default (${adminStrip})`], ['rediscover', 'Rediscover: photos at random'], ['onthisday', 'On this day'], ['off', 'Off']].map(([v, t]) => h('option', { value: v || '', selected: (v || '') === (L.strip || '') ? true : null }, t)));
  const moves = h('select', { class: 't' }, Object.entries(STRIP_MOVES).map(([k, t]) => h('option', { value: k, selected: k === (L.stripMove || STRIP_DEFAULT.move) ? true : null }, t)));
  const everies = h('select', { class: 't' }, STRIP_EVERY.map((s) => h('option', { value: s, selected: s === (L.stripEvery || STRIP_DEFAULT.every) ? true : null }, `Every ${everyText(s)}`)));
  const engines = h('select', { class: 't' }, Object.entries(ENGINES).map(([k, e]) => h('option', { value: k === 'duckduckgo' ? '' : k, selected: (k === 'duckduckgo' ? '' : k) === (L.search || '') ? true : null }, e.name)));
  const body = h('div', null, h('p', { class: 'muted small' }, 'Your own start page, on this account only: untick what you do not need, and put the tiles and the cards in your order. Birthdays and This week share a row when they follow each other.'),
    h('h3', null, 'Tiles'), sortable(tiles), h('h3', null, 'Cards under the tiles'), sortable(cards),
    h('div', { class: 'grid' }, fld('Photo strip', strip), fld('Web search', engines)),
    h('div', { class: 'grid' }, fld('The photo strip changes to', moves), fld('How often', everies)),
    h('p', { class: 'muted small' }, `In the search box, a prefix picks a site: ${BANG_HELP}.`));
  const v = await dialog('Customize the page', body, [{ label: 'Back to the default', value: 'reset' }, { label: 'Cancel', value: null }, { label: 'Save', value: 'save', primary: true }]);
  if (!v) return;
  const json = v === 'reset' ? {} : { hidden: [...tiles, ...cards].filter((t) => !t.on).map((t) => t.key), order: tiles.map((t) => t.key), cards: cards.map((c) => c.key), strip: strip.value || null, search: engines.value || null,
    stripMove: moves.value === STRIP_DEFAULT.move ? null : moves.value, stripEvery: +everies.value === STRIP_DEFAULT.every ? null : +everies.value };
  try { await api('/api/me/layout', { method: 'PUT', json }); toast(v === 'reset' ? 'Back to the default' : 'Saved'); if (route().view === 'home') onRoute(); } catch (e) { fail(e); }
}

/** /api/widgets/<key>?... as JSON, or null when the app is down, not open to this account, or the answer is not JSON. */
async function widget(key, params = {}) {
  try {
    const r = await fetch(`/api/widgets/${key}?${new URLSearchParams({ tz: viewerTz(), ...params })}`, { credentials: 'same-origin' });
    return r.ok ? await r.json() : null;
  } catch { return null; }
}
const inDays = (n) => (n === 0 ? 'Today' : n === 1 ? 'Tomorrow' : `In ${n} days`);

/** The two cards stand no taller than four fifths of one row of tiles above them (the first: on a tablet or phone the
    tiles take two rows or more), and never under 128px; one with more gets a "Show all" in its header. */
function capAgenda(apps, agenda) {
  if (!apps) return;
  const fit = () => {
    const row = apps.firstElementChild ? apps.firstElementChild.offsetHeight : apps.offsetHeight;
    agenda.style.setProperty('--cap', `${Math.max(128, Math.round(row * 0.8))}px`);  // a fifth lower: they use their width
    for (const card of agenda.querySelectorAll('.card')) {
      const rows = card.querySelector('.rows'), btn = card.querySelector('.showall');
      if (!rows || !btn) continue;
      const capped = card.classList.contains('capped'), over = capped ? rows.scrollHeight > rows.clientHeight + 1 : true;
      card.classList.toggle('over', capped && over);  // the fade at the bottom, only when something is cut off
      btn.hidden = capped && !over;
    }
  };
  new ResizeObserver(fit).observe(apps);
  new MutationObserver(fit).observe(agenda, { childList: true, subtree: true });
  fit();
}
const showAll = (card) => h('button', { class: 'lnk showall', hidden: true, onclick: () => { card.classList.toggle('capped'); card.querySelector('.showall').textContent = card.classList.contains('capped') ? 'Show all' : 'Show less'; } }, 'Show all');
/** ioCalendar carries the family's birthdays too (its birthdays calendar): with the Birthdays card on the page, the
    calendar's "X's birthday" / anniversary all-day events are left to that card. */
const isBirthdayEvent = (o) => o.allDay && /\b(birthday|anniversary)\b/i.test(o.title || '');
const withoutBirthdays = (items) => (S.birthdaysCard ? items.filter((o) => !isBirthdayEvent(o)) : items);

/** Birthdays (and the other dates ioContact keeps) in the next 30 days, a line each; a row opens the contact. */
async function drawBirthdays(el, again = false) {
  const app = S.apps.find((a) => a.key === 'iocontact'), d = await widget('iocontact');
  if (!d || !d.items || !el.isConnected) { if (!again) el.remove(); return; }
  const what = (it) => (it.label === 'birthday' ? (it.turns ? String(it.turns) : '') : it.label + (it.turns ? ` · ${it.turns} years` : ''));
  el.replaceChildren(h('div', { class: 'wghead' }, h('span', null, 'Birthdays'), showAll(el), h('a', { class: 'muted', href: app.url, title: app.url }, d.more ? `+${d.more} more · ioContact` : 'ioContact')),
    d.items.length ? h('div', { class: 'rows bdrows' }, d.items.map((it) => h('a', { class: 'bday', href: `${app.url}/#/c/${it.id}`, title: it.turns && it.label === 'birthday' ? `${it.name} turns ${it.turns}` : it.name }, contactFace(it),
      h('span', { class: 'bdname' }, it.name), h('span', { class: 'muted small bdwhat' }, what(it)),
      h('span', { class: `bdwhen${it.in === 0 ? ' today' : ''}` }, inDays(it.in)))))
      : h('div', { class: 'muted small' }, 'No birthdays in the next 30 days'));
}

/** The coming week from ioCalendar, day by day (today lives on the ioCalendar tile); a day opens in ioCalendar. */
async function drawWeek(el, again = false) {
  const app = S.apps.find((a) => a.key === 'iocalendar'), d = await widget('iocalendar', { kind: 'week' });
  if (!d || !d.days || !el.isConnected) { if (!again) el.remove(); return; }
  const head = (date) => { const s = new Date(`${date}T12:00:00`); const days = Math.round((s - new Date().setHours(12, 0, 0, 0)) / 86400000);
    return days === 1 ? 'Tomorrow' : s.toLocaleDateString([], { weekday: 'long' }); };
  const days = d.days.map((day) => ({ ...day, items: withoutBirthdays(day.items) })).filter((day) => day.items.length);
  el.replaceChildren(h('div', { class: 'wghead' }, h('span', null, 'This week'), showAll(el), h('a', { class: 'muted', href: app.url, title: app.url }, d.more ? `+${d.more} more · ioCalendar` : 'ioCalendar')),
    days.length ? h('div', { class: 'rows wkrows' }, days.map((day) => h('div', { class: 'wkday' },
      h('a', { class: 'wkhead', href: `${app.url}/#/day/${day.date}`, title: new Date(`${day.date}T12:00:00`).toLocaleDateString([], { month: 'long', day: 'numeric' }) },
        head(day.date), h('span', { class: 'muted small' }, new Date(`${day.date}T12:00:00`).toLocaleDateString([], { month: 'short', day: 'numeric' }))),
      day.items.map((o) => evRow(o, evTime(o))))))
      : h('div', { class: 'muted small' }, 'Nothing planned in the next 7 days'));
}

/** A card the width of the page with a row of ioPix photos: at random (Rediscover) or from this day in earlier years. */
async function drawStrip(el, kind) {
  const pix = S.apps.find((a) => a.key === 'iopix');
  let d;
  try {
    const r = await fetch(`/api/widgets/iopix?${new URLSearchParams({ tz: viewerTz(), kind, n: 16 })}`, { credentials: 'same-origin' });
    d = r.ok ? await r.json() : null;
  } catch { d = null; }
  if (!d || !d.items || !d.items.length || !el.isConnected) { el.remove(); return; }
  const otd = d.kind === 'onthisday';
  const cap = (it) => (otd ? (it.yearsAgo === 1 ? '1 year ago' : `${it.yearsAgo} years ago`) : (it.year || ''));
  // Shuffle, as ioPix has: a fresh row, picked again at random (On this day is the day's photos: nothing to shuffle)
  const reshuffle = () => { el.classList.add('busy'); drawStrip(el, kind); };
  const shuffle = otd ? null : h('button', { class: 'lnk shuffle', title: 'Another row of photos', onclick: (e) => { e.preventDefault(); reshuffle(); } }, icon('update', 's'), 'Shuffle');
  el.classList.remove('busy');
  const row = h('div', { class: 'row' }, d.items.map((it) => h('a', { class: 'wgph', href: pixPhotoUrl(pix, it.id), title: String(cap(it)) },
    h('img', { src: `/api/widgets/iopix/thumb/${it.id}`, alt: '', loading: 'lazy', onerror: (e) => e.target.parentNode.remove() }),
    cap(it) ? h('span', null, cap(it)) : null)));
  el.replaceChildren(h('div', { class: 'wghead' }, h('span', null, otd ? 'On this day' : 'Rediscover'), shuffle,
    h('a', { class: 'muted', href: pix.url, title: pix.url }, otd && d.count > d.items.length ? `${d.count} photos · ioPix` : 'ioPix')), row);
  autoStrip(el, row, otd ? null : reshuffle);
}

/* The strip changes by itself, as each person picks in Customize (layout stripMove, stripEvery): a fresh row of photos
   (Rediscover; On this day has no other photos, so it turns the page instead), the next screenful of the row, or
   nothing. It waits while the pointer is over it, while it is touched, dragged, wheeled or has the keyboard focus (and a
   little while after), while the tab is hidden or a dialog is open. For reduced motion, the page turns without gliding. */
const STRIP_MOVES = { shuffle: 'A fresh row of photos', page: 'The next photos in the row', off: 'Stays as it is' };
const STRIP_EVERY = [30, 60, 120, 300, 600, 1800];  // seconds
const STRIP_DEFAULT = { move: 'shuffle', every: 60 }, STRIP_REST = 8000;
const everyText = (s) => (s < 60 ? `${s} seconds` : s === 60 ? '1 minute' : `${s / 60} minutes`);
function autoStrip(el, row, reshuffle) {
  if (el.stopAuto) el.stopAuto();
  const L = S.layout || {};
  let move = L.stripMove || STRIP_DEFAULT.move;
  const every = (STRIP_EVERY.includes(L.stripEvery) ? L.stripEvery : STRIP_DEFAULT.every) * 1000;
  if (move === 'shuffle' && !reshuffle) move = 'page';
  if (move === 'off') return;
  const still = () => window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  let hover = false, touchedAt = 0, changedAt = Date.now();
  const busy = () => hover || el.contains(document.activeElement) || Date.now() - touchedAt < STRIP_REST;
  const touched = () => { touchedAt = Date.now(); };
  row.addEventListener('mouseenter', () => { hover = true; });
  row.addEventListener('mouseleave', () => { hover = false; touched(); });
  for (const ev of ['pointerdown', 'touchstart', 'touchmove', 'wheel', 'keydown']) row.addEventListener(ev, touched, { passive: true });
  const tick = () => {
    if (!el.isConnected) { el.stopAuto(); return; }
    if (Date.now() - changedAt < every || document.hidden || busy() || document.querySelector('.dialog-back')) return;
    changedAt = Date.now();
    if (move === 'shuffle') { el.stopAuto(); reshuffle(); return; }
    if (row.scrollWidth <= row.clientWidth + 1) return;
    const atEnd = row.scrollLeft + row.clientWidth >= row.scrollWidth - 2;
    row.scrollTo({ left: atEnd ? 0 : row.scrollLeft + row.clientWidth, behavior: still() ? 'auto' : 'smooth' });
  };
  const t = setInterval(tick, 1000);
  el.stopAuto = () => { clearInterval(t); el.stopAuto = null; };
}

// ------------------------------------------------------------------ what the tiles show (/api/widgets/<app>)
/* Under an app's name, a glimpse of it: ioPix's photos from this day in earlier years (else a few at random),
   ioCalendar's rest of today (else what's next), ioHealth's steps and rings. The server asks each app with the
   viewer's own sign-in; an app that is down or not open to this account leaves its tile as it was. */
const WIDGETS = { iopix: drawPixWidget, iocalendar: drawCalendarWidget, iotask: drawTasksWidget, iohealth: drawHealthWidget };
/** ioPix opens one photo in its lightbox at #/photos?p=<id>. */
const pixPhotoUrl = (pix, id) => `${pix.url}/#/photos?p=${id}`;
const viewerTz = () => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch { return ''; } };

function drawWidgets(page, again = false) {
  const tz = viewerTz();
  for (const tile of page.querySelectorAll('.app[data-app]')) {
    const draw = WIDGETS[tile.dataset.app], box = tile.querySelector('.more');
    if (!draw || !box) continue;
    const why = (text) => { if (box.isConnected) box.replaceChildren(h('div', { class: 'wg' }, h('div', { class: 'muted small wgwhy' }, text))); };
    fetch(`/api/widgets/${tile.dataset.app}?tz=${encodeURIComponent(tz)}`, { credentials: 'same-origin' })
      .then(async (r) => { if (r.ok) return r.json(); let detail = ''; try { detail = (await r.json()).detail || ''; } catch { /* no body */ } throw new Error(detail || `${r.status}`); })
      .then((d) => { if (!box.isConnected) return; const kids = draw(d); if (kids) box.replaceChildren(h('div', { class: 'wg' }, kids)); else why(EMPTY[tile.dataset.app] || 'Nothing to show'); })
      .catch((e) => { if (!again || !box.querySelector('.wg .wghead')) why(e.message); });  // the app is down, or not open to this account: the tile says so (a refresh that fails keeps what it showed)
  }
}

const EMPTY = { iopix: 'No photos yet', iocalendar: 'Nothing planned', iotask: 'Nothing due today', iohealth: 'No steps, rings or sleep for today yet' };
const wgHead = (t, extra) => h('div', { class: 'wghead' }, h('span', null, t), extra ? h('span', { class: 'muted' }, extra) : null);

function drawPixWidget(d) {
  if (!d.items || !d.items.length) return null;
  const otd = d.kind === 'onthisday';
  const cap = (it) => (otd ? (it.yearsAgo === 1 ? '1 year ago' : `${it.yearsAgo} years ago`) : (it.year || ''));
  // four small squares in a row: the year fits under each, "14 years ago" is the tooltip
  return [wgHead(otd ? 'On this day' : 'Rediscover', otd && d.count > d.items.length ? `${d.count} photos` : null),
    h('div', { class: 'wgpix' }, d.items.slice(0, 4).map((it) => h('span', { class: 'wgph', title: String(cap(it)), role: 'link', tabindex: '0',
      onclick: (e) => { e.preventDefault(); e.stopPropagation(); location.href = pixPhotoUrl(S.apps.find((a) => a.key === 'iopix'), it.id); },
      onkeydown: (e) => { if (e.key === 'Enter') e.target.click(); } },
      h('img', { src: `/api/widgets/iopix/thumb/${it.id}`, alt: '', loading: 'lazy', onerror: (e) => e.target.parentNode.remove() }),
      it.year ? h('span', null, it.year) : null)))];
}

function evTime(o) {
  if (o.allDay) return 'All day';
  const s = new Date(o.start);
  return isNaN(s) ? '' : s.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}
function evDay(o) {
  const s = new Date(o.allDay ? `${o.start}T12:00:00` : o.start);
  if (isNaN(s)) return '';
  const t = new Date(); t.setHours(0, 0, 0, 0);
  const days = Math.round((new Date(s.getFullYear(), s.getMonth(), s.getDate()) - t) / 86400000);
  return days === 1 ? 'Tomorrow' : s.toLocaleDateString([], days < 7 ? { weekday: 'long' } : { weekday: 'short', month: 'short', day: 'numeric' });
}
const evRow = (o, when) => h('div', { class: 'wgev', title: [o.title, o.location].filter(Boolean).join(' · ') },
  h('span', { class: 'dot', style: { background: o.color || 'var(--fg2)' } }), h('span', { class: 'wgwhen muted' }, when), h('span', { class: 'wgtitle' }, o.title));

function drawCalendarWidget(d) {
  const today = withoutBirthdays(d.today || []);
  if (today.length) {
    return [wgHead('Today', d.more ? `+${d.more} more` : null), today.map((o) => evRow(o, evTime(o)))];
  }
  if (d.next) return [wgHead('Next', evDay(d.next)), evRow(d.next, evTime(d.next))];
  return [wgHead('Today'), h('div', { class: 'muted small' }, 'Nothing planned')];
}

/** ioTask: what is due today (and what is overdue, first), in each list's colour. */
function drawTasksWidget(d) {
  const today = d.today || [];
  if (!today.length) return [wgHead('Today'), h('div', { class: 'muted small' }, 'Nothing due')];
  const when = (t) => { if (t.late) return 'Late'; if (t.allDay || !t.due) return ''; const s = new Date(t.due); return isNaN(s) ? '' : s.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }); };
  return [wgHead('Due today', [d.overdue ? `${d.overdue} overdue` : null, d.more ? `+${d.more} more` : null].filter(Boolean).join(' · ') || null),
    today.map((t) => evRow(t, when(t)))];
}

/** Three rings, outside in: move, exercise, stand; each full at its goal (and past it, a second lap is not drawn). */
function rings(r) {
  const ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 64 64'); svg.setAttribute('class', 'wgrings');
  [['move', 27, 'var(--ring-move)'], ['exercise', 19, 'var(--ring-exercise)'], ['stand', 11, 'var(--ring-stand)']].forEach(([k, rad, col]) => {
    const goal = r[`${k}Goal`], v = r[k], frac = goal > 0 && v != null ? Math.min(1, v / goal) : 0, len = 2 * Math.PI * rad;
    for (const [op, dash] of [[0.22, null], [1, frac]]) {
      if (dash === 0) continue;
      const c = document.createElementNS(ns, 'circle');
      c.setAttribute('cx', 32); c.setAttribute('cy', 32); c.setAttribute('r', rad); c.setAttribute('fill', 'none');
      c.setAttribute('stroke', col); c.setAttribute('stroke-width', 7); c.setAttribute('stroke-opacity', op);
      if (dash != null) { c.setAttribute('stroke-linecap', 'round'); c.setAttribute('stroke-dasharray', `${dash * len} ${len}`); c.setAttribute('transform', 'rotate(-90 32 32)'); }
      svg.append(c);
    }
  });
  return svg;
}
/** Seven bars, a day each, the last one today: the week's steps at a glance. */
function sparkline(week) {
  const ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg'), W = 7, G = 3, H = 22;
  svg.setAttribute('viewBox', `0 0 ${week.length * (W + G) - G} ${H}`); svg.setAttribute('class', 'wgspark');
  const top = Math.max(1, ...week.map((x) => x.steps || 0));
  week.forEach((x, i) => {
    const r = document.createElementNS(ns, 'rect'), hgt = x.steps ? Math.max(2, (x.steps / top) * H) : 2;
    r.setAttribute('x', i * (W + G)); r.setAttribute('y', H - hgt); r.setAttribute('width', W); r.setAttribute('height', hgt); r.setAttribute('rx', 1.5);
    r.setAttribute('class', i === week.length - 1 ? 'today' : x.steps ? '' : 'none');
    const t = document.createElementNS(ns, 'title');
    t.textContent = `${new Date(`${x.date}T12:00:00`).toLocaleDateString([], { weekday: 'short' })}: ${x.steps == null ? 'no data' : `${x.steps.toLocaleString()} steps`}`;
    r.append(t); svg.append(r);
  });
  return svg;
}
const hm = (min) => (min >= 60 ? `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, '0')}` : `${min} min`);
function drawHealthWidget(d) {
  if (d.steps == null && !d.rings && !d.sleep) return null;
  const r = d.rings, n = (v) => (v == null ? '–' : Math.round(v).toLocaleString());
  const line = (k, label, unit) => (r && r[`${k}Goal`] ? h('div', { class: 'wgring', title: `${label}: ${n(r[k])} of ${n(r[`${k}Goal`])} ${unit}` },
    h('span', { class: 'dot', style: { background: `var(--ring-${k})` } }), label, h('span', { class: 'muted' }, `${n(r[k])}/${n(r[`${k}Goal`])}`)) : null);
  const week = d.week && d.week.filter((x) => x.steps != null).length > 1 ? d.week : null;
  const when = (iso) => { const t = new Date(iso); return isNaN(t) ? '' : t.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }); };
  const total = week ? week.reduce((a, x) => a + (x.steps || 0), 0) : 0;
  // the head: "Today", and on its right the steps with the week's bars; under it the rings with their three lines
  // beside them, and the night's sleep as a fourth line (kept short so the row of tiles stays low)
  const steps = d.steps != null ? h('span', { class: 'wgsteps' }, h('span', null, h('b', null, n(d.steps)), ' steps'),
    week ? h('span', { class: 'wgtrend', title: `${n(total)} steps in the last 7 days` }, sparkline(week)) : null) : null;
  const sleep = d.sleep ? h('div', { class: 'wgsleep', title: d.sleep.start && d.sleep.end ? `Asleep ${when(d.sleep.start)} – ${when(d.sleep.end)}${d.sleep.inBed ? `, ${hm(d.sleep.inBed)} in bed` : ''}` : '' },
    h('span', { class: 'dot', style: { background: 'var(--sleep)' } }), 'Sleep', h('span', { class: 'muted' }, hm(d.sleep.asleep), h('span', { class: 'wgunit' }, ' asleep'))) : null;
  return [h('div', { class: 'wghead' }, h('span', null, 'Today'), steps),
    r ? h('div', { class: 'wghealth' }, rings(r), h('div', null, line('move', 'Move', 'kcal'), line('exercise', 'Exercise', 'min'), line('stand', 'Stand', 'h'), sleep)) : sleep];
}

/** The weather widget: the conditions now (with "Rain from 15:00" when the next hours bring some), and the days
    ahead. A click on the conditions opens the next 12 hours. Hidden until an admin sets it up. again: a refresh, which
    keeps what it shows when the server does not answer. */
// ------------------------------------------------------------------ Home Assistant: the Home card, the alerts
/* The entities an admin picked (Settings › Home Assistant), each with its state; a tap on one the admin lets the page
   control toggles it (a light, a switch, a lock, a cover, a scene…). Above the tiles, a line for what needs attention
   (a leak, smoke, a low battery, a door that should be closed). The server asks Home Assistant; the browser never does.
   The card redraws every minute on its own, on top of the page's live refresh. */
const HA_ICONS = { light: 'bulb', switch: 'power', input_boolean: 'power', fan: 'fan', lock: 'lock', cover: 'blind', scene: 'play', script: 'play', automation: 'play', button: 'play', input_button: 'play',
  climate: 'thermo', media_player: 'play', person: 'person', device_tracker: 'person', vacuum: 'home', weather: 'cloud', camera: 'wall', siren: 'warn' };
const HA_CLASS_ICONS = { door: 'door', garage_door: 'door', window: 'door', opening: 'door', temperature: 'thermo', humidity: 'cloud', battery: 'battery', power: 'bolt', energy: 'bolt', voltage: 'bolt', current: 'bolt',
  motion: 'person', occupancy: 'person', presence: 'person', moisture: 'warn', smoke: 'warn', gas: 'warn', carbon_monoxide: 'warn', problem: 'warn', safety: 'warn', lock: 'lock', illuminance: 'bulb' };
function haIcon(t) {
  if (t.domain === 'lock') return t.on ? 'unlock' : 'lock';
  return HA_CLASS_ICONS[t.class] || HA_ICONS[t.domain] || (t.domain === 'binary_sensor' ? 'check' : 'home');
}
/** Home Assistant's own page for an entity: its device (where a thermostat's settings are), or its history when it
    belongs to no device. */
const haLink = (t) => `${(S.ha && S.ha.url) || ''}${t.device ? `/config/devices/device/${encodeURIComponent(t.device)}` : `/history?entity_id=${encodeURIComponent(t.id)}`}`;
/** toggle | on | off, by way of the server; the entity's new state, or null (a toast says why). */
async function haAct(id, action) {
  try { return await api(`/api/ha/${encodeURIComponent(id)}/${action}`, { method: 'POST' }); } catch (e) { fail(e); return null; }
}
const haTile = (t) => {
  const kids = [icon(haIcon(t), 's'), h('span', { class: 'hbody' }, h('span', { class: 'hname' }, t.name), h('span', { class: 'hstate small' }, t.text || t.state))];
  if (!t.control) return h('a', { class: `hatile${t.on ? ' on' : ''}${t.state === 'unavailable' || t.state === 'missing' ? ' off' : ''}`, href: haLink(t), title: `${t.id} · ${t.device ? 'its device' : 'its history'} in Home Assistant`, target: '_blank', rel: 'noreferrer' }, kids);
  if (HA_POPUPS[t.domain]) {  // a thermostat, a cover: a popup with its controls instead of a toggle
    const b = h('button', { class: `hatile ctl${t.on ? ' on' : ''}`, title: `${t.id} · tap for its controls` }, kids);
    b.onclick = () => haPopup(t, (r) => { if (b.isConnected) b.replaceWith(haTile({ ...t, ...r, control: t.control })); });
    return b;
  }
  const b = h('button', { class: `hatile ctl${t.on ? ' on' : ''}`, title: `${t.id} · tap to ${{ scene: 'run', script: 'run', button: 'press', input_button: 'press', automation: 'run' }[t.domain] || (t.on ? 'turn off' : 'turn on')}`, 'aria-pressed': t.on == null ? null : String(!!t.on) }, kids);
  b.onclick = async () => {
    b.classList.add('busy');
    const card = b.closest('.homecard');
    const r = await haAct(t.id, 'toggle');
    if (r && b.isConnected) b.replaceWith(haTile({ ...t, ...r, control: t.control })); else b.classList.remove('busy');
    // a device that reports back late (Zigbee, Z-Wave, a cloud bulb): the card asks again in a few seconds
    if (card) setTimeout(() => { if (card.isConnected && !document.hidden) drawHomeCard(card, document.querySelector('.alerts'), true); }, 4000);
  };
  return b;
};
/* The popups: a thermostat (target temperature, mode, fan, preset) and a cover (open, stop, close, a position). Each
   change goes to /api/ha/<entity>/set and the popup redraws from the answer; `onChange` gets it too, for the tile. */
const HA_POPUPS = { climate: true, cover: true };
const haWord = (m) => ({ heat_cool: 'Heat · cool', fan_only: 'Fan', not_home: 'Away' })[m] || (m ? m.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase()) : '');
async function haSet(id, body) {
  try { return await api(`/api/ha/${encodeURIComponent(id)}/set`, { method: 'POST', json: body }); } catch (e) { fail(e); return null; }
}
function haPopup(t, onChange) {
  const body = h('div', { class: 'hapop' });
  let cur = t, busy = false;
  const send = async (payload) => {
    if (busy) return;
    busy = true; body.classList.add('busy');
    const r = await haSet(cur.id, payload);
    busy = false; body.classList.remove('busy');
    if (r && r.id) { cur = { ...cur, ...r }; onChange(r); draw(); }
  };
  const seg = (options, value, pick, label) => h('div', { class: 'seg', role: 'group', 'aria-label': label }, options.map((o) => h('button', { class: o === value ? 'on' : '', onclick: () => pick(o) }, label(o))));
  const draw = () => {
    const kids = [];
    if (cur.domain === 'climate' && cur.climate) {
      const c = cur.climate, step = c.step || 0.5, dec = step < 1 ? 1 : 0;
      const fmt = (v) => (v == null ? '–' : `${v.toFixed(dec)}${c.unit || '°'}`);
      const off = c.mode === 'off';
      const targetRow = (label, key, value, low, high) => h('div', { class: 'hatarget' }, label ? h('span', { class: 'muted small' }, label) : null,
        h('button', { class: 'iconbtn round', title: 'Lower', disabled: off || value == null || value - step < c.min ? true : null, onclick: () => send(key === 'temperature' ? { temperature: +(value - step).toFixed(2) } : { low: key === 'low' ? +(value - step).toFixed(2) : low, high: key === 'high' ? +(value - step).toFixed(2) : high }) }, '−'),
        h('span', { class: 'hatemp' }, fmt(value)),
        h('button', { class: 'iconbtn round', title: 'Raise', disabled: off || value == null || value + step > c.max ? true : null, onclick: () => send(key === 'temperature' ? { temperature: +(value + step).toFixed(2) } : { low: key === 'low' ? +(value + step).toFixed(2) : low, high: key === 'high' ? +(value + step).toFixed(2) : high }) }, '+'));
      kids.push(h('div', { class: 'hanow' }, h('span', { class: 'hacur' }, fmt(c.current)), h('span', { class: 'muted small' }, [c.action ? haWord(c.action) : haWord(c.mode), c.humidity != null ? `${c.humidity}% humidity` : null].filter(Boolean).join(' · '))));
      if (c.low != null && c.high != null && c.target == null) kids.push(targetRow('Low', 'low', c.low, c.low, c.high), targetRow('High', 'high', c.high, c.low, c.high));
      else kids.push(targetRow('', 'temperature', c.target));
      if (c.modes.length) kids.push(h('h3', null, 'Mode'), seg(c.modes, c.mode, (m) => send({ mode: m }), haWord));
      if (c.fans.length) kids.push(h('h3', null, 'Fan'), seg(c.fans, c.fan, (m) => send({ fan: m }), haWord));
      if (c.presets.length) kids.push(h('h3', null, 'Preset'), seg(c.presets, c.preset, (m) => send({ preset: m }), haWord));
    } else if (cur.domain === 'cover' && cur.cover) {
      const c = cur.cover;
      kids.push(h('div', { class: 'hanow' }, h('span', { class: 'hacur' }, cur.text || cur.state), c.position != null ? h('span', { class: 'muted small' }, `${c.position}% open`) : null),
        h('div', { class: 'habtns' },
          c.canOpen ? h('button', { class: 'pillbtn', disabled: !c.moving && cur.state === 'open' ? true : null, onclick: () => send({ action: 'open' }) }, icon('up', 's'), 'Open') : null,
          c.canStop ? h('button', { class: 'pillbtn noic', onclick: () => send({ action: 'stop' }) }, 'Stop') : null,
          c.canClose ? h('button', { class: 'pillbtn', disabled: !c.moving && cur.state === 'closed' ? true : null, onclick: () => send({ action: 'close' }) }, icon('down', 's'), 'Close') : null));
      if (c.canPosition) {
        const range = h('input', { type: 'range', min: 0, max: 100, step: 5, value: c.position == null ? 50 : c.position, 'aria-label': 'Position', onchange: (e) => send({ position: +e.target.value }) });
        kids.push(h('h3', null, 'Position'), h('div', { class: 'harange' }, h('span', { class: 'muted small' }, 'Closed'), range, h('span', { class: 'muted small' }, 'Open')));
      }
    } else kids.push(h('p', { class: 'muted' }, cur.text || cur.state));
    kids.push(h('p', { class: 'small' }, h('a', { class: 'lnk', href: haLink(cur), target: '_blank', rel: 'noreferrer' }, 'More in Home Assistant')));
    body.replaceChildren(...kids);
  };
  draw();
  // the thing moves while the popup is open (a cover closing, a device reporting back): the stream brings it, else a poll
  const take = (d) => {
    const fresh = (d.items || []).find((x) => x.id === cur.id);
    if (fresh && body.isConnected && !busy && JSON.stringify({ a: fresh.state, b: fresh.climate, c: fresh.cover }) !== JSON.stringify({ a: cur.state, b: cur.climate, c: cur.cover })) { cur = { ...cur, ...fresh }; onChange(fresh); draw(); }
  };
  const off = haSubscribe(take);
  const timer = S.haStream ? 0 : setInterval(async () => {
    if (!body.isConnected) { clearInterval(timer); return; }
    if (busy || document.hidden) return;
    let d; try { d = await api('/api/ha'); } catch { return; }
    take(d);
  }, 3000);
  dialog(cur.name, body, [{ label: 'Done', value: true, primary: true }]).then(() => { off(); if (timer) clearInterval(timer); });
}

/* Changes from Home Assistant as they happen: one EventSource per view on /api/ha/events (the server holds the
   websocket to Home Assistant and sends the Home card anew when something in it changes); whoever draws from it
   (the card, the wall's sensors, an open popup) subscribes here. The browser reconnects it by itself. */
const haListeners = new Set();
function haSubscribe(fn) {
  haListeners.add(fn);
  if (!S.haStream && window.EventSource) {
    S.haStream = new EventSource('/api/ha/events');
    S.haStream.onmessage = (e) => { let d; try { d = JSON.parse(e.data); } catch { return; } S.ha = d.enabled ? d : false; for (const f of [...haListeners]) { try { f(d); } catch { /* one listener's problem */ } } };
  }
  return () => { haListeners.delete(fn); };
}
function haStreamStop() {
  haListeners.clear();
  if (S.haStream) { S.haStream.close(); S.haStream = null; }
}
async function drawHomeCard(el, alertsEl, again = false) {
  if (!el.haLive) {  // the first draw: from here on the stream redraws the card as Home Assistant changes
    el.haLive = true;
    const off = haSubscribe((d) => { if (!el.isConnected) { off(); return; } renderHomeCard(el, alertsEl, d); });
  }
  let d;
  try { d = await api('/api/ha'); } catch (e) { if (!again) { el.hidden = false; el.replaceChildren(h('div', { class: 'muted small' }, e.message)); } return; }
  if (!el.isConnected) return;
  renderHomeCard(el, alertsEl, d);
}
function renderHomeCard(el, alertsEl, d) {
  S.ha = d.enabled ? d : false;
  if (!d.enabled) { el.hidden = S.user.role !== 'admin'; if (!el.hidden) el.replaceChildren(wgHead('Home'), h('a', { class: 'lnk small', href: '#/settings/ha' }, 'Add Home Assistant')); return; }
  el.hidden = false;
  const title = wgHead(d.name || 'Home', null);
  title.append(h('a', { class: 'muted', href: d.url, title: d.url, target: '_blank', rel: 'noreferrer' }, 'Home Assistant'));
  if (d.error) { el.replaceChildren(title, h('div', { class: 'muted small' }, d.error)); return; }
  el.replaceChildren(title,
    d.items.length ? h('div', { class: 'hatiles' }, d.items.map(haTile))
      : h('div', { class: 'muted small' }, S.user.role === 'admin' ? ['No entities picked yet: ', h('a', { class: 'lnk', href: '#/settings/ha' }, 'choose some')] : 'No entities picked yet.'));
  // what needs attention, above the tiles
  if (alertsEl) {
    const al = d.alerts || [];
    alertsEl.hidden = !al.length;
    alertsEl.replaceChildren(...al.map((a) => h('a', { class: 'alert', href: haLink(a), target: '_blank', rel: 'noreferrer', title: a.id }, icon('warn', 's'), h('b', null, a.name), ' ', a.text)));
  }
  // without the stream (an old browser), its own minute: a light switched elsewhere shows here soon
  clearTimeout(el.haTimer);
  if (!S.haStream) el.haTimer = setTimeout(() => { if (el.isConnected && !document.hidden) drawHomeCard(el, alertsEl, true); }, 60 * 1000);
}

async function drawWeather(el, again = false) {
  let w;
  try { w = await api('/api/weather'); } catch (e) { if (!again) el.replaceChildren(h('div', { class: 'muted small' }, e.message)); return; }
  if (!el.isConnected) return;
  if (!w.enabled) { el.replaceChildren(S.user.role === 'admin' ? h('a', { class: 'lnk small', href: '#/settings/weather' }, 'Add the weather') : null); return; }
  if (!w.current) { el.replaceChildren(h('div', { class: 'wxerr' }, wxIcon(7, 'big'), h('div', null, h('div', null, 'No weather right now'), h('div', { class: 'muted small' }, w.error || '')))); return; }
  const c = w.current, imp = w.units === 'imperial', u = imp ? 'imperial' : 'metric';
  const day = (d) => new Date(`${d.date}T12:00:00`).toLocaleDateString([], { weekday: 'short' });
  const t = (v) => fmtTemp(imp ? degF(v) : v);  // the forecasts come in °C
  const rain = rainNote(w);
  const hours = nextHours(w);
  let pop = null;
  const closePop = () => { if (pop) { pop.remove(); pop = null; document.removeEventListener('click', outside); } };
  const outside = (e) => { if (pop && !pop.contains(e.target) && !now.contains(e.target)) closePop(); };
  const now = h('button', { class: 'wxnow', 'aria-expanded': 'false',
    title: [w.location, c.feels[u] != null ? `feels ${fmtTemp(c.feels[u])}` : null, c.humidity != null ? `${c.humidity}% humidity` : null,
      c.wind[u] != null ? `wind ${Math.round(c.wind[u])} ${imp ? 'mph' : 'km/h'}` : null].filter(Boolean).join(' · '),
    onclick: () => {
      if (pop) return closePop();
      pop = h('div', { class: 'wxpop' }, h('div', { class: 'wghead' }, h('span', null, 'Next hours'), w.location ? h('span', { class: 'muted' }, w.location) : null),
        hours.length ? hourRow(w, hours) : h('div', { class: 'muted small' }, 'No hourly forecast from AccuWeather'),
        c.link ? h('a', { class: 'lnk small', href: c.link, target: '_blank', rel: 'noreferrer' }, 'More at AccuWeather') : null);
      el.append(pop);
      setTimeout(() => document.addEventListener('click', outside), 0);
    } },
    wxIcon(c.icon, 'big'),
    h('div', null, h('div', { class: 'wxtemp' }, fmtTemp(c.temp[u])), h('div', { class: 'wxtext small' }, c.text),
      rain ? h('div', { class: 'wxrain small' }, rain) : null));
  el.replaceChildren(now,
    w.forecast && w.forecast.days && w.forecast.days.length ? h('div', { class: 'wxdays' }, w.forecast.days.map((d) =>
      h('div', { class: 'wxday', title: `${d.text || ''}${d.rain != null ? ` · ${d.rain}% chance of rain` : ''}` }, h('span', { class: 'muted small' }, day(d)), wxIcon(d.icon), h('span', { class: 'small wxhi' }, t(d.max)), h('span', { class: 'muted small' }, t(d.min))))) : null,
    w.stale ? h('span', { class: 'muted small', title: w.error || 'AccuWeather did not answer' }, 'older') : h('span'));
}
/** The hours still ahead in AccuWeather's 12-hour forecast (the server's copy can be up to 90 minutes old). */
const nextHours = (w) => (w.hourly || []).filter((x) => new Date(x.t) > Date.now() - 30 * 60 * 1000);
const hourLabel = (x) => new Date(x.t).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
const isWet = (x) => x.wet || (x.rain != null && x.rain >= 50);
/** "Rain from 15:00", "Rain until 16:00", or nothing when the next hours stay dry. */
function rainNote(w) {
  const hs = nextHours(w);
  if (!hs.length) return '';
  const what = (x) => ({ Rain: 'Rain', Snow: 'Snow', Ice: 'Ice', Mixed: 'Sleet' })[x.kind] || 'Rain';
  if (isWet(hs[0])) {
    const dry = hs.find((x) => !isWet(x));
    return dry ? `${what(hs[0])} until ${hourLabel(dry)}` : `${what(hs[0])} for hours`;
  }
  const wet = hs.find(isWet);
  return wet ? `${what(wet)} from ${hourLabel(wet)}` : '';
}
/** The next hours in a row: the hour, the sky, the temperature, and the chance of rain when there is one. */
function hourRow(w, hours) {
  const imp = w.units === 'imperial', t = (v) => fmtTemp(imp ? degF(v) : v);
  return h('div', { class: 'wxhours' }, hours.map((x) => h('div', { class: `wxhour${isWet(x) ? ' wet' : ''}`, title: `${x.text || ''}${x.rain != null ? ` · ${x.rain}% chance of rain` : ''}` },
    h('span', { class: 'muted small' }, new Date(x.t).toLocaleTimeString([], { hour: 'numeric' })), wxIcon(x.icon), h('span', { class: 'small' }, t(x.temp)),
    h('span', { class: 'small wxpct' }, x.rain ? `${x.rain}%` : ''))));
}

/** The bookmarks, as homepage lays them out: a column per group, a row per link with its abbreviation (or icon), name and host. */
async function drawBookmarks(el) {
  let gs;
  try { gs = (await api('/api/bookmarks')).groups; } catch (e) { el.replaceChildren(h('div', { class: 'muted small' }, e.message)); return; }
  if (!el.isConnected) return;
  const canEdit = ['editor', 'admin'].includes(S.user.role);
  S.bookmarks = gs.flatMap((g) => g.links);  // the search box looks through them
  if (!gs.length) { el.replaceChildren(h('a', { class: 'lnk small', href: '#/bookmarks' }, canEdit ? 'Add bookmarks, or pick some for this page' : 'All bookmarks')); return; }
  const groups = gs.filter((g) => g.links.length || canEdit).map((g) => h('div', { class: 'bmgroup' }, h('h2', null, g.name),
    g.links.map((l) => {
      const src = bmIcon(l);
      return h('a', { class: 'bm', href: l.href, title: l.href, target: '_blank', rel: 'noreferrer', 'data-id': l.id },
        h('span', { class: 'bmic' }, src ? h('img', { src, alt: '', onerror: (e) => { e.target.replaceWith(l.abbr); } }) : l.abbr),
        h('span', { class: 'bmname' }, l.name), h('span', { class: 'bmdesc muted small' }, l.description));
    }),
    canEdit && !g.links.length ? h('a', { class: 'lnk small', href: '#/bookmarks' }, 'Nothing shown: add or pick links') : null));
  packBookmarks(el, groups);
  drawBookmarkStatus(el);
  bmIconsLater(el, S.bookmarks, async () => (await api('/api/bookmarks')).groups.flatMap((g) => g.links));
}

/** The groups packed into columns: each goes, in order, under the shortest column so far, so a short group fills the
    room under a short column instead of starting a new row under the longest one. Packed again when the width changes
    (the number of columns follows it: as many 250 px columns as fit, one on a phone). */
function packBookmarks(el, groups) {
  const GAP = 20, MIN = 250;
  let cols = 0;
  const pack = () => {
    const width = el.clientWidth || el.getBoundingClientRect().width;
    const n = Math.max(1, Math.min(groups.length, Math.floor((width + GAP) / (MIN + GAP))));
    if (n === cols) return;
    cols = n;
    const heights = new Array(n).fill(0), columns = Array.from({ length: n }, () => h('div', { class: 'bmcol' }));
    for (const g of groups) {
      const i = heights.indexOf(Math.min(...heights));
      columns[i].append(g);
      heights[i] += 36 + g.querySelectorAll('.bm, .lnk').length * 48 + 20;  // the heading, the rows, the gap under
    }
    el.style.setProperty('--bmcols', n);
    el.replaceChildren(...columns, h('a', { class: 'pillbtn bmall', href: '#/bookmarks', title: 'Every bookmark, what is on this page, and sync with browsers' }, icon('link', 's'), 'All bookmarks'));
  };
  pack();
  new ResizeObserver(pack).observe(el);
}

// ------------------------------------------------------------------ the wall display (#/wall)
/* For a tablet on the wall or a TV: the full screen, ioPix photos one after another behind a big clock, the date, the
   weather and its next hours, and what is planned today and in the coming days (and birthdays). It keeps the screen
   on where the browser allows it, refreshes itself (liveRefresh), and goes back to the start page with Escape or the
   button that shows on a touch. #/wall can be the tablet's home address. */
function enterWall() {
  location.hash = '#/wall';
  const el = document.documentElement;
  if (el.requestFullscreen && !document.fullscreenElement) el.requestFullscreen().catch(() => { /* not allowed here: the page still fills the window */ });
}
async function showWall(page) {
  const got = await api('/api/apps');
  S.allApps = got.items; S.layout = got.layout || { hidden: [], order: [], cards: [], strip: null };
  S.apps = got.items.filter((a) => !a.adminTool);
  const has = (k) => S.apps.some((a) => a.key === k);
  page.className = 'wallpage';
  const photos = h('div', { class: 'wallphotos' });
  const clock = h('div', { class: 'wallclock' }), date = h('div', { class: 'walldate' });
  const wx = h('div', { class: 'wallwx' }), hours = h('div', { class: 'wallhours' }), sensors = h('div', { class: 'wallsensors' });
  const agenda = h('div', { class: 'wallagenda' }), caption = h('div', { class: 'wallcap' });
  const bar = h('div', { class: 'wallbar' },
    h('button', { class: 'iconbtn', title: 'Full screen', onclick: () => { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen && document.documentElement.requestFullscreen().catch(() => {}); } }, icon('fullscreen')),
    h('a', { class: 'iconbtn', title: 'Back to the start page (Esc)', href: '#/' }, icon('close')));
  page.append(photos, h('div', { class: 'wallshade' }),
    h('div', { class: 'walltop' }, h('div', null, clock, date), wx),
    h('div', { class: 'wallbottom' }, agenda, h('div', { class: 'wallright' }, sensors, hours, caption)), bar);
  // the controls show on a touch or a move of the mouse, and fade after a few seconds
  let hideT;
  const wake = () => { bar.classList.add('on'); clearTimeout(hideT); hideT = setTimeout(() => bar.classList.remove('on'), 4000); };
  page.addEventListener('pointermove', wake); page.addEventListener('pointerdown', wake);
  const tick = () => {
    const n = new Date();
    clock.textContent = n.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    date.textContent = n.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' });
  };
  tick();
  const timers = [setInterval(tick, 1000)];
  // keep the screen on (Screen Wake Lock: Chrome, Safari 16.4+), asked again when the tab comes back
  let lock = null;
  const keepOn = async () => { try { if (navigator.wakeLock && !document.hidden) lock = await navigator.wakeLock.request('screen'); } catch { lock = null; } };
  const onVis = () => { if (!document.hidden) keepOn(); };
  document.addEventListener('visibilitychange', onVis); keepOn();
  const onKey = (e) => { if (e.key === 'Escape' && !document.fullscreenElement) location.hash = '#/'; };
  document.addEventListener('keydown', onKey);
  S.wallStop = () => { timers.forEach(clearInterval); clearTimeout(hideT); document.removeEventListener('visibilitychange', onVis); document.removeEventListener('keydown', onKey); if (lock) lock.release().catch(() => {}); if (document.fullscreenElement) document.exitFullscreen().catch(() => {}); };
  if (has('iopix')) timers.push(wallSlideshow(photos, caption, got.layout && got.layout.strip ? got.layout.strip : got.photoStrip));
  const draw = () => { wallWeather(wx, hours); wallAgenda(agenda, has); wallSensors(sensors); };
  draw();
  haSubscribe((d) => renderWallSensors(sensors, d));  // the house changes faster than the weather: as it happens
  timers.push(setInterval(() => { if (!document.hidden && !S.haStream) wallSensors(sensors); }, 60 * 1000));
  S.shownDay = dayKey(); S.refreshedAt = Date.now(); S.refresh = draw;
}
/** The Home Assistant entities ticked "wall" (Settings › Home Assistant), name and state each; what needs attention first. */
async function wallSensors(el) {
  let d;
  try { d = await api('/api/ha'); } catch { return; }
  renderWallSensors(el, d);
}
function renderWallSensors(el, d) {
  if (!el.isConnected) return;
  if (!d.enabled) { el.replaceChildren(); return; }
  const on = new Set(d.wall || []);
  const items = (d.items || []).filter((t) => on.has(t.id));
  el.replaceChildren(...(d.alerts || []).slice(0, 3).map((a) => h('div', { class: 'wallsensor alert' }, icon('warn', 's'), h('span', { class: 'hname' }, a.name), h('span', { class: 'hstate' }, a.text))),
    ...items.map((t) => h('div', { class: `wallsensor${t.on ? ' on' : ''}` }, icon(haIcon(t), 's'), h('span', { class: 'hname' }, t.name), h('span', { class: 'hstate' }, t.text || t.state))));
}
/** A photo every 20 seconds, fading into the next; landscape ones first on a landscape screen. A fresh batch when the
    row is used up. Returns the interval, for showWall to stop. */
function wallSlideshow(el, caption, kind) {
  let queue = [], busy = false;
  const fill = async () => {
    const d = await widget('iopix', { kind: kind === 'onthisday' ? 'onthisday' : 'rediscover', n: 24 });
    let items = (d && d.items) || [];
    const wide = innerWidth >= innerHeight;
    items = items.slice().sort((a, b) => (a.w && a.h ? ((a.w >= a.h) === wide ? 0 : 1) : 0.5) - (b.w && b.h ? ((b.w >= b.h) === wide ? 0 : 1) : 0.5));
    queue = items.map((it) => ({ ...it, otd: d.kind === 'onthisday' }));
  };
  const next = async () => {
    if (busy || !el.isConnected || document.hidden) return;
    busy = true;
    try {
      if (!queue.length) await fill();
      const it = queue.shift();
      if (!it) return;
      const img = new Image();
      img.alt = ''; img.className = 'wallimg';
      img.src = `/api/widgets/iopix/preview/${it.id}`;
      await img.decode().catch(() => null);
      if (!img.naturalWidth || !el.isConnected) return;
      const old = [...el.children];
      el.append(img);
      requestAnimationFrame(() => img.classList.add('on'));
      setTimeout(() => old.forEach((o) => o.remove()), 2000);
      caption.textContent = it.otd ? (it.yearsAgo === 1 ? '1 year ago today' : `${it.yearsAgo} years ago today`) : (it.year ? String(it.year) : '');
    } finally { busy = false; }
  };
  next();
  return setInterval(next, 20000);
}
async function wallWeather(el, hoursEl) {
  let w;
  try { w = await api('/api/weather'); } catch { return; }
  if (!el.isConnected || !w.enabled || !w.current) { if (w && !w.enabled) { el.replaceChildren(); hoursEl.replaceChildren(); } return; }
  const c = w.current, imp = w.units === 'imperial', u = imp ? 'imperial' : 'metric', t = (v) => fmtTemp(imp ? degF(v) : v);
  const rain = rainNote(w);
  el.replaceChildren(h('div', { class: 'wallnow' }, wxIcon(c.icon, 'big'), h('div', null, h('div', { class: 'walltemp' }, fmtTemp(c.temp[u])), h('div', null, c.text), rain ? h('div', { class: 'wxrain' }, rain) : null)),
    w.forecast && w.forecast.days ? h('div', { class: 'wxdays' }, w.forecast.days.slice(1, 5).map((d) => h('div', { class: 'wxday' },
      h('span', null, new Date(`${d.date}T12:00:00`).toLocaleDateString([], { weekday: 'short' })), wxIcon(d.icon), h('span', null, `${t(d.max)} ${t(d.min)}`)))) : null);
  const hs = nextHours(w).slice(0, 8);
  hoursEl.replaceChildren(hs.length ? hourRow(w, hs) : '');
}
/** Today (what is left of it) and the coming days, a line per event, with today's and tomorrow's birthdays on top. */
async function wallAgenda(el, has) {
  const [today, week, bdays] = await Promise.all([has('iocalendar') ? widget('iocalendar', { n: 6 }) : null, has('iocalendar') ? widget('iocalendar', { kind: 'week' }) : null,
    has('iocontact') ? widget('iocontact') : null]);
  if (!el.isConnected) return;
  S.birthdaysCard = !!(bdays && bdays.items);
  const kids = [];
  const soon = ((bdays && bdays.items) || []).filter((b) => b.in <= 1);
  if (soon.length) kids.push(h('div', { class: 'wallsec' }, soon.map((b) => h('div', { class: 'wallev' }, h('span', { class: 'when' }, inDays(b.in)), h('span', null, `🎂 ${b.name}${b.label === 'birthday' ? (b.turns ? ` turns ${b.turns}` : '') : ` · ${b.label}`}`)))));
  if (today) {
    const items = withoutBirthdays(today.today || []);
    kids.push(h('div', { class: 'wallsec' }, h('div', { class: 'wallhead' }, 'Today'),
      items.length ? items.map((o) => h('div', { class: 'wallev' }, h('span', { class: 'dot', style: { background: o.color || 'var(--fg2)' } }), h('span', { class: 'when' }, evTime(o)), h('span', null, o.title)))
        : h('div', { class: 'wallev muted' }, today.next ? `Nothing more today · next: ${today.next.title}, ${evDay(today.next)}` : 'Nothing more today'),
      today.more ? h('div', { class: 'wallev muted' }, `+${today.more} more`) : null));
  }
  if (week && week.days) {
    const days = week.days.map((d) => ({ ...d, items: withoutBirthdays(d.items) })).filter((d) => d.items.length).slice(0, 3);
    for (const d of days) {
      const s = new Date(`${d.date}T12:00:00`), n = Math.round((s - new Date().setHours(12, 0, 0, 0)) / 86400000);
      kids.push(h('div', { class: 'wallsec' }, h('div', { class: 'wallhead' }, n === 1 ? 'Tomorrow' : s.toLocaleDateString([], { weekday: 'long' })),
        d.items.slice(0, 4).map((o) => h('div', { class: 'wallev' }, h('span', { class: 'dot', style: { background: o.color || 'var(--fg2)' } }), h('span', { class: 'when' }, evTime(o)), h('span', null, o.title)))));
    }
  }
  el.replaceChildren(...kids);
}

// ------------------------------------------------------------------ settings
async function showSettings(page, r) {
  const adm = S.user.role === 'admin';
  const tabs = [['account', 'Account'], ['display', 'Display'], ...(adm ? [['weather', 'Home page'], ['ha', 'Home Assistant']] : []), ...(adm ? [['server', 'Server']] : []),
    ...(S.user.suiteAdmin ? [['security', 'Security'], ['global', 'Global settings']] : [])];
  if (!tabs.some(([k]) => k === r.tab)) r.tab = 'account';
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Settings')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/settings/${k}`; } }, l))));
  const body = h('div'); page.append(body);
  await ({ account: setAccount, display: setDisplay, apps: setHome, weather: setHome, ha: setHomeAssistant, server: setServer, security: setSuite, global: setSuite }[r.tab] || setAccount)(body, r);
}
const fld = (l, e) => h('label', { class: 'field' }, h('span', null, l), e);

/** Settings › Account and Display: iosuite-shared's panels, the same in every io app. */
const accountUi = () => import(new URL('api/auth/ui.js', document.baseURI).href);
async function setAccount(el) {
  await (await accountUi()).mountAccount(el, { toast, syncOnly: 'Bookmark sync only', onSaved: (u) => { Object.assign(S.user, u); drawUser(); } });
}
async function setDisplay(el) {
  const ui = await accountUi();
  el.append(ui.box('theme', 'Appearance', ui.themeRow(S.settings?.theme || 'system', setTheme)));
}
async function setHome(el) {
  const got = await api('/api/home/settings');
  const strip = h('select', { class: 't', onchange: async () => { try { await api('/api/home/settings', { method: 'POST', json: { photoStrip: strip.value } }); toast('Saved'); } catch (e) { fail(e); } } }, [['rediscover', 'Rediscover: photos at random'], ['onthisday', 'On this day (at random when there are none)'], ['off', 'Off']].map(([v, t]) => h('option', { value: v, selected: v === got.photoStrip ? true : null }, t)));
  el.append(h('div', { class: 'box' }, h('h2', null, icon('apps'), 'Home page'),
    h('p', { class: 'muted' }, 'The default for everyone. Each person can change it in Customize.'),
    h('div', { class: 'grid' }, fld('Photo strip under the tiles (ioPix)', strip))));
  await setWeather(el);
}

async function setWeather(el) {
  const s = await api('/api/weather/settings');
  const key = h('input', { class: 't', type: 'password', placeholder: s.hasKey ? '(kept)' : 'API key from developer.accuweather.com', disabled: s.keyFromEnv ? true : null, autocomplete: 'off', onchange: async () => { if (key.value.trim() && await save({ key: key.value.trim() })) { key.value = ''; key.placeholder = '(kept)'; } } });
  const units = h('select', { class: 't', style: 'width:auto', onchange: () => save({ units: units.value }) }, [['metric', '°C, km/h'], ['imperial', '°F, mph']].map(([v, l]) => h('option', { value: v, selected: v === s.units ? true : null }, l)));
  const q = h('input', { class: 't', placeholder: 'City, e.g. Boston or Antwerp', disabled: s.locationFromEnv ? true : null });
  const found = h('div', { class: 'found' });
  const where = h('p', null, s.locationKey ? `Place: ${s.locationName || s.locationKey}${s.locationFromEnv ? ' (ACCUWEATHER_LOCATION in the environment)' : ''}` : 'No place chosen yet.');
  const save = async (body) => { try { const r = await api('/api/weather/settings', { method: 'POST', json: body }); toast('Saved'); return r; } catch (e) { fail(e); return null; } };
  const search = async () => {
    found.replaceChildren(h('span', { class: 'muted small' }, 'Looking…'));
    try {
      const r = await api(`/api/weather/search?${new URLSearchParams({ q: q.value.trim(), ...(key.value.trim() ? { key: key.value.trim() } : {}) })}`);
      found.replaceChildren(...(r.items.length ? r.items.map((p) => h('button', { class: 'pillbtn noic', onclick: async () => {
        const name = [p.name, p.region, p.country].filter(Boolean).join(', ');
        if (await save({ ...(key.value.trim() ? { key: key.value.trim() } : {}), locationKey: p.key, locationName: name })) { where.textContent = `Place: ${name}`; key.value = ''; key.placeholder = '(kept)'; found.replaceChildren(); }
      } }, [p.name, p.region, p.country].filter(Boolean).join(', '))) : [h('span', { class: 'muted small' }, 'Nothing found')]));
    } catch (e) { found.replaceChildren(h('span', { class: 'err' }, e.message)); }
  };
  q.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); search(); } };
  el.append(h('div', { class: 'box' }, h('h2', null, icon('cloud'), 'Weather'),
    h('p', { class: 'muted' }, 'From AccuWeather. A free key from developer.accuweather.com is enough.'),
    h('div', { class: 'grid' }, fld('API key', key), fld('Units', units)),
    s.keyFromEnv ? h('p', { class: 'muted small' }, 'ACCUWEATHER_API_KEY in the environment sets the key.') : null,
    s.hasKey && !s.keyFromEnv ? h('p', null, h('button', { class: 'pillbtn noic', onclick: async () => { if (await confirmDialog('Remove the key', 'Remove the AccuWeather key? The widget disappears from the page.', 'Remove', true)) { await save({ key: '' }); onRoute(); } } }, 'Remove the key')) : null),
  h('div', { class: 'box' }, h('h2', null, icon('cloud'), 'Place'), where,
    s.locationFromEnv ? null : [h('div', { class: 'multi' }, q, h('button', { class: 'pillbtn noic', onclick: search }, 'Find')), found,
      h('p', { class: 'muted small' }, 'Type a city and pick it from the list.')]));
}

/** Settings › Home Assistant: the address and token, a test, and the entities the page shows, each with its name, whether
    a tap may switch it, whether it goes on the wall, and the state that needs attention. */
async function setHomeAssistant(el) {
  const s = await api('/api/ha/settings');
  const saveConn = async () => { if (await save(conn())) { if (tok.value.trim()) s.hasToken = true; tok.value = ''; tok.placeholder = s.hasToken ? '(kept)' : tok.placeholder; if (s.hasToken || s.tokenFromEnv) test(); } };
  const url = h('input', { class: 't', type: 'url', value: s.url || '', placeholder: 'http://homeassistant.local:8123', disabled: s.urlFromEnv ? true : null, autocomplete: 'off', onchange: () => saveConn() });
  const tok = h('input', { class: 't', type: 'password', placeholder: s.hasToken ? '(kept)' : 'Long-lived access token', disabled: s.tokenFromEnv ? true : null, autocomplete: 'off', onchange: () => saveConn() });
  const result = h('span', { class: 'muted small' });
  const conn = () => ({ ...(s.urlFromEnv ? {} : { url: url.value.trim() }), ...(tok.value.trim() ? { token: tok.value.trim() } : {}) });
  const save = async (body) => { try { const r = await api('/api/ha/settings', { method: 'POST', json: body }); toast('Saved'); return r; } catch (e) { fail(e); return null; } };
  const test = async () => {
    result.className = 'muted small'; result.textContent = 'Asking…';
    try { const r = await api('/api/ha/test', { method: 'POST', json: conn() }); result.className = 'small ok'; result.textContent = `${r.name} · Home Assistant ${r.version || ''} · ${r.entities} entities`; } catch (e) { result.className = 'small err'; result.textContent = e.message; }
  };
  // the entities picked, as rows
  let items = (s.entities || []).map((e) => ({ ...e }));
  const list = h('div', { class: 'halist' });
  const persist = async () => { const r = await save({ entities: items }); if (r) { items = r.entities.map((e) => ({ ...e })); drawList(); } };
  const drawList = () => { list.replaceChildren(h('div', { class: 'harow head' }, h('span'), h('span', null, 'Entity'), h('span', null, 'Shown as'), h('span', { title: 'A tap on the card switches it (editors and admins)' }, 'Control'), h('span', { title: 'On the wall display' }, 'Wall'), h('span', { title: 'Needs attention when its state is this (on, open, unlocked…); empty: never' }, 'Alert when'), h('span')),
    ...items.map((e, i) => h('div', { class: 'harow', 'data-id': e.id },
      h('button', { class: 'iconbtn grip', title: 'Drag to reorder', 'aria-label': 'Drag to reorder' }, icon('grip', 's')),
      h('span', { class: 'haid', title: e.id }, e.id),
      h('input', { class: 't', value: e.name || '', placeholder: 'Its own name', onchange: (ev) => { e.name = ev.target.value.trim(); persist(); } }),
      h('input', { type: 'checkbox', checked: e.control, onchange: (ev) => { e.control = ev.target.checked; persist(); } }),
      h('input', { type: 'checkbox', checked: e.wall, onchange: (ev) => { e.wall = ev.target.checked; persist(); } }),
      h('input', { class: 't', value: e.alert || '', placeholder: '–', onchange: (ev) => { e.alert = ev.target.value.trim().toLowerCase(); persist(); } }),
      h('span', { class: 'bmtools' }, h('button', { class: 'iconbtn', title: 'Remove', onclick: () => { items.splice(i, 1); persist(); } }, icon('close', 's'))))),
    ...(items.length ? [] : [h('p', { class: 'muted small' }, 'Nothing picked yet: find entities below and add them.')]));
    // reorder by dragging the handle (or ArrowUp / ArrowDown on it), as in the Bookmarks page
    for (const g of list.querySelectorAll('.grip')) dragSort(g, g.closest('.harow'), { root: list, lists: () => [list], items: '.harow:not(.head)', sorting: 'sorting-rows',
      done: () => { const by = Object.fromEntries(items.map((e) => [e.id, e])); items = [...list.querySelectorAll('.harow[data-id]')].map((r) => by[r.dataset.id]).filter(Boolean); persist(); } });
  };
  drawList();
  // the picker: a search among every entity Home Assistant has
  const q = h('input', { class: 't', placeholder: 'Find an entity: kitchen, garage, temperature…' });
  const found = h('div', { class: 'found' });
  const find = async () => {
    if (!q.value.trim()) { found.replaceChildren(); return; }
    found.replaceChildren(h('span', { class: 'muted small' }, 'Looking…'));
    try {
      const r = await api(`/api/ha/search?${new URLSearchParams({ q: q.value.trim(), n: 30 })}`);
      const have = new Set(items.map((e) => e.id));
      found.replaceChildren(...(r.items.length ? r.items.map((t) => h('button', { class: 'pillbtn', disabled: have.has(t.id) ? true : null, title: t.id, onclick: () => { items.push({ id: t.id, name: '', control: !!HA_ICONS[t.domain] && !['climate', 'media_player', 'person', 'device_tracker', 'weather', 'camera'].includes(t.domain), wall: false, alert: '' }); persist(); find(); } },
        icon(haIcon(t), 's'), `${t.name}`, h('span', { class: 'muted small' }, ` ${t.text || t.state}`))) : [h('span', { class: 'muted small' }, 'Nothing found')]));
    } catch (e) { found.replaceChildren(h('span', { class: 'err' }, e.message)); }
  };
  q.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); find(); } };
  const builtin = h('input', { type: 'checkbox', checked: s.builtinAlerts, onchange: async (e) => { await save({ builtinAlerts: e.target.checked }); } });
  el.append(h('div', { class: 'box' }, h('h2', null, icon('home'), 'Home Assistant'),
    h('p', { class: 'muted' }, 'For the Home card, the wall display and the search box. Make a token in Home Assistant under your profile › Security › Long-lived access tokens.'),
    h('div', { class: 'grid' }, fld('Address', url), fld('Access token', tok)),
    s.urlFromEnv || s.tokenFromEnv ? h('p', { class: 'muted small' }, `${[s.urlFromEnv ? 'HA_URL' : null, s.tokenFromEnv ? 'HA_TOKEN' : null].filter(Boolean).join(' and ')} in the environment set${s.urlFromEnv && s.tokenFromEnv ? '' : 's'} this.`) : null,
    h('p', { class: 'multi' }, h('button', { class: 'pillbtn noic', onclick: test }, 'Test'),
      s.hasToken && !s.tokenFromEnv ? h('button', { class: 'pillbtn noic', onclick: async () => { if (await confirmDialog('Remove the token', 'Remove the Home Assistant token? The Home card disappears from the page.', 'Remove', true)) { await save({ token: '' }); onRoute(); } } }, 'Remove the token') : null,
      result)),
  h('div', { class: 'box' }, h('h2', null, icon('tune'), 'On the page'),
    h('p', { class: 'muted' }, 'The Home card, in this order. Control: a tap switches it, for editors and admins (a viewer sees the state). Wall: on the wall display too. Alert when: the state to point out (on, open, unlocked…).'),
    list,
    h('div', { class: 'multi' }, q, h('button', { class: 'pillbtn noic', onclick: find }, 'Find')), found,
    h('label', { class: 'check' }, builtin, 'Also point out leak, smoke, gas and CO sensors, problems and batteries at 15% or under')));
}

/* The Bookmarks page (#/bookmarks, from the start page and the gear menu): the whole tree (folders in folders, as a
   browser keeps them), what of it is on the start page (the house on a folder or on a single link), the addresses a
   sync app needs, and files in and out. Everyone signed in sees it; editors and admins change it. */
async function showBookmarks(page) {
  const canEdit = ['editor', 'admin'].includes(S.user.role);
  const body = h('div');
  // the search box: as you type, the links that match (name, address, description, folder), wherever they are
  const q = h('input', { class: 't bmq', type: 'search', placeholder: 'Search the bookmarks', autocomplete: 'off', autocapitalize: 'off', spellcheck: 'false', enterkeyhint: 'search', 'aria-label': 'Search the bookmarks' });
  q.addEventListener('input', () => body.bmPaint && body.bmPaint());
  q.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && q.value) { e.stopPropagation(); q.value = ''; body.bmPaint && body.bmPaint(); }
    if (e.key === 'Enter') { const a = body.querySelector('.bmrow a.bmname'); if (a) { e.preventDefault(); a.click(); } }  // the first match
  });
  body.bmQuery = () => q.value.trim();
  page.append(h('div', { class: 'pagehead bmpagehead' },
    BM_APP ? null : h('a', { class: 'iconbtn', href: '#/', title: 'Back to the start page', 'aria-label': 'Back to the start page' }, icon('left')),
    h('h1', null, 'Bookmarks'),
    canEdit ? h('button', { class: 'pillbtn primary bmaddtop', onclick: () => body.bmAdd && body.bmAdd() }, icon('add', 's'), 'Link') : null,
    h('div', { class: 'bmsearch' }, icon('search', 's'), q)));
  page.append(body);
  await setBookmarks(body);
  // back to the app (from a tab it opened, or the home screen): the tree as it is now, as the start page does
  S.refresh = () => body.bmDraw && body.bmDraw();
}
/** Running as an app from the home screen (or installed), without the browser around it. */
const standalone = () => navigator.standalone === true || matchMedia('(display-mode: standalone)').matches;
const bmOpen = new Set();  // the folders unfolded, kept while the page is open
async function setBookmarks(el) {
  let tree = null, sync = null;
  const draw = async () => {
    [tree, sync] = await Promise.all([api('/api/bookmarks/tree'), api('/api/bookmarks/sync')]);
    if (!el.isConnected) return;
    paint();
    const mine = el.bmDrawn = {};  // a later draw makes the wait for icons of this one moot
    bmIconsLater(el, bmFlat(tree.items), async () => (el.bmDrawn === mine ? bmFlat((await api('/api/bookmarks/tree')).items) : []));
  };
  // the search box redraws from the tree in hand; changes fetch it again (draw)
  const paint = () => {
    if (!tree || !el.isConnected) return;
    const canEdit = ['editor', 'admin'].includes(S.user.role);
    const query = el.bmQuery ? fold(el.bmQuery()) : '';
    const call = async (path, opts, msg) => { try { await api(path, opts); if (msg) toast(msg); } catch (e) { fail(e); } await draw(); };
    // every folder, for the "Folder" choice of a link: the top level, then each with its path
    const folders = [{ id: 0, label: 'Top level' }];
    const where = new Map();  // a link's id: its folder and the folder's path, for the search results
    const walk = (items, path, parent) => {
      for (const x of items) {
        if (x.type === 'folder') { folders.push({ id: x.id, label: [...path, x.name].join(' › ') }); walk(x.items, [...path, x.name], x); }
        else where.set(x.id, { f: parent, path: path.join(' › ') });
      }
    };
    walk(tree.items, [], null);
    const few = tree.count <= 60;  // a small tree shows unfolded; a browser's whole menu starts folded
    const isOpen = (f) => bmOpen.has(f.id) || (few && !bmOpen.has(-f.id));
    const linkForm = (gid, l) => {
      const name = h('input', { class: 't', value: l ? l.name : '', placeholder: 'Name' }), href = h('input', { class: 't', value: l ? l.href : '', placeholder: 'https://…' });
      const abbr = h('input', { class: 't', value: l ? l.abbr : '', placeholder: 'Two letters (from the name when empty)', maxlength: 4 });
      const desc = h('input', { class: 't', value: l ? l.customDescription : '', placeholder: 'Line under the name (the host name when empty)' });
      const ic = h('input', { class: 't', value: l ? l.icon : '', placeholder: 'The site\'s own icon when empty; or an image address, or a dashboard-icons name (github.png)' });
      const grp = h('select', { class: 't' }, folders.map((x) => h('option', { value: x.id, selected: x.id === gid ? true : null }, x.label)));
      // an icon of your own (an SVG, or a PNG), kept in the database: it wins over the icon field
      const file = h('input', { type: 'file', accept: '.svg,.png,image/svg+xml,image/png', class: 't' });
      const drop = h('input', { type: 'checkbox' });
      const upload = h('div', { class: 'upload' }, l && l.iconUrl ? h('img', { src: l.iconUrl, alt: '', class: 'bmprev' }) : null, file,
        l && l.iconUrl ? h('label', { class: 'small' }, drop, ' Remove the uploaded icon') : null);
      Object.assign(href, { type: 'url', inputMode: 'url', autocapitalize: 'off', spellcheck: false }); href.setAttribute('autocorrect', 'off');
      name.placeholder = 'Name (the site\'s address when empty)';
      // what a phone rarely needs folds away: open when the link already has some of it
      const more = h('details', { class: 'bmmoreform', open: l && (l.customDescription || l.icon || l.iconUrl) ? true : null },
        h('summary', { class: 'muted small' }, 'Abbreviation, description and icon'),
        h('div', { class: 'grid' }, fld('Abbreviation', abbr), fld('Description', desc), fld('Icon', ic), h('div', { class: 'field' }, h('span', null, 'Upload an icon (SVG is best, or PNG)'), upload)));
      const hostOf = (u) => { try { return new URL(/^[a-z][a-z0-9+.-]*:/i.test(u) ? u : `https://${u}`).hostname.replace(/^www\./, ''); } catch { return u; } };
      return { body: h('div', null, h('div', { class: 'grid' }, fld('Address', href), fld('Name', name), fld('Folder', grp)), more),
        value: () => ({ name: name.value.trim() || hostOf(href.value.trim()), href: href.value.trim(), abbr: abbr.value, description: desc.value, icon: ic.value, groupId: +grp.value }), file: () => file.files[0], drop: () => drop.checked };
    };
    const editLink = async (gid, l) => {
      const f = linkForm(gid, l);
      const v = await dialog(l ? 'Change the link' : 'New link', f.body, [{ label: 'Cancel', value: null }, { label: l ? 'Save' : 'Add', value: () => ({ link: f.value(), file: f.file(), drop: f.drop() }), primary: true }]);
      if (!v) return;
      try {
        const saved = await api(l ? `/api/bookmarks/links/${l.id}` : `/api/bookmarks/groups/${v.link.groupId}/links`, { method: l ? 'PATCH' : 'POST', json: v.link });
        if (v.file) await api(`/api/bookmarks/links/${saved.id}/icon`, { method: 'PUT', body: v.file, headers: { 'Content-Type': v.file.type || 'application/octet-stream' } });
        else if (v.drop) await api(`/api/bookmarks/links/${saved.id}/icon`, { method: 'DELETE' });
        toast('Saved');
      } catch (e) { fail(e); }
      await draw();
    };
    const newFolder = async (parentId) => {
      const i = h('input', { class: 't', placeholder: 'Name, e.g. Developer' });
      const st = h('input', { type: 'checkbox', checked: true });
      const v = await dialog('New folder', h('div', null, fld('Name', i), h('label', { class: 'check' }, st, 'Show it on the start page')), [{ label: 'Cancel', value: null }, { label: 'Add', value: () => ({ name: i.value, start: st.checked }), primary: true }]);
      if (v && v.name.trim()) { bmOpen.add(parentId); await call('/api/bookmarks/groups', { method: 'POST', json: { ...v, parentId } }, 'Folder made'); }
    };
    const grip = (title, kind) => (canEdit ? h('button', { class: 'iconbtn grip', title, 'aria-label': title, 'data-kind': kind }, icon('grip', 's')) : null);
    // the house: lit when the folder (its links, as a group) or the link is on the start page
    const house = (on, title, click, disabled) => h('button', { class: `iconbtn bmstart${on ? ' on' : ''}`, title, 'aria-label': title, 'aria-pressed': on ? 'true' : 'false', disabled: disabled ? true : null, onclick: click }, icon('home', 's'));
    // a link's and a folder's tools: buttons in the row, or (on a phone) behind one ⋯ button, as a list to tap
    const linkActions = (l, f) => [
      { label: 'Open', icon: 'web', run: () => window.open(l.href, '_blank', 'noreferrer'), hidden: !l.linkable },
      { label: l.onStart ? 'Take it off the start page' : 'Show it on the start page', icon: 'home', disabled: !l.linkable, run: () => {
        const want = !l.onStart;  // as its folder when that already says so, else this link's own choice
        call(`/api/bookmarks/links/${l.id}`, { method: 'PATCH', json: { start: want === !!(f && f.start) ? null : want } });
      } },
      { label: 'Change', icon: 'edit', run: () => editLink(f ? f.id : 0, l) },
      { label: 'Copy the address', icon: 'copy', run: async () => { try { await navigator.clipboard.writeText(l.href); toast('Copied'); } catch { toast(l.href); } } },
      { label: 'Delete', icon: 'delete', danger: true, run: async () => { if (await confirmDialog('Delete the link', `Delete "${l.name || l.href}"? Browsers that sync lose it too.`, 'Delete', true)) call(`/api/bookmarks/links/${l.id}`, { method: 'DELETE' }, 'Deleted'); } },
    ];
    const moreBtn = (title, actions) => h('button', { class: 'iconbtn bmmore', title: 'More', 'aria-label': `More: ${title}`, onclick: () => sheet(title, actions) }, icon('more', 's'));
    const linkRow = (l, f, path) => h('div', { class: `bmrow${l.onStart ? '' : ' off'}`, 'data-id': l.id }, path === undefined ? grip('Drag to move the link', 'link') : null,
      h('span', { class: 'bmic' }, bmIcon(l) ? h('img', { src: bmIcon(l), alt: '', onerror: (e) => { e.target.replaceWith(l.abbr); } }) : l.abbr), l.linkable ? h('a', { class: 'bmname', href: l.href, target: '_blank', rel: 'noreferrer', title: l.href }, l.name || l.href) : h('span', { class: 'bmname', title: l.href }, l.name || l.href),
      h('span', { class: 'muted small bmdesc' }, path === undefined ? l.description : path || 'Top level'),
      !canEdit ? null : h('span', { class: 'bmtools' },
        house(l.onStart, !l.linkable ? 'Only web addresses can go on the start page' : l.onStart ? 'On the start page: click to take it off' : 'Not on the start page: click to show it', linkActions(l, f)[1].run, !l.linkable),
        h('button', { class: 'iconbtn', title: 'Change', onclick: () => editLink(f ? f.id : 0, l) }, icon('edit', 's')),
        h('button', { class: 'iconbtn', title: 'Delete', onclick: linkActions(l, f)[4].run }, icon('delete', 's'))),
      canEdit ? moreBtn(l.name || l.href, linkActions(l, f)) : null);
    const count = (f) => f.items.reduce((n, x) => n + (x.type === 'folder' ? count(x) : 1), 0);
    const folderActions = (f, n) => [
      { label: f.start ? 'Take it off the start page' : 'Show it on the start page', icon: 'home', run: () => call(`/api/bookmarks/groups/${f.id}`, { method: 'PATCH', json: { start: !f.start } }) },
      { label: 'Add a link', icon: 'add', run: () => { bmOpen.add(f.id); bmOpen.delete(-f.id); editLink(f.id, null); } },
      { label: 'Add a folder inside', icon: 'folder', run: () => { bmOpen.delete(-f.id); newFolder(f.id); } },
      { label: 'Rename', icon: 'edit', run: async () => { const i = h('input', { class: 't', value: f.name }); const v = await dialog('Rename the folder', i, [{ label: 'Cancel', value: null }, { label: 'Save', value: () => i.value, primary: true }]); if (v) call(`/api/bookmarks/groups/${f.id}`, { method: 'PATCH', json: { name: v } }, 'Saved'); } },
      { label: 'Delete the folder', icon: 'delete', danger: true, run: async () => { if (await confirmDialog('Delete the folder', `Delete "${f.name}" and the ${n} link(s) in it? Browsers that sync lose them too.`, 'Delete', true)) call(`/api/bookmarks/groups/${f.id}`, { method: 'DELETE' }, 'Deleted'); } },
    ];
    const folderBox = (f) => {
      const open = isOpen(f), n = count(f), acts = folderActions(f, n);
      return h('div', { class: `bmedit${open ? '' : ' shut'}`, 'data-id': f.id },
        h('div', { class: 'bmhead' }, grip('Drag to move the folder', 'group'),
          h('button', { class: 'bmfold', 'aria-expanded': open ? 'true' : 'false', title: open ? 'Fold' : 'Unfold', onclick: () => { if (open) { bmOpen.delete(f.id); bmOpen.add(-f.id); } else { bmOpen.add(f.id); bmOpen.delete(-f.id); } paint(); } },
            icon(open ? 'down' : 'right', 's'), icon('folder', 's'), h('b', null, f.name || '(no name)'), h('span', { class: 'muted small' }, `${n}`)),
          !canEdit ? null : h('span', { class: 'bmtools' },
            house(f.start, f.start ? 'On the start page, as a group with its links: click to take it off' : 'Not on the start page: click to show it as a group', acts[0].run),
            ...acts.slice(1).map((a) => h('button', { class: 'iconbtn', title: a.label, onclick: a.run }, icon(a.icon, 's')))),
          canEdit ? moreBtn(f.name || 'Folder', acts) : null),
        open ? level(f.items, f) : null);
    };
    // a folder's links, then the folders inside it (each list takes what is dragged into it)
    const level = (items, f) => h('div', { class: 'bmlevel' },
      h('div', { class: 'bmlinks', 'data-gid': f ? f.id : 0 }, items.filter((x) => x.type === 'bookmark').map((l) => linkRow(l, f))),
      h('div', { class: 'bmsubs', 'data-gid': f ? f.id : 0 }, items.filter((x) => x.type === 'folder').map(folderBox)));
    const copy = (text) => h('button', { class: 'iconbtn', title: 'Copy', onclick: async () => { try { await navigator.clipboard.writeText(text); toast('Copied'); } catch { toast(text); } } }, icon('copy', 's'));
    const addr = (label, text) => h('div', { class: 'bmaddr' }, h('span', { class: 'muted small' }, label), h('code', null, text), copy(text));
    const file = h('input', { type: 'file', accept: '.html,.htm,.xbel,.xml,text/html', class: 't' });
    const importFile = async () => {
      const f = file.files[0];
      if (!f) { toast('Choose a bookmarks file first'); return; }
      try { const r = await api('/api/bookmarks/import', { method: 'POST', json: { file: await f.text() } }); toast(`Added ${r.links} link(s) in ${r.groups} folder(s)`); } catch (e) { fail(e); }
      await draw();
    };
    const results = () => {
      const found = bmFlat(tree.items).filter((l) => fold(`${l.name} ${l.href} ${l.description || ''} ${where.get(l.id)?.path || ''}`).includes(query));
      return found.length ? h('div', { class: 'bmresults' }, found.slice(0, 200).map((l) => linkRow(l, where.get(l.id)?.f || null, where.get(l.id)?.path || '')))
        : h('p', { class: 'muted' }, 'No bookmark matches.');
    };
    el.bmAdd = () => editLink(0, null);
    el.replaceChildren(
      h('div', { class: 'box bmtree' }, h('h2', null, icon('link'), query ? 'Found' : 'Bookmarks'),
        h('p', { class: 'muted' }, canEdit ? 'Every bookmark of the family, in folders as a browser keeps them. The house says what is on the start page: on a folder it shows the folder as a group with its links, on a link it shows or hides just that one. Everything here syncs to the browsers, on the start page or not. Drag a folder or a link by its handle to move it.' : 'Every bookmark of the family, in folders as a browser keeps them. Editors and admins change them.'),
        query ? results() : tree.items.length ? h('div', { class: 'bmgroups' }, level(tree.items, null)) : h('p', { class: 'muted' }, 'No bookmarks yet.'),
        !canEdit || query ? null : h('div', { class: 'multi', style: 'margin-top:12px' },
          h('button', { class: 'pillbtn primary', onclick: () => newFolder(0) }, icon('add', 's'), 'Folder'),
          h('button', { class: 'pillbtn', onclick: () => editLink(0, null) }, icon('add', 's'), 'Link'))),
      h('div', { class: 'box' }, h('h2', null, icon('update'), 'Sync with browsers'),
        h('p', { class: 'muted' }, 'The ioSuite Bookmarks extension keeps a browser\'s own bookmarks the same as these, both ways: the bookmarks bar is the folder "Bookmarks bar" here, Firefox\'s bookmarks menu the folder "Bookmarks menu", and Other bookmarks everything else at the top (in Vivaldi, which keeps one tree: the folder set as its bookmark bar, and the rest of its Bookmarks). What is added, changed or deleted here or in one browser is so in every browser, within a minute. It signs in with one click.'),
        !sync.extension ? null : h('div', { class: 'multi' },
          h('a', { class: 'pillbtn primary', href: 'api/bookmarks/extension.zip', download: '' }, icon('download', 's'), `Extension ${sync.extension} for Chrome, Edge and Vivaldi`),
          h('a', { class: 'pillbtn', href: 'https://github.com/avandeputte/iosuite/releases?q=extension', target: '_blank', rel: 'noopener' }, 'For Firefox')),
        h('p', { class: 'muted small' }, 'Chrome, Edge and Vivaldi: unpack the file, open chrome://extensions (edge://extensions, vivaldi://extensions), turn on Developer mode, choose Load unpacked and pick the folder. Firefox: open the signed .xpi file of the release. Then type this page\'s address in the extension and say yes.'),
        !canEdit ? null : h('p', { class: 'muted' }, 'Other sync apps work too. With Floccus (Firefox, Chrome, Edge, Android, iOS): add an account of the kind Nextcloud Bookmarks, give it the first address, and say yes on the page it opens. Apps that sync a bookmarks file over WebDAV take the second address, the file bookmarks.xbel (or bookmarks.html), your name and an app password from Settings › Account; leave any passphrase empty.'),
        !canEdit ? null : addr('Nextcloud Bookmarks', sync.nextcloud), !canEdit ? null : addr('WebDAV folder', sync.webdav),
        sync.syncing ? h('p', { class: 'small' }, 'A browser is syncing right now.') : null),
      standalone() ? null : h('div', { class: 'box' }, h('h2', null, icon('phone'), 'On a phone'),
        h('p', { class: 'muted' }, 'These bookmarks as an app of their own, with an icon on the home screen: on an iPhone or iPad open the address below (Safari, or Vivaldi, Chrome, Edge or Firefox), tap Share, then Add to Home Screen. On Android or a desktop browser, choose Install (or Add to Home screen) in the browser\'s menu.'),
        addr('Bookmarks app', new URL('bookmarks', document.baseURI).href)),
      h('div', { class: 'box' }, h('h2', null, icon('download'), canEdit ? 'Import and export' : 'Export'),
        canEdit ? h('p', { class: 'muted' }, 'A bookmarks file exported from a browser (HTML) or an XBEL file is added at the top level; pick what goes on the start page afterwards.') : null,
        canEdit ? h('div', { class: 'multi' }, file, h('button', { class: 'pillbtn noic', onclick: importFile }, 'Import')) : null,
        h('p', { class: 'multi' }, h('a', { class: 'pillbtn', href: 'api/bookmarks/export.html', download: 'bookmarks.html' }, icon('download', 's'), 'Export for a browser (HTML)'),
          h('a', { class: 'pillbtn', href: 'api/bookmarks/export.xbel', download: 'bookmarks.xbel' }, icon('download', 's'), 'Export XBEL'))));
    const root = el.querySelector('.bmgroups');
    if (!root || !canEdit) return;
    // drag the grip (mouse, pen or finger): a link lands in any folder's links, a folder among any folder's folders
    const save = (list) => call(`/api/bookmarks/groups/${list.dataset.gid}/order`, { method: 'POST', json: { ids: [...list.children].filter((x) => x.dataset.id).map((x) => +x.dataset.id) } });
    for (const g of root.querySelectorAll('.grip')) {
      const group = g.dataset.kind === 'group', item = g.closest(group ? '.bmedit' : '.bmrow');
      dragSort(g, item, {
        root, lists: () => [...root.querySelectorAll(group ? '.bmsubs' : '.bmlinks')].filter((l) => !item.contains(l)), items: group ? '.bmedit' : '.bmrow', sorting: group ? 'sorting-groups' : 'sorting-links',
        done: (from, to) => save(to),
      });
    }
  };
  el.bmDraw = draw; el.bmPaint = paint;
  await draw();
}

/** A short list of things to do, each a full-width row to tap (a phone's stand-in for a row of small buttons). */
function sheet(title, actions) {
  const back = h('div', { class: 'dialog-back sheetback' });
  const close = () => back.remove();
  back.addEventListener('click', (e) => { if (e.target === back) close(); });
  back.append(h('div', { class: 'dialog sheet', role: 'dialog', 'aria-label': title },
    h('div', { class: 'sheettitle muted small' }, title),
    ...actions.filter((a) => !a.hidden).map((a) => h('button', { class: `sheetrow${a.danger ? ' danger' : ''}`, disabled: a.disabled ? true : null, onclick: () => { close(); a.run(); } }, icon(a.icon, 's'), a.label)),
    h('button', { class: 'sheetrow cancel', onclick: close }, 'Cancel')));
  document.body.append(back);
}

/** Reorder by dragging `handle` (mouse, pen or touch, through pointer events): `item` follows the pointer and the
    others make room; it can land in any of `lists()` (direct children matching `items`). `done(fromList, toList)` runs
    when the order changed. The handle also answers ArrowUp/ArrowDown from the keyboard, within its list. */
function dragSort(handle, item, o) {
  handle.style.touchAction = 'none';
  const kids = (list) => [...list.children].filter((x) => x.matches(o.items));
  handle.addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
    e.preventDefault();
    const list = item.parentNode, sib = e.key === 'ArrowUp' ? item.previousElementSibling : item.nextElementSibling;
    if (!sib || !sib.matches(o.items)) return;
    list.insertBefore(item, e.key === 'ArrowUp' ? sib : sib.nextSibling);
    o.done(list, list);
  });
  handle.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const from = item.parentNode, before = item.nextSibling;
    o.root.classList.add(o.sorting);  // groups fold to their headers while one is dragged
    item.classList.add('dragging');
    const top0 = item.getBoundingClientRect().top;
    const off = Math.min(e.clientY - top0, item.offsetHeight / 2);
    let y = e.clientY, scroll = 0;
    const place = () => {
      item.style.transform = '';
      const lists = o.lists();
      // the list under the pointer, else the nearest one
      let best = lists[0], dist = Infinity;
      for (const l of lists) {
        const r = l.getBoundingClientRect();
        const d = y < r.top ? r.top - y : y > r.bottom ? y - r.bottom : 0;
        if (d < dist) { dist = d; best = l; }
      }
      if (best) {
        const next = kids(best).find((k) => k !== item && y < k.getBoundingClientRect().top + k.offsetHeight / 2);
        if (next) { if (next !== item.nextElementSibling || item.parentNode !== best) best.insertBefore(item, next); }
        else if (item.parentNode !== best || kids(best).at(-1) !== item) best.append(item);
      }
      item.style.transform = `translateY(${y - off - item.getBoundingClientRect().top}px)`;
    };
    const tick = setInterval(() => { if (scroll) { window.scrollBy(0, scroll); place(); } }, 16);
    const still = (ev) => ev.preventDefault();
    const move = (ev) => {
      if (ev.pointerId !== e.pointerId) return;
      y = ev.clientY;
      scroll = y < 60 ? -12 : y > window.innerHeight - 60 ? 12 : 0;
      place();
    };
    const end = (ev) => {
      if (ev.pointerId !== e.pointerId) return;
      clearInterval(tick);
      removeEventListener('pointermove', move);
      removeEventListener('pointerup', end);
      removeEventListener('pointercancel', end);
      removeEventListener('touchmove', still);
      item.classList.remove('dragging');
      item.style.transform = '';
      o.root.classList.remove(o.sorting);
      if (ev.type === 'pointercancel') { from.insertBefore(item, before); return; }
      if (item.parentNode !== from || item.nextSibling !== before) o.done(from, item.parentNode);
    };
    // on the window, not the handle: moving the item in the page drops a pointer capture
    addEventListener('pointermove', move);
    addEventListener('pointerup', end);
    addEventListener('pointercancel', end);
    addEventListener('touchmove', still, { passive: false });  // no page scroll under the finger (iOS)
  });
}

// ------------------------------------------------------------------ settings › security and global settings (suite admins)
/* Everything in the Shared ioSuite database, for the whole suite: Security (people and their role in every app, roles,
   app passwords, sign-in at the proxy) and Global settings (the apps, keys and tokens). The same panel in every io app,
   served by iosuite-shared at /api/suite-admin/ui.js. */
async function setSuite(el, r) {
  let ui;
  try { ui = await import(new URL('api/suite-admin/ui.js', document.baseURI).href); } catch (e) { el.append(h('p', { class: 'err' }, `The panel did not load: ${e.message}`)); return; }
  await ui.mount(el, { tab: r.tab, sub: r.sub, toast, onSub: (x) => history.replaceState(null, '', `#/settings/${r.tab}/${x}`) });
}

// ------------------------------------------------------------------ settings › server (admins)
/* The server panel every io app shares (iosuite-shared /api/server/ui.js): version and updates,
   the server log and Restart. */
async function setServer(el) {
  let ui;
  try { ui = await serverUi(); } catch (e) { el.append(h('p', { class: 'err' }, `The Server panel did not load: ${e.message}`)); return; }
  await ui.mount(el, { toast });
}
const serverUi = () => import(new URL('api/server/ui.js', document.baseURI).href);

/** Admins: a note when the daily check found a newer version, with Update now. Hidden until the next version when dismissed. */
function updateBanner() {
  $('#updbanner')?.remove();
  const u = S.status && S.status.update;
  let dismissed = null; try { dismissed = localStorage.getItem('iosuite.updateDismissed'); } catch { /* private mode */ }
  if (!u || dismissed === u.remote) return;
  const b = h('div', { id: 'updbanner', role: 'status' }, icon('update'),
    h('span', null, `ioSuite ${u.version ? `v${u.version}` : 'update'} is available${u.message ? `: ${u.message.replace(/^v\d+\.\d+\.\d+:\s*/, '')}` : ''}`),
    h('button', { class: 'pillbtn primary noic', onclick: async () => { if (await confirmDialog('Update ioSuite', 'Install the new version and restart? The page reloads when it is back.', 'Update now')) { b.remove(); (await serverUi()).runUpdate({ toast }); } } }, 'Update now'),
    h('a', { class: 'pillbtn noic', href: '#/settings/server', onclick: () => b.remove() }, 'Details'),
    h('button', { class: 'iconbtn', title: 'Not now (hidden until the next version)', onclick: () => { try { localStorage.setItem('iosuite.updateDismissed', u.remote); } catch { /* */ } b.remove(); } }, icon('close', 's')));
  document.body.append(b);
}

// ------------------------------------------------------------------ sign-in
function showSignIn() {
  // as in the other io apps: a tile per account; one click for a passwordless viewer, a password for the others
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
    h('div', { class: 'brand' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }), h('span', { class: 'brand-name', style: { display: 'inline' } }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Suite'))),
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
  S.status = await api('/api/status');
  if (!S.status.user) { showSignIn(); return; }
  S.user = S.status.user;
  // sent here to sign in by a sync app's "may it sync?" page (app/ncbookmarks.py): back to it, now signed in
  const flow = new URLSearchParams(location.search).get('flow');
  if (flow && /^[\w-]{20,}$/.test(flow)) { location.replace('dav/nextcloud/index.php/login/v2/flow/' + flow); return; }
  try { S.settings = (await api('/api/auth/me')).settings || {}; } catch { S.settings = {}; }
  if (S.settings.theme && S.settings.theme !== (localStorage.getItem('iosuite.theme') || 'system')) setTheme(S.settings.theme);
  drawUser();
  if (BM_APP) { document.body.classList.add('bmapp'); $('#topbar .brand').href = './'; $('#topbar .brand').title = 'The start page'; }
  addEventListener('hashchange', onRoute);
  await onRoute();
  updateBanner();
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && document.querySelector('.dialog-back')) document.querySelector('.dialog-back').remove(); });
  // ⌘K / Ctrl-K: the search box on the start page (from another view: go there first)
  document.addEventListener('keydown', (e) => {
    if (e.key.toLowerCase() === 'k' && (e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey) {
      e.preventDefault();
      if (route().view !== 'home') { location.hash = '#/'; setTimeout(() => S.focusSearch && S.focusSearch(), 300); } else if (S.focusSearch) S.focusSearch();
    }
  });
  // back from an app: the page again as it is now (in place); and every few minutes while it stays open (liveRefresh)
  document.addEventListener('visibilitychange', () => liveRefresh(true));
  setInterval(() => liveRefresh(), 60 * 1000);
  setInterval(async () => { try { S.status = await api('/api/status'); updateBanner(); } catch { /* restarting */ } }, 15 * 60 * 1000);
}
start().catch(fail);
