/** Settings: one page in tabs, as in every ioThing app (the Security and Global settings tabs are users.js), and the
 *  Tools page. */
import { PREF, UNITS, act, api, dfDayLocal, errorBox, fill, fmtBytes, fmtWhen, h, icon, loadingBox, main, nf, plural, post, regionUsesMiles, store } from './core.js';
import { S, THEMES, applyBadgePref, applyTheme, avatarOf, hashFor, infoPrefsEditor, photosWith, pollSoon, toast, toastError } from './state.js';
import { confirmDialog } from './actions.js';
import { dbDialog, templatesSection } from './editing.js';
import { pageTitle } from './pages.js';
import { renderUserMenu, setupDialog, suiteSection } from './users.js';
import { personPicker } from './faces.js';
import { placeTagsDialog } from './admin.js';


/** Settings › AI: one table, a row per feature, with the model it runs on (download,
 *  update check) and the background job that fills it (progress, run again). Models without a job (places)
 *  and an installed search model that is not in use get rows of their own. */
function aiSection(view) {
  const body = h('div');
  let timer = 0;
  const checkBtn = h('button', { class: 'pillbtn', onclick: async () => { checkBtn.disabled = true; checkBtn.textContent = 'Checking…'; await act(() => post('/api/models/check', {})); draw(); } }, icon('spark'), 'Check models for updates');
  const wrap = h('div', { class: 'sbox' }, h('h2', null, 'AI analysis and models'),
    h('div', { class: 'muted', style: 'max-width:860px' }, `Everything runs here; nothing is written to digiKam. New photos are picked up automatically. The default model is the small, fast one; models never update on their own.`),
    h('div', { style: 'display:flex;gap:8px;flex-wrap:wrap;margin:14px 0' },
      h('button', { class: 'pillbtn on', onclick: async () => { await act(() => post('/api/analysis/run', { job: 'all' }), { toast: 'Checking for new and changed photos…' }); draw(); } }, icon('spark'), 'Check new and changed photos'), checkBtn),
    body);
  const fmtDate = (t) => (t ? dfDayLocal.format(new Date(t * 1000)) : '');  // when the model was installed: a real moment, in this browser's zone
  // a job's models: fixed ones (vision: RapidOCR; photo quality: the aesthetic and eye models; ages: MiVOLO) or the one
  // chosen for the feature (the table offers the alternatives in a menu)
  const JOB_MODEL = { vision: ['ocr'], looks: ['aesthetic', 'eyes'], ages: ['mivolo'], jerseys: ['ocr'] };
  const JOB_CHOICE = { embeddings: 'search_model', objects: 'object_model', faces: 'face_vectors', facedetect: 'face_detector', captions: 'caption_model', clothing: 'search_model', rotation: 'search_model', videos: 'speech_model' };
  const modelState = (m, p) => {
    const c = m.check;
    return p.running === m.key ? ['downloading…', 'on']
      : !m.installed ? ['not installed', 'warn']
      : !c ? [`installed ${fmtDate(m.at)}`, '']
      : c.status === 'current' ? ['up to date', 'ok']
      : c.status === 'update' ? [`update available (${c.remote})`, 'on']
      : c.status === 'newer' ? ['newer data available', 'on']
      : c.status === 'error' ? ['could not check', 'warn'] : [`installed ${m.revision || ''}`, ''];
  };
  const draw = async () => {
    let a, md;
    try { [a, md] = await Promise.all([api('/api/analysis'), api('/api/models')]); } catch { return; }
    if (S.route.view !== view || !body.isConnected) return;  // the page was drawn again meanwhile: this copy of the section is gone
    const q = a.queue || {}, p = md.progress || {};
    if (p.finished && !p.running && p.error) toast(`Download of ${p.finished} failed: ${p.error}`, null, null, 9000);
    const models = Object.fromEntries(md.models.map((m) => [m.key, m]));
    const choices = md.choices || {};
    // the menu of models a feature can run on; picking one that is not installed offers its download first
    const chooser = (group) => {
      const c = choices[group];
      if (!c) return null;
      const sel = h('select', { class: 'mpick', title: `Which model ${c.label.toLowerCase()} runs on`, onchange: async (e) => {
        const key = e.target.value, m = models[key];
        if (!m) return;
        if (!m.installed) {
          e.target.value = c.chosen;
          if (!await confirmDialog(`${m.label} is not installed. Download it (${m.size})? ${S.APP_NAME} keeps working meanwhile; choose it here again once it has arrived.`)) return;
          await act(() => post('/api/models/download', { key }), { toast: `Downloading ${m.label}…` });
          draw(); return;
        }
        const note = group === 'search_model' ? ' The library is indexed again with it in the background; search stays on the current model until that finishes.'
          : group === 'face_vectors' ? ' Every face is embedded again with it (the groups and suggestions rebuild in the background).'
          : group === 'face_detector' ? ' Used by the next face detection run.'
          : ' New photos use it from now on; “Run again” redoes the whole library with it.';
        
        try { await post('/api/settings', { [group]: key }); toast(`${c.label}: now ${m.label}.${note}`, null, null, 9000); } catch (err) { e.target.value = c.chosen; toastError(err); }
        draw();
      } }, c.options.map((k) => h('option', { value: k, selected: k === c.chosen }, models[k] ? models[k].label + (models[k].installed ? '' : ' (not installed)') : k)));
      return sel;
    };
    // what each choice is: size, speed, accuracy (the registry's own words), the chosen one marked
    const compare = (group) => {
      const c = choices[group];
      if (!c || c.options.length < 2) return null;
      // the table is redrawn while jobs run; a fold the user opened stays open until they close it
      return h('details', { class: 'mcompare', open: OPEN_COMPARE.has(group), ontoggle: (e) => { if (e.target.open) OPEN_COMPARE.add(group); else OPEN_COMPARE.delete(group); } }, h('summary', null, `Compare the ${c.options.length} models`),
        h('div', { class: 'mopts' }, c.options.map((k) => { const o = models[k]; if (!o) return null;
          return h('div', { class: 'mopt' + (k === c.chosen ? ' on' : '') },
            h('div', null, h('b', null, o.label), h('span', { class: 'muted' }, ` · ${o.size}${k === c.chosen ? ' · in use' : o.installed ? ' · installed' : ' · not installed'}`),
              ' ', h('a', { class: 'lnk', href: o.page, target: '_blank', rel: 'noopener' }, 'About')),
            h('div', { class: 'muted' }, o.what)); })));
    };
    const modelCell = (ms, group) => {
      ms = ms.filter(Boolean);
      if (!ms.length) return h('td', { class: 'muted' }, 'built in');
      if (ms.length > 1) return h('td', null, ms.map((m) => { const td = modelCell([m]); return h('div', { class: 'mmulti' }, ...td.childNodes); }));
      const m = ms[0];
      const [st, cls] = modelState(m, p);
      return h('td', null, h('div', null, group ? chooser(group) : h('a', { class: 'lnk', href: m.page, target: '_blank', rel: 'noopener', title: m.what }, m.label), h('span', { class: 'muted' }, ` · ${m.size}`)),
        h('div', { class: 'mst ' + cls, title: m.revision ? `revision ${m.revision}` : '' }, st, group ? [' · ', h('a', { class: 'lnk', href: m.page, target: '_blank', rel: 'noopener', title: m.what }, 'About')] : null),
        group ? h('div', { class: 'muted mwhat' }, m.what) : null,
        group ? compare(group) : null);
    };
    const modelBtn = (m) => {
      if (Array.isArray(m)) return m.map(modelBtn);
      if (!m) return null;
      const c = m.check, upd = c && (c.status === 'update' || c.status === 'newer' || c.status === 'missing');
      if (m.installed && !upd) return null;  // installed and current: nothing to offer
      return h('button', { class: 'pillbtn small' + (!m.installed || upd ? ' on' : ''), disabled: !!p.running, title: m.installed ? `Download ${m.label} again (${m.size})` : `Download ${m.label} (${m.size})`,
        onclick: async () => {
          if (!await confirmDialog(`Download ${m.label} (${m.size})${m.installed ? ' again, replacing the installed files' : ''}? ${S.APP_NAME} keeps working meanwhile.` + (m.kind === 'pip' ? `\n\nA package update takes effect after a restart of ${S.APP_NAME}.` : ''))) return;
          await act(() => post('/api/models/download', { key: m.key }), { toast: `Downloading ${m.label}…` });
          draw();
        } }, m.installed ? 'Update' : 'Download');
    };
    const progressCell = (j, m, extra) => {
      if (!j) return h('td', { class: 'muted' }, '—');
      const state = !j.enabled ? (m.some((x) => x && !x.installed) ? 'needs its model' : 'off') : j.running ? 'running…' : j.queued ? 'queued' : j.done >= j.total ? 'up to date' : j.key === 'facedetect' ? 'on request' : 'waiting';
      const now = Date.now() / 1000, idle = j.running && j.since ? (j.last ? now - j.last : now - j.since) : 0, stuck = idle > 300;
      return h('td', { class: 'mprog' },
        h('div', { class: 'ahead' }, h('span', { class: j.running ? 'mst on' : j.done >= j.total && j.enabled ? 'mst ok' : 'mst' }, state), h('span', { class: 'sp' }), h('span', { class: 'muted' }, `${nf.format(Math.min(j.done, j.total))} / ${nf.format(j.total)}`)),
        h('div', { class: 'bar' }, h('i', { style: `width:${j.total ? Math.min(100, 100 * j.done / j.total).toFixed(1) : 0}%` })),
        j.running && j.since ? h('div', { class: stuck ? 'warn' : 'muted', style: 'font-size:11.5px;margin-top:3px' }, `${Math.round((now - j.since) / 60)} min · last progress ${idle < 90 ? Math.round(idle) + ' s' : Math.round(idle / 60) + ' min'} ago`,
          j.current && j.current.length ? ` · ${j.current.map((x) => x.split('/').pop()).join(', ')}` : '', stuck ? ` · probably stuck on that file: see the server log, or restart ${S.APP_NAME}` : '') : null,
        extra);
    };
    // face detection writes to digiKam's database, so it never starts by itself: a Run link for the photos not looked at yet
    const runNow = (j) => j && j.key === 'facedetect' && j.enabled && !j.running && j.done < j.total ? h('button', { type: 'button', class: 'lnk mrerun', style: 'margin-right:12px', title: 'Look for faces in every photo not looked at yet', onclick: async () => {
      if (!await confirmDialog(`Look for faces in the ${nf.format(j.total - j.done)} photos not checked yet? New faces are added to digiKam’s database as unnamed faces; faces already marked are kept as they are.`)) return;
      try { const r = await post('/api/analysis/run', { job: 'facedetect' }); toast(`Looking for faces in ${nf.format(r.queued)} photos.`); } catch (e) { toastError(e); }
      draw();
    } }, 'Run') : null;
    const rerun = (j) => j && j.rerun && j.enabled ? h('button', { type: 'button', class: 'lnk mrerun', title: `Discard the results of “${j.label}” and compute them again for every photo`, onclick: async () => {
      if (!await confirmDialog(`Run “${j.label}” again from scratch for all ${nf.format(j.total)} photos? The current results for it are discarded first. This can take from several minutes to a few hours.`)) return;
      await act(() => post('/api/analysis/run', { job: j.key, reset: true }), { toast: `Re-running “${j.label}”.` });
      draw();
    } }, 'Run again') : null;
    const row = (label, detail, j, m, group) => h('tr', { 'data-job': j?.key || '', 'data-model': m.filter(Boolean).map((x) => x.key).join(' ') },
      h('td', { class: 'mfeat' }, h('b', null, label), detail ? h('div', { class: 'muted mdet', title: detail }, detail) : null),
      modelCell(m, group), progressCell(j, m, [runNow(j), rerun(j)]), h('td', { class: 'macts' }, modelBtn(m)));
    const rows = a.jobs.map((j) => {
      const group = JOB_CHOICE[j.key];
      const m = group ? [models[choices[group]?.chosen]] : (JOB_MODEL[j.key] || []).map((k) => models[k]);
      return row(j.label, j.detail, j, m, group && choices[group] ? group : null);
    });
    // a model with a job of its own row is shown there; the rest (place names) get a row each
    const inRows = new Set([...Object.values(choices).flatMap((c) => c.options), ...Object.values(JOB_MODEL).flat()]);
    for (const m of md.models) {
      if (inRows.has(m.key)) continue;
      const label = m.key === 'geonames' ? 'Places from GPS positions' : m.label;
      const detail = m.key === 'geonames' ? 'Town, region and country for each GPS position, offline; looked up when the search index is built.' : m.what;
      rows.push(row(label, detail, null, [m]));
    }
    fill(body,
      h('div', { class: 'muted', style: 'font-size:13px;margin-bottom:8px' }, h('b', { style: 'color:var(--fg)' }, 'Background work: '), q.running ? `running ${(a.jobs.find((j) => (j.key === 'quality' && q.running === 'pixels') || j.key === q.running) || {}).label || q.running}` : 'idle',
        `. Jobs run one at a time, in the order below, so ${S.APP_NAME} and other apps stay responsive; each may use up to `,
        h('select', { onchange: async (e) => { await act(() => post('/api/settings', { bg_threads: +e.target.value }), { toast: 'Applies when the next job starts.' }); } },
          Array.from({ length: Math.max(1, (q.cores || 4) - 1) }, (_, i) => h('option', { value: i + 1, selected: i + 1 === q.threads }, String(i + 1)))),
        ` of ${q.cores || '?'} cores.`, q.queued?.length ? ` Waiting: ${q.queued.length}.` : ''),
      h('div', { class: 'mwrap' }, h('table', { class: 'mtable' },
        h('thead', null, h('tr', null, ['Feature', 'Model', 'Progress', ''].map((c) => h('th', null, c)))), h('tbody', null, rows))));
    checkBtn.disabled = false; fill(checkBtn, icon('spark'), 'Check models for updates');
    clearTimeout(timer);
    if (a.jobs.some((j) => j.running) || p.running) timer = setTimeout(() => { if (S.route.view === view && body.isConnected) drawSafe(); }, 4000);
  };
  const drawRaw = draw;
  const drawSafe = async () => {  // a menu the user has open is not replaced under their pointer; try again shortly
    if (body.contains(document.activeElement) && document.activeElement.matches('select')) { clearTimeout(timer); timer = setTimeout(drawSafe, 1500); return; }
    return drawRaw();
  };
  drawSafe();
  return wrap;
}
export async function showSettings() { return settingsPage('settings'); }
/** Settings › Library › File scanner: on or off, how often, Scan now, and what the last pass found. */
function scannerRow(c) {
  const { m, row, btn, again, switchField } = c;
  const sc = m.scanner || {};
  const last = sc.last;
  const said = last ? `Last pass ${fmtWhen(last.finished)}: ${[last.added && plural(last.added, 'new file'), last.modified && plural(last.modified, 'changed file'), last.removed && plural(last.removed, 'file') + ' gone', last.folders && plural(last.folders, 'new folder')].filter(Boolean).join(', ') || 'nothing new'}.${last.skipped?.length ? ' ' + last.skipped.join(' ') : ''}${last.error ? ' Error: ' + last.error : ''}` : 'No pass yet.';
  const on = switchField('file_scanner', !!sc.enabled, { on: 'File scanner on: a first pass starts now.', off: 'File scanner off.', cls: 'chk' });
  const every = h('select', { class: 'sharepick', onchange: async (e) => { await act(() => post('/api/settings', { scan_interval: +e.target.value }), { toast: 'Saved' }); } },
    [[5, 'every 5 minutes'], [15, 'every 15 minutes'], [60, 'every hour'], [360, 'every 6 hours'], [1440, 'once a day']].map(([v, l]) => h('option', { value: v, selected: v === sc.interval }, l)));
  return row('File scanner',
    h('span', null, `Finds photos added, changed or removed outside ${S.APP_NAME}. ${S.NO_DK ? 'Without digiKam, this is how copied photos get in.' : 'Not needed if everything comes in through Upload or Import.'} `, h('span', { class: 'muted' }, sc.running ? 'Scanning now…' : said)),
    h('span', { class: 'toolbar' }, on, every,
      btn('Scan now', async () => { try { await post('/api/scan', {}); toast('Scanning the album folders…'); setTimeout(again, 4000); } catch (e) { toastError(e); } })));
}
const OPEN_COMPARE = new Set();  // model groups whose "Compare the models" fold is open on the AI tab
// Settings is split into tabs, in the order every io app uses: each stab() marks where one begins; what comes before
// the first is always shown
const STABS = {
  settings: [['account', 'Account'], ['display', 'Display'], ['editing', 'Editing'], ['library', 'Library'], ['ai', 'AI'],
    ['server', 'Server'], ['security', 'Security'], ['global', 'Global settings']],
};
const stab = (k) => h('span', { class: 'stab-mark', 'data-tab': k, hidden: true });
/** Each heading and the rows under it become one box, as the shared panels draw theirs. */
function boxed(els) {
  const out = [];
  let box = null;
  for (const el of els) {
    if (el.tagName === 'H2') { box = h('section', { class: 'sbox' }); el.before(box); out.push(box); }
    else if (!box || !el.matches('.srow, .intro, .muted, table')) { box = null; out.push(el); continue; }
    box.append(el);
  }
  return out;
}
function settingsTabs(page, view) {
  if (!page) return;
  const kids = [...page.children], groups = new Map();
  let cur = null;
  for (const el of kids) {
    if (el.classList.contains('stab-mark')) { cur = el.dataset.tab; groups.set(cur, []); continue; }
    if (cur) groups.get(cur).push(el);
  }
  for (const [k, els] of groups) groups.set(k, boxed(els));
  const tabs = STABS[view].filter(([k]) => groups.has(k));
  if (tabs.length < 2) return;
  let pick = S.route.params.get('tab');  // #/settings/security links straight to a tab; else the last one opened
  if (!groups.has(pick)) pick = store.local.get(PREF[`${view}Tab`], null);
  if (!groups.has(pick)) pick = tabs[0][0];
  const bar = h('div', { class: 'stabs', role: 'tablist' });
  const show = (k) => {
    if (!groups.has(k)) return;
    for (const [g, els] of groups) els.forEach((el) => { el.style.display = g === k ? '' : 'none'; });
    [...bar.children].forEach((b) => { b.classList.toggle('on', b.dataset.tab === k); b.setAttribute('aria-selected', b.dataset.tab === k); });
    store.local.set(PREF[`${view}Tab`], k);
    if (S.route.params.get('tab') !== k) { S.route.params.set('tab', k); S.route.params.delete('part'); history.replaceState(null, '', hashFor(view, S.route.params)); }
  };
  tabs.forEach(([k, label]) => bar.append(h('button', { class: 'pillbtn stab', role: 'tab', 'data-tab': k, onclick: () => show(k) }, typeof label === 'function' ? label() : label)));
  bar.show = show;
  page.querySelector('.stab-mark').before(bar);
  show(pick);
}
/** What every settings row is built from: the library data `m` (GET /api/maintenance), the page being drawn and the shared helpers
 * (row and button builders, the library action runner `maint`, and the checkbox that saves one setting). */
