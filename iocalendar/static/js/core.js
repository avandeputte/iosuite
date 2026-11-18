import { drawNav, showSignIn } from './shell.js';
import { route } from './main.js';
import { drawView } from './views.js';
import { client, h } from '../../api/auth/ui.js';  // the suite's shared helpers (iosuite-shared static/account-panel.js)
export { h };
export const api = client(document.baseURI, { signIn: () => showSignIn() });

// The helpers every page uses (api, h, icon), dates and repeat rules, and the app's state.

// ------------------------------------------------------------------ helpers
export const $ = (s, el = document) => el.querySelector(s);
/** replaceChildren that leaves out null and false (as h() does) and flattens lists. */
export const fill = (el, ...kids) => el.replaceChildren(...kids.flat(9).filter((k) => k != null && k !== false));
export const ICONS = {
  today: 'M19 3h-1V1h-2v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM7 10h5v5H7z',
  agenda: 'M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z',
  chevL: 'M15.41 7.41 14 6l-6 6 6 6 1.41-1.41L10.83 12z',
  chevR: 'M10 6 8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z',
  clock: 'M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z',
  money: 'M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z',
  repeat: 'M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z',
  bell: 'M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z',
  dup: 'M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z',
  globe: 'M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zm6.93 6h-2.95a15.65 15.65 0 0 0-1.38-3.56A8.03 8.03 0 0 1 18.92 8zM12 4.04c.83 1.2 1.48 2.53 1.91 3.96h-3.82c.43-1.43 1.08-2.76 1.91-3.96zM4.26 14C4.1 13.36 4 12.69 4 12s.1-1.36.26-2h3.38c-.08.66-.14 1.32-.14 2s.06 1.34.14 2H4.26zm.82 2h2.95c.32 1.25.78 2.45 1.38 3.56A7.987 7.987 0 0 1 5.08 16zm2.95-8H5.08a7.987 7.987 0 0 1 4.33-3.56A15.65 15.65 0 0 0 8.03 8zM12 19.96c-.83-1.2-1.48-2.53-1.91-3.96h3.82c-.43 1.43-1.08 2.76-1.91 3.96zM14.34 14H9.66c-.09-.66-.16-1.32-.16-2s.07-1.35.16-2h4.68c.09.65.16 1.32.16 2s-.07 1.34-.16 2zm.25 5.56c.6-1.11 1.06-2.31 1.38-3.56h2.95a8.03 8.03 0 0 1-4.33 3.56zM16.36 14c.08-.66.14-1.32.14-2s-.06-1.34-.14-2h3.38c.16.64.26 1.31.26 2s-.1 1.36-.26 2h-3.38z',
  contacts: 'M20 0H4v2h16V0zM4 24h16v-2H4v2zM20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm-8 2.75c1.24 0 2.25 1.01 2.25 2.25s-1.01 2.25-2.25 2.25S9.75 10.24 9.75 9 10.76 6.75 12 6.75zM17 17H7v-1.5c0-1.67 3.33-2.5 5-2.5s5 .83 5 2.5V17z',
  menuOpen: 'M3 18h13v-2H3v2zm0-5h10v-2H3v2zm0-7v2h13V6H3zm18 9.59L17.42 12 21 8.41 19.59 7l-5 5 5 5L21 15.59z',
  pin: 'M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H7c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1 1 1-1v-7H19v-2c-1.66 0-3-1.34-3-3z',
  menu: 'M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z',
  search: 'M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z',
  add: 'M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z',
  person: 'M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z',
  people: 'M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z',
  star: 'M12 17.27 18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z',
  place: 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z',
  link: 'M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z',
  upload: 'M9 16h6v-6h4l-7-7-7 7h4zm-4 2h14v2H5z',
  download: 'M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z',
  settings: 'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z',
  edit: 'M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a.996.996 0 0 0 0-1.41l-2.34-2.34a.996.996 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z',
  delete: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z',
  close: 'M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z',
  back: 'M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z',
  event: 'M17 12h-5v5h5v-5zM16 1v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2h-1V1h-2zm3 18H5V8h14v11z',
  logout: 'M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z',
  copy: 'M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z',
  open: 'M19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z',
  note: 'M3 18h12v-2H3v2zM3 6v2h18V6H3zm0 7h18v-2H3v2z',
  devices: 'M4 6h18V4H4c-1.1 0-2 .9-2 2v11H0v3h14v-3H4V6zm19 2h-6c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h6c.55 0 1-.45 1-1V9c0-.55-.45-1-1-1zm-1 9h-4v-7h4v7z',
  more: 'M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z',
  check: 'M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z',
  tune: 'M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 4v-2H11v2h10zm-6-4h2V7h4V5h-4V3h-2v6z',
  ai: 'M19 9l1.25-2.75L23 5l-2.75-1.25L19 1l-1.25 2.75L15 5l2.75 1.25L19 9zm-7.5.5L9 4 6.5 9.5 1 12l5.5 2.5L9 20l2.5-5.5L17 12l-5.5-2.5zM19 15l-1.25 2.75L15 19l2.75 1.25L19 23l1.25-2.75L23 19l-2.75-1.25L19 15z',
  server: 'M20 13H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1v-6c0-.55-.45-1-1-1zM7 19c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zM20 3H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1V4c0-.55-.45-1-1-1zM7 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z',
  theme: 'M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.389 5.389 0 0 1-4.4 2.26 5.403 5.403 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z',
  select: 'M3 5h2V3c-1.1 0-2 .9-2 2zm0 8h2v-2H3v2zm4 8h2v-2H7v2zM3 9h2V7H3v2zm10-6h-2v2h2V3zm6 0v2h2c0-1.1-.9-2-2-2zM5 21v-2H3c0 1.1.9 2 2 2zm-2-4h2v-2H3v2zM9 3H7v2h2V3zm2 18h2v-2h-2v2zm8-8h2v-2h-2v2zm0 8c1.1 0 2-.9 2-2h-2v2zm0-12h2V7h-2v2zm0 8h2v-2h-2v2zm-4 4h2v-2h-2v2zm0-16h2V3h-2v2zM7 17h10V7H7v10zm2-8h6v6H9V9z',
};
export const icon = (n, cls = '') => { const s = document.createElement('span'); s.className = 'ic ' + cls; s.innerHTML = `<svg viewBox="0 0 24 24"><path d="${ICONS[n] || ''}"/></svg>`; return s; };

