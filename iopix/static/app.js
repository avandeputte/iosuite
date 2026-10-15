// digiKam Viewer front end. No build step: plain ES module.

// ---------------------------------------------------------------- helpers
const $ = (s, r = document) => r.querySelector(s);
const ICONS = {
  search: 'M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z',
  disk: 'M2 20h20v-4H2v4zm2-3h2v2H4v-2zM2 4v4h20V4H2zm4 3H4V5h2v2zm-4 7h20v-4H2v4zm2-3h2v2H4v-2z',
  share: 'M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92s2.92-1.31 2.92-2.92-1.31-2.92-2.92-2.92z',
  gear: 'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z',
  wrench: 'M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6 6 9 1.6 4.7C.4 7.1.9 10.1 2.9 12.1c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.3-2.3c.5-.4.5-1.1.1-1.4z',
  close: 'M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z',
  back: 'M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z',
  left: 'M15.41 7.41 14 6l-6 6 6 6 1.41-1.41L10.83 12z',
  right: 'M10 6 8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z',
  info: 'M11 7h2v2h-2zm0 4h2v6h-2zm1-9C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z',
  download: 'M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z',
  photo: 'M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z',
  person: 'M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z',
  folder: 'M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z',
  tag: 'M17.63 5.84C17.27 5.33 16.67 5 16 5L5 5.01C3.9 5.01 3 5.9 3 7v10c0 1.1.9 1.99 2 1.99L16 19c.67 0 1.27-.33 1.63-.84L22 12l-4.37-6.16z',
  place: 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5a2.5 2.5 0 0 1 0-5 2.5 2.5 0 0 1 0 5z',
  play: 'M8 5v14l11-7z',
  pause: 'M6 19h4V5H6v14zm8-14v14h4V5h-4z',
  star: 'M12 17.27 18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z',
  tune: 'M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 4v-2H11v2h10zm-6-4h2V7h4V5h-4V3h-2v6z',
  explore: 'M12 10.9c-.61 0-1.1.49-1.1 1.1s.49 1.1 1.1 1.1c.61 0 1.1-.49 1.1-1.1s-.49-1.1-1.1-1.1zM12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm2.19 12.19L6 18l3.81-8.19L18 6l-3.81 8.19z',
  video: 'M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z',
  camera: 'M9 2 7.17 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2h-3.17L15 2H9zm3 15c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8.2a3.2 3.2 0 1 0 0 6.4 3.2 3.2 0 0 0 0-6.4z',
  open: 'M19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z',
  calendar: 'M19 4h-1V2h-2v2H8V2H6v2H5c-1.11 0-1.99.9-1.99 2L3 20a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V9h14v11z',
  face: 'M9 11.75a1.25 1.25 0 1 0 0 2.5 1.25 1.25 0 0 0 0-2.5zm6 0a1.25 1.25 0 1 0 0 2.5 1.25 1.25 0 0 0 0-2.5zM12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8 0-.29.02-.58.05-.86 2.36-1.05 4.23-2.98 5.21-5.37a9.974 9.974 0 0 0 10.41 3.97c.21.71.33 1.47.33 2.26 0 4.41-3.59 8-8 8z',
  text: 'M2.5 4v3h5v12h3V7h5V4h-13zm19 5h-9v3h3v7h3v-7h3V9z',
  heart: 'M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z',
  heartO: 'M16.5 3c-1.74 0-3.41.81-4.5 2.09C10.91 3.81 9.24 3 7.5 3 4.42 3 2 5.42 2 8.5c0 3.78 3.4 6.86 8.55 11.54L12 21.35l1.45-1.32C18.6 15.36 22 12.28 22 8.5 22 5.42 19.58 3 16.5 3zm-4.4 15.55l-.1.1-.1-.1C7.14 14.24 4 11.39 4 8.5 4 6.5 5.5 5 7.5 5c1.54 0 3.04.99 3.57 2.36h1.87C13.46 5.99 14.96 5 16.5 5c2 0 3.5 1.5 3.5 3.5 0 2.89-3.14 5.74-7.9 10.05z',
  check: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z',
  add: 'M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z',
  dup: 'M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z',
  spark: 'M19 9l1.25-2.75L23 5l-2.75-1.25L19 1l-1.25 2.75L15 5l2.75 1.25L19 9zm-7.5.5L9 4 6.5 9.5 1 12l5.5 2.5L9 20l2.5-5.5L17 12l-5.5-2.5zM19 15l-1.25 2.75L15 19l2.75 1.25L19 23l1.25-2.75L23 19l-2.75-1.25L19 15z',
  trash: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z',
  edit: 'M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z',
  link: 'M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.710 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z',
  remove: 'M19 13H5v-2h14v2z',
  map: 'M20.5 3l-.16.03L15 5.1 9 3 3.36 4.9c-.21.07-.36.25-.36.48V20.5c0 .28.22.5.5.5l.16-.03L9 18.9l6 2.1 5.64-1.9c.21-.07.36-.25.36-.48V3.5c0-.28-.22-.5-.5-.5zM15 19l-6-2.11V5l6 2.11V19z',
  copyright: 'M10.08 10.86c.05-.33.16-.62.3-.87s.34-.46.59-.62c.24-.15.54-.22.91-.23.23.01.44.05.63.13.2.09.38.21.52.36s.25.33.34.53.13.42.14.64h1.79c-.02-.47-.11-.9-.28-1.29s-.4-.73-.7-1.01-.66-.5-1.08-.66-.88-.23-1.39-.23c-.65 0-1.22.11-1.7.34s-.88.53-1.2.92-.56.84-.71 1.36S8 11.29 8 11.87v.27c0 .58.08 1.12.23 1.64s.39.97.71 1.35.72.69 1.2.91c.48.22 1.05.34 1.7.34.47 0 .91-.08 1.32-.23s.77-.36 1.08-.63.56-.58.74-.94.29-.74.3-1.15h-1.79c-.01.21-.06.4-.15.58s-.21.33-.36.46-.32.23-.52.3c-.19.07-.39.09-.6.1-.36-.01-.66-.08-.89-.23-.25-.16-.45-.37-.59-.62s-.25-.55-.3-.88-.08-.67-.08-1v-.27c0-.35.03-.68.08-1.01zM12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z',
};
function icon(name) {
  const s = document.createElement('span');
  s.className = 'ic';
  s.innerHTML = `<svg viewBox="0 0 24 24"><path d="${ICONS[name] || ''}"/></svg>`;
  return s;
}
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith('on')) el[k.toLowerCase()] = v;
    else if (k === 'class') el.className = v;
    else if (k === 'style') el.style.cssText = v;
    else if (k === 'value') el.value = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  const add = (c) => {
    if (c == null || c === false) return;
    if (Array.isArray(c)) c.forEach(add);
    else el.append(c.nodeType ? c : document.createTextNode(String(c)));
  };
  kids.forEach(add);
  return el;
}
/** Replace el's children with kids (nested arrays and nulls allowed, like h()). */
const fill = (el, ...kids) => { el.replaceChildren(...h('div', null, ...kids).childNodes); return el; };
const norm = (s) => String(s ?? '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
const nf = new Intl.NumberFormat();
const plural = (n, one, many = one + 's') => `${nf.format(n)} ${n === 1 ? one : many}`;
const sleep = (ms) => new Promise((ok) => setTimeout(ok, ms));
// Photo timestamps are the camera's local time stored as if UTC, so they are formatted in UTC to show what the camera saw.
const UTC = { timeZone: 'UTC' };
const dfDay = new Intl.DateTimeFormat(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric', ...UTC });
const dfMonth = new Intl.DateTimeFormat(undefined, { month: 'short', year: 'numeric', ...UTC });
const dfLong = new Intl.DateTimeFormat(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric', ...UTC });
const dfTime = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit', ...UTC });
// Real wall-clock moments (index built, GPS track recorded) are shown in this browser's time zone.
const dfDayLocal = new Intl.DateTimeFormat(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
const dfTimeLocal = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' });
const fmtWhen = (ts) => `${dfDayLocal.format(date(ts))} ${dfTimeLocal.format(date(ts))}`;
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const date = (ts) => new Date(ts * 1000);
const isoDay = (ts) => date(ts).toISOString().slice(0, 10);
function fmtBytes(b) {
  if (!b) return '';
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
  return `${b >= 100 || i === 0 ? Math.round(b) : b.toFixed(1)} ${u[i]}`;
}
function fmtDur(s) {
  s = Math.round(s || 0);
  const m = Math.floor(s / 60), hh = Math.floor(m / 60);
  return hh ? `${hh}:${String(m % 60).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}` : `${m}:${String(s % 60).padStart(2, '0')}`;
}
function fmtRange(a, b) {
  if (a == null) return '';
  const x = dfMonth.format(date(a)), y = dfMonth.format(date(b));
  return x === y ? x : `${x} – ${y}`;
}
async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}
async function post(path, body, retried) {
  const r = await fetch(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  if (!r.ok) {
    let msg = `${r.status} ${path}`; try { msg = (await r.json()).detail || msg; } catch { /* not json */ }
    // in a container (DIGIKAM_CHECK=ask) the viewer cannot see digiKam's process, so a database write is
    // refused until the owner vouches that digiKam is closed; ask once here, vouch for 10 minutes, retry
    if (r.status === 409 && !retried && DIGIKAM_CHECK === 'ask' && /digiKam is running/i.test(msg) && path !== '/api/settings') {
      if (confirm('The viewer cannot see whether digiKam is running (it runs in a container, or digiKam is on another machine).\n\nIs every digiKam that uses this database closed right now? Writing to the database while digiKam is open can corrupt it.\n\nOK: yes, it is closed; go ahead (remembered for 10 minutes).')) {
        await post('/api/settings', { digikam_closed: true }, true);
        return post(path, body, true);
      }
    }
    throw new Error(msg);
  }
  return r.json();
}
// Display preferences. Anonymous: the browser's localStorage. Signed in: the user's settings on the
// server (loaded with the session, written through, so they follow the user to another device).
let USER = null, USER_SETTINGS = null, settingsFlush = 0, settingsPending = {};
const store = {
  get(k, d) { if (USER_SETTINGS) return k in USER_SETTINGS ? String(USER_SETTINGS[k]) : d; try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set(k, v) {
    if (USER_SETTINGS) { USER_SETTINGS[k] = v; settingsPending[k] = v; clearTimeout(settingsFlush); settingsFlush = setTimeout(() => { const b = settingsPending; settingsPending = {}; post('/api/auth/settings', b).catch(() => {}); }, 400); return; }
    try { localStorage.setItem(k, v); } catch { /* private mode */ }
  },
};
/** A person's badge picture; the version key busts the cache when digiKam's tag icon changes. */
const faceUrl = (tagId) => `/face/${tagId}?v=${tagById.get(tagId)?.icon || 0}`;
// an account's avatar: the linked person's face badge from People, else the first letter
const avatarOf = (u, big) => u.person ? h('img', { class: 'avatar' + (big ? ' big' : ''), src: faceUrl(u.person), alt: '' }) : h('span', { class: 'avatar' + (big ? ' big' : '') }, u.name[0].toUpperCase());
function toast(msg, action, fn, ms = 6000) {
  const t = $('#toast');
  fill(t, msg, action ? h('a', { onclick: () => { t.hidden = true; fn(); } }, action) : null);
  t.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => { t.hidden = true; }, ms);
}

// ---------------------------------------------------------------- state & routing
let META = null, tagById = new Map(), albumById = new Map();
let route = { view: 'photos', params: new URLSearchParams() };
let viewKey = null;
const main = $('#main');
const FILTER_VIEWS = ['photos', 'map'];
const NAV = [
  ['photos', 'Photos', 'photo'], ['explore', 'Explore', 'explore'], ['favorites', 'Favorites', 'heartO', '#/photos?fav=1'],
  ['people', 'People', 'person'], ['places', 'Places', 'place'], ['albums', 'Albums', 'folder'], ['tags', 'Tags', 'tag'], ['map', 'Map', 'map'],
];
// hash route name -> page renderer (function declarations are hoisted, so this can sit above them)
const VIEW_FNS = { photos: showPhotos, explore: showExplore, people: showPeople, places: showPlaces, albums: showAlbums, tags: showTags, map: showMap, duplicates: showDuplicates,
  detected: showDetected, bursts: showBursts, events: showEvents, analysis: showAnalysis, settings: showSettings, maintenance: showMaintenance, consistency: showConsistency, faces: showFaces };
const VIEWS = Object.keys(VIEW_FNS);
const PARAM_VIEWS = ['places', 'bursts', 'faces'];  // views whose own query parameters (not photo filters) pick what they show
// favorites and app albums (stored by the app, not in digiKam)
const ST = { rev: -1, fav: new Set(), albums: [] };
let SEM = { enabled: false };
let CONCEPTS = null;  // the detected-content vocabulary with counts, fetched once for the search suggestions
function loadConcepts() { if (CONCEPTS || !SEM.enabled) return; CONCEPTS = []; api('/api/concepts').then((c) => { CONCEPTS = c.concepts.map((x) => ({ ...x, _n: norm(x.name) })); }).catch(() => { CONCEPTS = null; }); }
let APP_STAMP = null;
const applyBadgePref = () => document.body.classList.toggle('nobadges', store.get('badges', '1') === '0');
/** Appearance: light, dark, or follow the system (the default). Set on <html> so the stylesheet
 *  picks the palette; the browser chrome (theme-color) follows the page background. */
const THEMES = [['system', 'System'], ['light', 'Light'], ['dark', 'Dark']];
function applyTheme() {
  const t = store.get('theme', 'system');
  if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
  requestAnimationFrame(() => { const m = document.querySelector('meta[name=theme-color]'); if (m) m.content = getComputedStyle(document.body).backgroundColor; });
}
let dragTag = null;
let IS_ADMIN = true, SIGNED_IN = true, USERS_EXIST = false, REQUIRE_LOGIN = false, BOOTED = false, DIGIKAM_CHECK = 'pgrep', APP_VERSION = '', APP_COMMIT = '';
let EDITING = false, WRITE_FILES = false, CAN_MANAGE = false, manageTags = false, PENDING = 0, pollTimer = 0, keepView = false;
/** Re-check server status soon (after an edit) instead of waiting for the regular poll. */
function pollSoon(ms = 1500) { clearTimeout(pollTimer); pollTimer = setTimeout(pollStatus, ms); }
async function loadState() {
  const s = await api('/api/state');
  ST.rev = s.rev; ST.fav = new Set(s.favorites); ST.albums = s.albums;
}
const ualbumById = (id) => ST.albums.find((a) => a.id === +id);

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [path, qs = ''] = raw.split('?');
  return { view: VIEWS.includes(path) ? path : 'photos', params: new URLSearchParams(qs) };
}
function hashFor(view, params) {
  const qs = params ? params.toString() : '';
  return `#/${view}${qs ? '?' + qs : ''}`;
}
function go(view, params, replace = false) {
  history[replace ? 'replaceState' : 'pushState'](null, '', hashFor(view, params));
  onRoute();
}
function filterParams() {
  const p = new URLSearchParams(FILTER_VIEWS.includes(route.view) ? route.params : '');
  p.delete('p');
  return p;
}
/** Change the active filters, staying on the map if that is where we are. */
function applyFilter(mutate, view) {
  const p = filterParams();
  mutate(p);
  go(view || (route.view === 'map' ? 'map' : 'photos'), p);
}
function toggle(p, key, value) {
  value = String(value);
  const all = p.getAll(key);
  p.delete(key);
  if (all.includes(value)) all.filter((v) => v !== value).forEach((v) => p.append(key, v));
  else [...all, value].forEach((v) => p.append(key, v));
}
function setOne(p, key, value) {
  if (value == null || value === '' || p.get(key) === String(value)) p.delete(key);
  else p.set(key, value);
}
const photosWith = (obj) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(obj)) p.append(k, v);
  return p;
};

function onRoute() {
  route = parseHash();
  const fp = filterParams();
  const vp = new URLSearchParams(route.params); vp.delete('p');
  const key = route.view + '?' + (PARAM_VIEWS.includes(route.view) ? vp : fp).toString();
  document.querySelectorAll('#nav a, #topbar a.tool').forEach((a) => a.classList.toggle('on', a.dataset.v === (route.view === 'photos' && fp.get('fav') === '1' && [...fp.keys()].length === 1 ? 'favorites' : route.view)));
  renderChips();
  if (key !== viewKey) {
    viewKey = key;
    if (keepView) G.restore = main.scrollTop; else clearSelection(true);
    keepView = false;
    main.scrollTop = 0;
    removeScrubber();
    VIEW_FNS[route.view](PARAM_VIEWS.includes(route.view) ? vp : fp);
    if (!$('#filters').hidden) renderFilters();
  }
  syncLightbox();
}
window.addEventListener('popstate', onRoute);
window.addEventListener('hashchange', onRoute);

// ---------------------------------------------------------------- search box & chips
function chipList(p) {
  const out = [];
  const add = (key, value, label, opt = {}) => out.push({ key, value, label, ...opt });
  for (const [k, v] of p) {
    if (k === 'q') add(k, v, `“${v}”`, { ic: 'text' });
    else if (k === 'tag' || k === 'nottag') {
      const t = tagById.get(+v);
      add(k, v, (k === 'nottag' ? 'Not ' : '') + (t ? t.name : `Tag ${v}`), t?.person ? { img: faceUrl(+v) } : { ic: 'tag' });
    } else if (k === 'album') add(k, v, albumById.get(+v)?.name || `Album ${v}`, { ic: 'folder' });
    else if (k === 'year') add(k, v, v, { ic: 'calendar' });
    else if (k === 'month') add(k, v, MONTHS[v - 1] || v, { ic: 'calendar' });
    else if (k === 'from') add(k, v, `From ${v}`, { ic: 'calendar' });
    else if (k === 'to') add(k, v, `Until ${v}`, { ic: 'calendar' });
    else if (k === 'md') add(k, v, `On ${MONTHS[+v.slice(0, 2) - 1]} ${+v.slice(3)}, any year`, { ic: 'calendar' });
    else if (k === 'camera' || k === 'lens') add(k, v, v === '~' ? `No ${k}` : v, { ic: 'camera' });
    else if (k === 'fmt') add(k, v, v);
    else if (k === 'creator') add(k, v, `By ${v}`, { ic: 'copyright' });
    else if (k === 'rating') add(k, v, `${v}★ and up`, { ic: 'star' });
    else if (k === 'type') add(k, v, v === 'video' ? 'Videos' : 'Photos only', { ic: v === 'video' ? 'video' : 'photo' });
    else if (k === 'geo') add(k, v, v === '1' ? 'Has location' : 'No location', { ic: 'place' });
    else if (k === 'untagged') add(k, v, 'Untagged', { ic: 'tag' });
    else if (k === 'norejected') add(k, v, 'Hide rejected');
    else if (k === 'bbox') add(k, v, 'Map area', { ic: 'place' });
    else if (k === 'trail') add(k, v, `Trail for ${v}`, { ic: 'map' });
    else if (k === 'faces') add(k, v, { unknown: 'Unnamed faces', suggested: 'Face suggestions', ignored: 'Ignored faces', confirmed: 'Named faces' }[v] || v, { ic: 'face' });
    else if (k === 'fav') add(k, v, 'Favorites', { ic: 'heart' });
    else if (k === 'ualbum') add(k, v, ualbumById(v)?.name || 'Album', { ic: 'folder' });
    else if (k === 'place' || k === 'region' || k === 'country') add(k, v, v, { ic: 'place' });
    else if (k === 'sem') add(k, v, `Looks like “${v}”`, { ic: 'spark' });
    else if (k === 'like') add(k, v, 'Similar photos', { img: `/thumb/${v}` });
    else if (k === 'concept') add(k, v, `Detected: ${v}`, { ic: 'spark' });
    else if (k === 'blurry') add(k, v, 'Blurry', { ic: 'spark' });
    else if (k === 'sharpest') add(k, v, 'Sharpest', { ic: 'spark' });
    else if (k === 'exposure') add(k, v, v === 'dark' ? 'Very dark' : 'Very bright', { ic: 'spark' });
    else if (k === 'hastext') add(k, v, 'Contains text', { ic: 'text' });
    else if (k === 'bursts') add(k, v, 'In a burst', { ic: 'dup' });
    else if (k === 'bestonly') add(k, v, 'Best frame of each burst', { ic: 'dup' });
    else if (k === 'burst') add(k, v, 'One burst', { ic: 'dup' });
    else if (k === 'obj') add(k, v, `Shows: ${v}`, { ic: 'spark' });
    else if (k === 'npeople') add(k, v, v === '0' ? 'No people' : `${v} ${v === '1' ? 'person' : 'people'}`, { ic: 'person' });
    else if (k === 'dupes') add(k, v, 'Duplicates', { ic: 'dup' });
    else if (k === 'edited') add(k, v, 'Edited here, not yet in digiKam', { ic: 'edit' });
    else if (k === 'ids') add(k, v, `${nf.format(v.split(',').length)} chosen photos`, { ic: 'place' });
    else if (/^(iso|ap|fl|exp)_(min|max)$/.test(k)) {
      const [f, m] = k.split('_');
      add(k, v, `${{ iso: 'ISO', ap: 'ƒ/', fl: 'Focal mm', exp: 'Exposure s' }[f]} ${m === 'min' ? '≥' : '≤'} ${v}`, { ic: 'camera' });
    }
  }
  return out;
}
function renderChips() {
  const p = filterParams();
  const chips = chipList(p);
  $('#chips').replaceChildren(...chips.map((c) => h('span', { class: 'chip', title: c.label, 'data-k': c.key },
    c.img ? h('img', { src: c.img, alt: '' }) : null,
    h('span', { class: 't' }, c.label),
    h('button', { title: 'Remove', onclick: () => applyFilter((q) => {
      const rest = q.getAll(c.key).filter((v) => v !== c.value);
      q.delete(c.key);
      rest.forEach((v) => q.append(c.key, v));
    }) }, icon('close')))));
  $('#clear').hidden = !chips.length && !$('#q').value;
  $('#q').placeholder = chips.length ? 'Add to search…' : 'Search people, tags, albums, cameras, captions…';
}

let sgItems = [], sgSel = 0;
function suggestions(text) {
  const words = norm(text).split(/\s+/).filter(Boolean);
  const out = [{ ic: 'search', label: `Search everything for “${text.trim()}”`, kind: 'Text', act: (p) => p.append('q', text.trim()) }];
  if (!words.length || !META) return [];
  if (SEM.enabled) { loadConcepts(); out.push({ ic: 'spark', label: `Photos that look like “${text.trim()}”`, kind: 'Content', act: (p) => { p.delete('like'); p.set('sem', text.trim()); } }); }
  const score = (n) => {
    if (!words.every((w) => n.includes(w))) return -1;
    return n.startsWith(words[0]) ? 3 : new RegExp(`(^|[^a-z0-9])${words[0].replace(/[^\w]/g, '.')}`).test(n) ? 2 : 1;
  };
  const top = (list, limit, key, count) => list.map((x) => [score(x[key]), x]).filter((s) => s[0] > 0)
    .sort((a, b) => b[0] - a[0] || count(b[1]) - count(a[1])).slice(0, limit).map((s) => s[1]);
  const m = /^((?:19|20)\d\d)$/.exec(text.trim());
  if (m) out.push({ ic: 'calendar', label: m[1], kind: 'Year', act: (p) => p.set('year', m[1]) });
  const mm = /^([a-z]{3,})\.?(?:\s+((?:19|20)\d\d))?$/i.exec(text.trim());
  if (mm) {
    const mi = MONTHS.findIndex((x) => x.toLowerCase().startsWith(mm[1].toLowerCase()));
    if (mi >= 0) out.push({ ic: 'calendar', label: MONTHS[mi] + (mm[2] ? ' ' + mm[2] : ''), kind: 'Month',
      act: (p) => { p.set('month', mi + 1); if (mm[2]) p.set('year', mm[2]); } });
  }
  for (const c of top(CONCEPTS || [], 3, '_n', (c) => c.n))
    out.push({ ic: 'spark', label: c.name, kind: `Detected · ${nf.format(c.n)}`, act: (p) => p.set('concept', c.name) });
  const used = new Set(filterParams().getAll('tag'));
  const tags = META.tags.filter((t) => t.nAll && !used.has(String(t.id)));
  for (const t of top(tags.filter((t) => t.person), 6, '_n', (t) => t.nAll))
    out.push({ img: faceUrl(t.id), label: t.name, sub: nf.format(t.nAll), kind: 'Person', act: (p) => p.append('tag', t.id) });
  for (const t of top(tags.filter((t) => !t.person), 6, '_n', (t) => t.nAll))
    out.push({ ic: 'tag', label: t.name, sub: t.full.includes('/') ? t.full.split('/').slice(0, -1).join(' › ') : '', kind: `Tag · ${nf.format(t.nAll)}`, act: (p) => p.append('tag', t.id) });
  for (const a of top(META.albums.filter((a) => a.pid != null), 5, '_n', (a) => a.nAll))
    out.push({ ic: 'folder', label: a.name, sub: a.path, kind: `Album · ${nf.format(a.nAll)}`, act: (p) => { p.delete('album'); p.append('album', a.id); } });
  for (const [kind, key, list] of [['Camera', 'camera', META.cameras], ['Lens', 'lens', META.lenses], ['Creator', 'creator', META.creators]])
    for (const c of top(list.map(([name, n]) => ({ name, n, _n: norm(name) })), 3, '_n', (c) => c.n))
      out.push({ ic: kind === 'Creator' ? 'copyright' : 'camera', label: c.name, kind: `${kind} · ${nf.format(c.n)}`, act: (p) => p.append(key, c.name) });
  for (const c of top(placeRows, 5, '_n', (c) => c.n))
    out.push({ ic: 'place', label: c.name, sub: c.sub, kind: `Place · ${nf.format(c.n)}`, act: (p) => p.set(c.key, c.name) });
  if (words.length === 1) {
    if ('favorites'.startsWith(words[0])) out.push({ ic: 'heart', label: 'Favorites', kind: 'Filter', act: (p) => p.set('fav', '1') });
    if ('videos'.startsWith(words[0])) out.push({ ic: 'video', label: 'Videos', kind: 'Type', act: (p) => p.set('type', 'video') });
    if ('untagged'.startsWith(words[0])) out.push({ ic: 'tag', label: 'Untagged', kind: 'Filter', act: (p) => p.set('untagged', '1') });
  }
  return out;
}
function renderSuggest() {
  const box = $('#suggest');
  box.hidden = !sgItems.length;
  box.replaceChildren(...sgItems.map((s, i) => h('div', { class: 'sg' + (i === sgSel ? ' sel' : ''), onmousedown: (e) => { e.preventDefault(); pickSuggestion(i); } },
    s.img ? h('img', { src: s.img, alt: '' }) : icon(s.ic), h('span', null, s.label, s.sub ? h('span', { class: 'sub' }, s.sub) : null),
    h('span', { class: 'kind' }, s.kind))));
  box.querySelector('.sel')?.scrollIntoView({ block: 'nearest' });
}
function pickSuggestion(i) {
  const s = sgItems[i];
  if (!s) return;
  $('#q').value = '';
  sgItems = [];
  renderSuggest();
  applyFilter(s.act);
}
function initSearch() {
  const q = $('#q');
  q.addEventListener('input', () => { sgItems = suggestions(q.value); sgSel = 0; renderSuggest(); $('#clear').hidden = false; });
  q.addEventListener('focus', () => { if (q.value) { sgItems = suggestions(q.value); renderSuggest(); } });
  q.addEventListener('blur', () => { $('#suggest').hidden = true; });
  q.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { sgSel = Math.min(sgSel + 1, sgItems.length - 1); renderSuggest(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { sgSel = Math.max(sgSel - 1, 0); renderSuggest(); e.preventDefault(); }
    else if (e.key === 'Enter') { if (q.value.trim()) pickSuggestion(sgSel); }
    else if (e.key === 'Escape') { q.value = ''; sgItems = []; renderSuggest(); q.blur(); }
    else if (e.key === 'Backspace' && !q.value) {
      const chips = chipList(filterParams());
      const last = chips[chips.length - 1];
      if (last) applyFilter((p) => { const rest = p.getAll(last.key).filter((v) => v !== last.value); p.delete(last.key); rest.forEach((v) => p.append(last.key, v)); });
    }
  });
  $('#clear').onclick = () => { q.value = ''; sgItems = []; renderSuggest(); go(route.view === 'map' ? 'map' : 'photos', new URLSearchParams()); q.focus(); };
  $('#filterbtn').onclick = () => toggleFilters();
  document.querySelectorAll('[data-ic]').forEach((el) => el.replaceWith(icon(el.dataset.ic)));
}

// ---------------------------------------------------------------- breadcrumbs
/** parts: [[label, hash or null]]; the last part is the current location. */
function crumbs(parts) {
  return h('nav', { class: 'crumbs' }, parts.map(([label, href], i) => [
    i ? h('span', { class: 'sep' }, '›') : null,
    href && i < parts.length - 1 ? h('a', { href }, label) : h('span', { class: i === parts.length - 1 ? 'cur' : '' }, label)]));
}
const placeHash = (o) => hashFor('places', photosWith(o));
/** Where the current photo list sits in a hierarchy (album, place, tag, ...), if it does. */
function photoCrumbs(p) {
  const albums = p.getAll('album'), tags = p.getAll('tag');
  if (albums.length === 1 && albumById.get(+albums[0])) {
    const chain = [];
    for (let a = albumById.get(+albums[0]); a && a.pid != null; a = albumById.get(a.pid)) chain.unshift(a);
    return [['Albums', '#/albums'], ...chain.map((a) => [a.name, hashFor('photos', photosWith({ album: a.id, sort: 'old' }))])];
  }
  if (p.get('ualbum') && ualbumById(p.get('ualbum'))) return [['Albums', '#/albums'], ['My albums', '#/albums'], [ualbumById(p.get('ualbum')).name, null]];
  if (p.get('country') || p.get('region') || p.get('place')) {
    let [country, region, place] = [p.get('country'), p.get('region'), p.get('place')];
    const row = META.places.find((x) => (!place || x[0] === place) && (!region || x[1] === region) && (!country || x[2] === country));
    if (row) { country ||= row[2]; if (place || region) region ||= row[1]; }
    const out = [['Places', '#/places']];
    if (country) out.push([country, placeHash({ country })]);
    if (region) out.push([region, placeHash({ country, region })]);
    if (place) out.push([place, null]);
    return out;
  }
  if (tags.length === 1 && tagById.get(+tags[0])) {
    const chain = [];
    for (let t = tagById.get(+tags[0]); t; t = tagById.get(t.pid)) chain.unshift(t);
    return [[chain[0].name === 'People' ? 'People' : 'Tags', chain[0].name === 'People' ? '#/people' : '#/tags'],
      ...chain.filter((t, i) => !(i === 0 && t.name === 'People')).map((t) => [t.name, hashFor('photos', photosWith({ tag: t.id }))])];
  }
  if (p.get('concept')) return [['Explore', '#/explore'], ['Detected content', '#/detected'], [p.get('concept'), null]];
  if (p.get('dupes') || p.get('edited')) return [['Explore', '#/explore'], [p.get('dupes') ? 'Duplicates' : 'Edited here', null]];
  return null;
}

// ---------------------------------------------------------------- timeline grid
const SIZES = { S: [120, 80], M: [190, 110], L: [280, 170] };
// grid state: sel = selected photo ids; items = laid-out rows/headers; rendered = row index -> element currently in the DOM
const G = { sel: new Set(), lastSel: -1, data: null, items: [], ar: null, total: 0, top0: 0, restore: 0, rendered: new Map(), token: 0,
  size: store.get('tile', 'M') in SIZES ? store.get('tile', 'M') : 'M', group: store.get('group', 'day') === 'month' ? 'month' : 'day', lastTop: 0, lastT: 0, settle: 0, scrub: null };
/** The section a timestamp belongs to in the chronological grid: its day, or its month. */
function groupKey(ts) {
  if (G.group === 'month') { const dt = date(ts); return dt.getUTCFullYear() * 12 + dt.getUTCMonth(); }
  return Math.floor(ts / 86400);
}
const GAP = 4, BAR_H = 48, HEAD_H = 46;

async function showPhotos(fp) {
  const token = ++G.token;
  G.data = null;
  G.rendered.clear();
  const grid = h('div', { id: 'grid' }, h('div', { class: 'empty' }, 'Loading…'));
  main.replaceChildren(grid);
  let data;
  try { data = await api('/api/photos?' + fp.toString()); } catch (e) { grid.replaceChildren(h('div', { class: 'empty' }, 'Could not load photos: ' + e.message)); return; }
  if (token !== G.token || route.view !== 'photos') return;
  G.data = data;
  G.geo = new Set(data.geo || []);
  G.faces = new Set(data.faces || []);
  G.sort = fp.get('sort') || (data.ranked ? 'rel' : 'new');
  const n = data.count;
  G.ar = new Float32Array(n);
  for (let i = 0; i < n; i++) G.ar[i] = Math.min(2.6, Math.max(0.5, data.w[i] / (data.h[i] || 1)));
  grid.replaceChildren();
  grid.onclick = (e) => {
    const hc = e.target.closest('.hcheck');
    if (hc) { selectRange(+hc.dataset.s, +hc.dataset.e - 1, 'toggle'); return; }
    const t = e.target.closest('.tile');
    if (!t) return;
    const i = +t.dataset.i;
    if (e.target.closest('.tcheck') || G.sel.size) {
      if (e.shiftKey && G.lastSel >= 0) selectRange(Math.min(G.lastSel, i), Math.max(G.lastSel, i), true);
      else toggleSelect(i);
    } else openLightbox(G.data, i, true);
  };
  if (!n) {
    grid.append(h('div', { class: 'empty' }, 'No photos match this search.'));
    syncLightbox();
    return;
  }
  layoutGrid();
  if (G.restore) { main.scrollTop = G.restore; G.restore = 0; }
  renderGrid(true);
  updateSelBar();
  syncLightbox();
}

function layoutGrid() {
  const grid = $('#grid'), d = G.data;
  if (!grid || !d) return;
  const W = grid.clientWidth, H = SIZES[G.size][innerWidth < 800 ? 1 : 0];
  const items = [], byDate = G.sort === 'new' || G.sort === 'old';
  const sections = [];
  if (byDate) {
    let start = 0, day = groupKey(d.ts[0]);
    for (let i = 1; i <= d.count; i++) {
      const dd = i < d.count ? groupKey(d.ts[i]) : null;
      if (dd !== day) { sections.push([start, i]); start = i; day = dd; }
    }
  } else sections.push([0, d.count]);
  const trail = photoCrumbs(filterParams());
  const top0 = trail ? 30 : 0;
  G.top0 = top0;
  let y = BAR_H + top0;
  for (const [s, e] of sections) {
    if (byDate) { items.push({ y, h: HEAD_H, s, e, head: true }); y += HEAD_H; }
    let i = s;
    while (i < e) {
      let sum = 0, j = i;
      while (j < e) { sum += G.ar[j++]; if (sum * H + (j - i - 1) * GAP >= W) break; }
      const full = sum * H + (j - i - 1) * GAP >= W;
      const rh = full ? (W - (j - i - 1) * GAP) / sum : H;
      items.push({ y, h: rh, s: i, e: j });
      y += rh + GAP;
      i = j;
    }
    y += 8;
  }
  G.items = items;
  G.total = y + 40;
  grid.style.height = G.total + 'px';
  for (const el of G.rendered.values()) el.remove();
  G.rendered.clear();
  $('.gbar', grid)?.remove();
  $('.crumbs', grid)?.remove();
  if (trail) grid.append(crumbs(trail));
  grid.append(h('div', { class: 'gbar', style: `top:${top0}px` },
    h('span', { class: 'count' }, plural(d.count, 'item')),
    byDate ? h('span', null, fmtRange(Math.min(d.ts[0], d.ts[d.count - 1]), Math.max(d.ts[0], d.ts[d.count - 1]))) : null,
    h('span', { class: 'sp' }),
    h('span', { class: 'lnk selall', title: 'Select or deselect everything in this view', onclick: () => { G.sel.size >= d.count ? clearSelection() : selectRange(0, d.count - 1, true); } }, G.sel.size >= d.count ? 'Deselect all' : 'Select all'),
    [...filterParams().keys()].some((k) => k !== 'sort') ? h('button', { class: 'pillbtn dlbtn', title: 'Download these as zip files', onclick: () => downloadDialog(filterParams()) }, icon('download'), h('span', null, 'Download')) : null,
    // the default sort (newest, or best match for ranked results) is left out of the URL
    h('select', { title: 'Sort', onchange: (e) => applyFilter((p) => { ['new', 'rel'].includes(e.target.value) && !(d.ranked && e.target.value === 'new') ? p.delete('sort') : p.set('sort', e.target.value); }) },
      ...[...(d.ranked ? [['rel', 'Best match']] : []), ['new', 'Newest first'], ['old', 'Oldest first'], ['added', 'Recently modified'], ['rating', 'Top rated'], ['sharp', 'Sharpest first'], ['blur', 'Blurriest first'], ['name', 'File name'], ['size', 'Largest files']]
        .map(([v, l]) => h('option', { value: v, selected: v === G.sort }, l))),
    byDate ? h('select', { title: 'Group the photos by day or by month', class: 'groupsel', onchange: (e) => {
      const anchor = firstVisibleIndex();
      G.group = e.target.value; store.set('group', G.group); layoutGrid(); scrollToIndex(anchor, true); renderGrid(true);
    } }, h('option', { value: 'day', selected: G.group === 'day' }, 'By day'), h('option', { value: 'month', selected: G.group === 'month' }, 'By month')) : null,
    h('span', { class: 'seg', title: 'Thumbnail size' }, ...Object.keys(SIZES).map((k) => h('button', { class: k === G.size ? 'on' : '', onclick: () => {
      const anchor = firstVisibleIndex();
      G.size = k; store.set('tile', k); layoutGrid(); scrollToIndex(anchor, true); renderGrid(true);
    } }, k)))));
  buildScrubber(byDate);
}

function itemAt(y) { // last item starting at or above y
  let lo = 0, hi = G.items.length - 1;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (G.items[mid].y <= y) lo = mid; else hi = mid - 1; }
  return lo;
}
function firstVisibleIndex() {
  if (!G.items.length) return 0;
  return G.items[itemAt(main.scrollTop + 1)].s;
}
function scrollToIndex(i, top = false) {
  const it = G.items.find((x) => !x.head && i >= x.s && i < x.e);
  if (!it) return;
  if (top) main.scrollTop = it.y - (it.s === 0 ? BAR_H + HEAD_H + (G.top0 || 0) : 4);
  else if (it.y < main.scrollTop || it.y + it.h > main.scrollTop + main.clientHeight) main.scrollTop = it.y - main.clientHeight / 2 + it.h / 2;
}

