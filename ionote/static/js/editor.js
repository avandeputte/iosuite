/** One note: title, text (Markdown, with checklists you can tick), tags, folder, pin, its picture and the text read
 *  from it, its attached files, and the notes related to it. Saved as you type. */
import { $, h, api, state, icon, fmtDate, colorVar, toast, fail, canWrite, debounce, confirmIt, menu, displayTitle } from './core.js';
import { view, go, updateCard, refresh, markSelected } from './notes.js';
import { renderMarkdown, toggleTask, continueList, applyFormat, FORMATS } from './markdown.js';

let note = null;     // the note as the server last answered
let pending = {};    // fields changed and not yet saved
let saving = null;
let mode = 'edit';   // the text: 'preview' (drawn as Markdown) or 'edit' (the text box)
const MODE = 'ionote.textMode';
const prefMode = () => { try { return localStorage.getItem(MODE) || 'preview'; } catch (e) { return 'preview'; } };

const SOURCES = { clipboard: 'Copied', service: 'Saved with right-click', screenshot: 'Screenshot', manual: 'Typed', web: 'Made in the web app',
  photo: 'Photo', share: 'Shared', mcp: 'Made by an assistant', import: 'Imported' };

export async function openNote(id) {
  await flush();
  if (note && note.id !== id && Object.keys(pending).length) await flush();  // one more try before leaving the note
  if (note && note.id !== id && Object.keys(pending).length) {  // still not saved: stay, so what was typed is not lost
    toast('This note is not saved yet, so it stays open. Try again in a moment.');
    status('Not saved');
    return;
  }
  if (!id) { note = null; renderEmpty(); return; }
  try { note = await api(`api/notes/${id}`); } catch (e) { note = null; renderEmpty(e.status === 404 ? 'That note is gone.' : e.message); return; }
  pending = {};
  mode = prefMode() === 'preview' && note.body.trim() ? 'preview' : 'edit';
  render();
}

function renderEmpty(msg) {
  const pane = $('#note');
  if (!pane) return;
  pane.textContent = '';
  pane.append(h('div.noteempty', icon('notes'), h('div', msg || 'Pick a note, or make a new one.'), h('div.small', 'Paste a picture (⌘V) anywhere to save it as a note.')));
}

const save = debounce(() => { flush(); }, 700);

export function flush(keepalive = false) {
  // one save at a time, in order: each waits for the one before, and sends what is pending when its turn comes
  saving = (saving || Promise.resolve()).then(() => saveNow(keepalive));
  const mine = saving;
  mine.finally(() => { if (saving === mine) saving = null; });
  return mine;
}

async function saveNow(keepalive) {
  if (!note || !Object.keys(pending).length) return;
  // only the fields typed, and no clock of ours: the server stamps the time, so a browser whose clock is behind
  // never sees its edit refused (and thrown away) as older than the one it replaces
  const id = note.id, body = { ...pending };
  pending = {};
  status('Saving…');
  try {
    const n = await api(`api/notes/${id}`, { method: 'PUT', body, keepalive });
    if (!note || note.id !== id) return;  // another note is open by now: this answer is not for it
    note = { ...n, image: note.image, body: pending.body !== undefined ? pending.body : n.body };
    updateCard(note);
    status(Object.keys(pending).length ? 'Editing…' : 'Saved');
  } catch (e) {
    if (note && note.id === id) pending = { ...body, ...pending };  // kept, to be sent again with the next save
    status('Not saved: ' + e.message);
  }
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
  const src = `api/notes/${note.id}/image?v=${(note.imageSHA || '').slice(0, 8)}`;
  const img = h('img', { src, alt: displayTitle(note), onclick: () => { const z = h('div.zoom', { onclick: () => z.remove() }, h('img', { src })); document.body.append(z); } });
  const info = note.image ? `${note.image.width}×${note.image.height} · ${Math.round(note.image.bytes / 1024)} KB` : '';
  return h('div.picture', img, h('div.acts',
    h('a.pillbtn', { href: src + '&download=1' }, icon('download'), 'Download'),
    h('button.pillbtn', { onclick: copyPicture }, icon('copy'), 'Copy picture'),
    canWrite() && !note.deleted ? h('button.pillbtn', { onclick: async () => {
      if (!await confirmIt('Remove picture', 'Remove the picture from this note? The text read from it stays.', 'Remove', true)) return;
      try { note = { ...(await api(`api/notes/${note.id}/image`, { method: 'DELETE' })), image: null }; render(); updateCard(note); } catch (e) { fail(e); }
    } }, icon('trash'), 'Remove') : null,
    h('span.muted.small', info)));
}

