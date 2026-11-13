/* The Server panel: Settings › Server, the same screen in every io app (admins). The MCP switch (when the app has
   one), the installed version with Check for updates, Update now and the daily check, the server log, and Restart.
   Everything comes from iosuite-shared's /api/server and /api/log (Auth.server_router).

   Served at <app>/api/server/ui.js; it talks to the API next to it, so an app served under a sub-path works too. One
   ES module, no build step, its own styles (scoped under .iosv), using the app's colours when it has them (--fg,
   --fg2, --bg, --line, --accent, --brand, --danger; ioHealth's --text, --muted, --card, --link).

     const ui = await import(new URL('api/server/ui.js', document.baseURI).href);
     ui.mount(el, { toast });

   The app's info() for GET /api/server can add: mcpEnabled and mcpLocked (the MCP box; POST {mcpEnabled} goes to the
   app's apply()) and mcpAbout (what /mcp lets an assistant do).
*/
import { api, confirmDialog, fail, h, icon, setToast, styles, toast } from '../auth/ui.js';

const API = new URL('../', import.meta.url);   // .../api/

const short = (s) => `v${s.version}${s.installed && s.installed !== 'unknown' ? ` (${s.installed.slice(0, 7)})` : ''}`;

/** Watch /api/status until `done(status)` says so (or the time is up), then reload the page. */
function reloadWhen(done, ms, gave) {
  const until = Date.now() + ms, from = Date.now() + 3000;
  const look = async () => {
    try { const s = await fetch(new URL('status', API), { credentials: 'same-origin' }).then((r) => r.json()); if (Date.now() > from && done(s)) { location.reload(); return; } } catch { /* restarting */ }
    if (Date.now() < until) setTimeout(look, 3000); else toast(gave);
  };
  setTimeout(look, 3000);
}

/** Start update.sh, then reload once another version or commit answers. Exported for the app's "update available"
 *  banner, so Update now behaves the same there. Returns false when it could not start. */
export async function runUpdate(opts = {}) {
  setToast(opts.toast);
  let was;
  try { const s = await fetch(new URL('status', API), { credentials: 'same-origin' }).then((r) => r.json()); was = `${s.version}|${s.commit || ''}`; } catch { was = ''; }
  try { await api('server', { json: { action: 'update' } }); } catch (e) { fail(e); return false; }
  toast('Updating; the app restarts when it is done, and the page reloads.');
  reloadWhen((s) => s.version && `${s.version}|${s.commit || ''}` !== was, 240000, 'The update did not finish; see Settings › Server.');
  return true;
}

// ------------------------------------------------------------------ the boxes
function mcpBox(s, redraw) {
  const on = h('input', { type: 'checkbox', checked: s.mcpEnabled, disabled: s.mcpLocked ? true : null, onchange: async (e) => {
    try { await api('server', { json: { mcpEnabled: e.target.checked } }); toast('Saved'); redraw(); } catch (err) { e.target.checked = !e.target.checked; fail(err); }
  } });
  const addr = new URL('../mcp', API).href;
  return h('div', { class: 'sv-box' }, h('h2', null, icon('ai'), 'MCP server'),
    h('p', null, s.mcpAbout || `Lets an AI assistant work with ${s.name || 'this app'} as you.`, ' It signs in with an app password.'),
    h('label', { class: 'sv-check' }, on, ' The MCP server is on'),
    s.mcpLocked ? h('p', { class: 'sv-muted sv-small' }, 'MCP=1 in the environment keeps it on.') : null,
    s.mcpEnabled ? h('div', { class: 'sv-kv' }, h('span', null, 'Address'), h('span', null, addr)) : null);
}

