// Service worker: makes ionote installable and keeps the app shell (page, scripts, styles, icons) available.
// Shell files are fetched network-first so updates land at once, with the cache as the fallback. Notes, pictures
// and the API are never cached here: they always come from the server, so nothing shown is stale.
const SHELL = 'ionote-shell-v14';
const JS = ['theme', 'core', 'auth', 'markdown', 'notes', 'editor', 'templates', 'settings', 'suite', 'main'].map((m) => `./static/js/${m}.js`);
const FILES = ['./', './static/app.js', ...JS, './static/app.css', './manifest.webmanifest', './static/icons/mark.svg', './static/icons/icon-192.png', './static/icons/icon-512.png'];
self.addEventListener('install', (e) => { e.waitUntil(caches.open(SHELL).then((c) => c.addAll(FILES)).then(() => self.skipWaiting())); });
self.addEventListener('activate', (e) => { e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== SHELL).map((k) => caches.delete(k)))).then(() => self.clients.claim())); });
const ROOT = new URL('./', location.href).pathname;  // where the app is served: / or, behind one address for the whole suite, its own folder (/notes/)
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  const shell = url.pathname === ROOT || url.pathname === ROOT + 'manifest.webmanifest' || url.pathname.startsWith(ROOT + 'static/');
  if (!shell) return;
  e.respondWith(fetch(e.request).then((r) => { if (r.ok) { const copy = r.clone(); caches.open(SHELL).then((c) => c.put(e.request, copy)); } return r; })
    .catch(() => caches.match(e.request, { ignoreSearch: true })));
});