async function copyPicture() {
  try {
    const blob = await (await fetch(`api/notes/${note.id}/image`)).blob();
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
    const n = await api(`api/notes/${id}/image`, { method: 'POST', body: fd });
    toast(n.ocrQueued ? 'Picture saved; its text is being read' : 'Picture saved');
    if (note && note.id === id) { await openNote(id); }
    refresh();
    if (n.ocrQueued) setTimeout(() => { if (note && note.id === id && !note.ocrText) openNote(id).then(() => updateCard(note)); }, 6000);
    return n;
  } catch (e) { fail(e); }
}

// ---- attached files
const kb = (b) => b >= 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`;

function files() {
  const list = note.attachments || [];
  const w = canWrite() && !note.deleted;
  if (!list.length && !w) return null;
  const input = h('input', { type: 'file', multiple: true, hidden: true, onchange: (e) => { attachFiles(note.id, [...e.target.files]); e.target.value = ''; } });
  const items = list.map((a) => {
    const url = `api/notes/${note.id}/attachments/${a.id}`;
    const isImg = a.mime.startsWith('image/') && a.width;
    const thumb = isImg ? h('img', { src: `${url}/thumb?v=${(a.sha || '').slice(0, 8)}`, alt: '', loading: 'lazy' }) : h('span.fic', icon(a.mime === 'application/pdf' ? 'pdf' : 'file'));
    return h('div.file', h('a.fopen', { href: url, target: '_blank', rel: 'noopener', title: 'Open ' + a.name }, thumb,
      h('span.fname', a.name), h('span.muted.small', kb(a.bytes) + (a.width ? ` · ${a.width}×${a.height}` : ''))),
    h('a.iconbtn', { href: url + '?download=1', title: 'Download', 'aria-label': 'Download ' + a.name }, icon('download')),
    w ? h('button.iconbtn', { title: 'Remove', 'aria-label': 'Remove ' + a.name, onclick: async () => {
      if (!await confirmIt('Remove file', `Remove "${a.name}" from this note?`, 'Remove', true)) return;
      try { note = { ...(await api(url, { method: 'DELETE' })), image: note.image }; render(); updateCard(note); } catch (e) { fail(e); }
    } }, icon('close')) : null);
  });
  return h('div.files', input, items, w ? h('button.pillbtn.addfile', { onclick: () => input.click(), title: 'Attach PDFs, pictures or other files (or drop them on the note)' }, icon('attach'), list.length ? 'Attach more' : 'Attach files') : null);
}

/** Attach files to a note, one after the other; their text is read for search (PDFs, text files, pictures). */
export async function attachFiles(id, list) {
  if (!list.length) return;
  let last = null;
  for (const [i, f] of list.entries()) {
    const fd = new FormData();
    fd.append('file', f, f.name || 'file');
    toast(list.length > 1 ? `Attaching ${i + 1} of ${list.length}…` : `Attaching ${f.name}…`, 10000);
    try { last = await api(`api/notes/${id}/attachments`, { method: 'POST', body: fd }); } catch (e) { fail(e); return; }
  }
  toast(list.length > 1 ? `${list.length} files attached` : 'File attached');
  if (note && note.id === id && last) { note = { ...last, image: note.image }; render(); updateCard(note); }
  refresh();
}

// ---- related notes and suggestions
async function related(box, id) {
  let r;
  try { r = await api(`api/notes/${id}/related`); } catch (e) { return; }
  if (!note || note.id !== id || !box.isConnected) return;
  box.textContent = '';
  const w = canWrite() && !note.deleted;
  const sugg = [];
  if (w && r.folder && !note.folderID) {
    sugg.push(h('button.chip.sugg', { title: 'Move it to this folder', onclick: async () => { change('folderID', r.folder.id); await flush(); refresh(); render(); } }, icon('folder'), r.folder.name));
  }
  if (w) for (const t of r.tags.filter((t) => !note.tags.some((x) => x.toLowerCase() === t.toLowerCase()))) {
    sugg.push(h('button.chip.sugg', { title: 'Add this tag', onclick: async () => { note.tags = [...note.tags, t]; pending.tags = note.tags; await flush(); refresh(); render(); } }, '+#' + t));
  }
  if (sugg.length) box.append(h('div.suggest', h('span.muted.small', 'Suggested'), sugg));
  if (r.notes.length) {
    box.append(h('h4.relh', 'Related notes'), h('div.rel', r.notes.slice(0, 5).map((n) => h('a.relitem', { href: '#', onclick: (e) => { e.preventDefault(); go({ n: n.id }); } },
      n.hasImage ? h('img', { src: `api/notes/${n.id}/thumb?v=${(n.imageSHA || '').slice(0, 8)}`, alt: '', loading: 'lazy' }) : h('span.fic', icon('notes')),
      h('span.t', displayTitle(n)), h('span.muted.small', fmtDate(n.updatedAt))))));
  }
}

// ---- items of the other apps linked to this note (an event, a task, a contact, a recipe, a photo): the suite's panel
let linkUi = null;
let linkPanel = null;
async function mountLinks(el, id) {
  linkPanel = null;
  try { linkUi = linkUi || await import(new URL('api/related/ui.js', document.baseURI).href); } catch (e) { return; }
  if (!note || note.id !== id || !el.isConnected) return;
  linkPanel = linkUi.mount(el, { kind: 'note', id, toast, canEdit: canWrite() });
}

async function copyNote() {
  const text = [note.title, note.body].filter((s) => s && s.trim()).join('\n\n') || note.ocrText;
  try { await navigator.clipboard.writeText(text); toast('Copied'); } catch (e) { fail(e); }
}

function moreMenu(btn) {
  menu(btn, [
    { icon: 'copy', label: 'Copy text', action: copyNote },
    { icon: 'copy', label: 'Copy link', action: async () => { await navigator.clipboard.writeText(new URL('#/note/' + note.id, document.baseURI).href); toast('Link copied'); } },
    note.hasImage ? { icon: 'copy', label: 'Copy picture', action: copyPicture } : null,
    canWrite() && !note.deleted ? '-' : null,
    canWrite() && !note.deleted ? { icon: 'attach', label: 'Attach files…', action: () => { const i = $('.files input[type=file]'); if (i) i.click(); } } : null,
    canWrite() && !note.deleted ? { icon: 'template', label: 'Save as a template…', action: saveAsTemplate } : null,
    canWrite() && !note.deleted && linkPanel ? { icon: 'link', label: 'Link an event, task, contact…', action: () => linkPanel.pick() } : null,
    canWrite() ? '-' : null,
    canWrite() ? { icon: 'trash', label: 'Delete note', action: deleteNote } : null,
  ]);
}

async function saveAsTemplate() {
  const { ask } = await import('./core.js');
  const name = await ask('Save as a template', 'Template name', displayTitle(note), 'Save');
  if (!name) return;
  try {
    await flush();
    await api('api/templates', { method: 'POST', body: { name, title: note.title, body: note.body, tags: note.tags, folderID: note.folderID } });
    toast('Template saved: New note ▾ offers it');
    refresh();
  } catch (e) { fail(e); }
}

async function deleteNote() {
  try {
    await flush();
    await api(`api/notes/${note.id}`, { method: 'DELETE' });
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
    note.deleted && canWrite() ? h('button.pillbtn.primary', { onclick: async () => { await api(`api/notes/${note.id}/restore`, { method: 'POST' }).catch(fail); toast('Restored'); go({ v: 'all', n: note.id }); refresh(); } }, icon('restore'), 'Restore') : null,
    note.deleted && canWrite() ? h('button.pillbtn.danger', { onclick: async () => {
      if (!await confirmIt('Delete for good', 'Delete this note for good, with its files? This cannot be undone.', 'Delete for good', true)) return;
      try { await api(`api/trash/${note.id}`, { method: 'DELETE' }); toast('Deleted for good'); go({ n: null }); refresh(); } catch (e) { fail(e); }
    } }, 'Delete for good') : null,
    h('button.iconbtn', { title: 'Copy (⌘C with nothing selected)', 'aria-label': 'Copy', onclick: copyNote }, icon('copy')),
    canWrite() && !note.deleted ? h('button.iconbtn', { title: 'Delete', 'aria-label': 'Delete', onclick: deleteNote }, icon('trash')) : null,
    h('button.iconbtn', { title: 'More', 'aria-label': 'More', onclick: (e) => moreMenu(e.currentTarget) }, icon('more')));
  const t = h('input.ed-title', { value: note.title, placeholder: displayTitle({ ...note, title: '' }) === 'Untitled' ? 'Title' : displayTitle({ ...note, title: '' }), readOnly: !w, 'aria-label': 'Title',
    oninput: (e) => change('title', e.target.value) });
  const b = h('textarea.ed-body', { placeholder: w ? 'Write something… (Markdown works: # heading, **bold**, - [ ] checklist)' : '', readOnly: !w, 'aria-label': 'Text',
    oninput: (e) => { change('body', e.target.value); grow(e.target); },
    onkeydown: (e) => {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && continueList(b)) { e.preventDefault(); change('body', b.value); grow(b); return; }
      const f = (e.metaKey || e.ctrlKey) && !e.altKey && FORMATS.find((x) => x.key && keyCode(x.key) === e.code && !!x.shift === e.shiftKey);
      if (f) { e.preventDefault(); format(f.cmd); }
    } });
  const format = (cmd) => { applyFormat(b, cmd); change('body', b.value); grow(b); };
  b.value = note.body;
  // the text drawn as Markdown: a click (not on a link or a box) edits it; boxes tick and save at once
  const preview = h('div.ed-preview', { title: w ? 'Click to edit' : '', onclick: (e) => {
    if (!w || e.target.closest('a, input, label')) return;
    setMode('edit');
  } });
  const drawPreview = () => {
    preview.replaceChildren(renderMarkdown(note.body, w ? async (line, checked) => {
      note.body = toggleTask(note.body, line, checked);
      b.value = note.body;
      change('body', note.body);
      await flush();
      drawPreview();
    } : null));
  };
  const setMode = (m) => {
    mode = m;
    try { localStorage.setItem(MODE, m); } catch (e) { /* private mode */ }
    if (m === 'preview') drawPreview();
    preview.hidden = m !== 'preview';
    b.hidden = m === 'preview';
    modeBtn.replaceChildren(icon(m === 'preview' ? 'edit' : 'eye'));
    modeBtn.title = m === 'preview' ? 'Edit the text' : 'Show as formatted text';
    fmt.hidden = m === 'preview' || !w;
    if (m === 'edit') { requestAnimationFrame(() => { grow(b); if (w) b.focus(); }); }
  };
  const modeBtn = h('button.iconbtn', { 'aria-label': 'Formatted or plain text', onclick: () => setMode(mode === 'preview' ? 'edit' : 'preview') });
  // the formatting bar: a second row of the bar while the text is edited (a press keeps the selection in the text)
  const fmt = h('div.fmtbar', { role: 'toolbar', 'aria-label': 'Formatting' }, FORMATS.map((f) => f === '-' ? h('span.gap') :
    h('button.iconbtn', { title: f.label + (f.key ? ` (${f.shift ? '⇧' : ''}⌘${f.key.toUpperCase()})` : ''), 'aria-label': f.label,
      onmousedown: (e) => e.preventDefault(), onclick: () => format(f.cmd) }, icon(f.icon))));
  bar.insertBefore(modeBtn, bar.querySelector('.sp'));
  bar.append(fmt);
  const meta = h('div.ed-meta',
    h('span', 'Created ' + fmtDate(note.createdAt, true)),
    note.updatedAt - note.createdAt > 60 ? h('span', 'Edited ' + fmtDate(note.updatedAt, true)) : null,
    h('span', (SOURCES[note.source] || note.source) + (note.sourceApp ? ` from ${note.sourceApp}` : '')),
    note.changedBy ? h('span', 'by ' + note.changedBy) : null);
  const ocr = note.ocrText ? h('details.ocr', { open: !note.body }, h('summary', 'Text in the picture'), h('pre', note.ocrText)) : null;
  const rel = h('div.related');
  const linked = h('div.linked');
  const ed = h('div.editor', bar, t, meta, tagEditor(), picture(), ocr, preview, b, files(), linked, rel);
  pane.append(ed);
  setMode(mode);
  if (mode === 'edit') requestAnimationFrame(() => grow(b));
  if (!note.title && !note.body && !note.hasImage && w) t.focus();
  if (!note.deleted) { related(rel, note.id); mountLinks(linked, note.id); }
  // files dropped on the note are attached to it
  if (w) {
    ed.addEventListener('dragover', (e) => { if ([...e.dataTransfer.types].includes('Files')) { e.preventDefault(); e.stopPropagation(); ed.classList.add('dropping'); } });
    ed.addEventListener('dragleave', (e) => { if (!ed.contains(e.relatedTarget)) ed.classList.remove('dropping'); });
    ed.addEventListener('drop', (e) => {
      if (![...e.dataTransfer.types].includes('Files')) return;
      e.preventDefault(); e.stopPropagation(); ed.classList.remove('dropping');
      $('#drop').hidden = true;
      attachFiles(note.id, [...e.dataTransfer.files]);
    });
  }
}

/** The key's code (layout-free, and the same with ⇧): 'b' KeyB, '8' Digit8, '.' Period. */
const keyCode = (k) => /\d/.test(k) ? 'Digit' + k : k === '.' ? 'Period' : 'Key' + k.toUpperCase();

function grow(t) { t.style.height = 'auto'; t.style.height = Math.max(t.scrollHeight, window.innerHeight * 0.4) + 'px'; }

export const currentNote = () => note;
// an edit not saved yet goes as the tab closes (keepalive: the browser finishes the request after the page is gone)
window.addEventListener('pagehide', () => { if (note && Object.keys(pending).length) flush(true); });
export { markSelected };
