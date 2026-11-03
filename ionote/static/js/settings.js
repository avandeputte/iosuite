/** Settings (Display for everyone; Users and sign-in for admins), Maintenance (admins: storage and backups, MCP and
 *  OCR, version and log) and the change log. Laid out like iopix's Settings and Maintenance pages. */
import { $, h, api, state, icon, toast, fail, isAdmin, canWrite, dialog, confirmIt, fmtDate } from './core.js';
import { runUpdate } from './update.js';

function box(title, intro, ...kids) { return h('div.box', h('h2', title), intro ? h('p', intro) : null, ...kids); }
function sw(label, checked, onchange, disabled = false, hint = '') {
  return h('label.switch', h('input', { type: 'checkbox', checked, disabled, onchange: (e) => onchange(e.target.checked, e.target) }), h('span', label, hint ? h('span.muted.small', ' ' + hint) : null));
}
async function setSetting(k, v) { try { await api('/api/settings', { method: 'POST', body: { [k]: v } }); toast('Saved'); } catch (e) { fail(e); } }

function appearance() {
  let cur = 'light'; try { cur = localStorage.getItem('ionotes.theme') || 'light'; } catch (e) {}
  const sel = h('select', { onchange: (e) => {
    try { localStorage.setItem('ionotes.theme', e.target.value); } catch (err) {}
    if (e.target.value === 'system') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = e.target.value;
    if (state.me.user) api('/api/auth/settings', { method: 'POST', body: { theme: e.target.value } }).catch(() => {});
  } }, [['light', 'Light'], ['dark', 'Dark'], ['system', 'Same as the device']].map(([v, l]) => h('option', { value: v, selected: cur === v }, l)));
  return box('Appearance', null, h('div.row', h('label', 'Theme'), sel));
}

async function usersBox() {
  const { users, roles } = await api('/api/users');
  const tbody = h('tbody');
  const draw = (list) => {
    tbody.textContent = '';
    for (const u of list) {
      const role = h('select', { onchange: async (e) => { try { await api(`/api/users/${u.id}`, { method: 'POST', body: { role: e.target.value } }); toast('Saved'); } catch (err) { fail(err); e.target.value = u.role; } } },
        roles.map((r) => h('option', { value: r, selected: r === u.role }, r)));
      tbody.append(h('tr', h('td', u.name, u.passwordless ? h('span.muted.small', ' (one click)') : null), h('td', role), h('td.small', u.email || ''),
        h('td.small.muted', u.last_login ? fmtDate(u.last_login) : 'never'),
        h('td', h('button.iconbtn', { title: 'Change', onclick: () => editUser(u) }, icon('edit')))));
    }
  };
  draw(users);
  const add = h('button.pillbtn', { onclick: () => editUser(null) }, icon('add'), 'Add an account');
  return box('Accounts', 'Viewers read and search; editors also change notes (the Mac and iPhone apps sign in as an editor); admins also change these settings. The same roles as iopix.',
    h('table.grid', h('thead', h('tr', h('th', 'Name'), h('th', 'Role'), h('th', 'Email'), h('th', 'Last sign-in'), h('th', ''))), tbody), h('div.row', add));
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
      'Visitors get the sign-in screen and nothing else; the MCP endpoint then needs the admin token as a Bearer header.'),
    sw('Read-only', s.read_only, (v) => setSetting('read_only', v), s.read_only_env, s.read_only_env ? '(READ_ONLY=1 in ionotes.env)' : 'Nothing can be changed, by anyone.'));
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
  return box('Sign-in at the proxy', 'With Cloudflare Access (a Cloudflare Tunnel with an Access policy) or a proxy with Authelia, Authentik or oauth2-proxy in front, ionotes takes that sign-in: the person is matched to an account by email, then by name. For Cloudflare, set the team domain and the AUD tag so the signed token is checked. Settings in ionotes.env win.',
    h('div.row', h('label', 'Proxy'), mode), h('div.row', h('label', 'Cloudflare team'), fields[1]), h('div.row', h('label', 'Cloudflare AUD'), fields[2]),
    h('div.row', h('label', 'User header'), fields[3]), h('div.row', h('label', 'Proxy address'), fields[4]), h('div.row', h('label', 'Someone with no account'), create),
    seen, fixed.size ? h('p.small', 'Fixed in ionotes.env: ' + [...fixed].join(', ')) : null, h('div.row', save));
}

