"""Linked items: an event linked to its meeting notes, a task to a recipe, a note to a contact, across the apps.

A link joins two items of the suite, each named by its kind and its id in its app (KINDS: event, task, note, contact,
recipe, photo). It is one row of ios_related in the Shared ioSuite database and works both ways: the task shows the
recipe and the recipe shows the task. Nothing about the items is kept with it; what a link shows (the title, the date,
the small picture) is asked of the item's own app every time, with the viewer's own sign-in, so a link shows only to
someone who may see both of its items, and always as the item is now. A note is its owner's alone: an event linked to
it shows the link to the note's owner and to nobody else.

Every app with items mounts the router (Auth.related_router(): /api/related/*) and its pages mount the panel
(GET /api/related/ui.js):

    const rel = await import(new URL('api/related/ui.js', document.baseURI).href);
    rel.mount(el, { kind: 'task', id: 12, toast });   // "Linked" under the task, and the picker behind its + button

The picker searches every app that has items (the same way the start page's search box does), the coming events
and the open tasks first. Adding or removing a link needs a role of member or more in the app the item is in, and
both items must be ones the viewer sees. An app that deletes an item for good calls forget(kind, id).

The other app is asked the way the start page asks it: on localhost when it runs on this machine, then at its
address inside the network, then at its public one, with the suite's Cloudflare Access service token when one is set
(iosuite_shared.links), and with the viewer's own credentials (the shared session cookie, or the Authorization header
the request came with), so each app answers with what that person may see there.
"""
import datetime as dt
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response

from iosuite_shared import db, links, sessions, suite, users
from iosuite_shared.access import json_body

log = logging.getLogger("iosuite_shared.related")

