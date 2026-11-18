import { LOCAL_TZ, S, addDays, api, billAmount, billUrl, calOf, confirmDialog, describeReminder, describeRule, fail, fmtDay, h, icon, loadCals, memberBadge, parseDay, toast, whenText, writable, ymd } from './core.js';
import { go, route } from './main.js';
import { askScope, drawView } from './views.js';
import { eventWeather } from './weather.js';
import { safeUrl } from '../../api/auth/ui.js';  // a link that is a link (never javascript:)

// ------------------------------------------------------------------ one event
export const ridQ = (rid) => (rid ? `?recurrenceId=${encodeURIComponent(rid)}` : '');
/** The event as shown for one occurrence (an occurrence that was not changed has the series' times moved to its date). */
export function forOccurrence(j, rid) {
  if (!rid || (j.overrides || []).includes(rid) || !j.rrule) return j;
  const s = j.allDay ? parseDay(j.start) : new Date(j.start), e = j.allDay ? parseDay(j.end) : new Date(j.end);
  const ns = j.allDay ? parseDay(rid) : new Date(rid);
  const ne = j.allDay ? addDays(ns, Math.round((e - s) / 864e5)) : new Date(+ns + (e - s));  // whole days: a day of 23 or 25 hours is one day
  return { ...j, start: j.allDay ? ymd(ns) : ns.toISOString(), end: j.allDay ? ymd(ne) : ne.toISOString() };
}
export function mapsLink(place) { return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(place)}`; }
export function eventCard(j, inDialog) {
  const c = calOf(j.calendarId), w = c.writable;
  const line = (ic, ...v) => h('div', { class: 'line' }, icon(ic), h('div', { class: 'v' }, ...v));
  const people = (j.people || []).filter((p) => p.name || p.email);
  const occ = { ...j, recurring: !!j.rrule, recurrenceId: j.recurrenceId };
  return h('div', { class: 'evd', style: { '--c': c.color || 'var(--brand)' } },
    h('div', { class: 'tools' },
      w ? h('a', { class: 'iconbtn', title: 'Change (e)', href: `#/edit/${j.id}${j.recurrenceId ? `?rid=${encodeURIComponent(j.recurrenceId)}` : ''}`, onclick: closeDialogs }, icon('edit')) : null,
      writable().length ? h('a', { class: 'iconbtn', title: 'Duplicate', href: `#/new?copy=${j.id}`, onclick: closeDialogs }, icon('dup')) : null,
      h('a', { class: 'iconbtn', title: 'Download (.ics)', href: `api/events/${j.id}?format=ics`, download: `${(j.title || 'event').replace(/[^\w -]/g, '')}.ics` }, icon('download')),
      w ? h('button', { class: 'iconbtn', title: 'Delete', onclick: () => deleteEvent(occ) }, icon('delete')) : null,
      inDialog ? h('button', { class: 'iconbtn', title: 'Close', onclick: closeDialogs }, icon('close')) : null),
    h('h2', null, h('span', { class: 'sq' }), h('span', null, j.title || '(no title)',
      j.status === 'CANCELLED' ? h('span', { class: 'chip', style: { marginLeft: '8px' } }, 'Cancelled') : j.status === 'TENTATIVE' ? h('span', { class: 'chip', style: { marginLeft: '8px' } }, 'Tentative') : null)),
    line('clock', whenText(j), j.timezone && j.timezone !== LOCAL_TZ && !j.allDay ? h('div', { class: 'muted small' }, `Time zone ${j.timezone.replace(/_/g, ' ')}`) : null),
    j.rrule ? line('repeat', describeRule(j.rrule, j.allDay ? parseDay(j.start) : new Date(j.start))) : null,
    (j.members || []).length ? line('person', h('div', { class: 'chiprow' }, j.members.map((m) => h('span', { class: 'chip mchip' }, memberBadge(m), `For ${m.displayName}`)))) : null,
    j.location ? line('place', h('a', { class: 'lnk', href: mapsLink(j.location), target: '_blank', rel: 'noopener' }, j.location), eventWeather(j)) : null,
    people.length ? line('people', h('div', { class: 'chiprow' }, people.map((p) => {
      const label = p.name || p.email;
      const href = p.contactUrl || (p.email ? `mailto:${p.email}` : null);
      return h(href ? 'a' : 'span', { class: 'chip', href, target: p.contactUrl ? '_blank' : null, title: p.email || '' }, p.contactUrl ? icon('contacts', 's') : null, label);
    }))) : null,
    (j.reminders || []).length ? line('bell', (j.reminders || []).map((m) => describeReminder(m, j.allDay)).join(', ')) : null,
    j.notes ? line('note', h('div', { style: { whiteSpace: 'pre-wrap' } }, j.notes)) : null,
    j.url ? line('link', safeUrl(j.url) ? h('a', { class: 'lnk', href: j.url, target: '_blank', rel: 'noopener' }, j.url) : h('span', null, j.url)) : null,
    line('today', c.name || '', j.busy === false ? h('span', { class: 'muted' }, ' · shown as free') : null,
      c.kind === 'birthdays' ? h('div', { class: 'muted small' }, 'From ioContact; change the birthday there.') : null,
      c.kind === 'holidays' ? h('div', { class: 'muted small' }, 'A public holiday (Settings › Holidays and birthdays).') : null,
      c.kind === 'subscribed' ? h('div', { class: 'muted small' }, `From an outside calendar${c.subscription ? ` (${c.subscription.host})` : ''}; it changes there.`) : null),
    /^\d+$/.test(String(j.id)) && !['birthdays', 'holidays', 'subscribed'].includes(c.kind) ? linkedBox(j.id) : null);
}
/** "Linked" under an event: its meeting notes, tasks, contacts, recipes and photos from the other apps (the suite's
    panel); kind 'transaction': under a bill, the links of the ioMoney transaction that paid it (changed in ioMoney). */
