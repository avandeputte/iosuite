/* ioTasks web app: one module, no build step. The smart lists (Today, Scheduled, All, Completed) and the lists to
   pick in the sidebar; a list of tasks with a box to tick each off, quick add, subtasks under their task; the task form
   (due date and time, repeat, alert, priority, the family members it is for, notes, link); search, import, and
   settings (account, display, apps and devices, lists, and for admins family and server, and for suite admins security
   and global settings), laid out as in the other ioThing apps. */

// ------------------------------------------------------------------ helpers
const $ = (s, el = document) => el.querySelector(s);
/** replaceChildren that leaves out null and false (as h() does) and flattens lists. */
const fill = (el, ...kids) => el.replaceChildren(...kids.flat(9).filter((k) => k != null && k !== false));
/** append with the same manners. */
const put = (el, ...kids) => el.append(...kids.flat(9).filter((k) => k != null && k !== false));
const ICONS = {
  today: 'M19 3h-1V1h-2v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM7 10h5v5H7z',
  event: 'M17 12h-5v5h5v-5zM16 1v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2h-1V1h-2zm3 18H5V8h14v11z',
  inbox: 'M19 3H4.99C3.88 3 3 3.9 3 5v14c0 1.1.88 2 1.99 2H19c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 12h-4c0 1.66-1.35 3-3 3s-3-1.34-3-3H4.99V5H19v10z',
  done: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z',
  list: 'M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z',
  repeat: 'M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z',
  bell: 'M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z',
  flag: 'M14.4 6 14 4H5v17h2v-7h5.6l.4 2h7V6z',
  menuOpen: 'M3 18h13v-2H3v2zm0-5h10v-2H3v2zm0-7v2h13V6H3zm18 9.59L17.42 12 21 8.41 19.59 7l-5 5 5 5L21 15.59z',
  pin: 'M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3z',
  menu: 'M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z',
  search: 'M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z',
  add: 'M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z',
  person: 'M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z',
  people: 'M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z',
  link: 'M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z',
  upload: 'M9 16h6v-6h4l-7-7-7 7h4zm-4 2h14v2H5z',
  download: 'M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z',
  settings: 'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z',
  edit: 'M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a.996.996 0 0 0 0-1.41l-2.34-2.34a.996.996 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z',
  delete: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z',
  close: 'M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z',
  logout: 'M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z',
  copy: 'M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z',
  devices: 'M4 6h18V4H4c-1.1 0-2 .9-2 2v11H0v3h14v-3H4V6zm19 2h-6c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h6c.55 0 1-.45 1-1V9c0-.55-.45-1-1-1zm-1 9h-4v-7h4v7z',
  more: 'M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  check: 'M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z',
  chevR: 'M10 6 8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z',
  update: 'M21 10.12h-6.78l2.74-2.82c-2.73-2.7-7.15-2.8-9.88-.1a6.875 6.875 0 0 0 0 9.79 7.02 7.02 0 0 0 9.88 0C18.32 15.65 19 14.08 19 12.1h2c0 1.98-.88 4.55-2.64 6.29-3.51 3.48-9.21 3.48-12.72 0-3.5-3.47-3.53-9.11-.02-12.58a8.987 8.987 0 0 1 12.65 0L21 3v7.12z',
  tune: 'M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 4v-2H11v2h10zm-6-4h2V7h4V5h-4V3h-2v6z',
  ai: 'M19 9l1.25-2.75L23 5l-2.75-1.25L19 1l-1.25 2.75L15 5l2.75 1.25L19 9zm-7.5.5L9 4 6.5 9.5 1 12l5.5 2.5L9 20l2.5-5.5L17 12l-5.5-2.5zM19 15l-1.25 2.75L15 19l2.75 1.25L19 23l1.25-2.75L23 19l-2.75-1.25L19 15z',
  theme: 'M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.389 5.389 0 0 1-4.4 2.26 5.403 5.403 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z',
  subtask: 'M19 15l-6 6-1.42-1.42L15.17 16H4V4h2v10h9.17l-3.59-3.58L13 9l6 6z',
};
const icon = (n, cls = '') => { const s = document.createElement('span'); s.className = 'ic ' + cls; s.innerHTML = `<svg viewBox="0 0 24 24"><path d="${ICONS[n] || ''}"/></svg>`; return s; };

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
  const r = await fetch(path, o);
  if (r.status === 401 && !path.startsWith('/api/auth') && path !== '/api/status') { showSignIn(); throw new Error('Sign in first'); }
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch { /* not JSON */ }
    throw new Error(msg || `Error ${r.status}`);
  }
  const ct = r.headers.get('content-type') || '';
  return ct.includes('json') ? r.json() : r.text();
}

let toastTimer;
function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 3500);
}
const fail = (e) => toast(e.message || String(e));

function dialog(title, body, buttons, cls = '') {
  return new Promise((resolve) => {
    const back = h('div', { class: 'dialog-back' });
    const close = (v) => { back.remove(); resolve(v); };
    back.addEventListener('click', (e) => { if (e.target === back) close(null); });
    const btns = (buttons || [{ label: 'OK', value: true, primary: true }]).map((b) =>
      h('button', { class: `pillbtn noic ${b.primary ? 'primary' : ''} ${b.danger ? 'danger' : ''}`, onclick: () => close(typeof b.value === 'function' ? b.value() : b.value) }, b.label));
    back.append(h('div', { class: `dialog ${cls}`, role: 'dialog' }, h('h2', null, title), body, h('div', { class: 'btns' }, btns)));
    document.body.append(back);
    const f = back.querySelector('input,select,textarea'); if (f) f.focus();
  });
}
const confirmDialog = (title, text, ok = 'OK', danger = false) => dialog(title, h('p', null, text), [{ label: 'Cancel', value: false }, { label: ok, value: true, primary: !danger, danger }]);
function closeDialogs() { document.querySelectorAll('.dialog-back').forEach((d) => d.remove()); }

const hue = (s) => { let x = 0; for (const c of s || '') x = (x * 31 + c.charCodeAt(0)) % 360; return x; };
const initials = (fn) => { const p = (fn || '?').trim().split(/\s+/); return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase(); };
async function copyText(t) { try { await navigator.clipboard.writeText(t); toast('Copied'); } catch { toast(t); } }
const copyRow = (v) => h('div', { class: 'copy' }, h('code', null, v), h('button', { class: 'iconbtn', title: 'Copy', onclick: () => copyText(v) }, icon('copy', 's')));
const safeUrl = (u) => /^(https?:\/\/|mailto:)/i.test(u || '');  // a link that is a link (never javascript:)
const store = { get: (k) => { try { return localStorage.getItem(`iotasks.${k}`); } catch { return null; } }, set: (k, v) => { try { localStorage.setItem(`iotasks.${k}`, v); } catch { /* private mode */ } } };

