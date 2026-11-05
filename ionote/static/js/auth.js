/** Signing in: the account picker (one click for an account without a password), the password dialog, the first
 *  admin, the account menu. The same flow as iopix. */
import { $, h, api, state, dialog, toast, fail, initials, icon, menu, isAdmin } from './core.js';

export async function loadMe() {
  state.me = await api('/api/auth/me');
  return state.me;
}

/** The brand above the sign-in's title, as in iopix: the logo and the two-tone name. */
function signinBrand() {
  const n = (state.settings && state.settings.app_name) || 'ionotes';
  const name = n.toLowerCase() === 'ionotes' ? h('span.brand-name', h('span.io', n.slice(0, 2)), h('span.nm', n.toLowerCase() === 'ionotes' ? 'Notes' : n.slice(2))) : h('span.brand-name', n);
  return h('div.signin-brand', h('img.logo', { src: 'static/icons/mark.svg', alt: '' }), name);
}
const avatar = (a) => h('span.avatar.big', (a.name || '?')[0].toUpperCase());

/** iopix's sign-in: a tile per account (one click for an account without a password, a password for the others),
 *  "Other" to type a name. required: ionotes shows nothing else until someone signs in (no Cancel, no closing). */
export async function signIn(required = false) {
  if (!state.me.usersExist) return firstAdmin();
  const name = h('input.einput', { type: 'text', placeholder: 'User name', autocomplete: 'username' });
  const pw = h('input.einput', { type: 'password', placeholder: 'Password', autocomplete: 'current-password' });
  const form = h('div.signin-form', name, pw);
  const tiles = h('div.accounts');
  const login = async (body) => {
    try {
      await api('/api/auth/login', { method: 'POST', body });
      location.reload();
      return true;
    } catch (e) { fail(e); return false; }
  };
  const submit = () => login({ name: name.value.trim(), password: pw.value });
  [name, pw].forEach((i) => i.addEventListener('keydown', (e) => { e.stopPropagation(); if (e.key === 'Enter') submit(); }));
  const p = dialog('Sign in', h('div', tiles, form,
    h('p.muted.small', `Sign in to see your notes. Notes are private to each account.`)),
  [required ? null : { label: 'Cancel', value: null }, { label: 'Sign in', primary: true, action: submit }].filter(Boolean),
  { required, head: signinBrand() });
  api('/api/auth/accounts').then((d) => {
    if (!d.accounts.length) { name.focus(); return; }
    form.hidden = true;
    tiles.append(...d.accounts.map((a) => h('button.account', { type: 'button', 'data-n': a.name, title: a.passwordless ? `Sign in as ${a.name}` : `${a.name} (password)`, onclick: () => {
      if (a.passwordless) { login({ name: a.name }); return; }
      name.value = a.name; form.hidden = false;
      tiles.querySelectorAll('.account').forEach((t) => t.classList.toggle('on', t.dataset.n === a.name));
      pw.focus();
    } }, avatar(a), h('span.nm', a.name), a.passwordless ? null : h('span.muted.tiny', 'password'))),
    h('button.account', { type: 'button', title: 'Type a user name', onclick: () => { form.hidden = false; name.value = ''; tiles.querySelectorAll('.account').forEach((t) => t.classList.remove('on')); name.focus(); } },
      h('span.avatar.big.other', '…'), h('span.nm', 'Other')));
  }).catch(() => name.focus());
  return p;
}

async function firstAdmin() {
  const name = h('input.einput', { type: 'text', placeholder: 'Admin user name', autocomplete: 'username' });
  const pw = h('input.einput', { type: 'password', placeholder: 'Password (8 characters or more)', autocomplete: 'new-password' });
  const msg = h('p.err.small');
  return dialog('Create the admin account', h('div', h('p.muted', 'Right now ioNotes is open to anyone who can reach it. Once an admin exists, every account has notes of its own, visible to nobody else; the notes made so far become the admin\'s.'), h('div.signin-form', name, pw), msg), [
    { label: 'Cancel', value: null },
    { label: 'Create', primary: true, action: async () => { try { await api('/api/auth/setup', { method: 'POST', body: { name: name.value, password: pw.value } }); location.reload(); } catch (e) { msg.textContent = e.message; return false; } } },
  ]);
}

async function signOut() {
  try {
    const r = await api('/api/auth/logout', { method: 'POST' });
    if (r && r.cloudflareLogout) { location.href = r.cloudflareLogout; return; }
  } catch (e) { fail(e); }
  location.reload();
}

/** The account panel, as iopix's: who you are and what your role allows, how this browser is signed in, a new
 *  password, and Sign out everywhere else / Sign out / Done. */
