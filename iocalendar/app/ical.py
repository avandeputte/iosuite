"""iCalendar (RFC 5545) and jCal (RFC 7265): reading what calendar apps send, writing what the web app makes, the
columns the app searches and draws from, and the occurrences of a repeating event.

An event is kept as its whole iCalendar object (VCALENDAR with one or more VEVENTs of the same UID: the master and
the occurrences that were changed, each with a RECURRENCE-ID). The web app edits a few fields of it; everything else a
calendar app put there (alarms it acknowledged, attachments, X- properties) stays as it was.
"""
import copy
import datetime as dt
import hashlib
import json
import os
import re
import uuid as uuidlib
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import recurring_ical_events
from icalendar import Alarm, Calendar, Event, vCalAddress, vRecur, vText

from app import __version__, config

PRODID = f"-//iothing//ioCalendar {__version__}//EN"
UTC = dt.timezone.utc
FAR = dt.datetime(2200, 1, 1, tzinfo=UTC)
MAX_LAST = 20000  # occurrences counted to find where a bounded series ends; beyond that it counts as endless
REMINDER_DESC = "Reminder"


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
    """The server's time zone: floating times (no zone) and new events without one are read in it."""
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


def tz_name(d) -> str | None:
    """The IANA name of a datetime's zone (None for floating times and dates; 'UTC' for UTC)."""
    if not isinstance(d, dt.datetime) or d.tzinfo is None:
        return None
    k = getattr(d.tzinfo, "key", None) or getattr(d.tzinfo, "zone", None)
    if k:
        return k
    if d.utcoffset() == dt.timedelta(0):
        return "UTC"
    try:
        from icalendar.timezone import tzid_from_dt
        return tzid_from_dt(d)
    except Exception:  # noqa: BLE001
        return None


def to_utc(d, tzname: str | None = None) -> dt.datetime:
    """A date, floating or zoned datetime as an aware UTC datetime (a date: its midnight UTC; floating: in tzname or
    the server's zone)."""
    if isinstance(d, dt.datetime):
        if d.tzinfo is None:
            d = d.replace(tzinfo=zone(tzname))
        return d.astimezone(UTC)
    return dt.datetime(d.year, d.month, d.day, tzinfo=UTC)


def naive_utc(d, tzname: str | None = None) -> dt.datetime:
    """For the DATETIME columns."""
    return to_utc(d, tzname).replace(tzinfo=None)


def iso(d) -> str:
    """A date as YYYY-MM-DD, a datetime as ISO 8601 with its offset (floating: without one)."""
    if isinstance(d, dt.datetime):
        return d.isoformat(timespec="seconds")
    return d.isoformat()


def parse_when(s: str, tzname: str | None = None, all_day: bool = False):
    """'2026-11-03' (a date) or '2026-11-03T10:00[:00][Z|+01:00]' (a datetime: without an offset it is wall time in
    tzname). ValueError when it is neither."""
    s = (s or "").strip()
    if not s:
        raise ValueError("A date or time is missing")
    if all_day or re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return dt.date.fromisoformat(s[:10])
    d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=zone(tzname))
    elif tzname and valid_tz(tzname):
        d = d.astimezone(ZoneInfo(tzname))
    return d.replace(microsecond=0)


# ------------------------------------------------------------------ reading

