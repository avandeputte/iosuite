import { DAY, PALETTE, activityColor, activityName, cssVar, csvButton, csvNum, daysAgo, downloadCSV, empty, fmtDateShort, fmtDateTime, fmtHM, fmtLocal, fmtNum, h, isoDate, loading, pages, prettyUnit, resetPage, scaleFor, sectionOn, setParams, today, typeDec, typeLabel, typeList } from './core.js';
import { api, pageTitle, saveSettings, settings } from './shell.js';
import { card, chart, seg, stackedBars, stat, zoomGroup } from './charts.js';
import { lowerBound } from './workouts.js';

// ---------- blood glucose ----------

export const GLUCOSE_BANDS = [['veryLow', 'Very low', '#991b1b'], ['low', 'Low', '#ef4444'], ['inRange', 'In range', '#16a34a'], ['high', 'High', '#f59e0b'], ['veryHigh', 'Very high', '#c2410c']];
export const GLUCOSE_OVERLAYS = ['heart_rate', 'step_count', 'active_energy_burned', 'dietary_carbohydrates', 'insulin_delivery', 'apple_exercise_time',
  'heart_rate_variability_sdnn', 'respiratory_rate', 'body_mass'];
export const mmol = () => settings.glucoseUnit === 'mmol/L';
export const gUnit = () => mmol() ? 'mmol/L' : 'mg/dL';
export const gVal = v => v == null ? null : mmol() ? v / 18.0182 : v;
export const fmtG = v => v == null || !isFinite(v) ? '—' : fmtNum(gVal(v), mmol() ? 1 : 0);
export const pct = f => fmtNum((f || 0) * 100, 0) + '%';

export function rangeBar(r, height = 22) {
  const bar = h('div', { style: { display: 'flex', height: height + 'px', borderRadius: '6px', overflow: 'hidden', background: cssVar('--line') } });
  for (const [k, label, color] of GLUCOSE_BANDS) if (r[k] > 0) bar.append(h('div', { title: `${label}: ${pct(r[k])}`, style: { width: r[k] * 100 + '%', background: color } }));
  return bar;
}
export function rangeLegend(r, target) {
  const lo = fmtG(target[0]), hi = fmtG(target[1]);
  const labels = { veryLow: `< ${fmtG(54)}`, low: `${fmtG(54)}–${lo}`, inRange: `${lo}–${hi}`, high: `${hi}–${fmtG(250)}`, veryHigh: `> ${fmtG(250)}` };
  return h('div', { class: 'legend' }, GLUCOSE_BANDS.map(([k, label, color]) => h('span', {}, h('i', { style: { background: color } }), `${label} ${labels[k]}: `, h('b', {}, pct(r[k])))));
}

// glucoseLine: readings as [times, values] with a gap (null) wherever readings stop for more than 20 minutes
// (a sensor change, or no CGM), so the line isn't drawn straight across the missing time.
export function glucoseLine(readings) {
  const xs = [], ys = [];
  readings.forEach((r, i) => {
    // A null at each end of the gap, so points of other series joined in between can't bridge it.
    if (i && r[0] - readings[i - 1][0] > 1200) { xs.push(readings[i - 1][0] + 300, r[0] - 300); ys.push(null, null); }
    xs.push(r[0]); ys.push(gVal(r[1]));
  });
  return [xs, ys];
}

// keepGaps: after joining other series onto a glucose line, the glucose column has no value at their times; inside a
// gap (between the nulls glucoseLine put there) those become null too, so the line can't bridge the gap through them.
export function keepGaps(data) {
  const col = data[1];
  let inGap = false;
  for (let i = 0; i < col.length; i++) {
    if (col[i] === null) inGap = !inGap; // nulls come in pairs: where a gap starts and where it ends
    else if (col[i] === undefined) { if (inGap) col[i] = null; }
    else inGap = false;
  }
  return data;
}

