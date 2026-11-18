import { DOW, LOCAL_TZ, RDAY, S, addDays, addMonths, api, calOf, dayStart, describeReminder, describeRule, fail, fill, h, icon, isAuto, loadCals, memberBadge, ordinal, pad2, parseDay, sameDay, saveSettings, toast, weekStart, writable, ymd } from './core.js';
import { deleteEvent, forOccurrence, linkedBox, ridQ } from './event.js';
import { go } from './main.js';
import { askScope, daysBetween } from './views.js';

// ------------------------------------------------------------------ the event form
export const TIMED_REMINDERS = [0, 5, 10, 15, 30, 60, 120, 1440, 2880, 10080];
export const ALLDAY_REMINDERS = [-540, 900, 2340, 9540];
export function zones(cur) {
  let list = [];
  try { list = Intl.supportedValuesOf('timeZone'); } catch { list = [LOCAL_TZ, 'UTC']; }
  if (!list.includes('UTC')) list = ['UTC', ...list];
  return [...new Set([cur, LOCAL_TZ, ...list].filter(Boolean))];
}
export const hm = (d) => `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
/** The clock of a moment in a time zone, as a Date whose own fields carry it: what the date and time fields show, and
    send back as the time in that zone (the browser's zone is not the event's: one made elsewhere, or read abroad). */
export function wallIn(d, zone) {
  try {
    const p = {};
    new Intl.DateTimeFormat('en-CA', { timeZone: zone, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
      .formatToParts(d).forEach((x) => { p[x.type] = +x.value; });
    return new Date(p.year, p.month - 1, p.day, p.hour, p.minute);
  } catch (e) { return d; }
}
/** A time the server sent, on the clock of a zone; one without an offset is a clock time already (a floating event). */
export const clockIn = (iso, zone) => (/(Z|[+-]\d\d:?\d\d)$/.test(iso) ? wallIn(new Date(iso), zone) : new Date(iso));
export const nthOf = (d) => { const n = Math.ceil(d.getDate() / 7); return n >= 5 || addDays(d, 7).getMonth() !== d.getMonth() && n === 5 ? -1 : n; };
export const WEEKDAYS = ['MO', 'TU', 'WE', 'TH', 'FR'];

/** What the repeat menu shows for a rule: {kind, interval, freq, days, ends, until, count, text}. */
export function readRule(rule, d) {
  const out = { kind: 'none', interval: 1, freq: 'WEEKLY', days: [RDAY[d.getDay()]], ends: 'never', until: '', count: 10, text: rule || '' };
  if (!rule) return out;
  const p = Object.fromEntries(rule.split(';').filter(Boolean).map((x) => x.split('=')));
  out.freq = p.FREQ || 'WEEKLY'; out.interval = +(p.INTERVAL || 1);
  if (p.COUNT) { out.ends = 'count'; out.count = +p.COUNT; }
  if (p.UNTIL) { out.ends = 'until'; const u = p.UNTIL; out.until = `${u.slice(0, 4)}-${u.slice(4, 6)}-${u.slice(6, 8)}`; }
  const extra = Object.keys(p).filter((k) => !['FREQ', 'INTERVAL', 'COUNT', 'UNTIL', 'WKST', 'BYDAY', 'BYMONTHDAY'].includes(k));
  const days = p.BYDAY ? p.BYDAY.split(',') : [];
  const plainDays = days.every((x) => /^[A-Z]{2}$/.test(x));
  if (days.length) out.days = plainDays ? days : out.days;
  if (extra.length) { out.kind = 'keep'; return out; }
  const one = out.interval === 1;
  if (p.FREQ === 'DAILY' && !p.BYDAY && !p.BYMONTHDAY) out.kind = one ? 'daily' : 'custom';
  else if (p.FREQ === 'WEEKLY' && !p.BYMONTHDAY && plainDays) {
    if (one && (!days.length || (days.length === 1 && days[0] === RDAY[d.getDay()]))) out.kind = 'weekly';
    else if (one && days.length === 5 && WEEKDAYS.every((x) => days.includes(x))) out.kind = 'weekdays';
    else out.kind = 'custom';
  } else if (p.FREQ === 'MONTHLY' && one && !p.BYDAY && (!p.BYMONTHDAY || +p.BYMONTHDAY === d.getDate())) out.kind = 'monthly';
  else if (p.FREQ === 'MONTHLY' && one && days.length === 1 && !p.BYMONTHDAY && /^-?\d[A-Z]{2}$/.test(days[0])) out.kind = 'monthlyNth';
  else if (p.FREQ === 'YEARLY' && !p.BYDAY && !p.BYMONTHDAY) out.kind = one ? 'yearly' : 'custom';
  else if (['DAILY', 'MONTHLY', 'YEARLY'].includes(p.FREQ) && !p.BYDAY && !p.BYMONTHDAY) out.kind = 'custom';
  else out.kind = 'keep';
  return out;
}
/** The rule for what the repeat controls say. */
export function makeRule(st, d, allDay) {
  const day = RDAY[d.getDay()];
  const base = {
    none: null, keep: st.text.split(';').filter((x) => !/^(UNTIL|COUNT)=/.test(x)).join(';'),
    daily: 'FREQ=DAILY', weekly: `FREQ=WEEKLY;BYDAY=${day}`, weekdays: 'FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR',
    monthly: `FREQ=MONTHLY;BYMONTHDAY=${d.getDate()}`, monthlyNth: `FREQ=MONTHLY;BYDAY=${nthOf(d)}${day}`, yearly: 'FREQ=YEARLY',
    custom: [`FREQ=${st.freq}`, st.interval > 1 ? `INTERVAL=${st.interval}` : null,
      st.freq === 'WEEKLY' ? `BYDAY=${(st.days.length ? st.days : [day]).join(',')}` : null].filter(Boolean).join(';'),
  }[st.kind];
  if (!base) return null;
  if (st.ends === 'count' && st.count > 0) return `${base};COUNT=${st.count}`;
  if (st.ends === 'until' && st.until) {
    const u = parseDay(st.until);
    return `${base};UNTIL=${allDay ? st.until.replace(/-/g, '') : new Date(u.getFullYear(), u.getMonth(), u.getDate(), 23, 59, 59).toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z')}`;
  }
  return base;
}

