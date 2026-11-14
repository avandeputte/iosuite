"""iCalendar (RFC 5545) to-dos: reading what reminders apps send, writing what the web app makes, the columns the app
sorts and filters on, and completing a repeating task.

A task is kept as its whole iCalendar object: a VCALENDAR with one VTODO (and, rarely, changed occurrences of a
repeating one with a RECURRENCE-ID, kept as they came). The web app edits a few fields of the VTODO; everything else a
reminders app put there (its alarms, X-APPLE-SORT-ORDER, other X- properties) stays as it was.

Apple Reminders writes a due date as DUE (with DTSTART at the same moment when it has a time), a priority as 1 (high),
5 (medium) or 9 (low), a subtask as RELATED-TO the parent's UID, and an alert as a VALARM with an absolute trigger.
"""
import datetime as dt
import hashlib
import os
import re
import uuid as uuidlib
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil import rrule as du_rrule
from dateutil.relativedelta import relativedelta
from icalendar import Alarm, Calendar, Event, Todo, vDDDTypes, vRecur

from app import __version__, config
from iosuite_shared.errors import Invalid

PRODID = f"-//iothing//ioTask {__version__}//EN"
UTC = dt.timezone.utc
STATUSES = ("NEEDS-ACTION", "IN-PROCESS", "COMPLETED", "CANCELLED")
PRIORITIES = {"high": 1, "medium": 5, "low": 9, "none": 0, "": 0}
EDITABLE = ("title", "notes", "due", "start", "timezone", "priority", "done", "status", "percent", "url", "location",
            "categories", "parent", "rrule", "repeatAfter", "alarms")
# ioTask's own property: the task comes back this long after the day it is ticked off (an ISO 8601 duration of days,
# weeks, months or years: "P2W" is two weeks later), where RRULE counts from the due date. Reminders apps keep a
# property they do not know.
AFTER_DONE = "X-IOTASK-AFTER-DONE"
SORT_ORDER = "X-APPLE-SORT-ORDER"   # Apple Reminders' manual order: lower comes first; without it, the seconds from 2001 to CREATED
APPLE_EPOCH = dt.datetime(2001, 1, 1, tzinfo=UTC)
UNITS = {"D": "days", "W": "weeks", "M": "months", "Y": "years"}


# ------------------------------------------------------------------ time zones

def _system_tz() -> str:
    tz = os.environ.get("TZ", "").strip()
    if tz and not tz.startswith(":"):
        return tz
    try:
        p = Path("/etc/localtime").resolve()
        if "zoneinfo/" in str(p):
            return str(p).split("zoneinfo/", 1)[1]
    except OSError:
        pass
    try:
        return Path("/etc/timezone").read_text().strip() or "UTC"
    except OSError:
        return "UTC"


def default_tz() -> str:
    """The server's time zone: floating times (no zone) and new due times without one are read in it."""
    name = config.TZ or _system_tz()
    return name if valid_tz(name) else "UTC"


def valid_tz(name: str | None) -> bool:
    if not name:
        return False
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def zone(name: str | None) -> dt.tzinfo:
    return ZoneInfo(name) if valid_tz(name) else ZoneInfo(default_tz())


def to_utc(d, tzname: str | None = None) -> dt.datetime:
    """A date, floating or zoned datetime as an aware UTC datetime (a date: its midnight UTC; floating: in tzname or
    the server's zone)."""
    if isinstance(d, dt.datetime):
        if d.tzinfo is None:
            d = d.replace(tzinfo=zone(tzname))
        return d.astimezone(UTC)
    return dt.datetime(d.year, d.month, d.day, tzinfo=UTC)


def naive_utc(d, tzname: str | None = None) -> dt.datetime | None:
    """For the DATETIME columns."""
    return None if d is None else to_utc(d, tzname).replace(tzinfo=None)


def iso(d) -> str | None:
    """A date as YYYY-MM-DD, a datetime as ISO 8601 with its offset (floating: without one)."""
    if d is None:
        return None
    if isinstance(d, dt.datetime):
        return d.isoformat(timespec="seconds")
    return d.isoformat()