# kind -> the app its items are in, and what one is called
KINDS = {
    "event": {"app": "iocalendar", "label": "Event", "plural": "Events"},
    "task": {"app": "iotask", "label": "Task", "plural": "Tasks"},
    "note": {"app": "ionote", "label": "Note", "plural": "Notes"},
    "contact": {"app": "iocontact", "label": "Contact", "plural": "Contacts"},
    "recipe": {"app": "iorecipe", "label": "Recipe", "plural": "Recipes"},
    "photo": {"app": "iopix", "label": "Photo", "plural": "Photos"},
}
MAX_LINKS = 200  # links per item
TIMEOUT = 5      # seconds, per request to an app
UA = "ioSuite linked items"
_pool = ThreadPoolExecutor(max_workers=12, thread_name_prefix="related")
_ID = {"note": re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")}
_NUM = re.compile(r"[1-9][0-9]{0,17}")


class Unavailable(Exception):
    """The item's app could not be asked, or would not show it: (status, why)."""

    def __init__(self, status: int, why: str):
        super().__init__(why)
        self.status = status


def check(kind: str, item_id) -> tuple[str, str]:
    """(kind, id) as kept, or ValueError: a kind of KINDS and an id of the shape that app gives (a number; a note's UUID)."""
    kind, item_id = str(kind or "").strip().lower(), str(item_id or "").strip()
    if kind not in KINDS:
        raise ValueError(f"No such kind of item: {kind[:20]!r}")
    if not (_ID.get(kind) or _NUM).fullmatch(item_id):
        raise ValueError(f"Not the id of a {KINDS[kind]['label'].lower()}: {item_id[:40]!r}")
    return kind, item_id.upper() if kind == "note" else item_id


# ------------------------------------------------------------------ the links themselves (ios_related)

def _pair(a: tuple, b: tuple) -> tuple:
    """The two ends in the order they are kept (one row for both ways)."""
    return (a, b) if a <= b else (b, a)


def add(a: tuple, b: tuple, by: int | None = None) -> int:
    """Link item a to item b (each (kind, id)); the link's id. Linking the same two again changes nothing."""
    a, b = check(*a), check(*b)
    if a == b:
        raise ValueError("An item cannot be linked to itself")
    if len(of(*a)) >= MAX_LINKS:
        raise ValueError(f"An item can have up to {MAX_LINKS} links")
    (ak, ai), (bk, bi) = _pair(a, b)
    db.ex("INSERT IGNORE INTO ios_related (a_kind, a_id, b_kind, b_id, created_by, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
          (ak, ai, bk, bi, by, int(time.time())))
    return int(db.one("SELECT id FROM ios_related WHERE a_kind = %s AND a_id = %s AND b_kind = %s AND b_id = %s", (ak, ai, bk, bi))["id"])


def of(kind: str, item_id) -> list[dict]:
    """The item's links, the newest first: [{link, kind, id, createdAt, createdBy}] (kind and id: the other end)."""
    kind, item_id = check(kind, item_id)
    rows = db.q("SELECT id, a_kind, a_id, b_kind, b_id, created_at, created_by FROM ios_related "
                "WHERE (a_kind = %s AND a_id = %s) OR (b_kind = %s AND b_id = %s) ORDER BY id DESC",
                (kind, item_id, kind, item_id))
    out = []
    for r in rows:
        other = (r["b_kind"], r["b_id"]) if (r["a_kind"], r["a_id"]) == (kind, item_id) else (r["a_kind"], r["a_id"])
        out.append({"link": int(r["id"]), "kind": other[0], "id": other[1], "createdAt": r["created_at"], "createdBy": r["created_by"]})
    return out


def remove(kind: str, item_id, link_id: int) -> bool:
    """Remove one of the item's links; whether there was one."""
    kind, item_id = check(kind, item_id)
    return bool(db.ex("DELETE FROM ios_related WHERE id = %s AND ((a_kind = %s AND a_id = %s) OR (b_kind = %s AND b_id = %s))",
                      (int(link_id), kind, item_id, kind, item_id)))


def forget(kind: str, item_id) -> int:
    """The item is gone for good: its links go too (how many). Never raises: the app's delete has happened."""
    try:
        kind, item_id = check(kind, item_id)
        return int(db.ex("DELETE FROM ios_related WHERE (a_kind = %s AND a_id = %s) OR (b_kind = %s AND b_id = %s)",
                         (kind, item_id, kind, item_id)) or 0)
    except Exception as e:  # noqa: BLE001
        log.warning("could not remove the links of %s %s: %s", kind, item_id, e)
        return 0


def forget_many(kind: str, ids) -> int:
    """forget() for many items of one kind (an app purging what was deleted)."""
    return sum(forget(kind, i) for i in ids)


# ------------------------------------------------------------------ asking the item's app, as the viewer

def _headers(request: Request, image: bool = False) -> dict:
    h = {"User-Agent": UA, "Accept": "image/*" if image else "application/json", "Accept-Encoding": "identity"}
    tok = request.cookies.get(sessions.COOKIE)
    if tok:
        h["Cookie"] = f"{sessions.COOKIE}={tok}"
    elif request.headers.get("authorization"):
        h["Authorization"] = request.headers["authorization"]
    try:
        h.update(links.headers("", "", sign_in=False))  # the suite's Cloudflare Access service token, when one is set
    except Exception:  # noqa: BLE001  the database is away
        pass
    return h


def _bases(app: str) -> list[str]:
    try:
        got = links.addresses(app)
    except Exception:  # noqa: BLE001
        got = []
    return got or ([links.url(app)] if links.url(app) else [])


def ask(request: Request, app: str, path: str, params: dict = None, image: bool = False, timeout: float = TIMEOUT):
    """GET path at the app as the viewer: its JSON, or (bytes, content type) for an image. Unavailable otherwise:
    the app's own status (a 401 there is a 403 here: signed in here, not let in there), 502 when it does not answer."""
    bases = _bases(app)
    if not bases:
        raise Unavailable(502, f"{app} is not in the suite's list of apps")
    query = "?" + urllib.parse.urlencode(params) if params else ""
    h = _headers(request, image)
    for i, base in enumerate(bases):
        try:
            with urllib.request.urlopen(urllib.request.Request(base + path + query, headers=h), timeout=timeout) as r:  # noqa: S310  http(s) from the suite's list
                body = r.read(8 << 20)
                return (body, r.headers.get("Content-Type", "")) if image else json.loads(body or b"null")
        except urllib.error.HTTPError as e:
            raise Unavailable(403 if e.code == 401 else e.code, f"{app} answered {e.code}") from None
        except (urllib.error.URLError, OSError, ValueError) as e:
            if i == len(bases) - 1:
                raise Unavailable(502, f"{app} does not answer ({e})") from None
    raise Unavailable(502, f"{app} does not answer")


# ------------------------------------------------------------------ what an item looks like: one function per kind

def _iso_epoch(ts) -> str | None:
    """ioPix keeps the camera's wall time as if it were UTC: the same wall time, without a zone."""
    try:
        return dt.datetime.fromtimestamp(float(ts), dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="minutes")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _lines(text) -> list[str]:
    return [s for s in (ln.strip().lstrip("#>*- ").strip() for ln in str(text or "").splitlines()) if s]


def _item(kind: str, item_id, title: str, text: str = "", when: str = None, all_day: bool = False, done: bool = False,
          image: str = None) -> dict:
    """An item as the panel shows it. image: the part of /api/related/image/<kind>/<id>?p= that names the picture
    ('' for the item's only one), None without one."""
    app = KINDS[kind]["app"]
    base = links.url(app) or ""
    href = {"event": "#/event/{}", "task": "#/task/{}", "note": "#/note/{}", "contact": "#/c/{}", "recipe": "#/recipe/{}",
            "photo": "#/photos?p={}"}[kind].format(urllib.parse.quote(str(item_id)))
    return {"kind": kind, "id": str(item_id), "app": app, "title": (title or "").strip()[:120] or "(no title)",
            "text": (text or "").strip()[:140], "when": when, "allDay": bool(all_day), "done": bool(done),
            "image": image, "url": f"{base}/{href}" if base else None}


def _event(x: dict) -> dict:
    nx = x.get("next") or {}
    return _item("event", x.get("id"), x.get("title"), x.get("location") or "", nx.get("start") or x.get("start"), x.get("allDay"))


def _task(t: dict) -> dict:
    return _item("task", t.get("id"), t.get("summary") or t.get("title"), "", t.get("due"), t.get("dueAllDay"),
                 done=bool(t.get("done") or t.get("completed")))


def _note(n: dict) -> dict:
    body = _lines(n.get("body")) or _lines(n.get("ocrText"))
    title = str(n.get("title") or "").strip()
    if not title:
        title, body = (body[0], body[1:]) if body else ("Picture" if n.get("hasImage") else "Untitled", [])
    when = dt.datetime.fromtimestamp(float(n["updatedAt"]), dt.timezone.utc).isoformat(timespec="minutes") if n.get("updatedAt") else None
    return _item("note", n.get("id"), title, body[0] if body else "", when, image="" if n.get("hasImage") else None)


def _contact(c: dict) -> dict:
    return _item("contact", c.get("id"), c.get("fn"), " · ".join(x for x in (c.get("title"), c.get("org")) if x),
                 image="" if c.get("hasPhoto") else None)


def _recipe(r: dict) -> dict:
    m = re.search(r"/photos/(\d+)$", str(r.get("photo") or ""))
    mins = r.get("totalMinutes")
    return _item("recipe", r.get("id"), r.get("title"), f"{mins} min" if mins else "", image=m.group(1) if m else None)


def _photo(p: dict) -> dict:
    album = (p.get("album") or {}).get("name") if isinstance(p.get("album"), dict) else None
    title = p.get("title") or p.get("caption") or album or p.get("name") or "Photo"
    return _item("photo", p.get("id"), title, album if album and album != title else "", _iso_epoch(p.get("ts")), image="")


def _soon_first(items: list[dict]) -> list[dict]:
    """Events: those still to come soonest first, then the ones that are over, the latest first."""
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="minutes")

    def key(x):
        return (x.get("when") or "")[:16]
    soon = sorted((x for x in items if key(x) >= now[:16 if not x.get("allDay") else 10]), key=key)
    past = sorted((x for x in items if key(x) < now[:16 if not x.get("allDay") else 10]), key=key, reverse=True)
    return soon + past


