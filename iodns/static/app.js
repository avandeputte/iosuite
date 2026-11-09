/* ioDNS web app: one module, no build step, laid out as the other ioThing apps. Pages: the master list (a row per host
   name, a column per view), Compare (a view's servers against the master list, with a decision per name), Servers,
   Dynamic DNS, History and Settings (account, display, views, and for admins server, for suite admins security and
   global settings). */

// ------------------------------------------------------------------ helpers
const $ = (s, el = document) => el.querySelector(s);
const ICONS = {
  dns: 'M20 13H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1v-6c0-.55-.45-1-1-1zM7 19c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zM20 3H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1V4c0-.55-.45-1-1-1zM7 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
  list: 'M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z',
  compare: 'M10 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h5v2h2V1h-2v2zm0 15H5l5-6v6zm9-15h-5v2h5v13l-5-6v9h5c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2z',
  sync: 'M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46A7.93 7.93 0 0 0 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74A7.93 7.93 0 0 0 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z',
  globe: 'M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zm6.93 6h-2.95a15.65 15.65 0 0 0-1.38-3.56A8.03 8.03 0 0 1 18.92 8zM12 4.04c.83 1.2 1.48 2.53 1.91 3.96h-3.82c.43-1.43 1.08-2.76 1.91-3.96zM4.26 14C4.1 13.36 4 12.69 4 12s.1-1.36.26-2h3.38c-.08.66-.14 1.32-.14 2s.06 1.34.14 2H4.26zm.82 2h2.95c.32 1.25.78 2.45 1.38 3.56A7.987 7.987 0 0 1 5.08 16zm2.95-8H5.08a7.987 7.987 0 0 1 4.33-3.56A15.65 15.65 0 0 0 8.03 8zM12 19.96c-.83-1.2-1.48-2.53-1.91-3.96h3.82c-.43 1.43-1.08 2.76-1.91 3.96zM14.34 14H9.66c-.09-.66-.16-1.32-.16-2s.07-1.35.16-2h4.68c.09.65.16 1.32.16 2s-.07 1.34-.16 2zm.25 5.56c.6-1.11 1.06-2.31 1.38-3.56h2.95a8.03 8.03 0 0 1-4.33 3.56zM16.36 14c.08-.66.14-1.32.14-2s-.06-1.34-.14-2h3.38c.16.64.26 1.31.26 2s-.1 1.36-.26 2h-3.38z',
  history: 'M13 3a9 9 0 0 0-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42A8.954 8.954 0 0 0 13 21a9 9 0 0 0 0-18zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z',
  menu: 'M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z',
  menuOpen: 'M3 18h13v-2H3v2zm0-5h10v-2H3v2zm0-7v2h13V6H3zm18 9.59L17.42 12 21 8.41 19.59 7l-5 5 5 5L21 15.59z',
  pin: 'M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3z',
  search: 'M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z',
  add: 'M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z',
  person: 'M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z',
  settings: 'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z',
  edit: 'M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a.996.996 0 0 0 0-1.41l-2.34-2.34a.996.996 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z',
  delete: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z',
  close: 'M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z',
  check: 'M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z',
  upload: 'M9 16h6v-6h4l-7-7-7 7h4zm-4 2h14v2H5z',
  download: 'M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z',
  logout: 'M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z',
  theme: 'M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.389 5.389 0 0 1-4.4 2.26 5.403 5.403 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z',
  more: 'M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  update: 'M21 10.12h-6.78l2.74-2.82c-2.73-2.7-7.15-2.8-9.88-.1a6.875 6.875 0 0 0 0 9.79 7.02 7.02 0 0 0 9.88 0C18.32 15.65 19 14.08 19 12.1h2c0 1.98-.88 4.55-2.64 6.29-3.51 3.48-9.21 3.48-12.72 0-3.5-3.47-3.53-9.11-.02-12.58a8.987 8.987 0 0 1 12.65 0L21 3v7.12z',
  tune: 'M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 4v-2H11v2h10zm-6-4h2V7h4V5h-4V3h-2v6z',
  vpn: 'M12.65 10C11.83 7.67 9.61 6 7 6c-3.31 0-6 2.69-6 6s2.69 6 6 6c2.61 0 4.83-1.67 5.65-4H17v4h4v-4h2v-4H12.65zM7 14c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
  layers: 'M11.99 18.54l-7.37-5.73L3 14.07l9 7 9-7-1.63-1.27-7.38 5.74zM12 16l7.36-5.73L21 9l-9-7-9 7 1.63 1.27L12 16z',
  play: 'M8 5v14l11-7z',
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
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 4000);
}
const fail = (e) => toast(e.message || String(e));

function dialog(title, body, buttons, wide) {
  return new Promise((resolve) => {
    const back = h('div', { class: 'dialog-back' });
    const close = (v) => { back.remove(); resolve(v); };
    back.addEventListener('click', (e) => { if (e.target === back) close(null); });
    const btns = (buttons || [{ label: 'OK', value: true, primary: true }]).map((b) =>
      h('button', { class: `pillbtn noic ${b.primary ? 'primary' : ''} ${b.danger ? 'danger' : ''}`, onclick: async () => {
        if (typeof b.value !== 'function') { close(b.value); return; }
        try { const v = await b.value(); if (v !== undefined) close(v); } catch (e) { fail(e); }
      } }, b.label));
    back.append(h('div', { class: `dialog ${wide ? 'wide' : ''}`, role: 'dialog' }, h('h2', null, title), body, h('div', { class: 'btns' }, btns)));
    document.body.append(back);
    const f = back.querySelector('input:not([type=checkbox]),select,textarea'); if (f) f.focus();
  });
}
const confirmDialog = (title, text, ok = 'OK', danger = false) => dialog(title, typeof text === 'string' ? h('p', null, text) : text, [{ label: 'Cancel', value: false }, { label: ok, value: true, primary: !danger, danger }]);
const closeDialogs = () => document.querySelectorAll('.dialog-back').forEach((d) => d.remove());

