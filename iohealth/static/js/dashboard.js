import { DAY, MINUTE_INCRS, activityColor, activityName, alertSetting, cssVar, daysAgo, empty, fmtAgo, fmtCompact, fmtDate, fmtDateTime, fmtDayAgo, fmtDist, fmtDuration, fmtElev, fmtHM, fmtKcal, fmtNum, fmtPace, fmtSpeed, fmtTime, goalFor, goalMet, h, isoDate, paceSports, pages, prettyUnit, scaleFor, sectionOn, today, typeDec, typeLabel, typeList } from './core.js';
import { api, pageTitle, settings } from './shell.js';
import { card, rings, slopePerDay, sparkline, stackedBars, stat } from './charts.js';
import { fmtG, gUnit, pct, rangeBar, rangeLegend } from './glucose.js';

// ---------- dashboard ----------

export const DASH_KPIS = ['step_count', 'active_energy_burned', 'apple_exercise_time', 'distance_walking_running', 'flights_climbed',
  'resting_heart_rate', 'heart_rate_variability_sdnn', 'walking_heart_rate_average', 'vo2_max', 'body_mass', 'respiratory_rate',
  'oxygen_saturation', 'time_in_daylight', 'apple_sleeping_wrist_temperature'];

pages.dashboard = async (main) => {
  const types = await typeList();
  main.replaceChildren();
  const top = h('div', { class: 'grid cols-2' });
  const ringsCard = card('Activity rings');
  const sleepCard = card('Last night');
  const show = { activity: sectionOn('activity'), sleep: sectionOn('sleep'), workouts: sectionOn('workouts') };
  if (show.activity) top.append(ringsCard);
  if (show.sleep) top.append(sleepCard);
  const kpis = h('div', { class: 'grid kpis' });
  const workoutsCard = card('Recent workouts');
  const weeklyCard = card('Training volume, last 12 weeks');
  const glucoseCard = types.blood_glucose && sectionOn('glucose') ? card('Blood glucose, last 14 days') : null;
  const alertList = h('div', { class: 'alerts' });
  const alertsCard = card('Heads-up', alertList);
  alertsCard.hidden = true;
  alertsCard.style.marginBottom = '16px';
  // level: good, warn or bad; shown most serious first.
  const addAlert = (level, text, href) => {
    alertsCard.hidden = false;
    const el = h('div', { class: 'alert ' + level, 'data-rank': { bad: 0, warn: 1, good: 2 }[level] }, h('span', {}, { bad: '⚠️', warn: '⚠️', good: '✅' }[level]), h('span', {}, text),
      href ? h('a', { href, class: 'small noprint' }, 'Look →') : null);
    const after = [...alertList.children].find(c => +c.dataset.rank > +el.dataset.rank);
    alertList.insertBefore(el, after || null);
  };
  main.append(...[h('div', { class: 'row spread' }, pageTitle('dashboard', 'purple', 'Dashboard'), h('a', { href: '#/day', class: 'small' }, 'Today in detail →')), alertsCard,
    top.children.length ? top : null, glucoseCard, h('div', { style: { height: '16px' } }), kpis,
    show.workouts ? h('div', { class: 'grid cols-2' }, workoutsCard, weeklyCard) : null].filter(Boolean));

  // Rings: today big, the week small.
  if (show.activity) api('activity', { from: daysAgo(6), to: today() }).then(days => {
    const byDate = Object.fromEntries(days.map(d => [d.date, d]));
    const t = byDate[today()] || days[days.length - 1];
    const row = h('div', { class: 'rings-row' });
    for (let i = 6; i >= 0; i--) {
      const d = daysAgo(i);
      row.append(h('div', { class: 'ring-day' }, rings(byDate[d], 44), h('div', {}, new Date(d + 'T12:00').toLocaleDateString(undefined, { weekday: 'narrow' }))));
    }
    if (!t) { ringsCard.append(empty('No activity summaries yet.')); return; }
    const line = (label, v, goal, unit, color) => h('div', {}, h('div', { class: 'small muted' }, label),
      h('div', { style: { fontSize: '20px', fontWeight: 700, color: cssVar(color) } }, `${fmtNum(v, 0)}/${fmtNum(goal, 0)}`, h('small', { class: 'muted' }, ' ' + unit)));
    ringsCard.append(h('div', { class: 'row', style: { gap: '24px' } }, rings(t, 130),
      h('div', { class: 'grid', style: { gap: '8px' } }, line('Move', t.move, t.moveGoal, 'kcal', '--move'),
        line('Exercise', t.exercise, t.exerciseGoal, 'min', '--exercise'), line('Stand', t.stand, t.standGoal, 'h', '--stand')),
      row), h('p', { class: 'small muted' }, t.date === today() ? 'Today' : 'Latest day: ' + t.date));
  }).catch(e => ringsCard.append(h('p', { class: 'error' }, e.message)));

  if (glucoseCard) api('glucose', { from: daysAgo(13), to: today(), low: settings.glucoseLow || 70, high: settings.glucoseHigh || 180 }).then(g => {
    if (!settings.glucoseUnit) settings.glucoseUnit = g.recordedUnit;
    const st = g.stats;
    if (!st.readings) { glucoseCard.append(empty('No readings in the last 14 days.')); return; }
    const last = g.readings[g.readings.length - 1];
    glucoseCard.append(h('div', { class: 'stats' }, stat('Latest', fmtG(last[1]), gUnit()), stat('Average', fmtG(st.mean), gUnit()),
      stat('Time in range', pct(st.ranges.inRange)), stat('Below range', pct(st.ranges.low + st.ranges.veryLow)), stat('GMI', fmtNum(st.gmi, 1), '%'), stat('CV', fmtNum(st.cv, 1), '%')),
    h('div', { style: { marginTop: '12px' } }, rangeBar(st.ranges, 14)), rangeLegend(st.ranges, g.target),
    h('p', { class: 'small muted' }, 'Latest reading ', fmtAgo(last[0]), ' · ', h('a', { href: '#/glucose' }, 'Glucose details →')));
  }).catch(e => glucoseCard.append(h('p', { class: 'error' }, e.message)));

  // Sleep
  if (show.sleep) api('sleep', { from: daysAgo(14), to: today() }).then(nights => {
    if (!nights.length) { sleepCard.append(empty('No sleep data in the last two weeks.')); return; }
    const last = nights[nights.length - 1];
    const avg = nights.reduce((a, n) => a + n.asleep, 0) / nights.length;
    sleepCard.append(h('div', { class: 'stats' },
      stat('Asleep', fmtHM(last.asleep)), stat('Bedtime', last.start ? fmtTime(last.start) : '—'), stat('Woke up', last.end ? fmtTime(last.end) : '—'),
      stat('Deep', fmtHM(last.stages.deep)), stat('REM', fmtHM(last.stages.rem)), stat('14-night average', fmtHM(avg))),
    h('div', { style: { marginTop: '10px' } }, sparkline(nights.map(n => n.asleep / 60), { bars: true, color: '#8b5cf6', h: 44 })),
    h('p', { class: 'small muted' }, `Night of ${last.date} · `, h('a', { href: '#/sleep' }, 'Sleep details')));
  }).catch(e => sleepCard.append(h('p', { class: 'error' }, e.message)));

  dashboardAlerts(types, addAlert);

  // KPI cards: the usual ones plus any metric with a goal.
  const shown = [...new Set([...DASH_KPIS, ...(settings.goals || []).map(g => g.type)])].filter(t => types[t]);
  if (!shown.length) kpis.append(card(null, empty('No samples yet. Sync from the iPhone app and they show up here.')));
  for (const t of shown) {
    const info = types[t];
    const el = h('section', { class: 'card kpi', onclick: () => location.hash = t === 'blood_glucose' ? '#/glucose' : '#/metrics?types=' + t + '&range=90d' },
      h('div', { class: 'label' }, typeLabel(t)), h('div', { class: 'value' }, '…'));
    kpis.append(el);
    api('series', { type: t, from: daysAgo(59), to: today(), bucket: 'day' }).then(async sr => {
      const k = scaleFor(sr.unit), pts = sr.points;
      if (!pts.length) {
        // Nothing in the last 60 days: show the latest reading, however old, with its date.
        const lastDay = !info.cumulative && info.last ? isoDate(new Date(info.last * 1000)) : null;
        const old = lastDay ? (await api('series', { type: t, from: lastDay, to: lastDay, bucket: 'day' })).points.at(-1) : null;
        if (!old) { el.querySelector('.value').textContent = '—'; return; }
        el.querySelector('.value').replaceChildren(fmtNum(old.v * k, typeDec(t)), h('small', {}, prettyUnit(info.unit === '%' ? '%' : sr.unit)));
        el.append(h('div', { class: 'sub' }, 'last on ', fmtDayAgo(old.t), ' · none in 60 days'));
        return;
      }
      const byDay = new Map(pts.map(p => [isoDate(new Date(p.t * 1000)), p.v * k]));
      const vals = []; for (let i = 59; i >= 0; i--) vals.push(byDay.get(daysAgo(i)) ?? null);
      const last = pts[pts.length - 1];
      const avg = arr => { const xs = arr.filter(v => v != null); return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null; };
      const recent = avg(vals.slice(-7)), before = avg(vals.slice(-35, -7));
      const unit = prettyUnit(info.unit === '%' ? '%' : sr.unit);
      const headline = info.cumulative ? (byDay.get(today()) ?? 0) : last.v * k;
      const delta = recent != null && before ? (recent - before) / Math.abs(before) * 100 : null;
      const goal = goalFor(t);
      if (goal) goalNotes(t, goal, info, vals, last.v * k, unit, el, addAlert);
      const lowerIsBetter = ['resting_heart_rate', 'walking_heart_rate_average', 'respiratory_rate'].includes(t);
      const cls = delta == null || Math.abs(delta) < 2 ? 'flat' : (delta > 0) !== lowerIsBetter ? 'up' : 'down';
      const dec = t === 'blood_glucose' && /^mmol/i.test(sr.unit) ? 1 : typeDec(t);
      el.querySelector('.value').replaceChildren(fmtNum(headline, dec), h('small', {}, unit));
      el.append(h('div', { class: 'sub' }, info.cumulative ? 'today' : fmtDayAgo(last.t),
        ' · 7-day avg ', fmtNum(recent, typeDec(t)), delta != null ? h('span', { class: cls }, ` ${delta > 0 ? '▲' : '▼'} ${fmtNum(Math.abs(delta), 0)}%`) : null),
      sparkline(vals, { bars: info.cumulative, goal: goal ? +goal.value : null }));
      if (goal) el.append(el.querySelector('.goal-note'));
    }).catch(e => el.append(h('div', { class: 'sub error' }, e.message)));
  }

  // Workouts
  if (show.workouts) api('workouts', { from: daysAgo(83), to: today() }).then(ws => {
    if (!ws.length) { workoutsCard.append(empty('No workouts in the last 12 weeks.')); weeklyCard.append(empty('Nothing to show yet.')); return; }
    workoutsCard.append(workoutTable(ws.slice(0, 8), { compact: true }), h('p', { class: 'small' }, h('a', { href: '#/workouts' }, 'All workouts →')));
    const chartEl = h('div', { class: 'chart' });
    weeklyCard.append(chartEl);
    weeklyChart(chartEl, ws, 12);
  }).catch(e => workoutsCard.append(h('p', { class: 'error' }, e.message)));
};

