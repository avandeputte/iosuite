"""Bookmark upkeep: the links that no longer answer, the ones that moved, and the same address kept twice.

A browser's bookmarks pile up over the years. The Bookmarks page's "Tidy up" asks this module two things about the
tree of the person asking (their own bookmarks and the shared ones):

- duplicates(): the addresses kept more than once, wherever they are in the tree. Read from the tree, at once.
- a check of every web address: start() begins it in the background (a few addresses at a time, each asked once
  however many bookmarks hold it), state() says how far it is and what it found so far. A link is

    dead    nothing answered there (no such name, nothing listening, a timeout) or the server failed (a 5xx);
    gone    the server answered that the page is not there (404, 410);
    moved   the server says the page moved for good (301, 308) to another address (`to`): one that differs by more
            than http → https, a "www." or a trailing slash, which browsers sort out by themselves.

  Everything else is fine and not listed: a page that asks to sign in (401, 403), a temporary redirect, a site that
  dislikes being asked by a program. A certificate this server cannot vouch for is fine too (a router or a NAS at
  home), as it is for the dots on the start page (app/status.py). When more than half of the addresses give no
  answer at all, the trouble is this server's way out to the internet, not the bookmarks: the check says so
  (`offline`), and the page does not offer to delete them all.

The requests go out as the dots' do (iosuite_shared.outbound): to the address that was checked, never to this server
itself or a link-local address, never following a redirect, reading nothing of the answer but its status and where
it points. The answers are kept in memory, per person, until their next check or for a day; the list is always made
against the tree as it is now, so a link deleted or changed since is not in it.
"""
import ssl
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit

from iosuite_shared import outbound

from app import bookmarks, widgets

TIMEOUT = 6        # seconds per request (longer than the dots': a slow site is not a dead one)
WORKERS = 12       # addresses asked at the same time
MAX_LINKS = 5000   # addresses checked at most in one run
KEEP = 24 * 3600   # seconds a finished check is kept
OFFLINE_MIN = 6    # from this many addresses on, more than half of them silent means the server cannot get out
_opener = outbound.opener(outbound.not_this_machine, redirects=False)
_jobs: dict = {}   # account id (0: no accounts) -> Job
_lock = threading.Lock()


class Job:
    def __init__(self, urls: list[str]):
        self.urls, self.total, self.done = urls, len(urls), 0
        self.results: dict[str, dict] = {}
        self.started, self.finished = time.time(), None
        self.stop = False


def _same_page(a: str, b: str) -> bool:
    """Whether two addresses differ only by what a browser sorts out itself: http or https, a leading "www.", the
    host's case, a trailing slash."""
    def key(u):
        try:
            p = urlsplit(u)
        except ValueError:
            return u
        host = (p.hostname or "").lower()
        return (host[4:] if host.startswith("www.") else host, p.port, p.path.rstrip("/"), p.query)
    return key(a) == key(b)


def probe(href: str) -> dict:
    """{state: ok | dead | gone | moved, status, to}: one address asked once (HEAD; GET when the server dislikes HEAD
    or says "not found" to it, which some do to any HEAD)."""
    out = {"state": "dead", "status": None, "to": None}
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(href, method=method, headers={"User-Agent": widgets.UA, "Accept": "*/*"})
        try:
            with _opener.open(req, timeout=TIMEOUT) as r:  # noqa: S310 - an address someone bookmarked, checked as it connects
                return {"state": "ok", "status": r.status, "to": None}
        except outbound.NotAllowed:
            return {"state": "ok", "status": None, "to": None}  # this server itself, or a link-local address: not asked
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (400, 404, 405, 410, 501):
                continue  # asked again with GET before it is called gone
            if e.code in (301, 308):
                to = urljoin(href, e.headers.get("Location") or "")
                if to.startswith(("http://", "https://")) and not _same_page(href, to):
                    return {"state": "moved", "status": e.code, "to": to[:2048]}
                return {"state": "ok", "status": e.code, "to": None}
            if e.code in (404, 410):
                return {"state": "gone", "status": e.code, "to": None}
            return {"state": "dead" if e.code >= 500 else "ok", "status": e.code, "to": None}
        except ssl.SSLCertVerificationError:
            return {"state": "ok", "status": None, "to": None}
        except urllib.error.URLError as e:
            if isinstance(e.reason, ssl.SSLCertVerificationError):
                return {"state": "ok", "status": None, "to": None}
            return out
        except (OSError, ValueError):
            return out
    return out


def _uid() -> int:
    v = bookmarks.viewer()
    return (v.uid or 0) if v else 0