const hue = (s) => { let x = 0; for (const c of s || '') x = (x * 31 + c.charCodeAt(0)) % 360; return x; };
const initials = (fn) => { const p = (fn || '?').trim().split(/\s+/); return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase(); };
const fld = (l, e, hint) => h('label', { class: 'field' }, h('span', null, l), e, hint ? h('small', { class: 'muted' }, hint) : null);
const ago = (iso) => {
  if (!iso) return 'never';
  const s = (Date.now() - new Date(iso.endsWith('Z') || /[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z')) / 1000;
  if (s < 90) return 'just now';
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(iso).toLocaleString();
};

// ------------------------------------------------------------------ state
const S = { status: {}, user: null, suite: [], settings: {}, views: [], servers: [], providers: [], entries: [], ddns: {}, types: ['A', 'AAAA', 'CNAME'], q: '', cmp: {} };
const canEdit = () => S.user && ['editor', 'admin'].includes(S.user.role);
const isAdmin = () => S.user && S.user.role === 'admin';
const kindOf = (k) => S.providers.find((p) => p.kind === k) || { label: k, fields: [], target: true };
const viewOf = (slug) => S.views.find((v) => v.slug === slug) || { slug, name: slug };
const tailscales = () => S.servers.filter((s) => s.kind === 'tailscale');
const cftunnels = () => S.servers.filter((s) => s.kind === 'cftunnel');
/** A record's value as shown: a tunnel's "home|http://…" as "home → http://…". */
const fmtVal = (r) => r.type === 'TUNNEL' ? r.value.replace('|', ' → ') : r.value;

async function loadOverview() {
  const o = await api('/api/overview');
  Object.assign(S, { views: o.views, servers: o.servers, providers: o.providers, ddns: o.ddns, types: o.types });
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
    let theme = 'system'; try { theme = localStorage.getItem('iodns.theme') || 'system'; } catch { /* */ }
    menu = h('div', { class: 'menu' },
      h('div', { class: 'who' }, h('b', null, S.user.displayName), h('div', { class: 'muted small' }, `${S.user.name} · ${S.user.role}`)),
      h('a', { class: 'mi', href: '#/settings/account', onclick: closeMenu }, icon('person', 's'), 'Account'),
      h('button', { class: 'mi', onclick: () => { const n = { system: 'light', light: 'dark', dark: 'system' }[theme]; applyTheme(n); closeMenu(); toast(`Appearance: ${n}`); } },
        icon('theme', 's'), `Appearance: ${theme}`),
      h('a', { class: 'mi', href: '#/settings', onclick: closeMenu }, icon('settings', 's'), 'Settings'),
      h('button', { class: 'mi', onclick: async () => { const r = await api('/api/auth/logout', { method: 'POST' }); if (r && r.cloudflareLogout) location.href = r.cloudflareLogout; else location.reload(); } }, icon('logout', 's'), 'Sign out'));
    m.append(menu);
    setTimeout(() => document.addEventListener('click', outside), 0);
  };
  m.append(btn);
}
/* The suite (iosuite-shared's suite_apps): when other ioThing apps are registered, the app mark opens a menu of them. */
async function loadSuite() {
  try { const r = await api('/api/auth/suite'); S.suite = (r.items || []).filter((a) => a.app !== r.app && a.url); } catch { S.suite = []; }
  const b = $('#suitebtn');
  if (b) { b.hidden = !S.suite.length; b.onclick = () => toggleSuite(b); }
  drawNav();
}
let suitePop = null;
function closeSuite() {
  if (!suitePop) return;
  suitePop.remove(); suitePop = null;
  document.removeEventListener('click', suiteOutside, true);
}
function suiteOutside(e) { if (suitePop && !suitePop.contains(e.target) && !e.target.closest('.suitebtn')) closeSuite(); }
function appTile(a) {
  const mark = (a.name || a.app).replace(/^io(?=[A-Z])/, '').slice(0, 1).toUpperCase();
  const fallback = () => h('span', { class: 'appic fb', style: { background: a.color || 'var(--brand)' } }, mark);
  const ic = a.icon ? h('img', { class: 'appic', src: a.icon, alt: '', onerror: (e) => e.currentTarget.replaceWith(fallback()) }) : fallback();
  return h('a', { class: 'apptile', href: a.url, role: 'menuitem', title: a.description || a.name, onclick: closeSuite }, ic, h('span', { class: 'appnm' }, a.name || a.app));
}
function toggleSuite(btn) {
  if (suitePop) { closeSuite(); return; }
  if (!S.suite.length) return;
  suitePop = h('div', { class: 'suitepop', role: 'menu', 'aria-label': 'ioThing apps', style: { '--cols': String(Math.min(3, S.suite.length)) } }, S.suite.map(appTile));
  document.body.append(suitePop);
  const r = btn.getBoundingClientRect();
  suitePop.style.top = `${Math.round(r.bottom + 6)}px`;
  suitePop.style.left = `${Math.round(Math.max(8, Math.min(r.left - 6, innerWidth - suitePop.offsetWidth - 8)))}px`;
  setTimeout(() => document.addEventListener('click', suiteOutside, true), 0);
}
function applyTheme(choice) {
  try { if (choice) localStorage.setItem('iodns.theme', choice); } catch { /* private mode */ }
  let t = choice; try { t = t || localStorage.getItem('iodns.theme'); } catch { /* */ }
  t = t || 'system';
  if (t === 'system') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
  if (choice && S.user) saveSettings({ theme: choice });
}

/* The sidebar: the master list, Compare for each view (with how many names differ), servers, dynamic DNS, history,
   Settings. Docked beside the page on a wide screen, sliding over it otherwise, a bottom bar on a phone. */
const DOCK_MIN = 1100;
function drawNav() {
  const nav = $('#nav'); if (!S.user) return;
  const r = route();
  const link = (v, href, ic, label, n, on, hueVar, warn) => h('a', { href, 'data-v': v, class: [on ? 'on' : '', warn ? 'warnn' : ''].join(' '), style: hueVar ? { '--hue': `var(${hueVar})` } : null },
    icon(ic), h('span', { class: 'nl' }, label), n ? h('span', { class: 'n' }, n) : null);
  const sec = (label) => h('div', { class: 'navsec' }, h('span', null, label));
  const diffs = (slug) => { const ss = S.servers.filter((s) => s.view === slug && s.target && s.enabled); const n = ss.reduce((a, s) => a + (s.check.differences || 0), 0); const bad = ss.some((s) => s.check.ok === false); return { n, bad, any: ss.some((s) => s.check.at) }; };
  const brandName = h('span', { class: 'brand-name' }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'DNS'));
  nav.replaceChildren(...[
    h('div', { class: 'navhead' },
      S.suite.length
        ? h('div', { class: 'brand' }, h('button', { class: 'suitebtn', title: 'ioThing apps', 'aria-label': 'ioThing apps', onclick: (e) => toggleSuite(e.currentTarget) },
          h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' })), h('a', { class: 'brand-name', href: '#/' }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'DNS')))
        : h('a', { class: 'brand', href: '#/' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }), brandName),
      h('button', { id: 'sidebtn', class: 'iconbtn', onclick: sidebarButton })),
    link('records', '#/', 'list', 'Records', null, r.view === 'records', '--c-teal'),
    link('compare', `#/compare/${r.view === 'compare' ? r.slug : (S.views[0] || {}).slug || 'internal'}`, 'compare', 'Compare', null, r.view === 'compare', '--c-indigo'),
    link('servers', '#/servers', 'dns', 'Servers', S.servers.length || null, r.view === 'servers', '--c-blue'),
    link('ddns', '#/ddns', 'globe', 'Dynamic DNS', null, r.view === 'ddns', '--c-orange'),
    h('button', { class: 'navmore', 'data-v': 'more', title: 'More', onclick: moreSheet }, icon('more'), h('span', { class: 'nl' }, 'More')),
    h('div', { class: 'navgap' }), sec('Views'),
    S.views.map((v) => { const d = diffs(v.slug); return link('view', `#/compare/${v.slug}`, 'layers', v.name, d.any ? (d.bad ? '!' : d.n ? String(d.n) : '✓') : null, r.view === 'compare' && r.slug === v.slug, null, d.bad || d.n); }),
    h('div', { class: 'navgap' }),
    link('history', '#/history', 'history', 'History', null, r.view === 'history', '--c-slate'),
    h('div', { class: 'navfoot' }, link('settings', '#/settings', 'settings', 'Settings', null, r.view === 'settings')),
  ].flat(3).filter(Boolean));
  applySidebar();
  $('.navmore')?.classList.toggle('on', ['history', 'settings'].includes(r.view));
}
function sideDockedPref() { try { return localStorage.getItem('iodns.sidebar') !== '0'; } catch { return true; } }
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
  if (document.body.classList.contains('side-docked')) { try { localStorage.setItem('iodns.sidebar', '0'); } catch { /* */ } }
  else if (innerWidth >= DOCK_MIN) { try { localStorage.setItem('iodns.sidebar', '1'); } catch { /* */ } }
  else { closeNav(); return; }
  applySidebar();
}
function openNav() { document.body.classList.add('side-open'); $('#navscrim').hidden = false; }
function closeNav() { document.body.classList.remove('side-open'); $('#navscrim').hidden = true; }
function moreSheet() {
  const tile = (href, ic, label, hueV) => h('a', { href, style: { '--hue': hueV } }, h('span', { class: 'sic' }, icon(ic)), h('span', null, label));
  const grid = h('div', { class: 'sheetgrid' }, S.views.map((v) => tile(`#/compare/${v.slug}`, 'layers', `Compare ${v.name}`, 'var(--c-indigo)')),
    tile('#/history', 'history', 'History', 'var(--c-slate)'), tile('#/settings', 'settings', 'Settings', 'var(--c-slate)'));
  grid.addEventListener('click', (e) => { if (e.target.closest('a')) closeDialogs(); });
  return dialog('More', grid, [{ label: 'Close', value: null }]);
}

// ------------------------------------------------------------------ routes
function route() {
  const p = location.hash.replace(/^#\/?/, '').split('?')[0].split('/').map(decodeURIComponent);
  const [a, b, c] = p;
  if (!a) return { view: 'records' };
  if (a === 'compare') return { view: 'compare', slug: b || (S.views[0] || {}).slug || 'internal' };
  if (['servers', 'ddns', 'history'].includes(a)) return { view: a };
  if (a === 'settings') return { view: 'settings', tab: b || 'account', sub: c };
  return { view: 'records' };
}
async function onRoute() {
  const r = route();
  const main = $('#main');
  const page = h('div', { class: 'page' });
  main.replaceChildren(page);
  $('#newbtn').hidden = !(canEdit() && r.view === 'records');
  $('#search').hidden = !['records', 'compare'].includes(r.view);
  try {
    await ({ records: showRecords, compare: showCompare, servers: showServers, ddns: showDdns, history: showHistory, settings: showSettings })[r.view](page, r);
  } catch (e) { page.append(h('p', { class: 'warn' }, e.message)); }
  drawNav();
}

// ------------------------------------------------------------------ records (the master list)
const SRC_LABEL = (src) => {
  if (!src) return null;
  if (src === 'publicip') return 'public IPv4';
  if (src === 'publicip6') return 'public IPv6';
  if (src.startsWith('tailscale:')) return `tailnet: ${src.split(':').slice(2).join(':')}`;
  return src;
};
const recChip = (r) => h('span', { class: `rec t-${r.type}`, title: r.source ? `Follows ${SRC_LABEL(r.source)}` : (r.ttl ? `TTL ${r.ttl}s` : '') },
  h('b', null, r.type), h('span', { class: 'v' }, fmtVal(r)), r.source ? h('span', { class: 'src' }, r.source.startsWith('tailscale') ? 'TS' : 'IP') : null);
const matches = (e, q) => !q || e.name.includes(q) || (e.comment || '').toLowerCase().includes(q) || Object.values(e.records).flat().some((r) => r.value.includes(q));

async function showRecords(page) {
  S.entries = (await api('/api/entries')).items;
  const body = h('div');
  const draw = () => {
    const q = S.q.toLowerCase();
    const items = S.entries.filter((e) => matches(e, q));
    if (!S.entries.length) {
      body.replaceChildren(h('div', { class: 'empty' }, icon('dns'), h('p', null, 'The master list is empty.'),
        h('p', null, S.servers.some((s) => s.target) ? ['Bring in what a server already holds: ', h('a', { class: 'lnk', href: '#/servers' }, 'Servers › Import'), ', or add an entry with New.']
          : ['Start by adding your DNS servers under ', h('a', { class: 'lnk', href: '#/servers' }, 'Servers'), ', then import from one of them.'])));
      return;
    }
    body.replaceChildren(h('div', { class: 'tablewrap' }, h('table', { class: 't recs' },
      h('thead', null, h('tr', null, h('th', null, `Name (${items.length})`), S.views.map((v) => h('th', null, v.name)), h('th', null, 'Note'), canEdit() ? h('th', null) : null)),
      h('tbody', null, items.map((e) => h('tr', { class: canEdit() ? 'click' : null, onclick: canEdit() ? (ev) => { if (!ev.target.closest('button')) editEntry(e); } : null },
        h('td', { class: 'nm' }, e.name),
        S.views.map((v) => h('td', null, (e.records[v.slug] || []).map(recChip))),
        h('td', { class: 'muted small' }, e.comment),
        canEdit() ? h('td', { class: 'act' }, h('button', { class: 'iconbtn', title: 'Edit', onclick: () => editEntry(e) }, icon('edit', 's'))) : null))))));
  };
  S.redraw = draw;
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Records'),
    h('span', { class: 'muted' }, 'One row per name, one column per view. A value marked TS follows a Tailscale device, IP the public address; TUNNEL is a Cloudflare Tunnel public hostname.')), body);
  draw();
}

