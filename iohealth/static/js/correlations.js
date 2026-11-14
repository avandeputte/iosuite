import { $, COMMON_TYPES, cssVar, csvButton, csvNum, daysAgo, downloadCSV, empty, fmtCompact, fmtDate, fmtNum, h, hideTip, isoDate, loading, pages, prettyUnit, s, scaleFor, sectionOn, setParams, showError, showTip, today, typeDec, typeLabel, typeList } from './core.js';
import { api, pageTitle, settings } from './shell.js';
import { card, seg, stat } from './charts.js';

// ---------- correlations ----------

// Per-day values that aren't plain metrics.
export const CORR_EXTRA = { glucose_tir: ['Glucose time in range', '%', 0], glucose_cv: ['Glucose variability (CV)', '%', 1], workout_minutes: ['Workout minutes', 'min', 0] };
export const corrLabel = k => CORR_EXTRA[k]?.[0] || typeLabel(k);

// dailyValues returns Map(yyyy-mm-dd → value) and the unit for one metric over [from, to].
export async function dailyValues(key, from, to) {
  const out = new Map();
  if (key === 'glucose_tir' || key === 'glucose_cv') {
    const g = await api('glucose', { from, to, low: +settings.glucoseLow || 70, high: +settings.glucoseHigh || 180 });
    for (const d of g.days) if (d.n >= 12) out.set(d.date, key === 'glucose_tir' ? d.ranges.inRange * 100 : d.mean ? d.sd / d.mean * 100 : null);
    return { values: out, unit: '%' };
  }
  if (key === 'workout_minutes') {
    const ws = await api('workouts', { from, to });
    for (let d = new Date(from + 'T12:00'); isoDate(d) <= to; d.setDate(d.getDate() + 1)) out.set(isoDate(d), 0);
    for (const w of ws) { const d = isoDate(new Date(w.start * 1000)); if (out.has(d)) out.set(d, out.get(d) + w.duration / 60); }
    return { values: out, unit: 'min' };
  }
  const sr = await api('series', { type: key, from, to, bucket: 'day' });
  const k = scaleFor(sr.unit);
  for (const p of sr.points) out.set(isoDate(new Date(p.t * 1000)), p.v * k);
  return { values: out, unit: sr.unit === '%' ? '%' : prettyUnit(sr.unit) };
}

export function nextDay(d, n = 1) { const x = new Date(d + 'T12:00'); x.setDate(x.getDate() + n); return isoDate(x); }
// pairs: [date of Y, x, y] for days where both have a value; with lag 1, X is from the day before Y.
export function corrPairs(xs, ys, lag) {
  const out = [];
  for (const [d, y] of ys) {
    const x = xs.get(lag ? nextDay(d, -lag) : d);
    if (x != null && y != null && isFinite(x) && isFinite(y)) out.push([d, x, y]);
  }
  return out.sort((a, b) => a[0] < b[0] ? -1 : 1);
}
export function pearson(xs, ys) {
  const n = xs.length;
  if (n < 3) return null;
  const mx = xs.reduce((a, b) => a + b, 0) / n, my = ys.reduce((a, b) => a + b, 0) / n;
  let sxy = 0, sxx = 0, syy = 0;
  for (let i = 0; i < n; i++) { const dx = xs[i] - mx, dy = ys[i] - my; sxy += dx * dy; sxx += dx * dx; syy += dy * dy; }
  return sxx && syy ? { r: sxy / Math.sqrt(sxx * syy), slope: sxy / sxx, intercept: my - sxy / sxx * mx } : null;
}
export function ranks(v) {
  const idx = v.map((x, i) => [x, i]).sort((a, b) => a[0] - b[0]), r = new Array(v.length);
  for (let i = 0; i < idx.length;) { let j = i; while (j + 1 < idx.length && idx[j + 1][0] === idx[i][0]) j++; for (let k = i; k <= j; k++) r[idx[k][1]] = (i + j) / 2; i = j + 1; }
  return r;
}
export const strength = r => r == null ? '' : Math.abs(r) < 0.1 ? 'no real link' : Math.abs(r) < 0.3 ? 'a weak link' : Math.abs(r) < 0.5 ? 'a moderate link' : 'a strong link';
export function niceTicks(lo, hi, n = 5) {
  if (lo === hi) { lo -= 1; hi += 1; }
  const step0 = (hi - lo) / n, mag = 10 ** Math.floor(Math.log10(step0)), step = [1, 2, 2.5, 5, 10].map(f => f * mag).find(s => s >= step0);
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}

