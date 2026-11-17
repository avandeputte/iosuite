"""Demo data for iocalendar (the iosuite_demo package): the Calloways' calendars. The shared Family calendar with the week's routine
(school, piano, soccer, swimming), outings and appointments from a month ago to two months ahead, a Work calendar for
each parent, the children's own, and the public holidays of the United States (Oregon). Birthdays come from ioContact."""
import datetime as dt

import iosuite_demo as demo

from app import holiday, ical, model


def _add(cid: int, who: dict, data: dict, tz: str) -> dict:
    return model.save(cid, ical.build(data, tz), None, None, who["id"], tz)


def _at(n: int, hm: str) -> str:
    return f"{demo.day(n).isoformat()}T{hm}"


def _weekday(n: int, wd: int) -> int:
    """The offset of the first day on or after today+n that is weekday wd (0 Monday)."""
    d = demo.day(n)
    return n + (wd - d.weekday()) % 7


def seed(people: dict) -> None:
    m, r, a, t = (people[k] for k in ("morgan", "riley", "ava", "theo"))
    tz = demo.HOME["tz"]
    fam = model.db.one("SELECT id FROM cal_calendars WHERE owner_id IS NULL AND kind = 'events' AND slug = 'family'")
    fam = fam["id"] if fam else model.create_calendar(None, "Family", "Shared with everyone in the family", "#8e44d6", slug="family")
    model.update_calendar(fam, timezone=tz)
    school = model.create_calendar(None, "School", "Term dates, conferences and school events", "#0b8a9e", timezone=tz)
    work_m = model.create_calendar(m["id"], "Work", "Greenline Studio", "#1a73e8", timezone=tz)
    work_r = model.create_calendar(r["id"], "Work", "Juniper Hill High School", "#1e8e3e", timezone=tz)
    own = {p["key"]: model.create_calendar(p["id"], "Personal", f"{p['displayName']}'s own", p["color"], timezone=tz) for p in (a, t)}
    start = -35  # the routine starts five weeks ago

    def weekly(cid, who, title, wd, hm, minutes, members, location="", until=None, notes=""):
        n = _weekday(start, wd)
        s = dt.datetime.fromisoformat(_at(n, hm))
        data = {"title": title, "start": s.isoformat(timespec="minutes"),
                "end": (s + dt.timedelta(minutes=minutes)).isoformat(timespec="minutes"), "timezone": tz,
                "rrule": "FREQ=WEEKLY" + (f";UNTIL={until}" if until else ""), "members": members, "location": location,
                "notes": notes}
        _add(cid, who, model_fold(data), tz)

    weekly(fam, m, "Piano lesson", 1, "16:30", 45, ["Ava Calloway"], "Harmony Music School, 18 Elm Street")
    weekly(fam, r, "Soccer practice", 2, "17:00", 75, ["Theo Calloway"], "Riverside Park field 3", notes="Bring water and shin guards")
    weekly(fam, r, "Soccer game", 5, "10:00", 90, ["Theo Calloway", "Riley Calloway"], "Riverside Park")
    weekly(fam, m, "Swimming", 3, "18:00", 60, ["Ava Calloway", "Theo Calloway"], "Riverbend Aquatic Center")
    weekly(fam, m, "Family movie night", 4, "19:30", 120, ["Morgan Calloway", "Riley Calloway", "Ava Calloway", "Theo Calloway"])
    weekly(fam, r, "Recycling out", 6, "20:00", 15, ["Riley Calloway"])
    weekly(work_m, m, "Studio team meeting", 0, "09:30", 60, [], "Greenline Studio")
    weekly(work_r, r, "Department meeting", 3, "15:30", 60, [], "Room B12")
    weekly(own["ava"], a, "Robotics club", 4, "15:30", 90, ["Ava Calloway"], "Juniper Hill Middle School lab")
    weekly(own["theo"], t, "Scouts", 1, "18:30", 60, ["Theo Calloway"], "Community hall")

    one_off = [
        (fam, m, "Dentist: Theo", _at(_weekday(4, 3), "15:00"), 45, ["Theo Calloway"], "Bright Smiles Dental"),
        (fam, r, "Dinner with the Ramans", _at(_weekday(1, 5), "18:30"), 150, ["Morgan Calloway", "Riley Calloway"], "Priya and Lucas's"),
        (fam, m, "Vet: Biscuit's shots", _at(9, "11:00"), 30, ["Morgan Calloway"], "Willow Creek Animal Clinic"),
        (fam, r, "Car service", _at(_weekday(10, 1), "08:00"), 120, ["Riley Calloway"], "Juniper Auto"),
        (fam, m, "Farmers market", _at(_weekday(-14, 5), "09:00"), 120, [], "Main Street"),
        (fam, m, "Hike at Silver Creek", _at(_weekday(-7, 6), "09:30"), 300, ["Morgan Calloway", "Riley Calloway", "Ava Calloway", "Theo Calloway"], "Silver Creek trailhead"),
        (fam, r, "Grandma Eleanor visits", _at(-21, "12:00"), 240, [], ""),
        (school, r, "Parent-teacher conference: Ava", _at(_weekday(6, 3), "17:15"), 20, ["Ava Calloway", "Riley Calloway"], "Room 14"),
        (school, m, "Science fair", _at(_weekday(10, 4), "18:00"), 120, ["Ava Calloway"], "Juniper Hill Middle School gym"),
        (school, m, "School photo day", _at(_weekday(-10, 2), "09:00"), 60, ["Ava Calloway", "Theo Calloway"], ""),
        (work_m, m, "Juniper Park client review", _at(_weekday(2, 2), "14:00"), 90, [], "City hall, room 3"),
        (work_m, m, "Site visit: Hillside Gardens", _at(_weekday(8, 4), "10:00"), 180, [], ""),
        (work_r, r, "Chemistry exam", _at(_weekday(5, 1), "10:15"), 90, [], "Room B12"),
    ]
    for cid, who, title, when, minutes, members, location in one_off:
        s = dt.datetime.fromisoformat(when)
        _add(cid, who, model_fold({"title": title, "start": s.isoformat(timespec="minutes"),
                                   "end": (s + dt.timedelta(minutes=minutes)).isoformat(timespec="minutes"), "timezone": tz,
                                   "members": members, "location": location, "reminders": [60]}), tz)

    all_day = [
        (fam, m, "Coast weekend", 16, 3, ["Morgan Calloway", "Riley Calloway", "Ava Calloway", "Theo Calloway"], "Cannon Beach cabin"),
        (school, r, "No school: teacher training", _weekday(12, 4), 1, ["Ava Calloway", "Theo Calloway"], ""),
        (school, r, "Winter break", 35, 14, ["Ava Calloway", "Theo Calloway"], ""),
        (fam, m, "Daniel in town", -4, 2, [], ""),
    ]
    for cid, who, title, n, days, members, location in all_day:
        _add(cid, who, model_fold({"title": title, "start": demo.day(n).isoformat(), "end": demo.day(n + days).isoformat(),
                                   "allDay": True, "members": members, "location": location, "busy": False}), tz)

    holiday.set_country("US", "OR")
    try:
        holiday.sync()
    except Exception:  # noqa: BLE001 - the holidays library missing: the calendar fills at the next daily run
        pass


def model_fold(data: dict) -> dict:
    from app import members
    return members.fold(data)
