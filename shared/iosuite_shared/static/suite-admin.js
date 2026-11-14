/* The Suite admin panel: everything in the Shared ioSuite database for the whole suite, the same screen in every io
   app (suite admins only). People and their role in every app, sessions, app passwords (with their scope), every app's
   keys and tokens, the apps with their default role and sign-in requirement, sign-in at a reverse proxy, and the family
   (who is in it, their colour, their ioContact card and their person in photos: the same in every app).

   It fills two Settings tabs, Security (people, roles, app passwords, sign-in at the proxy) and Global settings (the
   apps, keys and tokens): TABS.
   Served by iosuite-shared at <app>/api/suite-admin/ui.js (Auth.admin_router()); it talks to the API next to it, so an
   app served under a sub-path works too. One ES module, no build step, its own styles (scoped under .iosa), using the
   app's colours when it has them (--fg, --fg2, --bg, --line, --accent, --brand, --danger; ioHealth's --text, --muted,
   --card, --link).

     const ui = await import(new URL('api/suite-admin/ui.js', document.baseURI).href);
     ui.mount(el, { tab: 'security', sub: 'people', toast, onSub: (s) => history.replaceState(null, '', `#/settings/security/${s}`) });
*/
const API = new URL('./', import.meta.url);   // .../api/suite-admin/

const ICONS = {
  add: 'M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z',
  people: 'M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z',
  key: 'M12.65 10C11.83 7.67 9.61 6 7 6c-3.31 0-6 2.69-6 6s2.69 6 6 6c2.61 0 4.83-1.67 5.65-4H17v4h4v-4h2v-4H12.65zM7 14c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
  apps: 'M4 8h4V4H4v4zm6 12h4v-4h-4v4zm-6 0h4v-4H4v4zm0-6h4v-4H4v4zm6 0h4v-4h-4v4zm6-10v4h4V4h-4zm-6 4h4V4h-4v4zm6 6h4v-4h-4v4zm0 6h4v-4h-4v4z',
  update: 'M17.65 6.35A7.958 7.958 0 0012 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0112 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z',
  lock: 'M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zM9 8V6c0-1.66 1.34-3 3-3s3 1.34 3 3v2H9z',
};
const icon = (n) => { const s = document.createElement('span'); s.className = 'sa-ic'; s.innerHTML = `<svg viewBox="0 0 24 24"><path d="${ICONS[n] || ''}"/></svg>`; return s; };

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'style' && typeof v === 'object') for (const [sk, sv] of Object.entries(v)) { if (sk.startsWith('--')) el.style.setProperty(sk, sv); else el.style[sk] = sv; }
    else if (k === 'value') el.value = v;
    else if (k === 'checked') el.checked = !!v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  const add = (k) => { if (k == null || k === false) return; if (Array.isArray(k)) k.forEach(add); else el.append(k instanceof Node ? k : String(k)); };
  kids.forEach(add);
  return el;
}

async function api(path, opts = {}) {
  const o = { credentials: 'same-origin', ...opts, headers: { ...(opts.headers || {}) } };
  if (o.json !== undefined) { o.body = JSON.stringify(o.json); o.headers['Content-Type'] = 'application/json'; delete o.json; }
  const r = await fetch(new URL(path, API), o);
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : (j.error || JSON.stringify(j.detail)); } catch { /* not JSON */ }
    throw new Error(msg || `Error ${r.status}`);
  }
  const ct = r.headers.get('content-type') || '';
  return ct.includes('json') ? r.json() : r.text();
}