export function scatterPlot(pairs, fit, xLabel, yLabel, xDec, yDec) {
  const W = 680, H = 400, L = 62, R = 16, T = 14, B = 46;
  const xs = pairs.map(p => p[1]), ys = pairs.map(p => p[2]);
  const pad = (a, b) => { const d = (b - a) * 0.05 || 1; return [a - d, b + d]; };
  const [x0, x1] = pad(Math.min(...xs), Math.max(...xs)), [y0, y1] = pad(Math.min(...ys), Math.max(...ys));
  const X = v => L + (v - x0) / (x1 - x0) * (W - L - R), Y = v => H - B - (v - y0) / (y1 - y0) * (H - T - B);
  const muted = cssVar('--muted'), line = cssVar('--line');
  const svg = s('svg', { class: 'scatter', viewBox: `0 0 ${W} ${H}` });
  for (const v of niceTicks(x0, x1)) svg.append(s('line', { x1: X(v), x2: X(v), y1: T, y2: H - B, stroke: line }), s('text', { x: X(v), y: H - B + 16, 'font-size': 11, fill: muted, 'text-anchor': 'middle' }, fmtCompact(v)));
  for (const v of niceTicks(y0, y1)) svg.append(s('line', { x1: L, x2: W - R, y1: Y(v), y2: Y(v), stroke: line }), s('text', { x: L - 6, y: Y(v) + 4, 'font-size': 11, fill: muted, 'text-anchor': 'end' }, fmtCompact(v)));
  svg.append(s('text', { x: (L + W - R) / 2, y: H - 8, 'font-size': 12, fill: muted, 'text-anchor': 'middle' }, xLabel),
    s('text', { x: 14, y: (T + H - B) / 2, 'font-size': 12, fill: muted, 'text-anchor': 'middle', transform: `rotate(-90 14 ${(T + H - B) / 2})` }, yLabel));
  const accent = cssVar('--accent');
  pairs.forEach(([d, x, y], i) => svg.append(s('circle', { cx: X(x), cy: Y(y), r: 4.5, fill: accent, 'fill-opacity': 0.25 + 0.6 * (i + 1) / pairs.length, style: 'cursor:pointer',
    onmousemove: e => showTip(e, `${fmtDate(new Date(d + 'T12:00') / 1000)} · ${fmtNum(x, xDec)} → ${fmtNum(y, yDec)}`), onmouseleave: hideTip,
    onclick: () => { hideTip(); location.hash = '#/day/' + d; } })));
  if (fit) {
    const ya = fit.intercept + fit.slope * x0, yb = fit.intercept + fit.slope * x1;
    svg.append(s('defs', {}, s('clipPath', { id: 'scatter-clip' }, s('rect', { x: L, y: T, width: W - L - R, height: H - T - B }))),
      s('line', { x1: X(x0), y1: Y(ya), x2: X(x1), y2: Y(yb), stroke: cssVar('--text'), 'stroke-width': 2, 'stroke-dasharray': '6 4', 'clip-path': 'url(#scatter-clip)' }));
  }
  return svg;
}