// Shades the target range (and optionally workouts) behind a chart whose glucose scale is 'g'.
export function glucoseBackdrop(target, workouts = []) {
  return u => {
    const ctx = u.ctx, { left, top, width, height } = u.bbox;
    ctx.save();
    const y1 = u.valToPos(gVal(target[1]), 'g', true), y2 = u.valToPos(gVal(target[0]), 'g', true);
    ctx.fillStyle = 'rgba(22,163,74,0.10)';
    ctx.fillRect(left, Math.max(top, y1), width, Math.min(top + height, y2) - Math.max(top, y1));
    ctx.fillStyle = 'rgba(249,115,22,0.13)';
    for (const w of workouts) {
      const x1 = u.valToPos(w.start, 'x', true), x2 = u.valToPos(w.end, 'x', true);
      if (x2 < left || x1 > left + width) continue;
      ctx.fillRect(Math.max(left, x1), top, Math.min(left + width, x2) - Math.max(left, x1), height);
    }
    ctx.restore();
  };
}

pages.glucose = async (main, _, params) => {
  const types = await typeList();
  const state = { range: params.get('range') || '14', overlays: (params.get('with') || '').split(',').filter(Boolean), workouts: params.get('workouts') !== '0' };
  if (!types.blood_glucose) {
    main.replaceChildren(pageTitle('drop', 'rose', 'Blood glucose'), card(null, empty('No blood glucose readings yet. Turn on Blood Glucose under Data types in the iPhone app (CGM apps such as Dexcom, Libre or a meter app write it to Health), then sync.')));
    return;
  }
  const body = h('div');
  const overlayChips = h('div', { class: 'row' });
  const unitSeg = h('span');
  main.replaceChildren(pageTitle('drop', 'rose', 'Blood glucose'),
    h('div', { class: 'toolbar' },
      seg([['1', '24 hours'], ['3', '3 days'], ['7', '7 days'], ['14', '14 days'], ['30', '30 days'], ['90', '90 days'], ['365', '1 year']], state.range, v => { state.range = v; draw(); }),
      unitSeg),
    body);
  async function draw() {
    resetPage();
    setParams(Object.fromEntries(Object.entries({ range: state.range, with: state.overlays.join(','), workouts: state.workouts ? '' : '0' }).filter(([, v]) => v)));
    loading(body);
    const days = +state.range;
    const from = days === 1 ? String(Math.floor(Date.now() / 1000) - DAY) : daysAgo(days - 1);
    const target = [+settings.glucoseLow || 70, +settings.glucoseHigh || 180];
    const [g, ws] = await Promise.all([api('glucose', { from, to: today(), low: target[0], high: target[1] }), api('workouts', { from: daysAgo(days), to: today() })]);
    if (!settings.glucoseUnit) settings.glucoseUnit = g.recordedUnit;
    unitSeg.replaceChildren(seg([['mg/dL', 'mg/dL'], ['mmol/L', 'mmol/L']], gUnit(), v => { settings.glucoseUnit = v; saveSettings(); draw(); }));
    const st = g.stats;
    if (!st.readings) { body.replaceChildren(card(null, empty('No readings in this period.'))); return; }
    const cgm = st.perDay > 50;

    const statsCard = card(null, h('div', { class: 'stats' },
      stat('Average', fmtG(st.mean), gUnit()), stat('GMI (est. A1c)', fmtNum(st.gmi, 1), '%'),
      stat('Time in range', pct(st.ranges.inRange)), stat('Below range', pct(st.ranges.low + st.ranges.veryLow)),
      stat('Above range', pct(st.ranges.high + st.ranges.veryHigh)), stat('Variability (CV)', fmtNum(st.cv, 1), '%'),
      stat('Std deviation', fmtG(st.sd), gUnit()), stat('Lows ≥ 15 min', fmtNum(st.lows)),
      stat('Lowest / highest', `${fmtG(st.min)} / ${fmtG(st.max)}`), stat('Readings', fmtNum(st.readings), cgm && days >= 3 ? `${fmtNum(st.perDay)}/day` : '')),
    h('div', { style: { marginTop: '14px' } }, rangeBar(st.ranges)), rangeLegend(st.ranges, g.target),
    h('p', { class: 'small muted' }, `Targets: time in range above 70 %, below range under 4 %, CV at or under 36 %. GMI estimates HbA1c from the average (3.31 + 0.02392 × mg/dL) and needs about 14 days of CGM data to mean much. Target range ${fmtG(g.target[0])}–${fmtG(g.target[1])} ${gUnit()} (change it in Settings).`));

    // Readings chart with overlays.
    const avail = GLUCOSE_OVERLAYS.filter(t => types[t]);
    overlayChips.replaceChildren(h('span', { class: 'muted small' }, 'Overlay:'),
      ...avail.map((t, i) => h('span', { class: 'chip' + (state.overlays.includes(t) ? ' on' : ''), style: { color: PALETTE[(i + 1) % PALETTE.length] },
        onclick: () => { state.overlays = state.overlays.includes(t) ? state.overlays.filter(x => x !== t) : [...state.overlays, t]; draw(); } },
      h('span', { class: 'dot', style: { background: PALETTE[(i + 1) % PALETTE.length] } }), typeLabel(t))),
      h('label', { class: 'chip' + (state.workouts ? ' on' : ''), style: { color: '#f97316' } }, h('input', { type: 'checkbox', checked: state.workouts, style: { margin: 0 },
        onchange: e => { state.workouts = e.target.checked; draw(); } }), 'Workouts'),
      h('a', { class: 'small', href: '#/metrics?types=' + ['blood_glucose', ...state.overlays].join(',') + '&range=' + (days <= 7 ? '7d' : days <= 30 ? '30d' : days <= 90 ? '90d' : '1y') + '&mode=stack' }, 'Open in Metrics →'));
    const readingsEl = h('div', { class: 'chart' });
    const agpEl = h('div', { class: 'chart' });
    const dailyEl = h('div', { class: 'chart' });
    body.replaceChildren(statsCard,
      card(null, h('div', { class: 'row spread' }, h('h2', {}, 'Readings'), csvButton(() => downloadCSV('iohealth-glucose-' + daysAgo(days - 1) + '-' + today(),
        ['time', 'glucose', 'unit', 'note'], g.readings.map(r => [fmtLocal(r[0]), csvNum(gVal(r[1]), 1), gUnit(), r[2] || ''])))), h('div', { class: 'toolbar' }, overlayChips), readingsEl,
        h('p', { class: 'small muted' }, 'Green band: target range. ', state.workouts ? 'Orange: workouts. ' : '', 'Overlays get their own axis. Drag to move, scroll or Shift-drag to zoom, double-click to reset.')),
      days < 3 ? null : h('div', { class: 'grid cols-2' },
        card('Daily pattern (ambulatory glucose profile)', agpEl, h('p', { class: 'small muted' }, `Every day of the period folded onto one: median line, 25–75 % and 5–95 % bands, per 15 minutes${cgm ? '' : '. With finger-prick readings only, the bands are rough'}.`)),
        card('Time in range per day', dailyEl)));

    // The readings chart covers the selected period at first; dragging or zooming past what's loaded fetches the readings,
    // overlays and workouts for the new view, so it can be moved back through the whole history.
    const bucket = days <= 3 ? 'raw' : days <= 30 ? 'hour' : 'day';
    const wsShown = state.workouts ? [...ws] : [];
    const overlaysFor = (a, b) => Promise.all(state.overlays.map(t => api('series', { type: t, from: a, to: b, bucket: isCumulativeType(types, t) && bucket === 'raw' ? 'hour' : bucket }).catch(() => null)));
    const defs = [];
    const joinData = (readings, overlayData) => {
      const tables = [glucoseLine(readings)];
      state.overlays.forEach((t, k) => {
        const sr = overlayData[k], d = defs.find(d => d.t === t);
        if (!d) return;
        tables.push(sr && sr.points.length ? [sr.points.map(p => p.t), sr.points.map(p => p.v * scaleFor(sr.unit))] : [[readings[0]?.[0] ?? 0], [null]]);
      });
      return tables.length > 1 ? keepGaps(uPlot.join(tables, tables.map((t, i) => [0, i ? 0 : 1]))) : tables[0];
    };
    const fromT = days === 1 ? +from : Math.floor(new Date(from + 'T00:00:00').getTime() / 1000), nowT = Math.floor(Date.now() / 1000);
    const overlayData = await overlaysFor(fromT, nowT);
    overlayData.forEach((sr, k) => {
      if (sr && sr.points.length) defs.push({ t: state.overlays[k], sr, color: PALETTE[(avail.indexOf(state.overlays[k]) + 1) % PALETTE.length] });
    });
    const joined = joinData(g.readings, overlayData);
    let loaded = [fromT, nowT], fetchSeq = 0;
    const group = zoomGroup({ home: [fromT, nowT], onView: async ([a, b]) => {
      if (a >= loaded[0] && b <= loaded[1]) return;
      const span = b - a, fa = Math.floor(a - span), fb = Math.min(nowT, Math.ceil(b + span)), seq = ++fetchSeq;
      try {
        const [gg, od, ww] = await Promise.all([api('glucose', { from: fa, to: fb, low: target[0], high: target[1] }), overlaysFor(fa, fb),
          state.workouts ? api('workouts', { from: fa, to: fb }) : []]);
        if (seq !== fetchSeq || !gg.readings.length) return;
        loaded = [fa, fb];
        wsShown.splice(0, wsShown.length, ...(Array.isArray(ww) ? ww : ww.workouts || []));
        const [va, vb] = group.view();
        readingsChart.setData(joinData(gg.readings, od), false);
        readingsChart.setScale('x', { min: va, max: vb });
      } catch (e) { /* keep what's shown */ }
    } });
    const readingsChart = chart(readingsEl, {
      xs: joined[0], height: 340, zoom: false, hooks: { drawClear: [glucoseBackdrop(g.target, wsShown)], setScale: [(u, key) => { if (key === 'x') group.scaled(u); }] },
      series: [
        { label: 'Glucose', color: '#e8445a', scale: 'g', unit: gUnit(), dec: mmol() ? 1 : 0, values: joined[1], points: !cgm || g.readings.length < 200, width: cgm ? 2 : 1.5,
          spanGaps: false, axisFmt: v => fmtNum(v, mmol() ? 1 : 0) },
        ...defs.map((d, k) => ({ label: typeLabel(d.t), color: d.color, scale: d.t, unit: prettyUnit(d.sr.unit), dec: typeDec(d.t, d.sr.unit), values: joined[k + 2],
          bars: d.sr.cumulative, width: 1.5, fill: d.sr.cumulative ? d.color + '66' : undefined })),
      ],
    });
    group.attach(readingsChart);
    // Ambulatory glucose profile and per-day time in range, for periods of several days.
    if (days < 3) { /* one day: the readings chart says it all */ }
    else if (g.agp.length > 3) {
      const xs = g.agp.map(b => b.minute * 60), col = k => g.agp.map(b => gVal(b[k]));
      chart(agpEl, { xs, height: 280, xTime: false, xIncrs: [3600, 7200, 10800, 14400, 21600], xFmt: (u, vals) => vals.map(v => `${String(Math.floor(v / 3600)).padStart(2, '0')}:${String(Math.floor(v % 3600 / 60)).padStart(2, '0')}`),
        hooks: { drawClear: [glucoseBackdrop(g.target)] },
        bands: [{ series: [1, 5], fill: '#e8445a1a' }, { series: [2, 4], fill: '#e8445a40' }],
        series: [['95 %', 'p95'], ['75 %', 'p75'], ['Median', 'p50'], ['25 %', 'p25'], ['5 %', 'p5']].map(([label, k]) => ({
          label, scale: 'g', values: col(k), color: k === 'p50' ? '#e8445a' : '#e8445a66', width: k === 'p50' ? 2.5 : 1, dash: k === 'p5' || k === 'p95' ? [4, 3] : undefined,
          unit: gUnit(), dec: mmol() ? 1 : 0, axisFmt: v => fmtNum(v, mmol() ? 1 : 0) })) });
    } else agpEl.append(empty('Not enough readings for a daily pattern.'));
    // Per-day time in range
    if (days >= 3) {
    const xs = g.days.map(d => new Date(d.date + 'T00:00').getTime() / 1000);
    stackedBars(dailyEl, { xs, height: 280, stacks: GLUCOSE_BANDS.map(([k, label, color]) => ({ label, color, values: g.days.map(d => d.ranges[k] * 100) })),
      valueFmt: v => fmtNum(v, 0) + '%', axisFmt: v => fmtNum(v) + '%', xFmt: (u, vals) => vals.map(v => fmtDateShort(v)) });
    }

    // How glucose moves around workouts and meals.
    if (cgm && days >= 3) {
      const slot = h('div');
      body.append(slot);
      const carbs = types.dietary_carbohydrates ? await api('series', { type: 'dietary_carbohydrates', from: daysAgo(days - 1), to: today(), bucket: 'raw' }).catch(() => null) : null;
      slot.replaceWith(responseCard(g.readings, sectionOn('workouts') ? ws.filter(w => w.start >= fromT) : [], carbs?.points || []));
    }

    // Finger-prick style readings list.
    if (!cgm) {
      const recent = g.readings.slice(-60).reverse();
      body.append(card('Latest readings', h('table', {}, h('tbody', {}, recent.map(r => h('tr', {},
        h('td', {}, fmtDateTime(r[0])), h('td', { class: 'r num' }, fmtG(r[1]), ' ', gUnit()), h('td', { class: 'muted' }, r[2] || ''),
        h('td', {}, h('span', { class: 'badge', style: { color: r[1] < g.target[0] ? '#ef4444' : r[1] > g.target[1] ? '#f59e0b' : '#16a34a' } },
          r[1] < g.target[0] ? 'low' : r[1] > g.target[1] ? 'high' : 'in range'))))))));
    }
  }
  draw();
};
export function isCumulativeType(types, t) { return !!types[t]?.cumulative; }

