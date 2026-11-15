import { REFRESH_HOURS, S, addDays, api, canOwn, canShared, confirmDialog, copyRow, describeReminder, fail, fill, h, icon, isAuto, loadCals, saveSettings, toast, weekStart, ymd } from './core.js';
import { applyTheme, colorPicker, drawNav, drawUser, newCalendar } from './shell.js';
import { TIMED_REMINDERS, zones } from './edit.js';
import { onRoute } from './main.js';
import { profileScope as scopeSelect } from '../../api/auth/ui.js';

// ------------------------------------------------------------------ settings
export async function showSettings(page, r) {
  const adm = S.user.role === 'admin';
  const tabs = [['account', 'Account'], ['display', 'Display'], ['devices', 'Apps and devices'], ['calendars', 'Calendars'], ['holidays', 'Holidays and birthdays'],
    ...(adm ? [['server', 'Server']] : []),
    ...(S.user.suiteAdmin ? [['security', SUITE_TABS.security], ['global', SUITE_TABS.global]] : [])];
  page.append(h('div', { class: 'pagehead' }, h('h1', null, 'Settings')),
    h('div', { class: 'tabs' }, tabs.map(([k, l]) => h('button', { class: r.tab === k ? 'on' : '', onclick: () => { location.hash = `#/settings/${k}`; } }, l))));
  const body = h('div'); page.append(body);
  await ({ account: setAccount, display: setDisplay, devices: setDevices, calendars: setCalendars, holidays: setHolidays, server: setServer,
    security: setSuite, global: setSuite }[r.tab] || setAccount)(body, r);
}
const fld = (l, e) => h('label', { class: 'field' }, h('span', null, l), e);
export const kv = (k, v) => h('div', { class: 'kv' }, h('div', { class: 'k' }, k), h('div', { class: 'v', style: { flex: 1 } }, typeof v === 'string' ? copyRow(v) : v));

export const accountUi = () => import(new URL('api/auth/ui.js', document.baseURI).href);
/** Settings › Account: display name, email and password, then the app passwords: iosuite-shared's panels (the same in every io app). */
export async function setAccount(el) {
  const ui = await accountUi();
  const pw = h('div');
  await ui.mountAccount(el, { toast, onSaved: (u) => { Object.assign(S.user, u); drawUser(); } });
  el.append(pw);
  await ui.mountAppPasswords(pw, { toast, syncOnly: 'Calendar apps only (CalDAV)' });
}

/** Settings › Display: the theme (saved with the account) and the calendar's own choices, each saved when changed. */
export async function setDisplay(el) {
  const ui = await accountUi();
  const save = async (changes) => { await saveSettings(changes); drawNav(); toast('Saved'); };
  const ws = h('select', { class: 't', onchange: (e) => save({ weekStart: +e.target.value }) }, [[1, 'Monday'], [0, 'Sunday'], [6, 'Saturday']].map(([v, l]) => h('option', { value: v, selected: v === weekStart() ? true : null }, l)));
  const dv = h('select', { class: 't', onchange: (e) => save({ defaultView: e.target.value }) }, [['month', 'Month'], ['week', 'Week'], ['day', 'Day'], ['agenda', 'Agenda']].map(([v, l]) => h('option', { value: v, selected: v === (S.settings.defaultView || 'month') ? true : null }, l)));
  const cur = S.settings.defaultReminder ?? '';
  const dr = h('select', { class: 't', onchange: (e) => save({ defaultReminder: e.target.value }) }, h('option', { value: '' }, 'None'), TIMED_REMINDERS.map((m) => h('option', { value: m, selected: String(m) === String(cur) ? true : null }, describeReminder(m, false))));
  el.append(ui.box('theme', 'Appearance', ui.themeRow(S.settings.theme || localStorage.getItem('iocalendar.theme') || 'system', (t) => { S.settings.theme = t; applyTheme(t); })),
    h('div', { class: 'box' }, h('h2', null, icon('tune'), 'Calendar'), h('div', { class: 'grid' }, fld('Weeks start on', ws), fld('Open on', dv), fld('Reminder for new events', dr))));
}

