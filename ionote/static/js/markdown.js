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
    put(ta, { from: start, to: s, text: '', start, end: start });
    return true;
  }
  const m = task || item;
  let marker = m[2];
  if (/^\d+/.test(marker)) marker = (parseInt(marker, 10) + 1) + marker.slice(-1);
  const text = '\n' + m[1] + marker + ' ' + (task ? '[ ] ' : '');
  put(ta, { from: s, to: e, text, start: s + text.length, end: s + text.length });
  return true;
}

/** The commands of the formatting bar, in its order ('-': a gap). key: the shortcut with ⌘ (Ctrl elsewhere),
 *  ⇧ when shift is set. The Mac and iPhone apps have the same commands and the same shortcuts. */
export const FORMATS = [
  { cmd: 'bold', label: 'Bold', icon: 'bold', key: 'b' },
  { cmd: 'italic', label: 'Italic', icon: 'italic', key: 'i' },
  { cmd: 'strike', label: 'Strikethrough', icon: 'strike', key: 'x', shift: true },
  { cmd: 'code', label: 'Code', icon: 'code', key: 'e' },
  { cmd: 'link', label: 'Link', icon: 'link', key: 'k' },
  '-',
  { cmd: 'heading', label: 'Heading', icon: 'heading', key: 'h', shift: true },
  { cmd: 'bullet', label: 'Bulleted list', icon: 'bullets', key: '8', shift: true },
  { cmd: 'number', label: 'Numbered list', icon: 'numbers', key: '7', shift: true },
  { cmd: 'checklist', label: 'Checklist', icon: 'checklist', key: 'l', shift: true },
  { cmd: 'quote', label: 'Quote', icon: 'quote', key: '.', shift: true },
  '-',
  { cmd: 'codeblock', label: 'Code block', icon: 'codeblock' },
  { cmd: 'rule', label: 'Divider', icon: 'rule' },
];
const WRAP = { bold: '**', italic: '*', strike: '~~', code: '`' };

/** One formatting command on a text with this selection: what to replace and the selection after it,
 *  { from, to, text, start, end } (offsets in the text as it was). Toggles: bold text turns plain again. */
export function formatEdit(value, s, e, cmd) {
  if (WRAP[cmd]) return wrap(value, s, e, WRAP[cmd]);
  if (cmd === 'link') return linkEdit(value, s, e);
  if (cmd === 'rule') return ruleEdit(value, s, e);
  if (cmd === 'codeblock') return fenceEdit(value, s, e);
  return linesEdit(value, s, e, cmd);
}

/** Apply a command to a text box (it can be undone with ⌘Z like typing). */
export function applyFormat(ta, cmd) {
  put(ta, formatEdit(ta.value, ta.selectionStart, ta.selectionEnd, cmd));
}

/** Make the lines the selection touches checklist items (or plain lines again when they all are). */
export const toggleChecklist = (ta) => applyFormat(ta, 'checklist');

/** Replace a part of the text box the way typing does, so ⌘Z undoes it (setRangeText where the browser can't). */
function put(ta, ed) {
  ta.focus();
  ta.setSelectionRange(ed.from, ed.to);
  let done = false;
  try { done = ed.text || ed.from !== ed.to ? document.execCommand(ed.text ? 'insertText' : 'delete', false, ed.text) : true; } catch (err) { done = false; }
  if (!done || ta.value.slice(ed.from, ed.from + ed.text.length) !== ed.text) {
    ta.setRangeText(ed.text, ed.from, ed.to, 'end');
  }
  ta.setSelectionRange(ed.start, ed.end);
}

/** **bold**, *italic*, ~~struck~~, `code` around the selection (the word at the caret when nothing is selected),
 *  or taken off when it is already there. Each line of a longer selection gets its own pair. */
