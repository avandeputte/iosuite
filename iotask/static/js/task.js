import { LOCAL_TZ, S, afterOf, afterParts, afterRule, api, closeDialogs, confirmDialog, defaultList, describeAfter, describeRule, dueOf, dueText, fail, fill, h, hm, icon, laterDays, listOf, memberBadge, parseDay, toast, writable, ymd } from './core.js';
import { taskRow } from './lists.js';
import { refresh } from './main.js';

// ------------------------------------------------------------------ one task: the form
export const TIMED_ALERTS = [[0, 'At the time'], [5, '5 minutes before'], [15, '15 minutes before'], [30, '30 minutes before'], [60, '1 hour before'], [120, '2 hours before'], [1440, '1 day before']];
export const ALLDAY_ALERTS = [[-540, 'On the day at 9:00'], [900, 'The day before at 9:00'], [9540, 'A week before at 9:00']];
export const REPEATS = [['', 'Never'], ['FREQ=DAILY', 'Daily'], ['FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR', 'Weekdays'], ['FREQ=WEEKLY', 'Weekly'], ['FREQ=WEEKLY;INTERVAL=2', 'Every 2 weeks'], ['FREQ=MONTHLY', 'Monthly'], ['FREQ=YEARLY', 'Yearly'], ['every', 'Every…']];

/** Wide screens: the task opens in a sheet over the list; phones: as a page of its own. */
export function openTask(id) {
  if (innerWidth < 700) { location.hash = `#/task/${id}`; return; }
  const back = h('div', { class: 'dialog-back' });
  const box = h('div', { class: 'dialog wide taskdlg', role: 'dialog' });
  back.append(box);
  back.addEventListener('click', (e) => { if (e.target === back) back.remove(); });
  document.body.append(back);
  taskForm(box, { id }, () => { back.remove(); refresh().catch(fail); }).catch((e) => { back.remove(); fail(e); });
}
export async function showTaskPage(page, r) {
  page.classList.add('form');
  const backTo = () => { if (history.length > 1) history.back(); else location.hash = '#/'; };
  await taskForm(page, r.view === 'task' ? { id: r.id } : { list: r.list, parent: r.parent }, backTo);
}

