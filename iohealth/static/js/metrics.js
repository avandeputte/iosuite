import { COMMON_TYPES, DAY, PALETTE, cssVar, csvButton, csvNum, daysAgo, downloadCSV, empty, fmtDate, fmtDateTime, fmtLocal, fmtNum, goalFor, h, isoDate, loading, pages, prettyUnit, resetPage, scaleFor, setParams, showError, today, typeDec, typeLabel, typeList } from './core.js';
import { api, pageTitle } from './shell.js';
import { card, chart, seg, slopePerDay, zoomGroup, zoomToolbar } from './charts.js';

// ---------- metrics explorer ----------

export const RANGES = [['today', 'Today', 1], ['yesterday', 'Yesterday', 1], ['7d', '7 days', 7], ['30d', '30 days', 30], ['90d', '90 days', 90], ['1y', '1 year', 365], ['2y', '2 years', 730], ['5y', '5 years', 1826], ['all', 'All', 0]];

pages.metrics = async (main, _, params) => {
  const types = await typeList();
  const state = {
    types: (params.get('types') || 'resting_heart_rate,heart_rate_variability_sdnn').split(',').filter(t => types[t]),
    range: params.get('range') || '90d', bucket: params.get('bucket') || 'auto', mode: params.get('mode') || 'stack',
    from: params.get('from') || '', to: params.get('to') || '', band: params.get('band') !== '0', cmp: params.get('cmp') || '',
  };
  const save = () => setParams(Object.fromEntries(Object.entries({ types: state.types.join(','), range: state.range, bucket: state.bucket,
    mode: state.mode, from: state.range === 'custom' ? state.from : '', to: state.range === 'custom' ? state.to : '', band: state.band ? '' : '0', cmp: state.cmp }).filter(([, v]) => v)));

  const all = Object.values(types).filter(t => t.kind === 'quantity' || t.kind === 'category').sort((a, b) => typeLabel(a.type).localeCompare(typeLabel(b.type)));
  const chips = h('div', { class: 'row' });
  const search = h('input', { list: 'type-options', placeholder: 'Add a metric…', style: { minWidth: '240px' } });
  const datalist = h('datalist', { id: 'type-options' }, all.map(t => h('option', { value: typeLabel(t.type) + ' · ' + t.type })));
  search.addEventListener('change', () => {
    const t = search.value.split(' · ').pop().trim();
    search.value = '';
    if (types[t] && !state.types.includes(t)) { state.types.push(t); draw(); }
  });
  const quick = h('div', { class: 'type-picker' }, COMMON_TYPES.filter(t => types[t]).map(t => h('span', { class: 'chip', onclick: () => {
    state.types = state.types.includes(t) ? state.types.filter(x => x !== t) : [...state.types, t]; draw();
  } }, typeLabel(t))));

  const fromIn = h('input', { type: 'date', value: state.from || daysAgo(90) });
  const toIn = h('input', { type: 'date', value: state.to || today() });
  const customRow = h('span', { class: 'row', hidden: state.range !== 'custom' }, fromIn, '–', toIn,
    h('button', { onclick: () => { state.from = fromIn.value; state.to = toIn.value; draw(); } }, 'Apply'));
  const bucketSel = h('select', { onchange: e => { state.bucket = e.target.value; draw(); } },
    [['auto', 'Auto'], ['raw', 'Every sample'], ['hour', 'Hourly'], ['day', 'Daily'], ['week', 'Weekly'], ['month', 'Monthly'], ['year', 'Yearly']]
      .map(([v, l]) => h('option', { value: v, selected: v === state.bucket }, l)));
  const cmpSel = h('select', { title: 'Draw an earlier period as a dashed line, shifted onto this one', onchange: e => { state.cmp = e.target.value; draw(); } },
    [['', 'No comparison'], ['prev', 'Compare: previous period'], ['year', 'Compare: a year earlier']].map(([v, l]) => h('option', { value: v, selected: v === state.cmp }, l)));
  const bandBox = h('label', { class: 'row small', style: { gap: '4px' } }, h('input', { type: 'checkbox', checked: state.band, onchange: e => { state.band = e.target.checked; draw(); } }), 'min/max band');

  const out = h('div');
  const summary = h('div');
  main.replaceChildren(pageTitle('chart', 'blue', 'Metrics'),
    h('section', { class: 'card' },
      h('div', { class: 'toolbar' }, chips),
      h('div', { class: 'toolbar' }, search, datalist, h('span', { class: 'muted small' }, 'or pick:')), quick,
      h('div', { class: 'toolbar', style: { marginTop: '12px', marginBottom: 0 } },
        seg([...RANGES.map(r => [r[0], r[1]]), ['custom', 'Custom']], state.range, v => { state.range = v; customRow.hidden = v !== 'custom'; if (v !== 'custom') draw(); }),
        customRow, bucketSel,
        seg([['stack', 'Stacked'], ['overlay', 'Overlay']], state.mode, v => { state.mode = v; draw(); }), bandBox, cmpSel)),
    h('div', { style: { height: '16px' } }), out, summary);

  // The bucket for a visible span: every sample when zoomed in close, coarser as the span grows.
  const bucketFor = (t, span) => {
    if (state.bucket !== 'auto') return state.bucket;
    const cumulative = types[t]?.cumulative;
    if (span <= 1.5 * DAY && !cumulative && t !== 'sleep_analysis') return 'raw';
    if (span <= 3 * DAY) return 'hour';
    if (span <= 400 * DAY) return 'day';
    if (span <= 4 * 365 * DAY) return 'week';
    return 'month';
  };
  const BUCKET_WORDS = { raw: 'every sample', hour: 'hourly', day: 'daily', week: 'weekly', month: 'monthly', year: 'yearly' };

  let drawSeq = 0;
  async function draw() {
    save();
    const seq = ++drawSeq;
    resetPage();
    chips.replaceChildren(...state.types.map((t, i) => h('span', { class: 'chip on', style: { color: PALETTE[i % PALETTE.length] } },
      h('span', { class: 'dot', style: { background: PALETTE[i % PALETTE.length] } }), typeLabel(t),
      h('span', { class: 'x', title: 'Remove', onclick: () => { state.types = state.types.filter(x => x !== t); draw(); } }, '✕'))));
    for (const c of quick.children) c.classList.toggle('on', state.types.some(t => typeLabel(t) === c.textContent));
    bandBox.hidden = cmpSel.hidden = state.mode !== 'stack';
    if (!state.types.length) { out.replaceChildren(card(null, empty('Pick one or more metrics above.'))); summary.replaceChildren(); return; }
    loading(out);
    let from, to = today();
    if (state.range === 'custom') { from = state.from || daysAgo(90); to = state.to || today(); }
    else if (state.range === 'today') from = today();
    else if (state.range === 'yesterday') from = to = daysAgo(1);
    else if (state.range === 'all') {
      const first = Math.min(...state.types.map(t => types[t].first));
      from = isoDate(new Date(first * 1000));
    } else from = daysAgo(RANGES.find(r => r[0] === state.range)[2] - 1);
    const home = [new Date(from + 'T00:00').getTime() / 1000, new Date(to + 'T00:00').getTime() / 1000 + DAY];
    const earliest = Math.min(...state.types.map(t => types[t].first)) - DAY;

    // What is loaded: the period fetched and each metric's reply.
    let loaded = { a: home[0], b: home[1], results: null };
    // Comparison: the same metrics for an earlier period, moved forward by `shift` onto this one.
    const shift = state.mode !== 'stack' || state.range === 'all' ? 0 : state.cmp === 'prev' ? home[1] - home[0] : state.cmp === 'year' ? 365 * DAY : 0;
    const cmpLabel = state.cmp === 'year' ? 'A year earlier' : 'Previous period';
    const fetchSet = (a, b, span) => Promise.all(state.types.map(t => api('series', { type: t, from: String(Math.floor(a)), to: String(Math.ceil(b)), bucket: bucketFor(t, span) })));
    const fetchAll = async (a, b) => {
      const [results, cmp] = await Promise.all([fetchSet(a, b, b - a), shift ? fetchSet(a - shift, b - shift, b - a) : null]);
      loaded.nextCmp = cmp;
      return results;
    };
    try {
      loaded.results = await fetchAll(home[0], home[1]);
      loaded.cmp = loaded.nextCmp;
    } catch (e) { if (seq === drawSeq) showError(out, e); return; }
    if (seq !== drawSeq) return;

    const viewLabel = h('span', { class: 'muted small' });
    const group = zoomGroup({ home, onView: v => refresh(v) });
    const defs = state.types.map((t, i) => ({ t, i, color: PALETTE[i % PALETTE.length], band: state.band && !types[t].cumulative }));
    const unitOf = d => loaded.results[d.i].unit;
    const k = d => scaleFor(unitOf(d));
    const isBars = d => loaded.results[d.i].cumulative;
    // Data arrays for a metric: [xs, value, (max, min)].
    const dataFor = d => {
      const pts = loaded.results[d.i].points, kk = k(d);
      const cols = [pts.map(p => p.t), pts.map(p => p.v * kk)];
      if (d.band) cols.push(pts.map(p => (p.max ?? p.v) * kk), pts.map(p => (p.min ?? p.v) * kk));
      if (!shift || !loaded.cmp) return cols;
      const cp = loaded.cmp[d.i].points;
      return uPlot.join([cols, [cp.map(p => p.t + shift), cp.map(p => p.v * kk)]]);
    };
    const hooks = { setScale: [(u, key) => { if (key === 'x') group.scaled(u); }] };
    const subtitles = [];
    let overlayChart, stackCharts = [];
    const zb = zoomToolbar(group, viewLabel);
    zb.insertBefore(csvButton(() => exportCsv()), zb.querySelector('.hint'));
    out.replaceChildren(card(null, zb));
    if (state.mode === 'overlay') {
      const el = h('div', { class: 'chart' });
      out.append(card(`${defs.map(d => typeLabel(d.t)).join(' · ')}`, el, h('p', { class: 'small muted' }, 'Each unit has its own axis.')));
      const joined = defs.length > 1 ? uPlot.join(defs.map(d => dataFor(d).slice(0, 2))) : dataFor(defs[0]).slice(0, 2);
      overlayChart = chart(el, { xs: joined[0], height: 420, hooks, zoom: false, series: defs.map((d, j) => ({
        label: typeLabel(d.t), color: d.color, unit: prettyUnit(unitOf(d)), dec: typeDec(d.t, unitOf(d)), scale: prettyUnit(unitOf(d)) || d.t, values: joined[j + 1],
        points: false, fill: isBars(d) ? d.color + '22' : undefined,
      })) });
      group.attach(overlayChart);
    } else {
      for (const d of defs) {
        const el = h('div', { class: 'chart' });
        const sub = h('span', { class: 'muted small' });
        subtitles.push([d, sub]);
        out.append(card(null, h('div', { class: 'row spread' }, h('h2', { style: { color: d.color } }, typeLabel(d.t)), sub), el));
        const cols = dataFor(d), dec = typeDec(d.t, unitOf(d)), unit = prettyUnit(unitOf(d));
        const series = [{ label: typeLabel(d.t), color: d.color, unit, dec, values: cols[1], bars: isBars(d), points: !isBars(d) && cols[0].length < 90 }];
        let bands;
        if (d.band) {
          series.push({ label: 'max', color: d.color + '55', width: 1, unit, dec, values: cols[2] });
          series.push({ label: 'min', color: d.color + '55', width: 1, unit, dec, values: cols[3] });
          bands = [{ series: [2, 3], fill: d.color + '1f' }];
        }
        if (shift) series.push({ label: cmpLabel, color: d.color + 'aa', width: 1.5, dash: [6, 4], unit, dec, values: cols[cols.length - 1] });
        const goal = goalFor(d.t);
        const goalHook = goal ? { draw: [u => { const y = u.valToPos(+goal.value, 'y', true); if (y < u.bbox.top || y > u.bbox.top + u.bbox.height) return;
          const ctx = u.ctx; ctx.save(); ctx.strokeStyle = cssVar('--good'); ctx.lineWidth = 1.5 * devicePixelRatio; ctx.setLineDash([6 * devicePixelRatio, 4 * devicePixelRatio]);
          ctx.beginPath(); ctx.moveTo(u.bbox.left, y); ctx.lineTo(u.bbox.left + u.bbox.width, y); ctx.stroke(); ctx.restore(); }] } : {};
        const u = chart(el, { xs: cols[0], series, bands, hooks: { ...hooks, ...goalHook }, zoom: false, height: defs.length > 2 ? 200 : 260, sync: 'metrics',
          yRange: !goal ? undefined : isBars(d) ? (u, mn, mx) => [0, Math.max(mx || 1, +goal.value) * 1.08]
            : (u, mn, mx) => { const lo = Math.min(mn, +goal.value), hi = Math.max(mx, +goal.value), p = (hi - lo) * 0.08 || 1; return [lo - p, hi + p]; } });
        stackCharts.push(u);
        group.attach(u);
      }
    }

    function describe([a, b]) {
      const r0 = loaded.results[0];
      const fmt = (b - a) <= 2 * DAY ? fmtDateTime : fmtDate;
      viewLabel.textContent = `${fmt(a)} – ${fmt(b - 1)} · ${BUCKET_WORDS[r0?.bucket] || ''}`;
      for (const [d, sub] of subtitles) {
        const r = loaded.results[d.i];
        sub.textContent = `${prettyUnit(r.unit) || 'count'} · ${BUCKET_WORDS[r.bucket]}${r.bucket === 'raw' ? '' : r.cumulative ? ' totals' : ' averages'}`;
      }
      renderSummary(a, b);
    }

    // After a zoom or pan: fetch again when the view leaves the loaded period or wants a finer or coarser bucket.
    let refreshSeq = 0;
    async function refresh([a, b]) {
      const span = b - a;
      const needs = a < Math.max(loaded.a, earliest) || b > loaded.b + 60 ||
        state.types.some((t, i) => bucketFor(t, span) !== loaded.results[i].bucket);
      if (!needs) { describe([a, b]); return; }
      const my = ++refreshSeq;
      const fa = Math.max(earliest, a - span / 2), fb = Math.min(Date.now() / 1000 + DAY, b + span / 2);
      viewLabel.textContent = 'Loading…';
      let results;
      try { results = await fetchAll(fa, fb); } catch (e) { viewLabel.textContent = 'Could not load: ' + e.message; return; }
      if (my !== refreshSeq || seq !== drawSeq) return;
      loaded = { a: fa, b: fb, results, cmp: loaded.nextCmp };
      const [va, vb] = group.view();
      group.syncing = true;
      if (overlayChart) {
        const joined = defs.length > 1 ? uPlot.join(defs.map(d => dataFor(d).slice(0, 2))) : dataFor(defs[0]).slice(0, 2);
        overlayChart.setData(joined, false);
      }
      stackCharts.forEach((u, j) => {
        const d = defs[j], cols = dataFor(d);
        u.series[1].points.show = () => !isBars(d) && cols[0].length < 90;
        u.setData(cols, false);
      });
      for (const u of group.charts) u.setScale('x', { min: va, max: vb });
      group.syncing = false;
      describe([va, vb]);
    }

    // Summary of what is on screen.
    function renderSummary(a, b) {
      const tb = h('tbody');
      for (const d of defs) {
        const r = loaded.results[d.i], kk = k(d), dec = typeDec(d.t, r.unit);
        const pts = r.points.filter(p => p.t >= a && p.t < b), vals = pts.map(p => p.v * kk);
        if (!vals.length) { tb.append(h('tr', {}, h('td', {}, typeLabel(d.t)), h('td', { colspan: 6, class: 'muted' }, 'no data in view'))); continue; }
        const avg = vals.reduce((x, y) => x + y, 0) / vals.length;
        const mn = Math.min(...pts.map(p => (p.min ?? p.v) * kk)), mx = Math.max(...pts.map(p => (p.max ?? p.v) * kk));
        const slope = (b - a) >= 14 * DAY ? slopePerDay(pts.map((p, i) => [p.t, vals[i]])) : null;
        tb.append(h('tr', {}, h('td', {}, h('span', { class: 'dot', style: { background: d.color, display: 'inline-block', width: '9px', height: '9px', borderRadius: '50%', marginRight: '6px' } }), typeLabel(d.t)),
          h('td', { class: 'r num' }, fmtNum(avg, dec), ' ', prettyUnit(r.unit)), h('td', { class: 'r num' }, fmtNum(mn, dec)), h('td', { class: 'r num' }, fmtNum(mx, dec)),
          h('td', { class: 'r num' }, r.cumulative && r.bucket !== 'raw' ? fmtNum(vals.reduce((x, y) => x + y, 0), dec) : '—'),
          h('td', { class: 'r num' }, fmtNum(vals[vals.length - 1], dec)),
          h('td', { class: 'r num' }, slope == null ? '—' : (slope > 0 ? '+' : '') + fmtNum(slope * 30, dec + 1) + ' / 30 days'),
          shift ? h('td', { class: 'r num' }, cmpCell(d, a, b, avg, dec)) : null));
      }
      const per = loaded.results[0]?.bucket === 'raw' ? 'sample' : { hour: 'hour', day: 'day', week: 'week', month: 'month', year: 'year' }[loaded.results[0]?.bucket];
      summary.replaceChildren(card('Summary of the visible period', h('table', {}, h('thead', {}, h('tr', {},
        ...['Metric', `Average per ${per}`, 'Min', 'Max', 'Total', 'Latest', 'Trend', ...(shift ? [cmpLabel] : [])].map((x, i) => h('th', { class: i ? 'r' : '' }, x)))), tb)));
    }
    // The comparison period's average for what is in view, and the change to now.
    function cmpCell(d, a, b, avg, dec) {
      const vals = (loaded.cmp?.[d.i]?.points || []).filter(p => p.t + shift >= a && p.t + shift < b).map(p => p.v * k(d));
      if (!vals.length) return '—';
      const was = vals.reduce((x, y) => x + y, 0) / vals.length;
      const ch = was ? (avg - was) / Math.abs(was) * 100 : null;
      return h('span', {}, fmtNum(was, dec), ch == null ? '' : h('span', { class: 'muted' }, ` ${ch > 0 ? '▲' : '▼'} ${fmtNum(Math.abs(ch), 0)}%`));
    }
    function exportCsv() {
      const [a, b] = group.view();
      const rows = [];
      for (const d of defs) {
        const r = loaded.results[d.i], kk = k(d);
        for (const p of r.points) if (p.t >= a && p.t < b) rows.push([fmtLocal(p.t), d.t, csvNum(p.v * kk), csvNum(p.min == null ? null : p.min * kk), csvNum(p.max == null ? null : p.max * kk), p.n ?? '', prettyUnit(r.unit), r.bucket]);
      }
      downloadCSV(`iohealth-${state.types.join('-')}-${isoDate(new Date(a * 1000))}-${isoDate(new Date((b - 1) * 1000))}`, ['time', 'metric', 'value', 'min', 'max', 'samples', 'unit', 'bucket'], rows);
    }
    describe(home);
  }
  draw();
};
