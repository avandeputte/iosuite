import { LABELS, MONTHS, S, allContacts, api, avatar, dialog, fail, fold, h, icon, loadMeta, scopeHash, toast, writableBooks } from './core.js';
import { onRoute } from './main.js';

// ------------------------------------------------------------------ the edit form
export async function showEdit(id, pane) {
  const c = id ? await api(`api/contacts/${id}`) : { name: {}, phones: [{ label: 'mobile', value: '' }], emails: [{ label: 'home', value: '' }], addresses: [], urls: [], social: [], dates: [], relations: [], tags: [],
    bookId: ((S.scope.kind === 'book' && writableBooks().find((b) => b.id === +S.scope.id)) || writableBooks().find((b) => b.shared) || writableBooks()[0] || {}).id, kind: 'individual' };
  const f = JSON.parse(JSON.stringify(c));
  f.name = f.name || {};
  const inp = (obj, key, ph, attrs = {}) => h('input', { class: 't', value: obj[key] || '', placeholder: ph || '', oninput: (e) => { obj[key] = e.target.value; }, ...attrs });
  const fld = (label, el) => h('label', { class: 'field' }, h('span', null, label), el);
  const sel = (obj, key, opts, extra = {}) => h('select', { class: 't', onchange: (e) => { obj[key] = e.target.value; }, ...extra },
    opts.map((o) => { const [v, l] = Array.isArray(o) ? o : [o, o]; return h('option', { value: v, selected: (obj[key] || '') === v ? true : null }, l); }));
  const labelSel = (obj, kind) => {
    const opts = [...LABELS[kind]]; if (obj.label && !opts.includes(obj.label)) opts.push(obj.label);
    const s = h('select', { class: 't' }, h('option', { value: '' }, '—'), opts.map((o) => h('option', { value: o, selected: (obj.label || '') === o ? true : null }, o)), h('option', { value: '__custom' }, 'Custom…'));
    s.onchange = async () => {
      if (s.value === '__custom') {
        const t = h('input', { class: 't', placeholder: 'Label' });
        const v = await dialog('Custom label', t, [{ label: 'Cancel', value: null }, { label: 'OK', value: () => t.value.trim(), primary: true }]);
        if (v) { obj.label = v; s.insertBefore(h('option', { value: v }, v), s.lastChild); s.value = v; } else s.value = obj.label || '';
      } else obj.label = s.value || null;
    };
    return s;
  };
  const rm = (arr, x, redraw) => h('button', { class: 'iconbtn', title: 'Remove', type: 'button', onclick: () => { arr.splice(arr.indexOf(x), 1); redraw(); } }, icon('close', 's'));
  const prefBox = (obj) => h('label', { class: 'prefck', title: 'Preferred' }, h('input', { type: 'checkbox', checked: !!obj.pref, onchange: (e) => { obj.pref = e.target.checked ? 1 : 0; } }), '★');

  function multi(title, ic, arr, kind, rowFn, blank) {
    const box = h('div');
    const draw = () => {
      box.replaceChildren(...arr.map((x) => rowFn(x, draw)), h('button', { class: 'addbtn', type: 'button', onclick: () => { arr.push(blank()); draw(); const ins = box.querySelectorAll('input'); if (ins.length) ins[ins.length - 1].focus(); } }, icon('add', 's'), `Add ${kind}`));
    };
    draw();
    return [h('div', { class: 'fsec' }, icon(ic), title), box];
  }
  const phones = multi('Phone numbers', 'phone', f.phones, 'phone', (x, d) => h('div', { class: 'multi' }, labelSel(x, 'phone'), inp(x, 'value', 'Phone', { type: 'tel' }), prefBox(x), rm(f.phones, x, d)), () => ({ label: 'mobile', value: '' }));
  const emails = multi('Email addresses', 'mail', f.emails, 'email', (x, d) => h('div', { class: 'multi' }, labelSel(x, 'email'), inp(x, 'value', 'Email', { type: 'email' }), prefBox(x), rm(f.emails, x, d)), () => ({ label: 'home', value: '' }));
  const addrs = multi('Addresses', 'place', f.addresses, 'address', (x, d) => h('div', { class: 'multi' }, labelSel(x, 'address'),
    h('div', { class: 'addr' }, inp(x, 'street', 'Street', { style: 'grid-column: 1 / -1' }), inp(x, 'ext', 'Apartment, suite…'), inp(x, 'city', 'City'), inp(x, 'region', 'State / region'),
      inp(x, 'postcode', 'Postal code'), inp(x, 'country', 'Country'), inp(x, 'pobox', 'PO Box')), prefBox(x), rm(f.addresses, x, d)), () => ({ label: 'home' }));
  const social = multi('Social profiles', 'people', f.social, 'profile', (x, d) => h('div', { class: 'multi' },
    sel(x, 'service', S.social.map((s) => [s.service, s.name])), inp(x, 'value', 'Profile address or user name'), rm(f.social, x, d)), () => ({ service: 'linkedin', value: '' }));
  const urls = multi('Websites', 'link', f.urls, 'website', (x, d) => h('div', { class: 'multi' }, labelSel(x, 'url'), inp(x, 'value', 'https://…', { type: 'url' }), rm(f.urls, x, d)), () => ({ label: 'homepage', value: '' }));
  const dateInputs = (obj) => [
    h('select', { class: 't dt', style: 'width:130px', onchange: (e) => { obj.month = +e.target.value || null; } }, h('option', { value: '' }, 'Month'), MONTHS.map((m, i) => h('option', { value: i + 1, selected: obj.month === i + 1 ? true : null }, m))),
    h('input', { class: 't dt', style: 'width:80px', type: 'number', min: 1, max: 31, placeholder: 'Day', value: obj.day || '', oninput: (e) => { obj.day = +e.target.value || null; } }),
    h('input', { class: 't dt', style: 'width:100px', type: 'number', min: 1, max: 9999, placeholder: 'Year', value: obj.year || '', oninput: (e) => { obj.year = +e.target.value || null; } })];
  f.birthday = f.birthday || {};
  const dates = multi('Other dates', 'event', f.dates, 'date', (x, d) => h('div', { class: 'multi' }, labelSel(x, 'date'), ...dateInputs(x), rm(f.dates, x, d)), () => ({ label: 'anniversary' }));

  // relations: a type (gendered labels set the other person's gender when unknown) and a contact or a plain name
  const everyone = await allContacts();
  const relOpts = () => S.rel.groups.map((g) => h('optgroup', { label: g.name }, g.types.flatMap((t) => t.male !== t.female
    ? [h('option', { value: `${t.type}|` }, t.label), h('option', { value: `${t.type}|M` }, t.male), h('option', { value: `${t.type}|F` }, t.female)]
    : [h('option', { value: `${t.type}|` }, t.label)])));
  const rels = multi('Relations', 'tree', f.relations, 'relation', (x, d) => {
    const s = h('select', { class: 't', style: 'width:170px' }, relOpts());
    const g = x.gender || x.relatedGender || '';
    s.value = `${x.type}|${g}`; if (!s.value) s.value = `${x.type}|`;
    s.onchange = () => { const [t, gg] = s.value.split('|'); x.type = t; x.gender = gg || null; };
    const pick = h('div', { class: 'picker' });
    const box = h('input', { class: 't', placeholder: 'Contact or name', value: x.relatedFn || x.relatedName || '' });
    const drop = h('div', { class: 'drop', hidden: true });
    box.oninput = () => {
      x.relatedId = null; x.relatedName = box.value; x.relatedFn = null;
      const q = fold(box.value).trim();
      const hits = q ? everyone.filter((p) => p.id !== f.id && q.split(/\s+/).every((w) => fold(p.fn).includes(w))).slice(0, 12) : [];
      drop.replaceChildren(...hits.map((p) => h('div', { class: 'row', onmousedown: (e) => { e.preventDefault(); x.relatedId = p.id; x.relatedFn = p.fn; x.relatedName = null; box.value = p.fn; drop.hidden = true; } }, avatar(p, 's'), h('div', { class: 'who' }, h('div', { class: 'nm' }, p.fn)))));
      drop.hidden = !hits.length;
    };
    box.onblur = () => setTimeout(() => { drop.hidden = true; }, 150);
    pick.append(box, drop);
    return h('div', { class: 'multi' }, s, pick, x.relatedId ? h('span', { class: 'muted small', title: 'Linked to a contact' }, icon('link', 's')) : null, rm(f.relations, x, d));
  }, () => ({ type: 'sibling', relatedName: '' }));

  // ioPix
  const iopixBox = h('div');
  const drawIopixBox = () => iopixBox.replaceChildren(f.iopix && f.iopix.personId
    ? h('div', { class: 'iopixcard' }, h('img', { src: `api/iopix/face/${f.iopix.personId}`, alt: '' }), h('b', null, f.iopix.name), h('button', { class: 'pillbtn noic', type: 'button', onclick: () => { f.iopix = null; drawIopix(); } }, 'Unlink'))
    : h('button', { class: 'pillbtn', type: 'button', onclick: async () => { const p = await pickIopix(f, false); if (p) { f.iopix = { personId: p.id, name: p.name }; drawIopix(); } } }, icon('image', 's'), 'Link to an ioPix person'));

  // photo: only ever the face of the linked ioPix person
  const prev = h('span');
  const drawPhoto = () => prev.replaceChildren(avatar({ fn: f.fn || f.name.given || c.fn || '?', iopix: f.iopix }, 'xl'));
  const drawIopix = () => { drawIopixBox(); drawPhoto(); };
  drawIopix();

  const tagIn = h('input', { class: 't', value: (f.tags || []).join(', '), placeholder: 'Family, Book club, Neighbors…', list: 'alltags' });
  const bookSel = h('select', { class: 't', onchange: (e) => { f.bookId = +e.target.value; } }, writableBooks().map((b) => h('option', { value: b.id, selected: b.id === f.bookId ? true : null }, b.name)));
  const kindSel = sel(f, 'kind', [['individual', 'Person'], ['org', 'Company or organization']]);
  const notes = h('textarea', { class: 't', placeholder: 'Anything worth remembering', oninput: (e) => { f.notes = e.target.value; } }); notes.value = f.notes || '';

  const save = async (e) => {
    e && e.preventDefault();
    f.tags = tagIn.value.split(',').map((t) => t.trim()).filter(Boolean);
    // a birthday can be any part of a date: a year, a year and month, a month and day, or all three
    if (!(f.birthday && (f.birthday.year || (f.birthday.month && f.birthday.day)))) f.birthday = null;
    f.relations = f.relations.map((r) => ({ type: r.type, relatedId: r.relatedId || null, relatedName: r.relatedId ? null : r.relatedName, gender: r.gender || null, label: r.label || null }));
    const payload = { ...f };
    delete payload.hasPhoto; delete payload.etag;
    try {
      const out = id ? await api(`api/contacts/${id}`, { method: 'PUT', json: payload }) : await api(`api/contacts?book=${f.bookId}`, { method: 'POST', json: payload });
      S.all = null; await loadMeta();
      toast('Saved'); location.hash = `#/c/${out.id}`;
    } catch (err) { fail(err); }
  };
  const nm = f.name;
  const form = h('form', { class: 'form', onsubmit: save },
    h('div', { class: 'pagehead' }, h('button', { class: 'iconbtn back', type: 'button', onclick: () => history.back() }, icon('back')), h('h1', null, id ? `Edit ${c.fn}` : 'New contact')),
    h('div', { class: 'photoedit' }, prev, h('p', { class: 'muted small' }, S.status.iopix
      ? 'The photo comes from ioPix: link this contact to an ioPix person (under ioPix below) to show their face.'
      : 'The photo comes from ioPix: once ioPix is set up, link this contact to a person there to show their face.')),
    h('div', { class: 'fsec' }, icon('person'), 'Name'),
    h('div', { class: 'grid' }, fld('First name', inp(nm, 'given', '', { autofocus: !id })), fld('Middle name', inp(nm, 'additional')), fld('Last name', inp(nm, 'family')),
      fld('Prefix', inp(nm, 'prefix', 'Dr., Mrs.')), fld('Suffix', inp(nm, 'suffix', 'Jr., III')), fld('Nickname', inp(f, 'nickname')), fld('Maiden name', inp(f, 'maiden')),
      fld('Display as', inp(f, 'fn', 'From the name parts')), fld('Gender', sel(f, 'gender', [['', '—'], ['F', 'Female'], ['M', 'Male'], ['O', 'Other'], ['N', 'Not applicable']])),
      fld('Kind', kindSel), fld('Phonetic first', inp(f, 'phoneticGiven')), fld('Phonetic last', inp(f, 'phoneticFamily'))),
    h('div', { class: 'fsec' }, icon('work'), 'Work'),
    h('div', { class: 'grid' }, fld('Company', inp(f, 'org')), fld('Department', inp(f, 'department')), fld('Job title', inp(f, 'title')), fld('Role', inp(f, 'role'))),
    h('div', { class: 'fsec' }, icon('cake'), 'Birthday', h('span', { class: 'muted small' }, ' · fill in what you know: the year, month and year, day and month, or all three')), h('div', { class: 'multi' }, ...dateInputs(f.birthday),
      h('label', { class: 'check', title: 'Unchecked: the birthday stays on the contact and on the Birthdays page but is left out of the birthday calendar feed' },
        h('input', { type: 'checkbox', checked: f.birthdayRemind !== false, onchange: (e) => { f.birthdayRemind = e.target.checked; } }), ' Remind me')),
    ...phones, ...emails, ...addrs, ...social, ...urls, ...dates, ...rels,
    S.status.iopix ? [h('div', { class: 'fsec' }, icon('image'), 'ioPix person'), iopixBox] : null,
    h('div', { class: 'fsec' }, icon('tag'), 'Labels and address book'),
    h('div', { class: 'grid' }, fld('Labels (comma separated)', tagIn), fld('Address book', bookSel)), h('datalist', { id: 'alltags' }, S.tags.map((t) => h('option', { value: t.tag }))),
    h('div', { class: 'fsec' }, icon('note'), 'Notes'), notes,
    h('div', { class: 'formbar' }, h('button', { class: 'pillbtn primary', type: 'submit' }, icon('check', 's'), 'Save'),
      h('button', { class: 'pillbtn noic', type: 'button', onclick: () => { location.hash = id ? `#/c/${id}` : scopeHash(); } }, 'Cancel')));
  pane.replaceChildren(form);
  pane.scrollTop = 0;
}

