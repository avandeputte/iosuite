/** One note: title, text, tags, folder, pin, its picture and the text read from it. Saved as you type. */
import { $, h, api, state, icon, fmtDate, colorVar, toast, fail, canWrite, debounce, confirmIt, menu, displayTitle } from './core.js';
import { view, go, updateCard, refresh, markSelected } from './notes.js';

let note = null;     // the note as the server last answered
let pending = {};    // fields changed and not yet saved
let saving = null;

const SOURCES = { clipboard: 'Copied', service: 'Saved with right-click', screenshot: 'Screenshot', manual: 'Typed', web: 'Made in the web app',
  photo: 'Photo', share: 'Shared', mcp: 'Made by an assistant', import: 'Imported' };

export async function openNote(id) {
  await flush();
  if (!id) { note = null; renderEmpty(); return; }
  try { note = await api(`/api/notes/${id}`); } catch (e) { note = null; renderEmpty(e.status === 404 ? 'That note is gone.' : e.message); return; }
  pending = {};
  render();
}

function renderEmpty(msg) {
  const pane = $('#note');
  if (!pane) return;
  pane.textContent = '';
  pane.append(h('div.noteempty', icon('notes'), h('div', msg || 'Pick a note, or make a new one.'), h('div.small', 'Paste a picture (⌘V) anywhere to save it as a note.')));
}

const save = debounce(() => { flush(); }, 700);

export async function flush(keepalive = false) {
  if (!note || !Object.keys(pending).length) return saving;
  const body = { ...pending, updatedAt: Date.now() / 1000 };
  pending = {};
  status('Saving…');
  saving = api(`/api/notes/${note.id}`, { method: 'PUT', body, keepalive }).then((n) => {
    const image = note.image;
    note = { ...n, image };
    updateCard(note);
    status('Saved');
  }).catch((e) => {
    if (e.status === 409 && e.body && e.body.current) { note = e.body.current; render(); toast('Someone changed this note meanwhile; showing their version'); }
    else { pending = { ...body, ...pending }; delete pending.updatedAt; status('Not saved: ' + e.message); }
  }).finally(() => { saving = null; });
  return saving;
}

function status(text) { const s = $('.edbar .status'); if (s) s.textContent = text; }

function change(field, value) {
  pending[field] = value;
  note[field] = value;
  status('Editing…');
  save();
}

function folderSelect() {
  return h('select', { 'aria-label': 'Folder', disabled: !canWrite() || note.deleted, onchange: async (e) => { change('folderID', e.target.value || null); await flush(); refresh(); } },
    h('option', { value: '' }, 'No folder'), state.meta.folders.map((f) => h('option', { value: f.id, selected: f.id === note.folderID }, f.name)));
}

