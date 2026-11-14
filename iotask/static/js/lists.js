import { $, ICONS, LOCAL_TZ, S, TZQ, api, canShared, confirmDialog, dayStart, dayWords, defaultList, describeAfter, describeRule, dialog, dragSort, dueOf, dueText, fail, fill, fmtTime, h, icon, isLate, laterDays, listOf, memberBadge, memberOf, popMenu, put, safeUrl, saveSettings, toast, toggleWho, ymd } from './core.js';
import { SMART } from './shell.js';
import { redraw, refresh } from './main.js';
import { openTask } from './task.js';

// ------------------------------------------------------------------ the task lists
export const showDone = (lid) => (S.settings.showCompleted || '').split(',').includes(String(lid));
export function setShowDone(lid, on) {
  const s = new Set((S.settings.showCompleted || '').split(',').filter(Boolean));
  if (on) s.add(String(lid)); else s.delete(String(lid));
  saveSettings({ showCompleted: [...s].join(',') });
}

/** A list is in the order its tasks were put in by hand (the ⋯ menu of the list), or by due date. */
export const byHand = (lid) => (S.settings.manualSort || '').split(',').includes(String(lid));
export function setByHand(lid, on) {
  const s = new Set((S.settings.manualSort || '').split(',').filter(Boolean));
  if (on) s.add(String(lid)); else s.delete(String(lid));
  saveSettings({ manualSort: [...s].join(',') });
}

/** The tasks the view shows, from the server: [rows, title, colour, the list (list view only)]. */
export async function fetchTasks(r) {
  const who = `&${TZQ}${S.who.size ? `&member=${[...S.who].join(',')}` : ''}`;
  if (r.view === 'list') {
    const c = listOf(r.id);
    if (!c.id) throw new Error('That list is not here (any more)');
    const items = (await api(`api/tasks?list=${c.id}&status=${showDone(c.id) ? 'all' : 'open'}&limit=2000${byHand(c.id) ? '&sort=manual' : ''}${who}`)).items;
    return [items, c.name, c.color, c];
  }
  if (r.view === 'search') {
    S.q = r.q;
    if ($('#q').value !== r.q) $('#q').value = r.q;
    if (!r.q) return [[], 'Search', null, null];
    return [(await api(`api/tasks?q=${encodeURIComponent(r.q)}&status=all&limit=300${who}`)).items, `“${r.q}”`, null, null];
  }
  const qs = { today: 'status=open&due=today', scheduled: 'status=open&due=scheduled', all: 'status=open', done: 'status=done&limit=300' }[r.view];
  return [(await api(`api/tasks?${qs}${who}`)).items, SMART[r.view][0], `var(${SMART[r.view][2]})`, null];
}

/** The tasks without a parent among them, in the server's order, and a function that gives a task's subtasks. */
export function tree(items) {
  const byUid = new Map(items.map((t) => [`${t.listId}|${t.uid}`, t]));
  const kids = new Map(), roots = [];
  for (const t of items) {
    const k = t.parent && byUid.has(`${t.listId}|${t.parent}`) ? `${t.listId}|${t.parent}` : null;
    if (k) { if (!kids.has(k)) kids.set(k, []); kids.get(k).push(t); } else roots.push(t);
  }
  return [roots, (t) => kids.get(`${t.listId}|${t.uid}`) || []];
}
/** A task with its subtasks under it (indented): one block, which is what moves when the task is dragged. */
export function taskGroup(t, kidsOf, depth, o) {
  const kids = kidsOf(t);
  return h('div', { class: 'tgrp', 'data-id': t.id }, taskRow(t, { ...o, depth }),
    kids.length ? h('div', { class: 'tkids' }, kids.map((k) => taskGroup(k, kidsOf, depth + 1, o))) : null);
}
/** Put tasks off to a day (each keeps its time; the alerts follow), with Undo. */
export async function postpone(ids, day) {
  try {
    const r = await api('api/tasks/postpone', { method: 'POST', json: { ids, due: ymd(day), tz: LOCAL_TZ } });
    await refresh();
    const w = dayWords(day);
    toast(`${r.moved === 1 ? 'Now due' : `${r.moved} tasks now due`} ${/^(Today|Tomorrow)$/.test(w) ? w.toLowerCase() : w}`, r.undo);
  } catch (e) { fail(e); }
}