function settingsContext(m, view) {
  const again = () => { if (S.route.view === view) (view === 'tools' ? showTools() : settingsPage(view)); };
  const when = (t) => (t ? fmtWhen(t) : 'never');
  const maint = async (action, msg, confirmText) => {
    if (confirmText && !await confirmDialog(confirmText)) return;
    await act(() => post('/api/maintenance', { action }), { toast: msg });
    setTimeout(again, 1500);
  };
  const row = (label, detail, btn) => h('div', { class: 'srow' }, h('div', null, h('b', null, label), h('div', { class: 'muted note' }, detail)), btn);
  const btn = (label, fn, primary) => h('button', { class: 'pillbtn' + (primary ? ' on' : ''), onclick: fn }, label);
  /** A checkbox that saves one on/off setting the moment it is clicked, says what it did, and springs back if the save failed. */
  const switchField = (key, checked, { label = 'On', on, off, disabled = false, after, cls } = {}) => h('label', { class: cls, style: cls ? null : 'display:flex;gap:8px;align-items:center;cursor:pointer;white-space:nowrap' },
    h('input', { type: 'checkbox', checked, disabled, onchange: async (e) => {
      try { await post('/api/settings', { [key]: e.target.checked }); toast(e.target.checked ? on : off); if (after) after(); } catch (err) { e.target.checked = !e.target.checked; toastError(err); } } }), label);
  /** A setting saved the moment it changes, with a "Saved" toast; the page is drawn again when `redraw`. */
  const save = async (body, redraw) => { try { await post('/api/settings', body); toast('Saved'); } catch (e) { toastError(e); } if (redraw) again(); };
  return { m, view, again, when, maint, row, btn, switchField, save };
}
/** Settings › Account: iosuite-shared's panels (the account, then its app passwords), the same in every io app, plus who you are in People. */
const accountUi = () => import(new URL('api/auth/ui.js', document.baseURI).href);
function panel(fill) {
  const el = h('div');
  fill(el).catch((e) => el.replaceChildren(errorBox(new Error(`The panel did not load: ${e.message}`))));
  return el;
}
function accountTab() {
  return [stab('account'), panel(async (el) => {
    const ui = await accountUi();
    await ui.mountAccount(el, { toast, onSaved: (u) => { Object.assign(S.USER, u); renderUserMenu(); } });
    const who = S.USER.person && S.tagById.get(S.USER.person);
    el.append(ui.box('person', 'You in People',
      h('div', { class: 'toolbar' }, avatarOf(S.USER, true), h('span', null, who ? who.name : 'Not linked to a person yet.'),
        S.IS_ADMIN ? h('button', { class: 'pillbtn', onclick: () => personPicker(async (t) => { try { S.USER = await post('/api/auth/person', { person: t.id }); renderUserMenu(); toast('Saved'); settingsPage('settings'); } catch (e) { toastError(e); } }) }, who ? 'Change' : 'Link to a person') : null,
        who ? h('a', { class: 'lnk', href: hashFor('photos', photosWith({ tag: S.USER.person })) }, 'Photos of me') : null)));
    const pw = h('div'); el.append(pw);
    await ui.mountAppPasswords(pw, { toast });
  })];
}
/** Settings › Display: the name, theme, units, badges, the info panel sections and the map provider. */
function displayTab(c) {
  const { m, row, save } = c;
  const kept = S.USER ? 'Saved with your account.' : 'Kept in this browser.';
  const seg = (id, attr, choices, cur, pick) => h('div', { class: 'eseg', id }, choices.map(([k, label]) => h('button', { class: cur === k ? 'on' : '', [`data-${attr}`]: k, onclick: (e) => {
    pick(k); for (const b of e.currentTarget.parentNode.children) b.classList.toggle('on', b === e.currentTarget); } }, label)));
  return [
    stab('display'),
    h('h2', null, 'Display'),
    S.IS_ADMIN ? row('Name', `What ${S.APP_NAME} calls itself, for everyone. Empty: ioPix.`,
      h('input', { class: 'einput', placeholder: 'ioPix', value: m.appNameSet || '', maxlength: 40, style: 'width:220px', onkeydown: (e) => { e.stopPropagation(); if (e.key === 'Enter') e.target.blur(); },
        onchange: async (e) => { await save({ app_name: e.target.value }); pollSoon(300); } })) : null,
    row('Theme', kept, seg('themeseg', 'theme', THEMES, store.get(PREF.theme, 'system'), (k) => { store.set(PREF.theme, k); applyTheme(); toast('Saved'); })),
    row('Units', `Automatic follows your region (${regionUsesMiles(navigator.language) ? 'miles' : 'kilometres'} here). ${kept}`,
      seg('unitseg', 'units', UNITS, store.get(PREF.units, 'auto'), (k) => { store.set(PREF.units, k); toast('Saved'); })),
    row('Thumbnail badges', 'Faces, GPS and favorite marks on thumbnails. Kept in this browser.',
      h('label', { style: 'display:flex;gap:8px;align-items:center;cursor:pointer' }, h('input', { type: 'checkbox', checked: store.get(PREF.badges, '1') !== '0',
        onchange: (e) => { store.set(PREF.badges, e.target.checked ? '1' : '0'); applyBadgePref(); } }), 'Show badges')),
    row('Info panel', `The sections the photo info panel shows. ${kept}`, infoPrefsEditor()),
    S.IS_ADMIN ? (() => {
      const keyIn = h('input', { class: 'einput', type: 'password', placeholder: m.googleMapsKeySet ? 'key is set; paste a new one to replace it' : 'Google Maps API key', autocomplete: 'off', style: 'width:260px',
        onkeydown: (e) => e.stopPropagation(), onchange: () => { if (keyIn.value.trim()) map({ map_provider: sel.value, google_maps_key: keyIn.value.trim() }); } });
      const srvIn = h('input', { class: 'einput', type: 'password', placeholder: m.googleServerKeySet ? 'server key is set; paste a new one to replace it' : 'Server key (optional)', autocomplete: 'off', style: 'width:260px',
        onkeydown: (e) => e.stopPropagation(), onchange: () => { if (srvIn.value.trim()) map({ google_server_key: srvIn.value.trim() }); } });
      const sel = h('select', { onchange: () => {
        if (sel.value === 'google' && !m.googleMapsKeySet && !keyIn.value.trim()) { keyIn.focus(); toast('Paste the Google Maps API key: it is saved when you leave the field.'); return; }
        map({ map_provider: sel.value });
      } }, h('option', { value: 'osm', selected: m.mapProvider !== 'google' }, 'OpenStreetMap'), h('option', { value: 'google', selected: m.mapProvider === 'google' }, 'Google Maps (your API key)'));
      const map = async (body) => { S.mapsLoaded = false; await save(body, true); };
      return row('Map provider', `Google needs a key with the Map Tiles and Geocoding APIs, restricted to ${S.APP_NAME}'s address. The optional server key is for geocoding and Vision.`,
        h('span', { class: 'toolbar tight' }, sel, keyIn, srvIn));
    })() : null,
  ];
}