def find(request: Request, kind: str, q: str, n: int = 6) -> list[dict]:
    """The viewer's items of this kind that match q, as the panel shows them."""
    app, q = KINDS[kind]["app"], q.strip()[:80]
    if kind == "event":
        got = ask(request, app, "/api/events", {"q": q, "limit": 60})
        return _soon_first([_event(x) for x in got.get("items", [])])[:n]
    if kind == "task":
        open_, done = _together(lambda: ask(request, app, "/api/tasks", {"q": q, "status": "open", "limit": n}),
                                lambda: ask(request, app, "/api/tasks", {"q": q, "status": "done", "limit": n}))
        rows = [] if isinstance(open_, Exception) else open_.get("items", [])
        rows += [] if isinstance(done, Exception) else done.get("items", [])
        if isinstance(open_, Exception) and isinstance(done, Exception):
            raise open_
        return [_task(t) for t in rows[:n]]
    if kind == "note":
        return [_note(x) for x in ask(request, app, "/api/notes", {"q": q, "limit": n}).get("notes", [])[:n]]
    if kind == "contact":
        return [_contact(x) for x in ask(request, app, "/api/contacts", {"q": q, "limit": n}).get("items", [])[:n]]
    if kind == "recipe":
        return [_recipe(x) for x in ask(request, app, "/api/recipes", {"q": q, "limit": n}).get("items", [])[:n]]
    if kind == "photo":
        got = ask(request, app, "/api/photos", {"q": q, "type": "photo"})
        return [_photo({"id": pid, "ts": ts}) for pid, ts in list(zip(got.get("id") or [], got.get("ts") or []))[:max(n, 12)]]
    return []


