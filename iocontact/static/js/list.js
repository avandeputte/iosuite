import { $, S, api, avatar, confirmDialog, dialog, fail, h, icon, loadMeta, scopeParams, scopeTitle, toast, writableBooks } from './core.js';
import { onRoute, route } from './main.js';

// ------------------------------------------------------------------ the list
export function drawList() {
  const pane = $('#main .listpane'); if (!pane) return;
  const keep = pane.scrollTop;
  const r = route();
  const order = localStorage.getItem('iocontact.order') || 'given';
  const head = h('div', { class: 'listhead' }, h('button', { class: 'iconbtn back', style: { display: 'none' } }),
    h('span', { class: 'title' }, scopeTitle()), h('span', { class: 'count' }, S.total),
    h('span', { class: 'tools' },
      h('button', { class: `iconbtn ${S.selecting ? 'on' : ''}`, title: 'Select', onclick: () => { S.selecting = !S.selecting; S.sel.clear(); drawList(); } }, icon('select', 's')),
      h('button', { class: 'iconbtn', title: `Sort by ${order === 'given' ? 'last name' : 'first name'}`, onclick: () => { localStorage.setItem('iocontact.order', order === 'given' ? 'family' : 'given'); onRoute(); } },
        h('span', { class: 'small', style: { fontWeight: 600 } }, order === 'given' ? 'A·first' : 'A·last')),
      h('a', { class: 'iconbtn', title: 'Download these as vCards', href: `api/contacts?${scopeParams()}&format=vcard` }, icon('download', 's'))));
  const kids = [head];
  if (S.selecting) kids.push(selBar());
  let last = null;
  for (const c of S.list) {
    const key = order === 'family' ? (c.family || c.fn) : (c.given || c.fn);
    const L = (key || '#').trim().charAt(0).toUpperCase();
    const letter = /[A-ZÀ-ɏ]/i.test(L) ? L : '#';
    if (!S.q && letter !== last && order !== 'updated') { kids.push(h('div', { class: 'letter' }, letter)); last = letter; }
    const sub = c.org && c.title ? `${c.title}, ${c.org}` : c.org || c.email || c.phone || '';
    const row = h('a', { class: `row ${r.id === c.id ? 'on' : ''}`, href: `#/c/${c.id}`, onclick: (e) => { if (S.selecting) { e.preventDefault(); toggleSel(c.id); } } },
      S.selecting ? h('input', { type: 'checkbox', checked: S.sel.has(c.id), onclick: (e) => { e.stopPropagation(); toggleSel(c.id); } }) : null,
      avatar(c), h('div', { class: 'who' }, h('div', { class: 'nm' }, c.fn), sub ? h('div', { class: 'sub' }, sub) : null),
      c.favorite ? icon('star', 's star') : null);
    kids.push(row);
  }
  if (!S.list.length) kids.push(h('div', { class: 'empty' }, S.q ? `Nothing matches “${S.q}”.` : 'No contacts here yet.'));
  pane.replaceChildren(...kids);
  pane.scrollTop = keep;
}
export function toggleSel(id) { if (S.sel.has(id)) S.sel.delete(id); else S.sel.add(id); drawList(); }
export function selBar() {
  const ids = [...S.sel];
  const act = async (action, extra = {}) => {
    if (!ids.length) return toast('Select some contacts first');
    if (action === 'delete' && !await confirmDialog('Delete contacts', `Delete ${ids.length} contact(s)? This cannot be undone.`, 'Delete', true)) return;
    try { await api('api/contacts/bulk', { method: 'POST', json: { ids, action, ...extra } }); S.sel.clear(); S.all = null; await loadMeta(); onRoute(); toast('Done'); } catch (e) { fail(e); }
  };
  return h('div', { class: 'selbar' }, h('b', null, `${ids.length} selected`),
    h('button', { class: 'pillbtn noic', onclick: () => { S.list.forEach((c) => S.sel.add(c.id)); drawList(); } }, 'All'),
    h('button', { class: 'pillbtn noic', onclick: () => act('favorite') }, '★'),
    h('button', { class: 'pillbtn noic', onclick: async () => {
      const t = h('input', { class: 't', placeholder: 'Label', list: 'taglist' });
      const v = await dialog('Add a label', h('div', null, t, h('datalist', { id: 'taglist' }, S.tags.map((x) => h('option', { value: x.tag })))), [{ label: 'Cancel', value: null }, { label: 'Add', value: () => t.value, primary: true }]);
      if (v) act('tag', { tag: v });
    } }, 'Label'),
    h('button', { class: 'pillbtn noic', onclick: async () => {
      const sel = h('select', { class: 't' }, writableBooks().map((b) => h('option', { value: b.id }, b.name)));
      const v = await dialog('Move to', sel, [{ label: 'Cancel', value: null }, { label: 'Move', value: () => sel.value, primary: true }]);
      if (v) act('move', { book: +v });
    } }, 'Move'),
    h('a', { class: 'pillbtn noic', href: `api/export?format=vcf&ids=${ids.join(',')}` }, 'Export'),
    h('button', { class: 'pillbtn noic danger', onclick: () => act('delete') }, 'Delete'));
}