// ------------------------------------------------------------------ dates
const pad2 = (n) => String(n).padStart(2, '0');
const ymd = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
const hm = (d) => `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
const parseDay = (s) => { const [y, m, d] = s.slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d); };
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const dayStart = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const sameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
const fmtTime = (d) => d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
const LOCAL_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
const TZQ = `tz=${encodeURIComponent(LOCAL_TZ)}`;  // whose "today" the server counts with
const DOW = (i, style = 'short') => new Date(2026, 1, 1 + i).toLocaleDateString([], { weekday: style }); // 1 Feb 2026 is a Sunday
const RDAY = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'];

/** A task's due as a Date (all-day: local midnight), or null. */
const dueOf = (t) => (t.due ? (t.dueAllDay ? parseDay(t.due) : new Date(t.due)) : null);
/** Open and past its time (a timed task) or its day (an all-day one). */
function isLate(t) {
  const d = dueOf(t);
  if (!d || t.done) return false;
  return t.dueAllDay ? d < dayStart(new Date()) : d < new Date();
}
/** A day in words: Today, Tomorrow, Yesterday, a weekday this week, else the date. */
function dayWords(d) {
  const t = dayStart(new Date()), n = Math.round((dayStart(d) - t) / 864e5);
  if (n === 0) return 'Today';
  if (n === 1) return 'Tomorrow';
  if (n === -1) return 'Yesterday';
  if (n > 1 && n < 7) return d.toLocaleDateString([], { weekday: 'long' });
  return d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric', year: d.getFullYear() !== t.getFullYear() ? 'numeric' : undefined });
}
const dueText = (t) => { const d = dueOf(t); return d ? dayWords(d) + (t.dueAllDay ? '' : `, ${fmtTime(d)}`) : ''; };
const ordinal = (n) => ({ 1: 'first', 2: 'second', 3: 'third', 4: 'fourth', 5: 'fifth', '-1': 'last' })[n] || `${n}th`;

/** A repeat rule (RRULE) in words. */
function describeRule(rule, day) {
  if (!rule) return '';
  const p = Object.fromEntries(rule.split(';').map((x) => x.split('=')));
  const n = +(p.INTERVAL || 1);
  const unit = { DAILY: 'day', WEEKLY: 'week', MONTHLY: 'month', YEARLY: 'year', HOURLY: 'hour' }[p.FREQ] || (p.FREQ || '').toLowerCase();
  let s = n === 1 ? `Every ${unit}` : `Every ${n} ${unit}s`;
  if (p.FREQ === 'DAILY' && n === 1) s = 'Daily';
  if (p.FREQ === 'WEEKLY' && p.BYDAY) {
    const days = p.BYDAY.split(',');
    if (days.length === 5 && ['MO', 'TU', 'WE', 'TH', 'FR'].every((d) => days.includes(d))) s = n === 1 ? 'Every weekday' : `${s} on weekdays`;
    else s += ' on ' + days.map((d) => DOW(RDAY.indexOf(d), 'long')).join(', ');
  }
  if (p.FREQ === 'MONTHLY') {
    if (p.BYDAY) { const m = p.BYDAY.match(/^(-?\d)?([A-Z]{2})$/); if (m) s += ` on the ${ordinal(m[1] || 1)} ${DOW(RDAY.indexOf(m[2]), 'long')}`; }
    else if (p.BYMONTHDAY) s += ` on day ${p.BYMONTHDAY}`;
    else if (day) s += ` on day ${day.getDate()}`;
  }
  if (p.COUNT) s += `, ${p.COUNT} more times`;
  if (p.UNTIL) { const u = p.UNTIL; s += `, until ${parseDay(`${u.slice(0, 4)}-${u.slice(4, 6)}-${u.slice(6, 8)}`).toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' })}`; }
  return s;
}

// ------------------------------------------------------------------ state
const S = { status: {}, user: null, suite: [], settings: {}, lists: [], counts: {}, members: [], who: new Set(), q: '' };
const listOf = (id) => S.lists.find((c) => c.id === id) || {};
const colorOf = (id) => listOf(id).color || 'var(--brand)';
const writable = () => S.lists.filter((c) => c.writable);
/** Where a new task goes when no list is open: the one chosen in Settings › Display, else your own first list. */
function defaultList() {
  const w = writable();
  return w.find((c) => c.id === +S.settings.defaultList) || w.find((c) => c.mine) || w[0] || null;
}
const memberOf = (id) => S.members.find((m) => m.id === id);
const MEMBER_COLORS = ['#1e8e3e', '#e0426a', '#1a73e8', '#e8710a', '#8e44d6', '#0b8a9e', '#b5452f', '#4b53c7', '#e8a100', '#5f6b7a'];
/** Each family member gets a colour of their own (by their place in the family list, so two never look alike). */
const memberColor = (m) => MEMBER_COLORS[Math.max(0, S.members.findIndex((x) => x.id === m.id)) % MEMBER_COLORS.length];
const memberBadge = (m) => h('span', { class: 'mem', title: m.displayName, style: { '--mc': memberColor(m) } }, initials(m.displayName));
function toggleWho(id) {
  if (id == null) S.who.clear(); else if (S.who.has(id)) S.who.delete(id); else S.who.add(id);
  saveSettings({ memberFilter: [...S.who].join(',') });
  onRoute();
}

async function loadLists() {
  const [lists, fam, counts] = await Promise.all([api(`/api/lists?${TZQ}`), api('/api/members').catch(() => ({ items: S.members })), api(`/api/counts?${TZQ}`).catch(() => S.counts)]);
  S.lists = lists.items;
  S.members = fam.items || [];
  S.counts = counts || {};
  for (const id of [...S.who]) if (!memberOf(id)) S.who.delete(id);
  $('#newbtn').hidden = !writable().length;
  drawNav();
}
async function saveSettings(changes) {
  Object.assign(S.settings, changes);
  try { await api('/api/auth/settings', { method: 'POST', json: changes }); } catch { /* kept for this visit */ }
}

// ------------------------------------------------------------------ chrome
function drawUser() {
  const m = $('#usermenu'); m.replaceChildren();
  if (!S.user) return;
  const btn = h('button', { class: 'avatarbtn', title: S.user.displayName, style: { background: `hsl(${hue(S.user.name)} 45% 45%)` } }, initials(S.user.displayName));
  let menu = null;
  const closeMenu = () => { if (menu) { menu.remove(); menu = null; document.removeEventListener('click', outside); } };
  const outside = (e) => { if (menu && !menu.contains(e.target) && e.target !== btn) closeMenu(); };
  btn.onclick = () => {
    if (menu) return closeMenu();
    menu = h('div', { class: 'menu' },
      h('div', { class: 'who' }, h('b', null, S.user.displayName), h('div', { class: 'muted small' }, `${S.user.name} · ${S.user.role}`)),
      h('a', { class: 'mi', href: '#/settings', onclick: closeMenu }, icon('settings', 's'), 'Settings'),
      h('button', { class: 'mi', onclick: async () => { const r = await api('/api/auth/logout', { method: 'POST' }); if (r && r.cloudflareLogout) location.href = r.cloudflareLogout; else location.reload(); } }, icon('logout', 's'), 'Sign out'));
    m.append(menu);
    setTimeout(() => document.addEventListener('click', outside), 0);
  };
  m.append(btn);
}
/* The suite (iosuite-shared's suite_apps): when other ioThing apps are registered, the app mark top left (in the sidebar; in
   the top bar on a phone) opens a menu of them, each a link to that app. Alone, the mark stays the link to Today. */