function renderGrid(force) {
  const grid = $('#grid'), d = G.data;
  if (!grid || !d || !G.items.length) return;
  const top = main.scrollTop, vh = main.clientHeight, now = performance.now();
  const speed = Math.abs(top - G.lastTop) / Math.max(1, now - G.lastT); // px per ms
  G.lastTop = top; G.lastT = now;
  const fast = !force && speed > 12;
  const a = itemAt(top - vh * 0.8), b = itemAt(top + vh * 1.8);
  for (const [k, el] of G.rendered) if (k < a || k > b) { el.remove(); G.rendered.delete(k); }
  for (let k = a; k <= b; k++) {
    if (G.rendered.has(k)) continue;
    const it = G.items[k];
    let el;
    if (it.head) {
      el = h('div', { class: 'ghead', style: `top:${it.y}px;height:${it.h}px` },
        h('span', { class: 'hcheck', title: G.group === 'month' ? 'Select this month' : 'Select this day', 'data-s': it.s, 'data-e': it.e }, icon('check')), (G.group === 'month' ? dfMonth : dfDay).format(date(d.ts[it.s])),
        it.e - it.s > 12 ? h('span', { class: 'n' }, nf.format(it.e - it.s)) : null);
    } else {
      el = h('div', { class: 'grow', style: `top:${it.y}px;height:${it.h}px` });
      for (let i = it.s; i < it.e; i++) {
        const img = document.createElement('img');
        img.alt = ''; img.decoding = 'async'; img.draggable = false;
        if (fast) img.dataset.src = `/thumb/${d.id[i]}`; else img.src = `/thumb/${d.id[i]}`;
        const tile = h('div', { class: 'tile' + (G.sel.has(d.id[i]) ? ' sel' : ''), 'data-i': i, style: `width:${(G.ar[i] * it.h).toFixed(2)}px` }, img,
          h('span', { class: 'tcheck', title: 'Select' }, icon('check')), ST.fav.has(d.id[i]) ? h('span', { class: 'fbadge' }, icon('heart')) : null);
        if (i in d.video) tile.append(h('span', { class: 'vbadge' }, d.video[i] ? fmtDur(d.video[i]) : null, icon('play')));
        const marks = [G.faces.has(i) ? h('span', { class: 'cbadge', title: 'Has face tags' }, icon('face')) : null, G.geo.has(i) ? h('span', { class: 'cbadge', title: 'Has GPS coordinates' }, icon('place')) : null].filter(Boolean);
        if (marks.length) tile.append(h('span', { class: 'cbadges' }, marks));
        el.append(tile);
      }
    }
    grid.append(el);
    G.rendered.set(k, el);
  }
  // While flinging through years, hold off on image requests until scrolling settles.
  clearTimeout(G.settle);
  G.settle = setTimeout(() => {
    grid.querySelectorAll('img[data-src]').forEach((img) => { img.src = img.dataset.src; delete img.dataset.src; });
  }, fast ? 90 : 0);
  updateScrubPos(top, vh);
}
let scrollRaf = 0;
main.addEventListener('scroll', () => {
  if (route.view !== 'photos' || scrollRaf) return;
  scrollRaf = requestAnimationFrame(() => { scrollRaf = 0; renderGrid(); });
}, { passive: true });

function removeScrubber() { $('#scrub')?.remove(); G.scrub = null; }
function buildScrubber(byDate) {
  removeScrubber();
  if (!byDate || G.total < main.clientHeight * 3) return;
  const d = G.data;
  const pos = h('div', { class: 'pos' });
  const sc = h('div', { id: 'scrub' }, pos, h('div', { class: 'bubble', hidden: true }));
  document.body.append(sc);
  const track = sc.clientHeight;
  G.scrub = { pos, track };  // read once here; updateScrubPos runs on every scroll frame and must not force a layout
  let lastYear = null, lastPx = -99;
  for (const it of G.items) {
    if (!it.head) continue;
    const yr = date(d.ts[it.s]).getUTCFullYear();
    if (yr === lastYear) continue;
    lastYear = yr;
    const px = (it.y / G.total) * track;
    if (px - lastPx < 16) continue;
    lastPx = px;
    sc.append(h('span', { class: 'yr', style: `top:${px}px` }, yr));
  }
  const bubble = $('.bubble', sc);
  const at = (e) => Math.min(1, Math.max(0, (e.clientY - sc.getBoundingClientRect().top) / track));
  const label = (f) => {
    const it = G.items[itemAt(f * G.total)];
    bubble.textContent = dfMonth.format(date(d.ts[it.s]));
    bubble.style.top = f * track + 'px';
    bubble.hidden = false;
  };
  let drag = false;
  sc.onpointerdown = (e) => { drag = true; sc.setPointerCapture(e.pointerId); main.scrollTop = at(e) * (G.total - main.clientHeight); label(at(e)); };
  sc.onpointermove = (e) => { label(at(e)); if (drag) main.scrollTop = at(e) * (G.total - main.clientHeight); };
  sc.onpointerup = sc.onpointercancel = () => { drag = false; };
  sc.onpointerleave = () => { if (!drag) bubble.hidden = true; };
  updateScrubPos();
}
function updateScrubPos(top = main.scrollTop, vh = main.clientHeight) {
  if (G.scrub) G.scrub.pos.style.top = (top / Math.max(1, G.total - vh)) * (G.scrub.track - 2) + 'px';
}
new ResizeObserver(() => {
  if (route.view === 'photos' && G.data?.count) {
    const anchor = firstVisibleIndex(), atTop = main.scrollTop < 10;
    layoutGrid();
    if (!atTop) scrollToIndex(anchor, true);
    renderGrid(true);
  }
  if (LB.open) sizeFrame();
}).observe(main);

// ---------------------------------------------------------------- selection & app-side actions
function redrawTiles() {
  for (const el of G.rendered.values()) el.remove();
  G.rendered.clear();
  renderGrid(true);
}
function toggleSelect(i) {
  const id = G.data.id[i];
  G.sel.has(id) ? G.sel.delete(id) : G.sel.add(id);
  G.lastSel = i;
  $(`.tile[data-i="${i}"]`, $('#grid'))?.classList.toggle('sel', G.sel.has(id));
  updateSelBar();
}
function selectRange(a, b, on) {
  const ids = G.data.id;
  if (on === 'toggle') { on = false; for (let i = a; i <= b; i++) if (!G.sel.has(ids[i])) { on = true; break; } }
  for (let i = a; i <= b; i++) on ? G.sel.add(ids[i]) : G.sel.delete(ids[i]);
  G.lastSel = b;
  redrawTiles();
  updateSelBar();
}
function clearSelection(silent) {
  if (!G.sel.size && silent) { updateSelBar(); return; }
  G.sel.clear(); G.lastSel = -1;
  if (!silent) redrawTiles();
  updateSelBar();
}
function updateSelBar() {
  let bar = $('#selbar');
  document.body.classList.toggle('selecting', G.sel.size > 0);
  const sa = $('#grid .selall');
  if (sa && G.data) sa.textContent = G.sel.size >= G.data.count ? 'Deselect all' : 'Select all';
  if (!G.sel.size) { bar?.remove(); return; }
  if (!bar) { bar = h('div', { id: 'selbar' }); document.body.append(bar); }
  const ids = () => [...G.sel];
  const inAlbum = route.view === 'photos' ? filterParams().get('ualbum') : null;
  const allFav = ids().every((id) => ST.fav.has(id));
  const btn = (ic, label, fn) => h('button', { class: 'pillbtn', title: label, onclick: fn }, icon(ic), h('span', null, label));
  fill(bar,
    h('button', { class: 'iconbtn', title: 'Clear selection (Esc)', onclick: () => clearSelection() }, icon('close')),
    h('span', { class: 'n' }, `${nf.format(G.sel.size)} selected`), h('span', { class: 'sp' }),
    btn(allFav ? 'heart' : 'heartO', allFav ? 'Unfavorite' : 'Favorite', async () => { await setFavorite(ids(), !allFav); }),
    btn('add', 'Add to album', () => albumDialog(ids())),
    EDITING ? btn('tag', 'Tag', () => tagDialog(ids())) : null,
    EDITING ? btn('edit', 'Edit', () => editDialog(ids())) : null,
    inAlbum ? btn('remove', 'Remove from album', async () => {
      try { await post(`/api/ualbums/${inAlbum}`, { ids: ids(), on: false }); } catch { toast('Could not update the album.'); return; }
      await loadState(); toast(`Removed ${nf.format(G.sel.size)} from the album.`); G.sel.clear(); viewKey = null; onRoute();
    }) : null,
    btn('download', 'Download zip', () => downloadDialog(photosWith({ ids: ids().join(',') }), G.sel.size)));
}
async function setFavorite(ids, on) {
  try { await post('/api/favorites', { ids, on }); } catch { toast('Could not save the favorite.'); return; }
  ids.forEach((id) => (on ? ST.fav.add(id) : ST.fav.delete(id)));
  ST.rev++;
  if (route.view === 'photos' && G.data) redrawTiles();
  updateSelBar();
  if (LB.open) updateFavBtn();
  if (ids.length > 1) toast(`${on ? 'Added' : 'Removed'} ${nf.format(ids.length)} ${on ? 'to' : 'from'} favorites.`);
}
function modal(title, ...kids) {
  const back = h('div', { class: 'modal-back', onclick: (e) => { if (e.target === back) back.remove(); } }, h('div', { class: 'modal' }, h('h3', null, title), ...kids));
  document.body.append(back);
  return back;
}
function albumDialog(ids) {
  const name = h('input', { class: 'pagefilter', style: 'margin:0;flex:1', placeholder: 'New album name' });
  const add = async (id, label) => {
    try {
      if (id == null) { if (!name.value.trim()) { name.focus(); return; } await post('/api/ualbums', { name: name.value.trim(), ids }); label = name.value.trim(); }
      else await post(`/api/ualbums/${id}`, { ids, on: true });
    } catch { toast('Could not update the album.'); return; }
    await loadState();
    back.remove();
    toast(`Added ${nf.format(ids.length)} to “${label}”.`, 'Open', () => { const a = ST.albums.find((x) => x.name === label); if (a) go('photos', photosWith({ ualbum: a.id })); });
  };
  const back = modal(`Add ${plural(ids.length, 'item')} to an album`,
    h('div', { class: 'alist' }, ST.albums.map((a) => h('div', { class: 'frow', onclick: () => add(a.id, a.name) }, icon('folder'), h('span', { class: 'nm' }, a.name), h('span', { class: 'ct' }, nf.format(a.n))))),
    h('div', { style: 'display:flex;gap:8px;margin-top:12px' }, name, h('button', { class: 'pillbtn on', onclick: () => add(null) }, icon('add'), 'Create')),
    h('div', { class: 'modal-btns' }, h('button', { class: 'pillbtn', onclick: () => back.remove() }, 'Cancel')));
  name.onkeydown = (e) => { if (e.key === 'Enter') add(null); };
  if (!ST.albums.length) name.focus();
}

// ---------------------------------------------------------------- metadata editing (XMP sidecars only)
function applyLocal(d, ch) {
  if ('rating' in ch) d.rating = ch.rating > 0 ? ch.rating : -1;
  for (const k of ['title', 'caption']) if (k in ch) d[k] = ch[k] || null;
  if ('taken' in ch) { d.taken = ch.taken; d.ts = Math.floor(Date.UTC(+ch.taken.slice(0, 4), +ch.taken.slice(5, 7) - 1, +ch.taken.slice(8, 10), +ch.taken.slice(11, 13), +ch.taken.slice(14, 16), +ch.taken.slice(17, 19)) / 1000); d.day = ch.taken.slice(0, 10); }
  if ('gps' in ch) { d.lat = ch.gps ? ch.gps.lat : null; d.lon = ch.gps ? ch.gps.lon : null; d.alt = ch.gps ? ch.gps.alt : null; }
  if (ch.template) { d.creator = ch.template.creator || null; d.copyright = ch.template.copyrightNotice || null; (d.extra ||= {}).copyright = Object.fromEntries(Object.entries(ch.template).filter(([, v]) => v)); }
  for (const id of ch.remove_tags || []) d.tags = d.tags.filter((t) => t.id !== id);
  for (const id of ch.add_tags || []) { const t = tagById.get(id); if (t && !d.tags.some((x) => x.id === id)) d.tags.push({ id, name: t.name, full: t.full, person: 0 }); }
  d.edited = 1;
}
async function editPhotos(ids, changes) {
  let r;
  try { r = await post('/api/edit', { ids, changes }); } catch (e) { toast('Could not save the change: ' + e.message); return false; }
  // a time shift lands differently on each photo, so those are re-fetched rather than patched locally
  for (const id of ids) { if ('shift' in changes) details.delete(id); else details.get(id)?.then((d) => applyLocal(d, changes)); }
  if (LB.open && ids.includes(LB.src.id[LB.i])) {
    const d = await getDetail(LB.src.id[LB.i]);
    if (LB.open && LB.src.id[LB.i] === d.id) { LB.detail = d; if (LB.info) renderInfo(); }  // unless the user has moved on meanwhile
    flashEdit(changes);
  }
  if (r.failed.length) toast(`${r.failed.length} could not be changed: ${r.failed[0].error}`);
  else if (ids.length > 1) toast(`Saved to ${nf.format(r.edited)} sidecar files. digiKam shows it after “Reread Metadata From File”, or apply them to its database from Explore.`);
  keepView = true;
  pollSoon();
  return true;
}
function flashEdit(ch) {
  const msg = 'rating' in ch ? (ch.rating ? '★'.repeat(ch.rating) : 'Rating cleared') : null;
  if (msg) toast(msg, null, null, 1200);
}
let RECENT_TAGS = null;
async function recentTags() { if (!RECENT_TAGS) try { RECENT_TAGS = (await api('/api/maintenance')).recentTags || []; } catch { RECENT_TAGS = []; } return RECENT_TAGS; }
async function noteRecent(ids) { try { RECENT_TAGS = (await post('/api/tags/recent', { ids })).recent; } catch { /* cosmetic */ } }
async function createTagThenPick(full, onPick) {
  // "Parent/Child" creates the child under an existing parent; a bare name makes a top-level tag
  const parts = full.split('/').map((s) => s.trim()).filter(Boolean);
  const name = parts.pop();
  let parent = 0;
  if (parts.length) { const p = META.tags.find((t) => !t.person && t.full.toLowerCase() === parts.join('/').toLowerCase()); if (!p) { toast(`Parent tag “${parts.join(' › ')}” does not exist.`); return; } parent = p.id; }
  if (!confirm(`Create the tag “${full}” in digiKam’s database? digiKam must be closed; a backup is made first.`)) return;
  let r;
  try { r = await post('/api/tags/op', { op: 'add', parent, name }); } catch (e) { toast(e.message, null, null, 9000); return; }
  await awaitReindex((m) => m.tags.some((t) => t.id === r.id));
  $('#taglist')?.remove();
  const t = tagById.get(r.id);
  if (t) onPick(t); else toast(`Created “${r.path}”; it will appear shortly.`);
}
function tagPicker(onPick, placeholder = 'Add a tag…', { recent = true } = {}) {
  const pick = (t) => { noteRecent([t.id]); onPick(t); };
  const wrap = h('div', { class: 'tpick' });
  if (recent) recentTags().then((ids) => { const row = ids.map((id) => tagById.get(id)).filter((t) => t && !t.person); if (row.length) wrap.prepend(h('div', { class: 'recent' }, h('span', { class: 'muted' }, 'Recent: '), row.map((t) => h('span', { class: 'ichip', title: t.full.replaceAll('/', ' › '), onclick: () => pick(t) }, t.name)))); });
  wrap.append(tagPickerInput(pick, placeholder));
  return wrap;
}
function tagPickerInput(onPick, placeholder) {
  const id = 'taglist';
  if (!$('#' + id)) document.body.append(h('datalist', { id }, META.tags.filter((t) => !t.person && !t.full.startsWith('People')).map((t) => h('option', { value: t.full }))));
  const inp = h('input', { class: 'pagefilter', style: 'margin:0;width:100%', placeholder, list: id });
  const tryPick = () => { const t = META.tags.find((x) => !x.person && x.full.toLowerCase() === inp.value.trim().toLowerCase()); if (t) { inp.value = ''; onPick(t); } };
  inp.oninput = tryPick;
  inp.onkeydown = (e) => { e.stopPropagation(); if (e.key === 'Enter') { tryPick(); if (inp.value.trim() && CAN_MANAGE) { const v = inp.value.trim(); inp.value = ''; createTagThenPick(v, onPick); } else if (inp.value) toast('Pick an existing tag from the list.'); } };
  if (CAN_MANAGE) inp.title = 'Type an existing tag, or a new one as “Parent/New tag” and press Enter to create it';
  return inp;
}
function editControls(cur, save) {
  // cur: {rating} of a single photo, or {} for a batch (digiKam's pick and color labels are not offered here)
  return [
    h('div', { class: 'erow' }, h('span', { class: 'el' }, 'Rating'), h('div', { class: 'stars' }, [1, 2, 3, 4, 5].map((n) => h('button', { class: n <= (cur.rating || 0) ? 'on' : '', title: `${n} star${n > 1 ? 's' : ''}`,
      onclick: () => save({ rating: cur.rating === n ? 0 : n }) }, icon('star'))), h('button', { class: 'clr', title: 'No rating', onclick: () => save({ rating: 0 }) }, icon('close')))),
  ];
}
function tagDialog(ids) {
  const back = modal(`Tag ${plural(ids.length, 'photo')}`,
    h('p', { class: 'muted' }, 'Pick a recent tag, type to find one, or type “Parent/New tag” and press Enter to create it. Each tag is applied as soon as you pick it.'),
    tagPicker((t) => editPhotos(ids, { add_tags: [t.id] })),
    h('div', { class: 'erow', style: 'margin-top:14px' }, h('span', { class: 'el' }, 'Remove'), tagPicker((t) => editPhotos(ids, { remove_tags: [t.id] }), 'Remove a tag from all…', { recent: false })),
    CAN_MANAGE ? h('div', { style: 'margin-top:14px' }, h('a', { class: 'lnk', onclick: () => { back.remove(); placeTagsDialog(ids); } }, 'Add place tags from GPS positions…')) : null,
    h('div', { class: 'modal-btns' }, h('button', { class: 'pillbtn on', onclick: () => back.remove() }, 'Done')));
}
function editDialog(ids) {
  const save = (ch) => editPhotos(ids, ch);
  const back = modal(`Edit ${plural(ids.length, 'item')}`,
    h('p', null, 'Each change is saved straight away to the XMP sidecar files. digiKam’s database is not touched.'),
    editControls({}, save),
    h('div', { class: 'erow' }, h('span', { class: 'el' }, 'Add tag'), tagPicker((t) => save({ add_tags: [t.id] }))),
    h('div', { class: 'erow' }, h('span', { class: 'el' }, 'Remove tag'), tagPicker((t) => save({ remove_tags: [t.id] }), 'Remove a tag…')),
    h('h4', null, 'Date'), dateEditor(ids, null),
    h('h4', null, 'Location and template'),
    h('div', { style: 'display:flex;gap:8px;flex-wrap:wrap' }, h('button', { class: 'pillbtn', onclick: () => locationDialog(ids, null) }, icon('place'), 'Set location on map'),
      h('button', { class: 'pillbtn', onclick: () => templatePicker(ids) }, icon('copyright'), 'Apply template'),
      h('button', { class: 'pillbtn', onclick: () => gpxDialog(ids) }, icon('map'), 'Correlate with GPS track')),
    h('div', { class: 'modal-btns' }, h('button', { class: 'pillbtn on', onclick: () => back.remove() }, 'Done')));
}

async function dbDialog() {
  let st;
  try { st = await api('/api/edits/db'); } catch { toast('Could not check the digiKam database status.'); return; }
  const msg = h('p', { class: st.digikamRunning ? 'warn' : '' }, st.digikamRunning
    ? (st.ask ? 'The viewer cannot see digiKam from inside its container. Quit digiKam, then confirm below.' : 'digiKam is running. Quit digiKam first; its database must not be changed while it is open.')
    : 'digiKam is closed, so its database can be updated now.');
  const vouch = st.ask && st.digikamRunning ? h('label', null, h('input', { type: 'checkbox', onchange: async (e) => {
    if (!e.target.checked) return;
    try { await post('/api/settings', { digikam_closed: true }); } catch (err) { toast(err.message); return; }
    back.remove(); dbDialog();
  } }), ' I have quit digiKam (this is trusted for 10 minutes)') : null;
  const applyBtn = h('button', { class: 'pillbtn on', disabled: !!st.digikamRunning || !st.pending, onclick: async () => {
    applyBtn.textContent = 'Updating…';
    try {
      const r = await post('/api/edits/db', {});
      back.remove();
      toast(`Updated ${plural(r.applied, 'item')} in digiKam’s database.` + (r.skipped.length ? ` ${r.skipped.length} skipped: ${r.skipped[0].reason}.` : ''), null, null, 9000);
      keepView = true; pollSoon();
    } catch (e) { applyBtn.textContent = 'Apply to digiKam database'; msg.className = 'warn'; msg.textContent = e.message; }
  } }, 'Apply to digiKam database');
  const back = modal('Apply edits to digiKam’s database',
    h('p', null, `${plural(st.pending, 'photo has', 'photos have')} edits that are saved in XMP sidecars but not yet in digiKam’s database.`),
    h('p', null, 'This writes the same ratings, labels, titles, captions and tags into digikam4.db. A copy of the database is saved in the viewer’s data/db-backups folder first.'),
    msg, vouch,
    h('div', { class: 'modal-btns' }, h('button', { class: 'pillbtn', onclick: () => back.remove() }, 'Cancel'),
      h('a', { class: 'pillbtn', href: hashFor('photos', photosWith({ edited: 1 })), onclick: () => back.remove() }, 'Show them'), applyBtn));
}

// ---------------------------------------------------------------- date, location and template editing
const TEMPLATE_LABEL = { creator: 'Creator', copyrightNotice: 'Copyright notice', rightsUsageTerms: 'Usage terms', creatorJobTitle: 'Job title', provider: 'Credit', source: 'Source', instructions: 'Instructions',
  'creatorContactInfo.address': 'Address', 'creatorContactInfo.city': 'City', 'creatorContactInfo.provinceState': 'State / province', 'creatorContactInfo.postalCode': 'Postal code', 'creatorContactInfo.country': 'Country', 'creatorContactInfo.phone': 'Phone', 'creatorContactInfo.email': 'Email', 'creatorContactInfo.webUrl': 'Web' };