/** The entry form: the name, a note, and for each view its records (type, then a typed value, the public address or a
    Tailscale device). */
async function editEntry(e) {
  const isNew = !e;
  e = e || { name: '', comment: '', records: {} };
  const name = h('input', { class: 't', value: e.name, placeholder: 'calendar.example.com', autocapitalize: 'none', spellcheck: 'false' });
  const comment = h('input', { class: 't', value: e.comment || '', placeholder: 'What it is (optional)' });
  const ts = tailscales();
  const devices = {};
  const loadDevices = async (sid) => { if (!devices[sid]) devices[sid] = api(`/api/servers/${sid}/devices`).then((r) => r.items).catch((x) => { fail(x); return []; }); return devices[sid]; };
  let tunnelNames = null;
  const loadTunnels = () => tunnelNames = tunnelNames || Promise.all(cftunnels().map((s) => api(`/api/servers/${s.id}/tunnels`).then((r) => r.items).catch((x) => { fail(x); return []; })))
    .then((ls) => [...new Set(ls.flat().filter((t) => t.remote).map((t) => t.name))]);
  const rows = {};
  const viewBox = (v) => {
    const list = h('div', { class: 'reclist' });
    rows[v.slug] = [];
    const addRow = (r) => {
      r = r || { type: 'A', value: '', source: null };
      const type = h('select', { class: 't type' }, S.types.map((t) => h('option', { value: t, selected: t === r.type ? true : null }, t)));
      const value = h('input', { class: 't val', value: r.source || r.type === 'TUNNEL' ? '' : r.value, placeholder: '192.168.1.10 / host.example.com', autocapitalize: 'none', spellcheck: 'false' });
      const srcOpts = [['', 'Typed'], ['publicip', 'Public address'], ...ts.map((s) => [`tailscale:${s.id}`, `Tailscale device (${s.name})`])];
      const cur = r.source ? (r.source.startsWith('tailscale:') ? r.source.split(':').slice(0, 2).join(':') : 'publicip') : '';
      const src = h('select', { class: 't src' }, srcOpts.map(([k, l]) => h('option', { value: k, selected: k === cur ? true : null }, l)));
      const dev = h('select', { class: 't dev', hidden: true });
      const [tName, tService] = r.type === 'TUNNEL' ? [r.value.split('|')[0], r.value.split('|').slice(1).join('|')] : ['', ''];
      const tun = h('select', { class: 't dev', hidden: true });
      const svc = h('input', { class: 't val', hidden: true, value: tService, placeholder: 'http://192.168.1.151:8620', autocapitalize: 'none', spellcheck: 'false' });
      let tunFilled = false;
      const fillTunnels = async () => {
        if (tunFilled) return; tunFilled = true;
        tun.replaceChildren(h('option', { value: '' }, 'Loading…'));
        const names = await loadTunnels();
        if (tName && !names.includes(tName)) names.push(tName);
        tun.replaceChildren(h('option', { value: '' }, names.length ? 'Pick a tunnel' : 'No tunnel: add a Cloudflare Tunnel server'), ...names.map((n) => h('option', { value: n, selected: n === tName ? true : null }, n)));
      };
      const fillDevices = async () => {
        const sid = src.value.split(':')[1];
        const want = r.source && r.source.startsWith(`tailscale:${sid}:`) ? r.source.split(':').slice(2).join(':') : '';
        dev.replaceChildren(h('option', { value: '' }, 'Loading…'));
        const items = await loadDevices(sid);
        dev.replaceChildren(h('option', { value: '' }, 'Pick a device'), ...items.map((d) => h('option', { value: d.name, selected: d.name === want ? true : null }, `${d.name} (${type.value === 'AAAA' ? d.ipv6 || 'no IPv6' : d.ipv4 || 'no IPv4'})`)));
      };
      const sync = () => {
        const isT = type.value === 'TUNNEL';
        tun.hidden = svc.hidden = !isT;
        if (isT) { fillTunnels(); src.value = ''; src.hidden = true; value.hidden = true; dev.hidden = true; return; }
        src.hidden = false;
        const s = src.value;
        value.hidden = !!s; dev.hidden = !s.startsWith('tailscale:');
        if (s.startsWith('tailscale:')) fillDevices();
        if (s === 'publicip' && !['A', 'AAAA'].includes(type.value)) type.value = 'A';
        src.disabled = type.value === 'CNAME';
        if (type.value === 'CNAME') { src.value = ''; value.hidden = false; dev.hidden = true; }
      };
      src.onchange = sync; type.onchange = sync;
      const row = { type, value, src, dev, tun, svc };
      row.el = h('div', { class: 'recrow' }, type, src, value, dev, tun, svc, h('button', { class: 'iconbtn', title: 'Remove', onclick: () => { row.el.remove(); rows[v.slug].splice(rows[v.slug].indexOf(row), 1); } }, icon('close', 's')));
      rows[v.slug].push(row); list.append(row.el);
      sync();
    };
    (e.records[v.slug] || []).forEach(addRow);
    return h('div', { class: 'vsec' }, h('div', { class: 'vsech' }, icon('layers', 's'), h('b', null, v.name),
      h('button', { class: 'pillbtn tiny', onclick: () => addRow() }, icon('add', 's'), 'Add a record')),
      v.description ? h('p', { class: 'muted small desc' }, v.description) : null, list);
  };
  const collect = () => {
    const recs = {};
    for (const [slug, rs] of Object.entries(rows)) {
      recs[slug] = rs.map((r) => {
        if (r.type.value === 'TUNNEL') {
          if (!r.svc.value.trim()) return {};
          if (!r.tun.value) throw new Error('Pick the tunnel');
          return { type: 'TUNNEL', value: `${r.tun.value}|${r.svc.value.trim()}` };
        }
        const s = r.src.value;
        if (s === 'publicip') return { type: r.type.value, source: r.type.value === 'AAAA' ? 'publicip6' : 'publicip' };
        if (s.startsWith('tailscale:')) { if (!r.dev.value) throw new Error('Pick the Tailscale device'); return { type: r.type.value, source: `${s}:${r.dev.value}` }; }
        return { type: r.type.value, value: r.value.value.trim() };
      }).filter((r) => r.source || r.value);
    }
    return { name: name.value.trim(), comment: comment.value.trim(), records: recs };
  };
  const body = h('div', { class: 'pform' }, h('div', { class: 'grid' }, fld('Name', name), fld('Note', comment)), S.views.map(viewBox),
    h('p', { class: 'muted small' }, 'A view without records leaves that name out of its servers (an internal-only name never reaches public DNS). Saving changes the master list only: Compare pushes it.'));
  const buttons = [
    !isNew ? { label: 'Delete', danger: true, value: async () => { if (!await confirmDialog('Delete', `Take ${e.name} out of the master list? The servers keep it until you push (Compare › Delete everywhere removes it from them too).`, 'Delete', true)) return undefined; await api(`/api/entries/${e.id}`, { method: 'DELETE' }); return 'deleted'; } } : null,
    { label: 'Cancel', value: null },
    { label: isNew ? 'Add' : 'Save', primary: true, value: async () => api(isNew ? '/api/entries' : `/api/entries/${e.id}`, { method: isNew ? 'POST' : 'PUT', json: collect() }) },
  ].filter(Boolean);
  const r = await dialog(isNew ? 'New entry' : e.name, body, buttons, true);
  if (r) { toast(r === 'deleted' ? 'Deleted' : 'Saved: Compare to push it'); if (route().view === 'records') onRoute(); }
}

