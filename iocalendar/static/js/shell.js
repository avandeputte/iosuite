import { $, DOW, ICONS, LOCAL_TZ, REFRESH_HOURS, S, addDays, addMonths, api, canOwn, canShared, dialog, fail, h, hue, icon, initials, isAuto, loadCals, memberBadge, memberColor, sameDay, startOfWeek, tasksOn, billsOn, billsOffered, toggleBills, toast, toggleCal, toggleTasks, toggleWho, weekStart, writable, ymd } from './core.js';
import { go, route } from './main.js';
import { drawView } from './views.js';

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
    const theme = localStorage.getItem('iocalendar.theme') || 'system';
    menu = h('div', { class: 'menu' },
      h('div', { class: 'who' }, h('b', null, S.user.displayName), h('div', { class: 'muted small' }, `${S.user.name} · ${S.user.role}`)),
      h('a', { class: 'mi', href: '#/settings/account', onclick: closeMenu }, icon('person', 's'), 'Account'),
      h('a', { class: 'mi', href: '#/settings/devices', onclick: closeMenu }, icon('devices', 's'), 'Connect apps and devices'),
      h('button', { class: 'mi', onclick: () => { const n = { system: 'light', light: 'dark', dark: 'system' }[theme]; localStorage.setItem('iocalendar.theme', n); applyTheme(); closeMenu(); toast(`Appearance: ${n}`); } },
        icon('theme', 's'), `Appearance: ${theme}`),
      h('a', { class: 'mi', href: '#/settings', onclick: closeMenu }, icon('settings', 's'), 'Settings'),
      h('button', { class: 'mi', onclick: async () => { const r = await api('api/auth/logout', { method: 'POST' }); if (r && r.cloudflareLogout) location.href = r.cloudflareLogout; else location.reload(); } }, icon('logout', 's'), 'Sign out'));
    m.append(menu);
    setTimeout(() => document.addEventListener('click', outside), 0);
  };
  m.append(btn);
}
/* The suite (iosuite-shared's suite_apps): when other ioThing apps are registered, the app mark top left (in the sidebar; in
   the top bar on a phone) opens a menu of them, each a link to that app. Alone, the mark stays the link to the calendar. */
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
  try { if (choice) localStorage.setItem('iocalendar.theme', choice); } catch { /* private mode */ }
  let t = choice; try { t = t || localStorage.getItem('iocalendar.theme'); } catch { /* */ }
  t = t || 'system';
  if (t === 'system') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
}

/** A small month in the sidebar: pick a day to go to it. */
export function miniMonth() {
  const base = S.mini || new Date(S.date.getFullYear(), S.date.getMonth(), 1);
  const first = startOfWeek(base), today = new Date();
  const g = h('div', { class: 'g' }, [0, 1, 2, 3, 4, 5, 6].map((i) => h('span', { class: 'h' }, DOW((i + weekStart()) % 7, 'narrow'))));
  for (let i = 0; i < 42; i++) {
    const d = addDays(first, i);
    g.append(h('span', { class: [d.getMonth() !== base.getMonth() ? 'o' : '', sameDay(d, today) ? 't' : sameDay(d, S.date) ? 'sel' : ''].join(' '),
      onclick: () => go(S.view === 'agenda' ? 'day' : S.view, d) }, d.getDate()));
  }
  return h('div', { class: 'mini' }, h('div', { class: 'mh' },
    h('span', null, base.toLocaleDateString([], { month: 'long', year: 'numeric' })),
    h('span', null, h('button', { class: 'iconbtn', title: 'Previous month', onclick: () => { S.mini = addMonths(base, -1); drawNav(); } }, icon('chevL', 's')),
      h('button', { class: 'iconbtn', title: 'Next month', onclick: () => { S.mini = addMonths(base, 1); drawNav(); } }, icon('chevR', 's')))), g);
}