export async function drawTasks(page, r) {
  const [items, title, color, list] = await fetchTasks(r);
  const smart = r.view !== 'list';
  const head = h('div', { class: 'pagehead tasks-head', style: color ? { '--c': color } : null },
    h('h1', null, title), h('span', { class: 'count' }, items.filter((t) => !t.done).length || ''), h('span', { class: 'grow' }),
    S.who.size ? h('button', { class: 'pillbtn noic', title: 'Show everyone’s tasks again', onclick: () => toggleWho(null) },
      `Only ${[...S.who].map(memberOf).filter(Boolean).map((m) => m.displayName).join(', ')}`) : null,
    list ? listMenu(list) : null);
  page.classList.add('taskpage');
  page.append(head);
  if (r.view === 'search' && !r.q) { page.append(h('p', { class: 'muted' }, 'Type in the search box: words from the title or the notes.')); return; }
  const canAdd = list ? list.writable : (['today', 'all', 'scheduled'].includes(r.view) && !!defaultList());
  const rows = h('div', { class: 'tasks' });
  const section = (label, cls) => h('div', { class: `tsec ${cls || ''}` }, label);
  // Overdue, with one button to put all of it (that you may change) off to today
  const overdue = () => {
    const mine = items.filter((t) => isLate(t) && listOf(t.listId).writable).map((t) => t.id);
    return h('div', { class: 'tsec late' }, h('span', null, 'Overdue'),
      mine.length ? h('button', { class: 'pillbtn noic tiny', title: 'Each keeps its time of day', onclick: () => postpone(mine, dayStart(new Date())) }, mine.length > 1 ? 'Move all to today' : 'Move to today') : null);
  };
  if (r.view === 'list') {
    const [roots, kidsOf] = tree(items);
    const hand = byHand(list.id) && list.writable;
    roots.forEach((t) => rows.append(taskGroup(t, kidsOf, 0, { grip: hand })));
    if (hand) {
      const order = (ids) => api(`api/lists/${list.id}/order`, { method: 'POST', json: { ids } }).catch((e) => { fail(e); redraw(); });
      [rows, ...rows.querySelectorAll('.tkids')].forEach((box) => dragSort(box, '.tgrp', '.grip', order));
    }
  } else if (r.view === 'today') {
    const late = items.filter(isLate), now = items.filter((t) => !isLate(t));
    if (late.length) put(rows, overdue(), late.map((t) => taskRow(t, { showList: true })));
    if (now.length) put(rows, late.length ? section('Today') : null, now.map((t) => taskRow(t, { showList: true, noDay: true })));
  } else if (r.view === 'scheduled') {
    let last = null;
    for (const t of items) {
      const d = dueOf(t), label = isLate(t) ? 'Overdue' : dayWords(d);
      if (label !== last) { rows.append(label === 'Overdue' ? overdue() : section(label)); last = label; }
      rows.append(taskRow(t, { showList: true, noDay: label !== 'Overdue' }));
    }
  } else {
    // All, Completed and search: grouped by list, in the sidebar's order
    for (const c of S.lists) {
      const mine = items.filter((t) => t.listId === c.id);
      if (!mine.length) continue;
      rows.append(h('div', { class: 'tsec', style: { '--c': c.color } }, h('a', { href: `#/list/${c.id}` }, c.name)));
      if (r.view === 'all') { const [roots, kidsOf] = tree(mine); roots.forEach((t) => rows.append(taskGroup(t, kidsOf, 0, {}))); }
      else mine.forEach((t) => rows.append(taskRow(t, {})));
    }
  }
  if (canAdd) page.append(quickAdd(r, list));
  page.append(rows);
  if (!items.length) page.append(h('div', { class: 'empty' }, icon(r.view === 'search' ? 'search' : 'done'),
    h('p', null, r.view === 'search' ? 'Nothing matches.' : r.view === 'done' ? 'Nothing ticked off yet.' : list && showDone(list.id) ? 'No tasks.' : 'All done.')));
  if (list && !showDone(list.id)) {
    page.append(h('p', { class: 'center' }, h('button', { class: 'pillbtn noic', onclick: () => { setShowDone(list.id, true); redraw(); } }, 'Show completed')));
  } else if (list && items.some((t) => t.done)) {
    page.append(h('p', { class: 'center' }, h('button', { class: 'pillbtn noic', onclick: () => { setShowDone(list.id, false); redraw(); } }, 'Hide completed'),
      list.writable ? [' ', h('button', { class: 'pillbtn noic danger', onclick: () => clearCompleted(list) }, 'Clear completed')] : null));
  }
}

