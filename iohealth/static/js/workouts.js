import { DAY, MINUTE_INCRS, activityColor, activityName, cssVar, csvButton, csvNum, daysAgo, distParts, downloadCSV, empty, fmtCompact, fmtDate, fmtDateTime, fmtDist, fmtDuration, fmtElev, fmtHM, fmtLocal, fmtNum, fmtPace, fmtSpeed, fmtTime, h, hideTip, imperial, isoDate, onCleanup, paceSports, pages, prettyUnit, refreshStatus, resetPage, s, scaleFor, setParams, showTip, typeLabel, typeList, weekdayFmt } from './core.js';
import { api, pageTitle, settings } from './shell.js';
import { card, chart, observeWidth, seg, stackedBars, stat } from './charts.js';
import { mondayOf, weeklyChart, workoutTable } from './dashboard.js';
import { workoutGlucose } from './glucose.js';

// ---------- workouts ----------

pages.workouts = async (main, _, params) => {
  const state = { type: params.get('type') || '', range: params.get('range') || '365' };
  const [all, profile] = await Promise.all([api('workouts'), api('profile').catch(() => ({}))]);
  const typesCount = {};
  for (const w of all) typesCount[w.activityType] = (typesCount[w.activityType] || 0) + 1;
  const years = [...new Set(all.map(w => new Date(w.start * 1000).getFullYear()))].sort((a, b) => b - a);

  const body = h('div');
  const typeSel = h('select', { onchange: e => { state.type = e.target.value; draw(); } }, h('option', { value: '' }, `All activities (${all.length})`),
    Object.entries(typesCount).sort((a, b) => b[1] - a[1]).map(([t, n]) => h('option', { value: t, selected: t === state.type }, `${activityName(t)} (${n})`)));
  const rangeSel = h('select', { onchange: e => { state.range = e.target.value; draw(); } },
    [['90', 'Last 90 days'], ['365', 'Last 12 months'], ...years.map(y => ['y' + y, String(y)]), ['all', 'All time']]
      .map(([v, l]) => h('option', { value: v, selected: v === state.range }, l)));
  main.replaceChildren(pageTitle('run', 'orange', 'Workouts'), h('div', { class: 'toolbar' }, typeSel, rangeSel), body);
  if (!all.length) { body.append(card(null, empty('No workouts yet.'))); return; }

  function draw() {
    resetPage();
    setParams(Object.fromEntries(Object.entries(state).filter(([, v]) => v)));
    let from = 0, to = Infinity;
    const now = Date.now() / 1000;
    if (state.range === 'all') from = 0;
    else if (state.range.startsWith('y')) { const y = +state.range.slice(1); from = new Date(y, 0, 1) / 1000; to = new Date(y + 1, 0, 1) / 1000; }
    else from = now - +state.range * DAY;
    const ws = all.filter(w => (!state.type || w.activityType === state.type) && w.start >= from && w.start < to);
    const sum = (f) => ws.reduce((a, w) => a + (f(w) || 0), 0);

    const totals = card(null, h('div', { class: 'stats' }, stat('Workouts', fmtNum(ws.length)), stat('Time', fmtHM(sum(w => w.duration) / 60)),
      stat('Distance', ...distParts(sum(w => w.distance))), stat('Energy', fmtNum(sum(w => w.energy)), 'kcal'),
      stat('Climbing', fmtElev(sum(w => w.elevation))), stat('Avg per week', fmtHM(sum(w => w.duration) / 60 / Math.max(1, ((Math.min(to, now) - Math.max(from, ws.length ? ws[ws.length - 1].start : from)) / (7 * DAY)))))));

    const calEl = h('div', { class: 'calendar' });
    const volEl = h('div', { class: 'chart' });
    const loadEl = h('div', { class: 'chart' });
    const spanDays = (Math.min(to, now) - (from || (all.length ? all[all.length - 1].start : now))) / DAY;
    const monthly = spanDays > 400;
    body.replaceChildren(totals,
      card('Calendar', calEl, h('p', { class: 'small muted' }, 'Each square is a day, darker for more workout time. Click one to open that day.')),
      h('div', { class: 'grid cols-2' }, card(monthly ? 'Time per month' : 'Time per week', volEl),
        card('Training load', loadEl, h('p', { class: 'small muted' },
          `Fitness is the 42-day and fatigue the 7-day weighted average of daily TRIMP (heart-rate based effort, max HR ${profile.maxHr || '?'}, resting ${profile.restingHr || '?'}). Form = fitness − fatigue. Workouts without heart rate are skipped.`))),
      card(null, h('div', { class: 'row spread' }, h('h2', {}, `${ws.length} workouts`), csvButton(() => downloadCSV('iohealth-workouts',
        ['start', 'end', 'activity', 'minutes', 'distance_m', 'energy_kcal', 'avg_hr', 'max_hr', 'climb_m', 'source'],
        ws.map(w => [fmtLocal(w.start), fmtLocal(w.end), activityName(w.activityType), csvNum(w.duration / 60, 1), csvNum(w.distance, 0), csvNum(w.energy, 0), csvNum(w.hrAvg, 0), csvNum(w.hrMax, 0), csvNum(w.elevation, 0), w.source])))),
        workoutTable(ws.slice(0, 300)), ws.length > 300 ? h('p', { class: 'small muted' }, 'Showing the latest 300; narrow the range to see others.') : null));

    calendar(calEl, ws, state.range.startsWith('y') ? new Date(+state.range.slice(1), 11, 31) : new Date());
    const periods = monthly ? Math.ceil(spanDays / 30.4) + 1 : Math.max(4, Math.ceil(Math.min(spanDays, 3650) / 7) + 1);
    if (state.range.startsWith('y')) weeklyChartRange(volEl, ws, from, to, monthly);
    else weeklyChart(volEl, ws, Math.min(periods, monthly ? 240 : 60), { monthly });
    trainingLoad(loadEl, all.filter(w => !state.type || w.activityType === state.type), profile, from, Math.min(to, now));
  }
  draw();
};