/** The task form: everything a task has, saved with Save (or Enter in the title). opts: {id} or {list, parent}. */
export async function taskForm(el, opts, done) {
  const t = opts.id ? await api(`api/tasks/${opts.id}`) : null;
  const lid = t ? t.listId : (opts.list || defaultList()?.id);
  const c = listOf(lid);
  const ro = t ? !c.writable : false;
  const parent = !t && opts.parent ? await api(`api/tasks/${opts.parent}`).catch(() => null) : null;
  const dd = t ? dueOf(t) : null;

  const title = h('input', { class: 't big', value: t ? t.title : '', placeholder: 'Title', disabled: ro || null });
  const notes = h('textarea', { class: 't', placeholder: 'Notes', disabled: ro || null }, t && t.notes ? t.notes : '');
  const list = h('select', { class: 't', disabled: ro || (parent ? true : null) },
    writable().concat(ro ? [c] : []).map((x) => h('option', { value: x.id, selected: x.id === lid ? true : null }, `${x.name}${x.shared ? ' (shared)' : ''}`)));
  const hasDue = h('input', { type: 'checkbox', checked: !!dd, disabled: ro || null });
  const date = h('input', { class: 't', type: 'date', value: ymd(dd || new Date()), disabled: ro || null });
  const hasTime = h('input', { type: 'checkbox', checked: !!(dd && !t.dueAllDay), disabled: ro || null });
  const time = h('input', { class: 't', type: 'time', value: dd && !t.dueAllDay ? hm(dd) : '09:00', disabled: ro || null });
  const repeat = h('select', { class: 't', disabled: ro || null });
  const alert = h('select', { class: 't', disabled: ro || null });
  const prio = h('select', { class: 't', disabled: ro || null }, [['', 'None'], ['low', 'Low'], ['medium', 'Medium'], ['high', 'High']].map(([v, l]) => h('option', { value: v, selected: (t ? t.priority || '' : '') === v ? true : null }, l)));
  const url = h('input', { class: 't', type: 'url', value: t && t.url ? t.url : '', placeholder: 'https://…', disabled: ro || null });
  const picked = new Set(t ? (t.members || []).map((m) => m.id) : [...S.who]);

  // repeat: the usual ones, "Every…" with a number of days, weeks, months or years, and the task's own rule when it
  // is yet another; counted from the due date, or from the day the task is ticked off (repeat after completion)
  const curRule = t ? t.rrule || afterRule(t.repeatAfter) : '';
  const reps = REPEATS.slice();
  const plain = afterParts(afterOf(curRule));  // [n, unit] when the rule is only "every n days / weeks / months / years"
  const listed = reps.some(([v]) => v === curRule);
  if (curRule && !listed && !plain) reps.splice(-1, 0, [curRule, describeRule(curRule, dd)]);
  const repValue = listed || !plain ? curRule : 'every';
  fill(repeat, reps.map(([v, l]) => h('option', { value: v, selected: v === repValue ? true : null }, l)));
  const every = h('input', { class: 't', type: 'number', min: 1, max: 999, value: plain ? plain[0] : 2, disabled: ro || null, 'aria-label': 'How many' });
  const unit = h('select', { class: 't', disabled: ro || null, 'aria-label': 'Days, weeks, months or years' },
    [['D', 'days'], ['W', 'weeks'], ['M', 'months'], ['Y', 'years']].map(([v, l]) => h('option', { value: v, selected: plain && plain[1] === v ? true : null }, l)));
  const from = h('select', { class: 't', disabled: ro || null }, [['due', 'The due date'], ['done', 'The day it is ticked off']].map(([v, l]) => h('option', { value: v, selected: (t && t.repeatAfter ? 'done' : 'due') === v ? true : null }, l)));
  const rule = () => (repeat.value === 'every' ? afterRule(`P${Math.max(1, Math.min(999, +every.value || 1))}${unit.value}`) : repeat.value);
  const everyBox = h('span', { class: 'everybox' }, every, unit);
  const drawRepeat = () => {
    everyBox.hidden = repeat.value !== 'every';
    repeat.closest('.field')?.classList.toggle('wide', repeat.value === 'every');  // room for the number and the unit
    from.closest('.field')?.toggleAttribute('hidden', !hasDue.checked || !afterOf(rule()));
  };
  repeat.onchange = drawRepeat;
  // alert: minutes before the due time (all-day: before its midnight), worked out from the task's first alert
  const alertMins = () => {
    if (!t || !t.alarms || !t.alarms.length || !dd) return null;
    return Math.round((dd - new Date(t.alarms[0])) / 6e4);
  };
  const drawAlerts = (keep) => {
    const opts2 = hasTime.checked ? TIMED_ALERTS : ALLDAY_ALERTS;
    const cur = keep ? alertMins() : null;
    const known = opts2.some(([m]) => m === cur);
    fill(alert, h('option', { value: '' }, 'None'), opts2.map(([m, l]) => h('option', { value: m, selected: m === cur ? true : null }, l)),
      cur != null && !known ? h('option', { value: 'keep', selected: true }, t.alarms.map((a) => new Date(a).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })).join(', ')) : null);
  };
  drawAlerts(true);
  const whenRow = h('div', { class: 'when-row' });
  const drawWhen = () => {
    fill(whenRow, h('label', { class: 'check' }, hasDue, ' Due'), hasDue.checked ? [date, h('label', { class: 'check' }, hasTime, ' At a time'), hasTime.checked ? time : null] : null);
    repeat.closest('.field')?.toggleAttribute('hidden', !hasDue.checked);
    alert.closest('.field')?.toggleAttribute('hidden', !hasDue.checked);
    drawRepeat();
  };
  // the days a task is usually put off to, one click each
  const laterRow = ro ? null : h('div', { class: 'chiprow laterrow' }, laterDays(true).map(([label, day]) => h('button', { type: 'button', class: 'chip toggle',
    onclick: () => { hasDue.checked = true; date.value = ymd(day); drawWhen(); } }, label)));
  hasDue.onchange = drawWhen;
  hasTime.onchange = () => { drawWhen(); drawAlerts(false); };

  const who = h('div', { class: 'chiprow' });
  const drawWho = () => fill(who, S.members.map((m) => h('button', { type: 'button', class: `chip toggle mchip ${picked.has(m.id) ? 'on' : ''}`, disabled: ro || null,
    onclick: () => { if (picked.has(m.id)) picked.delete(m.id); else picked.add(m.id); drawWho(); } }, memberBadge(m, true), m.displayName)));
  drawWho();

  const subs = h('div', { class: 'subs' });
  const linked = h('div', { class: 'linked' });
  const drawSubs = async () => {
    if (!t) return;
    const j = await api(`api/tasks/${t.id}`);
    fill(subs, h('div', { class: 'fsec' }, icon('subtask'), 'Subtasks'), h('div', { class: 'tasks' }, j.children.map((x) => {
      const row = taskRow(x, {});
      row.querySelector('.tbody').onclick = () => { closeDialogs(); openTask(x.id); };
      row.querySelector('.info').onclick = () => { closeDialogs(); openTask(x.id); };
      return row;
    })),
    ro ? null : h('input', { class: 'qadd', placeholder: 'Add a subtask', onkeydown: async (e) => {
      if (e.key !== 'Enter' || !e.target.value.trim()) return;
      e.preventDefault();
      try { await api('api/tasks', { method: 'POST', json: { title: e.target.value.trim(), parent: t.id, listId: t.listId } }); await drawSubs(); subs.querySelector('.qadd')?.focus(); } catch (err) { fail(err); }
    } }));
  };

  /** The fields as the API takes them. */
  const collect = () => {
    const data = { title: title.value.trim(), notes: notes.value, priority: prio.value || 'none', url: url.value.trim(), members: [...picked] };
    if (!hasDue.checked) { data.due = null; data.rrule = null; data.repeatAfter = null; data.alarms = []; return data; }
    data.due = hasTime.checked ? `${date.value}T${time.value || '09:00'}` : date.value;
    data.timezone = LOCAL_TZ;
    const after = from.value === 'done' ? afterOf(rule()) : null;
    data.rrule = after ? null : rule() || null;
    data.repeatAfter = after;
    if (alert.value !== 'keep') {
      const due = hasTime.checked ? new Date(`${date.value}T${time.value || '09:00'}`) : parseDay(date.value);
      data.alarms = alert.value === '' ? [] : [new Date(+due - +alert.value * 6e4).toISOString()];
    }
    return data;
  };
  const save = async () => {
    const data = collect();
    if (!data.title) { toast('A title, please'); title.focus(); return; }
    try {
      if (t) {
        if (+list.value !== t.listId) data.listId = +list.value;
        const r = await api(`api/tasks/${t.id}`, { method: 'PATCH', json: data });
        toast('Saved', r.undo);
      } else {
        data.listId = +list.value;
        if (parent) { data.parent = parent.id; data.listId = parent.listId; }
        await api('api/tasks', { method: 'POST', json: data });
        toast('Saved');
      }
      done();
    } catch (e) { fail(e); }
  };
  const del = async () => {
    const n = t.subtasks ? t.subtasks.total : 0;
    if (!await confirmDialog('Delete task', `Delete “${t.title || 'this task'}”${n ? ` and its ${n} subtask${n > 1 ? 's' : ''}` : ''}?`, 'Delete', true)) return;
    try { const r = await api(`api/tasks/${t.id}`, { method: 'DELETE' }); toast('Deleted', r.undo); done(); } catch (e) { fail(e); }
  };
  title.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); save(); } });
  const fld = (l, e, cls) => h('label', { class: `field ${cls || ''}` }, h('span', null, l), e);

  fill(el,
    h('div', { class: 'taskhead', style: { '--c': listOf(+list.value).color || 'var(--brand)' } },
      t ? h('button', { class: `tick big ${t.done ? 'on' : ''}`, title: t.done ? 'Not done after all' : 'Done', disabled: ro || null, onclick: async (e) => {
        try { const res = await api(`api/tasks/${t.id}/complete`, { method: 'POST', json: { done: !t.done, tz: LOCAL_TZ } }); toast(res.moved ? `Done. Next: ${dueText(res)}` : res.done ? 'Done' : 'Open again', res.undo); done(); } catch (err) { fail(err); }
        e.stopPropagation();
      } }) : null,
      title),
    parent ? h('p', { class: 'muted small' }, `Subtask of “${parent.title}”`) : null,
    ro ? h('p', { class: 'muted small' }, 'Read-only: editors and admins change shared lists.') : null,
    notes,
    h('div', { class: 'fsec' }, icon('today'), 'When'), whenRow, laterRow,
    h('div', { class: 'grid', style: { marginTop: '10px' } }, fld('Repeat', h('div', { class: 'reprow' }, repeat, everyBox)), fld('Counted from', from), fld('Alert', alert)),
    t && t.rrule ? h('p', { class: 'muted small' }, `${describeRule(t.rrule, dd)}. Ticking it off moves it to the next date.`) : null,
    t && t.repeatAfter ? h('p', { class: 'muted small' }, `Ticking it off brings it back ${describeAfter(t.repeatAfter).replace(/^A /, 'a ')}.`) : null,
    h('div', { class: 'fsec' }, icon('tune'), 'Details'),
    h('div', { class: 'grid' }, fld('List', list), fld('Priority', prio), fld('Link', url, 'wide')),
    S.members.length > 1 ? [h('div', { class: 'fsec' }, icon('people'), 'For'), who] : null,
    subs,
    linked,
    t ? h('p', { class: 'muted small' }, [t.created ? `Added ${new Date(t.created).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}` : null, t.done && t.completedAt ? `done ${new Date(t.completedAt).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}` : null].filter(Boolean).join(', ')) : null,
    h('div', { class: 'formbar' },
      ro ? null : h('button', { class: 'pillbtn primary noic', onclick: save }, 'Save'),
      h('button', { class: 'pillbtn noic', onclick: done }, ro ? 'Close' : 'Cancel'),
      t && !ro && !t.parent ? h('button', { class: 'pillbtn noic', title: 'A new subtask', onclick: () => { closeDialogs(); location.hash = `#/new?parent=${t.id}`; } }, 'Add subtask') : null,
      h('span', { class: 'grow' }),
      t && !ro ? h('button', { class: 'pillbtn noic danger', onclick: del }, 'Delete') : null));
  list.onchange = () => el.querySelector('.taskhead').style.setProperty('--c', listOf(+list.value).color || 'var(--brand)');
  drawWhen();
  if (t) mountLinks(linked, t.id);
  await drawSubs();
  if (!t) title.focus();
}

/** "Linked" under a task: the events, notes, contacts, recipes and photos of the other apps linked to it (the suite's panel). */
export let linkUi = null;
export async function mountLinks(el, id) {
  try { linkUi = linkUi || await import(new URL('api/related/ui.js', document.baseURI).href); } catch (e) { return; }
  if (el.isConnected) linkUi.mount(el, { kind: 'task', id, toast, onOpen: closeDialogs });
}
