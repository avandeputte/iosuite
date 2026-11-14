import { S, api, avatar, confirmDialog, dialog, fail, fmtDate, fold, h, icon, loadMeta, toast, writableBooks } from './core.js';
import { drawNav } from './shell.js';
import { onRoute } from './main.js';

// ------------------------------------------------------------------ clean up: duplicates, data quality, suggestions, merges
export async function refreshStatus() { try { S.status = await api('api/status'); drawNav(); } catch { /* */ } }
export const bookName = (id) => (S.books.find((b) => b.id === id) || {}).name;
export const LEVEL_HUE = { 'very likely': '--c-rose', likely: '--c-amber', possible: '--c-slate' };

/** Clean up (everyone, on the address books they can see): probable duplicates, data quality, the suggestions filed
    over MCP, and the merge history with Undo. */
export async function showCleanup(page, r) {
  const tabs = [['dups', 'Duplicates'], ['quality', 'Data quality'], ['suggest', `Suggestions${S.status.suggestions ? ` (${S.status.suggestions})` : ''}`], ['merges', 'Merge history']];
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Clean up')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/cleanup/${k}`; } }, l))));
  const body = h('div'); page.append(body);
  body.append(h('div', { class: 'muted' }, 'Loading…'));
  const views = { dups: maintDups, quality: maintQuality, suggest: maintSuggest, merges: maintMerges };
  await (views[r.tab] || maintDups)(body);
}

export async function maintDups(el) {
  const r = await api('api/duplicates');
  el.replaceChildren(h('p', { class: 'muted' }, 'Contacts that are probably the same person: the same email or phone, the same or a similar name, a nickname (Bob for Robert), the same birthday or company. Other birthdays, genders or a Sr./Jr. count against. The first name has to fit: people who only share a last name, an address, a home phone or a family email are never offered. Merging keeps everything (you choose where they disagree) and can be undone for 30 days.'));
  if (!r.groups.length) { el.append(h('div', { class: 'empty' }, icon('check'), h('p', null, 'No duplicates found.'))); return; }
  for (const g of r.groups) {
    const reasons = g.pairs.length === 1 ? g.pairs[0].reasons : g.pairs.map((p) => `${g.contacts.find((c) => c.id === p.a).fn} / ${g.contacts.find((c) => c.id === p.b).fn}: ${p.reasons.join(', ')}`);
    const box = h('div', { class: 'dup' },
      h('div', { class: 'duphead' }, h('span', { class: 'lvl', style: { '--hue': `var(${LEVEL_HUE[g.level]})` } }, g.level), h('span', { class: 'muted small' }, `score ${g.score}`)),
      h('ul', { class: 'reasons' }, reasons.map((x) => h('li', null, x))),
      g.contacts.map((c) => h('div', { class: 'duprow' }, avatar(c), h('div', { style: { minWidth: 0 } }, h('a', { class: 'lnk', href: `#/c/${c.id}` }, c.fn),
        h('div', { class: 'muted small' }, [c.org, c.email, c.phone, c.birthday ? fmtDate(c.birthday) : null, bookName(c.bookId)].filter(Boolean).join(' · '))))),
      !g.contacts.every((c) => (S.books.find((b) => b.id === c.bookId) || {}).writable) ? null : h('div', { class: 'btns' },
        h('button', { class: 'pillbtn primary', onclick: () => mergeDialog(g.contacts.map((c) => c.id), () => onRoute()) }, icon('merge', 's'), 'Compare and merge…'),
        h('button', { class: 'pillbtn noic', title: 'They are different people: do not offer them again', onclick: async () => {
          await api('api/duplicates/dismiss', { method: 'POST', json: { ids: g.contacts.map((c) => c.id) } }); box.remove(); toast('Kept apart');
        } }, 'Not duplicates')));
    el.append(box);
  }
}

export function fmtValue(field, v) {
  if (v == null) return '';
  if (field === 'name') return v.fn || [v.prefix, v.given, v.additional, v.family, v.suffix].filter(Boolean).join(' ');
  if (field === 'birthday') return fmtDate(v);
  if (field === 'iopix') return v.name || `ioPix person ${v.personId}`;
  if (field === 'gender') return ({ M: 'Male', F: 'Female', O: 'Other', N: 'None', U: 'Unknown' })[v] || v;
  if (field === 'addresses') return [v.street, [v.postcode, v.city].filter(Boolean).join(' '), v.region, v.country].filter(Boolean).join(', ') + (v.label ? ` (${v.label})` : '');
  if (field === 'social') return `${(S.social.find((x) => x.service === v.service) || {}).name || v.service}: ${v.value}`;
  if (field === 'relations') return `${v.typeLabel || v.type}: ${v.relatedFn || v.relatedName}`;
  if (field === 'dates') return `${v.label}: ${fmtDate(v)}`;
  if (typeof v === 'object') return `${v.value}${v.label ? ` (${v.label})` : ''}`;
  return String(v);
}