def _walk(t: bookmarks.Tree, pid=None):
    """Every link of the tree as the Bookmarks page lists them: a folder's links, then the folders inside it."""
    kids = t.children(pid)
    yield from (r for r in kids if not r["folder"])
    for r in kids:
        if r["folder"]:
            yield from _walk(t, r["id"])


def _links(t: bookmarks.Tree) -> list[dict]:
    return [r for r in _walk(t) if (r["url"] or "").lower().startswith(("http://", "https://"))]


def _run(job: Job) -> None:
    def one(url):
        if job.stop:
            return
        try:
            r = probe(url)
        except Exception:  # noqa: BLE001 - one odd address does not end the check
            r = {"state": "ok", "status": None, "to": None}
        job.results[url] = r
        job.done += 1
    with ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="bookmarkcheck") as pool:
        list(pool.map(one, job.urls))
    job.finished = time.time()


def start() -> dict:
    """Begin checking every web address of the viewer's tree (their own and the shared ones); the one already running
    for them goes on instead. → state()."""
    uid = _uid()
    urls = list(dict.fromkeys(r["url"] for r in _links(bookmarks.Tree())))[:MAX_LINKS]
    with _lock:
        now = time.time()
        for k in [k for k, j in _jobs.items() if j.finished and now - j.finished > KEEP]:
            del _jobs[k]
        job = _jobs.get(uid)
        if not job or job.finished:
            job = _jobs[uid] = Job(urls)
            threading.Thread(target=_run, args=(job,), name="bookmarkcheck", daemon=True).start()
    return state()


def state() -> dict:
    """{running, done, total, checkedAt, offline, items: [{id, name, href, path, shared, canChange, state, status,
    to}]}: how far the viewer's check is (checkedAt: when it finished, None while it runs or when there never was one)
    and the links of their tree, as it is now, that it found dead, gone or moved; the dead first, in the tree's order.
    offline: most addresses did not answer, which says more about this server's way out than about the bookmarks."""
    job = _jobs.get(_uid())
    if not job:
        return {"running": False, "done": 0, "total": 0, "checkedAt": None, "offline": False, "items": []}
    t = bookmarks.Tree()
    items = []
    for r in _links(t):
        res = job.results.get(r["url"])
        if not res or res["state"] == "ok":
            continue
        p = t.by.get(r["parent_id"])
        items.append({"id": r["id"], "name": r["name"], "href": r["url"], "path": " › ".join(t.path(p)) if p else "",
                      "shared": bool(r["shared"]), "canChange": bookmarks.may_change(r), **res})
    rank = {"dead": 0, "gone": 1, "moved": 2}
    items.sort(key=lambda x: rank[x["state"]])  # stable: the tree's order within each
    silent = sum(1 for r in list(job.results.values()) if r["state"] == "dead" and r["status"] is None)
    return {"running": job.finished is None, "done": job.done, "total": job.total,
            "checkedAt": int(job.finished) if job.finished else None,
            "offline": job.done >= OFFLINE_MIN and silent * 2 > job.done, "items": items}


def forget() -> None:
    """No check remembered (the tests)."""
    with _lock:
        for j in _jobs.values():
            j.stop = True
        _jobs.clear()


# ------------------------------------------------------------------ the same address twice

def _address_key(url: str) -> str:
    """What makes two bookmarks the same page: the address without its scheme, a leading "www.", the host's case, a
    trailing slash and the part after #."""
    try:
        p = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    if p.scheme.lower() not in ("http", "https"):
        return url.strip()
    host = (p.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    port = f":{p.port}" if p.port and p.port not in (80, 443) else ""
    return f"{host}{port}{p.path.rstrip('/')}{'?' + p.query if p.query else ''}"


def duplicates() -> dict:
    """{groups: [{href, links: [{id, name, href, path, shared, onStart, canChange}]}], extra}: the addresses the viewer's
    tree holds more than once, each with its copies in the tree's order but the one to keep first (one on the start
    page, else a shared one, else the first met); extra: how many copies that leaves over."""
    t = bookmarks.Tree()
    by: dict[str, list] = {}
    for r in _walk(t):
        if r["url"]:
            by.setdefault(_address_key(r["url"]), []).append(r)
    groups = []
    for rows in by.values():
        if len(rows) < 2:
            continue
        links = []
        for r in rows:
            p = t.by.get(r["parent_id"])
            links.append({"id": r["id"], "name": r["name"], "href": r["url"], "path": " › ".join(t.path(p)) if p else "",
                          "shared": bool(r["shared"]), "onStart": t.shown(r), "canChange": bookmarks.may_change(r)})
        links.sort(key=lambda x: (not x["onStart"], not x["shared"]))  # stable
        groups.append({"href": rows[0]["url"], "links": links})
    return {"groups": groups, "extra": sum(len(g["links"]) - 1 for g in groups)}
