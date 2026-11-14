import { $, S, api, dialog, fail, h, hue, icon, initials, loadMeta, toast } from './core.js';
import { route } from './main.js';

// ------------------------------------------------------------------ chrome
export function drawUser() {
  const m = $('#usermenu'); m.replaceChildren();
  if (!S.user) return;
  const btn = h('button', { class: 'avatarbtn', title: S.user.displayName, style: { background: `hsl(${hue(S.user.name)} 45% 45%)` } }, initials(S.user.displayName));
  let menu = null;
  const closeMenu = () => { if (menu) { menu.remove(); menu = null; document.removeEventListener('click', outside); } };
  const outside = (e) => { if (menu && !menu.contains(e.target) && e.target !== btn) closeMenu(); };
  btn.onclick = () => {
    if (menu) return closeMenu();
    const theme = localStorage.getItem('iocontact.theme') || 'system';
    menu = h('div', { class: 'menu' },
      h('div', { class: 'who' }, h('b', null, S.user.displayName), h('div', { class: 'muted small' }, `${S.user.name} · ${S.user.role}`)),
      h('a', { class: 'mi', href: '#/settings/account', onclick: closeMenu }, icon('person', 's'), 'Account'),
      h('a', { class: 'mi', href: '#/settings/devices', onclick: closeMenu }, icon('devices', 's'), 'Connect apps and devices'),
      h('button', { class: 'mi', onclick: () => { const n = { system: 'light', light: 'dark', dark: 'system' }[theme]; localStorage.setItem('iocontact.theme', n); applyTheme(); closeMenu(); toast(`Appearance: ${n}`); } },
        icon('theme', 's'), `Appearance: ${theme}`),
      h('a', { class: 'mi', href: '#/settings', onclick: closeMenu }, icon('settings', 's'), 'Settings'),
      h('button', { class: 'mi', onclick: async () => { await api('api/auth/logout', { method: 'POST' }); location.reload(); } }, icon('logout', 's'), 'Sign out'));
    m.append(menu);
    setTimeout(() => document.addEventListener('click', outside), 0);
  };
  m.append(btn);
}
/* The suite (iosuite-shared's suite_apps): when other ioThing apps are registered, the app mark top left (in the sidebar; in
   the top bar on a phone) opens a menu of them, each a link to that app. Alone, the mark stays the link to All contacts. */
export async function loadSuite() {
  try {
    const r = await api('api/auth/suite');
    S.suite = (r.items || []).filter((a) => a.url); suiteSelf = r.app;  // in the suite's one order, this app too
    if (!S.suite.some((a) => a.app !== r.app)) S.suite = [];  // only this app: no menu
  } catch { S.suite = []; }
  const b = $('#suitebtn');
  if (b) { b.hidden = !S.suite.length; b.onclick = () => toggleSuite(b); }
  if (!S.suite.length) closeSuite();
  drawNav();
}
export let suiteSelf = null;  // this app's key, marked in the menu
export let suitePop = null;
export function closeSuite() {
  if (!suitePop) return;
  suitePop.remove(); suitePop = null;
  document.removeEventListener('click', suiteOutside, true);
  document.removeEventListener('keydown', suiteKey);
  removeEventListener('resize', closeSuite);
}
export function suiteOutside(e) { if (suitePop && !suitePop.contains(e.target) && !e.target.closest('.suitebtn')) closeSuite(); }
export function suiteKey(e) { if (e.key === 'Escape') closeSuite(); }
export function appTile(a) {
  const mark = (a.name || a.app).replace(/^io(?=[A-Z])/, '').slice(0, 1).toUpperCase();
  const fallback = () => h('span', { class: 'appic fb', style: { background: a.color || 'var(--brand)' } }, mark);
  const ic = a.icon ? h('img', { class: 'appic', src: a.icon, alt: '', onerror: (e) => e.currentTarget.replaceWith(fallback()) }) : fallback();
  const el = h('a', { class: 'apptile', href: a.url, role: 'menuitem', title: a.description || a.name, onclick: closeSuite },
    ic, h('span', { class: 'appnm' }, a.name || a.app));
  el.classList.toggle('tool', !!a.adminTool);  // admin tools: a smaller icon
  if (a.app === suiteSelf) { el.classList.add('cur'); el.setAttribute('aria-current', 'page'); }
  return el;
}
export function toggleSuite(btn) {
  if (suitePop) { closeSuite(); return; }
  if (!S.suite.length) return;
  // the apps, then the admin tools (ioDNS…) in a section of their own: the server sends those to their admins only
  const apps = S.suite.filter((a) => !a.adminTool), tools = S.suite.filter((a) => a.adminTool);
  suitePop = h('div', { class: 'suitepop', role: 'menu', 'aria-label': 'ioThing apps', style: { '--cols': String(Math.min(3, Math.max(apps.length, tools.length))) } },
    ...apps.map(appTile), ...(tools.length ? [h('div', { class: 'suitesec' }, 'Admin tools'), ...tools.map(appTile)] : []));
  document.body.append(suitePop);
  const r = btn.getBoundingClientRect();
  suitePop.style.top = `${Math.round(r.bottom + 6)}px`;
  suitePop.style.left = `${Math.round(Math.max(8, Math.min(r.left - 6, innerWidth - suitePop.offsetWidth - 8)))}px`;
  setTimeout(() => { document.addEventListener('click', suiteOutside, true); document.addEventListener('keydown', suiteKey); addEventListener('resize', closeSuite); }, 0);
}
/** The theme: the account's (Settings › Display), remembered in this browser too so the sign-in page has it. */
export function applyTheme(choice) {
  try { if (choice) localStorage.setItem('iocontact.theme', choice); } catch { /* private mode */ }
  let t = choice; try { t = t || localStorage.getItem('iocontact.theme'); } catch { /* */ }
  t = t || 'system';
  if (t === 'system') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
}

