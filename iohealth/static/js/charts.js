import { DAY, cssVar, fmtCompact, fmtDateTime, fmtNum, h, onCleanup, s } from './core.js';

// ---------- charts ----------

export function observeWidth(el, f) {
  const ro = new ResizeObserver(() => f(el.clientWidth));
  ro.observe(el);
  onCleanup(() => ro.disconnect());
}

/* chart draws a uPlot time series.
   series: [{label, color, unit, dec, bars, scale, values, fill, dash, points, value(fmt)}]; data = [xs, ...values]. */
/* Unless zoom is false (the caller attaches its own zoomGroup), every chart gets drag to pan, wheel/pinch to zoom and
   Shift-drag to zoom, kept within its data; charts sharing a sync key move together. */
export const autoGroups = new Map();
// A line on a time axis stops wherever the samples stop: a hole much longer than the usual spacing between
// samples (and at least 30 minutes) is left empty instead of being bridged by a straight line.
export const gapCache = new WeakMap();
export function gapLimit(xs, ys) {
  let c = gapCache.get(ys);
  if (c && c.xs === xs) return c.limit;
  const d = [];
  let prev = -1;
  for (let i = 0; i < ys.length; i++) if (ys[i] != null) { if (prev >= 0) d.push(xs[i] - xs[prev]); prev = i; }
  d.sort((a, b) => a - b);
  const limit = Math.max(1800, 2.5 * (d.length ? d[d.length >> 1] : 0));
  gapCache.set(ys, { xs, limit });
  return limit;
}
export function sampleGaps(u, sidx, idx0, idx1, nullGaps) {
  const xs = u.data[0], ys = u.data[sidx], limit = gapLimit(xs, ys), px = x => Math.round(u.valToPos(x, 'x', true));
  const gaps = [...nullGaps];
  let prev = -1;
  for (let i = Math.max(0, idx0 - 1); i <= Math.min(ys.length - 1, idx1 + 1); i++) {
    if (ys[i] == null) continue;
    if (prev >= 0 && xs[i] - xs[prev] > limit) gaps.push([px(xs[prev]), px(xs[i])]);
    prev = i;
  }
  return gaps.sort((a, b) => a[0] - b[0]);
}
// A sample with no neighbour on either side would vanish once the line breaks, so it gets a dot.
export function lonePoints(u, sidx, show) {
  if (show) return null;
  const xs = u.data[0], ys = u.data[sidx], limit = gapLimit(xs, ys), out = [];
  const idx = [];
  for (let i = 0; i < ys.length; i++) if (ys[i] != null) idx.push(i);
  idx.forEach((i, k) => {
    const a = k ? xs[i] - xs[idx[k - 1]] : Infinity, b = k < idx.length - 1 ? xs[idx[k + 1]] - xs[i] : Infinity;
    if (a > limit && b > limit) out.push(i);
  });
  return out.length ? out : null;
}

