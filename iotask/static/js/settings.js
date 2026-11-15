import { $, S, api, canOwn, canShared, confirmDialog, copyRow, defaultList, dragSort, fail, h, icon, loadLists, saveSettings, store, toast, writable } from './core.js';
import { SMART, applyTheme, colorPicker, drawNav, drawUser, newList, orderLists } from './shell.js';
import { saveTemplate, smartAdd } from './lists.js';
import { onRoute } from './main.js';
import { profileScope as scopeSelect } from '../../api/auth/ui.js';

// ------------------------------------------------------------------ settings
export async function showSettings(page, r) {
  const adm = S.user.role === 'admin';
  const tabs = [['account', 'Account'], ['display', 'Display'], ['devices', 'Apps and devices'], ['lists', 'Lists'],
    ...(adm ? [['server', 'Server']] : []),
    ...(S.user.suiteAdmin ? [['security', SUITE_TABS.security], ['global', SUITE_TABS.global]] : [])];
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Settings')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/settings/${k}`; } }, l))));
  const body = h('div'); page.append(body);
  await ({ account: setAccount, display: setDisplay, devices: setDevices, lists: setLists, server: setServer,
    security: setSuite, global: setSuite }[r.tab] || setAccount)(body, r);
}
const fld = (l, e) => h('label', { class: 'field' }, h('span', null, l), e);
export const kv = (k, v) => h('div', { class: 'kv' }, h('div', { class: 'k' }, k), h('div', { class: 'v', style: { flex: 1 } }, typeof v === 'string' ? copyRow(v) : v));

export const accountUi = () => import(new URL('api/auth/ui.js', document.baseURI).href);
/** Settings › Account: display name, email and password, then the app passwords: iosuite-shared's panels (the same in every io app). */
export async function setAccount(el) {
  const ui = await accountUi();
  const pw = h('div');
  await ui.mountAccount(el, { toast, onSaved: (u) => { Object.assign(S.user, u); drawUser(); } });
  el.append(pw);
  await ui.mountAppPasswords(pw, { toast, syncOnly: 'Reminders apps only (CalDAV)' });
}

/** Settings › Display: the theme (saved with the account) and where the app opens and new tasks go. */
export async function setDisplay(el) {
  const ui = await accountUi();
  const save = async (changes) => { await saveSettings(changes); drawNav(); toast('Saved'); };
  const sv = h('select', { class: 't', onchange: (e) => save({ startView: e.target.value }) },
    Object.entries(SMART).slice(0, 3).map(([v, [l]]) => h('option', { value: v, selected: v === (S.settings.startView || 'today') ? true : null }, l)));
  const dl = h('select', { class: 't', onchange: (e) => save({ defaultList: +e.target.value }) },
    writable().map((c) => h('option', { value: c.id, selected: c.id === defaultList()?.id ? true : null }, `${c.name}${c.shared ? ' (shared)' : ''}`)));
  const qa = h('input', { type: 'checkbox', checked: smartAdd(), onchange: (e) => save({ quickAdd: e.target.checked ? 'on' : 'off' }) });
  el.append(ui.box('theme', 'Appearance', ui.themeRow(S.settings.theme || store.get('theme') || 'system', (t) => { S.settings.theme = t; applyTheme(t); })),
    h('div', { class: 'box' }, h('h2', null, icon('tune'), 'Tasks'), h('div', { class: 'grid' }, fld('Open on', sv), fld('New tasks go to', dl)),
      h('p', null, h('label', { class: 'check' }, qa, ' The new-task line understands what is typed')),
      h('p', { class: 'muted small' }, 'When (tomorrow 5pm, friday, 15 nov, in 2 weeks), how often (every monday, monthly, every 2 weeks after done), how important (!high), which list (#groceries) and for whom (@emma) become the task’s fields: “Pay rent every month on the 1st 9am !high”. What was understood shows under the line while you type; the rest is the title.')));
}