def parse_when(s: str, tzname: str | None = None):
    """'2026-11-03' (a date) or '2026-11-03T10:00[:00][Z|+01:00]' (a datetime: without an offset it is wall time in
    tzname). Invalid when it is neither."""
    s = (s or "").strip()
    if not s:
        raise Invalid("A date or time is missing")
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return dt.date.fromisoformat(s)
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise Invalid(f"Not an ISO date or date-time: {s}")
    if d.tzinfo is None:
        d = d.replace(tzinfo=zone(tzname))
    elif tzname and valid_tz(tzname):
        d = d.astimezone(ZoneInfo(tzname))
    return d.replace(microsecond=0)


# ------------------------------------------------------------------ reading

def parse(text: str | bytes) -> Calendar:
    """One VCALENDAR; Invalid when the text is not iCalendar."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    text = text.lstrip("﻿")
    if "BEGIN:VCALENDAR" not in text.upper():
        raise Invalid("Not an iCalendar object (no BEGIN:VCALENDAR)")
    try:
        cals = Calendar.from_ical(text, multiple=True)
    except Exception as e:  # noqa: BLE001 - the library raises several kinds
        raise Invalid(f"Not valid iCalendar: {e}") from e
    if not cals:
        raise Invalid("No VCALENDAR in the text")
    out = cals[0]
    for c in cals[1:]:  # several VCALENDARs in one file (some exports): one calendar with all their components
        for sub in c.subcomponents:
            out.add_component(sub)
    return out


def todos_of(cal: Calendar) -> list[Todo]:
    return [c for c in cal.subcomponents if c.name == "VTODO"]


def kinds_of(cal: Calendar) -> set[str]:
    """The components in an object besides time zones (a reminders server takes VTODO only)."""
    return {s.name for s in cal.subcomponents if s.name != "VTIMEZONE"}


def master_of(comps: list) -> Todo | None:
    """The VTODO without a RECURRENCE-ID (the task, or the series); for a lone changed occurrence, that one."""
    for c in comps:
        if "RECURRENCE-ID" not in c:
            return c
    return comps[0] if comps else None


def todo(cal: Calendar) -> Todo:
    t = master_of(todos_of(cal))
    if t is None:
        raise Invalid("No task (VTODO) in the object")
    return t


def split_by_uid(cal: Calendar) -> list[Calendar]:
    """A calendar with many to-dos (an import) as one object per UID, each with the VTIMEZONEs it uses."""
    tzs = {str(c.get("TZID")): c for c in cal.subcomponents if c.name == "VTIMEZONE"}
    groups: dict[str, list] = {}
    for t in todos_of(cal):
        uid = str(t.get("UID") or "").strip() or new_uid()
        if "UID" not in t:
            t.add("UID", uid)
        groups.setdefault(uid, []).append(t)
    out = []
    for comps in groups.values():
        c = new_calendar()
        used = set()
        for t in comps:
            for k in ("DTSTART", "DUE", "RECURRENCE-ID", "EXDATE", "RDATE"):
                vals = t.get(k)
                for v in (vals if isinstance(vals, list) else [vals]):
                    if v is not None and getattr(v, "params", None) and v.params.get("TZID"):
                        used.add(str(v.params["TZID"]))
        for name in sorted(used):
            if name in tzs:
                c.add_component(tzs[name])
        for t in sorted(comps, key=lambda x: "RECURRENCE-ID" in x):
            c.add_component(t)
        out.append(c)
    return out


def new_calendar() -> Calendar:
    c = Calendar()
    c.add("PRODID", PRODID)
    c.add("VERSION", "2.0")
    return c


def new_uid() -> str:
    return str(uuidlib.uuid4()).upper()


def text(cal: Calendar) -> str:
    return cal.to_ical().decode("utf-8")


def etag_of(ics: str) -> str:
    return hashlib.sha1(ics.encode("utf-8")).hexdigest()[:24]


def _val(t: Todo, name: str):
    v = t.get(name)
    if isinstance(v, list):
        v = v[0] if v else None
    return getattr(v, "dt", v)


def _str(t: Todo, name: str) -> str:
    v = t.get(name)
    if isinstance(v, list):
        v = v[0] if v else None
    return str(v).strip() if v is not None else ""


def due_of(t: Todo):
    """The due date or time: DUE, else DTSTART + DURATION."""
    d = _val(t, "DUE")
    if d is None and t.get("DTSTART") is not None and t.get("DURATION") is not None:
        d = _val(t, "DTSTART") + t["DURATION"].dt
    return d


def rrule_text(t: Todo) -> str | None:
    r = t.get("RRULE")
    if r is None:
        return None
    if isinstance(r, list):
        r = r[0]
    return r.to_ical().decode()


def categories_of(t: Todo) -> list[str]:
    c = t.get("CATEGORIES")
    out = []
    for x in (c if isinstance(c, list) else [c] if c is not None else []):
        out += [str(v) for v in getattr(x, "cats", [])]
    return out


def parent_of(t: Todo) -> str | None:
    """The parent's UID (RELATED-TO with RELTYPE PARENT, the default)."""
    rel = t.get("RELATED-TO")
    for r in (rel if isinstance(rel, list) else [rel] if rel is not None else []):
        if str(getattr(r, "params", {}).get("RELTYPE", "PARENT")).upper() == "PARENT" and str(r).strip():
            return str(r).strip()
    return None


