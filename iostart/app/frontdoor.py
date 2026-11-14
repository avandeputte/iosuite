"""The suite on one address: the start page answers at it and passes every other app's requests on.

    https://home.example.com/            ioStart itself
    https://home.example.com/calendar/…  ioCalendar   (its own /… on its own port)
    https://home.example.com/notes/…     ioNote       and so on: iosuite_shared.suite.FOLDERS

One name, one certificate and one port then reach the whole suite; each app keeps running on its own port, which
need not be open to anybody else (HOST=127.0.0.1). Off until a suite admin turns it on (Settings › Global settings ›
Apps › One address: one switch in the Shared ioSuite database), because it makes every app reachable wherever the
start page is; while it is off this module passes everything to ioStart untouched.

What is passed on is the request as it came: any method (CalDAV's PROPFIND and REPORT), the body as it arrives (an
upload is never held here), the answer as it is produced (a video's ranges, a live stream, MCP). The app is told where
the request came from the way a reverse proxy tells it, and believes it because the start page is on its machine
(iosuite_shared.proxyauth.Forwarded) or listed under Settings › Security:

    X-Forwarded-Prefix   /calendar: the folder, which the app puts in front of every address it writes
    X-Forwarded-For      what this request carried, then the address it really came from
    X-Forwarded-Proto    http or https, as the start page settled it; X-Forwarded-Host and Host: the name asked for
    X-IoSuite-Outside    1 when the request reached the start page from outside (proxyauth.external)

The headers a proxy names the signed-in person with (Remote-User…), and the visitor's address as Cloudflare gives it,
are taken off unless the request came from a proxy the suite trusts: the app sees this machine as the sender, and
must not take a visitor's own header for the proxy's word. Cloudflare Access's token passes as it is; every app checks its signature itself.

An app is passed on to at the address it recorded inside the network (on this machine: its loopback), never at its
public one, which may be this very address. An app that recorded none (in a container without INTERNAL_URL) has no
folder here. Phones look for a calendar or contacts account at /.well-known/caldav and /.well-known/carddav of the
name they are given: those go to ioCalendar's and ioContact's folders.

The answer comes back as the app gave it, but for a redirect to a place on this address that lost its folder
(Starlette's own trailing-slash redirect): the folder goes back in front. Websockets are not passed on (no app uses
one): asked for in an app's folder, they are refused.

A pure ASGI middleware, the first to see a request after the forwarded headers are settled (Auth.install(outer=)):
ioStart's own sign-in, body cap and routes never see what belongs to another app.
"""
import asyncio
import logging
import time
from urllib.parse import quote, urlsplit, urlunsplit

import httpx2
from iosuite_shared import prefix, proxyauth, suite

from app.auth import auth

log = logging.getLogger("iostart.frontdoor")
REFRESH_S = 5.0
# what belongs to one connection, never passed on (RFC 9110 §7.6.1)
HOP = frozenset(("connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "proxy-connection", "te", "trailer",
                 "transfer-encoding", "upgrade"))
SET_HERE = frozenset(("host", "x-forwarded-for", "x-forwarded-proto", "x-forwarded-host", "x-forwarded-prefix", "x-real-ip",
                      "forwarded", "expect", proxyauth.OUTSIDE_HEADER))  # expect: this server says "100 Continue" itself
WELL_KNOWN = {"/.well-known/caldav": "iocalendar", "/.well-known/carddav": "iocontact"}
_state = {"at": 0.0, "rev": -1, "on": False, "folders": {}, "apps": {}}
_lock = asyncio.Lock()
_client = None


def _load() -> dict:
    """{on, folders: {folder: where to pass on to}, apps: {app: folder}} from the Shared ioSuite database."""
    if not suite.one_address():
        return {"on": False, "folders": {}, "apps": {}}
    folders, apps = {}, {}
    for a in suite.apps():
        folder, up = suite.folder_of(a["app"]), suite.upstream_of(a)
        if folder and up:
            folders[folder] = up
            apps[a["app"]] = folder
    return {"on": True, "folders": folders, "apps": apps}


def _stale() -> bool:
    return time.time() - _state["at"] >= REFRESH_S or _state["rev"] != suite.door_rev()  # the switch flipped right here: at once


async def state() -> dict:
    if _stale():
        async with _lock:
            if _stale():
                rev = suite.door_rev()
                try:
                    _state.update(await asyncio.to_thread(_load))
                except Exception as e:  # noqa: BLE001 - the database is away: as it was
                    log.warning("the suite's one address: could not read the list of apps (%s)", e)
                _state.update(at=time.time(), rev=rev)
    return _state


