/** Settings (Display for everyone; Apps and devices for accounts; Users and sign-in for admins), Maintenance (admins: storage and backups, MCP and
 *  OCR, updates and logs) and the change log. Laid out as in every ioThing app: Settings is what is configured,
 *  Maintenance what is run or checked. */
import { $, h, api, state, icon, toast, fail, isAdmin, canWrite, dialog, confirmIt, fmtDate } from './core.js';
import { runUpdate } from './update.js';

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

async function usersBox() {
  const { users, roles } = await api('/api/users');
  const tbody = h('tbody');
  const draw = (list) => {
    tbody.textContent = '';
    for (const u of list) {
      const role = h('select', { onchange: async (e) => { try { await api(`/api/users/${u.id}`, { method: 'POST', body: { role: e.target.value } }); toast('Saved'); } catch (err) { fail(err); e.target.value = u.role; } } },
        roles.map((r) => h('option', { value: r, selected: r === u.role }, r)));
      tbody.append(h('tr', h('td', h('span.ucell', h('span.avatar', (u.name || '?')[0].toUpperCase()), h('span', u.name, state.me.user && u.id === state.me.user.id ? h('span.muted', ' (you)') : null, u.passwordless ? h('span.muted.small', ' (one click)') : null))), h('td', role), h('td.small', u.email || ''),
        h('td.small.muted', u.last_login ? fmtDate(u.last_login) : 'never'),
        h('td', h('button.iconbtn', { title: 'Change', onclick: () => editUser(u) }, icon('edit')))));
    }
  };
  draw(users);
  const add = h('button.pillbtn', { onclick: () => editUser(null) }, icon('add'), 'Add an account');
  return box('Accounts', 'Viewers read and search; editors also change notes (the Mac and iPhone apps sign in as an editor); admins also change these settings. The same roles as iopix.',
    h('table.grid.utable', h('thead', h('tr', h('th', 'Name'), h('th', 'Role'), h('th', 'Email'), h('th', 'Last sign-in'), h('th', ''))), tbody), h('div.row', add));
}

async function editUser(u) {
  const name = h('input', { type: 'text', value: u ? u.name : '', placeholder: 'User name' });
  const pw = h('input', { type: 'password', placeholder: u ? 'New password (leave empty to keep it)' : 'Password (8 characters or more; empty: one-click viewer)', autocomplete: 'new-password' });
  const email = h('input', { type: 'text', value: u ? u.email : '', placeholder: 'Email (optional; Cloudflare Access matches on it)' });
  const role = h('select', ['viewer', 'editor', 'admin'].map((r) => h('option', { value: r, selected: (u ? u.role : 'editor') === r }, r)));
  const listed = h('input', { type: 'checkbox', checked: u ? u.listed : true });
  const msg = h('p.err.small');
  const buttons = [{ label: 'Cancel' }];
  if (u) buttons.push({ label: 'Delete', danger: true, action: async () => {
    if (!await confirmIt('Delete account', `Delete ${u.name}?`, 'Delete', true)) return false;
    try { await api(`/api/users/${u.id}`, { method: 'POST', body: { delete: true } }); render(); } catch (e) { msg.textContent = e.message; return false; }
  } });
  buttons.push({ label: u ? 'Save' : 'Create', primary: true, action: async () => {
    try {
      if (u) {
        const body = { name: name.value, email: email.value, role: role.value, listed: listed.checked };
        if (pw.value) body.password = pw.value;
        await api(`/api/users/${u.id}`, { method: 'POST', body });
      } else {
        const nu = await api('/api/users', { method: 'POST', body: { name: name.value, password: pw.value, role: role.value, email: email.value } });
        if (!listed.checked) await api(`/api/users/${nu.id}`, { method: 'POST', body: { listed: false } });
      }
      render();
    } catch (e) { msg.textContent = e.message; return false; }
  } });
  await dialog(u ? `Account ${u.name}` : 'New account', h('div', name, pw, email, h('div.row', h('span', 'Role'), role), h('label.switch', listed, h('span', 'On the sign-in screen\'s account list')), msg), buttons);
}