export async function pickIopix(c, saveNow) {
  let ppl;
  try { ppl = (await api('api/iopix/people')).items; } catch (e) { fail(e); return null; }
  const q = h('input', { class: 't', placeholder: 'Search people in ioPix', value: c.fn || '' });
  const list = h('div', { style: { maxHeight: '50vh', overflowY: 'auto', marginTop: '10px' } });
  let chosen = null, resolveFn;
  const draw = () => {
    const s = fold(q.value).trim();
    const hits = ppl.filter((p) => !s || s.split(/\s+/).every((w) => fold(p.name).includes(w))).slice(0, 80);
    list.replaceChildren(...hits.map((p) => h('div', { class: 'row', onclick: () => { chosen = p; resolveFn(); } },
      h('span', { class: 'av' }, h('img', { src: `api/iopix/face/${p.id}`, alt: '', loading: 'lazy', onerror: (e) => { e.target.remove(); } })),
      h('div', { class: 'who' }, h('div', { class: 'nm' }, p.name), h('div', { class: 'sub' }, `${p.count} photos${p.contact ? ` · linked to ${p.contact.fn}` : ''}`)))));
    if (!hits.length) list.append(h('p', { class: 'muted' }, 'Nobody by that name in ioPix.'));
  };
  q.oninput = draw; draw();
  const body = h('div', null, q, list);
  const done = new Promise((r) => { resolveFn = r; });
  const dlg = dialog('Link to an ioPix person', body, [{ label: 'Cancel', value: null }]);
  await Promise.race([dlg, done]);
  document.querySelector('.dialog-back')?.remove();
  if (chosen && saveNow) {
    try { await api(`api/contacts/${c.id}`, { method: 'PATCH', json: { iopix: { personId: chosen.id, name: chosen.name } } }); toast(`Linked to ${chosen.name} in ioPix`); onRoute(); } catch (e) { fail(e); }
  }
  return chosen;
}
