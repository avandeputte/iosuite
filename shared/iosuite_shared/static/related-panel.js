/* Linked items, the same in every io app: "Linked" under an event, a task, a note, a contact or a recipe, and the
   picker that links another item to it, from any app of the suite. They talk to /api/related/* next to them
   (iosuite_shared.related). A link works both ways: the other item lists this one too.

     const rel = await import(new URL('api/related/ui.js', document.baseURI).href);
     const panel = rel.mount(el, { kind: 'task', id: 12, toast });   // draws into el (empty while there is nothing to show)
     // more options: canEdit: false (no + and ×, whatever the role), onOpen(item): runs before an item of this same app
     // opens in place (the app closes its dialog, say); items of the other apps open in a new tab
     panel.pick();                                                    // opens the picker (a menu item of the app's own, say)
*/
import { h, api, styles as kitStyles, setToast, toast, fail } from '../auth/ui.js';

const KINDS = {
  event: { label: 'Event', ic: 'M19 4h-1V2h-2v2H8V2H6v2H5c-1.11 0-1.99.9-1.99 2L3 20a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10zM9 14H7v-2h2v2zm4 0h-2v-2h2v2zm4 0h-2v-2h2v2zm-8 4H7v-2h2v2zm4 0h-2v-2h2v2zm4 0h-2v-2h2v2z', c: '#e8710a' },
  task: { label: 'Task', ic: 'M19 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2zm-9 14-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z', c: '#1e8e3e' },
  note: { label: 'Note', ic: 'M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z', c: '#f9ab00' },
  contact: { label: 'Contact', ic: 'M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z', c: '#1a73e8' },
  recipe: { label: 'Recipe', ic: 'M11 9H9V2H7v7H5V2H3v7c0 2.12 1.66 3.84 3.75 3.97V22h2.5v-9.03C11.34 12.84 13 11.12 13 9V2h-2v7zm5-3v8h2.5v8H21V2c-2.76 0-5 2.24-5 4z', c: '#d93025' },
  photo: { label: 'Photo', ic: 'M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z', c: '#9334e6' },
};
const IC = {
  link: 'M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z',
  add: 'M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z',
  close: 'M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z',
  search: 'M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z',
  check: 'M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z',
  open: 'M19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z',
};
const APPS = { iocalendar: 'ioCalendar', iotask: 'ioTask', ionote: 'ioNote', iocontact: 'ioContact', iorecipe: 'ioRecipe', iopix: 'ioPix' };
const svg = (d, cls = 'rl-ic') => { const s = document.createElement('span'); s.className = cls; s.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${d}"/></svg>`; return s; };

const CSS = `
.iosv.rl { margin: 16px 0 0; }
.iosv.rl:empty { display: none; }
.iosv .rl-head { display: flex; align-items: center; gap: 8px; margin: 0 0 6px; }
.iosv .rl-head h3 { margin: 0; font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--sv-fg2); flex: 1; display: flex; align-items: center; gap: 6px; }
.iosv .rl-head h3 .rl-ic { width: 16px; height: 16px; }
.iosv .rl-ic { display: inline-flex; width: 20px; height: 20px; flex: none; }
.iosv .rl-ic svg { width: 100%; height: 100%; fill: currentColor; }
.iosv .rl-add { font: inherit; font-size: 13px; display: inline-flex; align-items: center; gap: 4px; height: 30px; padding: 0 12px 0 8px; border-radius: 999px;
  border: 1px solid var(--sv-line); background: none; color: var(--sv-fg2); cursor: pointer; }
.iosv .rl-add .rl-ic { width: 18px; height: 18px; }
.iosv .rl-add:hover { background: var(--sv-accent-bg); color: var(--sv-accent); border-color: transparent; }
.iosv .rl-list { display: flex; flex-direction: column; gap: 2px; }
.iosv .rl-item { display: flex; align-items: center; gap: 10px; padding: 6px 6px; border-radius: 10px; color: inherit; text-decoration: none; min-width: 0; cursor: pointer; }
.iosv .rl-item:hover, .iosv .rl-item:focus-visible { background: var(--sv-bg2); outline: none; }
.iosv .rl-pic { width: 36px; height: 36px; border-radius: 8px; flex: none; display: flex; align-items: center; justify-content: center; overflow: hidden;
  background: color-mix(in srgb, var(--k) 16%, transparent); color: var(--k); }
.iosv .rl-pic.round { border-radius: 50%; }
.iosv .rl-pic img { width: 100%; height: 100%; object-fit: cover; display: block; }
.iosv .rl-txt { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.iosv .rl-t { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 500; }
.iosv .rl-t.done { text-decoration: line-through; color: var(--sv-fg2); }
.iosv .rl-s { font-size: 12px; color: var(--sv-fg2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.iosv .rl-x { flex: none; width: 30px; height: 30px; border-radius: 50%; border: 0; background: none; color: var(--sv-fg2); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; opacity: .55; }
.iosv .rl-x .rl-ic { width: 18px; height: 18px; }
.iosv .rl-item:hover .rl-x, .iosv .rl-x:focus-visible { opacity: 1; }
.iosv .rl-x:hover { background: var(--sv-accent-bg); color: var(--sv-danger); }
.iosv .rl-none { font-size: 13px; color: var(--sv-fg2); padding: 2px 0 4px; }
/* the picker */
.iosv-back.rl-back { align-items: flex-start; padding-top: 10vh; }
.iosv-back .sv-dialog.rl-dlg { max-width: 560px; padding: 0; display: flex; flex-direction: column; max-height: 80vh; overflow: hidden; }
.iosv .rl-sbar { display: flex; align-items: center; gap: 8px; padding: 12px 14px; border-bottom: 1px solid var(--sv-line); }
.iosv .rl-sbar > .rl-ic { color: var(--sv-fg2); }
.iosv .rl-q { flex: 1; min-width: 0; font: inherit; font-size: 16px; border: 0; outline: none; background: none; color: inherit; height: 32px; }
.iosv .rl-chips { display: flex; gap: 6px; padding: 10px 14px 4px; overflow-x: auto; scrollbar-width: none; flex: none; }
.iosv .rl-chip { font: inherit; font-size: 13px; height: 28px; padding: 0 12px; border-radius: 999px; border: 1px solid var(--sv-line); background: none; color: var(--sv-fg2); cursor: pointer; white-space: nowrap; }
.iosv .rl-chip.on { background: var(--sv-accent-bg); color: var(--sv-accent); border-color: transparent; }
.iosv .rl-res { overflow-y: auto; padding: 4px 8px 12px; flex: 1; min-height: 120px; }
.iosv .rl-grp { margin-top: 8px; }
.iosv .rl-grp h4 { margin: 4px 6px; font-size: 12px; font-weight: 600; color: var(--sv-fg2); }
.iosv .rl-grp .rl-err { font-size: 12px; color: var(--sv-fg2); margin: 0 6px; }
.iosv .rl-item.linked { opacity: .6; cursor: default; }
.iosv .rl-item.linked .rl-x { opacity: 1; color: var(--sv-accent); }
.iosv .rl-photos { display: grid; grid-template-columns: repeat(auto-fill, minmax(76px, 1fr)); gap: 4px; padding: 0 6px; }
.iosv .rl-ph { position: relative; aspect-ratio: 1; border-radius: 8px; overflow: hidden; border: 0; padding: 0; cursor: pointer; background: var(--sv-bg2); }
.iosv .rl-ph img { width: 100%; height: 100%; object-fit: cover; display: block; }
.iosv .rl-ph.linked { outline: 3px solid var(--sv-accent); outline-offset: -3px; cursor: default; }
.iosv .rl-hint { color: var(--sv-fg2); font-size: 13px; padding: 18px 8px; text-align: center; }
@media print { .iosv.rl { display: none; } }
@media (max-width: 600px) {
  .iosv-back.rl-back { padding: 0; }
  .iosv-back .sv-dialog.rl-dlg { max-width: none; max-height: none; height: 100%; border-radius: 0; }
  .iosv .rl-x { opacity: 1; }
}
`;
function styles() {
  kitStyles();
  if (!document.getElementById('iosv-rl-css')) document.head.append(h('style', { id: 'iosv-rl-css' }, CSS));
}

// ------------------------------------------------------------------ how one item reads
const lang = () => document.documentElement.lang || navigator.language || undefined;
function whenText(x) {
  if (!x.when) return '';
  const allDay = x.allDay || x.when.length <= 10;
  const d = new Date(allDay ? x.when.slice(0, 10) + 'T12:00:00' : x.when);
  if (Number.isNaN(d.getTime())) return '';
  const thisYear = d.getFullYear() === new Date().getFullYear();
  const day = d.toLocaleDateString(lang(), { weekday: x.kind === 'event' ? 'short' : undefined, day: 'numeric', month: 'short', year: thisYear ? undefined : 'numeric' });
  if (allDay || x.kind === 'note' || x.kind === 'photo') return day;
  return `${day}, ${d.toLocaleTimeString(lang(), { hour: 'numeric', minute: '2-digit' })}`;
}
function subtitle(x) {
  const k = KINDS[x.kind] || { label: x.kind };
  const w = whenText(x);
  const parts = [k.label];
  if (x.kind === 'task') parts.push(x.done ? 'done' : w ? `due ${w}` : '');
  else if (x.kind === 'note') parts.push(x.text || w);
  else parts.push(w);
  if (x.kind !== 'note' && x.text) parts.push(x.text);
  return parts.filter(Boolean).join(' · ');
}
const imageUrl = (x) => new URL(`../related/image/${x.kind}/${encodeURIComponent(x.id)}${x.image ? `?p=${encodeURIComponent(x.image)}` : ''}`, import.meta.url).href;
function pic(x) {
  const k = KINDS[x.kind] || KINDS.note;
  const box = h('span', { class: 'rl-pic' + (x.kind === 'contact' ? ' round' : ''), style: `--k:${k.c}` });
  if (x.image != null) {
    const img = h('img', { src: imageUrl(x), alt: '', loading: 'lazy' });
    img.addEventListener('error', () => box.replaceChildren(svg(k.ic)));
    box.append(img);
  } else box.append(svg(k.ic));
  return box;
}
/** Open the item: in place when it is in this app, else in a new tab (the other app). */
function open(x, onOpen) {
  if (!x.url) { toast(`${(KINDS[x.kind] || {}).label || 'That app'} has no address yet`); return; }
  let u;
  try { u = new URL(x.url, location.href); } catch { return; }
  if (u.origin === location.origin && u.pathname === location.pathname) { if (onOpen) onOpen(x); location.hash = u.hash; return; }
  window.open(u.href, '_blank', 'noopener');
}

// ------------------------------------------------------------------ "Linked" under an item
export function mount(el, opts = {}) {
  styles(); setToast(opts.toast);
  const { kind, id } = opts;
  const base = `related/${kind}/${encodeURIComponent(id)}`;
  let items = [], canEdit = false, loaded = false;
  el.classList.add('iosv', 'rl');
  const draw = () => {
    el.replaceChildren();
    if (!loaded || (!items.length && !canEdit)) return;
    el.append(h('div', { class: 'rl-head' }, h('h3', null, svg(IC.link), 'Linked'),
      canEdit ? h('button', { class: 'rl-add', type: 'button', title: 'Link an event, a task, a note, a contact, a recipe or a photo', onclick: pick }, svg(IC.add), 'Link') : null));
    if (!items.length) { el.append(h('div', { class: 'rl-none' }, 'Nothing linked yet. Link meeting notes, a recipe, a contact, a photo…')); return; }
    el.append(h('div', { class: 'rl-list' }, items.map((x) => h('div', { class: 'rl-item', role: 'link', tabindex: '0', title: `Open in ${APPS[x.app] || x.app}`,
      onclick: (e) => { if (!e.target.closest('.rl-x')) open(x, opts.onOpen); }, onkeydown: (e) => { if (e.key === 'Enter') open(x, opts.onOpen); } },
      pic(x), h('span', { class: 'rl-txt' }, h('span', { class: 'rl-t' + (x.done ? ' done' : '') }, x.title), h('span', { class: 'rl-s' }, subtitle(x))),
      canEdit ? h('button', { class: 'rl-x', type: 'button', title: 'Remove the link (the item stays)', 'aria-label': 'Remove the link', onclick: () => unlink(x) }, svg(IC.close)) : null))));
  };
  const load = async () => {
    try { const r = await api(base); items = r.items; canEdit = !!r.canEdit && opts.canEdit !== false; } catch (e) { items = []; canEdit = false; }
    loaded = true;
    draw();
  };
  async function unlink(x) {
    try { await api(`${base}/${x.link}`, { method: 'DELETE' }); items = items.filter((i) => i.link !== x.link); draw(); toast('Link removed'); } catch (e) { fail(e); }
  }
  async function pick() {
    const added = await picker({ kind, id, linked: items });
    if (added) { items = [added, ...items.filter((i) => i.link !== added.link)]; draw(); toast(`Linked: ${added.title}`); }
  }
  load();
  return { reload: load, pick: () => pick() };
}

// ------------------------------------------------------------------ the picker
let kindsCache = null;
async function kinds() {
  if (!kindsCache) kindsCache = api('related/kinds').then((r) => r.items).catch(() => { kindsCache = null; return []; });
  return kindsCache;
}

export function picker({ kind, id, linked = [] }) {
  styles();
  return new Promise(async (resolve) => {
    const have = new Set(linked.map((x) => `${x.kind}:${x.id}`));
    have.add(`${kind}:${id}`);
    const all = await kinds();
    let only = '', seq = 0, timer = 0, busy = false;
    const back = h('div', { class: 'iosv-back iosv rl-back' });
    const close = (v) => { back.remove(); removeEventListener('keydown', esc, true); resolve(v); };
    const esc = (e) => { if (e.key === 'Escape') { e.stopPropagation(); close(null); } };
    addEventListener('keydown', esc, true);
    back.addEventListener('click', (e) => { if (e.target === back) close(null); });
    const q = h('input', { class: 'rl-q', type: 'text', placeholder: 'Search the suite to link…', 'aria-label': 'Search', autocomplete: 'off', enterkeyhint: 'search' });
    const res = h('div', { class: 'rl-res' });
    const chipRow = h('div', { class: 'rl-chips', role: 'radiogroup', 'aria-label': 'What to find' });
    const chips = () => chipRow.replaceChildren(...[{ kind: '', plural: 'Everything' }, ...all].map((k) => h('button', { type: 'button', class: 'rl-chip' + (only === k.kind ? ' on' : ''),
      role: 'radio', 'aria-checked': String(only === k.kind), onclick: () => { only = k.kind; chips(); run(); } }, k.plural)));
    chips();
    const hint = () => res.replaceChildren(h('div', { class: 'rl-hint' }, all.length
      ? `Type to find ${all.map((k) => k.plural.toLowerCase()).join(', ').replace(/, ([^,]*)$/, ' and $1')} to link.`
      : 'No other app of the suite can be searched from here.'));
    const choose = async (x) => {
      if (busy || have.has(`${x.kind}:${x.id}`)) return;
      busy = true;
      try { const got = await api(`related/${kind}/${encodeURIComponent(id)}`, { json: { kind: x.kind, id: x.id } }); close(got); } catch (e) { fail(e); busy = false; }
    };
    const row = (x) => {
      const on = have.has(`${x.kind}:${x.id}`);
      return h('div', { class: 'rl-item' + (on ? ' linked' : ''), role: 'button', tabindex: '0', 'aria-disabled': on ? 'true' : null,
        onclick: () => choose(x), onkeydown: (e) => { if (e.key === 'Enter') choose(x); } },
        pic(x), h('span', { class: 'rl-txt' }, h('span', { class: 'rl-t' + (x.done ? ' done' : '') }, x.title), h('span', { class: 'rl-s' }, subtitle(x))),
        on ? h('span', { class: 'rl-x', title: 'Linked already' }, svg(IC.check)) : null);
    };
    const photo = (x) => {
      const on = have.has(`${x.kind}:${x.id}`);
      return h('button', { type: 'button', class: 'rl-ph' + (on ? ' linked' : ''), title: on ? 'Linked already' : subtitle(x), onclick: () => choose(x) },
        h('img', { src: imageUrl(x), alt: subtitle(x), loading: 'lazy' }));
    };
    async function run() {
      clearTimeout(timer);
      const text = q.value.trim();
      if (!text) { hint(); return; }
      const mine = ++seq;
      timer = setTimeout(async () => {
        if (!res.querySelector('.rl-grp')) res.replaceChildren(h('div', { class: 'rl-hint' }, 'Searching…'));
        let groups;
        try { groups = (await api(`related/search?q=${encodeURIComponent(text)}${only ? `&kinds=${only}` : ''}`)).groups; } catch (e) { if (mine === seq) res.replaceChildren(h('div', { class: 'rl-hint' }, e.message)); return; }
        if (mine !== seq) return;
        const shown = groups.filter((g) => g.items.length || (only && g.error));
        if (!shown.length) { res.replaceChildren(h('div', { class: 'rl-hint' }, `Nothing found for “${text}”.`)); return; }
        res.replaceChildren(...shown.map((g) => h('div', { class: 'rl-grp' }, h('h4', null, g.label),
          g.error && !g.items.length ? h('div', { class: 'rl-err' }, `Could not search: ${g.error}`) : null,
          g.kind === 'photo' ? h('div', { class: 'rl-photos' }, g.items.map(photo)) : h('div', { class: 'rl-list' }, g.items.map(row)))));
      }, 220);
    }
    q.addEventListener('input', run);
    back.append(h('div', { class: 'sv-dialog rl-dlg', role: 'dialog', 'aria-label': 'Link an item' },
      h('div', { class: 'rl-sbar' }, svg(IC.search), q, h('button', { class: 'rl-x', type: 'button', title: 'Close', 'aria-label': 'Close', onclick: () => close(null) }, svg(IC.close))),
      chipRow, res));
    document.body.append(back);
    hint();
    q.focus();
  });
}