/* The sidebar, as in ioPix: the name on top, the destinations in groups, Settings at the foot. It docks
   beside the page on a wide screen unless its button put it away (remembered); otherwise it slides over the page from the
   menu button. Phones get a bottom bar instead: four destinations and More. */
export const DOCK_MIN = 1100;
export function drawNav() {
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
          h('a', { class: 'brand-name', href: '#/', title: 'All contacts' }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Contact')))
        : h('a', { class: 'brand', href: '#/', title: 'All contacts' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }),
          h('span', { class: 'brand-name' }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Contact'))),
      h('button', { id: 'sidebtn', class: 'iconbtn', onclick: sidebarButton })),
    link('all', '#/', 'people', 'All contacts', total, listView && S.scope.kind === 'all', '--c-purple'),
    link('fav', '#/fav', 'star', 'Favorites', null, listView && S.scope.kind === 'fav', '--c-amber'),
    link('upcoming', '#/upcoming', 'cake', 'Birthdays', null, r.view === 'upcoming', '--c-rose'),
    S.status.iopix ? link('iopix', '#/iopix', 'image', 'ioPix people', null, r.view === 'iopix', '--c-indigo') : null,
    h('button', { class: 'navmore', 'data-v': 'more', title: 'More', onclick: moreSheet }, icon('more'), h('span', { class: 'nl' }, 'More')),
    h('div', { class: 'navgap' }),
    sec('Address books', canOwn() ? h('button', { class: 'iconbtn', title: 'New address book', onclick: newBook }, icon('add', 's')) : null),
    S.books.map((b) => h('a', { href: `#/book/${b.id}`, 'data-v': 'book', class: listView && S.scope.kind === 'book' && +S.scope.id === b.id ? 'on' : null,
      style: { '--hue': b.color || (b.shared ? 'var(--c-purple)' : 'var(--c-teal)') } },
      h('span', { class: 'ic dotic' }, h('span', { class: 'dot' })), h('span', { class: 'nl' }, b.name), h('span', { class: 'n' }, b.count))),
    S.tags.length ? [h('div', { class: 'navgap' }), sec('Labels'),
      S.tags.map((t) => h('a', { href: `#/tag/${encodeURIComponent(t.tag)}`, 'data-v': 'tag', class: listView && S.scope.kind === 'tag' && S.scope.name === t.tag ? 'on' : null, style: { '--hue': 'var(--c-orange)' } },
        icon('tag'), h('span', { class: 'nl' }, t.tag), h('span', { class: 'n' }, t.n)))] : null,
    h('div', { class: 'navgap' }), sec('Manage'),
    link('import', '#/import', 'upload', 'Import and export', null, r.view === 'import', '--c-green'),
    link('cleanup', '#/cleanup', 'wrench', 'Clean up', S.status.suggestions || null, r.view === 'cleanup', '--c-amber'),
    h('div', { class: 'navfoot' }, link('settings', '#/settings', 'settings', 'Settings', null, r.view === 'settings')),
  ].flat(3).filter(Boolean));
  applySidebar();
  $('.navmore')?.classList.toggle('on', ['book', 'tag', 'import', 'cleanup', 'settings', 'iopix'].some((v) => (v === 'book' || v === 'tag') ? listView && S.scope.kind === v : r.view === v));
}
export function sideDockedPref() { try { return localStorage.getItem('iocontact.sidebar') !== '0'; } catch { return true; } }
export function applySidebar() {
  const body = document.body, btn = $('#sidebtn');
  const docked = innerWidth >= DOCK_MIN && sideDockedPref();
  body.classList.toggle('side-docked', docked);
  if (docked) closeNav();
  if (!btn) return;
  const [ic, title] = docked ? ['menuOpen', 'Hide the sidebar'] : innerWidth >= DOCK_MIN ? ['pin', 'Keep the sidebar open'] : ['close', 'Close the sidebar'];
  btn.replaceChildren(icon(ic)); btn.title = title; btn.setAttribute('aria-label', title);
}
export function sidebarButton() {
  if (document.body.classList.contains('side-docked')) { try { localStorage.setItem('iocontact.sidebar', '0'); } catch { /* */ } }
  else if (innerWidth >= DOCK_MIN) { try { localStorage.setItem('iocontact.sidebar', '1'); } catch { /* */ } }
  else { closeNav(); return; }
  applySidebar();
}
export function openNav() { document.body.classList.add('side-open'); $('#navscrim').hidden = false; }
export function closeNav() { document.body.classList.remove('side-open'); $('#navscrim').hidden = true; }
/** Phones: what the bottom bar has no room for. */
export function moreSheet() {
  const r = route(); const listView = ['list', 'contact', 'edit', 'new'].includes(r.view);
  const tile = (href, ic, label, hue, on) => h('a', { href, class: on ? 'on' : null, style: { '--hue': hue } }, h('span', { class: 'sic' }, icon(ic)), h('span', null, label));
  const grid = h('div', { class: 'sheetgrid' },
    S.books.map((b) => tile(`#/book/${b.id}`, 'book', b.name, b.color || (b.shared ? 'var(--c-purple)' : 'var(--c-teal)'), listView && S.scope.kind === 'book' && +S.scope.id === b.id)),
    S.tags.map((t) => tile(`#/tag/${encodeURIComponent(t.tag)}`, 'tag', t.tag, 'var(--c-orange)', listView && S.scope.kind === 'tag' && S.scope.name === t.tag)),
    S.status.iopix ? tile('#/iopix', 'image', 'ioPix people', 'var(--c-indigo)', r.view === 'iopix') : null,
    tile('#/import', 'upload', 'Import and export', 'var(--c-green)', r.view === 'import'),
    tile('#/cleanup', 'wrench', 'Clean up', 'var(--c-amber)', r.view === 'cleanup'),
    tile('#/settings', 'settings', 'Settings', 'var(--c-slate)', r.view === 'settings'));
  const p = dialog('More', grid, [{ label: 'Close', value: null }]);
  grid.addEventListener('click', (e) => { if (e.target.closest('a')) document.querySelector('.dialog-back')?.remove(); });
  return p;
}