function versionBox(s, redraw) {
  const c = s.check, p = s.progress || {}, last = s.lastUpdate, name = s.name || 'The app';
  const state = h('p', null, p.running ? `Updating… ${name} restarts when it is done, and this page reloads.`
    : p.error ? `The last update failed: ${p.error}`
      : !c ? `You have ${short(s)}.`
        : c.status === 'current' ? `${short(s)} is the latest version.`
          : c.status === 'update' ? `You have ${short(s)}; ${c.remoteVersion ? `v${c.remoteVersion}` : 'a newer build'} is available${c.remoteDate ? ` (${c.remoteDate})` : ''}${c.remoteMessage ? `: ${c.remoteMessage.replace(/^v\d+\.\d+\.\d+:\s*/, '')}` : ''}.`
            : `Could not check: ${c.error}`);
  const auto = h('input', { type: 'checkbox', checked: s.autoCheck, disabled: s.autoCheckLocked ? true : null, onchange: async (e) => {
    try { await api('server', { json: { autoCheck: e.target.checked } }); toast('Saved'); redraw(); } catch (err) { e.target.checked = !e.target.checked; fail(err); }
  } });
  return h('div', { class: 'sv-box' }, h('h2', null, icon('update'), `${name} version`),
    state,
    !p.running && !p.error && last ? h('p', { class: last.ok ? 'sv-muted sv-small' : 'sv-warn sv-small' }, `Last update: ${last.text}`) : null,
    h('div', { class: 'sv-row' },
      h('button', { class: 'sv-btn', onclick: async () => { state.textContent = 'Checking…'; try { await api('server', { json: { action: 'check' } }); } catch (e) { fail(e); } redraw(); } }, icon('update'), 'Check for updates'),
      s.docker ? h('span', { class: 'sv-muted' }, 'Docker: docker compose pull && docker compose up -d')
        : s.canRun ? h('button', { class: `sv-btn${c && c.status === 'update' ? ' primary' : ''}`, disabled: p.running ? true : null, onclick: async () => {
          if (!await confirmDialog(`Update ${name}`, `Install the new version and restart ${name}? The page reloads when it is back.`, 'Update now')) return;
          if (await runUpdate()) setTimeout(redraw, 2500);
        } }, 'Update now')
          : h('span', { class: 'sv-muted' }, 'Run ./update.sh in the app folder to update.')),
    h('label', { class: 'sv-check' }, auto, ' Check for updates daily'),
    s.autoCheckLocked ? h('p', { class: 'sv-muted sv-small' }, 'UPDATE_CHECK=0 in the environment keeps it off.') : null,
    h('p', { class: 'sv-muted sv-small' }, `Follows ${s.repo} (${s.branch}). `, h('a', { href: `https://github.com/${s.repo}/commits/${s.branch}`, target: '_blank', rel: 'noopener' }, 'Change log'), '.'));
}

function logBox() {
  const level = h('select', { class: 'sv-in' }, [['any', 'Everything'], ['warning', 'Warnings and errors'], ['error', 'Errors'], ['auth', 'Sign-ins']].map(([v, l]) => h('option', { value: v }, l)));
  const contains = h('input', { class: 'sv-in', placeholder: 'Contains…' });
  const requests = h('input', { type: 'checkbox' });
  const out = h('pre', { class: 'sv-log' }, 'Loading…'), note = h('p', { class: 'sv-muted sv-small' });
  const load = async () => {
    try {
      const r = await api(`log?lines=300&level=${level.value}&contains=${encodeURIComponent(contains.value)}&requests=${requests.checked ? 1 : 0}`);
      out.textContent = r.lines.length ? r.lines.join('\n') : (r.note || 'Nothing matches.');
      note.textContent = r.note ? '' : `${r.file}: ${(r.size_bytes / 1024).toFixed(0)} kB, the last ${r.returned} lines.`;
      out.scrollTop = out.scrollHeight;
    } catch (e) { out.textContent = e.message; }
  };
  level.onchange = load; requests.onchange = load; contains.onchange = load;
  setTimeout(load, 0);
  return h('div', { class: 'sv-box' }, h('h2', null, icon('log'), 'Server log'),
    h('div', { class: 'sv-row' }, level, contains, h('label', { class: 'sv-check' }, requests, ' Requests too'),
      h('button', { class: 'sv-btn', onclick: load }, 'Reload'), h('a', { class: 'sv-btn', href: new URL('log/download', API).href }, icon('download'), 'Download')),
    out, note);
}

function restartBox(s) {
  const name = s.name || 'the app';
  return h('div', { class: 'sv-box' }, h('h2', null, icon('restart'), 'Restart'),
    h('div', { class: 'sv-row' }, h('button', { class: 'sv-btn', onclick: async () => {
      if (!await confirmDialog(`Restart ${name}`, 'Restart the server now? Everyone is disconnected for a few seconds.', 'Restart')) return;
      try { await api('server', { json: { action: 'restart' } }); } catch (e) { fail(e); return; }
      toast('Restarting…');
      reloadWhen(() => true, 90000, `${name} did not come back; check the service.`);
    } }, `Restart ${name}`)));
}

// ------------------------------------------------------------------ the panel
/** Draw the panel into `el`. opts: toast(msg) (the app's own toast; else the panel's). */
export async function mount(el, opts = {}) {
  styles();
  setToast(opts.toast);
  el.classList.add('iosv');
  let log = null, timer = 0;
  const draw = async () => {
    let s;
    try { s = await api('server'); } catch (e) { el.replaceChildren(h('p', { class: 'sv-warn' }, e.message)); return; }
    log = log || logBox();
    el.replaceChildren(...['mcpEnabled' in s ? mcpBox(s, draw) : null, versionBox(s, draw), log, restartBox(s)].filter(Boolean));
    clearTimeout(timer);
    if (s.progress && s.progress.running) timer = setTimeout(() => { if (el.isConnected) draw(); }, 4000);
  };
  el.replaceChildren(h('p', { class: 'sv-muted' }, 'Loading…'));
  await draw();
}
