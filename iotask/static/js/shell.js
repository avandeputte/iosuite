import { $, S, api, canOwn, canShared, closeDialogs, dialog, dragSort, fail, h, hue, icon, initials, loadLists, memberBadge, memberColor, store, toggleWho, writable } from './core.js';
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
    menu = h('div', { class: 'menu' },
      h('div', { class: 'who' }, h('b', null, S.user.displayName), h('div', { class: 'muted small' }, `${S.user.name} · ${S.user.role}`)),
      h('a', { class: 'mi', href: '#/settings', onclick: closeMenu }, icon('settings', 's'), 'Settings'),
      h('button', { class: 'mi', onclick: async () => { const r = await api('api/auth/logout', { method: 'POST' }); if (r && r.cloudflareLogout) location.href = r.cloudflareLogout; else location.reload(); } }, icon('logout', 's'), 'Sign out'));
    m.append(menu);
    setTimeout(() => document.addEventListener('click', outside), 0);
  };
  m.append(btn);
}
/* The suite (iosuite-shared's suite_apps): when other ioThing apps are registered, the app mark top left (in the sidebar; in
   the top bar on a phone) opens a menu of them, each a link to that app. Alone, the mark stays the link to Today. */
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
  // the apps, then the admin tools in a section of their own: the server sends those to their admins only
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
  if (choice) store.set('theme', choice);
  const t = choice || store.get('theme') || 'system';
  if (t === 'system') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
}

/* The sidebar, as in the other io apps: the name on top, the smart lists, the shared lists, the family, your own lists,
   Settings at the foot. It docks beside the page on a wide screen unless its button put it away (remembered); otherwise
   it slides over the page. Phones get a bottom bar instead. */