// ---------- glucose around workouts and meals ----------

// glucoseAt reads glucose (mg/dL) at time t from sorted readings: interpolated between neighbours up to 20 minutes
// apart, else the nearest reading within 7.5 minutes.
export function glucoseAt(rt, rv, t) {
  const b = lowerBound(rt, t), a = b - 1;
  if (a >= 0 && b < rt.length && rt[b] - rt[a] <= 1200) return rt[b] === rt[a] ? rv[a] : rv[a] + (rv[b] - rv[a]) * (t - rt[a]) / (rt[b] - rt[a]);
  if (b < rt.length && rt[b] - t <= 450) return rv[b];
  if (a >= 0 && t - rt[a] <= 450) return rv[a];
  return null;
}
export const RESPONSE_STEP = 5; // minutes
// glucoseResponse: the glucose curve from `before` minutes before t to `after` minutes after it on a 5-minute grid,
// with the baseline (average of the 30 minutes before). Null when the readings don't cover it well.
export function glucoseResponse(rt, rv, t, before = 60, after = 180) {
  const mins = [], vals = [];
  for (let m = -before; m <= after; m += RESPONSE_STEP) { mins.push(m); vals.push(glucoseAt(rt, rv, t + m * 60)); }
  const pre = vals.filter((v, i) => mins[i] >= -30 && mins[i] <= 0 && v != null);
  if (pre.length < 3 || vals.filter(v => v != null).length < vals.length * 0.6) return null;
  const base = pre.reduce((a, b) => a + b, 0) / pre.length;
  const at = m => vals[mins.indexOf(Math.round(m / RESPONSE_STEP) * RESPONSE_STEP)] ?? null;
  const within = (a, b) => vals.filter((v, i) => mins[i] >= a && mins[i] <= b && v != null);
  return { t, mins, vals, base, at, within };
}

