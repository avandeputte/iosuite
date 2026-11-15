import { api, h } from './core.js';

// ------------------------------------------------------------------ the weather (app/weather.py)
// The next seven days at the start page's weather place go on the day headers; an event with a place shows the weather
// there when it is within those days. Open-Meteo's weather codes (WMO) drawn with the start page's glyphs.
const WX = {
  sun: '<circle cx="12" cy="12" r="4.2"/><g stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8"/></g>',
  cloud: '<path d="M18.5 19H7a4.5 4.5 0 0 1-.7-8.95A6 6 0 0 1 17.8 9.5 4.75 4.75 0 0 1 18.5 19z"/>',
  partly: '<circle cx="8" cy="8" r="3.4"/><g stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M8 1.8v1.6M1.8 8h1.6M3.6 3.6l1.1 1.1M12.4 3.6l-1.1 1.1"/></g><path d="M19 20.5H9.5a3.8 3.8 0 0 1-.6-7.55A5 5 0 0 1 18.4 12 4 4 0 0 1 19 20.5z"/>',
  rain: '<path d="M18.5 15H7a4.5 4.5 0 0 1-.7-8.95A6 6 0 0 1 17.8 5.5 4.75 4.75 0 0 1 18.5 15z"/><g stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M8.5 17.5l-1 3M12.5 17.5l-1 3M16.5 17.5l-1 3"/></g>',
  storm: '<path d="M18.5 14H7a4.5 4.5 0 0 1-.7-8.95A6 6 0 0 1 17.8 4.5 4.75 4.75 0 0 1 18.5 14z"/><path d="M12.5 13.5 9 19h3l-1 4.5 4.5-6.5h-3l1.5-3.5z"/>',
  snow: '<path d="M18.5 14H7a4.5 4.5 0 0 1-.7-8.95A6 6 0 0 1 17.8 4.5 4.75 4.75 0 0 1 18.5 14z"/><g fill="currentColor"><circle cx="8.5" cy="18" r="1.3"/><circle cx="12.5" cy="20.5" r="1.3"/><circle cx="16.5" cy="18" r="1.3"/></g>',
  fog: '<g stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 9h16M3 13h18M5 17h14"/></g>',
};
const KIND = (c) => (c <= 1 ? 'sun' : c === 2 ? 'partly' : c === 3 ? 'cloud' : c <= 48 ? 'fog' : c <= 67 || (c >= 80 && c <= 82) ? 'rain'
  : c <= 77 || c === 85 || c === 86 ? 'snow' : c >= 95 ? 'storm' : 'cloud');
const TEXT = { 0: 'Clear', 1: 'Mostly clear', 2: 'Partly cloudy', 3: 'Cloudy', 45: 'Fog', 48: 'Freezing fog', 51: 'Light drizzle', 53: 'Drizzle', 55: 'Heavy drizzle',
  56: 'Freezing drizzle', 57: 'Freezing drizzle', 61: 'Light rain', 63: 'Rain', 65: 'Heavy rain', 66: 'Freezing rain', 67: 'Freezing rain', 71: 'Light snow',
  73: 'Snow', 75: 'Heavy snow', 77: 'Snow grains', 80: 'Showers', 81: 'Showers', 82: 'Heavy showers', 85: 'Snow showers', 86: 'Snow showers',
  95: 'Thunderstorms', 96: 'Thunderstorms with hail', 99: 'Thunderstorms with hail' };
export const wxText = (c) => TEXT[c] || '';
export function wxIcon(code) {
  const s = document.createElement('span');
  s.className = 'wx';
  s.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${WX[KIND(code)]}</svg>`;
  return s;
}
/** °C from the server, shown as the start page shows it (°F when it is set to imperial). */
export const temp = (c, units) => (c == null ? '' : `${Math.round(units === 'imperial' ? c * 9 / 5 + 32 : c)}°`);

let W = { days: [] }, at = 0, loading = null;
/** The forecast for the next days (asked again after an hour); never fails, an empty list instead. */
export function loadWeather() {
  if (Date.now() - at < 3600e3) return Promise.resolve(W);
  if (!loading) {
    loading = api('api/weather').catch(() => ({ days: [] })).then((r) => { W = r || { days: [] }; at = Date.now(); loading = null; return W; });
  }
  return loading;
}
const pad2 = (n) => String(n).padStart(2, '0');
const key = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
/** A day's forecast as a small badge (icon and high, low in the title), or null outside the forecast. */
export function dayWeather(d, long = false) {
  const x = (W.days || []).find((y) => y.date === key(d));
  if (!x) return null;
  const tip = `${W.place ? `${W.place}: ` : ''}${wxText(x.code)}, ${temp(x.max, W.units)} / ${temp(x.min, W.units)}${x.rain != null ? ` · ${x.rain}% chance of rain` : ''}`;
  return h('span', { class: 'wxd', title: tip, onclick: (ev) => ev.stopPropagation() }, wxIcon(x.code),
    h('span', { class: 'hi' }, temp(x.max, W.units)), long ? h('span', { class: 'lo' }, temp(x.min, W.units)) : null);
}
/** The weather where and when an event is, under its place: filled in once the server answers, empty otherwise. */
export function eventWeather(j) {
  const el = h('div', { class: 'evwx muted small' });
  if (!j.location || !/^\d+$/.test(String(j.id))) return el;
  const start = j.allDay ? String(j.start).slice(0, 10) : new Date(j.start).toISOString();
  const s = j.allDay ? new Date(`${start}T12:00:00`) : new Date(j.start);
  if (s < Date.now() - 864e5 || s > Date.now() + 7 * 864e5) return el;  // only within the forecast
  api(`api/events/${j.id}/weather?start=${encodeURIComponent(start)}`).then((r) => {
    if (!r || !r.found || !(r.hour || r.day)) return;
    const u = r.units, x = r.hour, d = r.day;
    const parts = x ? [wxText(x.code), temp(x.temp, u), x.rain ? `${x.rain}% chance of rain` : null]
      : [wxText(d.code), `${temp(d.max, u)} / ${temp(d.min, u)}`, d.rain ? `${d.rain}% chance of rain` : null];
    el.replaceChildren(wxIcon((x || d).code), h('span', null, parts.filter(Boolean).join(' · ')),
      r.place ? h('span', { class: 'where' }, `in ${r.place}`) : null);
  }).catch(() => {});
  return el;
}
