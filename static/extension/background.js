/* ioSuite Bookmarks: the background. Syncs when a bookmark changes here (a few seconds later), every minute (a small
 * request that asks whether the server changed), when the browser starts, and when asked from the popup.
 * Chrome and Edge run this as a service worker (sync.js comes in with importScripts); Firefox as a background page
 * that lists both scripts. What it keeps (storage.local): account {server, user, password, canWrite},
 * sync {rev, snap, map, roots}, status {at, ok, error, pushed}, mode (how the first sync goes). */
'use strict';
if (typeof IoSync === 'undefined' && typeof importScripts === 'function') importScripts('sync.js');
const ext = globalThis.browser || globalThis.chrome;
const QUIET_MS = 3000;  // after the last change here
let engine = null, running = null, again = false, timer = null;

const load = (keys) => ext.storage.local.get(keys);
const save = (o) => ext.storage.local.set(o);

async function request(account, method, path, body) {
  let r;
  try {
    r = await fetch(account.server + '/dav/ext' + path, {
      method, cache: 'no-store', credentials: 'omit',
      headers: { Authorization: 'Basic ' + btoa(unescape(encodeURIComponent(`${account.user}:${account.password}`))), ...(body ? { 'Content-Type': 'application/json' } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw Object.assign(new Error('The start page cannot be reached'), { offline: true });
  }
  if (r.status === 401) throw Object.assign(new Error('Signed out: the app password was removed. Sign in again.'), { signedOut: true });
  if (r.status === 423) throw Object.assign(new Error('Another sync app is syncing; trying again shortly'), { busy: true });
  if (!r.ok) throw new Error(`The start page answered ${r.status}`);
  return r.json();
}

async function badge(status) {
  const text = status.ok === false && !status.offline ? '!' : '';
  await ext.action.setBadgeText({ text });
  if (text) await ext.action.setBadgeBackgroundColor({ color: '#c0392b' });
}

async function once() {
  const { account, sync, mode } = await load(['account', 'sync', 'mode']);
  if (!account) return;
  engine = new IoSync.Sync({ bm: ext.bookmarks, state: sync || {}, http: (m, p, b) => request(account, m, p, b), log: (m) => console.warn(m) });
  let status;
  try {
    const me = await request(account, 'GET', '');
    if (me.canWrite !== account.canWrite) await save({ account: { ...account, canWrite: me.canWrite } });
    const res = await engine.run({ canWrite: me.canWrite, mode: mode || 'merge' });
    status = { at: Date.now(), ok: true, pushed: res.pushed, changed: res.changed };
  } catch (e) {
    status = { at: Date.now(), ok: false, error: e.message, offline: !!e.offline || !!e.busy, signedOut: !!e.signedOut };
  }
  // what it worked out is kept even when it stopped half way: the map of what is what must follow the browser
  await save({ sync: engine.state, status });
  engine = null;
  await badge(status);
}

/** One sync at a time; a change that arrives during one gets a sync of its own after it. */
function syncNow() {
  if (running) { again = true; return running; }
  running = once().catch((e) => console.error(e)).finally(() => {
    running = null;
    if (again) { again = false; soon(); }
  });
  return running;
}

function soon() {
  clearTimeout(timer);
  timer = setTimeout(syncNow, QUIET_MS);
}

function changedHere() {
  if (engine && engine.applying) return;  // the sync's own changes
  soon();
}
for (const ev of ['onCreated', 'onRemoved', 'onChanged', 'onMoved', 'onChildrenReordered', 'onImportEnded']) {
  if (ext.bookmarks[ev]) ext.bookmarks[ev].addListener(changedHere);
}

ext.alarms.onAlarm.addListener((a) => { if (a.name === 'sync') syncNow(); });
async function schedule() {
  if (!(await ext.alarms.get('sync'))) await ext.alarms.create('sync', { periodInMinutes: 1 });
}
ext.runtime.onInstalled.addListener(async ({ reason }) => {
  await schedule();
  if (reason === 'install') ext.runtime.openOptionsPage();
  else syncNow();
});
ext.runtime.onStartup.addListener(() => { schedule(); syncNow(); });
schedule();

ext.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg === 'sync') { syncNow().then(() => reply(true)); return true; }
  if (msg === 'signed-out') { clearTimeout(timer); ext.action.setBadgeText({ text: '' }); }
  return false;
});
