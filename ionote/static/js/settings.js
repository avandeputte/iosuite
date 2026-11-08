/** Settings, one page as in every ioThing app (Display for everyone; Apps and devices for accounts; Export and import of
 *  one's own notes; Server for admins; Security and Global settings for suite admins), and the change log. */
import { $, h, api, state, icon, toast, fail, isAdmin, canWrite, fmtDate } from './core.js';

/** A section of a settings page, as iopix draws one: the heading with its coloured marker and a line under it, an
 *  intro, then rows (title and explanation on the left, the control on the right, a line between rows). */
function box(title, intro, ...kids) { return h('section.sec', h('h2', title), intro ? h('p.intro', intro) : null, ...kids); }

const THEMES = [['light', 'Light'], ['dark', 'Dark'], ['system', 'System']];
function appearance() {
  let cur = 'light'; try { cur = localStorage.getItem('ionotes.theme') || 'light'; } catch (e) {}
  const seg = h('div.eseg', THEMES.map(([k, label]) => h('button' + (cur === k ? '.on' : ''), { type: 'button', onclick: (e) => {
    try { localStorage.setItem('ionotes.theme', k); } catch (err) {}
    if (k === 'system') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = k;
    if (state.me.user) api('/api/auth/settings', { method: 'POST', body: { theme: k } }).catch(() => {});
    for (const b of seg.children) b.classList.toggle('on', b === e.currentTarget);
  } }, label)));
  return box('Display', null, h('div.srow', h('div', h('b', 'Appearance'), h('div.muted.small', `Light (the default) or dark colors, or follow the device's setting. ${state.me.user ? 'Saved with your account, so it follows you to other devices.' : 'Remembered in this browser.'}`)), seg));
}

/** Settings › Security and Global settings (suite admins): the people and their role in every app (here
 *  too), app passwords, sign-in at the proxy; the apps, keys and tokens. The same panel in every io app, served by
 *  iosuite-shared. */
async function suitePanel(tab, sub) {
  const el = h('div');
  let ui;
  try { ui = await import(new URL('api/suite-admin/ui.js', document.baseURI).href); } catch (e) { return h('p.err', `The panel did not load: ${e.message}`); }
  await ui.mount(el, { tab, sub, toast, onSub: (x) => history.replaceState(null, '', `#/settings/${tab}/${x}`) });
  return el;
}

/** Settings › Server (admins): the MCP switch, the version and its updates, the server log and Restart:
 *  iosuite-shared's panel, the same in every io app. */
export const serverUi = () => import(new URL('api/server/ui.js', document.baseURI).href);
async function serverPanel() {
  const el = h('div');
  let ui;
  try { ui = await serverUi(); } catch (e) { return h('p.err', `The Server panel did not load: ${e.message}`); }
  await ui.mount(el, { toast });
  return el;
}

/** Settings › Apps and devices: the signed-in account's app passwords (one per app or device, revocable one by one),
 *  for the Mac and iPhone apps, MCP clients and anything else that signs in with HTTP Basic or a bearer token. */
async function devicesBox() {
  if (state.me.user.passwordless) return box('Apps and devices', 'A one-click account (no password) cannot have app passwords. Ask an admin to set a password on your account first.');
  const label = h('input', { placeholder: 'e.g. Claude on my Mac', 'aria-label': 'Name' });
  const shown = h('div'), list = h('div');
  const draw = async () => {
    const items = (await api('/api/auth/app-passwords')).items;
    list.replaceChildren(items.length ? h('table.t', h('tr', h('th', 'Name'), h('th', 'Made'), h('th', 'Last used'), h('th')),
      ...items.map((p) => h('tr', h('td', p.label), h('td', p.created ? new Date(p.created).toLocaleDateString() : ''), h('td', p.lastUsed ? new Date(p.lastUsed).toLocaleString() : 'never'),
        h('td', h('button.pillbtn', { onclick: async () => { try { await api(`/api/auth/app-passwords/${p.id}`, { method: 'DELETE' }); draw(); } catch (e) { fail(e); } } }, 'Revoke'))))) : h('p.small', 'No app passwords yet.'));
  };
  await draw();
  return box('Apps and devices', 'Give every app, device or assistant its own password instead of yours; revoke one without touching the others. Use your user name with it (HTTP Basic), or send it as "Authorization: Bearer <app password>".',
    h('div.row', h('label', 'New app password'), label, h('button.pillbtn', { onclick: async () => {
      try {
        const r = await api('/api/auth/app-passwords', { method: 'POST', body: { label: label.value || 'Device' } });
        shown.replaceChildren(h('p', h('b', 'Copy it now: '), 'it is shown only once. ', h('span.code', r.password)));
        label.value = ''; draw();
      } catch (e) { fail(e); }
    } }, 'Make')),
    shown, list);
}

