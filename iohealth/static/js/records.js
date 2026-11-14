import { activityColor, activityName, empty, fmtDate, fmtDist, fmtDuration, fmtElev, fmtHM, fmtKcal, fmtNum, fmtPace, fmtSpeed, h, paceSports, pages, prettyUnit, scaleFor, sectionOn, typeDec, typeHidden } from './core.js';
import { api, pageTitle } from './shell.js';
import { card } from './charts.js';

// ---------- records ----------

pages.records = async (main) => {
  const showWorkouts = sectionOn('workouts');
  const [rec, eff] = await Promise.all([api('records'), showWorkouts ? api('records/efforts', { type: 'running' }).catch(() => []) : []]);
  rec.records = rec.records.filter(r => r.group === 'workout' ? showWorkouts : !typeHidden(r.type));
  if (!sectionOn('activity')) rec.rings = [];
  const grid = h('div', { class: 'grid cols-3' });
  main.replaceChildren(pageTitle('trophy', 'green', 'Personal records'), grid);
  const fmtRec = r => {
    switch (r.unit) {
      case 's': return fmtDuration(r.value);
      case 'm': return r.name === 'Most climbing' ? fmtElev(r.value) : fmtDist(r.value);
      case 's/km': return paceSports.has(r.type) ? fmtPace(r.value) : fmtSpeed(1000 / r.value);
      case 'kcal': return fmtKcal(r.value);
      default: return fmtNum(r.value * scaleFor(r.unit), typeDec(r.type)) + ' ' + prettyUnit(r.unit);
    }
  };
  const recRow = r => h('div', { class: 'record' }, h('span', {}, r.unit === 's/km' && !paceSports.has(r.type) ? 'Fastest average speed' : r.name, h('div', { class: 'small muted' },
    r.uuid ? h('a', { href: '#/workout/' + r.uuid }, fmtDate(r.when)) : fmtDate(r.when))), h('span', { class: 'rv' }, fmtRec(r)));

  if (eff.length) grid.append(card('Fastest running efforts', ...eff.map(e => h('div', { class: 'record' }, h('span', {}, e.name,
    h('div', { class: 'small muted' }, h('a', { href: '#/workout/' + e.uuid }, fmtDate(e.start)))),
    h('span', { class: 'rv' }, fmtDuration(e.seconds), h('div', { class: 'small muted' }, fmtPace(e.seconds / (e.distance / 1000))))))));
  const days = rec.records.filter(r => r.group === 'day'), health = rec.records.filter(r => r.group === 'health');
  if (days.length) grid.append(card('Best days', ...days.map(recRow)));
  if (health.length) grid.append(card('Health bests', ...health.map(recRow)));
  if (rec.rings?.some(r => r.daysClosed)) grid.append(card('Ring streaks', ...rec.rings.map(r => h('div', { class: 'record' }, h('span', {}, r.ring,
    h('div', { class: 'small muted' }, `${fmtNum(r.daysClosed)} days closed · current streak ${r.current}`)), h('span', { class: 'rv' }, r.longest + ' days',
    h('div', { class: 'small muted' }, r.longest ? 'ended ' + fmtDate(new Date(r.longestEnded + 'T12:00') / 1000) : ''))))));
  const byType = {};
  for (const r of rec.records.filter(r => r.group === 'workout')) (byType[r.type] ||= []).push(r);
  for (const t of (rec.totals || []).map(t => t.activityType)) {
    const tot = rec.totals.find(x => x.activityType === t);
    if (!byType[t]) continue;
    grid.append(card(null, h('h2', { style: { color: activityColor(t) } }, activityName(t)),
      h('p', { class: 'small muted' }, `${fmtNum(tot.count)} workouts since ${fmtDate(tot.first)} · ${fmtHM(tot.duration / 60)}${tot.distance ? ' · ' + fmtDist(tot.distance, 0) : ''}`),
      ...byType[t].map(recRow)));
  }
  if (!grid.children.length) grid.append(card(null, empty('No records yet.')));
};