export function weeklyChartRange(el, ws, from, to, monthly) {
  // Weeks of a past year: the same as weeklyChart but anchored at the end of that year.
  const startOf = monthly ? (t => { const d = new Date(t * 1000); return new Date(d.getFullYear(), d.getMonth(), 1); }) : mondayOf;
  const xs = [];
  for (let d = startOf(from); d / 1000 < to; monthly ? d.setMonth(d.getMonth() + 1) : d.setDate(d.getDate() + 7)) xs.push(d.getTime() / 1000);
  const index = new Map(xs.map((x, i) => [x, i]));
  const byType = {};
  for (const w of ws) {
    const i = index.get(startOf(w.start).getTime() / 1000);
    if (i != null) (byType[w.activityType] ||= xs.map(() => 0))[i] += w.duration / 60;
  }
  const stacks = Object.entries(byType).map(([t, values]) => ({ label: activityName(t), color: activityColor(t), values }));
  if (!stacks.length) { el.append(empty('No workouts.')); return; }
  stackedBars(el, { xs, stacks, valueFmt: v => fmtHM(v), axisFmt: v => fmtCompact(v / 60) + 'h', incrs: MINUTE_INCRS });
}

export function calendar(el, ws, endDate) {
  const minutes = {};
  for (const w of ws) { const d = isoDate(new Date(w.start * 1000)); minutes[d] = (minutes[d] || 0) + w.duration / 60; }
  const end = new Date(endDate); end.setHours(0, 0, 0, 0);
  const start = new Date(end); start.setDate(start.getDate() - 364); start.setDate(start.getDate() - (start.getDay() + 6) % 7);
  const cell = 13, gap = 3, weeks = Math.ceil(((end - start) / 864e5 + 1) / 7);
  const svg = s('svg', { width: weeks * (cell + gap) + 30, height: 7 * (cell + gap) + 20 });
  const accent = cssVar('--accent'), lineC = cssVar('--line');
  const max = Math.max(60, ...Object.values(minutes));
  let lastMonth = -1;
  for (let d = new Date(start), i = 0; d <= end; d.setDate(d.getDate() + 1), i++) {
    const wk = Math.floor(i / 7), dow = (d.getDay() + 6) % 7, key = isoDate(d), m = minutes[key] || 0;
    if (d.getMonth() !== lastMonth && dow === 0) {
      lastMonth = d.getMonth();
      svg.append(s('text', { x: 30 + wk * (cell + gap), y: 10, 'font-size': 10, fill: cssVar('--muted') }, d.toLocaleDateString(undefined, { month: 'short' })));
    }
    const label = `${weekdayFmt.format(d)}: ${m ? fmtHM(m) : 'no workouts'}`;
    svg.append(s('rect', { x: 30 + wk * (cell + gap), y: 16 + dow * (cell + gap), width: cell, height: cell, rx: 2,
      fill: m ? accent : lineC, 'fill-opacity': m ? 0.25 + 0.75 * Math.min(1, m / max) : 1,
      onmousemove: e => showTip(e, label), onmouseleave: hideTip, onclick: () => { hideTip(); location.hash = '#/day/' + key; }, style: 'cursor:pointer' }));
  }
  ['Mon', 'Wed', 'Fri'].forEach((d, i) => svg.append(s('text', { x: 0, y: 26 + i * 2 * (cell + gap), 'font-size': 10, fill: cssVar('--muted') }, d)));
  el.replaceChildren(svg);
}

