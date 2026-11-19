"""What the tiles show under their name: a glimpse of each app (ioPix's On this day, ioCalendar's today, ioHealth's
steps and rings, ioMoney's bills of the week), what the search box finds in them, and what it adds to them (an event,
a task, a note).

The tile, the search and the pictures are asked at the suite's standard endpoints, which every app answers in one
shape (iosuite_shared.suiteitems: /api/suite/tile, /api/suite/search, /api/suite/items/{kind}/{id}/image), so
nothing here knows an app's own API; the app's manifest (app.json "start") says whether it has a tile and a search.
Adding an event, a task or a note goes to that app's own API (quick add).

The start page asks on the viewer's behalf: the request goes out from this server with the viewer's own credentials
(the suite's shared session cookie, or the Authorization header they came with), so each app answers with what that
person may see there and nothing more. Nothing is kept here. The browser never talks to the apps itself (the page's
Content-Security-Policy allows only this origin), so ioPix's thumbnails come through here too.

The app is found in the suite's list of apps and asked on the viewer's behalf (iosuite_shared.links.as_viewer): on
localhost when it runs on this machine, then at its address inside the network, then at its public one; the suite's
Cloudflare Access service token goes with every request when one is set (Settings › Global settings › Keys and
tokens). Only the address and the Cloudflare headers come from there: the credentials stay the viewer's own.

Every app is asked with a short timeout: an app that is down, or that this account has no access to, leaves its tile
as it was (the page hides the block) instead of holding up the others. An app that did not answer at any of its
addresses is left alone for links.BREAK_S seconds (the tile says so at once, no thread waits for it again), the address
that answered last is tried first, and a tile that needs several answers asks for them at the same time.
"""
import datetime as dt
import json
import re
import urllib.error

from fastapi import Request
from iosuite_shared import catalog, links

from app import apps

TIMEOUT = 4  # seconds, per request to an app
UA = "ioStart page"


class Unavailable(Exception):
    """The app could not be asked, or would not answer: (status, why). An app's 401 is a 403 here: the viewer is signed
    in to the start page, just not let in there (a 401 would send the page to its sign-in)."""

    def __init__(self, status: int, why: str):
        super().__init__(why)
        self.status = status


def _host(request: Request) -> str:
    return request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc


def forget() -> None:
    """Every app may be asked again, from its first address on (the tests; an admin changed the addresses)."""
    links.ask_again()


def fetch(request: Request, key: str, path: str, params: dict | None = None, raw: bool = False, body: dict | None = None, timeout: float = TIMEOUT):
    """GET path from the app (JSON, or (bytes, content type) with raw); with body, POST that JSON instead."""
    name = apps.name_of(key)
    wait = links.resting(key)
    if wait > 0:
        raise Unavailable(502, f"{name} did not answer a moment ago (asked again in {int(wait) + 1} s)")
    try:
        # a picture that took too long says nothing about the app (patient)
        return links.as_viewer(request, key, path, params, body, raw=raw, accept="image/*" if raw else None, timeout=timeout,
                               user_agent=UA, patient=raw, public=True)
    except urllib.error.HTTPError as e:
        if body is not None and e.code in (400, 403, 409):  # ioCalendar's own word on what it would not take
            try:
                why = json.loads(e.read()).get("detail")
            except (ValueError, AttributeError):
                why = None
            raise Unavailable(400, why if isinstance(why, str) else f"{name} would not take it ({e.code})")
        if e.code in (401, 403):
            raise Unavailable(403, f"{name} does not let this account in ({e.code}); open it once and sign in there")
        if e.code == 404:
            raise Unavailable(404, f"{name} has no {path} (is the address {name}'s?)")
        raise Unavailable(502, f"{name} answered {e.code}")
    except links.Unreachable as e:
        raise Unavailable(502, f"{name} is not reachable at {e.at or '(no address)'} ({type(e.why or e).__name__})")


# ------------------------------------------------------------------ ioCalendar: a new event from the search box

def iocalendar_calendars(request: Request) -> dict:
    """{items: [{id, name, color}]}: the calendars this viewer may add events to, as ioCalendar lists them (its own
    order, so the first is where ioCalendar itself would put a new event)."""
    got = fetch(request, "iocalendar", "/api/calendars")
    return {"items": [{"id": c.get("id"), "name": c.get("name"), "color": c.get("color")} for c in got.get("items", []) if c.get("writable")]}