export async function showEdit(page, r) {
  const editing = r.view === 'edit';
  const cals = writable().filter((c) => !isAuto(c));
  if (!cals.length) { page.append(h('div', { class: 'empty' }, icon('today'), h('p', null, 'You cannot add events to any calendar.'))); return; }
  let j;
  if (editing) {
    j = forOccurrence(await api(`api/events/${r.id}${ridQ(r.rid)}`), r.rid);
  } else if (r.copy) {
    j = await api(`api/events/${r.copy}`);
    delete j.id;
  } else {
    const d = r.date ? parseDay(r.date) : dayStart(new Date());
    let s;
    if (r.time) { const [hh, mm] = r.time.split(':').map(Number); s = new Date(d.getFullYear(), d.getMonth(), d.getDate(), hh, mm); }
    else if (sameDay(d, new Date())) { s = new Date(); s.setMinutes(0, 0, 0); s.setHours(s.getHours() + 1); }
    else s = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 9);
    const lastCal = cals.find((c) => c.id === +S.settings.lastCalendar && !S.hidden.has(c.id)) || cals.find((c) => !S.hidden.has(c.id)) || cals[0];
    const rem = S.settings.defaultReminder;
    j = { title: '', allDay: !!r.allDay, start: r.allDay ? ymd(d) : s.toISOString(), end: r.allDay ? ymd(addDays(d, 1)) : new Date(+s + 3600e3).toISOString(),
      calendarId: lastCal.id, timezone: lastCal.timezone || LOCAL_TZ, people: [], reminders: r.allDay || rem === undefined || rem === '' ? [] : [+rem], busy: true };
  }
  const original = j;
  const C = calOf(j.calendarId);
  const fld = (l, e, extra) => h('label', { class: 'field', style: extra }, h('span', null, l), e);
  const title = h('input', { class: 't', value: j.title || '', placeholder: 'Add a title', style: { fontSize: '20px', height: '48px' } });
  const calSel = h('select', { class: 't' }, cals.map((c) => h('option', { value: c.id, selected: c.id === j.calendarId ? true : null }, `${c.name}${c.shared ? ' (shared)' : ''}`)));
  if (editing && !cals.some((c) => c.id === j.calendarId)) calSel.prepend(h('option', { value: j.calendarId, selected: true }, C.name || 'This calendar'));
  // when
  const zone0 = j.timezone || C.timezone || LOCAL_TZ;  // the zone the fields are in: the one the selector starts on, and the times are saved in
  const s0 = j.allDay ? parseDay(j.start) : clockIn(j.start, zone0), e0 = j.allDay ? addDays(parseDay(j.end), -1) : clockIn(j.end, zone0);
  const allDay = h('input', { type: 'checkbox', checked: j.allDay });
  const sd = h('input', { class: 't', type: 'date', value: ymd(s0), required: true }), st = h('input', { class: 't', type: 'time', value: hm(s0), step: 300 });
  const ed = h('input', { class: 't', type: 'date', value: ymd(e0), required: true }), et = h('input', { class: 't', type: 'time', value: hm(e0), step: 300 });
  const tz = h('select', { class: 't', style: { width: 'auto', maxWidth: '260px' } }, zones(zone0).map((z) => h('option', { value: z, selected: z === zone0 ? true : null }, z.replace(/_/g, ' '))));
  const tzWrap = h('span', { class: 'prefck' }, icon('globe', 's'), tz);
  const startAt = () => (allDay.checked ? parseDay(sd.value) : new Date(`${sd.value}T${st.value || '00:00'}`));
  const endAt = () => (allDay.checked ? parseDay(ed.value) : new Date(`${ed.value}T${et.value || '00:00'}`));
  let length = endAt() - startAt();
  const onStart = () => { if (!sd.value) return; const e = allDay.checked ? addDays(startAt(), Math.round(Math.max(0, length) / 864e5)) : new Date(+startAt() + Math.max(0, length)); ed.value = ymd(e); if (!allDay.checked) et.value = hm(e); drawRepeat(); drawReminders(); };
  const onEnd = () => { if (!ed.value) return; length = endAt() - startAt(); if (length < 0) { length = allDay.checked ? 0 : 3600e3; onStart(); } };
  sd.onchange = st.onchange = onStart; ed.onchange = et.onchange = onEnd;
  const timedBits = [st, et, tzWrap];
  const showTimes = () => { timedBits.forEach((x) => { x.hidden = allDay.checked; }); };
  allDay.onchange = () => {
    if (allDay.checked) { length = Math.max(0, daysBetween(startAt(), endAt()) * 864e5); reminders.splice(0, reminders.length, ...reminders.filter((m) => ALLDAY_REMINDERS.includes(m))); }
    else { length = 3600e3; if (sd.value === ed.value) { const e = new Date(+startAt() + length); et.value = hm(e); } reminders.splice(0, reminders.length, ...reminders.filter((m) => TIMED_REMINDERS.includes(m))); }
    showTimes(); drawReminders();
  };
  showTimes();
  // repeat
  const rs = readRule(j.rrule, s0);
  const repSel = h('select', { class: 't', style: { width: 'auto' } });
  const repMore = h('div', { style: { display: 'grid', gap: '8px', marginTop: '8px' } });
  const drawRepeat = () => {
    const d = startAt();
    const opts = [['none', 'Does not repeat'], ['daily', 'Every day'], ['weekly', `Every week on ${DOW(d.getDay(), 'long')}`], ['weekdays', 'Every weekday (Monday to Friday)'],
      ['monthly', `Every month on day ${d.getDate()}`], ['monthlyNth', `Every month on the ${ordinal(nthOf(d))} ${DOW(d.getDay(), 'long')}`],
      ['yearly', `Every year on ${d.toLocaleDateString([], { month: 'long', day: 'numeric' })}`], ['custom', 'Custom…']];
    if (rs.kind === 'keep') opts.push(['keep', describeRule(rs.text, d) + ' (as set elsewhere)']);
    repSel.replaceChildren(...opts.map(([v, l]) => h('option', { value: v, selected: v === rs.kind ? true : null }, l)));
    const every = h('input', { class: 't', type: 'number', min: 1, max: 99, value: rs.interval, style: { width: '80px' }, oninput: (e) => { rs.interval = Math.max(1, +e.target.value || 1); } });
    const unit = h('select', { class: 't', style: { width: 'auto' }, onchange: (e) => { rs.freq = e.target.value; drawRepeat(); } },
      [['DAILY', 'days'], ['WEEKLY', 'weeks'], ['MONTHLY', 'months'], ['YEARLY', 'years']].map(([v, l]) => h('option', { value: v, selected: v === rs.freq ? true : null }, l)));
    const days = h('div', { class: 'days7' }, [0, 1, 2, 3, 4, 5, 6].map((i) => {
      const k = RDAY[(i + weekStart()) % 7];
      const lab = h('label', { class: rs.days.includes(k) ? 'on' : '', title: DOW((i + weekStart()) % 7, 'long') }, DOW((i + weekStart()) % 7, 'narrow'));
      lab.onclick = (e) => { e.preventDefault(); rs.days = rs.days.includes(k) ? rs.days.filter((x) => x !== k) : [...rs.days, k]; lab.classList.toggle('on'); };
      return lab;
    }));
    const endSel = h('select', { class: 't', style: { width: 'auto' }, onchange: (e) => { rs.ends = e.target.value; drawRepeat(); } },
      [['never', 'Never ends'], ['until', 'Ends on'], ['count', 'Ends after']].map(([v, l]) => h('option', { value: v, selected: v === rs.ends ? true : null }, l)));
    const until = h('input', { class: 't', type: 'date', value: rs.until || ymd(addMonths(d, 3)), onchange: (e) => { rs.until = e.target.value; } });
    if (!rs.until) rs.until = until.value;
    const count = h('input', { class: 't', type: 'number', min: 1, max: 999, value: rs.count, style: { width: '90px' }, oninput: (e) => { rs.count = Math.max(1, +e.target.value || 1); } });
    fill(repMore, 
      rs.kind === 'custom' ? h('div', { class: 'when-row' }, 'Every', every, unit) : null,
      rs.kind === 'custom' && rs.freq === 'WEEKLY' ? days : null,
      rs.kind !== 'none' ? h('div', { class: 'when-row' }, endSel, rs.ends === 'until' ? until : null, rs.ends === 'count' ? [count, ' times'] : null) : null);
  };
  repSel.onchange = () => { rs.kind = repSel.value; drawRepeat(); };
  drawRepeat();
  // place, people
  const place = h('input', { class: 't', value: j.location || '', placeholder: 'Address or place', autocomplete: S.status.places ? 'off' : null });
  // suggestions from Google Places while typing, when the suite has a Google key (app/places.py); else a plain field
  const pdrop = h('div', { class: 'drop', hidden: true });
  if (S.status.places) {
    const session = globalThis.crypto?.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    let lt, lseq = 0, hits = [], at = -1;
    const mark = () => [...pdrop.querySelectorAll('.row')].forEach((el, i) => el.classList.toggle('on', i === at));
    const pick = (it) => { place.value = it.text; pdrop.hidden = true; hits = []; at = -1; };
    place.addEventListener('input', () => {
      clearTimeout(lt);
      const v = place.value.trim();
      if (v.length < 3) { ++lseq; pdrop.hidden = true; hits = []; return; }
      lt = setTimeout(async () => {
        const n = ++lseq;
        let res = { items: [] };
        try { res = await api(`api/places?q=${encodeURIComponent(v)}&session=${encodeURIComponent(session)}`); } catch { /* typed only */ }
        if (n !== lseq) return;
        hits = res.items || []; at = -1;
        if (!hits.length && !res.error) { pdrop.hidden = true; return; }
        fill(pdrop, ...hits.map((it) => h('div', { class: 'row', onmousedown: (e) => { e.preventDefault(); pick(it); } },
          icon('place', 's'), h('div', { class: 'who' }, h('div', { class: 'nm' }, it.main), it.secondary ? h('div', { class: 'sub' }, it.secondary) : null))),
        res.error ? h('div', { class: 'muted small', style: { padding: '6px 10px' } }, res.error)
          : h('div', { class: 'muted small', style: { padding: '4px 10px', textAlign: 'right' } }, 'Suggestions by Google'));
        pdrop.hidden = false;
      }, 250);
    });
    place.addEventListener('keydown', (e) => {
      if (pdrop.hidden || !hits.length) return;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); at = (at + (e.key === 'ArrowDown' ? 1 : hits.length - 1 + (at < 0 ? 1 : 0))) % hits.length; mark(); }
      else if (e.key === 'Enter' && at >= 0) { e.preventDefault(); pick(hits[at]); }
      else if (e.key === 'Escape') { e.stopPropagation(); pdrop.hidden = true; }
    });
    place.addEventListener('blur', () => setTimeout(() => { pdrop.hidden = true; }, 150));
  }
  const people = (j.people || []).filter((p) => p.role !== 'organizer').map((p) => ({ name: p.name, email: p.email, contactId: p.contactId }));
  const pchips = h('div', { class: 'chiprow' });
  const pin = h('input', { class: 't', placeholder: S.status.iocontact ? 'Add someone (from ioContact, or type a name or email)' : 'Add someone (a name or email)', autocomplete: 'off' });
  const drop = h('div', { class: 'drop', hidden: true });
  const drawPeople = () => pchips.replaceChildren(...people.map((p, i) => h('span', { class: 'chip', title: p.email || '' }, p.contactId ? icon('contacts', 's') : icon('person', 's'), p.name || p.email,
    h('span', { class: 'x', title: 'Remove', onclick: () => { people.splice(i, 1); drawPeople(); } }, icon('close', 's')))));
  const addPerson = (p) => {
    if (!p.name && !p.email) return;
    if (!people.some((x) => (x.email && x.email === p.email) || (!x.email && !p.email && x.name === p.name))) people.push(p);
    pin.value = ''; drop.hidden = true; drawPeople(); pin.focus();
  };
  const typed = () => { const v = pin.value.trim(); const m = v.match(/^(.*?)\s*<([^>]+@[^>]+)>$/); return m ? { name: m[1], email: m[2] } : /^\S+@\S+\.\S+$/.test(v) ? { name: null, email: v } : { name: v, email: null }; };
  let pt, pseq = 0;
  pin.addEventListener('input', () => {
    clearTimeout(pt);
    const v = pin.value.trim();
    if (!v) { drop.hidden = true; return; }
    pt = setTimeout(async () => {
      const n = ++pseq;
      let res = { items: [] };
      try { res = await api(`api/people?q=${encodeURIComponent(v)}&limit=8`); } catch { /* typed only */ }
      if (n !== pseq) return;
      fill(drop, ...res.items.map((p) => h('div', { class: 'row', onmousedown: (e) => { e.preventDefault(); addPerson({ name: p.name, email: p.email, contactId: p.contactId }); } },
        p.contactId ? icon('contacts', 's') : icon('person', 's'), h('div', { class: 'who' }, h('div', { class: 'nm' }, p.name || p.email), p.email && p.name ? h('div', { class: 'sub' }, p.email) : null))),
      h('div', { class: 'row', onmousedown: (e) => { e.preventDefault(); addPerson(typed()); } }, icon('add', 's'), h('div', { class: 'who' }, h('div', { class: 'nm' }, `Add “${v}”`))),
      res.error ? h('div', { class: 'muted small', style: { padding: '6px 10px' } }, res.error) : null);
      drop.hidden = false;
    }, 180);
  });
  pin.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); addPerson(typed()); } if (e.key === 'Escape') drop.hidden = true; });
  pin.addEventListener('blur', () => setTimeout(() => { drop.hidden = true; }, 150));
  drawPeople();
  // the family members it is for (shared calendars)
  const forWho = new Set((j.members || []).map((m) => m.id));
  const mchips = h('div', { class: 'chiprow' });
  const drawMembers = () => fill(mchips, S.members.map((m) => h('button', { type: 'button', class: `chip mchip toggle ${forWho.has(m.id) ? 'on' : ''}`, 'aria-pressed': forWho.has(m.id) ? 'true' : 'false',
    onclick: () => { if (forWho.has(m.id)) forWho.delete(m.id); else forWho.add(m.id); drawMembers(); } }, memberBadge(m, true), m.displayName)));
  drawMembers();
  const forSec = h('div', null, h('div', { class: 'fsec' }, icon('person'), 'For'), mchips,
    h('p', { class: 'muted small', style: { margin: '4px 0 0' } }, 'Who in the family this is for. Calendar apps show it as a category.'));
  const showFor = () => { forSec.hidden = !S.members.length || !calOf(+calSel.value).shared; };
  calSel.addEventListener('change', showFor);
  showFor();
  // reminders
  const reminders = [...(j.reminders || [])];
  const rchips = h('div', { class: 'chiprow' });
  const drawReminders = () => {
    const opts = (allDay.checked ? ALLDAY_REMINDERS : TIMED_REMINDERS).filter((m) => !reminders.includes(m));
    const add = h('select', { class: 't', style: { width: 'auto', height: '32px' }, onchange: (e) => { if (e.target.value !== '') { reminders.push(+e.target.value); reminders.sort((a, b) => a - b); drawReminders(); } } },
      h('option', { value: '' }, reminders.length ? 'Add another' : 'Add a reminder'), opts.map((m) => h('option', { value: m }, describeReminder(m, allDay.checked))));
    fill(rchips, ...reminders.map((m, i) => h('span', { class: 'chip' }, icon('bell', 's'), describeReminder(m, allDay.checked),
      h('span', { class: 'x', title: 'Remove', onclick: () => { reminders.splice(i, 1); drawReminders(); } }, icon('close', 's')))), opts.length ? add : null);
  };
  drawReminders();
  const notes = h('textarea', { class: 't', placeholder: 'Notes' }, j.notes || '');
  const url = h('input', { class: 't', type: 'url', value: j.url || '', placeholder: 'https://' });
  const status = h('select', { class: 't' }, [['', 'Confirmed'], ['TENTATIVE', 'Tentative'], ['CANCELLED', 'Cancelled']].map(([v, l]) => h('option', { value: v, selected: (j.status === 'CONFIRMED' ? '' : j.status || '') === v ? true : null }, l)));
  const busy = h('select', { class: 't' }, h('option', { value: '1', selected: j.busy !== false ? true : null }, 'Busy'), h('option', { value: '0', selected: j.busy === false ? true : null }, 'Free'));

  const save = async () => {
    if (!sd.value || !ed.value) { toast('A date, please'); return; }
    if (endAt() < startAt()) { toast('The event ends before it starts'); return; }
    const data = { title: title.value.trim(), calendarId: +calSel.value, allDay: allDay.checked, location: place.value.trim() || null, notes: notes.value.trim() ? notes.value : null,
      people, reminders, url: url.value.trim() || null, status: status.value || null, busy: busy.value === '1' };
    if (pin.value.trim()) people.push(typed());
    if (!forSec.hidden) data.members = [...forWho];
    if (allDay.checked) { data.start = sd.value; data.end = ymd(addDays(parseDay(ed.value), 1)); }
    else { data.start = `${sd.value}T${st.value}`; data.end = `${ed.value}T${et.value}`; data.timezone = tz.value; }
    const rule = makeRule(rs, startAt(), allDay.checked);
    if (!editing || rule !== (original.rrule || null) || !r.rid) data.rrule = rule;
    try {
      if (!editing) {
        await api('api/events', { method: 'POST', json: data });
        saveSettings({ lastCalendar: data.calendarId });
        toast('Saved');
      } else {
        let qs = '';
        if (original.rrule && r.rid) {
          const scope = await askScope('Change');
          if (!scope) return;
          qs = `?scope=${scope}&recurrenceId=${encodeURIComponent(r.rid)}`;
          if (scope === 'this') delete data.rrule;
        }
        await api(`api/events/${r.id}${qs}`, { method: 'PATCH', json: data });
        toast('Saved');
      }
      await loadCals();
      go(S.view, parseDay(sd.value));
    } catch (e) { fail(e); }
  };
  page.classList.add('form');
  page.append(h('div', { class: 'pagehead' }, h('a', { class: 'iconbtn', href: `#/${S.view}/${ymd(S.date)}`, title: 'Cancel' }, icon('close')),
    h('h1', null, editing ? 'Change event' : 'New event')),
  title,
  h('div', { class: 'fsec' }, icon('clock'), 'When'),
  h('div', { class: 'when-row' }, sd, st, '–', ed, et, h('label', { class: 'check' }, allDay, ' All day'), tzWrap),
  h('div', { class: 'fsec' }, icon('repeat'), 'Repeat'), h('div', null, repSel, repMore),
  h('div', { class: 'fsec' }, icon('today'), 'Calendar'), h('div', { class: 'grid' }, fld('Calendar', calSel), fld('Show me as', busy), fld('Status', status)),
  forSec,
  h('div', { class: 'fsec' }, icon('place'), 'Where'), h('div', { class: 'picker' }, place, pdrop),
  h('div', { class: 'fsec' }, icon('people'), 'Who'), pchips, h('div', { class: 'picker', style: { marginTop: '6px' } }, pin, drop),
  h('div', { class: 'fsec' }, icon('bell'), 'Reminders'), rchips,
  h('p', { class: 'muted small', style: { margin: '4px 0 0' } }, 'Reminders go to the calendar apps on your phone and computer (through CalDAV).'),
  h('div', { class: 'fsec' }, icon('note'), 'Notes'), notes,
  h('div', { class: 'fsec' }, icon('link'), 'Link'), url,
  // the items linked to it in the other apps (an ioMoney transaction, a note, a task): changed at once, as on its card
  editing && /^\d+$/.test(String(r.id)) && !isAuto(C) ? linkedBox(r.id) : null,
  h('div', { class: 'formbar' }, h('button', { class: 'pillbtn primary', onclick: save }, icon('check', 's'), 'Save'),
    h('a', { class: 'pillbtn noic', href: `#/${S.view}/${ymd(S.date)}` }, 'Cancel'), h('span', { style: { flex: 1 } }),
    editing ? h('button', { class: 'pillbtn danger', onclick: () => deleteEvent({ ...original, id: r.id, recurring: !!original.rrule, recurrenceId: r.rid }) }, icon('delete', 's'), 'Delete') : null));
  title.addEventListener('keydown', (e) => { if (e.key === 'Enter') save(); });
  page.addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); save(); } });
  if (!editing) title.focus();
}
