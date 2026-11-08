/* The Server panel: Settings › Server, the same screen in every io app (admins). The MCP switch (when the app has
   one), the installed version with Check for updates, Update now and the daily check, what this server runs on, the
   server log, and Restart. Everything comes from iosuite-shared's /api/server and /api/log (Auth.server_router).

   Served at <app>/api/server/ui.js; it talks to the API next to it, so an app served under a sub-path works too. One
   ES module, no build step, its own styles (scoped under .iosv), using the app's colours when it has them (--fg,
   --fg2, --bg, --line, --accent, --brand, --danger; ioHealth's --text, --muted, --card, --link).

     const ui = await import(new URL('api/server/ui.js', document.baseURI).href);
     ui.mount(el, { toast });

   The app's info() for GET /api/server can add: mcpEnabled and mcpLocked (the MCP box; POST {mcpEnabled} goes to the
   app's apply()), mcpAbout (what /mcp lets an assistant do), and about: [[label, value], ...] (the This server box).
*/
const API = new URL('../', import.meta.url);   // .../api/

const ICONS = {
  update: 'M21 10.12h-6.78l2.74-2.82c-2.73-2.7-7.15-2.8-9.88-.1a6.875 6.875 0 0 0 0 9.79 7.02 7.02 0 0 0 9.88 0C18.32 15.65 19 14.08 19 12.1h2c0 1.98-.88 4.55-2.64 6.29-3.51 3.48-9.21 3.48-12.72 0-3.5-3.47-3.53-9.11-.02-12.58a8.987 8.987 0 0 1 12.65 0L21 3v7.12z',
  server: 'M20 13H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1v-6c0-.55-.45-1-1-1zM7 19c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zM20 3H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1V4c0-.55-.45-1-1-1zM7 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
  ai: 'M19 9l1.25-2.75L23 5l-2.75-1.25L19 1l-1.25 2.75L15 5l2.75 1.25L19 9zm-7.5.5L9 4 6.5 9.5 1 12l5.5 2.5L9 20l2.5-5.5L17 12l-5.5-2.5zM19 15l-1.25 2.75L15 19l2.75 1.25L19 23l1.25-2.75L23 19l-2.75-1.25L19 15z',
  log: 'M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z',
  restart: 'M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z',
  download: 'M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z',
};
const icon = (n) => { const s = document.createElement('span'); s.className = 'sv-ic'; s.innerHTML = `<svg viewBox="0 0 24 24"><path d="${ICONS[n] || ''}"/></svg>`; return s; };

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'checked') el.checked = !!v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  const add = (k) => { if (k == null || k === false) return; if (Array.isArray(k)) k.forEach(add); else el.append(k instanceof Node ? k : String(k)); };
  kids.forEach(add);
  return el;
}

async function api(path, opts = {}) {
  const o = { credentials: 'same-origin', ...opts, headers: { ...(opts.headers || {}) } };
  if (o.json !== undefined) { o.body = JSON.stringify(o.json); o.headers['Content-Type'] = 'application/json'; o.method = o.method || 'POST'; delete o.json; }
  const r = await fetch(new URL(path, API), o);
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : (j.error || JSON.stringify(j.detail)); } catch { /* not JSON */ }
    throw new Error(msg || `Error ${r.status}`);
  }
  return r.json();
}