def parse(text: str | bytes) -> Calendar:
    """One VCALENDAR; ValueError when the text is not iCalendar."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    text = text.lstrip("\ufeff")
    if "BEGIN:VCALENDAR" not in text.upper():
        raise ValueError("Not an iCalendar object (no BEGIN:VCALENDAR)")
    try:
        cals = Calendar.from_ical(text, multiple=True)
    except Exception as e:  # noqa: BLE001 - the library raises several kinds
        raise ValueError(f"Not valid iCalendar: {e}") from e
    if not cals:
        raise ValueError("No VCALENDAR in the text")
    if len(cals) == 1:
        return cals[0]
    out = cals[0]
    for c in cals[1:]:  # several VCALENDARs in one file (some exports): one calendar with all their components
        for sub in c.subcomponents:
            out.add_component(sub)
    return out


def events_of(cal: Calendar) -> list[Event]:
    return [c for c in cal.subcomponents if c.name == "VEVENT"]


def master_of(comps: list) -> Event | None:
    """The VEVENT without a RECURRENCE-ID (the series, or the one event); for a lone changed occurrence, that one."""
    for c in comps:
        if "RECURRENCE-ID" not in c:
            return c
    return comps[0] if comps else None


def split_by_uid(cal: Calendar) -> list[Calendar]:
    """A calendar with many events (an import, a feed) as one calendar object per UID, each with the VTIMEZONEs it uses."""
    tzs = {str(c.get("TZID")): c for c in cal.subcomponents if c.name == "VTIMEZONE"}
    groups: dict[str, list] = {}
    for ev in events_of(cal):
        uid = str(ev.get("UID") or "").strip() or new_uid()
        if "UID" not in ev:
            ev.add("UID", uid)
        groups.setdefault(uid, []).append(ev)
    out = []
    for uid, comps in groups.items():
        c = new_calendar()
        used = set()
        for ev in comps:
            for k in ("DTSTART", "DTEND", "RECURRENCE-ID", "EXDATE", "RDATE"):
                vals = ev.get(k)
                for v in (vals if isinstance(vals, list) else [vals]):
                    if v is not None and getattr(v, "params", None) and v.params.get("TZID"):
                        used.add(str(v.params["TZID"]))
        for t in sorted(used):
            if t in tzs:
                c.add_component(tzs[t])
        for ev in sorted(comps, key=lambda e: "RECURRENCE-ID" in e):  # the series first, then its changed occurrences
            c.add_component(ev)
        out.append(c)
    return out


def new_calendar() -> Calendar:
    c = Calendar()
    c.add("PRODID", PRODID)
    c.add("VERSION", "2.0")
    return c


def new_uid() -> str:
    return f"{uuidlib.uuid4()}@iocalendar"


def text(cal: Calendar) -> str:
    return cal.to_ical().decode("utf-8")


def etag_of(ics: str) -> str:
    return hashlib.sha1(ics.encode("utf-8")).hexdigest()[:24]


def _start_end(ev: Event, tzname: str | None = None):
    """(start, end) of a VEVENT as written (date or datetime); end from DTEND, DURATION, or the RFC 5545 default."""
    s = ev.get("DTSTART")
    if s is None:
        raise ValueError("An event without a start (DTSTART)")
    start = s.dt
    if ev.get("DTEND") is not None:
        end = ev["DTEND"].dt
    elif ev.get("DURATION") is not None:
        end = start + ev["DURATION"].dt
    else:
        end = start + dt.timedelta(days=1) if not isinstance(start, dt.datetime) else start
    if isinstance(start, dt.datetime) != isinstance(end, dt.datetime):  # mixed: follow the start
        end = (dt.datetime.combine(end, dt.time(), start.tzinfo) if isinstance(start, dt.datetime) else end.date())
    if end < start if type(end) is type(start) and not (isinstance(start, dt.datetime) and (start.tzinfo is None) != (end.tzinfo is None)) else False:
        end = start
    return start, end


def _rrule_text(ev: Event) -> str | None:
    r = ev.get("RRULE")
    if r is None:
        return None
    if isinstance(r, list):
        r = r[0]
    return r.to_ical().decode()


def _repeats(ev: Event) -> bool:
    return ev.get("RRULE") is not None or ev.get("RDATE") is not None


def people_of(ev: Event) -> list[dict]:
    out = []
    org = ev.get("ORGANIZER")
    vals = ev.get("ATTENDEE")
    vals = vals if isinstance(vals, list) else ([vals] if vals is not None else [])
    for role, v in ([("organizer", org)] if org is not None else []) + [("attendee", a) for a in vals]:
        addr = str(v)
        email = addr[7:] if addr.lower().startswith("mailto:") else None
        name = v.params.get("CN") if hasattr(v, "params") else None
        cid = v.params.get("X-IOCONTACTS-ID") if hasattr(v, "params") else None
        if not name and not email:
            m = re.match(r"urn:x-iocalendar:person:(.*)$", addr)
            name = m.group(1).replace("-", " ") if m else None
        if not (name or email):
            continue
        out.append({"name": str(name) if name else None, "email": email or None,
                    "contactId": int(cid) if cid and str(cid).isdigit() else None, "role": role,
                    "status": str(v.params.get("PARTSTAT", "")).lower() or None if hasattr(v, "params") else None})
    return out


def reminders_of(ev: Event) -> list[int]:
    """Minutes before the start of each alarm that is relative to the start (the ones the web app shows and edits)."""
    out = []
    for a in ev.walk("VALARM"):
        t = a.get("TRIGGER")
        if t is None or not isinstance(t.dt, dt.timedelta) or str(t.params.get("RELATED", "START")).upper() != "START":
            continue
        out.append(int(round(-t.dt.total_seconds() / 60)))
    return sorted(set(out))


def index(cal: Calendar, tzname: str | None = None) -> dict:
    """What the events table keeps beside the object: uid, summary, location, description, all_day, dtstart, dtend,
    tzid, rrule, status, range_start, range_end (naive UTC; range_end None: endless) and the people."""
    comps = events_of(cal)
    if not comps:
        raise ValueError("No VEVENT in the calendar object (ioCalendar keeps events)")
    uids = {str(c.get("UID") or "") for c in comps}
    if len(uids) != 1 or not next(iter(uids)):
        raise ValueError("A calendar object holds the events of one UID")
    m = master_of(comps)
    start, end = _start_end(m)
    tzid = tz_name(start) or (None if isinstance(start, dt.datetime) and start.tzinfo else None)
    all_day = not isinstance(start, dt.datetime)
    lo, hi = to_utc(start, tzname), to_utc(end, tzname)
    endless = False
    for c in comps:
        if c is m:
            continue
        try:
            s2, e2 = _start_end(c)
        except ValueError:
            continue
        lo, hi = min(lo, to_utc(s2, tzname)), max(hi, to_utc(e2, tzname))
    if _repeats(m):
        r = m.get("RRULE")
        r = r[0] if isinstance(r, list) else r
        if r is not None and not r.get("COUNT") and not r.get("UNTIL"):
            endless = True
        else:
            hi = max(hi, _last_end(cal, lo, tzname) or hi)
    people = []
    seen = set()
    for c in [m] + [x for x in comps if x is not m]:
        for p in people_of(c):
            k = (p["email"] or "", p["name"] or "")
            if k not in seen:
                seen.add(k)
                people.append(p)
    status = str(m.get("STATUS") or "").upper() or None
    return {"uid": str(m["UID"]), "summary": str(m.get("SUMMARY") or "")[:512], "location": (str(m.get("LOCATION")) or None) if m.get("LOCATION") else None,
            "description": str(m.get("DESCRIPTION")) if m.get("DESCRIPTION") else None, "all_day": 1 if all_day else 0,
            "dtstart": naive_utc(start, tzname), "dtend": naive_utc(end, tzname), "tzid": tzid,
            "rrule": _rrule_text(m), "status": status, "range_start": lo.replace(tzinfo=None),
            "range_end": None if endless else hi.replace(tzinfo=None), "people": people}


def _last_end(cal: Calendar, lo: dt.datetime, tzname: str | None) -> dt.datetime | None:
    last = None
    try:
        for i, occ in enumerate(recurring_ical_events.of(cal).between(lo - dt.timedelta(days=1), FAR)):
            s, e = _start_end(occ)
            e = to_utc(e, tzname)
            last = e if last is None or e > last else last
            if i > MAX_LAST:
                return None
    except Exception:  # noqa: BLE001 - a rule the library cannot expand: kept, shown from its first date on
        return None
    return last


# ------------------------------------------------------------------ occurrences

def occurrences(cal: Calendar, start: dt.datetime, end: dt.datetime, tzname: str | None = None) -> list[dict]:
    """The occurrences that overlap [start, end): {start, end, allDay, recurrenceId, title, location, status, override}."""
    comps = events_of(cal)
    m = master_of(comps)
    if m is None:
        return []
    recurring = _repeats(m) or any("RECURRENCE-ID" in c for c in comps)
    out = []
    try:
        found = recurring_ical_events.of(cal).between(start, end)
    except Exception:  # noqa: BLE001 - an object the library cannot expand: its master only
        found = [m]
    for occ in found:
        s, e = _start_end(occ)
        if to_utc(e, tzname) <= start and not (to_utc(s, tzname) >= start):
            continue
        rid = occ.get("RECURRENCE-ID")
        out.append({"start": s, "end": e, "allDay": not isinstance(s, dt.datetime),
                    "recurrenceId": iso(rid.dt) if (recurring and rid is not None) else None,
                    "title": str(occ.get("SUMMARY") or ""), "location": str(occ.get("LOCATION") or "") or None,
                    "status": str(occ.get("STATUS") or "").upper() or None,
                    "transparent": str(occ.get("TRANSP") or "").upper() == "TRANSPARENT",
                    "people": [p["name"] or p["email"] for p in people_of(occ)], "categories": _categories(occ)})
    return out


# ------------------------------------------------------------------ the JSON shape

def event_json(cal: Calendar, recurrence_id: str | None = None) -> dict:
    """The fields the web app and the REST API show and edit, for the series (or one changed occurrence)."""
    comps = events_of(cal)
    m = master_of(comps)
    ev = m
    if recurrence_id:
        ev = _find_override(comps, recurrence_id) or m
    s, e = _start_end(ev)
    tzid = tz_name(s)
    all_day = not isinstance(s, dt.datetime)
    out = {"uid": str(m["UID"]), "title": str(ev.get("SUMMARY") or ""), "location": str(ev.get("LOCATION") or "") or None,
           "notes": str(ev.get("DESCRIPTION") or "") or None, "allDay": all_day, "start": iso(s), "end": iso(e),
           "timezone": tzid if tzid and tzid != "UTC" else ("UTC" if tzid == "UTC" else None),
           "rrule": _rrule_text(m), "exdates": [], "people": people_of(ev), "reminders": reminders_of(ev),
           "url": str(ev.get("URL") or "") or None, "status": (str(ev.get("STATUS") or "").upper() or None),
           "busy": str(ev.get("TRANSP") or "OPAQUE").upper() != "TRANSPARENT",
           "categories": _categories(ev), "sequence": int(ev.get("SEQUENCE") or 0),
           "overrides": sorted(iso(c["RECURRENCE-ID"].dt) for c in comps if "RECURRENCE-ID" in c)}
    ex = m.get("EXDATE")
    for x in (ex if isinstance(ex, list) else [ex] if ex is not None else []):
        out["exdates"] += [iso(d.dt) for d in x.dts]
    if recurrence_id:
        out["recurrenceId"] = recurrence_id
    return out


def _categories(ev: Event) -> list[str]:
    c = ev.get("CATEGORIES")
    out = []
    for x in (c if isinstance(c, list) else [c] if c is not None else []):
        out += [str(v) for v in getattr(x, "cats", [])]
    return out


def _same_instant(a, b) -> bool:
    if isinstance(a, dt.datetime) and isinstance(b, dt.datetime):
        if (a.tzinfo is None) != (b.tzinfo is None):
            return a.replace(tzinfo=None) == b.replace(tzinfo=None)
        return a == b
    if isinstance(a, dt.datetime) or isinstance(b, dt.datetime):
        return False
    return a == b


def _find_override(comps, recurrence_id: str):
    rid = parse_rid(recurrence_id)
    for c in comps:
        if "RECURRENCE-ID" in c and _same_instant(c["RECURRENCE-ID"].dt, rid):
            return c
    return None


def parse_rid(s: str):
    s = (s or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return dt.date.fromisoformat(s)
    if re.fullmatch(r"\d{8}", s):
        return dt.date(int(s[:4]), int(s[4:6]), int(s[6:]))
    if re.fullmatch(r"\d{8}T\d{6}Z?", s):
        d = dt.datetime.strptime(s[:15], "%Y%m%dT%H%M%S")
        return d.replace(tzinfo=UTC) if s.endswith("Z") else d
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


# ------------------------------------------------------------------ writing (the web app and the REST API)

EDITABLE = ("title", "location", "notes", "allDay", "start", "end", "timezone", "rrule", "exdates", "people", "reminders",
            "url", "status", "busy", "categories")


def _set(ev: Event, name: str, value) -> None:
    if name in ev:
        del ev[name]
    if value not in (None, "", []):
        ev.add(name, value)


def _when(data: dict, ev: Event | None, tzname: str | None):
    """(start, end) for an edit: from data, falling back on the event's own."""
    all_day = data.get("allDay")
    tz = data.get("timezone")
    if ev is not None:
        s0, e0 = _start_end(ev)
        if all_day is None:
            all_day = not isinstance(s0, dt.datetime)
        if tz is None:
            tz = tz_name(s0)
    tz = tz if valid_tz(tz) else (tzname if valid_tz(tzname) else default_tz())
    if "start" in data or ev is None:
        start = parse_when(data.get("start") or "", tz, bool(all_day))
    else:
        start = s0 if (not isinstance(s0, dt.datetime)) == bool(all_day) else parse_when(iso(s0)[:10], tz, bool(all_day))
    if "end" in data and data.get("end"):
        end = parse_when(data["end"], tz, bool(all_day))
    elif ev is not None and "start" in data:  # moved: keep the length
        end = start + (e0 - s0) if type(e0) is type(s0) and isinstance(s0, dt.datetime) == isinstance(start, dt.datetime) else (
            start + dt.timedelta(days=1) if all_day else start + dt.timedelta(hours=1))
    elif ev is not None and type(s0) is type(start):
        end = e0
    else:
        end = start + (dt.timedelta(days=1) if all_day else dt.timedelta(hours=1))
    if isinstance(start, dt.datetime) and start.tzinfo and str(tz) and valid_tz(tz):
        start = start.astimezone(ZoneInfo(tz))
        end = end.astimezone(ZoneInfo(tz)) if isinstance(end, dt.datetime) else end
    if not isinstance(start, dt.datetime) and end <= start:
        end = start + dt.timedelta(days=1)
    if isinstance(start, dt.datetime) and end < start:
        raise ValueError("The event ends before it starts")
    return start, end


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
        raise ValueError(f"Not a repeat rule (RRULE): {value}") from e
    if not r.get("FREQ"):
        raise ValueError("A repeat rule needs FREQ (DAILY, WEEKLY, MONTHLY or YEARLY)")
    return r


