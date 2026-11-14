import { api, avatar, fail, h, icon, toast } from './core.js';
import { onRoute } from './main.js';

// ------------------------------------------------------------------ pages
export async function showUpcoming(page) {
  const days = +(localStorage.getItem('iocontact.days') || 60);
  const r = await api(`api/upcoming?days=${days}`);
  const range = h('select', { class: 't', style: 'width:auto', onchange: (e) => { localStorage.setItem('iocontact.days', e.target.value); onRoute(); } },
    [14, 30, 60, 90, 180, 366].map((d) => h('option', { value: d, selected: d === days ? true : null }, d === 366 ? 'The next year' : `The next ${d} days`)));
  const when = (x) => x.inDays === 0 ? 'Today' : x.inDays === 1 ? 'Tomorrow' : `In ${x.inDays} days`;
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Birthdays and anniversaries'), range,
    h('a', { class: 'pillbtn', href: '#/settings/devices' }, icon('event', 's'), 'Subscribe in your calendar')),
  r.items.length ? h('div', null, r.items.map((x) => h('div', { class: 'upc' },
    h('a', { class: 'who', href: `#/c/${x.contactId}` }, avatar({ id: x.contactId, fn: x.fn, hasPhoto: x.hasPhoto, iopixPersonId: x.iopixPersonId }, 'm'),
      h('div', null, h('div', null, h('b', null, x.fn)), h('div', { class: 'muted' }, `${x.label === 'birthday' ? 'Birthday' : x.label.charAt(0).toUpperCase() + x.label.slice(1)}${x.turns != null ? (x.label === 'birthday' ? ` · turns ${x.turns}` : ` · ${x.turns} years`) : ''}`))),
    h('div', { class: 'when' }, h('div', { class: 'days' }, when(x)), h('div', { class: 'muted small' }, new Date(x.date + 'T12:00').toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' }))),
    // every birthday is listed; "Remind me" only decides whether it goes in the birthday calendar feed
    x.label === 'birthday' && x.remind != null ? h('label', { class: 'check remind', title: 'Checked: this birthday is in the birthday calendar feed' },
      h('input', { type: 'checkbox', checked: x.remind, onchange: async (e) => {
        const box = e.target; box.disabled = true;
        try { await api(`api/contacts/${x.contactId}`, { method: 'PATCH', json: { birthdayRemind: box.checked } }); x.remind = box.checked; toast(box.checked ? `${x.fn}'s birthday is in the calendar feed` : `${x.fn}'s birthday is left out of the calendar feed`); }
        catch (err) { box.checked = !box.checked; fail(err); } finally { box.disabled = false; }
      } }), ' Remind me') : h('span', { class: 'remind' }))))
    : h('div', { class: 'empty' }, icon('cake'), h('p', null, 'No birthdays or anniversaries in that time.')));
}
