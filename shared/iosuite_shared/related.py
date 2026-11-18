"""Linked items: an event linked to its meeting notes, a task to a recipe, a note to a contact, across the apps.

A link joins two items of the suite, each named by its kind and its id in its app (KINDS: event, task, note, contact,
recipe, photo, item: a thing in ioThings, asset: a house, a car or another thing of value in ioMoney, transaction:
one of ioMoney's, what a thing was paid with, say; document: a paper kept in ioDocs, a passport or a policy). It is one row of ios_related in the Shared ioSuite database and
works both ways: the task shows the recipe and the recipe shows the task. Nothing about the items is kept with it; what a link shows (the title, the date,
the small picture) is asked of the item's own app every time, with the viewer's own sign-in, so a link shows only to
someone who may see both of its items, and always as the item is now. A note is its owner's alone: an event linked to
it shows the link to the note's owner and to nobody else.

Every app with items mounts the router (Auth.related_router(): /api/related/*) and its pages mount the panel
(GET /api/related/ui.js):

    const rel = await import(new URL('api/related/ui.js', document.baseURI).href);
    rel.mount(el, { kind: 'task', id: 12, toast });   // "Linked" under the task, and the picker behind its + button

The picker searches every app that has items (the same way the start page's search box does), the coming events
and the open tasks first. Adding or removing a link needs a role of member or more in the app the item is in, so it
is done there: an app asked about another app's kind (ioCalendar showing the ioMoney transaction that paid a bill)
passes the change on to that app as the viewer, where their role there counts (canEdit says whether it is one of
member or more), and both items must be ones the viewer sees. An app that
deletes an item for good calls forget(kind, id); one that gives an item a new id calls move(kind, old, new).

What an item looks like (its title, its line, its picture) is asked of its app at the suite's standard endpoints
(iosuite_shared.suiteitems: /api/suite/search with kinds=, /api/suite/items/{kind}/{id} and its /image), so nothing
here knows any app's own API: an app's manifest names its kinds of items, its provider answers for them.

The other app is asked on the viewer's behalf (iosuite_shared.links.as_viewer): on localhost when it runs on this
machine, then at its address inside the network, then at its public one, with the suite's Cloudflare Access service
token when one is set, and with the viewer's own credentials (the shared session cookie, or the Authorization header
the request came with), so each app answers with what that person may see there.
"""
import json
import logging
import re
import time
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response

from iosuite_shared import catalog, db, links, suite, users
from iosuite_shared.access import json_body

log = logging.getLogger("iosuite_shared.related")

# kind -> the app its items are in, what one is called, where one opens there: the apps' manifests (<app>/app.json "items")
KINDS = catalog.ITEMS
MAX_LINKS = 200  # links per item
TIMEOUT = 5      # seconds, per request to an app
UA = "ioSuite linked items"
_pool = ThreadPoolExecutor(max_workers=12, thread_name_prefix="related")
_UUID = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")
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
    if not (_UUID if KINDS[kind].get("id") == "uuid" else _NUM).fullmatch(item_id):
        raise ValueError(f"Not the id of a {KINDS[kind]['label'].lower()}: {item_id[:40]!r}")
    return kind, item_id.upper() if KINDS[kind].get("id") == "uuid" else item_id


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


def having(kind: str, ids) -> list[str]:
    """Which of these items of one kind have links (an app about to remove many of them, asking which to forget)."""
    try:
        ids = sorted({check(kind, i)[1] for i in ids})
    except ValueError:
        return []
    out: set = set()
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        marks = ", ".join(["%s"] * len(part))
        for r in db.q(f"SELECT a_id AS id FROM ios_related WHERE a_kind = %s AND a_id IN ({marks}) "
                      f"UNION SELECT b_id FROM ios_related WHERE b_kind = %s AND b_id IN ({marks})", (kind, *part, kind, *part)):
            out.add(str(r["id"]))
    return sorted(out)


def forget_many(kind: str, ids) -> int:
    """forget() for many items of one kind (an app purging what was deleted)."""
    return sum(forget(kind, i) for i in ids)


def move(kind: str, old_id, new_id) -> int:
    """The item lives on under another id (an event moved to another calendar is a new event there, as CalDAV sees
    it): its links follow it (how many). Never raises: the app's move has happened."""
    try:
        kind, old_id = check(kind, old_id)
        new = check(kind, new_id)
        links = of(kind, old_id)
        for link in links:
            (ak, ai), (bk, bi) = _pair(new, (link["kind"], link["id"]))
            db.ex("INSERT IGNORE INTO ios_related (a_kind, a_id, b_kind, b_id, created_by, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
                  (ak, ai, bk, bi, link["createdBy"], link["createdAt"]))
        forget(kind, old_id)
        return len(links)
    except Exception as e:  # noqa: BLE001
        log.warning("could not move the links of %s %s to %s: %s", kind, old_id, new_id, e)
        return 0


# ------------------------------------------------------------------ asking the item's app, as the viewer

