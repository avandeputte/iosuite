/** Sign-in and accounts: the session (loadUser sets S.USER and the fields that come with it), the user menu, the sign-in
 *  and setup dialogs, and the Security and Global settings tabs of Settings. */
import { $, SETTINGS, api, errorBox, fill, h, icon, post } from './core.js';
import { S, applyBadgePref, applyTheme, avatarOf, brandName, hashFor, onRoute, toast, toastError } from './state.js';
import { modal } from './actions.js';
import { boot, pollStatus } from './main.js';
import { loadSuite } from './suite.js';
import { popMenu } from './lightbox.js';

// ---- users: sign in / out, own password, first-admin setup, admin user management
export async function loadUser() {
  try { const me = await api('/api/auth/me'); S.USER = me.user; SETTINGS.user = me.user ? me.settings : null; S.IS_ADMIN = me.isAdmin; S.USERS_EXIST = me.usersExist; S.REQUIRE_LOGIN = !!me.requireLogin; S.VIA_PROXY = !!me.viaProxy; } catch { S.USER = null; SETTINGS.user = null; }
  renderUserMenu();
}
export function renderUserMenu() {
  loadSuite();  // the other apps' menu is per account: drawn again when the account changes
  const el = $('#usermenu'); if (!el) return;
  const btn = h('button', { class: 'iconbtn tool', title: S.USER ? `${S.USER.name} (${S.USER.role})` : S.USERS_EXIST ? 'Sign in' : 'Create the admin account',
    onclick: () => (!S.USER ? (S.USERS_EXIST ? loginDialog() : setupDialog()) : popMenu(btn, [  // the avatar menu, the same in every ioThing app
      ['Settings', () => { location.hash = '#/settings'; }],
      ['Sign out', signOut],
    ])) }, S.USER ? avatarOf(S.USER) : icon('person'));
  el.replaceChildren(btn);
}
async function afterLogin(me) {
  S.USER = me.user; SETTINGS.user = me.settings || {}; renderUserMenu();
  if (!S.BOOTED) { applyBadgePref(); applyTheme(); await boot(); return; }  // sign-in was required: load the library now
  await pollStatus(); applyBadgePref(); applyTheme(); S.viewKey = null; onRoute();
}
/** required: the viewer shows nothing else until someone signs in (no Cancel, no closing). */
export function loginDialog(required) {
  // the account picker: a tile per account; one click for a passwordless viewer, a password for the others
  const name = h('input', { class: 'einput', placeholder: 'User name', autocomplete: 'username' });
  const pw = h('input', { class: 'einput', type: 'password', placeholder: 'Password', autocomplete: 'current-password' });
  const form = h('div', { style: 'display:grid;gap:8px;margin-top:10px' }, name, pw);
  const tiles = h('div', { class: 'accounts' });
  const submit = async () => { try { const me = await post('/api/auth/login', { name: name.value.trim(), password: pw.value }); back.remove(); await afterLogin(me); toast(`Signed in as ${me.user.name}.`); } catch (e) { toastError(e); } };
  [name, pw].forEach((i) => { i.onkeydown = (e) => { e.stopPropagation(); if (e.key === 'Enter') submit(); }; });
  const back = modal('Sign in', tiles, form,
    h('p', { class: 'muted small' }, required ? `Sign in to use ${S.APP_NAME}.` : 'Without signing in you can browse everything; signing in keeps your display settings, favorites and albums on the server, and editors can change the library.'),
    { buttons: [required ? null : 'Cancel', ['Sign in', submit, 'on']] });
  back.querySelector('.modal').prepend(h('div', { class: 'signin-brand' }, h('span', { class: 'logo' }), brandName()));  // the logo and the name above the title
  if (required) { back.onclick = null; back.classList.add('required'); }
  api('/api/auth/accounts').then((d) => {
    if (!d.accounts.length) { name.focus(); return; }
    form.hidden = true;
    fill(tiles, d.accounts.map((a) => h('button', { class: 'account', title: a.passwordless ? `Sign in as ${a.name}` : `${a.name} (password)`, onclick: async () => {
      if (a.passwordless) { try { const me = await post('/api/auth/login', { name: a.name }); back.remove(); await afterLogin(me); toast(`Signed in as ${a.name}.`); } catch (e) { toastError(e); } return; }
      name.value = a.name; form.hidden = false; tiles.querySelectorAll('.account').forEach((t) => t.classList.toggle('on', t === tiles.querySelector(`[data-n="${CSS.escape(a.name)}"]`))); pw.focus();
    }, 'data-n': a.name }, avatarOf(a, true), h('span', { class: 'nm' }, a.name), a.passwordless ? null : h('span', { class: 'muted', style: 'font-size:11px' }, 'password'))),
      h('button', { class: 'account', title: 'Type a user name', onclick: () => { form.hidden = false; name.value = ''; name.focus(); } }, h('span', { class: 'avatar big', style: 'background:var(--bg3);color:var(--fg2)' }, '…'), h('span', { class: 'nm' }, 'Other')));
  }).catch(() => name.focus());
}
export function setupDialog() {
  const name = h('input', { class: 'einput', placeholder: 'Admin user name', autocomplete: 'username' });
  const pw = h('input', { class: 'einput', type: 'password', placeholder: 'Password (8 characters or more)', autocomplete: 'new-password' });
  const submit = async () => { try { const me = await post('/api/auth/setup', { name: name.value.trim(), password: pw.value }); back.remove(); await afterLogin({ user: me.user, settings: {} }); toast('Admin account created; you are signed in.'); } catch (e) { toastError(e); } };
  [name, pw].forEach((i) => { i.onkeydown = (e) => { e.stopPropagation(); if (e.key === 'Enter') submit(); }; });
  const back = modal('Create the admin account', h('p', { class: 'muted' }, `Right now ${S.APP_NAME} is open to anyone who can reach it. Once an admin exists, visitors browse read-only, signed-in users keep their settings on the server, and only editors and admins can change the library or the settings.`),
    h('div', { class: 'stack',}, name, pw),
    { buttons: ['Cancel', ['Create', submit, 'on']] });
  name.focus();
}
/** Sign out of this browser; through Cloudflare Access, its own sign-out page ends its session too. */
async function signOut() {
  let r; try { r = await post('/api/auth/logout', {}); } catch (e) { toastError(e); return; }
  if (r && r.cloudflareLogout) { location.href = r.cloudflareLogout; return; }
  if (S.REQUIRE_LOGIN) { location.reload(); return; }
  S.USER = null; SETTINGS.user = null; renderUserMenu(); await pollStatus(); applyBadgePref(); applyTheme(); S.viewKey = null; onRoute(); toast('Signed out.');
}
/** Settings › Security (people, roles, app passwords, sign-in at the proxy) or Settings › Global settings (the apps, keys
 *  and tokens), for suite admins and the whole suite. The same panel in every io app, served by iosuite-shared. */
export function suiteSection(tab) {
  const box = h('div');
  import(new URL('api/suite-admin/ui.js', document.baseURI).href)
    .then((ui) => ui.mount(box, { tab, sub: S.route.params.get('part'), toast, onSub: (x) => { S.route.params.set('part', x); history.replaceState(null, '', hashFor('settings', S.route.params)); } }))
    .catch((e) => fill(box, errorBox(new Error(`The suite panel did not load: ${e.message}`))));
  return box;
}