/** The profile through a short-lived link instead of the form post: the app on the Home Screen opens a download in a
 * separate sheet without its cookies, which a link opens by itself (the form post stays the fallback without script). */
export async function downloadProfile(e) {
  e.preventDefault();
  const f = e.target;
  const btn = f.querySelector('button[type=submit]');
  if (btn) btn.disabled = true;
  try {
    const all = f.elements.scope && f.elements.scope.value === 'suite';
    const r = await api(all ? 'api/apple-profile/suite/link' : 'api/apple-profile/link', { method: 'POST', json: { label: f.elements.label.value, password: f.elements.password.value } });
    location.href = r.url;
  } catch (err) {
    toast(err.message);
  } finally {
    if (btn) setTimeout(() => { btn.disabled = false; }, 1500);
  }
}

/** The "Set up" choice of the profile box: this app only, or every app that syncs (iosuite-shared's suite profile),
 * offered when the account may use two or more of them. Fields marked data-own belong to this app's own profile. */
export const profileScope = (apps, own) => { const s = scopeSelect(apps, own, { class: 't' }); return s && fld('Set up', s); };

/** Settings › Apps and devices: how to connect each kind of app (the app passwords themselves are on Settings › Account). */
export async function setDevices(el) {
  const info = await api('api/connect');
  const suiteApps = S.user.passwordless ? [] : (await api('api/apple-profile/suite').catch(() => ({ apps: [] }))).apps;
  const canPw = !S.user.passwordless;
  const isApple = /iPhone|iPad|Macintosh/.test(navigator.userAgent);
  const plabel = h('input', { class: 't', name: 'label', value: /iPad/.test(navigator.userAgent) ? 'iPad' : /Macintosh/.test(navigator.userAgent) ? 'Mac' : 'iPhone', style: 'max-width:200px' });
  const how = (summary, ...kids) => h('details', null, h('summary', { class: 'lnk' }, summary), ...kids);
  const subs = h('div');
  el.append(...[
    canPw ? h('div', { class: 'box' }, h('h2', null, icon('devices'), 'iPhone, iPad and Mac'),
      h('p', null, 'A profile that adds your calendars to Apple Calendar in one step.'),
      h('form', { method: 'POST', action: 'api/apple-profile', class: 'pform', onsubmit: downloadProfile },
        profileScope(suiteApps, 'ioCalendar'),
        fld('Device name', plabel),
        fld('Password', h('select', { class: 't', name: 'password' }, h('option', { value: 'new' }, 'Include a new app password'), h('option', { value: 'ask' }, 'Ask on the device'))),
        h('p', null, h('button', { class: 'pillbtn primary', type: 'submit' }, icon('download', 's'), 'Download the profile'))),
      how('How to install', h('p', { class: 'muted small' }, isApple ? 'Open the download, then Settings › Profile Downloaded › Install.' : 'Download it in Safari on the iPhone or iPad, then Settings › Profile Downloaded › Install. On a Mac: open the file, then System Settings › Privacy & Security › Profiles.',
        ' iOS shows the profile as “Not Verified”: that is expected. Revoke its app password under Settings › Account if the device is lost.',
        suiteApps.length > 1 ? ' A profile for all apps holds one app password per app; revoke each one in its own app.' : null))) : null,
    h('div', { class: 'box' }, h('h2', null, icon('today'), 'Calendar apps (CalDAV)'),
      h('p', null, 'Two-way sync with your user name and an app password (Settings › Account).'),
      kv('Server', info.server), kv('User name', info.user), kv('CalDAV', info.caldav),
      how('Address of each calendar', info.calendars.map((c) => kv(c.name, c.caldav))),
      how('How to connect', h('p', { class: 'muted small' }, 'Apple Calendar: Settings › Accounts › Add › Other CalDAV Account (iPhone: Settings › Calendar › Accounts). Android: DAVx⁵. Also Thunderbird, Evolution, GNOME, KDE.'),
        h('p', { class: 'muted small' }, 'Behind Cloudflare Access, add a Bypass policy for /dav/*, /.well-known/caldav and /ics/* (and /mcp).'))),
    subs,
    S.status.mcp ? h('div', { class: 'box' }, h('h2', null, icon('ai'), 'AI assistants (MCP)'),
      h('p', null, 'Give the assistant its own app password (not “Calendar apps only”), sent as a Bearer token.'),
      kv('MCP address', info.mcp),
      how('Setup for Claude Code and JSON-configured apps',
        copyRow(`claude mcp add --transport http iocalendar ${info.mcp} --header "Authorization: Bearer APP-PASSWORD"`),
        copyRow(JSON.stringify({ mcpServers: { iocalendar: { command: 'npx', args: ['-y', 'mcp-remote', info.mcp, '--header', 'Authorization: Bearer APP-PASSWORD'] } } }))))
      : (S.user.role === 'admin' ? h('div', { class: 'box' }, h('h2', null, icon('ai'), 'AI assistants (MCP)'), h('p', { class: 'muted' }, 'Off. Turn it on in ', h('a', { class: 'lnk', href: '#/settings/server' }, 'Settings › Server'), '.')) : null),
    h('div', { class: 'box' }, h('h2', null, icon('link'), 'Other apps (REST API)'),
      h('p', null, 'JSON, iCalendar or jCal with your user name and an app password. ', h('a', { class: 'lnk', href: info.api, target: '_blank' }, 'API documentation')),
      copyRow(`curl -u ${info.user}:APP-PASSWORD "${info.server}/api/occurrences?start=${ymd(new Date())}&end=${ymd(addDays(new Date(), 7))}"`))].filter(Boolean));
  (await accountUi()).mountFeeds(subs, { toast, icon: 'devices', title: 'Subscribe (read-only)',
    intro: 'For calendar apps that cannot sign in: every calendar you see, free/busy, or one calendar. Anyone with a link can read those events, so make one per app or device and stop it when it is no longer used.' }).catch(fail);
}