export let linkUi = null;
export function linkedBox(id, kind = 'event', empty) {
  const el = h('div', { class: 'linked' });
  (async () => {
    try { linkUi = linkUi || await import(new URL('api/related/ui.js', document.baseURI).href); } catch (e) { return; }
    linkUi.mount(el, { kind, id, toast, onOpen: closeDialogs, empty, first: kind === 'transaction' ? 'event' : undefined });
  })();
  return el;
}
/** A bill from ioMoney (one of its recurring transactions, on the day it is due): what it is, where it opens in
    ioMoney, and, once paid, the links of the transaction that paid it (an event, a receipt's thing), to see, open,
    add and remove. */
export function openBillCard(o) {
  const line = (ic, ...v) => h('div', { class: 'line' }, icon(ic), h('div', { class: 'v' }, ...v));
  const url = billUrl(o);
  closeDialogs();
  const back = h('div', { class: 'dialog-back' });
  back.addEventListener('click', (e) => { if (e.target === back) back.remove(); });
  const card = h('div', { class: 'evd bill-card', style: { '--c': '#94650a' } },
    h('div', { class: 'tools' },
      url ? h('a', { class: 'iconbtn', title: o.transactionId ? 'Open the payment in ioMoney' : 'Open its payments in ioMoney', href: url, target: '_blank', rel: 'noopener' }, icon('open')) : null,
      h('button', { class: 'iconbtn', title: 'Close', onclick: closeDialogs }, icon('close'))),
    h('h2', null, h('span', { class: 'sq' }), h('span', null, o.merchant,
      h('span', { class: 'chip', style: { marginLeft: '8px' } }, o.paid ? 'Paid' : o.amount > 0 ? 'Expected' : 'Due'))),
    line('today', fmtDay(parseDay(o.day))),
    line('money', h('span', { class: o.amount > 0 ? 'bill-in' : '' }, billAmount(o), o.amount > 0 ? ' in' : ''),
      [o.category, o.account].some(Boolean) ? h('div', { class: 'muted small' }, [o.category, o.account].filter(Boolean).join(' · ')) : null),
    o.frequency ? line('repeat', o.frequency, o.subscription ? h('span', { class: 'muted' }, ' · subscription') : null) : null,
    o.transactionId ? linkedBox(o.transactionId, 'transaction', 'Nothing linked to this payment yet. Link the event it was for, a receipt’s thing, a note…')
      : o.paid ? null : h('div', { class: 'muted small bill-note' }, 'Not paid yet. Once ioMoney sees the payment, you can link it to an event, a thing or a note here.'));
  back.append(h('div', { class: 'dialog', role: 'dialog', 'aria-label': o.merchant }, card));
  document.body.append(back);
}
export function closeDialogs() { document.querySelectorAll('.dialog-back').forEach((d) => d.remove()); }
export async function openEvent(o) {
  let j;
  try { j = await api(`api/events/${o.id}${ridQ(o.recurrenceId)}`); } catch (e) { fail(e); return; }
  j = forOccurrence(j, o.recurrenceId);
  if (o.recurrenceId) j.recurrenceId = o.recurrenceId;
  closeDialogs();
  const back = h('div', { class: 'dialog-back' });
  back.addEventListener('click', (e) => { if (e.target === back) back.remove(); });
  back.append(h('div', { class: 'dialog', role: 'dialog' }, eventCard(j, true)));
  document.body.append(back);
  S.open = j;
}
export async function showEventPage(page, r) {
  let j = await api(`api/events/${r.id}${ridQ(r.rid)}`);
  j = forOccurrence(j, r.rid);
  if (r.rid) j.recurrenceId = r.rid;
  S.open = j;
  page.append(h('div', { class: 'pagehead' }, h('a', { class: 'iconbtn', href: `#/${S.view}/${ymd(S.date)}`, title: 'Back' }, icon('back')), h('h1', null, 'Event')),
    h('div', { class: 'box', style: { maxWidth: '640px' } }, eventCard(j, false)));
}
export async function deleteEvent(o) {
  let scope = 'all';
  if (o.recurring && o.recurrenceId) { scope = await askScope('Delete'); if (!scope) return; }
  else if (!await confirmDialog('Delete event', `Delete “${o.title || 'this event'}”${o.recurring ? ' and every time it repeats' : ''}?`, 'Delete', true)) return;
  const qs = o.recurrenceId ? `?scope=${scope}&recurrenceId=${encodeURIComponent(o.recurrenceId)}` : '';
  try { await api(`api/events/${o.id}${qs}`, { method: 'DELETE' }); closeDialogs(); toast('Deleted'); } catch (e) { fail(e); return; }
  await loadCals();
  if (['month', 'week', 'day', 'agenda'].includes(route().view)) drawView(); else go(S.view, S.date);
}