async function loadSuite() {
  try {
    const r = await api('/api/auth/suite');
    S.suite = (r.items || []).filter((a) => a.app !== r.app && a.url);
  } catch { S.suite = []; }
  const b = $('#suitebtn');
  if (b) { b.hidden = !S.suite.length; b.onclick = () => toggleSuite(b); }
  if (!S.suite.length) closeSuite();
  drawNav();
}
let suitePop = null;
function closeSuite() {
  if (!suitePop) return;
  suitePop.remove(); suitePop = null;
  document.removeEventListener('click', suiteOutside, true);
  document.removeEventListener('keydown', suiteKey);
  removeEventListener('resize', closeSuite);
}
function suiteOutside(e) { if (suitePop && !suitePop.contains(e.target) && !e.target.closest('.suitebtn')) closeSuite(); }
function suiteKey(e) { if (e.key === 'Escape') closeSuite(); }
function appTile(a) {
  const mark = (a.name || a.app).replace(/^io(?=[A-Z])/, '').slice(0, 1).toUpperCase();
  const fallback = () => h('span', { class: 'appic fb', style: { background: a.color || 'var(--brand)' } }, mark);
  const ic = a.icon ? h('img', { class: 'appic', src: a.icon, alt: '', onerror: (e) => e.currentTarget.replaceWith(fallback()) }) : fallback();
  return h('a', { class: 'apptile', href: a.url, role: 'menuitem', title: a.description || a.name, onclick: closeSuite },
    ic, h('span', { class: 'appnm' }, a.name || a.app));
}
function toggleSuite(btn) {
  if (suitePop) { closeSuite(); return; }
  if (!S.suite.length) return;
  // the apps, then the admin tools in a section of their own: the server sends those to their admins only
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
function applyTheme(choice) {
  if (choice) store.set('theme', choice);
  const t = choice || store.get('theme') || 'system';
  if (t === 'system') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
}

/* The sidebar, as in the other io apps: the name on top, the smart lists, the shared lists, the family, your own lists,
   Settings at the foot. It docks beside the page on a wide screen unless its button put it away (remembered); otherwise
   it slides over the page. Phones get a bottom bar instead. */
const DOCK_MIN = 1100;
const SMART = { today: ['Today', 'today', '--c-blue'], scheduled: ['Scheduled', 'event', '--c-rose'], all: ['All', 'inbox', '--c-slate'], done: ['Completed', 'done', '--c-green'] };
function drawNav() {
  const nav = $('#nav'); const r = route();
  const link = (v, href, ic, label, n, on, hueVar) => h('a', { href, 'data-v': v, class: on ? 'on' : null, style: hueVar ? { '--hue': `var(${hueVar})` } : null },
    icon(ic), h('span', { class: 'nl' }, label), n ? h('span', { class: 'n' }, n) : null);
  const sec = (label, btn) => h('div', { class: 'navsec' }, h('span', null, label), btn || null);
  const listRow = (c) => h('a', { href: `#/list/${c.id}`, 'data-v': 'list', class: r.view === 'list' && r.id === c.id ? 'on' : null, style: { '--hue': c.color } },
    h('span', { class: 'ldot' }), h('span', { class: 'nl' }, c.name),
    h('span', { class: `n ${c.overdue ? 'late' : ''}`, title: c.overdue ? `${c.overdue} overdue` : null }, c.count || ''));
  const whoRow = (m) => h('a', { href: '#', 'data-v': 'who', class: `who ${S.who.has(m.id) ? 'picked' : ''}`, style: { '--mc': memberColor(m) },
    title: S.who.has(m.id) ? `Stop showing only ${m.displayName}'s tasks` : `Show only ${m.displayName}'s tasks`,
    onclick: (e) => { e.preventDefault(); toggleWho(m.id); } }, memberBadge(m), h('span', { class: 'nl' }, m.displayName));
  const shared = S.lists.filter((c) => c.shared), mine = S.lists.filter((c) => !c.shared);
  const brandName = () => [h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Tasks')];
  nav.replaceChildren(...[
    h('div', { class: 'navhead' },
      S.suite.length
        ? h('div', { class: 'brand' },
          h('button', { class: 'suitebtn', title: 'ioThing apps', 'aria-label': 'ioThing apps', 'aria-haspopup': 'menu', onclick: (e) => toggleSuite(e.currentTarget) },
            h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' })),
          h('a', { class: 'brand-name', href: '#/', title: 'Today' }, brandName()))
        : h('a', { class: 'brand', href: '#/', title: 'Today' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }),
          h('span', { class: 'brand-name' }, brandName())),
      h('button', { id: 'sidebtn', class: 'iconbtn', onclick: sidebarButton })),
    Object.entries(SMART).map(([k, [label, ic, hv]]) => link(k, `#/${k}`, ic, label, k === 'done' ? null : (k === 'today' ? S.counts.today : S.counts[k]) || null, r.view === k, hv)),
    h('button', { class: 'navmore', 'data-v': 'more', title: 'More', onclick: moreSheet }, icon('more'), h('span', { class: 'nl' }, 'More')),
    h('div', { class: 'navgap' }),
    sec('Shared', S.user.role !== 'viewer' ? h('button', { class: 'iconbtn', title: 'New shared list', onclick: () => newList(true) }, icon('add', 's')) : null),
    shared.map(listRow),
    S.members.length > 1 ? [h('div', { class: 'navgap' }),
      sec('Family', S.who.size ? h('button', { class: 'pillbtn noic tiny', title: 'Show everyone again', onclick: () => toggleWho(null) }, 'Everyone') : null),
      S.members.map(whoRow)] : null,
    h('div', { class: 'navgap' }),
    sec('Mine', h('button', { class: 'iconbtn', title: 'New private list', onclick: () => newList(false) }, icon('add', 's'))),
    mine.map(listRow),
    h('div', { class: 'navgap' }), sec('Manage'),
    writable().length ? link('import', '#/import', 'upload', 'Import', null, r.view === 'import', '--c-teal') : null,
    h('div', { class: 'navfoot' }, link('settings', '#/settings', 'settings', 'Settings', null, r.view === 'settings')),
  ].flat(3).filter(Boolean));
  applySidebar();
  $('.navmore')?.classList.toggle('on', ['list', 'import', 'settings', 'search'].includes(r.view));
}
function applySidebar() {
  const body = document.body, btn = $('#sidebtn');
  const docked = innerWidth >= DOCK_MIN && store.get('sidebar') !== '0';
  body.classList.toggle('side-docked', docked);
  if (docked) closeNav();
  if (!btn) return;
  const [ic, title] = docked ? ['menuOpen', 'Hide the sidebar'] : innerWidth >= DOCK_MIN ? ['pin', 'Keep the sidebar open'] : ['close', 'Close the sidebar'];
  btn.replaceChildren(icon(ic)); btn.title = title; btn.setAttribute('aria-label', title);
}
function sidebarButton() {
  if (document.body.classList.contains('side-docked')) store.set('sidebar', '0');
  else if (innerWidth >= DOCK_MIN) store.set('sidebar', '1');
  else { closeNav(); return; }
  applySidebar();
}
function openNav() { document.body.classList.add('side-open'); $('#navscrim').hidden = false; }
function closeNav() { document.body.classList.remove('side-open'); $('#navscrim').hidden = true; }
/** Phones: what the bottom bar has no room for (the lists, the family filter, import, settings). */
function moreSheet() {
  const r = route();
  const tile = (href, ic, label, hueV, on, click) => h('a', { href, class: on ? 'on' : null, style: { '--hue': hueV }, onclick: click || null }, h('span', { class: 'sic' }, icon(ic)), h('span', null, label));
  const grid = h('div', { class: 'sheetgrid' },
    S.lists.map((c) => tile(`#/list/${c.id}`, 'list', c.name, c.color, r.view === 'list' && r.id === c.id)),
    S.members.length > 1 ? S.members.map((m) => tile('#', 'person', S.who.has(m.id) ? `Only ${m.displayName}` : m.displayName, memberColor(m), S.who.has(m.id),
      (e) => { e.preventDefault(); e.stopPropagation(); closeDialogs(); toggleWho(m.id); moreSheet(); })) : null,
    writable().length ? tile('#/import', 'upload', 'Import', 'var(--c-teal)', r.view === 'import') : null,
    tile('#/settings', 'settings', 'Settings', 'var(--c-slate)', r.view === 'settings'));
  const p = dialog('More', grid, [{ label: 'Close', value: null }]);
  grid.addEventListener('click', (e) => { const a = e.target.closest('a'); if (a && a.getAttribute('href') !== '#') closeDialogs(); });
  return p;
}

const SWATCHES = ['#146b5e', '#1a73e8', '#e0426a', '#e8710a', '#8e44d6', '#1e8e3e', '#e8a100', '#b5452f', '#4b53c7', '#5f6b7a'];
function colorPicker(value, onPick) {
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
async function newList(shared) {
  const name = h('input', { class: 't', placeholder: shared ? 'Name, e.g. Groceries or Chores' : 'Name, e.g. Work' });
  const col = colorPicker(SWATCHES[S.lists.length % SWATCHES.length]);
  const body = h('div', { style: { display: 'grid', gap: '12px' } }, name, col,
    h('p', { class: 'muted small', style: { margin: 0 } }, shared ? 'Everyone in the family sees it and ticks tasks off; editors change it.' : 'Only you see it.'));
  if (!await dialog(shared ? 'New shared list' : 'New private list', body, [{ label: 'Cancel', value: false }, { label: 'Create', value: true, primary: true }])) return;
  try {
    const r = await api('/api/lists', { method: 'POST', json: { name: name.value, shared, color: col.get() } });
    await loadLists();
    location.hash = `#/list/${r.list.id}`;
  } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ routing
function route() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [path, query] = raw.split('?');
  const p = path.split('/').map(decodeURIComponent);
  const qs = new URLSearchParams(query || '');
  const [a, b] = p;
  if (!a) return { view: S.settings.startView || 'today' };
  if (SMART[a]) return { view: a };
  if (a === 'list' && b) return { view: 'list', id: +b };
  if (a === 'task' && b) return { view: 'task', id: +b };
  if (a === 'new') return { view: 'new', list: +qs.get('list') || null, parent: +qs.get('parent') || null };
  if (a === 'search') return { view: 'search', q: b || '' };
  if (a === 'import') return { view: 'import', list: +qs.get('list') || null };
  if (a === 'settings') return { view: 'settings', tab: b || 'account', sub: p[2] };
  return { view: 'today' };
}
const TASK_VIEWS = ['today', 'scheduled', 'all', 'done', 'list', 'search'];

async function onRoute() {
  const r = route();
  const main = $('#main');
  try {
    const page = h('div', { class: 'page' });
    main.replaceChildren(page);
    if (TASK_VIEWS.includes(r.view)) await drawTasks(page, r);
    else await ({ task: showTaskPage, new: showTaskPage, import: showImport, settings: showSettings })[r.view](page, r);
  } catch (e) { fail(e); }
  drawNav();
}
/** Draw the open view again, keeping where the page was scrolled to. */
async function redraw() {
  const r = route();
  if (!TASK_VIEWS.includes(r.view)) return;
  const top = $('#main').scrollTop;
  const page = h('div', { class: 'page' });
  try { await drawTasks(page, r); } catch (e) { fail(e); return; }
  $('#main').replaceChildren(page);
  $('#main').scrollTop = top;
}
async function refresh() { await loadLists(); await redraw(); }

// ------------------------------------------------------------------ the task lists
const showDone = (lid) => (S.settings.showCompleted || '').split(',').includes(String(lid));
function setShowDone(lid, on) {
  const s = new Set((S.settings.showCompleted || '').split(',').filter(Boolean));
  if (on) s.add(String(lid)); else s.delete(String(lid));
  saveSettings({ showCompleted: [...s].join(',') });
}

/** The tasks the view shows, from the server: [rows, title, colour, the list (list view only)]. */
async function fetchTasks(r) {
  const who = `&${TZQ}${S.who.size ? `&member=${[...S.who].join(',')}` : ''}`;
  if (r.view === 'list') {
    const c = listOf(r.id);
    if (!c.id) throw new Error('That list is not here (any more)');
    const items = (await api(`/api/tasks?list=${c.id}&status=${showDone(c.id) ? 'all' : 'open'}&limit=2000${who}`)).items;
    return [items, c.name, c.color, c];
  }
  if (r.view === 'search') {
    S.q = r.q;
    if ($('#q').value !== r.q) $('#q').value = r.q;
    if (!r.q) return [[], 'Search', null, null];
    return [(await api(`/api/tasks?q=${encodeURIComponent(r.q)}&status=all&limit=300${who}`)).items, `“${r.q}”`, null, null];
  }
  const qs = { today: 'status=open&due=today', scheduled: 'status=open&due=scheduled', all: 'status=open', done: 'status=done&limit=300' }[r.view];
  return [(await api(`/api/tasks?${qs}${who}`)).items, SMART[r.view][0], `var(${SMART[r.view][2]})`, null];
}

/** Subtasks right under their task (indented), the rest in the server's order. */
function nest(items) {
  const byUid = new Map(items.map((t) => [`${t.listId}|${t.uid}`, t]));
  const kids = new Map(), out = [];
  for (const t of items) {
    const k = t.parent && byUid.has(`${t.listId}|${t.parent}`) ? `${t.listId}|${t.parent}` : null;
    if (k) { if (!kids.has(k)) kids.set(k, []); kids.get(k).push(t); } else out.push(t);
  }
  const flat = [];
  const add = (t, depth) => { flat.push([t, depth]); for (const c of kids.get(`${t.listId}|${t.uid}`) || []) add(c, depth + 1); };
  out.forEach((t) => add(t, 0));
  return flat;
}

async function drawTasks(page, r) {
  const [items, title, color, list] = await fetchTasks(r);
  const smart = r.view !== 'list';
  const head = h('div', { class: 'pagehead tasks-head', style: color ? { '--c': color } : null },
    h('h1', null, title), h('span', { class: 'count' }, items.filter((t) => !t.done).length || ''), h('span', { class: 'grow' }),
    S.who.size ? h('button', { class: 'pillbtn noic', title: 'Show everyone’s tasks again', onclick: () => toggleWho(null) },
      `Only ${[...S.who].map(memberOf).filter(Boolean).map((m) => m.displayName).join(', ')}`) : null,
    list ? listMenu(list) : null);
  page.classList.add('taskpage');
  page.append(head);
  if (r.view === 'search' && !r.q) { page.append(h('p', { class: 'muted' }, 'Type in the search box: words from the title or the notes.')); return; }
  const canAdd = list ? list.writable : (['today', 'all', 'scheduled'].includes(r.view) && !!defaultList());
  const rows = h('div', { class: 'tasks' });
  const section = (label, cls) => h('div', { class: `tsec ${cls || ''}` }, label);
  if (r.view === 'list') {
    nest(items).forEach(([t, depth]) => rows.append(taskRow(t, { depth })));
  } else if (r.view === 'today') {
    const late = items.filter(isLate), now = items.filter((t) => !isLate(t));
    if (late.length) put(rows, section('Overdue', 'late'), late.map((t) => taskRow(t, { showList: true })));
    if (now.length) put(rows, late.length ? section('Today') : null, now.map((t) => taskRow(t, { showList: true, noDay: true })));
  } else if (r.view === 'scheduled') {
    let last = null;
    for (const t of items) {
      const d = dueOf(t), label = isLate(t) ? 'Overdue' : dayWords(d);
      if (label !== last) { rows.append(section(label, label === 'Overdue' ? 'late' : '')); last = label; }
      rows.append(taskRow(t, { showList: true, noDay: label !== 'Overdue' }));
    }
  } else {
    // All, Completed and search: grouped by list, in the sidebar's order
    for (const c of S.lists) {
      const mine = items.filter((t) => t.listId === c.id);
      if (!mine.length) continue;
      rows.append(h('div', { class: 'tsec', style: { '--c': c.color } }, h('a', { href: `#/list/${c.id}` }, c.name)));
      (r.view === 'all' ? nest(mine) : mine.map((t) => [t, 0])).forEach(([t, depth]) => rows.append(taskRow(t, { depth })));
    }
  }
  if (canAdd) page.append(quickAdd(r, list));
  page.append(rows);
  if (!items.length) page.append(h('div', { class: 'empty' }, icon(r.view === 'search' ? 'search' : 'done'),
    h('p', null, r.view === 'search' ? 'Nothing matches.' : r.view === 'done' ? 'Nothing ticked off yet.' : list && showDone(list.id) ? 'No tasks.' : 'All done.')));
  if (list && !showDone(list.id)) {
    page.append(h('p', { class: 'center' }, h('button', { class: 'pillbtn noic', onclick: () => { setShowDone(list.id, true); redraw(); } }, 'Show completed')));
  } else if (list && items.some((t) => t.done)) {
    page.append(h('p', { class: 'center' }, h('button', { class: 'pillbtn noic', onclick: () => { setShowDone(list.id, false); redraw(); } }, 'Hide completed'),
      list.writable ? [' ', h('button', { class: 'pillbtn noic danger', onclick: () => clearCompleted(list) }, 'Clear completed')] : null));
  }
}

/** The ⋯ menu of a list: show completed, export, import, clear completed, the list's settings. */
function listMenu(c) {
  const btn = h('button', { class: 'iconbtn', title: 'More', 'aria-haspopup': 'menu' }, icon('more'));
  let menu = null;
  const close = () => { if (menu) { menu.remove(); menu = null; document.removeEventListener('click', outside); } };
  const outside = (e) => { if (menu && !menu.contains(e.target) && !btn.contains(e.target)) close(); };
  btn.onclick = () => {
    if (menu) return close();
    const on = showDone(c.id);
    menu = h('div', { class: 'menu', style: { top: '44px' } },
      h('button', { class: 'mi', onclick: () => { close(); setShowDone(c.id, !on); redraw(); } }, icon('done', 's'), on ? 'Hide completed' : 'Show completed'),
      c.writable ? h('button', { class: 'mi', onclick: () => { close(); clearCompleted(c); } }, icon('delete', 's'), 'Clear completed') : null,
      h('a', { class: 'mi', href: `/api/lists/${c.id}/export`, onclick: close }, icon('download', 's'), 'Export (.ics)'),
      c.writable ? h('a', { class: 'mi', href: `#/import?list=${c.id}`, onclick: close }, icon('upload', 's'), 'Import') : null,
      h('a', { class: 'mi', href: `#/settings/lists/${c.id}`, onclick: close }, icon('settings', 's'), 'List settings'));
    btn.parentElement.style.position = 'relative';
    btn.after(menu);
    setTimeout(() => document.addEventListener('click', outside), 0);
  };
  return btn;
}
async function clearCompleted(c) {
  if (!await confirmDialog('Clear completed', `Delete the completed tasks of ${c.name}? Apps that sync the list lose them too.`, 'Delete', true)) return;
  try { const r = await api(`/api/lists/${c.id}/clear-completed`, { method: 'POST' }); toast(`${r.deleted} deleted`); await refresh(); } catch (e) { fail(e); }
}

/** The "New task" line on top of a list: Enter adds it and leaves the line ready for the next one. On Today and
    Scheduled a new task is due today. */
function quickAdd(r, list) {
  const target = list || defaultList();
  const input = h('input', { class: 'qadd', id: 'qadd', placeholder: list ? `New task in ${list.name}` : `New task (${target.name}${['today', 'scheduled'].includes(r.view) ? ', due today' : ''})`,
    autocomplete: 'off', enterkeyhint: 'done', 'aria-label': 'New task' });
  input.addEventListener('keydown', async (e) => {
    if (e.key !== 'Enter' || !input.value.trim()) return;
    e.preventDefault();
    const data = { title: input.value.trim(), listId: target.id };
    if (['today', 'scheduled'].includes(r.view)) data.due = ymd(new Date());
    if (S.who.size) data.members = [...S.who];
    input.disabled = true;
    try { await api('/api/tasks', { method: 'POST', json: data }); input.value = ''; await refresh(); } catch (err) { fail(err); }
    input.disabled = false;
    $('#qadd')?.focus();
  });
  return h('div', { class: 'qrow', style: { '--c': target.color } }, h('span', { class: 'tick ghost' }, icon('add', 's')), input,
    h('button', { class: 'iconbtn', title: 'More details', onclick: () => { location.hash = `#/new?list=${target.id}`; } }, icon('edit', 's')));
}

const PRIO_MARK = { high: '!!!', medium: '!!', low: '!' };
function taskRow(t, o = {}) {
  const c = listOf(t.listId), canTick = !!c.writable;
  const tick = h('button', { class: `tick ${t.done ? 'on' : ''}`, style: { '--c': c.color || 'var(--brand)' }, title: t.done ? 'Not done after all' : 'Done', 'aria-pressed': t.done ? 'true' : 'false', disabled: canTick ? null : true });
  tick.innerHTML = `<svg viewBox="0 0 24 24"><path d="${ICONS.check}"/></svg>`;
  const late = isLate(t);
  const meta = [
    t.due && !(o.noDay && t.dueAllDay) ? h('span', { class: late ? 'late' : '' }, o.noDay ? fmtTime(dueOf(t)) : dueText(t)) : null,
    t.rrule ? h('span', { title: describeRule(t.rrule, dueOf(t)) }, icon('repeat', 'xs')) : null,
    t.alarms && t.alarms.length && !t.done ? h('span', { title: t.alarms.map((a) => new Date(a).toLocaleString()).join('\n') }, icon('bell', 'xs')) : null,
    o.showList ? h('span', { class: 'lname', style: { '--c': c.color } }, c.name) : null,
    t.subtasks && t.subtasks.total ? h('span', null, icon('subtask', 'xs'), `${t.subtasks.total - t.subtasks.open}/${t.subtasks.total}`) : null,
    t.url && safeUrl(t.url) ? h('a', { href: t.url, target: '_blank', rel: 'noopener', onclick: (e) => e.stopPropagation(), title: t.url }, icon('link', 'xs')) : null,
    t.done && t.completedAt ? h('span', null, `Done ${dayWords(new Date(t.completedAt)).toLowerCase().replace(/^(mon|tue|wed|thu|fri|sat|sun)/i, (x) => x[0].toUpperCase() + x.slice(1))}`) : null,
  ].filter(Boolean);
  const row = h('div', { class: `trow ${t.done ? 'done' : ''}`, style: { '--depth': o.depth || 0 }, 'data-id': t.id },
    tick,
    h('div', { class: 'tbody', onclick: () => openTask(t.id) },
      h('div', { class: 'ttl' }, t.priority ? h('span', { class: 'prio' }, PRIO_MARK[t.priority] + ' ') : null, t.title || '(no title)'),
      t.notes ? h('div', { class: 'tnotes' }, t.notes) : null,
      meta.length ? h('div', { class: 'tmeta' }, meta) : null),
    (t.members || []).map((m) => memberOf(m.id) || m).map(memberBadge),
    h('button', { class: 'iconbtn info', title: 'Details', onclick: () => openTask(t.id) }, icon('chevR', 's')));
  tick.onclick = async () => {
    const done = !t.done;
    tick.classList.toggle('on', done); row.classList.toggle('done', done);
    try {
      const res = await api(`/api/tasks/${t.id}/complete`, { method: 'POST', json: { done } });
      if (res.moved) toast(`Done. Next: ${dueText(res) || 'again'}`);
      // a moment to see the tick before the row leaves a list of open tasks
      setTimeout(() => refresh().catch(fail), done && !res.moved ? 700 : 0);
    } catch (e) { tick.classList.toggle('on', !done); row.classList.toggle('done', !done); fail(e); }
  };
  return row;
}

// ------------------------------------------------------------------ one task: the form
const TIMED_ALERTS = [[0, 'At the time'], [5, '5 minutes before'], [15, '15 minutes before'], [30, '30 minutes before'], [60, '1 hour before'], [120, '2 hours before'], [1440, '1 day before']];
const ALLDAY_ALERTS = [[-540, 'On the day at 9:00'], [900, 'The day before at 9:00'], [9540, 'A week before at 9:00']];
const REPEATS = [['', 'Never'], ['FREQ=DAILY', 'Daily'], ['FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR', 'Weekdays'], ['FREQ=WEEKLY', 'Weekly'], ['FREQ=WEEKLY;INTERVAL=2', 'Every 2 weeks'], ['FREQ=MONTHLY', 'Monthly'], ['FREQ=YEARLY', 'Yearly']];

/** Wide screens: the task opens in a sheet over the list; phones: as a page of its own. */
function openTask(id) {
  if (innerWidth < 700) { location.hash = `#/task/${id}`; return; }
  const back = h('div', { class: 'dialog-back' });
  const box = h('div', { class: 'dialog wide taskdlg', role: 'dialog' });
  back.append(box);
  back.addEventListener('click', (e) => { if (e.target === back) back.remove(); });
  document.body.append(back);
  taskForm(box, { id }, () => { back.remove(); refresh().catch(fail); }).catch((e) => { back.remove(); fail(e); });
}
async function showTaskPage(page, r) {
  page.classList.add('form');
  const backTo = () => { if (history.length > 1) history.back(); else location.hash = '#/'; };
  await taskForm(page, r.view === 'task' ? { id: r.id } : { list: r.list, parent: r.parent }, backTo);
}

/** The task form: everything a task has, saved with Save (or Enter in the title). opts: {id} or {list, parent}. */
async function taskForm(el, opts, done) {
  const t = opts.id ? await api(`/api/tasks/${opts.id}`) : null;
  const lid = t ? t.listId : (opts.list || defaultList()?.id);
  const c = listOf(lid);
  const ro = t ? !c.writable : false;
  const parent = !t && opts.parent ? await api(`/api/tasks/${opts.parent}`).catch(() => null) : null;
  const dd = t ? dueOf(t) : null;

  const title = h('input', { class: 't big', value: t ? t.title : '', placeholder: 'Title', disabled: ro || null });
  const notes = h('textarea', { class: 't', placeholder: 'Notes', disabled: ro || null }, t && t.notes ? t.notes : '');
  const list = h('select', { class: 't', disabled: ro || (parent ? true : null) },
    writable().concat(ro ? [c] : []).map((x) => h('option', { value: x.id, selected: x.id === lid ? true : null }, `${x.name}${x.shared ? ' (shared)' : ''}`)));
  const hasDue = h('input', { type: 'checkbox', checked: !!dd, disabled: ro || null });
  const date = h('input', { class: 't', type: 'date', value: ymd(dd || new Date()), disabled: ro || null });
  const hasTime = h('input', { type: 'checkbox', checked: !!(dd && !t.dueAllDay), disabled: ro || null });
  const time = h('input', { class: 't', type: 'time', value: dd && !t.dueAllDay ? hm(dd) : '09:00', disabled: ro || null });
  const repeat = h('select', { class: 't', disabled: ro || null });
  const alert = h('select', { class: 't', disabled: ro || null });
  const prio = h('select', { class: 't', disabled: ro || null }, [['', 'None'], ['low', 'Low'], ['medium', 'Medium'], ['high', 'High']].map(([v, l]) => h('option', { value: v, selected: (t ? t.priority || '' : '') === v ? true : null }, l)));
  const url = h('input', { class: 't', type: 'url', value: t && t.url ? t.url : '', placeholder: 'https://…', disabled: ro || null });
  const picked = new Set(t ? (t.members || []).map((m) => m.id) : [...S.who]);

  // repeat: the usual ones, and the task's own rule when it is another
  const curRule = t && t.rrule ? t.rrule : '';
  const reps = REPEATS.slice();
  if (curRule && !reps.some(([v]) => v === curRule)) reps.push([curRule, describeRule(curRule, dd)]);
  fill(repeat, reps.map(([v, l]) => h('option', { value: v, selected: v === curRule ? true : null }, l)));
  // alert: minutes before the due time (all-day: before its midnight), worked out from the task's first alert
  const alertMins = () => {
    if (!t || !t.alarms || !t.alarms.length || !dd) return null;
    return Math.round((dd - new Date(t.alarms[0])) / 6e4);
  };
  const drawAlerts = (keep) => {
    const opts2 = hasTime.checked ? TIMED_ALERTS : ALLDAY_ALERTS;
    const cur = keep ? alertMins() : null;
    const known = opts2.some(([m]) => m === cur);
    fill(alert, h('option', { value: '' }, 'None'), opts2.map(([m, l]) => h('option', { value: m, selected: m === cur ? true : null }, l)),
      cur != null && !known ? h('option', { value: 'keep', selected: true }, t.alarms.map((a) => new Date(a).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })).join(', ')) : null);
  };
  drawAlerts(true);
  const whenRow = h('div', { class: 'when-row' });
  const drawWhen = () => {
    fill(whenRow, h('label', { class: 'check' }, hasDue, ' Due'), hasDue.checked ? [date, h('label', { class: 'check' }, hasTime, ' At a time'), hasTime.checked ? time : null] : null);
    repeat.closest('.field')?.toggleAttribute('hidden', !hasDue.checked);
    alert.closest('.field')?.toggleAttribute('hidden', !hasDue.checked);
  };
  hasDue.onchange = drawWhen;
  hasTime.onchange = () => { drawWhen(); drawAlerts(false); };

  const who = h('div', { class: 'chiprow' });
  const drawWho = () => fill(who, S.members.map((m) => h('button', { type: 'button', class: `chip toggle mchip ${picked.has(m.id) ? 'on' : ''}`, disabled: ro || null,
    onclick: () => { if (picked.has(m.id)) picked.delete(m.id); else picked.add(m.id); drawWho(); } }, memberBadge(m), m.displayName)));
  drawWho();

  const subs = h('div', { class: 'subs' });
  const drawSubs = async () => {
    if (!t) return;
    const j = await api(`/api/tasks/${t.id}`);
    fill(subs, h('div', { class: 'fsec' }, icon('subtask'), 'Subtasks'), h('div', { class: 'tasks' }, j.children.map((x) => {
      const row = taskRow(x, {});
      row.querySelector('.tbody').onclick = () => { closeDialogs(); openTask(x.id); };
      row.querySelector('.info').onclick = () => { closeDialogs(); openTask(x.id); };
      return row;
    })),
    ro ? null : h('input', { class: 'qadd', placeholder: 'Add a subtask', onkeydown: async (e) => {
      if (e.key !== 'Enter' || !e.target.value.trim()) return;
      e.preventDefault();
      try { await api('/api/tasks', { method: 'POST', json: { title: e.target.value.trim(), parent: t.id, listId: t.listId } }); await drawSubs(); subs.querySelector('.qadd')?.focus(); } catch (err) { fail(err); }
    } }));
  };

  /** The fields as the API takes them. */
  const collect = () => {
    const data = { title: title.value.trim(), notes: notes.value, priority: prio.value || 'none', url: url.value.trim(), members: [...picked] };
    if (!hasDue.checked) { data.due = null; data.rrule = null; data.alarms = []; return data; }
    data.due = hasTime.checked ? `${date.value}T${time.value || '09:00'}` : date.value;
    data.timezone = LOCAL_TZ;
    data.rrule = repeat.value || null;
    if (alert.value !== 'keep') {
      const due = hasTime.checked ? new Date(`${date.value}T${time.value || '09:00'}`) : parseDay(date.value);
      data.alarms = alert.value === '' ? [] : [new Date(+due - +alert.value * 6e4).toISOString()];
    }
    return data;
  };
  const save = async () => {
    const data = collect();
    if (!data.title) { toast('A title, please'); title.focus(); return; }
    try {
      if (t) {
        if (+list.value !== t.listId) data.listId = +list.value;
        await api(`/api/tasks/${t.id}`, { method: 'PATCH', json: data });
      } else {
        data.listId = +list.value;
        if (parent) { data.parent = parent.id; data.listId = parent.listId; }
        await api('/api/tasks', { method: 'POST', json: data });
      }
      toast('Saved');
      done();
    } catch (e) { fail(e); }
  };
  const del = async () => {
    const n = t.subtasks ? t.subtasks.total : 0;
    if (!await confirmDialog('Delete task', `Delete “${t.title || 'this task'}”${n ? ` and its ${n} subtask${n > 1 ? 's' : ''}` : ''}?`, 'Delete', true)) return;
    try { await api(`/api/tasks/${t.id}`, { method: 'DELETE' }); toast('Deleted'); done(); } catch (e) { fail(e); }
  };
  title.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); save(); } });
  const fld = (l, e, cls) => h('label', { class: `field ${cls || ''}` }, h('span', null, l), e);

  fill(el,
    h('div', { class: 'taskhead', style: { '--c': listOf(+list.value).color || 'var(--brand)' } },
      t ? h('button', { class: `tick big ${t.done ? 'on' : ''}`, title: t.done ? 'Not done after all' : 'Done', disabled: ro || null, onclick: async (e) => {
        try { const res = await api(`/api/tasks/${t.id}/complete`, { method: 'POST', json: { done: !t.done } }); toast(res.moved ? `Done. Next: ${dueText(res)}` : res.done ? 'Done' : 'Open again'); done(); } catch (err) { fail(err); }
        e.stopPropagation();
      } }) : null,
      title),
    parent ? h('p', { class: 'muted small' }, `Subtask of “${parent.title}”`) : null,
    ro ? h('p', { class: 'muted small' }, 'Read-only: editors and admins change shared lists.') : null,
    notes,
    h('div', { class: 'fsec' }, icon('today'), 'When'), whenRow,
    h('div', { class: 'grid', style: { marginTop: '10px' } }, fld('Repeat', repeat), fld('Alert', alert)),
    t && t.rrule ? h('p', { class: 'muted small' }, `${describeRule(t.rrule, dd)}. Ticking it off moves it to the next date.`) : null,
    h('div', { class: 'fsec' }, icon('tune'), 'Details'),
    h('div', { class: 'grid' }, fld('List', list), fld('Priority', prio), fld('Link', url, 'wide')),
    S.members.length > 1 ? [h('div', { class: 'fsec' }, icon('people'), 'For'), who] : null,
    subs,
    t ? h('p', { class: 'muted small' }, [t.created ? `Added ${new Date(t.created).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}` : null, t.done && t.completedAt ? `done ${new Date(t.completedAt).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}` : null].filter(Boolean).join(', ')) : null,
    h('div', { class: 'formbar' },
      ro ? null : h('button', { class: 'pillbtn primary noic', onclick: save }, 'Save'),
      h('button', { class: 'pillbtn noic', onclick: done }, ro ? 'Close' : 'Cancel'),
      t && !ro && !t.parent ? h('button', { class: 'pillbtn noic', title: 'A new subtask', onclick: () => { closeDialogs(); location.hash = `#/new?parent=${t.id}`; } }, 'Add subtask') : null,
      h('span', { class: 'grow' }),
      t && !ro ? h('button', { class: 'pillbtn noic danger', onclick: del }, 'Delete') : null));
  list.onchange = () => el.querySelector('.taskhead').style.setProperty('--c', listOf(+list.value).color || 'var(--brand)');
  drawWhen();
  await drawSubs();
  if (!t) title.focus();
}