function tagEditor() {
  const colors = Object.fromEntries((state.meta.tags || []).map((t) => [t.name.toLowerCase(), t.color]));
  const box = h('div.tags');
  const draw = () => {
    box.textContent = '';
    for (const t of note.tags) {
      const chip = h('span.tag', { onclick: () => go({ v: 'tag', t, f: null, n: null, q: '' }) }, '#' + t,
        canWrite() && !note.deleted ? h('button.x', { title: 'Remove tag', 'aria-label': `Remove ${t}`, onclick: (e) => { e.stopPropagation(); setTags(note.tags.filter((x) => x !== t)); } }, '×') : null);
      const cv = colorVar(colors[t.toLowerCase()]);
      if (cv) chip.style.setProperty('--tc', cv);
      box.append(chip);
    }
    if (canWrite() && !note.deleted) {
      const dl = h('datalist#tagnames', (state.meta.tags || []).map((t) => h('option', { value: t.name })));
      const input = h('input.tagin', { placeholder: 'Add a tag', list: 'tagnames', 'aria-label': 'Add a tag' });
      input.addEventListener('keydown', (e) => {
        if ((e.key === 'Enter' || e.key === ',') && input.value.trim()) { e.preventDefault(); setTags([...note.tags, ...input.value.split(',')]); }
        else if (e.key === 'Backspace' && !input.value && note.tags.length) setTags(note.tags.slice(0, -1));
      });
      input.addEventListener('blur', () => { if (input.value.trim()) setTags([...note.tags, ...input.value.split(',')]); });
      box.append(input, dl);
    }
  };
  const setTags = async (tags) => {
    const seen = new Set();
    note.tags = tags.map((t) => t.trim().replace(/^#+/, '').trim()).filter((t) => t && !seen.has(t.toLowerCase()) && seen.add(t.toLowerCase()));
    pending.tags = note.tags;
    draw();
    await flush();
    refresh();
    const inp = box.querySelector('.tagin'); if (inp) inp.focus();
  };
  draw();
  return box;
}

function picture() {
  if (!note.hasImage) {
    if (!canWrite() || note.deleted) return null;
    const file = h('input', { type: 'file', accept: 'image/*', hidden: true, onchange: (e) => e.target.files[0] && uploadPicture(note.id, e.target.files[0]) });
    return h('div.picture', file, h('button.pillbtn', { onclick: () => file.click() }, icon('upload'), 'Add a picture'));
  }
  const src = `/api/notes/${note.id}/image?v=${(note.imageSHA || '').slice(0, 8)}`;
  const img = h('img', { src, alt: displayTitle(note), onclick: () => { const z = h('div.zoom', { onclick: () => z.remove() }, h('img', { src })); document.body.append(z); } });
  const info = note.image ? `${note.image.width}×${note.image.height} · ${Math.round(note.image.bytes / 1024)} KB` : '';
  return h('div.picture', img, h('div.acts',
    h('a.pillbtn', { href: src + '&download=1' }, icon('download'), 'Download'),
    h('button.pillbtn', { onclick: copyPicture }, icon('copy'), 'Copy picture'),
    canWrite() && !note.deleted ? h('button.pillbtn', { onclick: async () => {
      if (!await confirmIt('Remove picture', 'Remove the picture from this note? The text read from it stays.', 'Remove', true)) return;
      try { note = { ...(await api(`/api/notes/${note.id}/image`, { method: 'DELETE' })), image: null }; render(); updateCard(note); } catch (e) { fail(e); }
    } }, icon('trash'), 'Remove') : null,
    h('span.muted.small', info)));
}

async function copyPicture() {
  try {
    const blob = await (await fetch(`/api/notes/${note.id}/image`)).blob();
    const png = blob.type === 'image/png' ? blob : await toPng(blob);
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': png })]);
    toast('Picture copied');
  } catch (e) { fail('This browser could not copy the picture: ' + e.message); }
}
async function toPng(blob) {
  const bmp = await createImageBitmap(blob);
  const c = document.createElement('canvas'); c.width = bmp.width; c.height = bmp.height;
  c.getContext('2d').drawImage(bmp, 0, 0);
  return new Promise((r) => c.toBlob(r, 'image/png'));
}

export async function uploadPicture(id, file) {
  const fd = new FormData();
  fd.append('file', file, file.name || 'picture.png');
  toast('Uploading the picture…', 10000);
  try {
    const n = await api(`/api/notes/${id}/image`, { method: 'POST', body: fd });
    toast(n.ocrQueued ? 'Picture saved; its text is being read' : 'Picture saved');
    if (note && note.id === id) { await openNote(id); }
    refresh();
    if (n.ocrQueued) setTimeout(() => { if (note && note.id === id && !note.ocrText) openNote(id).then(() => updateCard(note)); }, 6000);
    return n;
  } catch (e) { fail(e); }
}

async function copyNote() {
  const text = [note.title, note.body].filter((s) => s && s.trim()).join('\n\n') || note.ocrText;
  try { await navigator.clipboard.writeText(text); toast('Copied'); } catch (e) { fail(e); }
}

function moreMenu(btn) {
  menu(btn, [
    { icon: 'copy', label: 'Copy text', action: copyNote },
    { icon: 'copy', label: 'Copy link', action: async () => { await navigator.clipboard.writeText(location.origin + '/#/note/' + note.id); toast('Link copied'); } },
    note.hasImage ? { icon: 'copy', label: 'Copy picture', action: copyPicture } : null,
    canWrite() ? '-' : null,
    canWrite() ? { icon: 'trash', label: 'Delete note', action: deleteNote } : null,
  ]);
}

async function deleteNote() {
  try {
    await flush();
    await api(`/api/notes/${note.id}`, { method: 'DELETE' });
    toast('Moved to the trash');
    go({ n: null });
    refresh();
  } catch (e) { fail(e); }
}

function render() {
  const pane = $('#note');
  if (!pane) return;
  pane.textContent = '';
  const w = canWrite() && !note.deleted;
  const pin = h('button.iconbtn' + (note.pinned ? '.on' : ''), { title: note.pinned ? 'Unpin' : 'Pin to the top', 'aria-label': 'Pin', disabled: !w,
    onclick: async () => { change('pinned', !note.pinned); pin.classList.toggle('on', note.pinned); await flush(); refresh(); } }, icon('pin'));
  const bar = h('div.edbar',
    h('button#backbtn.iconbtn', { title: 'Back to the list', 'aria-label': 'Back', onclick: () => go({ n: null }) }, icon('back')),
    note.deleted ? null : folderSelect(), note.deleted ? null : pin,
    h('span.sp'), h('span.status'),
    note.deleted && canWrite() ? h('button.pillbtn.primary', { onclick: async () => { await api(`/api/notes/${note.id}/restore`, { method: 'POST' }).catch(fail); toast('Restored'); go({ v: 'all', n: note.id }); refresh(); } }, icon('restore'), 'Restore') : null,
    h('button.iconbtn', { title: 'Copy (⌘C with nothing selected)', 'aria-label': 'Copy', onclick: copyNote }, icon('copy')),
    canWrite() && !note.deleted ? h('button.iconbtn', { title: 'Delete', 'aria-label': 'Delete', onclick: deleteNote }, icon('trash')) : null,
    h('button.iconbtn', { title: 'More', 'aria-label': 'More', onclick: (e) => moreMenu(e.currentTarget) }, icon('more')));
  const t = h('input.ed-title', { value: note.title, placeholder: displayTitle({ ...note, title: '' }) === 'Untitled' ? 'Title' : displayTitle({ ...note, title: '' }), readOnly: !w, 'aria-label': 'Title',
    oninput: (e) => change('title', e.target.value) });
  const b = h('textarea.ed-body', { placeholder: w ? 'Write something…' : '', readOnly: !w, 'aria-label': 'Text', oninput: (e) => { change('body', e.target.value); grow(e.target); } });
  b.value = note.body;
  const meta = h('div.ed-meta',
    h('span', 'Created ' + fmtDate(note.createdAt, true)),
    note.updatedAt - note.createdAt > 60 ? h('span', 'Edited ' + fmtDate(note.updatedAt, true)) : null,
    h('span', (SOURCES[note.source] || note.source) + (note.sourceApp ? ` from ${note.sourceApp}` : '')),
    note.changedBy ? h('span', 'by ' + note.changedBy) : null);
  const ocr = note.ocrText ? h('details.ocr', { open: !note.body }, h('summary', 'Text in the picture'), h('pre', note.ocrText)) : null;
  pane.append(h('div.editor', bar, t, meta, tagEditor(), picture(), ocr, b));
  requestAnimationFrame(() => grow(b));
  if (!note.title && !note.body && !note.hasImage && w) t.focus();
}

function grow(t) { t.style.height = 'auto'; t.style.height = Math.max(t.scrollHeight, window.innerHeight * 0.4) + 'px'; }

export const currentNote = () => note;
// an edit not saved yet goes as the tab closes (keepalive: the browser finishes the request after the page is gone)
window.addEventListener('pagehide', () => { if (note && Object.keys(pending).length) flush(true); });
export { markSelected };
