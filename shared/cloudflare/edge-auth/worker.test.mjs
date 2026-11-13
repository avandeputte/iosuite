// node --test cloudflare/edge-auth/worker.test.mjs  (Node 18+: crypto.subtle, Response and atob are built in)
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import worker from "./worker.js";

const PW = "ical-3fa91c02-Xx_9aBcDeFgHiJkLmNoPqRsTu";
const HPW = "iohealth-0a1b2c3d-Yy_9aBcDeFgHiJkLmNoPqRsTu";
const sha = (s) => createHash("sha256").update(s).digest("hex");
const kv = new Map([["iocalendar:3fa91c02", JSON.stringify({ h: sha(PW) })], ["iohealth:0a1b2c3d", JSON.stringify({ h: sha(HPW) })]]);
const env = (mode) => ({
  MODE: mode, APPS: '{"calendar.example.com": "iocalendar", "health.example.com": "iohealth"}',
  APP_PASSWORDS: { get: async (k) => (kv.has(k) ? JSON.parse(kv.get(k)) : null) },
});
let forwarded = 0;
globalThis.fetch = async () => { forwarded++; return new Response("origin", { status: 207 }); };
const req = (path, pw, host = "calendar.example.com") => new Request(`https://${host}${path}`, {
  method: "PROPFIND", headers: pw === undefined ? {} : { Authorization: "Basic " + btoa(`alex:${pw}`) } });

test("a known app password goes on", async () => {
  forwarded = 0;
  assert.equal((await worker.fetch(req("/dav/calendars/", PW), env("enforce"))).status, 207);
  assert.equal(forwarded, 1);
});

test("enforce: wrong, unknown, account passwords and no credentials stop at the edge", async () => {
  forwarded = 0;
  for (const pw of [PW + "x", "ical-00000000-whatever", "hunter2", undefined]) {
    const r = await worker.fetch(req("/dav/calendars/", pw), env("enforce"));
    assert.equal(r.status, 401);
    assert.match(r.headers.get("WWW-Authenticate"), /realm="ioCalendar"/);
  }
  assert.equal((await worker.fetch(req("/dav/", PW, "other.example.com"), env("enforce"))).status, 401);
  assert.equal(forwarded, 0);
});

test("monitor lets failures through but answers a request with no credentials", async () => {
  forwarded = 0;
  assert.equal((await worker.fetch(req("/dav/", "hunter2"), env("monitor"))).status, 207);
  assert.equal((await worker.fetch(req("/dav/", undefined), env(undefined))).status, 401);
  assert.equal(forwarded, 1);
});

test("paths outside /dav are not checked", async () => {
  forwarded = 0;
  assert.equal((await worker.fetch(req("/davx", undefined), env("enforce"))).status, 207);
  assert.equal((await worker.fetch(req("/api/events", undefined), env("enforce"))).status, 207);
  assert.equal(forwarded, 2);
});

const hreq = (path, auth, method = "POST") => new Request(`https://health.example.com${path}`, {
  method, headers: auth ? { Authorization: auth } : {} });

test("ioHealth: /v1/ uploads need a known app password, Basic or Bearer; /v1/health stays open", async () => {
  forwarded = 0;
  assert.equal((await worker.fetch(hreq("/v1/sessions", "Basic " + btoa(`alex:${HPW}`)), env("enforce"))).status, 207);
  assert.equal((await worker.fetch(hreq("/v1/sessions/4/items", "Bearer " + HPW), env("enforce"))).status, 207);
  assert.equal((await worker.fetch(hreq("/v1/health", null, "GET"), env("enforce"))).status, 207);
  assert.equal(forwarded, 3);
  const r = await worker.fetch(hreq("/v1/sessions", "Basic " + btoa("alex:hunter2")), env("enforce"));
  assert.equal(r.status, 401);
  assert.match(r.headers.get("WWW-Authenticate"), /realm="ioHealth"/);
  assert.equal((await worker.fetch(hreq("/v1/sessions", "Bearer iohealth-0a1b2c3d-wrong"), env("enforce"))).status, 401);
  assert.equal((await worker.fetch(hreq("/v1/sessions", null), env("enforce"))).status, 401);
  assert.equal(forwarded, 3);
  assert.equal((await worker.fetch(hreq("/api/today", null, "GET"), env("enforce"))).status, 207); // the web app: not ours
  assert.equal((await worker.fetch(new Request("https://health.example.com/dav/"), env("enforce"))).status, 207);
});

test("the start page's bookmark sync: /dav is guarded, the Nextcloud sign-in flow before a password exists is not", async () => {
  const SPW = "iosuite-9f8e7d6c-Zz_9aBcDeFgHiJkLmNoPqRsTu";
  kv.set("iosuite:9f8e7d6c", JSON.stringify({ h: sha(SPW) }));
  const e = (mode) => ({ ...env(mode), APPS: '{"start.example.com": "iosuite"}' });
  const sreq = (path, pw, method = "GET") => new Request(`https://start.example.com${path}`, {
    method, headers: pw ? { Authorization: "Basic " + btoa(`alex:${pw}`) } : {} });
  const NC = "/dav/nextcloud/index.php/apps/bookmarks/public/rest/v2";
  forwarded = 0;
  assert.equal((await worker.fetch(sreq(`${NC}/folder/-1/children?layers=-1`, SPW), e("enforce"))).status, 207);
  assert.equal((await worker.fetch(sreq("/dav/bookmarks/bookmarks.xbel", SPW, "PROPFIND"), e("enforce"))).status, 207);
  assert.equal(forwarded, 2);
  for (const pw of [SPW + "x", "hunter2", null]) {
    const r = await worker.fetch(sreq(`${NC}/bookmark`, pw, "POST"), e("enforce"));
    assert.equal(r.status, 401);
    assert.match(r.headers.get("WWW-Authenticate"), /realm="ioSuite bookmarks"/);
  }
  assert.equal((await worker.fetch(sreq("/dav/nextcloud/ocs/v2.php/cloud/capabilities", null), e("monitor"))).status, 401);
  assert.equal(forwarded, 2);
  // no password yet: the app asks what this is, starts the flow and polls; the browser opens the page and says yes
  for (const [path, method] of [["/dav/nextcloud/status.php", "GET"], ["/dav/nextcloud/index.php/login/v2", "POST"],
    ["/dav/nextcloud/index.php/login/v2/poll", "POST"], ["/dav/nextcloud/index.php/login/v2/flow/abc", "GET"], ["/dav/nextcloud/index.php/login/v2/grant", "POST"]]) {
    assert.equal((await worker.fetch(sreq(path, null, method), e("enforce"))).status, 207, path);
  }
  assert.equal(forwarded, 7);
  assert.equal((await worker.fetch(sreq("/dav/nextcloud/index.php/login/v20", null, "POST"), e("enforce"))).status, 401);
  assert.equal((await worker.fetch(sreq("/api/bookmarks", null), e("enforce"))).status, 207); // the web app: not ours
});
