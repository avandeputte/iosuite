import { $, DOW, LOCAL_TZ, S, addDays, addMonths, api, calOf, colorOf, dayStart, dialog, fail, fmtDay, fmtTime, h, icon, memberBadge, memberOf, openTask, pad2, passesWho, sameDay, shownCals, span, startOfWeek, taskChip, taskOcc, taskTitle, tasksOn, tickBtn, billAmount, billChip, billOcc, billTitle, billsOn, openBill, paperChip, paperOcc, paperTitle, papersOn, openPaper, toast, weekStart, whenText, ymd } from './core.js';
import { drawNav } from './shell.js';
import { openEvent } from './event.js';
import { go } from './main.js';
import { dayWeather, loadWeather } from './weather.js';

// ------------------------------------------------------------------ the calendar views
export const daysBetween = (a, b) => Math.round((dayStart(b) - dayStart(a)) / 864e5);
export function viewRange() {
  const d = S.date;
  if (S.view === 'month') {
    const s = startOfWeek(new Date(d.getFullYear(), d.getMonth(), 1));
    const last = new Date(d.getFullYear(), d.getMonth() + 1, 0);
    return [s, addDays(s, Math.ceil((daysBetween(s, last) + 1) / 7) * 7)];
  }
  if (S.view === 'week') { const s = startOfWeek(d); return [s, addDays(s, 7)]; }
  if (S.view === 'agenda') { const s = dayStart(d); return [s, addDays(s, S.agendaDays || 31)]; }
  const s = dayStart(d); return [s, addDays(s, 1)];
}
export function viewTitle() {
  const d = S.date;
  if (S.view === 'month') return d.toLocaleDateString([], { month: 'long', year: 'numeric' });
  if (S.view === 'day') return d.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
  if (S.view === 'agenda') return sameDay(d, new Date()) ? 'Coming up' : `From ${d.toLocaleDateString([], { month: 'long', day: 'numeric', year: 'numeric' })}`;
  const s = startOfWeek(d), e = addDays(s, 6);
  if (s.getMonth() === e.getMonth()) return `${s.toLocaleDateString([], { month: 'long' })} ${s.getDate()} – ${e.getDate()}, ${e.getFullYear()}`;
  return `${s.toLocaleDateString([], { month: 'short', day: 'numeric', year: s.getFullYear() !== e.getFullYear() ? 'numeric' : undefined })} – ${e.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })}`;
}
export function stepView(n) {
  if (S.view === 'month') go('month', addMonths(S.date, n));
  else go(S.view, addDays(S.date, n * ({ week: 7, agenda: 30 }[S.view] || 1)));
}
export function calbar() {
  return h('div', { class: 'calbar' },
    h('button', { class: 'pillbtn noic', title: 'Today (t)', onclick: () => go(S.view, new Date()) }, 'Today'),
    h('button', { class: 'iconbtn', title: 'Earlier (←)', onclick: () => stepView(-1) }, icon('chevL')),
    h('button', { class: 'iconbtn', title: 'Later (→)', onclick: () => stepView(1) }, icon('chevR')),
    h('h1', null, viewTitle()), h('span', { class: 'grow' }),
    h('div', { class: 'seg', role: 'tablist' }, [['day', 'Day', 'd'], ['week', 'Week', 'w'], ['month', 'Month', 'm'], ['agenda', 'Agenda', 'a']].map(([v, l, k]) =>
      h('button', { class: S.view === v ? 'on' : '', title: `${l} (${k})`, onclick: () => go(v, S.date) }, l))));
}

/** Occurrences by day (YYYY-MM-DD) for the days given: a long event is on each of its days. */
export function byDay(days, items) {
  const m = new Map(days.map((d) => [ymd(d), []]));
  for (const o of items) {
    const [a, b] = span(o);
    const last = o.allDay ? addDays(b, -1) : new Date(Math.max(+a, +b - 1));
    for (let d = dayStart(a); d <= last; d = addDays(d, 1)) { const l = m.get(ymd(d)); if (l) l.push(o); }
  }
  return m;
}
/** Spans more than one day: drawn as a bar (month) or in the all-day row (week). */
export const longEvent = (o) => { if (o.allDay) return true; const [a, b] = span(o); return b - a >= 864e5; };