// ------------------------------------------------------------------ styles (once per page)
const CSS = `
.iosa, .iosa-back, .iosa-menu { --sa-fg: var(--fg, var(--text, #202124)); --sa-fg2: var(--fg2, var(--muted, #5f6368)); --sa-line: var(--line, #dadce0);
  --sa-bg: var(--card, var(--bg, #fff)); --sa-bg2: var(--bg2, color-mix(in srgb, var(--sa-fg) 7%, var(--sa-bg)));
  --sa-accent: var(--accent, var(--link, #1a73e8)); --sa-accent-bg: var(--accent-bg, color-mix(in srgb, var(--sa-accent) 14%, transparent));
  --sa-brand: var(--brand, var(--sa-accent)); --sa-danger: var(--danger, #d93025); --sa-update: #e8710a; color: var(--sa-fg); font-size: 14px; line-height: 1.45; }
.iosa *, .iosa-back * { box-sizing: border-box; }
.iosa .sa-ic, .iosa-back .sa-ic { display: inline-flex; width: 20px; height: 20px; flex: none; }
.iosa .sa-ic svg, .iosa-back .sa-ic svg { width: 100%; height: 100%; fill: currentColor; }
.iosa .sa-muted, .iosa-back .sa-muted { color: var(--sa-fg2); }
.iosa .sa-small, .iosa-back .sa-small { font-size: 12px; }
.iosa .sa-err, .iosa-back .sa-err { color: var(--sa-danger); }
.iosa .sa-intro { margin: 0 0 8px; }
.iosa .sa-segs { display: inline-flex; gap: 2px; padding: 3px; border-radius: 999px; background: var(--sa-bg2); margin: 4px 0 14px; flex-wrap: wrap; }
.iosa .sa-segs button { font: inherit; border: 0; background: none; cursor: pointer; padding: 6px 14px; border-radius: 999px; color: var(--sa-fg2); }
.iosa .sa-segs button.on { background: var(--sa-bg); color: var(--sa-accent); font-weight: 600; box-shadow: 0 1px 2px rgba(0,0,0,.12); }
.iosa .sa-box { border: 1px solid var(--sa-line); border-radius: 16px; padding: 16px 20px; margin-bottom: 16px; background: var(--card, transparent); min-width: min-content; }  /* a table wider than the page widens its box; past the window, the page scrolls at its edge */
.iosa .sa-box h2 { margin: 0 0 6px; font-size: 16px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.iosa .sa-box h2 .sa-ic { color: var(--sa-brand); }
.iosa .sa-box h3 { margin: 16px 0 4px; font-size: 13px; font-weight: 600; }
.iosa .sa-box p { margin: 6px 0; }
.iosa table.sa-t { border-collapse: collapse; width: 100%; }
.iosa table.sa-t th, .iosa table.sa-t td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--sa-line); vertical-align: middle; }
.iosa table.sa-t th { font-size: 12px; color: var(--sa-fg2); font-weight: 600; }
.iosa .sa-face, .iosa-back .sa-face { width: 28px; height: 28px; border-radius: 50%; object-fit: cover; flex: none; background: var(--sa-bg2); }
.iosa .sa-who, .iosa-back .sa-who { display: flex; align-items: center; gap: 8px; }
.iosa .sa-admins { display: flex; gap: 6px 8px; align-items: center; flex-wrap: wrap; padding: 10px 12px; border-radius: 10px; background: var(--sa-bg2); margin: 10px 0 6px; font-size: 13px; }
.iosa .sa-chip { font: inherit; font-size: 12px; color: var(--sa-fg); display: inline-flex; align-items: center; gap: 4px; padding: 2px 10px; border-radius: 999px; border: 1px solid var(--sa-line); background: var(--sa-bg); }
.iosa button.sa-chip { cursor: pointer; }
.iosa button.sa-chip:hover, .iosa button.sa-chip[aria-expanded="true"] { border-color: var(--sa-accent); color: var(--sa-accent); }
.iosa button.sa-chip.add { border-style: dashed; color: var(--sa-fg2); background: none; }
.iosa .sa-exc { display: grid; grid-template-columns: minmax(120px, max-content) 1fr; }  /* an app per row; only the people whose role differs */
.iosa .sa-exc > div { padding: 8px 0; border-bottom: 1px solid var(--sa-line); display: flex; align-items: center; gap: 6px; flex-wrap: wrap; min-width: 0; }
.iosa .sa-exc > div.sa-app { font-weight: 600; padding-right: 24px; }
.iosa-menu { position: fixed; z-index: 1002; min-width: 170px; padding: 4px; border-radius: 10px; border: 1px solid var(--sa-line); background: var(--sa-bg); color: var(--sa-fg); box-shadow: 0 6px 20px rgba(0,0,0,.25); font-size: 13px; }
.iosa-menu button { font: inherit; display: flex; justify-content: space-between; gap: 16px; width: 100%; text-align: left; border: 0; background: none; color: inherit; padding: 6px 10px; border-radius: 6px; cursor: pointer; }
.iosa-menu button:hover, .iosa-menu button:focus-visible { background: var(--sa-accent-bg); color: var(--sa-accent); outline: 0; }
.iosa-menu .sa-muted { color: var(--sa-fg2); font-size: 12px; }
.iosa-menu .sa-mhead { padding: 6px 10px 2px; font-size: 12px; color: var(--sa-fg2); }
.iosa-menu hr { border: 0; border-top: 1px solid var(--sa-line); margin: 4px 0; }
.iosa .sa-badge { display: inline-block; font-size: 12px; font-weight: 600; line-height: 1.5; padding: 1px 9px; border-radius: 999px; white-space: nowrap;
  color: var(--sa-update); background: color-mix(in srgb, var(--sa-update) 16%, transparent); border: 1px solid color-mix(in srgb, var(--sa-update) 45%, transparent); }
.iosa .sa-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; vertical-align: middle; }
.iosa a { color: var(--sa-accent); }
.iosa input.sa-in, .iosa select.sa-in, .iosa textarea.sa-in, .iosa-back input.sa-in, .iosa-back select.sa-in, .iosa-back textarea.sa-in {
  font: inherit; color: inherit; width: 100%; height: 40px; padding: 0 12px; border-radius: 8px; border: 1px solid var(--sa-line); background: var(--sa-bg); outline: 0; min-width: 0; margin: 0; }
.iosa textarea.sa-in { height: auto; padding: 8px 12px; resize: vertical; }
.iosa .sa-in:focus, .iosa-back .sa-in:focus { border-color: var(--sa-accent); box-shadow: 0 0 0 2px color-mix(in srgb, var(--sa-accent) 25%, transparent); }
.iosa select.sa-in.sa-sm, .iosa-back select.sa-in.sa-sm { height: 34px; width: auto; padding: 0 8px; }
.iosa .sa-btn, .iosa-back .sa-btn { font: inherit; display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 14px; border-radius: 999px; color: var(--sa-fg2);
  border: 1px solid var(--sa-line); background: none; cursor: pointer; flex: none; white-space: nowrap; }
.iosa .sa-btn .sa-ic, .iosa-back .sa-btn .sa-ic { width: 18px; height: 18px; margin-left: -4px; }
.iosa .sa-btn:hover, .iosa-back .sa-btn:hover { background: var(--sa-accent-bg); color: var(--sa-accent); border-color: transparent; }
.iosa .sa-btn.primary, .iosa-back .sa-btn.primary { background: var(--sa-brand); color: #fff; border-color: transparent; }
.iosa .sa-btn.primary:hover, .iosa-back .sa-btn.primary:hover { filter: brightness(.92); }
.iosa .sa-btn.danger:hover, .iosa-back .sa-btn.danger:hover { background: color-mix(in srgb, var(--sa-danger) 14%, transparent); color: var(--sa-danger); }
.iosa .sa-link, .iosa-back .sa-link { font: inherit; border: 0; background: none; padding: 0; cursor: pointer; color: var(--sa-accent); font-size: 12px; font-weight: 500; flex: none; }
.iosa .sa-link:hover, .iosa-back .sa-link:hover { text-decoration: underline; }
.iosa .sa-multi, .iosa-back .sa-multi { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.iosa .sa-multi input.sa-in, .iosa-back .sa-multi input.sa-in { flex: 1; min-width: 160px; width: auto; }
.iosa .sa-grid, .iosa-back .sa-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; margin: 8px 0; }
.iosa .sa-field, .iosa-back .sa-field { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.iosa .sa-field > span, .iosa-back .sa-field > span { font-size: 12px; color: var(--sa-fg2); }
.iosa label.sa-check, .iosa-back label.sa-check { display: flex; gap: 8px; align-items: flex-start; margin: 6px 0; }
.iosa label.sa-check input, .iosa-back label.sa-check input { margin-top: 3px; accent-color: var(--sa-brand); }
.iosa .sa-btns { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
.iosa-back { position: fixed; inset: 0; background: rgba(0,0,0,.4); z-index: 1000; display: flex; align-items: center; justify-content: center; padding: 16px; }
.iosa-back .sa-dialog { background: var(--sa-bg); border-radius: 16px; padding: 20px 22px; width: 100%; max-width: 460px; box-shadow: 0 2px 12px rgba(0,0,0,.4); max-height: 90vh; overflow: auto; }
.iosa-back .sa-dialog.wide { max-width: 620px; }
.iosa-back .sa-dialog h2 { margin: 0 0 10px; font-size: 18px; font-weight: 500; }
.iosa-back .sa-dialog h3 { margin: 18px 0 6px; font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 10px; }
.iosa-back .sa-dialog p { margin: 6px 0; }
.iosa-back .sa-dialog .sa-btns { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; flex-wrap: wrap; }
.iosa-back .sa-rolegrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 6px 16px; }
.iosa-back .sa-rolerow { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.iosa-back .sa-rolerow select.sa-in.sa-sm { width: 150px; flex: none; }
.iosa-back .sa-minirow { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--sa-line); font-size: 13px; }
.iosa-back .sa-minirow > span { min-width: 0; overflow-wrap: anywhere; }
.iosa-back .sa-btn.danger.solid { background: var(--sa-danger); color: #fff; border-color: transparent; }
.iosa-back .sa-btn:disabled { opacity: .45; cursor: default; pointer-events: none; }
.iosa-back .sa-pd { margin: 10px 0; border: 1px solid var(--sa-line); border-radius: 12px; overflow: hidden; }
.iosa-back .sa-pd > div { padding: 10px 14px; border-bottom: 1px solid var(--sa-line); }
.iosa-back .sa-pd > div:last-child { border-bottom: 0; }
.iosa-back .sa-pd b { display: block; font-weight: 600; margin-bottom: 2px; }
.iosa-back .sa-pd ul { margin: 0; padding-left: 18px; }
.iosa-back .sa-pd li.kept { color: var(--sa-fg2); list-style: circle; }
.iosa-back .sa-pd .sa-gone { color: var(--sa-danger); font-weight: 600; }
.iosa .sa-fam { display: flex; flex-direction: column; }
.iosa .sa-famrow { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 18px; padding: 12px 0; border-bottom: 1px solid var(--sa-line); }
.iosa .sa-famrow:last-child { border-bottom: 0; }
.iosa .sa-famrow.out > :not(.sa-famwho):not(.sa-famin) { display: none; }
.iosa .sa-famrow.out .sa-famwho { opacity: .6; }
.iosa .sa-famwho { display: flex; align-items: center; gap: 10px; min-width: 190px; flex: 1 1 190px; }
.iosa .sa-fammem { position: relative; flex: none; width: 36px; height: 36px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 700; font-size: 13px; background: var(--mc); }
.iosa .sa-fammem img { position: absolute; inset: 0; width: 100%; height: 100%; border-radius: 50%; object-fit: cover; box-shadow: 0 0 0 2px var(--mc); }
.iosa .sa-famin { flex: none; margin: 0 !important; align-items: center !important; }
.iosa .sa-famin input { margin-top: 0 !important; }
.iosa .sa-swatches { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; flex: 0 1 auto; }
.iosa .sa-sw { width: 22px; height: 22px; border-radius: 50%; border: 0; padding: 0; cursor: pointer; background: var(--c); box-shadow: inset 0 0 0 1px rgba(0,0,0,.12); }
.iosa .sa-sw.on { box-shadow: 0 0 0 2px var(--sa-bg), 0 0 0 4px var(--c); }
.iosa .sa-sw.custom { position: relative; overflow: hidden; background: conic-gradient(#e0426a, #e8a100, #1e8e3e, #0b8a9e, #1a73e8, #8e44d6, #e0426a); }
.iosa .sa-sw.custom input { position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; height: 100%; border: 0; padding: 0; }
.iosa .sa-famlinks { display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: flex-end; flex: 1 1 100%; padding-left: 46px; }
.iosa .sa-famlinks .sa-field { flex: 0 1 260px; }
@media (max-width: 600px) { .iosa .sa-famlinks { padding-left: 0; } .iosa .sa-famlinks .sa-field { flex: 1 1 200px; } }
.iosa .sa-famlinks select.sa-in, .iosa .sa-famlinks .sa-btn { height: 34px; width: 100%; justify-content: flex-start; overflow: hidden; text-overflow: ellipsis; }
.iosa-back .sa-cards { max-height: 320px; overflow: auto; margin-top: 8px; }
.iosa-back .sa-cards button { font: inherit; color: inherit; display: flex; width: 100%; text-align: left; border: 0; background: none; padding: 8px 10px; border-radius: 8px; cursor: pointer; gap: 8px; align-items: center; }
.iosa-back .sa-cards button:hover { background: color-mix(in srgb, var(--sa-accent) 14%, transparent); color: var(--sa-accent); }
.iosa-toast { position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%); background: #323232; color: #fff; padding: 12px 18px; border-radius: 8px; z-index: 1001; font-size: 14px; max-width: calc(100vw - 32px); }
`;
function styles() {
  if (document.getElementById('iosa-css')) return;
  document.head.append(h('style', { id: 'iosa-css' }, CSS));
}

// ------------------------------------------------------------------ small parts
let toastTimer;
let toast = (msg) => {
  let t = document.querySelector('.iosa-toast');
  if (!t) { t = h('div', { class: 'iosa-toast', role: 'status' }); document.body.append(t); }
  t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 3500);
};
const fail = (e) => toast(e.message || String(e));