def get(request: Request, kind: str, item_id: str) -> dict:
    """One item as the panel shows it; Unavailable when the viewer may not see it (or it is gone, or in the trash)."""
    app = KINDS[kind]["app"]
    q = urllib.parse.quote(item_id)
    if kind == "event":
        x = ask(request, app, f"/api/events/{q}")
        return _item("event", item_id, x.get("title"), x.get("location") or "", x.get("start"), x.get("allDay"))
    if kind == "task":
        return _task({**ask(request, app, f"/api/tasks/{q}"), "id": item_id})
    if kind == "note":
        n = ask(request, app, f"/api/notes/{q}")
        if n.get("deleted"):
            raise Unavailable(404, "That note is in the trash")
        return _note(n)
    if kind == "contact":
        return _contact(ask(request, app, f"/api/contacts/{q}"))
    if kind == "recipe":
        return _recipe(ask(request, app, f"/api/recipes/{q}"))
    if kind == "photo":
        return _photo(ask(request, app, f"/api/photo/{q}"))
    raise Unavailable(404, "No such kind of item")


def image(request: Request, kind: str, item_id: str, p: str = "") -> tuple[bytes, str]:
    """The item's small picture, from its app."""
    app, q = KINDS[kind]["app"], urllib.parse.quote(item_id)
    path, params = {"note": (f"/api/notes/{q}/thumb", None), "contact": (f"/api/contacts/{q}/photo", None),
                    "photo": (f"/thumb/{q}", {"fit": "square"}),
                    "recipe": (f"/api/recipes/{q}/photos/{p}", {"size": "small"}) if _NUM.fullmatch(p or "") else (None, None)}.get(kind, (None, None))
    if not path:
        raise Unavailable(404, "No picture")
    return ask(request, app, path, params, image=True, timeout=15)


def _together(*calls) -> list:
    out = []
    for f in [_pool.submit(c) for c in calls]:
        try:
            out.append(f.result())
        except Exception as e:  # noqa: BLE001 - handed to the caller
            out.append(e)
    return out


def available_kinds(user=None) -> list[str]:
    """The kinds whose app is in the suite's list (with an address) and lets this account in."""
    try:
        listed = {a["app"] for a in suite.visible(user) if a.get("url")}
    except Exception:  # noqa: BLE001
        return []
    return [k for k, v in KINDS.items() if v["app"] in listed]


def search(request: Request, q: str, kinds: list[str] = None, n: int = 6, user=None) -> list[dict]:
    """[{kind, label, items, error?}]: every app asked at the same time; one that does not answer (or lets the viewer in
    nowhere) gives an empty group with why."""
    have = available_kinds(user)
    want = [k for k in (kinds or have) if k in have]
    res = _together(*[(lambda k=k: find(request, k, q, n)) for k in want])
    out = []
    for k, r in zip(want, res):
        g = {"kind": k, "label": KINDS[k]["plural"], "items": [] if isinstance(r, Exception) else r}
        if isinstance(r, Exception):
            g["error"] = str(r) if isinstance(r, Unavailable) else "could not be searched"
            if not isinstance(r, Unavailable):
                log.warning("searching %s for links: %s", k, r)
        out.append(g)
    return out


def resolved(request: Request, kind: str, item_id: str) -> list[dict]:
    """The item's links as the viewer sees them: each other end asked of its app at the same time; the ones the viewer
    may not see (or that are gone, or whose app does not answer) are left out."""
    rows = of(kind, item_id)
    got = _together(*[(lambda r=r: get(request, r["kind"], r["id"])) for r in rows])
    return [{**g, "link": r["link"]} for r, g in zip(rows, got) if not isinstance(g, Exception)]