// ------------------------------------------------------------------ compare and push
const STATE = { same: ['ok', 'In step'], missing: ['missing', 'Missing'], extra: ['extra', 'Only on the server'], different: ['diff', 'Different'],
  unreachable: ['unr', 'Unreachable'], outside: ['out', 'Not its zone'], ok: ['ok', 'In step'] };
async function showCompare(page, r) {
  const v = viewOf(r.slug);
  const head = h('div', { class: 'pagehead' }, h('h1', null, `Compare: ${v.name}`));
  const tabs = h('div', { class: 'tabs' }, S.views.map((x) => h('button', { class: x.slug === v.slug ? 'on' : '', onclick: () => { location.hash = `#/compare/${x.slug}`; } }, x.name)));
  const out = h('div', null, h('p', { class: 'muted' }, 'Reading every server of this view…'));
  page.append(head, tabs, out);
  let st;
  try { st = await api(`/api/sync/${encodeURIComponent(v.slug)}`); } catch (e) { out.replaceChildren(h('p', { class: 'warn' }, e.message)); return; }
  api('/api/servers').then((x) => { S.servers = x.items; drawNav(); }).catch(() => {});
  if (!st.servers.length) {
    out.replaceChildren(h('div', { class: 'empty' }, icon('dns'), h('p', null, `No server answers for the ${v.name} view yet.`), isAdmin() ? h('a', { class: 'pillbtn primary', href: '#/servers' }, icon('add', 's'), 'Add a server') : null));
    return;
  }
  const decisions = {};
  let onlyDiff = S.cmp.onlyDiff ?? true;
  const servers = st.servers;
  const summary = h('div', { class: 'srvchips' }, servers.map((s) => h('span', { class: `chip srv ${s.ok ? (s.differences ? 'diff' : 'ok') : 'unr'}`, title: s.ok ? `${s.count} records` : s.error },
    h('span', { class: 'dot' }), h('b', null, s.name), h('span', { class: 'lab' }, s.ok ? (s.differences ? `${s.differences} to fix` : 'in step') : 'unreachable'))));
  const notes = st.notes && st.notes.length ? h('p', { class: 'muted small' }, st.notes.join(' · ')) : null;
  const errors = servers.filter((s) => !s.ok).map((s) => h('p', { class: 'warn' }, `${s.name}: ${s.error}`));
  const applyBtn = h('button', { class: 'pillbtn primary', disabled: true, onclick: () => run(false) }, icon('play', 's'), 'Apply');
  const count = () => Object.values(decisions).filter((d) => d && d !== 'skip').length;
  const refreshBtn = () => { const n = count(); applyBtn.disabled = !n || !canEdit(); applyBtn.lastChild.textContent = n ? `Apply ${n} change${n > 1 ? 's' : ''}` : 'Apply'; };
  const choice = (row) => {
    const opts = [['skip', 'Leave as it is']];
    if (row.master.length) opts.unshift(['master', 'Use the master list']);
    servers.forEach((s) => { const c = row.servers[s.id]; if (c && c.records.length && c.state !== 'same') opts.push([`server:${s.id}`, `Use ${s.name}'s`]); });
    opts.push(['delete', 'Delete everywhere']);
    const sel = h('select', { class: 't', disabled: !canEdit() }, opts.map(([k, l]) => h('option', { value: k, selected: k === (decisions[row.name] ?? row.default) ? true : null }, l)));
    decisions[row.name] = decisions[row.name] ?? row.default;
    sel.onchange = () => { decisions[row.name] = sel.value; refreshBtn(); };
    return sel;
  };
  const table = h('div', { class: 'tablewrap' });
  const draw = () => {
    const q = S.q.toLowerCase();
    const rows = st.rows.filter((x) => (!onlyDiff || x.state !== 'ok') && (!q || x.name.includes(q)));
    table.replaceChildren(rows.length ? h('table', { class: 't cmp' },
      h('thead', null, h('tr', null, h('th', null, `Name (${rows.length})`), h('th', null, 'Master list'), servers.map((s) => h('th', null, s.name)), h('th', null, 'Resolve'))),
      h('tbody', null, rows.map((x) => h('tr', { class: `st-${STATE[x.state][0]}` },
        h('td', { class: 'nm' }, x.name, h('div', { class: `badge b-${STATE[x.state][0]}` }, STATE[x.state][1])),
        h('td', null, x.master.length ? x.master.map(recChip) : h('span', { class: 'muted small' }, 'none')),
        servers.map((s) => { const c = x.servers[s.id] || { state: 'unreachable', records: [] }; return h('td', { class: `cell c-${STATE[c.state][0]}`, title: STATE[c.state][1] },
          c.state === 'same' ? h('span', { class: 'okmark' }, icon('check', 's')) : c.records.length ? c.records.map(recChip) : h('span', { class: 'muted small' }, STATE[c.state][1])); }),
        h('td', null, x.state === 'ok' ? null : choice(x))))))
      : h('div', { class: 'empty' }, icon('check'), h('p', null, onlyDiff ? 'Every server of this view holds the master list.' : 'Nothing here.')));
    refreshBtn();
  };
  const only = h('input', { type: 'checkbox', checked: onlyDiff, onchange: () => { onlyDiff = S.cmp.onlyDiff = only.checked; draw(); } });
  const prune = h('input', { type: 'checkbox' });
  async function run(all) {
    const path = all ? `/api/sync/${v.slug}/push` : `/api/sync/${v.slug}/apply`;
    const payload = all ? { prune: prune.checked } : { decisions };
    let preview;
    try { preview = await api(path, { method: 'POST', json: { ...payload, dryRun: true } }); } catch (e) { fail(e); return; }
    const masterChanges = Object.entries(preview.master || {});
    const ops = preview.servers.flatMap((s) => s.ops.map((o) => ({ ...o, server: s.name })));
    if (!ops.length && !masterChanges.length) { toast('Nothing to change'); return; }
    const opline = (o) => h('li', null, h('b', null, o.server), ': ', { add: 'add', delete: 'remove', update: 'change' }[o.op], ' ', h('code', null, `${o.name} ${o.type} ${fmtVal(o)}`), o.was ? h('span', { class: 'muted' }, ` (was ${fmtVal({ type: o.type, value: o.was })})`) : null);
    const body = h('div', null,
      masterChanges.length ? [h('h3', null, 'The master list'), h('ul', { class: 'ops' }, masterChanges.map(([n, rs]) => h('li', null, h('code', null, n), ' ← ', rs.length ? rs.map((x) => `${x.type} ${fmtVal(x)}`).join(', ') : 'removed')))] : null,
      ops.length ? [h('h3', null, 'The servers'), h('ul', { class: 'ops' }, ops.map(opline))] : null);
    if (!await confirmDialog(all ? 'Push the master list' : 'Apply these changes', body, `Apply ${ops.length + masterChanges.length}`)) return;
    applyBtn.disabled = true;
    try {
      const res = await api(path, { method: 'POST', json: payload });
      const errs = res.servers.flatMap((s) => s.errors.map((e) => `${s.name}: ${e}`));
      if (errs.length) await dialog('Some changes failed', h('ul', { class: 'ops' }, errs.map((e) => h('li', { class: 'warn' }, e))));
      else toast(`Done: ${res.servers.reduce((a, s) => a + s.ops.length, 0)} change(s) on the servers`);
    } catch (e) { fail(e); }
    onRoute();
  }
  out.replaceChildren(...[summary, notes, ...errors].filter(Boolean),
    h('div', { class: 'cmpbar' }, h('label', { class: 'check' }, only, ' Only what differs'), h('span', { class: 'grow' }),
      h('button', { class: 'pillbtn', onclick: () => onRoute() }, icon('sync', 's'), 'Compare again'),
      canEdit() ? [h('label', { class: 'check', title: 'Also remove the names only the servers hold' }, prune, ' and remove extras'),
        h('button', { class: 'pillbtn', onclick: () => run(true) }, icon('upload', 's'), 'Push all'), applyBtn] : null),
    table);
  draw();
  S.redraw = draw;
}