function signInBox(s) {
  return box('Sign-in', null,
    sw('Require sign-in', s.require_login, (v, el) => setSetting('require_login', v).then(() => { s.require_login = v; }).catch(() => { el.checked = !v; }), !state.me.usersExist,
      'Visitors get the sign-in screen and nothing else (the MCP endpoint always wants an app password).'),
    sw('Read-only', s.read_only, (v) => setSetting('read_only', v), s.read_only_env, s.read_only_env ? '(READ_ONLY=1 in config.env)' : 'Nothing can be changed, by anyone.'));
}

async function proxyBox() {
  const st = await api('/api/settings/proxy');
  const v = st.values, fixed = new Set(st.fromEnv);
  const field = (k, ph) => h('input', { type: 'text', value: v[k] || '', placeholder: ph, disabled: fixed.has(k), 'data-k': k });
  const mode = h('select', { 'data-k': 'AUTH_PROXY', disabled: fixed.has('AUTH_PROXY') }, ['off', 'cloudflare', 'haproxy', 'nginx', 'caddy', 'traefik', 'header'].map((m) => h('option', { value: m, selected: (v.AUTH_PROXY || 'off') === m }, m)));
  const create = h('select', { 'data-k': 'AUTH_PROXY_CREATE', disabled: fixed.has('AUTH_PROXY_CREATE') },
    [['', 'show the sign-in screen'], ['deny', 'refuse them'], ['viewer', 'make them a viewer account'], ['editor', 'make them an editor account']].map(([k, l]) => h('option', { value: k, selected: (v.AUTH_PROXY_CREATE || '') === k }, l)));
  const fields = [mode, field('CF_ACCESS_TEAM', 'myteam.cloudflareaccess.com'), field('CF_ACCESS_AUD', 'the Access application\'s AUD tag'),
    field('AUTH_PROXY_HEADER', 'header(s) with the user (other proxies)'), field('AUTH_PROXY_TRUSTED', '127.0.0.1, ::1 (the proxy\'s address)'), create];
  const save = h('button.pillbtn.primary', { onclick: async () => {
    const body = {};
    for (const f of fields) if (!f.disabled) body[f.dataset.k] = f.value;
    try { await api('/api/settings/proxy', { method: 'POST', body }); toast('Saved'); } catch (e) { fail(e); }
  } }, 'Save');
  const seen = st.seen && st.seen.aud ? h('p.small', `Last Cloudflare Access request: team ${st.seen.iss || '?'}, AUD ${Array.isArray(st.seen.aud) ? st.seen.aud.join(', ') : st.seen.aud}, ${st.seen.email || ''}`) : null;
  return box('Sign-in at the proxy', 'With Cloudflare Access (a Cloudflare Tunnel with an Access policy) or a proxy with Authelia, Authentik or oauth2-proxy in front, ioNotes takes that sign-in: the person is matched to an account by email, then by name. For Cloudflare, set the team domain and the AUD tag so the signed token is checked. Settings in config.env win.',
    h('div.row', h('label', 'Proxy'), mode), h('div.row', h('label', 'Cloudflare team'), fields[1]), h('div.row', h('label', 'Cloudflare AUD'), fields[2]),
    h('div.row', h('label', 'User header'), fields[3]), h('div.row', h('label', 'Proxy address'), fields[4]), h('div.row', h('label', 'Someone with no account'), create),
    seen, fixed.size ? h('p.small', 'Fixed in config.env: ' + [...fixed].join(', ')) : null, h('div.row', save));
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

async function mcpBox(s) {
  const url = (s.appUrl || location.origin) + '/mcp';
  return box('MCP server', 'Lets an assistant such as Claude search and read notes and look at their pictures and, as an editor, create, edit, file, tag and delete them; admins also get diagnostics and the updater. The same in every ioThing app: every assistant signs in with an app password (Settings › Apps and devices) and works on that account\'s own notes.',
    sw('MCP server at /mcp', s.mcp_enabled || s.mcp_forced, (v) => setSetting('mcp_enabled', v), s.mcp_forced, s.mcp_forced ? '(MCP=1 in config.env)' : ''),
    h('div.row', h('label', 'Address'), h('span.code', url)),
    h('p.small', 'Claude Code: claude mcp add --transport http ionotes ' + url + ' --header "Authorization: Bearer <app password>". Claude Desktop: "args": ["mcp-remote", "' + url + '", "--header", "Authorization: Bearer <app password>"].'));
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

/** Maintenance › Updates and logs: the version card, the server log and Restart, from iosuite-shared's /api/server and
 *  /api/log, so the page is the same in every ioThing app. */
async function updateBox() {
  const u = await api('/api/server');
  const out = h('p.small');
  const show = (c) => { out.className = 'small'; out.textContent = !c ? '' : c.status === 'current' ? `Up to date (${c.installed}).` : c.status === 'update' ? `A newer version is out: ${c.remoteVersion || c.remote} (${c.remoteDate}): ${c.remoteMessage}` : `Could not check: ${c.error}`; };
  show(u.check);
  const post = (body) => api('/api/server', { method: 'POST', body });
  return box('ionotes version', null, h('p', `Version ${u.version}, commit `, h('span.code', u.installed), u.docker ? ' (Docker: update by pulling the image)' : ''),
    u.lastUpdate ? h('p.small' + (u.lastUpdate.ok ? '.okc' : '.err'), 'Last update: ' + u.lastUpdate.text) : null,
    sw('Check for updates daily', u.autoCheck, async (v) => { try { await post({ autoCheck: v }); toast('Saved'); } catch (e) { fail(e); } }, u.autoCheckLocked, u.autoCheckLocked ? '(UPDATE_CHECK=0 in config.env)' : '(only GitHub’s public list of changes is asked; nothing about this server is sent)'),
    h('div.row', h('button.pillbtn', { onclick: async () => { out.textContent = 'Checking…'; show(await post({ action: 'check' }).catch((e) => ({ status: 'error', error: e.message }))); } }, 'Check for updates'),
      u.canRun ? h('button.pillbtn.primary', { onclick: async () => {
        if (!await confirmIt('Update ioNotes', 'Install the latest version and restart? It takes about a minute.', 'Update')) return;
        await runUpdate((msg, failed) => { out.className = 'small' + (failed ? ' err' : ''); out.textContent = msg; });
      } }, 'Update now') : null,
      h('a.pillbtn', { href: `https://github.com/${u.repo}/commits/${u.branch}`, target: '_blank', rel: 'noopener' }, 'Change log')), out,
    h('p.small.muted', `Follows ${u.repo} (${u.branch}).`));
}

function restartBox() {
  return box('Restart', 'Stops ioNotes; the service manager (systemd, launchd or Docker) starts it again within seconds. Nothing is lost; the page reloads when it is back.',
    h('div.row', h('button.pillbtn', { onclick: async () => {
      if (!await confirmIt('Restart ioNotes', 'Restart the server now? Everyone is disconnected for a few seconds.', 'Restart')) return;
      try { await api('/api/server', { method: 'POST', body: { action: 'restart' } }); } catch (e) { fail(e); return; }
      toast('Restarting…');
      const until = Date.now() + 90000, gone = Date.now() + 3000;
      const look = async () => {
        try { const r = await fetch('/api/status', { credentials: 'same-origin' }); if (r.ok && Date.now() > gone) { location.reload(); return; } } catch (e) { /* down */ }
        if (Date.now() < until) setTimeout(look, 2000); else toast('ionotes did not come back; check the service.');
      };
      setTimeout(look, 3000);
    } }, 'Restart ioNotes')));
}

function logBox() {
  const pre = h('pre.log', 'Loading…'), note = h('p.small.muted');
  const level = h('select', [['any', 'Everything'], ['warning', 'Warnings and errors'], ['error', 'Errors'], ['auth', 'Sign-ins']].map(([v, l]) => h('option', { value: v }, l)));
  const contains = h('input', { type: 'text', placeholder: 'Contains…' });
  const requests = h('input', { type: 'checkbox' });
  const load = async () => {
    const r = await api(`/api/log?lines=300&level=${level.value}&contains=${encodeURIComponent(contains.value)}&requests=${requests.checked ? 1 : 0}`).catch((e) => ({ lines: [e.message] }));
    pre.textContent = (r.lines || []).join('\n') || r.note || 'Nothing matches.';
    note.textContent = r.file && !r.note ? `${r.file}: ${(r.size_bytes / 1024).toFixed(0)} kB, the last ${r.returned} lines.` : '';
    pre.scrollTop = pre.scrollHeight;
  };
  level.addEventListener('change', load); contains.addEventListener('change', load); requests.addEventListener('change', load);
  load();
  return box('Server log', null, h('div.row', h('label', 'Show'), level, contains, h('label', requests, ' Requests too'), h('button.pillbtn', { onclick: load }, 'Reload'),
    h('a.pillbtn', { href: '/api/log/download' }, icon('download'), 'Download')), pre, note);
}

/** A page as iopix lays one out: the title with its icon tile, the tabs under it (the tab is in the address:
 *  #/settings/users), then the tab's boxes. */
let again = () => {};
function pageTitle(text, ic, hue, sub = '') { return h('h1.ptitle', h('span.pic', { style: `--hue:${hue}` }, icon(ic)), text, sub ? h('span.muted', sub) : null); }
async function tabbedPage(base, title, ic, hue, tabs, tab) {
  if (!state.version) { try { state.version = (await api('/api/status')).version; } catch (e) { /* the title goes without it */ } }
  const main = $('#main');
  main.textContent = '';
  const cur = tabs.find((t) => t[0] === tab) || tabs[0];
  const inner = h('div.pagein', pageTitle(title, ic, hue, state.version ? `ioNotes v${state.version}` : ''),
    tabs.length > 1 ? h('div.stabs', { role: 'tablist' }, tabs.map(([k, label]) => h('a.pillbtn' + (k === cur[0] ? '.on' : ''), { href: `#/${base}/${k}`, role: 'tab', 'aria-selected': String(k === cur[0]) }, label))) : null);
  main.append(h('div.page', inner));
  again = () => tabbedPage(base, title, ic, hue, tabs, cur[0]);
  try { for (const b of await cur[2]()) if (b) inner.append(b); } catch (e) { inner.append(h('p.err', e.message)); }
}
const render = () => again();

/** Settings: Display for everyone, Export and import of one's own notes, Users and sign-in for admins (as iopix's Settings). */
export function renderSettings(tab) {
  const tabs = [['display', 'Display', async () => [appearance(), state.me.user ? null : box('Account', state.me.usersExist ? 'Sign in to see your notes.' : 'No accounts yet: anyone who can reach ioNotes can read and change the notes. Create the admin account from the person icon at the top right.')]]];
  if (state.me.user || !state.me.usersExist) tabs.push(['export', 'Export and import', async () => [exportBox()]]);  // anyone's own notes
  if (state.me.user) tabs.push(['devices', 'Apps and devices', async () => [await devicesBox()]]);
  if (isAdmin()) tabs.push(['users', 'Users and sign-in', async () => { const s = await api('/api/settings'); return [state.me.usersExist ? await usersBox() : null, signInBox(s), await proxyBox()]; }]);
  return tabbedPage('settings', 'Settings', 'gear', 'var(--c-gray)', tabs, tab);
}

/** Maintenance (admins): where the notes are kept and their backups, MCP and the text in pictures, and Updates and
 *  logs (the version, the server log, restart), as in every ioThing app. */
export function renderMaintenance(tab) {
  if (!isAdmin()) { const main = $('#main'); main.textContent = ''; main.append(h('div.page', h('div.pagein', pageTitle('Maintenance', 'wrench', 'var(--c-orange)'), h('p.muted', 'For admins only.')))); return null; }
  const s = () => api('/api/settings');
  return tabbedPage('maintenance', 'Maintenance', 'wrench', 'var(--c-orange)', [
    ['storage', 'Storage and backups', async () => { const x = await s(); return [databaseBox(x), await ownersBox(), exportBox()]; }],
    ['mcp', 'MCP and text in pictures', async () => { const x = await s(); return [await mcpBox(x), ocrBox(x)]; }],
    ['updates', 'Updates and logs', async () => [await updateBox(), logBox(), restartBox()]],
  ], tab);
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
