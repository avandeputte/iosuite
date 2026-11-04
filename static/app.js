/* ioSuite web app: one module, no build step, as in the other io apps. The start page (the weather, a tile per app,
   the bookmarks as homepage lays them out) and the settings (account, apps, weather, bookmarks, users, server). Each tile keeps a `.more` block under its name, where the app shows a glimpse of
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
  up: 'M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z',
  down: 'M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z',
  edit: 'M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a.996.996 0 0 0 0-1.41l-2.34-2.34a.996.996 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z',
  delete: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z',
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
async function copyText(t) { try { await navigator.clipboard.writeText(t); toast('Copied'); } catch { toast(t); } }
const copyRow = (v) => h('div', { class: 'copy' }, h('code', null, v), h('button', { class: 'iconbtn', title: 'Copy', onclick: () => copyText(v) }, icon('copy', 's')));
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
/** What to show for a link: the SVG uploaded for it (served by this page) wins over the icon field. */
const bmIcon = (l) => l.iconUrl || bmIconUrl(l.icon);

const appName = (name, color) => h('span', { class: 'nm', style: { '--c': color } }, h('span', { class: 'io' }, 'io'), h('span', { class: 'ap' }, name.replace(/^io/, '')));

// ------------------------------------------------------------------ state
const S = { status: {}, user: null, settings: {}, apps: [] };

function drawUser() {
  const m = $('#usermenu'); m.replaceChildren();
  if (!S.user) return;
  const btn = h('button', { class: 'avatarbtn', title: S.user.displayName, style: { background: `hsl(${hue(S.user.name)} 45% 45%)` } }, initials(S.user.displayName));
  let menu = null;
  const closeMenu = () => { if (menu) { menu.remove(); menu = null; document.removeEventListener('click', outside); } };
  const outside = (e) => { if (menu && !menu.contains(e.target) && e.target !== btn) closeMenu(); };
  btn.onclick = () => {
    if (menu) return closeMenu();
    const theme = localStorage.getItem('iosuite.theme') || 'system';
    menu = h('div', { class: 'menu' },
      h('div', { class: 'who' }, h('b', null, S.user.displayName), h('div', { class: 'muted small' }, `${S.user.name} · ${S.user.role}`)),
      h('a', { class: 'mi', href: '#/settings/account', onclick: closeMenu }, icon('person', 's'), 'Account'),
      ['editor', 'admin'].includes(S.user.role) ? h('a', { class: 'mi', href: '#/settings/bookmarks', onclick: closeMenu }, icon('link', 's'), 'Bookmarks') : null,
      S.user.role === 'admin' ? h('a', { class: 'mi', href: '#/settings/apps', onclick: closeMenu }, icon('settings', 's'), 'Settings') : null,
      h('button', { class: 'mi', onclick: () => { const n = { system: 'light', light: 'dark', dark: 'system' }[theme]; localStorage.setItem('iosuite.theme', n); applyTheme(); closeMenu(); toast(`Appearance: ${n}`); } },
        icon('theme', 's'), `Appearance: ${theme}`),
      h('button', { class: 'mi', onclick: async () => { const r = await api('/api/auth/logout', { method: 'POST' }); if (r && r.cloudflareLogout) location.href = r.cloudflareLogout; else location.reload(); } }, icon('logout', 's'), 'Sign out'));
    m.append(menu);
    setTimeout(() => document.addEventListener('click', outside), 0);
  };
  m.append(btn);
}
function applyTheme() {
  const t = localStorage.getItem('iosuite.theme') || 'system';
  if (t === 'system') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
}