def _fit_until(r: vRecur, start) -> vRecur:
    """UNTIL has to be of the start's kind (RFC 5545): a date for an all-day event, UTC for a zoned start."""
    u = r.get("UNTIL")
    if not u:
        return r
    u = u[0] if isinstance(u, list) else u
    if not isinstance(start, dt.datetime):
        r["UNTIL"] = [u.date() if isinstance(u, dt.datetime) else u]
    else:
        if not isinstance(u, dt.datetime):
            u = dt.datetime.combine(u, dt.time(23, 59, 59), start.tzinfo)
        r["UNTIL"] = [to_utc(u) if start.tzinfo else u.replace(tzinfo=None)]
    return r


def _person(p: dict) -> vCalAddress | None:
    name = (p.get("name") or "").strip()[:200]
    email = (p.get("email") or "").strip()[:200]
    if not name and not email:
        return None
    if email:
        a = vCalAddress(f"mailto:{email}")
    else:
        a = vCalAddress("urn:x-iocalendar:person:" + re.sub(r"\s+", "-", name))
    if name:
        a.params["CN"] = vText(name)
    # people noted on an event, not invited: no reply is asked of them
    a.params["ROLE"] = "REQ-PARTICIPANT"
    a.params["PARTSTAT"] = str(p.get("status") or "accepted").upper() if str(p.get("status") or "").upper() in ("ACCEPTED", "DECLINED", "TENTATIVE", "NEEDS-ACTION") else "ACCEPTED"
    a.params["RSVP"] = "FALSE"
    if p.get("contactId"):
        a.params["X-IOCONTACTS-ID"] = str(int(p["contactId"]))
    return a