/** The profile through a short-lived link instead of the form post: the app on the Home Screen opens a download in a
 * separate sheet without its cookies, which a link opens by itself (the form post stays the fallback without script). */
export async function downloadProfile(e) {
  e.preventDefault();
  const f = e.target;
  const btn = f.querySelector('button[type=submit]');
  if (btn) btn.disabled = true;
  try {
    const all = f.elements.scope && f.elements.scope.value === 'suite';
    const res = await api(all ? 'api/apple-profile/suite/link' : 'api/apple-profile/link', { method: 'POST', json: { label: f.elements.label.value, password: f.elements.password.value } });
    location.href = res.url;
  } catch (err) {
    toast(err.message);
  } finally {
    if (btn) setTimeout(() => { btn.disabled = false; }, 1500);
  }
}

/** The "Set up" choice of the profile box: this app only, or every app that syncs (iosuite-shared's suite profile),
 * offered when the account may use two or more of them. Fields marked data-own belong to this app's own profile. */
export const profileScope = (apps, own) => { const s = scopeSelect(apps, own, { class: 't' }); return s && fld('Set up', s); };

/** Settings › Apps and devices: how to connect each kind of app (the app passwords themselves are on Settings › Account). */
export async function setDevices(el) {
  const info = await api('api/connect');
  const suiteApps = S.user.passwordless ? [] : (await api('api/apple-profile/suite').catch(() => ({ apps: [] }))).apps;
  const canPw = !S.user.passwordless;
  const isApple = /iPhone|iPad|Macintosh/.test(navigator.userAgent);
  const plabel = h('input', { class: 't', name: 'label', value: /iPad/.test(navigator.userAgent) ? 'iPad' : /Macintosh/.test(navigator.userAgent) ? 'Mac' : 'iPhone', style: 'max-width:200px' });
  const how = (summary, ...kids) => h('details', null, h('summary', { class: 'lnk' }, summary), ...kids);
  el.append(...[
    canPw ? h('div', { class: 'box' }, h('h2', null, icon('devices'), 'iPhone, iPad and Mac'),
      h('p', null, 'A profile that adds your lists to Apple Reminders in one step. Tasks you add or tick off there show up here, and the other way round.'),
      h('form', { method: 'POST', action: 'api/apple-profile', class: 'pform', onsubmit: downloadProfile },
        profileScope(suiteApps, 'ioTask'),
        fld('Device name', plabel),
        fld('Password', h('select', { class: 't', name: 'password' }, h('option', { value: 'new' }, 'Include a new app password'), h('option', { value: 'ask' }, 'Ask on the device'))),
        h('p', null, h('button', { class: 'pillbtn primary', type: 'submit' }, icon('download', 's'), 'Download the profile'))),
      how('How to install', h('p', { class: 'muted small' }, isApple ? 'Open the download, then Settings › Profile Downloaded › Install.' : 'Download it in Safari on the iPhone or iPad, then Settings › Profile Downloaded › Install. On a Mac: open the file, then System Settings › Privacy & Security › Profiles.',
        ' iOS shows the profile as “Not Verified”: that is expected. Revoke its app password under Settings › Account if the device is lost.',
        suiteApps.length > 1 ? ' A profile for all apps holds one app password per app; revoke each one in its own app.' : null),
      h('p', { class: 'muted small' }, 'The lists appear in Reminders under the account “ioTask”. Lists made there are made here too.'))) : null,
    h('div', { class: 'box' }, h('h2', null, icon('list'), 'Reminders and tasks apps (CalDAV)'),
      h('p', null, 'Two-way sync with your user name and an app password (Settings › Account).'),
      kv('Server', info.server), kv('User name', info.user), kv('CalDAV', info.caldav),
      how('Address of each list', info.lists.map((c) => kv(c.name, c.caldav))),
      how('How to connect', h('p', { class: 'muted small' }, 'Apple Reminders: iPhone Settings › Apps › Reminders › Reminders Accounts › Add Account › Other › Add CalDAV Account (Mac: System Settings › Internet Accounts › Add Other Account › CalDAV account). Android: DAVx⁵ with jtx Board, Tasks.org or OpenTasks. Also Thunderbird and Evolution.'),
        h('p', { class: 'muted small' }, 'Behind Cloudflare Access, add a Bypass policy for /dav/*, /.well-known/caldav and /profile/* (and /mcp).'))),
    S.status.mcp ? h('div', { class: 'box' }, h('h2', null, icon('ai'), 'AI assistants (MCP)'),
      h('p', null, 'Give the assistant its own app password (not “Reminders apps only”), sent as a Bearer token.'),
      kv('MCP address', info.mcp),
      how('Setup for Claude Code and JSON-configured apps',
        copyRow(`claude mcp add --transport http iotask ${info.mcp} --header "Authorization: Bearer APP-PASSWORD"`),
        copyRow(JSON.stringify({ mcpServers: { iotask: { command: 'npx', args: ['-y', 'mcp-remote', info.mcp, '--header', 'Authorization: Bearer APP-PASSWORD'] } } }))))
      : (S.user.role === 'admin' ? h('div', { class: 'box' }, h('h2', null, icon('ai'), 'AI assistants (MCP)'), h('p', { class: 'muted' }, 'Off. Turn it on in ', h('a', { class: 'lnk', href: '#/settings/server' }, 'Settings › Server'), '.')) : null),
    h('div', { class: 'box' }, h('h2', null, icon('link'), 'Other apps (REST API)'),
      h('p', null, 'JSON or iCalendar with your user name and an app password. ', h('a', { class: 'lnk', href: info.api, target: '_blank' }, 'API documentation')),
      copyRow(`curl -u ${info.user}:APP-PASSWORD "${info.server}/api/tasks?due=today"`))].filter(Boolean));
}

