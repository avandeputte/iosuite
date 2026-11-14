import { api, dayWords, fail, fill, fmtTime, h, hue, icon, initials, listOf, loadLists, parseDay, toast, undoStep, writable } from './core.js';

// ------------------------------------------------------------------ activity
/** What an entry of the log says, as the parts of a sentence. */
export function activityWords(a) {
  const who = a.user || 'Someone', more = a.count > 1 ? ` and ${a.count - 1} more` : '';
  const title = h('b', null, `“${a.title || '(no title)'}”`);
  const undo = a.detail === 'undo';
  const d = a.detail && !undo ? a.detail : '';
  switch (a.action) {
    case 'added': return [who, undo ? ' brought back ' : ' added ', title, more, d === 'import' ? ' (import)' : d.startsWith('template ') ? ` from the template ${d.slice(9)}` : d.startsWith('from ') ? ` (moved here ${d})` : ''];
    case 'done': return [who, ' ticked off ', title, more, d.startsWith('next ') ? ` (it repeats: next ${dayWords(parseDay(d.slice(5)))})` : ''];
    case 'reopened': return [who, ' opened ', title, ' again', more];
    case 'moved': return [who, ' moved ', title, more, d ? ` ${d}` : ''];
    case 'deleted': return [who, undo ? ' took back adding ' : ' deleted ', title, more];
    default: return [who, d === 'postponed' ? ' postponed ' : undo ? ' put back ' : ' changed ', title, more, d && d !== 'postponed' ? ` (${d})` : ''];
  }
}
/** Who did what, newest first (all the lists you see, or one), each step with Undo while the task is still as that
    step left it. */
export async function showActivity(page, r) {
  const c = r.list ? listOf(r.list) : null;
  const rows = h('div', { class: 'acts' });
  const more = h('p', { class: 'center' });
  let last = null, lastDay = null;
  const load = async () => {
    const items = (await api(`api/activity?limit=60${c && c.id ? `&list=${c.id}` : ''}${last ? `&before=${last}` : ''}`)).items;
    for (const a of items) {
      const at = new Date(a.at), day = dayWords(at);
      if (day !== lastDay) { rows.append(h('div', { class: 'tsec' }, day)); lastDay = day; }
      const l = listOf(a.listId);
      rows.append(h('div', { class: `act ${a.undone ? 'undone' : ''}` },
        h('span', { class: 'av', style: { '--h': hue(a.user || '') } }, a.user ? initials(a.user) : '?'),
        h('div', { class: 'abody' }, h('div', null, activityWords(a)),
          h('div', { class: 'tmeta' }, h('span', null, fmtTime(at)), l.id && !(c && c.id) ? h('span', { class: 'lname', style: { '--c': l.color } }, l.name) : null,
            a.via === 'caldav' ? h('span', null, 'in a reminders app') : a.via === 'mcp' ? h('span', null, 'through an assistant') : null,
            a.undone ? h('span', null, 'undone') : null)),
        a.canUndo ? h('button', { class: 'pillbtn noic', onclick: () => undoStep(a.batch) }, 'Undo') : null));
    }
    last = items.length ? items[items.length - 1].id : last;
    fill(more, items.length === 60 ? h('button', { class: 'pillbtn noic', onclick: () => load().catch(fail) }, 'Earlier') : null);
    if (!rows.children.length) rows.append(h('div', { class: 'empty' }, icon('history'), h('p', null, 'Nothing has happened yet.')));
  };
  page.classList.add('taskpage');
  page.append(h('div', { class: 'pagehead tasks-head', style: c && c.id ? { '--c': c.color } : null }, h('h1', null, c && c.id ? `Activity: ${c.name}` : 'Activity'), h('span', { class: 'grow' }),
    c && c.id ? h('a', { class: 'pillbtn noic', href: '#/activity' }, 'All lists') : null), rows, more);
  await load();
}

// ------------------------------------------------------------------ import
export async function showImport(page, r) {
  const w = writable();
  const sel = h('select', { class: 't', style: { maxWidth: '320px' } }, w.map((c) => h('option', { value: c.id, selected: c.id === r.list ? true : null }, `${c.name}${c.shared ? ' (shared)' : ''}`)));
  const file = h('input', { type: 'file', accept: '.ics,.ical,text/calendar', multiple: true });
  const replace = h('input', { type: 'checkbox', checked: true });
  const out = h('div');
  const run = async () => {
    if (!file.files.length) { toast('Pick a file first'); return; }
    const tot = { created: 0, updated: 0, skipped: 0, errors: [] };
    for (const f of file.files) {
      const fd = new FormData(); fd.append('file', f);
      try {
        const res = await api(`api/lists/${sel.value}/import?replace=${replace.checked}`, { method: 'POST', body: fd });
        tot.created += res.created; tot.updated += res.updated; tot.skipped += res.skipped; tot.errors.push(...res.errors);
      } catch (e) { tot.errors.push(`${f.name}: ${e.message}`); }
    }
    fill(out, h('p', null, `${tot.created} added, ${tot.updated} updated${tot.skipped ? `, ${tot.skipped} left as they were` : ''}.`),
      tot.errors.length ? h('details', null, h('summary', { class: 'lnk' }, `${tot.errors.length} could not be read`), h('ul', null, tot.errors.slice(0, 50).map((x) => h('li', null, x)))) : null);
    await loadLists();
  };
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Import')),
    w.length ? h('div', { class: 'box' }, h('h2', null, icon('upload'), 'Import'),
      h('p', null, 'An iCalendar file (.ics) with to-dos, from another tasks app or another ioTask. Due dates, repeats, alerts, priorities and subtasks come along; events in the file are left out.'),
      h('div', { class: 'pform' }, h('label', { class: 'field' }, h('span', null, 'Into the list'), sel), file,
        h('label', { class: 'check' }, replace, ' Update tasks that are already here (same UID)'),
        h('p', null, h('button', { class: 'pillbtn primary', onclick: run }, icon('upload', 's'), 'Import'))), out) : h('p', { class: 'muted' }, 'You cannot add tasks to any list.'));
}
