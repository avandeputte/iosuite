/* ioBackup web app: one module, no build step, laid out as the other ioThing apps. Pages: the backup jobs (the start
   page), the backups in each destination (with verify, download, delete and a restore of exactly what you pick),
   activity (every run with its log), servers, destinations and Settings (account, display, and for admins the
   server, for suite admins security and global settings). */

// ------------------------------------------------------------------ helpers
const $ = (s, el = document) => el.querySelector(s);
const ICONS = {
  dns: 'M20 13H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1v-6c0-.55-.45-1-1-1zM7 19c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zM20 3H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1V4c0-.55-.45-1-1-1zM7 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
  list: 'M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z',
  compare: 'M10 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h5v2h2V1h-2v2zm0 15H5l5-6v6zm9-15h-5v2h5v13l-5-6v9h5c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2z',
  sync: 'M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46A7.93 7.93 0 0 0 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74A7.93 7.93 0 0 0 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z',
  globe: 'M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zm6.93 6h-2.95a15.65 15.65 0 0 0-1.38-3.56A8.03 8.03 0 0 1 18.92 8zM12 4.04c.83 1.2 1.48 2.53 1.91 3.96h-3.82c.43-1.43 1.08-2.76 1.91-3.96zM4.26 14C4.1 13.36 4 12.69 4 12s.1-1.36.26-2h3.38c-.08.66-.14 1.32-.14 2s.06 1.34.14 2H4.26zm.82 2h2.95c.32 1.25.78 2.45 1.38 3.56A7.987 7.987 0 0 1 5.08 16zm2.95-8H5.08a7.987 7.987 0 0 1 4.33-3.56A15.65 15.65 0 0 0 8.03 8zM12 19.96c-.83-1.2-1.48-2.53-1.91-3.96h3.82c-.43 1.43-1.08 2.76-1.91 3.96zM14.34 14H9.66c-.09-.66-.16-1.32-.16-2s.07-1.35.16-2h4.68c.09.65.16 1.32.16 2s-.07 1.34-.16 2zm.25 5.56c.6-1.11 1.06-2.31 1.38-3.56h2.95a8.03 8.03 0 0 1-4.33 3.56zM16.36 14c.08-.66.14-1.32.14-2s-.06-1.34-.14-2h3.38c.16.64.26 1.31.26 2s-.1 1.36-.26 2h-3.38z',
  history: 'M13 3a9 9 0 0 0-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42A8.954 8.954 0 0 0 13 21a9 9 0 0 0 0-18zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z',
  menu: 'M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z',
  menuOpen: 'M3 18h13v-2H3v2zm0-5h10v-2H3v2zm0-7v2h13V6H3zm18 9.59L17.42 12 21 8.41 19.59 7l-5 5 5 5L21 15.59z',
  pin: 'M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3z',
  search: 'M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z',
  add: 'M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z',
  person: 'M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z',
  settings: 'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z',
  edit: 'M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a.996.996 0 0 0 0-1.41l-2.34-2.34a.996.996 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z',
  delete: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z',
  close: 'M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z',
  check: 'M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z',
  upload: 'M9 16h6v-6h4l-7-7-7 7h4zm-4 2h14v2H5z',
  download: 'M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z',
  logout: 'M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z',
  theme: 'M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.389 5.389 0 0 1-4.4 2.26 5.403 5.403 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z',
  more: 'M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  update: 'M21 10.12h-6.78l2.74-2.82c-2.73-2.7-7.15-2.8-9.88-.1a6.875 6.875 0 0 0 0 9.79 7.02 7.02 0 0 0 9.88 0C18.32 15.65 19 14.08 19 12.1h2c0 1.98-.88 4.55-2.64 6.29-3.51 3.48-9.21 3.48-12.72 0-3.5-3.47-3.53-9.11-.02-12.58a8.987 8.987 0 0 1 12.65 0L21 3v7.12z',
  tune: 'M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 4v-2H11v2h10zm-6-4h2V7h4V5h-4V3h-2v6z',
  vpn: 'M12.65 10C11.83 7.67 9.61 6 7 6c-3.31 0-6 2.69-6 6s2.69 6 6 6c2.61 0 4.83-1.67 5.65-4H17v4h4v-4h2v-4H12.65zM7 14c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
  layers: 'M11.99 18.54l-7.37-5.73L3 14.07l9 7 9-7-1.63-1.27-7.38 5.74zM12 16l7.36-5.73L21 9l-9-7-9 7 1.63 1.27L12 16z',
  play: 'M8 5v14l11-7z',
  backup: 'M19.35 10.04A7.49 7.49 0 0 0 12 4C9.11 4 6.6 5.64 5.35 8.04A5.994 5.994 0 0 0 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM14 13v4h-4v-4H7l5-5 5 5h-3z',
  cloud: 'M19.35 10.04A7.49 7.49 0 0 0 12 4C9.11 4 6.6 5.64 5.35 8.04A5.994 5.994 0 0 0 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96z',
  folder: 'M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z',
  restore: 'M13 3a9 9 0 0 0-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42A8.954 8.954 0 0 0 13 21a9 9 0 0 0 0-18z',
  back: 'M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z',
  job: 'M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z',
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
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 4000);
}
const fail = (e) => toast(e.message || String(e));

function dialog(title, body, buttons, wide) {
  return new Promise((resolve) => {
    const back = h('div', { class: 'dialog-back' });
    const close = (v) => { back.remove(); resolve(v); };
    back.addEventListener('click', (e) => { if (e.target === back) close(null); });
    const btns = (buttons || [{ label: 'OK', value: true, primary: true }]).map((b) =>
      h('button', { class: `pillbtn noic ${b.primary ? 'primary' : ''} ${b.danger ? 'danger' : ''}`, onclick: async () => {
        if (typeof b.value !== 'function') { close(b.value); return; }
        try { const v = await b.value(); if (v !== undefined) close(v); } catch (e) { fail(e); }
      } }, b.label));
    back.append(h('div', { class: `dialog ${wide ? 'wide' : ''}`, role: 'dialog' }, h('h2', null, title), body, h('div', { class: 'btns' }, btns)));
    document.body.append(back);
    const f = back.querySelector('input:not([type=checkbox]),select,textarea'); if (f) f.focus();
  });
}
const confirmDialog = (title, text, ok = 'OK', danger = false) => dialog(title, typeof text === 'string' ? h('p', null, text) : text, [{ label: 'Cancel', value: false }, { label: ok, value: true, primary: !danger, danger }]);
const closeDialogs = () => document.querySelectorAll('.dialog-back').forEach((d) => d.remove());