// ------------------------------------------------------------------ import
async function showImport(page, r) {
  const w = writable();
  const sel = h('select', { class: 't', style: { maxWidth: '320px' } }, w.map((c) => h('option', { value: c.id, selected: c.id === r.list ? true : null }, `${c.name}${c.shared ? ' (shared)' : ''}`)));
  const file = h('input', { type: 'file', accept: '.ics,.ical,text/calendar', multiple: true });
  const replace = h('input', { type: 'checkbox', checked: true });
  const out = h('div');
  const run = async () => {
    if (!file.files.length) { toast('Pick a file first'); return; }
    const tot = { created: 0, updated: 0, skipped: 0, errors: [] };
    for (const f of file.files) {
      const fd = new FormData(); fd.append('file', f);
      try {
        const res = await api(`/api/lists/${sel.value}/import?replace=${replace.checked}`, { method: 'POST', body: fd });
        tot.created += res.created; tot.updated += res.updated; tot.skipped += res.skipped; tot.errors.push(...res.errors);
      } catch (e) { tot.errors.push(`${f.name}: ${e.message}`); }
    }
    fill(out, h('p', null, `${tot.created} added, ${tot.updated} updated${tot.skipped ? `, ${tot.skipped} left as they were` : ''}.`),
      tot.errors.length ? h('details', null, h('summary', { class: 'lnk' }, `${tot.errors.length} could not be read`), h('ul', null, tot.errors.slice(0, 50).map((x) => h('li', null, x)))) : null);
    await loadLists();
  };
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Import')),
    w.length ? h('div', { class: 'box' }, h('h2', null, icon('upload'), 'Import'),
      h('p', null, 'An iCalendar file (.ics) with to-dos, from another tasks app or another ioTasks. Due dates, repeats, alerts, priorities and subtasks come along; events in the file are left out.'),
      h('div', { class: 'pform' }, h('label', { class: 'field' }, h('span', null, 'Into the list'), sel), file,
        h('label', { class: 'check' }, replace, ' Update tasks that are already here (same UID)'),
        h('p', null, h('button', { class: 'pillbtn primary', onclick: run }, icon('upload', 's'), 'Import'))), out) : h('p', { class: 'muted' }, 'You cannot add tasks to any list.'));
}