export let toastTimer;
export function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 3500);
}
export const fail = (e) => toast(e.message || String(e));

export function dialog(title, body, buttons) {
  return new Promise((resolve) => {
    const back = h('div', { class: 'dialog-back' });
    const close = (v) => { back.remove(); resolve(v); };
    back.addEventListener('click', (e) => { if (e.target === back) close(null); });
    const btns = (buttons || [{ label: 'OK', value: true, primary: true }]).map((b) =>
      h('button', { class: `pillbtn noic ${b.primary ? 'primary' : ''} ${b.danger ? 'danger' : ''}`, onclick: () => close(typeof b.value === 'function' ? b.value() : b.value) }, b.label));
    back.append(h('div', { class: 'dialog', role: 'dialog' }, h('h2', null, title), body, h('div', { class: 'btns' }, btns)));
    document.body.append(back);
    const f = back.querySelector('input,select,textarea'); if (f) f.focus();
  });
}
export const confirmDialog = (title, text, ok = 'OK', danger = false) => dialog(title, h('p', null, text), [{ label: 'Cancel', value: false }, { label: ok, value: true, primary: !danger, danger }]);

export const hue = (s) => { let x = 0; for (const c of s || '') x = (x * 31 + c.charCodeAt(0)) % 360; return x; };
export const initials = (fn) => { const p = (fn || '?').trim().split(/\s+/); return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase(); };
export async function copyText(t) { try { await navigator.clipboard.writeText(t); toast('Copied'); } catch { toast(t); } }
export const copyRow = (v) => h('div', { class: 'copy' }, h('code', null, v), h('button', { class: 'iconbtn', title: 'Copy', onclick: () => copyText(v) }, icon('copy', 's')));

// ------------------------------------------------------------------ dates
export const pad2 = (n) => String(n).padStart(2, '0');
export const ymd = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
export const parseDay = (s) => { const [y, m, d] = s.slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d); };
export const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
export const addMonths = (d, n) => { const x = new Date(d.getFullYear(), d.getMonth() + n, 1); x.setDate(Math.min(d.getDate(), new Date(x.getFullYear(), x.getMonth() + 1, 0).getDate())); return x; };
export const sameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
export const dayStart = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
export const weekStart = () => (S.settings.weekStart ?? 1);
export const startOfWeek = (d) => { const x = dayStart(d); const diff = (x.getDay() - weekStart() + 7) % 7; return addDays(x, -diff); };
export const fmtTime = (d) => d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
export const fmtDay = (d, opts = { weekday: 'long', month: 'long', day: 'numeric' }) => d.toLocaleDateString([], opts);
export const LOCAL_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
export const DOW = (i, style = 'short') => new Date(2026, 1, 1 + i).toLocaleDateString([], { weekday: style }); // 1 Feb 2026 is a Sunday
export const RDAY = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'];
/** An occurrence's start and end as Dates (all-day: local midnights; the end is the day after the last day). */
export function span(o) {
  if (o.allDay) return [parseDay(o.start), parseDay(o.end)];
  return [new Date(o.start), new Date(o.end)];
}
export const ordinal = (n) => ({ 1: 'first', 2: 'second', 3: 'third', 4: 'fourth', 5: 'fifth', '-1': 'last' })[n] || `${n}th`;