// ------------------------------------------------------------------ servers
async function showServers(page) {
  await loadOverview();
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Servers'),
    isAdmin() ? h('button', { class: 'pillbtn primary', onclick: () => editServer(null) }, icon('add', 's'), 'Add a server') : null));
  if (!S.servers.length) {
    page.append(h('div', { class: 'empty' }, icon('dns'), h('p', null, 'No DNS server yet.'), h('p', { class: 'muted' }, 'AdGuard Home, Pi-hole, UniFi gateways and Cloudflare are kept in step; Tailscale gives device addresses and split DNS.')));
    return;
  }
  for (const v of [...S.views, { slug: null, name: 'Sources' }]) {
    const ss = S.servers.filter((s) => (v.slug ? s.view === v.slug && s.target : !s.target));
    if (!ss.length) continue;
    page.append(h('h2', { class: 'sech' }, v.slug ? `${v.name} view` : 'Sources'), h('div', { class: 'cards' }, ss.map(serverCard)));
  }
}
function serverCard(s) {
  const st = s.check.ok === null ? 'unk' : s.check.ok ? (s.check.differences ? 'diff' : 'ok') : 'unr';
  const msg = h('div', { class: 'muted small' }, s.check.at ? `${s.check.ok ? (s.check.differences != null ? (s.check.differences ? `${s.check.differences} name(s) differ` : 'In step with the master list') : s.check.message) : s.check.message} · ${ago(s.check.at)}` : 'Not checked yet');
  const test = async () => { msg.textContent = 'Testing…'; try { const r = await api(`/api/servers/${s.id}/test`, { method: 'POST' }); msg.textContent = r.message; msg.className = r.ok ? 'small' : 'warn small'; } catch (e) { msg.textContent = e.message; } };
  return h('div', { class: `card srvcard s-${st}` + (s.enabled ? '' : ' off') },
    h('h3', null, h('span', { class: 'dot' }), s.name, h('span', { class: 'muted small kind' }, s.kindLabel)),
    h('div', { class: 'small' }, s.url || '', s.enabled ? null : h('b', null, ' · off')),
    msg,
    h('div', { class: 'cardbtns' },
      isAdmin() ? h('button', { class: 'pillbtn noic', onclick: test }, 'Test') : null,
      s.target && canEdit() ? h('button', { class: 'pillbtn noic', onclick: () => importDialog(s) }, 'Import') : null,
      s.kind === 'tailscale' && isAdmin() ? h('button', { class: 'pillbtn noic', onclick: () => splitDns(s) }, 'Split DNS') : null,
      isAdmin() ? h('button', { class: 'pillbtn noic', onclick: () => editServer(s) }, 'Edit') : null));
}