let TEMPLATES = null;
async function loadTemplates() { if (!TEMPLATES) try { TEMPLATES = (await api('/api/maintenance')).templates || []; } catch { TEMPLATES = []; } return TEMPLATES; }
function dateEditor(ids, current, after) {
  // current: "YYYY-MM-DDTHH:MM:SS" for one photo, or null for a batch
  const inp = h('input', { class: 'einput', type: 'datetime-local', step: 1, value: (current || '').slice(0, 16), style: 'margin:0;width:auto' });
  const setBtn = h('button', { class: 'pillbtn', onclick: async () => { if (!inp.value) return; const t = inp.value.length === 16 ? inp.value + ':00' : inp.value; if (await editPhotos(ids, { taken: t })) after?.(); } }, 'Set date');
  const amount = h('input', { class: 'einput', type: 'number', value: 1, style: 'margin:0;width:70px' });
  const unit = h('select', null, [['3600', 'hours'], ['60', 'minutes'], ['86400', 'days'], ['1', 'seconds']].map(([v, l]) => h('option', { value: v }, l)));
  const shift = (sign) => async () => { const s = sign * Math.round(+amount.value * +unit.value); if (!s) return; if (await editPhotos(ids, { shift: s })) after?.(); };
  return h('div', { class: 'dateedit' },
    h('div', { class: 'erow' }, h('span', { class: 'el' }, ids.length > 1 ? 'Set all to' : 'Taken'), inp, setBtn),
    h('div', { class: 'erow' }, h('span', { class: 'el' }, 'Shift by'), amount, unit, h('button', { class: 'pillbtn', title: 'Move the date later', onclick: shift(1) }, '+ later'), h('button', { class: 'pillbtn', title: 'Move the date earlier', onclick: shift(-1) }, '− earlier')),
    h('div', { class: 'muted', style: 'font-size:12px' }, 'Shifting keeps each photo’s own time and moves it by the same amount, for a camera clock that was wrong.'));
}
async function locationDialog(ids, current, after) {
  // current: {lat, lon, alt} or null. Drag the marker or click the map; coordinates can also be typed.
  const lat = h('input', { class: 'einput', type: 'number', step: 'any', placeholder: 'latitude', value: current?.lat ?? '', style: 'margin:0;width:140px' });
  const lon = h('input', { class: 'einput', type: 'number', step: 'any', placeholder: 'longitude', value: current?.lon ?? '', style: 'margin:0;width:140px' });
  const alt = h('input', { class: 'einput', type: 'number', step: 'any', placeholder: 'altitude m', value: current?.alt ?? '', style: 'margin:0;width:110px' });
  const mapEl = h('div', { class: 'imap', style: 'height:360px;margin:10px 0' });
  // address or landmark search (OpenStreetMap Nominatim through the server; GeoNames towns offline)
  let searchTimer = 0;
  const results = h('div', { class: 'alist', style: 'max-height:160px;margin-top:4px', hidden: true });
  const search = h('input', { class: 'einput', placeholder: 'Search an address or place, e.g. “Mt Lebanon High School”', style: 'margin:0;flex:1;min-width:240px',
    onkeydown: (e) => { e.stopPropagation(); if (e.key === 'Enter') { e.preventDefault(); clearTimeout(searchTimer); run(); } if (e.key === 'Escape') { results.hidden = true; } },
    oninput: () => { clearTimeout(searchTimer); searchTimer = setTimeout(run, 500); } });
  const run = async () => {
    const q = search.value.trim();
    if (q.length < 2) { results.hidden = true; return; }
    let r;
    try { r = await api('/api/geocode?q=' + encodeURIComponent(q)); } catch (e) { toast(e.message); return; }
    if (search.value.trim() !== q) return;
    results.hidden = false;
    fill(results, r.results.length ? r.results.map((x) => h('div', { class: 'frow', style: 'height:auto;padding:6px 8px', title: `${x.lat}, ${x.lon}`, onclick: () => {
      lat.value = x.lat; lon.value = x.lon; results.hidden = true; search.value = x.name; place();
      if (map) map.setView([x.lat, x.lon], x.zoom || 14);
    } }, icon('place'), h('span', { class: 'nm', style: 'white-space:normal' }, x.name, x.detail ? h('span', { class: 'muted' }, ' · ' + x.detail) : null)))
      : h('div', { class: 'muted', style: 'padding:6px 8px' }, r.source === 'offline' ? 'No town by that name in the offline place list (no internet connection for the full search).' : 'Nothing found.'));
  };
  const back = modal(ids.length > 1 ? `Set location for ${nf.format(ids.length)} photos` : 'Set location',
    h('p', { class: 'muted' }, 'Click the map or drag the pin, or type coordinates. Saved to the sidecar (and file, if on) and shown in digiKam after its database is updated.'),
    h('div', { style: 'display:flex;gap:8px;align-items:center;margin-top:6px' }, search), results,
    mapEl,
    h('div', { style: 'display:flex;gap:8px;flex-wrap:wrap;align-items:center' }, lat, lon, alt,
      h('button', { class: 'pillbtn', title: 'Use the location of the previous photo in the grid', onclick: () => { const i = G.data?.id.indexOf(ids[0]); for (let k = (i ?? 0) - 1; k >= 0; k--) { if (G.geo.has(k)) { getDetail(G.data.id[k]).then((d) => { lat.value = d.lat; lon.value = d.lon; alt.value = d.alt ?? ''; place(); }); return; } } toast('No earlier photo in this view has a location.'); } }, 'Copy from previous photo')),
    h('div', { class: 'modal-btns' }, h('button', { class: 'pillbtn', onclick: () => back.remove() }, 'Cancel'),
      current ? h('button', { class: 'pillbtn', onclick: async () => { if (confirm('Remove the location from ' + (ids.length > 1 ? 'these photos' : 'this photo') + '?')) { back.remove(); if (await editPhotos(ids, { gps: null })) after?.(); } } }, 'Remove location') : null,
      h('button', { class: 'pillbtn on', onclick: async () => { const la = +lat.value, lo = +lon.value; if (!lat.value || !lon.value || Math.abs(la) > 90 || Math.abs(lo) > 180) { toast('Enter a valid latitude and longitude.'); return; } back.remove(); if (await editPhotos(ids, { gps: { lat: la, lon: lo, alt: alt.value === '' ? null : +alt.value } })) after?.(); } }, icon('place'), 'Save location')));
  let map, marker;
  const place = () => { if (!map || !lat.value || !lon.value) return; const ll = [+lat.value, +lon.value]; marker ? marker.setLatLng(ll) : (marker = L.marker(ll, { draggable: true }).addTo(map).on('dragend', () => { const p = marker.getLatLng(); lat.value = p.lat.toFixed(6); lon.value = p.lng.toFixed(6); })); map.setView(ll, Math.max(map.getZoom(), 12)); };
  // a pasted "40.4441, -79.9623" (comma, semicolon or space separated; N/S/E/W suffixes allowed) fills both fields
  const pastePair = (e) => {
    const t = (e.clipboardData || window.clipboardData)?.getData('text') || '';
    const m = t.trim().match(/^(-?\d+(?:\.\d+)?)\s*°?\s*([NS])?\s*[,;\s]\s*(-?\d+(?:\.\d+)?)\s*°?\s*([EW])?$/i);
    if (!m) return;
    e.preventDefault();
    const la = +m[1] * (m[2] && m[2].toUpperCase() === 'S' ? -1 : 1), lo = +m[3] * (m[4] && m[4].toUpperCase() === 'W' ? -1 : 1);
    if (Math.abs(la) > 90 || Math.abs(lo) > 180) { toast('That does not look like a latitude, longitude pair.'); return; }
    lat.value = la; lon.value = lo; place();
    if (map) map.setView([la, lo], Math.max(map.getZoom(), 12));
  };
  lat.onpaste = lon.onpaste = pastePair;
  try { await loadLeaflet(false); } catch { mapEl.replaceChildren(h('div', { class: 'empty' }, 'The map needs an internet connection; coordinates can still be typed.')); return; }
  const L = window.L;
  await loadMaps();
  map = L.map(mapEl).setView(current ? [current.lat, current.lon] : [40.4, -80], current ? 13 : 4);
  tiles().addTo(map);
  map.on('click', (e) => { lat.value = e.latlng.lat.toFixed(6); lon.value = e.latlng.lng.toFixed(6); place(); });
  lat.onchange = lon.onchange = place;
  place();
}
async function gpxDialog(ids) {
  const file = h('input', { type: 'file', accept: '.gpx,application/gpx+xml' });
  const tzNow = -new Date().getTimezoneOffset() * 60;  // this browser's offset, as a sensible default
  const offset = h('select', null, [...Array(27)].map((_, i) => i - 12).map((hh) => h('option', { value: hh * 3600, selected: hh * 3600 === tzNow }, `UTC${hh >= 0 ? '+' : ''}${hh}`)));
  const shiftAmt = h('input', { class: 'einput', type: 'number', value: 0, style: 'margin:0;width:70px' });
  const shiftUnit = h('select', null, [['60', 'minutes'], ['1', 'seconds'], ['3600', 'hours']].map(([v, l]) => h('option', { value: v }, l)));
  const gap = h('select', null, [[120, '2 minutes'], [600, '10 minutes'], [1800, '30 minutes'], [3600, '1 hour'], [21600, '6 hours']].map(([v, l]) => h('option', { value: v, selected: v === 600 }, l)));
  const onlyMissing = h('input', { type: 'checkbox', checked: true });
  const result = h('div');
  const mapEl = h('div', { class: 'imap', style: 'height:260px;margin-top:10px', hidden: true });
  let token = null, preview = null;
  const params = () => ({ utc_offset: +offset.value, clock_shift: Math.round(+shiftAmt.value * +shiftUnit.value), max_gap: +gap.value, only_missing: onlyMissing.checked });
  const run = async () => {
    if (!file.files[0]) { toast('Choose a .gpx file first.'); return; }
    const fd = new FormData();
    fd.append('file', file.files[0]); fd.append('ids', ids.join(','));
    Object.entries(params()).forEach(([k, v]) => fd.append(k, v === true ? '1' : v === false ? '0' : v));
    fill(result, h('p', { class: 'muted' }, 'Matching…'));
    let r;
    try { const res = await fetch('/api/gpx/preview', { method: 'POST', body: fd }); r = await res.json(); if (!res.ok) throw new Error(r.detail || res.status); } catch (e) { fill(result, h('p', { class: 'warn' }, e.message)); return; }
    token = r.token; preview = r;
    const t = r.track;
    fill(result,
      h('p', null, `Track: ${nf.format(t.points)} points, ${t.km} km, ${fmtWhen(t.start)} to ${dfTimeLocal.format(date(t.end))} (in this browser’s time zone).`),
      h('p', null, h('b', null, `${nf.format(r.matched)} of ${nf.format(r.considered)} photos match`), r.unmatched ? ` (${nf.format(r.unmatched)} were taken too far from any track point)` : '', r.skipped_with_position ? `; ${nf.format(r.skipped_with_position)} already had a position and were left alone.` : '.'),
      r.matched ? h('div', { class: 'muted', style: 'font-size:12.5px' }, 'Typical gap between photo time and nearest track point: ', `${Math.round(r.matches.reduce((a, m) => a + m.gap, 0) / r.matches.length)} s`, '. If photos land in the wrong place, the camera clock or the UTC offset is off; adjust and match again.') : null);
    mapEl.hidden = !r.matched;
    if (r.matched) try {
      await loadLeaflet(false);
      const L = window.L;
      mapEl.replaceChildren();
      await loadMaps();
      const map = L.map(mapEl).fitBounds([[t.bbox[0], t.bbox[1]], [t.bbox[2], t.bbox[3]]]);
      tiles().addTo(map);
      r.matches.slice(0, 500).forEach((m) => L.circleMarker([m.lat, m.lon], { radius: 4, color: '#1a73e8', fillOpacity: .8 }).bindTooltip(m.name).addTo(map));
    } catch { mapEl.hidden = true; }
  };
  const back = modal(`Correlate ${nf.format(ids.length)} photos with a GPS track`,
    h('p', { class: 'muted' }, 'Like digiKam’s Geolocation Editor: each photo gets the position the track recorded at the moment it was taken. Track times are UTC; tell it what time zone the camera clock was set to.'),
    h('div', { class: 'erow' }, h('span', { class: 'el' }, 'GPX file'), file),
    h('div', { class: 'erow' }, h('span', { class: 'el' }, 'Camera zone'), offset, h('span', { class: 'muted', style: 'font-size:12px' }, 'what the camera’s clock was set to')),
    h('div', { class: 'erow' }, h('span', { class: 'el' }, 'Clock error'), shiftAmt, shiftUnit, h('span', { class: 'muted', style: 'font-size:12px' }, 'negative if the camera ran fast')),
    h('div', { class: 'erow' }, h('span', { class: 'el' }, 'Max gap'), gap, h('label', { style: 'display:flex;gap:6px;align-items:center;margin-left:12px' }, onlyMissing, 'only photos without a position')),
    h('div', { style: 'margin:8px 0' }, h('button', { class: 'pillbtn', onclick: run }, icon('spark'), 'Match')),
    result, mapEl,
    h('div', { class: 'modal-btns' }, h('button', { class: 'pillbtn', onclick: () => back.remove() }, 'Cancel'),
      h('button', { class: 'pillbtn on', onclick: async () => {
        if (!token || !preview?.matched) { toast('Match first.'); return; }
        if (!confirm(`Write positions to ${nf.format(preview.matched)} photos? Sidecars are backed up first; digiKam gets them with “Apply edits to digiKam database”.`)) return;
        try { const r = await post('/api/gpx/apply', { token, ids, ...params() }); back.remove(); toast(`Positions written to ${nf.format(r.edited)} photos.`); keepView = true; pollSoon(); }
        catch (e) { toast(e.message, null, null, 9000); }
      } }, icon('place'), 'Apply positions')));
  file.onchange = run;
}
async function templatePicker(ids, after) {
  const tpls = await loadTemplates();
  const back = modal(`Apply a metadata template to ${plural(ids.length, 'photo')}`,
    tpls.length ? h('div', { class: 'alist' }, tpls.map((t) => h('div', { class: 'frow', style: 'height:auto;padding:6px 8px', onclick: async () => { back.remove(); if (await editPhotos(ids, { template: Object.fromEntries(Object.keys(TEMPLATE_LABEL).map((k) => [k, t.fields[k] || ''])) })) after?.(); } },
      icon('copyright'), h('div', null, h('b', null, t.name), h('div', { class: 'muted', style: 'font-size:12px' }, Object.entries(t.fields).filter(([, v]) => v).map(([k, v]) => `${TEMPLATE_LABEL[k]}: ${v}`).join(' · ')))))) 
      : h('p', { class: 'muted' }, 'No templates yet. Define them in Settings > Metadata templates.'),
    h('p', { class: 'muted', style: 'font-size:12px' }, 'Applying a template sets every template field; fields left empty in the template are cleared on the photo, as in digiKam.'),
    h('div', { class: 'modal-btns' }, h('a', { class: 'pillbtn', href: '#/settings', onclick: () => back.remove() }, 'Manage templates'), h('button', { class: 'pillbtn', onclick: () => back.remove() }, 'Cancel')));
}
function templatesSection(m) {
  const list = h('div');
  let tpls = (m.templates || []).map((t) => ({ ...t, fields: { ...t.fields } }));
  const save = async () => { try { await post('/api/settings', { templates: tpls }); TEMPLATES = null; toast('Templates saved.'); } catch (e) { toast(e.message); } draw(); };
  const edit = (t, isNew) => {
    const name = h('input', { class: 'einput', style: 'margin:0', placeholder: 'Template name', value: t.name || '' });
    const inputs = Object.keys(TEMPLATE_LABEL).map((k) => [k, h('input', { class: 'einput', style: 'margin:0', placeholder: TEMPLATE_LABEL[k], value: t.fields[k] || '' })]);
    const back = modal(isNew ? 'New metadata template' : `Edit “${t.name}”`,
      h('div', { class: 'erow' }, h('span', { class: 'el' }, 'Name'), name),
      h('div', { class: 'alist', style: 'max-height:50vh' }, inputs.map(([k, inp]) => h('div', { class: 'erow' }, h('span', { class: 'el', style: 'width:120px' }, TEMPLATE_LABEL[k]), inp))),
      h('div', { class: 'modal-btns' }, h('button', { class: 'pillbtn', onclick: () => back.remove() }, 'Cancel'),
        h('button', { class: 'pillbtn on', onclick: () => { if (!name.value.trim()) { name.focus(); return; } t.name = name.value.trim(); inputs.forEach(([k, inp]) => { t.fields[k] = inp.value.trim(); }); if (isNew) tpls.push(t); back.remove(); save(); } }, 'Save')));
  };
  const draw = () => fill(list, tpls.map((t) => h('div', { class: 'srow' }, h('div', null, h('b', null, t.name), h('div', { class: 'muted', style: 'font-size:13px' }, Object.entries(t.fields).filter(([, v]) => v).map(([k, v]) => `${TEMPLATE_LABEL[k]}: ${v}`).join(' · ') || 'empty')),
      h('span', { style: 'display:flex;gap:6px' }, h('button', { class: 'pillbtn', onclick: () => edit(t, false) }, 'Edit'), h('button', { class: 'pillbtn', onclick: () => { if (confirm(`Delete the template “${t.name}”? Photos it was applied to are not changed.`)) { tpls = tpls.filter((x) => x !== t); save(); } } }, 'Delete')))),
    h('div', { style: 'margin-top:10px' }, h('button', { class: 'pillbtn', onclick: () => edit({ name: '', fields: {} }, true) }, icon('add'), 'New template')));
  draw();
  return h('div', null, h('h2', null, 'Metadata templates'), h('div', { class: 'muted', style: 'max-width:820px' }, 'Like digiKam’s templates: creator, copyright, credit, source, instructions and contact details, applied to any selection in one go from the Edit dialog or the info panel.'), list);
}

// ---------------------------------------------------------------- zip download
async function downloadDialog(p, selected) {
  p = new URLSearchParams(p);
  p.delete('sort');
  const name = selected ? `${selected} selected photos` : (chipList(p).map((c) => c.label.replace(/[“”]/g, '')).join(' ') || 'photos').slice(0, 80);
  const side = h('input', { type: 'checkbox' });
  const size = h('select', null, [[1000, '1 GB'], [2000, '2 GB'], [4000, '4 GB'], [8000, '8 GB']].map(([v, l]) => h('option', { value: v, selected: v === 2000 }, l)));
  const body = h('div', null, h('p', null, 'Working out the download…'));
  const back = modal('Download as zip', body,
    h('label', { style: 'margin-top:12px' }, side, ' Include digiKam XMP sidecar files'),
    h('label', { style: 'margin-top:8px' }, 'Split into zip files of at most ', size),
    h('div', { class: 'modal-btns' }, h('button', { class: 'pillbtn', onclick: () => back.remove() }, 'Close')));
  // the browser downloads each part through a hidden form, so even huge selections work
  const fetchPart = (i) => {
    const q = new URLSearchParams(p);
    q.set('name', name); q.set('part', i); q.set('part_mb', size.value);
    if (side.checked) q.set('sidecars', '1');
    const form = h('form', { method: 'post', action: '/api/zip', style: 'display:none' }, [...q].map(([k, v]) => h('input', { type: 'hidden', name: k, value: v })));
    document.body.append(form); form.submit(); form.remove();
  };
  const plan = async () => {
    const q = new URLSearchParams(p);
    q.set('part_mb', size.value);
    let r;
    try {
      const res = await fetch('/api/zip/plan', { method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body: q.toString() });
      r = await res.json();
      if (!res.ok) throw new Error(r.detail || res.status);
    } catch (e) { fill(body, h('p', { class: 'warn' }, String(e.message || e))); return; }
    if (!r.files) { fill(body, h('p', null, 'Nothing to download.')); return; }
    const one = r.parts.length === 1;
    fill(body,
      h('p', null, `${nf.format(r.files)} original ${r.files === 1 ? 'file' : 'files'}, ${fmtBytes(r.bytes)}, in their album folders${one ? '.' : `, split into ${r.parts.length} zip files.`}`),
      one ? h('button', { class: 'pillbtn on', onclick: () => { fetchPart(0); toast('Download started.'); } }, icon('download'), 'Download')
        : [h('div', { class: 'alist' }, r.parts.map((pt, i) => { const b = h('div', { class: 'frow', title: `${pt.first} … ${pt.last}`, onclick: () => { fetchPart(i); b.classList.add('on'); } },
            icon('download'), h('span', { class: 'nm' }, `Part ${i + 1}`, h('span', { class: 'muted' }, `  ${pt.first === pt.last ? pt.first : pt.first + ' … ' + pt.last}`)), h('span', { class: 'ct' }, `${nf.format(pt.files)} · ${fmtBytes(pt.bytes)}`)); return b; })),
          h('p', { class: 'muted', style: 'margin:10px 0 0;font-size:12.5px' }, 'Click each part to download it. Parts follow album order, and unzipping them all into one folder gives the complete set.')]);
  };
  size.onchange = plan;
  plan();
}

// ---------------------------------------------------------------- explore / people / albums / tags
function card({ img, fallback, name, sub, onclick }) {
  const im = img ? h('img', { src: img, alt: '', loading: 'lazy' }) : null;
  if (im && fallback) im.onerror = () => { im.onerror = null; im.src = fallback; };
  return h('div', { class: 'card', onclick }, h('span', { class: 'cv' }, im), h('div', { class: 'nm', title: name }, name), sub ? h('div', { class: 'sb' }, sub) : null);
}
const thumbCard = (cover, name, sub, params) => card({ img: cover ? `/thumb/${cover}` : null, name, sub, onclick: () => go('photos', photosWith(params)) });
const personCard = (t) => card({ img: faceUrl(t.id), fallback: t.cover ? `/thumb/${t.cover}` : null, name: t.name, sub: nf.format(t.nAll), onclick: () => go('photos', photosWith({ tag: t.id })) });
/** Leaf person tags with photos (a person tag with children is a family/group). */
const people = () => META.tags.filter((t) => t.person && t.n > 0 && !t.hasKids).sort((a, b) => b.nAll - a.nAll);