/** The ⋯ menu of a list: show completed, the order, templates, activity, print, export, import, clear completed, the
    list's settings. */
export function listMenu(c) {
  return h('button', { class: 'iconbtn', title: 'More', 'aria-haspopup': 'menu', onclick: (e) => {
    const on = showDone(c.id), hand = byHand(c.id);
    popMenu(e.currentTarget, [
      ['done', on ? 'Hide completed' : 'Show completed', () => { setShowDone(c.id, !on); redraw(); }],
      ['sort', hand ? 'Sort by due date' : 'Sort by hand (drag)', () => { setByHand(c.id, !hand); redraw(); }],
      c.writable ? ['template', 'Add from a template…', () => addFromTemplate(c)] : null,
      ['template', 'Save as a template…', () => saveTemplate(c)],
      ['history', 'Activity', `#/activity?list=${c.id}`],
      ['print', 'Print', () => window.print()],
      ['download', 'Export (.ics)', `api/lists/${c.id}/export`],
      c.writable ? ['upload', 'Import', `#/import?list=${c.id}`] : null,
      c.writable ? ['delete', 'Clear completed', () => clearCompleted(c)] : null,
      ['settings', 'List settings', `#/settings/lists/${c.id}`]]);
  } }, icon('more'));
}

/** Templates: a list's tasks kept to add again (a packing list, the weekly shop). */
export async function saveTemplate(c) {
  const name = h('input', { class: 't', value: c.name });
  const shared = h('input', { type: 'checkbox', checked: c.shared && canShared() });
  const body = h('div', { style: { display: 'grid', gap: '12px' } }, h('label', { class: 'field' }, h('span', null, 'Name'), name),
    canShared() ? h('label', { class: 'check' }, shared, ' Everyone in the family can use it') : null,
    h('p', { class: 'muted small', style: { margin: 0 } }, 'Every task of the list with its notes, priority, link, people and subtasks. Due dates, repeats and what is ticked off are left out.'));
  if (!await dialog('Save as a template', body, [{ label: 'Cancel', value: false }, { label: 'Save', value: true, primary: true }])) return;
  try {
    const r = await api('api/templates', { method: 'POST', json: { name: name.value, listId: c.id, shared: shared.checked } });
    toast(`Template ${r.template.name} saved (${r.template.count} tasks)`);
  } catch (e) { fail(e); }
}
export async function addFromTemplate(c) {
  const tpls = (await api('api/templates')).items;
  if (!tpls.length) { await dialog('Templates', h('p', null, 'There are no templates yet. Make one of a list with “Save as a template…” in its ⋯ menu.')); return; }
  const sel = h('select', { class: 't' }, tpls.map((t) => h('option', { value: t.id }, `${t.name} (${t.count} tasks)`)));
  const hasDue = h('input', { type: 'checkbox' });
  const date = h('input', { class: 't', type: 'date', value: ymd(new Date()), hidden: true });
  hasDue.onchange = () => { date.hidden = !hasDue.checked; };
  const body = h('div', { style: { display: 'grid', gap: '12px' } }, h('label', { class: 'field' }, h('span', null, 'Template'), sel),
    h('div', { class: 'when-row' }, h('label', { class: 'check' }, hasDue, ' All due on'), date));
  if (!await dialog(`Add to ${c.name}`, body, [{ label: 'Cancel', value: false }, { label: 'Add', value: true, primary: true }])) return;
  try {
    const r = await api(`api/templates/${sel.value}/apply`, { method: 'POST', json: { listId: c.id, due: hasDue.checked ? date.value : null } });
    await refresh();
    toast(`${r.created} tasks added`, r.undo);
  } catch (e) { fail(e); }
}
export async function clearCompleted(c) {
  if (!await confirmDialog('Clear completed', `Delete the completed tasks of ${c.name}? Apps that sync the list lose them too.`, 'Delete', true)) return;
  try { const r = await api(`api/lists/${c.id}/clear-completed`, { method: 'POST' }); await refresh(); toast(`${r.deleted} deleted`, r.undo); } catch (e) { fail(e); }
}