function dialog(title, body, buttons, wide = false) {
  return new Promise((resolve) => {
    const back = h('div', { class: 'iosa-back' });
    const close = (v) => { back.remove(); removeEventListener('keydown', esc); resolve(v); };
    const esc = (e) => { if (e.key === 'Escape') close(null); };
    addEventListener('keydown', esc);
    back.addEventListener('click', (e) => { if (e.target === back) close(null); });
    const btns = (buttons || [{ label: 'OK', value: true, primary: true }]).map((b) =>
      h('button', { class: `sa-btn ${b.primary ? 'primary' : ''} ${b.danger ? 'danger' : ''} ${b.solid ? 'solid' : ''}`, 'data-id': b.id, onclick: () => close(typeof b.value === 'function' ? b.value() : b.value) }, b.label));
    back.append(h('div', { class: `sa-dialog${wide ? ' wide' : ''}`, role: 'dialog' }, h('h2', null, title), body, h('div', { class: 'sa-btns' }, btns)));
    document.body.append(back);
    const f = back.querySelector('input:not([type=checkbox]),select,textarea'); if (f) f.focus();
  });
}
const confirmDialog = (title, text, ok = 'OK', danger = false) => dialog(title, h('p', null, text), [{ label: 'Cancel', value: false }, { label: ok, value: true, primary: !danger, danger }]);
const fld = (l, e) => h('label', { class: 'sa-field' }, h('span', null, l), e);
const box = (ic, title, ...kids) => h('div', { class: 'sa-box' }, h('h2', null, icon(ic), title), ...kids);

const SCOPE_LABEL = { '': 'Everything', dav: 'Sync only (CalDAV, CardDAV, LDAP)' };
const ROLE_HELP = { none: 'no access', viewer: 'only looks', member: 'keeps their own', editor: 'also changes shared', admin: 'also settings' };
// what each role means, in the words the Roles and Apps panes show
const ROLE_LEGEND = [
  ['viewer', 'looks at what is shared with everyone (the Family calendar, the photo library) and changes nothing'],
  ['member', 'also keeps their own private calendars, lists, contacts, notes, health data and favourites'],
  ['editor', 'also changes what is shared with everyone'],
  ['admin', 'also the app’s settings']];
const legend = () => h('ul', { class: 'sa-muted sa-small', style: { margin: '4px 0 10px', paddingLeft: '18px' } },
  ROLE_LEGEND.map(([r, t]) => h('li', null, h('b', null, r), `: ${t}`)));
// a person without a password is a member at most, so an app's editor or admin default is member for them
const PW_MAX = ['none', 'viewer', 'member'];
const ALL_ROLES = ['none', 'viewer', 'member', 'editor', 'admin'];
const allowedFor = (u) => (u.passwordless ? PW_MAX : ALL_ROLES);
const defaultFor = (u, a) => (u.passwordless && !PW_MAX.includes(a.defaultRole) ? 'member' : a.defaultRole);
const TOOL_NOTE = 'suite admins only';
function sinceText(ts) {
  if (!ts) return 'never';
  const s = Date.now() / 1000 - ts;
  if (s < 90) return 'just now';
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  if (s < 86400 * 45) return `${Math.round(s / 86400)} d ago`;
  return new Date(ts * 1000).toLocaleDateString();
}
const appLabel = (o, key) => (o.apps.find((a) => a.app === key) || {}).name || key;

// ------------------------------------------------------------------ the panel
export const SUBS = [['people', 'People'], ['family', 'Family'], ['roles', 'Roles'], ['passwords', 'App passwords'], ['signin', 'Sign-in at the proxy'], ['apps', 'Apps'], ['updates', 'Updates'], ['keys', 'Keys and tokens']];
/** The two Settings tabs the panel fills, in every app: #/settings/security/<sub> and #/settings/global/<sub>. */
export const TABS = {
  security: { label: 'Security', subs: ['people', 'family', 'roles', 'passwords', 'signin'],
    intro: 'Who can sign in to the io apps, who is in the family, and with which role. Changes apply to every app.' },
  global: { label: 'Global settings', subs: ['apps', 'updates', 'keys'],
    intro: 'Settings for every io app: default roles, sign-in, updates and keys.' },
};

/** Draw the panel into `el`. Options: tab (security or global: which parts are shown, see TABS), sub (the first part
    shown), onSub(sub) (called when another part is picked, e.g. to put it in the address), toast(msg) (the app's own
    toast; else the panel's). */
export async function mount(el, opts = {}) {
  styles();
  if (opts.toast) toast = opts.toast;
  const root = h('div', { class: 'iosa' });
  el.replaceChildren(root);
  const tab = TABS[opts.tab] || TABS.security;
  const subs = SUBS.filter(([k]) => tab.subs.includes(k));
  let sub = subs.some(([k]) => k === opts.sub) ? opts.sub : subs[0][0];
  let photo = null;  // ioPix's People (the person in photos), read once, when People is first shown
  const photoPeople = () => (photo = photo || api('photo-people').catch((e) => ({ available: false, people: [], error: e.message })));
  const draw = async () => {
    let o;
    try { o = await api('../suite-admin'); } catch (e) { root.replaceChildren(h('p', { class: 'sa-err' }, e.message)); return; }
    const body = h('div');
    root.replaceChildren(
      h('p', { class: 'sa-muted sa-intro' }, tab.intro),
      h('div', { class: 'sa-segs' }, subs.map(([k, l]) => h('button', { class: sub === k ? 'on' : '', onclick: () => go(k) }, l))),
      body);
    const ctx = { o, redraw: draw, go, photoPeople };
    await ({ people: people, family: family, roles: roles, passwords: passwords, keys: keys, apps: apps, updates: updates, signin: signin })[sub](body, ctx);
  };
  const go = (k) => { sub = k; if (opts.onSub) opts.onSub(k); draw(); };
  await draw();
  return { go, refresh: draw };
}

/** A role picker for one account in one app: "default (…)" removes the row, so the app's default applies. */
function roleSelect(u, a) {
  if (a.adminTool) return null;  // an admin tool is for suite admins only: no role to pick
  const cur = u.roles[a.app] || '';
  return h('select', { class: 'sa-in sa-sm', title: `${u.displayName} in ${a.name}` },
    h('option', { value: '' }, `default (${defaultFor(u, a)})`),
    [...new Set([...allowedFor(u), ...(cur ? [cur] : [])])].map((x) => h('option', { value: x, selected: x === cur ? true : null }, x)));
}

const faceUrl = (id) => new URL(`photo-people/${id}/face.jpg`, API).href;
const face = (id) => h('img', { class: 'sa-face', src: faceUrl(id), alt: '', loading: 'lazy', onerror: (e) => { e.target.style.visibility = 'hidden'; } });

function people(el, ctx) {
  const { o } = ctx;
  // the person in photos (ioPix's People): a column, filled in once ioPix answered, left out without ioPix
  const photoTh = h('th', { style: { display: 'none' } }, 'In photos');
  const photoTd = {};
  ctx.photoPeople().then((p) => {
    if (!p.available) return;
    const names = new Map(p.people.map((x) => [x.id, x.name]));
    photoTh.style.display = '';
    for (const u of o.users) {
      const td = photoTd[u.id];
      td.style.display = '';
      td.replaceChildren(u.photoPerson ? h('span', { class: 'sa-who' }, face(u.photoPerson), names.get(u.photoPerson) || `#${u.photoPerson}`) : h('span', { class: 'sa-muted' }, '–'));
    }
  });
  el.append(box('people', 'People',
    h('table', { class: 'sa-t' }, h('tr', null, h('th', null, 'Account'), photoTh, h('th', null, 'Email'), h('th', null, 'Sign-in'), h('th', null, 'Last seen'), h('th')),
      o.users.map((u) => h('tr', null,
        h('td', null, h('b', null, u.displayName), h('div', { class: 'sa-muted sa-small' }, u.name,
          u.suiteAdmin ? ' · suite admin' : '', u.listed ? '' : ' · not on the sign-in list', u.id === o.me ? ' · you' : '')),
        (photoTd[u.id] = h('td', { class: 'sa-small', style: { display: 'none' } })),
        h('td', { class: 'sa-small' }, u.email || h('span', { class: 'sa-muted' }, '–')),
        h('td', { class: 'sa-small' }, u.passwordless ? 'One click (LAN, member at most)' : 'Password',
          u.appPasswords ? h('div', { class: 'sa-muted' }, `${u.appPasswords} app password${u.appPasswords > 1 ? 's' : ''}`) : null),
        h('td', { class: 'sa-small' }, sinceText(u.lastSeen || u.last_login), h('div', { class: 'sa-muted' }, `${u.sessions} session${u.sessions === 1 ? '' : 's'}`)),
        h('td', { style: { textAlign: 'right' } }, h('button', { class: 'sa-btn', onclick: () => editAccount(ctx, u) }, 'Manage'))))),
    h('p', null, h('button', { class: 'sa-btn primary', onclick: () => editAccount(ctx, null) }, icon('add'), 'Add someone'))));
}

/** Family: the one list of the family for every app (iosuite_shared.family). Everyone with an account is in it unless
    taken out here; each member has a colour (picked, or the next free one), their ioContact card and their person in
    ioPix's People (their face). ioCalendar tags events with them, ioTask gives them tasks. */
