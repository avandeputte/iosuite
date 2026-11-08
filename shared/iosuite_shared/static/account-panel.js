/* The account panels, the same in every io app, and the small kit the Server panel shares (h, api, the styles):
   Settings › Account (display name, email, password), the Appearance and Units rows of Settings › Display, and the
   signed-in account's own app passwords (Settings › Apps and devices). They talk to /api/auth/* next to them.

     const ui = await import(new URL('api/auth/ui.js', document.baseURI).href);
     await ui.mountAccount(el, { toast });                         // Settings › Account
     el.append(ui.themeRow(current, (k) => applyTheme(k)));         // 'light' | 'dark' | 'system', saved with the account
     el.append(ui.unitsRow(current, (k) => applyUnits(k)));         // 'auto' | 'metric' | 'imperial'
     await ui.mountAppPasswords(el, { toast, syncOnly: 'Calendar apps only (CalDAV)' });

   ui.box(icon, title, ...kids) and ui.row(label, hint, control) build the app's own boxes in the same look.
*/
const API = new URL('../', import.meta.url);   // .../api/

export const ICONS = {
  update: 'M21 10.12h-6.78l2.74-2.82c-2.73-2.7-7.15-2.8-9.88-.1a6.875 6.875 0 0 0 0 9.79 7.02 7.02 0 0 0 9.88 0C18.32 15.65 19 14.08 19 12.1h2c0 1.98-.88 4.55-2.64 6.29-3.51 3.48-9.21 3.48-12.72 0-3.5-3.47-3.53-9.11-.02-12.58a8.987 8.987 0 0 1 12.65 0L21 3v7.12z',
  server: 'M20 13H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1v-6c0-.55-.45-1-1-1zM7 19c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zM20 3H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1V4c0-.55-.45-1-1-1zM7 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
  ai: 'M19 9l1.25-2.75L23 5l-2.75-1.25L19 1l-1.25 2.75L15 5l2.75 1.25L19 9zm-7.5.5L9 4 6.5 9.5 1 12l5.5 2.5L9 20l2.5-5.5L17 12l-5.5-2.5zM19 15l-1.25 2.75L15 19l2.75 1.25L19 23l1.25-2.75L23 19l-2.75-1.25L19 15z',
  log: 'M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z',
  restart: 'M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z',
  person: 'M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z',
  key: 'M12.65 10C11.83 7.67 9.61 6 7 6c-3.31 0-6 2.69-6 6s2.69 6 6 6c2.61 0 4.83-1.67 5.65-4H17v4h4v-4h2v-4H12.65zM7 14c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
  theme: 'M12 3a9 9 0 1 0 0 18c.83 0 1.5-.67 1.5-1.5 0-.39-.15-.74-.39-1.01-.23-.26-.38-.61-.38-.99 0-.83.67-1.5 1.5-1.5H16c2.76 0 5-2.24 5-5 0-4.42-4.03-8-9-8zm-5.5 9c-.83 0-1.5-.67-1.5-1.5S5.67 9 6.5 9 8 9.67 8 10.5 7.33 12 6.5 12zm3-4C8.67 8 8 7.33 8 6.5S8.67 5 9.5 5s1.5.67 1.5 1.5S10.33 8 9.5 8zm5 0c-.83 0-1.5-.67-1.5-1.5S13.67 5 14.5 5s1.5.67 1.5 1.5S15.33 8 14.5 8zm3 4c-.83 0-1.5-.67-1.5-1.5S16.67 9 17.5 9s1.5.67 1.5 1.5-.67 1.5-1.5 1.5z',
  devices: 'M4 6h18V4H4c-1.1 0-2 .9-2 2v11H0v3h14v-3H4V6zm19 2h-6c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h6c.55 0 1-.45 1-1V9c0-.55-.45-1-1-1zm-1 9h-4v-7h4v7z',
  download: 'M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z',
};
export const icon = (n) => { const s = document.createElement('span'); s.className = 'sv-ic'; s.innerHTML = `<svg viewBox="0 0 24 24"><path d="${ICONS[n] || ''}"/></svg>`; return s; };

export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'checked') el.checked = !!v;
    else if (k === 'value') el.value = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  const add = (k) => { if (k == null || k === false) return; if (Array.isArray(k)) k.forEach(add); else el.append(k instanceof Node ? k : String(k)); };
  kids.forEach(add);
  return el;
}