const hue = (s) => { let x = 0; for (const c of s || '') x = (x * 31 + c.charCodeAt(0)) % 360; return x; };
const initials = (fn) => { const p = (fn || '?').trim().split(/\s+/); return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase(); };
const fld = (l, e, hint) => h('label', { class: 'field' }, h('span', null, l), e, hint ? h('small', { class: 'muted' }, hint) : null);
const ago = (iso) => {
  if (!iso) return 'never';
  const s = (Date.now() - new Date(iso.endsWith('Z') || /[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z')) / 1000;
  if (s < 90) return 'just now';
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(iso).toLocaleString();
};


// ------------------------------------------------------------------ state
const S = { status: {}, user: null, suite: [], settings: {}, servers: [], destinations: [], jobs: [], busy: false, now: null, backupDir: '', suiteServer: {} };
const canEdit = () => S.user && ['editor', 'admin'].includes(S.user.role);
const isAdmin = () => S.user && S.user.role === 'admin';
const byId = (list, id) => (list || []).find((x) => x.id === id);
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
let pollTimer = null;

async function loadOverview() {
  const o = await api('/api/overview');
  Object.assign(S, { servers: o.servers, destinations: o.destinations, jobs: o.jobs, busy: o.busy, now: o.now, backupDir: o.backupDir, suiteServer: o.suiteServer });
  drawNav();
}
async function saveSettings(changes) {
  Object.assign(S.settings, changes);
  try { await api('/api/auth/settings', { method: 'POST', json: changes }); } catch { /* kept for this visit */ }
}

const size = (n) => {
  if (n == null) return '';
  const u = ['B', 'KB', 'MB', 'GB', 'TB']; let i = 0; n = +n;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${i ? n.toFixed(1) : n} ${u[i]}`;
};
const when = (iso) => {
  if (!iso) return '';
  const d = new Date(iso); if (isNaN(d)) return iso;
  const now = new Date(), t = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (d.toDateString() === now.toDateString()) return `today ${t}`;
  return `${d.toLocaleDateString([], { month: 'short', day: 'numeric', year: d.getFullYear() === now.getFullYear() ? undefined : 'numeric' })} ${t}`;
};
const dur = (a, b) => {
  if (!a || !b) return '';
  const s = Math.round((new Date(b) - new Date(a)) / 1000);
  return s >= 60 ? `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s` : `${s}s`;
};
const STATUS = { ok: ['b-ok', 'Succeeded'], failed: ['b-diff', 'Failed'], running: ['b-missing', 'Running'], queued: ['b-extra', 'Queued'], cancelled: ['b-extra', 'Cancelled'] };
const pill = (st) => h('span', { class: `badge ${(STATUS[st] || ['b-extra'])[0]}` }, (STATUS[st] || [null, st])[1]);
function scheduleText(s) {
  s = s || { mode: 'manual' };
  const t = s.time || '02:00';
  switch (s.mode) {
    case 'hourly': return `${s.every > 1 ? `every ${s.every} hours` : 'hourly'} at :${String(s.minute || 0).padStart(2, '0')}`;
    case 'daily': return `daily at ${t}`;
    case 'weekly': return `${(s.days || []).map((d) => DAYS[d % 7]).join(', ')} at ${t}`;
    case 'monthly': return `monthly on day ${s.day || 1} at ${t}`;
    case 'cron': return `cron ${s.cron}`;
    default: return 'on demand only';
  }
}
const btn = (label, onclick, cls = '') => h('button', { class: `pillbtn noic ${cls}`, onclick }, label);
const fail2 = (el) => (e) => el.replaceChildren(h('p', { class: 'warn' }, e.message || String(e)));

// ------------------------------------------------------------------ jobs (the start page)
async function showJobs(page) {
  await loadOverview();
  const { items: runs } = await api('/api/runs?limit=8');
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Backup jobs'),
    isAdmin() ? h('button', { class: 'pillbtn primary', disabled: !S.servers.length || !S.destinations.length, onclick: () => editJob(null) }, icon('add', 's'), 'New job') : null));
  const steps = [];
  if (!S.servers.length) steps.push(['Add the MariaDB server to back up (the suite\'s own, or any other)', '#/servers']);
  if (!S.destinations.length) steps.push(['Add a destination: a folder or Google Drive', '#/destinations']);
  if (!S.jobs.length) steps.push(['Make a backup job: what to back up, where, how often, how many to keep', null]);
  if (steps.length && isAdmin()) {
    page.append(h('div', { class: 'box' }, h('h2', null, icon('play'), 'Getting started'),
      h('ol', null, steps.map(([t, l]) => h('li', null, l ? h('a', { class: 'lnk', href: l }, t) : t)))));
  }
  if (!S.jobs.length) {
    if (!isAdmin()) page.append(h('div', { class: 'empty' }, icon('backup'), h('p', null, 'No backup job yet.')));
  } else {
    page.append(h('div', { class: 'tablewrap' }, h('table', { class: 't' },
      h('tr', null, h('th', null, 'Job'), h('th', null, 'What'), h('th', null, 'Where'), h('th', null, 'When'), h('th', null, 'Last run'), h('th', null)),
      S.jobs.map(jobRow))));
  }
  page.append(h('h2', { class: 'sech' }, 'Recent activity'), runsTable(runs), runs.length ? h('p', null, h('a', { class: 'lnk', href: '#/activity' }, 'All activity')) : null);
  if (S.busy) pollTimer = setTimeout(onRoute, 4000);
}
function jobRow(j) {
  const srv = byId(S.servers, j.serverId), dst = byId(S.destinations, j.destinationId), lr = j.lastRun;
  const what = (j.databases === 'all' ? 'all databases' : j.databases.join(', ') || 'no databases') + (j.includeUsers ? ' + users' : '');
  return h('tr', null,
    h('td', null, h('b', null, j.name), h('div', { class: 'muted small' }, srv ? srv.name : '?')),
    h('td', null, what),
    h('td', null, dst ? dst.name : '?', h('div', { class: 'muted small' }, j.keep ? `keeps the newest ${j.keep}` : 'keeps them all')),
    h('td', null, j.enabled ? scheduleText(j.schedule) : h('span', { class: 'muted' }, 'paused'), j.nextRun ? h('div', { class: 'muted small' }, `next ${when(j.nextRun)}`) : null),
    h('td', null, j.pending ? pill('running') : lr ? h('a', { href: `#/run/${lr.id}` }, pill(lr.status)) : h('span', { class: 'muted' }, 'never'),
      lr ? h('div', { class: 'muted small' }, when(lr.finished), lr.result && lr.result.size ? ` · ${size(lr.result.size)}` : '') : null),
    h('td', { style: { whiteSpace: 'nowrap', textAlign: 'right' } },
      canEdit() ? h('button', { class: 'pillbtn noic primary tiny', disabled: j.pending, onclick: () => runJob(j) }, 'Run now') : null, ' ',
      isAdmin() ? h('button', { class: 'pillbtn noic tiny', onclick: () => editJob(j) }, 'Edit') : null));
}
async function runJob(j) {
  try { const r = await api(`/api/jobs/${j.id}/run`, { method: 'POST' }); location.hash = `#/run/${r.runId}`; } catch (e) { fail(e); }
}
async function editJob(j) {
  const isNew = !j;
  j = j || { name: '', serverId: (S.servers[0] || {}).id, destinationId: (S.destinations[0] || {}).id, databases: 'all', includeUsers: true, keep: 7,
    enabled: true, desync: false, lockAll: false, compressLevel: 6, schedule: { mode: 'daily', time: '02:00' } };
  const sch = { mode: 'manual', time: '02:00', minute: 0, every: 1, days: [1], day: 1, cron: '0 2 * * *', ...j.schedule };
  const inp = (attrs) => h('input', { class: 't', ...attrs });
  const f = {
    name: inp({ value: j.name, placeholder: 'Nightly' }),
    server: h('select', { class: 't', onchange: () => loadDbs() }, S.servers.map((s) => h('option', { value: s.id, selected: s.id === j.serverId }, s.name))),
    dest: h('select', { class: 't' }, S.destinations.map((d) => h('option', { value: d.id, selected: d.id === j.destinationId }, d.name))),
    all: h('input', { type: 'radio', name: 'dbm', checked: j.databases === 'all', onchange: () => { dbBox.hidden = true; } }),
    some: h('input', { type: 'radio', name: 'dbm', checked: j.databases !== 'all', onchange: () => { dbBox.hidden = false; loadDbs(); } }),
    users: h('input', { type: 'checkbox', checked: j.includeUsers }),
    keep: inp({ type: 'number', min: 0, value: j.keep, style: { width: '110px' } }),
    enabled: h('input', { type: 'checkbox', checked: j.enabled }),
    desync: h('input', { type: 'checkbox', checked: j.desync }),
    lock: h('input', { type: 'checkbox', checked: j.lockAll }),
    level: h('select', { class: 't' }, [1, 3, 6, 9].map((n) => h('option', { value: n, selected: +j.compressLevel === n }, n === 1 ? '1 (fastest)' : n === 9 ? '9 (smallest)' : String(n)))),
    mode: h('select', { class: 't', onchange: () => showSched() }, [['manual', 'On demand only'], ['hourly', 'Every few hours'], ['daily', 'Daily'], ['weekly', 'Weekly'], ['monthly', 'Monthly'], ['cron', 'Cron expression']]
      .map(([v, t]) => h('option', { value: v, selected: v === sch.mode }, t))),
    time: inp({ type: 'time', value: sch.time, style: { width: '130px' } }),
    minute: inp({ type: 'number', min: 0, max: 59, value: sch.minute, style: { width: '80px' } }),
    every: inp({ type: 'number', min: 1, max: 23, value: sch.every || 1, style: { width: '80px' } }),
    day: inp({ type: 'number', min: 1, max: 31, value: sch.day, style: { width: '80px' } }),
    cron: inp({ value: sch.cron, placeholder: 'minute hour day month weekday' }),
    days: DAYS.map((d, i) => h('input', { type: 'checkbox', value: i, checked: (sch.days || []).includes(i) })),
  };
  const dbBox = h('div', { class: 'chiprow', hidden: j.databases === 'all' });
  const galeraNote = h('p', { class: 'muted small' });
  const schedBox = h('div', { class: 'pform' });
  const row = (...k) => h('div', { style: { display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' } }, ...k);
  function showSched() {
    const m = f.mode.value, parts = [];
    if (m === 'hourly') parts.push(row('every', f.every, 'hour(s), at minute', f.minute));
    if (['daily', 'weekly', 'monthly'].includes(m)) parts.push(row('at', f.time, m === 'monthly' ? ['on day', f.day] : null));
    if (m === 'weekly') parts.push(row(f.days.map((c, i) => h('label', { class: 'check' }, c, DAYS[i]))));
    if (m === 'cron') parts.push(f.cron, h('small', { class: 'muted' }, `Five fields: minute, hour, day of the month, month, day of the week. The server's time now: ${when(S.now)}.`));
    schedBox.replaceChildren(...parts);
  }
  showSched();
  const picked = new Set(j.databases === 'all' ? [] : j.databases);
  async function loadDbs() {
    if (f.some.checked) dbBox.replaceChildren(h('span', { class: 'muted small' }, 'Reading the databases from the server…'));
    try {
      const info = await api(`/api/servers/${f.server.value}/info`);
      galeraNote.textContent = info.galera ? `This server is a Galera node (${info.galera.state}, a cluster of ${info.galera.cluster_size}). Desync keeps a long dump from slowing the cluster down.` : '';
      if (!f.some.checked) return;
      const dbs = info.databases.filter((d) => !d.system);
      for (const n of picked) if (!dbs.some((d) => d.name === n)) dbs.push({ name: n, size: null });  // picked before, gone from the server now
      dbBox.replaceChildren(...dbs.map((d) => h('label', { class: 'check' },
        h('input', { type: 'checkbox', checked: picked.has(d.name), onchange: (e) => (e.target.checked ? picked.add(d.name) : picked.delete(d.name)) }),
        d.name, d.size != null ? h('span', { class: 'muted small' }, ` ${size(d.size)}`) : null)));
      if (!dbs.length) dbBox.replaceChildren(h('span', { class: 'muted small' }, 'No databases on this server besides the system ones.'));
    } catch (e) { if (f.some.checked) dbBox.replaceChildren(h('span', { class: 'warn small' }, e.message)); }
  }
  loadDbs();
  const save = async () => {
    const schedule = { mode: f.mode.value, time: f.time.value || '02:00', minute: +f.minute.value || 0, every: +f.every.value || 1,
      day: +f.day.value || 1, cron: f.cron.value, days: f.days.filter((c) => c.checked).map((c) => +c.value) };
    if (schedule.mode === 'weekly' && !schedule.days.length) throw new Error('Pick at least one day of the week');
    const json = { name: f.name.value, serverId: +f.server.value, destinationId: +f.dest.value, databases: f.all.checked ? 'all' : [...picked],
      includeUsers: f.users.checked, keep: +f.keep.value || 0, enabled: f.enabled.checked, desync: f.desync.checked, lockAll: f.lock.checked,
      compressLevel: +f.level.value, schedule };
    await api(isNew ? '/api/jobs' : `/api/jobs/${j.id}`, { method: isNew ? 'POST' : 'PUT', json });
    return true;
  };
  const del = async () => {
    if (!await confirmDialog(`Delete ${j.name}`, 'The job and its schedule go. The backups it made stay where they are.', 'Delete', true)) return undefined;
    await api(`/api/jobs/${j.id}`, { method: 'DELETE' }); return true;
  };
  const body = h('div', { class: 'pform' },
    fld('Name', f.name, 'The backup files are named after it.'),
    fld('Server', f.server), fld('Destination', f.dest),
    h('div', { class: 'field' }, h('span', null, 'What to back up'),
      h('label', { class: 'check' }, f.all, 'All the databases (new ones are picked up by themselves)'),
      h('label', { class: 'check' }, f.some, 'Only these databases'), dbBox,
      h('label', { class: 'check' }, f.users, 'Users, roles and their grants')),
    h('div', { class: 'field' }, h('span', null, 'When'), row(f.mode, h('label', { class: 'check' }, f.enabled, 'On'))), schedBox,
    fld('How many backups to keep', f.keep, 'After each good backup, the older backups of this job beyond this number are deleted from the destination. 0 keeps them all.'),
    h('details', null, h('summary', { class: 'muted' }, 'Galera and more'), galeraNote,
      h('div', { class: 'pform' },
        h('label', { class: 'check' }, f.desync, 'Galera: take this node out of flow control during the backup (wsrep_desync; the user needs SUPER)'),
        h('label', { class: 'check' }, f.lock, 'Lock every table instead of a transaction snapshot (only for MyISAM or Aria tables; blocks writes)'),
        fld('Compression', f.level))));
  const r = await dialog(isNew ? 'New backup job' : `Edit ${j.name}`, body,
    [...(isNew ? [] : [{ label: 'Delete', danger: true, value: del }]), { label: 'Cancel', value: null }, { label: isNew ? 'Make the job' : 'Save', primary: true, value: save }], true);
  if (r) { toast('Saved'); onRoute(); }
}

// ------------------------------------------------------------------ servers
async function showServers(page) {
  await loadOverview();
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Servers'),
    isAdmin() ? h('button', { class: 'pillbtn primary', onclick: () => editServer(null) }, icon('add', 's'), 'Add a server') : null),
  h('p', { class: 'muted' }, 'The MariaDB servers to back up and restore onto: the one the suite\'s apps keep their data on, and any other. For a Galera cluster, add one node (or each, to restore onto a given one).'));
  if (!S.servers.length) { page.append(h('div', { class: 'empty' }, icon('dns'), h('p', null, 'No server yet.'))); return; }
  page.append(h('div', { class: 'cards' }, S.servers.map((s) => {
    const msg = h('div', { class: 'muted small' });
    const test = async () => { msg.textContent = 'Connecting…'; try { msg.replaceChildren(serverInfoView(await api(`/api/servers/${s.id}/info`))); } catch (e) { msg.textContent = e.message; msg.className = 'warn small'; } };
    return h('div', { class: 'card' },
      h('h3', null, icon('dns'), s.name),
      h('div', { class: 'small' }, s.host ? `${s.host}${s.port ? `:${s.port}` : ''}` : (s.socket || 'the local socket'), ' · ', s.user || 'the default user', s.tls ? ' · TLS' : ''),
      msg,
      isAdmin() ? h('div', { class: 'cardbtns' }, btn('Test', test), btn('Edit', () => editServer(s))) : null);
  })));
}
function serverInfoView(info) {
  const dbs = info.databases.filter((d) => !d.system);
  return h('div', { class: 'small' },
    h('p', null, h('b', null, `Connected: MariaDB ${info.version}`)),
    info.galera ? h('p', null, `Galera node: ${info.galera.state}, a cluster of ${info.galera.cluster_size} (${info.galera.cluster_status})`) : null,
    h('p', { class: 'muted' }, `${dbs.length} database(s): ${dbs.map((d) => `${d.name} (${size(d.size)})`).join(', ')}`),
    dbs.some((d) => d.non_innodb) ? h('p', { class: 'warn' }, `Some tables are not InnoDB (${dbs.filter((d) => d.non_innodb).map((d) => d.name).join(', ')}): the transaction snapshot does not cover them${info.galera ? ', and Galera does not replicate them' : ''}.`) : null);
}
async function editServer(s) {
  const isNew = !s; s = s || {};
  const f = { name: h('input', { class: 't', value: s.name || '' }), host: h('input', { class: 't', value: s.host || '', placeholder: 'db.lan (empty: the local socket)' }),
    port: h('input', { class: 't', value: s.port || '', placeholder: '3306' }), socket: h('input', { class: 't', value: s.socket || '', placeholder: '/run/mysqld/mysqld.sock' }),
    user: h('input', { class: 't', value: s.user || '', placeholder: 'backup', autocomplete: 'off' }),
    password: h('input', { class: 't', type: 'password', autocomplete: 'new-password', placeholder: s.passwordSet ? 'unchanged' : '' }),
    tls: h('input', { type: 'checkbox', checked: !!s.tls }) };
  const result = h('div');
  const json = () => ({ id: s.id, name: f.name.value, host: f.host.value, port: f.port.value, socket: f.socket.value, user: f.user.value,
    password: f.password.value === '' && s.passwordSet ? null : f.password.value, tls: f.tls.checked });
  const suite = isNew && S.suiteServer.host ? h('p', null, h('button', { class: 'pillbtn noic tiny', onclick: () => {
    f.name.value = f.name.value || 'Suite database server'; f.host.value = S.suiteServer.host; f.port.value = S.suiteServer.port || ''; f.user.focus();
  } }, 'The suite\'s own database server'), h('span', { class: 'muted small' }, ' fills in its address; give it an account that may read every database.')) : null;
  const del = async () => {
    if (!await confirmDialog(`Remove ${s.name}`, 'Only the connection settings go; nothing on the server changes.', 'Remove', true)) return undefined;
    await api(`/api/servers/${s.id}`, { method: 'DELETE' }); return true;
  };
  const r = await dialog(isNew ? 'Add a server' : `Edit ${s.name}`, h('div', { class: 'pform' }, suite,
    fld('Name', f.name), fld('Host', f.host), fld('Port', f.port), fld('Socket (instead of a host)', f.socket), fld('User', f.user), fld('Password', f.password),
    h('label', { class: 'check' }, f.tls, 'Require TLS'),
    h('details', null, h('summary', { class: 'muted' }, 'What the user needs'),
      h('pre', { class: 'log', style: { maxHeight: 'none', whiteSpace: 'pre-wrap' } }, "CREATE USER 'backup'@'%' IDENTIFIED BY '…';\nGRANT SELECT, SHOW VIEW, TRIGGER, EVENT, LOCK TABLES,\n  SHOW DATABASES ON *.* TO 'backup'@'%';\n-- Galera desync (SET GLOBAL wsrep_desync) also needs SUPER.\n-- A restore makes databases, users and grants: restore onto a server\n-- added with an administrator's account (root…).")),
    result),
  [...(isNew ? [] : [{ label: 'Remove', danger: true, value: del }]), { label: 'Cancel', value: null },
    { label: 'Test', value: async () => { result.replaceChildren(h('p', { class: 'muted small' }, 'Connecting…')); try { result.replaceChildren(serverInfoView(await api('/api/servers/test', { method: 'POST', json: json() }))); } catch (e) { result.replaceChildren(h('p', { class: 'warn small' }, e.message)); } return undefined; } },
    { label: 'Save', primary: true, value: async () => { await api(isNew ? '/api/servers' : `/api/servers/${s.id}`, { method: isNew ? 'POST' : 'PUT', json: json() }); return true; } }], true);
  if (r) { toast('Saved'); onRoute(); }
}

// ------------------------------------------------------------------ destinations
async function showDestinations(page) {
  await loadOverview();
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Destinations'),
    isAdmin() ? h('button', { class: 'pillbtn primary', onclick: () => editDest(null) }, icon('add', 's'), 'Add a destination') : null),
  h('p', { class: 'muted' }, 'Where backups are kept: a folder on this machine (or a disk mounted there) or Google Drive. Each backup is one .mdbk.tar file.'));
  if (!S.destinations.length) { page.append(h('div', { class: 'empty' }, icon('folder'), h('p', null, 'No destination yet.'))); return; }
  page.append(h('div', { class: 'cards' }, S.destinations.map((d) => {
    const msg = h('div', { class: 'muted small' });
    const test = async () => { msg.textContent = 'Testing…'; try { msg.textContent = (await api(`/api/destinations/${d.id}/test`, { method: 'POST' })).message; msg.className = 'small'; } catch (e) { msg.textContent = e.message; msg.className = 'warn small'; } };
    const g = d.kind === 'gdrive';
    return h('div', { class: 'card' },
      h('h3', null, icon(g ? 'cloud' : 'folder'), d.name, h('span', { class: 'muted small' }, g ? ' Google Drive' : ' Folder')),
      h('div', { class: 'small' }, g ? (d.folderId ? `folder ${d.folderId}` : `folder “${d.folderName}”`) : d.path),
      g ? h('div', { class: d.signedIn ? 'muted small' : 'warn small' }, d.signedIn ? (d.auth === 'service_account' ? 'Service account' : `Signed in${d.account ? ` as ${d.account}` : ''}`) : 'Not signed in') : null,
      msg,
      h('div', { class: 'cardbtns' }, h('a', { class: 'pillbtn noic', href: `#/backups/${d.id}` }, 'Backups'),
        isAdmin() && g && d.auth !== 'service_account' ? btn(d.signedIn ? 'Sign in again' : 'Sign in with Google', () => googleSignIn(d), d.signedIn ? '' : 'primary') : null,
        isAdmin() ? btn('Test', test) : null, isAdmin() ? btn('Edit', () => editDest(d)) : null));
  })));
}
async function editDest(d) {
  const isNew = !d; d = d || { kind: 'local', path: S.backupDir, auth: 'oauth', folderName: 'ioBackup' };
  const f = { name: h('input', { class: 't', value: d.name || '' }),
    kind: h('select', { class: 't', onchange: () => show() }, h('option', { value: 'local', selected: d.kind === 'local' }, 'A folder'), h('option', { value: 'gdrive', selected: d.kind === 'gdrive' }, 'Google Drive')),
    path: h('input', { class: 't', value: d.path || S.backupDir }),
    auth: h('select', { class: 't', onchange: () => show() }, h('option', { value: 'oauth', selected: d.auth !== 'service_account' }, 'My Google account (sign in with a code)'),
      h('option', { value: 'service_account', selected: d.auth === 'service_account' }, 'A service account (Shared Drive)')),
    clientId: h('input', { class: 't', value: d.clientId || '' }),
    clientSecret: h('input', { class: 't', type: 'password', placeholder: d.clientSecretSet ? 'unchanged' : '', autocomplete: 'off' }),
    folderName: h('input', { class: 't', value: d.folderName || 'ioBackup' }),
    folderId: h('input', { class: 't', value: d.folderId || '', placeholder: 'from the folder\'s address in Drive' }),
    sa: h('textarea', { class: 't', rows: 4, placeholder: d.serviceAccountSet ? '(a key is kept; paste a new one to replace it)' : '{ "type": "service_account", … }' }) };
  const box = h('div', { class: 'pform' });
  function show() {
    if (f.kind.value === 'local') { box.replaceChildren(fld('Folder on this machine', f.path, 'Made when it is missing. In Docker, mount a volume there (the image uses /backups).')); return; }
    const oauth = f.auth.value !== 'service_account';
    box.replaceChildren(fld('Sign in with', f.auth), ...(oauth ? [
      h('p', { class: 'muted small' }, 'Once, in your own Google Cloud project: turn on the Google Drive API and make an OAuth client ID of the type “TVs and Limited Input devices”; give its ID and secret here. After saving, Sign in with Google. ioBackup only sees the files it makes itself (drive.file).'),
      fld('OAuth client ID', f.clientId), fld('OAuth client secret', f.clientSecret), fld('Folder name in your Drive', f.folderName, 'Made on first use.')] : [
      h('p', { class: 'muted small' }, 'Make a service account and a JSON key, add the service account to a Shared Drive as a Content manager, and give the ID of a folder in it. A service account has no storage of its own: a folder in a My Drive does not work.'),
      fld('Service account key (JSON)', f.sa), fld('Folder ID', f.folderId)]));
  }
  show();
  const del = async () => {
    if (!await confirmDialog(`Remove ${d.name}`, 'Only the settings go; the backup files stay where they are.', 'Remove', true)) return undefined;
    await api(`/api/destinations/${d.id}`, { method: 'DELETE' }); return true;
  };
  const r = await dialog(isNew ? 'Add a destination' : `Edit ${d.name}`, h('div', { class: 'pform' }, fld('Name', f.name), fld('Kind', f.kind), box),
    [...(isNew ? [] : [{ label: 'Remove', danger: true, value: del }]), { label: 'Cancel', value: null },
      { label: 'Save', primary: true, value: () => api(isNew ? '/api/destinations' : `/api/destinations/${d.id}`, { method: isNew ? 'POST' : 'PUT', json: {
        name: f.name.value, kind: f.kind.value, path: f.path.value, auth: f.auth.value, clientId: f.clientId.value, folderName: f.folderName.value, folderId: f.folderId.value,
        clientSecret: f.clientSecret.value || (d.clientSecretSet ? null : ''), serviceAccount: f.sa.value || (d.serviceAccountSet ? null : '') } }) }], true);
  if (!r) return;
  toast('Saved');
  await onRoute();
  if (r.id && r.kind === 'gdrive' && r.auth !== 'service_account' && !r.signedIn) googleSignIn(r);
}
async function googleSignIn(d) {
  const out = h('div', null, h('p', { class: 'muted' }, 'Asking Google for a code…'));
  let open = true;
  dialog('Sign in with Google', out, [{ label: 'Close', value: null }]).then(() => { open = false; });
  let flow;
  try { flow = await api(`/api/destinations/${d.id}/google`, { method: 'POST' }); } catch (e) { out.replaceChildren(h('p', { class: 'warn' }, e.message)); return; }
  const status = h('p', { class: 'muted' }, 'Waiting for you to approve…');
  out.replaceChildren(h('p', null, 'Open ', h('a', { class: 'lnk', href: flow.url, target: '_blank', rel: 'noopener' }, flow.url), ' on any device and type:'),
    h('p', { style: { fontSize: '28px', fontWeight: 600, letterSpacing: '3px', textAlign: 'center' } }, flow.code), status);
  const tick = async () => {
    if (!open) return;
    try {
      const st = await api(`/api/google/${flow.id}`);
      if (st.status === 'ok') { status.className = ''; status.textContent = 'Signed in: backups can go to Google Drive now.'; onRoute(); return; }
      if (st.status !== 'pending') { status.className = 'warn'; status.textContent = st.error || `The sign-in ${st.status === 'denied' ? 'was refused' : 'ran out of time'}.`; return; }
    } catch (e) { status.textContent = e.message; }
    setTimeout(tick, 2500);
  };
  setTimeout(tick, 2500);
}