def _alarm(minutes: int, title: str) -> Alarm:
    a = Alarm()
    a.add("ACTION", "DISPLAY")
    a.add("DESCRIPTION", title or REMINDER_DESC)
    a.add("TRIGGER", dt.timedelta(minutes=-int(minutes)))
    a.add("UID", str(uuidlib.uuid4()).upper())
    return a


def safe_url(u) -> str | None:
    """A link on an event: http(s) or mailto only (never javascript: or the like), else none."""
    u = (u or "").strip()[:2000]
    return u if re.match(r"^(https?://|mailto:)", u, re.I) else None


def apply(ev: Event, data: dict, tzname: str | None = None, series: bool = True) -> Event:
    """Change the fields named in data on this VEVENT (others stay as they are)."""
    if any(k in data for k in ("start", "end", "allDay", "timezone")) or "DTSTART" not in ev:
        start, end = _when(data, ev if "DTSTART" in ev else None, tzname)
        _set(ev, "DTSTART", start)
        if "DURATION" in ev:
            del ev["DURATION"]
        _set(ev, "DTEND", end)
        if series and ev.get("RRULE") is not None and "rrule" not in data:
            ev["RRULE"] = _fit_until(ev["RRULE"] if not isinstance(ev["RRULE"], list) else ev["RRULE"][0], start)
    if "title" in data:
        _set(ev, "SUMMARY", (data.get("title") or "").strip()[:500] or None)
    if "location" in data:
        _set(ev, "LOCATION", (data.get("location") or "").strip()[:1000] or None)
    if "notes" in data:
        _set(ev, "DESCRIPTION", (data.get("notes") or "").rstrip() or None)
    if "url" in data:
        _set(ev, "URL", safe_url(data.get("url")))
    if "status" in data:
        st = str(data.get("status") or "").upper()
        _set(ev, "STATUS", st if st in ("CONFIRMED", "TENTATIVE", "CANCELLED") else None)
    if "busy" in data:
        _set(ev, "TRANSP", "OPAQUE" if data.get("busy") in (None, True) else "TRANSPARENT")
    if "categories" in data:
        cats = [str(c).strip()[:64] for c in (data.get("categories") or []) if str(c).strip()]
        _set(ev, "CATEGORIES", cats or None)
    if series and "rrule" in data:
        r = _rrule(data.get("rrule"))
        _set(ev, "RRULE", _fit_until(r, ev["DTSTART"].dt) if r is not None else None)
        if r is None:
            for k in ("EXDATE", "RDATE"):
                if k in ev:
                    del ev[k]
    if series and "exdates" in data:
        if "EXDATE" in ev:
            del ev["EXDATE"]
        for x in data.get("exdates") or []:
            add_exdate(ev, parse_rid(x) if not isinstance(x, (dt.date, dt.datetime)) else x)
    if "people" in data:
        if "ATTENDEE" in ev:
            del ev["ATTENDEE"]
        for p in data.get("people") or []:
            if isinstance(p, str):
                p = {"name": p}
            if p.get("role") == "organizer":
                continue
            a = _person(p)
            if a is not None:
                ev.add("ATTENDEE", a)
    if "reminders" in data:
        want = sorted({int(m) for m in (data.get("reminders") or []) if str(m).lstrip("-").isdigit() and -10080 <= int(m) <= 40320})
        if want != reminders_of(ev):
            keep = [a for a in ev.subcomponents if a.name != "VALARM" or not (isinstance(a.get("TRIGGER").dt if a.get("TRIGGER") is not None else None, dt.timedelta)
                                                                             and str(a["TRIGGER"].params.get("RELATED", "START")).upper() == "START")]
            ev.subcomponents[:] = keep + [_alarm(m, str(ev.get("SUMMARY") or "")) for m in want]
    stamp(ev)
    return ev