// ------------------------------------------------------------------ settings
async function showSettings(page, r) {
  const adm = S.user.role === 'admin';
  const tabs = [['account', 'Account'], ['display', 'Display'], ['devices', 'Apps and devices'], ['lists', 'Lists'],
    ...(adm ? [['family', 'Family'], ['server', 'Server']] : []),
    ...(S.user.suiteAdmin ? [['security', SUITE_TABS.security], ['global', SUITE_TABS.global]] : [])];
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Settings')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/settings/${k}`; } }, l))));
  const body = h('div'); page.append(body);
  await ({ account: setAccount, display: setDisplay, devices: setDevices, lists: setLists, family: setFamily, server: setServer,
    security: setSuite, global: setSuite }[r.tab] || setAccount)(body, r);
}
const fld = (l, e) => h('label', { class: 'field' }, h('span', null, l), e);
const kv = (k, v) => h('div', { class: 'kv' }, h('div', { class: 'k' }, k), h('div', { class: 'v', style: { flex: 1 } }, typeof v === 'string' ? copyRow(v) : v));

const accountUi = () => import(new URL('api/auth/ui.js', document.baseURI).href);
/** Settings › Account: display name, email and password, then the app passwords: iosuite-shared's panels (the same in every io app). */
async function setAccount(el) {
  const ui = await accountUi();
  const pw = h('div');
  await ui.mountAccount(el, { toast, onSaved: (u) => { Object.assign(S.user, u); drawUser(); } });
  el.append(pw);
  await ui.mountAppPasswords(pw, { toast, syncOnly: 'Reminders apps only (CalDAV)' });
}