def ask(request: Request, app: str, path: str, params: dict = None, image: bool = False, timeout: float = TIMEOUT):
    """GET path at the app as the viewer (links.as_viewer): its JSON, or (bytes, content type) for an image.
    Unavailable otherwise: the app's own status (a 401 there is a 403 here: signed in here, not let in there), 502
    when it does not answer."""
    try:
        return links.as_viewer(request, app, path, params, raw=image, accept="image/*" if image else None, timeout=timeout,
                               user_agent=UA, patient=True, public=True, limit=8 << 20)
    except urllib.error.HTTPError as e:
        raise Unavailable(403 if e.code == 401 else e.code if e.code >= 400 else 502, f"{app} answered {e.code}") from None
    except (urllib.error.URLError, OSError) as e:
        raise Unavailable(502, str(getattr(e, "reason", "")) or f"{app} does not answer") from None


# ------------------------------------------------------------------ what an item looks like: its app says (/api/suite/*)

def _shown(kind: str, x: dict) -> dict:
    """An item as its app answers it (iosuite_shared.suiteitems), as the panel shows it: its address in its app, and
    money said in its line."""
    app = KINDS[kind]["app"]
    base = links.url(app) or ""
    text = str(x.get("text") or "")
    if isinstance(x.get("amount"), (int, float)):
        text = " · ".join(t for t in (f"{x.get('currency') or ''} {float(x['amount']):,.2f}".strip(), text) if t)
    return {"kind": kind, "id": str(x.get("id")), "app": app, "appName": catalog.name_of(app), "title": x.get("title") or "(no title)",
            "text": text[:140], "when": x.get("when"), "allDay": bool(x.get("allDay")), "done": bool(x.get("done")),
            "image": x.get("image"), "url": f"{base}/{x['href']}" if base and x.get("href") else None}


def find(request: Request, kind: str, q: str, n: int = 6) -> list[dict]:
    """The viewer's items of this kind that match q, as the panel shows them (the coming ones first)."""
    got = ask(request, KINDS[kind]["app"], "/api/suite/search", {"q": q.strip()[:80], "n": n, "kinds": kind})
    rows = got.get("items", []) if isinstance(got, dict) else []
    return [_shown(kind, x) for x in rows if x.get("kind") == kind]


def get(request: Request, kind: str, item_id: str) -> dict:
    """One item as the panel shows it; Unavailable when the viewer may not see it (or it is gone, or in the trash)."""
    return _shown(kind, ask(request, KINDS[kind]["app"], f"/api/suite/items/{kind}/{urllib.parse.quote(item_id)}"))


def image(request: Request, kind: str, item_id: str, p: str = "") -> tuple[bytes, str]:
    """The item's small picture, from its app."""
    return ask(request, KINDS[kind]["app"], f"/api/suite/items/{kind}/{urllib.parse.quote(item_id)}/image", {"p": p[:40]} if p else None,
               image=True, timeout=15)


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

    def own(kind: str) -> bool:
        """Whether items of this kind are this app's: an item's links are changed in its own app, where the role that
        lets someone change it is the one they have (the member of one app is not one of every other)."""
        return KINDS[kind]["app"] == auth.app

    def may_change(u: dict, kind: str) -> bool:
        """Another app's item: its links change there (theirs()), for a member or more of that app."""
        if own(kind) or not users.any_users():
            return True
        return users.RANK.get(users.role_of(u, KINDS[kind]["app"]), 0) >= users.RANK["member"]

    def theirs(request: Request, kind: str, item_id: str, tail: str = "", body: dict = None, method: str = None):
        """The item is another app's: the same request, made there as the viewer (that app checks the role it gives)."""
        path = f"/api/related/{kind}/{urllib.parse.quote(item_id)}{tail}"
        try:
            return links.as_viewer(request, KINDS[kind]["app"], path, body=body, method=method, timeout=TIMEOUT,
                                   user_agent=UA, public=True)
        except urllib.error.HTTPError as e:
            why = f"{catalog.name_of(KINDS[kind]['app'])} answered {e.code}"
            try:
                why = str(json.loads(e.read() or b"{}").get("detail") or why)
            except Exception:  # noqa: BLE001 - not JSON: its status says it
                pass
            raise HTTPException(403 if e.code == 401 else e.code if e.code >= 400 else 502, why) from None
        except (urllib.error.URLError, OSError) as e:
            raise HTTPException(502, str(getattr(e, "reason", "")) or f"{catalog.name_of(KINDS[kind]['app'])} does not answer") from None

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
        return {"items": resolved(request, kind, item_id), "canEdit": users.at_least(u, "member") and may_change(u, kind)}

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
        if not own(kind):
            return await run_in_threadpool(theirs, request, kind, item_id, "", {"kind": other[0], "id": other[1]})

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
        if not own(kind):
            return theirs(request, kind, item_id, f"/{int(link_id)}", method="DELETE")
        seen(request, kind, item_id)
        if not remove(kind, item_id, link_id):
            raise HTTPException(404, "No such link")
        return {"ok": True}

    return r