def stamp(ev: Event, bump: bool = True) -> None:
    now = dt.datetime.now(UTC).replace(microsecond=0)
    _set(ev, "DTSTAMP", now)
    _set(ev, "LAST-MODIFIED", now)
    if "CREATED" not in ev:
        ev.add("CREATED", now)
    if bump:
        _set(ev, "SEQUENCE", int(ev.get("SEQUENCE") or 0) + (1 if "SEQUENCE" in ev else 0))


def add_exdate(ev: Event, when) -> None:
    """Leave one occurrence out of the series (the value in the start's own form)."""
    s = ev["DTSTART"].dt
    if isinstance(s, dt.datetime):
        if not isinstance(when, dt.datetime):
            when = dt.datetime.combine(when, s.timetz())
        when = when.astimezone(s.tzinfo) if (s.tzinfo and when.tzinfo) else (when.replace(tzinfo=None) if not s.tzinfo else when.replace(tzinfo=s.tzinfo))
    elif isinstance(when, dt.datetime):
        when = when.date()
    ev.add("EXDATE", when)


def finish(cal: Calendar) -> Calendar:
    """VTIMEZONE definitions for every zone the events use (calendar apps want them), and the header."""
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
    """A new calendar object from the JSON fields."""
    cal = new_calendar()
    ev = Event()
    ev.add("UID", (data.get("uid") or "").strip()[:250] or new_uid())
    apply(ev, {**{"title": ""}, **data}, tzname)
    if "SEQUENCE" not in ev:
        ev.add("SEQUENCE", 0)
    cal.add_component(ev)
    return finish(cal)