export function chart(el, { xs, series, height = 240, sync, xTime = true, xRange, xFmt, xIncrs, xSpace, bands, legend = true, yRange, hooks, axisFmt, incrs, zoom = true }) {
  const muted = cssVar('--muted'), line = cssVar('--line');
  const scales = { x: { time: xTime } };
  const axes = [{ stroke: muted, grid: { stroke: line, width: 1 }, ticks: { stroke: line }, values: xFmt, incrs: xIncrs }];
  if (xSpace) axes[0].space = xSpace; // an undefined space would replace uPlot's default and drop every label
  const useries = [{ label: xTime ? 'Time' : '', value: xTime ? (u, v) => v == null ? '' : fmtDateTime(v) : (u, v) => v == null ? '' : (xFmt ? xFmt(u, [v])[0] : v) }];
  const seen = [];
  for (const sr of series) {
    const sc = sr.scale || 'y';
    if (!scales[sc]) {
      const n = seen.push(sc);
      scales[sc] = { auto: true, dir: sr.invert ? -1 : 1 };
      if (yRange || sr.bars || sr.zero) scales[sc].range = yRange || ((u, mn, mx) => [Math.min(0, mn ?? 0), (mx ?? 1) > 0 ? mx * 1.08 : 1]);
      axes.push({
        scale: sc, side: n % 2 ? 3 : 1, stroke: seen.length > 1 || series.length > 1 ? (sr.axisColor || sr.color) : muted,
        grid: { show: n === 1, stroke: line, width: 1 }, ticks: { stroke: line }, size: 60, incrs: sr.incrs || (n === 1 ? incrs : undefined),
        values: (u, vals) => vals.map(v => (sr.axisFmt || axisFmt || fmtCompact)(v)),
      });
    }
    useries.push({
      label: sr.label, stroke: sr.color, scale: sc, width: sr.bars ? 0 : (sr.width ?? 2), dash: sr.dash,
      fill: sr.bars ? (sr.fill || sr.color) : sr.fill, spanGaps: sr.bars ? true : xTime ? false : sr.spanGaps ?? true, show: sr.show ?? true,
      paths: sr.bars ? uPlot.paths.bars({ size: [0.75, sr.barMax || 48], align: 1 }) : sr.stepped ? uPlot.paths.stepped({ align: 1 }) : undefined,
      points: { show: sr.points ?? false, size: 5, fill: sr.color, filter: !sr.bars && xTime ? lonePoints : undefined },
      gaps: !sr.bars && xTime ? sampleGaps : undefined,
      value: sr.value || ((u, v) => v == null ? '—' : fmtNum(v, sr.dec ?? 1) + (sr.unit ? ' ' + sr.unit : '')),
    });
  }
  const opts = {
    width: el.clientWidth || 600, height, scales, axes, series: useries, bands,
    legend: { show: legend, live: true }, cursor: { sync: sync ? { key: sync, setSeries: false } : undefined, drag: { x: true, y: false }, bind: { dblclick: () => () => null } },
    hooks: zoom ? { ...hooks, setScale: [...(hooks?.setScale || []), (u, key) => { if (key === 'x' && u.zoomGroup) u.zoomGroup.scaled(u); }] } : hooks,
  };
  const u = new uPlot(opts, [xs, ...series.map(sr => sr.values)], el);
  if (xRange) u.setScale('x', { min: xRange[0], max: xRange[1] });
  if (zoom && xs.length > 1) {
    let g = sync && autoGroups.get(sync);
    if (!g) {
      // uPlot sets its scales only on the first draw, so the starting view comes from the data (half a step wider
      // on each side when there are bars, so the first and last bars aren't cut).
      const pad = series.some(sr => sr.bars) ? (xs[xs.length - 1] - xs[0]) / (xs.length - 1) / 2 : 0;
      const home = xRange ? [...xRange] : [xs[0] - pad, xs[xs.length - 1] + pad];
      g = zoomGroup({ home, minT: home[0], maxT: home[1], minSpan: Math.max(Math.min(900, (home[1] - home[0]) / 50), 3 * (home[1] - home[0]) / xs.length) });
      if (sync) { autoGroups.set(sync, g); onCleanup(() => autoGroups.delete(sync)); }
    }
    u.zoomGroup = g;
    g.attach(u);
  }
  observeWidth(el, w => u.setSize({ width: w, height }));
  onCleanup(() => u.destroy());
  return u;
}

/* zoomGroup keeps the x axes of several charts together and adds zoom and pan: drag to pan, Shift-drag across a chart to zoom into
   that period, the mouse wheel, Ctrl/⌘ + scroll or a trackpad pinch to zoom, Shift + scroll or a sideways swipe to pan, two-finger pinch and
   one-finger drag on touch screens, double-click to go back. onView([from, to]) runs once the view settles. */