/** A day's entries in order: what takes the whole day (events, then the tasks without a time), then by time. */
export const dayOrder = (x, y) => longEvent(y) - longEvent(x) || (longEvent(x) ? !!(x.task || x.bill || x.paper) - !!(y.task || y.bill || y.paper) : 0) || span(x)[0] - span(y)[0];

export let drawSeq = 0;
export async function drawView() {
  const main = $('#main');
  main.classList.remove('showdetail');
  const [s, e] = viewRange();
  const seq = ++drawSeq;
  const ids = shownCals().map((c) => c.id);
  const [occ, tasks, , bills, papers] = await Promise.all([
    ids.length ? api(`api/occurrences?start=${encodeURIComponent(s.toISOString())}&end=${encodeURIComponent(e.toISOString())}&calendars=${ids.join(',')}`) : { items: [] },
    tasksOn() ? api(`api/tasks?start=${ymd(s)}&end=${ymd(e)}&tz=${encodeURIComponent(LOCAL_TZ)}`).catch((x) => ({ available: false, reason: x.message, items: [] })) : null,
    loadWeather(),
    billsOn() ? api(`api/bills?start=${ymd(s)}&end=${ymd(e)}`).catch((x) => ({ available: false, reason: x.message, items: [] })) : null,
    papersOn() ? api(`api/papers?start=${ymd(s)}&end=${ymd(e)}`).catch((x) => ({ available: false, reason: x.message, items: [] })) : null]);
  if (seq !== drawSeq) return;
  if (tasks) {
    const was = `${S.tasks.available}|${S.tasks.url}`;
    S.tasks = tasks;
    if (was !== `${tasks.available}|${tasks.url}`) drawNav();  // the link to ioTask, or why its tasks are not here
  }
  if (bills) {
    const was = `${S.bills.available}|${S.bills.reason}`;
    S.bills = bills;
    if (was !== `${bills.available}|${bills.reason}`) drawNav();  // ioMoney's bills offered, or why they are not here
  }
  if (papers) {
    const was = `${S.papers.available}|${S.papers.reason}`;
    S.papers = papers;
    if (was !== `${papers.available}|${papers.reason}`) drawNav();  // ioDocs' documents offered, or why they are not here
  }
  S.occ = [...occ.items, ...(tasks ? tasks.items.map(taskOcc) : []), ...(papers ? papers.items.map(paperOcc) : [])].filter(passesWho)
    .concat(bills ? bills.items.map(billOcc) : []);
  const body = h('div', { class: 'calbody' });
  const key = `${S.view}|${ymd(s)}`;
  const keep = S.drawn === key ? main.querySelector('.calbody')?.scrollTop : undefined;
  S.drawn = key;
  main.replaceChildren(h('div', { class: 'calpage' }, calbar(), body));
  ({ month: drawMonth, week: drawWeek, day: drawWeek, agenda: drawAgenda })[S.view](body, s, e, keep);
}

export const canChange = (o) => !!calOf(o.calendarId).writable;
export function chip(o, day) {
  if (o.task) return taskChip(o);
  if (o.bill) return billChip(o);
  if (o.paper) return paperChip(o);
  const [a] = span(o);
  const long = longEvent(o);
  const el = h('div', { class: ['chip-ev', long ? 'allday' : '', o.status === 'CANCELLED' ? 'cancelled' : '', o.status === 'TENTATIVE' ? 'tentative' : ''].join(' '),
    style: { '--c': colorOf(o.calendarId) }, title: `${o.title || '(no title)'}\n${whenText(o)}${o.location ? '\n' + o.location : ''}`,
    draggable: canChange(o) ? 'true' : null,
    onclick: (ev) => { ev.stopPropagation(); openEvent(o); } },
  long ? null : h('span', { class: 'dot' }), !long && sameDay(a, day) ? h('span', { class: 't' }, fmtTime(a)) : null, h('span', { class: 'nm' }, o.title || '(no title)'),
  (o.members || []).map(memberOf).filter(Boolean).map(memberBadge));
  el.addEventListener('dragstart', (ev) => { S.drag = { o, from: day, grabMin: 0 }; ev.dataTransfer.effectAllowed = 'move'; ev.dataTransfer.setData('text/plain', o.title || ''); });
  return el;
}