def iocalendar_add(request: Request, b: dict) -> dict:
    """A new event in ioCalendar, from {title, start, end?, allDay, timezone?, calendarId?}: start / end are ISO
    (a date for an all-day event, a date and time with its offset otherwise); no end is an hour (or the day).
    {id, url}: the event and where it opens in ioCalendar."""
    if not isinstance(b, dict):
        raise Unavailable(400, "An object, please")
    title = str(b.get("title") or "").strip()[:500]
    start = str(b.get("start") or "").strip()
    if not title or not start:
        raise Unavailable(400, "A title and a start, please")
    all_day = bool(b.get("allDay"))
    try:
        if all_day:
            dt.date.fromisoformat(start[:10])
        else:
            dt.datetime.fromisoformat(start)
        if b.get("end"):
            (dt.date.fromisoformat if all_day else dt.datetime.fromisoformat)(str(b["end"])[:10] if all_day else str(b["end"]))
    except ValueError:
        raise Unavailable(400, "start / end: ISO dates (and times)")
    ev = {"title": title, "start": start[:10] if all_day else start, "allDay": all_day}
    if b.get("end"):
        ev["end"] = str(b["end"])[:10] if all_day else str(b["end"])
    tz = str(b.get("timezone") or "")
    if tz and re.fullmatch(r"[A-Za-z0-9_+\-/]{1,64}", tz):
        ev["timezone"] = tz
    if b.get("calendarId") not in (None, ""):
        ev["calendarId"] = b["calendarId"]
    got = fetch(request, "iocalendar", "/api/events", body=ev)
    eid = got.get("id") if isinstance(got, dict) else None
    return {"id": eid, "url": f"{apps.url_for('iocalendar')}/#/event/{eid}" if eid is not None else None}


# ------------------------------------------------------------------ ioTask and ioNote: a new task, a new note from the search box

def iotask_lists(request: Request) -> dict:
    """{items: [{id, name, color}]}: the lists this viewer may add tasks to, in ioTask's own order (the first is where
    ioTask itself would put a new task)."""
    got = fetch(request, "iotask", "/api/lists")
    return {"items": [{"id": c.get("id"), "name": c.get("name"), "color": c.get("color")} for c in got.get("items", []) if c.get("writable")]}


def iotask_add(request: Request, b: dict) -> dict:
    """A new task in ioTask, from {title, due?, listId?, timezone?}: due is a date (2026-11-21) or a date and time
    (2026-11-21T17:00, in timezone). {id, url}: the task and where it opens in ioTask."""
    if not isinstance(b, dict):
        raise Unavailable(400, "An object, please")
    title = str(b.get("title") or "").strip()[:500]
    if not title:
        raise Unavailable(400, "A title, please")
    task = {"title": title}
    due = str(b.get("due") or "").strip()
    if due:
        try:
            (dt.date.fromisoformat if len(due) == 10 else dt.datetime.fromisoformat)(due)
        except ValueError:
            raise Unavailable(400, "due: a date (2026-11-21) or a date and time (2026-11-21T17:00)")
        task["due"] = due
    tz = str(b.get("timezone") or "")
    if tz and re.fullmatch(r"[A-Za-z0-9_+\-/]{1,64}", tz):
        task["timezone"] = tz
    if b.get("listId") not in (None, ""):
        task["listId"] = b["listId"]
    got = fetch(request, "iotask", "/api/tasks", body=task)
    tid = got.get("id") if isinstance(got, dict) else None
    return {"id": tid, "url": f"{apps.url_for('iotask')}/#/task/{tid}" if tid is not None else None}


def ionote_add(request: Request, b: dict) -> dict:
    """A new note in ioNote, the viewer's own, from {title?, text?} (one of the two at least). {id, url}."""
    if not isinstance(b, dict):
        raise Unavailable(400, "An object, please")
    title, text = str(b.get("title") or "").strip()[:500], str(b.get("text") or "").strip()[:20000]
    if not title and not text:
        raise Unavailable(400, "A title or some text, please")
    got = fetch(request, "ionote", "/api/notes", body={"title": title, "body": text, "sourceApp": "ioStart"})
    nid = got.get("id") if isinstance(got, dict) else None
    return {"id": nid, "url": f"{apps.url_for('ionote')}/#/note/{nid}" if nid is not None else None}


# ------------------------------------------------------------------ the tiles, the search box, the pictures: /api/suite/*

def _start(key: str) -> dict:
    return (catalog.APPS.get(key) or {}).get("start") or {}


def image(request: Request, key: str, kind: str, item_id: str, p: str = "") -> tuple[bytes, str]:
    """An item's picture, from its app (a photo, a contact's face, a recipe's or a thing's picture)."""
    if not re.fullmatch(r"[a-z_]{2,30}", kind or "") or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", item_id or ""):
        raise Unavailable(404, "No such item")
    return fetch(request, key, f"/api/suite/items/{kind}/{item_id}/image", {"p": p[:40]} if p else None, raw=True,
                 timeout=20 if p == "preview" else TIMEOUT)


def get(request: Request, key: str, tz: str = "", kind: str = "", n: int = 0, q: str = "") -> dict:
    """The app's tile (kind and n as the app takes them), or with q what it finds for the search box."""
    st = _start(key)
    if tz and not re.fullmatch(r"[A-Za-z0-9_+\-/]{1,64}", tz):
        tz = ""
    if q.strip():
        if not st.get("find"):
            raise Unavailable(404, f"{apps.name_of(key)} has nothing to search here")
        return fetch(request, key, "/api/suite/search", {"q": q.strip()[:80], "n": 5, "tz": tz} if tz else {"q": q.strip()[:80], "n": 5})
    if not st.get("tile"):
        raise Unavailable(404, f"{apps.name_of(key)} shows only in the search box" if st.get("find") else f"{key} has nothing to show here")
    params = {k: v for k, v in (("tz", tz), ("kind", re.sub(r"[^a-z0-9:]", "", kind)[:20]), ("n", max(0, min(int(n or 0), 24)))) if v}
    return fetch(request, key, "/api/suite/tile", params)
