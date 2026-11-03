/** Signing in: the account picker (one click for an account without a password), the password dialog, the first
 *  admin, the account menu. The same flow as iopix. */
import { $, h, api, state, dialog, menu, toast, fail, initials, icon } from './core.js';

export async function loadMe() {
  state.me = await api('/api/auth/me');
  return state.me;
}

export async function signIn() {
  if (!state.me.usersExist) return firstAdmin();
  const { accounts } = await api('/api/auth/accounts');
  const name = h('input', { type: 'text', placeholder: 'User name', autocomplete: 'username' });
  const pw = h('input', { type: 'password', placeholder: 'Password', autocomplete: 'current-password' });
  const msg = h('p.err.small');
  let chosen = null;
  const pick = (a, tile) => {
    chosen = a;
    for (const t of tiles.children) t.classList.toggle('on', t === tile);
    name.value = a ? a.name : '';
    form.hidden = false;
    name.hidden = !!a;
    if (a && a.passwordless) go();
    else (a ? pw : name).focus();
  };
  const tiles = h('div.accounts', accounts.map((a) => {
    const t = h('button.acct', { type: 'button', onclick: () => pick(a, t) }, h('span.avatar', initials(a.name)), h('span', a.name));
    return t;
  }), h('button.acct', { type: 'button', onclick: (e) => pick(null, e.currentTarget) }, h('span.avatar', icon('person')), h('span', 'Other')));
  const form = h('div', name, pw);
  form.hidden = accounts.length > 0;
  const go = async () => {
    try {
      await api('/api/auth/login', { method: 'POST', body: { name: chosen ? chosen.name : name.value, password: chosen && chosen.passwordless ? '' : pw.value } });
      $('.scrim') && $('.scrim').remove();
      location.reload();
    } catch (e) { msg.textContent = e.message; return false; }
  };
  pw.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
  return dialog('Sign in to ionotes', h('div', accounts.length ? tiles : null, form, msg), [{ label: 'Cancel', value: null }, { label: 'Sign in', primary: true, action: go }]);
}

async function firstAdmin() {
  const name = h('input', { type: 'text', placeholder: 'User name', autocomplete: 'username' });
  const pw = h('input', { type: 'password', placeholder: 'Password (8 characters or more)', autocomplete: 'new-password' });
  const msg = h('p.err.small');
  return dialog('Create the admin account', h('div', h('p.muted', 'Until an account exists, anyone who can reach ionotes can read and change the notes. The first account is the admin.'), name, pw, msg), [
    { label: 'Cancel', value: null },
    { label: 'Create', primary: true, action: async () => { try { await api('/api/auth/setup', { method: 'POST', body: { name: name.value, password: pw.value } }); location.reload(); } catch (e) { msg.textContent = e.message; return false; } } },
  ]);
}

async function changePassword() {
  const cur = h('input', { type: 'password', placeholder: 'Current password', autocomplete: 'current-password' });
  const pw = h('input', { type: 'password', placeholder: 'New password (8 characters or more)', autocomplete: 'new-password' });
  const msg = h('p.err.small');
  await dialog('Change your password', h('div', cur, pw, msg), [{ label: 'Cancel' }, { label: 'Change', primary: true, action: async () => {
    try { await api('/api/auth/password', { method: 'POST', body: { current: cur.value, password: pw.value } }); toast('Password changed; your other sessions are signed out'); } catch (e) { msg.textContent = e.message; return false; }
  } }]);
}

async function signOut() {
  try {
    const r = await api('/api/auth/logout', { method: 'POST' });
    if (r && r.cloudflareLogout) { location.href = r.cloudflareLogout; return; }
  } catch (e) { fail(e); }
  location.reload();
}

export function renderUserMenu() {
  const el = $('#usermenu');
  el.textContent = '';
  const me = state.me;
  if (!me.user) {
    el.append(h('button.pillbtn', { onclick: signIn }, icon('person'), h('span.lbl', me.usersExist ? 'Sign in' : 'Set up')));
    return;
  }
  const btn = h('button.iconbtn', { title: me.user.name, 'aria-label': 'Account', onclick: () => menu(btn, [
    { head: `${me.user.name} · ${me.user.role}${me.signedInBy === 'cloudflare' ? ' · via Cloudflare' : ''}` },
    { icon: 'gear', label: 'Settings', action: () => { location.hash = '#/settings'; } },
    me.canWrite ? { icon: 'history', label: 'Change log', action: () => { location.hash = '#/changes'; } } : null,
    !me.user.passwordless ? { icon: 'edit', label: 'Change password', action: changePassword } : null,
    { icon: 'logout', label: 'Sign out everywhere', action: async () => { await api('/api/auth/logout_all', { method: 'POST' }); toast('Your other sessions are signed out'); } },
    '-',
    { icon: 'logout', label: 'Sign out', action: signOut },
  ]) }, h('span.avatar', initials(me.user.name)));
  el.append(btn);
}