export function drawMonth(body, s, e) {
  const weeks = Math.round(daysBetween(s, e) / 7);
  const days = Array.from({ length: weeks * 7 }, (_, i) => addDays(s, i));
  const map = byDay(days, S.occ), today = new Date(), month = S.date.getMonth();
  const grid = h('div', { class: 'month', style: { '--weeks': weeks } },
    h('div', { class: 'dows' }, [0, 1, 2, 3, 4, 5, 6].map((i) => h('div', null, DOW((i + weekStart()) % 7)))));
  for (let w = 0; w < weeks; w++) {
    const row = h('div', { class: 'wk' });
    for (const d of days.slice(w * 7, w * 7 + 7)) {
      const list = map.get(ymd(d)).slice().sort(dayOrder);
      const cell = h('div', { class: ['mday', d.getMonth() !== month ? 'other' : '', sameDay(d, today) ? 'today' : ''].join(' '),
        onclick: () => newAt(d), title: 'New event' },
      h('span', { class: 'dnum', title: 'Open the day', onclick: (ev) => { ev.stopPropagation(); go('day', d); } }, d.getDate() === 1 ? d.toLocaleDateString([], { month: 'short', day: 'numeric' }) : d.getDate()),
      dayWeather(d), list.map((o) => chip(o, d)));
      dropTarget(cell, (o) => moveBy(o, daysBetween(S.drag.from, d) * 864e5, true));
      row.append(cell);
    }
    grid.append(row);
  }
  body.append(grid);
  // as many chips as fit; the rest behind "N more"
  requestAnimationFrame(() => grid.querySelectorAll('.mday').forEach((cell) => {
    const chips = [...cell.querySelectorAll('.chip-ev')];
    const fit = Math.max(1, Math.floor((cell.clientHeight - 34) / 24));
    if (chips.length <= fit) return;
    chips.slice(fit - 1).forEach((c) => { c.hidden = true; });
    const n = chips.length - fit + 1;
    const d = days[[...grid.querySelectorAll('.mday')].indexOf(cell)];
    cell.append(h('div', { class: 'more', onclick: (ev) => { ev.stopPropagation(); dayList(d, map.get(ymd(d))); } }, `${n} more`));
  }));
}
export function dayList(d, list) {
  const body = h('div', { style: { display: 'flex', flexDirection: 'column', gap: '2px', minWidth: '280px' } }, list.map((o) => chip(o, d)));
  body.addEventListener('click', () => document.querySelector('.dialog-back')?.remove());
  dialog(fmtDay(d), body, [{ label: 'Open the day', value: () => go('day', d) }, { label: 'Close', value: null, primary: true }]);
}
export function dropTarget(el, done) {
  el.addEventListener('dragover', (ev) => { if (!S.drag) return; ev.preventDefault(); el.classList.add('drop'); });
  el.addEventListener('dragleave', () => el.classList.remove('drop'));
  el.addEventListener('drop', (ev) => { ev.preventDefault(); el.classList.remove('drop'); if (S.drag) { const o = S.drag.o; done(o, ev); S.drag = null; } });
}

