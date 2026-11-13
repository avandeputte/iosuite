"""The sync API of the ioSuite Bookmarks browser extension (static/extension/): the tree in one request, and a browser's
changes in one request, applied together.

    GET  <address>/dav/ext        who is signed in, whether they may change the bookmarks, the revision
    GET  <address>/dav/ext/tree   {rev, tree}: every folder and link, nested, with their ids
    POST <address>/dav/ext/sync   {base, ops}: a browser's changes since its copy at revision `base`;
                                  answers {rev, ids, tree}: the tree after them, and the ids given to what it made
    GET  <address>/dav/ext/icon/<id>  the icon of a link's site, as the server keeps it (app/siteicons.py); 404 without one

ioStart, the iPhone and iPad app (the repository avandeputte/iostart-apps), speaks the same API: it shows the tree,
sends what is changed in it as ops, and draws the links with the icons.

The extension signs in with Nextcloud's sign-in flow (app/ncbookmarks.py: one click, a sync-only app password in the
Shared ioSuite database) and then HTTP Basic, like the other sync clients; under /dav, so the Cloudflare Worker checks
the app password as for them. The extension keeps the tree as it last saw it, works out what the browser changed since
(made, renamed, moved, reordered, deleted), sends that, and makes the browser's bookmarks the tree it gets back: what
was deleted here goes from every browser at their next sync.

An op is one of
    {"op": "create", "ref": "<a name for it>", "parent": <id | null: the top | "<ref>">, "folder": bool, "title", "url"}
    {"op": "update", "id", "title"?, "url"?}
    {"op": "order", "parent": <id | null | "<ref>">, "ids": [<id | "<ref>">, …]}   (moves what comes from elsewhere)
    {"op": "delete", "id"}
applied creates, then updates, then orders, then deletes. A change to something already gone is skipped. A delete of
something changed on the server after `base` (in another browser, or on the start page) is skipped too: it comes back
to the browser, which is the safe way round.
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

from app import __version__, bookmarks, bookmarksync as sync, siteicons
from iosuite_shared import users

BASE = "/dav/ext"
router = APIRouter()
MAX_OPS = 20000


def tree(t: bookmarks.Tree | None = None, pid=None) -> list[dict]:
    t = t or bookmarks.Tree()
    return [{"id": r["id"], "folder": True, "title": r["name"], "children": tree(t, r["id"])} if r["folder"] else
            {"id": r["id"], "folder": False, "title": r["name"], "url": r["url"]} for r in t.children(pid)]


def _state() -> dict:
    """The revision first, then the tree: a change in between makes the copy newer than its revision, which only ever
    makes the next sync more careful (a delete of it is skipped), never wrong."""
    rev = bookmarks.revision()
    return {"rev": rev, "tree": tree()}


def apply(base: int, ops: list) -> dict:
    """The ops of one browser, together (see the module's doc). Returns {rev, ids, tree}."""
    if not isinstance(ops, list) or len(ops) > MAX_OPS:
        raise bookmarks.BadBookmark("The changes are not a list, or too many at once")
    ops = [o for o in ops if isinstance(o, dict)]
    ids: dict = {}

    def ref(v):
        """An id, a ref to something made in this request (None when it was not made), or None: the top."""
        if v is None or v in (0, -1):
            return None
        if isinstance(v, str) and not v.lstrip("-").isdigit():
            if v not in ids:
                raise LookupError(v)
            return ids[v]
        return int(v)

    if not ops:
        return {**_state(), "ids": ids}
    with bookmarks.writing() as now:
        for o in (o for o in ops if o.get("op") == "create"):
            try:
                r = bookmarks.create(ref(o.get("parent")), bool(o.get("folder")), str(o.get("title") or ""),
                                     None if o.get("folder") else str(o.get("url") or ""))
            except (LookupError, ValueError):  # its folder was not made (or is gone), or the address is unusable
                continue
            if isinstance(o.get("ref"), str):
                ids[o["ref"]] = r["id"]
        for o in (o for o in ops if o.get("op") == "update"):
            c = {k: str(o[k] or "") for k in ("title", "url") if k in o}
            if "title" in c:
                c["name"] = c.pop("title")
            try:
                bookmarks.change(int(o["id"]), c)
            except (KeyError, LookupError, ValueError):
                continue
        for o in (o for o in ops if o.get("op") == "order"):
            try:
                parent = ref(o.get("parent"))
                want = []
                for i in o.get("ids") or []:
                    try:
                        want.append(ref(i))
                    except (LookupError, ValueError):
                        pass
                bookmarks.order(parent, [i for i in want if i is not None])
            except (LookupError, ValueError):
                continue
        t = bookmarks.Tree()
        for o in (o for o in ops if o.get("op") == "delete"):
            try:
                nid = int(o["id"])
            except (KeyError, TypeError, ValueError):
                continue
            if nid not in t.by:
                continue
            if any(base < t.by[i]["rev"] < now for i in t.below(nid) if i in t.by):
                continue  # changed after the browser's copy: it stays, and comes back to the browser
            bookmarks.remove(nid)
            t = bookmarks.Tree()
    return {**_state(), "ids": ids}


def _guard(fn):
    async def run(*a, **kw):
        try:
            return await run_in_threadpool(fn, *a, **kw)
        except bookmarks.BadBookmark as e:
            return JSONResponse({"error": str(e)}, status_code=400)
    return run


@router.get(BASE, include_in_schema=False)
def hello(request: Request):
    u = sync.user(request)
    return {"user": u["name"], "displayName": u.get("displayName") or u["name"], "canWrite": bool(users.can_write(u)),
            "rev": bookmarks.revision(), "version": __version__}


@router.get(BASE + "/rev", include_in_schema=False)
def rev(request: Request):
    """What the extension asks every minute: whether anything changed."""
    sync.user(request)
    return {"rev": bookmarks.revision()}


@router.get(BASE + "/tree", include_in_schema=False)
async def get_tree(request: Request):
    sync.user(request)
    return await _guard(_state)()


@router.get(BASE + "/icon/{nid}", include_in_schema=False)
def icon(nid: int, request: Request):
    """The icon of a link's site, for a client that draws the bookmarks itself (the iOS app): the image as the server
    fetched it. Asks for the look when it is due, like the Bookmarks page; 404 until there is one (or for good)."""
    sync.user(request)
    try:
        r = bookmarks.node(nid)
    except bookmarks.BadBookmark:
        raise HTTPException(404, "No such bookmark")
    s = None if r["folder"] else siteicons.site(r["url"] or "")
    if s:
        siteicons.of(r["url"])
    ic = siteicons.get(s) if s else None
    if not ic:
        raise HTTPException(404, "No icon")
    return Response(bytes(ic["data"]), media_type=ic["mime"],
                    headers={"Cache-Control": "private, max-age=86400", "ETag": f'"{ic["etag"]}"',
                             "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox", "X-Content-Type-Options": "nosniff"})


@router.post(BASE + "/sync", include_in_schema=False)
async def post_sync(request: Request):
    sync.user(request, write=True)
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, "Unreadable request body")
    if not isinstance(body, dict):
        raise HTTPException(400, "Unreadable request body")
    if sync.locked_at():  # a Floccus sync is half way: its next request would find the tree changed under it
        return JSONResponse({"error": "Another sync app is syncing; trying again shortly"}, status_code=423, headers={"Retry-After": "20"})
    try:
        base = int(body.get("base") or 0)
    except (TypeError, ValueError):
        base = 0
    return await _guard(apply)(base, body.get("ops") or [])