# ------------------------------------------------------------------ the routes

def router(auth) -> APIRouter:
    """/api/related/*, for an app of the suite (Auth.related_router())."""
    r = APIRouter()
    access = auth.access

    def me(request: Request) -> dict:
        """Who asks (the routes' access markers let them in; {} on an install without accounts yet, open to all)."""
        return auth.current_user(request) or {}

    writer = me  # access.member_write: a member or more

    def item(kind, item_id) -> tuple[str, str]:
        try:
            return check(kind, item_id)
        except ValueError as e:
            raise HTTPException(404, str(e)) from None

    def seen(request: Request, kind: str, item_id: str) -> dict:
        try:
            return get(request, kind, item_id)
        except Unavailable as e:
            raise HTTPException(404 if e.status in (403, 404) else e.status,
                                f"That {KINDS[kind]['label'].lower()} is not there, or you may not see it" if e.status in (403, 404) else str(e)) from None

    @r.get("/api/related/ui.js", include_in_schema=False, dependencies=[access.signed_in])
    def api_ui():
        """The panel (static/related-panel.js): "Linked" under an item, and the picker."""
        return FileResponse(Path(__file__).with_name("static") / "related-panel.js", media_type="text/javascript",
                            headers={"Cache-Control": "no-cache"})

    @r.get("/api/related/kinds", dependencies=[access.signed_in])
    def api_kinds(request: Request):
        """The kinds of items that can be linked here: those whose app is in the suite."""
        have = set(available_kinds(me(request)))
        return {"items": [{"kind": k, "label": v["label"], "plural": v["plural"], "app": v["app"]} for k, v in KINDS.items() if k in have]}

    @r.get("/api/related/search", dependencies=[access.signed_in])
    def api_search(request: Request, q: str = "", kinds: str = ""):
        """The picker: items of every app (or of kinds, comma-separated) that match q, grouped by kind."""
        u = me(request)
        if not q.strip():
            return {"groups": []}
        return {"groups": search(request, q, [k.strip() for k in kinds.split(",") if k.strip()] or None, user=u)}

    @r.get("/api/related/image/{kind}/{item_id}", dependencies=[access.signed_in])
    def api_image(kind: str, item_id: str, request: Request, p: str = ""):
        """An item's small picture, passed through from its app (the page shows pictures from its own address only)."""
        me(request)
        kind, item_id = item(kind, item_id)
        try:
            body, ctype = image(request, kind, item_id, p)
        except Unavailable as e:
            raise HTTPException(404 if e.status in (401, 403) else e.status, str(e)) from None
        return Response(body, media_type=ctype if ctype.startswith("image/") else "image/jpeg",
                        headers={"Cache-Control": "private, max-age=3600"})

    @r.get("/api/related/{kind}/{item_id}", dependencies=[access.signed_in])
    def api_links(kind: str, item_id: str, request: Request):
        """{items, canEdit}: the items linked to this one that you may see, the newest link first."""
        u = me(request)
        kind, item_id = item(kind, item_id)
        seen(request, kind, item_id)
        return {"items": resolved(request, kind, item_id), "canEdit": users.at_least(u, "member")}

    @r.post("/api/related/{kind}/{item_id}", dependencies=[access.member_write])
    async def api_add(kind: str, item_id: str, request: Request):
        """Link this item to {kind, id}: you must see both. The linked item as listed."""
        from starlette.concurrency import run_in_threadpool
        u = writer(request)
        kind, item_id = item(kind, item_id)
        b = await json_body(request)
        try:
            other = check(b.get("kind"), b.get("id"))
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

        def go():
            seen(request, kind, item_id)
            got = seen(request, *other)
            try:
                link = add((kind, item_id), other, u.get("id"))
            except ValueError as e:
                raise HTTPException(400, str(e)) from None
            return {**got, "link": link}
        return await run_in_threadpool(go)

    @r.delete("/api/related/{kind}/{item_id}/{link_id}", dependencies=[access.member_write])
    def api_remove(kind: str, item_id: str, link_id: int, request: Request):
        """Remove one of this item's links."""
        writer(request)
        kind, item_id = item(kind, item_id)
        seen(request, kind, item_id)
        if not remove(kind, item_id, link_id):
            raise HTTPException(404, "No such link")
        return {"ok": True}

    return r