pages.correlations = async (main, _, params) => {
  const types = await typeList();
  const options = [...Object.keys(CORR_EXTRA).filter(k => k.startsWith('glucose') ? types.blood_glucose && sectionOn('glucose') : sectionOn('workouts')),
    ...Object.values(types).filter(t => t.kind === 'quantity' || t.kind === 'category' || t.kind === 'ring').map(t => t.type)]
    .sort((a, b) => corrLabel(a).localeCompare(corrLabel(b)));
  const pick = (want, ...fallbacks) => [want, ...fallbacks].find(k => k && options.includes(k)) || options[0];
  const state = {
    y: pick(params.get('y'), 'blood_glucose', 'resting_heart_rate', 'step_count'),
    x: pick(params.get('x'), 'sleep_analysis', 'step_count', 'active_energy_burned'),
    range: params.get('range') || '1y', lag: params.get('lag') === '1' ? 1 : 0,
  };
  const sel = (key) => h('select', { onchange: e => { state[key] = e.target.value; draw(); } }, options.map(k => h('option', { value: k, selected: k === state[key] }, corrLabel(k))));
  const xSel = sel('x'), ySel = sel('y');
  const out = h('div'), table = h('div');
  main.replaceChildren(pageTitle('scatter', 'teal', 'Correlations'),
    card(null, h('div', { class: 'toolbar' }, h('span', {}, 'Does'), xSel, h('span', {}, 'go with'), ySel, h('span', {}, '?')),
      h('div', { class: 'toolbar', style: { marginBottom: 0 } },
        seg([['90d', '90 days'], ['1y', '1 year'], ['2y', '2 years'], ['5y', '5 years']], state.range, v => { state.range = v; draw(); }),
        seg([['0', 'Same day'], ['1', 'Day before']], String(state.lag), v => { state.lag = +v; draw(); }),
        h('span', { class: 'muted small' }, 'Day before: the first metric from the day before the second (e.g. sleep or a workout, then the next day’s glucose).'))),
    h('div', { style: { height: '16px' } }, ''), out, table);

  let seq = 0;
  async function draw() {
    const my = ++seq;
    setParams({ x: state.x, y: state.y, range: state.range, lag: String(state.lag) });
    xSel.value = state.x; ySel.value = state.y;
    loading(out);
    const days = { '90d': 90, '1y': 365, '2y': 730, '5y': 1826 }[state.range] || 365;
    const from = daysAgo(days), to = today();
    let X, Y;
    try { [X, Y] = await Promise.all([dailyValues(state.x, from, to), dailyValues(state.y, from, to)]); } catch (e) { if (my === seq) showError(out, e); return; }
    if (my !== seq) return;
    const pairs = corrPairs(X.values, Y.values, state.lag);
    const xDec = CORR_EXTRA[state.x]?.[2] ?? typeDec(state.x), yDec = CORR_EXTRA[state.y]?.[2] ?? typeDec(state.y);
    const xl = `${corrLabel(state.x)}${state.lag ? ' (day before)' : ''}${X.unit ? ' · ' + X.unit : ''}`, yl = `${corrLabel(state.y)}${Y.unit ? ' · ' + Y.unit : ''}`;
    if (pairs.length < 5) { out.replaceChildren(card(null, empty(`Only ${pairs.length} days have both. Pick a longer period or other metrics.`))); }
    else {
      const fit = pearson(pairs.map(p => p[1]), pairs.map(p => p[2]));
      const rho = pearson(ranks(pairs.map(p => p[1])), ranks(pairs.map(p => p[2])));
      const r = fit?.r;
      const words = r == null ? 'One of them doesn’t change, so there is nothing to compare.'
        : `${pairs.length} days show ${strength(r)}${Math.abs(r) >= 0.1 ? (r > 0 ? ': when ' + corrLabel(state.x).toLowerCase() + ' is higher, ' + corrLabel(state.y).toLowerCase() + ' tends to be higher too.' : ': when ' + corrLabel(state.x).toLowerCase() + ' is higher, ' + corrLabel(state.y).toLowerCase() + ' tends to be lower.') : '.'}`;
      out.replaceChildren(card(null,
        h('div', { class: 'row spread' }, h('h2', { style: { margin: 0 } }, `${corrLabel(state.x)} and ${corrLabel(state.y)}`),
          csvButton(() => downloadCSV(`iohealth-${state.x}-vs-${state.y}`, ['date', state.x + (state.lag ? '_day_before' : ''), state.y], pairs.map(p => [p[0], csvNum(p[1]), csvNum(p[2])])))),
        h('div', { class: 'stats', style: { margin: '12px 0' } }, stat('Correlation (r)', fmtNum(r, 2)), stat('Rank correlation', fmtNum(rho?.r, 2)),
          stat('Explains', r == null ? '—' : fmtNum(r * r * 100, 0) + '%', 'of the variation'), stat('Days', fmtNum(pairs.length)),
          fit ? stat(`Per 1 ${X.unit || 'unit'} more`, (fit.slope > 0 ? '+' : '') + fmtNum(fit.slope, Math.max(yDec, 2)), Y.unit) : null),
        h('p', {}, words),
        scatterPlot(pairs, fit, xl, yl, xDec, yDec),
        h('p', { class: 'small muted' }, 'Each dot is a day (darker is more recent); click one to open that day. The dashed line is the best straight-line fit. A link isn’t proof that one causes the other.')));
    }
    drawTable(my, from, to);
  }

  // What else goes with the second metric, same day and day before.
  async function drawTable(my, from, to) {
    const cands = [...new Set([...COMMON_TYPES, 'sleep_analysis', 'dietary_carbohydrates', 'dietary_energy_consumed', 'number_of_alcoholic_beverages', 'dietary_caffeine',
      'time_in_daylight', 'mindful_session', 'body_mass', ...Object.keys(CORR_EXTRA)])].filter(k => options.includes(k) && k !== state.y);
    table.replaceChildren(card(`What goes with ${corrLabel(state.y).toLowerCase()}`, h('p', { class: 'muted small' }, 'Working it out…')));
    const Y = await dailyValues(state.y, from, to).catch(() => null);
    const rows = await Promise.all(cands.map(async k => {
      const X = await dailyValues(k, from, to).catch(() => null);
      if (!X || !Y) return null;
      const res = [0, 1].map(lag => { const p = corrPairs(X.values, Y.values, lag); return p.length >= 14 ? { r: pearson(p.map(x => x[1]), p.map(x => x[2]))?.r, n: p.length } : null; });
      return res.some(x => x?.r != null) ? { k, res } : null;
    }));
    if (my !== seq) return;
    const list = rows.filter(Boolean).sort((a, b) => Math.max(...b.res.map(x => Math.abs(x?.r ?? 0))) - Math.max(...a.res.map(x => Math.abs(x?.r ?? 0))));
    const cell = (x, lag, k) => h('td', { class: 'r num click', style: { cursor: 'pointer' }, onclick: () => { state.x = k; state.lag = lag; draw(); $('#app').scrollTo(0, 0); } },
      x?.r == null ? '—' : h('span', {}, h('span', { class: 'corr-bar', style: { width: Math.abs(x.r) * 60 + 'px', background: x.r > 0 ? '#2563eb' : '#e8445a', marginRight: '8px' } }), fmtNum(x.r, 2)));
    table.replaceChildren(card(`What goes with ${corrLabel(state.y).toLowerCase()}`, list.length ? h('table', {},
      h('thead', {}, h('tr', {}, h('th', {}, 'Metric'), h('th', { class: 'r' }, 'Same day (r)'), h('th', { class: 'r' }, 'Day before (r)'), h('th', { class: 'r' }, 'Days'))),
      h('tbody', {}, list.map(({ k, res }) => h('tr', {}, h('td', {}, corrLabel(k)), cell(res[0], 0, k), cell(res[1], 1, k), h('td', { class: 'r num muted' }, fmtNum(Math.max(res[0]?.n || 0, res[1]?.n || 0))))))) : empty('Not enough overlapping days.'),
    h('p', { class: 'small muted' }, 'Blue: both go up together. Red: one goes up as the other goes down. Click a number to plot it. Needs at least 14 days in common.')));
  }
  draw();
};