def status_of(t: Todo) -> str:
    st = _str(t, "STATUS").upper()
    if st in STATUSES:
        return st
    return "COMPLETED" if t.get("COMPLETED") is not None else "NEEDS-ACTION"


def priority_of(t: Todo) -> int:
    try:
        p = int(_str(t, "PRIORITY") or 0)
    except ValueError:
        return 0
    return p if 0 <= p <= 9 else 0


def priority_name(p: int) -> str | None:
    return None if not p else "high" if p < 5 else "medium" if p == 5 else "low"


def sort_of(t: Todo) -> int | None:
    """Where the task stands in its list's manual order (X-APPLE-SORT-ORDER, else as Reminders counts without one: the
    seconds from 2001 to when it was made)."""
    try:
        n = int(float(_str(t, SORT_ORDER)))
        if n:
            return n
    except ValueError:
        pass
    made = _val(t, "CREATED")
    return int((to_utc(made) - APPLE_EPOCH).total_seconds()) if isinstance(made, dt.datetime) else None


def set_sort(cal: Calendar, n: int) -> None:
    t = todo(cal)
    _set(t, SORT_ORDER, str(int(n)))
    stamp(t)


def after_done_of(t: Todo) -> str | None:
    """How long after it is ticked off the task comes back ("P2W"), or None."""
    try:
        return _after_done(_str(t, AFTER_DONE))
    except ValueError:
        return None


def _after_done(value) -> str | None:
    """A repeat-after-completion duration, checked: P and a number of days, weeks, months or years."""
    if not value:
        return None
    m = re.fullmatch(r"P([1-9]\d{0,2})([DWMY])", str(value).strip().upper())
    if not m:
        raise Invalid("repeatAfter is a number of days, weeks, months or years as an ISO 8601 duration: P3D, P2W, P1M, P1Y")
    return m.group(0)


def alarms_of(t: Todo, tzname: str | None = None) -> list[str]:
    """When each alert goes off, as ISO date-times: absolute triggers as they are, relative ones from the due time (or
    the start, for RELATED=START with a start)."""
    out = []
    for a in t.walk("VALARM"):
        tr = a.get("TRIGGER")
        if tr is None:
            continue
        v = tr.dt
        if isinstance(v, dt.timedelta):
            rel = str(tr.params.get("RELATED", "START")).upper()
            base = _val(t, "DTSTART") if rel == "START" and t.get("DTSTART") is not None else due_of(t)
            if base is None:
                continue
            if not isinstance(base, dt.datetime):
                base = dt.datetime.combine(base, dt.time(9, 0), zone(tzname))  # an all-day task's alerts: from 9 in the morning
            v = base + v
        if isinstance(v, dt.datetime):
            out.append(iso(v if v.tzinfo else v.replace(tzinfo=zone(tzname))))
    return sorted(set(out))