/** Settings › Library: the two databases, album roots, sync with digiKam and the file scanner. */
function libraryTab(c) {
  const { m, row, btn, again, switchField } = c;
  return [
    stab('library'),
    h('h2', null, 'Library'),
    h('div', { class: 'muted intro' }, m.paths ? `${m.paths.library} (${nf.format(m.photos)} photos and videos). ${S.APP_NAME}'s own files are in ${m.paths.data}.` : `${nf.format(m.photos)} photos in the library.`),
    (() => {
      const d = m.database || {};
      const inp = (k, ph, type = 'text', w = 160) => h('input', { class: 'einput', type, placeholder: ph, value: type === 'password' ? '' : (d[k] ?? ''), autocomplete: 'off', style: `margin:0;width:${w}px`, onkeydown: (e) => e.stopPropagation() });
      const type = h('select', null, h('option', { value: 'sqlite', selected: d.type === 'sqlite' }, 'SQLite (digikam4.db file)'), h('option', { value: 'mysql', selected: d.type === 'mysql' }, 'MySQL / MariaDB'), h('option', { value: 'none', selected: d.type === 'none' }, 'None: I don’t use digiKam'));
      const f = { sqlite_dir: inp('sqlite_dir', 'folder with digikam4.db', 'text', 320), host: inp('host', 'host'), port: inp('port', 'port', 'text', 70), database: inp('database', 'database'), user: inp('user', 'user'),
        password: inp('password', d.password_set ? 'password (stored; leave empty to keep)' : 'password', 'password', 220) };
      const backup = h('select', null, [['auto', 'full backup only before deleting photos or a tag, or a merge'], ['skip', 'never (the server is backed up elsewhere)']].map(([v, l]) => h('option', { value: v, selected: (d.backup === 'skip' ? 'skip' : 'auto') === v }, l)));
      const sq = h('div', { class: 'toolbar tight mt6' }, f.sqlite_dir), my = h('div', { class: 'toolbar tight mt6' }, f.host, f.port, f.database, f.user, f.password);
      const show = () => { sq.hidden = type.value !== 'sqlite'; my.hidden = type.value !== 'mysql'; backup.hidden = test.hidden = type.value === 'none'; }; type.onchange = show;
      const payload = () => ({ type: type.value, sqlite_dir: f.sqlite_dir.value, host: f.host.value, port: f.port.value, database: f.database.value, user: f.user.value, password: f.password.value, backup: backup.value });
      const result = h('div', { class: 'muted', style: 'font-size:12.5px;margin-top:6px' });
      const test = btn('Test connection', async () => { fill(result, 'Testing…'); try { const r = await post('/api/db/test', payload()); fill(result, `OK: ${nf.format(r.images)} photos, ${nf.format(r.tags)} tags, DBVersion ${r.dbVersion}, album root ${r.roots.join(', ')}`); } catch (e) { fill(result, e.message); } });
      show();
      return row('digiKam database', d.type === 'none'
        ? `None: ${S.APP_NAME} keeps the library itself and the file scanner finds the photos. To start using digiKam later, let it read the folder first, then choose its database here.`
        : `Currently ${d.type === 'mysql' ? `MySQL ${d.user}@${d.host}:${d.port}/${d.database}` : `SQLite in ${d.sqlite_dir}`}. Changing it rebuilds the index; ${S.APP_NAME}'s own data stays.`,
        h('div', null, h('div', { class: 'toolbar tight' }, type, backup), sq, my,
          h('div', { style: 'display:flex;gap:6px;margin-top:8px' },
            test,
            btn('Save and switch', async () => { if (!await confirmDialog(type.value === 'none' ? `Stop using digiKam’s database? ${S.APP_NAME} keeps working from its own copy of the library.` : `Switch ${S.APP_NAME} to this digiKam database now?`)) return; try { await post('/api/settings', { database: payload() }); toast('Database settings saved; the index is rebuilding.'); } catch (e) { toastError(e); return; } setTimeout(again, 2500); }, true)),
          result));
    })(),
    (() => {
      const body = h('div', { class: 'muted small' }, 'Loading…');
      const draw = async () => {
        let d; try { d = await api('/api/roots'); } catch (e) { fill(body, e.message); return; }
        const inputs = new Map();
        fill(body, h('div', { class: 'stack' }, d.roots.map((r) => {
          const inp = h('input', { class: 'einput', placeholder: r.localPath, value: r.overridden ? r.localPath : '', style: 'width:340px', onkeydown: (e) => e.stopPropagation() });
          inputs.set(r.digikamPath, inp);
          return h('div', null, h('div', null, h('b', null, r.label || 'Album root'), ' ', h('span', { class: 'muted' }, `digiKam: ${r.digikamPath}`)),
            h('div', { style: 'display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:4px' }, inp,
              h('span', { class: 'muted smaller' }, r.exists ? `found: ${r.localPath} (${r.sample >= 2000 ? '2,000+' : nf.format(r.sample)} files)` : `not found: ${r.localPath}`)));
        }), h('div', { style: 'display:flex;gap:6px' },
          btn('Check', draw),
          btn('Save', async () => { const m = {}; inputs.forEach((inp, k) => { m[k] = inp.value.trim(); }); try { await post('/api/settings', { album_roots: m }); toast('Album roots saved; the index is rebuilding.'); } catch (e) { toastError(e); return; } setTimeout(draw, 2500); }, true))));
      };
      draw();
      return row('Album roots', 'Where each digiKam album root is on this machine. Empty: the default. Changing it rebuilds the index.', body);
    })(),
    row(`${S.APP_NAME} database`, `Where ${S.APP_NAME} keeps its own data (users, albums, settings, AI results). Switching copies every row across and restarts ${S.APP_NAME}.`, viewerDbPanel()),
    (() => {
      const d = m.digikam || {};
      if (d.none) return null;  // no digiKam at all: nothing to sync with
      if (d.conflict) {
        const planEl = h('div', { class: 'muted note mt6' }, 'Working out what changed…');
        api('/api/library/merge').then((p) => fill(planEl, p.total ? 'To merge: ' + p.summary.join(', ') + '.' : 'Nothing to merge.')).catch((e) => fill(planEl, e.message));
        const wrap = row('Sync with digiKam', `On, but ${plural(d.localChanges, 'change')} made while it was off ${d.localChanges === 1 ? 'is' : 'are'} not in digiKam yet. Merge writes them into digiKam after a backup; Replace drops them and copies digiKam’s library again.`,
          h('span', { style: 'display:flex;gap:6px;flex-wrap:wrap' },
            btn('Merge into digiKam', async () => { if (!await confirmDialog('Write the changes made while sync was off into digiKam’s database? digiKam must be closed; its database is backed up first.')) return; try { const r = await post('/api/library/merge', {}); toast(`Merged: ${Object.entries(r.applied).map(([k, v]) => `${v} ${k.replace('_', ' ')}`).join(', ') || 'nothing to do'}${r.conflicts ? `; ${r.conflicts} rows digiKam had also changed (the viewer’s values won)` : ''}.`, null, null, 12000); } catch (e) { toastError(e, 10000); } setTimeout(again, 2500); }, true),
            btn('Replace with digiKam’s', async () => { if (!await confirmDialog(`Drop the ${plural(d.localChanges, 'change')} made while sync was off and copy the library from digiKam again? Edits in sidecars are kept.`)) return; await act(() => post('/api/settings', { library_replace: true }), { toast: 'Copying the library from digiKam…' }); setTimeout(again, 2500); }),
            btn('Turn sync off', async () => { await act(() => post('/api/settings', { digikam_sync: false })); again(); })));
        wrap.firstChild.append(planEl);
        return wrap;
      }
      return row('Sync with digiKam', `On: ${S.APP_NAME} reads digiKam’s database when digiKam saves, and writes edits back while digiKam is closed. Off: ${S.APP_NAME} works on its own copy.${d.sync && !d.reachable ? ' digiKam’s database is unreachable right now; the copy is in use.' : ''}`,
        switchField('digikam_sync', !!d.sync, { on: 'Sync with digiKam on.', off: 'Sync with digiKam off.', after: () => setTimeout(again, 1500) }));
    })(),
    scannerRow(c),
  ];
}

