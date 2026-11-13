"""A bookmark's icon by default: the site's own, as a browser finds it.

The server asks the bookmarked page for its <link rel="icon"> (and the apple-touch-icon), takes the best of them, and
falls back to /favicon.ico. What it finds is kept in the database per site (scheme, host and port: the links of one
site share an icon) and served by the start page itself, so a viewer's browser never asks the bookmarked sites
anything. A link's own icon (one uploaded for it, or its icon field) always wins; see app/bookmarks.py.

The fetching happens off the request, a few sites at a time: a listing names the sites it has no answer for, and the
page asks again a moment later. An icon is looked for again after REFRESH; a site that had none, after RETRY (the one
it had is kept when a later look fails).
"""
import base64
import hashlib
import logging
import queue
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import unquote_to_bytes, urljoin, urlsplit

from iosuite_shared import outbound

from app import config, db

log = logging.getLogger("iostart.siteicons")

REFRESH = timedelta(days=30)   # an icon that was found is looked for again after this
RETRY = timedelta(days=1)      # a site without one is asked again after this
TIMEOUT = 6                    # seconds per request
PAGE_MAX = 512 * 1024          # of the page's HTML: the icons are named in its <head>
ICON_MAX = 512 * 1024
WORKERS = 3
TRIES = 4                      # icons named by the page that are tried, best first
UA = "Mozilla/5.0 (compatible; ioStart page; bookmark icon)"


def _allowed(ip) -> bool:
    """Any host but this server itself and the link-local addresses, as for the bookmark pings (app/status.py): the
    home network is what many bookmarks are for."""
    return outbound.not_this_machine(ip)


_opener = outbound.opener(_allowed, redirects=True)  # each hop checked like the first, http(s) only


def site(url: str) -> str | None:
    """The site an address belongs to ("https://example.org", the port kept when it is not the usual one), or None for
    an address that has no icon to fetch (not http(s))."""
    try:
        u = urlsplit(url or "")
        host, port = u.hostname, u.port
    except ValueError:
        return None
    if u.scheme not in ("http", "https") or not host:
        return None
    s = f"{u.scheme}://{host}" + (f":{port}" if port and port != (443 if u.scheme == "https" else 80) else "")
    return s if len(s) <= 255 else None


# ------------------------------------------------------------------ what an icon is

def _svg(data: bytes) -> bytes | None:
    from app import bookmarks  # the same rules as an uploaded SVG
    try:
        return bookmarks.clean_svg(data).encode("utf-8")
    except bookmarks.BadBookmark:
        return None


def image(data: bytes) -> tuple[bytes, str] | None:
    """(the bytes to keep, their type) when this is an image a browser shows in an <img>, else None. The type comes
    from the bytes, never from what the site says they are."""
    if not data or len(data) > ICON_MAX:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return data, "image/png"
    if data[:4] in (b"\x00\x00\x01\x00", b"\x00\x00\x02\x00") and len(data) > 22:
        return data, "image/x-icon"
    if data[:3] == b"\xff\xd8\xff":
        return data, "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return data, "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return data, "image/webp"
    if b"<svg" in data[:4096]:
        svg = _svg(data)
        return (svg, "image/svg+xml") if svg else None
    return None


class _Links(HTMLParser):
    """The <link rel="icon" ...> of a page (and its <base href>)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found, self.base = [], None

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "base" and a.get("href") and self.base is None:
            self.base = a["href"]
        if tag != "link" or not a.get("href"):
            return
        rel = set(a.get("rel", "").lower().split())
        if "mask-icon" in rel or not rel & {"icon", "apple-touch-icon", "apple-touch-icon-precomposed"}:
            return
        self.found.append((_score(rel, a), a["href"].strip()))


def _score(rel: set, a: dict) -> int:
    """How good an icon is for a small square on the page: an SVG, then the one closest above 64 px, an
    apple-touch-icon (180 px when it does not say), a plain icon last (16 px, usually)."""
    href, sizes = a["href"].lower(), a.get("sizes", "").lower()
    if "svg" in a.get("type", "").lower() or href.split("?")[0].endswith(".svg") or sizes == "any":
        return 1000
    px = max([int(m) for m in re.findall(r"(\d+)x\d+", sizes)] or [180 if "icon" not in rel else 16])
    return 900 - (px - 64) // 8 if px >= 64 else px


def candidates(html: str, page: str) -> list[str]:
    """The addresses of the icons a page names, best first."""
    p = _Links()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001 - a page that is not HTML: what was found until then
        pass
    try:
        base = urljoin(page, p.base) if p.base else page
        out = []
        for _, href in sorted(p.found, key=lambda f: -f[0]):
            u = href if href.startswith("data:") else urljoin(base, href)
            if u not in out:
                out.append(u)
        return out
    except ValueError:
        return []


# ------------------------------------------------------------------ fetching

def _get(url: str, limit: int, accept: str) -> tuple[bytes, str]:
    """(the body up to `limit` bytes, the address it came from after redirects). An error page is read too: a site
    behind a sign-in still names its icon. Raises OSError / ValueError for no answer."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Encoding": "identity"})
    try:
        with _opener.open(req, timeout=TIMEOUT) as r:  # noqa: S310 - a bookmark an editor saved, checked as it connects
            return r.read(limit + 1), r.geturl()
    except urllib.error.HTTPError as e:
        try:
            return e.read(limit + 1), e.geturl() or url
        finally:
            e.close()
    except outbound.Invalid as e:
        raise ValueError(str(e)) from e