export function zoomGroup({ home, onView, minT, maxT, minSpan = 900 }) {
  const g = { charts: [], home, syncing: false, timer: null };
  g.view = () => { const u = g.charts[0]; return u && u.scales.x.min != null ? [u.scales.x.min, u.scales.x.max] : g.home; };
  g.set = (a, b) => {
    const limit = maxT || Date.now() / 1000 + DAY, low = minT ?? -Infinity;
    if (b - a < minSpan) { const c = (a + b) / 2; a = c - minSpan / 2; b = c + minSpan / 2; }
    if (b - a >= limit - low) { a = low; b = limit; }
    else if (b > limit) { a -= b - limit; b = limit; }
    else if (a < low) { b += low - a; a = low; }
    g.syncing = true;
    for (const u of g.charts) u.setScale('x', { min: a, max: b });
    g.syncing = false;
    g.changed();
  };
  g.zoom = (f, center) => { const [a, b] = g.view(); const c = center ?? (a + b) / 2; g.set(c - (c - a) * f, c + (b - c) * f); };
  g.pan = f => { const [a, b] = g.view(), d = (b - a) * f; g.set(a + d, b + d); };
  g.reset = () => g.set(...g.home);
  g.changed = () => { clearTimeout(g.timer); g.timer = setTimeout(() => onView && onView(g.view()), 350); };
  // Called from the chart's setScale hook, e.g. after a drag-to-zoom on one chart.
  g.scaled = u => {
    if (g.syncing) return;
    g.syncing = true;
    for (const o of g.charts) if (o !== u) o.setScale('x', { min: u.scales.x.min, max: u.scales.x.max });
    g.syncing = false;
    g.changed();
  };
  g.attach = u => {
    g.charts.push(u);
    u.setScale('x', { min: g.home[0], max: g.home[1] });
    const over = u.over;
    const tAt = clientX => { const r = over.getBoundingClientRect(); return u.posToVal(clientX - r.left, 'x'); };
    // A mouse wheel moves in notches (whole lines, or wheelDelta steps of 120) and zooms without Ctrl; a trackpad
    // sends a smooth stream, and plain two-finger scrolling over a chart keeps scrolling the page.
    let smoothUntil = 0;
    over.addEventListener('wheel', e => {
      const sideways = Math.abs(e.deltaX) > Math.abs(e.deltaY);
      const notch = e.deltaMode !== 0 || (e.wheelDeltaY && e.wheelDeltaY % 120 === 0 && !e.deltaX);
      if (!notch) smoothUntil = e.timeStamp + 400;
      if (e.ctrlKey || e.metaKey) { e.preventDefault(); g.zoom(Math.exp(e.deltaY * 0.01), tAt(e.clientX)); }
      else if (notch && !e.shiftKey && e.timeStamp > smoothUntil) { e.preventDefault(); g.zoom(e.deltaY > 0 ? 1.25 : 0.8, tAt(e.clientX)); }
      else if (sideways || e.shiftKey) { e.preventDefault(); const [a, b] = g.view(); const d = (sideways ? e.deltaX : e.deltaY) / over.clientWidth * (b - a); g.set(a + d, b + d); }
    }, { passive: false });
    // Click and drag pans; Shift- or Alt-drag falls through to uPlot's drag-to-zoom selection.
    over.style.cursor = 'grab';
    over.addEventListener('mousedown', e => {
      if (e.shiftKey || e.altKey || e.button !== 0) return;
      e.stopPropagation(); e.preventDefault();
      const x0 = e.clientX, [a0, b0] = g.view();
      over.style.cursor = 'grabbing';
      let frame;
      const move = m => { cancelAnimationFrame(frame); frame = requestAnimationFrame(() => { const d = -(m.clientX - x0) / over.clientWidth * (b0 - a0); g.set(a0 + d, b0 + d); }); };
      const up = () => { over.style.cursor = 'grab'; window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up); };
      window.addEventListener('mousemove', move); window.addEventListener('mouseup', up);
    }, true);
    over.addEventListener('dblclick', e => { e.stopPropagation(); g.reset(); }, true);
    let touch = null;
    over.addEventListener('touchstart', e => {
      const [a, b] = g.view();
      touch = { a, b, x: [...e.touches].map(t => t.clientX), moved: false };
    }, { passive: true });
    over.addEventListener('touchmove', e => {
      if (!touch) return;
      const xs = [...e.touches].map(t => t.clientX), w = over.clientWidth, span = touch.b - touch.a;
      if (xs.length === 2 && touch.x.length === 2) {
        e.preventDefault();
        const d0 = Math.abs(touch.x[0] - touch.x[1]) || 1, d1 = Math.abs(xs[0] - xs[1]) || 1;
        const c = tAt((touch.x[0] + touch.x[1]) / 2), f = d0 / d1;
        g.set(c - (c - touch.a) * f, c + (touch.b - c) * f);
      } else if (xs.length === 1 && touch.x.length === 1 && (touch.moved || Math.abs(xs[0] - touch.x[0]) > 12)) {
        e.preventDefault();
        touch.moved = true;
        const d = -(xs[0] - touch.x[0]) / w * span;
        g.set(touch.a + d, touch.b + d);
      }
    }, { passive: false });
    over.addEventListener('touchend', () => { touch = null; });
  };
  return g;
}

export function zoomToolbar(g, label) {
  const btn = (text, title, f) => h('button', { title, onclick: f }, text);
  return h('div', { class: 'toolbar zoombar' },
    h('span', { class: 'seg' }, btn('−', 'Zoom out', () => g.zoom(2)), btn('+', 'Zoom in', () => g.zoom(0.5))),
    h('span', { class: 'seg' }, btn('◀', 'Earlier', () => g.pan(-0.5)), btn('▶', 'Later', () => g.pan(0.5))),
    btn('Reset', 'Back to the selected range', () => g.reset()), label,
    h('span', { class: 'muted small hint' }, 'Drag to move · Shift-drag across a chart to zoom in · mouse wheel, Ctrl/⌘ + scroll or pinch to zoom · double-click to reset'));
}

/* stackedBars draws stacked bars with uPlot by plotting running totals, tallest first, so each bar covers the ones
   above it; the legend shows each part's own value. */
export function stackedBars(el, { xs, stacks, height = 240, unit = '', dec = 0, axisFmt, valueFmt, xFmt, sync, incrs }) {
  const totals = xs.map(() => 0);
  const cum = stacks.map(st => st.values.map((v, i) => (totals[i] += v || 0)));
  const fmt = valueFmt || (v => fmtNum(v, dec) + (unit ? ' ' + unit : ''));
  const series = stacks.map((st, k) => ({
    label: st.label, color: st.color, bars: true, values: cum[k], scale: 'y',
    value: (u, v, si, i) => i == null ? '—' : fmt(st.values[i] || 0),
  })).reverse();
  return chart(el, { xs, series, height, axisFmt: axisFmt || fmtCompact, xFmt, sync, incrs, yRange: (u, mn, mx) => [0, (mx || 1) * 1.08] });
}