def edit(cal: Calendar, data: dict, tzname: str | None = None, recurrence_id: str | None = None) -> Calendar:
    """Change the series (recurrence_id None) or one occurrence of it (which becomes a changed occurrence, RFC 5545
    RECURRENCE-ID, starting from the series' fields)."""
    comps = events_of(cal)
    m = master_of(comps)
    if not recurrence_id:
        apply(m, data, tzname)
        if any(k in data for k in ("start", "allDay", "timezone")):
            _realign_overrides(cal, m)
        return finish(cal)
    ov = _find_override(comps, recurrence_id)
    if ov is None:
        ov = Event()
        for k, v in m.property_items(recursive=False):
            if k in ("BEGIN", "END", "RRULE", "RDATE", "EXDATE", "DTSTART", "DTEND", "DURATION", "RECURRENCE-ID"):
                continue
            ov.add(k, v, encode=False)
        for sub in m.subcomponents:  # its own copies: an alarm changed on the occurrence must not change the series'
            ov.add_component(copy.deepcopy(sub))
        rid = _rid_value(m, parse_rid(recurrence_id))
        ov.add("RECURRENCE-ID", rid)
        s0, e0 = _start_end(m)
        ov.add("DTSTART", rid)
        ov.add("DTEND", rid + (e0 - s0))
        cal.add_component(ov)
    apply(ov, data, tzname, series=False)
    return finish(cal)


def _rid_value(m: Event, rid):
    """An occurrence's original start in the series' own form (zone, or date)."""
    s = m["DTSTART"].dt
    if isinstance(s, dt.datetime):
        if not isinstance(rid, dt.datetime):
            rid = dt.datetime.combine(rid, s.timetz())
        if s.tzinfo is not None:
            rid = (rid if rid.tzinfo else rid.replace(tzinfo=s.tzinfo)).astimezone(s.tzinfo)
        else:
            rid = rid.replace(tzinfo=None)
        return rid
    return rid.date() if isinstance(rid, dt.datetime) else rid


def _realign_overrides(cal: Calendar, m: Event) -> None:
    """After the series moved to another time or kind, its changed occurrences and left-out dates no longer name
    occurrences that exist: they are dropped (the calendar apps do the same)."""
    cal.subcomponents[:] = [c for c in cal.subcomponents if not (c.name == "VEVENT" and "RECURRENCE-ID" in c)]
    if "EXDATE" in m:
        del m["EXDATE"]


def remove_occurrence(cal: Calendar, recurrence_id: str) -> Calendar:
    """Delete one occurrence: an EXDATE on the series, and its changed occurrence (if any) goes."""
    comps = events_of(cal)
    m = master_of(comps)
    rid = parse_rid(recurrence_id)
    cal.subcomponents[:] = [c for c in cal.subcomponents if c is m or not (c.name == "VEVENT" and "RECURRENCE-ID" in c and _same_instant(c["RECURRENCE-ID"].dt, _rid_value(m, rid)))]
    if _repeats(m):
        add_exdate(m, _rid_value(m, rid))
    stamp(m)
    return finish(cal)


def end_series_before(cal: Calendar, recurrence_id: str) -> Calendar:
    """Make the series stop before this occurrence (for 'this and following'): UNTIL just before it; changed
    occurrences and left-out dates from it on go."""
    comps = events_of(cal)
    m = master_of(comps)
    rid = _rid_value(m, parse_rid(recurrence_id))
    r = m.get("RRULE")
    r = r[0] if isinstance(r, list) else r
    if r is not None:
        r = vRecur(dict(r))
        r.pop("COUNT", None)
        if isinstance(rid, dt.datetime):
            r["UNTIL"] = [to_utc(rid - dt.timedelta(seconds=1))] if rid.tzinfo else [rid - dt.timedelta(seconds=1)]
        else:
            r["UNTIL"] = [rid - dt.timedelta(days=1)]
        _set(m, "RRULE", r)

    def later(v) -> bool:
        a, b = v, rid
        if isinstance(a, dt.datetime) and isinstance(b, dt.datetime):
            return (a if a.tzinfo or not b.tzinfo else a.replace(tzinfo=b.tzinfo)) >= (b if b.tzinfo or not a.tzinfo else b.replace(tzinfo=a.tzinfo))
        a = a.date() if isinstance(a, dt.datetime) else a
        b = b.date() if isinstance(b, dt.datetime) else b
        return a >= b
    cal.subcomponents[:] = [c for c in cal.subcomponents if c is m or not (c.name == "VEVENT" and "RECURRENCE-ID" in c and later(c["RECURRENCE-ID"].dt))]
    ex = m.get("EXDATE")
    if ex is not None:
        keep = [d.dt for x in (ex if isinstance(ex, list) else [ex]) for d in x.dts if not later(d.dt)]
        del m["EXDATE"]
        for d in keep:
            m.add("EXDATE", d)
    rd = m.get("RDATE")
    if rd is not None:
        keep = [d.dt for x in (rd if isinstance(rd, list) else [rd]) for d in x.dts if not isinstance(d.dt, tuple) and not later(d.dt)]
        del m["RDATE"]
        for d in keep:
            m.add("RDATE", d)
    stamp(m)
    return finish(cal)