/** A repeat rule (RRULE) in words. */
export function describeRule(rule, startDay) {
  if (!rule) return '';
  const p = Object.fromEntries(rule.split(';').map((x) => x.split('=')));
  const n = +(p.INTERVAL || 1);
  const unit = { DAILY: 'day', WEEKLY: 'week', MONTHLY: 'month', YEARLY: 'year' }[p.FREQ] || p.FREQ.toLowerCase();
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
    else if (startDay) s += ` on day ${startDay.getDate()}`;
  }
  if (p.FREQ === 'YEARLY' && startDay && !p.BYMONTH) s += ` on ${startDay.toLocaleDateString([], { month: 'long', day: 'numeric' })}`;
  if (p.COUNT) s += `, ${p.COUNT} times`;
  if (p.UNTIL) { const u = p.UNTIL; s += `, until ${parseDay(`${u.slice(0, 4)}-${u.slice(4, 6)}-${u.slice(6, 8)}`).toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' })}`; }
  return s;
}
export function describeReminder(m, allDay) {
  if (allDay && m % 60 === 0 && m !== 0 && Math.abs(m) <= 40320) {
    // relative to midnight: -540 = on the day at 9:00, 900 = the day before at 9:00
    const days = Math.ceil(m / 1440), mins = days * 1440 - m;
    const at = new Date(2026, 0, 1, Math.floor(mins / 60), mins % 60);
    if (mins >= 0 && mins < 1440) return `${days === 0 ? 'On the day' : days === 1 ? 'The day before' : days === 7 ? 'A week before' : `${days} days before`} at ${fmtTime(at)}`;
  }
  if (m === 0) return 'At the start';
  if (m < 0) return `${-m} minutes after the start`;
  if (m % 10080 === 0) return `${m / 10080} week${m > 10080 ? 's' : ''} before`;
  if (m % 1440 === 0) return `${m / 1440} day${m > 1440 ? 's' : ''} before`;
  if (m % 60 === 0) return `${m / 60} hour${m > 60 ? 's' : ''} before`;
  return `${m} minutes before`;
}
export function whenText(o) {
  const [s, e] = span(o);
  if (o.allDay) {
    const last = addDays(e, -1);
    return sameDay(s, last) ? fmtDay(s) : `${fmtDay(s, { weekday: 'short', month: 'short', day: 'numeric' })} – ${fmtDay(last, { weekday: 'short', month: 'short', day: 'numeric', year: last.getFullYear() !== s.getFullYear() ? 'numeric' : undefined })}`;
  }
  if (sameDay(s, e) || (e - s <= 86400000 && e.getHours() === 0 && e.getMinutes() === 0 && sameDay(addDays(s, 1), e))) return `${fmtDay(s)} · ${fmtTime(s)} – ${fmtTime(e)}`;
  return `${fmtDay(s, { weekday: 'short', month: 'short', day: 'numeric' })} ${fmtTime(s)} – ${fmtDay(e, { weekday: 'short', month: 'short', day: 'numeric' })} ${fmtTime(e)}`;
}

