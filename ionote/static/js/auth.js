/** Signing in: the account picker (one click for an account without a password), the password dialog, the first
 *  admin, the account menu. The same flow as iopix. */
import { $, h, api, state, dialog, fail, initials, icon, menu } from './core.js';

export async function loadMe() {
  state.me = await api('/api/auth/me');
  return state.me;
}

/** The brand above the sign-in's title, as in iopix: the logo and the two-tone name. */
function signinBrand() {
  const n = (state.settings && state.settings.app_name) || 'ionote';
  const name = n.toLowerCase() === 'ionote' ? h('span.brand-name', h('span.io', n.slice(0, 2)), h('span.nm', 'Note')) : h('span.brand-name', n);
  return h('div.signin-brand', h('img.logo', { src: 'static/icons/mark.svg', alt: '' }), name);
}
const avatar = (a) => h('span.avatar.big', (a.name || '?')[0].toUpperCase());

/** iopix's sign-in: a tile per account (one click for an account without a password, a password for the others),
 *  "Other" to type a name. required: ionote shows nothing else until someone signs in (no Cancel, no closing). */
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
  return dialog('Create the admin account', h('div', h('p.muted', 'Right now ioNote is open to anyone who can reach it. Once an admin exists, every account has notes of its own, visible to nobody else; notes made so far stay with the open install, so export them first (Import and export) and import them once signed in.'), h('div.signin-form', name, pw), msg), [
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

/** The top right, as in every ioThing app: the account's initial in a small amber circle, which opens the avatar menu
 *  (Settings, sign out); signed out, a person icon that signs in (or creates
 *  the admin account). */
export function renderUserMenu() {
  const el = $('#usermenu');
  el.textContent = '';
  const me = state.me;
  if (!me.user) {
    el.append(h('button.iconbtn.tool', { title: me.usersExist ? 'Sign in' : 'Create the admin account', 'aria-label': 'Sign in', onclick: () => signIn() }, icon('person')));
    return;
  }
  const btn = h('button.iconbtn.tool', { title: `${me.user.name} (${me.user.role})`, 'aria-label': 'Account', onclick: () => menu(btn, [
    { head: `${me.user.name} · ${me.user.role}` },
    { label: 'Settings', icon: 'gear', action: () => { location.hash = '#/settings'; } },
    '-',
    me.signedInBy === 'proxy' ? null : { label: me.signedInBy === 'cloudflare' && me.throughCloudflare ? 'Sign out (of Cloudflare too)' : 'Sign out', action: signOut },
  ]) }, h('span.avatar', initials(me.user.name)));
  el.append(btn);
}