function wrap(v, s, e, mark) {
  const n = mark.length, ch = mark[0];
  if (s === e) {  // the word around the caret, or an empty pair to type in
    const word = /[\p{L}\p{N}_'’]/u;
    let a = s, b = e;
    while (a > 0 && word.test(v[a - 1])) a--;
    while (b < v.length && word.test(v[b])) b++;
    if (a === b) {
      if (v.slice(s - n, s) === mark && v.slice(s, s + n) === mark) return { from: s - n, to: s + n, text: '', start: s - n, end: s - n };
      return { from: s, to: e, text: mark + mark, start: s + n, end: s + n };
    }
    const ed = wrap(v, a, b, mark);
    const shift = ed.text.length - (b - a) > 0 ? n : -n;  // keep the caret where it was in the word
    return { ...ed, start: s + shift, end: s + shift };
  }
  // a run of the mark's character next to the selection: ** for bold, an odd run (* or ***) for italic
  const run = (t, i, step) => { let k = 0; while (t[i + k * step] === ch) k++; return k; };
  const left = run(v, s - 1, -1), right = run(v, e, 1);
  const marked = (l, r) => ch === '*' ? (n === 2 ? l >= 2 && r >= 2 : l % 2 === 1 && r % 2 === 1) : l >= n && r >= n;
  if (marked(left, right)) return { from: s - n, to: e + n, text: v.slice(s, e), start: s - n, end: e - n };
  const sel = v.slice(s, e);
  const inner = (t) => t.length > 2 * n && run(t, 0, 1) < t.length && marked(run(t, 0, 1), run(t, t.length - 1, -1));
  const lines = sel.split('\n');
  const filled = lines.filter((l) => l.trim());
  const off = filled.length && filled.every((l) => inner(l.trim()));
  const text = lines.map((l) => {
    if (!l.trim()) return l;
    const [, lead, body, tail] = l.match(/^(\s*)(.*?)(\s*)$/);
    return lead + (off ? body.slice(n, body.length - n) : mark + body + mark) + tail;
  }).join('\n');
  if (lines.length === 1) {  // select the words themselves, without the marks
    const [, lead, , tail] = sel.match(/^(\s*)(.*?)(\s*)$/s);
    return { from: s, to: e, text, start: s + lead.length + (off ? 0 : n), end: s + text.length - tail.length - (off ? 0 : n) };
  }
  return { from: s, to: e, text, start: s, end: s + text.length };
}

/** [selection](https://) with the address selected to type over; a selected address becomes [](address). */
function linkEdit(v, s, e) {
  const sel = v.slice(s, e).trim();
  if (/^(https?:\/\/|mailto:)\S+$/.test(sel)) return { from: s, to: e, text: `[](${sel})`, start: s + 1, end: s + 1 };
  const label = v.slice(s, e).replace(/\n+/g, ' ');
  const text = `[${label}](https://)`;
  if (!label) return { from: s, to: e, text, start: s + 1, end: s + 1 };
  return { from: s, to: e, text, start: s + label.length + 3, end: s + text.length - 1 };
}

/** A --- divider on its own line, after the line the caret is on. */
function ruleEdit(v, s, e) {
  let stop = v.indexOf('\n', e); if (stop < 0) stop = v.length;
  const before = v.slice(0, stop);
  const lead = !before.trim() ? '' : before.endsWith('\n\n') ? '' : before.endsWith('\n') ? '\n' : '\n\n';
  const text = lead + '---\n';
  const after = v.slice(stop);
  const tail = after.startsWith('\n') ? '' : '\n';
  return { from: stop, to: stop, text: text + tail, start: stop + text.length + tail.length, end: stop + text.length + tail.length };
}

/** ``` fences around the lines the selection touches (an empty block to type in when nothing is selected),
 *  or taken off when the lines are a block already. */
function fenceEdit(v, s, e) {
  const start = v.lastIndexOf('\n', s - 1) + 1;
  let stop = v.indexOf('\n', e > s && v[e - 1] === '\n' ? e - 1 : e); if (stop < 0) stop = v.length;
  const lines = v.slice(start, stop).split('\n');
  if (lines.length >= 2 && FENCE.test(lines[0]) && FENCE.test(lines[lines.length - 1])) {
    const text = lines.slice(1, -1).join('\n');
    return { from: start, to: stop, text, start, end: start + text.length };
  }
  if (s === e && !lines.join('').trim()) {
    const text = '```\n\n```';
    return { from: start, to: stop, text, start: start + 4, end: start + 4 };
  }
  const body = lines.join('\n');
  const text = '```\n' + body + '\n```';
  return { from: start, to: stop, text, start: start + 4, end: start + 4 + body.length };
}

const HEAD = /^(\s{0,3})(#{1,6})\s+/;
const QUOTE = /^(\s*)>\s?/;
const PREFIX = /^\s*(>\s?)?(#{1,6}\s+)?(([-*+]|\d+[.)])\s+(\[( |x|X)\]\s?)?)?/;
const LISTED = /^(\s*)([-*+]|\d+[.)])\s+(\[( |x|X)\]\s?)?/;

/** Headings, lists, checklists and quotes on every line the selection touches; the same command again takes it off
 *  (a heading goes #, ##, ###, then plain). */
function linesEdit(v, s, e, cmd) {
  const start = v.lastIndexOf('\n', s - 1) + 1;
  let stop = v.indexOf('\n', e > s && v[e - 1] === '\n' ? e - 1 : e); if (stop < 0) stop = v.length;
  const lines = v.slice(start, stop).split('\n');
  const filled = lines.filter((l) => l.trim());
  const all = (re) => (filled.length ? filled : lines).every((l) => re(l));
  const isTask = (l) => TASK.test(l);
  const isBullet = (l) => !isTask(l) && /^\s*[-*+]\s+/.test(l);
  const isNumber = (l) => !isTask(l) && /^\s*\d+[.)]\s+/.test(l);
  const bare = (l) => l.replace(QUOTE, '$1').replace(HEAD, '$1').replace(LISTED, '$1');
  let next;
  if (cmd === 'heading') {
    const m = (filled[0] || lines[0]).match(HEAD);
    const level = m ? m[2].length : 0;
    const hashes = level >= 3 ? '' : '#'.repeat(level + 1) + ' ';
    next = lines.map((l) => (l.trim() || lines.length === 1) ? l.replace(HEAD, '$1').replace(/^(\s{0,3})/, '$1' + hashes) : l);
  } else if (cmd === 'quote') {
    const off = all((l) => QUOTE.test(l));
    next = lines.map((l) => off ? l.replace(QUOTE, '$1') : (l.trim() || lines.length === 1) ? '> ' + l : l);
  } else {
    const test = { bullet: isBullet, number: isNumber, checklist: isTask }[cmd];
    const off = all(test);
    let k = 0;
    next = lines.map((l) => {
      if (!l.trim() && lines.length > 1) return l;
      const indent = l.match(/^\s*/)[0];
      const text = bare(l).slice(indent.length);
      if (off) return indent + text;
      if (cmd === 'bullet') return `${indent}- ${text}`;
      if (cmd === 'number') return `${indent}${++k}. ${text}`;
      // a checklist keeps a list's own marker
      const it = !isTask(l) && l.match(ITEM);
      return isTask(l) ? l : it ? `${it[1]}${it[2]} [ ] ${it[3]}` : `${indent}- [ ] ${text}`;
    });
  }
  const text = next.join('\n');
  if (lines.length === 1 && s === e) {  // the caret stays in the words it was in
    const prefix = (l) => l.match(PREFIX)[0].length;
    const pos = start + Math.max(prefix(text), s - start - prefix(lines[0]) + prefix(text));
    return { from: start, to: stop, text, start: pos, end: pos };
  }
  return { from: start, to: stop, text, start: s === e ? start + text.length : start, end: start + text.length };
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
