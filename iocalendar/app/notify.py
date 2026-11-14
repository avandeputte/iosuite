"""Notifications from ioCalendar (iosuite_shared.push): the reminders set on events, when they go off, for the
people who turned notifications on.

An event is for the family members it is tagged with; untagged, for the owner of its private calendar, else (a shared
calendar) for whoever added it. A reminder of an all-day event counts from the start of its day. The app runs this
every minute for the reminders of the next day, and every quarter of an hour for the ones further ahead (up to four
weeks, what the web app offers); each goes out once. It does nothing while nobody has a device.
"""
import datetime as dt

from iosuite_shared import push

from app import db, ical, members, model

APP = "iocalendar"
SHORT = (dt.timedelta(days=1), dt.timedelta(minutes=15))   # (how far ahead, how late a reminder may still go out)
LONG = (dt.timedelta(days=29), dt.timedelta(minutes=20))
_ticks = {"n": 0}


def tick() -> int:
    """The every-minute chore: the near reminders each time, the far ones every 15th time."""
    _ticks["n"] += 1
    return run(long=_ticks["n"] % 15 == 1)


def _start_utc(o: dict, tzname: str | None) -> dt.datetime:
    s = o["start"]
    if not isinstance(s, dt.datetime):
        return dt.datetime.combine(s, dt.time(), ical.zone(tzname)).astimezone(dt.timezone.utc)
    return ical.to_utc(s, tzname)


def _when(start: dt.datetime, all_day: bool, now: dt.datetime) -> str:
    """'In 15 minutes', 'Today at 14:00', 'Tomorrow', 'Fri 21 Nov at 09:30'..., in the server's time zone."""
    local, today = start.astimezone(ical.zone(None)), now.astimezone(ical.zone(None)).date()
    mins = round((start - now).total_seconds() / 60)
    if not all_day and 0 < mins < 60:
        return f"In {mins} minute{'s' if mins != 1 else ''}"
    if not all_day and -1 <= mins <= 0:
        return "Now"
    day = "Today" if local.date() == today else "Tomorrow" if local.date() == today + dt.timedelta(days=1) else f"{local:%a %d %b}"
    return day if all_day else f"{day} at {local:%H:%M}"


def run(now: dt.datetime = None, long: bool = False) -> int:
    """Send the reminders that went off; how many notifications went out."""
    people = {u["id"] for u in push.recipients("events")}
    if not people:
        return 0
    now = now or dt.datetime.now(dt.timezone.utc)
    ahead, late = LONG if long else SHORT
    cals = {c["id"]: c for c in db.q("SELECT * FROM cal_calendars WHERE kind NOT IN ('birthdays', 'holidays')")}
    rows = [r for r in model.rows_in_range(list(cals), now - late - dt.timedelta(days=7), now + ahead) if "VALARM" in (r["ics"] or "")]
    fam = members.family()
    sent = 0
    for r in rows:
        c = cals[r["calendar_id"]]
        try:
            occ = ical.occurrences(model.parsed(r), now - late - dt.timedelta(days=7), now + ahead + dt.timedelta(days=1), c.get("timezone"))
        except Exception:  # noqa: BLE001 - one broken object does not stop the others
            continue
        for o in occ:
            if o["status"] == "CANCELLED" or not o["reminders"]:
                continue
            start = _start_utc(o, c.get("timezone"))
            for m in o["reminders"]:
                at = start - dt.timedelta(minutes=m)
                if not (now - late < at <= now):
                    continue
                whom = set(members.ids_of(o["categories"], fam)) or ({c["owner_id"]} if c["owner_id"] is not None else
                                                                     {r["created_by"]} if r.get("created_by") else set())
                body = " · ".join(x for x in (_when(start, o["allDay"], now), o["location"], c["name"]) if x)
                day = start.astimezone(ical.zone(c.get("timezone"))).date().isoformat()
                for uid in whom & people:
                    sent += push.notify(uid, "events", o["title"] or "An event", body, url=push.link(APP, f"#/day/{day}"),
                                        once=f"event:{r['uid']}:{start:%Y%m%dT%H%M}:{m}", tag=f"event-{r['id']}")
    return sent
