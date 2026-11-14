import { $, h } from './core.js';

// ---------- accounts: sign-in, the account menu, Settings › Account (people, roles and proxy sign-in: Settings › Security) ----------
// The same flow as iopix (and ionote, ioContact): accounts live in the Shared ioSuite database, so
// one sign-in serves every app on the domain. Health data is private: nothing shows until someone signs in.

export let me = { user: null, usersExist: false, isAdmin: false };
export const isAdmin = () => !!me.isAdmin;

export async function authApi(path, { method = 'GET', body } = {}) {
  const r = await fetch(path, { method, credentials: 'same-origin', headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || data.detail || r.statusText);
  return data;
}

export async function loadMe() {
  try { me = await authApi('api/auth/me'); } catch { me = { user: null, usersExist: false, isAdmin: false }; }
  return me;
}

/** A dialog: a scrim and a card; buttons are [{label, primary, danger, action}] (action returning false keeps it open).
 *  required: nothing of the app shows behind it and it can't be dismissed. Resolves with the button's value. */
export function dialog(title, body, buttons, { required = false, head = null } = {}) {
  return new Promise(resolve => {
    const scrim = h('div', { class: 'scrim' + (required ? ' required' : '') });
    const close = v => { scrim.remove(); document.removeEventListener('keydown', onKey); resolve(v); };
    const onKey = e => { if (e.key === 'Escape' && !required) close(null); };
    const acts = h('div', { class: 'acts' }, buttons.filter(Boolean).map(b => h('button', {
      class: (b.primary ? 'primary' : '') + (b.danger ? ' danger' : ''),
      onclick: async () => { if (b.action) { if (await b.action() === false) return; } close(b.value ?? b.label); } }, b.label)));
    scrim.append(h('div', { class: 'dialog' }, head, h('h2', {}, title), body, acts));
    if (!required) scrim.addEventListener('click', e => { if (e.target === scrim) close(null); });
    document.addEventListener('keydown', onKey);
    document.body.append(scrim);
    const first = scrim.querySelector('input:not([hidden]), button');
    if (first) first.focus();
  });
}

export function toast(text, ms = 3000) {
  const t = h('div', { class: 'toast' }, text);
  document.body.append(t);
  setTimeout(() => t.remove(), ms);
}

export const avatar = (a, big = false) => h('span', { class: 'avatar' + (big ? ' big' : '') }, ((a && (a.displayName || a.name)) || '?')[0].toUpperCase());

/** The brand above the sign-in's title, as in iopix: the logo and the name. */
export const signinBrand = () => h('div', { class: 'signin-brand' }, h('img', { class: 'logo', src: 'static/icons/mark.svg', alt: '' }),
  h('span', { class: 'brand-name' }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Health')));

export let signingIn = false;
/** iopix's sign-in: a tile per account (one click for an account without a password, a password for the others),
 *  "Other" to type a name. required: ioHealth shows nothing else until someone signs in (no Cancel, no closing). */
export async function signIn(required = false) {
  if (signingIn) return;
  signingIn = true;
  try {
    if (!me.usersExist) return await firstAdmin();
    const name = h('input', { type: 'text', placeholder: 'User name', autocomplete: 'username' });
    const pw = h('input', { type: 'password', placeholder: 'Password', autocomplete: 'current-password' });
    const form = h('div', { class: 'signin-form' }, name, pw);
    const msg = h('p', { class: 'error small' });
    const tiles = h('div', { class: 'accounts' });
    const login = async body => {
      try { await authApi('api/auth/login', { method: 'POST', body }); location.reload(); return true; } catch (e) { msg.textContent = e.message; return false; }
    };
    const submit = () => login({ name: name.value.trim(), password: pw.value });
    for (const i of [name, pw]) i.addEventListener('keydown', e => { e.stopPropagation(); if (e.key === 'Enter') submit(); });
    authApi('api/auth/accounts').then(d => {
      if (!d.accounts.length) { name.focus(); return; }
      form.hidden = true;
      tiles.append(...d.accounts.map(a => h('button', { type: 'button', class: 'account', 'data-n': a.name, title: a.passwordless ? `Sign in as ${a.name}` : `${a.name} (password)`,
        onclick: () => {
          if (a.passwordless) { login({ name: a.name }); return; }
          name.value = a.name; form.hidden = false;
          for (const t of tiles.querySelectorAll('.account')) t.classList.toggle('on', t.dataset.n === a.name);
          pw.focus();
        } }, avatar(a, true), h('span', { class: 'nm' }, a.name), a.passwordless ? null : h('span', { class: 'muted tiny' }, 'password'))),
        h('button', { type: 'button', class: 'account', title: 'Type a user name', onclick: () => {
          form.hidden = false; name.value = ''; for (const t of tiles.querySelectorAll('.account')) t.classList.remove('on'); name.focus();
        } }, h('span', { class: 'avatar big other' }, '…'), h('span', { class: 'nm' }, 'Other')));
    }).catch(() => name.focus());
    return await dialog('Sign in', h('div', {}, tiles, form, msg, h('p', { class: 'muted small' }, 'Sign in to see your health data. Each account sees its own.')),
      [required ? null : { label: 'Cancel', value: null }, { label: 'Sign in', primary: true, action: submit }], { required, head: signinBrand() });
  } finally { signingIn = false; }
}

export async function firstAdmin() {
  const name = h('input', { type: 'text', placeholder: 'Admin user name', autocomplete: 'username' });
  const pw = h('input', { type: 'password', placeholder: 'Password (8 characters or more)', autocomplete: 'new-password' });
  const msg = h('p', { class: 'error small' });
  return dialog('Create the admin account', h('div', {}, h('p', { class: 'muted' }, 'No accounts yet. The first account is the suite admin (admin in ioHealth and the other ioThing apps). Create it from inside your network.'),
    h('div', { class: 'signin-form' }, name, pw), msg), [
    { label: 'Create', primary: true, action: async () => {
      try { await authApi('api/auth/setup', { method: 'POST', body: { name: name.value.trim(), password: pw.value } }); location.reload(); } catch (e) { msg.textContent = e.message; return false; }
    } }], { required: true, head: signinBrand() });
}

export async function signOut() {
  try {
    const r = await authApi('api/auth/logout', { method: 'POST' });
    if (r && r.cloudflareLogout) { location.href = r.cloudflareLogout; return; }
  } catch (e) { toast(e.message); }
  location.reload();
}

export function menu(anchor, items) {
  const el = h('div', { class: 'menu' });
  const close = () => { el.remove(); document.removeEventListener('click', onDoc, true); };
  const onDoc = e => { if (!el.contains(e.target)) close(); };
  for (const it of items) {
    if (!it) continue;
    if (it === '-') { el.append(h('hr')); continue; }
    if (it.head) { el.append(h('div', { class: 'head' }, it.head)); continue; }
    el.append(h('button', { type: 'button', onclick: () => { close(); it.action(); } }, it.label));
  }
  const r = anchor.getBoundingClientRect();
  el.style.top = (r.bottom + 6) + 'px';
  el.style.right = Math.max(8, window.innerWidth - r.right) + 'px';
  document.body.append(el);
  setTimeout(() => document.addEventListener('click', onDoc, true));
}

export function renderUserMenu() {
  const el = $('#usermenu');
  if (!el) return;
  el.textContent = '';
  if (!me.user) {
    el.append(h('button', { class: 'small-btn', onclick: () => signIn(false) }, me.usersExist ? 'Sign in' : 'Set up'));
    return;
  }
  const btn = h('button', { class: 'avatar-btn', title: me.user.name, 'aria-label': 'Account', onclick: () => menu(btn, [
    { head: `${me.user.name} · ${me.user.role}${me.signedInBy === 'cloudflare' ? ' · via Cloudflare' : ''}` },
    { label: 'Settings', action: () => { location.hash = '#/settings'; } },
    '-',
    { label: 'Sign out', action: signOut },
  ]) }, avatar(me.user));
  el.append(btn);
}

// ---- Settings › Account

export const accountUi = () => import(new URL('api/auth/ui.js', document.baseURI).href);
/** Settings › Account: display name, email and password, iosuite-shared's panel (the same in every io app). */
export async function setAccount() {
  const el = h('div');
  await (await accountUi()).mountAccount(el, { toast, onSaved: u => { Object.assign(me.user, u); renderUserMenu(); } });
  return [el];
}

// ---- Settings › Security and Global settings (suite admins): the people and their role in every app
// (here too), app passwords, sign-in at the proxy; the apps, keys and tokens. The same panel in every io app, served by iosuite-shared.

export async function suitePanel(tab, sub) {
  const el = h('div');
  let ui;
  try { ui = await import(new URL('api/suite-admin/ui.js', document.baseURI).href); } catch (e) { return [h('p', { class: 'error' }, `The panel did not load: ${e.message}`)]; }
  await ui.mount(el, { tab, sub, toast, onSub: (x) => history.replaceState(null, '', `#/settings/${tab}/${x}`) });
  return [el];
}