// ------------------------------------------------------------------ styles (once per page)
const CSS = `
.iosv, .iosv-back { --sv-fg: var(--fg, var(--text, #202124)); --sv-fg2: var(--fg2, var(--muted, #5f6368)); --sv-line: var(--line, #dadce0);
  --sv-bg: var(--card, var(--bg, #fff)); --sv-bg2: var(--bg2, color-mix(in srgb, var(--sv-fg) 7%, var(--sv-bg)));
  --sv-accent: var(--accent, var(--link, #1a73e8)); --sv-accent-bg: var(--accent-bg, color-mix(in srgb, var(--sv-accent) 14%, transparent));
  --sv-brand: var(--brand, var(--sv-accent)); --sv-danger: var(--danger, #d93025); color: var(--sv-fg); font-size: 14px; line-height: 1.45; }
.iosv *, .iosv-back * { box-sizing: border-box; }
.iosv .sv-ic { display: inline-flex; width: 20px; height: 20px; flex: none; }
.iosv .sv-ic svg { width: 100%; height: 100%; fill: currentColor; }
.iosv .sv-muted { color: var(--sv-fg2); }
.iosv .sv-small { font-size: 12px; }
.iosv .sv-warn { color: var(--sv-danger); }
.iosv .sv-box { border: 1px solid var(--sv-line); border-radius: 16px; padding: 16px 20px; margin-bottom: 16px; background: var(--card, transparent); }
.iosv .sv-box h2 { margin: 0 0 6px; font-size: 16px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.iosv .sv-box h2 .sv-ic { color: var(--sv-brand); }
.iosv .sv-box p { margin: 6px 0; }
.iosv a { color: var(--sv-accent); }
.iosv .sv-kv { display: flex; gap: 12px; padding: 6px 0; border-bottom: 1px solid var(--sv-line); }
.iosv .sv-kv:last-of-type { border-bottom: 0; }
.iosv .sv-kv > span:first-child { flex: 0 0 140px; color: var(--sv-fg2); }
.iosv .sv-kv > span:last-child { min-width: 0; overflow-wrap: anywhere; }
.iosv .sv-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 8px 0; }
.iosv .sv-in { font: inherit; color: inherit; height: 36px; padding: 0 10px; border-radius: 8px; border: 1px solid var(--sv-line); background: var(--sv-bg); min-width: 0; margin: 0; }
.iosv input.sv-in { flex: 1; max-width: 240px; }
.iosv .sv-btn, .iosv-back .sv-btn { font: inherit; display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 14px; border-radius: 999px; color: var(--sv-fg2);
  border: 1px solid var(--sv-line); background: none; cursor: pointer; flex: none; white-space: nowrap; text-decoration: none; }
.iosv .sv-btn .sv-ic { width: 18px; height: 18px; margin-left: -4px; }
.iosv .sv-btn:hover, .iosv-back .sv-btn:hover { background: var(--sv-accent-bg); color: var(--sv-accent); border-color: transparent; }
.iosv .sv-btn.primary, .iosv-back .sv-btn.primary { background: var(--sv-brand); color: #fff; border-color: transparent; }
.iosv .sv-btn[disabled] { opacity: .5; pointer-events: none; }
.iosv label.sv-check { display: flex; gap: 8px; align-items: flex-start; margin: 6px 0; }
.iosv label.sv-check input { margin-top: 3px; accent-color: var(--sv-brand); }
.iosv pre.sv-log { max-height: 420px; overflow: auto; font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; background: var(--sv-bg2);
  border-radius: 8px; padding: 10px 12px; margin: 8px 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.iosv-back { position: fixed; inset: 0; background: rgba(0,0,0,.4); z-index: 1000; display: flex; align-items: center; justify-content: center; padding: 16px; }
.iosv-back .sv-dialog { background: var(--sv-bg); border-radius: 16px; padding: 20px 22px; width: 100%; max-width: 460px; box-shadow: 0 2px 12px rgba(0,0,0,.4); }
.iosv-back .sv-dialog h2 { margin: 0 0 10px; font-size: 18px; font-weight: 500; }
.iosv-back .sv-btns { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; flex-wrap: wrap; }
.iosv-toast { position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%); background: #323232; color: #fff; padding: 12px 18px; border-radius: 8px; z-index: 1001; font-size: 14px; max-width: calc(100vw - 32px); }
@media (max-width: 560px) { .iosv .sv-kv { flex-direction: column; gap: 2px; } .iosv .sv-kv > span:first-child { flex: none; } }
`;
function styles() {
  if (document.getElementById('iosv-css')) return;
  document.head.append(h('style', { id: 'iosv-css' }, CSS));
}

