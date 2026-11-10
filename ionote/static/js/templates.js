/** Manage › Templates (#/templates): starting points for new notes. A template has a title, text, tags and a folder;
 *  {{date}}, {{time}}, {{weekday}} and the like are filled in when a note is made from it (New note ▾, the apps). */
import { $, h, api, state, icon, toast, fail, canWrite, confirmIt } from './core.js';
import { loadMeta, renderNav } from './notes.js';

const EXAMPLES = [
  { name: 'Meeting notes', title: 'Meeting {{date}}', body: '**Who:** \n\n## Agenda\n- \n\n## Notes\n\n\n## Actions\n- [ ] ', tags: ['meeting'] },
  { name: 'Daily log', title: '{{weekday}} {{date}}', body: '## Done\n- \n\n## To do\n- [ ] \n\n## Notes\n', tags: ['daily'] },
  { name: 'Shopping list', title: 'Shopping {{date}}', body: '- [ ] \n', tags: ['shopping'] },
];

let editing = null;  // the template open in the form (null: none; {}: a new one)

export async function renderTemplates() {
  const main = $('#main');
  main.textContent = '';
  const list = (state.meta && state.meta.templates) || [];
  const w = canWrite();
  const page = h('div.pagein.templates');
  page.append(h('h1.ptitle', h('span.pic', { style: '--hue:var(--c-purple)' }, icon('template')), 'Templates', h('span.sp'),
    w ? h('button.pillbtn.primary', { onclick: () => { editing = { name: '', title: '', body: '', tags: [], folderID: null }; renderTemplates(); } }, icon('add'), 'New template') : null));
  page.append(h('p.muted', 'Start a note from a template with New note ▾, here, or in the apps. In the title and text, {{date}}, {{time}}, {{datetime}}, ',
    '{{weekday}}, {{month}}, {{year}}, {{tomorrow}} and {{yesterday}} are filled in when the note is made.'));
  if (editing) page.append(form(editing));
  if (!list.length && !editing) {
    page.append(h('section.sec', h('p', 'No templates yet.'), w ? h('div.chips', h('span.muted.small', 'Add an example:'),
      EXAMPLES.map((ex) => h('button.chip', { onclick: async () => { try { await api('/api/templates', { method: 'POST', body: ex }); await reload(); } catch (e) { fail(e); } } }, ex.name))) : null));
  }
  for (const t of list) {
    if (editing && editing.id === t.id) continue;
    const folder = t.folderID && state.meta.folders.find((f) => f.id === t.folderID);
    page.append(h('section.sec.tpl',
      h('div.tplhead', icon('template'), h('b', t.name), h('span.sp'),
        w ? h('button.pillbtn', { onclick: () => useTemplate(t) }, icon('add'), 'New note') : null,
        w ? h('button.iconbtn', { title: 'Edit', 'aria-label': 'Edit ' + t.name, onclick: () => { editing = { ...t }; renderTemplates(); } }, icon('edit')) : null,
        w ? h('button.iconbtn', { title: 'Delete', 'aria-label': 'Delete ' + t.name, onclick: async () => {
          if (!await confirmIt('Delete template', `Delete the template "${t.name}"? Notes made from it stay.`, 'Delete', true)) return;
          try { await api(`/api/templates/${t.id}`, { method: 'DELETE' }); await reload(); } catch (e) { fail(e); }
        } }, icon('trash')) : null),
      h('div.muted.small', [t.title ? 'Title: ' + t.title : null, folder ? 'Folder: ' + folder.name : null, t.tags.length ? t.tags.map((x) => '#' + x).join(' ') : null].filter(Boolean).join(' · ')),
      t.body ? h('pre.tplbody', t.body.slice(0, 400)) : null));
  }
  main.append(h('div.page', page));
}

function form(t) {
  const name = h('input', { value: t.name, placeholder: 'Name, e.g. Meeting notes', 'aria-label': 'Name' });
  const title = h('input', { value: t.title, placeholder: 'Title of new notes, e.g. Meeting {{date}}', 'aria-label': 'Title' });
  const body = h('textarea.tplta', { placeholder: 'Text of new notes (Markdown: ## heading, - [ ] checklist)', 'aria-label': 'Text' });
  body.value = t.body;
  const tags = h('input', { value: t.tags.join(', '), placeholder: 'Tags, separated by commas', 'aria-label': 'Tags' });
  const folder = h('select', { 'aria-label': 'Folder' }, h('option', { value: '' }, 'No folder'),
    state.meta.folders.map((f) => h('option', { value: f.id, selected: f.id === t.folderID }, f.name)));
  const save = async () => {
    if (!name.value.trim()) { toast('Give the template a name'); name.focus(); return; }
    const data = { name: name.value.trim(), title: title.value, body: body.value, tags: tags.value.split(','), folderID: folder.value || null, updatedAt: Date.now() / 1000 };
    try {
      if (t.id) await api(`/api/templates/${t.id}`, { method: 'PUT', body: data });
      else await api('/api/templates', { method: 'POST', body: data });
      editing = null;
      toast('Template saved');
      await reload();
    } catch (e) { fail(e); }
  };
  setTimeout(() => name.focus(), 0);
  return h('section.sec.tplform', h('h2', t.id ? 'Edit template' : 'New template'),
    h('label', 'Name', name), h('label', 'Title', title), h('label', 'Text', body), h('label', 'Tags', tags), h('label', 'Folder', folder),
    h('div.acts', h('button.pillbtn', { onclick: () => { editing = null; renderTemplates(); } }, 'Cancel'), h('button.pillbtn.primary', { onclick: save }, 'Save')));
}

async function reload() { await loadMeta(); renderNav(); renderTemplates(); }

let onUse = () => {};
/** main.js hands over how a note is made from a template (newNote with the fields filled in). */
export function setTemplateHandler(fn) { onUse = fn; }
export const useTemplate = (t) => onUse(t);