function accountDialog() {
  const me = state.me, u = me.user;
  const cur = h('input.einput', { type: 'password', placeholder: 'Current password', autocomplete: 'current-password' });
  const pw = h('input.einput', { type: 'password', placeholder: 'New password (8 characters or more)', autocomplete: 'new-password' });
  const by = me.signedInBy;
  const how = h('p.muted.small', h('b', 'Signed in: '), by === 'cloudflare' ? (me.throughCloudflare ? 'through Cloudflare Access, from outside your network.' : 'through Cloudflare Access; this browser stays signed in on your home network too.')
    : by === 'proxy' ? 'at the sign-in page of your proxy; sign out there.' : by === 'oneclick' || u.passwordless ? 'here, with one click (no password).' : 'here, with a password.');
  const role = u.role === 'admin' || u.role === 'suiteAdmin' ? 'You can change your notes, the settings and the accounts.' : u.role === 'editor' ? 'You can read and change your notes.' : 'You can read and search your notes.';
  const viaProxy = by === 'proxy' || me.viaProxy;
  const change = h('button.pillbtn', { type: 'button', onclick: async () => {
    try { await api('/api/auth/password', { method: 'POST', body: { current: cur.value, password: pw.value } }); toast('Password changed; your other sessions are signed out'); cur.value = pw.value = ''; } catch (e) { fail(e); }
  } }, 'Change password');
  const buttons = [];
  if (by !== 'proxy') {
    buttons.push({ label: 'Sign out everywhere else', action: async () => {
      try { await api('/api/auth/logout_all', { method: 'POST' }); toast('Signed out everywhere else'); } catch (e) { fail(e); }
      return false;
    } });
    buttons.push({ label: by === 'cloudflare' && me.throughCloudflare ? 'Sign out (of Cloudflare too)' : 'Sign out', action: signOut });
  }
  buttons.push({ label: 'Done', primary: true });
  return dialog(`${u.name} · ${u.role}`, h('div.acct', h('p.muted', role), how,
    viaProxy || u.passwordless ? null : [h('h4', 'Change password'), h('div.signin-form', cur, pw), h('div.row', change)]), buttons);
}

function cycleTheme() {
  let cur = 'light'; try { cur = localStorage.getItem('ionotes.theme') || 'light'; } catch (e) {}
  const next = { light: 'dark', dark: 'system', system: 'light' }[cur] || 'light';
  try { localStorage.setItem('ionotes.theme', next); } catch (e) {}
  if (next === 'system') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = next;
  if (state.me.user) api('/api/auth/settings', { method: 'POST', body: { theme: next } }).catch(() => {});
  toast(`Appearance: ${next}`);
}

/** The top right, as in every ioThing app: the account's initial in a small amber circle, which opens the avatar menu
 *  (the account panel, appearance, Settings, Maintenance, sign out); signed out, a person icon that signs in (or creates
 *  the admin account). */
export function renderUserMenu() {
  const el = $('#usermenu');
  el.textContent = '';
  const me = state.me;
  if (!me.user) {
    el.append(h('button.iconbtn.tool', { title: me.usersExist ? 'Sign in' : 'Create the admin account', 'aria-label': 'Sign in', onclick: () => signIn() }, icon('person')));
    return;
  }
  let theme = 'light'; try { theme = localStorage.getItem('ionotes.theme') || 'light'; } catch (e) {}
  const btn = h('button.iconbtn.tool', { title: `${me.user.name} (${me.user.role})`, 'aria-label': 'Account', onclick: () => menu(btn, [
    { head: `${me.user.name} · ${me.user.role}` },
    { label: 'Account', icon: 'person', action: accountDialog },
    { label: `Appearance: ${theme}`, icon: 'palette', action: cycleTheme },
    { label: 'Settings', icon: 'gear', action: () => { location.hash = '#/settings'; } },
    isAdmin() ? { label: 'Maintenance', icon: 'wrench', action: () => { location.hash = '#/maintenance'; } } : null,
    '-',
    me.signedInBy === 'proxy' ? null : { label: 'Sign out everywhere else', icon: 'logout', action: async () => { try { await api('/api/auth/logout_all', { method: 'POST' }); toast('Signed out everywhere else'); } catch (e) { fail(e); } } },
    me.signedInBy === 'proxy' ? null : { label: me.signedInBy === 'cloudflare' && me.throughCloudflare ? 'Sign out (of Cloudflare too)' : 'Sign out', action: signOut },
  ]) }, h('span.avatar', initials(me.user.name)));
  el.append(btn);
}