// goalNotes adds a goal line to a dashboard card and raises streaks, misses and trends as alerts. vals are the last
// 60 days (today last) in the units shown.
export function goalNotes(t, goal, info, vals, latest, unit, el, addAlert) {
  const label = typeLabel(t), target = +goal.value, dec = typeDec(t);
  const word = goal.dir === 'max' ? 'at most' : 'at least';
  const note = h('div', { class: 'sub goal-note' });
  el.append(note);
  const daily = info.cumulative || info.kind === 'ring' || t === 'sleep_analysis';
  if (daily) {
    const todayMet = goalMet(goal, vals[vals.length - 1]);
    const past = vals.slice(0, -1);
    const met7 = past.slice(-7).filter(v => goalMet(goal, v)).length;
    let streak = 0;
    for (let i = past.length - 1; i >= 0 && goalMet(goal, past[i]); i--) streak++;
    if (todayMet) streak++;
    note.append(`Goal ${word} ${fmtNum(target, dec)} · met ${met7} of the last 7 days`, streak >= 2 ? ` · ${streak}-day streak` : '');
    if (streak >= 3) addAlert('good', `${label}: goal met ${streak} days in a row.`, '#/metrics?types=' + t + '&range=30d');
    else if (past.slice(-3).length === 3 && past.slice(-3).every(v => v != null && !goalMet(goal, v)) && !todayMet)
      addAlert('warn', `${label}: goal (${word} ${fmtNum(target, dec)}) missed the last 3 days.`, '#/metrics?types=' + t + '&range=30d');
    return;
  }
  // A level to reach (weight, resting heart rate…): how far, and whether the 30-day trend heads there.
  if (goalMet(goal, latest)) {
    note.append(`Goal ${word} ${fmtNum(target, dec)} · reached`);
    addAlert('good', `${label} is at your goal (${word} ${fmtNum(target, dec)} ${unit}).`, '#/metrics?types=' + t + '&range=90d');
    return;
  }
  const gap = Math.abs(target - latest);
  const recent = vals.slice(-30).map((v, i) => [i * DAY, v]).filter(p => p[1] != null);
  const slope = recent.length >= 5 ? slopePerDay(recent) : null; // per day
  const toward = slope != null && (target - latest) * slope > 0;
  let eta = '';
  if (toward && Math.abs(slope) > 1e-9) {
    const days = gap / Math.abs(slope);
    if (days < 365) eta = ' · on track for ' + fmtDayAgo(Date.now() / 1000 + days * DAY);
  }
  note.append(`Goal ${word} ${fmtNum(target, dec)} · ${fmtNum(gap, dec)} to go${eta}`);
  if (slope != null && !toward && Math.abs(slope * 30) > Math.abs(latest) * 0.005)
    addAlert('warn', `${label} is moving away from your goal: ${slope > 0 ? '+' : '−'}${fmtNum(Math.abs(slope * 30), dec)} ${unit} over 30 days (goal ${word} ${fmtNum(target, dec)}).`, '#/metrics?types=' + t + '&range=90d');
}