export async function setCalendars(el) {
  await loadCals();
  const tzs = zones(S.status.timezone);
  el.append(h('p', null, canShared() ? h('button', { class: 'pillbtn', onclick: async () => { await newCalendar(true); onRoute(); } }, icon('add', 's'), 'New shared calendar') : null, ' ',
    canOwn() ? h('button', { class: 'pillbtn', onclick: async () => { await newCalendar(false); onRoute(); } }, icon('add', 's'), 'New private calendar') : null),
  ...S.cals.map((c) => {
    const auto = isAuto(c);
    const save = async (body) => { try { await api(`api/calendars/${c.id}`, { method: 'PATCH', json: body }); await loadCals(); toast('Saved'); } catch (e) { fail(e); } };
    const name = h('input', { class: 't', value: c.name, onchange: (e) => save({ name: e.target.value }) });
    const col = colorPicker(c.color, (v) => save({ color: v }));
    const tz = h('select', { class: 't', onchange: (e) => save({ timezone: e.target.value || null }) }, h('option', { value: '' }, `Server default (${S.status.timezone})`), tzs.map((z) => h('option', { value: z, selected: z === c.timezone ? true : null }, z.replace(/_/g, ' '))));
    const desc = h('input', { class: 't', value: c.description || '', placeholder: 'What it is for', onchange: (e) => save({ description: e.target.value }) });
    const sub = c.kind === 'subscribed' ? c.subscription : null;
    const manage = !!(sub && sub.manage);
    const canEdit = c.writable || (auto && S.user.role === 'admin') || manage;
    return h('div', { class: 'box', style: { '--c': c.color } },
      h('h2', null, h('span', { class: 'chip-ev allday', style: { '--c': c.color, display: 'inline-flex', width: '14px', height: '14px', padding: 0 } }), c.name,
        h('span', { class: 'muted small', style: { fontWeight: 400 } }, c.kind === 'birthdays' ? 'from ioContact, read-only' : c.kind === 'holidays' ? 'public holidays, read-only'
          : sub ? `outside calendar, read-only, ${c.shared ? 'shared with everyone' : 'only you'}` : c.shared ? 'shared with everyone' : 'only you')),
      sub ? subscriptionBox(c, sub, manage) : null,
      canEdit ? [h('div', { class: 'grid' }, fld('Name', name), fld('Description', desc), auto ? null : fld('Time zone for floating times', tz)), h('div', { style: { margin: '10px 0' } }, col),
        h('p', null,
        (!auto || manage) && (!c.shared || S.user.role === 'admin') ? h('button', { class: 'pillbtn noic danger', onclick: async () => {
          if (!await confirmDialog('Delete calendar', `Delete ${c.name} and its ${c.count || 0} events? Apps that sync it lose it too.`, 'Delete', true)) return;
          try { await api(`api/calendars/${c.id}`, { method: 'DELETE' }); await loadCals(); onRoute(); } catch (e) { fail(e); }
        } }, 'Delete') : null)] : h('p', { class: 'muted' }, auto ? (c.kind === 'holidays' ? 'Filled from Settings › Holidays and birthdays.' : 'Filled from ioContact (Settings › Holidays and birthdays).') : `${c.count || 0} events. Editors and admins change shared calendars.`));
  }));
}