// the suite's roles, each able to do what the one before can: a viewer only looks, a member keeps their own books,
// an editor changes the shared ones too
export const RANK = { none: 0, viewer: 1, member: 2, editor: 3, admin: 4 };
export const roleAtLeast = (r) => (RANK[S.user && S.user.role] || 0) >= RANK[r];
export const canOwn = () => roleAtLeast('member');
export const canShared = () => roleAtLeast('editor');

export async function newBook() {
  const name = h('input', { class: 't', placeholder: 'Name, e.g. Work or School friends' });
  const shared = h('input', { type: 'checkbox' });
  const body = h('div', null, name, canShared() ? h('label', { class: 'prefck', style: { marginTop: '10px' } }, shared, 'Shared with the whole family') : null);
  if (!await dialog('New address book', body, [{ label: 'Cancel', value: false }, { label: 'Create', value: true, primary: true }])) return;
  try { const r = await api('api/books', { method: 'POST', json: { name: name.value, shared: shared.checked } }); await loadMeta(); location.hash = `#/book/${r.book.id}`; } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ sign-in
export function showSignIn() {
  // like ioPix: a tile per account; one click for a passwordless account, a password for the others
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
    try { await api(first ? 'api/auth/setup' : 'api/auth/login', { method: 'POST', json: { name: n, password: p } }); location.reload(); } catch (x) { err.textContent = x.message; }
  };
  const go = (e) => { e.preventDefault(); login(name.value.trim(), pw.value); };
  document.body.append(h('div', { class: 'signin' }, h('form', { class: 'dialog', onsubmit: go },
    h('div', { class: 'brand' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }), h('span', { class: 'brand-name', style: { display: 'inline' } }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Contact'))),
    first ? h('p', { class: 'muted' }, 'Welcome. Make the first account: it is the admin, who adds the rest of the family in Settings.') : h('h2', null, 'Sign in'),
    tiles, form, err, h('div', { class: 'btns' }, btn))));
  if (first) { name.focus(); return; }
  const pick = (t) => tiles.querySelectorAll('.account').forEach((x) => x.classList.toggle('on', x === t));
  api('api/auth/accounts').then((d) => {
    if (!d.accounts.length) { name.focus(); return; }
    form.hidden = true; btn.hidden = true;
    const face = (a) => {
      const el = h('span', { class: 'av big', style: { '--h': hue(a.displayName || a.name) } }, initials(a.displayName || a.name));
      if (a.meContactId) { const img = h('img', { src: `api/auth/accounts/${a.id}/photo`, alt: '', onerror: () => img.remove() }); el.append(img); }
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