// ------------------------------------------------------------------ backups
async function showBackups(page, r) {
  await loadOverview();
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Backups')));
  if (!S.destinations.length) { page.append(h('div', { class: 'empty' }, icon('folder'), h('p', null, 'No destination yet.'))); return; }
  let did = +r.id || +(sessionStorage.getItem('iobackup.dest') || 0);
  if (!byId(S.destinations, did)) did = S.destinations[0].id;
  try { sessionStorage.setItem('iobackup.dest', String(did)); } catch { /* */ }
  const d = byId(S.destinations, did);
  if (S.destinations.length > 1) {
    page.querySelector('.pagehead').append(h('select', { class: 't', style: { width: 'auto' }, onchange: (e) => { location.hash = `#/backups/${e.target.value}`; } },
      S.destinations.map((x) => h('option', { value: x.id, selected: x.id === did }, x.name))));
  }
  const list = h('div', null, h('p', { class: 'muted' }, d.kind === 'gdrive' ? 'Reading the Google Drive folder…' : 'Reading the folder…'));
  page.append(list);
  try {
    const { items, free } = await api(`/api/destinations/${did}/backups`);
    const total = items.reduce((a, b) => a + b.size, 0);
    const base = (b) => `/api/destinations/${did}/backups/${encodeURIComponent(b.name)}`;
    list.replaceChildren(h('p', { class: 'muted' }, `${items.length} backup(s) in ${d.name}, ${size(total)}${free != null ? ` · ${size(free)} free` : ''}`),
      !items.length ? h('div', { class: 'empty' }, icon('backup'), h('p', null, 'No backup here yet.')) :
        h('div', { class: 'tablewrap' }, h('table', { class: 't' }, h('tr', null, h('th', null, 'Backup'), h('th', null, 'Taken'), h('th', null, 'Size'), h('th', null)),
          items.map((b) => h('tr', null,
            h('td', null, h('b', null, b.label || '?'), h('div', { class: 'muted small' }, b.name)),
            h('td', null, when(b.created)), h('td', null, size(b.size)),
            h('td', { style: { whiteSpace: 'nowrap', textAlign: 'right' } },
              isAdmin() ? h('a', { class: 'pillbtn noic primary tiny', href: `#/restore/${did}/${encodeURIComponent(b.name)}` }, 'Restore…') : null, ' ',
              canEdit() ? h('button', { class: 'pillbtn noic tiny', onclick: async (ev) => {
                const el = ev.currentTarget; el.disabled = true; el.textContent = 'Checking…';
                try { const v = await api(`${base(b)}/verify`, { method: 'POST' }); toast(v.problems.length ? `${v.problems.length} problem(s): ${v.problems[0]}` : `${v.files} files, every checksum matches`); } catch (e) { fail(e); }
                el.disabled = false; el.textContent = 'Verify';
              } }, 'Verify') : null, ' ',
              isAdmin() ? h('a', { class: 'pillbtn noic tiny', href: `${base(b)}/download` }, 'Download') : null, ' ',
              isAdmin() ? h('button', { class: 'pillbtn noic danger tiny', onclick: async () => {
                if (!await confirmDialog(`Delete ${b.name}`, `The backup file is deleted from ${d.name}. This cannot be undone.`, 'Delete', true)) return;
                try { await api(base(b), { method: 'DELETE' }); onRoute(); } catch (e) { fail(e); }
              } }, 'Delete') : null))))));
  } catch (e) { fail2(list)(e); }
}