/** Move an occurrence by ms (whole days for all-day events), asking which ones when it repeats. */
export async function moveBy(o, ms, days) {
  if (!ms) return;
  const [a, b] = span(o);
  let data;
  if (o.allDay) {
    const n = Math.round(ms / 864e5);
    if (!n) return;
    data = { start: ymd(addDays(a, n)), end: ymd(addDays(b, n)) };
  } else if (days) {
    const n = Math.round(ms / 864e5);
    data = { start: addDays(a, n).toISOString(), end: addDays(b, n).toISOString() };
  } else data = { start: new Date(+a + ms).toISOString(), end: new Date(+b + ms).toISOString() };
  await saveOccurrence(o, data, 'Move');
}
export async function saveOccurrence(o, data, verb) {
  let scope = 'all';
  if (o.recurring && o.recurrenceId) { scope = await askScope(verb); if (!scope) return; }
  const qs = o.recurrenceId ? `?scope=${scope}&recurrenceId=${encodeURIComponent(o.recurrenceId)}` : '';
  try { await api(`api/events/${o.id}${qs}`, { method: 'PATCH', json: data }); toast('Moved'); } catch (e) { fail(e); }
  drawView();
}
export function askScope(verb) {
  const v = verb.toLowerCase();
  return dialog(`${verb} a repeating event`, h('p', null, `${verb} only this one, this one and the ones after it, or every one?`),
    [{ label: 'Cancel', value: null }, { label: 'This one', value: 'this' }, { label: 'This and later', value: 'following' }, { label: `All of them`, value: 'all', primary: v !== 'delete', danger: v === 'delete' }]);
}
export function newAt(d, time) {
  const q = new URLSearchParams({ date: ymd(d) });
  if (time) q.set('time', time);
  location.hash = `#/new?${q}`;
}

