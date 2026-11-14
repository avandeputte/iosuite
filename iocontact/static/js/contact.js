import { S, SOCIAL_COLORS, age, ageWord, api, avatar, confirmDialog, fail, fmtDate, h, icon, loadMeta, scopeHash, toast } from './core.js';
import { refreshStatus, suggList } from './cleanup.js';
import { pickIopix } from './edit.js';
import { onRoute } from './main.js';

// ------------------------------------------------------------------ a contact
export async function showContact(id, pane) {
  const c = await api(`api/contacts/${id}`);
  S.current = c;
  const book = S.books.find((b) => b.id === c.bookId);
  const canEdit = book && book.writable;
  const back = h('button', { class: 'iconbtn back', title: 'Back', onclick: () => { location.hash = scopeHash(); } }, icon('back'));
  const sub = [c.title, c.department, c.org].filter(Boolean).join(' · ');
  const fav = h('button', { class: `iconbtn ${c.favorite ? 'on' : ''}`, title: c.favorite ? 'Remove from favorites' : 'Add to favorites', disabled: !canEdit,
    onclick: async () => { try { await api(`api/contacts/${id}`, { method: 'PATCH', json: { favorite: !c.favorite } }); onRoute(); } catch (e) { fail(e); } } }, icon(c.favorite ? 'star' : 'starO'));
  const a = age(c.birthday);
  const headChips = [c.nickname ? h('span', { class: 'chip' }, `“${c.nickname}”`) : null,
    book ? h('a', { class: 'chip', href: `#/book/${book.id}` }, h('span', { class: 'dot', style: { width: '8px', height: '8px', borderRadius: '50%', background: book.color || (book.shared ? 'var(--c-purple)' : 'var(--c-teal)') } }), book.name) : null,
    ...c.tags.map((t) => h('a', { class: 'chip', href: `#/tag/${encodeURIComponent(t)}` }, icon('tag', 's'), t))];
  const cards = [];
  const card = (ic, title, hueVar, ...body) => h('div', { class: 'card', style: { '--hue': `var(${hueVar})` } }, h('h3', null, icon(ic), title), ...body);
  const kv = (k, v, pref) => h('div', { class: 'kv' }, h('div', { class: 'k' }, k || ''), h('div', { class: 'v' }, v, pref ? h('span', { class: 'pref' }, '★') : null));
  if (c.phones.length) cards.push(card('phone', 'Phone', '--c-green', c.phones.map((p) => kv(p.label, h('a', { class: 'lnk', href: `tel:${p.value.replace(/[^\d+]/g, '')}` }, p.value), p.pref))));
  if (c.emails.length) cards.push(card('mail', 'Email', '--c-blue', c.emails.map((e) => kv(e.label, h('a', { class: 'lnk', href: `mailto:${e.value}` }, e.value), e.pref))));
  if (c.addresses.length) cards.push(card('place', 'Address', '--c-rose', c.addresses.map((ad) => {
    const lines = [ad.pobox && `PO Box ${ad.pobox}`, ad.ext, ad.street, [ad.postcode, ad.city].filter(Boolean).join(' '), ad.region, ad.country].filter(Boolean);
    const q = encodeURIComponent(lines.join(', '));
    return kv(ad.label, h('div', null, lines.map((l) => h('div', null, l)), h('a', { class: 'lnk small', href: `https://www.openstreetmap.org/search?query=${q}`, target: '_blank', rel: 'noopener' }, 'Map')));
  })));
  if (c.birthday || c.dates.length) cards.push(card('cake', 'Dates', '--c-amber',
    c.birthday ? kv('birthday', h('span', null, fmtDate(c.birthday), a != null ? h('span', { class: 'muted' }, ` · ${ageWord(c.birthday)}`) : null,
      c.birthdayRemind === false ? h('span', { class: 'muted', title: 'Left out of the birthday calendar feed' }, ' · not in the calendar feed') : null)) : null,
    c.dates.map((d) => kv(d.label, h('span', null, fmtDate(d), d.year ? h('span', { class: 'muted' }, ` · ${age(d)} years`) : null)))));
  const implied = c.impliedRelations || [];
  if (c.relations.length || implied.length) {
    const fam = new Set(S.rel.groups[0].types.map((t) => t.type));
    // implied by the family (her parent's sister is her aunt): worked out live, saved only when asked
    const keep = async (r) => {
      const rels = c.relations.map((x) => ({ type: x.type, relatedId: x.relatedId || null, relatedName: x.relatedId ? null : x.relatedName, label: x.label || null }));
      const payload = { ...c, relations: [...rels, { type: r.type, relatedId: r.relatedId }] };
      delete payload.hasPhoto; delete payload.etag; delete payload.impliedRelations;
      try { await api(`api/contacts/${id}`, { method: 'PUT', json: payload }); toast(`${r.relatedFn} saved as ${r.typeLabel.toLowerCase()}`); onRoute(); } catch (e) { fail(e); }
    };
    const ichip = (r) => h('span', { class: 'chip rel implied', title: `Implied: ${r.viaLabel.toLowerCase()} ${r.viaFn}` },
      h('a', { href: `#/c/${r.relatedId}` }, avatar({ id: r.relatedId, fn: r.relatedFn, hasPhoto: r.relatedHasPhoto, iopixPersonId: r.relatedIopixPersonId }, 's')),
      h('a', { href: `#/c/${r.relatedId}` }, r.relatedFn), h('span', { class: 'lab' }, `${r.typeLabel} · via ${r.viaFn}`),
      canEdit ? h('button', { class: 'keep', title: `Save as ${r.typeLabel.toLowerCase()}, so it also goes to phones and other apps`, onclick: () => keep(r) }, '+') : null);
    const chip = (r) => r.relatedId ? h('a', { class: 'chip rel', href: `#/c/${r.relatedId}` }, avatar({ id: r.relatedId, fn: r.relatedFn, hasPhoto: r.relatedHasPhoto, iopixPersonId: r.relatedIopixPersonId }, 's'), r.relatedFn, h('span', { class: 'lab' }, r.typeLabel))
      : h('span', { class: 'chip rel' }, avatar({ fn: r.relatedName }, 's'), r.relatedName, h('span', { class: 'lab' }, r.typeLabel));
    const famRels = c.relations.filter((r) => fam.has(r.type)), others = c.relations.filter((r) => !fam.has(r.type));
    cards.push(card('tree', 'Relations', '--c-purple',
      famRels.length ? h('div', null, famRels.map(chip)) : null,
      implied.length ? h('div', null, h('div', { class: 'muted small', style: { margin: '2px 0 6px' } }, 'Implied by the family'), implied.map(ichip)) : null,
      others.length ? h('div', null, others.map(chip)) : null,
      famRels.some((r) => r.relatedId) || implied.length ? h('a', { class: 'lnk small', href: `#/tree/${c.id}` }, 'Family tree') : null));
  }
  if (c.social.length) cards.push(card('people', 'Social', '--c-indigo', h('div', null, c.social.map((s) => {
    const [col, ab] = SOCIAL_COLORS[s.service] || SOCIAL_COLORS.other;
    const name = (S.social.find((x) => x.service === s.service) || {}).name || s.service;
    const show = s.value.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '');
    return h('a', { class: 'social', href: s.url, target: '_blank', rel: 'noopener', title: name }, h('span', { class: 'badge', style: { background: col } }, ab), show);
  }))));
  if (c.urls.length) cards.push(card('link', 'Websites', '--c-cyan', c.urls.map((u) => kv(u.label, h('a', { class: 'lnk', href: /^[a-z]+:/i.test(u.value) ? u.value : `https://${u.value}`, target: '_blank', rel: 'noopener' }, u.value)))));
  if (c.iopix) cards.push(card('image', 'ioPix', '--c-indigo', h('div', { class: 'iopixcard' },
    h('img', { src: `api/iopix/face/${c.iopix.personId}`, alt: '', onerror: (e) => { e.target.style.visibility = 'hidden'; } }),
    h('div', null, h('div', null, h('b', null, c.iopix.name || `Person ${c.iopix.personId}`)),
      c.iopix.url ? h('a', { class: 'lnk', href: c.iopix.url, target: '_blank', rel: 'noopener' }, 'Photos in ioPix ', icon('open', 's')) : null,
      canEdit ? h('div', { style: { marginTop: '6px', display: 'flex', gap: '6px', flexWrap: 'wrap' } },
        h('button', { class: 'pillbtn noic', onclick: async () => { await api(`api/contacts/${id}`, { method: 'PATCH', json: { iopix: null } }); onRoute(); } }, 'Unlink')) : null))));
  if (c.notes) cards.push(card('note', 'Notes', '--c-slate', h('div', { class: 'notes' }, c.notes)));
  const meCard = S.user.meContactId === c.id;
  const tools = h('div', { class: 'dtools' },
    canEdit ? h('a', { class: 'pillbtn primary', href: `#/c/${id}/edit` }, icon('edit', 's'), 'Edit') : null,
    h('a', { class: 'pillbtn', href: `api/contacts/${id}?format=vcard` }, icon('download', 's'), 'vCard'),
    S.status.iopix && !c.iopix && canEdit ? h('button', { class: 'pillbtn', onclick: () => pickIopix(c, true) }, icon('image', 's'), 'Link to ioPix') : null,
    !canEdit ? null : h('button', { class: 'pillbtn', title: 'Look this person up (Gravatar by email, and their GitHub, Mastodon and Bluesky profiles). What is found waits for you to accept it.', onclick: async (e) => {
      e.currentTarget.disabled = true;
      try { const r = await api(`api/contacts/${id}/lookup`, { method: 'POST' }); toast(r.added ? `${r.added} suggestion${r.added === 1 ? '' : 's'} found` : r.errors.length ? `Nothing new (${r.errors[0]})` : 'Nothing new found'); await refreshStatus(); onRoute(); } catch (err) { fail(err); }
    } }, icon('bulb', 's'), 'Look up'),
    h('button', { class: 'pillbtn', title: 'Tell CardDAV apps that this card is you', onclick: async () => { await api('api/me-contact', { method: 'PUT', json: { contactId: meCard ? null : c.id } }); S.user = (await api('api/auth/me')).user; toast(meCard ? 'Not you any more' : 'This is now your own card'); onRoute(); } },
      icon('person', 's'), meCard ? 'This is me ✓' : 'This is me'),
    canEdit ? h('button', { class: 'pillbtn danger', onclick: async () => {
      if (!await confirmDialog('Delete contact', `Delete ${c.fn}? Apps synced over CardDAV will delete it too.`, 'Delete', true)) return;
      try { await api(`api/contacts/${id}`, { method: 'DELETE' }); S.all = null; await loadMeta(); location.hash = scopeHash(); } catch (e) { fail(e); }
    } }, icon('delete', 's'), 'Delete') : null);
  let sugg = [];
  try { sugg = (await api(`api/suggestions?contact=${id}`)).items; } catch { /* none */ }
  if (sugg.length) cards.unshift(h('div', { class: 'card sugg', style: { '--hue': 'var(--c-amber)' } }, h('h3', null, icon('bulb'), `Suggestions (${sugg.length})`),
    h('p', { class: 'muted small' }, 'Found by a lookup or an assistant. Nothing changes until you accept.'), suggList(sugg, canEdit, () => onRoute())));
  pane.replaceChildren(h('div', { class: 'detail' },
    h('div', { class: 'dhead' }, back, avatar(c, 'xl'), h('div', { style: { flex: 1, minWidth: '200px' } },
      h('h1', null, c.fn), sub ? h('div', { class: 'sub' }, sub) : null, c.maiden ? h('div', { class: 'sub' }, `née ${c.maiden}`) : null, h('div', { class: 'chips' }, headChips)), fav),
    tools, cards.length ? h('div', { class: 'cards' }, cards) : h('p', { class: 'muted' }, 'Nothing else is known about this contact yet.'),
    linkedBox(id),
    h('p', { class: 'muted small', style: { marginTop: '24px' } }, `Changed ${new Date(c.updated).toLocaleString()} · UID ${c.uid}`)));
  pane.scrollTop = 0;
}

/** "Linked" under a contact: the events, tasks, notes, recipes and photos of the other apps linked to it (the suite's panel). */
export let linkUi = null;
export function linkedBox(id) {
  const el = h('div', { class: 'linked' });
  (async () => {
    try { linkUi = linkUi || await import(new URL('api/related/ui.js', document.baseURI).href); } catch (e) { return; }
    linkUi.mount(el, { kind: 'contact', id, toast });
  })();
  return el;
}