export const DOCK_MIN = 1100;
export const SMART = { today: ['Today', 'today', '--c-blue'], scheduled: ['Scheduled', 'event', '--c-rose'], all: ['All', 'inbox', '--c-slate'], done: ['Completed', 'done', '--c-green'] };
export function drawNav() {
  const nav = $('#nav'); const r = route();
  const link = (v, href, ic, label, n, on, hueVar) => h('a', { href, 'data-v': v, class: on ? 'on' : null, style: hueVar ? { '--hue': `var(${hueVar})` } : null },
    icon(ic), h('span', { class: 'nl' }, label), n ? h('span', { class: 'n' }, n) : null);
  const sec = (label, btn) => h('div', { class: 'navsec' }, h('span', null, label), btn || null);
  const listRow = (c) => h('a', { href: `#/list/${c.id}`, 'data-v': 'list', 'data-id': c.id, class: r.view === 'list' && r.id === c.id ? 'on' : null, style: { '--hue': c.color } },
    h('span', { class: 'ldot' }), h('span', { class: 'nl' }, c.name),
    h('span', { class: `n ${c.overdue ? 'late' : ''}`, title: c.overdue ? `${c.overdue} overdue` : null }, c.count || ''));
  const whoRow = (m) => h('a', { href: '#', 'data-v': 'who', class: `who ${S.who.has(m.id) ? 'picked' : ''}`, style: { '--mc': memberColor(m) },
    title: S.who.has(m.id) ? `Stop showing only ${m.displayName}'s tasks` : `Show only ${m.displayName}'s tasks`,
    onclick: (e) => { e.preventDefault(); toggleWho(m.id); } }, memberBadge(m, true), h('span', { class: 'nl' }, m.displayName));
  const shared = S.lists.filter((c) => c.shared), mine = S.lists.filter((c) => !c.shared);
  // the lists of a kind, in the order they were put in: drag one (with a mouse) to move it
  const group = (lists, can) => {
    const g = h('div', { class: 'navgrp' }, lists.map(listRow));
    if (can && lists.length > 1) dragSort(g, 'a', null, orderLists);
    return g;
  };
  const brandName = () => [h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Task')];
  nav.replaceChildren(...[
    h('div', { class: 'navhead' },
      S.suite.length
        ? h('div', { class: 'brand' },
          h('button', { class: 'suitebtn', title: 'ioThing apps', 'aria-label': 'ioThing apps', 'aria-haspopup': 'menu', onclick: (e) => toggleSuite(e.currentTarget) },
            h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' })),
          h('a', { class: 'brand-name', href: '#/', title: 'Today' }, brandName()))
        : h('a', { class: 'brand', href: '#/', title: 'Today' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }),
          h('span', { class: 'brand-name' }, brandName())),
      h('button', { id: 'sidebtn', class: 'iconbtn', onclick: sidebarButton })),
    Object.entries(SMART).map(([k, [label, ic, hv]]) => link(k, `#/${k}`, ic, label, k === 'done' ? null : (k === 'today' ? S.counts.today : S.counts[k]) || null, r.view === k, hv)),
    h('button', { class: 'navmore', 'data-v': 'more', title: 'More', onclick: moreSheet }, icon('more'), h('span', { class: 'nl' }, 'More')),
    h('div', { class: 'navgap' }),
    sec('Shared', canShared() ? h('button', { class: 'iconbtn', title: 'New shared list', onclick: () => newList(true) }, icon('add', 's')) : null),
    group(shared, canShared()),
    S.members.length > 1 ? [h('div', { class: 'navgap' }),
      sec('Family', S.who.size ? h('button', { class: 'pillbtn noic tiny', title: 'Show everyone again', onclick: () => toggleWho(null) }, 'Everyone') : null),
      S.members.map(whoRow)] : null,
    h('div', { class: 'navgap' }),
    canOwn() || mine.length ? sec('Mine', canOwn() ? h('button', { class: 'iconbtn', title: 'New private list', onclick: () => newList(false) }, icon('add', 's')) : null) : null,
    group(mine, canOwn()),
    h('div', { class: 'navgap' }), sec('Manage'),
    link('activity', '#/activity', 'history', 'Activity', null, r.view === 'activity', '--c-slate'),
    writable().length ? link('import', '#/import', 'upload', 'Import', null, r.view === 'import', '--c-teal') : null,
    h('div', { class: 'navfoot' }, link('settings', '#/settings', 'settings', 'Settings', null, r.view === 'settings')),
  ].flat(3).filter(Boolean));
  applySidebar();
  $('.navmore')?.classList.toggle('on', ['list', 'import', 'settings', 'search', 'activity'].includes(r.view));
}
export async function orderLists(ids) {
  try { await api('api/lists/order', { method: 'POST', json: { ids } }); await loadLists(); } catch (e) { fail(e); drawNav(); }
}
export function applySidebar() {
  const body = document.body, btn = $('#sidebtn');
  const docked = innerWidth >= DOCK_MIN && store.get('sidebar') !== '0';
  body.classList.toggle('side-docked', docked);
  if (docked) closeNav();
  if (!btn) return;
  const [ic, title] = docked ? ['menuOpen', 'Hide the sidebar'] : innerWidth >= DOCK_MIN ? ['pin', 'Keep the sidebar open'] : ['close', 'Close the sidebar'];
  btn.replaceChildren(icon(ic)); btn.title = title; btn.setAttribute('aria-label', title);
}
export function sidebarButton() {
  if (document.body.classList.contains('side-docked')) store.set('sidebar', '0');
  else if (innerWidth >= DOCK_MIN) store.set('sidebar', '1');
  else { closeNav(); return; }
  applySidebar();
}
export function openNav() { document.body.classList.add('side-open'); $('#navscrim').hidden = false; }
export function closeNav() { document.body.classList.remove('side-open'); $('#navscrim').hidden = true; }
/** Phones: what the bottom bar has no room for (the lists, the family filter, import, settings). */
export function moreSheet() {
  const r = route();
  const tile = (href, ic, label, hueV, on, click) => h('a', { href, class: on ? 'on' : null, style: { '--hue': hueV }, onclick: click || null }, h('span', { class: 'sic' }, icon(ic)), h('span', null, label));
  const grid = h('div', { class: 'sheetgrid' },
    S.lists.map((c) => tile(`#/list/${c.id}`, 'list', c.name, c.color, r.view === 'list' && r.id === c.id)),
    S.members.length > 1 ? S.members.map((m) => tile('#', 'person', S.who.has(m.id) ? `Only ${m.displayName}` : m.displayName, memberColor(m), S.who.has(m.id),
      (e) => { e.preventDefault(); e.stopPropagation(); closeDialogs(); toggleWho(m.id); moreSheet(); })) : null,
    tile('#/activity', 'history', 'Activity', 'var(--c-slate)', r.view === 'activity'),
    writable().length ? tile('#/import', 'upload', 'Import', 'var(--c-teal)', r.view === 'import') : null,
    tile('#/settings', 'settings', 'Settings', 'var(--c-slate)', r.view === 'settings'));
  const p = dialog('More', grid, [{ label: 'Close', value: null }]);
  grid.addEventListener('click', (e) => { const a = e.target.closest('a'); if (a && a.getAttribute('href') !== '#') closeDialogs(); });
  return p;
}

export const SWATCHES = ['#146b5e', '#1a73e8', '#e0426a', '#e8710a', '#8e44d6', '#1e8e3e', '#e8a100', '#b5452f', '#4b53c7', '#5f6b7a'];
export function colorPicker(value, onPick) {
  let cur = value || SWATCHES[0];
  const own = h('input', { type: 'color', value: cur, title: 'Another colour' });
  const row = h('div', { class: 'colors' });
  const draw = () => row.replaceChildren(...SWATCHES.map((c) => h('button', { type: 'button', class: c === cur ? 'on' : '', style: { '--c': c }, title: c, onclick: () => { cur = c; own.value = c; draw(); if (onPick) onPick(c); } })), own);
  own.oninput = () => { cur = own.value; draw(); };
  own.onchange = () => { if (onPick) onPick(cur); };
  draw();
  row.get = () => cur;
  return row;
}
export async function newList(shared) {
  const name = h('input', { class: 't', placeholder: shared ? 'Name, e.g. Groceries or Chores' : 'Name, e.g. Work' });
  const col = colorPicker(SWATCHES[S.lists.length % SWATCHES.length]);
  const tpls = (await api('api/templates').catch(() => ({ items: [] }))).items;
  const from = h('select', { class: 't' }, h('option', { value: '' }, 'An empty list'), tpls.map((t) => h('option', { value: t.id }, `The template ${t.name} (${t.count} tasks)`)));
  const body = h('div', { style: { display: 'grid', gap: '12px' } }, name, col, tpls.length ? h('label', { class: 'field' }, h('span', null, 'Start with'), from) : null,
    h('p', { class: 'muted small', style: { margin: 0 } }, shared ? 'Everyone in the family sees it and ticks tasks off; editors change it.' : 'Only you see it.'));
  if (!await dialog(shared ? 'New shared list' : 'New private list', body, [{ label: 'Cancel', value: false }, { label: 'Create', value: true, primary: true }])) return;
  try {
    const picked = tpls.find((t) => t.id === +from.value);
    const r = await api('api/lists', { method: 'POST', json: { name: name.value || (picked ? picked.name : ''), shared, color: col.get() } });
    if (picked) await api(`api/templates/${picked.id}/apply`, { method: 'POST', json: { listId: r.list.id } });
    await loadLists();
    location.hash = `#/list/${r.list.id}`;
  } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ sign-in
export function showSignIn() {
  // as in the other io apps: a tile per account; one click for a passwordless account, a password for the others
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
  const submit = (e) => { e.preventDefault(); login(name.value.trim(), pw.value); };
  document.body.append(h('div', { class: 'signin' }, h('form', { class: 'dialog', onsubmit: submit },
    h('div', { class: 'brand' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }), h('span', { class: 'brand-name', style: { display: 'inline' } }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Task'))),
    first ? h('p', { class: 'muted' }, 'Welcome. Make the first account: it is the admin, who adds the rest of the family in Settings. (Already use another io app? Sign in there first, or use the same name and password here once the apps share their accounts.)') : h('h2', null, 'Sign in'),
    tiles, form, err, h('div', { class: 'btns' }, btn))));
  if (first) { name.focus(); return; }
  const pick = (t) => tiles.querySelectorAll('.account').forEach((x) => x.classList.toggle('on', x === t));
  api('api/auth/accounts').then((d) => {
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