/** Settings › Editing: where metadata is written, sidecar names and the metadata templates. */
function editingTab(c) {
  const { m, row, switchField, save } = c;
  return [
    stab('editing'),
    h('h2', null, 'Editing'),
    row('Write metadata into image files', 'Off: sidecars only. On: JPEG, PNG, TIFF and WebP files too.',
      switchField('write_files', !!m.writeFiles, { on: 'Edits go into image files too.', off: 'Edits go into sidecars only.' })),
    row('Sidecar file names', 'For new sidecars; existing ones are read either way. Pick what your digiKam uses.',
      h('select', { onchange: (e) => save({ sidecar_compat: e.target.value === '1' }) },
        h('option', { value: '0', selected: !m.sidecarCompat }, 'photo.jpg.xmp (digiKam’s default)'), h('option', { value: '1', selected: !!m.sidecarCompat }, 'photo.xmp'))),
    templatesSection(m),
  ];
}

/** Tools (#/tools, admins): the checks, suggestions and clean-up pages, each summarised in a line, and the library actions. */
export async function showTools() {
  let m;
  if (!main.querySelector('.tpage')) main.replaceChildren(h('div', { class: 'page spage tpage' }, loadingBox('Loading…')));
  if (!S.IS_ADMIN) { main.replaceChildren(h('div', { class: 'empty' }, 'Tools are for admins.')); return; }
  try { m = await api('/api/maintenance'); } catch (e) { if (S.route.view === 'tools') main.replaceChildren(h('div', { class: 'empty' }, 'Could not load the tools: ' + e.message)); return; }
  if (S.route.view !== 'tools') return;
  const c = settingsContext(m, 'tools');
  const { row, btn, maint, when, again } = c;
  const summary = (url, text, open) => {  // a page summarised in a line from a quick read of it
    const line = h('span', null, '');
    api(url).then((d) => fill(line, text(d))).catch(() => fill(line, ''));
    return [line, open];
  };
  const openBtn = (view) => h('a', { class: 'pillbtn on', href: `#/${view}` }, 'Open');
  const toolRow = (label, url, text, what, view) => { const [line, open] = summary(url, text, openBtn(view)); return row(label, h('span', null, line, what), open); };
  const page = h('div', { class: 'page spage tpage' },
    pageTitle('wrench', 'slate', 'Tools'),
    h('h2', null, 'Checks'),
    toolRow('Metadata consistency', '/api/consistency?limit=1', (d) => d.progress.running ? `Checking… ${nf.format(d.progress.done)} / ${nf.format(d.progress.total)} photos. `
      : !d.summary.scanned ? 'Not checked yet. ' : `${d.summary.mismatched ? plural(d.summary.mismatched, 'photo disagrees', 'photos disagree') : 'Everything agrees'}${d.summary.scanned_at ? ` (checked ${fmtWhen(d.summary.scanned_at)})` : ''}. `,
      'Rating, title, caption and tags in digiKam, the sidecars and the files.', 'consistency'),
    toolRow('Metadata quality', '/api/quality', (q) => (q.near.extra ? `${plural(q.near.extra, 'face is', 'faces are')} stored twice. ` : '')
      + (q.separate.count ? `${plural(q.separate.count, 'photo has', 'photos have')} the same person twice. ` : '')
      + (q.unnamed.count ? `${plural(q.unnamed.count, 'photo has', 'photos have')} faces but no names. ` : '')
      + (q.invalid.count ? `${plural(q.invalid.count, 'box is', 'boxes are')} outside the photo. ` : ''),
      'Missing locations, odd dates, duplicate faces and boxes outside the photo.', 'quality'),
    toolRow('Duplicate files', '/api/duplicates', (d) => d.groups.length ? `${plural(d.groups.length, 'set')} of identical files, ${fmtBytes(d.wasted)} that could be freed. ` : 'No identical copies. ',
      'From digiKam’s fingerprints; remove the extras in digiKam.', 'duplicates'),
    toolRow('Damaged files', '/api/filecheck', (d) => d.progress.running ? `Checking… ${nf.format(d.progress.done)} / ${nf.format(d.progress.total)} files. `
      : !d.checked ? 'Not checked yet. ' : d.found.length ? `${plural(d.found.length, 'damaged file')} (${nf.format(d.found.filter((x) => x.fixable).length)} repairable). ` : 'Nothing damaged. ',
      'Files that stop early or cannot be decoded, with a safe repair where there is one.', 'damaged'),
    h('h2', null, 'Suggestions'),
    ...[['datesuggest', 'Date suggestions', 'A year for photos marked Date unknown.', 'suggestion'],
      ['placesuggest', 'Place suggestions', 'A position for photos without one, from the photos around them.', 'suggestion'],
      ['jerseys', 'Jersey numbers', 'Players read from shirt numbers.', 'suggestion'],
      ['clothing', 'Clothing matches', 'People recognised by what they wear at the same event.', 'suggestion'],
      ['rotation', 'Wrongly rotated', 'Photos on their side or upside down.', 'photo']].map(([view, label, what, noun]) =>
      toolRow(label, `/api/${view}?limit=1`, (d) => d.ready === false ? 'Not analysed yet. ' : `${d.total ? plural(d.total, noun) : `No ${noun}s`}. `, what, view)),
    S.EDITING ? row('Place tags', 'Places/Country/Region/Town tags from each photo’s GPS position.', h('button', { class: 'pillbtn', onclick: placeTagsDialog }, icon('place'), 'Review and run')) : null,
    h('h2', null, 'Library'),
    row('Rescan the library', `The index is rebuilt whenever digiKam saves (last saved ${when(m.digikamSaved)}, index built ${when(m.indexBuilt)}).`, btn('Rescan now', () => maint('reindex', 'Rescanning the library…'), true)),
    S.EDITING ? row('Edits waiting for digiKam', m.pendingEdits ? `${plural(m.pendingEdits, 'photo has', 'photos have')} edits in sidecars that digiKam’s database does not have yet${m.digikamRunning ? '; close digiKam to apply them' : ''}.` : 'None.',
      m.pendingEdits ? btn('Apply to digiKam database…', dbDialog, !m.digikamRunning) : null) : null,
    S.CAN_MANAGE ? (() => {  // digiKam's pick labels, which iopix does not use: counted, and cleared on request
      const line = h('span', null, '');
      const boxes = { 1: h('input', { type: 'checkbox', checked: true }), 2: h('input', { type: 'checkbox' }), 3: h('input', { type: 'checkbox' }) };
      const names = { 1: 'Rejected', 2: 'Pending', 3: 'Accepted' };
      const wrap = h('span', { class: 'toolbar' });
      api('/api/picklabels').then((d) => {
        const cnt = d.counts, p = d.progress;
        fill(line, p.running ? `Clearing… sidecars ${nf.format(p.done)} / ${nf.format(p.total)}. ` : `${['Rejected', 'Pending', 'Accepted'].map((n, i) => `${n}: ${nf.format(cnt[i + 1])}`).join(', ')}. `);
        fill(wrap, [1, 2, 3].map((k) => h('label', { class: 'chk' }, boxes[k], names[k])), btn('Clear…', async () => {
          const ks = [1, 2, 3].filter((k) => boxes[k].checked), n = ks.reduce((a, k) => a + cnt[k], 0);
          if (!ks.length || !n) { toast('No photo carries the chosen labels.'); return; }
          if (!await confirmDialog(`Take the ${ks.map((k) => names[k]).join(', ')} pick label off ${plural(n, 'photo')}? digiKam’s database is backed up first, sidecars that carry the label are cleaned too (each backed up), and every photo’s change is in the edit log with undo.`, { ok: 'Clear', danger: true })) return;
          try { const r = await post('/api/picklabels/clear', { levels: ks }); toast(`Pick label cleared from ${plural(r.cleared, 'photo')}.`); } catch (e) { toastError(e); }
          again();
        }, true));
      }).catch(() => fill(line, ''));
      return row('Pick labels', h('span', null, line, `digiKam’s pick labels, which ${S.APP_NAME} never sets.`), wrap);
    })() : null,
    row('Tag cover photos', 'Picked by the content model; pick again after big tagging changes.', btn('Pick again', () => maint('covers', 'Choosing tag covers in the background.'))),
  );
  main.replaceChildren(page);
  boxed([...page.children].slice(1));
}

