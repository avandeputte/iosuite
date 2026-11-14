import { MINUTE_INCRS, cssVar, csvButton, csvNum, daysAgo, downloadCSV, empty, fmtDateShort, fmtHM, fmtLocal, fmtNum, fmtTime, h, hideTip, loading, pages, resetPage, s, setParams, showTip, today } from './core.js';
import { api, pageTitle } from './shell.js';
import { card, chart, seg, stackedBars, stat } from './charts.js';

// ---------- sleep ----------

export const STAGES = [['deep', 'Deep', '#3730a3'], ['core', 'Core', '#3b82f6'], ['rem', 'REM', '#06b6d4'], ['asleep', 'Asleep (unspecified)', '#8b5cf6'], ['awake', 'Awake', '#f97316']];

pages.sleep = async (main, _, params) => {
  const state = { range: params.get('range') || '30' };
  const body = h('div');
  main.replaceChildren(pageTitle('bed', 'indigo', 'Sleep'), h('div', { class: 'toolbar' },
    seg([['14', '2 weeks'], ['30', '30 days'], ['90', '90 days'], ['365', '1 year']], state.range, v => { state.range = v; draw(); })), body);
  async function draw() {
    resetPage();
    setParams({ range: state.range });
    loading(body);
    const nights = await api('sleep', { from: daysAgo(+state.range - 1), to: today() });
    if (!nights.length) { body.replaceChildren(card(null, empty('No sleep data in this period.'))); return; }
    const avg = f => { const xs = nights.map(f).filter(v => v != null && isFinite(v)); return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null; };
    // Clock times as minutes from noon, so 23:30 and 00:30 average to midnight.
    const clock = t => { const d = new Date(t * 1000); let m = d.getHours() * 60 + d.getMinutes() - 720; if (m < 0) m += 1440; return m; };
    const fmtClock = m => { if (m == null) return '—'; const x = Math.round(m + 720) % 1440; return `${String(Math.floor(x / 60)).padStart(2, '0')}:${String(x % 60).padStart(2, '0')}`; };
    const beds = nights.filter(n => n.start).map(n => clock(n.start));
    const sd = beds.length > 1 ? Math.sqrt(beds.reduce((a, b) => a + (b - avg(n => n.start ? clock(n.start) : null)) ** 2, 0) / beds.length) : null;
    const stagesChart = h('div', { class: 'chart' }), clockChart = h('div', { class: 'chart' });
    const nightCard = card('Night');
    body.replaceChildren(
      card(null, h('div', { class: 'stats' }, stat('Avg asleep', fmtHM(avg(n => n.asleep))), stat('Avg in bed', fmtHM(avg(n => n.inBed || null))),
        stat('Avg bedtime', fmtClock(avg(n => n.start ? clock(n.start) : null))), stat('Avg wake', fmtClock(avg(n => n.end ? clock(n.end) : null))),
        stat('Bedtime spread', sd == null ? '—' : '±' + fmtNum(sd) + ' min'), stat('Avg deep', fmtHM(avg(n => n.stages.deep))), stat('Avg REM', fmtHM(avg(n => n.stages.rem))),
        stat('Nights ≥ 7 h', fmtNum(nights.filter(n => n.asleep >= 420).length / nights.length * 100) + '%'))),
      card(null, h('div', { class: 'row spread' }, h('h2', {}, 'Sleep stages per night'), csvButton(() => downloadCSV('iohealth-sleep',
        ['night_ending', 'bedtime', 'wake', 'asleep_min', 'in_bed_min', ...STAGES.map(x => x[0] + '_min')],
        nights.map(n => [n.date, n.start ? fmtLocal(n.start) : '', n.end ? fmtLocal(n.end) : '', csvNum(n.asleep, 0), csvNum(n.inBed, 0), ...STAGES.map(x => csvNum(n.stages[x[0]] || 0, 0))])))), stagesChart, h('p', { class: 'small muted' }, 'Click a night for its timeline. When several apps record the same night, the one with the most sleep is used.')),
      h('div', { class: 'grid cols-2' }, card('Bedtime and wake time', clockChart), nightCard));
    const xs = nights.map(n => new Date(n.date + 'T00:00').getTime() / 1000);
    const used = STAGES.filter(([k]) => nights.some(n => n.stages[k] > 0));
    const u = stackedBars(stagesChart, { xs, height: 280, stacks: used.map(([k, label, color]) => ({ label, color, values: nights.map(n => (n.stages[k] || 0)) })),
      valueFmt: fmtHM, axisFmt: v => fmtNum(v / 60) + 'h', incrs: MINUTE_INCRS, xFmt: (u, vals) => vals.map(v => fmtDateShort(v)) });
    u.over.addEventListener('click', () => { if (u.cursor.idx != null) showNight(nights[u.cursor.idx].date); });
    u.over.style.cursor = 'pointer';
    chart(clockChart, { xs, height: 240, incrs: [60, 120, 180, 240, 360], yRange: (u, mn, mx) => [Math.min(mn, 480) - 30, Math.max(mx, 1260) + 30], axisFmt: fmtClock, series: [
      { label: 'Bedtime', color: '#8b5cf6', values: nights.map(n => n.start ? clock(n.start) : null), points: true, width: 1, value: (u, v) => fmtClock(v) },
      { label: 'Wake', color: '#f59e0b', values: nights.map(n => n.end ? clock(n.end) : null), points: true, width: 1, value: (u, v) => fmtClock(v) },
    ] });
    async function showNight(date) {
      nightCard.replaceChildren(h('h2', {}, 'Night of ' + new Date(date + 'T12:00').toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })));
      try {
        const n = await api('sleep', { date });
        nightCard.append(hypnogram(n), h('div', { class: 'stats', style: { marginTop: '12px' } }, stat('Asleep', fmtHM(n.asleep)),
          ...used.map(([k, label]) => stat(label, fmtHM(n.stages[k] || 0)))), h('p', { class: 'small muted' }, 'Source: ' + n.source + ' · ', h('a', { href: '#/day/' + date }, 'The day after →')));
      } catch (e) { nightCard.append(h('p', { class: 'error' }, e.message)); }
    }
    showNight(nights[nights.length - 1].date);
  }
  draw();
};

