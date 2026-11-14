"""The Nextcloud Bookmarks API (REST v2), served under /dav/nextcloud as a Nextcloud in a sub-folder would be: what
Floccus and the other clients written for Nextcloud Bookmarks sync with.

    <address>/dav/nextcloud/index.php/apps/bookmarks/public/rest/v2/…   the folders, the bookmarks, tags, the lock
    <address>/dav/nextcloud/index.php/login/v2                          Nextcloud's sign-in flow for apps
    <address>/dav/nextcloud/ocs/v2.php/cloud/capabilities, status.php   what a client asks before it starts

A client is given <address>/dav/nextcloud as the server. It signs in with HTTP Basic (the account's name and an app
password), or runs the sign-in flow: it opens a page of the start page in the browser, where whoever is signed in
says yes, and gets an app password of its own (Shared ioSuite database, scope "sync only", listed and revocable in
Settings like any other).

Where this differs from Nextcloud: the family shares one tree; a bookmark is in one folder (the same address in two
folders is two bookmarks, as in a browser: a lookup by address therefore finds nothing, so a client never merges
them); a folder's id and a bookmark's come from one sequence. The root folder is -1.
"""
import hashlib
import html
import json
import secrets
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, Response
from iosuite_shared import apppasswords, prefix, sessions

from app import __version__, bookmarkfiles, bookmarks, bookmarksync as sync, config
from app.auth import auth

BASE = "/dav/nextcloud"
router = APIRouter()
NC_VERSION = {"major": 31, "minor": 0, "micro": 0, "string": "31.0.0", "edition": "", "extendedSupport": False}
BOOKMARKS_APP = "15.1.0"  # the Nextcloud Bookmarks version whose API this is


def ok(**kw) -> dict:
    return {"status": "success", **kw}


def fail(status: int, msg: str) -> JSONResponse:
    return JSONResponse({"status": "error", "data": [msg]}, status_code=status)


def _stamp(d) -> int:
    return int(d.replace(tzinfo=None).timestamp()) if d else 0


def bookmark(r: dict, u: dict) -> dict:
    return {"id": r["id"], "url": r["url"], "target": r["url"], "title": r["name"], "description": r["description"] or "",
            "added": _stamp(r["created_at"]), "lastmodified": _stamp(r["updated_at"]), "userId": u["name"], "tags": bookmarks.tags_of(r),
            "folders": [r["parent_id"] or -1], "clickcount": 0, "available": True, "archivedFile": None, "lastPreview": 0,
            "htmlContent": None, "textContent": None}


def folder(r: dict, u: dict) -> dict:
    return {"id": r["id"], "title": r["name"], "parent_folder": r["parent_id"] or -1, "userId": u["name"]}


def _fid(v) -> int | None:
    """A folder id of the API (-1: the root) as the store's (None), or 404."""
    try:
        return bookmarks._folder(int(v))
    except (TypeError, ValueError):
        raise bookmarks.NotFound("No such folder")


def _layers(request: Request) -> int:
    try:
        return int(request.query_params.get("layers", 0))
    except ValueError:
        return 0


async def _json(request: Request) -> dict:
    """The body, JSON or a form (the API takes both)."""
    ctype = request.headers.get("content-type", "")
    try:
        if "json" in ctype:
            b = json.loads(await request.body() or b"{}")
            return b if isinstance(b, dict) else {}
        f = await request.form()
        out: dict = {}
        for k in f.keys():
            vals = f.getlist(k)
            out[k[:-2] if k.endswith("[]") else k] = vals if k.endswith("[]") or len(vals) > 1 else vals[0]
        return out
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Unreadable request body")


def _guard(fn):
    """Runs a handler's work off the event loop; what the store refuses is the API's error answer."""
    async def run(*a, **kw):
        try:
            return await run_in_threadpool(fn, *a, **kw)
        except bookmarks.NotFound as e:
            return fail(404, str(e))
        except bookmarks.NotAllowed as e:
            return fail(403, str(e))
        except bookmarks.BadBookmark as e:
            return fail(400, str(e))
    return run