async function editServer(s) {
  const isNew = !s;
  const kinds = S.providers;
  const kind = h('select', { class: 't', disabled: !isNew }, kinds.map((k) => h('option', { value: k.kind, selected: s && s.kind === k.kind ? true : null }, k.label)));
  const name = h('input', { class: 't', value: s ? s.name : '', placeholder: 'AdGuard 1' });
  const view = h('select', { class: 't' }, S.views.map((v) => h('option', { value: v.slug, selected: (s ? s.view : 'internal') === v.slug ? true : null }, v.name)));
  const enabled = h('input', { type: 'checkbox', checked: s ? s.enabled : true });
  const fieldsBox = h('div', { class: 'grid' });
  const status = h('p', { class: 'muted small' });
  let inputs = {};
  const drawFields = () => {
    const k = kindOf(kind.value);
    inputs = {};
    const opts = s ? s.options : {};
    const show = [];
    for (const f of k.fields) {
      let el;
      const cur = f.key === 'url' ? (s ? s.url : '') || f.default || '' : opts[f.key] ?? f.default ?? '';
      if (f.type === 'password') el = h('input', { class: 't', type: 'password', autocomplete: 'new-password', placeholder: s && s.secretSet ? 'Kept (type to replace)' : '' });
      else if (f.type === 'check') el = h('input', { type: 'checkbox', checked: !!cur });
      else if (f.type === 'select') el = h('select', { class: 't' }, f.options.map(([v, l]) => h('option', { value: v, selected: v === cur ? true : null }, l)));
      else el = h('input', { class: 't', value: cur, placeholder: f.hint || '', autocapitalize: 'none', spellcheck: 'false' });
      inputs[f.key] = { f, el };
      const wrap = f.type === 'check' ? h('label', { class: 'check full' }, el, ' ', f.label) : fld(f.label, el, f.type !== 'text' && f.type !== 'url' ? f.hint : null);
      inputs[f.key].wrap = wrap;
      show.push(wrap);
    }
    fieldsBox.replaceChildren(...show);
    const when = () => { for (const { f, wrap } of Object.values(inputs)) if (f.when) wrap.hidden = !Object.entries(f.when).every(([kk, vv]) => inputs[kk] && inputs[kk].el.value === vv); };
    for (const { el } of Object.values(inputs)) el.addEventListener('change', when);
    when();
    view.closest('label').hidden = !k.target;
    if (!name.value) name.placeholder = k.label;
  };
  const collect = () => {
    const b = { kind: kind.value, name: name.value.trim() || kindOf(kind.value).label, enabled: enabled.checked, options: {} };
    if (kindOf(kind.value).target) b.view = view.value;
    for (const [key, { f, el }] of Object.entries(inputs)) {
      const v = f.type === 'check' ? el.checked : el.value.trim();
      if (key === 'url') b.url = v;
      else if (key === 'secret') { if (v) b.secret = v; }
      else b.options[key] = v;
    }
    return b;
  };
  const body = h('div', { class: 'pform' }, h('div', { class: 'grid' }, fld('Kind', kind), fld('Name', name), fld('View', view, 'which answers this server gives')), fieldsBox,
    h('label', { class: 'check' }, enabled, ' Kept in step (off: left out of comparisons and pushes)'), status,
    h('p', { class: 'muted small' }, 'The password or key is kept with the suite\'s keys and tokens (Settings › Global settings), never shown again.'));
  kind.onchange = drawFields;
  drawFields();
  const testIt = async () => { status.textContent = 'Testing…'; status.className = 'muted small'; try { const r = await api('/api/servers/test', { method: 'POST', json: { ...collect(), id: s ? s.id : null } }); status.textContent = r.message; status.className = r.ok ? 'okmsg small' : 'warn small'; } catch (e) { status.textContent = e.message; status.className = 'warn small'; } return undefined; };
  const r = await dialog(isNew ? 'Add a DNS server' : s.name, body, [
    !isNew ? { label: 'Remove', danger: true, value: async () => { if (!await confirmDialog('Remove', `Forget ${s.name}? Nothing on the server itself changes.`, 'Remove', true)) return undefined; await api(`/api/servers/${s.id}`, { method: 'DELETE' }); return 'removed'; } } : null,
    { label: 'Test', value: testIt },
    { label: 'Cancel', value: null },
    { label: isNew ? 'Add' : 'Save', primary: true, value: () => api(isNew ? '/api/servers' : `/api/servers/${s.id}`, { method: isNew ? 'POST' : 'PATCH', json: collect() }) },
  ].filter(Boolean), true);
  if (r) { toast(r === 'removed' ? 'Removed' : 'Saved'); onRoute(); }
}

async function importDialog(s) {
  const mode = h('div', { class: 'radios' }, [
    ['merge', 'Merge', 'Add the names the master list lacks; where both have a name, the master list stays.'],
    ['overwrite', 'Merge, the server wins', 'As Merge, but where both have a name, take the server\'s records.'],
    ['replace', 'Replace', `The ${viewOf(s.view).name} records of the master list become exactly ${s.name}'s.`]].map(([v, l, d], i) =>
    h('label', { class: 'radio' }, h('input', { type: 'radio', name: 'mode', value: v, checked: i === 0 }), h('span', null, h('b', null, l), h('br'), h('span', { class: 'muted small' }, d)))));
  const ok = await confirmDialog(`Import from ${s.name}`, h('div', null, h('p', null, `Load the master list's ${viewOf(s.view).name} records from ${s.name}. The servers are not changed (Compare pushes).`), mode), 'Import');
  if (!ok) return;
  try {
    const r = await api(`/api/servers/${s.id}/import`, { method: 'POST', json: { mode: mode.querySelector('input:checked').value } });
    toast(`${r.records} records read: ${r.added} added, ${r.changed} changed, ${r.removed} removed`);
    location.hash = '#/';
  } catch (e) { fail(e); }
}

async function splitDns(s) {
  let cur = {};
  try { cur = (await api(`/api/servers/${s.id}/split-dns`)).domains || {}; } catch (e) { fail(e); return; }
  const domain = h('input', { class: 't', placeholder: 'example.com', autocapitalize: 'none' });
  const ns = h('input', { class: 't', placeholder: '100.101.102.103 (the tailnet address of the DNS server)' });
  const list = h('table', { class: 't' }, Object.entries(cur).map(([d, v]) => h('tr', null, h('td', null, d), h('td', null, (v || []).join(', ')),
    h('td', null, h('button', { class: 'pillbtn noic tiny', onclick: async () => { try { await api(`/api/servers/${s.id}/split-dns`, { method: 'PUT', json: { domain: d, nameservers: [] } }); toast(`${d}: off`); closeDialogs(); } catch (e) { fail(e); } } }, 'Stop')))));
  const r = await dialog('Tailscale split DNS', h('div', { class: 'pform' },
    h('p', { class: 'muted' }, 'Devices on the tailnet ask these name servers for these domains. Point your domain at the DNS server that holds the Tailscale view.'),
    Object.keys(cur).length ? list : h('p', { class: 'muted small' }, 'No split DNS yet.'),
    h('div', { class: 'grid' }, fld('Domain', domain), fld('Name server', ns))), [
    { label: 'Close', value: null },
    { label: 'Save', primary: true, value: () => api(`/api/servers/${s.id}/split-dns`, { method: 'PUT', json: { domain: domain.value.trim(), nameservers: ns.value.split(',').map((x) => x.trim()).filter(Boolean) } }) }], true);
  if (r) toast('Split DNS saved');
}