def index(cal: Calendar, tzname: str | None = None) -> dict:
    """What the tasks table keeps beside the object."""
    t = todo(cal)
    uid = _str(t, "UID")
    if not uid:
        raise Invalid("A task without a UID")
    due, start, done_at = due_of(t), _val(t, "DTSTART"), _val(t, "COMPLETED")
    st = status_of(t)
    return {"uid": uid, "summary": _str(t, "SUMMARY")[:512], "description": _str(t, "DESCRIPTION") or None, "status": st,
            "done": int(st in ("COMPLETED", "CANCELLED")), "priority": priority_of(t),
            "due": naive_utc(due, tzname) if due is not None else None, "due_all_day": int(due is not None and not isinstance(due, dt.datetime)),
            "start": naive_utc(start, tzname) if start is not None else None,
            "completed_at": naive_utc(done_at, tzname) if isinstance(done_at, dt.datetime) else None,
            "parent_uid": (parent_of(t) or "")[:255] or None, "rrule": (rrule_text(t) or "")[:1024] or None, "sort_order": sort_of(t)}


def todo_json(cal: Calendar, tzname: str | None = None) -> dict:
    """A task as the REST API and the web app see it."""
    t = todo(cal)
    due, start, done_at = due_of(t), _val(t, "DTSTART"), _val(t, "COMPLETED")
    st = status_of(t)
    p = priority_of(t)
    pct = _str(t, "PERCENT-COMPLETE")
    return {"uid": _str(t, "UID"), "title": _str(t, "SUMMARY"), "notes": _str(t, "DESCRIPTION") or None,
            "status": st.lower(), "done": st in ("COMPLETED", "CANCELLED"),
            "completedAt": iso(done_at) if isinstance(done_at, dt.datetime) else None,
            "due": iso(due), "dueAllDay": due is not None and not isinstance(due, dt.datetime), "start": iso(start),
            "priority": priority_name(p), "priorityValue": p, "percent": int(pct) if pct.isdigit() else None,
            "url": _str(t, "URL") or None, "location": _str(t, "LOCATION") or None, "categories": categories_of(t),
            "parent": parent_of(t), "rrule": rrule_text(t), "repeatAfter": after_done_of(t), "alarms": alarms_of(t, tzname),
            "sortOrder": sort_of(t)}


# ------------------------------------------------------------------ writing

def _set(t, name: str, value, params: dict | None = None) -> None:
    if name in t:
        del t[name]
    if value not in (None, "", []):
        t.add(name, value, parameters=params)


def safe_url(u) -> str | None:
    """A link on a task: http(s) or mailto only (never javascript: or the like), else none."""
    u = (u or "").strip()[:2000]
    return u if re.match(r"^(https?://|mailto:)", u, re.I) else None


def _rrule(value: str | dict | None):
    if not value:
        return None
    if isinstance(value, dict):
        value = ";".join(f"{k.upper()}={','.join(map(str, v)) if isinstance(v, list) else v}" for k, v in value.items())
    value = str(value).strip()
    if value.upper().startswith("RRULE:"):
        value = value[6:]
    try:
        r = vRecur.from_ical(value)
    except Exception as e:  # noqa: BLE001
        raise Invalid(f"Not a repeat rule (RRULE): {value}") from e
    if not r.get("FREQ"):
        raise Invalid("A repeat rule needs FREQ (DAILY, WEEKLY, MONTHLY or YEARLY)")
    if str(r["FREQ"][0]).upper() in ("SECONDLY", "MINUTELY", "HOURLY"):
        raise Invalid("A task repeats daily at most")
    return r