export const FIELD_LABEL = { name: 'Name', nickname: 'Nickname', maiden: 'Maiden name', gender: 'Gender', birthday: 'Birthday', org: 'Company', department: 'Department',
  title: 'Job title', role: 'Role', notes: 'Notes', iopix: 'ioPix person', phoneticGiven: 'Phonetic first name', phoneticFamily: 'Phonetic last name',
  emails: 'Emails', phones: 'Phones', addresses: 'Addresses', urls: 'Websites', social: 'Social profiles', dates: 'Dates', tags: 'Labels', relations: 'Relations' };

export async function mergeDialog(ids, done, keepId) {
  let pv; try { pv = await api(`api/merge/preview?ids=${ids.join(',')}&keep=${keepId || ids[0]}`); } catch (e) { fail(e); return; }
  const byId = Object.fromEntries(pv.contacts.map((c) => [c.id, c]));
  const pick = {}; const keepLists = {};
  const body = h('div', { class: 'mergedlg' });
  body.append(h('div', { class: 'mrow' }, h('div', { class: 'mk' }, 'Keep'), h('div', { class: 'mv' }, pv.contacts.map((c) => h('label', { class: 'check' },
    h('input', { type: 'radio', name: 'mkeep', checked: c.id === pv.keep, onchange: () => { back.remove(); mergeDialog(ids, done, c.id); } }),
    `${c.fn} (${bookName(c.bookId) || 'book'})`))), h('p', { class: 'muted small' }, 'The kept contact stays in its address book and keeps its link in phones; the others are deleted.')));
  for (const [field, opts] of Object.entries(pv.choices)) {
    const name = `mf-${field}`;
    const current = (opts.find((o) => JSON.stringify(field === 'name' ? Object.fromEntries(Object.entries(pv.merged.name).filter(([, x]) => x)) : pv.merged[field]) === JSON.stringify(o.value)) || opts[0]).contactId;
    pick[field] = current;
    body.append(h('div', { class: 'mrow' }, h('div', { class: 'mk' }, FIELD_LABEL[field] || field), h('div', { class: 'mv' }, opts.map((o) => h('label', { class: 'check' },
      h('input', { type: 'radio', name, checked: o.contactId === current, onchange: () => { pick[field] = o.contactId; } }),
      h('span', null, fmtValue(field, o.value)),
      h('span', { class: 'muted small' }, ` · ${byId[o.contactId].fn}`))))));
  }
  for (const field of ['phones', 'emails', 'addresses', 'urls', 'social', 'dates', 'tags', 'relations']) {
    const list = pv.merged[field] || [];
    if (!list.length) continue;
    keepLists[field] = list.map(() => true);
    body.append(h('div', { class: 'mrow' }, h('div', { class: 'mk' }, FIELD_LABEL[field]), h('div', { class: 'mv' }, list.map((x, i) => h('label', { class: 'check' },
      h('input', { type: 'checkbox', checked: true, onchange: (e) => { keepLists[field][i] = e.target.checked; } }), field === 'tags' ? x : fmtValue(field, x))))));
  }
  const back = h('div', { class: 'dialog-back' });
  const close = () => back.remove();
  back.addEventListener('click', (e) => { if (e.target === back) close(); });
  back.append(h('div', { class: 'dialog wide', role: 'dialog' }, h('h2', null, `Merge ${pv.contacts.length} contacts`), body,
    h('div', { class: 'btns' }, h('button', { class: 'pillbtn noic', onclick: close }, 'Cancel'),
      h('button', { class: 'pillbtn primary noic', onclick: async () => {
        const res = JSON.parse(JSON.stringify(pv.merged));
        for (const [field, cid] of Object.entries(pick)) {
          const src = byId[cid];
          if (field === 'name') { res.name = { ...src.name }; res.fn = src.fn; } else res[field] = src[field];
        }
        for (const [field, flags] of Object.entries(keepLists)) res[field] = (pv.merged[field] || []).filter((_, i) => flags[i]);
        try {
          await api('api/contacts/merge', { method: 'POST', json: { keep: pv.keep, others: ids.filter((x) => x !== pv.keep), result: res } });
          close(); S.all = null; await loadMeta(); toast('Merged. Clean up › Merge history can undo it for 30 days.'); done && done(pv.keep);
        } catch (e) { fail(e); }
      } }, 'Merge'))));
  document.body.append(back);
}

