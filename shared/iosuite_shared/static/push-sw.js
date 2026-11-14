/* The suite's notifications service worker (iosuite_shared.push), served at /api/auth/push/sw.js in every app and
   registered with that folder as its scope. It only shows what the server pushes and opens the app a notification
   is about when it is tapped: no fetch handler, no cache, so it never stands between the app and its pages. */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('push', (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch { d = { body: e.data ? e.data.text() : '' }; }
  const opts = { body: d.body || '', data: { url: d.url || null } };
  if (d.tag) { opts.tag = d.tag; opts.renotify = true; }
  e.waitUntil(self.registration.showNotification(d.title || 'ioSuite', opts));
});

self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const target = new URL((e.notification.data && e.notification.data.url) || '/', self.location.origin).href;
  e.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    const same = wins.find((w) => w.url.split('#')[0] === target.split('#')[0]);
    if (same) {
      try { if (same.url !== target && 'navigate' in same) await same.navigate(target); } catch { /* another origin's window */ }
      return same.focus();
    }
    return self.clients.openWindow(target);
  })());
});

// The push service replaced the subscription (it expired, or the browser renewed it): keep the new one.
self.addEventListener('pushsubscriptionchange', (e) => {
  e.waitUntil((async () => {
    const api = new URL('./', self.location.href);   // .../api/auth/push/
    const info = await (await fetch(api.href.replace(/\/$/, ''), { credentials: 'include' })).json();
    const key = Uint8Array.from(atob(info.key.replace(/-/g, '+').replace(/_/g, '/')), (c) => c.charCodeAt(0));
    const sub = e.newSubscription || await self.registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
    await fetch(new URL('devices', api).href, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subscription: sub.toJSON() }) });
  })().catch(() => {}));
});