// ------------------------------------------------------------------ state
// the suite's roles, each able to do what the one before can: a viewer only looks, a member keeps their own calendars,
// an editor changes the shared ones too
export const RANK = { none: 0, viewer: 1, member: 2, editor: 3, admin: 4 };
export const roleAtLeast = (r) => (RANK[S.user && S.user.role] || 0) >= RANK[r];
export const canOwn = () => roleAtLeast('member');
export const canShared = () => roleAtLeast('editor');
export const S = { status: {}, user: null, suite: [], settings: {}, cals: [], hidden: new Set(), members: [], who: new Set(), view: 'month', date: dayStart(new Date()), occ: [], q: '', mini: null, editing: null, tasks: { items: [] }, bills: { items: [] }, papers: { items: [] } };
export const calOf = (id) => S.cals.find((c) => c.id === id) || {};
export const colorOf = (id) => calOf(id).color || 'var(--brand)';
export const writable = () => S.cals.filter((c) => c.writable);
export const shownCals = () => S.cals.filter((c) => !S.hidden.has(c.id));
/** Filled by the server (Birthdays from ioContact, public Holidays, outside calendars subscribed by address): nobody changes their events here. */
export const AUTO_KINDS = ['birthdays', 'holidays', 'subscribed'];
/** How often an outside calendar may be fetched again, in hours, and how each choice reads. */
export const REFRESH_HOURS = [[1, 'Every hour'], [3, 'Every 3 hours'], [6, 'Every 6 hours'], [12, 'Twice a day'], [24, 'Once a day'], [168, 'Once a week']];
export const isAuto = (c) => AUTO_KINDS.includes(c.kind);
export const memberOf = (id) => S.members.find((m) => m.id === id);
/** Each family member's colour, initials and face are the suite's (Settings › Security › Family), the same in every io app. */
export const memberColor = (m) => m.color || '#5f6b7a';
/** A member's badge: their initials on their colour; `face`: their face (ioPix, else their ioContact card) when they have one. */
export const memberBadge = (m, face = false) => h('span', { class: `mem${face && m.hasFace ? ' face' : ''}`, title: m.displayName, style: { '--mc': memberColor(m) } }, m.initials || initials(m.displayName),
  face && m.hasFace ? h('img', { src: `api/auth/family/${m.id}/face`, alt: '', loading: 'lazy', onerror: (e) => { e.currentTarget.parentNode.classList.remove('face'); e.currentTarget.remove(); } }) : null);
/** With family members picked in the sidebar: only the events tagged with one of them (holidays, birthdays and outside calendars stay). */
export const passesWho = (o) => !S.who.size || isAuto(calOf(o.calendarId)) || (o.members || []).some((id) => S.who.has(id));