export async function setLists(el, r) {
  await loadLists();
  const tpls = (await api('api/templates').catch(() => ({ items: [] }))).items;
  const box = (c) => {
    const save = async (body) => { try { await api(`api/lists/${c.id}`, { method: 'PATCH', json: body }); await loadLists(); toast('Saved'); } catch (e) { fail(e); } };
    const name = h('input', { class: 't', value: c.name, onchange: (e) => save({ name: e.target.value }) });
    const desc = h('input', { class: 't', value: c.description || '', placeholder: 'What it is for', onchange: (e) => save({ description: e.target.value }) });
    const col = colorPicker(c.color, (v) => save({ color: v }));
    return h('div', { class: 'box', id: `list-${c.id}`, 'data-id': c.id, style: { '--c': c.color } },
      h('h2', null, c.writable ? h('span', { class: 'grip', title: 'Drag to move the list' }, icon('grip', 's')) : null, h('span', { class: 'ldot', style: { '--hue': c.color } }), c.name,
        h('span', { class: 'muted small', style: { fontWeight: 400 } }, c.shared ? 'shared with everyone' : 'only you')),
      c.writable ? [h('div', { class: 'grid' }, fld('Name', name), fld('Description', desc)), h('div', { style: { margin: '10px 0' } }, col),
        h('p', null, h('a', { class: 'pillbtn noic', href: `api/lists/${c.id}/export` }, 'Export (.ics)'), ' ',
          h('button', { class: 'pillbtn noic', onclick: () => saveTemplate(c).then(() => onRoute()) }, 'Save as a template…'), ' ',
          !c.shared || S.user.role === 'admin' ? h('button', { class: 'pillbtn noic danger', onclick: async () => {
            if (!await confirmDialog('Delete list', `Delete ${c.name} and its tasks? Apps that sync it lose it too.`, 'Delete', true)) return;
            try { await api(`api/lists/${c.id}`, { method: 'DELETE' }); await loadLists(); onRoute(); } catch (e) { fail(e); }
          } }, 'Delete') : null)]
        : h('p', { class: 'muted' }, `${c.count || 0} open tasks. Editors and admins change shared lists.`));
  };
  // the lists of a kind, in their order: a list moves by its grip (the sidebar follows)
  const group = (lists) => {
    const g = h('div', { class: `listboxes ${lists.length > 1 ? '' : 'one'}` }, lists.map(box));
    dragSort(g, '.box', '.grip', orderLists);
    return g;
  };
  const tplRow = (t) => h('tr', null,
    h('td', null, t.writable ? h('input', { class: 't', value: t.name, 'aria-label': 'Name', onchange: async (e) => { try { await api(`api/templates/${t.id}`, { method: 'PATCH', json: { name: e.target.value } }); toast('Saved'); } catch (x) { fail(x); } } }) : t.name),
    h('td', { class: 'muted' }, `${t.count} tasks`), h('td', { class: 'muted' }, t.shared ? 'shared with everyone' : 'only you'),
    h('td', { style: { textAlign: 'right' } }, t.writable ? h('button', { class: 'pillbtn noic danger', onclick: async () => {
      if (!await confirmDialog('Delete template', `Delete the template ${t.name}? The lists made from it stay.`, 'Delete', true)) return;
      try { await api(`api/templates/${t.id}`, { method: 'DELETE' }); onRoute(); } catch (x) { fail(x); }
    } }, 'Delete') : null));
  el.append(h('p', null, canShared() ? h('button', { class: 'pillbtn', onclick: () => newList(true) }, icon('add', 's'), 'New shared list') : null, ' ',
    canOwn() ? h('button', { class: 'pillbtn', onclick: () => newList(false) }, icon('add', 's'), 'New private list') : null),
  group(S.lists.filter((c) => c.shared)), group(S.lists.filter((c) => !c.shared)),
  h('div', { class: 'box' }, h('h2', null, icon('template'), 'Templates'),
    h('p', { class: 'muted' }, 'A list’s tasks kept to add again: a packing list, the weekly shop. Save one from a list (here, or in the list’s ⋯ menu); add its tasks with “Add from a template…” in a list’s ⋯ menu, or start a new list with it.'),
    tpls.length ? h('table', { class: 't' }, tpls.map(tplRow)) : null));
  if (r.sub) setTimeout(() => $(`#list-${r.sub}`)?.scrollIntoView({ block: 'start' }), 0);
}