def carry_over(old: Calendar, new: Calendar, recurrence_id: str, data: dict, tzname: str | None = None) -> None:
    """When a series is split at an occurrence into a new one with the same schedule: the dates left out and the changed
    occurrences from that one on belong to the new series (the edit is made on those occurrences too)."""
    comps = events_of(old)
    m = master_of(comps)
    rid = _rid_value(m, parse_rid(recurrence_id))
    nm = master_of(events_of(new))

    def later(v) -> bool:
        a, b = v, rid
        if isinstance(a, dt.datetime) and isinstance(b, dt.datetime):
            return (a if a.tzinfo or not b.tzinfo else a.replace(tzinfo=b.tzinfo)) >= (b if b.tzinfo or not a.tzinfo else b.replace(tzinfo=a.tzinfo))
        a = a.date() if isinstance(a, dt.datetime) else a
        b = b.date() if isinstance(b, dt.datetime) else b
        return a >= b
    ex = m.get("EXDATE")
    carried = [d.dt for x in (ex if isinstance(ex, list) else [ex] if ex is not None else []) for d in x.dts if later(d.dt)]
    for d in carried:
        add_exdate(nm, d)
    r = nm.get("RRULE")
    r = r[0] if isinstance(r, list) else r
    if carried and r is not None and r.get("COUNT"):  # a left-out date still takes one of the COUNT slots
        r = vRecur(dict(r))
        r["COUNT"] = [int(r["COUNT"][0]) + len(carried)]
        _set(nm, "RRULE", r)
    for c in comps:
        if c is not m and "RECURRENCE-ID" in c and later(c["RECURRENCE-ID"].dt):
            ov = copy.deepcopy(c)
            _set(ov, "UID", nm["UID"])
            apply(ov, data, tzname, series=False)
            new.add_component(ov)


def remaining_count(cal: Calendar, recurrence_id: str, tzname: str | None = None) -> int | None:
    """For a series with COUNT: how many occurrences are left from this one on (a split series keeps that many)."""
    m = master_of(events_of(cal))
    r = m.get("RRULE")
    r = r[0] if isinstance(r, list) else r
    if r is None or not r.get("COUNT"):
        return None
    rid = to_utc(_rid_value(m, parse_rid(recurrence_id)), tzname)
    n = 0
    for occ in recurring_ical_events.of(cal).between(to_utc(m["DTSTART"].dt, tzname) - dt.timedelta(days=1), FAR):
        rr = occ.get("RECURRENCE-ID")
        when = to_utc(rr.dt if rr is not None else occ["DTSTART"].dt, tzname)
        if when >= rid:
            n += 1
    return max(1, n)


# ------------------------------------------------------------------ jCal (RFC 7265)

def _jtype(v) -> str:
    from icalendar.prop import (vBoolean, vDDDTypes, vDuration, vFloat, vGeo, vInt, vPeriod, vUri, vUTCOffset, vDDDLists,
                                vCategory, vWeekday, vFrequency)
    if isinstance(v, vDDDTypes):
        x = v.dt
        return "date-time" if isinstance(x, dt.datetime) else "date" if isinstance(x, dt.date) else "duration" if isinstance(x, dt.timedelta) else "period"
    if isinstance(v, vDDDLists):
        x = v.dts[0].dt if v.dts else None
        return "date-time" if isinstance(x, dt.datetime) else "date" if isinstance(x, dt.date) else "period"
    for cls, name in ((vRecur, "recur"), (vCalAddress, "cal-address"), (vUri, "uri"), (vInt, "integer"), (vFloat, "float"),
                      (vBoolean, "boolean"), (vDuration, "duration"), (vUTCOffset, "utc-offset"), (vPeriod, "period"), (vGeo, "float"),
                      (vCategory, "text"), (vWeekday, "text"), (vFrequency, "text")):
        if isinstance(v, cls):
            return name
    return "text" if isinstance(v, (vText, str)) else "unknown"


def _jdate(x) -> str:
    if isinstance(x, dt.datetime):
        s = x.strftime("%Y-%m-%dT%H:%M:%S")
        return s + ("Z" if x.tzinfo is not None and x.utcoffset() == dt.timedelta(0) and tz_name(x) in ("UTC", "Etc/UTC", None) else "")
    return x.isoformat()


