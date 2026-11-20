import { ALERT_DEFAULTS, SECTIONS, applySections, fmtCompact, forgetTypeList, h, pages, prettyUnit, sectionOn, typeHidden, typeLabel } from './core.js';
import { api, apiCache, applyTheme, pageTitle, saveSettings, settings } from './shell.js';
import { card, seg } from './charts.js';
import { accountUi, isAdmin, me, setAccount, suitePanel, toast } from './accounts.js';

// ---------- settings: tabs, as in every ioThing app (#/settings/account … #/settings/server) ----------
// One Settings page for everything, in every ioThing app. Each tab loads only what it shows. The account's own tabs
// come first, then the admins' (the server) and the suite admins' (Security:
// people, roles, app passwords, sign-in at the proxy; Global settings: the apps, keys; iosuite-shared's panel).

export const SUITE_TABS = { security: 'Security', global: 'Global settings' };
export const SETTINGS_TABS = () => [['account', 'Account'], ['display', 'Display'], ['health', 'Health'], ['goals', 'Goals and alerts'],
  ...(isAdmin() ? [['server', 'Server']] : []),
  ...(me.isSuiteAdmin ? [['security', SUITE_TABS.security], ['global', SUITE_TABS.global]] : [])];

/** The page title and a row of tabs linking to #/<view>/<tab>.
 *  Draws at once; the tab fills the returned body when its data is in. */
export function tabbedPage(main, view, ic, title, tabs, arg) {
  let tab = arg;
  if (!tabs.some(([k]) => k === tab)) tab = tabs[0][0];
  if (arg !== tab) history.replaceState(null, '', `#/${view}/${tab}`);
  const body = h('div', {}, h('p', { class: 'muted' }, 'Loading…'));
  main.replaceChildren(h('div', { class: 'spage' }, pageTitle(ic, 'slate', title),
    h('div', { class: 'stabs', role: 'tablist' }, tabs.map(([k, l]) => h('button', { role: 'tab', class: k === tab ? 'on' : '', 'aria-selected': String(k === tab),
      onclick: () => { location.hash = `#/${view}/${k}`; } }, l))),
    body));
  return { tab, body };
}

pages.settings = async (main, arg, params) => {
  const [t, sub] = (arg || '').split('/');  // #/settings/security/<part>
  const { tab, body } = tabbedPage(main, 'settings', 'gear', 'Settings', SETTINGS_TABS(), t);
  const els = await ({ account: setAccount, display: setDisplay, health: setHealth, goals: setGoals,
    server: setServer, security: () => suitePanel(tab, sub), global: () => suitePanel(tab, sub) }[tab])(body);
  if (els) body.replaceChildren(...els.filter(Boolean));
};

export const sortedTypeList = async () => (await api('types').catch(() => [])).slice().sort((a, b) => typeLabel(a.type).localeCompare(typeLabel(b.type)));