function databaseBox(s) {
  const d = s.database;
  const where = d.type === 'mysql' ? `MariaDB/MySQL ${d.user}@${d.host}:${d.port}/${d.database}` : `SQLite file ${d.sqlite_file}`;
  const out = h('p.small');
  const f = {};
  for (const [k, ph] of [['host', '192.168.1.89'], ['port', '3306'], ['database', 'notes'], ['user', 'notes']]) f[k] = h('input', { type: 'text', value: d[k] || '', placeholder: ph });
  f.password = h('input', { type: 'password', placeholder: d.password_set ? '(unchanged)' : 'password', autocomplete: 'new-password' });
  const vals = () => ({ type: 'mysql', host: f.host.value, port: f.port.value || 3306, database: f.database.value, user: f.user.value, password: f.password.value, keep_password: !f.password.value });
  const test = h('button.pillbtn', { onclick: async () => {
    out.textContent = 'Testing…';
    const r = await api('/api/db/test', { method: 'POST', body: vals() }).catch((e) => ({ ok: false, error: e.message }));
    out.className = 'small ' + (r.ok ? (r.warning ? 'warnc' : 'okc') : 'err');
    out.textContent = r.ok ? `Connected: ${r.version}${r.warning ? '. ' + r.warning : ''}` : r.error;
  } }, 'Test');
  const saveb = h('button.pillbtn.primary', { onclick: async () => {
    try { await api('/api/db/save', { method: 'POST', body: vals() }); out.className = 'small okc'; out.textContent = 'Saved. Restart ionotes to use it (the notes are not copied across; export and import them).'; } catch (e) { out.className = 'small err'; out.textContent = e.message; }
  } }, 'Save');
  const env = d.fromEnv && d.fromEnv.length;
  return box('Database', null, h('p', 'Notes, pictures, accounts and settings are all in: ', h('span.code', where), d.error ? h('span.err', ' ' + d.error) : null),
    h('p.small', `${s.images.images} pictures, ${(s.images.bytes / 1048576).toFixed(1)} MB, stored in the database.`),
    env ? h('p.small', 'Set in ionotes.env (DB_*): ' + d.fromEnv.join(', ') + '. Change it there.') :
      h('div', ...Object.entries({ Host: f.host, Port: f.port, Database: f.database, User: f.user, Password: f.password }).map(([l, e]) => h('div.row', h('label', l), e)), h('div.row', test, saveb)),
    out);
}

async function mcpBox(s) {
  const tok = await api('/api/mcp/token');
  const tokEl = h('span.code', '••••••••');
  const show = h('button.pillbtn', { onclick: () => { tokEl.textContent = tok.token; show.remove(); } }, 'Show');
  const regen = h('button.pillbtn', { disabled: tok.fromEnv, onclick: async () => {
    if (!await confirmIt('New token', 'Make a new token? MCP clients using the old one stop working.', 'New token', true)) return;
    const r = await api('/api/mcp/token', { method: 'POST' }); tok.token = r.token; tokEl.textContent = r.token;
  } }, 'New token');
  const who = h('select', (s.accounts || []).map((a) => h('option', { value: a.id, selected: a.id === s.mcp_user }, a.name)));
  who.addEventListener('change', () => setSetting('mcp_user', Number(who.value)));
  return box('MCP server', 'Lets an assistant such as Claude search and read the notes and look at their pictures; with the admin token it can also create, edit, file, tag and delete them, and run diagnostics. The same as iopix\'s MCP server. Notes are private to each account, so it works on the notes of one account.',
    sw('MCP server at /mcp', s.mcp_enabled || s.mcp_forced, (v) => setSetting('mcp_enabled', v), s.mcp_forced, s.mcp_forced ? '(MCP=1 in ionotes.env)' : ''),
    (s.accounts || []).length ? h('div.row', h('label', 'Notes of'), who) : null,
    h('div.row', h('label', 'Address'), h('span.code', tok.url)),
    h('div.row', h('label', 'Admin token'), tokEl, show, regen),
    h('p.small', 'Claude Desktop: "args": ["mcp-remote", "' + tok.url + '", "--header", "Authorization: Bearer <token>"]. Treat the token like the admin password.'));
}

function ocrBox(s) {
  const o = s.ocr;
  return box('Text in pictures', 'The Mac and iPhone apps read the text in screenshots and photos themselves and send it along. For pictures added in the web app, the server reads it with RapidOCR.',
    h('p.small', !o.enabled ? 'Off (OCR=0 in ionotes.env).' : o.installed ? `RapidOCR is installed${o.queued ? `; ${o.queued} pictures waiting` : ''}.` :
      'RapidOCR is not installed: pictures added in the web app are kept without their text. Install it with ./setup.sh --features ocr (or pip install -e \'.[ocr]\').'),
    o.error ? h('p.small.err', 'Last failure: ' + o.error) : null);
}

