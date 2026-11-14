"""What the code review of 14 November 2026 settled: a floating time is the calendar's clock and a whole day is a date
(both shown on the right day whatever the zone), and links to other items of the suite follow an event to another
calendar and go with a deleted calendar."""
import datetime as dt
from zoneinfo import ZoneInfo

from iosuite_shared import related

from app import ical

FLOAT = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//EN\r\nBEGIN:VEVENT\r\nUID:{uid}\r\nDTSTAMP:20260101T000000Z\r\n"
         "{when}SUMMARY:x\r\n{extra}END:VEVENT\r\nEND:VCALENDAR\r\n")


def day(date: str, zone: str):
    """[start, end) of one day in a zone, in UTC, as the week and day views ask."""
    s = dt.datetime.fromisoformat(date).replace(tzinfo=ZoneInfo(zone))
    return s.astimezone(dt.timezone.utc), (s + dt.timedelta(days=1)).astimezone(dt.timezone.utc)


def seen(when: str, date: str, zone: str, extra: str = "") -> bool:
    cal = ical.parse(FLOAT.format(uid="x", when=when, extra=extra))
    return bool(ical.occurrences(cal, *day(date, zone), zone))


def test_a_floating_time_is_the_calendars_clock():
    # 23:30 on the 10th, no zone: on the 10th in Auckland (10:30 UTC) and in Los Angeles (07:30 UTC on the 11th)
    for zone in ("Pacific/Auckland", "America/Los_Angeles", "Europe/Brussels"):
        when = "DTSTART:20261110T233000\r\nDTEND:20261110T234500\r\n"
        assert seen(when, "2026-11-10", zone), zone
        assert not seen(when, "2026-11-11", zone) and not seen(when, "2026-11-09", zone), zone
    # early in the morning too
    when = "DTSTART:20261110T003000\r\nDTEND:20261110T010000\r\n"
    for zone in ("Pacific/Auckland", "America/Los_Angeles"):
        assert seen(when, "2026-11-10", zone) and not seen(when, "2026-11-09", zone), zone
    # a repeating one, every day at 23:30: one a day
    cal = ical.parse(FLOAT.format(uid="r", when="DTSTART:20261101T233000\r\nDTEND:20261101T234500\r\n", extra="RRULE:FREQ=DAILY\r\n"))
    assert len(ical.occurrences(cal, *day("2026-11-10", "Pacific/Auckland"), "Pacific/Auckland")) == 1


def test_a_whole_day_is_a_date_in_any_zone():
    when = "DTSTART;VALUE=DATE:20261111\r\nDTEND;VALUE=DATE:20261112\r\n"
    for zone in ("Europe/Brussels", "America/New_York", "Pacific/Auckland", "Pacific/Honolulu", "UTC"):
        assert seen(when, "2026-11-11", zone), zone
        assert not seen(when, "2026-11-10", zone), zone
        assert not seen(when, "2026-11-12", zone), zone
    # two days, written with the end date (the day after): both days, not the third
    when = "DTSTART;VALUE=DATE:20261111\r\nDTEND;VALUE=DATE:20261113\r\n"
    assert seen(when, "2026-11-12", "America/New_York") and not seen(when, "2026-11-13", "America/New_York")
    # a birthday each year
    cal = ical.parse(FLOAT.format(uid="b", when="DTSTART;VALUE=DATE:20001111\r\n", extra="RRULE:FREQ=YEARLY\r\n"))
    s, e = day("2026-11-10", "Asia/Tokyo")
    assert ical.occurrences(cal, s, e + dt.timedelta(days=1), "Asia/Tokyo")[0]["start"] == dt.date(2026, 11, 11)
    assert ical.occurrences(cal, s, e, "Asia/Tokyo") == []


def test_the_api_shows_whole_days_on_their_date(client, family_id):
    client.post(f"/api/events?calendar={family_id}", json={"title": "Holiday", "start": "2026-11-11", "allDay": True})
    client.post(f"/api/events?calendar={family_id}", json={"title": "Before", "start": "2026-11-10", "allDay": True})
    got = client.get("/api/occurrences?start=2026-11-11T00:00:00-05:00&end=2026-11-12T00:00:00-05:00").json()["items"]
    assert [o["title"] for o in got] == ["Holiday"]


def test_links_follow_an_event_to_another_calendar_and_go_with_a_calendar(client, family_id):
    mine = client.post("/api/calendars", json={"name": "Work"}).json()["calendar"]["id"]
    e = client.post(f"/api/events?calendar={family_id}", json={"title": "Dentist", "start": "2026-11-10T10:00"}).json()
    related.add(("event", e["id"]), ("note", "8F6C1E2A-0000-4000-8000-000000000001"))
    moved = client.patch(f"/api/events/{e['id']}", json={"calendarId": mine}).json()
    assert moved["id"] != e["id"]
    assert [(x["kind"], x["id"]) for x in related.of("event", moved["id"])] == [("note", "8F6C1E2A-0000-4000-8000-000000000001")]
    assert related.of("event", e["id"]) == []
    assert client.delete(f"/api/calendars/{mine}").status_code == 200
    assert related.of("event", moved["id"]) == []
