/* Two-way sync against a running start page: browsers (in memory, fake.js) driven by the extension's own sync
 * engine. Run by tests/test_bookmark_extension.py, or by hand:
 *   SERVER=http://127.0.0.1:8630 SYNC_USER=alex SYNC_PASSWORD=<an app password> node tests/extension/e2e.js
 * It starts from the server's bookmarks as they are and expects them empty. */
'use strict';
const assert = require('node:assert/strict');
const { Sync } = require('../../static/extension/sync.js');
const { FakeBookmarks } = require('./fake.js');

const { SERVER, SYNC_USER, SYNC_PASSWORD } = process.env;
const AUTH = 'Basic ' + Buffer.from(`${SYNC_USER}:${SYNC_PASSWORD}`).toString('base64');
let requests = [];

async function call(method, url, body) {
  const r = await fetch(SERVER + url, { method, headers: { Authorization: AUTH, ...(body ? { 'Content-Type': 'application/json' } : {}) }, body: body ? JSON.stringify(body) : undefined });
  if (!r.ok) throw new Error(`${method} ${url}: ${r.status} ${await r.text()}`);
  return r.json();
}
const http = (method, path, body) => { requests.push(`${method} ${path}`); return call(method, '/dav/ext' + path, body); };
const nc = (method, path, body) => call(method, '/dav/nextcloud/index.php/apps/bookmarks/public/rest/v2' + path, body);  // "the server changed": what another app, or the start page, does

function browser(kind) {
  const bm = new FakeBookmarks(kind);
  const sync = new Sync({ bm, http, state: {} });
  const ids = kind !== 'firefox' ? { bar: '1', other: '2' } : { bar: 'toolbar_____', other: 'unfiled_____', menu: 'menu________' };
  return { bm, sync, ...ids, run: (o) => sync.run(o), state: () => JSON.parse(JSON.stringify(sync.state)) };
}
const find = (b, title) => Object.values(b.bm.nodes).find((n) => n.title === title);
const serverTree = async () => {
  const f = (l) => l.map((n) => (n.folder ? `${n.title}[${f(n.children)}]` : n.title)).join(',');
  return f((await http('GET', '/tree')).tree);
};
const serverId = async (title) => {
  const walk = (l) => { for (const n of l) { if (n.title === title) return n.id; const x = n.folder && walk(n.children); if (x) return x; } return null; };
  return walk((await http('GET', '/tree')).tree);
};