def forget() -> None:
    """Read the switch and the list again on the next request (the switch was just flipped here; tests)."""
    _state["at"] = 0.0


def client() -> httpx2.AsyncClient:
    global _client
    if _client is None:
        # no pool limit to queue behind and no read timeout to cut a live stream; a dead app is noticed on connect.
        # trust_env off: the apps are on this network, never behind the machine's HTTP proxy
        _client = httpx2.AsyncClient(timeout=httpx2.Timeout(10, read=None, write=None, pool=None), follow_redirects=False, trust_env=False,
                                     limits=httpx2.Limits(max_connections=None, max_keepalive_connections=32))
        for h in ("accept", "accept-encoding", "user-agent"):  # the visitor's own or none: nothing asked for in their name
            _client.headers.pop(h, None)
    return _client


async def close() -> None:
    global _client
    c, _client = _client, None
    if c is not None:
        await c.aclose()


def _headers(scope: dict, folder: str, proxy) -> list:  # folder: "/calendar", with the start page's own in front
    """The request's headers as the app gets them (see the module's text)."""
    got = [(k.decode("latin-1").lower(), v.decode("latin-1")) for k, v in scope.get("headers") or []]
    named = {k: v for k, v in got}
    peer = scope.get("iothing.peer") or (scope.get("client") or ("",))[0]
    from_proxy = proxy.from_trusted(peer)
    drop = set(HOP) | SET_HERE
    for name in (named.get("connection") or "").split(","):  # what the sender tied to its own connection
        drop.add(name.strip().lower())
    if "transfer-encoding" in named:  # sent in pieces: a length beside it is not the body's (and h11 would refuse it)
        drop.add("content-length")
    if not from_proxy:  # a visitor's own word for who is signed in, or for the address Cloudflare saw, is nobody's word
        drop.update(h.lower() for h in (*proxyauth.GENERIC_HEADERS, proxyauth.CF_HEADER, *proxy.headers(), "cf-connecting-ip"))
    out = [(k, v) for k, v in got if k not in drop]
    host = named.get("host") or ""
    out.append(("host", host))
    out.append(("x-forwarded-host", (named.get("x-forwarded-host") or host).split(",")[0].strip()))
    out.append(("x-forwarded-proto", "https" if scope.get("scheme") in ("https", "wss") else "http"))
    out.append(("x-forwarded-for", ", ".join(x for x in (named.get("x-forwarded-for"), peer) if x)))
    out.append(("x-forwarded-prefix", folder))
    if proxy.external(named, peer):
        out.append((proxyauth.OUTSIDE_HEADER, "1"))
    return out


def _location(value: str, hosts: set, folder: str) -> str:
    """An app's redirect to a place on this address that lost its folder: Starlette's own trailing-slash redirect
    builds it from the request, where the folder is not the root path (iosuite_shared.prefix). The folder goes back
    in front; a redirect elsewhere, relative to the page, or already in the folder stays as it is."""
    p = urlsplit(value)
    if p.scheme or p.netloc:
        if p.netloc.lower() not in hosts:
            return value
    elif not value.startswith("/"):
        return value
    if p.path == folder or p.path.startswith(folder + "/"):
        return value
    return urlunsplit((p.scheme, p.netloc, folder + (p.path or "/"), p.query, p.fragment))


async def _plain(send, status: int, text: str, headers=()) -> None:
    body = text.encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"text/plain; charset=utf-8"), (b"content-length", str(len(body)).encode()), *headers]})
    await send({"type": "http.response.body", "body": body})


async def _redirect(send, status: int, where: str) -> None:
    await _plain(send, status, "", [(b"location", where.encode("latin-1"))])