async function showExplore() {
  const now = new Date();
  const md = `${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  const strip = h('div', { class: 'jrows' });
  const otd = h('div', { hidden: true }, h('h2', { style: '--hue:var(--c-rose)' }, h('span', { class: 'hic' }, icon('calendar')), `On this day · ${MONTHS[now.getMonth()]} ${now.getDate()}`, h('a', { href: hashFor('photos', photosWith({ md })) }, 'See all')), strip);
  const detected = h('div', { hidden: true }), trips = h('div', { hidden: true });
  const rootTags = META.tags.filter((t) => t.pid == null && t.nAll && !(t.person && !META.tags.some((c) => c.pid === t.id))).sort((a, b) => b.nAll - a.nAll);
  const pill = (label, n, params) => h('a', { class: 'pill', href: hashFor('photos', photosWith(params)) }, label, n != null ? h('b', null, nf.format(n)) : null);
  const count = (list, v) => (list.find((x) => x[0] === v) || [0, 0])[1];
  const ppl = people();
  // the summary: one card per number, each with an icon and its own colour; most open the matching view
  const stat = (hue, ic, value, label, href) => h(href ? 'a' : 'div', { class: 'stat', style: `--hue:var(--c-${hue})`, href },
    h('span', { class: 'sic' }, icon(ic)), h('div', null, h('b', null, value), h('span', null, label)));
  // section headings with a coloured icon; the pill group below a heading shares its hue
  const sec = (hue, ic, title, link, linkLabel) => h('h2', { style: `--hue:var(--c-${hue})` }, h('span', { class: 'hic' }, icon(ic)), title, link ? h('a', { href: link }, linkLabel) : null);
  const group = (hue, ...kids) => h('div', { class: 'pills', style: `--hue:var(--c-${hue})` }, ...kids);
  main.replaceChildren(h('div', { class: 'page' },
    h('h1', null, 'Explore'),
    h('div', { class: 'stats' },
      stat('blue', 'photo', nf.format(META.total - META.videos), 'photos', '#/photos'),
      stat('purple', 'video', nf.format(META.videos), 'videos', hashFor('photos', photosWith({ type: 'video' }))),
      stat('amber', 'person', nf.format(ppl.length), 'people', '#/people'),
      stat('teal', 'folder', nf.format(META.albums.length), 'albums', '#/albums'),
      stat('green', 'place', nf.format(META.geotagged), 'with location', '#/map'),
      stat('slate', 'disk', fmtBytes(META.bytes), 'on disk')),
    otd,
    META.places.length ? [sec('green', 'place', 'Places', '#/places', 'See all'),
      h('div', { class: 'cards' }, META.places.slice(0, 12).map(placeCard))] : null,
    sec('amber', 'person', 'People', '#/people', 'See all'),
    h('div', { class: 'cards people' }, ppl.slice(0, 16).map(personCard)),
    detected, trips,
    sec('orange', 'tag', 'Things', '#/tags', 'All tags'),
    h('div', { class: 'cards' }, rootTags.map((t) => thumbCard(t.cover, t.name, nf.format(t.nAll), { tag: t.id }))),
    sec('cyan', 'tune', 'Quick filters'),
    h('div', { class: 'pills' },
      pill('Videos', META.videos, { type: 'video' }), pill('★★★★★', count(META.ratings, 5), { rating: 5 }),
      pill('★★★ and up', META.ratings.filter((r) => r[0] >= 3).reduce((a, r) => a + r[1], 0), { rating: 3 }),
      USER?.person && tagById.get(USER.person) ? pill('Photos of me', tagById.get(USER.person).nAll, { tag: USER.person }) : null,
      pill('Untagged', null, { untagged: 1 }),
      pill('No location', META.total - META.geotagged, { geo: 0 }), pill('Favorites', ST.fav.size, { fav: 1 }),
      h('a', { class: 'pill', href: '#/duplicates' }, 'Duplicate files'), h('a', { class: 'pill', href: '#/bursts' }, 'Bursts & best shots'),
      h('a', { class: 'pill', href: '#/events' }, 'Events & trips'), h('a', { class: 'pill', href: '#/settings' }, 'Settings'), h('a', { class: 'pill', href: '#/maintenance' }, 'Maintenance'), pill('Contains text', null, { hastext: 1 }), pill('Blurry', null, { blurry: 1 }),
      EDITING ? pill('Edited here, not yet in digiKam', PENDING, { edited: 1 }) : null,
      EDITING && PENDING ? h('a', { class: 'pill', onclick: dbDialog }, 'Apply edits to digiKam database…') : null,
      h('a', { class: 'pill', href: '#/map' }, 'Map', h('b', null, nf.format(META.geotagged)))),
    EDITING ? [h('h2', null, 'Editing'),
      h('label', { style: 'display:flex;gap:10px;align-items:flex-start;max-width:760px;cursor:pointer' },
        h('input', { type: 'checkbox', checked: WRITE_FILES, style: 'margin-top:3px', onchange: async (e) => {
          try { WRITE_FILES = (await post('/api/settings', { write_files: e.target.checked })).write_files; } catch { e.target.checked = WRITE_FILES; toast('Could not change the setting.'); return; }
          toast(WRITE_FILES ? 'Edits will now also be written into JPEG, PNG, TIFF and WebP files.' : 'Edits will be written to sidecars only.');
        } }),
        h('span', null, 'Also write metadata into the image files (XMP, EXIF and IPTC), like digiKam’s “write to sidecar and file” mode. ',
          h('span', { class: 'muted' }, 'Applies to JPEG, PNG, TIFF and WebP; other formats and videos stay sidecar-only, as in digiKam. Before a file is first rewritten, the original is copied to the viewer’s file-backups folder, and Undo restores it.')))] : null,
    sec('blue', 'calendar', 'Years'),
    group('blue', META.years.map(([y, n]) => pill(y, n, { year: y }))),
    sec('purple', 'camera', 'Cameras'),
    group('purple', META.cameras.map(([c, n]) => pill(c, n, { camera: c }))),
    sec('teal', 'camera', 'Lenses'),
    group('teal', META.lenses.slice(0, 40).map(([c, n]) => pill(c, n, { lens: c }))),
    META.creators.length ? [sec('rose', 'copyright', 'Photographers'), group('rose', META.creators.slice(0, 30).map(([c, n]) => pill(c, n, { creator: c })))] : null,
    sec('slate', 'photo', 'File types'),
    group('slate', META.formats.map(([c, n]) => pill(c, n, { fmt: c })))));
  api('/api/events').then((ev) => {
    const list = ev.events.filter((e) => e.kind === 'trip').slice(0, 8);
    if (route.view !== 'explore' || !list.length) return;
    fill(trips, h('h2', { style: '--hue:var(--c-cyan)' }, h('span', { class: 'hic' }, icon('map')), 'Trips', h('a', { href: '#/events' }, 'All events & trips')), h('div', { class: 'cards' }, list.map(eventCard)));
    trips.hidden = false;
  }).catch(() => {});
  if (SEM.enabled) api('/api/concepts').then((c) => {
    if (route.view !== 'explore' || !c.concepts.length) return;
    fill(detected, h('h2', { style: '--hue:var(--c-purple)' }, h('span', { class: 'hic' }, icon('spark')), 'Detected content', h('a', { href: '#/detected' }, 'See all')),
      h('div', { class: 'cards' }, c.concepts.sort((a, b) => b.n - a.n).slice(0, 12).map(conceptCard)));
    detected.hidden = false;
  }).catch(() => {});
  try {
    const d = await api(`/api/photos?md=${md}&norejected=1`);
    if (route.view !== 'explore' || !d.count) return;
    for (let i = 0; i < Math.min(d.count, 24); i++) {  // a few rows; "See all" has the rest
      strip.append(h('div', { class: 'tile', style: `--ar:${Math.max(0.5, Math.min(2.2, d.w[i] / (d.h[i] || 1))).toFixed(3)}`, title: dfDay.format(date(d.ts[i])),
        onclick: () => go('photos', photosWith({ md, norejected: 1, p: d.id[i] })) }, h('img', { src: `/thumb/${d.id[i]}`, loading: 'lazy', alt: '' })));
    }
    otd.hidden = false;
  } catch { /* optional section */ }
}

function showPeople() {
  const all = people();
  const cards = h('div', { class: 'cards people' });
  const draw = (f) => cards.replaceChildren(...all.filter((t) => !f || t._n.includes(f)).map(personCard));
  const todo = h('div', { class: 'pills', style: 'margin:6px 0 4px' });
  api('/api/faces/summary').then((s) => fill(todo,
    s.suggested[0] ? h('a', { class: 'pill', href: '#/faces?tab=suggested' }, 'Suggestions to confirm', h('b', null, `${nf.format(s.suggested[1])} in ${nf.format(s.suggested[0])} photos`)) : null,
    s.unknown[0] ? h('a', { class: 'pill', href: '#/faces?tab=unknown' }, 'Unnamed faces', h('b', null, `${nf.format(s.unknown[1])} in ${nf.format(s.unknown[0])} photos`)) : null,
    s.ignored[0] ? h('a', { class: 'pill', href: '#/faces?tab=ignored' }, 'Ignored faces', h('b', null, nf.format(s.ignored[1]))) : null)).catch(() => {});
  main.replaceChildren(h('div', { class: 'page' }, h('h1', null, 'People ', h('span', { class: 'muted' }, nf.format(all.length))), todo,
    h('input', { class: 'pagefilter', placeholder: 'Find a person…', oninput: (e) => draw(norm(e.target.value)) }), h('div', { style: 'height:14px' }), cards));
  draw('');
}

function showAlbums() {
  const root = META.albums.find((a) => a.pid == null);
  const tops = META.albums.filter((a) => root && a.pid === root.id).sort((a, b) => b.path.localeCompare(a.path, undefined, { numeric: true }));
  const body = h('div');
  const albumCard = (a, name) => withDl(a, thumbCard(a.cover, name, `${nf.format(a.nAll)} · ${fmtRange(a.tsMin, a.tsMax)}`, { album: a.id, sort: 'old' }));
  const withDl = (a, c) => { c.querySelector('.cv').append(h('button', { class: 'carddl', title: 'Download this album as a zip', onclick: (e) => { e.stopPropagation(); downloadDialog(photosWith({ album: a.id })); } }, icon('download'))); return c; };
  // viewer albums: a change is posted, then the list is redrawn from the reloaded state
  const change = async (path, body) => { try { await post(path, body); } catch { toast('Could not update the album.'); return; } await loadState(); showAlbums(); };
  const mine = (a) => {
    const c = thumbCard(a.cover, a.name, plural(a.n, 'item'), { ualbum: a.id });
    const act = (ic, title, fn) => h('button', { class: 'carddl', title, onclick: async (e) => { e.stopPropagation(); await fn(); } }, icon(ic));
    c.querySelector('.cv').append(h('span', { class: 'cardacts' },
      act('link', 'Copy a link to this album', async () => { await navigator.clipboard?.writeText(location.origin + '/' + hashFor('photos', photosWith({ ualbum: a.id }))); toast('Link copied. It works for anyone who can reach this viewer.'); }),
      act('edit', 'Rename', () => { const n = prompt('Album name', a.name); if (n && n.trim()) return change(`/api/ualbums/${a.id}`, { name: n.trim() }); }),
      act('download', 'Download as a zip', () => downloadDialog(photosWith({ ualbum: a.id }))),
      act('trash', 'Delete this album (photos are not touched)', () => { if (confirm(`Delete the album “${a.name}”? The photos themselves are not affected.`)) return change(`/api/ualbums/${a.id}`, { delete: true }); })));
    return c;
  };
  const newCard = h('div', { class: 'card', onclick: () => { const n = prompt('Name for the new album'); if (n && n.trim()) change('/api/ualbums', { name: n.trim() }); } },
    h('span', { class: 'cv newalbum' }, icon('add')), h('div', { class: 'nm' }, 'New album'), h('div', { class: 'sb' }, 'Stored in the viewer, not in digiKam'));
  const draw = (f) => {
    body.replaceChildren();
    const my = ST.albums.filter((a) => !f || norm(a.name).includes(f));
    if (my.length || !f) body.append(h('h2', null, 'My albums', h('span', { class: 'muted' }, 'made in this viewer')),
      h('div', { class: 'cards' }, my.map(mine), f ? null : newCard), h('h2', { style: 'margin-top:40px' }, 'digiKam folders'));
    for (const t of tops) {
      const kids = META.albums.filter((a) => a.path.startsWith(t.path + '/') && (!f || a._n.includes(f)));
      const self = !f || t._n.includes(f);
      if (!kids.length && !self) continue;
      body.append(h('h2', { class: 'sub' }, t.name, h('span', { class: 'muted' }, nf.format(t.nAll)),
        h('a', { href: hashFor('photos', photosWith({ album: t.id, sort: 'old' })) }, 'View all'),
        h('span', { class: 'more', onclick: () => downloadDialog(photosWith({ album: t.id })) }, 'Download zip')));
      body.append(h('div', { class: 'cards' }, kids.length ? kids.map((a) => albumCard(a, a.path.slice(t.path.length + 1))) : albumCard(t, t.name)));
    }
    if (!body.querySelector('.card')) body.append(h('div', { class: 'empty' }, 'No albums match.'));
  };
  main.replaceChildren(h('div', { class: 'page' }, h('h1', null, 'Albums ', h('span', { class: 'muted' }, nf.format(META.albums.length))),
    h('input', { class: 'pagefilter', placeholder: 'Find an album…', oninput: (e) => draw(norm(e.target.value)) }), body));
  draw('');
}

const placeCard = ([city, region, country, n, cover]) => card({ img: `/thumb/${cover}`, name: city, sub: `${[region, country].filter(Boolean).join(', ')} · ${nf.format(n)}`,
  onclick: () => go('photos', photosWith({ place: city, ...(region ? { region } : {}), ...(country ? { country } : {}) })) });
function showPlaces(vp) {
  if (!META.places.length) {
    main.replaceChildren(h('div', { class: 'empty' }, 'Place names are not set up yet. They need the offline GeoNames data in the app folder (see the README).'));
    return;
  }
  const country = vp?.get('country') || null, region = vp?.get('region') || null;
  const rows = META.places.filter((x) => (!country || x[2] === country) && (!region || (x[1] || 'Other') === region));
  const level = !country ? 2 : !region ? 1 : 0;  // which column of a place row this page lists
  const groups = new Map();
  for (const x of rows) {
    const key = level === 0 ? x[0] : (x[level] || 'Other');
    if (!groups.has(key)) groups.set(key, { name: key, n: 0, cover: x[4], top: 0, kids: new Set(), row: x });
    const g = groups.get(key);
    g.n += x[3];
    g.kids.add(level === 2 ? (x[1] || 'Other') : x[0]);
    if (x[3] > g.top) { g.top = x[3]; g.cover = x[4]; }
  }
  const list = [...groups.values()].sort((a, b) => b.n - a.n);
  const mk = (g) => level === 2
    ? card({ img: `/thumb/${g.cover}`, name: g.name, sub: `${nf.format(g.n)} · ${plural(g.kids.size, 'region')}`, onclick: () => go('places', photosWith({ country: g.name })) })
    : level === 1
      ? card({ img: `/thumb/${g.cover}`, name: g.name, sub: `${nf.format(g.n)} · ${plural(g.kids.size, 'town')}`, onclick: () => go('places', photosWith({ country, region: g.name })) })
      : thumbCard(g.cover, g.name, nf.format(g.n), { place: g.name, ...(g.row[1] ? { region: g.row[1] } : {}), country });
  const here = level === 2 ? {} : level === 1 ? { country } : { country, ...(region !== 'Other' ? { region } : {}) };
  const total = rows.reduce((a, x) => a + x[3], 0);
  const cards = h('div', { class: 'cards' });
  const draw = (f) => { const l = list.filter((g) => !f || norm(g.name).includes(f)); fill(cards, l.length ? l.map(mk) : h('div', { class: 'empty' }, 'No places match.')); };
  main.replaceChildren(h('div', { class: 'page' },
    crumbs([['Places', '#/places'], ...(country ? [[country, placeHash({ country })]] : []), ...(region ? [[region, null]] : [])]),
    h('h1', null, region || country || 'Places', ' ', h('span', { class: 'muted' }, nf.format(total))),
    h('div', { class: 'muted' }, level === 2 ? 'Countries where your geotagged photos were taken. Open one to see its regions, then towns. Names come from each photo’s GPS position, worked out offline.'
      : level === 1 ? `Regions of ${country}.` : `Towns in ${region}, ${country}.`),
    h('div', { style: 'display:flex;gap:10px;align-items:center;flex-wrap:wrap' },
      h('input', { class: 'pagefilter', placeholder: level === 2 ? 'Find a country…' : level === 1 ? 'Find a region…' : 'Find a town…', oninput: (e) => draw(norm(e.target.value)) }),
      level < 2 ? h('a', { class: 'pillbtn', style: 'margin-top:6px', href: hashFor('photos', photosWith(here)) }, icon('photo'), `All ${nf.format(total)} photos here`) : null,
      level < 2 ? h('a', { class: 'pillbtn', style: 'margin-top:6px', href: hashFor('map', photosWith(here)) }, icon('map'), 'Map') : null),
    h('div', { style: 'height:14px' }), cards));
  draw('');
}

const conceptCard = (c) => thumbCard(c.cover, c.name[0].toUpperCase() + c.name.slice(1), nf.format(c.n), { concept: c.name });
async function showDetected() {
  main.replaceChildren(h('div', { class: 'empty' }, 'Looking at what the model sees…'));
  let d;
  try { d = await api('/api/concepts'); } catch { main.replaceChildren(h('div', { class: 'empty' }, 'Could not load detected content.')); return; }
  if (route.view !== 'detected') return;
  if (!d.enabled) { main.replaceChildren(h('div', { class: 'empty' }, 'Content search is not enabled (see the README).')); return; }
  const body = h('div');
  const draw = (f) => {
    body.replaceChildren();
    const groups = new Map();
    for (const c of d.concepts) { if (f && !norm(c.name).includes(f)) continue; if (!groups.has(c.group)) groups.set(c.group, []); groups.get(c.group).push(c); }
    for (const [g, list] of groups) body.append(h('h2', null, g, h('span', { class: 'muted' }, `${list.length} subjects`)),
      h('div', { class: 'cards' }, list.sort((a, b) => b.n - a.n).map(conceptCard)));
    if (!body.children.length) body.append(h('div', { class: 'empty' }, 'Nothing matches. Try the search box: type any description and pick “Photos that look like…”.'));
  };
  main.replaceChildren(h('div', { class: 'page' }, crumbs([['Explore', '#/explore'], ['Detected content', null]]), h('h1', null, 'Detected content ', h('span', { class: 'muted' }, nf.format(d.concepts.length))),
    h('div', { class: 'muted', style: 'max-width:820px' }, 'What the content-search model sees in your photos. It does not store labels: each photo is compared with a fixed list of several hundred everyday subjects and filed under the few it matches best. These are guesses and can be wrong; they are not written to digiKam. For anything not listed here, type a description in the search box.',
      d.indexing ? ' Indexing is still running, so counts will grow.' : ''),
    h('input', { class: 'pagefilter', placeholder: 'Find a subject…', oninput: (e) => draw(norm(e.target.value)) }), body));
  draw('');
}

const eventCard = (e) => thumbCard(e.cover, e.title, `${e.when} · ${nf.format(e.n)}${e.kind === 'trip' && e.days > 1 ? ` · ${e.days} days` : ''}`, { from: e.from, to: e.to, sort: 'old' });
async function showEvents() {
  main.replaceChildren(h('div', { class: 'empty' }, 'Working out events and trips…'));
  let d;
  try { d = await api('/api/events'); } catch { main.replaceChildren(h('div', { class: 'empty' }, 'Could not load events.')); return; }
  if (route.view !== 'events') return;
  let kind = '';
  const body = h('div');
  const draw = (f) => {
    body.replaceChildren();
    const years = new Map();
    for (const e of d.events) {
      if ((kind && e.kind !== kind) || (f && !norm(e.title + ' ' + (e.places || []).join(' ')).includes(f))) continue;
      const y = e.from.slice(0, 4);
      if (!years.has(y)) years.set(y, []);
      years.get(y).push(e);
    }
    for (const [y, list] of years) body.append(h('h2', null, y, h('span', { class: 'muted' }, `${list.length}`),
      h('a', { href: hashFor('photos', photosWith({ year: y })) }, 'All of ' + y)), h('div', { class: 'cards' }, list.map(eventCard)));
    if (!body.children.length) body.append(h('div', { class: 'empty' }, 'Nothing matches.'));
  };
  const filter = h('input', { class: 'pagefilter', placeholder: 'Find an event or trip…', oninput: (e) => draw(norm(e.target.value)) });
  const seg = h('span', { class: 'eseg', style: 'margin-top:6px' }, [['', 'All'], ['trip', 'Trips'], ['event', 'Events']].map(([k, l]) => h('button', { class: k === kind ? 'on' : '', onclick: (e) => {
    kind = k; seg.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b === e.target)); draw(norm(filter.value)); } }, l)));
  main.replaceChildren(h('div', { class: 'page' }, crumbs([['Explore', '#/explore'], ['Events & trips', null]]),
    h('h1', null, 'Events & trips ', h('span', { class: 'muted' }, nf.format(d.events.length))),
    h('div', { class: 'muted', style: 'max-width:820px' }, 'Trips are runs of days photographed far from where most of your photos are taken. Events are other days with 20 or more photos, named after the title most of them share, or the town. Worked out from dates, GPS and titles; nothing is stored in digiKam.'),
    h('div', { style: 'display:flex;gap:10px;align-items:center;flex-wrap:wrap' }, filter, seg), body));
  draw('');
}

async function showBursts(vp) {
  const qs = new URLSearchParams(vp || '');
  main.replaceChildren(h('div', { class: 'empty' }, 'Finding bursts…'));
  const list = h('div');
  let offset = 0, total = 0, src = { id: [] };
  const more = h('button', { class: 'pillbtn', style: 'margin:20px auto;display:flex', onclick: () => load() }, 'Show more bursts');
  const pct = (v) => (v == null ? '' : `${Math.round(v * 100)}`);
  const group = (g) => {
    const best = g.items.find((x) => x.best) || g.items[0];
    const others = (keep) => g.items.filter((x) => x.id !== keep.id).map((x) => x.id);
    const start = src.id.length;
    g.items.forEach((x) => src.id.push(x.id));
    const row = h('div', { class: 'duprow' }, g.items.map((x, k) => h('div', { class: 'dupitem burstitem' + (x.best ? ' best' : '') + '' },
      h('div', { class: 'tile', style: `width:${Math.round(150 * Math.min(2, x.w / (x.h || 1)))}px;height:150px`, onclick: () => openLightbox(src, start + k, true) },
        h('img', { src: `/thumb/${x.id}`, loading: 'lazy', alt: '' }), x.best ? h('span', { class: 'bestbadge' }, icon('star'), 'Best') : null),
      h('div', { class: 'sb' }, [x.sharpn != null ? `sharpness ${pct(x.sharpn)}` : null, x.faceq != null ? `faces ${pct(x.faceq)}` : null].filter(Boolean).join(' · ') || ' '),)));
    return h('div', { class: 'dupgroup' }, h('div', { style: 'display:flex;gap:14px;align-items:baseline;flex-wrap:wrap' },
      h('span', null, dfDay.format(date(g.items[0].ts)), ' ', h('span', { class: 'muted' }, `${dfTime.format(date(g.items[0].ts))} · ${g.items.length} frames`)),
      h('a', { class: 'lnk', href: hashFor('photos', photosWith({ burst: g.burst, sort: 'old' })) }, 'Open in grid')), row);
  };
  const load = async () => {
    qs.set('offset', offset);
    let d;
    try { d = await api('/api/bursts?' + qs.toString()); } catch { list.append(h('div', { class: 'empty' }, 'Could not load bursts.')); return; }
    if (route.view !== 'bursts') return;
    total = d.bursts;
    if (!offset) head.textContent = d.bursts ? `${nf.format(d.bursts)} bursts covering ${nf.format(d.photos)} photos. The best frame is picked by sharpness and how good the faces look; check it before rejecting the rest.` : 'No bursts found here.';
    list.append(...d.groups.map(group));
    offset += d.groups.length;
    more.hidden = offset >= total;
    syncLightbox();
  };
  const refresh = () => { offset = 0; src = { id: [] }; list.replaceChildren(); setTimeout(load, 1800); };
  const head = h('div', { class: 'muted', style: 'max-width:820px' });
  const scoped = [...qs.keys()].length > 0;  // bursts within a search, rather than the whole library
  main.replaceChildren(h('div', { class: 'page' }, crumbs([['Explore', '#/explore'], ['Bursts & best shots', null]]),
    h('h1', null, 'Bursts & best shots'), head,
    scoped ? h('div', { class: 'enote', style: 'max-width:760px' }, 'Showing bursts within your current search only. ', h('a', { class: 'lnk', href: '#/bursts' }, 'Show all bursts')) : null,
    list, more));
  more.hidden = true;
  await load();
}

// ---- users: sign in / out, own password, first-admin setup, admin user management
async function loadUser() {
  try { const me = await api('/api/auth/me'); USER = me.user; USER_SETTINGS = me.user ? me.settings : null; IS_ADMIN = me.isAdmin; SIGNED_IN = me.signedIn; USERS_EXIST = me.usersExist; REQUIRE_LOGIN = !!me.requireLogin; } catch { USER = null; USER_SETTINGS = null; }
  renderUserMenu();
}
function renderUserMenu() {
  const el = $('#usermenu'); if (!el) return;
  el.replaceChildren(USER
    ? h('button', { class: 'iconbtn tool', title: `${USER.name} (${USER.role}) · account`, onclick: accountDialog }, avatarOf(USER))
    : h('button', { class: 'iconbtn tool', title: USERS_EXIST ? 'Sign in' : 'Create the admin account', onclick: () => (USERS_EXIST ? loginDialog() : setupDialog()) }, icon('person')));
}
async function afterLogin(me) {
  USER = me.user; USER_SETTINGS = me.settings || {}; renderUserMenu();
  if (!BOOTED) { applyBadgePref(); applyTheme(); await boot(); return; }  // sign-in was required: load the library now
  await pollStatus(); applyBadgePref(); applyTheme(); viewKey = null; onRoute();
}
/** required: the viewer shows nothing else until someone signs in (no Cancel, no closing). */
function loginDialog(required) {
  // the account picker: a tile per account; one click for a passwordless viewer, a password for the others
  const name = h('input', { class: 'einput', placeholder: 'User name', autocomplete: 'username', style: 'margin:0;width:100%' });
  const pw = h('input', { class: 'einput', type: 'password', placeholder: 'Password', autocomplete: 'current-password', style: 'margin:0;width:100%' });
  const form = h('div', { style: 'display:grid;gap:8px;margin-top:10px' }, name, pw);
  const tiles = h('div', { class: 'accounts' });
  const go = async () => { try { const me = await post('/api/auth/login', { name: name.value.trim(), password: pw.value }); back.remove(); await afterLogin(me); toast(`Signed in as ${me.user.name}.`); } catch (e) { toast(e.message); } };
  [name, pw].forEach((i) => { i.onkeydown = (e) => { e.stopPropagation(); if (e.key === 'Enter') go(); }; });
  const back = modal('Sign in', tiles, form,
    h('p', { class: 'muted', style: 'font-size:12.5px' }, required ? 'Sign in to use this viewer.' : 'Without signing in you can browse everything; signing in keeps your display settings, favorites and albums on the server, and editors can change the library.'),
    h('div', { class: 'modal-btns' }, required ? null : h('button', { class: 'pillbtn', onclick: () => back.remove() }, 'Cancel'), h('button', { class: 'pillbtn on', onclick: go }, 'Sign in')));
  if (required) { back.onclick = null; back.classList.add('required'); }
  api('/api/auth/accounts').then((d) => {
    if (!d.accounts.length) { name.focus(); return; }
    form.hidden = true;
    fill(tiles, d.accounts.map((a) => h('button', { class: 'account', title: a.passwordless ? `Sign in as ${a.name}` : `${a.name} (password)`, onclick: async () => {
      if (a.passwordless) { try { const me = await post('/api/auth/login', { name: a.name }); back.remove(); await afterLogin(me); toast(`Signed in as ${a.name}.`); } catch (e) { toast(e.message); } return; }
      name.value = a.name; form.hidden = false; tiles.querySelectorAll('.account').forEach((t) => t.classList.toggle('on', t === tiles.querySelector(`[data-n="${CSS.escape(a.name)}"]`))); pw.focus();
    }, 'data-n': a.name }, avatarOf(a, true), h('span', { class: 'nm' }, a.name), a.passwordless ? null : h('span', { class: 'muted', style: 'font-size:11px' }, 'password'))),
      h('button', { class: 'account', title: 'Type a user name', onclick: () => { form.hidden = false; name.value = ''; name.focus(); } }, h('span', { class: 'avatar big', style: 'background:var(--bg3);color:var(--fg2)' }, '…'), h('span', { class: 'nm' }, 'Other')));
  }).catch(() => name.focus());
}
function setupDialog() {
  const name = h('input', { class: 'einput', placeholder: 'Admin user name', autocomplete: 'username', style: 'margin:0;width:100%' });
  const pw = h('input', { class: 'einput', type: 'password', placeholder: 'Password (8 characters or more)', autocomplete: 'new-password', style: 'margin:0;width:100%' });
  const go = async () => { try { const me = await post('/api/auth/setup', { name: name.value.trim(), password: pw.value }); back.remove(); await afterLogin({ user: me.user, settings: {} }); toast('Admin account created; you are signed in.'); } catch (e) { toast(e.message); } };
  [name, pw].forEach((i) => { i.onkeydown = (e) => { e.stopPropagation(); if (e.key === 'Enter') go(); }; });
  const back = modal('Create the admin account', h('p', { class: 'muted' }, 'Right now the viewer is open to anyone who can reach it. Once an admin exists, visitors browse read-only, signed-in users keep their settings on the server, and only editors and admins can change the library or the settings.'),
    h('div', { style: 'display:grid;gap:8px' }, name, pw),
    h('div', { class: 'modal-btns' }, h('button', { class: 'pillbtn', onclick: () => back.remove() }, 'Not now'), h('button', { class: 'pillbtn on', onclick: go }, 'Create')));
  name.focus();
}
function accountDialog() {
  const cur = h('input', { class: 'einput', type: 'password', placeholder: 'Current password', autocomplete: 'current-password', style: 'margin:0;width:100%' });
  const pw = h('input', { class: 'einput', type: 'password', placeholder: 'New password (8 characters or more)', autocomplete: 'new-password', style: 'margin:0;width:100%' });
  [cur, pw].forEach((i) => { i.onkeydown = (e) => e.stopPropagation(); });
  const back = modal(`${USER.name} · ${USER.role}`,
    h('p', { class: 'muted' }, USER.role === 'admin' ? 'You can change the library, the settings and the users.' : USER.role === 'editor' ? 'You can change the library (edits, tags, faces, places).' : 'You can browse, and keep favorites, albums and display settings.'),
    h('h4', null, 'Who you are in People'),
    h('div', { style: 'display:flex;gap:8px;align-items:center;flex-wrap:wrap' }, avatarOf(USER, true), h('span', null, USER.person && tagById.get(USER.person) ? tagById.get(USER.person).name : 'not linked'),
      h('button', { class: 'pillbtn', onclick: () => personPicker(async (t) => { try { USER = await post('/api/auth/person', { person: t.id }); renderUserMenu(); back.remove(); accountDialog(); } catch (e) { toast(e.message); } }) }, USER.person ? 'Change' : 'Link to a person'),
      USER.person ? h('a', { class: 'lnk', href: hashFor('photos', photosWith({ tag: USER.person })), onclick: () => back.remove() }, 'Photos of me') : null),
    h('h4', null, 'Change password'), h('div', { style: 'display:grid;gap:8px' }, cur, pw),
    h('div', { style: 'margin-top:8px' }, h('button', { class: 'pillbtn', onclick: async () => { try { await post('/api/auth/password', { current: cur.value, password: pw.value }); toast('Password changed.'); cur.value = pw.value = ''; } catch (e) { toast(e.message); } } }, 'Change password')),
    h('div', { class: 'modal-btns' }, h('button', { class: 'pillbtn', onclick: async () => { back.remove(); await post('/api/auth/logout', {}); if (REQUIRE_LOGIN) { location.reload(); return; } USER = null; USER_SETTINGS = null; renderUserMenu(); await pollStatus(); applyBadgePref(); applyTheme(); viewKey = null; onRoute(); toast('Signed out.'); } }, 'Sign out'),
      h('button', { class: 'pillbtn on', onclick: () => back.remove() }, 'Done')));
}
function usersSection() {
  const body = h('div');
  const wrap = h('div', null, h('h2', null, 'Users'),
    h('div', { class: 'muted', style: 'max-width:820px' }, 'Visitors who are not signed in browse read-only with display settings in their browser. Viewers keep settings, favorites and albums on the server; editors can also change the library; admins can also change settings, run maintenance and manage users.'),
    h('div', { class: 'srow' }, h('div', null, h('b', null, 'Require sign-in'), h('div', { class: 'muted', style: 'font-size:13px' }, 'Visitors see only the sign-in screen; nothing from the library (not even thumbnails) is served without an account. MCP clients then need the admin token as a bearer header (see the README).')),
      h('label', { style: 'display:flex;gap:8px;align-items:center;cursor:pointer;white-space:nowrap' }, h('input', { type: 'checkbox', id: 'reqlogin', checked: REQUIRE_LOGIN, disabled: !USERS_EXIST, onchange: async (e) => {
        try { await post('/api/settings', { require_login: e.target.checked }); REQUIRE_LOGIN = e.target.checked; toast(REQUIRE_LOGIN ? 'Visitors now have to sign in.' : 'Visitors can browse again.'); } catch (err) { e.target.checked = !e.target.checked; toast(err.message); } } }), 'Require sign-in')), body);
  const draw = async () => {
    let d; try { d = await api('/api/users'); } catch (e) { fill(body, h('div', { class: 'muted' }, e.message)); return; }
    const name = h('input', { class: 'einput', placeholder: 'User name', style: 'margin:0;width:160px' }), pw = h('input', { class: 'einput', type: 'password', placeholder: 'Password', style: 'margin:0;width:160px' });
    const email = h('input', { class: 'einput', type: 'email', placeholder: 'Email (optional)', autocomplete: 'off', style: 'margin:0;width:200px' });
    const role = h('select', null, d.roles.map((r) => h('option', { value: r }, r)));
    const nopw = h('label', { style: 'display:flex;gap:6px;align-items:center;font-size:13px' }, h('input', { type: 'checkbox', onchange: (e) => { pw.disabled = e.target.checked; if (e.target.checked) { pw.value = ''; role.value = 'viewer'; } } }), 'no password (one-click sign-in, viewer only)');
    [name, pw, email].forEach((i) => { i.onkeydown = (e) => e.stopPropagation(); });
    const act = async (fn, after = draw) => { try { await fn(); } catch (err) { toast(err.message); } after(); };
    const setPerson = (u, t) => act(async () => { await post(`/api/users/${u.id}`, { person: t ? t.id : null }); if (USER && USER.id === u.id) { USER.person = t ? t.id : null; renderUserMenu(); } });
    fill(body, h('table', { class: 'utable' },
      h('thead', null, h('tr', null, ['Account', 'Email', 'Person in People', 'Role', 'Password', ''].map((c) => h('th', null, c)))),
      h('tbody', null, d.users.map((u) => h('tr', { 'data-user': u.name },
        h('td', null, h('span', { class: 'ucell' }, avatarOf(u), h('span', null, u.name, u.id === USER?.id ? h('span', { class: 'muted' }, ' (you)') : null))),
        h('td', null, u.email || h('span', { class: 'muted' }, 'none'), ' ',
          h('a', { class: 'lnk', onclick: () => { const v = prompt(`Email address for ${u.name} (empty to clear)`, u.email || ''); if (v !== null) act(async () => { await post(`/api/users/${u.id}`, { email: v.trim() }); }); } }, u.email ? 'change' : 'set')),
        h('td', null, u.person && tagById.get(u.person) ? tagById.get(u.person).name : h('span', { class: 'muted' }, 'not linked'), ' ',
          h('a', { class: 'lnk', onclick: () => personPicker((t) => setPerson(u, t)) }, u.person ? 'change' : 'link'), u.person ? [' · ', h('a', { class: 'lnk', onclick: () => setPerson(u, null) }, 'unlink')] : null),
        h('td', null, h('select', { onchange: (e) => act(async () => { await post(`/api/users/${u.id}`, { role: e.target.value }); toast(`${u.name} is now ${e.target.value}.`); }) }, d.roles.map((r) => h('option', { value: r, selected: r === u.role }, r)))),
        h('td', null, u.passwordless ? h('span', { class: 'muted' }, 'none (one-click)') : 'set', ' ',
          h('a', { class: 'lnk', onclick: () => { const p = prompt(`New password for ${u.name} (8 characters or more)`); if (p) act(async () => { await post(`/api/users/${u.id}`, { password: p }); toast('Password set.'); }, () => {}); } }, 'set'),
          u.role === 'viewer' && !u.passwordless ? [' · ', h('a', { class: 'lnk', title: 'One-click sign-in from the account picker', onclick: () => { if (confirm(`Remove ${u.name}’s password? Anyone who can reach the viewer can then sign in as this viewer with one click.`)) act(() => post(`/api/users/${u.id}`, { password: '' })); } }, 'remove')] : null),
        h('td', { style: 'text-align:right' }, u.id !== USER?.id ? h('button', { class: 'pillbtn', onclick: () => { if (confirm(`Delete the user ${u.name}?`)) act(() => post(`/api/users/${u.id}`, { delete: true })); } }, 'Delete') : null))))),
      h('div', { style: 'display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:10px' }, name, email, pw, role, nopw, h('button', { class: 'pillbtn on', onclick: async () => {
        try { await post('/api/users', { name: name.value.trim(), email: email.value.trim(), password: nopw.querySelector('input').checked ? '' : pw.value, role: nopw.querySelector('input').checked ? 'viewer' : role.value }); toast(`Added ${name.value.trim()}.`); } catch (err) { toast(err.message); } draw();
      } }, icon('add'), 'Add user')));
  };
  draw();
  return wrap;
}
function showAnalysis() { go('maintenance', null, true); }  // the old #/analysis page now lives in Maintenance; keep bookmarks working

// ---------------------------------------------------------------- settings & maintenance
function modelsSection(view) {
  const body = h('div');
  const checkBtn = h('button', { class: 'pillbtn', onclick: async () => { checkBtn.disabled = true; checkBtn.textContent = 'Checking…'; try { await post('/api/models/check', {}); } catch (e) { toast(e.message); } draw(); } }, icon('spark'), 'Check for updates');
  const wrap = h('div', null,
    h('h2', null, 'Models and data'),
    h('div', { class: 'muted', style: 'max-width:820px' }, 'Everything below was downloaded once and is never updated on its own. “Check for updates” asks each source whether the exact files the viewer uses have changed since they were downloaded (a commit on the model hub, a newer file, a newer package). It cannot tell whether a different, better model exists; the page link on each row is where to look for that, and switching models is a code change.'),
    h('div', { style: 'margin:14px 0' }, checkBtn), body);
  const fmtDate = (t) => (t ? dfDay.format(new Date(t * 1000)) : '');
  const draw = async () => {
    let d;
    try { d = await api('/api/models'); } catch { return; }
    if (route.view !== view) return;
    const p = d.progress || {};
    if (p.finished && !p.running && p.error) toast(`Download of ${p.finished} failed: ${p.error}`, null, null, 9000);
    fill(body, d.models.map((m) => {
      const c = m.check;
      const state = p.running === m.key ? 'downloading…'
        : !m.installed ? 'not installed'
        : !c ? `installed ${fmtDate(m.at)} · ${m.revision}`
        : c.status === 'current' ? `up to date · ${m.revision}`
        : c.status === 'update' ? `update available: ${c.remote}${c.remote_at ? ' (' + c.remote_at.slice(0, 10) + ')' : ''}, installed ${m.revision}`
        : c.status === 'newer' ? `newer data available (${c.remote}); installed ${m.revision}`
        : c.status === 'error' ? `could not check: ${c.error}` : `installed ${m.revision}`;
      return h('div', { class: 'ajob' },
        h('div', { class: 'ahead' }, h('b', null, m.label), h('span', { class: 'muted' }, state), h('span', { class: 'sp' }),
          h('a', { class: 'lnk', href: m.page, target: '_blank', rel: 'noopener', style: 'font-size:13px' }, 'model page'),
          h('button', { class: 'pillbtn' + (c && (c.status === 'update' || c.status === 'newer' || c.status === 'missing') ? ' on' : ''), disabled: !!p.running, style: 'margin-left:10px',
            onclick: async () => {
              if (!confirm(`Download ${m.label} (${m.size})${m.installed ? ' again, replacing the installed files' : ''}? The viewer keeps working meanwhile.`)) return;
              try { await post('/api/models/download', { key: m.key }); toast(`Downloading ${m.label}…`); } catch (e) { toast(e.message); }
              draw();
            } }, m.installed ? (c && (c.status === 'update' || c.status === 'newer') ? 'Update' : 'Download again') : 'Download')),
        h('div', { class: 'muted', style: 'font-size:13px;margin-top:6px' }, m.what, m.kind === 'pip' ? ' Updating the package takes effect after a restart of the viewer.' : ''));
    }));
    if (p.running) setTimeout(() => { if (route.view === view) draw(); }, 3000);
    checkBtn.disabled = false; fill(checkBtn, icon('spark'), 'Check for updates');
  };
  draw();
  return wrap;
}
function analysisSection(view, part = 'jobs') {
  // part 'jobs': the job list with progress (Maintenance); 'prefs': the search model and the core budget (Settings)
  const body = h('div');
  const wrap = h('div', null,
    ...(part === 'jobs' ? [h('h2', null, 'AI analysis'),
    h('div', { class: 'muted', style: 'max-width:820px' }, 'Everything here runs locally, wherever the viewer is running, and is stored in its own data folder. New and changed photos are picked up automatically, about 20 seconds after digiKam saves them; “Check for new photos now” does the same on demand.'),
    h('div', { style: 'margin:14px 0' }, h('button', { class: 'pillbtn on', onclick: async () => { try { await post('/api/analysis/run', { job: 'all' }); toast('Checking for new and changed photos…'); } catch (e) { toast(e.message); } draw(); } }, icon('spark'), 'Check for new photos now')),] : [h('h2', null, 'Search and background work')]),
    body);
  const draw = async () => {
    let d;
    try { d = await api('/api/analysis'); } catch { return; }
    if (route.view !== view) return;
    const q = d.queue || {};
    const sel = h('select', { onchange: async (e) => { try { await post('/api/settings', { bg_threads: +e.target.value }); toast('Applies when the next job starts.'); } catch (err) { toast(err.message); } } },
      Array.from({ length: Math.max(1, (q.cores || 4) - 1) }, (_, i) => h('option', { value: i + 1, selected: i + 1 === q.threads }, String(i + 1))));
    fill(body, h('div', { class: 'ajob', style: 'border-top:0;padding-top:0' },
      h('div', { class: 'ahead' }, h('b', null, 'Background work'), h('span', { class: 'muted' }, q.running ? `running: ${(d.jobs.find((j) => (j.key === 'quality' && q.running === 'pixels') || j.key === q.running) || {}).label || q.running}` : 'idle')),
      h('div', { class: 'muted', style: 'font-size:13px;margin-top:6px' }, ...(part === 'prefs'
        ? ['Jobs run one at a time, in a fixed order, so the viewer and other apps stay responsive. Each job may use up to ', sel, ` of ${q.cores || '?'} cores.`]
        : [`Jobs run one at a time, in the order below. Each may use up to ${q.threads} of ${q.cores || '?'} cores (change that in Settings).`, q.queued?.length ? ` Waiting: ${q.queued.length}.` : '']))),
      part === 'jobs' ? d.jobs.map((j) => h('div', { class: 'ajob' },
      h('div', { class: 'ahead' }, h('b', null, j.label), h('span', { class: 'muted' }, !j.enabled ? 'not installed' : j.running ? 'running…' : j.queued ? 'queued' : j.done >= j.total ? 'up to date' : 'waiting'),
        h('span', { class: 'sp' }), h('span', null, `${nf.format(Math.min(j.done, j.total))} / ${nf.format(j.total)}`)),
      h('div', { class: 'bar' }, h('i', { style: `width:${j.total ? Math.min(100, 100 * j.done / j.total).toFixed(1) : 0}%` })),
      j.running && j.since ? (() => { const now = Date.now() / 1000, idle = j.last ? now - j.last : now - j.since, stuck = idle > 300;
        return h('div', { class: stuck ? 'warn' : 'muted', style: 'font-size:12px;margin-top:4px' }, `running for ${Math.round((now - j.since) / 60)} min · last progress ${idle < 90 ? Math.round(idle) + ' s' : Math.round(idle / 60) + ' min'} ago`,
          j.current && j.current.length ? ` · working on ${j.current.map((p) => p.split('/').pop()).join(', ')}` : '',
          stuck ? ' · no progress for over 5 minutes: probably stuck on that file; see the server log (journalctl -u digikam-viewer, docker logs, or data/server.log) and consider restarting the viewer from Maintenance' : ''); })() : null,
      h('div', { class: 'muted', style: 'font-size:13px;margin-top:6px' }, j.detail, ' ',
        j.rerun && j.enabled ? h('a', { class: 'lnk', onclick: async () => {
          if (!confirm(`Run “${j.label}” again from scratch for all ${nf.format(j.total)} photos? The current results for it are discarded first. This can take from several minutes to a few hours.`)) return;
          try { await post('/api/analysis/run', { job: j.key, reset: true }); toast(`Re-running “${j.label}”.`); } catch (e) { toast(e.message); }
          draw();
        } }, 'Run again from scratch') : null))) : null);
    const other = (d.models || []).find((m) => m.installed && !m.chosen);
    if (other && part === 'prefs') body.append(h('div', { class: 'ajob' },
      h('div', { class: 'ahead' }, h('b', null, 'Search model'), h('span', { class: 'muted' }, `using ${d.models.find((m) => m.active)?.label || 'none'}`)),
      h('div', { class: 'muted', style: 'font-size:13px;margin-top:6px' },
        other.key === 'siglip2'
          ? 'SigLIP 2 base is also installed. Measured on 2,160 of your photos against your own tags it was slightly better on average than CLIP (better for animals, zoo, costumes; worse for weddings, bowling, food), and it indexes about 4 times slower. Switching re-indexes the whole library in the background; search stays on the current model until that finishes, and you can switch back at any time. '
          : `${other.label} is also installed. Switching back is immediate; its index is kept. `,
        h('a', { class: 'lnk', onclick: async () => {
          if (!confirm(`Switch content search to ${other.label}?`)) return;
          try { await post('/api/settings', { search_model: other.key }); toast(`Switching to ${other.label}.`); } catch (e) { toast(e.message); }
          draw();
        } }, `Switch to ${other.label}`))));
    if (part === 'jobs' && d.jobs.some((j) => j.running)) setTimeout(() => { if (route.view === view) draw(); }, 4000);
  };
  draw();
  return wrap;
}

const SRC_LABEL = { db: 'Database', sidecar: 'Sidecar', file: 'Image file' };
const FIELD_LABEL = { rating: 'Rating', title: 'Title', caption: 'Caption', tags: 'Tags' };
async function showConsistency() {
  let field = '', offset = 0, selected = new Set(), d;
  const head = h('div'), list = h('div'), more = h('button', { class: 'pillbtn', style: 'margin:16px 0', onclick: () => load(true) }, 'Show more');
  const fmtv = (f, v) => v == null ? h('i', { class: 'muted' }, 'absent') : f === 'tags' ? (v.length ? h('span', null, v.map((t) => h('span', { class: 'ichip', style: 'height:24px;font-size:12px;margin:1px' }, t.split('/').pop()))) : h('i', { class: 'muted' }, 'none'))
    : f === 'rating' ? (v ? '★'.repeat(v) : h('i', { class: 'muted' }, 'none')) : (v || h('i', { class: 'muted' }, 'empty'));
  const item = (r) => {
    const cb = h('input', { type: 'checkbox', checked: selected.has(r.id), onchange: (e) => { e.target.checked ? selected.add(r.id) : selected.delete(r.id); bar(); } });
    return h('div', { class: 'crec' + (selected.has(r.id) ? ' sel' : '') },
      h('div', { class: 'chead' }, EDITING ? cb : null, h('img', { src: `/thumb/${r.id}`, loading: 'lazy', alt: '', onclick: () => openLightbox({ id: [r.id] }, 0, true) }),
        h('div', null, h('b', null, r.name), h('div', { class: 'muted', style: 'font-size:12px' }, r.path.replace(/^.*\/photos\//, ''), !r.has_sidecar ? ' · no sidecar' : '', !r.file_xmp ? (r.file_editable ? ' · no metadata in the file' : ' · file type cannot hold metadata') : ''))),
      h('table', { class: 'ctable' }, h('tr', null, h('th'), ...['db', 'sidecar', 'file'].map((s) => h('th', null, SRC_LABEL[s]))),
        ...r.mismatch.map((f) => h('tr', null, h('td', null, FIELD_LABEL[f]), ...['db', 'sidecar', 'file'].map((s) => h('td', null, fmtv(f, r.fields[f][s])))))));
  };
  const syncBar = h('div', { id: 'selbar', hidden: true });
  const bar = () => {
    syncBar.hidden = !selected.size;
    if (!selected.size) return;
    const src = h('select', null, ['db', 'sidecar', 'file'].map((s) => h('option', { value: s }, SRC_LABEL[s])));
    const tg = ['db', 'sidecar', 'file'].map((s) => h('label', { style: 'display:flex;gap:4px;align-items:center' }, h('input', { type: 'checkbox', value: s, checked: s !== 'db' }), SRC_LABEL[s]));
    const fl = Object.keys(FIELD_LABEL).map((f) => h('label', { style: 'display:flex;gap:4px;align-items:center' }, h('input', { type: 'checkbox', value: f, checked: true }), FIELD_LABEL[f]));
    fill(syncBar, h('button', { class: 'iconbtn', title: 'Clear selection', onclick: () => { selected.clear(); bar(); load(); } }, icon('close')),
      h('span', { class: 'n' }, `${nf.format(selected.size)} selected`), h('span', { class: 'sp' }),
      h('span', null, 'Copy from ', src, ' to '), h('span', { style: 'display:flex;gap:10px' }, tg), h('span', { class: 'muted' }, '|'), h('span', { style: 'display:flex;gap:8px' }, fl),
      h('button', { class: 'pillbtn on', onclick: async () => {
        const targets = tg.map((l) => l.firstChild).filter((c) => c.checked && c.value !== src.value).map((c) => c.value);
        const fields = fl.map((l) => l.firstChild).filter((c) => c.checked).map((c) => c.value);
        if (!targets.length) { toast('Pick at least one target other than the source.'); return; }
        const n = selected.size;
        if (!confirm(`Copy ${fields.map((f) => FIELD_LABEL[f].toLowerCase()).join(', ')} from the ${SRC_LABEL[src.value].toLowerCase()} to the ${targets.map((t) => SRC_LABEL[t].toLowerCase()).join(' and ')} for ${nf.format(n)} ${n === 1 ? 'photo' : 'photos'}?` +
          (targets.includes('db') ? '\n\ndigiKam must be closed; its database is backed up first.' : '') + (targets.includes('file') ? '\n\nImage files are rewritten in place (metadata only; pixels untouched); the original of each is kept in the viewer’s file-backups folder.' : '') + '\n\nSidecars are backed up before they change.')) return;
        try { const r = await post('/api/consistency/sync', { ids: [...selected], source: src.value, targets, fields }); toast(`Synced ${nf.format(r.synced)}${r.skipped.length ? `, skipped ${r.skipped.length}: ${r.skipped[0].reason}` : ''}.`, null, null, 9000); }
        catch (e) { toast(e.message, null, null, 9000); return; }
        selected.clear(); bar(); load();
      } }, icon('spark'), 'Sync'));
  };
  const load = async (append) => {
    if (!append) offset = 0;
    try { d = await api(`/api/consistency?field=${field}&offset=${offset}&limit=60`); } catch (e) { list.replaceChildren(h('div', { class: 'empty' }, e.message)); return; }
    if (route.view !== 'consistency') return;
    const s = d.summary, p = d.progress;
    fill(head,
      p.running ? h('div', { class: 'enote' }, `Scanning… ${nf.format(p.done)} / ${nf.format(p.total)}`) : null,
      s.scanned ? h('div', { class: 'stats' }, h('div', null, h('b', null, nf.format(s.scanned)), 'photos checked'), h('div', null, h('b', null, nf.format(s.mismatched)), 'disagree'),
        h('div', null, h('b', null, nf.format(s.no_sidecar)), 'without a sidecar'), ...Object.entries(s.by_field).filter(([, n]) => n).map(([f, n]) => h('div', null, h('b', null, nf.format(n)), FIELD_LABEL[f].toLowerCase()))) : h('p', { class: 'muted' }, 'Nothing scanned yet.'),
      p.error ? h('p', { class: 'warn' }, 'Last error: ' + p.error) : null);
    if (!append) list.replaceChildren();
    if (!d.items.length && !offset) list.append(h('div', { class: 'empty' }, s.scanned ? 'Everything that was scanned agrees.' : ''));
    list.append(...d.items.map(item));
    offset += d.items.length;
    more.hidden = offset >= d.total;
    if (p.running) setTimeout(() => { if (route.view === 'consistency' && !offset) load(); }, 4000);
  };
  const scan = async (subset, rescanAll) => {
    const q = subset ? filterParams() : new URLSearchParams();
    q.set('rescan_all', rescanAll ? '1' : '0');
    try { const r = await fetch('/api/consistency/scan', { method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body: q.toString() }).then((x) => x.json()); toast(`Checking ${nf.format(r.queued)} photos in the background.`); } catch (e) { toast(e.message); }
    setTimeout(load, 1500);
  };
  const sel = h('select', { onchange: (e) => { field = e.target.value; load(); } }, h('option', { value: '' }, 'Any field'), ...Object.entries(FIELD_LABEL).map(([f, l]) => h('option', { value: f }, l)));
  main.replaceChildren(h('div', { class: 'page' }, crumbs([['Maintenance', '#/maintenance'], ['Metadata consistency', null]]),
    h('h1', null, 'Metadata consistency'),
    h('div', { class: 'muted', style: 'max-width:820px' }, 'For each photo, the rating, title, caption and tags are read from three places: digiKam’s database, the XMP sidecar, and the metadata embedded in the image file. Photos where they disagree are listed below. Select photos, choose which copy is right, and sync the others to it. An absent value (no sidecar, nothing in the file) counts as a disagreement only when another copy has a value.'),
    h('div', { style: 'display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:14px 0' },
      h('button', { class: 'pillbtn on', onclick: () => scan(false, false) }, icon('spark'), 'Check new and changed photos'),
      h('button', { class: 'pillbtn', onclick: () => { if (confirm('Re-check every photo in the library? This reads every sidecar and image file and takes a while.')) scan(false, true); } }, 'Re-check whole library'),
      [...filterParams().keys()].length ? h('button', { class: 'pillbtn', onclick: () => scan(true, true) }, 'Check the current search only') : null,
      h('span', { class: 'sp' }), h('span', null, 'Show: ', sel),
      h('button', { class: 'pillbtn', onclick: () => { d.items.forEach((r) => selected.add(r.id)); bar(); load(); } }, 'Select all shown')),
    head, list, more), syncBar);
  load();
}

async function placeTagsDialog(ids) {
  let p;
  try { p = await api('/api/placetags' + (ids ? '?ids=' + ids.join(',') : '')); } catch (e) { toast(e.message); return; }
  const body = h('div');
  const draw = () => fill(body,
    h('p', null, `${nf.format(p.to_tag)} of ${nf.format(p.photos)} geotagged photos would get a place tag they do not have yet.`),
    p.missing_tags.length ? h('p', null, `${nf.format(p.missing_tags.length)} new tags would be created under “${p.root}” (${nf.format(p.existing_tags)} already exist), for example: `, h('i', null, p.missing_tags.slice(0, 5).join(', '), p.missing_tags.length > 5 ? ', …' : '')) : h('p', null, 'All the needed tags already exist.'),
    p.missing_tags.length && p.digikamRunning ? h('p', { class: 'warn' }, 'digiKam is running. Quit it first; the new tags go into its database.') : null,
    p.progress.running ? h('p', { class: 'enote' }, `Running: ${nf.format(p.progress.done)} / ${nf.format(p.progress.total)} photos tagged, ${p.progress.created} tags created.`) : null,
    p.progress.error ? h('p', { class: 'warn' }, p.progress.error) : null);
  draw();
  const back = modal(ids ? `Place tags for ${nf.format(ids.length)} photos` : 'Place tags for the whole library', body,
    h('p', { class: 'muted', style: 'font-size:12.5px' }, 'Town names come from the offline place lookup and can be a neighbouring town. Tags are assigned through the normal edit path, so they reach digiKam’s database with “Apply edits to digiKam database”.'),
    h('div', { class: 'modal-btns' }, h('button', { class: 'pillbtn', onclick: () => back.remove() }, 'Close'),
      h('button', { class: 'pillbtn on', disabled: !p.to_tag || p.progress.running || !!(p.missing_tags.length && p.digikamRunning), onclick: async () => {
        try { const r = await post('/api/placetags', { ids: ids || [] }); toast(`Tagging ${nf.format(r.to_tag)} photos${r.creating ? `, creating ${r.creating} tags` : ''} in the background.`); } catch (e) { toast(e.message, null, null, 9000); return; }
        const poll = async () => { try { p = await api('/api/placetags' + (ids ? '?ids=' + ids.join(',') : '')); } catch { return; } draw(); if (p.progress.running && back.isConnected) setTimeout(poll, 3000); else if (back.isConnected) { indexMeta(await api('/api/meta')); } };
        setTimeout(poll, 1500);
      } }, icon('place'), 'Create and assign')));
}

async function facesBatch(ops, msg) {
  let r;
  try { r = await post('/api/faces/batch', { ops }); } catch (e) { toast(e.message, null, null, 9000); return null; }
  toast(`${msg}: ${nf.format(r.done)} done${r.failed.length ? `, ${r.failed.length} failed (${r.failed[0].error})` : ''}.`, null, null, 7000);
  await awaitReindex(() => true, 20, 500);
  details.clear();
  return r;
}
async function showFaces(vp) {
  const tab = (vp && vp.get('tab')) || 'suggested';
  const page = h('div', { class: 'page' });
  const tabs = h('div', { class: 'eseg', style: 'margin:10px 0' }, [['suggested', 'Suggestions'], ['unknown', 'Unnamed faces'], ['ignored', 'Ignored']].map(([k, l]) => h('button', { class: k === tab ? 'on' : '', onclick: () => go('faces', photosWith({ tab: k })) }, l)));
  const body = h('div');
  main.replaceChildren(page);
  page.append(crumbs([['People', '#/people'], ['Faces', null]]), h('h1', null, 'Faces'), tabs, body);
  let d;
  try { d = await api(`/api/faces/queue?kind=${tab}&limit=500`); } catch (e) { body.replaceChildren(h('div', { class: 'empty' }, e.message)); return; }
  if (route.view !== 'faces') return;
  const crop = (f) => h('img', { class: 'fcrop', src: `/facecrop/${f.photo}/${f.x}/${f.y}/${f.w}/${f.h}.jpg`, alt: '', loading: 'lazy', title: `${f.file} · ${dfDay.format(date(f.ts))} · click to open the photo`, onclick: () => openLightbox({ id: [f.photo] }, 0, true) });
  const op = (f, o, extra) => ({ op: o, image: f.photo, rect: [f.x, f.y, f.w, f.h], ...extra });
  const refresh = () => showFaces(vp);
  if (!d.faces.length) { body.append(h('div', { class: 'empty' }, tab === 'suggested' ? 'No suggestions waiting. digiKam makes suggestions when you run face recognition there.' : tab === 'unknown' ? 'No unnamed faces.' : 'No ignored faces.')); return; }
  if (tab === 'suggested') {
    body.append(h('div', { class: 'muted', style: 'max-width:820px' }, `${nf.format(d.total)} faces digiKam thinks it recognised, grouped by person, like digiKam’s People view. Confirm a whole group at once, or decide face by face. Everything is written to digiKam’s database (digiKam closed; backup first).`));
    for (const [tag, name, count] of d.groups) {
      const faces = d.faces.filter((f) => f.tag === tag);
      const sel = new Set(faces.map((f, i) => i));
      const grid = h('div', { class: 'fgrid' });
      const draw = () => fill(grid, faces.map((f, i) => h('div', { class: 'fcell' + (sel.has(i) ? ' sel' : '') },
        h('label', { class: 'fchk' }, h('input', { type: 'checkbox', checked: sel.has(i), onchange: (e) => { e.target.checked ? sel.add(i) : sel.delete(i); draw(); } })),
        crop(f),
        h('div', { class: 'facts' },
          h('button', { class: 'tact', title: `Yes, this is ${name}`, onclick: async () => { if (await facesBatch([op(f, 'confirm')], `Confirmed ${name}`)) refresh(); } }, icon('check')),
          h('button', { class: 'tact', title: 'Someone else…', onclick: () => personPicker(async (t) => { if (await facesBatch([op(f, 'name', { tag: t.id })], `Named ${t.name}`)) refresh(); }) }, icon('person')),
          h('button', { class: 'tact', title: 'Not a face to name (ignore)', onclick: async () => { if (await facesBatch([op(f, 'ignore')], 'Ignored')) refresh(); } }, icon('close'))))));
      draw();
      body.append(h('div', { class: 'fgroup' },
        h('div', { class: 'fghead' }, h('img', { src: faceUrl(tag), alt: '' }), h('b', null, name), h('span', { class: 'muted' }, `${nf.format(count)} suggested`), h('span', { class: 'sp' }),
          h('button', { class: 'pillbtn on', onclick: async () => { const chosen = faces.filter((f, i) => sel.has(i)); if (!chosen.length) { toast('Nothing selected in this group.'); return; } if (!confirm(`Confirm ${chosen.length} faces as ${name}?`)) return; if (await facesBatch(chosen.map((f) => op(f, 'confirm')), `Confirmed ${name}`)) refresh(); } }, icon('check'), 'Confirm selected'),
          h('button', { class: 'pillbtn', onclick: async () => { const chosen = faces.filter((f, i) => sel.has(i)); if (!chosen.length) return; if (!confirm(`Reject ${chosen.length} suggestions of ${name}? The faces stay as unknown.`)) return; if (await facesBatch(chosen.map((f) => op(f, 'unknown')), 'Rejected')) refresh(); } }, 'Reject selected'),
          h('button', { class: 'pillbtn', onclick: () => { sel.size === faces.length ? sel.clear() : faces.forEach((f, i) => sel.add(i)); draw(); } }, 'Toggle all')),
        grid));
    }
    return;
  }
  // unnamed or ignored faces: a selectable grid, name or ignore many at once
  const sel = new Set();
  const grid = h('div', { class: 'fgrid' });
  const bar = h('div', { style: 'display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:10px 0' });
  const chosen = () => d.faces.filter((f, i) => sel.has(i));
  const drawBar = () => CAN_MANAGE && fill(bar,
    h('span', null, `${nf.format(sel.size)} selected of ${nf.format(d.faces.length)}`),
    h('button', { class: 'pillbtn', onclick: () => { sel.size === d.faces.length ? sel.clear() : d.faces.forEach((f, i) => sel.add(i)); draw(); } }, sel.size === d.faces.length ? 'Select none' : 'Select all'),
    h('button', { class: 'pillbtn on', disabled: !sel.size, onclick: () => personPicker(async (t) => { const c = chosen(); if (!confirm(`Name ${c.length} faces as ${t.name}?`)) return; if (await facesBatch(c.map((f) => op(f, 'name', { tag: t.id })), `Named ${t.name}`)) refresh(); }) }, icon('person'), 'Name selected…'),
    tab === 'unknown' ? h('button', { class: 'pillbtn', disabled: !sel.size, onclick: async () => { const c = chosen(); if (!confirm(`Ignore ${c.length} faces? They stay, marked as not a person to name.`)) return; if (await facesBatch(c.map((f) => op(f, 'ignore')), 'Ignored')) refresh(); } }, 'Ignore selected') : null,
    tab === 'ignored' ? h('button', { class: 'pillbtn', disabled: !sel.size, onclick: async () => { const c = chosen(); if (await facesBatch(c.map((f) => op(f, 'unknown')), 'Back to unknown')) refresh(); } }, 'Back to unnamed') : null,
    h('button', { class: 'pillbtn', disabled: !sel.size, onclick: async () => { const c = chosen(); if (!confirm(`Remove ${c.length} face regions? The photos are not touched.`)) return; if (await facesBatch(c.map((f) => op(f, 'remove')), 'Removed')) refresh(); } }, 'Remove selected'));
  const draw = () => { fill(grid, d.faces.map((f, i) => h('div', { class: 'fcell' + (sel.has(i) ? ' sel' : ''), onclick: (e) => { if (e.target.tagName === 'IMG' && !e.shiftKey && !sel.size) return; if (!CAN_MANAGE) return; e.preventDefault(); sel.has(i) ? sel.delete(i) : sel.add(i); draw(); } },
    CAN_MANAGE ? h('label', { class: 'fchk' }, h('input', { type: 'checkbox', checked: sel.has(i), onclick: (e) => e.stopPropagation(), onchange: (e) => { e.target.checked ? sel.add(i) : sel.delete(i); draw(); } })) : null, crop(f),
    h('div', { class: 'muted', style: 'font-size:11px;text-align:center' }, dfMonth.format(date(f.ts)))))); drawBar(); };
  body.append(h('div', { class: 'muted', style: 'max-width:820px' }, tab === 'unknown' ? `${nf.format(d.total)} faces digiKam found but could not name. Tick the ones that are the same person and name them together; tick ones that are not faces to name and ignore them. Click a face to open its photo.` : `${nf.format(d.total)} faces marked as not to be named.`), bar, grid);
  draw();
  if (d.total > d.faces.length) body.append(h('p', { class: 'muted' }, `Showing the first ${nf.format(d.faces.length)}; decide these and the next ones appear.`));
}

async function showSettings() { return settingsPage('settings'); }
async function showMaintenance() { if (!IS_ADMIN) { main.replaceChildren(h('div', { class: 'empty' }, 'Maintenance is for admins. Sign in as an admin to see it.')); return; } return settingsPage('maintenance'); }
// Settings: preferences. Maintenance: library actions, job progress, models, storage. One loader, two layouts.
async function settingsPage(view) {
  let m;
  try { m = await api('/api/maintenance'); } catch (e) { main.replaceChildren(h('div', { class: 'empty' }, 'Could not load settings: ' + e.message)); return; }
  if (route.view !== view) return;
  const when = (t) => (t ? fmtWhen(t) : 'never');
  const act = async (action, msg, confirmText) => {
    if (confirmText && !confirm(confirmText)) return;
    try { await post('/api/maintenance', { action }); toast(msg); } catch (e) { toast(e.message); }
    setTimeout(() => { if (route.view === view) settingsPage(view); }, 1500);
  };
  const row = (label, detail, btn) => h('div', { class: 'srow' }, h('div', null, h('b', null, label), h('div', { class: 'muted', style: 'font-size:13px' }, detail)), btn);
  const btn = (label, fn, primary) => h('button', { class: 'pillbtn' + (primary ? ' on' : ''), onclick: fn }, label);
  const st = m.storage;
  main.replaceChildren(h('div', { class: 'page' },
    h('h1', null, view === 'settings' ? 'Settings' : 'Maintenance', h('span', { class: 'muted', style: 'font-size:13px;font-weight:400;margin-left:12px' }, `digiKam Viewer v${APP_VERSION || '?'}${APP_COMMIT && APP_COMMIT !== 'unknown' ? ' · ' + APP_COMMIT : ''}`)),
    h('div', { class: 'muted', style: 'max-width:820px' }, `Library: ${m.paths.library} (${nf.format(m.photos)} items). digiKam database: ${m.paths.digikamDb}. Everything the viewer writes lives in ${m.paths.data}.`),
    !USERS_EXIST ? row('No users yet', 'The viewer is open to anyone who can reach it. Create the admin account to switch on sign-in: visitors then browse read-only, and only editors and admins can change the library.', btn('Create the admin account', setupDialog, true)) : null,
    ...(view === 'settings' ? [
    h('h2', null, 'Display'),
    row('Appearance', `Light or dark colours, or follow the device. ${USER ? 'Saved with your account, so it follows you to other devices.' : 'Remembered in this browser; sign in to keep it with an account.'}`,
      h('div', { class: 'eseg', id: 'themeseg' }, THEMES.map(([k, label]) => h('button', { class: store.get('theme', 'system') === k ? 'on' : '', 'data-theme': k, onclick: (e) => {
        store.set('theme', k); applyTheme(); for (const b of e.currentTarget.parentNode.children) b.classList.toggle('on', b === e.currentTarget); } }, label)))),
    row('Thumbnail badges', 'The small marks on thumbnails: face tags, GPS coordinates and favorites. This is remembered per browser.',
      h('label', { style: 'display:flex;gap:8px;align-items:center;cursor:pointer' }, h('input', { type: 'checkbox', checked: store.get('badges', '1') !== '0',
        onchange: (e) => { store.set('badges', e.target.checked ? '1' : '0'); applyBadgePref(); applyTheme(); } }), 'Show badges')),
    IS_ADMIN ? (() => {
      const sel = h('select', null, h('option', { value: 'osm', selected: m.mapProvider !== 'google' }, 'OpenStreetMap (no account needed)'), h('option', { value: 'google', selected: m.mapProvider === 'google' }, 'Google Maps (your API key)'));
      const keyIn = h('input', { class: 'einput', type: 'password', placeholder: m.googleMapsKeySet ? 'key is set; paste a new one to replace it' : 'Google Maps API key', autocomplete: 'off', style: 'margin:0;width:260px' });
      return row('Map provider', `Maps and place search use ${m.mapProvider === 'google' && m.googleMapsKeySet ? 'Google Maps' : 'OpenStreetMap'}. Google needs an API key from the Google Cloud console with the Map Tiles API and Geocoding API enabled and billing on; restrict the key to this viewer's address. The key is stored in the viewer's settings and never shown again.`,
        h('span', { style: 'display:flex;gap:6px;flex-wrap:wrap;align-items:center' }, sel, keyIn, btn('Save', async () => {
          const body = { map_provider: sel.value }; if (keyIn.value.trim()) body.google_maps_key = keyIn.value.trim();
          if (sel.value === 'google' && !keyIn.value.trim() && !m.googleMapsKeySet) { toast('Enter the Google Maps API key first.'); return; }
          try { await post('/api/settings', body); mapsLoaded = false; toast('Map provider saved.'); } catch (e) { toast(e.message); }
          settingsPage(view);
        })));
    })() : null,
    IS_ADMIN ? (() => {
      const d = m.database || {};
      const inp = (k, ph, type = 'text', w = 160) => h('input', { class: 'einput', type, placeholder: ph, value: type === 'password' ? '' : (d[k] ?? ''), autocomplete: 'off', style: `margin:0;width:${w}px`, onkeydown: (e) => e.stopPropagation() });
      const type = h('select', null, h('option', { value: 'sqlite', selected: d.type !== 'mysql' }, 'SQLite (digikam4.db file)'), h('option', { value: 'mysql', selected: d.type === 'mysql' }, 'MySQL / MariaDB'));
      const f = { sqlite_dir: inp('sqlite_dir', 'folder with digikam4.db', 'text', 320), host: inp('host', 'host'), port: inp('port', 'port', 'text', 70), database: inp('database', 'database'), user: inp('user', 'user'),
        password: inp('password', d.password_set ? 'password (stored; leave empty to keep)' : 'password', 'password', 220) };
      const backup = h('select', null, [['auto', 'back up before every write (file copy / mysqldump)'], ['daily', 'MySQL: at most one dump a day for ordinary edits; always before bulk or destructive ones'], ['skip', 'no backup (the server is backed up elsewhere)']].map(([v, l]) => h('option', { value: v, selected: (d.backup || 'auto') === v }, l)));
      const sq = h('div', { style: 'display:flex;gap:6px;flex-wrap:wrap;margin-top:6px' }, f.sqlite_dir), my = h('div', { style: 'display:flex;gap:6px;flex-wrap:wrap;margin-top:6px' }, f.host, f.port, f.database, f.user, f.password);
      const show = () => { sq.hidden = type.value !== 'sqlite'; my.hidden = type.value !== 'mysql'; }; type.onchange = show; show();
      const payload = () => ({ type: type.value, sqlite_dir: f.sqlite_dir.value, host: f.host.value, port: f.port.value, database: f.database.value, user: f.user.value, password: f.password.value, backup: backup.value });
      const result = h('div', { class: 'muted', style: 'font-size:12.5px;margin-top:6px' });
      return row('digiKam database', `Where digiKam keeps its database. Currently ${d.type === 'mysql' ? `MySQL ${d.user}@${d.host}:${d.port}/${d.database}` : `SQLite in ${d.sqlite_dir}`}. Changing it rebuilds the index from the other database within seconds; the viewer's own data (favorites, albums, users, analysis) stays. Test first.`,
        h('div', null, h('div', { style: 'display:flex;gap:6px;flex-wrap:wrap;align-items:center' }, type, backup), sq, my,
          h('div', { style: 'display:flex;gap:6px;margin-top:8px' },
            btn('Test connection', async () => { fill(result, 'Testing…'); try { const r = await post('/api/db/test', payload()); fill(result, `OK: ${nf.format(r.images)} photos, ${nf.format(r.tags)} tags, DBVersion ${r.dbVersion}, album root ${r.roots.join(', ')}`); } catch (e) { fill(result, e.message); } }),
            btn('Save and switch', async () => { if (!confirm('Switch the viewer to this digiKam database now?')) return; try { await post('/api/settings', { database: payload() }); toast('Database settings saved; the index is rebuilding.'); } catch (e) { toast(e.message); return; } setTimeout(() => settingsPage(view), 2500); }, true)),
          result));
    })() : null,
    IS_ADMIN ? (() => {
      const body = h('div', { class: 'muted', style: 'font-size:12.5px' }, 'Loading…');
      const draw = async () => {
        let d; try { d = await api('/api/roots'); } catch (e) { fill(body, e.message); return; }
        const inputs = new Map();
        fill(body, h('div', { style: 'display:grid;gap:8px' }, d.roots.map((r) => {
          const inp = h('input', { class: 'einput', placeholder: r.localPath, value: r.overridden ? r.localPath : '', style: 'margin:0;width:340px', onkeydown: (e) => e.stopPropagation() });
          inputs.set(r.digikamPath, inp);
          return h('div', null, h('div', null, h('b', null, r.label || 'Album root'), ' ', h('span', { class: 'muted' }, `digiKam: ${r.digikamPath}`)),
            h('div', { style: 'display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:4px' }, inp,
              h('span', { class: 'muted', style: 'font-size:12px' }, r.exists ? `found: ${r.localPath} (${r.sample >= 2000 ? '2,000+' : nf.format(r.sample)} files)` : `not found: ${r.localPath}`)));
        }), h('div', { style: 'display:flex;gap:6px' },
          btn('Check', draw),
          btn('Save', async () => { const m = {}; inputs.forEach((inp, k) => { m[k] = inp.value.trim(); }); try { await post('/api/settings', { album_roots: m }); toast('Album roots saved; the index is rebuilding.'); } catch (e) { toast(e.message); return; } setTimeout(draw, 2500); }, true))));
      };
      draw();
      return row('Album roots', `Where each album root digiKam knows is mounted here. Leave a field empty to use the default (PHOTOS_ROOT for a single-root library, else the path digiKam recorded); enter a path when the folder is mounted elsewhere, e.g. /photos in a container. Changing it rebuilds the index.`, body);
    })() : null,
    IS_ADMIN ? row('Read-only mode', m.readOnlyLocked ? 'Locked on by READ_ONLY=1 in the environment: nothing in the library can be changed from the viewer.'
      : `${m.readOnly ? 'On' : 'Off'}. When on, the viewer only browses: editing, tagging, face naming, place tags, GPS tracks, metadata sync and database updates are switched off and refused by the server. Favorites and viewer albums keep working; they never touch the library.`,
      m.readOnlyLocked ? null : btn(m.readOnly ? 'Turn off' : 'Turn on', async () => { try { await post('/api/settings', { read_only: !m.readOnly }); const s = await api('/api/status'); EDITING = s.editing; CAN_MANAGE = s.editing && s.dbWrite; } catch (e) { toast(e.message); } settingsPage(view); })) : null,
    IS_ADMIN ? analysisSection(view, 'prefs') : null,
    IS_ADMIN && USERS_EXIST ? usersSection() : null,
    IS_ADMIN && EDITING ? [
    h('h2', null, 'Editing'),
    row('Write metadata into image files', `Off: edits go to XMP sidecars only. On: also into JPEG, PNG, TIFF and WebP files, like digiKam’s “sidecar and file” mode. Currently ${m.writeFiles ? 'on' : 'off'}.`,
      btn(m.writeFiles ? 'Turn off' : 'Turn on', async () => { try { await post('/api/settings', { write_files: !m.writeFiles }); } catch (e) { toast(e.message); } settingsPage(view); })),
    h('h2', null, 'Place tags'),
    row('Tags from GPS positions', 'Turns each geotagged photo’s town into real digiKam tags under “Places/Country/Region/Town”, so places are searchable in digiKam as well. Missing tags are created in digiKam’s database (digiKam closed); assignments go to sidecars like any edit.',
      h('button', { class: 'pillbtn', onclick: placeTagsDialog }, icon('place'), 'Review and run')),
    templatesSection(m),
    ] : null,
    ] : [
    h('h2', null, 'Library'),
    row('Rescan the library now', `The index is rebuilt from digiKam’s database whenever digiKam saves (last saved ${when(m.digikamSaved)}; index built ${when(m.indexBuilt)}). Force it here if something looks stale.`,
      btn('Rescan now', () => act('reindex', 'Rescanning the library…'), true)),
    row('Thumbnails', `${fmtBytes(st.thumbnails)} of grid thumbnails, ${fmtBytes(st.previews)} of viewer previews, ${fmtBytes(st.faces)} of face crops. Rebuilding thumbnails takes several minutes for the whole library.`,
      h('span', { style: 'display:flex;gap:6px;flex-wrap:wrap' }, btn('Rebuild thumbnails', () => act('thumbs', 'Rebuilding thumbnails in the background.', `Delete all grid thumbnails (${fmtBytes(st.thumbnails)}) and rebuild them?`)),
        btn('Clear previews', () => act('previews', 'Previews cleared; they are remade as you open photos.')), btn('Clear face crops', () => act('faces', 'Face crops cleared; they are remade as needed.')))),
    row('Tag cover photos', 'The photo shown for each tag is chosen by the content model. Pick them again after big tagging changes.', btn('Pick again', () => act('covers', 'Choosing tag covers in the background.'))),
    analysisSection(view, 'jobs'),
    modelsSection(view),
    h('h2', null, 'Metadata consistency'),
    row('Database, sidecars and image files', 'Compares rating, labels, title, caption and tags across digiKam’s database, each photo’s XMP sidecar and the metadata embedded in the file, then lets you sync them in the direction you choose.',
      h('a', { class: 'pillbtn on', href: '#/consistency' }, 'Open the checker')),
    EDITING ? [h('h2', null, 'digiKam database'),
    row('Edits waiting for digiKam', m.pendingEdits ? `${plural(m.pendingEdits, 'photo has', 'photos have')} edits saved in sidecars that digiKam’s database does not have yet. digiKam is ${m.digikamRunning ? 'running, so they cannot be applied right now' : 'closed, so they can be applied now'}.` : 'None. digiKam’s database and the sidecars agree.',
      m.pendingEdits ? btn('Apply to digiKam database…', dbDialog, !m.digikamRunning) : null),
    ] : null,
    (() => {
      const body = h('div', { class: 'muted', style: 'font-size:13px' }, 'Loading…');
      const draw = async () => {
        let u; try { u = await api('/api/update'); } catch (e) { fill(body, e.message); return; }
        const c = u.check, p = u.progress, last = u.lastUpdate;
        const outcome = !p.running && !p.error && last ? h('div', { class: last.ok ? 'muted' : 'warn', style: 'font-size:12px;margin-top:2px' }, `last update: ${last.text}`) : null;
        const state = p.running ? 'updating… the viewer restarts when it is done' : p.error ? `last update failed: ${p.error}` : !c ? `v${u.version} · commit ${u.installed}` : c.status === 'current' ? `v${u.version} (${u.installed}) is the latest` : c.status === 'update' ? `newer version on GitHub: ${c.remote} from ${c.remoteDate} (${c.remoteMessage}); installed ${u.installed}` : `could not check: ${c.error}`;
        fill(body, state, outcome, h('div', { style: 'display:flex;gap:6px;margin-top:6px' },
          btn('Check for updates', async () => { fill(body, 'Checking…'); try { await post('/api/update', { action: 'check' }); } catch (e) { toast(e.message); } draw(); }),
          btn('MCP update token…', async () => { try { const t = await post('/api/update', { action: 'token' }); const back = modal('MCP update token', h('p', { class: 'muted' }, 'An MCP client (e.g. Claude) can run the update with the update_viewer tool and this token; the endpoint itself has no sign-in, so treat it like a password.'), h('div', { class: 'einput', style: 'font-family:monospace;user-select:all;word-break:break-all' }, t.token), t.fromEnv ? h('p', { class: 'muted' }, 'Set by MCP_ADMIN_TOKEN in the environment.') : null,
            h('div', { class: 'modal-btns' }, t.fromEnv ? null : h('button', { class: 'pillbtn', onclick: async () => { if (!confirm('Generate a new token? The old one stops working.')) return; try { await post('/api/update', { action: 'regenerate_token' }); } catch (e) { toast(e.message); } back.remove(); } }, 'Regenerate'), h('button', { class: 'pillbtn on', onclick: () => back.remove() }, 'Close'))); } catch (e) { toast(e.message); } }),
          u.docker ? h('span', { class: 'muted' }, 'Docker: update by pulling the image (docker compose pull && docker compose up -d).')
            : u.canRun ? btn('Update now', async () => { if (!confirm('Fetch the latest version, refresh the packages and restart the viewer?')) return; try { await post('/api/update', { action: 'run' }); toast('Updating; the viewer restarts when it is done.'); } catch (e) { toast(e.message); } setTimeout(draw, 3000); }, c && c.status === 'update') : null));
        if (p.running) setTimeout(() => { if (route.view === view) draw(); }, 5000);
      };
      draw();
      return row('Viewer version', 'The code running here, and whether the GitHub main branch has something newer. "Update now" runs update.sh (git pull or a fresh tarball), keeps your settings and data, and restarts the service.', body);
    })(),
    row('Restart the viewer', 'Stops the server; launchd, Docker or systemd starts it again within seconds. Needed after updating the RapidOCR package.',
      btn('Restart', async () => { if (!confirm('Restart the viewer now?')) return; try { await post('/api/restart', {}); toast('Restarting…'); } catch (e) { toast(e.message); } })),
    h('h2', null, 'Storage'),
    h('div', { class: 'kv', style: 'max-width:520px' }, ...[['Thumbnails', st.thumbnails], ['Previews', st.previews], ['Face crops', st.faces], ['Search index', st.index], ['Analysis results', st.analysis], ['Content embeddings', st.embeddings], ['AI models', st.models], ['Sidecar backups', st.backups], ['Image file backups (originals)', st.fileBackups], ['Database backups', st.dbBackups], ['Free disk space', st.free]].flatMap(([k, v]) => [h('span', null, k), h('span', null, fmtBytes(v) || '0 B')])),
    ]),
    h('div', { class: 'muted', style: 'font-size:13px;margin-top:10px;max-width:820px' }, 'Backups of sidecars, of image files whose metadata was rewritten (the full original file, kept once per photo), and of digiKam’s database are kept in the data folder. They are never deleted automatically; remove them by hand once you are happy with the corresponding changes.')));
}