// Banister TRIMP per day, then exponentially weighted fitness (42 days) and fatigue (7 days).
export function trainingLoad(el, ws, profile, from, to) {
  const maxHr = +settings.maxHr || profile.maxHr, rest = profile.restingHr || 60;
  if (!maxHr) { el.append(empty('Needs a maximum heart rate (Settings) or your date of birth.')); return; }
  const male = profile.characteristics?.biologicalSex === '2';
  const daily = new Map();
  let first = Infinity;
  for (const w of ws) {
    if (!w.hrAvg) continue;
    const hrr = Math.max(0, Math.min(1, (w.hrAvg - rest) / (maxHr - rest)));
    const trimp = (w.duration / 60) * hrr * 0.64 * Math.exp((male ? 1.92 : 1.67) * hrr);
    const day = Math.floor(new Date(isoDate(new Date(w.start * 1000)) + 'T00:00').getTime() / 1000);
    daily.set(day, (daily.get(day) || 0) + trimp);
    first = Math.min(first, day);
  }
  if (!daily.size) { el.append(empty('No workouts with heart rate.')); return; }
  const xs = [], fit = [], fat = [], form = [], load = [];
  let ctl = 0, atl = 0;
  const startDay = new Date(first * 1000); startDay.setHours(0, 0, 0, 0);
  for (let d = startDay; d.getTime() / 1000 <= to; d.setDate(d.getDate() + 1)) {
    const t = d.getTime() / 1000, x = daily.get(t) || 0;
    ctl += (x - ctl) / 42; atl += (x - atl) / 7;
    if (t >= from - DAY) { xs.push(t); fit.push(ctl); fat.push(atl); form.push(ctl - atl); load.push(x || null); }
  }
  if (!xs.length) { el.append(empty('No data in this range.')); return; }
  chart(el, { xs, height: 240, series: [
    { label: 'Fitness', color: '#2563eb', dec: 0, values: fit },
    { label: 'Fatigue', color: '#e8445a', dec: 0, values: fat },
    { label: 'Form', color: '#16a34a', dec: 0, values: form, dash: [4, 3] },
    { label: 'Daily TRIMP', color: '#9aa1ad88', dec: 0, values: load, bars: true, scale: 'trimp', axisColor: cssVar('--muted') },
  ] });
}