/** Settings › Display: the theme (saved with the account) and where the app opens and new tasks go. */
async function setDisplay(el) {
  const ui = await accountUi();
  const save = async (changes) => { await saveSettings(changes); drawNav(); toast('Saved'); };
  const sv = h('select', { class: 't', onchange: (e) => save({ startView: e.target.value }) },
    Object.entries(SMART).slice(0, 3).map(([v, [l]]) => h('option', { value: v, selected: v === (S.settings.startView || 'today') ? true : null }, l)));
  const dl = h('select', { class: 't', onchange: (e) => save({ defaultList: +e.target.value }) },
    writable().map((c) => h('option', { value: c.id, selected: c.id === defaultList()?.id ? true : null }, `${c.name}${c.shared ? ' (shared)' : ''}`)));
  el.append(ui.box('theme', 'Appearance', ui.themeRow(S.settings.theme || store.get('theme') || 'system', (t) => { S.settings.theme = t; applyTheme(t); })),
    h('div', { class: 'box' }, h('h2', null, icon('tune'), 'Tasks'), h('div', { class: 'grid' }, fld('Open on', sv), fld('New tasks go to', dl))));
}

/** The profile through a short-lived link instead of the form post: the app on the Home Screen opens a download in a
 * separate sheet without its cookies, which a link opens by itself (the form post stays the fallback without script). */