// ------------------------------------------------------------------ routes
function route() {
  const [a, b] = location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
  if (a === 'settings') return { view: 'settings', tab: b || 'account' };
  return { view: 'home' };
}
async function onRoute() {
  const r = route();
  const page = h('div', { class: 'page' });
  // the start page has no top bar: the account menu sits in its first row instead (showHome moves it there)
  document.body.classList.toggle('home', r.view === 'home');
  if (r.view !== 'home') $('#topbar').append($('#usermenu'));
  $('#main').replaceChildren(page);
  try { await ({ home: showHome, settings: showSettings })[r.view](page, r); } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ the start page
const greeting = () => { const hr = new Date().getHours(); return hr < 5 ? 'Good night' : hr < 12 ? 'Good morning' : hr < 18 ? 'Good afternoon' : 'Good evening'; };

async function showHome(page) {
  const got = await api('/api/apps');
  S.apps = got.items;
  const first = (S.user.displayName || S.user.name).split(/\s+/)[0];
  const wx = h('div', { class: 'weather' });
  page.append(h('div', { class: 'top' }, h('div', { class: 'hello' }, h('h1', null, `${greeting()}, ${first}`),
    h('div', { class: 'muted' }, new Date().toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' }))), wx, $('#usermenu')));
  drawWeather(wx);  // fills in when AccuWeather (or the server's copy) answers
  // the tiles: an app with something to show gets a column of its own; the others go two to a column, half the height
  const tile = (a, small) => h('a', { class: `app${small ? ' small' : ''}`, href: a.url, 'data-app': a.key, title: a.url },
    h('img', { src: a.icon, alt: '' }), h('span', { class: 'who' }, appName(a.name, a.color), h('span', { class: 'tag' }, a.tagline)),
    h('div', { class: 'more' }));  // what the app shows here: drawWidgets
  const big = S.apps.filter((a) => WIDGETS[a.key]), rest = S.apps.filter((a) => !WIDGETS[a.key]);
  const stacks = []; for (let i = 0; i < rest.length; i += 2) stacks.push(h('div', { class: 'stack' }, rest.slice(i, i + 2).map((a) => tile(a, true))));
  if (!S.apps.length) page.append(h('div', { class: 'empty' }, 'No apps to show. ', S.user.role === 'admin' ? h('a', { class: 'lnk', href: '#/settings/apps' }, 'Settings › Apps') : null));
  else page.append(h('div', { class: 'apps', style: { '--cols': big.length + stacks.length } }, big.map((a) => tile(a, false)), stacks));
  drawWidgets(page);
  // the week ahead: birthdays from ioContacts and the coming days' events from ioCalendar, a card each
  const agenda = h('div', { class: 'agenda' });
  if (S.apps.some((a) => a.key === 'iocontacts')) { const c = h('div', { class: 'card birthdays' }); agenda.append(c); drawBirthdays(c); }
  if (S.apps.some((a) => a.key === 'iocalendar')) { const c = h('div', { class: 'card week' }); agenda.append(c); drawWeek(c); }
  if (agenda.childElementCount) page.append(agenda);
  if (got.photoStrip !== 'off' && S.apps.some((a) => a.key === 'iopix')) { const strip = h('div', { class: 'strip' }); page.append(strip); drawStrip(strip, got.photoStrip); }
  const bm = h('div', { class: 'bookmarks' });
  page.append(bm);
  drawBookmarks(bm);
}

/** /api/widgets/<key>?... as JSON, or null when the app is down, not open to this account, or the answer is not JSON. */
async function widget(key, params = {}) {
  try {
    const r = await fetch(`/api/widgets/${key}?${new URLSearchParams({ tz: viewerTz(), ...params })}`, { credentials: 'same-origin' });
    return r.ok ? await r.json() : null;
  } catch { return null; }
}
const inDays = (n) => (n === 0 ? 'Today' : n === 1 ? 'Tomorrow' : `In ${n} days`);

/** Birthdays (and the other dates ioContacts keeps) in the next 30 days; each row opens the contact. */
async function drawBirthdays(el) {
  const app = S.apps.find((a) => a.key === 'iocontacts'), d = await widget('iocontacts');
  if (!d || !d.items || !el.isConnected) { el.remove(); return; }
  const who = (it) => h('span', { class: 'face' }, it.hasPhoto ? h('img', { src: `/api/widgets/iocontacts/photo/${it.id}`, alt: '', loading: 'lazy', onerror: (e) => e.target.replaceWith(initials(it.name)) }) : initials(it.name));
  const what = (it) => [it.label === 'birthday' ? (it.turns ? `Turns ${it.turns}` : 'Birthday') : it.label + (it.turns ? ` · ${it.turns} years` : '')].join('');
  el.replaceChildren(h('div', { class: 'wghead' }, h('span', null, 'Birthdays'), h('a', { class: 'muted', href: app.url, title: app.url }, d.more ? `+${d.more} more · ioContacts` : 'ioContacts')),
    d.items.length ? h('div', { class: 'rows' }, d.items.map((it) => h('a', { class: 'bday', href: `${app.url}/#/c/${it.id}` }, who(it),
      h('span', { class: 'bdwho' }, h('span', { class: 'bdname' }, it.name), h('span', { class: 'muted small' }, what(it))),
      h('span', { class: `bdwhen${it.in === 0 ? ' today' : ''}` }, inDays(it.in)))))
      : h('div', { class: 'muted small' }, 'No birthdays in the next 30 days'));
}

/** The coming week from ioCalendar, day by day (today lives on the ioCalendar tile); a day opens in ioCalendar. */
async function drawWeek(el) {
  const app = S.apps.find((a) => a.key === 'iocalendar'), d = await widget('iocalendar', { kind: 'week' });
  if (!d || !d.days || !el.isConnected) { el.remove(); return; }
  const head = (date) => { const s = new Date(`${date}T12:00:00`); const days = Math.round((s - new Date().setHours(12, 0, 0, 0)) / 86400000);
    return days === 1 ? 'Tomorrow' : s.toLocaleDateString([], { weekday: 'long' }); };
  el.replaceChildren(h('div', { class: 'wghead' }, h('span', null, 'This week'), h('a', { class: 'muted', href: app.url, title: app.url }, d.more ? `+${d.more} more · ioCalendar` : 'ioCalendar')),
    d.days.length ? h('div', { class: 'rows' }, d.days.map((day) => h('div', { class: 'wkday' },
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
  const shuffle = otd ? null : h('button', { class: 'lnk shuffle', title: 'Another row of photos', onclick: (e) => { e.preventDefault(); el.classList.add('busy'); drawStrip(el, kind); } }, icon('update', 's'), 'Shuffle');
  el.classList.remove('busy');
  el.replaceChildren(h('div', { class: 'wghead' }, h('span', null, otd ? 'On this day' : 'Rediscover'), shuffle,
    h('a', { class: 'muted', href: pix.url, title: pix.url }, otd && d.count > d.items.length ? `${d.count} photos · ioPix` : 'ioPix')),
    h('div', { class: 'row' }, d.items.map((it) => h('a', { class: 'wgph', href: pixPhotoUrl(pix, it.id), title: String(cap(it)) },
      h('img', { src: `/api/widgets/iopix/thumb/${it.id}`, alt: '', loading: 'lazy', onerror: (e) => e.target.parentNode.remove() }),
      cap(it) ? h('span', null, cap(it)) : null))));
}

// ------------------------------------------------------------------ what the tiles show (/api/widgets/<app>)
/* Under an app's name, a glimpse of it: ioPix's photos from this day in earlier years (else a few at random),
   ioCalendar's rest of today (else what's next), ioHealth's steps and rings. The server asks each app with the
   viewer's own sign-in; an app that is down or not open to this account leaves its tile as it was. */
const WIDGETS = { iopix: drawPixWidget, iocalendar: drawCalendarWidget, iohealth: drawHealthWidget };
/** ioPix opens one photo in its lightbox at #/photos?p=<id>. */
const pixPhotoUrl = (pix, id) => `${pix.url}/#/photos?p=${id}`;
const viewerTz = () => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch { return ''; } };

function drawWidgets(page) {
  const tz = viewerTz();
  for (const tile of page.querySelectorAll('.app[data-app]')) {
    const draw = WIDGETS[tile.dataset.app], box = tile.querySelector('.more');
    if (!draw || !box) continue;
    fetch(`/api/widgets/${tile.dataset.app}?tz=${encodeURIComponent(tz)}`, { credentials: 'same-origin' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d && box.isConnected) { const kids = draw(d); if (kids) box.replaceChildren(h('div', { class: 'wg' }, kids)); } })
      .catch(() => { /* the tile stays as it was */ });
  }
}

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
  if (d.today && d.today.length) {
    return [wgHead('Today', d.more ? `+${d.more} more` : null), d.today.map((o) => evRow(o, evTime(o)))];
  }
  if (d.next) return [wgHead('Next', evDay(d.next)), evRow(d.next, evTime(d.next))];
  return [wgHead('Today'), h('div', { class: 'muted small' }, 'Nothing planned')];
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
  return [wgHead('Today'), h('div', { class: 'wghealth' }, r ? rings(r) : null,
    h('div', null, d.steps != null ? h('div', { class: 'wgsteps' }, h('b', null, n(d.steps)), ' steps', week ? h('span', { class: 'wgtrend', title: `${n(total)} steps in the last 7 days` }, sparkline(week)) : null) : null,
      line('move', 'Move', 'kcal'), line('exercise', 'Exercise', 'min'), line('stand', 'Stand', 'h'))),
    d.sleep ? h('div', { class: 'wgsleep', title: d.sleep.start && d.sleep.end ? `Asleep ${when(d.sleep.start)} – ${when(d.sleep.end)}${d.sleep.inBed ? `, ${hm(d.sleep.inBed)} in bed` : ''}` : '' },
      h('span', { class: 'dot', style: { background: 'var(--sleep)' } }), 'Sleep', h('span', { class: 'muted' }, `${hm(d.sleep.asleep)} asleep`)) : null];
}

/** The weather widget: the conditions now, a line of details, and the days ahead. Hidden until an admin sets it up. */
async function drawWeather(el) {
  let w;
  try { w = await api('/api/weather'); } catch (e) { el.replaceChildren(h('div', { class: 'muted small' }, e.message)); return; }
  if (!el.isConnected) return;
  if (!w.enabled) { el.replaceChildren(S.user.role === 'admin' ? h('a', { class: 'lnk small', href: '#/settings/weather' }, 'Add the weather') : null); return; }
  if (!w.current) { el.replaceChildren(h('div', { class: 'wxerr' }, wxIcon(7, 'big'), h('div', null, h('div', null, 'No weather right now'), h('div', { class: 'muted small' }, w.error || '')))); return; }
  const c = w.current, imp = w.units === 'imperial', u = imp ? 'imperial' : 'metric';
  const day = (d) => new Date(`${d.date}T12:00:00`).toLocaleDateString([], { weekday: 'short' });
  const t = (v) => fmtTemp(imp ? degF(v) : v);  // the forecast comes in °C
  el.replaceChildren(
    h('a', { class: 'wxnow', href: c.link || '#', target: c.link ? '_blank' : null, rel: 'noreferrer',
      title: [w.location, c.feels[u] != null ? `feels ${fmtTemp(c.feels[u])}` : null, c.humidity != null ? `${c.humidity}% humidity` : null,
        c.wind[u] != null ? `wind ${Math.round(c.wind[u])} ${imp ? 'mph' : 'km/h'}` : null].filter(Boolean).join(' · ') },
      wxIcon(c.icon, 'big'),
      h('div', null, h('div', { class: 'wxtemp' }, fmtTemp(c.temp[u])), h('div', { class: 'wxtext small' }, c.text))),
    w.forecast && w.forecast.days && w.forecast.days.length ? h('div', { class: 'wxdays' }, w.forecast.days.map((d) =>
      h('div', { class: 'wxday', title: `${d.text || ''}${d.rain != null ? ` · ${d.rain}% chance of rain` : ''}` }, h('span', { class: 'muted small' }, day(d)), wxIcon(d.icon), h('span', { class: 'small' }, `${t(d.max)} `, h('span', { class: 'muted' }, t(d.min)))))) : null,
    w.stale ? h('span', { class: 'muted small', title: w.error || 'AccuWeather did not answer' }, 'older') : h('span'));
}

/** The bookmarks, as homepage lays them out: a column per group, a row per link with its abbreviation (or icon), name and host. */
async function drawBookmarks(el) {
  let gs;
  try { gs = (await api('/api/bookmarks')).groups; } catch (e) { el.replaceChildren(h('div', { class: 'muted small' }, e.message)); return; }
  if (!el.isConnected) return;
  const canEdit = ['editor', 'admin'].includes(S.user.role);
  if (!gs.length) { el.replaceChildren(canEdit ? h('a', { class: 'lnk small', href: '#/settings/bookmarks' }, 'Add bookmarks') : null); return; }
  el.replaceChildren(...gs.filter((g) => g.links.length || canEdit).map((g) => h('div', { class: 'bmgroup' }, h('h2', null, g.name),
    g.links.map((l) => {
      const src = bmIcon(l);
      return h('a', { class: 'bm', href: l.href, title: l.href, target: '_blank', rel: 'noreferrer' },
        h('span', { class: 'bmic' }, src ? h('img', { src, alt: '', onerror: (e) => { e.target.replaceWith(l.abbr); } }) : l.abbr),
        h('span', { class: 'bmname' }, l.name), h('span', { class: 'bmdesc muted small' }, l.description));
    }),
    canEdit && !g.links.length ? h('a', { class: 'lnk small', href: '#/settings/bookmarks' }, 'Empty: add a link') : null)));
}

// ------------------------------------------------------------------ settings
async function showSettings(page, r) {
  const adm = S.user.role === 'admin';
  const canEdit = ['editor', 'admin'].includes(S.user.role);
  const tabs = [['account', 'Account'], ...(adm ? [['apps', 'Apps'], ['weather', 'Weather']] : []), ...(canEdit ? [['bookmarks', 'Bookmarks']] : []), ...(adm ? [['users', 'Users'], ['server', 'Server']] : [])];
  if (!tabs.some(([k]) => k === r.tab)) r.tab = 'account';
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Settings')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/settings/${k}`; } }, l))));
  const body = h('div'); page.append(body);
  await ({ account: setAccount, apps: setApps, weather: setWeather, bookmarks: setBookmarks, users: setUsers, server: setServer }[r.tab] || setAccount)(body);
}
const fld = (l, e) => h('label', { class: 'field' }, h('span', null, l), e);
const kv = (k, v) => h('div', { class: 'kv' }, h('div', { class: 'k' }, k), h('div', { class: 'v', style: { flex: 1 } }, typeof v === 'string' ? copyRow(v) : v));

async function setAccount(el) {
  const u = S.user;
  const dn = h('input', { class: 't', value: u.displayName || '' }), em = h('input', { class: 't', type: 'email', value: u.email || '' });
  const old = h('input', { class: 't', type: 'password', autocomplete: 'current-password' }), nw = h('input', { class: 't', type: 'password', autocomplete: 'new-password' });
  el.append(h('div', { class: 'box' }, h('h2', null, icon('person'), 'You'),
    h('p', { class: 'muted' }, 'The same account as in every io app: a change here shows up everywhere.'),
    h('div', { class: 'grid' }, fld('Display name', dn), fld('Email (for sign-in at a proxy)', em)),
    h('p', null, h('button', { class: 'pillbtn primary', onclick: async () => { try { S.user = (await api('/api/auth/me', { method: 'PATCH', json: { displayName: dn.value, email: em.value } })).user; drawUser(); toast('Saved'); } catch (e) { fail(e); } } }, icon('check', 's'), 'Save'))),
  u.hasPassword ? h('div', { class: 'box' }, h('h2', null, icon('key'), 'Password'), h('div', { class: 'grid' }, fld('Current password', old), fld('New password (8 or more)', nw)),
    h('p', null, h('button', { class: 'pillbtn', onclick: async () => { try { await api('/api/auth/password', { method: 'POST', json: { current: old.value, password: nw.value } }); old.value = nw.value = ''; toast('Password changed'); } catch (e) { fail(e); } } }, 'Change password'), ' ',
      h('button', { class: 'pillbtn noic', onclick: async () => { if (await confirmDialog('Sign out everywhere', 'Sign out on every other browser and device, in every io app? (Apps with an app password keep working.)', 'Sign out the others')) { try { await api('/api/auth/logout_all', { method: 'POST' }); toast('Signed out elsewhere'); } catch (e) { fail(e); } } } }, 'Sign out everywhere else'))) : null);
}

async function setApps(el) {
  const got = await api('/api/apps/settings'), items = got.items;
  const strip = h('select', { class: 't' }, [['rediscover', 'Rediscover: photos at random'], ['onthisday', 'On this day (at random when there are none)'], ['off', 'Off']].map(([v, t]) => h('option', { value: v, selected: v === got.photoStrip ? true : null }, t)));
  const rows = items.map((a) => {
    const url = h('input', { class: 't', value: a.envUrl || a.url, placeholder: `empty: this host, port ${a.port}`, disabled: a.envUrl ? true : null });
    const shown = h('input', { type: 'checkbox', checked: !a.hidden });
    return { a, url, shown, el: h('div', { class: 'approw' }, h('img', { src: `static/icons/apps/${a.key}.svg`, alt: '' }), h('span', { class: 'nm' }, a.name), url,
      h('label', { class: 'check' }, shown, ' On the page'), a.envUrl ? h('span', { class: 'muted small' }, `${a.key.toUpperCase()}_URL in the environment`) : null) };
  });
  el.append(h('div', { class: 'box' }, h('h2', null, icon('apps'), 'The apps on the start page'),
    h('p', { class: 'muted' }, 'Where each app is reached, as the family opens it: its public address behind the reverse proxy, or its LAN address. Empty: the host this page was opened on, with the app’s usual port (the one-box install). An address set in the environment (IOPIX_URL and friends) wins over this.'),
    rows.map((r) => r.el),
    h('div', { class: 'grid' }, fld('Photo strip under the tiles (ioPix)', strip)),
    h('p', null, h('button', { class: 'pillbtn primary', onclick: async () => {
      const body = { ...Object.fromEntries(rows.map((r) => [r.a.key, { ...(r.a.envUrl ? {} : { url: r.url.value.trim() }), hidden: !r.shown.checked }])), photoStrip: strip.value };
      try { await api('/api/apps/settings', { method: 'POST', json: body }); toast('Saved'); } catch (e) { fail(e); }
    } }, icon('check', 's'), 'Save'))));
}

async function setWeather(el) {
  const s = await api('/api/weather/settings');
  const key = h('input', { class: 't', type: 'password', placeholder: s.hasKey ? '(kept)' : 'API key from developer.accuweather.com', disabled: s.keyFromEnv ? true : null, autocomplete: 'off' });
  const units = h('select', { class: 't', style: 'width:auto' }, [['metric', '°C, km/h'], ['imperial', '°F, mph']].map(([v, l]) => h('option', { value: v, selected: v === s.units ? true : null }, l)));
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
    h('p', { class: 'muted' }, 'The weather on the start page comes from AccuWeather. A free key (developer.accuweather.com, "Core Weather", 50 calls a day) is enough: this server asks AccuWeather at most every 45 minutes for the conditions and every 6 hours for the forecast, and only while someone opens the page; browsers never talk to AccuWeather.'),
    h('div', { class: 'grid' }, fld('API key', key), fld('Units', units)),
    s.keyFromEnv ? h('p', { class: 'muted small' }, 'ACCUWEATHER_API_KEY in the environment sets the key.') : null,
    h('p', null, h('button', { class: 'pillbtn primary', onclick: async () => { if (await save({ ...(key.value.trim() ? { key: key.value.trim() } : {}), units: units.value })) { key.value = ''; key.placeholder = '(kept)'; } } }, icon('check', 's'), 'Save'), ' ',
      s.hasKey && !s.keyFromEnv ? h('button', { class: 'pillbtn noic', onclick: async () => { if (await confirmDialog('Remove the key', 'Remove the AccuWeather key? The widget disappears from the page.', 'Remove', true)) { await save({ key: '' }); onRoute(); } } }, 'Remove the key') : null)),
  h('div', { class: 'box' }, h('h2', null, icon('cloud'), 'Place'), where,
    s.locationFromEnv ? null : [h('div', { class: 'multi' }, q, h('button', { class: 'pillbtn noic', onclick: search }, 'Find')), found,
      h('p', { class: 'muted small' }, 'Type a city and pick it from the list (one AccuWeather call per search).')]));
}

async function setBookmarks(el) {
  const draw = async () => {
    const gs = (await api('/api/bookmarks')).groups;
    if (!el.isConnected) return;
    const call = async (path, opts, msg) => { try { await api(path, opts); if (msg) toast(msg); await draw(); } catch (e) { fail(e); } };
    const linkForm = (g, l) => {
      const name = h('input', { class: 't', value: l ? l.name : '', placeholder: 'Name' }), href = h('input', { class: 't', value: l ? l.href : '', placeholder: 'https://…' });
      const abbr = h('input', { class: 't', value: l ? l.abbr : '', placeholder: 'Two letters (from the name when empty)', maxlength: 4 });
      const desc = h('input', { class: 't', value: l ? l.customDescription : '', placeholder: 'Line under the name (the host name when empty)' });
      const ic = h('input', { class: 't', value: l ? l.icon : '', placeholder: 'Icon: an image address, or a name from dashboard-icons (github.png)' });
      const grp = h('select', { class: 't' }, gs.map((x) => h('option', { value: x.id, selected: x.id === g.id ? true : null }, x.name)));
      // an SVG of your own, kept in the database: it wins over the icon field
      const file = h('input', { type: 'file', accept: '.svg,image/svg+xml', class: 't' });
      const drop = h('input', { type: 'checkbox' });
      const upload = h('div', { class: 'upload' }, l && l.iconUrl ? h('img', { src: l.iconUrl, alt: '', class: 'bmprev' }) : null, file,
        l && l.iconUrl ? h('label', { class: 'small' }, drop, ' Remove the uploaded icon') : null);
      return { body: h('div', { class: 'grid' }, fld('Name', name), fld('Address', href), fld('Abbreviation', abbr), fld('Description', desc), fld('Icon', ic), h('div', { class: 'field' }, h('span', null, 'Upload an SVG icon'), upload), fld('Group', grp)),
        value: () => ({ name: name.value, href: href.value, abbr: abbr.value, description: desc.value, icon: ic.value, groupId: +grp.value }), file: () => file.files[0], drop: () => drop.checked };
    };
    const editLink = async (g, l) => {
      const f = linkForm(g, l);
      const v = await dialog(l ? 'Change the link' : 'New link', f.body, [{ label: 'Cancel', value: null }, { label: l ? 'Save' : 'Add', value: () => ({ link: f.value(), file: f.file(), drop: f.drop() }), primary: true }]);
      if (!v) return;
      try {
        const saved = await api(l ? `/api/bookmarks/links/${l.id}` : `/api/bookmarks/groups/${g.id}/links`, { method: l ? 'PATCH' : 'POST', json: v.link });
        if (v.file) await api(`/api/bookmarks/links/${saved.id}/icon`, { method: 'PUT', body: v.file, headers: { 'Content-Type': 'image/svg+xml' } });
        else if (v.drop) await api(`/api/bookmarks/links/${saved.id}/icon`, { method: 'DELETE' });
        toast('Saved');
      } catch (e) { fail(e); }
      await draw();
    };
    const move = (list, i, d) => { const ids = list.map((x) => x.id); const [x] = ids.splice(i, 1); ids.splice(i + d, 0, x); return ids; };
    const newGroup = h('input', { class: 't', placeholder: 'New group, e.g. Developer', style: 'max-width:280px' });
    const yaml = h('textarea', { class: 't', placeholder: '- Developer:\n    - Github:\n        - abbr: GH\n          href: https://github.com/', spellcheck: 'false' });
    const replace = h('input', { type: 'checkbox' });
    el.replaceChildren(
      h('div', { class: 'box' }, h('h2', null, icon('link'), 'Bookmarks'),
        h('p', { class: 'muted' }, 'Groups of links under the apps, as homepage shows them: a two-letter badge (or an icon), the name and the site. Everyone in the family sees the same bookmarks; editors and admins change them.'),
        gs.length ? gs.map((g, gi) => h('div', { class: 'bmedit' },
          h('div', { class: 'bmhead' }, h('b', null, g.name),
            h('button', { class: 'iconbtn', title: 'Up', disabled: gi === 0 ? true : null, onclick: () => call('/api/bookmarks/groups/order', { method: 'POST', json: { ids: move(gs, gi, -1) } }) }, icon('up', 's')),
            h('button', { class: 'iconbtn', title: 'Down', disabled: gi === gs.length - 1 ? true : null, onclick: () => call('/api/bookmarks/groups/order', { method: 'POST', json: { ids: move(gs, gi, 1) } }) }, icon('down', 's')),
            h('button', { class: 'iconbtn', title: 'Rename', onclick: async () => { const i = h('input', { class: 't', value: g.name }); const v = await dialog('Rename the group', i, [{ label: 'Cancel', value: null }, { label: 'Save', value: () => i.value, primary: true }]); if (v) call(`/api/bookmarks/groups/${g.id}`, { method: 'PATCH', json: { name: v } }, 'Saved'); } }, icon('edit', 's')),
            h('button', { class: 'iconbtn', title: 'Delete the group', onclick: async () => { if (await confirmDialog('Delete the group', `Delete "${g.name}" and its ${g.links.length} link(s)?`, 'Delete', true)) call(`/api/bookmarks/groups/${g.id}`, { method: 'DELETE' }, 'Deleted'); } }, icon('delete', 's')),
            h('button', { class: 'pillbtn', style: 'margin-left:auto', onclick: () => editLink(g, null) }, icon('add', 's'), 'Link')),
          g.links.map((l, li) => h('div', { class: 'bmrow' }, h('span', { class: 'bmic' }, bmIcon(l) ? h('img', { src: bmIcon(l), alt: '', onerror: (e) => { e.target.replaceWith(l.abbr); } }) : l.abbr), h('span', { class: 'bmname' }, l.name), h('span', { class: 'muted small bmdesc' }, l.description),
            h('span', { class: 'bmtools' },
              h('button', { class: 'iconbtn', title: 'Up', disabled: li === 0 ? true : null, onclick: () => call(`/api/bookmarks/groups/${g.id}/order`, { method: 'POST', json: { ids: move(g.links, li, -1) } }) }, icon('up', 's')),
              h('button', { class: 'iconbtn', title: 'Down', disabled: li === g.links.length - 1 ? true : null, onclick: () => call(`/api/bookmarks/groups/${g.id}/order`, { method: 'POST', json: { ids: move(g.links, li, 1) } }) }, icon('down', 's')),
              h('button', { class: 'iconbtn', title: 'Change', onclick: () => editLink(g, l) }, icon('edit', 's')),
              h('button', { class: 'iconbtn', title: 'Delete', onclick: async () => { if (await confirmDialog('Delete the link', `Delete "${l.name}"?`, 'Delete', true)) call(`/api/bookmarks/links/${l.id}`, { method: 'DELETE' }, 'Deleted'); } }, icon('delete', 's'))))))) : h('p', { class: 'muted' }, 'No bookmarks yet.'),
        h('div', { class: 'multi', style: 'margin-top:12px' }, newGroup, h('button', { class: 'pillbtn primary', onclick: () => { if (newGroup.value.trim()) call('/api/bookmarks/groups', { method: 'POST', json: { name: newGroup.value } }, 'Group made'); } }, icon('add', 's'), 'Group'))),
      h('div', { class: 'box' }, h('h2', null, icon('link'), 'Import from homepage'),
        h('p', { class: 'muted' }, 'Paste a homepage bookmarks.yaml: its groups and links are added here (a group with the same name gets the links).'),
        yaml, h('p', null, h('label', { class: 'check' }, replace, ' Replace everything that is here first')),
        h('p', null, h('button', { class: 'pillbtn primary', onclick: async () => { try { const r = await api('/api/bookmarks/import', { method: 'POST', json: { yaml: yaml.value, replace: replace.checked } }); toast(`${r.groups} group(s) and ${r.links} link(s) added`); yaml.value = ''; draw(); } catch (e) { fail(e); } } }, icon('check', 's'), 'Import'))));
  };
  await draw();
}

async function setUsers(el) {
  const r = await api('/api/users');
  const roles = r.roles || ['viewer', 'editor', 'admin'];
  const name = h('input', { class: 't', placeholder: 'User name' }), pw = h('input', { class: 't', type: 'password', placeholder: 'Password (8 or more)' });
  const role = h('select', { class: 't' }, roles.map((x) => h('option', { value: x, selected: x === 'viewer' ? true : null }, x)));
  const patch = async (u, body, msg) => { try { await api(`/api/users/${u.id}`, { method: 'PATCH', json: body }); toast(msg); return true; } catch (e) { fail(e); return false; } };
  el.append(h('div', { class: 'box' }, h('h2', null, icon('people'), 'Family members'),
    h('p', { class: 'muted' }, 'The accounts are the same as in the other io apps; the role here is for the start page. Everyone sees the page; admins also set the apps’ addresses and manage accounts. The role in each app is set in that app.'),
    h('table', { class: 't' }, h('tr', null, h('th', null, 'Name'), h('th', null, 'Display name'), h('th', null, 'Role'), h('th')),
      r.users.map((u) => {
        const rs = h('select', { class: 't', style: 'width:auto' }, [...new Set([...roles, u.role])].map((x) => h('option', { value: x, selected: x === u.role ? true : null }, x)));
        rs.onchange = async () => { if (!await patch(u, { role: rs.value }, 'Saved')) onRoute(); };
        return h('tr', null, h('td', null, u.name, u.suiteAdmin ? h('span', { class: 'muted small' }, ' · suite admin') : null), h('td', null, u.displayName), h('td', null, rs), h('td', { style: { whiteSpace: 'nowrap' } },
          h('button', { class: 'pillbtn noic', onclick: async () => { const p = h('input', { class: 't', type: 'password' }); const v = await dialog(`New password for ${u.name}`, p, [{ label: 'Cancel', value: null }, { label: 'Set', value: () => p.value, primary: true }]); if (v) patch(u, { password: v }, 'Password set'); } }, 'Password'), ' ',
          u.id !== S.user.id ? h('button', { class: 'pillbtn noic danger', onclick: async () => { if (await confirmDialog('Delete account', `Delete ${u.name}? This removes the account from every io app.`, 'Delete', true)) { try { await api(`/api/users/${u.id}`, { method: 'DELETE' }); onRoute(); } catch (e) { fail(e); } } } }, 'Delete') : null));
      })),
    h('h2', { style: { marginTop: '16px' } }, 'Add someone'), h('div', { class: 'multi' }, name, pw, role,
      h('button', { class: 'pillbtn primary', onclick: async () => { try { await api('/api/users', { method: 'POST', json: { name: name.value, password: pw.value, role: role.value } }); toast('Account made'); onRoute(); } catch (e) { fail(e); } } }, icon('add', 's'), 'Add'))));
}

async function setServer(el) {
  const draw = async () => {
    let s; try { s = await api('/api/server'); } catch (e) { el.replaceChildren(h('p', null, e.message)); return; }
    if (!el.isConnected) return;
    const c = s.check, p = s.progress, last = s.lastUpdate;
    const state = p.running ? 'Updating… ioSuite restarts when it is done, and this page reloads.'
      : p.error ? `The last update failed: ${p.error}`
        : !c ? `You have v${s.version}${s.installed !== 'unknown' ? ` (${s.installed})` : ''}.`
          : c.status === 'current' ? `v${s.version} is the latest version.`
            : c.status === 'update' ? `You have v${s.version}; ${c.remoteVersion ? `v${c.remoteVersion}` : 'a newer build'} is available${c.remoteDate ? ` (${c.remoteDate})` : ''}${c.remoteMessage ? `: ${c.remoteMessage.replace(/^v\d+\.\d+\.\d+:\s*/, '')}` : ''}.`
              : `Could not check: ${c.error}`;
    const sw = (on, label, key, locked) => h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: on, disabled: locked ? true : null, onchange: async (e) => {
      try { await api('/api/server', { method: 'POST', json: { [key]: e.target.checked } }); S.status = await api('/api/status'); toast('Saved'); draw(); } catch (err) { e.target.checked = !e.target.checked; fail(err); }
    } }), ' ', label);
    el.replaceChildren(
      h('div', { class: 'box' }, h('h2', null, icon('update'), 'ioSuite version'),
        h('p', null, state),
        !p.running && !p.error && last ? h('p', { class: last.ok ? 'muted small' : 'warn small' }, `Last update: ${last.text}`) : null,
        h('p', null,
          h('button', { class: 'pillbtn', onclick: async () => { el.querySelector('.box p').textContent = 'Checking…'; try { await api('/api/server', { method: 'POST', json: { action: 'check' } }); } catch (e) { fail(e); } draw(); } }, icon('update', 's'), 'Check for updates'), ' ',
          s.docker ? h('span', { class: 'muted' }, 'Docker: update by pulling the image (docker compose pull && docker compose up -d).')
            : s.canRun ? h('button', { class: `pillbtn ${c && c.status === 'update' ? 'primary' : ''}`, disabled: p.running ? true : null, onclick: async () => {
              if (!await confirmDialog('Update ioSuite', 'Fetch the newest version, refresh its packages and restart ioSuite? Settings stay; the page reloads when the new version is up.', 'Update now')) return;
              if (await runUpdate()) setTimeout(draw, 2500);
            } }, icon('check', 's'), 'Update now')
              : h('span', { class: 'muted' }, 'This install cannot update itself from here (run ./update.sh in the app folder).')),
        h('p', null, sw(s.autoCheck, 'Check for a new version once a day (only GitHub’s public list of changes is asked; nothing about this server is sent)', 'autoCheck', s.autoCheckLocked)),
        s.autoCheckLocked ? h('p', { class: 'muted small' }, 'UPDATE_CHECK=0 in the environment keeps it off.') : null,
        h('p', { class: 'muted small' }, `Follows ${s.repo} (${s.branch}). Database ${s.database}.`)),
      h('div', { class: 'box' }, h('h2', null, icon('server'), 'This page'), kv('Address', s.url),
        h('p', { class: 'muted small' }, 'Set PUBLIC_URL when the address above is not the one the family uses (behind a reverse proxy).')));
    if (p.running) setTimeout(() => { if (el.isConnected) draw(); }, 4000);
  };
  await draw();
}

/** Start update.sh on the server, then watch /api/status until another version or commit answers, and reload. */
async function runUpdate() {
  try { await api('/api/server', { method: 'POST', json: { action: 'update' } }); } catch (e) { fail(e); return false; }
  toast('Updating; ioSuite restarts when it is done, and the page reloads.');
  const was = `${S.status.version}|${S.status.commit || ''}`, until = Date.now() + 240000;
  const look = async () => {
    try { const s = await fetch('/api/status', { credentials: 'same-origin' }).then((r) => r.json()); if (s.version && `${s.version}|${s.commit || ''}` !== was) { location.reload(); return; } } catch { /* restarting */ }
    if (Date.now() < until) setTimeout(look, 4000); else toast('The update did not finish; see Settings › Server.');
  };
  setTimeout(look, 4000);
  return true;
}

/** Admins: a note when the daily check found a newer version, with Update now. Hidden until the next version when dismissed. */
function updateBanner() {
  $('#updbanner')?.remove();
  const u = S.status && S.status.updateAvailable;
  let dismissed = null; try { dismissed = localStorage.getItem('iosuite.updateDismissed'); } catch { /* private mode */ }
  if (!u || dismissed === u.remote) return;
  const b = h('div', { id: 'updbanner', role: 'status' }, icon('update'),
    h('span', null, `ioSuite ${u.version ? `v${u.version}` : 'update'} is available${u.message ? `: ${u.message.replace(/^v\d+\.\d+\.\d+:\s*/, '')}` : ''}`),
    h('button', { class: 'pillbtn primary noic', onclick: async () => { if (await confirmDialog('Update ioSuite', 'Install the new version and restart? The page reloads when it is back.', 'Update now')) { b.remove(); runUpdate(); } } }, 'Update now'),
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
  try { S.settings = (await api('/api/auth/me')).settings || {}; } catch { S.settings = {}; }
  drawUser();
  addEventListener('hashchange', onRoute);
  await onRoute();
  updateBanner();
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && document.querySelector('.dialog-back')) document.querySelector('.dialog-back').remove(); });
  // back from an app: the tiles again as they are now
  document.addEventListener('visibilitychange', () => { if (!document.hidden && route().view === 'home' && !document.querySelector('.dialog-back')) onRoute(); });
  setInterval(async () => { try { S.status = await api('/api/status'); updateBanner(); } catch { /* restarting */ } }, 15 * 60 * 1000);
}
start().catch(fail);