export async function api(path, opts = {}) {
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
/* settings rows (label and hint on the left, the control on the right), segmented choices, tables */
.iosv .sv-srow { display: flex; gap: 16px; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--sv-line); flex-wrap: wrap; }
.iosv .sv-srow:last-child { border-bottom: 0; }
.iosv .sv-srow > div:first-child { min-width: 200px; flex: 1; }
.iosv .sv-seg { display: inline-flex; border: 1px solid var(--sv-line); border-radius: 999px; overflow: hidden; }
.iosv .sv-seg button { font: inherit; border: 0; background: none; color: var(--sv-fg2); padding: 6px 14px; cursor: pointer; }
.iosv .sv-seg button + button { border-left: 1px solid var(--sv-line); }
.iosv .sv-seg button.on { background: var(--sv-accent-bg); color: var(--sv-accent); }
.iosv .sv-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px 16px; margin: 8px 0; }
.iosv label.sv-field { display: flex; flex-direction: column; gap: 4px; }
.iosv label.sv-field > span { font-size: 12px; color: var(--sv-fg2); }
.iosv label.sv-field input.sv-in { max-width: none; flex: none; }
.iosv table.sv-t { width: 100%; border-collapse: collapse; margin: 8px 0; }
.iosv table.sv-t th, .iosv table.sv-t td { text-align: left; padding: 6px 8px 6px 0; border-bottom: 1px solid var(--sv-line); font-size: 13px; }
.iosv table.sv-t th { color: var(--sv-fg2); font-weight: 500; }
.iosv code.sv-code { font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; background: var(--sv-bg2); padding: 4px 8px; border-radius: 6px; overflow-wrap: anywhere; user-select: all; }
@media (max-width: 560px) { .iosv .sv-kv { flex-direction: column; gap: 2px; } .iosv .sv-kv > span:first-child { flex: none; } }
`;
export function styles() {
  if (document.getElementById('iosv-css')) return;
  document.head.append(h('style', { id: 'iosv-css' }, CSS));
}

let toastTimer;
let showToast = (msg) => {
  let t = document.querySelector('.iosv-toast');
  if (!t) { t = h('div', { class: 'iosv-toast', role: 'status' }); document.body.append(t); }
  t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 3500);
};
/** The app's own toast, when it passes one (mount(el, {toast})); else the panels' own. */
export const setToast = (fn) => { if (fn) showToast = fn; };
export const toast = (msg) => showToast(msg);
export const fail = (e) => toast(e.message || String(e));

export function confirmDialog(title, text, ok) {
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


// ------------------------------------------------------------------ building blocks
/** A box as every Settings tab draws one: an icon, a title, then its rows. */
export function box(ic, title, ...kids) {
  styles();
  return h('div', { class: 'iosv' }, h('div', { class: 'sv-box' }, h('h2', null, ic ? icon(ic) : null, title), ...kids));
}
/** A settings row: the label (and a short hint) on the left, the control on the right. */
export const row = (label, hint, control) => h('div', { class: 'sv-srow' }, h('div', null, h('b', null, label), hint ? h('div', { class: 'sv-muted sv-small' }, hint) : null), control);
const field = (label, input) => h('label', { class: 'sv-field' }, h('span', null, label), input);
const when = (t) => (t ? new Date(t * 1000).toLocaleDateString() : '');

/** Segmented choices that save at once: [[value, label], ...]. */
export function segmented(choices, current, onPick) {
  const seg = h('div', { class: 'sv-seg', role: 'radiogroup' }, choices.map(([v, l]) => h('button', { type: 'button', class: v === current ? 'on' : '', role: 'radio', 'aria-checked': String(v === current),
    onclick: async (e) => {
      const b = e.currentTarget;
      for (const x of seg.children) { x.classList.toggle('on', x === b); x.setAttribute('aria-checked', String(x === b)); }
      try { await onPick(v); } catch (err) { fail(err); }
    } }, l)));
  return seg;
}
const saveSetting = (body) => api('auth/settings', { json: body }).then(() => toast('Saved'));

// ------------------------------------------------------------------ Settings › Display
/** Appearance: Light, Dark or System, saved with the account (the app applies it with apply(value)). */
export const themeRow = (current, apply) => row('Theme', 'Saved with your account.',
  segmented([['light', 'Light'], ['dark', 'Dark'], ['system', 'System']], current || 'system', async (v) => { apply(v); await saveSetting({ theme: v }); }));
/** Units: Automatic (from the browser's region), Kilometres or Miles, saved with the account. */
export const unitsRow = (current, apply) => row('Units', 'Automatic follows your region.',
  segmented([['auto', 'Automatic'], ['metric', 'Kilometres'], ['imperial', 'Miles']], current || 'auto', async (v) => { apply(v); await saveSetting({ units: v }); }));

// ------------------------------------------------------------------ Settings › Account
/** Display name and email (saved when a field is left), and the password. opts: toast, onSaved(user). */
export async function mountAccount(el, opts = {}) {
  styles(); setToast(opts.toast);
  el.classList.add('iosv');
  const me = await api('auth/me');
  const u = me.user;
  const save = (k) => async (e) => {
    if (e.target.value === (u[k] || '')) return;
    try { const r = await api('auth/me', { method: 'PATCH', json: { [k]: e.target.value } }); Object.assign(u, r.user); toast('Saved'); if (opts.onSaved) opts.onSaved(r.user); } catch (err) { fail(err); }
  };
  const dn = h('input', { class: 'sv-in', value: u.displayName || '', onchange: save('displayName') });
  const em = h('input', { class: 'sv-in', type: 'email', value: u.email || '', onchange: save('email') });
  const cur = h('input', { class: 'sv-in', type: 'password', autocomplete: 'current-password' });
  const nw = h('input', { class: 'sv-in', type: 'password', autocomplete: 'new-password' });
  el.replaceChildren(
    h('div', { class: 'sv-box' }, h('h2', null, icon('person'), 'You'),
      h('p', { class: 'sv-muted sv-small' }, `${u.name} · ${u.suiteAdmin ? 'suite admin' : u.role}. One account for every io app.`),
      h('div', { class: 'sv-grid' }, field('Display name', dn), field('Email (for sign-in at a proxy)', em))),
    h('div', { class: 'sv-box' }, h('h2', null, icon('key'), 'Password'),
      u.passwordless ? h('p', { class: 'sv-muted' }, 'This account signs in with one click and has no password. A suite admin can give it one.')
        : me.viaProxy ? h('p', { class: 'sv-muted' }, 'You signed in at the proxy; change the password there.')
          : [h('div', { class: 'sv-grid' }, field('Current password', cur), field('New password (8 or more)', nw)),
            h('div', { class: 'sv-row' }, h('button', { class: 'sv-btn', onclick: async () => {
              try { await api('auth/password', { json: { current: cur.value, password: nw.value } }); cur.value = nw.value = ''; toast('Password changed; your other sessions are signed out'); } catch (e) { fail(e); }
            } }, 'Change password'))]));
}

// ------------------------------------------------------------------ Settings › Apps and devices
/** The signed-in account's app passwords here: make one (shown once), list, revoke. opts: toast, syncOnly (the label of
 *  the sync-only choice, e.g. 'Calendar apps only (CalDAV)'; offered when the app has sync protocols), onChange(). */
export async function mountAppPasswords(el, opts = {}) {
  styles(); setToast(opts.toast);
  el.classList.add('iosv');
  const me = await api('auth/me');
  if (me.user.passwordless) {
    el.replaceChildren(h('div', { class: 'sv-box' }, h('h2', null, icon('key'), 'App passwords'), h('p', { class: 'sv-muted' }, 'A one-click account cannot have app passwords. A suite admin can give it a password first.')));
    return;
  }
  const label = h('input', { class: 'sv-in', placeholder: 'Name, e.g. Alex’s iPhone', 'aria-label': 'Name' });
  const shown = h('div'), list = h('div');
  let scopes = [''];
  const sync = h('input', { type: 'checkbox', checked: true });
  const scopeText = (s) => (s ? (opts.syncOnly || 'Sync apps only') : 'Everything');
  const draw = async () => {
    const r = await api('auth/app-passwords');
    scopes = r.scopes || [''];
    syncRow.hidden = !(opts.syncOnly && scopes.includes('dav'));
    list.replaceChildren(r.items.length ? h('table', { class: 'sv-t' }, h('tr', null, h('th', null, 'Name'), syncRow.hidden ? null : h('th', null, 'Works for'), h('th', null, 'Made'), h('th', null, 'Last used'), h('th')),
      r.items.map((p) => h('tr', null, h('td', null, p.label), syncRow.hidden ? null : h('td', null, scopeText(p.scope)), h('td', null, when(p.created)), h('td', null, p.lastUsed ? when(p.lastUsed) : 'never'),
        h('td', { style: 'text-align:right' }, h('button', { class: 'sv-btn', onclick: async () => {
          if (!await confirmDialog('Revoke app password', `Revoke “${p.label}”? Whatever uses it stops signing in.`, 'Revoke')) return;
          try { await api(`auth/app-passwords/${p.id}`, { method: 'DELETE' }); draw(); if (opts.onChange) opts.onChange(); } catch (e) { fail(e); }
        } }, 'Revoke'))))) : h('p', { class: 'sv-muted' }, 'No app passwords yet.'));
  };
  const syncRow = h('label', { class: 'sv-check' }, sync, ` ${opts.syncOnly || ''}`);
  el.replaceChildren(h('div', { class: 'sv-box' }, h('h2', null, icon('key'), 'App passwords'),
    h('p', { class: 'sv-muted' }, 'One per app or device, used with your user name instead of your password. Revoke one without touching the others.'),
    h('div', { class: 'sv-row' }, label, h('button', { class: 'sv-btn primary', onclick: async () => {
      try {
        const r = await api('auth/app-passwords', { json: { label: label.value.trim() || 'Device', scope: !syncRow.hidden && sync.checked ? 'dav' : '' } });
        shown.replaceChildren(h('p', null, h('b', null, 'Copy it now, it is shown only once: '), h('code', { class: 'sv-code' }, r.password)));
        label.value = ''; draw(); if (opts.onChange) opts.onChange();
      } catch (e) { fail(e); }
    } }, 'New app password')), syncRow, shown, list));
  await draw();
}