async function downloadProfile(e) {
  e.preventDefault();
  const f = e.target;
  const btn = f.querySelector('button[type=submit]');
  if (btn) btn.disabled = true;
  try {
    const res = await api('/api/apple-profile/link', { method: 'POST', json: { label: f.elements.label.value, password: f.elements.password.value } });
    location.href = res.url;
  } catch (err) {
    toast(err.message);
  } finally {
    if (btn) setTimeout(() => { btn.disabled = false; }, 1500);
  }
}

/** Settings › Apps and devices: how to connect each kind of app (the app passwords themselves are on Settings › Account). */
async function setDevices(el) {
  const info = await api('/api/connect');
  const canPw = !S.user.passwordless;
  const isApple = /iPhone|iPad|Macintosh/.test(navigator.userAgent);
  const plabel = h('input', { class: 't', name: 'label', value: /iPad/.test(navigator.userAgent) ? 'iPad' : /Macintosh/.test(navigator.userAgent) ? 'Mac' : 'iPhone', style: 'max-width:200px' });
  const how = (summary, ...kids) => h('details', null, h('summary', { class: 'lnk' }, summary), ...kids);
  el.append(...[
    canPw ? h('div', { class: 'box' }, h('h2', null, icon('devices'), 'iPhone, iPad and Mac'),
      h('p', null, 'A profile that adds your lists to Apple Reminders in one step. Tasks you add or tick off there show up here, and the other way round.'),
      h('form', { method: 'POST', action: '/api/apple-profile', class: 'pform', onsubmit: downloadProfile },
        fld('Device name', plabel),
        fld('Password', h('select', { class: 't', name: 'password' }, h('option', { value: 'new' }, 'Include a new app password'), h('option', { value: 'ask' }, 'Ask on the device'))),
        h('p', null, h('button', { class: 'pillbtn primary', type: 'submit' }, icon('download', 's'), 'Download the profile'))),
      how('How to install', h('p', { class: 'muted small' }, isApple ? 'Open the download, then Settings › Profile Downloaded › Install.' : 'Download it in Safari on the iPhone or iPad, then Settings › Profile Downloaded › Install. On a Mac: open the file, then System Settings › Privacy & Security › Profiles.',
        ' iOS shows the profile as “Not Verified”: that is expected. Revoke its app password under Settings › Account if the device is lost.'),
      h('p', { class: 'muted small' }, 'The lists appear in Reminders under the account “ioTasks”. Lists made there are made here too.'))) : null,
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
        copyRow(`claude mcp add --transport http iotasks ${info.mcp} --header "Authorization: Bearer APP-PASSWORD"`),
        copyRow(JSON.stringify({ mcpServers: { iotasks: { command: 'npx', args: ['-y', 'mcp-remote', info.mcp, '--header', 'Authorization: Bearer APP-PASSWORD'] } } }))))
      : (S.user.role === 'admin' ? h('div', { class: 'box' }, h('h2', null, icon('ai'), 'AI assistants (MCP)'), h('p', { class: 'muted' }, 'Off. Turn it on in ', h('a', { class: 'lnk', href: '#/settings/server' }, 'Settings › Server'), '.')) : null),
    h('div', { class: 'box' }, h('h2', null, icon('link'), 'Other apps (REST API)'),
      h('p', null, 'JSON or iCalendar with your user name and an app password. ', h('a', { class: 'lnk', href: info.api, target: '_blank' }, 'API documentation')),
      copyRow(`curl -u ${info.user}:APP-PASSWORD "${info.server}/api/tasks?due=today"`))].filter(Boolean));
}

async function setLists(el, r) {
  await loadLists();
  el.append(h('p', null, S.user.role !== 'viewer' ? h('button', { class: 'pillbtn', onclick: () => newList(true) }, icon('add', 's'), 'New shared list') : null, ' ',
    h('button', { class: 'pillbtn', onclick: () => newList(false) }, icon('add', 's'), 'New private list')),
  ...S.lists.map((c) => {
    const save = async (body) => { try { await api(`/api/lists/${c.id}`, { method: 'PATCH', json: body }); await loadLists(); toast('Saved'); } catch (e) { fail(e); } };
    const name = h('input', { class: 't', value: c.name, onchange: (e) => save({ name: e.target.value }) });
    const desc = h('input', { class: 't', value: c.description || '', placeholder: 'What it is for', onchange: (e) => save({ description: e.target.value }) });
    const col = colorPicker(c.color, (v) => save({ color: v }));
    return h('div', { class: 'box', id: `list-${c.id}`, style: { '--c': c.color } },
      h('h2', null, h('span', { class: 'ldot', style: { '--hue': c.color } }), c.name,
        h('span', { class: 'muted small', style: { fontWeight: 400 } }, c.shared ? 'shared with everyone' : 'only you')),
      c.writable ? [h('div', { class: 'grid' }, fld('Name', name), fld('Description', desc)), h('div', { style: { margin: '10px 0' } }, col),
        h('p', null, h('a', { class: 'pillbtn noic', href: `/api/lists/${c.id}/export` }, 'Export (.ics)'), ' ',
          !c.shared || S.user.role === 'admin' ? h('button', { class: 'pillbtn noic danger', onclick: async () => {
            if (!await confirmDialog('Delete list', `Delete ${c.name} and its tasks? Apps that sync it lose it too.`, 'Delete', true)) return;
            try { await api(`/api/lists/${c.id}`, { method: 'DELETE' }); await loadLists(); onRoute(); } catch (e) { fail(e); }
          } }, 'Delete') : null)]
        : h('p', { class: 'muted' }, `${c.count || 0} open tasks. Editors and admins change shared lists.`));
  }));
  if (r.sub) setTimeout(() => $(`#list-${r.sub}`)?.scrollIntoView({ block: 'start' }), 0);
}

