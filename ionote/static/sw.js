// Service worker: makes ionotes installable and keeps the app shell (page, scripts, styles, icons) available.
// Shell files are fetched network-first so updates land at once, with the cache as the fallback. Notes, pictures
// and the API are never cached here: they always come from the server, so nothing shown is stale.
const SHELL = 'ionotes-shell-v5';
const JS = ['theme', 'core', 'auth', 'notes', 'editor', 'settings', 'update', 'main'].map((m) => `./js/${m}.js`);
const FILES = ['./', './index.html', './app.js', ...JS, './app.css', './manifest.webmanifest', './icons/mark-64.png', './icons/favicon-32.png', './icons/icon-192.png', './icons/icon-512.png'];
self.addEventListener('install', (e) => { e.waitUntil(caches.open(SHELL).then((c) => c.addAll(FILES)).then(() => self.skipWaiting())); });
self.addEventListener('activate', (e) => { e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== SHELL).map((k) => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  const shell = url.pathname === '/' || /\/(index\.html|app\.js|js\/[^/]+\.js|app\.css|manifest\.webmanifest|icons\/[^/]+)$/.test(url.pathname);
  if (!shell) return;
  e.respondWith(fetch(e.request).then((r) => { if (r.ok) { const copy = r.clone(); caches.open(SHELL).then((c) => c.put(e.request, copy)); } return r; })
    .catch(() => caches.match(e.request, { ignoreSearch: true })));
});