async function family(el, ctx) {
  let r;
  try { r = await api('family'); } catch (e) { el.append(h('p', { class: 'sa-err' }, e.message)); return; }
  const list = h('div', { class: 'sa-fam' });
  const memFace = (m) => {
    const b = h('span', { class: 'sa-fammem', style: { '--mc': m.color } }, m.initials);
    if (m.hasFace) b.append(h('img', { src: new URL(`../auth/family/${m.id}/face?${m.photoPerson || ''}-${m.contactId || ''}`, API).href, alt: '', onerror: (e) => e.currentTarget.remove() }));
    return b;
  };
  const save = async (m, body, msg) => {
    try { await api(`family/${m.id}`, { method: 'PATCH', json: body }); r = await api('family'); draw(); if (msg) toast(msg); } catch (e) { fail(e); }
  };
  let people = null;
  ctx.photoPeople().then((p) => { people = p; if (p.available) draw(); });
  const row = (m) => {
    const inF = h('input', { type: 'checkbox', checked: m.inFamily, onchange: () => save(m, { inFamily: inF.checked }, inF.checked ? `${m.displayName} is in the family` : `${m.displayName} is out of the family`) });
    const sw = (c) => h('button', { class: `sa-sw ${m.color.toLowerCase() === c.toLowerCase() ? 'on' : ''}`, style: { '--c': c }, title: c, 'aria-label': `Colour ${c}`,
      onclick: () => save(m, { color: c }) });
    const custom = h('input', { type: 'color', value: m.color, title: 'Another colour', onchange: (e) => save(m, { color: e.target.value }) });
    const isPalette = r.palette.some((c) => c.toLowerCase() === m.color.toLowerCase());
    const swatches = h('div', { class: 'sa-swatches' }, r.palette.map(sw),
      h('span', { class: `sa-sw custom ${isPalette ? '' : 'on'}`, style: isPalette ? null : { '--c': m.color, background: m.color }, title: 'Another colour' }, custom),
      m.colorPicked ? h('button', { class: 'sa-link', title: 'Give back the colour, so the next free one is used', onclick: () => save(m, { color: null }) }, 'Reset') : null);
    const card = h('button', { class: 'sa-btn', title: 'Their card in ioContact', onclick: () => pickCard(m) },
      m.contactId ? (m.contactName || `Card #${m.contactId}`) : h('span', { class: 'sa-muted' }, 'Link a card…'));
    let photo = null;
    if (people && people.available) {
      const list2 = people.people.slice().sort((a, b) => a.name.localeCompare(b.name));
      if (m.photoPerson && !list2.some((x) => x.id === m.photoPerson)) list2.unshift({ id: m.photoPerson, name: `#${m.photoPerson} (not in People any more)` });
      photo = h('select', { class: 'sa-in', onchange: (e) => save(m, { photoPerson: e.target.value ? Number(e.target.value) : null }) },
        h('option', { value: '' }, 'not linked'), list2.map((x) => h('option', { value: x.id, selected: x.id === m.photoPerson ? true : null }, x.name)));
    }
    return h('div', { class: `sa-famrow ${m.inFamily ? '' : 'out'}` },
      h('div', { class: 'sa-famwho' }, memFace(m), h('div', null, h('b', null, m.displayName), h('div', { class: 'sa-muted sa-small' }, m.name, m.inFamily ? '' : ' · not in the family'))),
      h('label', { class: 'sa-check sa-famin', title: 'In the family: events and tasks can be for them, and they get a private calendar and list' }, inF, h('span', null, 'In the family')),
      swatches,
      h('div', { class: 'sa-famlinks' }, fld('ioContact card', card), photo ? fld('Person in photos (ioPix)', photo) : null));
  };
  const pickCard = async (m) => {
    const q = h('input', { class: 'sa-in', placeholder: 'Search ioContact', value: m.displayName });
    const out = h('div', { class: 'sa-cards' });
    let chosen;
    const done = { close: null };
    const find = async () => {
      let res; try { res = await api(`family/contacts?q=${encodeURIComponent(q.value.trim())}`); } catch (e) { out.replaceChildren(h('p', { class: 'sa-err' }, e.message)); return; }
      if (!res.available) { out.replaceChildren(h('p', { class: 'sa-muted' }, 'ioContact is not in the suite.')); return; }
      out.replaceChildren(...(res.error ? [h('p', { class: 'sa-err' }, res.error)] : []),
        ...(res.items.length ? res.items.map((c) => h('button', { onclick: () => { chosen = c; done.close(); } }, c.fn || `#${c.id}`, c.iopixPersonId ? h('span', { class: 'sa-muted sa-small' }, ' · has a face') : null))
          : [h('p', { class: 'sa-muted' }, 'No card matches.')]));
    };
    let t; q.addEventListener('input', () => { clearTimeout(t); t = setTimeout(find, 250); });
    find();
    const body = h('div', null, h('p', { class: 'sa-muted' }, `${m.displayName}’s own card in ioContact (the one ioContact calls “This is me”). Its photo is their face when no person in photos is linked.`), q, out);
    const p = dialog(`${m.displayName}’s card`, body, [...(m.contactId ? [{ label: 'Unlink', value: 'unlink', danger: true }] : []), { label: 'Cancel', value: null }]);
    done.close = () => out.closest('.iosa-back')?.dispatchEvent(new MouseEvent('click'));  // a pick closes the dialog, as a click beside it does
    const v = await p;
    if (chosen) {
      const b = { contactId: chosen.id };
      if (chosen.iopixPersonId && !m.photoPerson) b.photoPerson = chosen.iopixPersonId;  // the card's face, linked too
      await save(m, b, `${m.displayName}: ${chosen.fn}`);
    } else if (v === 'unlink') await save(m, { contactId: null }, `${m.displayName}: no card`);
  };
  const draw = () => list.replaceChildren(...r.items.map(row));
  draw();
  el.append(box('people', 'Family',
    h('p', { class: 'sa-muted' }, 'One list for every app: events in ioCalendar and tasks in ioTask can be for these people, and they show with the same colour, initials and face everywhere. Everyone with an account is in the family unless taken out here (an admin or guest account is not family).'),
    list));
}

/** The account dialog: who they are, how they sign in, their role in every app, and (existing accounts) their
    sessions and app passwords. */
