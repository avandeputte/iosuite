"""The REST API (JSON; iCalendar and jCal by content negotiation), the subscription links and the settings the web app
uses. OpenAPI docs at /api/docs.

Clients authenticate with the web session cookie, HTTP Basic (name + password or app password) or
`Authorization: Bearer <app password>`. Events are JSON by default; ask for text/calendar or application/calendar+json
(jCal, RFC 7265) with Accept or ?format=ics|jcal, and send either of them (or JSON) to create or change one.
"""
import copy
import datetime as dt
import json
import re

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

from app import APP_VERSION, config, contacts, db, ical, model, updates, users

router = APIRouter()

ICS_TYPE = "text/calendar"
JCAL_TYPE = "application/calendar+json"


# ------------------------------------------------------------------ helpers

def me(request: Request) -> dict:
    u = request.state.user
    if not u:
        raise HTTPException(401, "Sign in first")
    return u


def admin(request: Request) -> dict:
    u = me(request)
    if not users.is_admin(u):
        raise HTTPException(403, "Admins only")
    return u


def readable_calendar(u: dict, cid) -> dict:
    c = model.calendar(int(cid)) if str(cid).isdigit() else None
    if not model.can_read(u, c):
        raise HTTPException(404, "No such calendar")
    return c


def writable_calendar(u: dict, cid) -> dict:
    c = readable_calendar(u, cid)
    if not model.can_write(u, c):
        raise HTTPException(403, "The Birthdays calendar comes from ioContacts" if c.get("kind") == "birthdays"
                            else "Viewers can only change their own private calendars")
    return c


def readable_event(u: dict, eid: int) -> tuple[dict, dict]:
    r = model.get_row(eid)
    c = model.calendar(r["calendar_id"]) if r else None
    if not r or r["deleted"] or not model.can_read(u, c):
        raise HTTPException(404, "No such event")
    return r, c


def writable_event(u: dict, eid: int) -> tuple[dict, dict]:
    r, c = readable_event(u, eid)
    if not model.can_write(u, c):
        raise HTTPException(403, "You can see this event but not change it")
    return r, c


def visible(u: dict, ids: str | None = None) -> list[dict]:
    cals = model.calendars_for(u)
    if ids:
        want = {int(x) for x in re.split(r"[,\s]+", ids) if x.strip().isdigit()}
        cals = [c for c in cals if c["id"] in want]
    return cals


def wants(request: Request, fmt: str | None) -> str:
    if fmt:
        return {"ics": "ics", "ical": "ics", "icalendar": "ics", "jcal": "jcal", "json": "json"}.get(fmt.lower(), "json")
    acc = request.headers.get("accept", "")
    if JCAL_TYPE in acc:
        return "jcal"
    if ICS_TYPE in acc:
        return "ics"
    return "json"


def _base(request: Request) -> str:
    if config.PUBLIC_URL:
        return config.PUBLIC_URL
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def _when(s: str | None, name: str) -> dt.datetime:
    if not s:
        raise HTTPException(400, f"{name} is missing (an ISO date or date-time)")
    try:
        d = ical.parse_when(s, "UTC")
    except ValueError:
        raise HTTPException(400, f"{name} is not an ISO date or date-time: {s}")
    return ical.to_utc(d)


