import { $, S, addDays, api, calOf, colorOf, fill, fmtTime, h, icon, isAuto, loadCals, parseDay, toast, writable } from './core.js';

// ------------------------------------------------------------------ search
export async function showSearch(page, r) {
  S.q = r.q;
  if ($('#q').value !== r.q) $('#q').value = r.q;
  page.append(h('div', { class: 'pagehead' }, h('h1', null, r.q ? `“${r.q}”` : 'Search')));
  if (!r.q) { page.append(h('p', { class: 'muted' }, 'Type in the search box: a title, a place, a name or words from the notes.')); return; }
  const res = await api(`api/events?q=${encodeURIComponent(r.q)}&limit=300`);
  const now = Date.now();
  const at = (x) => (x.next ? (x.allDay ? parseDay(x.next.start) : new Date(x.next.start)) : null);
  const soon = res.items.filter((x) => at(x) && (x.allDay ? +addDays(at(x), 1) : +new Date(x.next.end)) >= now).sort((a, b) => at(a) - at(b));
  const past = res.items.filter((x) => !soon.includes(x)).sort((a, b) => (at(b) || 0) - (at(a) || 0));
  const row = (x) => {
    const d = at(x);
    const href = `#/event/${x.id}${x.next && x.next.recurrenceId ? `?rid=${encodeURIComponent(x.next.recurrenceId)}` : ''}`;
    return h('a', { class: 'arow', href, style: { '--c': colorOf(x.calendarId), color: 'inherit', textDecoration: 'none' } }, h('span', { class: 'dot' }),
      h('span', { class: 'tm' }, d ? d.toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' }) + (x.allDay ? '' : ` ${fmtTime(d)}`) : ''),
      h('div', { style: { minWidth: 0 } }, h('div', { class: 'nm' }, x.title || '(no title)', x.recurring ? h('span', { class: 'muted small' }, ' · repeats') : null),
        h('div', { class: 'sub' }, [x.location, calOf(x.calendarId).name].filter(Boolean).join(' · '))));
  };
  if (!res.items.length) { page.append(h('div', { class: 'empty' }, icon('search'), h('p', null, 'Nothing matches.'))); return; }
  if (soon.length) page.append(h('div', { class: 'fsec' }, 'Coming up'), h('div', { class: 'evs' }, soon.map(row)));
  if (past.length) page.append(h('div', { class: 'fsec' }, 'Earlier'), h('div', { class: 'evs' }, past.map(row)));
}

// ------------------------------------------------------------------ import and export
export async function showImport(page) {
  const w = writable().filter((c) => !isAuto(c));
  const sel = h('select', { class: 't', style: { maxWidth: '320px' } }, w.map((c) => h('option', { value: c.id }, `${c.name}${c.shared ? ' (shared)' : ''}`)));
  const file = h('input', { type: 'file', accept: '.ics,.ical,.ifb,text/calendar', multiple: true });
  const replace = h('input', { type: 'checkbox', checked: true });
  const out = h('div');
  const run = async () => {
    if (!file.files.length) { toast('Pick a file first'); return; }
    const tot = { created: 0, updated: 0, skipped: 0, errors: [] };
    for (const f of file.files) {
      const fd = new FormData(); fd.append('file', f);
      try {
        const r = await api(`api/calendars/${sel.value}/import?replace=${replace.checked}`, { method: 'POST', body: fd });
        tot.created += r.created; tot.updated += r.updated; tot.skipped += r.skipped; tot.errors.push(...r.errors);
      } catch (e) { tot.errors.push(`${f.name}: ${e.message}`); }
    }
    fill(out, h('p', null, `${tot.created} added, ${tot.updated} updated${tot.skipped ? `, ${tot.skipped} left as they were` : ''}.`),
      tot.errors.length ? h('details', null, h('summary', { class: 'lnk' }, `${tot.errors.length} could not be read`), h('ul', null, tot.errors.slice(0, 50).map((x) => h('li', null, x)))) : null);
    await loadCals();
  };
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Import')),
    w.length ? h('div', { class: 'box' }, h('h2', null, icon('upload'), 'Import'),
      h('p', null, 'An iCalendar file (.ics) from Google Calendar (Settings › Import & export › Export, then unzip), Apple Calendar (File › Export), Outlook or any other calendar. Repeating events, exceptions, reminders and time zones come along.'),
      h('div', { class: 'pform' }, h('label', { class: 'field' }, h('span', null, 'Into the calendar'), sel), file,
        h('label', { class: 'check' }, replace, ' Update events that are already here (same UID)'),
        h('p', null, h('button', { class: 'pillbtn primary', onclick: run }, icon('upload', 's'), 'Import'))), out) : null);
}
