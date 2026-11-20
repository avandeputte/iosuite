import { api, applyTheme, setNavOn, settings, whenIdle } from './shell.js';

// ---------- basics: the helpers every page uses ----------

export const $ = (sel, el = document) => el.querySelector(sel);
export const TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
export const DAY = 86400;
// Axis steps for values in minutes, so ticks land on whole hours.
export const MINUTE_INCRS = [15, 30, 60, 120, 180, 240, 360, 600, 1200, 1800, 3000, 6000, 12000];

export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') for (const [sk, sv] of Object.entries(v)) { if (sk.startsWith('--')) el.style.setProperty(sk, sv); else el.style[sk] = sv; }
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'html') el.innerHTML = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export const svgNS = 'http://www.w3.org/2000/svg';
export function s(tag, attrs, ...children) {
  const el = document.createElementNS(svgNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null) continue;
    if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v);
  }
  for (const c of children.flat()) if (c != null) el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return el;
}

export function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

// ---------- formatting ----------

export const nf = {};
export function fmtNum(v, dec = 0) {
  if (v == null || !isFinite(v)) return '—';
  const k = dec;
  nf[k] ||= new Intl.NumberFormat(undefined, { minimumFractionDigits: dec, maximumFractionDigits: dec });
  return nf[k].format(v);
}
export function fmtCompact(v) {
  if (v == null || !isFinite(v)) return '';
  const a = Math.abs(v);
  if (a >= 1e6) return fmtNum(v / 1e6, 1) + 'M';
  if (a >= 1e4) return fmtNum(v / 1e3, 0) + 'k';
  if (a >= 100) return fmtNum(v, 0);
  if (a >= 10) return fmtNum(v, 1).replace(/\.0$/, '');
  return fmtNum(v, 2).replace(/\.?0+$/, '');
}
export function fmtDuration(sec, short = false) {
  if (sec == null || !isFinite(sec)) return '—';
  sec = Math.round(sec);
  const hh = Math.floor(sec / 3600), mm = Math.floor(sec % 3600 / 60), ss = sec % 60;
  if (short) return hh ? `${hh}h ${String(mm).padStart(2, '0')}m` : `${mm}m`;
  return hh ? `${hh}:${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}` : `${mm}:${String(ss).padStart(2, '0')}`;
}
export function fmtHM(minutes) {
  if (minutes == null || !isFinite(minutes)) return '—';
  const m = Math.round(minutes);
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m`;
}
export const dateFmt = new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
export const dateShortFmt = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' });
export const weekdayFmt = new Intl.DateTimeFormat(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
export const dateTimeFmt = new Intl.DateTimeFormat(undefined, { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
export const timeFmt = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' });
export const fmtDate = t => t == null ? '—' : dateFmt.format(new Date(t * 1000));
export const fmtDateShort = t => dateShortFmt.format(new Date(t * 1000));
export const fmtDateTime = t => dateTimeFmt.format(new Date(t * 1000));
export const fmtTime = t => timeFmt.format(new Date(t * 1000));
// 'today', 'yesterday', or the date (with the year when it isn't this year).
export function fmtDayAgo(t) {
  const d = new Date(t * 1000), day = isoDate(d);
  if (day === today()) return 'today';
  if (day === daysAgo(1)) return 'yesterday';
  return d.getFullYear() === new Date().getFullYear() ? fmtDateShort(t) : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}
export function fmtAgo(t) {
  const d = Date.now() / 1000 - t;
  if (d < 90) return 'just now';
  if (d < 3600) return `${Math.round(d / 60)} min ago`;
  if (d < 86400) return `${Math.round(d / 3600)} h ago`;
  return `${Math.round(d / 86400)} days ago`;
}
export function isoDate(d) { // local yyyy-mm-dd
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
export function daysAgo(n) { const d = new Date(); d.setDate(d.getDate() - n); return isoDate(d); }
export const today = () => isoDate(new Date());

// 'auto' (the default) follows the browser's region: miles where roads are signed in miles (the US, the UK, Liberia, Myanmar)
export const MILE_REGIONS = ['US', 'PR', 'GU', 'VI', 'AS', 'MP', 'UM', 'GB', 'LR', 'MM'];
export function regionUsesMiles(lang) {
  try { const l = new Intl.Locale(lang || 'en-US'); return MILE_REGIONS.includes(l.region || l.maximize().region); } catch { return false; }
}
export const imperial = () => settings.units === 'imperial' || (settings.units === 'auto' && regionUsesMiles(navigator.language));
export function fmtDist(m, dec) {
  if (m == null) return '—';
  if (imperial()) return fmtNum(m / 1609.344, dec ?? 2) + ' mi';
  return m < 1000 && dec == null ? fmtNum(m, 0) + ' m' : fmtNum(m / 1000, dec ?? 2) + ' km';
}
export function distParts(m) {
  return imperial() ? [fmtNum(m / 1609.344, 2), 'mi'] : [fmtNum(m / 1000, 2), 'km'];
}
export function fmtPace(secPerKm) {
  if (!secPerKm || !isFinite(secPerKm)) return '—';
  const v = imperial() ? secPerKm * 1.609344 : secPerKm;
  return fmtDuration(v) + (imperial() ? ' /mi' : ' /km');
}
export function fmtSpeed(mps) {
  if (mps == null) return '—';
  return imperial() ? fmtNum(mps * 2.236936, 1) + ' mph' : fmtNum(mps * 3.6, 1) + ' km/h';
}
export const fmtElev = m => m == null ? '—' : imperial() ? fmtNum(m * 3.28084, 0) + ' ft' : fmtNum(m, 0) + ' m';
export const fmtKcal = k => k == null ? '—' : fmtNum(k, 0) + ' kcal';

// ---------- health types ----------

export const TYPES = {
  step_count: ['Steps', 0], distance_walking_running: ['Walking + running distance', 2], distance_cycling: ['Cycling distance', 1],
  distance_swimming: ['Swimming distance', 0], active_energy_burned: ['Active energy', 0], basal_energy_burned: ['Resting energy', 0],
  apple_exercise_time: ['Exercise minutes', 0], apple_stand_time: ['Stand minutes', 0], apple_move_time: ['Move minutes', 0],
  flights_climbed: ['Flights climbed', 0], heart_rate: ['Heart rate', 0], resting_heart_rate: ['Resting heart rate', 0],
  walking_heart_rate_average: ['Walking heart rate', 0], heart_rate_variability_sdnn: ['Heart rate variability', 0],
  heart_rate_recovery_one_minute: ['Cardio recovery', 0], vo2_max: ['VO₂ max', 1], body_mass: ['Weight', 1],
  body_mass_index: ['Body mass index', 1], body_fat_percentage: ['Body fat', 1], lean_body_mass: ['Lean body mass', 1],
  height: ['Height', 0], waist_circumference: ['Waist', 1], oxygen_saturation: ['Blood oxygen', 1], respiratory_rate: ['Respiratory rate', 1],
  body_temperature: ['Body temperature', 1], apple_sleeping_wrist_temperature: ['Wrist temperature', 2],
  blood_pressure_systolic: ['Blood pressure (systolic)', 0], blood_pressure_diastolic: ['Blood pressure (diastolic)', 0],
  blood_glucose: ['Blood glucose', 0], insulin_delivery: ['Insulin', 1], walking_speed: ['Walking speed', 2], walking_step_length: ['Step length', 0],
  walking_asymmetry_percentage: ['Walking asymmetry', 1], walking_double_support_percentage: ['Double support time', 1],
  apple_walking_steadiness: ['Walking steadiness', 0], six_minute_walk_test_distance: ['Six-minute walk', 0],
  stair_ascent_speed: ['Stair speed up', 2], stair_descent_speed: ['Stair speed down', 2], running_speed: ['Running speed', 2],
  running_power: ['Running power', 0], running_stride_length: ['Stride length', 2], running_vertical_oscillation: ['Vertical oscillation', 1],
  running_ground_contact_time: ['Ground contact time', 0], cycling_power: ['Cycling power', 0], cycling_cadence: ['Cycling cadence', 0],
  cycling_speed: ['Cycling speed', 1], cycling_functional_threshold_power: ['Cycling FTP', 0], physical_effort: ['Physical effort', 1],
  time_in_daylight: ['Time in daylight', 0], environmental_audio_exposure: ['Environmental sound', 0],
  headphone_audio_exposure: ['Headphone audio', 0], sleep_analysis: ['Sleep', 1], mindful_session: ['Mindful minutes', 0],
  apple_stand_hour: ['Stand hours', 0], dietary_energy_consumed: ['Dietary energy', 0], dietary_water: ['Water', 0],
  dietary_caffeine: ['Caffeine', 0], dietary_carbohydrates: ['Carbohydrates', 0], dietary_sugar: ['Sugar', 0], dietary_fiber: ['Fiber', 0], dietary_protein: ['Protein', 0], number_of_alcoholic_beverages: ['Alcoholic drinks', 0],
  uv_exposure: ['UV index', 0], swimming_stroke_count: ['Swimming strokes', 0], push_count: ['Wheelchair pushes', 0],
  underwater_depth: ['Underwater depth', 1], water_temperature: ['Water temperature', 1], workout_effort_score: ['Workout effort', 1],
  atrial_fibrillation_burden: ['AFib history', 1], electrodermal_activity: ['Electrodermal activity', 2],
  activity_move: ['Move ring', 0], activity_move_goal: ['Move goal', 0], activity_move_percent: ['Move ring % of goal', 0],
  activity_exercise: ['Exercise ring', 0], activity_exercise_goal: ['Exercise goal', 0], activity_exercise_percent: ['Exercise ring % of goal', 0],
  activity_stand: ['Stand ring', 0], activity_stand_goal: ['Stand goal', 0], activity_stand_percent: ['Stand ring % of goal', 0],
};
export const typeLabel = t => TYPES[t]?.[0] || t.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase());
export const typeDec = (t, unit) => /^mmol/i.test(unit || '') ? 1 : TYPES[t]?.[1] ?? 1;
export const PRETTY_UNITS = { 'count/min': 'bpm', count: '', degC: '°C', degF: '°F', dBASPL: 'dB', 'mL/kg·min': 'mL/kg/min', 'mL/min·kg': 'mL/kg/min', 'ml/(kg*min)': 'mL/kg/min',
  'mL/(kg·min)': 'mL/kg/min', 'kcal/hr·kg': 'kcal/h/kg', 'kcal/(kg*hr)': 'kcal/h/kg', mmHg: 'mmHg', 'mg/dL': 'mg/dL', 'm/s': 'm/s' };
export const prettyUnit = u => u == null ? '' : /^mmol</i.test(u) ? 'mmol/L' : (u in PRETTY_UNITS ? PRETTY_UNITS[u] : u);
// HealthKit percentages are fractions; show them out of 100.
export const scaleFor = unit => unit === '%' ? 100 : 1;

export const COMMON_TYPES = ['blood_glucose', 'step_count', 'active_energy_burned', 'apple_exercise_time', 'distance_walking_running', 'flights_climbed',
  'heart_rate', 'resting_heart_rate', 'heart_rate_variability_sdnn', 'walking_heart_rate_average', 'vo2_max', 'body_mass',
  'body_fat_percentage', 'oxygen_saturation', 'respiratory_rate', 'apple_sleeping_wrist_temperature', 'time_in_daylight',
  'walking_speed', 'running_power'];

export const ACTIVITY_NAMES = { highIntensityIntervalTraining: 'HIIT', traditionalStrengthTraining: 'Strength training',
  functionalStrengthTraining: 'Functional strength', mixedCardio: 'Mixed cardio', crossTraining: 'Cross training',
  preparationAndRecovery: 'Recovery', mindAndBody: 'Mind & body', swimBikeRun: 'Multisport', stairClimbing: 'Stair climbing',
  coreTraining: 'Core training', cardioDance: 'Dance', socialDance: 'Social dance', wheelchairWalkPace: 'Wheelchair walk',
  wheelchairRunPace: 'Wheelchair run', other: 'Other' };
export const activityName = a => ACTIVITY_NAMES[a] || (a || 'Workout').replace(/([a-z])([A-Z])/g, '$1 $2').replace(/^./, c => c.toUpperCase());
export const ACTIVITY_COLORS = { running: '#e8445a', walking: '#16a34a', hiking: '#65a30d', cycling: '#2563eb', swimming: '#06b6d4',
  traditionalStrengthTraining: '#8b5cf6', functionalStrengthTraining: '#a855f7', highIntensityIntervalTraining: '#f97316',
  yoga: '#db2777', rowing: '#0ea5e9', elliptical: '#f59e0b', mixedCardio: '#ef4444', coreTraining: '#c026d3' };
export const PALETTE = ['#e8445a', '#2563eb', '#16a34a', '#f59e0b', '#8b5cf6', '#06b6d4', '#db2777', '#65a30d', '#f97316', '#0f766e'];
export function activityColor(a) {
  if (ACTIVITY_COLORS[a]) return ACTIVITY_COLORS[a];
  let x = 0;
  for (const c of a || '') x = (x * 31 + c.charCodeAt(0)) >>> 0;
  return PALETTE[x % PALETTE.length];
}
export const paceSports = new Set(['running', 'walking', 'hiking', 'wheelchairRunPace', 'wheelchairWalkPace', 'trackAndField']);

// ---------- page lifecycle ----------

export let cleanups = [];
export function onCleanup(f) { cleanups.push(f); }
export function resetPage() { for (const f of cleanups.splice(0)) { try { f(); } catch (e) { console.error(e); } } }

export function loading(el) { el.replaceChildren(h('p', { class: 'muted' }, 'Loading…')); }
export function showError(el, e) { el.replaceChildren(h('p', { class: 'error' }, 'Could not load: ' + e.message)); console.error(e); }
export function empty(msg) { return h('div', { class: 'empty' }, msg); }

export const tip = h('div', { class: 'tip', hidden: true });
document.body.append(tip);
export function showTip(e, text) { tip.textContent = text; tip.hidden = false; tip.style.left = (e.clientX + 12) + 'px'; tip.style.top = (e.clientY + 12) + 'px'; }
export function hideTip() { tip.hidden = true; }

// ---------- export ----------

// downloadCSV saves rows (arrays) under a header as a .csv file.
export function downloadCSV(name, header, rows) {
  const esc = v => v == null || (typeof v === 'number' && !isFinite(v)) ? '' : /[",\n]/.test(String(v)) ? '"' + String(v).replace(/"/g, '""') + '"' : String(v);
  const text = [header, ...rows].map(r => r.map(esc).join(',')).join('\r\n');
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }));
  const a = h('a', { href: url, download: name.replace(/[^\w.-]+/g, '-') + '.csv' });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
export function csvButton(f, title = 'Download the data shown as a CSV file') { return h('button', { class: 'noprint small-btn', title, onclick: f }, '⤓ CSV'); }
// Local date and time as text for CSV files.
export function fmtLocal(t) { const d = new Date(t * 1000); return isoDate(d) + ' ' + d.toTimeString().slice(0, 8); }
export const csvNum = (v, dec = 3) => v == null || !isFinite(v) ? '' : +v.toFixed(dec);

// printPage turns the page into a PDF through the browser's print dialog: light colours, no menus or buttons, and a
// line saying what is shown. Charts are drawn again first so they print in light colours.
export async function printPage() {
  const root = document.documentElement, theme = root.getAttribute('data-theme');
  const dark = theme === 'dark' || (!theme && matchMedia('(prefers-color-scheme: dark)').matches);
  root.classList.add('printing');
  if (dark) { root.setAttribute('data-theme', 'light'); await render(); }
  await whenIdle();
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  fillPrintHead();
  const done = async () => {
    root.classList.remove('printing');
    if (dark) { applyTheme(); await render(); }
  };
  window.addEventListener('afterprint', done, { once: true });
  window.print();
}
export function fillPrintHead() {
  const main = $('#app');
  const picked = [...main.querySelectorAll('.toolbar .seg button.on, .toolbar select')].map(el => el.tagName === 'SELECT' ? el.selectedOptions[0]?.textContent : el.textContent)
    .filter(t => t && !/^(mg\/dL|mmol\/L)$/.test(t));
  const view = [...main.querySelectorAll('.zoombar > .muted.small:not(.hint)')].map(el => el.textContent).filter(Boolean);
  $('#print-head').replaceChildren(h('b', {}, 'ioHealth'), ' · ', [...picked, ...view].join(' · '), h('span', { class: 'muted' }, ' · printed ' + fmtDateTime(Date.now() / 1000)));
}
window.addEventListener('beforeprint', fillPrintHead);
$('#print-btn')?.addEventListener('click', printPage);

// ---------- goals ----------

// settings.goals: [{type, dir: 'min' (at least) | 'max' (at most), value}] in the units the app shows.
export const goalFor = t => (settings.goals || []).find(g => g.type === t && g.value !== '' && isFinite(+g.value));
export const goalMet = (g, v) => v != null && (g.dir === 'max' ? v <= +g.value : v >= +g.value);
export const ALERT_DEFAULTS = { tir: 70, lows: 1, rhr: 5, hrv: 15, sleep: 45, sync: 24 }; // rhr, hrv and sleep: as app/usual.py DEFAULTS
export const alertSetting = k => { const v = settings.alerts?.[k]; return v === '' || v == null || !isFinite(+v) ? ALERT_DEFAULTS[k] : +v; };

// Sections and metrics can be switched off in Settings; switched-off metrics are left out of every list and chart.
export const SECTIONS = [['activity', 'Activity rings', 'the Move/Exercise/Stand card on the dashboard'], ['sleep', 'Sleep', 'the Sleep page, the last-night card and sleep in Metrics'],
  ['glucose', 'Blood glucose', 'the Glucose page and the dashboard glucose card'], ['workouts', 'Workouts', 'the Workouts and Map pages and the workout cards on the dashboard'],
  ['records', 'Records', 'the Records page']];
export const sectionOn = name => !(settings.hiddenSections || []).includes(name);
export function typeHidden(t) {
  if ((settings.hiddenTypes || []).includes(t)) return true;
  if (t === 'sleep_analysis' && !sectionOn('sleep')) return true;
  if (t === 'blood_glucose' && !sectionOn('glucose')) return true;
  if (t.startsWith('activity_') && !sectionOn('activity')) return true;
  return false;
}
export function applySections() {
  const pageSection = { sleep: 'sleep', glucose: 'glucose', workouts: 'workouts', map: 'workouts', records: 'records' };
  for (const a of document.querySelectorAll('#nav a')) a.hidden = !!pageSection[a.dataset.page] && !sectionOn(pageSection[a.dataset.page]);
}
applySections();
export let typeListPromise;
export function forgetTypeList() { typeListPromise = null; }  // the list is read again (a type hidden or shown)
export function typeList() {
  return typeListPromise ||= api('types').then(list => Object.fromEntries(list.filter(t => !typeHidden(t.type)).map(t => [t.type, t])));
}

// ---------- router ----------

export const pages = {};
export function route() {
  const [path, query] = location.hash.replace(/^#\/?/, '').split('?');
  const [page, ...rest] = path.split('/');
  return { page: page || 'dashboard', arg: rest.join('/'), params: new URLSearchParams(query || '') };
}
export function setParams(params) {
  const r = route();
  const q = new URLSearchParams(params).toString();
  history.replaceState(null, '', '#/' + (r.page === 'dashboard' ? '' : r.page) + (r.arg ? '/' + r.arg : '') + (q ? '?' + q : ''));
}
// The chart and map libraries, loaded the first time a page needs them (most pages chart; maps are on two)
const loaded = {};
function vendor(js, css) {
  if (!document.querySelector(`link[href="${css}"]`)) document.head.append(h('link', { rel: 'stylesheet', href: css }));
  return loaded[js] ||= new Promise((ok, fail) => document.head.append(h('script', { src: js, onload: ok,
    onerror: () => { delete loaded[js]; fail(new Error(`${js} did not load`)); } })));
}
const charts = () => vendor('static/vendor/uPlot.iife.min.js', 'static/vendor/uPlot.min.css');
const maps = () => vendor('static/vendor/leaflet.js', 'static/vendor/leaflet.css');
const NEEDS = { settings: [], records: [], map: [maps], workout: [charts, maps] };  // every other page: the charts

export async function render() {
  resetPage();
  const r = route();
  const pageName = r.page === 'workout' ? 'workouts' : r.page;
  setNavOn(pageName);
  const main = $('#app');
  loading(main);
  main.scrollTo(0, 0);
  const f = pages[r.page] || pages.dashboard;
  try {
    await Promise.all((NEEDS[pages[r.page] ? r.page : 'dashboard'] || [charts]).map(load => load()));
    await f(main, r.arg, r.params);
  } catch (e) { showError(main, e); }
}
window.addEventListener('hashchange', render);

export async function refreshStatus() {
  try {
    const st = await api('status', {}, { cache: false });
    const el = $('#sync-status');
    if (st.lastSync?.started) el.textContent = `Last sync ${fmtAgo(st.lastSync.finished || st.lastSync.started)}` + (st.lastSync.device ? ` from ${st.lastSync.device}` : '');
    else el.textContent = 'No sync yet';
    window.healthStatus = st;
    if (st.version) { const v = $('#nav-version'); if (v) v.textContent = `ioHealth v${st.version}`; }
  } catch { /* shown by the page */ }
}