function exportBox() {
  const file = h('input', { type: 'file', accept: '.zip,.json', hidden: true, onchange: async (e) => {
    const f = e.target.files[0]; if (!f) return;
    const fd = new FormData(); fd.append('file', f);
    toast('Importing…', 60000);
    try { const r = await api('/api/import', { method: 'POST', body: fd }); toast(`Imported ${r.notes} notes, ${r.pictures} pictures, ${r.folders} folders${r.skipped ? `; ${r.skipped} were newer here` : ''}`, 6000); } catch (err) { fail(err); }
  } });
  return box('Export and import', 'Every note as Markdown with its picture, in folders, plus notes.json with everything; a zip made here imports again on any ionotes server (records keep their ids; newer copies on the server win).',
    h('div.row', h('a.pillbtn', { href: '/api/export.zip' }, icon('download'), 'Export all notes'), h('a.pillbtn', { href: '/api/export.zip?trash=1' }, 'With the trash'),
      canWrite() ? h('button.pillbtn', { onclick: () => file.click() }, icon('upload'), 'Import…') : null, file));
}

async function updateBox(s) {
  const u = await api('/api/update');
  const out = h('p.small');
  const show = (c) => { out.className = 'small'; out.textContent = !c ? '' : c.status === 'current' ? `Up to date (${c.installed}).` : c.status === 'update' ? `A newer version is out: ${c.remoteVersion || c.remote} (${c.remoteDate}): ${c.remoteMessage}` : `Could not check: ${c.error}`; };
  show(u.check);
  return box('ionotes version', null, h('p', `Version ${u.version}, commit `, h('span.code', u.installed), u.docker ? ' (Docker: update by pulling the image)' : ''),
    u.lastUpdate ? h('p.small' + (u.lastUpdate.ok ? '.okc' : '.err'), 'Last update: ' + u.lastUpdate.text) : null,
    sw('Check for updates daily', s.update_check, (v) => setSetting('update_check', v)),
    h('div.row', h('button.pillbtn', { onclick: async () => { out.textContent = 'Checking…'; show(await api('/api/update/check', { method: 'POST' }).catch((e) => ({ status: 'error', error: e.message }))); } }, 'Check for updates'),
      u.canRun ? h('button.pillbtn.primary', { onclick: async () => {
        if (!await confirmIt('Update ionotes', 'Install the latest version and restart? It takes about a minute.', 'Update')) return;
        await runUpdate((msg, failed) => { out.className = 'small' + (failed ? ' err' : ''); out.textContent = msg; });
      } }, 'Update now') : null), out);
}


function logBox() {
  const pre = h('pre.log', 'Loading…');
  const level = h('select', ['any', 'warning', 'error', 'auth'].map((l) => h('option', { value: l }, l)));
  const load = async () => { const r = await api(`/api/log?lines=300&level=${level.value}`).catch((e) => ({ lines: [e.message] })); pre.textContent = (r.lines || []).join('\n') || r.note || '(empty)'; pre.scrollTop = pre.scrollHeight; };
  level.addEventListener('change', load);
  load();
  return box('Server log', null, h('div.row', h('label', 'Show'), level, h('button.pillbtn', { onclick: load }, 'Reload')), pre);
}

/** A page as iopix lays one out: the title with its icon tile, the tabs under it (the tab is in the address:
 *  #/settings/users), then the tab's boxes. */
let again = () => {};
function pageTitle(text, ic, hue) { return h('h1.ptitle', h('span.pic', { style: `--hue:${hue}` }, icon(ic)), text); }
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

/** Settings: Display for everyone; Users and sign-in for admins (as iopix's Settings). */
export function renderSettings(tab) {
  const tabs = [['display', 'Display', async () => [appearance(), state.me.user ? null : box('Account', state.me.usersExist ? 'Sign in to see your notes.' : 'No accounts yet: anyone who can reach ionotes can read and change the notes. Create the admin account from the person icon at the top right.')]]];
  if (isAdmin()) tabs.push(['users', 'Users and sign-in', async () => { const s = await api('/api/settings'); return [state.me.usersExist ? await usersBox() : null, signInBox(s), await proxyBox()]; }]);
  return tabbedPage('settings', 'Settings', 'gear', 'var(--c-gray)', tabs, tab);
}

/** Maintenance (admins): where the notes are kept and their backups, MCP and the text in pictures, and ionotes itself
 *  (version, updates, the server log). Laid out like iopix's Maintenance. */
export function renderMaintenance(tab) {
  if (!isAdmin()) { const main = $('#main'); main.textContent = ''; main.append(h('div.page', h('div.pagein', pageTitle('Maintenance', 'wrench', 'var(--c-orange)'), h('p.muted', 'For admins only.')))); return null; }
  const s = () => api('/api/settings');
  return tabbedPage('maintenance', 'Maintenance', 'wrench', 'var(--c-orange)', [
    ['storage', 'Storage and backups', async () => { const x = await s(); return [databaseBox(x), exportBox()]; }],
    ['mcp', 'MCP and text in pictures', async () => { const x = await s(); return [await mcpBox(x), ocrBox(x)]; }],
    ['ionotes', 'ionotes', async () => { const x = await s(); return [await updateBox(x), logBox()]; }],
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
