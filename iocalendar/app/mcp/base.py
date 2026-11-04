"""The MCP server instance and what every tool module shares: who is asking, and finding calendars and events."""
import contextvars
import datetime as dt

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from app import APP_VERSION, config, ical, members, model, users

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
ADDS = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
DELETES = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)

server = MCPServer(
    "iocalendar",
    title="ioCalendar",
    version=APP_VERSION,
    instructions=(
        "The family's calendars (ioCalendar). Start with overview: it says who you are, the calendars you can see and "
        "change, the time zone, and what is on today and in the coming week. agenda lists what happens between two dates "
        "(repeating events expanded); search_events finds events by title, place, notes or people; get_event has "
        "everything about one. Times are ISO 8601: '2026-11-03T10:00' is wall-clock time in the event's time zone (the "
        "timezone argument, else the calendar's, else the server's); '2026-11-03' is a date (all-day). For an all-day "
        "event the end date is the day after the last day. A repeating event has one id; its occurrences are named by "
        "their recurrenceId (from agenda). To change or delete one occurrence give occurrence=<recurrenceId> and "
        "scope='this', or scope='following' for it and the ones after. People on an event are noted, never invited: "
        "nothing is sent to them. Events can be tagged with the family members they are for (members: names from "
        "overview's family); agenda and search_events filter by member. The shared Holidays calendar holds the public "
        "holidays and cannot be changed. Ask before deleting events or calendars."
    ),
)

current_user: contextvars.ContextVar = contextvars.ContextVar("iocalendar_mcp_user", default=None)  # set per request


def who() -> dict:
    u = current_user.get()
    if not u:
        raise ToolError("Not signed in: connect with an ioCalendar app password (Settings › Apps and devices)")
    return u


def need_admin() -> dict:
    u = who()
    if not users.is_admin(u):
        raise ToolError("Only an admin can do this")
    return u


def event_link(eid: int) -> str | None:
    return f"{config.PUBLIC_URL}/#/event/{eid}" if config.PUBLIC_URL else None


def clamp(n, lo: int, hi: int) -> int:
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = lo
    return max(lo, min(n, hi))


def when(s: str | None, default: dt.datetime | None = None, tz: str | None = None) -> dt.datetime:
    """An ISO date or date-time from an argument, as UTC (a date: its midnight in tz or the server's zone)."""
    if not s:
        if default is None:
            raise ToolError("A date is missing")
        return default
    try:
        d = ical.parse_when(s, tz or ical.default_tz())
    except ValueError:
        raise ToolError(f"Not an ISO date or date-time: {s}")
    if not isinstance(d, dt.datetime):
        d = dt.datetime.combine(d, dt.time(), ical.zone(tz))
    return ical.to_utc(d)


# ---- calendars

def calendars(u: dict) -> list[dict]:
    return model.calendars_for(u)


def find_calendar(u: dict, ref, writable: bool = False) -> dict:
    """A calendar by id, name or slug ("Family", "Personal")."""
    cals = calendars(u)
    s = str(ref).strip()
    hit = [c for c in cals if str(c["id"]) == s] or [c for c in cals if c["name"].lower() == s.lower() or c["slug"] == s.lower()]
    if not hit:
        raise ToolError(f"No calendar '{ref}'. These are yours: " + ", ".join(f"{c['name']} (id {c['id']})" for c in cals))
    if len(hit) > 1:
        raise ToolError(f"'{ref}' names more than one calendar: " + ", ".join(f"{c['name']} (id {c['id']})" for c in hit))
    c = hit[0]
    if writable and not model.can_write(u, c):
        raise ToolError(f"You can read '{c['name']}' but not change it" + (f" ({model.read_only_reason(c)})" if model.read_only_reason(c)
                                                                            else " (viewers change only their own private calendars)"))
    return c


def default_calendar(u: dict) -> dict:
    """Where a new event goes when no calendar is named: the first shared calendar this account may change, else its own."""
    cals = [c for c in calendars(u) if model.can_write(u, c)]
    if not cals:
        raise ToolError("This account cannot add events anywhere")
    return cals[0]


def calendar_names(u: dict) -> dict:
    return {c["id"]: c["name"] for c in calendars(u)}


# ---- events

def find_event(u: dict, ref, writable: bool = False) -> tuple[dict, dict]:
    """An event (row, calendar) by id, or by a title that matches exactly one event."""
    cals = {c["id"]: c for c in calendars(u)}
    s = str(ref).strip()
    if not s:
        raise ToolError("Name an event (its id or its title)")
    if s.isdigit():
        r = model.get_row(int(s))
        if not r or r["deleted"] or r["calendar_id"] not in cals:
            raise ToolError(f"No event with id {s}")
    else:
        rows = [x for x in model.search_rows(list(cals), s, 10) if x["summary"].lower() == s.lower()] or model.search_rows(list(cals), s, 10)
        if not rows:
            raise ToolError(f"No event matches '{s}'. Try search_events or agenda.")
        if len(rows) > 1:
            raise ToolError(f"'{s}' matches several events; give the id: " + "; ".join(f"{x['summary']} (id {x['id']})" for x in rows))
        r = rows[0]
    c = cals[r["calendar_id"]]
    if writable and not model.can_write(u, c):
        raise ToolError(f"You can read '{r['summary']}' but not change it (calendar {c['name']})")
    return r, c


def event_out(u: dict, r: dict, recurrence_id: str | None = None) -> dict:
    j = model.event_out(r, recurrence_id=recurrence_id)
    for k in ("href", "etag", "sequence"):
        j.pop(k, None)
    j["calendar"] = calendar_names(u).get(r["calendar_id"])
    j["members"] = [m["displayName"] for m in j.get("members") or []]
    if r["rrule"]:
        j["next"] = model.next_occurrence(r)
    link = event_link(r["id"])
    if link:
        j["webUrl"] = link
    return {k: v for k, v in j.items() if v not in (None, "", [], {})}


def member_names(ids) -> list[str]:
    by_id = {m["id"]: m["displayName"] for m in members.family()}
    return [by_id[i] for i in ids or [] if i in by_id]


def member_ids(refs) -> set[int] | None:
    """A member argument (a name, or a list of names or ids) as member ids; None when not given."""
    if refs in (None, "", []):
        return None
    try:
        return {m["id"] for m in members.resolve(refs)}
    except ValueError as e:
        raise ToolError(str(e))


def occurrence_out(u: dict, o: dict) -> dict:
    out = {"id": o["id"], "title": o["title"], "start": o["start"], "end": o["end"], "allDay": o["allDay"] or None,
           "calendar": calendar_names(u).get(o["calendarId"]), "location": o["location"], "people": o["people"],
           "members": member_names(o.get("members")),
           "recurrenceId": o["recurrenceId"] if o["recurring"] else None, "status": o["status"],
           "free": (not o["busy"]) or None}
    return {k: v for k, v in out.items() if v not in (None, "", [], {})}
