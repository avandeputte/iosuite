import { csvButton, csvNum, distParts, downloadCSV, empty, fmtHM, fmtLocal, fmtNum, fmtTime, h, isoDate, pages, prettyUnit, scaleFor, sectionOn, today, typeDec, typeList } from './core.js';
import { api, pageTitle, settings } from './shell.js';
import { card, chart, rings, stat } from './charts.js';
import { workoutTable } from './dashboard.js';
import { fmtG, gUnit, gVal, glucoseBackdrop, glucoseLine, keepGaps, mmol, pct, rangeBar, rangeLegend } from './glucose.js';
import { hypnogram } from './sleep.js';

// ---------- one day ----------

// Shades spans of time behind a chart: workouts orange, sleep violet.
export function spansBackdrop(spans) {
  return u => {
    const ctx = u.ctx, { left, top, width, height } = u.bbox;
    ctx.save();
    for (const sp of spans) {
      const x1 = u.valToPos(sp.start, 'x', true), x2 = u.valToPos(sp.end, 'x', true);
      if (x2 < left || x1 > left + width) continue;
      ctx.fillStyle = sp.color;
      ctx.fillRect(Math.max(left, x1), top, Math.min(left + width, x2) - Math.max(left, x1), height);
    }
    ctx.restore();
  };
}

export const DAY_TOTALS = [['step_count', 'Steps'], ['active_energy_burned', 'Active energy'], ['apple_exercise_time', 'Exercise'], ['distance_walking_running', 'Distance'],
  ['flights_climbed', 'Flights'], ['resting_heart_rate', 'Resting HR'], ['heart_rate_variability_sdnn', 'HRV'], ['body_mass', 'Weight'], ['dietary_carbohydrates', 'Carbs'],
  ['dietary_energy_consumed', 'Food energy'], ['time_in_daylight', 'Daylight']];