def _jvalues(v, t: str) -> list:
    from icalendar.prop import vDDDLists, vGeo
    if t == "recur":
        out = {}
        for k, vals in v.items():
            vals = [(_jdate(x) if isinstance(x, (dt.date, dt.datetime)) else x) for x in vals]
            out[k.lower()] = vals[0] if len(vals) == 1 else vals
        return [out]
    if isinstance(v, vGeo):
        return [[v.latitude, v.longitude]]
    if isinstance(v, vDDDLists):
        return [_jdate(d.dt) for d in v.dts]
    if t in ("date", "date-time"):
        return [_jdate(v.dt)]
    if t == "integer":
        return [int(v)]
    if t == "float":
        return [float(v)]
    if t == "boolean":
        return [bool(v)]
    if hasattr(v, "cats"):
        return [str(c) for c in v.cats]
    raw = v.to_ical()
    raw = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    if t == "text":
        return [str(v)]
    return [raw]


def to_jcal(comp) -> list:
    props = []
    for k, v in comp.property_items(recursive=False, sorted=False):
        if k in ("BEGIN", "END"):
            continue
        for one in (v if isinstance(v, list) else [v]):
            t = _jtype(one)
            params = {pk.lower(): (str(pv) if not isinstance(pv, list) else [str(x) for x in pv])
                      for pk, pv in (getattr(one, "params", {}) or {}).items() if pk.upper() not in ("VALUE",)}
            props.append([k.lower(), params, t] + _jvalues(one, t))
    return [comp.name.lower(), props, [to_jcal(c) for c in comp.subcomponents]]


def _ical_value(t: str, v) -> str:
    if t == "recur" and isinstance(v, dict):
        return ";".join(f"{k.upper()}={','.join(_ical_value('date-time' if k == 'until' else 'text', x) for x in (vv if isinstance(vv, list) else [vv]))}"
                        for k, vv in v.items())
    if t in ("date", "date-time") and isinstance(v, str):
        return v.replace("-", "").replace(":", "")
    if t == "boolean":
        return "TRUE" if v else "FALSE"
    if t == "text":
        return str(v).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    if isinstance(v, list):
        return ";".join(str(x) for x in v)
    return str(v)


def _param(v) -> str:
    v = re.sub(r'["\x00-\x1f\x7f]', "", str(v))  # RFC 5545: no quotes or control characters in a parameter value
    return f'"{v}"' if re.search(r'[;:,]', v) else v


def from_jcal(obj) -> Calendar:
    """jCal (a JSON array, or its text) as an iCalendar object."""
    if isinstance(obj, (str, bytes)):
        obj = json.loads(obj)
    if not (isinstance(obj, list) and len(obj) == 3 and isinstance(obj[0], str)):
        raise ValueError("Not jCal: expected [\"vcalendar\", [properties], [components]]")
    lines: list[str] = []

    def comp(c):
        name, props, subs = c
        lines.append(f"BEGIN:{name.upper()}")
        for p in props:
            pname, params, t, *vals = p
            ps = "".join(f";{k.upper()}={','.join(_param(x) for x in v) if isinstance(v, list) else _param(v)}" for k, v in (params or {}).items())
            if t in ("date",) and pname.lower() not in ("dtstamp",):
                ps += ";VALUE=DATE"
            elif t == "period":
                ps += ";VALUE=PERIOD"
            sep = ";" if pname.lower() == "geo" else ","
            joined = sep.join(_ical_value(t, v) for v in vals) if pname.lower() != "geo" else ";".join(str(x) for x in vals[0])
            lines.append(f"{pname.upper()}{ps}:{joined}")
        for s in subs:
            comp(s)
        lines.append(f"END:{name.upper()}")
    try:
        comp(obj)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Not valid jCal: {e}") from e
    return parse("\r\n".join(lines) + "\r\n")


# ------------------------------------------------------------------ feeds

def feed(objects: list[str], name: str, description: str = "", color: str | None = None, tzname: str | None = None,
         refresh_hours: int = 1) -> str:
    """Many calendar objects as one VCALENDAR (a subscription or an export), each VTIMEZONE once."""
    out = new_calendar()
    out.add("CALSCALE", "GREGORIAN")
    out.add("METHOD", "PUBLISH")
    out.add("X-WR-CALNAME", name)
    if description:
        out.add("X-WR-CALDESC", description)
    if tzname:
        out.add("X-WR-TIMEZONE", tzname)
    if color:
        out.add("X-APPLE-CALENDAR-COLOR", color)
    out.add("REFRESH-INTERVAL", dt.timedelta(hours=refresh_hours), parameters={"VALUE": "DURATION"})
    out.add("X-PUBLISHED-TTL", dt.timedelta(hours=refresh_hours))
    tzs: dict = {}
    events = []
    for o in objects:
        try:
            c = parse(o)
        except ValueError:
            continue
        for sub in c.subcomponents:
            if sub.name == "VTIMEZONE":
                tzs.setdefault(str(sub.get("TZID")), sub)
            elif sub.name in ("VEVENT", "VTODO", "VJOURNAL"):
                events.append(sub)
    for t in tzs.values():
        out.add_component(t)
    for e in events:
        out.add_component(e)
    return out.to_ical().decode("utf-8")