/* The sidebar, as in ioPix and ioContact: the name on top, the destinations, the calendars (each with its colour as a
   check box that shows or hides it), Settings at the foot. It docks beside the page on a wide screen unless its button
   put it away (remembered); otherwise it slides over the page. Phones get a bottom bar instead. */
export const DOCK_MIN = 1100;
export function drawNav() {
  const nav = $('#nav'); const r = route();
  const calView = ['month', 'week', 'day'].includes(r.view);
  const link = (v, href, ic, label, n, on, hue) => h('a', { href, 'data-v': v, class: on ? 'on' : null, style: hue ? { '--hue': `var(${hue})` } : null },
    icon(ic), h('span', { class: 'nl' }, label), n ? h('span', { class: 'n' }, n) : null);
  const sec = (label, btn) => h('div', { class: 'navsec' }, h('span', null, label), btn || null);
  const check = '<svg viewBox="0 0 24 24"><path d="' + ICONS.check + '"/></svg>';
  const calRow = (c) => {
    const ck = h('span', { class: 'ck' }); ck.innerHTML = check;
    return h('a', { href: '#', 'data-v': 'cal', class: `cal ${S.hidden.has(c.id) ? '' : 'shown'}`, title: `${S.hidden.has(c.id) ? 'Show' : 'Hide'} ${c.name}`,
      style: { '--hue': c.color }, onclick: (e) => { e.preventDefault(); toggleCal(c.id); } },
      ck, h('span', { class: 'nl' }, c.name), h('span', { class: 'n' }, isAuto(c) ? '' : c.count || ''));
  };
  const whoRow = (m) => h('a', { href: '#', 'data-v': 'who', class: `who ${S.who.has(m.id) ? 'picked' : ''}`, style: { '--mc': memberColor(m) },
    title: S.who.has(m.id) ? `Stop showing only ${m.displayName}'s events` : `Show only ${m.displayName}'s events`,
    onclick: (e) => { e.preventDefault(); toggleWho(m.id); } }, memberBadge(m, true), h('span', { class: 'nl' }, m.displayName));
  const taskRow = () => {
    const ck = h('span', { class: 'ck' }); ck.innerHTML = check;
    const why = tasksOn() && S.tasks.available === false ? S.tasks.reason : null;
    return h('a', { href: '#', 'data-v': 'cal', class: `cal ${tasksOn() ? 'shown' : ''} ${why ? 'away' : ''}`, style: { '--hue': '#146b5e' },
      title: why || (tasksOn() ? 'Hide the tasks that are due' : 'Show the tasks on the day they are due'),
      onclick: (e) => { e.preventDefault(); toggleTasks(); } }, ck, h('span', { class: 'nl' }, 'Tasks due'));
  };
  const billRow = () => {
    const ck = h('span', { class: 'ck' }); ck.innerHTML = check;
    const why = billsOn() && S.bills.available === false ? S.bills.reason : null;
    return h('a', { href: '#', 'data-v': 'cal', class: `cal ${billsOn() ? 'shown' : ''} ${why ? 'away' : ''}`, style: { '--hue': '#94650a' },
      title: why || (billsOn() ? 'Hide the bills that are due' : 'Show the household’s bills on the day they are due'),
      onclick: (e) => { e.preventDefault(); toggleBills(); } }, ck, h('span', { class: 'nl' }, 'Bills due'));
  };
  const shared = S.cals.filter((c) => c.shared), mine = S.cals.filter((c) => !c.shared);
  nav.replaceChildren(...[
    h('div', { class: 'navhead' },
      S.suite.length
        ? h('div', { class: 'brand' },
          h('button', { class: 'suitebtn', title: 'ioThing apps', 'aria-label': 'ioThing apps', 'aria-haspopup': 'menu', onclick: (e) => toggleSuite(e.currentTarget) },
            h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' })),
          h('a', { class: 'brand-name', href: '#/', title: 'Calendar' }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Calendar')))
        : h('a', { class: 'brand', href: '#/', title: 'Calendar' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }),
          h('span', { class: 'brand-name' }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Calendar'))),
      h('button', { id: 'sidebtn', class: 'iconbtn', onclick: sidebarButton })),
    link('calendar', `#/${S.view === 'agenda' ? 'month' : S.view}/${ymd(S.date)}`, 'today', 'Calendar', null, calView, '--c-rose'),
    link('agenda', '#/agenda', 'agenda', 'Agenda', null, r.view === 'agenda', '--c-blue'),
    h('button', { class: 'navmore', 'data-v': 'more', title: 'More', onclick: moreSheet }, icon('more'), h('span', { class: 'nl' }, 'More')),
    miniMonth(),
    sec('Shared', canShared() ? h('button', { class: 'iconbtn', title: 'New shared calendar', onclick: () => newCalendar(true) }, icon('add', 's')) : null),
    shared.map(calRow),
    S.members.length > 1 ? [h('div', { class: 'navgap' }),
      sec('Family', S.who.size ? h('button', { class: 'pillbtn noic tiny', title: 'Show everyone again', onclick: () => toggleWho(null) }, 'Everyone') : null),
      S.members.map(whoRow)] : null,
    h('div', { class: 'navgap' }),
    canOwn() || mine.length ? sec('Mine', canOwn() ? h('button', { class: 'iconbtn', title: 'New private calendar', onclick: () => newCalendar(false) }, icon('add', 's')) : null) : null,
    mine.map(calRow),
    S.status.iotask ? [h('div', { class: 'navgap' }),
      sec('ioTask', S.tasks.url ? h('a', { class: 'iconbtn', href: S.tasks.url, target: '_blank', rel: 'noopener', title: 'Open ioTask' }, icon('open', 's')) : null),
      taskRow()] : null,
    billsOffered() ? [h('div', { class: 'navgap' }),
      sec('ioMoney', S.bills.url ? h('a', { class: 'iconbtn', href: S.bills.url, target: '_blank', rel: 'noopener', title: 'Open ioMoney' }, icon('open', 's')) : null),
      billRow()] : null,
    h('div', { class: 'navgap' }), sec('Manage'),
    writable().some((c) => !isAuto(c)) ? link('import', '#/import', 'upload', 'Import', null, r.view === 'import', '--c-green') : null,
    h('div', { class: 'navfoot' }, link('settings', '#/settings', 'settings', 'Settings', null, r.view === 'settings')),
  ].flat(3).filter(Boolean));
  applySidebar();
  $('.navmore')?.classList.toggle('on', ['import', 'settings', 'search'].includes(r.view));
}
export function sideDockedPref() { try { return localStorage.getItem('iocalendar.sidebar') !== '0'; } catch { return true; } }
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
  if (document.body.classList.contains('side-docked')) { try { localStorage.setItem('iocalendar.sidebar', '0'); } catch { /* */ } }
  else if (innerWidth >= DOCK_MIN) { try { localStorage.setItem('iocalendar.sidebar', '1'); } catch { /* */ } }
  else { closeNav(); return; }
  applySidebar();
}
export function openNav() { document.body.classList.add('side-open'); $('#navscrim').hidden = false; }
export function closeNav() { document.body.classList.remove('side-open'); $('#navscrim').hidden = true; }
/** Phones: what the bottom bar has no room for (the calendars to show, import, settings). */
export function moreSheet() {
  const r = route();
  const tile = (href, ic, label, hue, on, click) => h('a', { href, class: on ? 'on' : null, style: { '--hue': hue }, onclick: click || null }, h('span', { class: 'sic' }, icon(ic)), h('span', null, label));
  const grid = h('div', { class: 'sheetgrid' },
    S.cals.map((c) => tile('#', S.hidden.has(c.id) ? 'close' : 'check', c.name, c.color, !S.hidden.has(c.id), (e) => { e.preventDefault(); e.stopPropagation(); toggleCal(c.id); document.querySelector('.dialog-back')?.remove(); moreSheet(); })),
    S.members.length > 1 ? S.members.map((m) => tile('#', 'person', S.who.has(m.id) ? `Only ${m.displayName}` : m.displayName, memberColor(m), S.who.has(m.id),
      (e) => { e.preventDefault(); e.stopPropagation(); toggleWho(m.id); document.querySelector('.dialog-back')?.remove(); moreSheet(); })) : null,
    writable().some((c) => !isAuto(c)) ? tile('#/import', 'upload', 'Import', 'var(--c-green)', r.view === 'import') : null,
    tile('#/settings', 'settings', 'Settings', 'var(--c-slate)', r.view === 'settings'));
  const p = dialog('More', grid, [{ label: 'Close', value: null }]);
  grid.addEventListener('click', (e) => { const a = e.target.closest('a'); if (a && a.getAttribute('href') !== '#') document.querySelector('.dialog-back')?.remove(); });
  return p;
}

export const SWATCHES = ['#8e44d6', '#0b8a9e', '#1a73e8', '#e0426a', '#1e8e3e', '#e8710a', '#4b53c7', '#e8a100', '#5f6b7a', '#b5452f'];
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
export async function newCalendar(shared) {
  const name = h('input', { class: 't', placeholder: shared ? 'Name, e.g. Soccer or School' : 'Name, e.g. Work' });
  const col = colorPicker(SWATCHES[S.cals.length % SWATCHES.length]);
  // or an outside calendar: its web address (school, sports club, bin collection), fetched again on a schedule
  const url = h('input', { class: 't', type: 'url', inputmode: 'url', autocomplete: 'off', spellcheck: 'false', placeholder: 'https://… or webcal://… (optional)' });
  const every = h('select', { class: 't' }, REFRESH_HOURS.map(([n, l]) => h('option', { value: n, selected: n === 6 ? true : null }, l)));
  const subRow = h('div', { style: { display: 'grid', gap: '6px' }, hidden: true },
    h('label', { class: 'field' }, h('span', null, 'Fetch it again'), every),
    h('p', { class: 'muted small', style: { margin: 0 } }, 'Read-only here: its events change only at the address. Leave the name empty to use the calendar\'s own.'));
  url.oninput = () => { subRow.hidden = !url.value.trim(); name.placeholder = url.value.trim() ? 'Name (optional)' : shared ? 'Name, e.g. Soccer or School' : 'Name, e.g. Work'; };
  const body = h('div', { style: { display: 'grid', gap: '12px' } }, name, col,
    h('label', { class: 'field' }, h('span', null, 'Subscribe to an outside calendar by its web address'), url), subRow,
    h('p', { class: 'muted small', style: { margin: 0 } }, shared ? 'Everyone in the family sees it; editors change it.' : 'Only you see it.'));
  for (;;) {  // a wrong address keeps the dialog's answers for another try
    if (!await dialog(shared ? 'New shared calendar' : 'New private calendar', body, [{ label: 'Cancel', value: false }, { label: 'Create', value: true, primary: true }])) return;
    try {
      if (url.value.trim()) {
        toast('Reading the calendar…');
        const r = await api('api/subscriptions', { method: 'POST', json: { url: url.value.trim(), name: name.value, shared, color: col.get(), refreshHours: Number(every.value) } });
        toast(`${r.calendar.name}: ${r.calendar.count || 0} events`);
      } else {
        await api('api/calendars', { method: 'POST', json: { name: name.value, shared, color: col.get(), timezone: LOCAL_TZ } });
      }
      await loadCals(); drawView(); return;
    } catch (e) { fail(e); }
  }
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
    h('div', { class: 'brand' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }), h('span', { class: 'brand-name', style: { display: 'inline' } }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Calendar'))),
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