// ------------------------------------------------------------------ dynamic DNS
async function showDdns(page) {
  const d = await api('/api/ddns');
  const unifi = S.servers.filter((s) => s.kind === 'unifi');
  const entries = (await api('/api/entries')).items.filter((e) => Object.values(e.records).flat().some((r) => r.source === 'publicip' || r.source === 'publicip6'));
  const detect = h('select', { class: 't', disabled: !isAdmin() },
    h('option', { value: 'auto', selected: d.detect === 'auto' ? true : null }, 'Ask an address service (ipify, icanhazip)'),
    unifi.map((s) => h('option', { value: `unifi:${s.id}`, selected: d.detect === `unifi:${s.id}` ? true : null }, `The WAN address of ${s.name}`)),
    h('option', { value: 'url', selected: d.detect.startsWith('http') ? true : null }, 'This page…'));
  const url = h('input', { class: 't', value: d.detect.startsWith('http') ? d.detect : '', placeholder: 'https://… (answers with the address alone)', hidden: !d.detect.startsWith('http') });
  const minutes = h('input', { class: 't', type: 'number', min: 0, max: 1440, value: d.minutes, disabled: !isAdmin() });
  detect.onchange = () => { url.hidden = detect.value !== 'url'; if (detect.value !== 'url') save(); };
  const save = async () => { try { await api('/api/ddns', { method: 'PUT', json: { detect: detect.value === 'url' ? url.value.trim() : detect.value, minutes: +minutes.value } }); toast('Saved'); } catch (e) { fail(e); } };
  url.onchange = save; minutes.onchange = save;
  const now = async (push) => { try { const r = await api('/api/ddns/run', { method: 'POST', json: { push } }); toast(r.changed ? `New address: ${r.ipv4 || ''} ${r.ipv6 || ''}` : push ? 'Pushed' : `Unchanged: ${r.ipv4 || r.ipv6 || 'none found'}`); onRoute(); } catch (e) { fail(e); } };
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Dynamic DNS')),
    h('div', { class: 'box' }, h('h2', null, icon('globe'), 'The public address'),
      h('div', { class: 'kv' }, h('div', { class: 'k' }, 'IPv4'), h('div', { class: 'v' }, h('code', null, d.ipv4 || 'not found yet'))),
      h('div', { class: 'kv' }, h('div', { class: 'k' }, 'IPv6'), h('div', { class: 'v' }, h('code', null, d.ipv6 || 'none'))),
      h('div', { class: 'kv' }, h('div', { class: 'k' }, 'Checked'), h('div', { class: 'v' }, d.checkedAt ? ago(new Date(+d.checkedAt * 1000).toISOString()) : 'never', d.error ? h('span', { class: 'warn' }, ` · ${d.error}`) : null)),
      canEdit() ? h('p', null, h('button', { class: 'pillbtn', onclick: () => now(false) }, icon('sync', 's'), 'Check now'), ' ',
        h('button', { class: 'pillbtn', onclick: () => now(true) }, icon('upload', 's'), 'Push the records now')) : null),
    h('div', { class: 'box' }, h('h2', null, icon('tune'), 'How'),
      h('div', { class: 'grid' }, fld('Find the address with', detect), fld('Every (minutes, 0: never on its own)', minutes)), url,
      h('p', { class: 'muted small' }, 'When it changes, every record set to "Public address" takes it, and the servers that hold those records are updated straight away.')),
    h('div', { class: 'box' }, h('h2', null, icon('list'), `Records that follow it (${entries.length})`),
      entries.length ? h('table', { class: 't' }, entries.map((e) => h('tr', null, h('td', { class: 'nm' }, e.name),
        h('td', null, Object.entries(e.records).map(([v, rs]) => rs.filter((r) => r.source && r.source.startsWith('publicip')).map((r) => [h('span', { class: 'muted small' }, `${viewOf(v).name}: `), recChip(r)]))))))
        : h('p', { class: 'muted' }, 'None yet. In an entry, set a record\'s value to "Public address" (usually in the External view).')));
}

// ------------------------------------------------------------------ history
async function showHistory(page) {
  const items = (await api('/api/history?limit=300')).items;
  const LABEL = { edit: 'Changed', delete: 'Deleted', push: 'Pushed', resolve: 'Resolved', import: 'Imported', server: 'Server', ddns: 'Dynamic DNS', tailscale: 'Tailscale' };
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'History')),
    items.length ? h('div', { class: 'hist' }, items.map((x) => h('div', { class: `hrow ${x.ok ? '' : 'bad'}` },
      h('div', { class: 'hmeta' }, h('b', null, LABEL[x.action] || x.action), x.server ? ` · ${x.server}` : '', h('span', { class: 'muted small' }, ` · ${x.user || 'ioDNS'} · ${new Date(x.at + (x.at.endsWith('Z') ? '' : 'Z')).toLocaleString()}`)),
      h('pre', { class: 'hdetail' }, x.detail))))
      : h('div', { class: 'empty' }, icon('history'), h('p', null, 'Nothing yet.')));
}