/** Settings › Security and Global settings (suite admins): the people, their role in every app, app
    passwords, sign-in at the proxy; the apps, keys and tokens. The same panel in every io app, served by iosuite-shared. */
export const SUITE_TABS = { security: 'Security', global: 'Global settings' };
export async function setSuite(el, r) {
  let ui;
  try { ui = await import(new URL('api/suite-admin/ui.js', document.baseURI).href); } catch (e) { el.append(h('p', { class: 'warn' }, `The panel did not load: ${e.message}`)); return; }
  await ui.mount(el, { tab: r.tab, sub: r.sub, toast, onSub: (x) => history.replaceState(null, '', `#/settings/${r.tab}/${x}`) });
}

/** Settings › Server (admins): the MCP switch, the version and its updates, the server log and Restart
    (iosuite-shared's panel, the same in every io app), then Export: each list as an .ics file. */
export async function setServer(el) {
  let ui;
  const panel = h('div');
  el.append(panel);
  try { ui = await serverUi(); } catch (e) { panel.append(h('p', { class: 'warn' }, `The Server panel did not load: ${e.message}`)); return; }
  await ui.mount(panel, { toast });
  await loadLists();
  el.append(h('div', { class: 'box' }, h('h2', null, icon('download'), 'Export'),
    h('p', null, 'Each list as an .ics file.'),
    h('table', { class: 't' }, S.lists.map((c) => h('tr', null, h('td', null, h('span', { class: 'ldot', style: { '--hue': c.color } }), ' ', c.name),
      h('td', { class: 'muted' }, `${c.count || 0} open tasks`),
      h('td', { style: { textAlign: 'right' } }, h('a', { class: 'pillbtn noic', href: `api/lists/${c.id}/export` }, 'Download')))))));
}
export const serverUi = () => import(new URL('api/server/ui.js', document.baseURI).href);