export async function maintQuality(el) {
  const r = await api('api/quality');
  const found = r.checks.filter((c) => c.count), clear = r.checks.filter((c) => !c.count);
  el.replaceChildren(h('p', { class: 'muted' }, 'Checks for untidy or doubtful data. Where a fix is offered it changes only contacts you may change; everything else links to the contact to correct by hand.'));
  if (!found.length) el.append(h('div', { class: 'empty' }, icon('check'), h('p', null, 'Everything looks tidy.')));
  const SEV = { problem: '--c-rose', tidy: '--c-amber', info: '--c-slate' };
  for (const c of found) {
    const cc = h('input', { class: 't', placeholder: '+32', style: { width: '80px' }, value: (() => { try { return localStorage.getItem('iocontact.cc') || ''; } catch { return ''; } })() });
    const fixBtn = c.fix ? h('button', { class: 'pillbtn', onclick: async () => {
      const json = { check: c.check };
      if (c.check === 'national_phone') { if (!cc.value.trim()) { toast('Type the country code first, such as +32'); cc.focus(); return; } json.countryCode = cc.value; try { localStorage.setItem('iocontact.cc', cc.value); } catch { /* */ } }
      try { const res = await api('api/quality/fix', { method: 'POST', json }); toast(`Fixed ${res.fixed.length}${res.skipped.length ? `, ${res.skipped.length} left (not yours to change, or nothing found)` : ''}`); S.all = null; onRoute(); } catch (e) { fail(e); }
    } }, icon('check', 's'), c.fix) : null;
    el.append(h('details', { class: 'qcheck' }, h('summary', null, h('span', { class: 'lvl', style: { '--hue': `var(${SEV[c.severity]})` } }, c.count), h('b', null, c.title)),
      h('div', { class: 'qbody' }, c.fix ? h('p', null, c.check === 'national_phone' ? [h('span', { class: 'muted' }, 'Country code to add: '), cc, ' '] : null, fixBtn) : null,
        h('table', { class: 't' }, c.items.slice(0, 300).map((x) => h('tr', null, h('td', null, h('a', { class: 'lnk', href: `#/c/${x.contactId}` }, x.fn)), h('td', { class: 'muted' }, x.detail || ''), h('td', { class: 'muted small' }, bookName(x.bookId) || '')))),
        c.items.length > 300 ? h('p', { class: 'muted small' }, `and ${c.items.length - 300} more`) : null)));
  }
  if (clear.length) el.append(h('p', { class: 'muted small', style: { marginTop: '16px' } }, icon('check', 's'), ' No findings: ', clear.map((c) => c.title.toLowerCase()).join('; '), '.'));
}