// ------------------------------------------------------------------ settings
const SUITE_TABS = { security: 'Security', global: 'Global settings' };
async function showSettings(page, r) {
  const tabs = [['account', 'Account'], ['display', 'Display'], ['views', 'Views'], ['data', 'Export and import'],
    ...(isAdmin() ? [['server', 'Server']] : []), ...(S.user.suiteAdmin ? [['security', SUITE_TABS.security], ['global', SUITE_TABS.global]] : [])];
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Settings')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/settings/${k}`; } }, l))));
  const body = h('div'); page.append(body);
  await ({ account: setAccount, display: setDisplay, views: setViews, data: setData, server: setServer, security: setSuite, global: setSuite }[r.tab] || setAccount)(body, r);
}
const accountUi = () => import(new URL('api/auth/ui.js', document.baseURI).href);
async function setAccount(el) {
  const ui = await accountUi();
  const pw = h('div');
  await ui.mountAccount(el, { toast, onSaved: (u) => { Object.assign(S.user, u); drawUser(); } });
  el.append(pw);
  await ui.mountAppPasswords(pw, { toast });
}
async function setDisplay(el) {
  const ui = await accountUi();
  let t = 'system'; try { t = localStorage.getItem('iodns.theme') || 'system'; } catch { /* */ }
  el.append(ui.box('theme', 'Appearance', ui.themeRow(S.settings.theme || t, (x) => { S.settings.theme = x; applyTheme(x); })));
}
async function setViews(el) {
  await loadOverview();
  el.append(h('div', { class: 'box' }, h('h2', null, icon('layers'), 'Views'),
    h('p', { class: 'muted' }, 'A view is one answer to "who is asking": the house, the internet, the tailnet… Each server answers for one view, and each entry can hold different records in each.'),
    h('table', { class: 't' }, h('tr', null, h('th', null, 'Name'), h('th', null, 'What it is'), h('th', null, 'Servers'), h('th', null, 'Entries'), h('th', null)),
      S.views.map((v) => {
        const nm = h('input', { class: 't', value: v.name, disabled: !isAdmin(), onchange: async (e) => { try { await api(`/api/views/${v.id}`, { method: 'PATCH', json: { name: e.target.value } }); await loadOverview(); toast('Saved'); } catch (x) { fail(x); } } });
        const ds = h('input', { class: 't', value: v.description, disabled: !isAdmin(), onchange: async (e) => { try { await api(`/api/views/${v.id}`, { method: 'PATCH', json: { description: e.target.value } }); toast('Saved'); } catch (x) { fail(x); } } });
        return h('tr', null, h('td', null, nm), h('td', null, ds), h('td', null, v.servers), h('td', null, v.entries),
          h('td', null, isAdmin() ? h('button', { class: 'pillbtn noic danger tiny', onclick: async () => {
            if (!await confirmDialog('Delete the view', `Delete ${v.name} and its records in the master list (${v.entries} entries have some)? Its servers are kept, without a view.`, 'Delete', true)) return;
            try { await api(`/api/views/${v.id}`, { method: 'DELETE' }); onRoute(); } catch (x) { fail(x); }
          } }, 'Delete') : null));
      })),
    isAdmin() ? h('p', null, h('button', { class: 'pillbtn', onclick: async () => {
      const name = h('input', { class: 't', placeholder: 'Guests' });
      const r = await dialog('New view', fld('Name', name), [{ label: 'Cancel', value: null }, { label: 'Add', primary: true, value: () => api('/api/views', { method: 'POST', json: { name: name.value.trim() } }) }]);
      if (r) onRoute();
    } }, icon('add', 's'), 'New view')) : null));
}
async function setData(el) {
  const file = h('input', { type: 'file', accept: '.json,application/json' });
  const replace = h('input', { type: 'checkbox' });
  el.append(h('div', { class: 'box' }, h('h2', null, icon('download'), 'Export'), h('p', null, 'The master list (views and entries) as a JSON file.'),
    h('p', null, h('a', { class: 'pillbtn', href: '/api/export', download: 'iodns.json' }, icon('download', 's'), 'Download'))),
  canEdit() ? h('div', { class: 'box' }, h('h2', null, icon('upload'), 'Import a file'), h('p', null, 'An ioDNS export back in: entries are added, or replaced when the name is already here.'),
    h('div', { class: 'pform' }, file, h('label', { class: 'check' }, replace, ' Remove the entries that are not in the file'),
      h('p', null, h('button', { class: 'pillbtn primary', onclick: async () => {
        const f = file.files[0]; if (!f) { toast('Pick a file'); return; }
        try { const data = JSON.parse(await f.text()); const r = await api('/api/import/file', { method: 'POST', json: { data, replace: replace.checked } }); toast(`${r.entries} entries imported${r.removed ? `, ${r.removed} removed` : ''}`); } catch (e) { fail(e); }
      } }, icon('upload', 's'), 'Import')))) : null);
}
async function setSuite(el, r) {
  let ui;
  try { ui = await import(new URL('api/suite-admin/ui.js', document.baseURI).href); } catch (e) { el.append(h('p', { class: 'warn' }, `The panel did not load: ${e.message}`)); return; }
  await ui.mount(el, { tab: r.tab, sub: r.sub, toast, onSub: (x) => history.replaceState(null, '', `#/settings/${r.tab}/${x}`) });
}
const serverUi = () => import(new URL('api/server/ui.js', document.baseURI).href);
async function setServer(el) {
  const panel = h('div'); el.append(panel);
  try { await (await serverUi()).mount(panel, { toast }); } catch (e) { panel.append(h('p', { class: 'warn' }, `The Server panel did not load: ${e.message}`)); }
}
function updateBanner() {
  $('#updbanner')?.remove();
  const u = S.status && S.status.update;
  let dismissed = null; try { dismissed = localStorage.getItem('iodns.updateDismissed'); } catch { /* */ }
  if (!u || dismissed === u.remote) return;
  const b = h('div', { id: 'updbanner', role: 'status' }, icon('update'),
    h('span', null, `ioDNS ${u.version ? `v${u.version}` : 'update'} is available${u.message ? `: ${u.message.replace(/^v\d+\.\d+\.\d+:\s*/, '')}` : ''}`),
    h('button', { class: 'pillbtn primary noic', onclick: async () => { if (await confirmDialog('Update ioDNS', 'Install the new version and restart? The page reloads when it is back.', 'Update now')) { b.remove(); (await serverUi()).runUpdate({ toast }); } } }, 'Update now'),
    h('a', { class: 'pillbtn noic', href: '#/settings/server', onclick: () => b.remove() }, 'Details'),
    h('button', { class: 'iconbtn', title: 'Not now', onclick: () => { try { localStorage.setItem('iodns.updateDismissed', u.remote); } catch { /* */ } b.remove(); } }, icon('close', 's')));
  document.body.append(b);
}

// ------------------------------------------------------------------ sign-in
function showSignIn() {
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
    h('div', { class: 'brand' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }), h('span', { class: 'brand-name', style: { display: 'inline' } }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'DNS'))),
    first ? h('p', { class: 'muted' }, 'Welcome. Make the first account: it is the admin. (Already use another io app? Sign in there first: the apps share their accounts.)') : h('h2', null, 'Sign in'),
    tiles, form, err, h('div', { class: 'btns' }, btn))));
  if (first) { name.focus(); return; }
  const pick = (t) => tiles.querySelectorAll('.account').forEach((x) => x.classList.toggle('on', x === t));
  api('/api/auth/accounts').then((d) => {
    if (!d.accounts.length) { name.focus(); return; }
    form.hidden = true; btn.hidden = true;
    tiles.append(...d.accounts.map((a) => {
      const t = h('button', { type: 'button', class: 'account', onclick: () => {
        pick(t);
        if (a.passwordless) { login(a.name, ''); return; }
        name.value = a.name; name.hidden = true; form.hidden = false; btn.hidden = false; pw.value = ''; pw.focus();
      } }, h('span', { class: 'av big', style: { '--h': hue(a.displayName || a.name) } }, initials(a.displayName || a.name)), h('span', { class: 'nm' }, a.displayName || a.name), a.passwordless ? null : h('span', { class: 'muted small' }, 'password'));
      return t;
    }), h('button', { type: 'button', class: 'account', onclick: (e) => { pick(e.currentTarget); name.value = ''; name.hidden = false; form.hidden = false; btn.hidden = false; name.focus(); } },
      h('span', { class: 'av big other' }, '…'), h('span', { class: 'nm' }, 'Other')));
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
  if (S.settings.theme) { try { localStorage.setItem('iodns.theme', S.settings.theme); } catch { /* */ } applyTheme(); }
  drawUser();
  await loadOverview();
  $('#newbtn').onclick = () => editEntry(null);
  $('#menubtn').onclick = openNav;
  $('#navscrim').onclick = closeNav;
  $('#nav').addEventListener('click', (e) => { if (e.target.closest('a') && !document.body.classList.contains('side-docked')) closeNav(); });
  addEventListener('resize', applySidebar);
  let t;
  $('#q').addEventListener('input', (e) => { clearTimeout(t); t = setTimeout(() => { S.q = e.target.value.trim(); if (S.redraw) S.redraw(); }, 150); });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { if (document.querySelector('.dialog-back')) closeDialogs(); else if (document.body.classList.contains('side-open')) closeNav(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) || document.querySelector('.signin, .dialog-back')) return;
    if (e.key === '/') { e.preventDefault(); $('#q').focus(); }
    else if (e.key === 'n' && canEdit()) { e.preventDefault(); editEntry(null); }
  });
  addEventListener('hashchange', () => { S.redraw = null; onRoute(); });
  await onRoute();
  loadSuite();
  updateBanner();
  setInterval(async () => { try { S.status = await api('/api/status'); updateBanner(); } catch { /* restarting */ } }, 15 * 60 * 1000);
}
start().catch(fail);
