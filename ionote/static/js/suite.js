/** The suite (iosuite-shared's suite_apps): when other ioThing apps are registered, the app mark top left (in the sidebar;
 *  in the top bar on a phone) opens a menu of them, each a link to that app. Alone, the mark and the name stay the link to
 *  All notes. The same as ioContacts'. */
import { $, h, api } from './core.js';

let apps = [], pop = null;

export async function loadSuite() {
  try {
    const r = await api('/api/auth/suite');
    apps = (r.items || []).filter((a) => a.app !== r.app && a.url);
  } catch (e) { apps = []; }
  const b = $('#suitebtn');
  if (b) { b.hidden = !apps.length; b.onclick = () => toggleSuite(b); }
  if (!apps.length) closeSuite();
  drawBrand();
}

/** The name on top of the sidebar: with other apps, the mark is the switcher's button and the name the link home. */
function drawBrand() {
  const old = $('#nav .navhead .brand');
  if (!old) return;
  const mark = () => h('img.brand-mark', { src: 'icons/mark.svg', alt: '' });
  const name = () => h('span.brand-name', h('span.io', 'io'), h('span.nm', 'Notes'));
  old.replaceWith(apps.length
    ? h('div.brand',
      h('button.suitebtn', { type: 'button', title: 'ioThing apps', 'aria-label': 'ioThing apps', 'aria-haspopup': 'menu', onclick: (e) => toggleSuite(e.currentTarget) }, mark()),
      h('a.brand-home', { href: '#/notes', title: 'All notes' }, name()))
    : h('a.brand', { href: '#/notes', title: 'All notes' }, mark(), name()));
}

function closeSuite() {
  if (!pop) return;
  pop.remove(); pop = null;
  document.removeEventListener('click', outside, true);
  document.removeEventListener('keydown', onKey);
  removeEventListener('resize', closeSuite);
}
function outside(e) { if (pop && !pop.contains(e.target) && !e.target.closest('.suitebtn')) closeSuite(); }
function onKey(e) { if (e.key === 'Escape') { closeSuite(); e.stopPropagation(); } }

function appTile(a) {
  const letter = (a.name || a.app).replace(/^io(?=[A-Z])/, '').slice(0, 1).toUpperCase();
  const fallback = () => h('span.appic.fb', { style: { background: a.color || 'var(--brand)' } }, letter);
  const ic = a.icon ? h('img.appic', { src: a.icon, alt: '', onerror: (e) => e.currentTarget.replaceWith(fallback()) }) : fallback();
  return h('a.apptile', { href: a.url, role: 'menuitem', title: a.description || a.name, onclick: closeSuite }, ic, h('span.appnm', a.name || a.app));
}

function toggleSuite(btn) {
  if (pop) { closeSuite(); return; }
  if (!apps.length) return;
  pop = h('div.suitepop', { role: 'menu', 'aria-label': 'ioThing apps' }, ...apps.map(appTile));
  pop.style.setProperty('--cols', String(Math.min(3, apps.length)));
  document.body.append(pop);
  const r = btn.getBoundingClientRect();
  pop.style.top = `${Math.round(r.bottom + 6)}px`;
  pop.style.left = `${Math.round(Math.max(8, Math.min(r.left - 6, innerWidth - pop.offsetWidth - 8)))}px`;
  setTimeout(() => { document.addEventListener('click', outside, true); document.addEventListener('keydown', onKey); addEventListener('resize', closeSuite); }, 0);
}