/** An outside calendar's address, how often it is fetched and how the last fetch went; the address only for those who manage it. */
function subscriptionBox(c, sub, manage) {
  const every = (n) => (REFRESH_HOURS.find(([x]) => x === n) || [n, `Every ${n} hours`])[1].toLowerCase();
  const status = sub.error ? h('p', { class: 'small', style: { color: 'var(--danger)' } }, `The last fetch failed: ${sub.error}`
    + (sub.synced ? ` (events as of ${new Date(sub.synced * 1000).toLocaleString()})` : ''))
    : h('p', { class: 'muted small' }, sub.synced ? `${sub.events ?? c.count ?? 0} events, last fetched ${new Date(sub.synced * 1000).toLocaleString()}.` : 'Not fetched yet.');
  if (!manage) return [h('p', { class: 'muted' }, `From ${sub.host}, fetched ${every(sub.refreshHours)}. ${c.shared ? 'Editors and admins change it.' : ''}`), status];
  const patch = async (body) => {
    try {
      const r = await api(`api/subscriptions/${c.id}`, { method: 'PATCH', json: body });
      toast(r.sync && !r.sync.ok ? r.sync.error : 'Saved'); await loadCals(); onRoute();
    } catch (e) { fail(e); onRoute(); }
  };
  const url = h('input', { class: 't', type: 'url', value: sub.url || '', spellcheck: 'false', autocomplete: 'off', onchange: (e) => { toast('Reading the calendar…'); patch({ url: e.target.value }); } });
  const sel = h('select', { class: 't', onchange: (e) => patch({ refreshHours: Number(e.target.value) }) },
    REFRESH_HOURS.map(([n, l]) => h('option', { value: n, selected: n === sub.refreshHours ? true : null }, l)));
  return [h('div', { class: 'grid' }, fld('Web address', url), fld('Fetch it again', sel)), status,
    h('p', null, h('button', { class: 'pillbtn', onclick: async (e) => {
      e.currentTarget.disabled = true;
      try { const r = await api(`api/subscriptions/${c.id}/refresh`, { method: 'POST' }); toast(r.ok ? `Up to date: ${r.events} events` : r.error); await loadCals(); } catch (err) { fail(err); }
      onRoute();
    } }, icon('repeat', 's'), 'Fetch now'))];
}

/** Settings › Security and Global settings (suite admins): the people, their role in every app, app
    passwords, sign-in at the proxy; the apps, keys and tokens. The same panel in every io app, served by iosuite-shared. */