/** Settings › Server: iosuite-shared's panel, the same in every ioThing app, then the backups to download. */
export const serverUi = () => import(new URL('api/server/ui.js', document.baseURI).href);
function serverTab(c) {
  const { row } = c;
  const box = h('div');
  serverUi().then((ui) => ui.mount(box, { toast })).catch((e) => fill(box, errorBox(new Error(`The Server panel did not load: ${e.message}`))));
  return [stab('server'), box,
    h('h2', null, 'Backups'),
    row('Download a backup', S.NO_DK ? `${S.APP_NAME}’s database and search index, as a zip.` : `digiKam’s database as it is now, and ${S.APP_NAME}’s database and search index as a zip.`,
      h('div', { style: 'display:flex;gap:8px;flex-wrap:wrap' }, S.NO_DK ? null : h('a', { class: 'pillbtn', href: '/api/backup/digikam', download: '' }, icon('download'), h('span', null, 'digiKam database')),
        h('a', { class: 'pillbtn', href: '/api/backup/app', download: '' }, icon('download'), h('span', null, `${S.APP_NAME} data (zip)`))))];
}
async function settingsPage(view) {
  let m;
  if (!main.querySelector('.spage:not(.tpage)')) main.replaceChildren(h('div', { class: 'page spage' }, loadingBox('Loading the settings…')));
  try { m = await api('/api/maintenance'); } catch (e) { if (S.route.view === view) main.replaceChildren(h('div', { class: 'empty' }, 'Could not load settings: ' + e.message)); return; }
  if (S.route.view !== view) return;
  const c = settingsContext(m, view);
  const { row, btn } = c;
  const suite = S.USER && S.USER.suiteAdmin;
  main.replaceChildren(h('div', { class: 'page spage' },
    pageTitle('gear', 'slate', 'Settings'),
    !S.USERS_EXIST ? row('No users yet', `${S.APP_NAME} is open to anyone who can reach it. Create the admin account to switch on sign-in.`, btn('Create the admin account', setupDialog, true)) : null,
    S.USER ? accountTab() : null,
    displayTab(c),
    S.IS_ADMIN && S.EDITING ? editingTab(c) : null,
    S.IS_ADMIN ? libraryTab(c) : null,
    S.IS_ADMIN ? [stab('ai'), aiSection(view)] : null,
    S.IS_ADMIN ? serverTab(c) : null,
    suite ? [stab('security'), suiteSection('security')] : null,
    suite ? [stab('global'), suiteSection('global')] : null,
  ));
  settingsTabs(main.querySelector('.spage'), view);
}