// ---------- one workout ----------

pages.workout = async (main, id) => {
  const w = await api('workouts/' + encodeURIComponent(id));
  const name = activityName(w.activityType);
  const isPace = paceSports.has(w.activityType);
  const statsByType = Object.fromEntries((w.statistics || []).map(s => [s.type, s]));
  const statsEl = h('div', { class: 'stats' },
    stat('Duration', fmtDuration(w.duration)),
    w.distance ? stat('Distance', ...distParts(w.distance)) : null,
    w.distance && isPace ? stat('Avg pace', fmtPace(w.duration / (w.distance / 1000))) : null,
    w.distance && !isPace ? stat('Avg speed', fmtSpeed(w.distance / w.duration)) : null,
    w.energy ? stat('Active energy', fmtNum(w.energy), 'kcal') : null,
    w.hrAvg ? stat('Avg heart rate', fmtNum(w.hrAvg), 'bpm') : null,
    w.hrMax ? stat('Max heart rate', fmtNum(w.hrMax), 'bpm') : null,
    (w.elevation || w.routeGain) ? stat('Climb', fmtElev(w.elevation ?? w.routeGain)) : null,
    statsByType.running_power ? stat('Avg power', fmtNum(statsByType.running_power.average), 'W') : null,
    statsByType.cycling_power ? stat('Avg power', fmtNum(statsByType.cycling_power.average), 'W') : null,
    statsByType.cycling_cadence ? stat('Avg cadence', fmtNum(statsByType.cycling_cadence.average), 'rpm') : null,
    statsByType.step_count && w.duration ? stat('Cadence', fmtNum(statsByType.step_count.sum / (w.duration / 60)), 'spm') : null,
    w.metadata?.HKAverageMETs ? stat('Avg METs', fmtNum(parseFloat(w.metadata.HKAverageMETs), 1)) : null,
    w.metadata?.HKWeatherTemperature ? stat('Weather', weatherText(w.metadata)) : null,
  );

  main.replaceChildren(
    h('p', { class: 'small' }, h('a', { href: '#/workouts' }, '← Workouts')),
    h('div', { class: 'row spread' }, h('h1', { style: { color: activityColor(w.activityType) } }, name),
      h('span', { class: 'muted' }, fmtDateTime(w.start), ' – ', fmtTime(w.end), ' · ', w.source, w.indoor ? h('span', { class: 'badge', style: { marginLeft: '6px' } }, 'Indoor') : null)),
    card(null, statsEl));

  const series = w.series || {};
  const route = w.route || [];
  let mapMarker, map, routeTimes = route.map(p => p[0]);

  if (route.length > 1) {
    const mapEl = h('div', { class: 'map' });
    let colorBy = 'speed';
    const legend = h('div', { class: 'legend' });
    const mapCard = card(null, h('div', { class: 'row spread', style: { marginBottom: '10px' } }, h('h2', { style: { margin: 0 } }, 'Route'),
      seg([['speed', isPace ? 'Pace' : 'Speed'], ['hr', 'Heart rate'], ['alt', 'Elevation'], ['plain', 'Plain']], colorBy, v => { colorBy = v; paint(); })), mapEl, legend);
    main.append(mapCard);
    map = makeMap(mapEl);
    const latlngs = route.map(p => [p[1], p[2]]);
    const speeds = smoothSpeed(route);
    let layer;
    function paint() {
      if (layer) layer.remove();
      layer = L.layerGroup().addTo(map);
      const vals = colorBy === 'speed' ? speeds : colorBy === 'hr' ? route.map(p => p[6] > 0 ? p[6] : null) : colorBy === 'alt' ? route.map(p => p[3]) : null;
      if (!vals || vals.every(v => v == null)) {
        L.polyline(latlngs, { color: activityColor(w.activityType), weight: 4 }).addTo(layer);
        legend.replaceChildren(colorBy !== 'plain' ? 'No data for this colouring.' : '');
      } else {
        const sorted = vals.filter(v => v != null).sort((a, b) => a - b);
        const lo = sorted[Math.floor(sorted.length * 0.05)], hi = sorted[Math.floor(sorted.length * 0.95)];
        const step = Math.max(1, Math.floor(route.length / 400));
        for (let i = 0; i < route.length - 1; i += step) {
          const j = Math.min(route.length - 1, i + step), v = vals[i];
          const f = v == null || hi === lo ? 0.5 : Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
          L.polyline([latlngs[i], latlngs[j]], { color: rampColor(f), weight: 5, opacity: .95 }).addTo(layer);
        }
        const fmtV = colorBy === 'speed' ? (v => isPace ? fmtPace(1000 / v) : fmtSpeed(v)) : colorBy === 'hr' ? (v => fmtNum(v) + ' bpm') : fmtElev;
        legend.replaceChildren(h('span', {}, h('i', { style: { background: rampColor(0) } }), fmtV(lo)), h('span', {}, h('i', { style: { background: rampColor(.5) } }), 'middle'),
          h('span', {}, h('i', { style: { background: rampColor(1) } }), fmtV(hi)));
      }
      L.circleMarker(latlngs[0], { radius: 6, color: '#fff', weight: 2, fillColor: '#16a34a', fillOpacity: 1 }).addTo(layer).bindTooltip('Start');
      L.circleMarker(latlngs[latlngs.length - 1], { radius: 6, color: '#fff', weight: 2, fillColor: '#dc2626', fillOpacity: 1 }).addTo(layer).bindTooltip('Finish');
    }
    paint();
    map.fitBounds(L.latLngBounds(latlngs), { padding: [20, 20] });
    mapMarker = L.circleMarker(latlngs[0], { radius: 7, color: '#fff', weight: 2, fillColor: '#111', fillOpacity: 1, opacity: 0, fillOpacity: 0 }).addTo(map);
  }

  // Charts over time, synced with each other and with the map marker.
  const chartsCard = card('Over time');
  const hooks = { setCursor: [u => {
    if (!mapMarker || u.cursor.idx == null) return;
    const t = u.data[0][u.cursor.idx];
    let i = lowerBound(routeTimes, t);
    if (i >= route.length) i = route.length - 1;
    if (i >= 0 && Math.abs(routeTimes[i] - t) < 120) { mapMarker.setLatLng([route[i][1], route[i][2]]); mapMarker.setStyle({ opacity: 1, fillOpacity: 1 }); }
  }] };
  let charts = 0;
  const addChart = (title, xs, values, opts) => {
    if (!xs.length || values.every(v => v == null)) return;
    const el = h('div', { class: 'chart' });
    chartsCard.append(h('h3', {}, title), el);
    chart(el, { xs, height: 170, sync: 'workout', hooks, series: [{ label: title, values, ...opts }], xFmt: (u, vals) => vals.map(v => fmtDuration(v - w.start)), xTime: false });
    charts++;
  };
  const hr = series.heart_rate || [];
  addChart('Heart rate', hr.map(p => p[0]), hr.map(p => p[1]), { color: '#e8445a', unit: 'bpm', dec: 0, fill: '#e8445a18' });
  if (route.length > 1) {
    const sp = smoothSpeed(route);
    if (isPace) addChart('Pace', routeTimes, sp.map(v => v && v > 0.5 ? 1000 / v : null), { color: '#2563eb', invert: true, axisFmt: v => fmtPace(v).replace(/ \/.*/, ''), value: (u, v) => v == null ? '—' : fmtPace(v), fill: undefined });
    else addChart('Speed', routeTimes, sp.map(v => v == null ? null : imperial() ? v * 2.236936 : v * 3.6), { color: '#2563eb', unit: imperial() ? 'mph' : 'km/h', dec: 1 });
    addChart('Elevation', routeTimes, route.map(p => imperial() ? p[3] * 3.28084 : p[3]), { color: '#65a30d', unit: imperial() ? 'ft' : 'm', dec: 0, fill: '#65a30d22' });
  }
  for (const [t, label, unit, color, k] of [['running_power', 'Running power', 'W', '#f59e0b', 1], ['cycling_power', 'Power', 'W', '#f59e0b', 1],
    ['cycling_cadence', 'Cadence', 'rpm', '#8b5cf6', 1], ['running_stride_length', 'Stride length', 'm', '#8b5cf6', 1],
    ['running_vertical_oscillation', 'Vertical oscillation', 'cm', '#06b6d4', 1], ['running_ground_contact_time', 'Ground contact', 'ms', '#db2777', 1]]) {
    const sr = series[t];
    if (sr?.length > 2) addChart(label, sr.map(p => p[0]), sr.map(p => p[1] * k), { color, unit, dec: 0 });
  }
  if (charts) main.append(chartsCard);
  const types = await typeList();
  if (types.blood_glucose) {
    const gl = await workoutGlucose(w).catch(() => null);
    if (gl) { main.append(gl[0]); gl[1](); }
  }

  const grid = h('div', { class: 'grid cols-2' });
  // Splits
  const sp = (w.splits || {})[imperial() ? 'mi' : 'km'] || [];
  if (sp.length) {
    const unitM = imperial() ? 1609.344 : 1000;
    const paces = sp.map(x => x.seconds / (x.distance / unitM));
    const fastest = Math.min(...paces), slowest = Math.max(...paces);
    const tb = h('tbody');
    sp.forEach((x, i) => tb.append(h('tr', {},
      h('td', { class: 'num' }, x.distance < unitM * 0.98 ? fmtNum(x.distance / unitM, 2) : x.index),
      h('td', { class: 'num' }, isPace ? fmtDuration(paces[i]) : fmtSpeed(x.distance / x.seconds)),
      h('td', { style: { width: '40%' } }, h('div', { class: 'bar-bg' }, h('div', { class: 'bar', style: { width: (30 + 70 * (slowest === fastest ? 1 : (slowest - paces[i]) / (slowest - fastest))) + '%', background: paces[i] === fastest ? '#16a34a' : cssVar('--accent') } }))),
      h('td', { class: 'r num' }, x.hr ? fmtNum(x.hr) + ' bpm' : ''),
      h('td', { class: 'r num' }, fmtElev(x.gain)))));
    grid.append(card(`Splits per ${imperial() ? 'mile' : 'km'}`, h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, imperial() ? 'Mile' : 'Km'),
      h('th', {}, isPace ? 'Pace' : 'Speed'), h('th', {}), h('th', { class: 'r' }, 'HR'), h('th', { class: 'r' }, 'Climb'))), tb)));
  }
  // Zones
  if (w.zones?.length) {
    const total = w.zones.reduce((a, z) => a + z.seconds, 0) || 1;
    const colors = ['#94a3b8', '#3b82f6', '#22c55e', '#f59e0b', '#ef4444'];
    grid.append(card('Heart rate zones', ...w.zones.map((z, i) => h('div', { class: 'zone-row' },
      h('span', {}, h('b', {}, 'Zone ' + z.zone), h('div', { class: 'small muted' }, `${z.low}–${z.high} bpm`)),
      h('div', { class: 'bar-bg' }, h('div', { class: 'bar', style: { width: (z.seconds / total * 100) + '%', background: colors[i], height: '14px' } })),
      h('span', { class: 'num r' }, fmtDuration(z.seconds), h('div', { class: 'small muted' }, fmtNum(z.seconds / total * 100) + '%')))),
    h('p', { class: 'small muted' }, `Max heart rate ${fmtNum(w.maxHr)} bpm (${{ setting: 'from Settings', age: '220 − age', observed: 'highest recorded this year' }[w.maxHrFrom] || ''}).`)));
  }
  // Best efforts
  if (w.efforts?.length && isPace) {
    grid.append(card('Best efforts in this workout', ...w.efforts.map(e => h('div', { class: 'record' }, h('span', {}, e.name),
      h('span', { class: 'rv' }, fmtDuration(e.seconds), h('div', { class: 'small muted' }, fmtPace(e.seconds / (e.distance / 1000))))))));
  }
  // Segments and laps
  const laps = (w.events || []).filter(e => e.type === 'lap' || e.type === 'segment');
  if (w.activities?.length > 1) {
    grid.append(card('Segments', h('table', {}, h('tbody', {}, w.activities.map(a => h('tr', {}, h('td', {}, activityName(a.activity_type)),
      h('td', {}, fmtTime(a.start)), h('td', { class: 'r num' }, a.end ? fmtDuration(a.end - a.start) : '')))))));
  }
  if (laps.length) {
    grid.append(card(`Laps and segments (${laps.length})`, h('table', {}, h('tbody', {}, laps.map((e, i) => h('tr', {},
      h('td', {}, `${e.type} ${i + 1}`), h('td', {}, fmtDuration(e.start - w.start)), h('td', { class: 'r num' }, fmtDuration(e.end - e.start))))))));
  }
  // All statistics
  if (w.statistics?.length) {
    grid.append(card('All statistics', h('table', {}, h('thead', {}, h('tr', {}, ...['Type', 'Average', 'Min', 'Max', 'Total'].map((x, i) => h('th', { class: i ? 'r' : '' }, x)))),
      h('tbody', {}, w.statistics.map(st => h('tr', {}, h('td', {}, typeLabel(st.type), h('span', { class: 'muted small' }, ' ' + prettyUnit(st.unit))),
        ...['average', 'minimum', 'maximum', 'sum'].map(k => h('td', { class: 'r num' }, st[k] == null ? '' : fmtCompact(st[k] * scaleFor(st.unit))))))))));
  }
  if (grid.children.length) main.append(grid);
};