def route(method: str, path: str):
    """A route of the bookmarks API, at .../index.php/apps/bookmarks/... and without index.php (pretty URLs)."""
    def deco(fn):
        for root in (f"{BASE}/index.php/apps/bookmarks/public/rest/v2", f"{BASE}/apps/bookmarks/public/rest/v2"):
            router.add_api_route(root + path, fn, methods=[method], include_in_schema=False)
        return fn
    return deco


# ------------------------------------------------------------------ what a client asks first

@router.get(BASE + "/status.php", include_in_schema=False)
def status():
    return {"installed": True, "maintenance": False, "needsDbUpgrade": False, "version": "31.0.0.0", "versionstring": "31.0.0",
            "edition": "", "productname": "ioStart", "extendedSupport": False}


def _ocs(data: dict) -> dict:
    return {"ocs": {"meta": {"status": "ok", "statuscode": 200, "message": "OK"}, "data": data}}


@router.get(BASE + "/ocs/{v}/cloud/capabilities", include_in_schema=False)
def capabilities(v: str, request: Request):
    sync.user(request)
    return _ocs({"version": NC_VERSION, "capabilities": {
        "core": {"pollinterval": 60, "webdav-root": "remote.php/webdav"},
        "bookmarks": {"version": BOOKMARKS_APP, "javascript-bookmarks": True, "hash-functions": ["sha256"]},
        "iostart": {"version": __version__}}})


@router.get(BASE + "/ocs/{v}/cloud/user", include_in_schema=False)
def cloud_user(v: str, request: Request):
    u = sync.user(request)
    return _ocs({"id": u["name"], "display-name": u.get("displayName") or u["name"], "displayname": u.get("displayName") or u["name"],
                 "email": u.get("email") or None, "enabled": True, "language": "en"})


# ------------------------------------------------------------------ Nextcloud's sign-in flow for apps (login flow v2)

FLOW_TTL = 20 * 60
_flows: dict = {}  # poll token -> {at, page (the token in the page's address), ua, done: {loginName, appPassword} | None}


def _root(request: Request) -> str:
    """The address this server is reached at, as the client reached it."""
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    scheme = "https" if sessions.over_https(request) else request.url.scheme
    return (config.PUBLIC_URL.rstrip("/") if config.PUBLIC_URL and not host else f"{scheme}://{host}{prefix.of(request)}")


def _flow_by_page(page: str):
    now = time.time()
    for k in [k for k, f in _flows.items() if now - f["at"] > FLOW_TTL]:
        _flows.pop(k, None)
    return next((f for f in _flows.values() if secrets.compare_digest(f["page"], page)), None)


@router.post(BASE + "/index.php/login/v2", include_in_schema=False)
def flow_start(request: Request):
    """Anyone may start a flow: it gives nothing until somebody signed in says yes on the page."""
    _flow_by_page("")  # forgets the old ones
    if len(_flows) > 200:
        raise HTTPException(429, "Too many sign-ins waiting; try again in a few minutes")
    poll, page = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    who = request.query_params.get("client") or request.headers.get("user-agent") or ""  # ?client=: the extension names itself
    _flows[poll] = {"at": time.time(), "page": page, "ua": who[:80], "done": None}
    root = _root(request) + BASE
    return {"poll": {"token": poll, "endpoint": f"{root}/index.php/login/v2/poll"}, "login": f"{root}/index.php/login/v2/flow/{page}"}