// mealsFrom groups carbohydrate entries less than 30 minutes apart into meals of at least 10 g.
export function mealsFrom(points) {
  const meals = [];
  for (const p of points) {
    const last = meals[meals.length - 1];
    if (last && p.t - last.t <= 1800) last.carbs += p.v;
    else meals.push({ t: p.t, carbs: p.v });
  }
  return meals.filter(m => m.carbs >= 10);
}

export const fmtMin = m => m === 0 ? '0' : (m < 0 ? '−' : '+') + (Math.abs(m) >= 60 && Math.abs(m) % 60 === 0 ? Math.abs(m) / 60 + ' h' : Math.abs(m) + ' min');
export const fmtDelta = v => v == null || !isFinite(v) ? '—' : (v > 0 ? '+' : v < 0 ? '−' : '') + fmtG(Math.abs(v));

// responseCard: average glucose change around workouts (per activity) or meals (per meal size), and the list.
export function responseCard(readings, workouts, carbPoints) {
  const rt = readings.map(r => r[0]), rv = readings.map(r => r[1]);
  const body = h('div');
  let mode = workouts.length ? 'workouts' : 'meals';
  const el = card(null, h('div', { class: 'row spread', style: { marginBottom: '10px' } }, h('h2', { style: { margin: 0 } }, 'Glucose around workouts and meals'),
    h('div', { class: 'row' }, seg([['workouts', `Workouts`], ['meals', 'Meals']], mode, v => { mode = v; draw(); }), csvButton(() => exportCsv()))), body);
  let rows = [];
  function draw() {
    const isW = mode === 'workouts';
    const events = isW ? workouts.map(w => ({ t: w.start, w, dur: Math.round((w.end - w.start) / 60) }))
      : mealsFrom(carbPoints).map(m => ({ t: m.t, carbs: m.carbs }));
    const after = isW ? 180 : 180;
    rows = [];
    for (const e of events) {
      const r = glucoseResponse(rt, rv, e.t, 60, after);
      if (!r) continue;
      if (isW) {
        const endM = Math.min(e.dur, after), during = r.within(0, endM + 60);
        rows.push({ e, r, group: e.w.activityType, groupLabel: activityName(e.w.activityType), color: activityColor(e.w.activityType),
          a: r.at(endM) == null ? null : r.at(endM) - r.base, b: during.length ? Math.min(...during) : null, c: r.at(endM + 60) == null ? null : r.at(endM + 60) - r.base });
      } else {
        const post = r.mins.map((m, i) => [m, r.vals[i]]).filter(([m, v]) => m >= 0 && v != null);
        if (!post.length) continue;
        const [pm, pv] = post.reduce((x, y) => y[1] > x[1] ? y : x);
        const back = post.find(([m, v]) => m > pm && v <= r.base + 10);
        const size = e.carbs < 30 ? ['small', 'Under 30 g', '#16a34a'] : e.carbs < 60 ? ['medium', '30–60 g', '#f59e0b'] : ['large', '60 g or more', '#e8445a'];
        rows.push({ e, r, group: size[0], groupLabel: size[1], color: size[2], a: pv - r.base, b: pm, c: back ? back[0] : null });
      }
    }
    if (!rows.length) {
      body.replaceChildren(empty(isW ? 'No workouts in this period with glucose readings around them. Pick a longer period.' :
        carbPoints.length ? 'No meals with readings around them in this period. Pick a longer period.' : 'No carbohydrates logged. Log meals (carbs) in an app that writes to Health and they show up here.'));
      return;
    }
    // Average change from the baseline per group.
    const groups = new Map();
    for (const x of rows) (groups.get(x.group) || groups.set(x.group, { label: x.groupLabel, color: x.color, rows: [] }).get(x.group)).rows.push(x);
    const top = [...groups.values()].sort((a, b) => b.rows.length - a.rows.length).slice(0, 6);
    const mins = rows[0].r.mins;
    const series = top.map(g => ({
      label: `${g.label} (${g.rows.length})`, color: g.color, unit: gUnit(), dec: mmol() ? 1 : 0, width: 2.5,
      values: mins.map((m, i) => { const ds = g.rows.filter(x => x.r.vals[i] != null).map(x => x.r.vals[i] - x.r.base); return ds.length ? gVal(ds.reduce((a, b) => a + b, 0) / ds.length) : null; }),
      value: (u, v) => v == null ? '—' : (v > 0 ? '+' : '') + fmtNum(v, mmol() ? 1 : 0) + ' ' + gUnit(),
    }));
    const chartEl = h('div', { class: 'chart' });
    const tb = h('tbody');
    for (const x of rows.slice().sort((a, b) => b.e.t - a.e.t).slice(0, 60)) {
      tb.append(h('tr', { class: 'click', onclick: () => location.hash = isW ? '#/workout/' + x.e.w.uuid : '#/day/' + isoDate(new Date(x.e.t * 1000)) },
        h('td', {}, fmtDateTime(x.e.t)),
        h('td', {}, isW ? h('span', { style: { color: x.color, fontWeight: 600 } }, activityName(x.e.w.activityType), h('span', { class: 'muted' }, ' · ' + fmtHM(x.e.dur))) : fmtNum(x.e.carbs, 0) + ' g'),
        h('td', { class: 'r num' }, fmtG(x.r.base)),
        h('td', { class: 'r num' }, fmtDelta(x.a)),
        h('td', { class: 'r num' }, isW ? fmtG(x.b) : fmtMin(x.b)),
        h('td', { class: 'r num' }, isW ? fmtDelta(x.c) : x.c == null ? 'not within 3 h' : fmtMin(x.c))));
    }
    const heads = isW ? ['When', 'Workout', 'Before', 'Change by the end', 'Lowest (to 1 h after)', '1 h after the end'] : ['When', 'Carbs', 'Before', 'Rise to peak', 'Peak after', 'Back near start'];
    body.replaceChildren(chartEl,
      h('p', { class: 'small muted' }, isW ? 'Average change from the level in the 30 minutes before the start, per activity. 0 is the start of the workout.'
        : 'Average change from the level in the 30 minutes before eating, per meal size. Carb entries less than 30 minutes apart count as one meal.'),
      h('table', {}, h('thead', {}, h('tr', {}, ...heads.map((x, i) => h('th', { class: i > 1 ? 'r' : '' }, x)))), tb),
      ...(rows.length > 60 ? [h('p', { class: 'small muted' }, `Latest 60 of ${rows.length}; the chart uses all of them.`)] : []));
    chart(chartEl, { xs: mins.map(m => m * 60), xTime: false, height: 260, xIncrs: [1800, 3600, 7200, 10800], xSpace: 64, xFmt: (u, vals) => vals.map(v => fmtMin(v / 60)), series,
      axisFmt: v => (v > 0 ? '+' : '') + fmtNum(v, mmol() ? 1 : 0),
      hooks: { drawClear: [u => { const ctx = u.ctx, x = u.valToPos(0, 'x', true), y = u.valToPos(0, 'y', true); ctx.save(); ctx.strokeStyle = cssVar('--muted'); ctx.setLineDash([4, 4]);
        ctx.beginPath(); ctx.moveTo(x, u.bbox.top); ctx.lineTo(x, u.bbox.top + u.bbox.height); ctx.moveTo(u.bbox.left, y); ctx.lineTo(u.bbox.left + u.bbox.width, y); ctx.stroke(); ctx.restore(); }] } });
  }
  function exportCsv() {
    const isW = mode === 'workouts';
    downloadCSV('iohealth-glucose-' + mode, isW ? ['start', 'workout', 'minutes', 'before', 'change_by_end', 'lowest', 'change_1h_after', 'unit'] : ['time', 'carbs_g', 'before', 'rise_to_peak', 'peak_min', 'back_near_start_min', 'unit'],
      rows.map(x => isW ? [fmtLocal(x.e.t), activityName(x.e.w.activityType), x.e.dur, csvNum(gVal(x.r.base), 1), csvNum(gVal(x.a), 1), csvNum(gVal(x.b), 1), csvNum(gVal(x.c), 1), gUnit()]
        : [fmtLocal(x.e.t), csvNum(x.e.carbs, 0), csvNum(gVal(x.r.base), 1), csvNum(gVal(x.a), 1), x.b, x.c ?? '', gUnit()]));
  }
  draw();
  return el;
}