export function weatherText(m) {
  const t = m.HKWeatherTemperature.split(' ');
  let v = parseFloat(t[0]);
  if (t[1] === 'degF' && !imperial()) v = (v - 32) * 5 / 9;
  if (t[1] === 'degC' && imperial()) v = v * 9 / 5 + 32;
  const hum = m.HKWeatherHumidity ? ` · ${fmtNum(parseFloat(m.HKWeatherHumidity) / (parseFloat(m.HKWeatherHumidity) > 100 ? 100 : 1))}%` : '';
  return fmtNum(v) + (imperial() ? '°F' : '°C') + hum;
}

export function lowerBound(arr, x) { let lo = 0, hi = arr.length; while (lo < hi) { const m = (lo + hi) >> 1; if (arr[m] < x) lo = m + 1; else hi = m; } return lo; }

// smoothSpeed: metres per second from distance over a ±15 s window, which is steadier than the per-fix GPS speed.
export function smoothSpeed(route) {
  const out = new Array(route.length).fill(null);
  let a = 0, b = 0;
  for (let i = 0; i < route.length; i++) {
    while (route[a][0] < route[i][0] - 15) a++;
    while (b < route.length - 1 && route[b + 1][0] <= route[i][0] + 15) b++;
    const dt = route[b][0] - route[a][0];
    if (dt > 3) out[i] = (route[b][4] - route[a][4]) / dt;
  }
  return out;
}