def _fit_until(r: vRecur, anchor) -> vRecur:
    """UNTIL has to be of the anchor's kind (RFC 5545): a date for a date, UTC for a zoned time."""
    u = r.get("UNTIL")
    if not u or anchor is None:
        return r
    u = u[0] if isinstance(u, list) else u
    if not isinstance(anchor, dt.datetime):
        r["UNTIL"] = [u.date() if isinstance(u, dt.datetime) else u]
    else:
        if not isinstance(u, dt.datetime):
            u = dt.datetime.combine(u, dt.time(23, 59, 59), anchor.tzinfo)
        r["UNTIL"] = [to_utc(u) if anchor.tzinfo else u.replace(tzinfo=None)]
    return r


def _alarm(at: dt.datetime, title: str) -> Alarm:
    a = Alarm()
    a.add("ACTION", "DISPLAY")
    a.add("DESCRIPTION", title or "Reminder")
    a.add("TRIGGER", to_utc(at), parameters={"VALUE": "DATE-TIME"})
    a.add("UID", str(uuidlib.uuid4()).upper())
    return a


def _priority(v) -> int:
    if isinstance(v, str) and v.strip().lower() in PRIORITIES:
        return PRIORITIES[v.strip().lower()]
    try:
        p = int(v or 0)
    except (TypeError, ValueError):
        raise Invalid("priority is high, medium, low or none (or 0-9)")
    if not 0 <= p <= 9:
        raise Invalid("priority is 0 (none) to 9")
    return p


def _wall(d, tzname: str | None) -> dt.datetime:
    """A date or time as the clock on the wall shows it (a date: its midnight)."""
    if not isinstance(d, dt.datetime):
        return dt.datetime(d.year, d.month, d.day)
    return (d.astimezone(zone(tzname)) if d.tzinfo else d).replace(tzinfo=None)


def shift_alarms(t: Todo, old, new, tzname: str | None = None) -> None:
    """The alerts follow the due date: each absolute one moves by as much as the due did, on the clock (an alert at
    9:00 stays at 9:00 across a change of the clocks). Alerts counted from the due time move by themselves."""
    if old is None or new is None:
        return
    if isinstance(old, dt.datetime) and isinstance(new, dt.datetime):
        delta = _wall(new, tzname) - _wall(old, tzname)
    else:  # a day became a time or the other way round: the alerts move by whole days
        delta = _wall(new, tzname).date() - _wall(old, tzname).date()
    if not delta:
        return
    for a in t.walk("VALARM"):
        tr = a.get("TRIGGER")
        if tr is not None and isinstance(tr.dt, dt.datetime):
            at = tr.dt if tr.dt.tzinfo else tr.dt.replace(tzinfo=zone(tzname))
            z = zone(tzname)
            a["TRIGGER"] = vDDDTypes(((at.astimezone(z).replace(tzinfo=None) + delta).replace(tzinfo=z)).astimezone(UTC))
            a["TRIGGER"].params["VALUE"] = "DATE-TIME"
        if "ACKNOWLEDGED" in a:
            del a["ACKNOWLEDGED"]


def set_done(t: Todo, done: bool) -> None:
    """Mark the VTODO itself done or not done (no repeat handling: see complete)."""
    if done:
        now = dt.datetime.now(UTC).replace(microsecond=0)
        _set(t, "STATUS", "COMPLETED")
        _set(t, "COMPLETED", now)
        _set(t, "PERCENT-COMPLETE", 100)
    else:
        _set(t, "STATUS", "NEEDS-ACTION")
        _set(t, "COMPLETED", None)
        _set(t, "PERCENT-COMPLETE", None)