// ------------------------------------------------------------------ restore
async function showRestore(page, r) {
  await loadOverview();
  const did = +r.id, name = r.name, d = byId(S.destinations, did);
  page.append(h('div', { class: 'pagehead' }, h('a', { class: 'iconbtn', href: `#/backups/${did}`, title: 'Back to the backups' }, icon('back')), h('h1', null, 'Restore')));
  const wrap = h('div', null, h('p', { class: 'muted' }, d && d.kind === 'gdrive' ? 'Downloading the backup from Google Drive and reading it (a big one takes a while)…' : 'Reading the backup…'));
  page.append(wrap);
  let c;
  try { c = await api(`/api/destinations/${did}/backups/${encodeURIComponent(name)}`); } catch (e) { fail2(wrap)(e); return; }
  wrap.replaceChildren(restoreForm(did, name, c));
}
function restoreForm(did, name, c) {
  const dbState = c.databases.map((db) => {
    const objs = [...db.tables.map((t) => ['table', t]), ...db.views.map((v) => ['view', v]), ...(db.routines ? [['routines', null]] : []), ...(db.events ? [['events', null]] : [])];
    const st = { db, objs, on: h('input', { type: 'checkbox' }),
      mode: h('select', { class: 't', style: { width: 'auto' } }, h('option', { value: 'all' }, 'everything'), h('option', { value: 'some' }, 'pick tables…')),
      target: h('input', { class: 't', value: db.name, title: 'Restore under this database name', style: { width: '180px' } }),
      checks: objs.map(() => h('input', { type: 'checkbox', checked: true })) };
    st.box = h('div', { class: 'chiprow', hidden: true, style: { margin: '6px 0 0 26px' } }, objs.map((o, i) => h('label', { class: 'check' }, st.checks[i],
      o[1] || (o[0] === 'routines' ? 'procedures and functions' : 'events'), o[1] ? h('span', { class: 'muted small' }, ` ${o[0]}`) : null)));
    st.mode.onchange = () => { st.box.hidden = st.mode.value !== 'some'; };
    st.on.onchange = () => { st.mode.disabled = st.target.disabled = !st.on.checked; if (!st.on.checked) st.box.hidden = true; else st.mode.onchange(); };
    st.on.onchange();
    return st;
  });
  const accts = [...c.accounts.roles.map((n) => ({ kind: 'role', name: n, system: false })),
    ...c.accounts.users.filter((u) => !u.system).map((u) => ({ kind: 'user', name: u.name, system: false })),
    ...c.accounts.users.filter((u) => u.system).map((u) => ({ kind: 'user', name: u.name, system: true }))].map((a) => ({ ...a, cb: h('input', { type: 'checkbox' }) }));
  const server = h('select', { class: 't' }, S.servers.map((s) => h('option', { value: s.id }, s.name)));
  const opt = { schema: h('input', { type: 'checkbox' }), replace: h('input', { type: 'checkbox' }), force: h('input', { type: 'checkbox' }) };
  const plan = () => {
    const p = { databases: [], roles: [], users: [], schema_only: opt.schema.checked, replace_users: opt.replace.checked, force: opt.force.checked };
    for (const s of dbState) {
      if (!s.on.checked) continue;
      const objects = s.mode.value === 'all' ? null : s.objs.filter((o, i) => s.checks[i].checked);
      if (objects && !objects.length) continue;
      p.databases.push({ name: s.db.name, target: s.target.value.trim() || s.db.name, objects });
    }
    for (const a of accts) if (a.cb.checked) (a.kind === 'role' ? p.roles : p.users).push(a.name);
    return p;
  };
  const base = `/api/destinations/${did}/backups/${encodeURIComponent(name)}`;
  async function review() {
    const p = plan();
    if (!p.databases.length && !p.roles.length && !p.users.length) { toast('Pick something to restore'); return; }
    const target = server.selectedOptions[0].text;
    let pv;
    try { pv = await api(`${base}/preview`, { method: 'POST', json: { serverId: +server.value, plan: p } }); } catch (e) { fail(e); return; }
    const ok = await dialog(`Restore onto ${target}?`, h('div', null,
      h('p', { class: 'muted small' }, `MariaDB ${pv.version}${pv.galera ? ` · a Galera node (${pv.galera.state}): everything restored replicates to the whole cluster` : ''}`),
      h('ul', null, pv.lines.map((l) => h('li', null, l))),
      pv.warnings.length ? h('div', null, h('p', { class: 'warn' }, h('b', null, 'On the target server:')), h('ul', null, pv.warnings.map((w) => h('li', { class: 'warn' }, w)))) : null),
    [{ label: 'Cancel', value: null }, { label: 'Restore now', danger: true, value: () => api(`${base}/restore`, { method: 'POST', json: { serverId: +server.value, plan: p } }) }], true);
    if (ok) location.hash = `#/run/${ok.runId}`;
  }
  const allDbs = btn('All', () => dbState.forEach((s) => { s.on.checked = true; s.on.onchange(); }), 'tiny');
  const allUsers = btn('All but the system accounts', () => accts.forEach((a) => { a.cb.checked = !a.system; }), 'tiny');
  return h('div', null,
    h('div', { class: 'box' }, h('h2', null, icon('backup'), c.label || c.name),
      h('p', { class: 'muted small' }, `Taken ${when(c.created)} from ${c.source} · MariaDB ${c.server_version}${c.galera ? ' · Galera' : ''} · ${c.consistency}`),
      h('p', { class: 'muted small' }, name)),
    h('div', { class: 'box' }, h('h2', null, icon('dns'), 'Databases', c.databases.length ? h('span', { style: { marginLeft: 'auto' } }, allDbs) : null),
      !c.databases.length ? h('p', { class: 'muted' }, 'This backup holds no database.') :
        dbState.map((s) => h('div', { style: { padding: '8px 0', borderBottom: '1px solid var(--line)' } },
          h('div', { style: { display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' } }, h('label', { class: 'check' }, s.on, h('b', null, s.db.name)),
            h('span', { class: 'muted small' }, `${s.db.tables.length} tables, ${s.db.views.length} views · ${size(s.db.bytes)}`), s.mode, h('span', { class: 'muted small' }, 'as'), s.target), s.box))),
    h('div', { class: 'box' }, h('h2', null, icon('person'), 'Users, roles and grants', accts.length ? h('span', { style: { marginLeft: 'auto' } }, allUsers) : null),
      !c.has_accounts ? h('p', { class: 'muted' }, 'This backup was taken without the users.') :
        h('div', { class: 'chiprow' }, accts.map((a) => h('label', { class: 'check' }, a.cb, a.name, h('span', { class: 'muted small' }, ` ${a.kind}`), a.system ? h('span', { class: 'warn small' }, ' system') : null))),
      c.has_accounts ? h('p', { class: 'muted small' }, 'Grants are restored after the databases, so grants on restored tables and procedures apply cleanly. Passwords come back as their stored hashes.') : null),
    h('div', { class: 'box' }, h('h2', null, icon('restore'), 'Restore onto'),
      h('div', { class: 'pform' }, S.servers.length ? server : h('p', { class: 'warn' }, 'Add a server first.'),
        h('label', { class: 'check' }, opt.schema, 'The structure only (no rows)'),
        h('label', { class: 'check' }, opt.replace, 'Replace the users that exist already (password and settings); otherwise they are kept and only grants are added'),
        h('label', { class: 'check' }, opt.force, 'Carry on past SQL errors'),
        h('p', { class: 'muted small' }, 'Restored tables and views replace those of the same name in the target database; nothing else in it is touched. Stop the apps whose database you restore over, and start them again after.'),
        h('p', null, h('button', { class: 'pillbtn primary noic', disabled: !S.servers.length, onclick: review }, 'Review the restore…')))));
}

// ------------------------------------------------------------------ activity
function runsTable(runs) {
  if (!runs.length) return h('div', { class: 'empty' }, icon('history'), h('p', null, 'Nothing has run yet.'));
  return h('div', { class: 'tablewrap' }, h('table', { class: 't' }, h('tr', null, h('th', null, 'What'), h('th', null, 'Status'), h('th', null, 'Started'), h('th', null, 'Took'), h('th', null, 'Result')),
    runs.map((r) => h('tr', { class: 'click', onclick: () => { location.hash = `#/run/${r.id}`; } },
      h('td', null, h('b', null, r.title), h('div', { class: 'muted small' }, r.trigger === 'schedule' ? 'scheduled' : (r.user ? `by ${r.user}` : 'by hand'))),
      h('td', null, pill(r.status)), h('td', null, when(r.started || r.queued)), h('td', null, dur(r.started, r.finished)),
      h('td', { class: 'muted small' }, r.status === 'ok' && r.result && r.result.size ? `${size(r.result.size)}${r.result.pruned && r.result.pruned.length ? `, ${r.result.pruned.length} older removed` : ''}`
        : (r.status === 'failed' ? r.last.replace(/^\S+ /, '') : ''))))));
}
async function showActivity(page) {
  const { items } = await api('/api/runs?limit=200');
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Activity')), runsTable(items));
  if (items.some((r) => ['running', 'queued'].includes(r.status))) pollTimer = setTimeout(onRoute, 4000);
}
async function showRun(page, r) {
  const run = await api(`/api/runs/${r.id}`);
  const active = ['queued', 'running'].includes(run.status);
  page.append(h('div', { class: 'pagehead' }, h('a', { class: 'iconbtn', href: '#/activity', title: 'Activity' }, icon('back')), h('h1', null, run.title), pill(run.status),
    active && canEdit() ? h('button', { class: 'pillbtn noic danger', onclick: async () => { try { await api(`/api/runs/${run.id}/cancel`, { method: 'POST' }); onRoute(); } catch (e) { fail(e); } } }, 'Cancel') : null),
  h('p', { class: 'muted' }, `${run.trigger === 'schedule' ? 'Scheduled' : `Started by ${run.user || 'hand'}`} · queued ${when(run.queued)}${run.finished ? ` · took ${dur(run.started, run.finished)}` : ''}`),
  run.status === 'ok' && run.kind === 'backup' && run.result ? h('p', null, `Backup ${run.result.file} (${size(run.result.size)}) stored. `, h('a', { class: 'lnk', href: `#/backups/${run.result.destinationId}` }, 'See the backups')) : null,
  run.log.length ? h('pre', { class: 'runlog' }, run.log.map((l) => h('div', { class: /FAILED|error/.test(l) ? 'e' : /warning|note:/.test(l) ? 'w' : '' }, l))) : h('p', { class: 'muted' }, 'Waiting to start…'));
  if (active) pollTimer = setTimeout(onRoute, 1500);
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
    let theme = 'system'; try { theme = localStorage.getItem('iobackup.theme') || 'system'; } catch { /* */ }
    menu = h('div', { class: 'menu' },
      h('div', { class: 'who' }, h('b', null, S.user.displayName), h('div', { class: 'muted small' }, `${S.user.name} · ${S.user.role}`)),
      h('a', { class: 'mi', href: '#/settings/account', onclick: closeMenu }, icon('person', 's'), 'Account'),
      h('button', { class: 'mi', onclick: () => { const n = { system: 'light', light: 'dark', dark: 'system' }[theme]; applyTheme(n); closeMenu(); toast(`Appearance: ${n}`); } },
        icon('theme', 's'), `Appearance: ${theme}`),
      h('a', { class: 'mi', href: '#/settings', onclick: closeMenu }, icon('settings', 's'), 'Settings'),
      h('button', { class: 'mi', onclick: async () => { const r = await api('/api/auth/logout', { method: 'POST' }); if (r && r.cloudflareLogout) location.href = r.cloudflareLogout; else location.reload(); } }, icon('logout', 's'), 'Sign out'));
    m.append(menu);
    setTimeout(() => document.addEventListener('click', outside), 0);
  };
  m.append(btn);
}
/* The suite (iosuite-shared's suite_apps): when other ioThing apps are registered, the app mark opens a menu of them. */
async function loadSuite() {
  try { const r = await api('/api/auth/suite'); S.suite = (r.items || []).filter((a) => a.app !== r.app && a.url); } catch { S.suite = []; }
  const b = $('#suitebtn');
  if (b) { b.hidden = !S.suite.length; b.onclick = () => toggleSuite(b); }
  drawNav();
}
let suitePop = null;
function closeSuite() {
  if (!suitePop) return;
  suitePop.remove(); suitePop = null;
  document.removeEventListener('click', suiteOutside, true);
}
function suiteOutside(e) { if (suitePop && !suitePop.contains(e.target) && !e.target.closest('.suitebtn')) closeSuite(); }
function appTile(a) {
  const mark = (a.name || a.app).replace(/^io(?=[A-Z])/, '').slice(0, 1).toUpperCase();
  const fallback = () => h('span', { class: 'appic fb', style: { background: a.color || 'var(--brand)' } }, mark);
  const ic = a.icon ? h('img', { class: 'appic', src: a.icon, alt: '', onerror: (e) => e.currentTarget.replaceWith(fallback()) }) : fallback();
  return h('a', { class: 'apptile', href: a.url, role: 'menuitem', title: a.description || a.name, onclick: closeSuite }, ic, h('span', { class: 'appnm' }, a.name || a.app));
}
function toggleSuite(btn) {
  if (suitePop) { closeSuite(); return; }
  if (!S.suite.length) return;
  // the apps, then (for their admins only: the server sends them to nobody else) the admin tools, apart
  const apps = S.suite.filter((a) => !a.adminTool), tools = S.suite.filter((a) => a.adminTool);
  suitePop = h('div', { class: 'suitepop', role: 'menu', 'aria-label': 'ioThing apps', style: { '--cols': String(Math.min(3, Math.max(apps.length, tools.length))) } },
    ...apps.map(appTile), ...(tools.length ? [h('div', { class: 'suitesec' }, 'Admin tools'), ...tools.map(appTile)] : []));
  document.body.append(suitePop);
  const r = btn.getBoundingClientRect();
  suitePop.style.top = `${Math.round(r.bottom + 6)}px`;
  suitePop.style.left = `${Math.round(Math.max(8, Math.min(r.left - 6, innerWidth - suitePop.offsetWidth - 8)))}px`;
  setTimeout(() => document.addEventListener('click', suiteOutside, true), 0);
}
function applyTheme(choice) {
  try { if (choice) localStorage.setItem('iobackup.theme', choice); } catch { /* private mode */ }
  let t = choice; try { t = t || localStorage.getItem('iobackup.theme'); } catch { /* */ }
  t = t || 'system';
  if (t === 'system') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
  if (choice && S.user) saveSettings({ theme: choice });
}

/* The sidebar: jobs, backups, activity, servers, destinations, Settings. Docked beside the page on a wide screen,
   sliding over it otherwise, a bottom bar on a phone. */
const DOCK_MIN = 1100;
function drawNav() {
  const nav = $('#nav'); if (!S.user) return;
  const r = route();
  const link = (v, href, ic, label, n, on, hueVar) => h('a', { href, 'data-v': v, class: on ? 'on' : '', style: hueVar ? { '--hue': `var(${hueVar})` } : null },
    icon(ic), h('span', { class: 'nl' }, label), n ? h('span', { class: 'n' }, n) : null);
  const brandName = h('span', { class: 'brand-name' }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Backup'));
  const running = S.busy ? '…' : null;
  nav.replaceChildren(...[
    h('div', { class: 'navhead' },
      S.suite.length
        ? h('div', { class: 'brand' }, h('button', { class: 'suitebtn', title: 'ioThing apps', 'aria-label': 'ioThing apps', onclick: (e) => toggleSuite(e.currentTarget) },
          h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' })), h('a', { class: 'brand-name', href: '#/' }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Backup')))
        : h('a', { class: 'brand', href: '#/' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }), brandName),
      h('button', { id: 'sidebtn', class: 'iconbtn', onclick: sidebarButton })),
    link('jobs', '#/', 'job', 'Jobs', S.jobs.length || null, r.view === 'jobs', '--c-orange'),
    link('backups', '#/backups', 'backup', 'Backups', null, ['backups', 'restore'].includes(r.view), '--c-blue'),
    link('activity', '#/activity', 'history', 'Activity', running, ['activity', 'run'].includes(r.view), '--c-slate'),
    h('button', { class: 'navmore', 'data-v': 'more', title: 'More', onclick: moreSheet }, icon('more'), h('span', { class: 'nl' }, 'More')),
    h('div', { class: 'navgap' }),
    link('servers', '#/servers', 'dns', 'Servers', S.servers.length || null, r.view === 'servers', '--c-indigo'),
    link('destinations', '#/destinations', 'folder', 'Destinations', S.destinations.length || null, r.view === 'destinations', '--c-teal'),
    h('div', { class: 'navfoot' }, link('settings', '#/settings', 'settings', 'Settings', null, r.view === 'settings')),
  ].flat(3).filter(Boolean));
  applySidebar();
  $('.navmore')?.classList.toggle('on', ['servers', 'destinations', 'settings'].includes(r.view));
}
function sideDockedPref() { try { return localStorage.getItem('iobackup.sidebar') !== '0'; } catch { return true; } }
function applySidebar() {
  const body = document.body, btn = $('#sidebtn');
  const docked = innerWidth >= DOCK_MIN && sideDockedPref();
  body.classList.toggle('side-docked', docked);
  if (docked) closeNav();
  if (!btn) return;
  const [ic, title] = docked ? ['menuOpen', 'Hide the sidebar'] : innerWidth >= DOCK_MIN ? ['pin', 'Keep the sidebar open'] : ['close', 'Close the sidebar'];
  btn.replaceChildren(icon(ic)); btn.title = title; btn.setAttribute('aria-label', title);
}
function sidebarButton() {
  if (document.body.classList.contains('side-docked')) { try { localStorage.setItem('iobackup.sidebar', '0'); } catch { /* */ } }
  else if (innerWidth >= DOCK_MIN) { try { localStorage.setItem('iobackup.sidebar', '1'); } catch { /* */ } }
  else { closeNav(); return; }
  applySidebar();
}
function openNav() { document.body.classList.add('side-open'); $('#navscrim').hidden = false; }
function closeNav() { document.body.classList.remove('side-open'); $('#navscrim').hidden = true; }
function moreSheet() {
  const tile = (href, ic, label, hueV) => h('a', { href, style: { '--hue': hueV } }, h('span', { class: 'sic' }, icon(ic)), h('span', null, label));
  const grid = h('div', { class: 'sheetgrid' }, tile('#/servers', 'dns', 'Servers', 'var(--c-indigo)'), tile('#/destinations', 'folder', 'Destinations', 'var(--c-teal)'),
    tile('#/settings', 'settings', 'Settings', 'var(--c-slate)'));
  grid.addEventListener('click', (e) => { if (e.target.closest('a')) closeDialogs(); });
  return dialog('More', grid, [{ label: 'Close', value: null }]);
}


// ------------------------------------------------------------------ routes
function route() {
  const p = location.hash.replace(/^#\/?/, '').split('?')[0].split('/').map(decodeURIComponent);
  const [a, b, c] = p;
  if (!a) return { view: 'jobs' };
  if (a === 'backups') return { view: 'backups', id: b };
  if (a === 'restore') return { view: 'restore', id: b, name: c };
  if (a === 'run') return { view: 'run', id: b };
  if (['servers', 'destinations', 'activity'].includes(a)) return { view: a };
  if (a === 'settings') return { view: 'settings', tab: b || 'account', sub: c };
  return { view: 'jobs' };
}
async function onRoute() {
  clearTimeout(pollTimer); pollTimer = null;
  const r = route();
  const main = $('#main');
  const page = h('div', { class: 'page' });
  const fresh = location.hash !== main.dataset.at;
  if (fresh) main.dataset.at = location.hash;
  const keep = main.scrollTop;
  try {
    await ({ jobs: showJobs, backups: showBackups, restore: showRestore, run: showRun, servers: showServers, destinations: showDestinations,
      activity: showActivity, settings: showSettings })[r.view](page, r);
  } catch (e) { page.append(h('p', { class: 'warn' }, e.message)); }
  main.replaceChildren(page);  // drawn whole, then shown: a page polled while something runs does not flicker
  main.scrollTop = fresh ? 0 : keep;
  if (r.view === 'run' && !fresh) { const lg = page.querySelector('.runlog'); if (lg) main.scrollTop = main.scrollHeight; }
  drawNav();
}

// ------------------------------------------------------------------ settings
const SUITE_TABS = { security: 'Security', global: 'Global settings' };
async function showSettings(page, r) {
  const tabs = [['account', 'Account'], ['display', 'Display'], ...(isAdmin() ? [['server', 'Server']] : []),
    ...(S.user.suiteAdmin ? [['security', SUITE_TABS.security], ['global', SUITE_TABS.global]] : [])];
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Settings')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/settings/${k}`; } }, l))));
  const body = h('div'); page.append(body);
  await ({ account: setAccount, display: setDisplay, server: setServer, security: setSuite, global: setSuite }[r.tab] || setAccount)(body, r);
}
const accountUi = () => import(new URL('api/auth/ui.js', document.baseURI).href);
async function setAccount(el) {
  const ui = await accountUi();
  const pw = h('div');
  await ui.mountAccount(el, { toast, onSaved: (u) => { Object.assign(S.user, u); drawUser(); } });
  el.append(pw);
  await ui.mountAppPasswords(pw, { toast });
}
async function setDisplay(el) {
  const ui = await accountUi();
  let t = 'system'; try { t = localStorage.getItem('iobackup.theme') || 'system'; } catch { /* */ }
  el.append(ui.box('theme', 'Appearance', ui.themeRow(S.settings.theme || t, (x) => { S.settings.theme = x; applyTheme(x); })));
}
async function setSuite(el, r) {
  let ui;
  try { ui = await import(new URL('api/suite-admin/ui.js', document.baseURI).href); } catch (e) { el.append(h('p', { class: 'warn' }, `The panel did not load: ${e.message}`)); return; }
  await ui.mount(el, { tab: r.tab, sub: r.sub, toast, onSub: (x) => history.replaceState(null, '', `#/settings/${r.tab}/${x}`) });
}
const serverUi = () => import(new URL('api/server/ui.js', document.baseURI).href);
async function setServer(el) {
  const panel = h('div'); el.append(panel);
  try { await (await serverUi()).mount(panel, { toast }); } catch (e) { panel.append(h('p', { class: 'warn' }, `The Server panel did not load: ${e.message}`)); }
}
function updateBanner() {
  $('#updbanner')?.remove();
  const u = S.status && S.status.update;
  let dismissed = null; try { dismissed = localStorage.getItem('iobackup.updateDismissed'); } catch { /* */ }
  if (!u || dismissed === u.remote) return;
  const b = h('div', { id: 'updbanner', role: 'status' }, icon('update'),
    h('span', null, `ioBackup ${u.version ? `v${u.version}` : 'update'} is available${u.message ? `: ${u.message.replace(/^v\d+\.\d+\.\d+:\s*/, '')}` : ''}`),
    h('button', { class: 'pillbtn primary noic', onclick: async () => { if (await confirmDialog('Update ioBackup', 'Install the new version and restart? The page reloads when it is back.', 'Update now')) { b.remove(); (await serverUi()).runUpdate({ toast }); } } }, 'Update now'),
    h('a', { class: 'pillbtn noic', href: '#/settings/server', onclick: () => b.remove() }, 'Details'),
    h('button', { class: 'iconbtn', title: 'Not now', onclick: () => { try { localStorage.setItem('iobackup.updateDismissed', u.remote); } catch { /* */ } b.remove(); } }, icon('close', 's')));
  document.body.append(b);
}

// ------------------------------------------------------------------ sign-in
function showSignIn() {
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
    h('div', { class: 'brand' }, h('img', { src: 'static/icons/mark.svg', alt: '', class: 'brand-mark' }), h('span', { class: 'brand-name', style: { display: 'inline' } }, h('span', { class: 'io' }, 'io'), h('span', { class: 'nm' }, 'Backup'))),
    first ? h('p', { class: 'muted' }, 'Welcome. Make the first account: it is the admin. (Already use another io app? Sign in there first: the apps share their accounts.)') : h('h2', null, 'Sign in'),
    tiles, form, err, h('div', { class: 'btns' }, btn))));
  if (first) { name.focus(); return; }
  const pick = (t) => tiles.querySelectorAll('.account').forEach((x) => x.classList.toggle('on', x === t));
  api('/api/auth/accounts').then((d) => {
    if (!d.accounts.length) { name.focus(); return; }
    form.hidden = true; btn.hidden = true;
    tiles.append(...d.accounts.map((a) => {
      const t = h('button', { type: 'button', class: 'account', onclick: () => {
        pick(t);
        if (a.passwordless) { login(a.name, ''); return; }
        name.value = a.name; name.hidden = true; form.hidden = false; btn.hidden = false; pw.value = ''; pw.focus();
      } }, h('span', { class: 'av big', style: { '--h': hue(a.displayName || a.name) } }, initials(a.displayName || a.name)), h('span', { class: 'nm' }, a.displayName || a.name), a.passwordless ? null : h('span', { class: 'muted small' }, 'password'));
      return t;
    }), h('button', { type: 'button', class: 'account', onclick: (e) => { pick(e.currentTarget); name.value = ''; name.hidden = false; form.hidden = false; btn.hidden = false; name.focus(); } },
      h('span', { class: 'av big other' }, '…'), h('span', { class: 'nm' }, 'Other')));
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
  if (S.settings.theme) { try { localStorage.setItem('iobackup.theme', S.settings.theme); } catch { /* */ } applyTheme(); }
  drawUser();
  await loadOverview();
  $('#menubtn').onclick = openNav;
  $('#navscrim').onclick = closeNav;
  $('#nav').addEventListener('click', (e) => { if (e.target.closest('a') && !document.body.classList.contains('side-docked')) closeNav(); });
  addEventListener('resize', applySidebar);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { if (document.querySelector('.dialog-back')) closeDialogs(); else if (document.body.classList.contains('side-open')) closeNav(); return; }
  });
  addEventListener('hashchange', onRoute);
  await onRoute();
  loadSuite();
  updateBanner();
  setInterval(async () => { try { S.status = await api('/api/status'); updateBanner(); } catch { /* restarting */ } }, 15 * 60 * 1000);
}
start().catch(fail);