export function hypnogram(n) {
  const segs = n.segments.filter(s => s.stage !== 'inBed');
  if (!segs.length) return empty('No stage data.');
  const t0 = Math.min(...segs.map(s => s.s)), t1 = Math.max(...segs.map(s => s.e));
  const rows = ['awake', 'rem', 'core', 'deep', 'asleep'].filter(k => segs.some(s => s.stage === k));
  const W = 600, rowH = 26, H = rows.length * rowH + 22;
  const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', preserveAspectRatio: 'none', style: 'max-height:200px' });
  const X = t => 70 + (t - t0) / (t1 - t0) * (W - 80);
  rows.forEach((k, i) => svg.append(s('text', { x: 0, y: i * rowH + 17, 'font-size': 11, fill: cssVar('--muted') }, STAGES.find(x => x[0] === k)[1].replace(' (unspecified)', ''))));
  for (const sg of segs) {
    const i = rows.indexOf(sg.stage);
    if (i < 0) continue;
    svg.append(s('rect', { x: X(sg.s), y: i * rowH + 4, width: Math.max(1, X(sg.e) - X(sg.s)), height: rowH - 8, rx: 3, fill: STAGES.find(x => x[0] === sg.stage)[2],
      onmousemove: e => showTip(e, `${STAGES.find(x => x[0] === sg.stage)[1]} ${fmtTime(sg.s)}–${fmtTime(sg.e)}`), onmouseleave: hideTip }));
  }
  for (let t = Math.ceil(t0 / 3600) * 3600; t < t1; t += 3600) {
    svg.append(s('text', { x: X(t), y: H - 4, 'font-size': 10, fill: cssVar('--muted'), 'text-anchor': 'middle' }, fmtTime(t).replace(/:00/, '')));
  }
  return svg;
}