export function rampColor(f) { // blue → green → yellow → red
  const stops = [[37, 99, 235], [22, 163, 74], [234, 179, 8], [220, 38, 38]];
  const x = f * (stops.length - 1), i = Math.min(stops.length - 2, Math.floor(x)), t = x - i;
  const c = stops[i].map((v, k) => Math.round(v + (stops[i + 1][k] - v) * t));
  return `rgb(${c.join(',')})`;
}

export function makeMap(el) {
  const map = L.map(el, { scrollWheelZoom: true, preferCanvas: true });
  const tiles = window.healthStatus?.tiles || {};
  // The page's Referrer-Policy (same-origin) would send tile requests without a Referer, and OpenStreetMap's tile
  // usage policy blocks those with a 403. Send just the site's origin to the tile server, nothing else.
  L.tileLayer(tiles.url || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    referrerPolicy: 'strict-origin-when-cross-origin', maxZoom: 19, attribution: tiles.attribution || '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  onCleanup(() => map.remove());
  observeWidth(el, () => map.invalidateSize());
  return map;
}

// ---------- all routes ----------

pages.map = async (main, _, params) => {
  const state = { type: params.get('type') || '', range: params.get('range') || '365' };
  const all = await api('workouts');
  const withRoute = all.filter(w => w.hasRoute);
  const typesCount = {};
  for (const w of withRoute) typesCount[w.activityType] = (typesCount[w.activityType] || 0) + 1;
  const years = [...new Set(withRoute.map(w => new Date(w.start * 1000).getFullYear()))].sort((a, b) => b - a);
  const mapEl = h('div', { class: 'map tall' });
  const info = h('span', { class: 'muted small' });
  const legend = h('div', { class: 'legend' });
  main.replaceChildren(pageTitle('map', 'cyan', 'Map'),
    h('div', { class: 'toolbar' },
      h('select', { onchange: e => { state.type = e.target.value; draw(); } }, h('option', { value: '' }, 'All activities'),
        Object.entries(typesCount).sort((a, b) => b[1] - a[1]).map(([t, n]) => h('option', { value: t, selected: t === state.type }, `${activityName(t)} (${n})`))),
      h('select', { onchange: e => { state.range = e.target.value; draw(); } },
        [['90', 'Last 90 days'], ['365', 'Last 12 months'], ...years.map(y => ['y' + y, String(y)]), ['all', 'All time']].map(([v, l]) => h('option', { value: v, selected: v === state.range }, l))),
      info),
    card(null, mapEl, legend));
  if (!withRoute.length) { mapEl.replaceWith(empty('No workouts with GPS routes yet.')); return; }
  await refreshStatus();
  const map = makeMap(mapEl);
  map.setView([20, 0], 2);
  let layer;
  async function draw() {
    setParams(Object.fromEntries(Object.entries(state).filter(([, v]) => v)));
    const p = {};
    if (state.type) p.type = state.type;
    if (state.range.startsWith('y')) { p.from = state.range.slice(1) + '-01-01'; p.to = state.range.slice(1) + '-12-31'; }
    else if (state.range === 'all') p.from = '2000-01-01';
    else p.from = daysAgo(+state.range);
    info.textContent = 'Loading routes…';
    const lines = await api('routes', p);
    if (layer) layer.remove();
    layer = L.featureGroup().addTo(map);
    const types = {};
    let dist = 0;
    for (const r of lines) {
      types[r.activityType] = (types[r.activityType] || 0) + 1;
      dist += r.distance;
      L.polyline(r.points, { color: activityColor(r.activityType), weight: 3, opacity: lines.length > 50 ? 0.45 : 0.8 })
        .bindTooltip(`${activityName(r.activityType)} · ${fmtDate(r.start)} · ${fmtDist(r.distance)}`, { sticky: true })
        .on('click', () => location.hash = '#/workout/' + r.uuid).addTo(layer);
    }
    info.textContent = `${lines.length} routes · ${fmtDist(dist, 0)}`;
    legend.replaceChildren(...Object.entries(types).map(([t, n]) => h('span', {}, h('i', { style: { background: activityColor(t) } }), `${activityName(t)} (${n})`)));
    if (lines.length) map.fitBounds(layer.getBounds(), { padding: [20, 20] });
  }
  draw();
};