pages.day = async (main, arg) => {
  const date = /^\d{4}-\d{2}-\d{2}$/.test(arg) ? arg : today();
  const types = await typeList();
  const t0 = new Date(date + 'T00:00').getTime() / 1000, t1 = new Date(date + 'T00:00');
  t1.setDate(t1.getDate() + 1);
  const end = t1.getTime() / 1000;
  const shift = n => { const d = new Date(date + 'T12:00'); d.setDate(d.getDate() + n); return isoDate(d); };
  const go = d => location.hash = '#/day/' + d;
  const picker = h('input', { type: 'date', value: date, max: today(), onchange: e => e.target.value && go(e.target.value) });
  const title = new Date(date + 'T12:00').toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
  const statsEl = h('div', { class: 'stats' });
  const timeline = h('div');
  const side = h('div', { class: 'grid cols-2' });
  const csvRows = [];
  main.replaceChildren(
    h('div', { class: 'row spread' }, pageTitle('calendar', 'amber', title),
      h('div', { class: 'daynav toolbar', style: { margin: 0 } }, h('button', { onclick: () => go(shift(-1)) }, '◀ Previous'), picker,
        h('button', { onclick: () => go(shift(1)), disabled: date >= today() }, 'Next ▶'), date !== today() ? h('button', { onclick: () => go(today()) }, 'Today') : null,
        csvButton(() => downloadCSV('iohealth-' + date, ['time', 'metric', 'value', 'unit'], csvRows)))),
    card(null, statsEl), h('div', { style: { height: '16px' } }), timeline, side);

  const show = { glucose: types.blood_glucose && sectionOn('glucose'), sleep: types.sleep_analysis && sectionOn('sleep'), workouts: sectionOn('workouts'), activity: sectionOn('activity') };
  const target = [+settings.glucoseLow || 70, +settings.glucoseHigh || 180];
  const totalsWanted = DAY_TOTALS.filter(([t]) => types[t]);
  const [totals, ring, night, ws, gl, hr, steps, energy, carbs] = await Promise.all([
    Promise.all(totalsWanted.map(([t]) => api('series', { type: t, from: date, to: date, bucket: 'day' }).catch(() => null))),
    show.activity ? api('activity', { from: date, to: date }).then(a => a[0]).catch(() => null) : null,
    show.sleep ? api('sleep', { date }).catch(() => null) : null,
    show.workouts ? api('workouts', { from: date, to: date }).catch(() => []) : [],
    show.glucose ? api('glucose', { from: date, to: date, low: target[0], high: target[1] }).catch(() => null) : null,
    types.heart_rate ? api('series', { type: 'heart_rate', from: date, to: date, bucket: 'raw' }).catch(() => null) : null,
    types.step_count ? api('series', { type: 'step_count', from: date, to: date, bucket: 'hour' }).catch(() => null) : null,
    types.active_energy_burned ? api('series', { type: 'active_energy_burned', from: date, to: date, bucket: 'hour' }).catch(() => null) : null,
    types.dietary_carbohydrates ? api('series', { type: 'dietary_carbohydrates', from: date, to: date, bucket: 'raw' }).catch(() => null) : null,
  ]);
  if (gl && !settings.glucoseUnit) settings.glucoseUnit = gl.recordedUnit;

  // Numbers for the day.
  const stats = [];
  totalsWanted.forEach(([t, label], i) => {
    const p = totals[i]?.points?.[0];
    if (!p) return;
    const unit = totals[i].unit, v = p.v * scaleFor(unit);
    if (t === 'apple_exercise_time') stats.push(stat(label, fmtHM(v)));
    else if (t === 'distance_walking_running') stats.push(stat(label, ...distParts(unit === 'km' ? v * 1000 : unit === 'mi' ? v * 1609.344 : v)));
    else stats.push(stat(label, fmtNum(v, typeDec(t, unit)), prettyUnit(unit)));
    csvRows.push([date, t, csvNum(v), prettyUnit(unit)]);
  });
  if (night) stats.push(stat('Slept', fmtHM(night.asleep)));
  if (gl?.stats?.readings) stats.push(stat('Avg glucose', fmtG(gl.stats.mean), gUnit()), stat('Time in range', pct(gl.stats.ranges.inRange)));
  if (ws.length) stats.push(stat(ws.length === 1 ? 'Workout' : `${ws.length} workouts`, fmtHM(ws.reduce((a, w) => a + w.duration, 0) / 60)));
  if (ring) stats.unshift(h('div', { class: 'stat' }, rings(ring, 64)));
  statsEl.replaceChildren(...(stats.length ? stats : [empty('Nothing recorded on this day.')]));

  // Timeline: everything on one clock, sleep and workouts shaded.
  const spans = [...ws.map(w => ({ start: w.start, end: w.end, color: 'rgba(249,115,22,0.15)' }))];
  if (night?.segments) for (const sg of night.segments) if (sg.stage !== 'inBed' && sg.stage !== 'awake') spans.push({ start: sg.s, end: sg.e, color: 'rgba(139,92,246,0.10)' });
  const backdrop = spansBackdrop(spans);
  const charts = [], later = [];
  const add = (titleText, el) => { charts.push(h('h3', { style: { marginTop: charts.length ? '14px' : 0 } }, titleText), el); };
  const xr = [t0, end];
  const hourOnly = new Intl.DateTimeFormat(undefined, { hour: 'numeric' });
  const hourFmt = (u, vals) => vals.map(v => v % 3600 === 0 ? hourOnly.format(new Date(v * 1000)) : fmtTime(v));
  // Clock labels such as "10:00 PM" are wide: whole hours, spaced so they never touch whatever the chart's width.
  const hourAxis = { xFmt: hourFmt, xIncrs: [300, 900, 1800, 3600, 7200, 10800, 14400, 21600, 43200], xSpace: 64 };
  if (gl?.readings?.length) {
    const el = h('div', { class: 'chart' });
    add('Blood glucose', el);
    const carbPts = (carbs?.points || []);
    const tables = [glucoseLine(gl.readings)];
    if (carbPts.length) tables.push([carbPts.map(p => p.t), carbPts.map(p => p.v)]);
    const d = tables.length > 1 ? keepGaps(uPlot.join(tables, [[0, 1], [0, 0]])) : tables[0];
    later.push(() => chart(el, { xs: d[0], height: 240, xRange: xr, ...hourAxis, sync: 'day', hooks: { drawClear: [glucoseBackdrop(gl.target), backdrop] }, series: [
      { label: 'Glucose', color: '#e8445a', scale: 'g', unit: gUnit(), dec: mmol() ? 1 : 0, values: d[1], spanGaps: false, points: gl.readings.length < 60, axisFmt: v => fmtNum(v, mmol() ? 1 : 0) },
      ...(carbPts.length ? [{ label: 'Carbs', color: '#f59e0b', fill: '#f59e0b99', scale: 'carbs', unit: 'g', dec: 0, values: d[2], bars: true, barMax: 8 }] : []),
    ] }));
    for (const r of gl.readings) csvRows.push([fmtLocal(r[0]), 'blood_glucose', csvNum(gVal(r[1]), 1), gUnit()]);
    for (const p of carbPts) csvRows.push([fmtLocal(p.t), 'dietary_carbohydrates', csvNum(p.v, 1), 'g']);
  }
  if (hr?.points?.length) {
    const el = h('div', { class: 'chart' });
    add('Heart rate', el);
    later.push(() => chart(el, { xs: hr.points.map(p => p.t), height: 180, xRange: xr, ...hourAxis, sync: 'day', hooks: { drawClear: [backdrop] },
      series: [{ label: 'Heart rate', color: '#e8445a', unit: 'bpm', dec: 0, values: hr.points.map(p => p.v), width: 1.5 }] }));
    for (const p of hr.points) csvRows.push([fmtLocal(p.t), 'heart_rate', csvNum(p.v, 0), 'bpm']);
  }
  if (steps?.points?.length || energy?.points?.length) {
    const el = h('div', { class: 'chart' });
    add('Steps and active energy per hour', el);
    const tables = [steps, energy].filter(x => x?.points?.length).map(x => [x.points.map(p => p.t + 1800), x.points.map(p => p.v)]);
    const d = tables.length > 1 ? uPlot.join(tables) : tables[0];
    const series = [];
    if (steps?.points?.length) series.push({ label: 'Steps', color: '#2563eb', unit: '', dec: 0, values: d[1], bars: true, fill: '#2563ebaa' });
    if (energy?.points?.length) series.push({ label: 'Active energy', color: '#f97316', unit: 'kcal', dec: 0, values: d[series.length + 1], scale: 'kcal', width: 2 });
    later.push(() => chart(el, { xs: d[0], height: 180, xRange: xr, ...hourAxis, sync: 'day', hooks: { drawClear: [backdrop] }, series }));
    for (const x of [steps, energy]) for (const p of x?.points || []) csvRows.push([fmtLocal(p.t), x.type, csvNum(p.v, 1), prettyUnit(x.unit)]);
  }
  timeline.replaceChildren(charts.length ? card('Timeline', ...charts, h('p', { class: 'small muted' },
    'Violet: asleep. Orange: workouts. Charts move together: drag to move, scroll or pinch to zoom, double-click to reset.')) : card(null, empty('No timeline data for this day.')));
  for (const f of later) f();

  // Sleep and workouts.
  if (night) side.append(card('Sleep that ended this morning', hypnogram(night), h('div', { class: 'stats', style: { marginTop: '12px' } },
    stat('Asleep', fmtHM(night.asleep)), stat('Bedtime', night.start ? fmtTime(night.start) : '—'), stat('Woke up', night.end ? fmtTime(night.end) : '—'),
    stat('Deep', fmtHM(night.stages.deep)), stat('REM', fmtHM(night.stages.rem)))));
  if (ws.length) side.append(card('Workouts', workoutTable(ws, { compact: true })));
  if (gl?.stats?.readings > 20) side.append(card('Blood glucose', h('div', { class: 'stats' }, stat('Average', fmtG(gl.stats.mean), gUnit()),
    stat('Lowest / highest', `${fmtG(gl.stats.min)} / ${fmtG(gl.stats.max)}`), stat('Variability (CV)', fmtNum(gl.stats.cv, 1), '%'), stat('Lows ≥ 15 min', fmtNum(gl.stats.lows))),
    h('div', { style: { marginTop: '12px' } }, rangeBar(gl.stats.ranges)), rangeLegend(gl.stats.ranges, gl.target)));
};