// week and day: a column per day, hours down the side
export const HH = 48;
export function drawWeek(body, s, e, keep) {
  const n = S.view === 'day' ? 1 : 7;
  const days = Array.from({ length: n }, (_, i) => addDays(s, i));
  const map = byDay(days, S.occ), today = new Date();
  const grid = h('div', { class: 'tgrid', style: { '--days': n, '--hh': `${HH}px` } });
  grid.append(h('div', { class: 'head' }), ...days.map((d) => h('div', { class: `head thead-day ${sameDay(d, today) ? 'today' : ''}`, onclick: () => go('day', d) },
    h('div', { class: 'dow' }, DOW(d.getDay(), n === 1 ? 'long' : 'short')), h('span', { class: `dnum ${sameDay(d, today) ? 'today' : ''}` }, d.getDate()), dayWeather(d, true))));
  grid.append(h('div', { class: 'alldaylabel' }, 'all day'), ...days.map((d) => {
    const cell = h('div', { class: 'alldayrow', onclick: () => location.hash = `#/new?date=${ymd(d)}&allday=1` }, map.get(ymd(d)).filter(longEvent).map((o) => chip(o, d)));
    dropTarget(cell, (o) => moveBy(o, daysBetween(S.drag.from, d) * 864e5, true));
    return cell;
  }));
  const hours = h('div', { class: 'hours' }, Array.from({ length: 24 }, (_, i) => h('div', { class: 'hour' }, i ? new Date(2026, 0, 1, i).toLocaleTimeString([], { hour: 'numeric' }) : '')));
  grid.append(hours);
  days.forEach((d) => {
    const col = h('div', { class: `dcol ${sameDay(d, today) ? 'today' : ''}` });
    const minAt = (ev) => Math.max(0, Math.min(1440 - 15, Math.round((ev.clientY - col.getBoundingClientRect().top) / HH * 60 / 15) * 15));
    col.addEventListener('click', (ev) => { if (ev.target !== col) return; const m = Math.floor(minAt(ev) / 30) * 30; newAt(d, `${pad2(m / 60 | 0)}:${pad2(m % 60)}`); });
    dropTarget(col, (o, ev) => {
      const m = minAt(ev) - (S.drag.grabMin || 0);
      const [a] = span(o);
      const to = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, Math.round(m / 15) * 15);
      if (o.allDay) return; // an all-day event stays one
      moveBy(o, to - a, false);
    });
    const lay = layout(map.get(ymd(d)).filter((o) => !longEvent(o)), d);
    for (const x of lay) {
      const o = x.o, [a, b] = span(o);
      if (o.task) {
        col.append(h('div', { class: `tev task ${o.done ? 'done' : ''}`, title: taskTitle(o), onclick: (ev) => { ev.stopPropagation(); openTask(o); },
          style: { '--c': o.color || 'var(--brand)', top: `${x.top / 60 * HH}px`, height: `${(x.bottom - x.top) / 60 * HH - 2}px`,
            left: `calc(${x.col / x.cols * 100}% + 1px)`, width: `calc(${100 / x.cols}% - 3px)` } }, tickBtn(o), h('span', { class: 'nm' }, o.title)));
        continue;
      }
      const el = h('div', { class: ['tev', o.status === 'CANCELLED' ? 'cancelled' : '', o.busy === false ? 'free' : ''].join(' '),
        style: { '--c': colorOf(o.calendarId), top: `${x.top / 60 * HH}px`, height: `${Math.max(18, (x.bottom - x.top) / 60 * HH - 2)}px`,
          left: `calc(${x.col / x.cols * 100}% + 1px)`, width: `calc(${100 / x.cols}% - 3px)` },
        title: `${o.title || '(no title)'}\n${whenText(o)}${o.location ? '\n' + o.location : ''}`, draggable: canChange(o) ? 'true' : null,
        onclick: (ev) => { ev.stopPropagation(); openEvent(o); } },
      h('div', { class: 'nm' }, o.title || '(no title)'),
      x.bottom - x.top >= 45 ? h('div', { class: 't' }, `${fmtTime(a)} – ${fmtTime(b)}`) : null,
      x.bottom - x.top >= 75 && o.location ? h('div', { class: 't' }, o.location) : null);
      el.addEventListener('dragstart', (ev) => {
        S.drag = { o, from: d, grabMin: Math.round((ev.clientY - el.getBoundingClientRect().top) / HH * 60 / 15) * 15 };
        ev.dataTransfer.effectAllowed = 'move'; ev.dataTransfer.setData('text/plain', o.title || '');
      });
      col.append(el);
    }
    if (sameDay(d, today)) col.append(h('div', { class: 'nowline', style: { top: `${(today.getHours() * 60 + today.getMinutes()) / 60 * HH}px` } }));
    grid.append(col);
  });
  body.append(grid);
  const now = new Date();
  body.scrollTop = keep ?? (days.some((d) => sameDay(d, now)) ? Math.max(0, (now.getHours() - 2) * HH) : 7 * HH);
}
/** Timed occurrences of one day, side by side where they overlap: [{o, top, bottom (minutes), col, cols}]. */
export function layout(list, d) {
  const d0 = dayStart(d), d1 = addDays(d0, 1);
  const xs = list.map((o) => {
    const [a, b] = span(o);
    const top = (Math.max(a, d0) - d0) / 6e4, bottom = (Math.min(Math.max(b, +a + 15 * 6e4), d1) - d0) / 6e4;
    return { o, top, bottom: Math.max(bottom, top + 15) };
  }).sort((x, y) => x.top - y.top || y.bottom - x.bottom);
  let group = [], cols = [], end = -1;
  const close = () => { group.forEach((x) => { x.cols = cols.length; }); group = []; cols = []; };
  for (const x of xs) {
    if (x.top >= end) { close(); end = -1; }
    let c = cols.findIndex((last) => last <= x.top);
    if (c < 0) { c = cols.length; cols.push(0); }
    cols[c] = x.bottom; x.col = c; group.push(x); end = Math.max(end, x.bottom);
  }
  close();
  return xs;
}
export function moveNowLine() {
  const l = $('.nowline'); if (!l) return;
  const t = new Date();
  l.style.top = `${(t.getHours() * 60 + t.getMinutes()) / 60 * HH}px`;
}