export const SUITE_TABS = { security: 'Security', global: 'Global settings' };
export async function setSuite(el, r) {
  let ui;
  try { ui = await import(new URL('api/suite-admin/ui.js', document.baseURI).href); } catch (e) { el.append(h('p', { class: 'warn' }, `The panel did not load: ${e.message}`)); return; }
  await ui.mount(el, { tab: r.tab, sub: r.sub, toast, onSub: (x) => history.replaceState(null, '', `#/settings/${r.tab}/${x}`) });
}

/** Settings › Holidays and birthdays, for admins: the Birthdays calendar ioContact fills (the suite connects the two by
    itself, so there is nothing else to set). */
export async function birthdaysBox(el) {
  const s = await api('api/iocontact/settings');
  const out = h('p', { class: 'muted small' }, s.lastSync && s.lastSync.synced ? `Last brought up to date ${new Date(s.lastSync.synced * 1000).toLocaleString()} (${s.lastSync.count} dates).` : s.lastSync && s.lastSync.error ? `The last sync failed: ${s.lastSync.error}` : '');
  const bdays = h('input', { type: 'checkbox', checked: s.birthdays, onchange: async (e) => {
    try {
      const r = await api('api/iocontact/settings', { method: 'POST', json: { birthdays: e.target.checked } });
      S.status = await api('api/status'); await loadCals();
      out.className = r.sync && !r.sync.ok ? 'warn' : 'muted small';
      out.textContent = r.sync ? (r.sync.ok ? (r.sync.count ? `${r.sync.count} dates.` : 'The Birthdays calendar is off.') : r.sync.error) : '';
      toast('Saved');
    } catch (err) { e.target.checked = !e.target.checked; fail(err); }
  } });
  el.append(h('div', { class: 'box' }, h('h2', null, icon('contacts'), 'Birthdays'),
    h('p', { class: 'muted' }, s.enabled ? ['Birthdays and anniversaries from ', h('a', { href: s.url, target: '_blank', rel: 'noopener' }, 'ioContact'), ', updated every six hours.']
      : 'Shown once ioContact runs in the same suite.'),
    h('p', null, h('label', { class: 'check' }, bdays, ' Show the Birthdays calendar'), ' ',
      s.enabled ? h('button', { class: 'pillbtn noic', onclick: async () => { try { const r = await api('api/iocontact/sync', { method: 'POST' }); await loadCals(); toast(r.ok ? `Birthdays: ${r.count} dates` : r.error); } catch (e) { fail(e); } } }, 'Update now') : null), out));
}

