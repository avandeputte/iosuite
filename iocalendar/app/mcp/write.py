"""The tools that change events and calendars, with the same permissions as the web app: a viewer changes only their
own private calendars, editors and admins the shared ones too. Every change reaches phones and apps at their next sync."""
from typing import Literal, Optional

from mcp.server.mcpserver.exceptions import ToolError

from app import ical, members, model
from app.mcp.base import ADDS, DELETES, WRITES, default_calendar, event_out, find_calendar, find_event, server, who

EVENT_FIELDS = """
    Times are ISO 8601: '2026-11-03T10:00' (wall-clock time in timezone) or '2026-11-03' with all_day. For an all-day
    event end is the day after the last day ('2026-12-24' to '2026-12-27' is three days); left out, an all-day event
    is one day and a timed one an hour.
    people: names on the event, each a name or {name, email}: noted on the event, never invited.
    members: the family members the event is for (names from overview's family, or list_family_members); kept as
    iCalendar categories so calendar apps show them; [] removes the tags.
    reminders: minutes before the start, e.g. [15, 1440] (15 minutes and a day before); [] removes them.
    repeat: an RFC 5545 RRULE such as 'FREQ=WEEKLY;BYDAY=MO,WE', 'FREQ=MONTHLY;BYMONTHDAY=1;COUNT=12',
    'FREQ=YEARLY' or 'FREQ=DAILY;UNTIL=20261231'; '' stops the repeating.
"""


def fields(fn):
    fn.__doc__ = (fn.__doc__ or "") + EVENT_FIELDS
    return fn


def _data(title=None, start=None, end=None, all_day=None, timezone=None, location=None, notes=None, people=None,
          reminders=None, repeat=None, url=None, free=None, status=None, members_=None) -> dict:
    d = {}
    if members_ is not None:
        try:
            d["members"] = [m["id"] for m in members.resolve(members_)]
        except ValueError as e:
            raise ToolError(str(e))
    for k, v in (("title", title), ("start", start), ("end", end), ("allDay", all_day), ("timezone", timezone), ("location", location),
                 ("notes", notes), ("people", people), ("reminders", reminders), ("rrule", repeat), ("url", url), ("status", status)):
        if v is not None:
            d[k] = v
    if free is not None:
        d["busy"] = not free
    if "timezone" in d and d["timezone"] and not ical.valid_tz(d["timezone"]):
        raise ToolError(f"Unknown time zone '{d['timezone']}' (an IANA name such as Europe/Brussels or America/New_York)")
    return d


def _fold(d: dict) -> dict:
    from app import members as m
    return m.fold(d)


@server.tool(annotations=ADDS)
@fields
def create_event(title: str, start: str, end: Optional[str] = None, all_day: bool = False, calendar: Optional[str] = None,
                 timezone: Optional[str] = None, location: Optional[str] = None, notes: Optional[str] = None,
                 people: Optional[list] = None, reminders: Optional[list[int]] = None, repeat: Optional[str] = None,
                 url: Optional[str] = None, free: bool = False, members: Optional[list[str]] = None) -> dict:
    """Add an event. calendar: a name or id (else the Family calendar, or your own when you may not change it)."""
    u = who()
    c = find_calendar(u, calendar, writable=True) if calendar else default_calendar(u)
    d = _data(title, start, end, all_day, timezone or c.get("timezone"), location, notes, people, reminders, repeat, url, free,
              members_=members)
    try:
        cal = ical.build(_fold(d), c.get("timezone"))
    except ValueError as e:
        raise ToolError(str(e))
    r = model.save(c["id"], cal, None, None, u["id"])
    return event_out(u, r)


@server.tool(annotations=WRITES)
@fields
def update_event(event: str, title: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None,
                 all_day: Optional[bool] = None, timezone: Optional[str] = None, location: Optional[str] = None,
                 notes: Optional[str] = None, people: Optional[list] = None, reminders: Optional[list[int]] = None,
                 repeat: Optional[str] = None, url: Optional[str] = None, free: Optional[bool] = None,
                 status: Optional[Literal["confirmed", "tentative", "cancelled", ""]] = None,
                 occurrence: Optional[str] = None, scope: Literal["all", "this", "following"] = "all",
                 members: Optional[list[str]] = None) -> dict:
    """Change an event (by id or title); only the fields given change ('' clears a text field). For a repeating event,
    occurrence (a recurrenceId from agenda) with scope 'this' changes that occurrence only, 'following' it and the ones
    after (the series is split: a new event is returned), 'all' the series (a new start then moves every occurrence by
    as much)."""
    from app.api import change
    u = who()
    r, c = find_event(u, event, writable=True)
    d = _data(title, start, end, all_day, timezone, location, notes, people, reminders, repeat, url, free, status, members_=members)
    if not d:
        raise ToolError("Nothing to change")
    try:
        r2, rid, _ = change(u, r, c, d, True, scope, occurrence)
    except (ValueError, PermissionError) as e:
        raise ToolError(str(e))
    return event_out(u, r2, rid)


@server.tool(annotations=DELETES)
def delete_event(event: str, occurrence: Optional[str] = None, scope: Literal["all", "this", "following"] = "all") -> dict:
    """Delete an event (by id or title), or of a repeating event one occurrence (occurrence=<recurrenceId>,
    scope='this') or it and the ones after (scope='following'). Ask the person first."""
    from app.api import remove
    u = who()
    r, c = find_event(u, event, writable=True)
    try:
        remove(u, r, c, scope, occurrence)
    except ValueError as e:
        raise ToolError(str(e))
    return {"deleted": r["summary"], "id": r["id"], "scope": scope if occurrence else "all"}


@server.tool(annotations=WRITES)
def move_event(event: str, calendar: str) -> dict:
    """Move an event (with all its occurrences) to another calendar."""
    u = who()
    r, _ = find_event(u, event, writable=True)
    c = find_calendar(u, calendar, writable=True)
    try:
        r2 = model.move(r["id"], c["id"])
    except ValueError as e:
        raise ToolError(str(e))
    return event_out(u, r2)


@server.tool(annotations=ADDS)
def create_calendar(name: str, shared: bool = False, color: Optional[str] = None, description: Optional[str] = None,
                    timezone: Optional[str] = None) -> dict:
    """A new calendar: private (only you see it) or shared with everyone (editors and admins). color: #rrggbb."""
    u = who()
    if shared and u.get("role") not in ("editor", "admin"):
        raise ToolError("Only editors make shared calendars")
    cid = model.create_calendar(None if shared else u["id"], name, description, color, timezone=timezone)
    c = model.calendar(cid)
    return {"id": c["id"], "name": c["name"], "shared": shared, "color": c["color"]}


@server.tool(annotations=ADDS)
def import_ics(ics: str, calendar: Optional[str] = None, replace: bool = True) -> dict:
    """Events from iCalendar text (one event or a whole .ics export) into a calendar. An event whose UID the calendar
    has already is updated (replace=false: left as it is)."""
    u = who()
    c = find_calendar(u, calendar, writable=True) if calendar else default_calendar(u)
    try:
        return model.import_text(c["id"], ics, u["id"], replace)
    except ValueError as e:
        raise ToolError(str(e))
