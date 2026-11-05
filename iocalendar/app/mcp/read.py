"""The read-only tools: what any signed-in account may ask about the calendars it can see."""
import datetime as dt
from typing import Optional

from mcp.server.mcpserver.exceptions import ToolError

from app import __version__, config, contacts, holiday, ical, members, model
from app.mcp.base import READ_ONLY, calendars, clamp, event_out, find_calendar, find_event, member_ids, occurrence_out, server, when, who


def _pick(u: dict, names: Optional[list[str]]) -> list[dict]:
    if not names:
        return calendars(u)
    return [find_calendar(u, n) for n in names]


@server.tool(annotations=READ_ONLY)
def overview() -> dict:
    """Who you are signed in as, the calendars you can see (with counts and whether you may change them), the family
    members events can be tagged with, the server's time zone and today's date there, the public holidays shown, and
    what is on today and in the next seven days. Start here."""
    u = who()
    tz = ical.default_tz()
    now = dt.datetime.now(ical.zone(tz))
    day0 = dt.datetime.combine(now.date(), dt.time(), now.tzinfo)
    occ = model.occurrences(calendars(u), ical.to_utc(day0), ical.to_utc(day0 + dt.timedelta(days=8)))
    return {
        "you": {"name": u["name"], "displayName": u.get("displayName"), "role": u.get("role")},
        "calendars": [{"id": c["id"], "name": c["name"], "shared": c["owner_id"] is None, "events": c.get("n"),
                       "youCanChange": model.can_write(u, c), "kind": c["kind"], "timezone": c.get("timezone")} for c in calendars(u)],
        "timezone": tz, "now": now.isoformat(timespec="minutes"), "today": now.date().isoformat(), "weekday": now.strftime("%A"),
        "nextSevenDays": [occurrence_out(u, o) for o in occ][:200],
        "family": [m["displayName"] for m in members.family()],
        "holidays": _holidays(),
        "iocontactsConnected": contacts.enabled(), "version": __version__, "webApp": config.PUBLIC_URL or None,
    }


def _holidays():
    s = holiday.settings()
    if not s["country"]:
        return None
    p = holiday.public_settings()
    return {"country": p.get("countryName") or s["country"], "region": p.get("regionName") or s["region"]}


@server.tool(annotations=READ_ONLY)
def list_family_members() -> list:
    """The family members an event can be tagged with (the accounts that use ioCalendar)."""
    who()
    return members.public(members.family())


@server.tool(annotations=READ_ONLY)
def list_calendars() -> list:
    """The calendars you can see: the shared Family calendar (and other shared ones, Birthdays from ioContacts and the
    public Holidays among them) and your private ones."""
    u = who()
    return [{"id": c["id"], "name": c["name"], "description": c.get("description"), "color": c.get("color"), "shared": c["owner_id"] is None,
             "events": c.get("n"), "youCanChange": model.can_write(u, c), "kind": c["kind"]} for c in calendars(u)]


@server.tool(annotations=READ_ONLY)
def agenda(start: str, end: Optional[str] = None, calendars: Optional[list[str]] = None, text: Optional[str] = None,
           member: Optional[list[str]] = None, limit: int = 300) -> dict:
    """What happens between start and end (ISO dates or date-times; end defaults to a week after start), soonest
    first, with repeating events expanded into their occurrences. calendars: names or ids (all when left out). text:
    only events whose title, place, notes or people match. member: only events tagged with these family members
    (names). Each item has the event id and, for a repeating event, the
    recurrenceId that names that occurrence."""
    u = who()
    s = when(start)
    e = when(end, s + dt.timedelta(days=7))
    if e <= s:
        raise ToolError("end is before start")
    if e - s > dt.timedelta(days=800):
        raise ToolError("At most about two years at a time")
    occ = model.occurrences(_pick(u, calendars), s, e, text or "", member_ids(member))
    n = clamp(limit, 1, 2000)
    return {"from": s.isoformat(), "to": e.isoformat(), "total": len(occ), "items": [occurrence_out(u, o) for o in occ[:n]]}


@server.tool(annotations=READ_ONLY)
def search_events(text: str = "", calendars: Optional[list[str]] = None, member: Optional[list[str]] = None, limit: int = 50) -> list:
    """Events (not occurrences) whose title, place, notes or people match every word of text, the most recent first,
    with the next occurrence of repeating ones. member: only events tagged with these family members (names)."""
    u = who()
    mids = member_ids(member)
    n = clamp(limit, 1, 500)
    rows = model.search_rows([c["id"] for c in _pick(u, calendars)], text, n if mids is None else 100000)
    if mids is not None:
        rows = [r for r in rows if model.tagged(r, mids)][:n]
    names = {c["id"]: c["name"] for c in _pick(u, None)}
    out = []
    for r in rows:
        x = {"id": r["id"], "title": r["summary"], "calendar": names.get(r["calendar_id"]), "location": r["location"],
             "allDay": bool(r["all_day"]) or None, "repeats": r["rrule"]}
        if r["rrule"]:
            x["next"] = model.next_occurrence(r)
        else:
            j = model.event_out(r)
            x["start"], x["end"] = j["start"], j["end"]
        out.append({k: v for k, v in x.items() if v not in (None, "", [], {})})
    return out


@server.tool(annotations=READ_ONLY)
def get_event(event: str, occurrence: Optional[str] = None) -> dict:
    """Everything about one event (by id or title): title, start and end, time zone, all-day, the repeat rule (RRULE)
    with its left-out dates and changed occurrences, place, notes, people, reminders (minutes before), link, status.
    occurrence: a recurrenceId, for what that one occurrence looks like."""
    u = who()
    r, _ = find_event(u, event)
    return event_out(u, r, occurrence)


@server.tool(annotations=READ_ONLY)
def get_ics(event: str) -> str:
    """One event as iCalendar text (RFC 5545), exactly as calendar apps get it."""
    u = who()
    r, _ = find_event(u, event)
    return r["ics"]


@server.tool(annotations=READ_ONLY)
def free_busy(start: str, end: Optional[str] = None, calendars: Optional[list[str]] = None) -> dict:
    """When you are busy between start and end (default: a week): the timed events not marked free or cancelled,
    merged into periods, and the free gaps between them."""
    from app.api import busy_periods
    u = who()
    s = when(start)
    e = when(end, s + dt.timedelta(days=7))
    if e - s > dt.timedelta(days=400):
        raise ToolError("At most a year at a time")
    busy = busy_periods(_pick(u, calendars), s, e)
    free, cur = [], s
    for a, b in busy:
        if a > cur:
            free.append({"start": cur.isoformat(), "end": a.isoformat()})
        cur = max(cur, b)
    if cur < e:
        free.append({"start": cur.isoformat(), "end": e.isoformat()})
    return {"busy": [{"start": a.isoformat(), "end": b.isoformat()} for a, b in busy], "free": free}


@server.tool(annotations=READ_ONLY)
def connection_details() -> dict:
    """What to type into a calendar app for your account: the CalDAV address and user name (with an app password from
    Settings › Apps and devices), and the private subscription links (.ics) of your calendars."""
    from app import users
    u = who()
    base = config.PUBLIC_URL or "(this server's address)"
    tok = users.feed_token(u["id"])
    return {"user": u["name"], "caldav": f"{base}/dav/", "subscriptions": {c["name"]: f"{base}/ics/{tok}/{c['slug']}.ics" for c in calendars(u)},
            "all": f"{base}/ics/{tok}/all.ics", "freeBusy": f"{base}/ics/{tok}/freebusy.vfb", "api": f"{base}/api/docs"}