function exportBox() {
  const file = h('input', { type: 'file', accept: '.zip,.json', hidden: true, onchange: async (e) => {
    const f = e.target.files[0]; if (!f) return;
    const fd = new FormData(); fd.append('file', f);
    toast('Importing…', 60000);
    try { const r = await api('/api/import', { method: 'POST', body: fd }); toast(`Imported ${r.notes} notes, ${r.pictures} pictures, ${r.folders} folders${r.skipped ? `; ${r.skipped} were newer here` : ''}`, 6000); } catch (err) { fail(err); }
  } });
  return box('Export and import', 'Your notes (each account has its own) as Markdown with their pictures, in folders, plus notes.json with everything; a zip made here imports again on any ioNotes server (records keep their ids; newer copies on the server win).',
    h('div.row', h('a.pillbtn', { href: '/api/export.zip' }, icon('download'), 'Export all notes'), h('a.pillbtn', { href: '/api/export.zip?trash=1' }, 'With the trash'),
      canWrite() ? h('button.pillbtn', { onclick: () => file.click() }, icon('upload'), 'Import…') : null, file));
}

/** A page as iopix lays one out: the title with its icon tile, the tabs under it (the tab is in the address:
 *  #/settings/devices), then the tab's boxes. */
let again = () => {};
function pageTitle(text, ic, hue, sub = '') { return h('h1.ptitle', h('span.pic', { style: `--hue:${hue}` }, icon(ic)), text, sub ? h('span.muted', sub) : null); }
async function tabbedPage(base, title, ic, hue, tabs, tab) {
  const main = $('#main');
  main.textContent = '';
  const cur = tabs.find((t) => t[0] === tab) || tabs[0];
  const inner = h('div.pagein', pageTitle(title, ic, hue),
    tabs.length > 1 ? h('div.stabs', { role: 'tablist' }, tabs.map(([k, label]) => h('a.pillbtn' + (k === cur[0] ? '.on' : ''), { href: `#/${base}/${k}`, role: 'tab', 'aria-selected': String(k === cur[0]) }, label))) : null);
  main.append(h('div.page', inner));
  again = () => tabbedPage(base, title, ic, hue, tabs, cur[0]);
  try { for (const b of await cur[2]()) if (b) inner.append(b); } catch (e) { inner.append(h('p.err', e.message)); }
}
const render = () => again();

/** Settings: Display for everyone; Apps and devices for accounts; Export and import of one's own notes; Server for
 *  admins; Security and Global settings for suite admins. */
export function renderSettings(tab, sub) {
  const tabs = [['display', 'Display', async () => [appearance(), state.me.user ? null : box('Account', state.me.usersExist ? 'Sign in to see your notes.' : 'No accounts yet: anyone who can reach ioNotes can read and change the notes. Create the admin account from the person icon at the top right.')]]];
  if (state.me.user) tabs.push(['devices', 'Apps and devices', async () => [await devicesBox()]]);
  if (state.me.user || !state.me.usersExist) tabs.push(['export', 'Export and import', async () => [exportBox()]]);  // anyone's own notes
  if (isAdmin()) {
    tabs.push(['server', 'Server', async () => [await serverPanel()]]);
  }
  if (state.me.isSuiteAdmin) tabs.push(['security', 'Security', async () => [await suitePanel('security', sub)]], ['global', 'Global settings', async () => [await suitePanel('global', sub)]]);
  return tabbedPage('settings', 'Settings', 'gear', 'var(--c-gray)', tabs, tab);
}

export async function renderChanges() {
  const main = $('#main');
  main.textContent = '';
  const tbody = h('tbody');
  const inner = h('div.pagein', pageTitle('Change log', 'history', 'var(--c-indigo)'), h('p.muted', 'Every change to a note, folder or tag, from the web app, the Mac and iPhone apps and MCP, newest first.'),
    h('table.grid', h('thead', h('tr', h('th', 'When'), h('th', 'Who'), h('th', 'What'), h('th', ''))), tbody));
  main.append(h('div.page', inner));
  if (!canWrite()) { tbody.append(h('tr', h('td', { colspan: 4 }, 'Editors only.'))); return; }
  let before = null;
  const more = h('button.pillbtn.more', { onclick: () => load() }, 'Older');
  const load = async () => {
    const r = await api('/api/changes?limit=200' + (before ? '&before=' + before : ''));
    for (const c of r.changes) {
      tbody.append(h('tr', h('td.small', fmtDate(c.ts, true)), h('td', c.user), h('td', `${c.action} ${c.kind}`),
        h('td', c.kind === 'note' && c.action !== 'delete' ? h('a', { href: '#/note/' + c.uuid }, c.summary) : c.summary)));
      before = c.id;
    }
    if (r.changes.length < 200) more.remove();
  };
  inner.append(more);
  await load();
}