// tasks from ioTask, when it is part of the suite: each on the day it is due, ticked off from here
export const tasksOn = () => !!S.status.iotask && S.settings.hideTasks !== '1';
/** A task as the views take an occurrence: on its due day (half an hour from its time, when it has one). */
export function taskOcc(t) {
  if (t.allDay) return { ...t, task: true, start: t.due.slice(0, 10), end: ymd(addDays(parseDay(t.due), 1)) };
  return { ...t, task: true, start: t.due, end: new Date(+new Date(t.due) + 30 * 6e4).toISOString() };
}
export function toggleTasks() {
  saveSettings({ hideTasks: tasksOn() ? '1' : '' });
  drawNav();
  if (['month', 'week', 'day', 'agenda'].includes(route().view)) drawView();
}
export function openTask(o) { if (S.tasks.url) window.open(`${S.tasks.url}/#/task/${o.id}`, '_blank', 'noopener'); }
export function tickBtn(o) {
  const b = h('button', { class: `tk ${o.done ? 'on' : ''}`, disabled: !o.writable, 'aria-label': o.done ? 'Not done after all' : 'Done',
    title: !o.writable ? 'You can see this task but not change it' : o.done ? 'Not done after all' : 'Done',
    onclick: (ev) => { ev.stopPropagation(); tickTask(o); } });
  b.innerHTML = `<svg viewBox="0 0 24 24"><path d="${ICONS.check}"/></svg>`;
  return b;
}
export async function tickTask(o) {
  try {
    const r = await api(`api/tasks/${o.id}/complete`, { method: 'POST', json: { done: !o.done, tz: LOCAL_TZ } });
    const next = r.moved && r.due ? fmtDay(r.allDay ? parseDay(r.due) : new Date(r.due), { weekday: 'short', month: 'short', day: 'numeric' }) : null;
    toast(next ? `Done. It comes back on ${next}` : r.done ? 'Done' : 'Open again');
  } catch (e) { fail(e); }
  if (['month', 'week', 'day', 'agenda'].includes(route().view)) drawView();
}
// the household's coming bills from ioMoney (its recurring transactions), for those with a role there
export const billsOn = () => !!S.status.iomoney && S.settings.hideBills !== '1';
/** ioMoney did answer this person (a role there): the sidebar offers the bills, and remembers why they are away. */
export const billsOffered = () => !!S.status.iomoney && !/not part of the suite|No role/.test(S.bills.reason || '');
export const billOcc = (b) => ({ ...b, bill: true, allDay: true, title: b.merchant, start: b.day, end: ymd(addDays(parseDay(b.day), 1)) });
export function toggleBills() {
  saveSettings({ hideBills: billsOn() ? '1' : '' });
  drawNav();
  if (['month', 'week', 'day', 'agenda'].includes(route().view)) drawView();
}
const moneyFmt = {};
export function billAmount(o) {
  const cur = o.currency || 'USD';
  let s;
  try { s = (moneyFmt[cur] = moneyFmt[cur] || new Intl.NumberFormat([], { style: 'currency', currency: cur })).format(Math.abs(+o.amount || 0)); } catch { s = `${Math.abs(+o.amount || 0).toFixed(2)} ${cur}`; }
  return `${o.approximate ? '≈ ' : ''}${o.amount > 0 ? '+' : ''}${s}`;
}
export const billTitle = (o) => `${o.merchant}: ${billAmount(o)}${o.amount > 0 ? ' in' : ''}\n${[o.category, o.account, o.frequency, o.paid ? 'paid' : null].filter(Boolean).join(' · ')}`;
/** ioMoney's page for the bill: the transaction that paid it, else its payments found by name. */
export const billUrl = (o) => (S.bills.url ? (o.transactionId ? `${S.bills.url}/#/transaction/${o.transactionId}` : `${S.bills.url}/#/transactions?${new URLSearchParams({ q: o.merchant })}`) : '');
/** The bill's card (event.js): what it is, and the links of the transaction that paid it. */
export function openBill(o) { import('./event.js').then((m) => m.openBillCard(o)).catch(fail); }
export function billChip(o) {
  return h('div', { class: `chip-ev bill ${o.paid ? 'done' : ''}`, style: { '--c': '#94650a' }, title: billTitle(o), onclick: (ev) => { ev.stopPropagation(); openBill(o); } },
    h('span', { class: 'bm' }, '$'), h('span', { class: 'nm' }, o.merchant), h('span', { class: 'amt' }, billAmount(o)));
}
// the documents from ioDocs that expire (a passport, a license, a policy), on the day they do
export const papersOn = () => !!S.status.iodocs && S.settings.hidePapers !== '1';
/** ioDocs did answer this person: the sidebar offers the documents, and remembers why they are away. */
export const papersOffered = () => !!S.status.iodocs && !/not part of the suite|No role/.test(S.papers.reason || '');
export const paperOcc = (p) => ({ ...p, paper: true, allDay: true, start: p.day, end: ymd(addDays(parseDay(p.day), 1)) });
export function togglePapers() {
  saveSettings({ hidePapers: papersOn() ? '1' : '' });
  drawNav();
  if (['month', 'week', 'day', 'agenda'].includes(route().view)) drawView();
}
export const paperTitle = (o) => `${o.title} expires\n${o.kind}`;
export function openPaper(o) { if (S.papers.url) window.open(`${S.papers.url}/#/doc/${o.id}`, '_blank', 'noopener'); }
export function paperChip(o) {
  return h('div', { class: 'chip-ev paper', style: { '--c': '#a03a6a' }, title: paperTitle(o), onclick: (ev) => { ev.stopPropagation(); openPaper(o); } },
    h('span', { class: 'bm' }, '!'), h('span', { class: 'nm' }, `${o.title} expires`));
}
export const taskTitle = (o) => `${o.title}\n${o.list ? `${o.list} · ` : ''}${o.allDay ? 'Due this day' : `Due at ${fmtTime(span(o)[0])}`}${o.done ? ' · done' : ''}${o.repeats ? ' · repeats' : ''}`;
export function taskChip(o) {
  return h('div', { class: `chip-ev task ${o.done ? 'done' : ''}`, style: { '--c': o.color || 'var(--brand)' }, title: taskTitle(o),
    onclick: (ev) => { ev.stopPropagation(); openTask(o); } },
  tickBtn(o), o.allDay ? null : h('span', { class: 't' }, fmtTime(span(o)[0])), h('span', { class: 'nm' }, o.title),
  (o.members || []).map(memberOf).filter(Boolean).map(memberBadge));
}

export function toggleWho(id) {
  if (id == null) S.who.clear(); else if (S.who.has(id)) S.who.delete(id); else S.who.add(id);
  saveSettings({ memberFilter: [...S.who].join(',') });
  drawNav();
  if (['month', 'week', 'day', 'agenda'].includes(route().view)) drawView();
}

export async function loadCals() {
  const [cals, fam] = await Promise.all([api('api/calendars'), api('api/members').catch(() => ({ items: S.members }))]);
  S.cals = cals.items;
  S.members = fam.items || [];
  for (const id of [...S.who]) if (!memberOf(id)) S.who.delete(id);
  drawNav();
}
export async function saveSettings(changes) {
  Object.assign(S.settings, changes);
  try { await api('api/auth/settings', { method: 'POST', json: changes }); } catch { /* kept for this visit */ }
}
export function toggleCal(id) {
  if (S.hidden.has(id)) S.hidden.delete(id); else S.hidden.add(id);
  saveSettings({ hiddenCalendars: [...S.hidden].join(',') });
  drawNav();
  if (['month', 'week', 'day', 'agenda'].includes(route().view)) drawView();
}
