/* ioSuite web app: one module, no build step, as in the other io apps. The start page (a tile per app) and the
   settings (account, users, apps, server). Each tile keeps a `.more` block under its name, empty for now: the place for
   what an app will show on the start page later (today's events, the newest photos…), filled from /api/apps. */

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
  $('#main').replaceChildren(page);
  try { await ({ home: showHome, settings: showSettings })[r.view](page, r); } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ the start page
const greeting = () => { const hr = new Date().getHours(); return hr < 5 ? 'Good night' : hr < 12 ? 'Good morning' : hr < 18 ? 'Good afternoon' : 'Good evening'; };

async function showHome(page) {
  S.apps = (await api('/api/apps')).items;
  const first = (S.user.displayName || S.user.name).split(/\s+/)[0];
  page.append(h('div', { class: 'hello' }, h('h1', null, `${greeting()}, ${first}`),
    h('div', { class: 'muted' }, new Date().toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' }))));
  if (!S.apps.length) { page.append(h('div', { class: 'empty' }, 'No apps to show. ', S.user.role === 'admin' ? h('a', { class: 'lnk', href: '#/settings/apps' }, 'Settings › Apps') : null)); return; }
  page.append(h('div', { class: 'apps' }, S.apps.map((a) =>
    h('a', { class: 'app', href: a.url, 'data-app': a.key, title: a.url },
      h('img', { src: a.icon, alt: '' }), appName(a.name, a.color), h('span', { class: 'tag' }, a.tagline),
      h('div', { class: 'more' })))));  // room for what the app shows here later
}

// ------------------------------------------------------------------ settings
async function showSettings(page, r) {
  const adm = S.user.role === 'admin';
  const tabs = [['account', 'Account'], ...(adm ? [['apps', 'Apps'], ['users', 'Users'], ['server', 'Server']] : [])];
  if (!tabs.some(([k]) => k === r.tab)) r.tab = 'account';
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Settings')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/settings/${k}`; } }, l))));
  const body = h('div'); page.append(body);
  await ({ account: setAccount, apps: setApps, users: setUsers, server: setServer }[r.tab] || setAccount)(body);
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
  const items = (await api('/api/apps/settings')).items;
  const rows = items.map((a) => {
    const url = h('input', { class: 't', value: a.envUrl || a.url, placeholder: `empty: this host, port ${a.port}`, disabled: a.envUrl ? true : null });
    const shown = h('input', { type: 'checkbox', checked: !a.hidden });
    return { a, url, shown, el: h('div', { class: 'approw' }, h('img', { src: `static/icons/apps/${a.key}.${a.key === 'ionotes' ? 'png' : 'svg'}`, alt: '' }), h('span', { class: 'nm' }, a.name), url,
      h('label', { class: 'check' }, shown, ' On the page'), a.envUrl ? h('span', { class: 'muted small' }, `${a.key.toUpperCase()}_URL in the environment`) : null) };
  });
  el.append(h('div', { class: 'box' }, h('h2', null, icon('apps'), 'The apps on the start page'),
    h('p', { class: 'muted' }, 'Where each app is reached, as the family opens it: its public address behind the reverse proxy, or its LAN address. Empty: the host this page was opened on, with the app’s usual port (the one-box install). An address set in the environment (IOPIX_URL and friends) wins over this.'),
    rows.map((r) => r.el),
    h('p', null, h('button', { class: 'pillbtn primary', onclick: async () => {
      const body = Object.fromEntries(rows.map((r) => [r.a.key, { ...(r.a.envUrl ? {} : { url: r.url.value.trim() }), hidden: !r.shown.checked }]));
      try { await api('/api/apps/settings', { method: 'POST', json: body }); toast('Saved'); } catch (e) { fail(e); }
    } }, icon('check', 's'), 'Save'))));
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