@router.post(BASE + "/index.php/login/v2/poll", include_in_schema=False)
async def flow_poll(request: Request):
    """404 until the page said yes; then, once, the name and the app password made for the client."""
    token = str((await _json(request)).get("token") or "")
    f = _flows.get(token)
    if not f or not f["done"]:
        return JSONResponse([], status_code=404)
    _flows.pop(token, None)
    return {"server": _root(request) + BASE, **f["done"]}


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>
:root {{ color-scheme: light dark; }} body {{ font: 16px/1.5 system-ui, sans-serif; margin: 0; min-height: 100vh; display: grid; place-items: center; background: Canvas; color: CanvasText; }}
main {{ max-width: 440px; padding: 28px; }} h1 {{ font-size: 22px; margin: 0 0 12px; }} p {{ margin: 0 0 14px; }} .muted {{ opacity: .7; font-size: 14px; }}
button, a.btn {{ font: inherit; padding: 10px 18px; border-radius: 10px; border: 0; background: #2f3a5a; color: #fff; cursor: pointer; text-decoration: none; display: inline-block; }}
</style></head><body><main>{body}</main></body></html>""", headers={"Cache-Control": "no-store", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'"})


@router.get(BASE + "/index.php/login/v2/flow/{page}", include_in_schema=False)
def flow_page(page: str, request: Request):
    f = _flow_by_page(page)
    if not f or f["done"]:
        return _page("ioStart", "<h1>This sign-in link is no longer valid</h1><p>Start again from the app that sent you here.</p>")
    u = auth.current_user(request)
    if not u:
        # the start page, which brings the visitor back here once signed in (static/app.js: ?flow=): one tab, so it
        # also works where there is only one, as in the sign-in sheet of the iPhone app
        return _page("ioStart", '<h1>Sign in to ioStart first</h1><p>Then you are asked whether the app may sync the bookmarks.</p>'
                                f'<p><a class="btn" href="{prefix.of(request)}/?flow={html.escape(page)}">Sign in</a></p>')
    who = html.escape(f["ua"] or "An app")
    can = "read and change" if sync.users.is_member(u) else "read"
    return _page("Sync bookmarks with ioStart", f"""<h1>Let this app sync the bookmarks?</h1>
<p><b>{who}</b> asks to {can} your bookmarks and the shared ones as <b>{html.escape(u["name"])}</b>.</p>
<p class="muted">It gets an app password of its own, for sync only. You can revoke it any time in Settings.</p>
<form method="post" action="{prefix.of(request)}{BASE}/index.php/login/v2/grant"><input type="hidden" name="page" value="{html.escape(page)}"><button>Allow</button></form>""")


@router.post(BASE + "/index.php/login/v2/grant", include_in_schema=False)
async def flow_grant(request: Request):
    """The yes of whoever is signed in, in the browser (the session cookie, from this site: not a password, not another site)."""
    u = auth.current_user(request)
    if not u or "authorization" in request.headers or auth.cross_site(request):
        raise HTTPException(403, "Sign in to ioStart in this browser first")
    f = _flow_by_page(str((await _json(request)).get("page") or ""))
    if not f or f["done"]:
        return _page("ioStart", "<h1>This sign-in link is no longer valid</h1><p>Start again from the app that sent you here.</p>")
    label = f"Bookmark sync: {f['ua']}" if f["ua"] else "Bookmark sync"
    pw = await run_in_threadpool(apppasswords.create, u["id"], auth.app, label, apppasswords.DAV)
    f["done"] = {"loginName": u["name"], "appPassword": pw}
    return _page("ioStart", "<h1>Done</h1><p>The app is signed in. You can close this tab and go back to it.</p>")


# ------------------------------------------------------------------ the lock

@route("POST", "/lock")
def lock_set(request: Request):
    sync.user(request, write=True)
    if sync.locked_at():
        return fail(423, "Another client is syncing")
    sync.lock()
    return ok()


@route("DELETE", "/lock")
def lock_free(request: Request):
    sync.user(request, write=True)
    sync.unlock()
    return ok()


# ------------------------------------------------------------------ folders

def _children(t: bookmarks.Tree, u: dict, pid, layers: int) -> list[dict]:
    out = []
    for r in t.children(pid):
        if r["folder"]:
            f = {"type": "folder", **folder(r, u)}
            if layers != 0:
                f["children"] = _children(t, u, r["id"], layers - 1)
            out.append(f)
        else:
            out.append({"type": "bookmark", **bookmark(r, u)})
    return out


def _subfolders(t: bookmarks.Tree, u: dict, pid, layers: int) -> list[dict]:
    return [{**folder(r, u), "children": _subfolders(t, u, r["id"], layers - 1) if layers != 0 else []} for r in t.children(pid) if r["folder"]]


@route("GET", "/folder")
async def folders(request: Request):
    u = sync.user(request)
    return await _guard(lambda: ok(data=_subfolders(bookmarks.Tree(), u, _fid(request.query_params.get("root", -1)), _layers(request))))()


@route("POST", "/folder")
async def folder_new(request: Request):
    u, b = sync.user(request, write=True), await _json(request)

    def work():
        sync.alive()
        return ok(item=folder(bookmarks.create(_fid(b.get("parent_folder", -1)), True, str(b.get("title") or ""), start=False), u))
    return await _guard(work)()


@route("GET", "/folder/{fid}")
async def folder_get(fid: int, request: Request):
    u = sync.user(request)

    def work():
        if fid == -1:
            return ok(item={"id": -1, "title": "", "parent_folder": -1, "userId": u["name"]})
        return ok(item=folder(bookmarks.node(_fid(fid)), u))
    return await _guard(work)()


@route("PUT", "/folder/{fid}")
async def folder_put(fid: int, request: Request):
    u, b = sync.user(request, write=True), await _json(request)

    def work():
        sync.alive()
        c = {}
        if "title" in b:
            c["name"] = str(b["title"] or "")
        if "parent_folder" in b:
            c["parent"] = _fid(b["parent_folder"])
        nid = _fid(fid)
        if nid is None:
            raise bookmarks.BadBookmark("The root folder cannot be changed")
        return ok(item=folder(bookmarks.change(nid, c), u))
    return await _guard(work)()


@route("DELETE", "/folder/{fid}")
async def folder_delete(fid: int, request: Request):
    sync.user(request, write=True)

    def work():
        sync.alive()
        nid = _fid(fid)
        if nid is None:
            raise bookmarks.BadBookmark("The root folder cannot be deleted")
        bookmarks.remove(nid)
        return ok()
    return await _guard(work)()


@route("GET", "/folder/{fid}/children")
async def folder_children(fid: int, request: Request):
    u = sync.user(request)
    return await _guard(lambda: ok(data=_children(bookmarks.Tree(), u, _fid(fid), _layers(request))))()


@route("GET", "/folder/{fid}/count")
async def folder_count(fid: int, request: Request):
    sync.user(request)

    def work():
        t, pid = bookmarks.Tree(), _fid(fid)
        ids = t.below(pid) if pid is not None else set(t.by)
        return ok(item=sum(1 for i in ids if not t.by[i]["folder"]))
    return await _guard(work)()


def _sha(obj) -> str:
    # as JavaScript's JSON.stringify writes it (Floccus hashes the very same text): no spaces, text as it is
    return hashlib.sha256(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8", "surrogatepass")).hexdigest()


def tree_hash(t: bookmarks.Tree, pid, fields=("title", "url")) -> str:
    """The hash of a folder as Nextcloud Bookmarks and Floccus compute it: of {title, children: [hashes]} for a folder
    (the root has no title), of the fields asked for a bookmark, children in their order."""
    def of(r):
        if not r["folder"]:
            vals = {"title": r["name"], "url": r["url"], "tags": sorted(bookmarks.tags_of(r)), "description": r["description"] or ""}
            return _sha({f: vals[f] for f in fields})
        return _sha({"title": r["name"], "children": [of(c) for c in t.children(r["id"])]})
    if pid is None:
        return _sha({"children": [of(c) for c in t.children(None)]})
    return of(t.by[pid])


@route("GET", "/folder/{fid}/hash")
async def folder_hash(fid: int, request: Request):
    sync.user(request)
    q = request.query_params
    if q.get("hashFn", "sha256") != "sha256":
        return fail(400, "Unsupported hash function (sha256 only)")
    fields = tuple(f for f in (q.getlist("fields[]") or q.getlist("fields") or ["title", "url"]) if f in ("title", "url", "tags", "description")) or ("title", "url")
    return await _guard(lambda: ok(data=tree_hash(bookmarks.Tree(), _fid(fid), fields)))()


@route("GET", "/folder/{fid}/childorder")
async def childorder_get(fid: int, request: Request):
    sync.user(request)

    def work():
        t, layers = bookmarks.Tree(), _layers(request)

        def level(pid, n):
            return [{"type": "folder", "id": r["id"], **({"children": level(r["id"], n - 1)} if n != 0 else {})} if r["folder"]
                    else {"type": "bookmark", "id": r["id"]} for r in t.children(pid)]
        return ok(data=level(_fid(fid), layers))
    return await _guard(work)()


@route("PATCH", "/folder/{fid}/childorder")
async def childorder_set(fid: int, request: Request):
    sync.user(request, write=True)
    b = await _json(request)

    def work():
        sync.alive()
        pid = _fid(fid)
        t = bookmarks.Tree()
        ids = []
        for it in b.get("data") or []:
            try:
                i = int(str(it.get("id")).split(";")[0])
            except (TypeError, ValueError, AttributeError):
                continue
            if i in t.by and t.by[i]["parent_id"] == pid:  # ordering never moves anything in from elsewhere
                ids.append(i)
        bookmarks.order(pid, ids)
        return ok()
    return await _guard(work)()


@route("POST", "/folder/{fid}/import")
async def folder_import(fid: int, request: Request):
    """A bookmarks HTML file (multipart field bm_import) added to the folder; answers with what it made."""
    sync.user(request, write=True)
    form = await request.form()
    up = form.get("bm_import")
    if up is None or not hasattr(up, "read"):
        return fail(400, "No file provided for import")
    text = (await up.read()).decode("utf-8", "replace")

    def work():
        sync.alive()
        try:
            parsed = bookmarkfiles.parse(text)
        except bookmarkfiles.BadFile as e:
            raise bookmarks.BadBookmark(str(e))
        return ok(data=bookmarks.add_items(_fid(fid), parsed))
    return await _guard(work)()


@route("DELETE", "/folder/{fid}/bookmarks/{bid}")
async def folder_bookmark_remove(fid: int, bid: int, request: Request):
    sync.user(request, write=True)

    def work():
        sync.alive()
        r = bookmarks.node(bid)
        if r["folder"] or r["parent_id"] != _fid(fid):
            raise bookmarks.NotFound("That bookmark is not in this folder")
        bookmarks.remove(bid)
        return ok()
    return await _guard(work)()


@route("POST", "/folder/{fid}/bookmarks/{bid}")
async def folder_bookmark_add(fid: int, bid: int, request: Request):
    """Nextcloud adds the bookmark to one more folder; here a bookmark is in one, so it moves."""
    sync.user(request, write=True)

    def work():
        sync.alive()
        if bookmarks.node(bid)["folder"]:
            raise bookmarks.NotFound("No such bookmark")
        bookmarks.change(bid, {"parent": _fid(fid)})
        return ok()
    return await _guard(work)()


# ------------------------------------------------------------------ bookmarks

@route("GET", "/bookmark")
async def bookmark_list(request: Request):
    """page / limit (page=-1: everything), folder, tags[], search[], sortby (title | added | lastmodified | url).
    url=…: always nothing (see the top of the file: no address is unique here)."""
    u = sync.user(request)
    q = request.query_params

    def work():
        if q.get("url"):
            return ok(data=[])
        t = bookmarks.Tree()
        rows = [r for r in t.rows if not r["folder"]]
        if q.get("folder") not in (None, ""):
            pid = _fid(q.get("folder"))
            rows = [r for r in rows if r["parent_id"] == pid]
        tags = q.getlist("tags[]") or q.getlist("tags")
        if tags:
            rows = [r for r in rows if set(tags) <= set(bookmarks.tags_of(r))]
        for s in [x.lower() for x in (q.getlist("search[]") or q.getlist("search")) if x]:
            rows = [r for r in rows if s in f'{r["name"]}\n{r["url"]}\n{r["description"] or ""}\n{r["tags"] or ""}'.lower()]
        key = {"title": lambda r: r["name"].lower(), "url": lambda r: r["url"], "added": lambda r: r["created_at"]}.get(q.get("sortby") or "")
        rows.sort(key=key or (lambda r: r["updated_at"]), reverse=key is None or q.get("sortby") == "added")
        try:
            page, limit = int(q.get("page", 0)), max(1, min(int(q.get("limit", 10)), 1000))
        except ValueError:
            page, limit = 0, 10
        if page >= 0:
            rows = rows[page * limit:(page + 1) * limit]
        return ok(data=[bookmark(r, u) for r in rows])
    return await _guard(work)()


def _one_folder(b: dict):
    """The folder a bookmark goes into: the last one named (a client that moves a bookmark names the new one last)."""
    fs = b.get("folders")
    if isinstance(fs, (str, int)):
        fs = [fs]
    return _fid(fs[-1]) if fs else None


def _tags(b: dict):
    t = b.get("tags")
    return [t] if isinstance(t, str) else list(t or [])


@route("POST", "/bookmark")
async def bookmark_new(request: Request):
    u, b = sync.user(request, write=True), await _json(request)

    def work():
        sync.alive()
        url = str(b.get("url") or b.get("target") or "")
        r = bookmarks.create(_one_folder(b), False, str(b.get("title") or ""), url, tags=_tags(b), description=str(b.get("description") or ""))
        return ok(item=bookmark(r, u))
    return await _guard(work)()


@route("POST", "/bookmark/click")
def bookmark_click(request: Request):
    sync.user(request)
    return ok()


@route("GET", "/bookmark/export")
async def bookmark_export(request: Request):
    sync.user(request)
    body = await run_in_threadpool(lambda: bookmarkfiles.to_html(sync.items()))
    return Response(body, media_type="text/html; charset=utf-8")


@route("GET", "/bookmark/{bid}")
async def bookmark_get(bid: int, request: Request):
    u = sync.user(request)

    def work():
        r = bookmarks.node(bid)
        if r["folder"]:
            raise bookmarks.NotFound("No such bookmark")
        return ok(item=bookmark(r, u))
    return await _guard(work)()


@route("PUT", "/bookmark/{bid}")
async def bookmark_put(bid: int, request: Request):
    u, b = sync.user(request, write=True), await _json(request)

    def work():
        sync.alive()
        if bookmarks.node(bid)["folder"]:
            raise bookmarks.NotFound("No such bookmark")
        c = {}
        if "url" in b or "target" in b:
            c["url"] = str(b.get("url") or b.get("target") or "")
        if "title" in b:
            c["name"] = str(b["title"] or "")
        if "tags" in b:
            c["tags"] = _tags(b)
        if "description" in b:
            c["description"] = str(b["description"] or "")
        if b.get("folders"):
            c["parent"] = _one_folder(b)
        return ok(item=bookmark(bookmarks.change(bid, c), u))
    return await _guard(work)()


@route("DELETE", "/bookmark/{bid}")
async def bookmark_delete(bid: int, request: Request):
    sync.user(request, write=True)

    def work():
        sync.alive()
        if bookmarks.node(bid)["folder"]:
            raise bookmarks.NotFound("No such bookmark")
        bookmarks.remove(bid)
        return ok()
    return await _guard(work)()


@route("POST", "/bookmark/{bid}/click")
def bookmark_click_one(bid: int, request: Request):
    sync.user(request)
    return ok()


# ------------------------------------------------------------------ tags

@route("GET", "/tag")
async def tags(request: Request):
    sync.user(request)

    def work():
        count: dict = {}
        for r in bookmarks.Tree().rows:
            for t in bookmarks.tags_of(r):
                count[t] = count.get(t, 0) + 1
        if request.query_params.get("count") in ("true", "1"):
            return [{"name": t, "count": n} for t, n in sorted(count.items())]
        return sorted(count)
    return await _guard(work)()


def _retag(old: str, new: str | None) -> None:
    with bookmarks.writing():
        for r in bookmarks.Tree().rows:
            ts = bookmarks.tags_of(r)
            if old in ts:
                bookmarks.change(r["id"], {"tags": [new if t == old else t for t in ts if new or t != old]})


@route("PUT", "/tag/{name}")
async def tag_rename(name: str, request: Request):
    sync.user(request, write=True)
    b = await _json(request)
    new = str(b.get("name") or "").strip()
    if not new:
        return fail(400, "A name for the tag, please")
    await _guard(lambda: _retag(name, new))()
    return ok()


@route("DELETE", "/tag/{name}")
async def tag_delete(name: str, request: Request):
    sync.user(request, write=True)
    await _guard(lambda: _retag(name, None))()
    return ok()
