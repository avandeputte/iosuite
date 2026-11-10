/** Markdown for notes, drawn as DOM nodes (never as HTML strings, so nothing in a note can run as a script):
 *  headings, **bold**, *italic*, ~~struck~~, `code`, fenced code blocks, > quotes, lists, - [ ] checklists you can
 *  tick, links ([text](https://…) and bare addresses) and --- rules. A single line break stays a line break, since
 *  most notes are plain text. The Mac and iPhone apps draw the same subset. */
import { h } from './core.js';

const TASK = /^(\s*)([-*+]|\d+[.)])\s+\[( |x|X)\]\s?(.*)$/;
const ITEM = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
const FENCE = /^\s*(```|~~~)/;

/** Inline markdown of one line, as nodes. */
function inline(text) {
  const out = [];
  // code first (nothing inside it is markdown), then links, then emphasis
  const re = /(`+)([^`]+?)\1|\[([^\]]+)\]\((https?:\/\/[^\s)]+|mailto:[^\s)]+)\)|(https?:\/\/[^\s<>()]+[^\s<>().,;:!?'"])|\*\*([^*]+)\*\*|__([^_]+)__|~~([^~]+)~~|\*([^*\s][^*]*?)\*|(?<![\w])_([^_\s][^_]*?)_(?![\w])/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[2] !== undefined) out.push(h('code', m[2]));
    else if (m[3] !== undefined) out.push(link(m[4], inline(m[3])));
    else if (m[5] !== undefined) out.push(link(m[5], m[5]));
    else if (m[6] !== undefined || m[7] !== undefined) out.push(h('strong', inline(m[6] ?? m[7])));
    else if (m[8] !== undefined) out.push(h('del', inline(m[8])));
    else if (m[9] !== undefined || m[10] !== undefined) out.push(h('em', inline(m[9] ?? m[10])));
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function link(href, kids) {
  return h('a', { href, target: '_blank', rel: 'noopener noreferrer', onclick: (e) => e.stopPropagation() }, kids);
}

/** The note's text as a fragment. onToggle(lineIndex, checked): a checklist box was clicked (null: read-only boxes). */
export function renderMarkdown(text, onToggle = null) {
  const lines = (text || '').split('\n');
  const root = h('div.md');
  let para = null, list = null, quote = null;
  const end = () => { para = null; list = null; quote = null; };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (FENCE.test(line)) {
      const fence = line.trim().slice(0, 3), code = [];
      for (i++; i < lines.length && !lines[i].trim().startsWith(fence); i++) code.push(lines[i]);
      end();
      root.append(h('pre', h('code', code.join('\n'))));
      continue;
    }
    if (!line.trim()) { end(); continue; }
    let m;
    if ((m = line.match(/^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/))) { end(); root.append(h('h' + Math.min(6, m[1].length + 1), inline(m[2]))); continue; }
    if (/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(line)) { end(); root.append(h('hr')); continue; }
    if ((m = line.match(/^\s*>\s?(.*)$/))) {
      if (!quote) { end(); quote = h('blockquote'); root.append(quote); } else quote.append(h('br'));
      quote.append(...inline(m[1]));
      continue;
    }
    const task = line.match(TASK), item = !task && line.match(ITEM);
    if (task || item) {
      const ordered = /\d/.test((task || item)[2]);
      if (!list || list.ordered !== ordered) { para = null; quote = null; list = { ordered, el: h(ordered ? 'ol' : 'ul') }; root.append(list.el); }
      const depth = Math.min(4, Math.floor((task || item)[1].replace(/\t/g, '    ').length / 2));
      let li;
      if (task) {
        const done = task[3] !== ' ';
        const box = h('input', { type: 'checkbox', checked: done, disabled: !onToggle, 'aria-label': task[4] || 'Checklist item' });
        const line = i;
        if (onToggle) box.addEventListener('click', (e) => { e.stopPropagation(); onToggle(line, box.checked); });
        li = h('li.task' + (done ? '.done' : ''), h('label', { onclick: (e) => e.stopPropagation() }, box, h('span', inline(task[4]))));
      } else li = h('li', inline(item[3]));
      if (depth) li.style.marginLeft = depth * 1.4 + 'em';
      list.el.append(li);
      continue;
    }
    if (list && /^\s{2,}\S/.test(line)) { list.el.lastChild.append(h('br'), ...inline(line.trim())); continue; }
    if (!para) { list = null; quote = null; para = h('p'); root.append(para); } else para.append(h('br'));
    para.append(...inline(line));
  }
  return root;
}

/** The text with the checklist box on this line ticked or unticked. */
export function toggleTask(text, lineIndex, checked) {
  const lines = text.split('\n');
  const m = (lines[lineIndex] || '').match(TASK);
  if (!m) return text;
  lines[lineIndex] = lines[lineIndex].replace(/\[( |x|X)\]/, checked ? '[x]' : '[ ]');
  return lines.join('\n');
}

/** [done, total] checklist items in a text (code blocks left out). */
export function taskCounts(text) {
  let done = 0, total = 0, code = false;
  for (const line of (text || '').split('\n')) {
    if (FENCE.test(line)) { code = !code; continue; }
    const m = !code && line.match(TASK);
    if (m) { total++; if (m[3] !== ' ') done++; }
  }
  return [done, total];
}

/** Whether a text uses any markdown worth drawing (plain text is shown as it is). */
export const looksLikeMarkdown = (text) => /(^|\n)\s*(#{1,6}\s|[-*+]\s|\d+[.)]\s|>\s|```|---\s*$)|\*\*[^*]+\*\*|\[[^\]]+\]\(https?:|`[^`]+`|https?:\/\//.test(text || '');

/** Enter in the text box: a list item continues the list (a checklist with an empty box); Enter on an empty item ends
 *  the list. Returns true when it handled the key. */
export function continueList(ta) {
  const { selectionStart: s, selectionEnd: e, value } = ta;
  if (s !== e) return false;
  const start = value.lastIndexOf('\n', s - 1) + 1;
  const line = value.slice(start, s);
  const task = line.match(TASK), item = !task && line.match(ITEM);
  if (!task && !item) return false;
  const content = task ? task[4] : item[3];
  if (!content.trim()) {  // an empty item: the list ends here
    ta.setRangeText('', start, s, 'end');
    return true;
  }
  const m = task || item;
  let marker = m[2];
  if (/^\d+/.test(marker)) marker = (parseInt(marker, 10) + 1) + marker.slice(-1);
  ta.setRangeText('\n' + m[1] + marker + ' ' + (task ? '[ ] ' : ''), s, e, 'end');
  return true;
}

/** Make the lines the selection touches checklist items (or plain lines again when they all are). */
export function toggleChecklist(ta) {
  const { selectionStart: s, selectionEnd: e, value } = ta;
  const start = value.lastIndexOf('\n', s - 1) + 1;
  let stop = value.indexOf('\n', e); if (stop < 0) stop = value.length;
  const lines = value.slice(start, stop).split('\n');
  const all = lines.every((l) => TASK.test(l));
  const next = lines.map((l) => {
    if (all) return l.replace(/^(\s*)([-*+]|\d+[.)])\s+\[( |x|X)\]\s?/, '$1');
    if (TASK.test(l)) return l;
    const it = l.match(ITEM);
    return it ? `${it[1]}${it[2]} [ ] ${it[3]}` : `- [ ] ${l}`;
  }).join('\n');
  ta.setRangeText(next, start, stop, 'end');
}

/** A template's placeholders filled in with this device's clock: {{date}} {{time}} {{datetime}} {{weekday}}
 *  {{month}} {{year}} {{tomorrow}} {{yesterday}} (the same as the server's and the apps'). */
export function expandTemplate(text, now = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const shift = (days) => { const d = new Date(now); d.setDate(d.getDate() + days); return ymd(d); };
  const time = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  const values = { date: ymd(now), time, datetime: `${ymd(now)} ${time}`, weekday: now.toLocaleDateString('en-US', { weekday: 'long' }),
    month: now.toLocaleDateString('en-US', { month: 'long' }), year: String(now.getFullYear()), tomorrow: shift(1), yesterday: shift(-1) };
  return (text || '').replace(/\{\{\s*(date|time|datetime|weekday|month|year|tomorrow|yesterday)\s*\}\}/gi, (_, k) => values[k.toLowerCase()]);
}