def apply(t: Todo, data: dict, tzname: str | None = None) -> Todo:
    """Change the fields named in data on this VTODO (others stay as they are)."""
    tz = data.get("timezone") if valid_tz(data.get("timezone")) else (tzname if valid_tz(tzname) else default_tz())
    if "title" in data:
        _set(t, "SUMMARY", (data.get("title") or "").strip()[:500] or None)
    if "notes" in data:
        _set(t, "DESCRIPTION", (data.get("notes") or "").rstrip() or None)
    if "location" in data:
        _set(t, "LOCATION", (data.get("location") or "").strip()[:1000] or None)
    if "url" in data:
        _set(t, "URL", safe_url(data.get("url")))
    if "due" in data:
        old_due, old_start = due_of(t), _val(t, "DTSTART")
        new = parse_when(data["due"], tz) if data.get("due") else None
        if "DURATION" in t:
            del t["DURATION"]
        _set(t, "DUE", new)
        if "start" not in data and old_start is not None:
            # a start that went with the old due (Apple writes both at the same moment) follows it; one of the other
            # kind, or after the new due, would make the object invalid (RFC 5545: DUE not before DTSTART, same kind)
            if new is None or old_start == old_due or type(old_start) is not type(new) or to_utc(old_start, tz) > to_utc(new, tz):
                _set(t, "DTSTART", new)
        if "alarms" not in data:
            shift_alarms(t, old_due, new, tz)
    if "start" in data:
        st = parse_when(data["start"], tz) if data.get("start") else None
        d = due_of(t)
        if st is not None and d is not None and (type(st) is not type(d) or to_utc(st, tz) > to_utc(d, tz)):
            raise Invalid("The start is after the due date (or not of the same kind: both dates, or both times)")
        _set(t, "DTSTART", st)
    if "priority" in data:
        p = _priority(data.get("priority"))
        _set(t, "PRIORITY", p or None)
    if "percent" in data:
        pc = data.get("percent")
        _set(t, "PERCENT-COMPLETE", max(0, min(100, int(pc))) if pc not in (None, "") else None)
    if "status" in data and data.get("status"):
        st = str(data["status"]).upper()
        if st not in STATUSES:
            raise Invalid("status is needs-action, in-process, completed or cancelled")
        if st == "COMPLETED":
            set_done(t, True)
        else:
            set_done(t, False)
            _set(t, "STATUS", st)
    if "done" in data and data.get("done") is not None and bool(data["done"]) != (status_of(t) in ("COMPLETED", "CANCELLED")):
        set_done(t, bool(data["done"]))
    if "categories" in data:
        cats = [str(c).strip()[:64] for c in (data.get("categories") or []) if str(c).strip()]
        _set(t, "CATEGORIES", cats or None)
    if "parent" in data:
        if "RELATED-TO" in t:
            del t["RELATED-TO"]
        p = str(data.get("parent") or "").strip()[:255]
        if p:
            if p == _str(t, "UID"):
                raise Invalid("A task cannot be its own subtask")
            t.add("RELATED-TO", p, parameters={"RELTYPE": "PARENT"})
    if "rrule" in data:
        r = _rrule(data.get("rrule"))
        anchor = _val(t, "DTSTART") if t.get("DTSTART") is not None else due_of(t)
        if r is not None and anchor is None:
            raise Invalid("A repeating task needs a due date")
        _set(t, "RRULE", _fit_until(r, anchor) if r is not None else None)
        if r is not None and "repeatAfter" not in data:  # one way of repeating at a time
            _set(t, AFTER_DONE, None)
    if "repeatAfter" in data:
        rule = _after_done(data.get("repeatAfter"))
        _set(t, AFTER_DONE, rule)
        if rule:
            _set(t, "RRULE", None)
    if "alarms" in data:
        t.subcomponents[:] = [a for a in t.subcomponents if a.name != "VALARM"]
        for x in data.get("alarms") or []:
            at = parse_when(str(x), tz)
            if not isinstance(at, dt.datetime):
                at = dt.datetime.combine(at, dt.time(9, 0), zone(tz))
            t.add_component(_alarm(at, _str(t, "SUMMARY")))
    stamp(t)
    return t