// dashboardAlerts: things worth a look, from the alert settings.
export function dashboardAlerts(types, addAlert) {
  const syncH = alertSetting('sync');
  if (syncH > 0) api('status', {}, { cache: false }).then(st => {
    const t = st.lastSync?.finished || st.lastSync?.started;
    if (t && Date.now() / 1000 - t > syncH * 3600) addAlert('warn', `No sync from the iPhone for ${fmtAgo(t).replace(' ago', '')}. Open the app on the phone to send the latest data.`);
  }).catch(() => {});
  if (types.blood_glucose && sectionOn('glucose')) {
    api('glucose', { from: daysAgo(6), to: today(), low: +settings.glucoseLow || 70, high: +settings.glucoseHigh || 180 }).then(g => {
      const st = g.stats;
      if (!st.readings || st.perDay < 50) return;
      const tir = st.ranges.inRange * 100, want = alertSetting('tir'), lows = alertSetting('lows');
      if (lows > 0 && st.lows >= lows) addAlert('bad', `${st.lows} low${st.lows === 1 ? '' : 's'} (under ${fmtG(g.target[0])} ${gUnit()} for 15 minutes or more) in the last 7 days.`, '#/glucose?range=7');
      if (want > 0 && tir < want) addAlert('warn', `Glucose time in range was ${fmtNum(tir, 0)}% over the last 7 days, under your ${fmtNum(want, 0)}% target.`, '#/glucose?range=7');
      else if (want > 0) addAlert('good', `Glucose time in range ${fmtNum(tir, 0)}% over the last 7 days.`, '#/glucose?range=7');
    }).catch(() => {});
  }
  // outside your usual (resting heart rate, heart rate variability, sleep): worked out by the server, which also sends it as a notification
  api('usual', {}, { cache: false }).then(found => { for (const f of found) addAlert('warn', `${f.title}: ${f.body}`, f.href); }).catch(() => {});
}

