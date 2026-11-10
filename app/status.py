"""Is each app up, and does it have an update waiting? Is each bookmark reachable?

The start page asks every app its /api/status with the viewer's own sign-in (as app/widgets.py does for the tiles'
glimpses) and pings each bookmark's address from the server, a few at a time, and remembers the answers for a while:
a page opened ten times in a minute asks each app once. The tiles and bookmarks show a dot from it.
"""
import ipaddress
import socket
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor

from fastapi import Request

from app import apps, bookmarks, widgets

APP_TTL = 60       # seconds an app's answer is kept
LINK_TTL = 300     # seconds a bookmark's ping is kept
TIMEOUT = 3        # seconds per request
MAX_KEPT = 2000    # answers remembered at most (one per app and viewer, one per bookmark)
_cache: dict = {}  # key -> (expires, value)
_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="status")


def _remember(key, ttl, make):
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
    v = make()
    with _lock:
        _cache[key] = (now + ttl, v)
        if len(_cache) > MAX_KEPT:  # the ones that ran out first, then the ones closest to it
            for k in [k for k, (until, _) in _cache.items() if until <= now]:
                del _cache[k]
            for k in sorted(_cache, key=lambda k: _cache[k][0])[:max(0, len(_cache) - MAX_KEPT)]:
                del _cache[k]
    return v


def forget() -> None:
    with _lock:
        _cache.clear()


# ------------------------------------------------------------------ the apps

def _app(request: Request, key: str) -> dict:
    """{ok, version, update, why}: up (its /api/status answers) and, for an admin there, whether it can update."""
    try:
        s = widgets.fetch(request, key, "/api/status")
    except widgets.Unavailable as e:
        # 401/403 from the app: it is up, the viewer is just not an account there (or no session); 404: an older app
        return {"ok": e.status in (403, 404), "version": None, "update": None, "why": str(e)}
    if not isinstance(s, dict):
        return {"ok": False, "version": None, "update": None, "why": f"{key} did not answer with its status"}
    upd = s.get("update")  # the suite's status shape: {version, remote, message, date} for an admin there, else null
    if isinstance(upd, dict):
        upd = upd.get("version") or upd.get("remote") or True
    elif upd is not None and not isinstance(upd, (str, bool)):
        upd = bool(upd)
    return {"ok": True, "version": s.get("version"), "update": upd or None, "why": None}


def of_apps(request: Request) -> dict:
    """{key: {ok, version, update}} for every app on the page, asked in parallel; cached per viewer for APP_TTL."""
    host = widgets._host(request)
    tok = request.cookies.get(widgets.sessions.COOKIE) or request.headers.get("authorization") or ""
    keys = [t["key"] for t in apps.tiles(host, getattr(request.state, "user", None))]

    def ask(key):
        return key, _remember(("app", key, tok[:24], host), APP_TTL, lambda: _app(request, key))
    return dict(_pool.map(ask, keys))


# ------------------------------------------------------------------ the bookmarks

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # a 3xx is an answer: the server is up; never follow it (not to a host the editor did not name)


_opener = urllib.request.build_opener(_NoRedirect)


def pingable(href: str) -> bool:
    """A bookmark the server may ping: http(s), to a named host that is not this server itself or a link-local address
    (the cloud metadata services live there). Home-network addresses are what bookmarks are for, so they are fine."""
    try:
        u = urlsplit(href)
        host = u.hostname
    except ValueError:
        return False
    if u.scheme not in ("http", "https") or not host:
        return False
    try:
        addrs = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addrs = [ipaddress.ip_address(a[4][0]) for a in socket.getaddrinfo(host, u.port or 0, proto=socket.IPPROTO_TCP)]
        except (socket.gaierror, OSError, ValueError):
            return True  # unknown name: the ping fails on its own
    return not any(a.is_loopback or a.is_link_local or a.is_unspecified for a in addrs)


def _ping(href: str) -> dict:
    """{ok, status}: HEAD (GET when the server dislikes HEAD); a 3xx or 4xx is "up" (it answered), a 5xx or no answer is
    not. Redirects are not followed, and nothing of the answer but its status is read."""
    if not href.startswith(("http://", "https://")):
        return {"ok": None, "status": None}  # nothing to ping (a mailto:, a file share…)
    if not pingable(href):
        return {"ok": None, "status": None}
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(href, method=method, headers={"User-Agent": widgets.UA, "Accept": "*/*"})
        try:
            with _opener.open(req, timeout=TIMEOUT) as r:  # noqa: S310 - an address a bookmark editor saved, checked above
                return {"ok": True, "status": r.status}
        except urllib.error.HTTPError as e:
            if e.code in (405, 501) and method == "HEAD":
                continue
            return {"ok": e.code < 500, "status": e.code}
        except (urllib.error.URLError, OSError, ValueError):
            return {"ok": False, "status": None}
    return {"ok": False, "status": None}


def of_bookmarks() -> dict:
    """{link id: {ok, status}} for every bookmark, pinged in parallel; cached per address for LINK_TTL."""
    links = [(l["id"], l["href"]) for g in bookmarks.groups() for l in g["links"]]

    def ask(item):
        lid, href = item
        return str(lid), _remember(("link", href), LINK_TTL, lambda: _ping(href))
    return dict(_pool.map(ask, links))