def stamp(t: Todo, bump: bool = True) -> None:
    now = dt.datetime.now(UTC).replace(microsecond=0)
    _set(t, "DTSTAMP", now)
    _set(t, "LAST-MODIFIED", now)
    if "CREATED" not in t:
        t.add("CREATED", now)
    if bump:
        _set(t, "SEQUENCE", int(_str(t, "SEQUENCE") or 0) + (1 if "SEQUENCE" in t else 0))


def finish(cal: Calendar) -> Calendar:
    """VTIMEZONE definitions for every zone the task uses (reminders apps want them), and the header."""
    if "PRODID" not in cal:
        cal.add("PRODID", PRODID)
    if "VERSION" not in cal:
        cal.add("VERSION", "2.0")
    try:
        cal.add_missing_timezones()
    except Exception:  # noqa: BLE001 - a zone the library cannot describe: apps fall back on its name
        pass
    return cal


def build(data: dict, tzname: str | None = None) -> Calendar:
    """A new task object from the JSON fields."""
    cal = new_calendar()
    t = Todo()
    t.add("UID", (data.get("uid") or "").strip()[:250] or new_uid())
    if not data.get("done") and not data.get("status"):
        t.add("STATUS", "NEEDS-ACTION")
    apply(t, {**{"title": ""}, **data}, tzname)
    if "SEQUENCE" not in t:
        t.add("SEQUENCE", 0)
    cal.add_component(t)
    return finish(cal)


def edit(cal: Calendar, data: dict, tzname: str | None = None) -> Calendar:
    apply(todo(cal), data, tzname)
    return finish(cal)


def next_due(t: Todo, tzname: str | None = None):
    """For a repeating task: (delta, the rule with COUNT one lower) to its next occurrence after the current one, or
    None when the series is over (or cannot be worked out)."""
    rt = rrule_text(t)
    anchor = _val(t, "DTSTART") if t.get("DTSTART") is not None else due_of(t)
    if not rt or anchor is None:
        return None
    all_day = not isinstance(anchor, dt.datetime)
    start = dt.datetime.combine(anchor, dt.time()) if all_day else anchor
    try:
        rule = du_rrule.rrulestr(rt, dtstart=start, ignoretz=all_day or start.tzinfo is None)
        nxt = rule.after(start, inc=False)
    except (ValueError, TypeError):
        return None
    if nxt is None:
        return None
    r = t["RRULE"] if not isinstance(t["RRULE"], list) else t["RRULE"][0]
    if r.get("COUNT"):
        n = int(r["COUNT"][0] if isinstance(r["COUNT"], list) else r["COUNT"])
        if n <= 1:
            return None
        r["COUNT"] = [n - 1]
    return nxt - start, r


def _add(day: dt.date, after: str) -> dt.date:
    """A day, a repeat-after-completion duration later."""
    return day + relativedelta(**{UNITS[after[-1]]: int(after[1:-1])})


def _move_to(t: Todo, new, tzname: str | None) -> None:
    """Open again with a new due date: the start that went with it and the alerts move along."""
    old, start = due_of(t), _val(t, "DTSTART")
    if "DURATION" in t:
        del t["DURATION"]
    _set(t, "DUE", new)
    if start is not None:
        if old is not None and type(start) is type(old) and type(old) is type(new):
            _set(t, "DTSTART", start + (new - old))
        else:
            _set(t, "DTSTART", new)
    shift_alarms(t, old, new, tzname)
    for a in t.walk("VALARM"):
        if "ACKNOWLEDGED" in a:
            del a["ACKNOWLEDGED"]
    set_done(t, False)
    stamp(t)