async function editAccount(ctx, u) {
  const { o } = ctx;
  const isNew = !u, me = u && u.id === o.me;
  u = u || { name: '', displayName: '', email: '', listed: true, suiteAdmin: false, passwordless: false, roles: {} };
  const name = h('input', { class: 'sa-in', value: u.name, autocomplete: 'off' });
  const dn = h('input', { class: 'sa-in', value: isNew ? '' : u.displayName, autocomplete: 'off' });
  const em = h('input', { class: 'sa-in', type: 'email', value: u.email, autocomplete: 'off' });
  const listed = h('input', { type: 'checkbox', checked: u.listed });
  const sa = h('input', { type: 'checkbox', checked: u.suiteAdmin, disabled: me ? true : null });
  const pw = h('input', { class: 'sa-in', type: 'password', autocomplete: 'new-password', placeholder: isNew ? '8 or more; empty: one click on the LAN, member at most' : (u.passwordless ? 'none yet (one click on the LAN)' : 'unchanged') });
  const nopw = h('input', { type: 'checkbox', checked: !isNew && u.passwordless });
  const sels = {};
  const roleRows = o.apps.map((a) => { sels[a.app] = roleSelect(u, a); return h('div', { class: 'sa-rolerow' }, h('span', null, a.name, a.registered ? '' : h('span', { class: 'sa-muted sa-small' }, ' (not running)')), sels[a.app] || h('span', { class: 'sa-muted sa-small' }, TOOL_NOTE)); });
  const extra = h('div');
  // the person in photos: someone in ioPix's People; their face is the account's picture in ioPix (sign-in screen, menu)
  const ppSel = h('select', { class: 'sa-in' }, h('option', { value: '' }, 'not linked'));
  const ppFace = h('span');
  const ppNote = h('div', { class: 'sa-muted sa-small' });
  const ppRow = h('div', { style: { display: 'none' } }, h('h3', null, 'Person in photos'),
    h('div', { class: 'sa-who' }, ppFace, ppSel), ppNote);
  const showFace = () => ppFace.replaceChildren(...(ppSel.value ? [face(ppSel.value)] : []));
  ppSel.addEventListener('change', showFace);
  ctx.photoPeople().then((p) => {
    if (!p.available) return;
    ppRow.style.display = '';
    const list = p.people.slice().sort((a, b) => a.name.localeCompare(b.name));
    if (u.photoPerson && !list.some((x) => x.id === u.photoPerson)) list.unshift({ id: u.photoPerson, name: `#${u.photoPerson} (not in People any more)` });
    ppSel.append(...list.map((x) => h('option', { value: x.id, selected: x.id === u.photoPerson ? true : null }, x.photos != null ? `${x.name} (${x.photos})` : x.name)));
    ppSel.value = u.photoPerson ? String(u.photoPerson) : '';
    showFace();
    ppNote.textContent = p.error || 'Someone in ioPix’s People: their face is this account’s picture in ioPix (the sign-in screen and the menu) and “Photos of me” shows their photos.';
  });
  const body = h('div', null,
    h('div', { class: 'sa-grid' }, fld('User name', name), fld('Display name', dn), fld('Email', em), fld(isNew ? 'Password' : 'New password', pw)),
    !isNew && !me ? h('label', { class: 'sa-check' }, nopw, h('span', null, 'No password: one-click sign-in on the LAN only, member at most everywhere, no app passwords')) : null,
    h('label', { class: 'sa-check' }, listed, h('span', null, 'On the sign-in list')),
    h('label', { class: 'sa-check' }, sa, h('span', null, 'Suite admin: admin in every app, manages this screen', me ? h('span', { class: 'sa-muted sa-small' }, ' (another suite admin can change yours)') : '')),
    ppRow, h('h3', null, 'Role in each app'), h('div', { class: 'sa-rolegrid' }, roleRows), extra);
  if (!isNew) accountExtra(extra, o, u);
  const save = async () => {
    const roles = {};
    for (const [k, s] of Object.entries(sels)) if (s && (s.value || '') !== (u.roles[k] || '')) roles[k] = s.value || null;
    const b = { name: name.value.trim(), displayName: dn.value.trim(), email: em.value.trim(), listed: listed.checked, suiteAdmin: sa.checked, roles };
    if (isNew) b.password = pw.value;
    else if (nopw.checked && !u.passwordless) b.password = '';
    else if (pw.value) b.password = pw.value;
    if (me) delete b.suiteAdmin;
    const pp = ppSel.value ? Number(ppSel.value) : null;
    if (ppRow.style.display !== 'none' && pp !== (u.photoPerson || null)) b.photoPerson = pp;
    try {
      await api(isNew ? 'users' : `users/${u.id}`, { method: isNew ? 'POST' : 'PATCH', json: b });
      toast(isNew ? 'Account made' : 'Saved'); return true;
    } catch (e) { fail(e); return false; }
  };
  const buttons = [{ label: 'Cancel', value: null }];
  if (!isNew && !me) buttons.unshift({ label: 'Delete', value: 'delete', danger: true });
  buttons.push({ label: isNew ? 'Add' : 'Save', value: 'save', primary: true });
  // the dialog closes on any button; keep it open on a failed save by asking again
  for (;;) {
    const v = await dialog(isNew ? 'Add someone' : u.displayName, body, buttons, true);
    if (v === 'save') { if (await save()) break; continue; }
    if (v === 'delete') {
      if (await deletePerson(u)) break;
      continue;
    }
    break;
  }
  ctx.redraw();
}
// ---- deleting someone: what goes in every app (GET users/<id>/data), a typed confirmation, then what went
const num = (n) => Number(n).toLocaleString();
function personData(d, done, who) {
  const box = h('div', { class: 'sa-pd' });
  const empty = [];
  for (const a of d.apps || []) {
    const gone = a.items.filter((i) => !i.kept), kept = a.items.filter((i) => i.kept);
    if (!a.items.length && !a.error) { empty.push(a.name); continue; }
    box.append(h('div', null, h('b', null, a.name),
      a.error ? h('p', { class: 'sa-err sa-small' }, done
        ? `${a.name} could not be reached (${a.error}); it removes ${who}’s data the next time it starts.`
        : `${a.name} could not be asked (${a.error}). If you delete now, it removes ${who}’s data the next time it starts.`) : null,
      gone.length || kept.length ? h('ul', null,
        gone.map((i) => h('li', null, h('span', { class: 'sa-gone' }, num(i.count)), ` ${i.what}`)),
        kept.map((i) => h('li', { class: 'kept' }, `${num(i.count)} ${i.what}: ${done ? 'kept' : 'stay'}, shared with everyone`))) : null));
  }
  if (d.shared) box.append(h('div', null, h('b', null, 'The account'), h('ul', null,
    h('li', null, `${who}’s sign-in, from every app`), d.shared.map((i) => h('li', null, h('span', { class: 'sa-gone' }, num(i.count)), ` ${i.what}`)))));
  if (empty.length) box.append(h('div', { class: 'sa-muted sa-small' }, `Nothing of ${who}’s in ${empty.join(', ')}.`));
  return box;
}
async function deletePerson(u) {
  const who = u.displayName || u.name;
  const list = h('div', null, h('p', { class: 'sa-muted' }, `Looking at what ${who} keeps in each app…`));
  const typed = h('input', { class: 'sa-in', autocomplete: 'off', autocapitalize: 'off', spellcheck: 'false', placeholder: u.name });
  const body = h('div', null,
    h('p', null, `This deletes ${who}’s account and removes everything that is only theirs, in every app. It cannot be undone.`),
    list,
    h('p', { class: 'sa-muted sa-small' }, 'What they added to something everyone shares (the Family calendar, shared lists, family recipes, shared bookmarks and albums) stays for the others.'),
    fld(`Type ${u.name} to confirm`, typed));
  const asked = dialog(`Delete ${who}?`, body, [{ label: 'Cancel', value: false }, { label: 'Delete for good', value: true, danger: true, solid: true, id: 'go' }], true);
  const go = [...document.querySelectorAll('.iosa-back')].pop().querySelector('[data-id=go]');
  let looked = false;
  const check = () => { go.disabled = !(looked && typed.value.trim() === u.name); };
  typed.addEventListener('input', check);
  check();
  api(`users/${u.id}/data`)
    .then((d) => list.replaceChildren(personData(d, false, who)))
    .catch((e) => list.replaceChildren(h('p', { class: 'sa-err' }, `Could not look at the apps: ${e.message}`)))
    .finally(() => { looked = true; check(); });
  if (!await asked) return false;
  const busy = h('div', { class: 'iosa-back' }, h('div', { class: 'sa-dialog', role: 'dialog' }, h('h2', null, `Deleting ${who}…`),
    h('p', { class: 'sa-muted' }, 'Each app removes their data; with a lot of health data or photos this can take a minute.')));
  document.body.append(busy);
  let res;
  try { res = await api(`users/${u.id}`, { method: 'DELETE' }); } catch (e) { busy.remove(); fail(e); return false; }
  busy.remove();
  await dialog(`${who} is deleted`, h('div', null, h('p', null, 'This is what was removed:'), personData(res, true, who)), null, true);
  return true;
}
async function accountExtra(el, o, u) {
  let ses, pws;
  try { [ses, pws] = await Promise.all([api(`users/${u.id}/sessions`), api(`app-passwords?user=${u.id}`)]); } catch (e) { el.replaceChildren(h('p', { class: 'sa-err' }, e.message)); return; }
  const draw = () => el.replaceChildren(...[
    h('h3', null, 'Sessions', ses.sessions.length ? h('button', { class: 'sa-link', onclick: async () => {
      try { await api(`users/${u.id}/sessions`, { method: 'DELETE' }); ses.sessions = ses.sessions.filter((s) => s.current); toast('Signed out everywhere'); draw(); } catch (e) { fail(e); }
    } }, 'End all') : null),
    ses.sessions.length ? ses.sessions.map((s) => h('div', { class: 'sa-minirow' }, h('span', null, `${appLabel(o, s.app)} · ${s.client}${s.cloudflare ? ' · via Cloudflare' : ''}`, h('span', { class: 'sa-muted sa-small' }, ` ${s.lastIp || s.ip || ''} · ${sinceText(s.lastSeen)}${s.current ? ' · this browser' : ''}`)),
      s.current ? null : h('button', { class: 'sa-link', onclick: async () => { try { await api(`users/${u.id}/sessions?session=${encodeURIComponent(s.id)}`, { method: 'DELETE' }); ses.sessions = ses.sessions.filter((x) => x !== s); draw(); } catch (e) { fail(e); } } }, 'End'))) : h('p', { class: 'sa-muted sa-small' }, 'Not signed in anywhere.'),
    h('h3', null, 'App passwords'),
    pws.items.length ? pws.items.map((p) => h('div', { class: 'sa-minirow' }, h('span', null, `${p.appName} · ${p.label}`, h('span', { class: 'sa-muted sa-small' }, ` ${SCOPE_LABEL[p.scope] || p.scope} · used ${sinceText(p.lastUsed)}`)),
      h('button', { class: 'sa-link', onclick: async () => { if (await revokeAppPassword(p)) { pws.items = pws.items.filter((x) => x !== p); draw(); } } }, 'Revoke'))) : h('p', { class: 'sa-muted sa-small' }, 'None. Make one under App passwords.')].flat());
  draw();
}
async function revokeAppPassword(p) {
  if (!await confirmDialog('Revoke app password', `Revoke "${p.label}" (${p.displayName}, ${p.appName})? The device using it stops working.`, 'Revoke', true)) return false;
  try { await api(`app-passwords/${p.id}`, { method: 'DELETE' }); toast('Revoked'); return true; } catch (e) { fail(e); return false; }
}

/** A small menu under `anchor`: items are {label, hint, run}, '-' (a line) or a string (a heading). One at a time; a
    click elsewhere, Esc or scrolling closes it. Fixed to the window, so it works whatever scrolls the page. */