class FrontDoor:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "websocket":
            return await self.socket(scope, receive, send)
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        st = await state()
        if not st["on"]:
            return await self.app(scope, receive, send)
        path = scope.get("path") or "/"
        query = (scope.get("query_string") or b"").decode("latin-1")
        own = scope.get(prefix.SCOPE_KEY) or ""  # the start page's own folder, when it is in one itself
        if path in WELL_KNOWN:  # a phone asking this name for its calendar or contacts account
            folder = st["apps"].get(WELL_KNOWN[path])
            if folder:
                return await _redirect(send, 301, f"{own}/{folder}/dav/")
            return await self.app(scope, receive, send)
        first, slash, _rest = path[1:].partition("/")
        upstream = st["folders"].get(first) if first else None
        if upstream is None:
            return await self.app(scope, receive, send)
        if not slash:  # /calendar: the page's relative addresses need /calendar/
            return await _redirect(send, 308, f"{own}/{first}/" + (f"?{query}" if query else ""))
        raw = (scope.get("raw_path") or b"").decode("latin-1")  # as it was sent: nothing decoded and encoded again
        raw = raw[len(first) + 1:] if raw.startswith(f"/{first}/") else quote(path[len(first) + 1:], safe="/:@!$&'()*+,;=-._~")
        await self.forward(scope, receive, send, upstream + raw + (f"?{query}" if query else ""), f"{own}/{first}")

    async def socket(self, scope, receive, send) -> None:
        """No app of the suite uses a websocket (server-sent events stream through forward): one asked for in an
        app's folder is refused here, plainly, rather than landing on the start page's own routes."""
        st = await state()
        first = (scope.get("path") or "/")[1:].partition("/")[0]
        if not st["on"] or first not in st["folders"]:
            return await self.app(scope, receive, send)
        if (await receive())["type"] == "websocket.connect":
            log.info("websocket to %s refused: the front door passes on plain requests only", scope.get("path"))
            await send({"type": "websocket.close", "code": 1008})

    async def forward(self, scope, receive, send, url: str, folder: str) -> None:
        headers = _headers(scope, folder, auth.proxy)
        gone = asyncio.Event()  # the browser went away
        sent = {k.decode("latin-1").lower(): v for k, v in scope.get("headers") or []}
        has_body = "transfer-encoding" in sent or sent.get("content-length", b"0").strip() not in (b"", b"0")
        done_reading = asyncio.Event()

        async def body():
            while True:
                m = await receive()
                if m["type"] == "http.disconnect":
                    gone.set()
                    raise ConnectionError("the client went away while sending")
                if m.get("body"):
                    yield m["body"]
                if not m.get("more_body"):
                    done_reading.set()
                    return

        if not has_body:
            done_reading.set()
        try:
            req = client().build_request(scope["method"], url, headers=headers, content=body() if has_body else None)
            resp = await client().send(req, stream=True)
        except httpx2.InvalidURL:  # a path longer than any app takes
            return await _plain(send, 414, "That address is too long.\n")
        except (httpx2.ConnectError, httpx2.ConnectTimeout) as e:
            log.info("%s is not answering at %s (%s)", folder, url.split("/", 3)[2], e)
            return await _plain(send, 502, f"The app in {folder}/ is not answering. It may be starting or updating: try again in a moment.\n")
        except (httpx2.HTTPError, ConnectionError, OSError) as e:
            if gone.is_set():
                return
            log.warning("passing %s %s on failed: %s", scope["method"], scope.get("path"), e)
            return await _plain(send, 502, f"The app in {folder}/ could not be reached.\n")

        async def watch():  # a live stream ends when the browser leaves, not when the app has something to say
            await done_reading.wait()
            while True:
                m = await receive()
                if m["type"] == "http.disconnect":
                    gone.set()
                    return

        watcher = asyncio.ensure_future(watch())
        try:
            # date and server: this server writes its own
            out = [(k.lower(), v) for k, v in resp.headers.raw if k.decode("latin-1").lower() not in HOP and k.lower() not in (b"date", b"server")]
            hosts = {sent.get(h, b"").decode("latin-1").split(",")[0].strip().lower() for h in ("host", "x-forwarded-host")} - {""}
            out = [(k, _location(v.decode("latin-1"), hosts, folder).encode("latin-1") if k == b"location" else v) for k, v in out]
            await send({"type": "http.response.start", "status": resp.status_code, "headers": out})
            chunks = resp.aiter_raw().__aiter__()
            while True:
                nxt = asyncio.ensure_future(chunks.__anext__())
                await asyncio.wait({nxt, watcher}, return_when=asyncio.FIRST_COMPLETED)
                if not nxt.done():  # the browser left first
                    nxt.cancel()
                    try:
                        await nxt
                    except (asyncio.CancelledError, StopAsyncIteration, httpx2.HTTPError, OSError):
                        pass
                    return
                try:
                    chunk = nxt.result()
                except StopAsyncIteration:
                    break
                if chunk:
                    await send({"type": "http.response.body", "body": chunk, "more_body": True})
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        except (httpx2.HTTPError, OSError) as e:  # the app went away mid-answer: the connection is cut, as it would be without us
            if not gone.is_set():
                log.info("%s stopped answering mid-way on %s: %s", folder, scope.get("path"), e)
            return  # one line, no traceback: the answer is left unfinished, so the server closes the connection
        finally:
            watcher.cancel()
            await resp.aclose()