/** Who is in the family: the people tasks can be for, each with a private list of their own. Accounts, passwords and
    roles are the suite's (Settings › Security, suite admins). */
async function setFamily(el) {
  const [res, fam] = await Promise.all([api('/api/users'), api('/api/members')]);
  const leftOut = new Set(fam.leftOut || []);
  el.append(h('div', { class: 'box' }, h('h2', null, icon('people'), 'Family members'),
    h('p', { class: 'muted' }, 'The people tasks can be for, each with a private list. Accounts are added under Settings › Security.'),
    h('table', { class: 't' }, h('tr', null, h('th', null, 'Name'), h('th', null, 'Display name'), h('th', null, 'Role here'), h('th', null, 'In the family')),
      res.users.map((u) => {
        const fk = h('input', { type: 'checkbox', checked: !leftOut.has(u.id), title: `${u.displayName} is someone tasks can be for` });
        fk.onchange = async () => {
          try { await api(`/api/members/${u.id}`, { method: 'PUT', json: { inFamily: fk.checked } }); await loadLists(); toast(fk.checked ? `${u.displayName} is in the family` : `${u.displayName} is left out of the family`); } catch (e) { fk.checked = !fk.checked; fail(e); }
        };
        return h('tr', null, h('td', null, u.name, u.suiteAdmin ? h('span', { class: 'muted small' }, ' · suite admin') : null), h('td', null, u.displayName), h('td', { class: 'muted' }, u.role), h('td', null, h('label', { class: 'check' }, fk)));
      }))));
}

/** Settings › Security and Global settings (suite admins): the people, their role in every app, app
    passwords, sign-in at the proxy; the apps, keys and tokens. The same panel in every io app, served by iosuite-shared. */
const SUITE_TABS = { security: 'Security', global: 'Global settings' };
async function setSuite(el, r) {
  let ui;
  try { ui = await import(new URL('api/suite-admin/ui.js', document.baseURI).href); } catch (e) { el.append(h('p', { class: 'warn' }, `The panel did not load: ${e.message}`)); return; }
  await ui.mount(el, { tab: r.tab, sub: r.sub, toast, onSub: (x) => history.replaceState(null, '', `#/settings/${r.tab}/${x}`) });
}

/** Settings › Server (admins): the MCP switch, the version and its updates, this server, the server log and Restart
    (iosuite-shared's panel, the same in every io app), then Export: each list as an .ics file. */
async function setServer(el) {
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
      h('td', { style: { textAlign: 'right' } }, h('a', { class: 'pillbtn noic', href: `/api/lists/${c.id}/export` }, 'Download')))))));
}
const serverUi = () => import(new URL('api/server/ui.js', document.baseURI).href);

/** Admins: a note when the daily check found a newer version, with Update now. Hidden until the next version when dismissed. */
function updateBanner() {
  $('#updbanner')?.remove();
  const u = S.status && S.status.update;
  if (!u || store.get('updateDismissed') === u.remote) return;
  const b = h('div', { id: 'updbanner', role: 'status' }, icon('update'),
    h('span', null, `ioTasks ${u.version ? `v${u.version}` : 'update'} is available${u.message ? `: ${u.message.replace(/^v\d+\.\d+\.\d+:\s*/, '')}` : ''}`),
    h('button', { class: 'pillbtn primary noic', onclick: async () => { if (await confirmDialog('Update ioTasks', 'Install the new version and restart? The page reloads when it is back.', 'Update now')) { b.remove(); (await serverUi()).runUpdate({ toast }); } } }, 'Update now'),
    h('a', { class: 'pillbtn noic', href: '#/settings/server', onclick: () => b.remove() }, 'Details'),
    h('button', { class: 'iconbtn', title: 'Not now (hidden until the next version)', onclick: () => { store.set('updateDismissed', u.remote); b.remove(); } }, icon('close', 's')));
  document.body.append(b);
}

// ------------------------------------------------------------------ sign-in
function showSignIn() {
  // as in the other io apps: a tile per account; one click for a passwordless viewer, a password for the others
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
    try { await api(first ? '/api/auth/setup' : '/api/auth/login', { method: 'POST', json: { name: n, password: p } }); location.reload(); } catch (x) { err.textContent = x.message; }
  };
  const submit = (e) => { e.preventDefault(); login(name.value.trim(), pw.value); };
  document.body.append(h('div', { class: 'signin' }, h('form', { class: 'dialog', onsubmit: submit },
    h('div', { class: 'brand' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }), h('span', { class: 'brand-name', style: { display: 'inline' } }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Tasks'))),
    first ? h('p', { class: 'muted' }, 'Welcome. Make the first account: it is the admin, who adds the rest of the family in Settings. (Already use another io app? Sign in there first, or use the same name and password here once the apps share their accounts.)') : h('h2', null, 'Sign in'),
    tiles, form, err, h('div', { class: 'btns' }, btn))));
  if (first) { name.focus(); return; }
  const pick = (t) => tiles.querySelectorAll('.account').forEach((x) => x.classList.toggle('on', x === t));
  api('/api/auth/accounts').then((d) => {
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

// ------------------------------------------------------------------ start
async function start() {
  applyTheme();
  document.querySelectorAll('[data-ic]').forEach((el) => el.replaceWith(icon(el.dataset.ic)));
  S.status = await api('/api/status');
  if (!S.status.user) { showSignIn(); return; }
  S.user = S.status.user;
  try { S.settings = (await api('/api/auth/me')).settings || {}; } catch { S.settings = {}; }
  if (S.settings.theme) applyTheme(S.settings.theme);
  S.who = new Set(String(S.settings.memberFilter || '').split(',').filter(Boolean).map(Number));
  drawUser();
  await loadLists();
  $('#newbtn').onclick = () => {
    const q = $('#qadd');
    if (q) { q.focus(); return; }
    const r = route();
    location.hash = r.view === 'list' && listOf(r.id).writable ? `#/new?list=${r.id}` : '#/new';
  };
  $('#menubtn').onclick = openNav;
  $('#navscrim').onclick = closeNav;
  $('#nav').addEventListener('click', (e) => { if (e.target.closest('a:not(.who)') && !document.body.classList.contains('side-docked')) closeNav(); });
  addEventListener('resize', applySidebar);
  let t;
  $('#q').addEventListener('input', (e) => {
    clearTimeout(t);
    t = setTimeout(() => {
      const q = e.target.value.trim();
      if (q) location.hash = `#/search/${encodeURIComponent(q)}`;
      else if (route().view === 'search') location.hash = '#/';
    }, 250);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { if (document.querySelector('.dialog-back')) closeDialogs(); else if (document.body.classList.contains('side-open')) closeNav(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) || document.querySelector('.signin, .dialog-back')) return;
    const k = e.key;
    if (k === '/') { e.preventDefault(); $('#q').focus(); }
    else if (k === 'n') { e.preventDefault(); $('#newbtn').click(); }
    else if (k === 't') location.hash = '#/today';
    else if (k === 's') location.hash = '#/scheduled';
    else if (k === 'a') location.hash = '#/all';
  });
  addEventListener('hashchange', onRoute);
  await onRoute();
  loadSuite();
  updateBanner();
  // come back to the tab: show what changed elsewhere (a phone, another person)
  let away = Date.now();
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { away = Date.now(); return; }
    if (Date.now() - away > 60000 && !document.querySelector('.dialog-back')) refresh().catch(() => {});
  });
  setInterval(async () => { try { S.status = await api('/api/status'); updateBanner(); } catch { /* restarting */ } }, 15 * 60 * 1000);
}
start().catch(fail);