export function suggList(items, canEdit, after) {
  const wrap = h('div', { class: 'slist' });
  for (const x of items) {
    const row = h('div', { class: 'srow' },
      h('div', { class: 'sk' }, x.fieldLabel),
      h('div', { class: 'sv' }, fmtValue(x.field, x.value),
        h('div', { class: 'muted small' }, x.source, x.by ? ` · via ${x.by}` : '', x.evidence && /^https?:\/\//i.test(x.evidence) ? [' · ', h('a', { class: 'lnk', href: x.evidence, target: '_blank', rel: 'noopener noreferrer' }, 'source ', icon('open', 's'))] : null, x.note ? ` · ${x.note}` : '')),
      h('div', { class: 'sb' },
        canEdit ? h('button', { class: 'pillbtn noic primary', onclick: async () => { try { await api(`api/suggestions/${x.id}/accept`, { method: 'POST' }); row.remove(); await refreshStatus(); after && after(x); } catch (e) { fail(e); } } }, 'Accept') : null,
        canEdit ? h('button', { class: 'pillbtn noic', onclick: async () => { await api(`api/suggestions/${x.id}/dismiss`, { method: 'POST' }); row.remove(); await refreshStatus(); } }, 'Dismiss') : null));
    wrap.append(row);
  }
  return wrap;
}

export async function maintSuggest(el) {
  const r = await api('api/suggestions');
  const prog = h('span', { class: 'muted' });
  const run = h('button', { class: 'pillbtn', onclick: async () => {
    run.disabled = true; let offset = 0, total = 1, added = 0;
    while (offset < total) {
      prog.textContent = `Looking up… ${offset} of ${total === 1 ? '?' : total}`;
      try { const res = await api('api/lookup', { method: 'POST', json: { offset, limit: 20 } }); total = res.total; offset += Math.max(res.done, 1); added += res.added; } catch (e) { fail(e); break; }
    }
    prog.textContent = `${added} new suggestion${added === 1 ? '' : 's'}`; await refreshStatus(); setTimeout(onRoute, 800);
  } }, icon('bulb', 's'), 'Look up all contacts');
  el.replaceChildren(h('div', { class: 'box' }, h('h2', null, icon('bulb'), 'Enrichment'),
    h('p', null, 'Suggestions for your contacts, from public sources: Gravatar (looked up by email address, sent as a hash), and the GitHub, Mastodon and Bluesky profiles on a contact. LinkedIn, Facebook, Instagram and X offer no lookup that apps may use; an AI assistant connected over MCP can research people there and file what it finds here. Nothing changes until you accept it, and what you dismiss is not offered again.'),
    h('p', null, run, ' ', prog)));
  if (!r.items.length) { el.append(h('div', { class: 'empty' }, icon('check'), h('p', null, 'No suggestions waiting.'))); return; }
  const by = new Map();
  for (const x of r.items) { if (!by.has(x.contactId)) by.set(x.contactId, []); by.get(x.contactId).push(x); }
  for (const [cid, list] of by) {
    const book = S.books.find((b) => b.id === list[0].bookId); const canEdit = book && book.writable;
    const box = h('div', { class: 'dup' }, h('div', { class: 'duprow' }, avatar({ id: cid, fn: list[0].fn }), h('a', { class: 'lnk', href: `#/c/${cid}` }, h('b', null, list[0].fn)),
      h('span', { style: { flex: 1 } }),
      canEdit ? h('button', { class: 'pillbtn noic', onclick: async () => {
        for (const x of list) { try { await api(`api/suggestions/${x.id}/accept`, { method: 'POST' }); } catch { /* a rival value already taken */ } }
        await refreshStatus(); onRoute();
      } }, 'Accept all') : null,
      canEdit ? h('button', { class: 'pillbtn noic', onclick: async () => { for (const x of list) await api(`api/suggestions/${x.id}/dismiss`, { method: 'POST' }); await refreshStatus(); box.remove(); } }, 'Dismiss all') : null),
    suggList(list, canEdit, () => {}));
    el.append(box);
  }
}

export async function maintMerges(el) {
  const r = await api('api/merges');
  el.replaceChildren(h('p', { class: 'muted' }, 'Each merge is kept for 30 days with the contacts as they were before it, so it can be undone: the merged contacts come back as they were, with their relations. After that, or once a merged contact is gone for good, it can no longer be undone.'));
  if (!r.items.length) { el.append(h('div', { class: 'empty' }, h('p', null, 'No merges yet.'))); return; }
  el.append(h('table', { class: 't' }, h('tr', null, h('th', null, 'When'), h('th', null, 'Contacts'), h('th', null, 'By'), h('th')),
    r.items.map((m) => h('tr', null, h('td', null, new Date(m.at).toLocaleString()),
      h('td', null, m.names, m.keepName ? [h('br'), h('a', { class: 'lnk small', href: `#/c/${m.keepId}` }, `now ${m.keepName}`)] : null),
      h('td', null, m.by || ''),
      h('td', null, m.undone ? h('span', { class: 'muted' }, 'undone') : m.canUndo ? h('button', { class: 'pillbtn noic', onclick: async () => {
        if (!await confirmDialog('Undo merge', `Put ${m.names} back as they were before the merge?${m.changedSince ? ' Changes made to the merged contact since then are lost.' : ''}`, 'Undo merge')) return;
        try { await api(`api/merges/${m.id}/undo`, { method: 'POST' }); S.all = null; await loadMeta(); toast('Merge undone'); onRoute(); } catch (e) { fail(e); }
      } }, 'Undo') : h('span', { class: 'muted' }, 'can no longer be undone'))))));
}

export async function showImport(page) {
  const wb = writableBooks();
  const book = h('select', { class: 't', style: 'width:auto' }, wb.map((b) => h('option', { value: b.id }, b.name)));
  const mode = h('select', { class: 't', style: 'width:auto' }, h('option', { value: 'update' }, 'Update contacts already here (same UID)'), h('option', { value: 'skip' }, 'Skip contacts already here'));
  const file = h('input', { type: 'file', accept: '.vcf,.vcard,.csv,.json,text/vcard,text/csv,application/json' });
  const out = h('div', { class: 'muted', style: { marginTop: '8px' } });
  const ebook = h('select', { class: 't', style: 'width:auto' }, h('option', { value: 'all' }, 'All address books'), S.books.map((b) => h('option', { value: b.id }, b.name)));
  const exp = (fmt) => { location.href = `api/export?format=${fmt}&book=${ebook.value}`; };
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Import and export')),
    h('div', { class: 'box' }, h('h2', null, icon('upload'), 'Import'),
      h('p', { class: 'muted' }, 'vCard files (.vcf, from Apple Contacts, iPhone, Android, Outlook, Thunderbird, Google… vCard 2.1, 3.0 and 4.0; many contacts in one file), jCard (.json), or a CSV exported from Google Contacts or Outlook.'),
      h('div', { class: 'multi' }, h('span', null, 'Into'), book, mode), h('div', { class: 'multi' }, file,
        h('button', { class: 'pillbtn primary', onclick: async () => {
          if (!file.files[0]) return toast('Pick a file first');
          const fd = new FormData(); fd.append('file', file.files[0]); fd.append('book', book.value); fd.append('mode', mode.value);
          out.textContent = 'Importing…';
          try { const r = await api('api/import', { method: 'POST', body: fd }); out.textContent = `Read ${r.read}: ${r.created} new, ${r.updated} updated, ${r.skipped} skipped.`; S.all = null; await loadMeta(); } catch (e) { out.textContent = ''; fail(e); }
        } }, icon('upload', 's'), 'Import')), out),
    h('div', { class: 'box' }, h('h2', null, icon('download'), 'Export'), h('div', { class: 'multi' }, h('span', null, 'From'), ebook),
      h('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } },
        h('button', { class: 'pillbtn noic', onclick: () => exp('vcf') }, 'vCard 3.0 (most apps)'), h('button', { class: 'pillbtn noic', onclick: () => exp('vcf4') }, 'vCard 4.0'),
        h('button', { class: 'pillbtn noic', onclick: () => exp('csv-google') }, 'Google CSV'), h('button', { class: 'pillbtn noic', onclick: () => exp('csv-outlook') }, 'Outlook CSV'),
        h('button', { class: 'pillbtn noic', onclick: () => exp('jcard') }, 'jCard (JSON)'))));
}

export async function showIopix(page) {
  const r = await api('api/iopix/people');
  const q = h('input', { class: 't', placeholder: 'Search', style: 'max-width:280px' });
  const grid = h('div', { class: 'ppl' });
  const draw = () => {
    const s = fold(q.value).trim();
    grid.replaceChildren(...r.items.filter((p) => !s || fold(p.name).includes(s)).map((p) => h('div', { class: 'pcard' },
      h('img', { src: `api/iopix/face/${p.id}`, alt: '', loading: 'lazy', onerror: (e) => { e.target.style.visibility = 'hidden'; } }), h('div', { class: 'nm' }, p.name), h('div', { class: 'muted small' }, `${p.count} photos`),
      p.contact ? h('a', { class: 'lnk small', href: `#/c/${p.contact.id}` }, p.contact.fn)
        : h('button', { class: 'pillbtn noic', onclick: async () => {
          const parts = p.name.split(' ');
          try { const c = await api(`api/contacts?book=${(writableBooks().find((b) => b.shared) || writableBooks()[0]).id}`, { method: 'POST', json: { name: { given: parts[0], family: parts.slice(1).join(' ') }, iopix: { personId: p.id, name: p.name } } });
            S.all = null; await loadMeta(); location.hash = `#/c/${c.id}/edit`; } catch (e) { fail(e); }
        } }, 'Make a contact'))));
  };
  q.oninput = draw; draw();
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'ioPix people'), q,
    h('button', { class: 'pillbtn', onclick: async () => {
      const s = await api('api/iopix/auto-link?dry=true', { method: 'POST' });
      if (!s.items.length) return toast('No unlinked contact has the exact name of an ioPix person');
      if (!await dialog('Link by name', h('div', null, h('p', null, `${s.items.length} contact(s) have the exact name of one ioPix person:`), h('ul', null, s.items.slice(0, 40).map((x) => h('li', null, x.fn)))), [{ label: 'Cancel', value: false }, { label: 'Link them', value: true, primary: true }])) return;
      await api('api/iopix/auto-link?dry=false', { method: 'POST' }); toast('Linked'); onRoute();
    } }, icon('link', 's'), 'Link by name')),
  h('p', { class: 'muted' }, 'Everyone named in ioPix. A linked contact shows the face from ioPix and links to their photos.'), grid);
}