export function mondayOf(t) { const d = new Date(t * 1000); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - (d.getDay() + 6) % 7); return d; }

// weeklyChart: workout minutes per week, stacked by activity type.
export function weeklyChart(el, ws, weeks, { height = 240, monthly = false } = {}) {
  const startOf = monthly ? (t => { const d = new Date(t * 1000); return new Date(d.getFullYear(), d.getMonth(), 1); }) : mondayOf;
  const end = startOf(Date.now() / 1000);
  const xs = [];
  for (let i = weeks - 1; i >= 0; i--) {
    const d = new Date(end);
    if (monthly) d.setMonth(d.getMonth() - i); else d.setDate(d.getDate() - 7 * i);
    xs.push(d.getTime() / 1000);
  }
  const index = new Map(xs.map((x, i) => [x, i]));
  const byType = {};
  for (const w of ws) {
    const i = index.get(startOf(w.start).getTime() / 1000);
    if (i == null) continue;
    (byType[w.activityType] ||= xs.map(() => 0))[i] += w.duration / 60;
  }
  const order = Object.entries(byType).sort((a, b) => b[1].reduce((x, y) => x + y) - a[1].reduce((x, y) => x + y));
  const stacks = order.map(([t, values]) => ({ label: activityName(t), color: activityColor(t), values }));
  if (!stacks.length) { el.append(empty('No workouts in this period.')); return; }
  stackedBars(el, { xs, stacks, height, valueFmt: v => fmtHM(v), axisFmt: v => fmtCompact(v / 60) + 'h', incrs: MINUTE_INCRS });
}