let closeMenu = () => {};
function menu(anchor, items) {
  closeMenu();
  const m = h('div', { class: 'iosa-menu', role: 'menu' }, items.map((it) => it === '-' ? h('hr')
    : typeof it === 'string' ? h('div', { class: 'sa-mhead' }, it)
    : h('button', { role: 'menuitem', onclick: () => { closeMenu(); it.run(); } }, it.label, it.hint ? h('span', { class: 'sa-muted' }, it.hint) : null)));
  document.body.append(m);
  const r = anchor.getBoundingClientRect(), vw = document.documentElement.clientWidth, vh = document.documentElement.clientHeight;
  m.style.left = `${Math.max(8, Math.min(r.left, vw - m.offsetWidth - 8))}px`;
  m.style.top = `${r.bottom + 4 + m.offsetHeight > vh - 8 ? Math.max(8, r.top - 4 - m.offsetHeight) : r.bottom + 4}px`;
  anchor.setAttribute('aria-expanded', 'true');
  const off = (e) => {
    if (e.type === 'keydown') { if (e.key === 'Escape') { closeMenu(); anchor.focus(); } return; }
    if (e.type === 'scroll' || !(m.contains(e.target) || anchor.contains(e.target))) closeMenu();
  };
  const evs = ['mousedown', 'keydown', 'scroll'];
  evs.forEach((t) => document.addEventListener(t, off, true));
  closeMenu = () => { m.remove(); anchor.removeAttribute('aria-expanded'); evs.forEach((t) => document.removeEventListener(t, off, true)); closeMenu = () => {}; };
  const first = m.querySelector('button'); if (first) first.focus();
}

/** Roles: one row per app with its default role, and only the people whose role there differs from it. The page grows
    downward as apps are added; suite admins (admin everywhere) are one line above. */
function roles(el, ctx) {
  const { o } = ctx;
  const admins = o.users.filter((u) => u.suiteAdmin), people = o.users.filter((u) => !u.suiteAdmin);
  const dflt = defaultFor, allowed = allowedFor;
  const list = h('div', { class: 'sa-exc' });
  const set = async (u, a, role) => {
    try {
      await api(`users/${u.id}`, { method: 'PATCH', json: { roles: { [a.app]: role } } });
      if (role) u.roles[a.app] = role; else delete u.roles[a.app];
      toast(`${u.displayName}: ${role || `default (${dflt(u, a)})`} in ${a.name}`);
      draw();
    } catch (e) { fail(e); ctx.redraw(); }
  };
  const roleItems = (u, a) => allowed(u).map((r) => ({ label: r, hint: r === u.roles[a.app] ? 'now' : r === dflt(u, a) ? 'default' : '', run: () => set(u, a, r) }));
  const chip = (u, a) => {
    const b = h('button', { class: 'sa-chip', 'aria-haspopup': 'menu', title: `${u.displayName} in ${a.name}` }, `${u.displayName}: `, h('b', null, u.roles[a.app]));
    b.onclick = () => menu(b, [`${u.displayName} in ${a.name}`, ...roleItems(u, a), '-', { label: 'Back to the default', hint: dflt(u, a), run: () => set(u, a, null) }]);
    return b;
  };
  const adder = (a) => {
    const rest = people.filter((u) => !u.roles[a.app]);
    if (!rest.length) return null;
    const b = h('button', { class: 'sa-chip add', 'aria-haspopup': 'menu', title: `Give someone another role in ${a.name}` }, icon('add'), 'person');
    b.querySelector('.sa-ic').style.cssText = 'width:14px;height:14px';
    b.onclick = () => menu(b, [`Someone in ${a.name}`, ...rest.map((u) => ({ label: u.displayName, hint: `now ${dflt(u, a)}`,
      run: () => menu(b, [`${u.displayName} in ${a.name}`, ...roleItems(u, a).filter((x) => x.label !== dflt(u, a))]) }))]);
    return b;
  };
  const draw = () => list.replaceChildren(...o.apps.flatMap((a) => [
    h('div', { class: 'sa-app' }, a.name, a.registered ? null : h('span', { class: 'sa-muted sa-small', style: { fontWeight: 400 } }, '(not running)')),
    a.adminTool ? h('div', null, h('span', { class: 'sa-muted sa-small' }, `admin tool: ${TOOL_NOTE}`))
      : h('div', null, h('span', { class: 'sa-muted sa-small' }, `everyone: ${a.defaultRole}`),
        people.filter((u) => u.roles[a.app]).map((u) => chip(u, a)), adder(a))]));
  draw();
  el.append(box('lock', 'Roles',
    h('p', { class: 'sa-muted' }, 'Each app gives everyone its default role (set under Global settings › Apps). Only the people who have another role in an app are listed there. Each role can do what the one before it does:'),
    legend(),
    admins.length ? h('div', { class: 'sa-admins' }, h('span', { class: 'sa-muted' }, 'Suite admins, admin in every app:'),
      admins.map((u) => h('span', { class: 'sa-chip' }, u.displayName)), h('span', { class: 'sa-muted sa-small' }, 'Change this under People.')) : null,
    people.length ? list : h('p', { class: 'sa-muted' }, 'Everyone is a suite admin, so there are no roles to set.')));
}

async function passwords(el, ctx) {
  const { o } = ctx;
  const fu = h('select', { class: 'sa-in sa-sm' }, h('option', { value: '' }, 'Everyone'), o.users.map((u) => h('option', { value: u.id }, u.displayName)));
  const fa = h('select', { class: 'sa-in sa-sm' }, h('option', { value: '' }, 'Every app'), o.apps.map((a) => h('option', { value: a.app }, a.name)));
  const list = h('div');
  const draw = async () => {
    let r; try { r = await api(`app-passwords?${new URLSearchParams({ ...(fu.value ? { user: fu.value } : {}), ...(fa.value ? { app: fa.value } : {}) })}`); } catch (e) { list.replaceChildren(h('p', { class: 'sa-err' }, e.message)); return; }
    list.replaceChildren(r.items.length ? h('table', { class: 'sa-t' }, h('tr', null, h('th', null, 'Person'), h('th', null, 'App'), h('th', null, 'Device'), h('th', null, 'Reaches'), h('th', null, 'Made'), h('th', null, 'Last used'), h('th')),
      r.items.map((p) => {
        const sc = h('select', { class: 'sa-in sa-sm' }, [...new Set([...(o.scopes || ['', 'dav']), p.scope])].map((s) => h('option', { value: s, selected: s === p.scope ? true : null }, SCOPE_LABEL[s] || s)));
        sc.onchange = async () => { try { await api(`app-passwords/${p.id}`, { method: 'PATCH', json: { scope: sc.value } }); p.scope = sc.value; toast('Saved'); } catch (e) { fail(e); sc.value = p.scope; } };
        return h('tr', null, h('td', null, p.displayName), h('td', null, p.appName), h('td', null, p.label), h('td', null, sc),
          h('td', { class: 'sa-small' }, new Date(p.created * 1000).toLocaleDateString()), h('td', { class: 'sa-small' }, sinceText(p.lastUsed)),
          h('td', { style: { textAlign: 'right' } }, h('button', { class: 'sa-btn danger', onclick: async () => { if (await revokeAppPassword(p)) draw(); } }, 'Revoke')));
      })) : h('p', { class: 'sa-muted' }, 'No app passwords here.'));
  };
  fu.onchange = fa.onchange = draw;
  const who = h('select', { class: 'sa-in sa-sm' }, o.users.filter((u) => !u.passwordless).map((u) => h('option', { value: u.id }, u.displayName)));
  const app = h('select', { class: 'sa-in sa-sm' }, o.apps.map((a) => h('option', { value: a.app }, a.name)));
  const label = h('input', { class: 'sa-in', placeholder: 'Device, e.g. Alex’s iPhone' });
  const scope = h('select', { class: 'sa-in sa-sm' }, (o.scopes || ['', 'dav']).map((s) => h('option', { value: s }, SCOPE_LABEL[s] || s)));
  el.append(box('key', 'App passwords',
    h('p', { class: 'sa-muted' }, 'For clients that cannot use the sign-in page (CalDAV, CardDAV, LDAP, MCP). “Sync only” works for sync and nothing else.'),
    h('div', { class: 'sa-multi' }, fu, fa), list),
  box('add', 'Make one for someone',
    h('div', { class: 'sa-multi' }, who, app, scope, label, h('button', { class: 'sa-btn primary', onclick: async () => {
      try {
        const r = await api('app-passwords', { method: 'POST', json: { userId: Number(who.value), app: app.value, label: label.value.trim(), scope: scope.value } });
        label.value = '';
        await dialog('App password', h('div', null, h('p', null, `For ${r.name} in ${appLabel(o, r.app)}. Copy it now: it is not shown again.`),
          h('div', { class: 'sa-multi' }, h('input', { class: 'sa-in', value: r.password, readonly: true, onfocus: (e) => e.target.select() }),
            h('button', { class: 'sa-btn', onclick: async () => { try { await navigator.clipboard.writeText(r.password); toast('Copied'); } catch { toast('Select it and copy'); } } }, 'Copy')),
          h('p', { class: 'sa-muted sa-small' }, `User name: ${r.name}`)), [{ label: 'Done', value: true, primary: true }]);
        draw();
      } catch (e) { fail(e); }
    } }, 'Make'))));
  draw();
}