(async () => {
  assert.equal(await serverTree(), '', 'the test starts from no bookmarks');

  // ---- a first browser brings its bookmarks
  const A = browser('chrome');
  await A.bm.create({ parentId: A.bar, title: 'News', url: 'https://news.example/' });
  const dev = await A.bm.create({ parentId: A.bar, title: 'Dev' });
  await A.bm.create({ parentId: dev.id, title: 'Docs', url: 'https://docs.example/' });
  const rec = await A.bm.create({ parentId: A.other, title: 'Recipes' });
  await A.bm.create({ parentId: rec.id, title: 'Bread', url: 'https://bread.example/' });
  A.bm.calls = 0;
  await A.run();
  assert.equal(await serverTree(), 'Bookmarks bar[News,Dev[Docs]],Recipes[Bread]');
  assert.equal(A.bm.calls, 0, 'nothing in the browser needed changing');

  // ---- nothing changed anywhere: one small request, nothing touched
  requests = [];
  assert.deepEqual(await A.run(), { changed: false, pushed: 0 });
  assert.deepEqual(requests, ['GET /rev']);

  // ---- a second browser (Firefox, with what it ships with) joins: both sides merge
  const B = browser('firefox');
  await B.bm.create({ parentId: B.bar, title: 'Get Help', url: 'https://support.example/' });
  await B.bm.create({ parentId: B.bar, type: 'separator' });
  await B.bm.create({ parentId: B.menu, title: 'Mozilla', url: 'https://mozilla.example/' });
  await B.bm.create({ parentId: B.other, title: 'Recipes' });  // the same folder exists already: matched by name, not doubled
  await B.run();
  assert.equal(await serverTree(), 'Bookmarks bar[News,Dev[Docs],Get Help],Recipes[Bread],Bookmarks menu[Mozilla]');
  assert.equal(B.bm.show(B.bar), 'News,Dev[Docs],Get Help,---');
  assert.equal(B.bm.show(B.menu), 'Mozilla');
  assert.equal(B.bm.show(B.other), 'Recipes[Bread]');
  await A.run();
  assert.equal(A.bm.show(A.bar), 'News,Dev[Docs],Get Help');
  assert.equal(A.bm.show(A.other), 'Recipes[Bread],Bookmarks menu[Mozilla]');  // Chrome has no bookmarks menu: a folder

  // ---- a delete on the server reaches every browser
  await nc('DELETE', `/bookmark/${await serverId('News')}`);
  await A.run(); await B.run();
  assert.equal(A.bm.show(A.bar), 'Dev[Docs],Get Help');
  assert.equal(B.bm.show(B.bar), 'Dev[Docs],Get Help,---');
  await nc('DELETE', `/folder/${await serverId('Recipes')}`);  // a folder with what is in it
  await A.run(); await B.run();
  assert.equal(A.bm.show(A.other), 'Bookmarks menu[Mozilla]');
  assert.equal(B.bm.show(B.other), '');
  assert.equal(await serverTree(), 'Bookmarks bar[Dev[Docs],Get Help],Bookmarks menu[Mozilla]');

  // ---- a delete in one browser reaches the server and the other browser
  await A.bm.removeTree(find(A, 'Dev').id);
  await A.run(); await B.run();
  assert.equal(await serverTree(), 'Bookmarks bar[Get Help],Bookmarks menu[Mozilla]');
  assert.equal(B.bm.show(B.bar), 'Get Help,---');

  // ---- made, renamed, re-addressed, moved and reordered in one browser
  await B.bm.create({ parentId: B.bar, index: 0, title: 'Mail', url: 'https://mail.example/' });
  const tools = await B.bm.create({ parentId: B.other, title: 'Tools' });
  await B.bm.create({ parentId: tools.id, title: 'Timer', url: 'https://timer.example/' });
  await B.bm.update(find(B, 'Get Help').id, { title: 'Help', url: 'https://help.example/' });
  await B.bm.move(find(B, 'Mozilla').id, { parentId: tools.id, index: 0 });
  await B.run(); await A.run();
  assert.equal(await serverTree(), 'Bookmarks bar[Mail,Help],Bookmarks menu[],Tools[Mozilla,Timer]');
  assert.equal(A.bm.show(A.bar), 'Mail,Help');
  assert.equal(A.bm.show(A.other), 'Bookmarks menu[],Tools[Mozilla,Timer]');
  assert.equal(find(A, 'Help').url, 'https://help.example/');
  await A.bm.move(find(A, 'Help').id, { parentId: A.bar, index: 0 });  // reorder
  await A.bm.move(find(A, 'Timer').id, { parentId: A.bar });           // out of a folder, to the bar
  await A.run(); await B.run();
  assert.equal(await serverTree(), 'Bookmarks bar[Help,Mail,Timer],Bookmarks menu[],Tools[Mozilla]');
  assert.equal(B.bm.show(B.bar), 'Help,Mail,Timer,---');
  assert.equal(B.bm.show(B.other), 'Tools[Mozilla]');

  // ---- what the start page makes at the top (a group) is in Other bookmarks everywhere; a change there arrives
  const work = (await nc('POST', '/folder', { parent_folder: -1, title: 'Work' })).item;
  await nc('POST', '/bookmark', { url: 'https://wiki.example/', title: 'Wiki', folders: [work.id] });
  await nc('PUT', `/bookmark/${await serverId('Mail')}`, { title: 'Webmail' });
  await A.run(); await B.run();
  for (const X of [A, B]) assert.ok(X.bm.show(X.other).endsWith('Work[Wiki]'), X.bm.show(X.other));
  assert.equal(A.bm.show(A.bar), 'Help,Webmail,Timer');

  // ---- both changed while apart: both changes are kept
  await A.bm.create({ parentId: find(A, 'Work').id, title: 'From A', url: 'https://a.example/' });
  await B.bm.create({ parentId: find(B, 'Work').id, title: 'From B', url: 'https://b.example/' });
  await B.bm.remove(find(B, 'Timer').id);
  await A.run(); await B.run(); await A.run();
  assert.equal(A.bm.show(A.bar), 'Help,Webmail');
  assert.equal(A.bm.show(A.other), B.bm.show(B.other).replace('Tools[Mozilla],', 'Bookmarks menu[],Tools[Mozilla],'));
  assert.ok(A.bm.show(A.other).includes('Work[Wiki,From A,From B]'), A.bm.show(A.other));

  // ---- deleted here, but changed on the server meanwhile: it comes back rather than being lost
  await nc('PUT', `/bookmark/${await serverId('Wiki')}`, { title: 'Wiki (new address)', url: 'https://wiki2.example/' });
  await A.bm.remove(find(A, 'Wiki').id);
  await A.run();
  assert.ok(A.bm.show(A.other).includes('Wiki (new address)'), A.bm.show(A.other));

  // ---- a browser's own state survives being stored and read back (the extension keeps it in storage)
  const A2 = { bm: A.bm, sync: new Sync({ bm: A.bm, http, state: A.state() }) };
  requests = [];
  assert.deepEqual(await A2.sync.run(), { changed: false, pushed: 0 });
  assert.deepEqual(requests, ['GET /rev']);

  // ---- a new browser that takes the server's bookmarks: what only it had goes
  const C = browser('chrome');
  await C.bm.create({ parentId: C.bar, title: 'Junk', url: 'https://junk.example/' });
  const imp = await C.bm.create({ parentId: C.other, title: 'Imported' });
  await C.bm.create({ parentId: imp.id, title: 'Old', url: 'https://old.example/' });
  const before = await serverTree();
  await C.run({ mode: 'server' });
  assert.equal(await serverTree(), before);
  assert.equal(C.bm.show(C.bar), A.bm.show(A.bar));
  assert.equal(C.bm.show(C.other), A.bm.show(A.other));

  // ---- an account that may only read: the browser follows the server, and sends nothing
  await C.bm.create({ parentId: C.bar, title: 'Mine', url: 'https://mine.example/' });
  requests = [];
  await C.run({ canWrite: false });
  assert.ok(!requests.some((r) => r.startsWith('POST')), requests.join());
  assert.equal(await serverTree(), before);

  // ---- Vivaldi: one tree; the folder set as its bookmark bar is the bar, the rest is "Other bookmarks"; its Trash is a delete
  const V = browser('vivaldi');
  const sd = await V.bm.create({ parentId: '1', title: 'Speed Dial' }); V.bm.flag(sd.id, 'speeddial');
  await V.bm.create({ parentId: sd.id, title: 'Vivaldi', url: 'https://vivaldi.example/' });
  const vb = await V.bm.create({ parentId: '1', title: 'My bar' }); V.bm.flag(vb.id, 'bookmarkbar');
  await V.bm.create({ parentId: vb.id, title: 'Help', url: 'https://help.example/' });  // on the server's bar already
  await V.bm.create({ parentId: '2', title: 'Unseen', url: 'https://unseen.example/' });  // Vivaldi does not show this folder: left alone
  await V.run(); await A.run();
  assert.equal(V.bm.show(vb.id), A.bm.show(A.bar));
  assert.ok(V.bm.show('1').startsWith('My bar['), V.bm.show('1'));
  assert.equal(V.bm.show('1').replace(/^My bar\[[^\]]*\],/, ''), A.bm.show(A.other));
  assert.ok(A.bm.show(A.other).endsWith('Speed Dial[Vivaldi]') && !(await serverTree()).includes('My bar') && !(await serverTree()).includes('Unseen'));
  await V.bm.move(find(V, 'Vivaldi').id, { parentId: '4' });  // deleted in Vivaldi: to its Trash
  await V.bm.create({ parentId: vb.id, title: 'Search', url: 'https://search.example/' });
  await V.run(); await A.run();
  assert.ok(A.bm.show(A.other).endsWith('Speed Dial[]') && A.bm.show(A.bar).endsWith(',Search'));
  await nc('DELETE', `/bookmark/${await serverId('Search')}`);
  await V.run();
  assert.equal(V.bm.show(vb.id), A.bm.show(A.bar).replace(',Search', ''));
  assert.equal(V.bm.show('4'), 'Vivaldi');
  V.bm.calls = 0;
  assert.deepEqual(await V.run(), { changed: false, pushed: 0 });
  assert.equal(V.bm.calls, 0);
  const W = browser('vivaldi');  // no bookmark bar folder yet: "Bookmarks bar" is made, first in the tree
  await W.run({ mode: 'server' });
  assert.equal(W.bm.show('1'), V.bm.show('1').replace('My bar[', 'Bookmarks bar['));

  // ---- a Vivaldi that synced with the first version of the extension (which lined it up as Chrome: the bar's links
  // loose in its tree, the rest in the folder Vivaldi does not show): the new line-up starts over, and deletes nothing
  const U = browser('vivaldi');
  const plain = U.sync;
  const { Sync: S } = require('../../static/extension/sync.js');
  const asChrome = { getTree: async () => { const [t] = await U.bm.getTree(); const strip = (n) => { delete n.trash; delete n.speeddial; delete n.bookmarkbar; (n.children || []).forEach(strip); return n; }; t.children = t.children.filter((c) => c.id !== '4'); return [strip(t)]; } };
  for (const m of ['get', 'getChildren', 'create', 'update', 'move', 'remove', 'removeTree']) asChrome[m] = (...a) => U.bm[m](...a);
  const old = new S({ bm: asChrome, http, state: {} });
  await A.run(); await old.run({ mode: 'server' });
  assert.equal(U.bm.show('1'), A.bm.show(A.bar));       // as 1.0.0 left it: the bar's links at the top of the tree
  assert.equal(U.bm.show('2'), A.bm.show(A.other));     // and everything else where Vivaldi does not show it
  const kept = await serverTree();
  plain.state = JSON.parse(JSON.stringify(old.state));
  await U.run();
  assert.equal(await serverTree(), kept, 'nothing was deleted, moved or doubled on the server');
  assert.equal(U.bm.show('1'), V.bm.show('1').replace('My bar[', 'Bookmarks bar['));
  assert.equal(U.bm.show('2'), '');
  assert.equal(find(U, 'Bookmarks bar').bookmarkbar, true);
  assert.deepEqual(await U.run(), { changed: false, pushed: 0 });

  // ---- every browser ends the same, and a last round changes nothing
  await A.run(); await B.run();
  for (const X of [A, B]) { X.bm.calls = 0; assert.deepEqual(await X.run(), { changed: false, pushed: 0 }); assert.equal(X.bm.calls, 0); }
  assert.equal(B.bm.show(B.bar), A.bm.show(A.bar) + ',---');
  console.log('ok: ' + await serverTree());
})().catch((e) => { console.error(e); process.exit(1); });