def complete(cal: Calendar, done: bool, tzname: str | None = None) -> bool:
    """Tick a task off (done) or open it again. A repeating task that is ticked off moves on to its next occurrence
    instead, as Apple Reminders does: the due date, the start and the alerts move by as much, and it stays open. One
    that repeats after completion comes back that long after today (tzname's today), at its usual time. True when it
    moved on."""
    t = todo(cal)
    if done:
        after = after_done_of(t)
        if after:
            old = due_of(t)
            if isinstance(old, dt.datetime):
                z = old.tzinfo or zone(tzname)
                day = _add(dt.datetime.now(z).date(), after)
                new = dt.datetime.combine(day, old.replace(tzinfo=None).time(), old.tzinfo)
            else:
                new = _add(dt.datetime.now(zone(tzname)).date(), after)
            _move_to(t, new, tzname)
            return True
        step = next_due(t, tzname)
        if step is not None:
            delta, r = step
            by = "DUE" if _val(t, "DUE") is not None else "DTSTART"
            was = _val(t, by)
            for k in ("DUE", "DTSTART"):
                v = _val(t, k)
                if v is not None:
                    _set(t, k, v + delta if isinstance(v, dt.datetime) else v + dt.timedelta(days=delta.days))
            t["RRULE"] = r
            shift_alarms(t, was, _val(t, by), tzname)  # on the clock: an alert at 9:00 stays at 9:00 when the clocks change in between
            for a in t.walk("VALARM"):
                if "ACKNOWLEDGED" in a:
                    del a["ACKNOWLEDGED"]
            set_done(t, False)
            stamp(t)
            return True
    set_done(t, done)
    stamp(t)
    return False


def keep_after_done(old: Calendar, new: Calendar, tzname: str | None = None) -> bool:
    """A reminders app saved a task that repeats after completion. The rule is ioTask's own, so an app that dropped it
    gets it back; and when the app ticked the task off, it comes back with its next due date instead of closing. True
    when the object was changed (the app then fetches it again)."""
    rule = after_done_of(todo(old))
    if not rule:
        return False
    t, changed = todo(new), False
    if not after_done_of(t):
        if rrule_text(t):  # the app gave it a repeat of its own: that one counts now
            return False
        _set(t, AFTER_DONE, rule)
        changed = True
    if status_of(t) == "COMPLETED" and status_of(todo(old)) != "COMPLETED":
        complete(new, True, tzname)
        changed = True
    return changed


def postpone(cal: Calendar, day: dt.date, tzname: str | None = None) -> None:
    """Due on another day, at the time it had (the alerts follow)."""
    t = todo(cal)
    old = due_of(t)
    if isinstance(old, dt.datetime):
        new = dt.datetime.combine(day, old.replace(tzinfo=None).time(), old.tzinfo)
    else:
        new = day
    start = _val(t, "DTSTART")
    if "DURATION" in t:
        del t["DURATION"]
    _set(t, "DUE", new)
    if start is not None:
        _set(t, "DTSTART", start + (new - old) if old is not None and type(start) is type(old) else new)
    shift_alarms(t, old, new, tzname)
    stamp(t)


def feed(objects: list, name: str, color: str | None = None) -> str:
    """Many task objects (parsed, or as text) as one VCALENDAR (an export), each VTIMEZONE once."""
    out = new_calendar()
    out.add("X-WR-CALNAME", name)
    if color:
        out.add("X-APPLE-CALENDAR-COLOR", color)
    tzs: dict = {}
    items = []
    for o in objects:
        try:
            c = o if isinstance(o, Calendar) else parse(o)
        except ValueError:
            continue
        for sub in c.subcomponents:
            if sub.name == "VTIMEZONE":
                tzs.setdefault(str(sub.get("TZID")), sub)
            elif sub.name == "VTODO":
                items.append(sub)
    for z in tzs.values():
        out.add_component(z)
    for i in items:
        out.add_component(i)
    return out.to_ical().decode("utf-8")


def vtimezone(name: str | None) -> str | None:
    """A VTIMEZONE for a zone (CalDAV's calendar-timezone)."""
    if not name:
        return None
    cal = new_calendar()
    ev = Event()
    ev.add("DTSTART", dt.datetime(2026, 1, 1, tzinfo=zone(name)))
    cal.add_component(ev)
    try:
        cal.add_missing_timezones()
    except Exception:  # noqa: BLE001
        return None
    cal.subcomponents[:] = [c for c in cal.subcomponents if c.name == "VTIMEZONE"]
    return text(cal) if cal.subcomponents else None