/** Every app's keys and tokens for things outside the suite (Home Assistant, AccuWeather, Google Maps...), kept in the
    Shared ioSuite database. Write-only: a value is never shown back, only whether one is set. */
async function keys(el, ctx) {
  const { o } = ctx;
  let r;
  try { r = await api('keys'); } catch (e) { el.replaceChildren(h('p', { class: 'sa-err' }, e.message)); return; }
  const groups = {};
  for (const k of r.items) (groups[k.app] = groups[k.app] || []).push(k);
  const order = Object.keys(groups).sort((a, b) => (a === '' ? 1 : b === '' ? -1 : appLabel(o, a).localeCompare(appLabel(o, b))));
  const row = (k) => {
    const inp = h('input', { class: 'sa-in', type: 'password', autocomplete: 'off', placeholder: k.set ? 'set; paste a new one to replace it' : 'not set' });
    const where = k.app === '' ? '_suite' : k.app;
    const save = async (value) => {
      try { const n = await api(`keys/${encodeURIComponent(where)}/${encodeURIComponent(k.name)}`, { method: 'PUT', json: { value } }); Object.assign(k, n); toast(n.set ? 'Saved' : 'Cleared'); el.replaceChildren(); keys(el, ctx); } catch (e) { fail(e); }
    };
    return h('div', { style: { padding: '10px 0', borderTop: '1px solid var(--sa-line)' } },
      h('div', null, h('b', null, k.label), ' ', h('span', { class: 'sa-small' }, k.set ? '· set' : h('span', { class: 'sa-muted' }, '· not set'),
        k.updated ? h('span', { class: 'sa-muted' }, ` ${sinceText(k.updated)}${k.updatedBy ? ` by ${k.updatedBy}` : ''}`) : null)),
      k.hint ? h('div', { class: 'sa-muted sa-small' }, k.hint) : null,
      k.envSet ? h('div', { class: 'sa-muted sa-small' }, `${k.env} in the app's environment wins over this one.`) : null,
      h('div', { style: { marginTop: '6px' } }, h('div', { class: 'sa-multi' }, inp,
        h('button', { class: 'sa-btn', onclick: () => { if (inp.value.trim()) save(inp.value.trim()); else toast('Paste the new value first'); } }, 'Replace'),
        k.set ? h('button', { class: 'sa-btn danger', onclick: async () => { if (await confirmDialog('Clear key', `Clear ${k.label}? What uses it stops working until a new one is set.`, 'Clear', true)) save(''); } }, 'Clear') : null)));
  };
  el.append(box('key', 'Keys and tokens',
    h('p', { class: 'sa-muted' }, 'Keys for services outside the suite. A saved value is never shown again.'),
    order.length ? order.map((a) => [h('h3', null, a === '' ? 'Whole suite' : appLabel(o, a)), h('div', null, groups[a].map(row))]) : h('p', { class: 'sa-muted' }, 'No app keeps any yet.')));
}

function apps(el, ctx) {
  const { o } = ctx;
  el.append(box('apps', 'Apps',
    h('p', { class: 'sa-muted' }, 'The default role is what someone without a role in the app gets (“none”: invitation only). Admin tools are for suite admins only. “Sign-in required” shows visitors only the sign-in page: on unless you turn it off, and always on in an admin tool.'),
    legend(),
    h('table', { class: 'sa-t' }, h('tr', null, h('th', null, 'App'), h('th', null, 'Version'), h('th', null, 'Default role'), h('th', null, 'Sign-in required'), h('th', null, 'In use'), h('th')),
      o.apps.map((a) => {
        const dr = a.adminTool ? h('span', { class: 'sa-muted sa-small' }, TOOL_NOTE)
          : h('select', { class: 'sa-in sa-sm' }, (o.defaultRoles || ['none', 'viewer', 'member', 'editor']).map((x) => h('option', { value: x, selected: x === a.defaultRole ? true : null }, `${x} (${ROLE_HELP[x]})`)));
        dr.onchange = async () => { try { await api(`apps/${a.app}`, { method: 'PATCH', json: { defaultRole: dr.value } }); a.defaultRole = dr.value; toast(`${a.name}: ${dr.value} by default`); } catch (e) { fail(e); dr.value = a.defaultRole; } };
        const rl = a.adminTool ? h('input', { type: 'checkbox', checked: true, disabled: true, title: 'An admin tool always requires sign-in' })
          : h('input', { type: 'checkbox', checked: a.requireLogin, onchange: async (e) => { try { await api(`apps/${a.app}`, { method: 'PATCH', json: { requireLogin: e.target.checked } }); toast('Saved'); } catch (err) { e.target.checked = !e.target.checked; fail(err); } } });
        return h('tr', null,
          h('td', null, h('span', { style: { whiteSpace: 'nowrap' } }, h('span', { class: 'sa-dot', style: { background: a.color || 'var(--sa-fg2)' } }), ' ', a.url ? h('a', { href: a.url, target: '_blank', rel: 'noopener' }, a.name) : h('b', null, a.name)),
            h('div', { class: 'sa-muted sa-small' }, a.registered ? `${a.app} · seen ${sinceText(a.lastSeen)}` : `${a.app} · not registered (only in the data)`)),
          h('td', { class: 'sa-small' }, a.version || '–'), h('td', null, dr), h('td', null, rl),
          h('td', { class: 'sa-small' }, `${a.roles} role${a.roles === 1 ? '' : 's'}, ${a.appPasswords} app password${a.appPasswords === 1 ? '' : 's'}`),
          h('td', { style: { textAlign: 'right' } }, h('button', { class: 'sa-btn danger', onclick: () => forgetApp(ctx, a) }, 'Forget')));
      }))));
}
/* Updates: the suite has one version and one update, every app at once (iosuite_shared.suiteupdates). The apps pick a
   request up within seconds, so the page follows along while an update runs, and loads again when it is over: the app
   that serves this page was updated too. The apps' own lines are under Details. */
async function updates(el) {
  let d, timer = null, until = 0, round = false;
  try { d = await api('updates'); } catch (e) { el.replaceChildren(h('p', { class: 'sa-err' }, e.message)); return; }
  const head = h('div'), list = h('div');
  const v = (x) => (x ? `v${x}` : 'an unknown version');
  const refresh = async () => {
    timer = null;
    if (!el.isConnected) return;
    try { d = await api('updates'); draw(); } catch { /* the app serving this page is restarting: try again */ }
    if (round && d.status !== 'updating') { location.reload(); return; }
    if (round || Date.now() < until) timer = setTimeout(refresh, 4000);
  };
  const watch = () => { until = Date.now() + 30000; if (!timer) timer = setTimeout(refresh, 3000); };
  const ask = async (json) => {
    try { d = await api('updates', { method: 'POST', json }); draw(); watch(); return true; } catch (e) { fail(e); return false; }
  };
  const update = async () => {
    if (!await confirmDialog('Update ioSuite', `Install ${v(d.latest)} in every app? Each app restarts; this page follows along and loads again when they are back.`, 'Update')) return;
    await ask({ action: 'update' });
  };
  const last = (a) => {
    if (!a.watching) return h('span', { class: 'sa-muted' }, 'not running');
    if (a.pending === 'update' || a.state === 'running') return 'updating…';
    if (a.docker && a.behind) return h('span', { class: 'sa-muted' }, 'Docker: pull the image');
    if (!a.state) return h('span', { class: 'sa-muted' }, '–');
    return h('span', { class: a.state === 'failed' ? 'sa-err' : '' }, a.state, a.message ? h('div', { class: 'sa-muted sa-small' }, a.message) : null);
  };
  const draw = () => {
    const live = d.apps.filter((a) => a.watching), name = (k) => appLabel({ apps: d.apps }, k);
    round = round || d.status === 'updating';
    const checked = h('span', { class: 'sa-muted sa-small' }, ` Checked ${sinceText(d.checked)}.`);
    let line, button = null;
    if (d.status === 'updating') {
      line = [h('b', null, `Updating to ${v(d.latest)}…`), ` ${live.filter((a) => !a.behind).length} of ${live.length} apps done.`];
    } else if (d.status === 'update') {
      line = [h('b', null, `ioSuite ${v(d.installed)}`), ' is installed. ', h('span', { class: 'sa-badge' }, `Update available: ${v(d.latest)}`), checked];
      button = d.canUpdate ? h('button', { class: 'sa-btn primary', onclick: update }, d.failed.length ? 'Try again' : `Update to ${v(d.latest)}`) : null;
    } else if (d.status === 'error') {
      line = [h('b', null, `ioSuite ${v(d.installed)}`), ' is installed. ', h('span', { class: 'sa-err' }, 'GitHub could not be asked for the newest version.')];
    } else {
      line = [h('b', null, `ioSuite ${v(d.installed)}`), ' is the newest version.', checked];
    }
    const docker = d.apps.filter((a) => a.behind && a.docker);
    head.replaceChildren(...[
      h('p', { style: { fontSize: '15px' } }, line),
      d.failed.length ? h('p', { class: 'sa-err' }, `The update failed in ${d.failed.map(name).join(', ')}; see Details.`) : null,
      docker.length && d.status === 'update' ? h('p', { class: 'sa-muted sa-small' }, `In Docker (${docker.map((a) => a.name).join(', ')}): docker compose pull && docker compose up -d`) : null,
      h('div', { class: 'sa-multi', style: { margin: '10px 0' } }, button,
        h('button', { class: 'sa-btn', disabled: d.status === 'updating' ? true : null, onclick: async () => { if (await ask({ action: 'check' })) toast('Asking GitHub…'); } }, 'Check now'))].filter(Boolean));
    // the apps' own lines, shown without asking when they are not all in the same place: one failed, or some are behind and others not
    const uneven = d.failed.length > 0 || (d.status === 'update' && d.behind.length < live.length);
    const was = list.querySelector('details');
    list.replaceChildren(h('details', { open: (was ? was.open : uneven) ? true : null },
      h('summary', { class: 'sa-muted', style: { cursor: 'pointer' } }, `Details: ${d.apps.length} app${d.apps.length === 1 ? '' : 's'}`),
      h('table', { class: 'sa-t' }, h('tr', null, h('th', null, 'App'), h('th', null, 'Version'), h('th', null, 'Last update')),
        d.apps.map((a) => h('tr', null,
          h('td', null, h('b', null, a.name), h('div', { class: 'sa-muted sa-small' }, a.app)),
          h('td', { class: 'sa-small' }, a.version || '–', a.behind ? [' ', h('span', { class: 'sa-badge' }, 'behind')] : null, a.commit ? h('div', { class: 'sa-muted' }, a.commit) : null),
          h('td', { class: 'sa-small' }, last(a)))))));
  };
  draw();
  if (round) watch();
  const auto = h('input', { type: 'checkbox', checked: d.autoCheck, onchange: async (e) => { if (await ask({ autoCheck: e.target.checked })) toast('Saved'); else e.target.checked = !e.target.checked; } });
  el.append(box('update', 'Updates',
    h('p', { class: 'sa-muted' }, 'The suite has one version, and every app is updated together: each app installs the new version with its own update.sh and restarts; settings and data stay.'),
    head, h('label', { class: 'sa-check' }, auto, h('span', null, 'Check for a new version daily')), list));
}