export async function setDisplay() {
  const sortedTypes = await sortedTypeList();
  const typeFilter = h('input', { placeholder: 'Filter…', style: { width: '200px' } });
  const typeRows = h('div', { class: 'grid', style: { gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '2px 16px', marginTop: '10px' } });
  const drawTypes = () => typeRows.replaceChildren(...sortedTypes.filter(t => !typeFilter.value || typeLabel(t.type).toLowerCase().includes(typeFilter.value.toLowerCase()))
    .map(t => h('label', { class: 'row small', style: { gap: '6px', flexWrap: 'nowrap' } },
      h('input', { type: 'checkbox', checked: !(settings.hiddenTypes || []).includes(t.type), onchange: e => {
        const set = new Set(settings.hiddenTypes || []);
        e.target.checked ? set.delete(t.type) : set.add(t.type);
        settings.hiddenTypes = [...set]; saveSettings(); forgetTypeList();
      } }), typeLabel(t.type), h('span', { class: 'muted' }, fmtCompact(t.count)))));
  typeFilter.addEventListener('input', drawTypes);
  drawTypes();
  const ui = await accountUi();
  const saveNow = async () => { saveSettings(); };
  return [
    ui.box('theme', 'Display',
      ui.themeRow(settings.theme === 'auto' ? 'system' : settings.theme, v => { settings.theme = v === 'system' ? 'auto' : v; applyTheme(); }, saveNow),
      ui.unitsRow(settings.units || 'auto', v => { settings.units = v; apiCache.clear(); }, saveNow)),
    card('Sections', h('p', { class: 'small muted', style: { marginTop: 0 } }, 'Untick what you don\'t use to hide it everywhere.'),
      ...SECTIONS.map(([key, label, what]) => h('label', { class: 'row', style: { gap: '8px', margin: '6px 0' } },
        h('input', { type: 'checkbox', checked: sectionOn(key), onchange: e => {
          const set = new Set(settings.hiddenSections || []);
          e.target.checked ? set.delete(key) : set.add(key);
          settings.hiddenSections = [...set]; saveSettings(); forgetTypeList(); applySections();
        } }), h('b', {}, label), h('span', { class: 'muted small' }, what)))),
    card('Metrics', h('div', { class: 'row spread' }, h('span', { class: 'small muted' }, 'Untick a metric to hide it everywhere. The number is how many samples you have.'),
      h('span', { class: 'row' }, typeFilter,
        h('button', { onclick: () => { settings.hiddenTypes = []; saveSettings(); forgetTypeList(); drawTypes(); } }, 'Show all'))), typeRows)];
}

export async function setHealth() {
  const profile = await api('profile').catch(() => ({}));
  const maxIn = h('input', { type: 'number', min: 120, max: 230, placeholder: String(profile.maxHr || ''), value: settings.maxHr, style: { width: '110px' }, onchange: () => { settings.maxHr = maxIn.value; saveSettings(); apiCache.clear(); } });
  const saveRange = () => { settings.glucoseLow = lowIn.value || '70'; settings.glucoseHigh = highIn.value || '180'; saveSettings(); apiCache.clear(); };
  const lowIn = h('input', { type: 'number', min: 50, max: 120, value: settings.glucoseLow || 70, style: { width: '90px' }, onchange: saveRange });
  const highIn = h('input', { type: 'number', min: 100, max: 300, value: settings.glucoseHigh || 180, style: { width: '90px' }, onchange: saveRange });
  return [
    card('Blood glucose',
      h('div', { class: 'toolbar' }, h('span', { style: { width: '160px' } }, 'Unit'),
        seg([['mg/dL', 'mg/dL'], ['mmol/L', 'mmol/L']], settings.glucoseUnit || 'mg/dL', v => { settings.glucoseUnit = v; saveSettings(); })),
      h('div', { class: 'toolbar' }, h('span', { style: { width: '160px' } }, 'Target range (mg/dL)'), lowIn, '–', highIn),
      h('p', { class: 'small muted' }, 'Usually 70–180 mg/dL (3.9–10.0 mmol/L).')),
    card('Heart rate',
      h('div', { class: 'toolbar' }, h('span', { style: { width: '160px' } }, 'Maximum heart rate'), maxIn,
        h('span', { class: 'muted small' }, profile.maxHr ? `Without a value: ${profile.maxHr} bpm (${profile.maxHrFrom === 'age' ? '220 − age' : 'highest recorded'})` : '')),
      h('p', { class: 'small muted' }, 'For heart rate zones and training load.'))];
}