export async function setHolidays(el) {
  const s = await api('api/holidays/settings');
  const adm = S.user.role === 'admin';
  const last = (x) => (x && x.synced ? `Last filled ${new Date(x.synced * 1000).toLocaleString()} (${x.count} holidays, last year to three years ahead).` : x && x.error ? `The last fill failed: ${x.error}` : '');
  const shown = s.items.map((x) => x.where).join('; ');
  const box = h('div', { class: 'box' }, h('h2', null, icon('star'), 'Public holidays'),
    h('p', { class: 'muted' }, 'A shared calendar with the public holidays of each country you add.'),
    h('p', null, shown ? `Showing the holidays of ${shown}${s.guessed ? ' (from the time zone; pick another below)' : ''}.` : 'Off: no country picked.'));
  el.append(box);
  if (!adm) { box.append(h('p', { class: 'muted small' }, 'An admin picks the countries.')); return; }
  const countries = (await api('api/holidays/countries')).items;
  const LANG = (code) => { try { return new Intl.DisplayNames([], { type: 'language' }).of(code.replace('_', '-')) || code; } catch { return code; } };
  const list = h('div');
  const rows = [];
  const out = h('div', null, h('p', { class: 'muted small' }, last(s.lastSync)));
  // every change saves the whole list (a row without a country is left out until one is picked)
  const save = async () => {
    try {
      const items = rows.filter((r) => r.country.value).map((r) => ({ country: r.country.value, region: r.region.value, language: r.lang.value }));
      const r = await api('api/holidays/settings', { method: 'POST', json: { items } });
      await loadCals();
      fill(out, h('p', { class: r.sync && !r.sync.ok ? 'warn' : 'muted small' }, !r.items.length ? 'The Holidays calendars are off.' : r.sync.ok ? `Holidays of ${r.items.map((x) => x.where).join('; ')}: ${r.sync.count} dates.` : r.sync.error));
      toast('Saved');
    } catch (e) { fail(e); }
  };
  // one row per country: country, region, language and Remove
  const addRow = async (it) => {
    const country = h('select', { class: 't' }, h('option', { value: '' }, 'Pick a country'),
      countries.map((c) => h('option', { value: c.code, selected: it && c.code === it.country ? true : null }, c.name)));
    const region = h('select', { class: 't' });
    const lang = h('select', { class: 't' });
    const draw = async (keep) => {
      const code = country.value;
      if (!code) { fill(region, h('option', { value: '' }, '—')); fill(lang, h('option', { value: '' }, '—')); region.disabled = lang.disabled = true; return; }
      const info = await api(`api/holidays/countries/${code}`);
      fill(region, h('option', { value: '' }, info.regions.length ? 'The whole country' : 'No regions'),
        info.regions.map((r) => h('option', { value: r.code, selected: keep && r.code === it.region ? true : null }, r.name === r.code ? r.code : `${r.name} (${r.code})`)));
      fill(lang, h('option', { value: '' }, info.defaultLanguage ? `${LANG(info.defaultLanguage)} (default)` : 'Default'),
        info.languages.map((l) => h('option', { value: l, selected: keep && l === it.language ? true : null }, LANG(l))));
      region.disabled = !info.regions.length; lang.disabled = !info.languages.length;
    };
    country.onchange = async () => { await draw(false); await save(); };
    region.onchange = lang.onchange = save;
    const row = { country, region, lang };
    row.el = h('div', { class: 'grid', style: { marginBottom: '8px' } }, fld('Country', country), fld('Region (state, province…)', region), fld('Names in', lang),
      h('div', { style: { alignSelf: 'end' } }, h('button', { class: 'pillbtn noic', onclick: async () => { row.el.remove(); rows.splice(rows.indexOf(row), 1); if (country.value) await save(); } }, 'Remove')));
    rows.push(row); list.append(row.el);
    await draw(!!it);
  };
  for (const it of s.items) await addRow(it);
  box.append(list, h('p', null, h('button', { class: 'pillbtn noic', onclick: () => addRow(null) }, 'Add a country')), out);
  await birthdaysBox(el);
}

/** Settings › Server (admins): the MCP switch, the version and its updates, the server log and Restart
    (iosuite-shared's panel, the same in every io app), then Export: each calendar as an .ics file. */
export async function setServer(el) {
  let ui;
  const panel = h('div');
  el.append(panel);
  try { ui = await serverUi(); } catch (e) { panel.append(h('p', { class: 'warn' }, `The Server panel did not load: ${e.message}`)); return; }
  await ui.mount(panel, { toast });
  await loadCals();
  el.append(h('div', { class: 'box' }, h('h2', null, icon('download'), 'Export'),
      h('p', null, 'Each calendar as an .ics file.'),
      h('table', { class: 't' }, S.cals.map((c) => h('tr', null, h('td', null, h('span', { class: 'chip-ev', style: { '--c': c.color, display: 'inline-flex' } }, h('span', { class: 'dot' }), h('span', { class: 'nm' }, c.name))),
        h('td', { class: 'muted' }, c.kind === 'birthdays' ? 'from ioContact' : `${c.count || 0} events`),
        h('td', { style: { textAlign: 'right' } }, h('a', { class: 'pillbtn noic', href: `api/calendars/${c.id}/export` }, 'Download'))))),
      ));
}
export const serverUi = () => import(new URL('api/server/ui.js', document.baseURI).href);