async function forgetApp(ctx, a) {
  const data = h('input', { type: 'checkbox' });
  const v = await dialog(`Forget ${a.name}`, h('div', null, h('p', null, `Take ${a.name} off the list of apps? If it is still installed, it comes back the next time it starts.`),
    h('label', { class: 'sa-check' }, data, h('span', null, `Also remove its roles, settings and app passwords (${a.roles} roles, ${a.appPasswords} app passwords): it was uninstalled for good`))),
  [{ label: 'Cancel', value: null }, { label: 'Forget', value: () => (data.checked ? 'data' : 'list'), danger: true }]);
  if (!v) return;
  try { await api(`apps/${a.app}${v === 'data' ? '?data=1' : ''}`, { method: 'DELETE' }); toast(`${a.name} forgotten`); ctx.redraw(); } catch (e) { fail(e); }
}

/* Sign-in at a reverse proxy (Cloudflare Access on a tunnel, or Authelia & co. behind nginx...), once for every app:
   iosuite-shared keeps it suite-wide and reads it from nowhere else (config.env and the environment are ignored). */
const PROXIES = [['off', 'Off'], ['cloudflare', 'Cloudflare Access'], ['haproxy', 'HAProxy'], ['nginx', 'nginx'], ['caddy', 'Caddy'], ['traefik', 'Traefik'], ['header', 'Another proxy']];
const NO_ACCOUNT = [['', 'Gets the sign-in screen'], ['deny', 'Is denied access'], ['viewer', 'Gets a viewer account'], ['member', 'Gets a member account'], ['editor', 'Gets an editor account']];
async function signin(el) {
  let d;
  try { d = await api('proxy'); } catch (e) { el.replaceChildren(h('p', { class: 'sa-err' }, e.message)); return; }
  const draw = () => {
    const v = d.values;
    const opt = (list, cur) => list.map(([k, l]) => h('option', { value: k, selected: k === (cur || '') ? true : null }, l));
    const mode = h('select', { class: 'sa-in' }, opt(PROXIES, (v.AUTH_PROXY || 'off').toLowerCase()));
    const team = h('input', { class: 'sa-in', value: v.CF_ACCESS_TEAM, placeholder: 'myteam.cloudflareaccess.com', autocomplete: 'off' });
    const aud = h('textarea', { class: 'sa-in', rows: 2, placeholder: 'Application Audience (AUD) tag; several: one per line', style: { fontFamily: 'monospace', fontSize: '12px' } }, (d.auds || []).join('\n'));
    const header = h('input', { class: 'sa-in', value: v.AUTH_PROXY_HEADER, placeholder: 'default: Cf-Access-Authenticated-User-Email / Remote-User, X-Forwarded-User…', autocomplete: 'off' });
    const trusted = h('input', { class: 'sa-in', value: v.AUTH_PROXY_TRUSTED, placeholder: 'default: 127.0.0.1, ::1', autocomplete: 'off' });
    const create = h('select', { class: 'sa-in' }, opt(NO_ACCOUNT, (v.AUTH_PROXY_CREATE || '').toLowerCase()));
    const cf = h('div', { class: 'sa-grid' }, fld('Cloudflare team domain', team), fld('AUD tag(s)', aud));
    const other = h('div', { class: 'sa-grid' }, fld('User header', header));
    const addr = h('div', { class: 'sa-grid' }, fld('Reverse proxy addresses', trusted));
    const rest = h('div', { class: 'sa-grid' }, fld('Someone with no account', create));
    const show = () => { cf.style.display = mode.value === 'cloudflare' ? '' : 'none'; other.style.display = rest.style.display = mode.value === 'off' ? 'none' : ''; };
    mode.onchange = show;
    const seen = d.seen && d.seen.iss ? h('p', { class: 'sa-muted sa-small' }, `Last request through Cloudflare (unverified): team ${String(d.seen.iss).replace(/^https:\/\//, '')}, AUD ${[].concat(d.seen.aud || []).join(', ')}${d.seen.email ? ', ' + d.seen.email : ''}. `,
      h('button', { class: 'sa-link', onclick: () => {
        mode.value = 'cloudflare'; show(); team.value = String(d.seen.iss).replace(/^https:\/\//, '');
        const tags = aud.value.split(/[\s,]+/).filter(Boolean); [].concat(d.seen.aud || []).forEach((t) => { if (!tags.includes(t)) tags.push(t); }); aud.value = tags.join('\n');
      } }, 'Use these')) : null;
    const here = d.here || {};
    const state = here.mode === 'off' || !here.mode ? 'Off: everyone uses the suite’s own sign-in.' : here.mode === 'cloudflare'
      ? (here.cloudflareVerified ? `On: Cloudflare Access tokens are verified (${(here.auds || []).length} AUD tag${(here.auds || []).length === 1 ? '' : 's'}).` : 'On, but without the team domain and AUD tag: nobody is signed in through Cloudflare.')
      : `On (${here.mode}): the user header is believed from ${(here.trusted || []).join(', ')}.`;
    const save = async () => {
      const body = { AUTH_PROXY: mode.value === 'off' ? '' : mode.value, CF_ACCESS_TEAM: team.value.trim(), CF_ACCESS_AUD: aud.value.split(/[\s,]+/).filter(Boolean).join(', '),
        AUTH_PROXY_HEADER: header.value.trim(), AUTH_PROXY_TRUSTED: trusted.value.trim(), AUTH_PROXY_CREATE: create.value };
      try { d = await api('proxy', { method: 'PUT', json: body }); toast('Saved for every app'); draw(); } catch (e) { fail(e); }
    };
    el.replaceChildren(box('key', 'Sign-in at the proxy',
      h('p', { class: 'sa-muted' }, 'Someone signed in at your reverse proxy (Cloudflare Access, Authelia, Authentik, oauth2-proxy…) is signed in to every io app, matched by email, then name.'),
      h('p', null, h('b', null, state)),
      h('div', { class: 'sa-grid' }, fld('Proxy', mode)), cf, seen,
      h('p', { class: 'sa-muted sa-small' }, 'Team domain: Zero Trust › Settings › Team name and domain. AUD tag: Zero Trust › Access › Applications › Overview (one per application).'),
      other, rest, addr,
      h('p', { class: 'sa-muted sa-small' }, 'Reverse proxy addresses: where your reverse proxy connects from (addresses or networks), whether or not it signs people in. Whoever comes through a proxy that is not listed counts as outside your network: no one-click sign-in, no first account. A header that names the user is believed from these addresses only.'),
      h('div', { class: 'sa-btns' }, h('button', { class: 'sa-btn primary', onclick: save }, 'Save for every app'))));
    show();
  };
  draw();
}