def _data(url: str) -> bytes | None:
    """The bytes of a data: address (some pages carry their icon inline)."""
    head, _, body = url[5:].partition(",")
    try:
        return base64.b64decode(body + "=" * (-len(body) % 4)) if head.endswith(";base64") else unquote_to_bytes(body)
    except ValueError:
        return None


def _icon(url: str) -> tuple[bytes, str] | None:
    if url.startswith("data:"):
        return image(_data(url) or b"")
    try:
        return image(_get(url, ICON_MAX, "image/*,*/*;q=0.5")[0])
    except (OSError, ValueError):
        return None


def find(url: str) -> tuple[bytes, str] | None:
    """The icon of the site this address is on: the best one its page names, else /favicon.ico; None when there is
    none (or nothing answers)."""
    tried, where = [], url
    try:
        body, where = _get(url, PAGE_MAX, "text/html,*/*;q=0.5")
        for c in candidates(body[:PAGE_MAX].decode("utf-8", "replace"), where)[:TRIES]:
            tried.append(c)
            got = _icon(c)
            if got:
                return got
    except (OSError, ValueError):
        pass
    for root in dict.fromkeys(s for s in (site(where), site(url)) if s):
        if root + "/favicon.ico" not in tried:
            got = _icon(root + "/favicon.ico")
            if got:
                return got
    return None


# ------------------------------------------------------------------ the store

def keep(s: str, found: tuple[bytes, str] | None) -> None:
    """Record a look: the icon, or that there was none (an earlier icon stays)."""
    if found:
        data, mime = found
        db.ex("INSERT INTO prt_site_icons (site, data, mime, etag, fetched_at) VALUES (%s, %s, %s, %s, UTC_TIMESTAMP()) "
              "ON DUPLICATE KEY UPDATE data = VALUES(data), mime = VALUES(mime), etag = VALUES(etag), fetched_at = VALUES(fetched_at)",
              (s, data, mime, hashlib.sha256(data).hexdigest()[:16]))
    else:
        db.ex("INSERT INTO prt_site_icons (site, fetched_at) VALUES (%s, UTC_TIMESTAMP()) ON DUPLICATE KEY UPDATE fetched_at = VALUES(fetched_at)", (s,))


def known() -> dict:
    """{site: {etag (None: no icon), due (time for another look)}} of every site looked at."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return {r["site"]: {"etag": r["etag"], "due": now - r["fetched_at"] > (REFRESH if r["etag"] else RETRY)}
            for r in db.q("SELECT site, etag, fetched_at FROM prt_site_icons")}


def get(s: str) -> dict | None:
    """{data, mime, etag} of a site's icon, or None."""
    return db.one("SELECT data, mime, etag FROM prt_site_icons WHERE site = %s AND data IS NOT NULL", (s,))


def of(url: str, have: dict | None = None) -> dict:
    """For a link without an icon of its own: {siteIcon: where the page gets the site's icon ('' when it has none),
    iconPending: True while the first look is still to come}. Asks for the look when it is due. `have` is known(),
    when the caller reads many links."""
    s = site(url)
    if not s:
        return {"siteIcon": "", "iconPending": False}
    if have is None:
        have = known()
    k = have.get(s)
    asked = (not k or k["due"]) and config.SITE_ICONS
    if asked:
        want(s, url)
    return {"siteIcon": f"api/bookmarks/site-icon?site={urllib.parse.quote(s, safe='')}&v={k['etag']}" if k and k["etag"] else "",
            "iconPending": asked and k is None}


def forget(s: str) -> None:
    """Look again the next time the site's icon is wanted."""
    db.ex("DELETE FROM prt_site_icons WHERE site = %s", (s,))


# ------------------------------------------------------------------ the workers

_todo: queue.Queue = queue.Queue()
_queued: set = set()
_lock = threading.Lock()
_threads: list = []


def want(s: str, url: str) -> None:
    """Queue a look at a site's icon (once per site while it waits); the first link seen names the page asked."""
    with _lock:
        if s in _queued:
            return
        _queued.add(s)
        while len(_threads) < WORKERS:
            t = threading.Thread(target=_work, name=f"siteicons-{len(_threads)}", daemon=True)
            _threads.append(t)
            t.start()
    _todo.put((s, url))


def _work() -> None:
    while True:
        s, url = _todo.get()
        try:
            keep(s, find(url))
        except Exception:  # noqa: BLE001 - one site must not stop the others
            log.exception("looking for the icon of %s", s)
        finally:
            with _lock:
                _queued.discard(s)
            _todo.task_done()


def settle() -> None:
    """Tests: wait until every queued look is done."""
    _todo.join()