/** The new-task line reads plain English unless that is switched off (Settings › Display). */
export const smartAdd = () => S.settings.quickAdd !== 'off';
/** What the server made of a line, as chips: [[icon or mark, words]]. */
export function quickChips(p) {
  const due = { due: p.due, dueAllDay: !!p.due && !p.due.includes('T') };
  const c = listOf(p.listId);
  return [
    p.due ? [icon('today', 'xs'), dueText(due)] : null,
    p.rrule ? [icon('repeat', 'xs'), describeRule(p.rrule, dueOf(due))] : null,
    p.repeatAfter ? [icon('repeat', 'xs'), describeAfter(p.repeatAfter)] : null,
    p.priority ? [icon('flag', 'xs'), `${p.priority[0].toUpperCase()}${p.priority.slice(1)} priority`] : null,
    c.id ? [h('span', { class: 'ldot', style: { '--hue': c.color } }), c.name] : null,
    ...(p.members || []).map(memberOf).filter(Boolean).map((m) => [memberBadge(m), m.displayName]),
  ].filter(Boolean);
}

/** The "New task" line on top of a list: Enter adds it and leaves the line ready for the next one. What it says about
    when, how often, how important, which list and for whom becomes the task's fields, shown under the line while
    typing ("Pay rent every month on the 1st 9am !high"). On Today and Scheduled a new task is due today unless the
    line says when. */
export function quickAdd(r, list) {
  const target = list || defaultList();
  const input = h('input', { class: 'qadd', id: 'qadd', placeholder: list ? `New task in ${list.name}` : `New task (${target.name}${['today', 'scheduled'].includes(r.view) ? ', due today' : ''})`,
    title: smartAdd() ? 'Understands dates, repeats and priorities: “Call the bank tomorrow 5pm”, “Pay rent every month on the 1st !high”' : null,
    autocomplete: 'off', enterkeyhint: 'done', 'aria-label': 'New task' });
  const hint = h('div', { class: 'qhint', hidden: true });
  let seq = 0, timer;
  input.addEventListener('input', () => {
    clearTimeout(timer);
    const text = input.value.trim();
    const my = ++seq;
    if (!smartAdd() || !text) { hint.hidden = true; return; }
    timer = setTimeout(async () => {
      try {
        const p = await api(`api/quick?text=${encodeURIComponent(text)}&${TZQ}`);
        if (my !== seq) return;
        const chips = quickChips(p);
        fill(hint, h('span', { class: 'qt' }, p.title), chips.map((c) => h('span', { class: 'qchip' }, c)));
        hint.hidden = !chips.length;
      } catch { hint.hidden = true; }
    }, 150);
  });
  input.addEventListener('keydown', async (e) => {
    if (e.key !== 'Enter' || !input.value.trim()) return;
    e.preventDefault();
    const text = input.value.trim();
    const data = smartAdd() ? { text, timezone: LOCAL_TZ, listId: target.id } : { title: text, listId: target.id };
    if (['today', 'scheduled'].includes(r.view)) data.due = ymd(new Date());
    if (S.who.size) data.members = [...S.who];
    input.disabled = true;
    try {
      const t = await api('api/tasks', { method: 'POST', json: data });
      input.value = ''; seq += 1; hint.hidden = true;
      await refresh();
      if (t.title !== text) toast(`Added “${t.title}”${t.due ? `, ${dueText(t).toLowerCase()}` : ''}${t.listId !== target.id ? ` to ${listOf(t.listId).name}` : ''}`, t.undo);
    } catch (err) { fail(err); }
    input.disabled = false;
    $('#qadd')?.focus();
  });
  return h('div', { class: 'qwrap' }, h('div', { class: 'qrow', style: { '--c': target.color } }, h('span', { class: 'tick ghost' }, icon('add', 's')), input,
    h('button', { class: 'iconbtn', title: 'More details', onclick: () => { location.hash = `#/new?list=${target.id}`; } }, icon('edit', 's'))), hint);
}

