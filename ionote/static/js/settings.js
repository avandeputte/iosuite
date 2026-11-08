/** Settings, one page as in every ioThing app (Display for everyone; Apps and devices for accounts; Export and import of
 *  one's own notes; Notes, Storage and backups and Server for admins; Security and Global settings for
 *  suite admins), and the change log. */
import { $, h, api, state, icon, toast, fail, isAdmin, canWrite, confirmIt, fmtDate } from './core.js';

/** A section of a settings page, as iopix draws one: the heading with its coloured marker and a line under it, an
 *  intro, then rows (title and explanation on the left, the control on the right, a line between rows). */
function box(title, intro, ...kids) { return h('section.sec', h('h2', title), intro ? h('p.intro', intro) : null, ...kids); }
function sw(label, checked, onchange, disabled = false, hint = '') {
  return h('div.srow', h('div', h('b', label), hint ? h('div.muted.small', hint) : null),
    h('label.check', h('input', { type: 'checkbox', checked, disabled, onchange: (e) => onchange(e.target.checked, e.target) }), h('span', label)));
}
async function setSetting(k, v) { try { await api('/api/settings', { method: 'POST', body: { [k]: v } }); toast('Saved'); } catch (e) { fail(e); } }

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

/** What only ioNotes has: read-only mode. Accounts, roles, the sign-in requirement and sign-in at the proxy are the
 *  suite's (Settings › Security, Global settings). */
