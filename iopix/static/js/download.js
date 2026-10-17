/** Zip downloads. */
import { $, api, fill, fmtBytes, h, icon, nf } from './core.js';
import { toast } from './state.js';
import { chipList } from './search.js';
import { modal } from './actions.js';

export async function downloadDialog(p, selected) {
  p = new URLSearchParams(p);
  p.delete('sort');
  const name = selected ? `${selected} selected photos` : (chipList(p).map((c) => c.label.replace(/[“”]/g, '')).join(' ') || 'photos').slice(0, 80);
  const side = h('input', { type: 'checkbox' });
  const size = h('select', null, [[1000, '1 GB'], [2000, '2 GB'], [4000, '4 GB'], [8000, '8 GB']].map(([v, l]) => h('option', { value: v, selected: v === 2000 }, l)));
  const body = h('div', null, h('p', null, 'Working out the download…'));
  const back = modal('Download as zip', body,
    h('label', { style: 'margin-top:12px' }, side, ' Include digiKam XMP sidecar files'),
    h('label', { style: 'margin-top:8px' }, 'Split into zip files of at most ', size),
    h('div', { class: 'modal-btns' }, h('button', { class: 'pillbtn', onclick: () => back.remove() }, 'Close')));
  // the browser downloads each part through a hidden form, so even huge selections work
  const fetchPart = (i) => {
    const q = new URLSearchParams(p);
    q.set('name', name); q.set('part', i); q.set('part_mb', size.value);
    if (side.checked) q.set('sidecars', '1');
    const form = h('form', { method: 'post', action: '/api/zip', style: 'display:none' }, [...q].map(([k, v]) => h('input', { type: 'hidden', name: k, value: v })));
    document.body.append(form); form.submit(); form.remove();
  };
  const plan = async () => {
    const q = new URLSearchParams(p);
    q.set('part_mb', size.value);
    let r;
    try {
      const res = await fetch('/api/zip/plan', { method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body: q.toString() });
      r = await res.json();
      if (!res.ok) throw new Error(r.detail || res.status);
    } catch (e) { fill(body, h('p', { class: 'warn' }, String(e.message || e))); return; }
    if (!r.files) { fill(body, h('p', null, 'Nothing to download.')); return; }
    const one = r.parts.length === 1;
    fill(body,
      h('p', null, `${nf.format(r.files)} original ${r.files === 1 ? 'file' : 'files'}, ${fmtBytes(r.bytes)}, in their folders${one ? '.' : `, split into ${r.parts.length} zip files.`}`),
      one ? h('button', { class: 'pillbtn on', onclick: () => { fetchPart(0); toast('Download started.'); } }, icon('download'), 'Download')
        : [h('div', { class: 'alist' }, r.parts.map((pt, i) => { const b = h('div', { class: 'frow', title: `${pt.first} … ${pt.last}`, onclick: () => { fetchPart(i); b.classList.add('on'); } },
            icon('download'), h('span', { class: 'nm' }, `Part ${i + 1}`, h('span', { class: 'muted' }, `  ${pt.first === pt.last ? pt.first : pt.first + ' … ' + pt.last}`)), h('span', { class: 'ct' }, `${nf.format(pt.files)} · ${fmtBytes(pt.bytes)}`)); return b; })),
          h('p', { class: 'muted', style: 'margin:10px 0 0;font-size:12.5px' }, 'Click each part to download it. Parts follow folder order, and unzipping them all into one folder gives the complete set.')]);
  };
  size.onchange = plan;
  plan();
}