export async function setGoals() {
  const [sortedTypes, allTypes] = await Promise.all([sortedTypeList(), api('types').catch(() => [])]);
  // Goals: a metric, at least / at most, and a value in the units the app shows.
  const goalTypes = sortedTypes.filter(t => ['quantity', 'category', 'ring'].includes(t.kind) && !typeHidden(t.type));
  const unitOf = t => { const x = allTypes.find(a => a.type === t); return !x ? '' : x.unit === '%' ? '%' : t === 'sleep_analysis' ? 'h per night' : prettyUnit(x.unit); };
  const goalsEl = h('div');
  const drawGoals = () => goalsEl.replaceChildren(...(settings.goals || []).map((g, i) => h('div', { class: 'goal-row' },
    h('select', { onchange: e => { g.type = e.target.value; saveSettings(); drawGoals(); } }, goalTypes.map(t => h('option', { value: t.type, selected: t.type === g.type }, typeLabel(t.type)))),
    h('select', { onchange: e => { g.dir = e.target.value; saveSettings(); } }, [['min', 'at least'], ['max', 'at most']].map(([v, l]) => h('option', { value: v, selected: v === g.dir }, l))),
    h('input', { type: 'number', step: 'any', value: g.value, placeholder: 'value', style: { width: '110px' }, onchange: e => { g.value = e.target.value; saveSettings(); } }),
    h('span', { class: 'muted small' }, g.type === 'sleep_analysis' ? 'hours a night' : unitOf(g.type) + (goalTypes.find(t => t.type === g.type)?.cumulative || g.type.startsWith('activity_') ? ' a day' : '')),
    h('button', { title: 'Remove this goal', onclick: () => { settings.goals.splice(i, 1); saveSettings(); drawGoals(); } }, '✕'))),
    ...((settings.goals || []).length ? [] : [h('p', { class: 'muted small' }, 'No goals yet.')]));
  drawGoals();
  const addGoal = () => {
    const used = new Set((settings.goals || []).map(g => g.type));
    const t = ['step_count', 'body_mass', 'sleep_analysis', 'apple_exercise_time'].find(x => goalTypes.some(g => g.type === x) && !used.has(x)) || goalTypes[0]?.type;
    if (!t) return;
    settings.goals = [...(settings.goals || []), { type: t, dir: t === 'body_mass' ? 'max' : 'min', value: '' }];
    saveSettings(); drawGoals();
  };
  const alertIn = (k, label, unit) => h('div', { class: 'goal-row' }, h('span', { style: { width: '300px' } }, label),
    h('input', { type: 'number', min: 0, step: 'any', value: settings.alerts?.[k] ?? '', placeholder: String(ALERT_DEFAULTS[k]), style: { width: '90px' },
      onchange: e => { settings.alerts = { ...(settings.alerts || {}), [k]: e.target.value }; saveSettings(); } }), h('span', { class: 'muted small' }, unit));
  return [
    card('Goals', h('p', { class: 'small muted', style: { marginTop: 0 } }, 'Shown on the dashboard cards and in Metrics, with streaks.'),
      goalsEl, h('button', { onclick: addGoal, style: { marginTop: '6px' } }, '+ Add a goal')),
    card('Alerts on the dashboard', h('p', { class: 'small muted', style: { marginTop: 0 } }, 'Empty: the default in grey. 0 turns an alert off. "Your usual" is the last 7 days against the 4 weeks before; those three also come as a notification on the day they begin (Account › Notifications, Outside your usual).'),
      alertIn('tir', 'Glucose time in range under (last 7 days)', '%'), alertIn('lows', 'Glucose lows in the last 7 days, at least', 'lows'),
      alertIn('rhr', 'Resting heart rate above your usual by', 'bpm'), alertIn('hrv', 'Heart rate variability below your usual by', '%'),
      alertIn('sleep', 'Sleep below your usual by', 'minutes a night'),
      alertIn('sync', 'No sync from the iPhone for', 'hours'))];
}

// ---- Settings › Server (admins): the version and its updates, the server log and Restart:
// iosuite-shared's panel, the same in every ioThing app.

export const serverUi = () => import(new URL('api/server/ui.js', document.baseURI).href);
export async function setServer() {
  const el = h('div');
  let ui;
  try { ui = await serverUi(); } catch (e) { return [h('p', { class: 'error' }, `The Server panel did not load: ${e.message}`)]; }
  await ui.mount(el, { toast });
  return [el];
}