async def body_object(request: Request) -> tuple[dict | None, object | None]:
    """The request body as (JSON fields, None) or (None, a parsed iCalendar object) from text/calendar or jCal."""
    ct = request.headers.get("content-type", "").split(";")[0].strip().lower()
    raw = await request.body()
    if len(raw) > config.MAX_EVENT_BYTES:
        raise HTTPException(413, "That event is too large")
    try:
        if ct in (ICS_TYPE, "text/x-vcalendar", "application/ics") or raw.lstrip()[:15].upper() == b"BEGIN:VCALENDAR":
            return None, ical.parse(raw)
        data = json.loads(raw or b"{}")
        if ct == JCAL_TYPE or (isinstance(data, list) and data[:1] == ["vcalendar"]):
            return None, ical.from_jcal(data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not isinstance(data, dict):
        raise HTTPException(400, "Expected an event object, iCalendar or jCal")
    return data, None


def event_response(request: Request, r: dict, fmt: str | None = None, status: int = 200, recurrence_id: str | None = None):
    f = wants(request, fmt)
    headers = {"ETag": f'"{r["etag"]}"'}
    if f == "ics":
        return Response(r["ics"], status_code=status, media_type="text/calendar; charset=utf-8", headers=headers)
    if f == "jcal":
        return JSONResponse(ical.to_jcal(model.parsed(r)), status_code=status, media_type=JCAL_TYPE, headers=headers)
    return JSONResponse(event_out(r, recurrence_id), status_code=status, headers=headers)


def event_out(r: dict, recurrence_id: str | None = None) -> dict:
    j = model.event_out(r, recurrence_id=recurrence_id)
    for p in j["people"]:
        if p.get("contactId"):
            p["contactUrl"] = contacts.contact_url(p["contactId"])
    return j


def _check_match(request: Request, r: dict) -> None:
    h = request.headers.get("if-match")
    if h and h.strip() != "*" and r["etag"] not in [t.strip().removeprefix("W/").strip('"') for t in h.split(",")]:
        raise HTTPException(412, "The event was changed meanwhile (If-Match does not match its ETag); load it again")


# ------------------------------------------------------------------ status and the account

@router.get("/api/status")
def status(request: Request):
    u = request.state.user
    adm = users.is_admin(u)
    return {"app": "ioCalendar", "version": APP_VERSION, "commit": updates.local_commit()[:7] if u else None,
            "usersExist": users.any_users(), "user": users.public(u), "timezone": ical.default_tz(),
            "iocontacts": contacts.enabled() if u else None, "viaProxy": getattr(request.state, "via_proxy", False),
            "mcp": mcp_enabled() if u else None,
            "updateAvailable": updates.available() if adm and updates.auto_check_enabled() else None}


def mcp_enabled() -> bool:
    """Settings › Server › MCP server: off until an admin turns it on (or MCP=1 in the environment)."""
    if config.MCP_FORCED:
        return True
    try:
        return db.get_setting("mcp_enabled", "0") == "1"
    except Exception:  # noqa: BLE001
        return False


@router.patch("/api/auth/me")
async def patch_me(request: Request):
    """Your display name and email (sign-in at a proxy matches the email)."""
    u = me(request)
    b = await request.json()
    f = {}
    if "displayName" in b:
        f["display_name"] = (b["displayName"] or "").strip() or None
    if "email" in b:
        f["email"] = (b["email"] or "").strip() or None
    try:
        nu = await run_in_threadpool(lambda: users.update(u["id"], **f))
    except ValueError as e:
        raise HTTPException(400, str(e))
    users.forget_cached_auth()
    return {"user": users.public(nu)}


# ------------------------------------------------------------------ the server: version, updates, MCP

@router.get("/api/server")
def server_info(request: Request):
    """Admins: the installed version, the last update check, whether update.sh can run here, and the switches."""
    admin(request)
    return {**updates.status(), "mcpEnabled": mcp_enabled(), "mcpLocked": config.MCP_FORCED, "mcpUrl": f"{_base(request)}/mcp",
            "timezone": ical.default_tz(), "database": f"{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"}


@router.post("/api/server")
async def server_action(request: Request):
    """Admins. Body: {action: check | update, ref?} or {mcpEnabled: bool} / {autoCheck: bool}."""
    admin(request)
    b = await request.json()
    if "mcpEnabled" in b:
        if config.MCP_FORCED and not b["mcpEnabled"]:
            raise HTTPException(400, "MCP=1 in the environment keeps the MCP server on")
        db.set_setting("mcp_enabled", "1" if b["mcpEnabled"] else "0")
    if "autoCheck" in b:
        if config.UPDATE_CHECK_LOCKED and b["autoCheck"]:
            raise HTTPException(400, "UPDATE_CHECK=0 in the environment keeps the daily check off")
        db.set_setting("update_check", "1" if b["autoCheck"] else "0")
        if not b["autoCheck"]:
            updates.forget_check()
    action = b.get("action")
    if action == "check":
        return await run_in_threadpool(updates.check)
    if action == "update":
        try:
            updates.run(str(b.get("ref") or ""))
        except RuntimeError as e:
            raise HTTPException(409, str(e))
        return {"started": True}
    return server_info(request)


# ------------------------------------------------------------------ calendars

@router.get("/api/calendars")
def list_calendars(request: Request):
    u = me(request)
    return {"items": [model.calendar_public(c, u) for c in model.calendars_for(u)]}


@router.post("/api/calendars")
async def add_calendar(request: Request):
    """{name, color?, description?, timezone?, shared?}: shared calendars are made by editors and admins."""
    u = me(request)
    b = await request.json()
    shared = bool(b.get("shared"))
    if shared and not users.can_write(u):
        raise HTTPException(403, "Only editors make shared calendars")
    if not (b.get("name") or "").strip():
        raise HTTPException(400, "A name, please")
    cid = model.create_calendar(None if shared else u["id"], b["name"], b.get("description"), b.get("color"), timezone=b.get("timezone"))
    c = model.calendar(cid)
    c["n"] = 0
    return JSONResponse({"calendar": model.calendar_public(c, u)}, status_code=201)


@router.patch("/api/calendars/{cid}")
async def edit_calendar(cid: int, request: Request):
    u = me(request)
    writable_calendar(u, cid)
    b = await request.json()
    model.update_calendar(cid, **{k: b[k] for k in ("name", "description", "color", "timezone", "sort") if k in b})
    return {"calendar": model.calendar_public(model.calendar(cid), u)}


@router.delete("/api/calendars/{cid}")
def del_calendar(cid: int, request: Request):
    u = me(request)
    c = writable_calendar(u, cid)
    if model.is_shared(c) and not users.is_admin(u):
        raise HTTPException(403, "Only an admin deletes a shared calendar")
    if model.is_shared(c) and len([x for x in model.calendars_for(u) if x["owner_id"] is None and x["kind"] == "events"]) <= 1:
        raise HTTPException(400, "The last shared calendar stays")
    if not model.is_shared(c) and len([x for x in model.calendars_for(u) if x["owner_id"] == u["id"]]) <= 1:
        raise HTTPException(400, "Your last private calendar stays")
    model.delete_calendar(cid)
    return {"ok": True}


@router.get("/api/calendars/{cid}/export")
def export_calendar(cid: int, request: Request):
    """The whole calendar as one .ics file."""
    c = readable_calendar(me(request), cid)
    name = re.sub(r"[^A-Za-z0-9 _-]", "", c["name"]).strip() or "calendar"
    return Response(model.export_text([c], c["name"]), media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}-{dt.date.today().isoformat()}.ics"'})


@router.post("/api/calendars/{cid}/import")
async def import_calendar(cid: int, request: Request, replace: bool = True):
    """An .ics file (multipart field `file`, or a text/calendar body) into this calendar. Events whose UID the calendar
    has already are updated (replace=false: skipped)."""
    u = me(request)
    writable_calendar(u, cid)
    ct = request.headers.get("content-type", "")
    if ct.startswith("multipart/"):
        form = await request.form()
        f = form.get("file")
        if f is None or not hasattr(f, "read"):
            raise HTTPException(400, "No file")
        raw = await f.read()
    else:
        raw = await request.body()
    if len(raw) > config.MAX_IMPORT_BYTES:
        raise HTTPException(413, "That file is too large")
    try:
        return await run_in_threadpool(model.import_text, cid, raw.decode("utf-8", "replace"), u["id"], replace)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ------------------------------------------------------------------ occurrences, events

@router.get("/api/occurrences")
def occurrences(request: Request, start: str, end: str, calendars: str | None = None, q: str = ""):
    """Every occurrence between start and end (ISO dates or date-times; repeating events expanded, changed occurrences
    and left-out dates applied), from the calendars named (ids, comma-separated) or all you see."""
    u = me(request)
    s, e = _when(start, "start"), _when(end, "end")
    if e <= s:
        raise HTTPException(400, "end is before start")
    if e - s > dt.timedelta(days=800):
        raise HTTPException(400, "At most about two years at a time")
    return {"items": model.occurrences(visible(u, calendars), s, e, q)}


@router.get("/api/events")
def list_events(request: Request, q: str = "", calendar: str | None = None, limit: int = 100, format: str | None = None):
    """Events (not their occurrences) matching q in their title, place, notes or people, newest first, with the next
    occurrence of each; with Accept: text/calendar (or ?format=ics) one .ics with all of them."""
    u = me(request)
    cals = visible(u, calendar)
    rows = model.search_rows([c["id"] for c in cals], q, max(1, min(limit, 5000)))
    if wants(request, format) == "ics":
        return Response(ical.feed([r["ics"] for r in rows], "ioCalendar"), media_type="text/calendar; charset=utf-8")
    out = []
    for r in rows:
        out.append({"id": r["id"], "calendarId": r["calendar_id"], "title": r["summary"], "location": r["location"],
                    "allDay": bool(r["all_day"]), "recurring": bool(r["rrule"]), "next": model.next_occurrence(r)})
    return {"items": out}


@router.post("/api/events")
async def create_event(request: Request, calendar: str | None = None):
    """A new event in ?calendar= (or the calendarId field; else your first calendar you may change), from JSON fields
    (title, start, end, allDay, timezone, location, notes, people, reminders, rrule...), iCalendar or jCal."""
    u = me(request)
    data, cal = await body_object(request)
    cid = calendar or (data or {}).get("calendarId")
    if not cid:
        mine = [c for c in model.calendars_for(u) if model.can_write(u, c)]
        if not mine:
            raise HTTPException(403, "You cannot add events anywhere")
        cid = mine[0]["id"]
    c = writable_calendar(u, cid)
    try:
        if cal is None:
            cal = ical.build(data, c.get("timezone"))
        else:
            ical.finish(cal)
        uid = ical.index(cal, c.get("timezone"))["uid"]
    except ValueError as e:
        raise HTTPException(400, str(e))
    if model.by_uid(c["id"], uid):
        raise HTTPException(409, "That calendar already has an event with this UID")
    r = await run_in_threadpool(model.save, c["id"], cal, None, None, u["id"])
    return event_response(request, r, None, 201)


@router.get("/api/events/{eid}")
def get_event(eid: int, request: Request, format: str | None = None, recurrenceId: str | None = None):
    r, _ = readable_event(me(request), eid)
    return event_response(request, r, format, recurrence_id=recurrenceId)


def _occurrence_start(cal, recurrence_id: str):
    """Where an occurrence is now (its changed start, or the series' own)."""
    comps = ical.events_of(cal)
    ov = ical._find_override(comps, recurrence_id)
    if ov is not None:
        return ical._start_end(ov)
    m = ical.master_of(comps)
    s0, e0 = ical._start_end(m)
    rid = ical._rid_value(m, ical.parse_rid(recurrence_id))
    return rid, rid + (e0 - s0)


def _shift_series(cal, data: dict, recurrence_id: str, tzname) -> dict:
    """An edit made on one occurrence but meant for the whole series: a new start or end moves every occurrence by the
    same amount (or gives each the new times of day)."""
    if not any(k in data for k in ("start", "end")):
        return data
    m = ical.master_of(ical.events_of(cal))
    ms, me_ = ical._start_end(m)
    os_, oe = _occurrence_start(cal, recurrence_id)
    all_day = data.get("allDay", not isinstance(ms, dt.datetime))
    tz = data.get("timezone") or ical.tz_name(ms) or tzname
    try:
        ns = ical.parse_when(data.get("start") or ical.iso(os_), tz, bool(all_day))
        ne = ical.parse_when(data.get("end") or ical.iso(oe), tz, bool(all_day))
    except ValueError as e:
        raise HTTPException(400, str(e))
    out = dict(data)
    if isinstance(ns, dt.datetime) and isinstance(os_, dt.datetime):
        delta = ns - os_.astimezone(ns.tzinfo) if os_.tzinfo else ns.replace(tzinfo=None) - os_
        nms = (ms if ms.tzinfo else ms.replace(tzinfo=ns.tzinfo)).astimezone(ns.tzinfo) + delta
    else:
        d0 = os_.date() if isinstance(os_, dt.datetime) else os_
        d1 = ns.date() if isinstance(ns, dt.datetime) else ns
        base = ms.date() if isinstance(ms, dt.datetime) else ms
        nms = base + (d1 - d0)
        if isinstance(ns, dt.datetime):
            nms = dt.datetime.combine(nms, ns.timetz())
    out["start"] = ical.iso(nms)
    out["end"] = ical.iso(nms + (ne - ns))
    return out


def change(u: dict, r: dict, c: dict, data: dict, partial: bool = True, scope: str = "all",
           recurrence_id: str | None = None) -> tuple[dict, str | None, bool]:
    """Change an event from JSON fields, for the series or (with recurrence_id) one occurrence (scope this) or it and
    the ones after (scope following: the series is split, and the new one is returned). ValueError with the message to
    show, PermissionError when a calendar may not be changed. (row, the occurrence the row is shown for, made new)."""
    tzname = c.get("timezone")
    if data.get("calendarId") not in (None, "") and int(data["calendarId"]) != r["calendar_id"]:
        target = model.calendar(int(data["calendarId"]))
        if not model.can_write(u, target):
            raise PermissionError("You cannot add events to that calendar")
        r = model.move(r["id"], target["id"])
        c = target
        tzname = c.get("timezone")
    data = {k: v for k, v in data.items() if k in ical.EDITABLE}
    cal = copy.deepcopy(model.parsed(r))
    if not partial:  # a full replacement: fields left out are cleared
        for k in ("location", "notes", "url", "people", "reminders", "rrule", "categories"):
            data.setdefault(k, None)
    m = ical.master_of(ical.events_of(cal))
    repeating = m.get("RRULE") is not None or m.get("RDATE") is not None
    if scope not in ("all", "this", "following"):
        raise ValueError("scope is all, this or following")
    if recurrence_id and repeating and scope == "following" and \
            ical._same_instant(ical._rid_value(m, ical.parse_rid(recurrence_id)), m["DTSTART"].dt):
        scope = "all"  # from the first one on: the whole series
    if not recurrence_id or not repeating or scope == "all":
        if recurrence_id and repeating:
            data = _shift_series(cal, data, recurrence_id, tzname)
        ical.edit(cal, data, tzname)
        return model.save(r["calendar_id"], cal, r["id"], None, u["id"]), None, False
    if scope == "this":
        data.pop("rrule", None)
        ical.edit(cal, data, tzname, recurrence_id)
        return model.save(r["calendar_id"], cal, r["id"], None, u["id"]), recurrence_id, False
    left = ical.remaining_count(cal, recurrence_id, tzname)
    os_, oe = _occurrence_start(cal, recurrence_id)
    j = ical.event_json(cal)
    fresh = {k: j[k] for k in ("title", "location", "notes", "allDay", "timezone", "rrule", "people", "reminders", "url", "status", "busy", "categories")}
    fresh.update(start=ical.iso(os_), end=ical.iso(oe))
    if left and fresh.get("rrule"):
        fresh["rrule"] = re.sub(r"COUNT=\d+", f"COUNT={left}", fresh["rrule"])
    fresh.update(data)
    newc = ical.build(fresh, tzname)
    ical.end_series_before(cal, recurrence_id)
    model.save(r["calendar_id"], cal, r["id"], None, u["id"])
    return model.save(r["calendar_id"], newc, None, None, u["id"]), None, True


def remove(u: dict, r: dict, c: dict, scope: str = "all", recurrence_id: str | None = None) -> None:
    """Delete an event, or one occurrence (scope this), or it and the ones after (scope following)."""
    cal = copy.deepcopy(model.parsed(r))
    m = ical.master_of(ical.events_of(cal))
    repeating = m.get("RRULE") is not None or m.get("RDATE") is not None
    if not recurrence_id or not repeating or scope == "all":
        model.delete(r["id"])
        return
    if scope == "this":
        ical.remove_occurrence(cal, recurrence_id)
    elif scope == "following":
        if ical._same_instant(ical._rid_value(m, ical.parse_rid(recurrence_id)), m["DTSTART"].dt):
            model.delete(r["id"])
            return
        ical.end_series_before(cal, recurrence_id)
    else:
        raise ValueError("scope is all, this or following")
    model.save(r["calendar_id"], cal, r["id"], None, u["id"], c.get("timezone"))


async def _change(request: Request, eid: int, partial: bool, scope: str, recurrence_id: str | None):
    u = me(request)
    r, c = writable_event(u, eid)
    _check_match(request, r)
    data, newcal = await body_object(request)
    if newcal is not None:  # a whole new object for the event
        try:
            uid = ical.index(newcal, c.get("timezone"))["uid"]
        except ValueError as e:
            raise HTTPException(400, str(e))
        if uid != r["uid"]:
            raise HTTPException(400, "The UID of an event cannot change")
        r2 = await run_in_threadpool(model.save, r["calendar_id"], ical.finish(newcal), r["id"], None, u["id"])
        return event_response(request, r2)
    try:
        r2, rid, made = await run_in_threadpool(change, u, r, c, data, partial, scope, recurrence_id)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return event_response(request, r2, status=201 if made else 200, recurrence_id=rid)


@router.put("/api/events/{eid}")
async def replace_event(eid: int, request: Request, scope: str = "all", recurrenceId: str | None = None):
    """Replace an event: JSON fields (those left out are cleared), iCalendar or jCal. With recurrenceId, scope says
    what the change is for: all (the series), this (that occurrence only) or following (it and the ones after: the
    series is split in two). If-Match with the ETag refuses a change made on an old copy."""
    return await _change(request, eid, False, scope, recurrenceId)


@router.patch("/api/events/{eid}")
async def patch_event(eid: int, request: Request, scope: str = "all", recurrenceId: str | None = None):
    """Change some fields of an event (the others stay), with the same scope and recurrenceId as PUT. calendarId moves it."""
    return await _change(request, eid, True, scope, recurrenceId)


@router.delete("/api/events/{eid}")
def delete_event(eid: int, request: Request, scope: str = "all", recurrenceId: str | None = None):
    """Delete an event, or with recurrenceId one occurrence (scope=this) or it and the ones after (scope=following)."""
    u = me(request)
    r, c = writable_event(u, eid)
    _check_match(request, r)
    try:
        remove(u, r, c, scope, recurrenceId)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


# ------------------------------------------------------------------ people, free/busy

@router.get("/api/people")
async def people(request: Request, q: str = "", limit: int = 12):
    """Names for the people on an event: from ioContacts when it is connected, and the people on earlier events."""
    u = me(request)
    out, err = [], None
    q = q.strip()
    if q and contacts.enabled():
        try:
            out = await run_in_threadpool(contacts.search, q, max(1, min(limit, 50)))
        except Exception as e:  # noqa: BLE001
            err = f"ioContacts did not answer: {type(e).__name__}"
    seen = {(p.get("email") or "", p["name"]) for p in out}
    for p in model.people_seen([c["id"] for c in model.calendars_for(u)], q, limit):
        if (p["email"] or "", p["name"]) not in seen and len(out) < limit:
            out.append({"contactId": p["contactId"], "name": p["name"], "email": p["email"], "url": contacts.contact_url(p["contactId"])})
    return {"items": out, "error": err}


def busy_periods(cals: list[dict], s: dt.datetime, e: dt.datetime) -> list[tuple[dt.datetime, dt.datetime]]:
    out = []
    for o in model.occurrences(cals, s, e):
        if not o["busy"] or o["status"] == "CANCELLED" or o["allDay"]:
            continue
        a, b = ical.to_utc(dt.datetime.fromisoformat(o["start"])), ical.to_utc(dt.datetime.fromisoformat(o["end"]))
        if b > s and a < e:
            out.append((max(a, s), min(b, e)))
    out.sort()
    merged: list = []
    for a, b in out:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


@router.get("/api/free-busy")
def free_busy(request: Request, start: str, end: str, calendars: str | None = None):
    """When you are busy between start and end (timed events that are not marked free or cancelled), merged."""
    u = me(request)
    s, e = _when(start, "start"), _when(end, "end")
    if e - s > dt.timedelta(days=400):
        raise HTTPException(400, "At most a year at a time")
    return {"busy": [{"start": a.isoformat(), "end": b.isoformat()} for a, b in busy_periods(visible(u, calendars), s, e)]}


def vfreebusy(cals: list[dict], who: dict, days_back: int = 7, days_ahead: int = 60) -> str:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    s, e = now - dt.timedelta(days=days_back), now + dt.timedelta(days=days_ahead)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{ical.PRODID}", "METHOD:PUBLISH", "BEGIN:VFREEBUSY",
             f"UID:freebusy-{who['id']}@iocalendar", f"DTSTAMP:{now:%Y%m%dT%H%M%SZ}", f"DTSTART:{s:%Y%m%dT%H%M%SZ}", f"DTEND:{e:%Y%m%dT%H%M%SZ}"]
    if who.get("email"):
        lines.append(f"ORGANIZER;CN={who.get('displayName') or who['name']}:mailto:{who['email']}")
    for a, b in busy_periods(cals, s, e):
        lines.append(f"FREEBUSY;FBTYPE=BUSY:{a:%Y%m%dT%H%M%SZ}/{b:%Y%m%dT%H%M%SZ}")
    lines += ["END:VFREEBUSY", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"


# ------------------------------------------------------------------ connection details, subscription links

@router.get("/api/connect")
def connect_info(request: Request):
    """What to type into a calendar app: CalDAV, the subscription links, free/busy, the API."""
    u = me(request)
    base = _base(request)
    tok = users.feed_token(u["id"])
    cals = model.calendars_for(u)
    return {"user": u["name"], "server": base, "caldav": f"{base}/dav/", "principal": f"{base}/dav/principals/{u['name']}/",
            "calendars": [{"id": c["id"], "name": c["name"], "caldav": f"{base}/dav/calendars/{u['name']}/{c['slug']}/",
                           "ics": f"{base}/ics/{tok}/{c['slug']}.ics"} for c in cals],
            "all": f"{base}/ics/{tok}/all.ics", "webcal": re.sub(r"^https?://", "webcal://", f"{base}/ics/{tok}/all.ics"),
            "freebusy": f"{base}/ics/{tok}/freebusy.vfb", "api": f"{base}/api/docs", "mcp": f"{base}/mcp"}


@router.post("/api/feeds/reset")
def feeds_reset(request: Request):
    """A new private link for your subscriptions (the old ones stop working)."""
    users.reset_feed_token(me(request)["id"])
    return {"ok": True}


@router.get("/ics/{token}/{name}")
def feed(token: str, name: str, request: Request):
    """The subscription links (no sign-in: the token in the link is the secret): one calendar (<slug>.ics), every
    calendar you see (all.ics) or when you are busy (freebusy.vfb / .ifb)."""
    u = users.user_from_feed_token(token)
    if not u:
        raise HTTPException(404)
    cals = model.calendars_for(u)
    if name in ("freebusy.vfb", "freebusy.ifb"):
        return Response(vfreebusy(cals, u), media_type="text/calendar; charset=utf-8")
    if not name.endswith(".ics"):
        raise HTTPException(404)
    slug = name[:-4]
    if slug == "all":
        pick, title = cals, "ioCalendar"
    else:
        pick = [c for c in cals if c["slug"] == slug]
        if not pick:
            raise HTTPException(404)
        title = pick[0]["name"]
    return Response(model.export_text(pick, title), media_type="text/calendar; charset=utf-8",
                    headers={"Cache-Control": "private, max-age=300"})


@router.post("/api/apple-profile")
def apple_profile(request: Request, label: str = Form("iPhone"), password: str = Form("new")):
    """A configuration profile (.mobileconfig) that adds the CalDAV account to an iPhone, iPad or Mac in one go.
    password: "new" puts a new app password (named after label) in the profile; "ask" leaves it out."""
    import plistlib
    import uuid
    from urllib.parse import urlsplit
    u = me(request)
    if u.get("passwordless"):
        raise HTTPException(403, "A one-click account cannot have app passwords")
    base = _base(request)
    parts = urlsplit(base)
    ssl = parts.scheme == "https"
    host = parts.hostname or "localhost"
    port = parts.port or (443 if ssl else 80)
    label = (label or "iPhone").strip()[:48] or "iPhone"
    secret = users.create_app_password(u["id"], f"{label} (profile)") if password == "new" else None
    ident = "net.iothing.iocalendar." + re.sub(r"[^A-Za-z0-9.-]", "-", host) + "." + re.sub(r"[^A-Za-z0-9-]", "-", u["name"])
    who = u.get("displayName") or u["name"]
    caldav = {"PayloadType": "com.apple.caldav.account", "PayloadVersion": 1, "PayloadIdentifier": ident + ".caldav",
              "PayloadUUID": str(uuid.uuid4()).upper(), "PayloadDisplayName": "Calendars (CalDAV)",
              "CalDAVAccountDescription": "ioCalendar", "CalDAVHostName": host, "CalDAVPort": port, "CalDAVUseSSL": ssl,
              "CalDAVPrincipalURL": f"{parts.path.rstrip('/')}/dav/principals/{u['name']}/", "CalDAVUsername": u["name"]}
    if secret:
        caldav["CalDAVPassword"] = secret
    profile = {"PayloadType": "Configuration", "PayloadVersion": 1, "PayloadIdentifier": ident,
               "PayloadUUID": str(uuid.uuid4()).upper(), "PayloadDisplayName": f"ioCalendar for {who}",
               "PayloadDescription": f"Adds {who}'s ioCalendar calendars from {host}." + ("" if secret else " The device asks for an app password while installing."),
               "PayloadOrganization": "ioCalendar", "PayloadRemovalDisallowed": False, "PayloadContent": [caldav]}
    return Response(plistlib.dumps(profile), media_type="application/x-apple-aspen-config",
                    headers={"Content-Disposition": f'attachment; filename="iocalendar-{re.sub(r"[^A-Za-z0-9-]", "-", u["name"])}.mobileconfig"',
                             "Cache-Control": "no-store"})


# ------------------------------------------------------------------ ioContacts

@router.get("/api/iocontacts/settings")
def iocontacts_settings(request: Request):
    admin(request)
    return contacts.public_settings()


@router.post("/api/iocontacts/settings")
async def iocontacts_save(request: Request):
    """Admins: {url, user, password, cfId, cfSecret, birthdays}. Saving tests the connection and brings the Birthdays
    calendar up to date."""
    admin(request)
    b = await request.json()
    contacts.save_settings(b.get("url"), b.get("user"), b.get("password"), b.get("cfId"), b.get("cfSecret"),
                           b.get("birthdays") if "birthdays" in b else None)
    test = await run_in_threadpool(contacts.test) if contacts.enabled() else None
    sync = await run_in_threadpool(contacts.sync_birthdays) if (not test or test.get("ok")) else None
    return {**contacts.public_settings(), "test": test, "sync": sync}


@router.post("/api/iocontacts/sync")
async def iocontacts_sync(request: Request):
    admin(request)
    return await run_in_threadpool(contacts.sync_birthdays)