export const PRIO_MARK = { high: '!!!', medium: '!!', low: '!' };
export function taskRow(t, o = {}) {
  const c = listOf(t.listId), canTick = !!c.writable;
  const tick = h('button', { class: `tick ${t.done ? 'on' : ''}`, style: { '--c': c.color || 'var(--brand)' }, title: t.done ? 'Not done after all' : 'Done', 'aria-pressed': t.done ? 'true' : 'false', disabled: canTick ? null : true });
  tick.innerHTML = `<svg viewBox="0 0 24 24"><path d="${ICONS.check}"/></svg>`;
  const late = isLate(t);
  const meta = [
    t.due && !(o.noDay && t.dueAllDay) ? h('span', { class: late ? 'late' : '' }, o.noDay ? fmtTime(dueOf(t)) : dueText(t)) : null,
    t.rrule || t.repeatAfter ? h('span', { title: t.rrule ? describeRule(t.rrule, dueOf(t)) : describeAfter(t.repeatAfter) }, icon('repeat', 'xs')) : null,
    t.alarms && t.alarms.length && !t.done ? h('span', { title: t.alarms.map((a) => new Date(a).toLocaleString()).join('\n') }, icon('bell', 'xs')) : null,
    o.showList ? h('span', { class: 'lname', style: { '--c': c.color } }, c.name) : null,
    t.subtasks && t.subtasks.total ? h('span', null, icon('subtask', 'xs'), `${t.subtasks.total - t.subtasks.open}/${t.subtasks.total}`) : null,
    t.url && safeUrl(t.url) ? h('a', { href: t.url, target: '_blank', rel: 'noopener', onclick: (e) => e.stopPropagation(), title: t.url }, icon('link', 'xs')) : null,
    t.done && t.completedAt ? h('span', null, `Done ${dayWords(new Date(t.completedAt)).toLowerCase().replace(/^(mon|tue|wed|thu|fri|sat|sun)/i, (x) => x[0].toUpperCase() + x.slice(1))}`) : null,
  ].filter(Boolean);
  // put off: a button on the tasks that are overdue or due today (the others show it under the mouse)
  const d0 = dueOf(t), soon = !!d0 && dayStart(d0) <= dayStart(new Date());
  const later = canTick && !t.done && d0 ? h('button', { class: `iconbtn later ${soon ? 'soon' : ''}`, title: 'Postpone', 'aria-haspopup': 'menu', onclick: (e) => {
    popMenu(e.currentTarget, [...laterDays(dayStart(d0) < dayStart(new Date())).map(([label, day]) => ['later', label, () => postpone([t.id], day)]),
      ['event', 'Another day…', () => openTask(t.id)]]);
  } }, icon('later', 's')) : null;
  const row = h('div', { class: `trow ${t.done ? 'done' : ''}`, style: { '--depth': o.depth || 0 }, 'data-id': t.id },
    o.grip ? h('span', { class: 'grip', title: 'Drag to move' }, icon('grip', 's')) : null,
    tick,
    h('div', { class: 'tbody', onclick: () => openTask(t.id) },
      h('div', { class: 'ttl' }, t.priority ? h('span', { class: 'prio' }, PRIO_MARK[t.priority] + ' ') : null, t.title || '(no title)'),
      t.notes ? h('div', { class: 'tnotes' }, t.notes) : null,
      meta.length ? h('div', { class: 'tmeta' }, meta) : null),
    (t.members || []).map((m) => memberOf(m.id) || m).map(memberBadge),
    later,
    h('button', { class: 'iconbtn info', title: 'Details', onclick: () => openTask(t.id) }, icon('chevR', 's')));
  tick.onclick = async () => {
    const done = !t.done;
    tick.classList.toggle('on', done); row.classList.toggle('done', done);
    try {
      const res = await api(`api/tasks/${t.id}/complete`, { method: 'POST', json: { done, tz: LOCAL_TZ } });
      if (done) toast(res.moved ? `Done. Next: ${dueText(res) || 'again'}` : 'Done', res.undo);
      // a moment to see the tick before the row leaves a list of open tasks
      setTimeout(() => refresh().catch(fail), done && !res.moved ? 700 : 0);
    } catch (e) { tick.classList.toggle('on', !done); row.classList.toggle('done', !done); fail(e); }
  };
  return row;
}