/** The viewer's own database (MariaDB/MySQL): where it is, whether it answers, and the fields to test and move to
 *  another one. The same panel serves Settings and the set-up page the app shows while it has no database at all
 *  (main.js), where `setup` makes the button say so and the page reload once the viewer restarts. */
export function viewerDbPanel({ setup = false } = {}) {
  const body = h('div', { class: 'muted note' }, 'Loading…');
  const btn = (label, fn, primary) => h('button', { class: 'pillbtn' + (primary ? ' on' : ''), onclick: fn }, label);
  (async () => {
    let d; try { d = await api('/api/viewerdb'); } catch (e) { fill(body, e.message); return; }
    if (d.locked) {  // configured but not answering, and nobody signed in: only Retry (the connection is changed in data/viewer-db.json or DB_* in config.env)
      const result = h('div', { class: 'muted', style: 'font-size:12.5px;margin-top:6px' });
      fill(body, h('div', null, `${S.APP_NAME}’s database is configured but not answering: `, h('span', { class: 'warn' }, d.error || ''),
        h('div', { class: 'muted note mt6' }, 'Start the database server (or wait for it) and retry. To use another server, change data/viewer-db.json or the DB_* settings in config.env and restart.')),
        h('div', { class: 'btnrow', style: 'margin-top:8px' },
          btn('Retry the configured database', async () => { fill(result, 'Trying…'); try { await post('/api/viewerdb/retry', {}); fill(result, 'It answers now. Restarting…'); setTimeout(() => location.reload(), 4000); } catch (e) { fill(result, e.message); } }, true)), result);
      return;
    }
    const inp = (k, ph, type = 'text', w = 160) => h('input', { class: 'einput', type, placeholder: ph, value: type === 'password' ? '' : (d[k] ?? ''), autocomplete: 'off', style: `margin:0;width:${w}px`, onkeydown: (e) => e.stopPropagation() });
    const f = { host: inp('host', 'host'), port: inp('port', 'port', 'text', 70), database: inp('database', 'database'), user: inp('user', 'user'),
      password: inp('password', d.password_set ? 'password (stored; leave empty to keep)' : 'password', 'password') };
    const fields = h('div', { class: 'toolbar tight mt6' }, f.host, f.port, f.database, f.user, f.password);
    const hasData = d.configured && !d.error;
    const copy = h('input', { type: 'checkbox', checked: true }), drop = h('input', { type: 'checkbox' });  // dropping is opt-in: the target may be a database in use
    const copyLabel = hasData ? 'Copy all the data from the current database to the new one' : null;
    const opts = h('div', { style: 'display:grid;gap:4px;margin-top:8px;font-size:13px' },
      copyLabel ? h('label', { class: 'chk' }, copy, copyLabel) : null,
      h('label', { class: 'chk' }, drop, `Drop and recreate ${S.APP_NAME}’s tables at the target first (a clean slate; anything already there is lost)`));
    const payload = () => ({ host: f.host.value, port: f.port.value, database: f.database.value, user: f.user.value, password: f.password.value });
    const result = h('div', { class: 'muted', style: 'font-size:12.5px;margin-top:6px' });
    const restartThen = (msg) => { fill(result, msg + ' Restarting…'); setTimeout(() => { if (setup) location.reload(); else pollSoon(2000); }, 4000); };
    const current = !d.configured ? `No database yet: ${S.APP_NAME} needs a MariaDB or MySQL database of its own. Create an empty one with a user that owns it, enter its details and press Use this database.`
      : `${d.error ? 'Configured' : 'Currently'}: MySQL ${d.user}@${d.host}:${d.port}/${d.database}`;
    fill(body, h('div', null, current, d.error && d.configured ? h('span', { class: 'warn' }, ` · not answering: ${d.error}`) : null),
      fields, opts,
      h('div', { class: 'btnrow', style: 'margin-top:8px' },
        btn('Test connection', async () => { fill(result, 'Testing…'); try { const r = await post('/api/viewerdb/test', payload()); const t = Object.entries(r.tables); fill(result, `OK: ${r.version}. ${t.length ? `${S.APP_NAME} tables already there: ` + t.map(([k, n]) => `${k} ${nf.format(n)}`).join(', ') : 'An empty database.'}`); } catch (e) { fill(result, e.message); } }),
        d.configured && d.error ? btn('Retry the configured database', async () => { fill(result, 'Trying…'); try { await post('/api/viewerdb/retry', {}); restartThen('It answers now.'); } catch (e) { fill(result, e.message); } }) : null,
        btn(d.configured ? 'Switch' : 'Use this database', async () => {
          const p = payload();
          if (!await confirmDialog(`${d.configured ? 'Switch' : 'Set up'} ${S.APP_NAME} on MySQL ${p.user}@${p.host}:${p.port}/${p.database}?` + (copyLabel && copy.checked ? `\n\nEvery row is copied there first${drop.checked ? ', after dropping and recreating the tables there' : ''}.` : drop.checked ? '\n\nThe tables there are dropped and created again.' : '') + `\n\n${S.APP_NAME} restarts on the new database.`, { ok: d.configured ? 'Switch' : 'Use it' })) return;
          fill(result, 'Copying… this can take a minute on a large library.');
          try { const r = await post('/api/viewerdb/switch', { ...p, copy: !!copyLabel && copy.checked, drop: drop.checked }); restartThen(`Set up on ${r.database}: ` + Object.entries(r.copied).map(([k, n]) => `${k} ${nf.format(n)}`).join(', ') + '.'); } catch (e) { fill(result, e.message); }
        }, true)), result);
  })();
  return body;
}