export function drawAgenda(body, s, e) {
  const days = Array.from({ length: daysBetween(s, e) }, (_, i) => addDays(s, i));
  const map = byDay(days, S.occ), today = new Date();
  const wrap = h('div', { class: 'agenda' });
  let any = false;
  for (const d of days) {
    const list = map.get(ymd(d)).sort(dayOrder);
    if (!list.length) continue;
    any = true;
    wrap.append(h('div', { class: `aday ${sameDay(d, today) ? 'today' : ''}` },
      h('div', { class: 'when', onclick: () => go('day', d), style: { cursor: 'pointer' } }, h('div', { class: 'n' }, d.getDate()),
        h('div', { class: 'w' }, d.toLocaleDateString([], { weekday: 'short', month: 'short' })), dayWeather(d, true)),
      h('div', { class: 'evs' }, list.map((o) => agendaRow(o, d)))));
  }
  if (!any) wrap.append(h('div', { class: 'empty' }, icon('agenda'), h('p', null, shownCals().length || tasksOn() || billsOn() || papersOn() ? 'Nothing planned in these weeks.' : 'Every calendar is hidden: tick one in the sidebar.')));
  wrap.append(h('p', null, h('button', { class: 'pillbtn noic', onclick: () => { S.agendaDays = (S.agendaDays || 31) + 61; drawView(); } }, 'Show more')));
  body.append(wrap);
}
export function agendaRow(o, d) {
  const [a, b] = span(o);
  if (o.bill) {
    return h('div', { class: `arow bill ${o.paid ? 'done' : ''}`, style: { '--c': '#94650a' }, title: billTitle(o), onclick: () => openBill(o) },
      h('span', { class: 'bm' }, '$'), h('span', { class: 'tm' }, 'Bill'),
      h('div', { style: { minWidth: 0 } }, h('div', { class: 'nm' }, o.merchant, ' · ', billAmount(o)),
        h('div', { class: 'sub' }, [o.category, o.account, o.paid ? 'paid' : null].filter(Boolean).join(' · '))));
  }
  if (o.paper) {
    return h('div', { class: 'arow paper', style: { '--c': '#a03a6a' }, title: paperTitle(o), onclick: () => openPaper(o) },
      h('span', { class: 'bm' }, '!'), h('span', { class: 'tm' }, 'Expires'),
      h('div', { style: { minWidth: 0 } }, h('div', { class: 'nm' }, o.title),
        h('div', { class: 'sub' }, [o.kind, (o.members || []).map(memberOf).filter(Boolean).map((m) => m.displayName).join(', ')].filter(Boolean).join(' · '))));
  }
  if (o.task) {
    return h('div', { class: `arow task ${o.done ? 'done' : ''}`, style: { '--c': o.color || 'var(--brand)' }, title: taskTitle(o), onclick: () => openTask(o) },
      tickBtn(o), h('span', { class: 'tm' }, o.allDay ? 'Task' : `Task · ${fmtTime(a)}`),
      h('div', { style: { minWidth: 0 } }, h('div', { class: 'nm' }, o.title),
        h('div', { class: 'sub' }, [o.list, (o.members || []).map(memberOf).filter(Boolean).map((m) => m.displayName).join(', ')].filter(Boolean).join(' · '))));
  }
  const tm = o.allDay ? 'All day' : longEvent(o) || !sameDay(a, new Date(+b - 1)) ? (sameDay(a, d) ? `From ${fmtTime(a)}` : sameDay(b, d) ? `Until ${fmtTime(b)}` : 'All day') : `${fmtTime(a)} – ${fmtTime(b)}`;
  return h('div', { class: 'arow', style: { '--c': colorOf(o.calendarId) }, onclick: () => openEvent(o) },
    h('span', { class: 'dot' }), h('span', { class: 'tm' }, tm),
    h('div', { style: { minWidth: 0 } }, h('div', { class: 'nm', style: o.status === 'CANCELLED' ? { textDecoration: 'line-through' } : null }, o.title || '(no title)'),
      o.location || (o.people || []).length || (o.members || []).length ? h('div', { class: 'sub' }, [(o.members || []).map(memberOf).filter(Boolean).map((m) => m.displayName).join(', '),
        o.location, (o.people || []).map((p) => p.name || p.email).join(', ')].filter(Boolean).join(' · ')) : null));
}