export function sparkline(values, { w = 190, h: ht = 38, color = cssVar('--accent'), bars = false, goal = null } = {}) {
  const pts = values.map((v, i) => [i, v]).filter(p => p[1] != null && isFinite(p[1]));
  const svg = s('svg', { width: '100%', height: ht, viewBox: `0 0 ${w} ${ht}`, preserveAspectRatio: 'none' });
  if (pts.length < 2) return svg;
  const ys = pts.map(p => p[1]);
  if (goal != null && isFinite(goal)) ys.push(goal);
  let mn = Math.min(...ys), mx = Math.max(...ys);
  if (bars) mn = 0;
  if (mx === mn) { mx += 1; mn -= 1; }
  const X = i => i / (values.length - 1) * (w - 2) + 1, Y = v => ht - 2 - (v - mn) / (mx - mn) * (ht - 4);
  if (bars) {
    const bw = Math.max(1, (w / values.length) * 0.7);
    for (const [i, v] of pts) svg.append(s('rect', { x: X(i) - bw / 2, y: Y(v), width: bw, height: ht - 2 - Y(v), fill: color, opacity: .75 }));
  } else {
    svg.append(s('path', { d: pts.map((p, k) => (k ? 'L' : 'M') + X(p[0]).toFixed(1) + ',' + Y(p[1]).toFixed(1)).join(''), fill: 'none', stroke: color, 'stroke-width': 1.8, 'vector-effect': 'non-scaling-stroke' }));
  }
  if (goal != null && isFinite(goal)) svg.append(s('line', { x1: 0, x2: w, y1: Y(goal), y2: Y(goal), stroke: cssVar('--good'), 'stroke-width': 1.2, 'stroke-dasharray': '4 3', 'vector-effect': 'non-scaling-stroke' }));
  return svg;
}

export function rings(a, size = 120) {
  const svg = s('svg', { width: size, height: size, viewBox: '0 0 120 120' });
  const defs = [[a?.move, a?.moveGoal, '--move', 52], [a?.exercise, a?.exerciseGoal, '--exercise', 38], [a?.stand, a?.standGoal, '--stand', 24]];
  for (const [v, goal, color, r] of defs) {
    const c = cssVar(color), len = 2 * Math.PI * r, f = goal > 0 ? (v || 0) / goal : 0;
    svg.append(s('circle', { cx: 60, cy: 60, r, fill: 'none', stroke: c, 'stroke-opacity': .2, 'stroke-width': 12 }));
    // Past 100 % the ring keeps going round, a darker lap on top.
    svg.append(s('circle', { cx: 60, cy: 60, r, fill: 'none', stroke: c, 'stroke-width': 12, 'stroke-linecap': 'round',
      'stroke-dasharray': `${Math.min(f, 1) * len} ${len}`, transform: 'rotate(-90 60 60)' }));
    if (f > 1) svg.append(s('circle', { cx: 60, cy: 60, r, fill: 'none', stroke: c, 'stroke-width': 12, 'stroke-linecap': 'round', filter: 'brightness(.75)',
      'stroke-dasharray': `${Math.min(f - 1, 1) * len} ${len}`, transform: 'rotate(-90 60 60)' }));
  }
  return svg;
}

export function seg(options, value, onChange) {
  const el = h('div', { class: 'seg' });
  for (const [v, label] of options) {
    el.append(h('button', { class: v === value ? 'on' : '', onclick: () => {
      for (const b of el.children) b.classList.remove('on');
      el.querySelector(`[data-v="${CSS.escape(v)}"]`).classList.add('on');
      onChange(v);
    }, 'data-v': v }, label));
  }
  return el;
}

export function card(title, ...children) { return h('section', { class: 'card' }, title ? h('h2', {}, title) : null, ...children); }
export function stat(k, v, unit) { return h('div', { class: 'stat' }, h('div', { class: 'k' }, k), h('div', { class: 'v' }, v, unit ? h('small', {}, unit) : null)); }

// Linear trend per day over [t, v] points.
export function slopePerDay(points) {
  const n = points.length;
  if (n < 3) return null;
  let sx = 0, sy = 0, sxx = 0, sxy = 0;
  for (const [t, v] of points) { const x = t / DAY; sx += x; sy += v; sxx += x * x; sxy += x * v; }
  const d = n * sxx - sx * sx;
  return d ? (n * sxy - sx * sy) / d : null;
}