async function showDuplicates() {
  main.replaceChildren(h('div', { class: 'empty' }, 'Looking for duplicates…'));
  let d;
  try { d = await api('/api/duplicates'); } catch { main.replaceChildren(h('div', { class: 'empty' }, 'Could not load duplicates.')); return; }
  if (route.view !== 'duplicates') return;
  const src = { id: d.groups.flatMap((g) => g.items.map((x) => x.id)) };
  let k = 0;
  main.replaceChildren(h('div', { class: 'page' }, crumbs([['Explore', '#/explore'], ['Duplicate files', null]]), h('h1', null, 'Duplicate files'),
    h('div', { class: 'muted' }, d.groups.length ? `${nf.format(d.groups.length)} sets of byte-identical files, ${fmtBytes(d.wasted)} that could be freed. The viewer never deletes anything; remove the extras in digiKam.`
      : 'No byte-identical files found. digiKam’s file hashes say every item is unique.'),
    d.groups.map((g) => h('div', { class: 'dupgroup' }, h('div', { class: 'muted' }, `${g.items.length} copies · ${fmtBytes(g.size)} each`),
      h('div', { class: 'duprow' }, g.items.map((x) => { const i = k++; return h('div', { class: 'dupitem' },
        h('div', { class: 'tile', style: `width:${Math.round(150 * Math.min(2, x.w / (x.h || 1)))}px;height:150px`, onclick: () => openLightbox(src, i, true) }, h('img', { src: `/thumb/${x.id}`, loading: 'lazy', alt: '' })),
        h('div', { class: 'nm', title: x.name }, x.name), h('a', { class: 'sb lnk', href: hashFor('photos', photosWith({ album: albumIdByPath(x.album), sort: 'old' })) }, x.album.replace(/^\//, ''))); }))))));
  syncLightbox();
}
const albumIdByPath = (path) => META.albums.find((a) => a.path === path)?.id ?? '';

async function tagOp(op, t) {
  let r;
  try { r = await post('/api/tags/op', op); } catch (e) { toast(e.message, null, null, 9000); return; }
  toast(op.op === 'icon' ? `“${r.path}” now uses this photo.` : op.op === 'add' ? `Created “${r.path}”.` : `${{ rename: 'Renamed', move: 'Moved', delete: 'Deleted' }[op.op]} “${r.path}”${r.new_path ? ` → “${r.new_path}”` : ''}.` +
    (r.sidecars ? ` Updating ${nf.format(r.photos)} photos’ sidecars in the background.` : ''), null, null, 8000);
  await awaitReindex();
  $('#taglist')?.remove();  // the tag datalist is rebuilt from the new tag list on next use
  details.clear();
  if (route.view === 'tags') showTags();
  pollSoon(500);
}
const openTags = new Set();  // which tag nodes are expanded, kept across redraws
/** digiKam's own face buckets under People; not real people and not to be renamed, moved or deleted. */
const isFaceBucket = (t) => ['Unknown', 'Ignored', 'Unconfirmed'].includes(t.name) && t.full.startsWith('People/');
/** parent id (0 = top level) -> child tags, optionally leaving some tags out. */
function tagKids(skip = () => false) {
  const kidsOf = new Map();
  for (const t of META.tags) { if (skip(t)) continue; const k = t.pid ?? 0; if (!kidsOf.has(k)) kidsOf.set(k, []); kidsOf.get(k).push(t); }
  return kidsOf;
}
function tagTreePicker(onPick, { exclude = () => false, allowTop = true } = {}) {
  const kidsOf = tagKids(isFaceBucket);
  const filter = h('input', { class: 'pagefilter', style: 'margin:0 0 8px;width:100%', placeholder: 'Find a tag…' });
  const list = h('div', { class: 'alist', style: 'max-height:45vh' });
  const row = (t, depth, flat) => {
    const kids = flat ? [] : (kidsOf.get(t.id) || []);
    const box = h('div');
    const node = h('div', null,
      h('div', { class: 'frow' + (exclude(t) ? ' dis' : ''), style: `padding-left:${8 + depth * 18}px`, title: t.full, onclick: () => { if (!exclude(t)) onPick(t); } },
        h('span', { class: 'tw', style: kids.length ? '' : 'visibility:hidden', onclick: (e) => { e.stopPropagation(); if (!box.children.length) box.append(...kids.map((k) => row(k, depth + 1))); box.hidden = !box.hidden; e.currentTarget.style.transform = box.hidden ? '' : 'rotate(90deg)'; } }, icon('right')),
        icon('tag'), h('span', { class: 'nm' }, flat ? t.full.replaceAll('/', ' › ') : t.name), h('span', { class: 'ct' }, nf.format(t.nAll))), box);
    box.hidden = true;
    return node;
  };
  const draw = (f) => list.replaceChildren(...(allowTop && !f ? [h('div', { class: 'frow', onclick: () => onPick(null) }, icon('folder'), h('span', { class: 'nm' }, h('i', null, 'Top level (no parent)')))] : []),
    ...(f ? META.tags.filter((t) => t._n.includes(f)).slice(0, 100).map((t) => row(t, 0, true)) : (kidsOf.get(0) || []).map((t) => row(t, 0))));
  filter.oninput = () => draw(norm(filter.value));
  draw('');
  return h('div', null, filter, list);
}
function moveTagDialog(t) {
  const sub = (x) => x.id === t.id || x.full.startsWith(t.full + '/') || x.id === t.pid;
  const move = (parent) => { back.remove(); tagOp({ op: 'move', id: t.id, parent }, t); };
  const back = modal(`Move “${t.name}” into…`,
    h('p', null, `Now at “${t.full.replaceAll('/', ' › ')}”. Its sub-tags and photos move with it. Pick the new parent:`),
    tagTreePicker((dest) => { if (dest && sub(dest)) { toast('A tag cannot be moved into itself.'); return; } move(dest ? dest.id : 0); }, { exclude: sub, allowTop: t.pid != null }),
    h('div', { class: 'modal-btns' }, h('button', { class: 'pillbtn', onclick: () => back.remove() }, 'Cancel')));
}

function showTags() {
  const kidsOf = tagKids();
  const row = (t, flat) => {
    const kids = flat ? [] : (kidsOf.get(t.id) || []);
    const node = h('div', { class: 'tnode' });
    const box = h('div', { class: 'tkids' });
    const expand = (on) => {
      if (on && !box.children.length) box.append(...kids.map((k) => row(k)));
      node.classList.toggle('open', on);
      box.hidden = !on;
      on ? openTags.add(t.id) : openTags.delete(t.id);
    };
    const tw = h('span', { class: 'tw', style: kids.length ? '' : 'visibility:hidden', onclick: (e) => { e.stopPropagation(); expand(!node.classList.contains('open')); } }, icon('right'));
    box.hidden = true;
    if (!flat && kids.length && openTags.has(t.id)) expand(true);
    const cover = t.face ? h('img', { class: 'rnd', src: faceUrl(t.face), loading: 'lazy', alt: '' })
      : t.cover ? h('img', { src: `/thumb/${t.cover}`, loading: 'lazy', alt: '' }) : h('span', { class: 'ph' }, icon('tag'));
    const special = t.full === 'People' || isFaceBucket(t);
    const can = manageTags && !special;
    const isPerson = t.person || t.full.startsWith('People/');
    const act = (ic, title, fn) => h('button', { class: 'iconbtn tact', title, onclick: (e) => { e.stopPropagation(); fn(); } }, icon(ic));
    const trow = h('div', { class: 'trow', title: t.full, onclick: () => go('photos', photosWith({ tag: t.id })) }, tw, cover,
      h('span', { class: 'nm' }, flat ? t.full.replaceAll('/', ' › ') : t.name),
      can ? h('span', { class: 'tacts' },
        act('add', 'Add a tag inside this one', () => { const n = prompt(`New tag inside “${t.name}”`); if (n) tagOp({ op: 'add', parent: t.id, name: n }); }),
        act('edit', 'Rename', () => { const n = prompt('Rename tag', t.name); if (n && n !== t.name) tagOp({ op: 'rename', id: t.id, name: n }, t); }),
        h('button', { class: 'pillbtn tmove', title: 'Move this tag (with its sub-tags) under another tag, or to the top level', onclick: (e) => { e.stopPropagation(); moveTagDialog(t); } }, icon('folder'), 'Move'),
        isPerson ? null : act('trash', 'Delete', () => { const kidsN = META.tags.filter((x) => x.full.startsWith(t.full + '/')).length;
          if (confirm(`Delete the tag “${t.full}”${kidsN ? ` and its ${kidsN} sub-tags` : ''}?\n\nIt will be removed from ${nf.format(t.nAll)} photos (the photos themselves are not touched).`)) tagOp({ op: 'delete', id: t.id }, t); })) : null,
      h('span', { class: 'ct' }, nf.format(t.nAll)));
    if (can && !flat) {  // drag a tag onto another tag to file it there
      trow.draggable = true;
      trow.ondragstart = (e) => { e.dataTransfer.setData('text/tag', String(t.id)); e.dataTransfer.effectAllowed = 'move'; dragTag = t; };
      trow.ondragend = () => { dragTag = null; document.querySelectorAll('.trow.over').forEach((x) => x.classList.remove('over')); };
    }
    if (manageTags && !special) {
      const ok = () => dragTag && dragTag.id !== t.id && dragTag.pid !== t.id && !t.full.startsWith(dragTag.full + '/');
      trow.ondragover = (e) => { if (ok()) { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; trow.classList.add('over'); } };
      trow.ondragleave = () => trow.classList.remove('over');
      trow.ondrop = (e) => { e.preventDefault(); trow.classList.remove('over'); if (ok()) { const d = dragTag; dragTag = null; openTags.add(t.id); tagOp({ op: 'move', id: d.id, parent: t.id }, d); } };
    }
    node.append(trow, box);
    return node;
  };
  const tree = h('div', { class: 'tree' });
  const topZone = h('div', { class: 'dropzone', hidden: !manageTags }, icon('folder'), 'Drop a tag here to make it a top-level tag');
  topZone.ondragover = (e) => { if (dragTag && dragTag.pid != null) { e.preventDefault(); topZone.classList.add('over'); } };
  topZone.ondragleave = () => topZone.classList.remove('over');
  topZone.ondrop = (e) => { e.preventDefault(); topZone.classList.remove('over'); if (dragTag && dragTag.pid != null) { const d = dragTag; dragTag = null; tagOp({ op: 'move', id: d.id, parent: 0 }, d); } };
  const draw = (f) => tree.replaceChildren(...(f ? META.tags.filter((t) => t._n.includes(f)).sort((a, b) => b.nAll - a.nAll).slice(0, 200).map((t) => row(t, true))
    : (kidsOf.get(0) || []).map((t) => row(t))));
  main.replaceChildren(h('div', { class: 'page' }, h('h1', null, 'Tags ', h('span', { class: 'muted' }, nf.format(META.tags.length))),
    h('div', { class: 'muted' }, 'Selecting a tag also includes everything filed under it.'),
    h('div', { style: 'display:flex;gap:10px;align-items:center;flex-wrap:wrap' },
      h('input', { class: 'pagefilter', placeholder: 'Find a tag…', oninput: (e) => draw(norm(e.target.value)) }),
      CAN_MANAGE ? h('button', { class: 'pillbtn' + (manageTags ? ' on' : ''), style: 'margin-top:6px', onclick: () => { manageTags = !manageTags; document.body.classList.toggle('managing', manageTags); showTags(); } }, icon('edit'), manageTags ? 'Done managing' : 'Manage tags') : null,
      manageTags ? h('button', { class: 'pillbtn', style: 'margin-top:6px', onclick: () => { const n = prompt('New top-level tag'); if (n) tagOp({ op: 'add', parent: 0, name: n }); } }, icon('add'), 'New top-level tag') : null),
    manageTags ? h('div', { class: 'enote', style: 'max-width:760px' }, 'To change the hierarchy, drag a tag onto the tag that should contain it, or use its Move button to pick a parent from the tree. Sub-tags and photos move with it. Changes go to digiKam’s database, so digiKam must be closed; a backup is saved first, and the sidecars of affected photos are updated in the background. People tags are managed in digiKam.') : null,
    h('div', { style: 'height:8px' }), topZone, tree));
  draw('');
}

// ---------------------------------------------------------------- map
const M = { data: null, map: null, token: 0 };
let leafletP = null, clusterP = null;
function loadLeaflet(cluster) {
  const css = (href) => document.head.append(h('link', { rel: 'stylesheet', href }));
  const js = (src) => new Promise((ok, fail) => document.head.append(h('script', { src, onload: ok, onerror: () => fail(new Error('offline')) })));
  leafletP ||= (css('https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'), js('https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'));
  if (!cluster) return leafletP;
  clusterP ||= leafletP.then(() => {
    css('https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css');
    css('https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css');
    return js('https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js');
  });
  return clusterP;
}
// tile provider from the server (OpenStreetMap, or Google Maps with the owner's key); fetched once, OSM until it arrives
let MAPS = { provider: 'osm', url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', attribution: '© OpenStreetMap contributors', maxZoom: 19, link: 'https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=15/{lat}/{lon}', linkLabel: 'OpenStreetMap' };
let mapsLoaded = false;
async function loadMaps() { if (mapsLoaded) return MAPS; try { MAPS = await api('/api/maps'); if (MAPS.error) toast(MAPS.error, null, null, 8000); } catch { /* keep OSM */ } mapsLoaded = true; return MAPS; }
const tiles = () => window.L.tileLayer(MAPS.url, { maxZoom: MAPS.maxZoom, attribution: MAPS.attribution });
const mapLink = (lat, lon) => MAPS.link.replaceAll('{lat}', lat).replaceAll('{lon}', lon);

async function showMap(fp) {
  const token = ++M.token;
  M.data = null;
  M.map?.remove(); M.map = null;
  const el = h('div', { id: 'map' });
  const bar = h('div', { class: 'mapbar' });
  main.replaceChildren(el, bar);
  let d;
  try { [d] = await Promise.all([api('/api/map?' + fp.toString()), loadLeaflet(true)]); } catch {
    main.replaceChildren(h('div', { class: 'empty' }, 'The map needs an internet connection for map tiles. Everything else works offline.'));
    return;
  }
  if (token !== M.token || route.view !== 'map') return;
  const L = window.L;
  M.data = d;
  await loadMaps();
  const map = M.map = L.map(el, { worldCopyJump: true }).setView([30, 0], 2);
  tiles().addTo(map);
  const dot = L.divIcon({ className: '', html: '<div class="pm"></div>', iconSize: [14, 14], iconAnchor: [7, 7] });
  const group = L.markerClusterGroup({ chunkedLoading: true, maxClusterRadius: 55, showCoverageOnHover: false, zoomToBoundsOnClick: false });
  group.addLayers(d.id.map((id, i) => L.marker([d.lat[i], d.lon[i]], { icon: dot, idx: i }).on('click', () => openLightbox(M.data, i, true))));
  // clicking a bubble offers all of its photos at once instead of forcing a drill-down
  group.on('clusterclick', (ev) => {
    const idxs = ev.layer.getAllChildMarkers().map((m) => m.options.idx).sort((a, b) => a - b);
    const b = ev.layer.getBounds();
    const openAll = () => {
      map.closePopup();
      const q = filterParams();
      q.delete('bbox'); q.delete('ids');
      if (idxs.length <= 600) q.set('ids', idxs.map((i) => d.id[i]).join(','));
      else q.set('bbox', [b.getSouth() - 1e-4, b.getWest() - 1e-4, b.getNorth() + 1e-4, b.getEast() + 1e-4].map((x) => x.toFixed(5)).join(','));
      go('photos', q);
    };
    const el = h('div', { class: 'mpop' },
      h('div', { class: 'mthumbs' }, idxs.slice(0, 8).map((i) => h('img', { src: `/thumb/${d.id[i]}`, alt: '', onclick: () => { map.closePopup(); openLightbox(M.data, i, true); } }))),
      h('div', { class: 'mbtns' },
        h('button', { class: 'pillbtn on', onclick: openAll }, icon('photo'), `Open all ${nf.format(idxs.length)} photos`),
        h('button', { class: 'pillbtn', onclick: () => { map.closePopup(); ev.layer.zoomToBounds({ padding: [30, 30] }); } }, 'Zoom in')));
    L.popup({ maxWidth: 360, minWidth: 300, closeButton: false }).setLatLng(ev.layer.getLatLng()).setContent(el).openOn(map);
  });
  map.addLayer(group);
  if (d.id.length) map.fitBounds(L.latLngBounds(d.id.map((_, i) => [d.lat[i], d.lon[i]])).pad(0.1), { maxZoom: 15 });
  const trailDay = fp.get('trail') || (fp.get('from') && fp.get('from') === fp.get('to') ? fp.get('from') : null);
  if (trailDay) api(`/api/trail?day=${trailDay}`).then((t) => {
    if (token !== M.token || t.id.length < 2) return;
    const pts = t.id.map((_, i) => [t.lat[i], t.lon[i]]);
    L.polyline(pts, { color: '#ea4335', weight: 3, opacity: .8, dashArray: '6 6' }).addTo(map);
    L.circleMarker(pts[0], { radius: 7, color: '#34a853', fillOpacity: 1 }).bindTooltip('Start · ' + dfTime.format(date(t.ts[0]))).addTo(map);
    L.circleMarker(pts[pts.length - 1], { radius: 7, color: '#ea4335', fillOpacity: 1 }).bindTooltip('End · ' + dfTime.format(date(t.ts[t.ts.length - 1]))).addTo(map);
    const km = pts.reduce((a, p, i) => i ? a + Math.hypot(p[0] - pts[i - 1][0], (p[1] - pts[i - 1][1]) * Math.cos(p[0] * Math.PI / 180)) * 111.2 : 0, 0);
    bar.append(h('span', { class: 'pillbtn', style: 'cursor:default' }, `Trail: ${t.id.length} photos, ${km.toFixed(1)} km, ${dfTime.format(date(t.ts[0]))} to ${dfTime.format(date(t.ts[t.ts.length - 1]))}`));
    map.fitBounds(L.latLngBounds(pts).pad(0.15));
  }).catch(() => {});
  bar.append(h('span', { class: 'pillbtn', style: 'cursor:default' }, `${nf.format(d.id.length)} with location`),
    h('button', { class: 'pillbtn', onclick: () => {
      const b = map.getBounds();
      applyFilter((p) => p.set('bbox', [b.getSouth(), b.getWest(), b.getNorth(), b.getEast()].map((x) => x.toFixed(4)).join(',')), 'photos');
    } }, icon('photo'), 'Show photos in this area'));
  syncLightbox();
}

// ---------------------------------------------------------------- filter drawer (browse all metadata)
const expanded = new Set();
function toggleFilters(force) {
  const el = $('#filters');
  el.hidden = force != null ? !force : !el.hidden;
  document.body.classList.toggle('filters-open', !el.hidden);
  $('#filterbtn').classList.toggle('on', !el.hidden);
  store.set('filters', el.hidden ? '0' : '1');
  if (!el.hidden) renderFilters();
}
let facetToken = 0;
async function renderFilters() {
  const el = $('#filters');
  const p = filterParams();
  const token = ++facetToken;
  let f;
  try { f = await api('/api/facets?' + p.toString()); } catch { return; }
  if (token !== facetToken) return;
  const has = (k, v) => p.getAll(k).includes(String(v));
  const frow = (label, count, on, onclick, extra) => h('div', { class: 'frow' + (on ? ' on' : ''), onclick, title: label }, extra, h('span', { class: 'nm' }, label),
    h('span', { class: 'ct' }, count != null ? nf.format(count) : ''));
  const section = (title, rows, limit = 8) => {
    if (!rows.length) return null;
    const open = expanded.has(title);
    return [h('h3', null, title, rows.length > limit ? h('span', { class: 'more', onclick: () => { open ? expanded.delete(title) : expanded.add(title); renderFilters(); } },
      open ? 'Show less' : `All ${rows.length}`) : null), ...(open ? rows : rows.slice(0, limit))];
  };
  const multi = (key, list, labelOf = (v) => v, extraOf) => list.filter(([v]) => v != null).map(([v, n]) =>
    frow(labelOf(v), n, has(key, v), () => applyFilter((q) => toggle(q, key, v)), extraOf?.(v)));
  const tagRows = (person) => f.tags.filter(([id]) => !!tagById.get(id)?.person === person).map(([id, n]) => {
    const t = tagById.get(id);
    return t && frow(person ? t.name : t.full.split('/').slice(-2).join(' › '), n, has('tag', id), () => applyFilter((q) => toggle(q, 'tag', id)),
      person ? h('img', { src: faceUrl(id), loading: 'lazy', alt: '' }) : null);
  }).filter(Boolean);
  const range = (label, key, lohi, step) => h('div', { class: 'fpair' }, h('label', null, label), ...['min', 'max'].map((m, i) =>
    h('input', { type: 'number', step, placeholder: lohi[i] != null ? `${m} ${+(+lohi[i]).toFixed(1)}` : m, value: p.get(`${key}_${m}`) || '',
      onchange: (e) => applyFilter((q) => { e.target.value ? q.set(`${key}_${m}`, e.target.value) : q.delete(`${key}_${m}`); }) })));
  const dateIn = (label, key, ph) => h('div', { class: 'fpair' }, h('label', null, label),
    h('input', { type: 'date', value: p.get(key) || '', title: ph, onchange: (e) => applyFilter((q) => { e.target.value ? q.set(key, e.target.value) : q.delete(key); }) }));
  const rating = +(p.get('rating') || 0);
  const scroll = el.scrollTop;
  fill(el,
    h('div', { class: 'fhead' }, h('span', null, 'Filters'), h('span', { class: 'muted', style: 'margin-left:10px;font-size:13px' }, `${nf.format(f.count)} items`), h('span', { class: 'sp' }),
      [...p.keys()].length ? h('span', { class: 'lnk', style: 'font-size:13px;margin-right:6px', onclick: () => go(route.view === 'map' ? 'map' : 'photos', new URLSearchParams()) }, 'Clear all') : null,
      h('button', { class: 'iconbtn', title: 'Close', onclick: () => toggleFilters(false) }, icon('close'))),
    h('h3', null, 'Type'),
    frow('Photos', f.count - f.videos, p.get('type') === 'photo', () => applyFilter((q) => setOne(q, 'type', 'photo'))),
    frow('Videos', f.videos, p.get('type') === 'video', () => applyFilter((q) => setOne(q, 'type', 'video'))),
    h('h3', null, 'Rating at least'),
    h('div', { class: 'stars' }, [1, 2, 3, 4, 5].map((n) => h('button', { class: n <= rating ? 'on' : '', title: `${n} star${n > 1 ? 's' : ''} and up`,
      onclick: () => applyFilter((q) => setOne(q, 'rating', n)) }, icon('star')))),
    h('h3', null, 'Date'),
    dateIn('From', 'from', f.tsMin != null ? isoDay(f.tsMin) : ''), dateIn('Until', 'to', f.tsMax != null ? isoDay(f.tsMax) : ''),
    section('Year', multi('year', f.years), 6),
    section('People', tagRows(true)),
    section('Tags', [...tagRows(false), frow('Untagged', null, p.get('untagged') === '1', () => applyFilter((q) => setOne(q, 'untagged', '1')))]),
    section('Album', f.albums.map(([id, n]) => albumById.get(id) && frow(albumById.get(id).path.replace(/^\//, ''), n, has('album', id),
      () => applyFilter((q) => toggle(q, 'album', id)))).filter(Boolean), 6),
    h('h3', null, 'Location'),
    frow('Favorites', null, p.get('fav') === '1', () => applyFilter((q) => setOne(q, 'fav', '1')), icon('heart')),
    frow('Has location', f.geotagged, p.get('geo') === '1', () => applyFilter((q) => setOne(q, 'geo', '1'))),
    frow('No location', f.count - f.geotagged, p.get('geo') === '0', () => applyFilter((q) => setOne(q, 'geo', '0'))),
    f.geotagged ? frow('Show these on the map', null, false, () => go('map', p), icon('place')) : null,
    section('Country', multi('country', f.countries), 5),
    section('Place', f.places.map(([city, region, country, n]) => frow(`${city}${region ? ', ' + region : ''}`, n, p.get('place') === city,
      () => applyFilter((q) => { if (q.get('place') === city) { q.delete('place'); q.delete('region'); } else { q.set('place', city); region ? q.set('region', region) : q.delete('region'); } }))), 8),
    section('Camera', f.cameras.map(([v, n]) => frow(v ?? 'Unknown camera', n, has('camera', v ?? '~'), () => applyFilter((q) => toggle(q, 'camera', v ?? '~')))), 6),
    section('Lens', multi('lens', f.lenses), 6),
    section('Quality', [
      f.extras.sharpest ? frow('Sharpest fifth', f.extras.sharpest, p.get('sharpest') === '1', () => applyFilter((q) => setOne(q, 'sharpest', '1'))) : null,
      f.extras.blurry ? frow('Blurry (least sharp tenth)', f.extras.blurry, p.get('blurry') === '1', () => applyFilter((q) => setOne(q, 'blurry', '1'))) : null,
      f.extras.dark ? frow('Very dark', f.extras.dark, p.get('exposure') === 'dark', () => applyFilter((q) => setOne(q, 'exposure', 'dark'))) : null,
      f.extras.bright ? frow('Very bright', f.extras.bright, p.get('exposure') === 'bright', () => applyFilter((q) => setOne(q, 'exposure', 'bright'))) : null,
      f.extras.hastext ? frow('Contains text', f.extras.hastext, p.get('hastext') === '1', () => applyFilter((q) => setOne(q, 'hastext', '1'))) : null,
    ].filter(Boolean), 9),
    section('Bursts', f.extras.bursts ? [
      frow('In a burst', f.extras.bursts, p.get('bursts') === '1', () => applyFilter((q) => setOne(q, 'bursts', '1'))),
      frow('Show only the best frame of each burst', null, p.get('bestonly') === '1', () => applyFilter((q) => setOne(q, 'bestonly', '1'))),
      frow('Review these bursts', null, false, () => go('bursts', p), icon('dup'))] : [], 9),
    section('People in the picture', f.npeople.sort((a, b) => a[0] - b[0]).reduce((acc, [n, c]) => { const k = n >= 5 ? '5+' : String(n); const e = acc.find((x) => x[0] === k); e ? e[1] += c : acc.push([k, c]); return acc; }, [])
      .map(([k, c]) => frow(k === '0' ? 'No people' : k === '1' ? '1 person' : `${k} people`, c, p.get('npeople') === k, () => applyFilter((q) => setOne(q, 'npeople', k)))), 8),
    section('Objects', multi('obj', f.objects), 8),
    h('h3', null, 'Exposure'),
    range('ISO', 'iso', f.iso, 1), range('Aperture ƒ/', 'ap', f.aperture, 0.1), range('Focal mm', 'fl', f.focal, 1),
    section('Photographer', multi('creator', f.creators), 5),
    section('File type', multi('fmt', f.formats), 10),
  );
  el.scrollTop = scroll;
}

// ---------------------------------------------------------------- lightbox
// src = the list being browsed ({id, w, h, ts, video}); faces/objects = overlay toggles; pushed = we added a history entry for ?p=
const LB = { open: false, src: null, i: 0, token: 0, info: store.get('info', '0') === '1', faces: false, objects: false, scale: 1, tx: 0, ty: 0, ar: 1.5, pushed: false, detail: null, play: 0, mini: null, hires: false };
const details = new Map();  // photo id -> promise of /api/photo/:id, bounded LRU-ish cache
const NATIVE = new Set(['JPG', 'PNG', 'GIF', 'WEBP']);
function getDetail(id) {
  if (!details.has(id)) {
    details.set(id, api(`/api/photo/${id}`));
    if (details.size > 400) details.delete(details.keys().next().value);
  }
  return details.get(id);
}
function currentSource() { return route.view === 'map' ? M.data : route.view === 'photos' ? G.data : { id: [] }; }
function syncLightbox() {
  const p = +route.params.get('p');
  if (!p) { if (LB.open) closeLightbox(false); return; }
  if (LB.open && LB.src.id[LB.i] === p) return;
  const src = currentSource();
  if (!src) return; // still loading; called again when data arrives
  const idx = src.id.indexOf(p);
  if (idx >= 0) openLightbox(src, idx, false); else openLightbox({ id: [p] }, 0, false);
}
function setPhotoParam(id, push) {
  const p = new URLSearchParams(route.params);
  p.set('p', id);
  history[push ? 'pushState' : 'replaceState'](null, '', hashFor(route.view, p));
  route = parseHash();
}

function buildLightbox() {
  const lb = $('#lightbox');
  const btn = (name, title, fn, cls = '') => h('button', { class: 'iconbtn ' + cls, title, onclick: (e) => { e.stopPropagation(); fn(); } }, icon(name));
  LB.el = {
    frame: h('div', { class: 'lb-frame' }), ttl: h('div', { class: 'ttl' }),
    info: h('aside', { class: 'lb-info', hidden: !LB.info }),
    favBtn: btn('heartO', 'Favorite (L)', () => setFavorite([LB.src.id[LB.i]], !ST.fav.has(LB.src.id[LB.i]))),
    albumBtn: btn('add', 'Add to album', () => albumDialog([LB.src.id[LB.i]])),
    playBtn: btn('play', 'Slideshow (space)', toggleSlideshow), facesBtn: btn('face', 'Show faces (F)', toggleFaces), addFaceBtn: btn('add', 'Add a face: drag a rectangle around it', startDrawFace), objectsBtn: btn('dup', 'Show detected objects (O)', toggleObjects),
    infoBtn: btn('info', 'Info (I)', toggleInfo, LB.info ? 'on' : ''),
    shareBtn: btn('share', 'Share', shareNow),
    dl: h('a', { class: 'iconbtn', title: 'Download original (D)', download: '' }, icon('download')),
    orig: h('a', { class: 'iconbtn', title: 'Open original in a new tab', target: '_blank', rel: 'noopener' }, icon('open')),
  };
  const e = LB.el;
  e.prev = h('button', { class: 'lb-nav prev', title: 'Previous (←)', onclick: (ev) => { ev.stopPropagation(); step(-1); } }, icon('left'));
  e.next = h('button', { class: 'lb-nav next', title: 'Next (→)', onclick: (ev) => { ev.stopPropagation(); step(1); } }, icon('right'));
  // the film strip: thumbnails of the photos around the current one, along the bottom edge.
  // Like a taskbar set to auto-hide it stays out of the way, slides up when the pointer reaches
  // the bottom edge (or on a tap of its grip on touch screens) and drops again when it leaves.
  e.strip = h('div', { class: 'lb-strip' }, h('div', { class: 'grip', title: 'Film strip', onclick: () => e.strip.classList.toggle('show') }), h('div', { class: 'reel' }));
  e.stage = h('div', { class: 'lb-stage' },
    h('div', { class: 'lb-top' }, btn('close', 'Close (Esc): back to the list', () => closeLightbox(true)), e.ttl, h('span', { class: 'sp' }), e.playBtn, e.facesBtn, e.addFaceBtn, e.objectsBtn, e.shareBtn, e.dl, e.favBtn, e.albumBtn, e.infoBtn),
    e.frame, e.prev, e.next, e.strip);
  lb.replaceChildren(e.stage, e.info);
  initGestures(e.stage);
  let idle;
  e.stage.addEventListener('pointermove', (ev) => {
    e.stage.classList.remove('lb-idle');
    clearTimeout(idle);
    idle = setTimeout(() => e.stage.classList.add('lb-idle'), 2800);
    if (ev.pointerType === 'mouse') {
      const nearBottom = e.stage.clientHeight - ev.clientY + e.stage.getBoundingClientRect().top < 110;
      e.strip.classList.toggle('show', nearBottom || ev.target.closest('.lb-strip') !== null);
    }
  });
  e.stage.addEventListener('pointerleave', () => { e.strip.classList.remove('show'); unpeek(); });
  e.strip.addEventListener('pointerleave', unpeek);
}

/** Share: the device's own share sheet (AirDrop, Messages, Mail and the rest on a Mac or phone)
 *  with the picture attached, as PhotoStructure does. The screen-size JPEG is fetched as soon as
 *  the photo is shown, so the sheet opens inside the click, which browsers require. Where the
 *  browser has no share sheet (Firefox on the desktop, plain http) the menu below opens instead. */
function shareNow() {
  const anchor = LB.el.shareBtn;
  if (!navigator.share) { shareMenu(anchor); return; }
  const id = LB.src.id[LB.i], d = LB.detail, name = d?.name || `photo-${id}.jpg`;
  const data = { title: name, url: location.href };
  const file = LB.shareFile && LB.shareFile.id === id ? LB.shareFile.file : null;
  if (file && (!navigator.canShare || navigator.canShare({ files: [file] }))) { data.files = [file]; delete data.url; }
  navigator.share(data).catch((e) => {
    if (e.name === 'AbortError') return;  // the sheet was dismissed
    shareMenu(anchor);
  });
}
/** Fetch the picture a share would attach (the screen-size JPEG, named after the photo). */
function prefetchShareFile(id, d) {
  if (!navigator.share || d.video) { LB.shareFile = null; return; }
  fetch(`/preview/${id}`).then((r) => r.blob()).then((blob) => {
    if (LB.open && LB.src.id[LB.i] === id) LB.shareFile = { id, file: new File([blob], d.name.replace(/\.[^.]+$/, '') + '.jpg', { type: 'image/jpeg' }) };
  }).catch(() => {});
}

/** The fallback menu: a link to the photo here, the original or a smaller JPEG as a download,
 *  the original in a tab, and an email with the link. Anchored under the share button. */
function shareMenu(anchor) {
  const open = $('.sharemenu');
  if (open) { open.remove(); return; }
  const id = LB.src.id[LB.i], d = LB.detail, name = d?.name || `photo ${id}`, url = location.href;
  const item = (label, attrs, sub) => h('a', { class: 'fmi', ...attrs }, label, sub ? h('div', { class: 'muted', style: 'font-size:12px' }, sub) : null);
  const done = (msg) => { menu.remove(); if (msg) toast(msg); };
  const menu = h('div', { class: 'facemenu sharemenu' }, h('div', { class: 'fmh' }, 'Share'),
    item('Copy link', { onclick: async () => { try { await navigator.clipboard.writeText(url); done('Link copied.'); } catch { done('Could not copy; the address bar has the link.'); } } }, 'to this photo in the viewer'),
    item('Download original', { href: `/orig/${id}?dl=1`, download: name, onclick: () => menu.remove() }, d?.bytes ? `${name} · ${fmtBytes(d.bytes)}` : name),
    !d?.video ? item('Download preview', { href: `/preview/${id}?dl=1`, onclick: () => menu.remove() }, 'a smaller JPEG for messages and email') : null,
    item('Open original in a new tab', { href: `/orig/${id}`, target: '_blank', rel: 'noopener', onclick: () => menu.remove() }),
    item('Email a link', { href: `mailto:?subject=${encodeURIComponent(name)}&body=${encodeURIComponent(url)}`, onclick: () => menu.remove() }));
  const { stage } = LB.el;
  stage.append(menu);
  // under the button's right edge; the bar sits at the stage's top-left, so the button's offsets are stage coordinates
  menu.style.top = (anchor.offsetTop + anchor.offsetHeight + 4) + 'px';
  menu.style.left = Math.max(8, Math.min(anchor.offsetLeft + anchor.offsetWidth - menu.offsetWidth, stage.clientWidth - menu.offsetWidth - 8)) + 'px';
  const close = (e) => { if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener('pointerdown', close, true); } };
  setTimeout(() => document.addEventListener('pointerdown', close, true), 0);
}

/** Hovering a strip thumbnail shows that photo over the stage, without leaving the current one;
 *  the thumbnail appears at once and the full preview replaces it when loaded. */
function peek(id) {
  clearTimeout(LB.peekT);
  LB.peekT = setTimeout(() => {
    if (!LB.open) return;
    const { stage } = LB.el;
    let im = LB.peekEl;
    if (!im) { im = LB.peekEl = h('img', { class: 'lb-peek', alt: '', draggable: 'false' }); stage.append(im); }
    im.dataset.id = id;
    im.src = `/thumb/${id}`;
    const full = new Image();
    full.onload = () => { if (LB.peekEl === im && im.dataset.id === String(id)) im.src = full.src; };
    full.src = `/preview/${id}`;
  }, 90);
}
function unpeek() {
  clearTimeout(LB.peekT);
  LB.peekEl?.remove(); LB.peekEl = null;
}

/** Rebuild the strip around the current photo when it drifts out of the rendered window, and
 *  keep the current one marked and centred. */
function renderStrip() {
  const { src, i, el } = LB, reel = el.strip.querySelector('.reel');
  if (!src || src.id.length < 2) { el.strip.hidden = true; return; }
  el.strip.hidden = false;
  const W = 80;  // thumbnails rendered on each side; a window keeps a 30,000-photo grid cheap
  if (LB.stripSrc !== src || LB.stripLo == null || i < LB.stripLo + 15 && LB.stripLo > 0 || i > LB.stripHi - 15 && LB.stripHi < src.id.length - 1) {
    const lo = Math.max(0, i - W), hi = Math.min(src.id.length - 1, i + W);
    LB.stripSrc = src; LB.stripLo = lo; LB.stripHi = hi;
    const kids = [];
    for (let k = lo; k <= hi; k++) {
      const ar = src.w ? Math.max(0.6, Math.min(2.2, src.w[k] / (src.h[k] || 1))) : 1;
      kids.push(h('img', { src: `/thumb/${src.id[k]}`, alt: '', loading: 'lazy', draggable: 'false', 'data-i': k, style: `width:${Math.round(56 * ar)}px`,
        onpointerenter: (ev) => { if (ev.pointerType === 'mouse' && k !== LB.i) peek(src.id[k]); else unpeek(); },
        onclick: () => { unpeek(); if (LB.i === k) return; LB.i = k; setPhotoParam(src.id[k], false); showItem(); } }));
    }
    reel.replaceChildren(...kids);
  }
  for (const im of reel.children) im.classList.toggle('cur', +im.dataset.i === i);
  const cur = reel.querySelector('.cur');
  // scroll the reel itself: scrollIntoView would also scroll the stage to reach a parked strip
  if (cur) reel.scrollTo({ left: cur.offsetLeft - reel.clientWidth / 2 + cur.offsetWidth / 2, behavior: el.strip.classList.contains('show') ? 'smooth' : 'instant' });
}

function openLightbox(src, i, fromUser) {
  if (!LB.el) buildLightbox();
  const wasOpen = LB.open;
  LB.open = true; LB.src = src; LB.i = i;
  if (!wasOpen) {  // the info panel opens the way it was last left (the account's setting, or this browser's)
    LB.info = store.get('info', '0') === '1';
    LB.el.info.hidden = !LB.info; LB.el.infoBtn.classList.toggle('on', LB.info);
  }
  $('#lightbox').hidden = false;
  if (fromUser) { setPhotoParam(src.id[i], !wasOpen); if (!wasOpen) LB.pushed = true; }
  showItem();
}
function closeLightbox(fromUser) {
  if (!LB.open) return;
  stopSlideshow();
  LB.open = false; LB.token++;
  LB.el.frame.replaceChildren();
  LB.mini?.remove(); LB.mini = null; LB.stripSrc = null;
  $('.facemenu')?.remove();
  $('#lightbox').hidden = true;
  const src = LB.src, i = LB.i;
  if (fromUser) {
    if (LB.pushed) { LB.pushed = false; history.back(); }
    else { const p = new URLSearchParams(route.params); p.delete('p'); history.replaceState(null, '', hashFor(route.view, p)); route = parseHash(); }
  }
  LB.pushed = false;
  if (src === G.data && route.view === 'photos') { scrollToIndex(i); renderGrid(true); }
}
function step(d) {
  const n = LB.i + d;
  if (n < 0 || n >= LB.src.id.length) { if (LB.play) stopSlideshow(); return; }
  LB.i = n;
  setPhotoParam(LB.src.id[n], false);
  showItem();
}

function showItem() {
  const { src, i, el } = LB;
  const id = src.id[i], token = ++LB.token;
  unpeek(); $('.sharemenu')?.remove();
  LB.scale = 1; LB.tx = LB.ty = 0; LB.detail = null; LB.hires = false;
  const img = h('img', { src: `/thumb/${id}`, alt: '', draggable: 'false' });
  LB.img = img;
  el.frame.replaceChildren(img);
  if (src.w) LB.ar = src.w[i] / (src.h[i] || 1);
  else img.onload = () => { if (token === LB.token && !LB.detail) { LB.ar = img.naturalWidth / img.naturalHeight; sizeFrame(); } };
  sizeFrame();
  el.ttl.textContent = src.ts ? dfDay.format(date(src.ts[i])) : '';
  // the strip's thumbnails come after the photo and its details, not in competition with them
  setTimeout(() => { if (token === LB.token) renderStrip(); }, LB.stripSrc === src ? 0 : 350);
  updateFavBtn();
  el.dl.href = `/orig/${id}?dl=1`;
  el.orig.href = `/orig/${id}`;
  el.prev.style.visibility = i > 0 ? '' : 'hidden';
  el.next.style.visibility = i < src.id.length - 1 ? '' : 'hidden';
  let isVideo = src.video ? i in src.video : undefined;
  const loadPreview = () => {
    const pre = new Image();
    pre.onload = () => { if (token === LB.token && !LB.hires) img.src = pre.src; };
    pre.src = `/preview/${id}`;
  };
  const mountVideo = () => {
    const v = h('video', { src: `/orig/${id}`, poster: `/preview/${id}`, controls: true, autoplay: true, playsinline: true });
    v.onerror = () => { if (token === LB.token) { v.remove(); toast('This video format cannot play in the browser.', 'Download', () => el.dl.click()); } };
    v.onended = () => { if (LB.play) step(1); };
    el.frame.append(v);
  };
  if (isVideo === true) mountVideo(); else if (isVideo === false) loadPreview();
  getDetail(id).then((d) => {
    if (token !== LB.token) return;
    LB.detail = d;
    LB.ar = d.w / (d.h || 1);
    sizeFrame();
    if (isVideo === undefined) { isVideo = !!d.video; d.video ? mountVideo() : loadPreview(); }
    el.ttl.replaceChildren(d.title || d.name, h('small', null, `${dfDay.format(date(d.ts))} · ${dfTime.format(date(d.ts))}`));
    el.facesBtn.style.display = d.faces.length || d.faces_other?.length ? '' : 'none';
    el.addFaceBtn.style.display = CAN_MANAGE && !d.video ? '' : 'none';
    el.objectsBtn.style.display = d.boxes?.length ? '' : 'none';
    prefetchShareFile(id, d);
    renderFaces();
    if (LB.info) renderInfo();
  }).catch(() => {});
  // warm the neighbours so stepping feels instant
  for (const j of [i + 1, i - 1, i + 2]) {
    if (j < 0 || j >= src.id.length) continue;
    new Image().src = `/thumb/${src.id[j]}`;
    if (src.video && !(j in src.video) && Math.abs(j - i) === 1) new Image().src = `/preview/${src.id[j]}`;
  }
}
function updateFavBtn() {
  const on = ST.fav.has(LB.src.id[LB.i]);
  LB.el.favBtn.replaceChildren(icon(on ? 'heart' : 'heartO'));
  LB.el.favBtn.classList.toggle('faved', on);
}
function sizeFrame() {
  const { stage, frame } = LB.el;
  const sw = stage.clientWidth, sh = stage.clientHeight;
  const w = Math.min(sw, sh * LB.ar), hgt = w / LB.ar;
  LB.fw = w; LB.fh = hgt;
  frame.style.width = w + 'px'; frame.style.height = hgt + 'px';
  frame.style.marginLeft = -w / 2 + 'px'; frame.style.marginTop = -hgt / 2 + 'px';
  applyZoom();
}
function applyZoom() {
  const { stage, frame } = LB.el;
  if (LB.scale <= 1.001) { LB.scale = 1; LB.tx = LB.ty = 0; }
  const mx = Math.max(0, (LB.fw * LB.scale - stage.clientWidth) / 2), my = Math.max(0, (LB.fh * LB.scale - stage.clientHeight) / 2);
  LB.tx = Math.min(mx, Math.max(-mx, LB.tx)); LB.ty = Math.min(my, Math.max(-my, LB.ty));
  frame.style.transform = `translate(${LB.tx}px, ${LB.ty}px) scale(${LB.scale})`;
  stage.style.cursor = LB.scale > 1 ? 'grab' : '';
  // past the preview's resolution, switch to the original file if the browser can show it
  const d = LB.detail;
  if (LB.scale > 1.4 && d && !d.video && !LB.hires && NATIVE.has(d.fmt) && Math.max(d.w, d.h) > 2560) {
    LB.hires = true;
    const token = LB.token, full = new Image();
    full.onload = () => { if (token === LB.token) LB.img.src = full.src; };
    full.src = `/orig/${d.id}`;
  }
}
function zoomAt(factor, cx, cy) {
  const { stage } = LB.el, r = stage.getBoundingClientRect();
  const s2 = Math.min(10, Math.max(1, LB.scale * factor));
  const dx = cx - r.left - r.width / 2 - LB.tx, dy = cy - r.top - r.height / 2 - LB.ty;
  LB.tx += dx * (1 - s2 / LB.scale); LB.ty += dy * (1 - s2 / LB.scale);
  LB.scale = s2;
  applyZoom();
}
function initGestures(stage) {
  const pts = new Map();
  let start = null, pinch = 0, moved = false;
  stage.addEventListener('wheel', (e) => {
    if (e.target.closest('.lb-top, .lb-strip')) return;
    e.preventDefault();
    zoomAt(Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0022)), e.clientX, e.clientY);
  }, { passive: false });
  stage.addEventListener('dblclick', (e) => {
    if (e.target.closest('button, a, video')) return;
    LB.scale > 1 ? (LB.scale = 1, applyZoom()) : zoomAt(3, e.clientX, e.clientY);
  });
  stage.addEventListener('pointerdown', (e) => {
    // the face menu lives inside the stage; capturing its pointer would swallow its clicks
    if (e.target.closest('button, a, video, .facebox, .facemenu, .lb-strip')) return;
    pts.set(e.pointerId, e);
    stage.setPointerCapture(e.pointerId);
    moved = false;
    if (pts.size === 1) start = { x: e.clientX, y: e.clientY, tx: LB.tx, ty: LB.ty };
    if (pts.size === 2) { const [a, b] = [...pts.values()]; pinch = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY); }
  });
  stage.addEventListener('pointermove', (e) => {
    if (!pts.has(e.pointerId)) return;
    pts.set(e.pointerId, e);
    if (pts.size === 2) {
      const [a, b] = [...pts.values()];
      const dist = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
      if (pinch) zoomAt(dist / pinch, (a.clientX + b.clientX) / 2, (a.clientY + b.clientY) / 2);
      pinch = dist; moved = true;
    } else if (start && LB.scale > 1) {
      LB.tx = start.tx + e.clientX - start.x; LB.ty = start.ty + e.clientY - start.y;
      moved = true;
      applyZoom();
    }
  });
  const up = (e) => {
    if (!pts.has(e.pointerId)) return;
    pts.delete(e.pointerId);
    if (start && pts.size === 0 && LB.scale === 1 && !moved) {
      const dx = e.clientX - start.x, dy = e.clientY - start.y;
      if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) step(dx < 0 ? 1 : -1);
      else if (dy > 90 && Math.abs(dy) > Math.abs(dx) * 1.5 && e.pointerType === 'touch') closeLightbox(true);
    }
    if (pts.size === 0) { start = null; pinch = 0; }
  };
  stage.addEventListener('pointerup', up);
  stage.addEventListener('pointercancel', up);
}
function toggleInfo() {
  LB.info = !LB.info;
  store.set('info', LB.info ? '1' : '0');
  LB.el.info.hidden = !LB.info;
  LB.el.infoBtn.classList.toggle('on', LB.info);
  if (LB.info) renderInfo();
  sizeFrame();
}
function toggleObjects() {
  LB.objects = !LB.objects;
  LB.el.objectsBtn.classList.toggle('on', LB.objects);
  renderFaces();
}
function toggleFaces() {
  LB.faces = !LB.faces;
  LB.el.facesBtn.classList.toggle('on', LB.faces);
  renderFaces();
}
/** Face regions on the photo (confirmed, suggested, unknown), shown when LB.faces is on; ignored ones are never drawn. */
const faceRegions = (d) => [...d.faces.map((f) => ({ ...f, kind: 'confirmed' })), ...(d.faces_other || [])].filter((f) => f.kind !== 'ignored');
/** Redraw the face and object overlays on the picture from the toggles in LB.faces / LB.objects. */
function renderFaces() {
  const { frame } = LB.el, d = LB.detail;
  frame.querySelectorAll('.facebox').forEach((x) => x.remove());
  if (!d || d.video) return;
  for (const b of LB.objects ? d.boxes || [] : []) {
    frame.append(h('div', { class: 'facebox objbox', style: `left:${b.x * 100}%;top:${b.y * 100}%;width:${b.w * 100}%;height:${b.h * 100}%` }, h('span', null, b.cls)));
  }
  const pct = (f) => `left:${(f.x / d.w) * 100}%;top:${(f.y / d.h) * 100}%;width:${(f.w / d.w) * 100}%;height:${(f.h / d.h) * 100}%`;
  for (const f of LB.faces ? faceRegions(d) : []) {
    const label = f.kind === 'confirmed' ? f.name : f.kind === 'unknown' ? 'Unknown' : f.kind === 'suggested' ? `${f.name}?` : 'Ignored';
    frame.append(h('div', { class: 'facebox face-' + f.kind, style: pct(f), title: label + (CAN_MANAGE ? ' · click for options' : ''),
      onclick: (e) => { e.stopPropagation(); CAN_MANAGE ? faceMenu(e.currentTarget, f, d) : (f.kind === 'confirmed' && filterFromLightbox({ tag: f.tag })); } }, h('span', null, label)));
  }
}
function faceMenu(box, f, d) {
  $('.facemenu')?.remove();
  const rect = () => [f.x, f.y, f.w, f.h];
  const item = (label, fn, danger) => h('div', { class: 'fmi' + (danger ? ' danger' : ''), onclick: (e) => { e.stopPropagation(); menu.remove(); fn(); } }, label);
  const nameIt = () => personPicker((t) => faceOp({ op: 'name', image: d.id, rect: rect(), tag: t.id }));
  const items = f.kind === 'confirmed' ? [
    item(`Show all photos of ${f.name}`, () => filterFromLightbox({ tag: f.tag })),
    d.id !== tagById.get(f.tag)?.icon ? item(`Use as ${f.name}’s badge picture`, () => setTagIcon(tagById.get(f.tag) || { id: f.tag, name: f.name, person: 1 }, d.id)) : null,
    item('This is someone else…', nameIt),
    item('Forget the name (keep as unknown face)', () => faceOp({ op: 'unknown', image: d.id, rect: rect() })),
    item('Not a face to name (ignore)', () => faceOp({ op: 'ignore', image: d.id, rect: rect() })),
    item('Remove this face region', () => { if (confirm(`Remove ${f.name}’s face region from this photo?`)) faceOp({ op: 'remove', image: d.id, rect: rect() }); }, true),
  ] : f.kind === 'suggested' ? [
    item(`Yes, this is ${f.name}`, () => faceOp({ op: 'confirm', image: d.id, rect: rect() })),
    item('No, this is someone else…', nameIt),
    item('Not a face to name (ignore)', () => faceOp({ op: 'ignore', image: d.id, rect: rect() })),
    item('Remove this region', () => faceOp({ op: 'remove', image: d.id, rect: rect() }), true),
  ] : [
    item('Who is this?…', nameIt),
    f.kind !== 'ignored' ? item('Not a face to name (ignore)', () => faceOp({ op: 'ignore', image: d.id, rect: rect() })) : item('Keep as unknown face', () => faceOp({ op: 'unknown', image: d.id, rect: rect() })),
    item('Remove this region', () => faceOp({ op: 'remove', image: d.id, rect: rect() }), true),
  ];
  const menu = h('div', { class: 'facemenu' }, h('div', { class: 'fmh' }, f.kind === 'confirmed' ? f.name : f.kind === 'suggested' ? `Suggestion: ${f.name}` : f.kind === 'unknown' ? 'Unknown face' : 'Ignored face'), items);
  const inPanel = !!box.closest('.lb-info');
  // a menu opened from the info panel is fixed to the viewport, but it has to live inside #lightbox
  // (its own stacking context) or the lightbox paints over it
  const stage = inPanel ? $('#lightbox') : LB.el.stage, sr = inPanel ? { left: 0, top: 0, width: innerWidth, height: innerHeight } : stage.getBoundingClientRect(), br = box.getBoundingClientRect();
  if (inPanel) menu.style.position = 'fixed';
  stage.append(menu);
  const mw = menu.offsetWidth, mh = menu.offsetHeight;
  let left = br.left - sr.left, top = br.bottom - sr.top + 4;
  if (left + mw > sr.width - 8) left = Math.max(8, sr.width - mw - 8);
  if (top + mh > sr.height - 8) top = Math.max(8, br.top - sr.top - mh - 4);
  menu.style.left = left + 'px'; menu.style.top = top + 'px';
  const close = (e) => { if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener('pointerdown', close, true); } };
  setTimeout(() => document.addEventListener('pointerdown', close, true), 0);
}
async function faceOp(op) {
  let r;
  try { r = await post('/api/faces/op', op); } catch (e) { toast(e.message, null, null, 9000); return; }
  toast({ name: `Named ${r.name}.`, confirm: `Confirmed ${r.name}.`, ignore: 'Face ignored.', unknown: 'Name removed; the face stays as unknown.', remove: 'Face region removed.', add: `Added ${r.name}.`, move: 'Region moved.' }[op.op] + (r.sidecar_error ? ` (sidecar not updated: ${r.sidecar_error})` : ''));
  const id = op.image;
  await awaitReindex(() => true, 15, 500);
  details.delete(id);
  if (LB.open && LB.src.id[LB.i] === id) { LB.detail = null; getDetail(id).then((d) => { if (LB.src.id[LB.i] === id) { LB.detail = d; renderFaces(); if (LB.info) renderInfo(); } }); }
}
function personPicker(onPick) {
  // the "People" root carries digiKam's person property too, but it is not someone a face can be named after
  const people = META.tags.filter((t) => t.person && t.full !== 'People' && t.full.split('/')[0] === 'People');
  const inp = h('input', { class: 'pagefilter', style: 'margin:0;width:100%', placeholder: 'Type a name…' });
  const list = h('div', { class: 'alist', style: 'max-height:40vh;margin-top:8px' });
  const families = META.tags.filter((t) => !t.person && t.full.startsWith('People/') && t.full.split('/').length === 2);
  const draw = () => {
    const f = norm(inp.value);
    const hits = people.filter((t) => !f || t._n.includes(f)).sort((a, b) => b.nAll - a.nAll).slice(0, 30);
    fill(list, hits.map((t) => h('div', { class: 'frow', onclick: () => { back.remove(); onPick(t); } }, h('img', { src: faceUrl(t.id), loading: 'lazy', alt: '' }), h('span', { class: 'nm' }, t.name, h('span', { class: 'muted' }, '  ' + t.full.split('/').slice(1, -1).join(' › '))), h('span', { class: 'ct' }, nf.format(t.nAll)))),
      f && !hits.some((t) => t._n === f) ? h('div', { class: 'frow', onclick: () => createPerson(inp.value.trim()) }, icon('add'), h('span', { class: 'nm' }, `New person “${inp.value.trim()}”…`)) : null);
  };
  const createPerson = (name) => {
    const fam = h('select', null, h('option', { value: 0 }, 'directly under People'), families.map((t) => h('option', { value: t.id }, t.name)));
    const sub = modal(`New person “${name}”`, h('div', { class: 'erow' }, h('span', { class: 'el' }, 'Family'), fam),
      h('p', { class: 'muted', style: 'font-size:12.5px' }, 'Created in digiKam’s database as a person tag (digiKam closed, backup first).'),
      h('div', { class: 'modal-btns' }, h('button', { class: 'pillbtn', onclick: () => sub.remove() }, 'Cancel'), h('button', { class: 'pillbtn on', onclick: async () => {
        let r;
        try { r = await post('/api/faces/person', { name, parent: +fam.value || (META.tags.find((t) => t.full === 'People')?.id || 0) }); } catch (e) { toast(e.message, null, null, 9000); return; }
        sub.remove(); back.remove();
        await awaitReindex((m) => m.tags.some((t) => t.id === r.id));
        const t = tagById.get(r.id); if (t) onPick(t); else toast('Person created; it will appear shortly.');
      } }, 'Create')));
  };
  inp.oninput = draw;
  inp.onkeydown = (e) => { e.stopPropagation(); if (e.key === 'Enter') { const f = norm(inp.value); const t = people.find((x) => x._n === f); if (t) { back.remove(); onPick(t); } } };
  const back = modal('Who is this?', inp, list, h('div', { class: 'modal-btns' }, h('button', { class: 'pillbtn', onclick: () => back.remove() }, 'Cancel')));
  draw(); inp.focus();
}
function startDrawFace() {
  const { stage, frame } = LB.el, d = LB.detail;
  if (!d || d.video) return;
  if (!LB.faces) toggleFaces();
  toast('Drag a rectangle around the face.', null, null, 4000);
  const box = h('div', { class: 'facebox face-draw' });
  let start = null;
  const toImg = (e) => { const r = frame.getBoundingClientRect(); return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * d.w, Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)) * d.h]; };
  const down = (e) => { e.preventDefault(); e.stopPropagation(); start = toImg(e); frame.append(box); stage.setPointerCapture(e.pointerId); };
  const move = (e) => { if (!start) return; const p = toImg(e); const x = Math.min(start[0], p[0]), y = Math.min(start[1], p[1]), w = Math.abs(p[0] - start[0]), hh = Math.abs(p[1] - start[1]); box.style.cssText = `left:${x / d.w * 100}%;top:${y / d.h * 100}%;width:${w / d.w * 100}%;height:${hh / d.h * 100}%`; };
  const up = (e) => {
    if (!start) return;
    const p = toImg(e); const x = Math.round(Math.min(start[0], p[0])), y = Math.round(Math.min(start[1], p[1])), w = Math.round(Math.abs(p[0] - start[0])), hh = Math.round(Math.abs(p[1] - start[1]));
    start = null; stop();
    if (w < 8 || hh < 8) { box.remove(); return; }
    personPicker((t) => { box.remove(); faceOp({ op: 'add', image: d.id, rect: [x, y, w, hh], tag: t.id }); });
  };
  const stop = () => { stage.removeEventListener('pointerdown', down, true); stage.removeEventListener('pointermove', move, true); stage.removeEventListener('pointerup', up, true); stage.style.cursor = ''; };
  stage.style.cursor = 'crosshair';
  stage.addEventListener('pointerdown', down, true); stage.addEventListener('pointermove', move, true); stage.addEventListener('pointerup', up, true);
}
async function setTagIcon(t, photoId) {
  if (!confirm(`Use this photo as the ${t.person ? 'badge picture' : 'thumbnail'} for “${t.name}”? This is saved in digiKam’s database (digiKam must be closed; a backup is made first).`)) return;
  await tagOp({ op: 'icon', id: t.id, photo: photoId }, t);
  if (LB.open) { details.delete(LB.src.id[LB.i]); showItem(); }
}
function toggleSlideshow() { LB.play ? stopSlideshow() : (LB.play = setInterval(() => { if (!LB.el.frame.querySelector('video')) step(1); }, 4000), LB.el.playBtn.replaceChildren(icon('pause'))); }
function stopSlideshow() { clearInterval(LB.play); LB.play = 0; LB.el?.playBtn.replaceChildren(icon('play')); }
function filterFromLightbox(obj) {
  closeLightbox(false);
  LB.pushed = false;
  go('photos', photosWith(obj));
}
function renderInfo() {
  const d = LB.detail, el = LB.el.info;
  if (!d) return;
  LB.mini?.remove(); LB.mini = null;
  const lnk = (text, obj) => h('a', { onclick: () => filterFromLightbox(obj) }, text);
  const saveOne = (ch) => editPhotos([d.id], ch);
  const irow = (ic, a, b) => h('div', { class: 'irow' }, icon(ic), h('div', null, h('div', { class: 'a' }, a), b ? h('div', { class: 'b' }, b) : null));
  const exposure = [d.aperture ? `ƒ/${+d.aperture.toFixed(1)}` : null,
    d.exposure ? (d.exposure < 1 ? `1/${Math.round(1 / d.exposure)} s` : `${+d.exposure.toFixed(1)} s`) : null,
    d.focal ? `${+d.focal.toFixed(1)} mm${d.focal35 && Math.round(d.focal35) !== Math.round(d.focal) ? ` (${Math.round(d.focal35)} mm eq.)` : ''}` : null,
    d.iso ? `ISO ${d.iso}` : null, d.flash != null && (d.flash & 1) ? 'Flash' : null].filter(Boolean).join(' · ');
  const mp = d.w * d.h / 1e6;
  const peopleTags = d.tags.filter((t) => t.person), tags = d.tags.filter((t) => !t.person);
  const chip = (t) => h('span', { class: 'ichip', title: t.full.replaceAll('/', ' › '), onclick: () => filterFromLightbox({ tag: t.id }) },
    t.person ? h('img', { src: faceUrl(t.id), alt: '' }) : null, t.name,
    CAN_MANAGE && d.id !== tagById.get(t.id)?.icon ? h('button', { class: 'tx', title: t.person ? `Use this photo as ${t.name}’s badge picture (digiKam must be closed)` : `Use this photo as the thumbnail for “${t.name}” (digiKam must be closed)`,
      onclick: (e) => { e.stopPropagation(); setTagIcon(t, d.id); } }, icon('photo')) : null);
  const stars = d.rating > 0 ? '★'.repeat(d.rating) + '☆'.repeat(5 - d.rating) : null;
  const ex = d.extra || {}, cr = ex.copyright || {}, vid = ex.video || {};
  const kv = [];
  const addKv = (k, v) => { if (v != null && v !== '') kv.push(h('span', null, k), h('span', null, v)); };
  if (!EDITING) addKv('Rating', stars);
  if (d.creator) kv.push(h('span', null, 'Creator'), h('span', null, lnk(d.creator, { creator: d.creator })));
  if (EDITING) kv.push(h('span', null, 'Template'), h('span', null, h('a', { class: 'lnk', onclick: () => templatePicker([d.id]) }, 'Apply a metadata template…')));
  addKv('Copyright', d.copyright);
  for (const [k, v] of Object.entries(cr)) if (!['creator', 'copyrightNotice'].includes(k)) addKv(k.replace('creatorContactInfo.', '').replace(/([A-Z])/g, ' $1').toLowerCase(), v);
  for (const [k, v] of Object.entries(ex.properties || {})) addKv(k, v);
  if (d.video) { addKv('Duration', d.duration ? fmtDur(d.duration) : null); addKv('Video codec', vid.codec); addKv('Frame rate', vid.fps ? `${+(+vid.fps).toFixed(2)} fps` : null); addKv('Audio', vid.audio); }
  addKv('File modified', d.modified?.replace('T', ' '));
  const mapEl = d.lat != null ? h('div', { class: 'imap' }) : null;
  fill(el,
    h('div', { class: 'ihead' }, h('button', { class: 'iconbtn', title: 'Close info', onclick: toggleInfo }, icon('close')), 'Info'),
    d.title ? h('div', { class: 'title' }, d.title) : null,
    d.caption_ai ? h('div', { class: 'muted', style: 'margin:4px 0 8px;font-style:italic' }, d.caption_ai.charAt(0).toUpperCase() + d.caption_ai.slice(1), h('span', { style: 'font-style:normal;font-size:11px;opacity:.7' }, ' · AI description')) : null,
    d.caption ? h('div', { class: 'muted', style: 'margin:6px 0 10px;white-space:pre-wrap' }, d.caption) : null,
    irow('calendar', lnk(dfLong.format(date(d.ts)), { from: d.day, to: d.day, sort: 'old' }), [dfTime.format(date(d.ts)), EDITING ? [' · ', h('a', { class: 'lnk', onclick: (e) => { const box = e.target.closest('.irow').nextSibling; box.hidden = !box.hidden; } }, 'change')] : null]),
    EDITING ? h('div', { hidden: true, style: 'margin:0 0 8px 40px' }, dateEditor([d.id], d.taken)) : null,
    irow(d.video ? 'video' : 'photo', d.name, [d.video ? null : `${mp >= 1 ? mp.toFixed(1) : mp.toFixed(2)} MP`, `${d.w} × ${d.h}`, fmtBytes(d.size), d.fmt].filter(Boolean).join(' · ')),
    d.album ? irow('folder', lnk(d.album.path.replace(/^\//, '') || d.album.name, { album: d.album.id, sort: 'old' }), 'Album') : null,
    d.camera || exposure ? irow('camera', d.camera ? lnk(d.camera, { camera: d.camera }) : 'Unknown camera',
      [d.lens ? lnk(d.lens, { lens: d.lens }) : null, d.lens && exposure ? h('br') : null, exposure]) : null,
    EDITING ? [h('h4', null, 'Edit'),
      editControls({ rating: Math.max(d.rating, 0) }, saveOne),
      h('input', { class: 'einput', placeholder: 'Title', value: d.title || '', onkeydown: (e) => { e.stopPropagation(); if (e.key === 'Enter') e.target.blur(); },
        onchange: (e) => saveOne({ title: e.target.value }) }),
      h('textarea', { class: 'einput', placeholder: 'Caption', rows: 2, onkeydown: (e) => e.stopPropagation(), onchange: (e) => saveOne({ caption: e.target.value }) }, d.caption || ''),
      d.edited ? h('div', { class: 'enote' }, WRITE_FILES ? 'Changed here and saved to the sidecar and the image file. ' : 'Changed here and saved to the sidecar. ', 'digiKam shows it after “Reread Metadata From File”, or apply it to digiKam’s database from Explore. ',
        h('a', { class: 'lnk', onclick: async () => { try { await post('/api/edit/revert', { ids: [d.id] }); } catch (e) { toast(e.message); return; } details.delete(d.id); toast('Viewer edits undone; sidecar restored.'); keepView = true; clearTimeout(pollTimer); pollTimer = setTimeout(async () => { await pollStatus(); if (LB.open && LB.src.id[LB.i] === d.id) showItem(); }, 1500); } }, 'Undo')) : null] : null,
    // one row per face (named, suggested, unknown); a person tag without a face region gets a row with the badge picture
    (() => {
      const faced = new Set(d.faces.map((f) => f.tag));
      const rows = [...faceRegions(d),
        ...peopleTags.filter((t) => !faced.has(t.id)).map((t) => ({ kind: 'tagonly', tag: t.id, name: t.name }))];
      if (!rows.length) return null;
      return [h('h4', null, 'People'), h('div', { class: 'facerows' }, rows.map((f) => h('div', { class: 'facerow', title: f.kind === 'confirmed' || f.kind === 'tagonly' ? (CAN_MANAGE ? 'Options for this face' : `Show all photos of ${f.name}`) : 'Show the face on the photo',
        onclick: (e) => {
          if (f.kind !== 'tagonly' && !LB.faces) toggleFaces();
          if (CAN_MANAGE && f.kind !== 'tagonly') faceMenu(e.currentTarget, f, d);
          else if (f.kind === 'confirmed' || f.kind === 'tagonly') filterFromLightbox({ tag: f.tag });
        } },
        h('img', { src: f.kind === 'tagonly' ? faceUrl(f.tag) : `/facecrop/${d.id}/${f.x}/${f.y}/${f.w}/${f.h}.jpg`, alt: '' }),
        h('span', { class: 'nm' }, f.kind === 'confirmed' || f.kind === 'tagonly' ? f.name : f.kind === 'suggested' ? [h('i', null, 'Suggestion: '), f.name] : h('i', null, 'Unknown face')),
        CAN_MANAGE && f.kind !== 'tagonly' ? h('span', { class: 'muted', style: 'font-size:12px' }, 'options ▾') : null)))];
    })(),
    tags.length || EDITING ? [h('h4', null, 'Tags'), h('div', { class: 'ichips' }, tags.map((t) => { const c = chip(t);
      if (EDITING) c.append(h('button', { class: 'tx', title: 'Remove this tag', onclick: (e) => { e.stopPropagation(); saveOne({ remove_tags: [t.id] }); } }, icon('close'))); return c; })),
      EDITING ? h('div', { style: 'margin-top:8px' }, tagPicker((t) => saveOne({ add_tags: [t.id] }))) : null] : null,
    d.sharpn != null || d.burst || d.ocr ? [h('h4', null, 'Analysis'),
      d.sharpn != null ? h('div', { class: 'irow' }, icon('spark'), h('div', null, h('div', { class: 'a' }, `Sharper than ${Math.round(d.sharpn * 100)}% of your photos`),
        h('div', { class: 'b' }, [d.faceq != null ? `Face quality ${Math.round(d.faceq * 100)} / 100` : null, d.bright != null && (d.bright < 0.2 || d.clip_lo > 0.5) ? 'Very dark' : null,
          d.bright != null && (d.bright > 0.8 || d.clip_hi > 0.3) ? 'Very bright' : null].filter(Boolean).join(' · ')))) : null,
      d.burst ? h('div', { class: 'irow' }, icon('dup'), h('div', null, h('div', { class: 'a' }, lnk(`Part of a burst of ${d.burst_size} frames`, { burst: d.burst, sort: 'old' })),
        h('div', { class: 'b' }, d.burst_best ? 'Picked as the best frame' : ['Not the best frame', d.burst_best_id ? [' · ', h('a', { class: 'lnk', title: d.burst_best_name, onclick: () => { const i = LB.src.id.indexOf(d.burst_best_id); if (i >= 0) { LB.i = i; setPhotoParam(d.burst_best_id, false); showItem(); } else openLightbox({ id: [d.burst_best_id] }, 0, true); } }, 'open the best frame')] : null]))) : null,
      d.ocr ? h('div', { class: 'irow' }, icon('text'), h('div', null, h('div', { class: 'b' }, 'Text in the picture'), h('div', { class: 'a', style: 'font-size:12.5px' }, d.ocr.slice(0, 600).split(/\n+/).map((t) => t.trim()).filter(Boolean).join(' · ')))) : null] : null,
    d.boxes?.length ? [h('h4', null, 'Objects'), h('div', { class: 'ichips' }, [...new Set(d.boxes.map((b) => b.cls))].map((c) => h('span', { class: 'ichip', onclick: () => filterFromLightbox({ obj: c }) },
      c, h('b', { style: 'font-weight:400;color:var(--fg2)' }, d.boxes.filter((b) => b.cls === c).length > 1 ? ` ×${d.boxes.filter((b) => b.cls === c).length}` : ''))))] : null,
    d.concepts?.length ? [h('h4', null, 'Detected'), h('div', { class: 'ichips' }, d.concepts.map((c) => h('span', { class: 'ichip', title: `The model’s guess (${Math.round(c.p * 100)}% of its vote)`, onclick: () => filterFromLightbox({ concept: c.name }) }, icon('spark'), c.name)))] : null,
    d.similar && !d.video ? h('div', { class: 'irow' }, icon('spark'), h('div', null, h('div', { class: 'a' }, lnk('More photos like this', { like: d.id })))) : null,
    EDITING && d.lat == null ? h('div', { class: 'irow' }, icon('place'), h('div', null, h('a', { class: 'lnk', onclick: () => locationDialog([d.id], null) }, 'Set location on the map'))) : null,
    d.lat != null ? [h('h4', null, 'Location', EDITING ? h('a', { class: 'lnk', style: 'margin-left:10px;text-transform:none;letter-spacing:0;font-weight:400', onclick: () => locationDialog([d.id], { lat: d.lat, lon: d.lon, alt: d.alt }) }, 'change') : null),
      d.place ? h('div', { class: 'a', style: 'margin-bottom:6px' }, lnk(d.place, { place: d.place, ...(d.region ? { region: d.region } : {}) }),
        d.region ? [', ', lnk(d.region, { region: d.region })] : null, d.country ? [', ', lnk(d.country, { country: d.country })] : null) : null,
      mapEl,
      h('div', { class: 'irow' }, icon('place'), h('div', null, h('div', { class: 'a' }, `${d.lat.toFixed(5)}, ${d.lon.toFixed(5)}`),
        h('div', { class: 'b' }, d.alt != null && d.alt !== 0 ? `${Math.round(d.alt)} m altitude · ` : null, ex.orientationGps != null ? `facing ${Math.round(ex.orientationGps)}° · ` : null,
          h('a', { class: 'lnk', onclick: () => go('map', photosWith({ from: d.day, to: d.day, trail: d.day })) }, 'Day’s trail'), ' · ',
          lnk('Photos nearby', { bbox: [d.lat - 0.01, d.lon - 0.015, d.lat + 0.01, d.lon + 0.015].map((x) => x.toFixed(4)).join(',') }), ' · ',
          h('a', { href: mapLink(d.lat, d.lon), target: '_blank', rel: 'noopener' }, MAPS.linkLabel))))] : null,
    kv.length ? [h('h4', null, 'Details'), h('div', { class: 'kv' }, kv)] : null,
    h('h4', null, 'File'),
    h('div', { class: 'b muted', style: 'word-break:break-all;user-select:all;font-size:12.5px' }, d.path));
  if (mapEl) {
    const token = LB.token;
    loadLeaflet(false).then(async () => {
      if (token !== LB.token || !mapEl.isConnected) return;
      const L = window.L;
      await loadMaps();
      if (token !== LB.token || !mapEl.isConnected) return;
      LB.mini = L.map(mapEl, { zoomControl: false, attributionControl: false, scrollWheelZoom: false }).setView([d.lat, d.lon], 13);
      tiles().addTo(LB.mini);
      L.marker([d.lat, d.lon], { icon: L.divIcon({ className: '', html: '<div class="pm"></div>', iconSize: [14, 14], iconAnchor: [7, 7] }) }).addTo(LB.mini);
    }).catch(() => { mapEl.remove(); });
  }
}

document.addEventListener('keydown', (e) => {
  if (e.target.matches('input, select, textarea') || e.metaKey || e.ctrlKey || e.altKey) return;
  if (LB.open) {
    if (e.key === 'Escape') closeLightbox(true);
    else if (e.key === 'ArrowRight') step(1);
    else if (e.key === 'ArrowLeft') step(-1);
    else if (e.key === 'i' || e.key === 'I') toggleInfo();
    else if (e.key === 'f' || e.key === 'F') toggleFaces();
    else if (e.key === 'o' || e.key === 'O') toggleObjects();
    else if (e.key === 'd' || e.key === 'D') LB.el.dl.click();
    else if (e.key === 'l' || e.key === 'L') LB.el.favBtn.click();
    else if (EDITING && /^[0-5]$/.test(e.key)) editPhotos([LB.src.id[LB.i]], { rating: +e.key });
    else if (e.key === ' ') { const v = LB.el.frame.querySelector('video'); v ? (v.paused ? v.play() : v.pause()) : toggleSlideshow(); }
    else return;
    e.preventDefault();
  } else if (e.key === '/') { $('#q').focus(); e.preventDefault(); }
  else if (e.key === 'Escape' && G.sel.size) clearSelection();
});

// ---------------------------------------------------------------- startup
let placeRows = [];  // search suggestions for towns, regions and countries, with their photo counts
function indexMeta(meta) {
  META = meta;
  tagById = new Map(meta.tags.map((t) => [t.id, t]));
  albumById = new Map(meta.albums.map((a) => [a.id, a]));
  for (const t of meta.tags) { t._n = norm(t.full.replaceAll('/', ' ')); if (t.pid != null && tagById.has(t.pid)) tagById.get(t.pid).hasKids = true; }
  for (const a of meta.albums) a._n = norm(a.path);
  const rows = new Map();
  for (const [city, region, country, n] of meta.places) {
    for (const [key, name, sub] of [['place', city, [region, country].filter(Boolean).join(', ')], ['region', region, country], ['country', country, '']]) {
      if (!name) continue;
      const r = rows.get(key + name) || rows.set(key + name, { key, name, sub, n: 0, _n: norm(name) }).get(key + name);
      r.n += n;
    }
  }
  placeRows = [...rows.values()];
}
/**
 * After a change to digiKam's database, wait for the server to rebuild its index and load the new metadata.
 * `until` can demand more than a version bump (e.g. that a new tag is present). Returns whether it happened.
 */
async function awaitReindex(until = () => true, tries = 20, ms = 400) {
  let seen = META.version;
  for (let i = 0; i < tries; i++) {
    await sleep(ms);
    try {
      const s = await api('/api/status');
      if (s.version === seen) continue;
      seen = s.version;
      const m = await api('/api/meta');
      if (until(m)) { indexMeta(m); return true; }
    } catch { /* retry */ }
  }
  return false;
}
async function pollStatus() {
  let delay = 20000;
  try {
    const s = await api('/api/status');
    const el = $('#status');
    const progress = (label, p, ms) => { el.replaceChildren(label, h('br'), `${nf.format(p.done)} / ${nf.format(p.total)}`, h('div', { class: 'bar' }, h('i', { style: `width:${(100 * p.done / p.total).toFixed(1)}%` }))); delay = ms; };
    el.replaceChildren();
    if (s.thumbs.running && s.thumbs.total) progress('Preparing thumbnails', s.thumbs, 3000);
    else if (s.semantic.running && s.semantic.total) progress('Learning photo content', s.semantic, 4000);
    const an = s.analysis || {};
    for (const [key, label] of [['quality', 'Scoring sharpness'], ['vision', 'Reading text in photos'], ['objects', 'Finding objects'], ['captions', 'Describing photos']]) {
      if (an[key]?.running && an[key].total && !el.childNodes.length) progress(label, an[key], 5000);
    }
    if (s.tagJobs.pending) {
      el.replaceChildren('Updating tag in sidecars', h('br'), `${nf.format(s.tagJobs.pending)} left`);
      delay = 3000;
    }
    if (s.app && APP_STAMP && s.app !== APP_STAMP && !LB.open && !G.sel.size) { location.reload(); return; }  // the viewer was updated: use the new version
    if (s.app) APP_STAMP = s.app;
    SEM = s.semantic; EDITING = s.editing; PENDING = s.pendingEdits; WRITE_FILES = s.writeFiles; CAN_MANAGE = s.editing && s.dbWrite;
    IS_ADMIN = s.isAdmin; SIGNED_IN = s.signedIn; USERS_EXIST = s.usersExist; DIGIKAM_CHECK = s.digikamCheck || 'pgrep';
    if (s.appVersion) { APP_VERSION = s.appVersion; APP_COMMIT = s.commit || ''; const b = $('.brand'); if (b) b.title = `digiKam Viewer v${APP_VERSION}${APP_COMMIT ? ' (' + APP_COMMIT + ')' : ''}`; } if ((s.user && s.user.id) !== (USER && USER.id)) { USER = s.user; renderUserMenu(); }
    document.body.classList.toggle('noadmin', !IS_ADMIN);
    if (PENDING && s.dbWrite && !el.childNodes.length) el.replaceChildren(h('a', { class: 'lnk', style: 'cursor:pointer', title: 'Edits saved in sidecars that digiKam’s database does not have yet', onclick: dbDialog },
      `${nf.format(PENDING)} ${PENDING === 1 ? 'edit' : 'edits'} not in digiKam yet`));
    if (s.rev !== ST.rev && ST.rev >= 0) { const mine = ST.rev; await loadState(); if (mine !== ST.rev && route.view === 'albums') showAlbums(); }
    if (META && s.version && s.version !== META.version) {
      indexMeta(await api('/api/meta'));
      details.clear();
      if (!LB.open) { const quiet = keepView; if (!quiet) keepView = route.view === 'photos'; viewKey = null; onRoute(); if (!quiet) toast('Library updated from digiKam.'); }
      else viewKey = null;
    }
  } catch { /* server restarting */ }
  pollSoon(delay);
}
async function start() {
  await loadUser();
  $('#nav').replaceChildren(...NAV.map(([v, label, ic, href]) => h('a', { href: href || `#/${v}`, 'data-v': v }, icon(ic), label)), h('div', { id: 'status' }));
  initSearch();
  applyBadgePref(); applyTheme();
  if (REQUIRE_LOGIN && !USER) { document.body.classList.add('locked'); loginDialog(true); return; }  // boot() runs after sign-in
  await boot();
}
/** Load the library and show the first view; once per page load, after sign-in when that is required. */
async function boot() {
  BOOTED = true; document.body.classList.remove('locked');
  try { indexMeta(await api('/api/meta')); await loadState(); } catch (e) { main.replaceChildren(h('div', { class: 'empty' }, 'Could not reach the server: ' + e.message)); return; }
  if (store.get('filters', '0') === '1' && innerWidth >= 1100) toggleFilters(true);
  await pollStatus();
  onRoute();
}
start();