// The glucose curve around one workout, for the workout page.
export async function workoutGlucose(w) {
  const target = [+settings.glucoseLow || 70, +settings.glucoseHigh || 180];
  const g = await api('glucose', { from: String(Math.floor(w.start - 3600)), to: String(Math.ceil(w.end + 7200)), low: target[0], high: target[1] });
  if (g.readings.length < 6) return null;
  if (!settings.glucoseUnit) settings.glucoseUnit = g.recordedUnit;
  const rt = g.readings.map(r => r[0]), rv = g.readings.map(r => r[1]);
  const r = glucoseResponse(rt, rv, w.start, 60, Math.round((w.end - w.start) / 60) + 120);
  const endM = Math.round((w.end - w.start) / 60);
  const el = h('div', { class: 'chart' });
  const c = card('Blood glucose around this workout', r ? h('div', { class: 'stats', style: { marginBottom: '10px' } },
    stat('Before', fmtG(r.base), gUnit()), stat('Change by the end', fmtDelta(r.at(endM) == null ? null : r.at(endM) - r.base), gUnit()),
    stat('Lowest', fmtG(Math.min(...r.within(0, endM + 60))), gUnit()), stat('1 h after the end', fmtDelta(r.at(endM + 60) == null ? null : r.at(endM + 60) - r.base), gUnit())) : null,
  el, h('p', { class: 'small muted' }, 'From an hour before to two hours after. Orange: the workout. Green band: target range.'));
  const line = glucoseLine(g.readings);
  return [c, () => chart(el, { xs: line[0], height: 240, hooks: { drawClear: [glucoseBackdrop(g.target, [w])] },
    series: [{ label: 'Glucose', color: '#e8445a', scale: 'g', unit: gUnit(), dec: mmol() ? 1 : 0, values: line[1], spanGaps: false, points: rt.length < 60, axisFmt: v => fmtNum(v, mmol() ? 1 : 0) }] })];
}