function readOnlyBox(s) {
  return box('Read-only', state.me.isSuiteAdmin ? h('span', 'People, their role here, whether sign-in is required and sign-in at the proxy are under ', h('a', { href: '#/settings/security' }, 'Settings › Security'), ' and ', h('a', { href: '#/settings/global' }, 'Global settings'), ', for every io app at once.') : 'People, roles and sign-in are managed by a suite admin under Settings › Security.',
    sw('Read-only', s.read_only, (v) => setSetting('read_only', v), s.read_only_env, s.read_only_env ? '(READ_ONLY=1 in config.env)' : 'Nothing can be changed, by anyone.'));
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

function databaseBox(s) {
  const d = s.database;
  const where = d.type === 'mysql' ? `MariaDB/MySQL ${d.user}@${d.host}:${d.port}/${d.database}` : `SQLite file ${d.sqlite_file}`;
  const out = h('p.small');
  const f = {};
  for (const [k, ph] of [['host', 'db.example.lan'], ['port', '3306'], ['database', 'notes'], ['user', 'notes']]) f[k] = h('input', { type: 'text', value: d[k] || '', placeholder: ph });
  f.password = h('input', { type: 'password', placeholder: d.password_set ? '(unchanged)' : 'password', autocomplete: 'new-password' });
  const vals = () => ({ type: 'mysql', host: f.host.value, port: f.port.value || 3306, database: f.database.value, user: f.user.value, password: f.password.value, keep_password: !f.password.value });
  const test = h('button.pillbtn', { onclick: async () => {
    out.textContent = 'Testing…';
    const r = await api('/api/db/test', { method: 'POST', body: vals() }).catch((e) => ({ ok: false, error: e.message }));
    out.className = 'small ' + (r.ok ? (r.warning ? 'warnc' : 'okc') : 'err');
    out.textContent = r.ok ? `Connected: ${r.version}${r.warning ? '. ' + r.warning : ''}` : r.error;
  } }, 'Test');
  const saveb = h('button.pillbtn.primary', { onclick: async () => {
    try { await api('/api/db/save', { method: 'POST', body: vals() }); out.className = 'small okc'; out.textContent = 'Saved. Restart ioNotes to use it (the notes are not copied across; export and import them).'; } catch (e) { out.className = 'small err'; out.textContent = e.message; }
  } }, 'Save');
  const env = d.fromEnv && d.fromEnv.length;
  const sd = s.suite_database || {};
  return box('Database', null, h('p', 'Notes, pictures and ioNotes\' settings are in: ', h('span.code', where), d.error ? h('span.err', ' ' + d.error) : null),
    h('p.small', 'Accounts, sessions and the suite-wide settings are in the Shared ioSuite database: ', h('span.code', `${sd.user}@${sd.host}:${sd.port}/${sd.database}`),
      sd.fromEnv && sd.fromEnv.length ? ` (set in config.env: ${sd.fromEnv.join(', ')})` : ' (the defaults; set IOSUITE_DB_* in config.env)', '.'),
    h('p.small', `${s.images.images} pictures, ${(s.images.bytes / 1048576).toFixed(1)} MB, stored in the database.`),
    env ? h('p.small', 'Set in config.env (DB_*): ' + d.fromEnv.join(', ') + '. Change it there.') :
      h('div', ...Object.entries({ Host: f.host, Port: f.port, Database: f.database, User: f.user, Password: f.password }).map(([l, e]) => h('div.row', h('label', l), e)), h('div.row', test, saveb)),
    out);
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

function ocrBox(s) {
  const o = s.ocr;
  return box('Text in pictures', 'The Mac and iPhone apps read the text in screenshots and photos themselves and send it along. For pictures added in the web app, the server reads it with RapidOCR.',
    h('p.small', !o.enabled ? 'Off (OCR=0 in config.env).' : o.installed ? `RapidOCR is installed${o.queued ? `; ${o.queued} pictures waiting` : ''}.` :
      'RapidOCR is not installed: pictures added in the web app are kept without their text. Install it with ./setup.sh --features ocr (or pip install -e \'.[ocr]\').'),
    o.error ? h('p.small.err', 'Last failure: ' + o.error) : null);
}

/** Who owns the notes: each account (or id with no account any more) and its notes, and a way to give them all to
 *  another account, e.g. when the notes from before accounts existed went to another admin. */
async function ownersBox() {
  const d = await api('/api/owners');
  const tbody = h('tbody');
  for (const o of d.owners) {
    const label = o.name || (o.id === 0 ? 'From before accounts existed' : o.id < 0 ? 'Nobody' : `No account here (id ${o.id})`);
    const to = h('select', { 'aria-label': 'Give to' }, d.accounts.filter((a) => a.id !== o.id).map((a) => h('option', { value: a.id, selected: state.me.user && a.id === state.me.user.id }, a.name)));
    const give = h('button.pillbtn', { onclick: async () => {
      const name = to.selectedOptions[0] ? to.selectedOptions[0].textContent : '';
      if (!await confirmIt('Give the notes', `Give all ${o.notes} notes of ${label}, with their folders and tag colours, to ${name}? Only ${name} will see them.`, 'Give')) return;
      try { const r = await api('/api/owners/move', { method: 'POST', body: { from: o.id, to: Number(to.value) } }); toast(`${r.moved} notes moved to ${name}`); location.reload(); } catch (e) { fail(e); }
    } }, 'Give');
    tbody.append(h('tr', h('td', label, state.me.user && o.id === state.me.user.id ? h('span.muted', ' (you)') : null), h('td', String(o.notes)),
      h('td', d.accounts.length > (o.name ? 1 : 0) ? h('div.row', to, give) : null)));
  }
  if (!d.owners.length) tbody.append(h('tr', h('td', { colspan: 3 }, 'No notes yet.')));
  return box('Who owns the notes', 'Notes are private to each account. When accounts were turned on, the notes made before went to the first admin; if they went to the wrong account, give them to the right one here.',
    h('table.grid', h('thead', h('tr', h('th', 'Owner'), h('th', 'Notes'), h('th', 'Give them to'))), tbody));
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

/** Settings: Display for everyone; Apps and devices for accounts; Export and import of one's own notes; for admins Notes
 *  (read-only, text in pictures), Storage and backups (the database, who owns the notes) and Server; for suite admins
 *  Security and Global settings. */
export function renderSettings(tab, sub) {
  const tabs = [['display', 'Display', async () => [appearance(), state.me.user ? null : box('Account', state.me.usersExist ? 'Sign in to see your notes.' : 'No accounts yet: anyone who can reach ioNotes can read and change the notes. Create the admin account from the person icon at the top right.')]]];
  if (state.me.user) tabs.push(['devices', 'Apps and devices', async () => [await devicesBox()]]);
  if (state.me.user || !state.me.usersExist) tabs.push(['export', 'Export and import', async () => [exportBox()]]);  // anyone's own notes
  if (isAdmin()) {
    const s = () => api('/api/settings');
    tabs.push(['notes', 'Notes', async () => { const x = await s(); return [readOnlyBox(x), ocrBox(x)]; }],
      ['storage', 'Storage and backups', async () => { const x = await s(); return [databaseBox(x), await ownersBox()]; }],
      ['server', 'Server', async () => [await serverPanel()]]);
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