let toastTimer;
let toast = (msg) => {
  let t = document.querySelector('.iosv-toast');
  if (!t) { t = h('div', { class: 'iosv-toast', role: 'status' }); document.body.append(t); }
  t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 3500);
};
const fail = (e) => toast(e.message || String(e));

function confirmDialog(title, text, ok) {
  return new Promise((resolve) => {
    const back = h('div', { class: 'iosv-back iosv' });
    const close = (v) => { back.remove(); removeEventListener('keydown', esc); resolve(v); };
    const esc = (e) => { if (e.key === 'Escape') close(false); };
    addEventListener('keydown', esc);
    back.addEventListener('click', (e) => { if (e.target === back) close(false); });
    back.append(h('div', { class: 'sv-dialog', role: 'dialog', 'aria-label': title }, h('h2', null, title), h('p', null, text),
      h('div', { class: 'sv-btns' }, h('button', { class: 'sv-btn', onclick: () => close(false) }, 'Cancel'),
        h('button', { class: 'sv-btn primary', onclick: () => close(true) }, ok))));
    document.body.append(back);
    back.querySelector('.primary').focus();
  });
}

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
  if (opts.toast) toast = opts.toast;
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
    h('p', null, s.mcpAbout || `The address /mcp that lets an AI assistant (Claude, for example) work with ${s.name || 'this app'} as the account it signs in with.`,
      ' Each assistant signs in with an app password (Settings › Apps and devices) and has that account’s rights. Off: /mcp does not answer at all.'),
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
      s.docker ? h('span', { class: 'sv-muted' }, 'Docker: update by pulling the image (docker compose pull && docker compose up -d).')
        : s.canRun ? h('button', { class: `sv-btn${c && c.status === 'update' ? ' primary' : ''}`, disabled: p.running ? true : null, onclick: async () => {
          if (!await confirmDialog(`Update ${name}`, `Fetch the newest version, refresh its packages and restart ${name}? Settings and data stay; the page reloads when the new version is up.`, 'Update now')) return;
          if (await runUpdate()) setTimeout(redraw, 2500);
        } }, 'Update now')
          : h('span', { class: 'sv-muted' }, 'This install cannot update itself from here (run ./update.sh in the app folder).')),
    h('label', { class: 'sv-check' }, auto, ' Check for a new version once a day (only GitHub’s public list of changes is asked; nothing about this server is sent)'),
    s.autoCheckLocked ? h('p', { class: 'sv-muted sv-small' }, 'UPDATE_CHECK=0 in the environment keeps it off.') : null,
    h('p', { class: 'sv-muted sv-small' }, `Follows ${s.repo} (${s.branch}). `, h('a', { href: `https://github.com/${s.repo}/commits/${s.branch}`, target: '_blank', rel: 'noopener' }, 'Change log'), '.'));
}

function aboutBox(s) {
  if (!s.about || !s.about.length) return null;
  return h('div', { class: 'sv-box' }, h('h2', null, icon('server'), 'This server'),
    s.about.map(([k, v]) => h('div', { class: 'sv-kv' }, h('span', null, k), h('span', null, v == null || v === '' ? '—' : String(v)))),
    h('p', { class: 'sv-muted sv-small' }, 'These are set in the app’s config.env (or the environment), not here.'));
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
    h('p', null, `Stops ${name}; the service manager (systemd, launchd or Docker) starts it again within seconds. Nothing is lost; the page reloads when it is back.`),
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
  if (opts.toast) toast = opts.toast;
  el.classList.add('iosv');
  let log = null, timer = 0;
  const draw = async () => {
    let s;
    try { s = await api('server'); } catch (e) { el.replaceChildren(h('p', { class: 'sv-warn' }, e.message)); return; }
    log = log || logBox();
    el.replaceChildren('mcpEnabled' in s ? mcpBox(s, draw) : null, versionBox(s, draw), aboutBox(s), log, restartBox(s));
    clearTimeout(timer);
    if (s.progress && s.progress.running) timer = setTimeout(() => { if (el.isConnected) draw(); }, 4000);
  };
  el.replaceChildren(h('p', { class: 'sv-muted' }, 'Loading…'));
  await draw();
}