export function workoutTable(ws, { compact = false } = {}) {
  const tb = h('tbody');
  for (const w of ws) {
    const pace = w.distance > 0 && paceSports.has(w.activityType) ? fmtPace(w.duration / (w.distance / 1000)) : w.distance > 0 ? fmtSpeed(w.distance / w.duration) : '';
    tb.append(h('tr', { class: 'click', onclick: () => location.hash = '#/workout/' + w.uuid },
      h('td', {}, h('span', { class: 'chip', style: { color: activityColor(w.activityType), padding: '1px 8px' } }, h('span', { class: 'dot', style: { background: activityColor(w.activityType) } }), activityName(w.activityType)),
        w.hasRoute ? ' 📍' : ''),
      h('td', {}, compact ? fmtDate(w.start) : fmtDateTime(w.start)),
      h('td', { class: 'r num' }, fmtDuration(w.duration)),
      h('td', { class: 'r num' }, w.distance ? fmtDist(w.distance) : ''),
      compact ? null : h('td', { class: 'r num' }, pace),
      h('td', { class: 'r num' }, w.energy ? fmtKcal(w.energy) : ''),
      h('td', { class: 'r num' }, w.hrAvg ? fmtNum(w.hrAvg, 0) + ' bpm' : ''),
      compact ? null : h('td', { class: 'r num' }, w.elevation ? fmtElev(w.elevation) : ''),
      compact ? null : h('td', { class: 'muted' }, w.source)));
  }
  return h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'Workout'), h('th', {}, 'Date'), h('th', { class: 'r' }, 'Time'),
    h('th', { class: 'r' }, 'Distance'), compact ? null : h('th', { class: 'r' }, 'Pace / speed'), h('th', { class: 'r' }, 'Energy'), h('th', { class: 'r' }, 'Avg HR'),
    compact ? null : h('th', { class: 'r' }, 'Climb'), compact ? null : h('th', {}, 'Source'))), tb);
}
