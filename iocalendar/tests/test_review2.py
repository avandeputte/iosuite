"""What the code review of 10 November 2026 found: a series that repeats every second is refused and never expanded,
a move to another calendar is one transaction, the subscription token stays out of the request log, and the replies
that only name events do not read the events themselves."""
import logging
import time

import pytest

from app import db, ical, model
from app.main import FeedTokenFilter
from tests.test_api import mk, occ
from tests.test_review_fixes import ICS

BASE = "/dav/calendars/alex/family/"


@pytest.fixture()
def dav(client):
    """CalDAV requests with an app password, beside the signed-in web session of `client`."""
    pw = client.post("/api/auth/app-passwords", json={"label": "iPhone"}).json()["password"]
    return lambda method, path, body=None, **h: client.request(method, path, content=body, auth=("alex", pw), headers=h)


def test_a_series_for_every_second_is_refused(client, family_id, dav):
    for rule in ("FREQ=SECONDLY", "FREQ=MINUTELY", "FREQ=SECONDLY;UNTIL=20270101T000000Z", "FREQ=MINUTELY;INTERVAL=10;COUNT=5000",
                 "FREQ=DAILY;BYHOUR=8,9,10,11,12,13,14,15,16,17;BYMINUTE=0,10,20,30,40,50"):
        r = client.post(f"/api/events?calendar={family_id}", json={"title": "Tick", "start": "2026-11-02T09:00", "rrule": rule})
        assert r.status_code == 400 and "half hour" in r.text, (rule, r.text)
        ics = ICS.format(uid="tick", start="20261102T090000", end="20261102T091500", title="Tick", extra=f"RRULE:{rule}\r\n")
        assert dav("PUT", BASE + "tick.ics", ics).status_code == 400, rule
    # every half hour, every hour, and a short burst are events like any other
    mk(client, family_id, title="Pills", start="2026-11-02T09:00", end="2026-11-02T09:05", timezone="UTC", rrule="FREQ=MINUTELY;INTERVAL=10;COUNT=6")
    mk(client, family_id, title="Feed", start="2026-11-03T00:00", end="2026-11-03T00:10", timezone="UTC", rrule="FREQ=MINUTELY;INTERVAL=30")
    assert [i["title"] for i in occ(client, "2026-11-02T00:00:00Z", "2026-11-03T00:00:00Z")] == ["Pills"] * 6
    assert [i["title"] for i in occ(client, "2026-11-03T00:00:00Z", "2026-11-04T00:00:00Z")] == ["Feed"] * 48


def test_a_stored_series_for_every_second_is_drawn_once(client, family_id, dav):
    e = mk(client, family_id, title="Tick", start="2026-11-02T09:00", end="2026-11-02T09:01", timezone="UTC", rrule="FREQ=DAILY")
    row = model.get_row(e["id"])
    db.ex("UPDATE cal_events SET ics = %s, etag = 'old', range_end = NULL WHERE id = %s", (row["ics"].replace("FREQ=DAILY", "FREQ=SECONDLY"), e["id"]))
    t = time.time()
    assert [i["title"] for i in occ(client, "2026-11-01", "2026-12-01")] == ["Tick"]
    assert occ(client, "2026-12-01", "2027-01-01") == []
    q = ('<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:getetag/><c:calendar-data>'
         '<c:expand start="20261101T000000Z" end="20270101T000000Z"/></c:calendar-data></d:prop><c:filter><c:comp-filter name="VCALENDAR">'
         '<c:comp-filter name="VEVENT"><c:time-range start="20261101T000000Z"/></c:comp-filter></c:comp-filter></c:filter></c:calendar-query>')
    r = dav("REPORT", BASE, q, Depth="1")
    assert r.status_code == 207 and "FREQ=SECONDLY" in r.text  # not expanded: the object as it is
    assert time.time() - t < 5


def test_the_size_of_a_series_is_read_from_its_rule():
    def master(rule):
        return ical.master_of(ical.events_of(ical.parse(ICS.format(uid="x", start="20261102T090000", end="20261102T100000", title="x", extra=f"RRULE:{rule}\r\n"))))
    assert ical._size(master("FREQ=DAILY;COUNT=10")) == 11 and ical._size(master("FREQ=DAILY")) is None
    assert ical._size(master("FREQ=WEEKLY;UNTIL=20271102T000000Z")) < 60
    assert not ical.too_frequent(master("FREQ=HOURLY")) and not ical.too_frequent(master("FREQ=SECONDLY;COUNT=600"))
    assert ical.too_frequent(master("FREQ=SECONDLY;COUNT=5000")) and ical.too_frequent(master("FREQ=HOURLY;BYMINUTE=0,15,30,45"))
    # a long series counts as endless without being expanded
    cal = ical.parse(ICS.format(uid="x", start="20261102T090000", end="20261102T100000", title="x", extra="RRULE:FREQ=HOURLY;COUNT=10000000\r\n"))
    t = time.time()
    assert ical.index(cal)["range_end"] is None and time.time() - t < 2


def test_an_open_time_range_looks_at_one_occurrence(client, family_id, dav):
    mk(client, family_id, title="Daily", start="2020-01-01T09:00", end="2020-01-01T10:00", timezone="UTC", rrule="FREQ=DAILY")
    mk(client, family_id, title="Past", start="2020-01-01T09:00", end="2020-01-01T10:00", timezone="UTC")
    q = ('<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:displayname/></d:prop><c:filter>'
         '<c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT"><c:time-range start="20261101T000000Z"/></c:comp-filter>'
         '</c:comp-filter></c:filter></c:calendar-query>')
    r = dav("REPORT", BASE, q, Depth="1")
    assert r.status_code == 207 and "Daily" in r.text and "Past" not in r.text


def test_a_move_that_fails_keeps_the_event(client, family_id, monkeypatch):
    other = client.post("/api/calendars", json={"name": "Soccer", "shared": True}).json()["calendar"]["id"]
    e = mk(client, family_id, title="Match", start="2026-11-07T10:00")
    tok = model.calendar(family_id)["sync_token"]

    def broken(*a, **kw):
        raise RuntimeError("the database went away")
    real = model.save
    monkeypatch.setattr(model, "save", broken)
    with pytest.raises(RuntimeError):
        model.move(e["id"], other)
    monkeypatch.setattr(model, "save", real)
    row = model.get_row(e["id"])
    assert row["deleted"] == 0 and row["calendar_id"] == family_id and "Match" in row["ics"]
    assert model.calendar(family_id)["sync_token"] == tok
    # and a move that works: gone from the old calendar, there in the new one
    moved = model.move(e["id"], other)
    assert moved["calendar_id"] == other and model.get_row(e["id"])["deleted"] == 1
    assert [i["calendarId"] for i in occ(client)] == [other]


def test_the_subscription_token_stays_out_of_the_request_log():
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                            ("10.0.0.5:1234", "GET", "/ics/0123456789abcdef/all.ics?member=Ann", "1.1", 200), None)
    assert FeedTokenFilter().filter(rec) is True
    line = rec.getMessage()
    assert "0123456789abcdef" not in line and "/ics/-/all.ics?member=Ann" in line
    plain = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d', ("10.0.0.5:1234", "GET", "/api/calendars", "1.1", 200), None)
    FeedTokenFilter().filter(plain)
    assert "/api/calendars" in plain.getMessage()


def test_listings_do_not_read_the_events(client, family_id, dav):
    e = mk(client, family_id, title="Piano", start="2026-11-10T10:00", notes="x" * 500)
    row = model.get_row(e["id"])
    listed = model.rows(family_id, listing=True)
    assert "ics" not in listed[0] and listed[0]["ics_bytes"] == len(row["ics"].encode()) and listed[0]["etag"] == row["etag"]
    r = dav("PROPFIND", BASE, '<d:propfind xmlns:d="DAV:"><d:prop><d:getetag/><d:getcontentlength/></d:prop></d:propfind>', Depth="1")
    assert r.status_code == 207 and row["etag"] in r.text and f">{len(row['ics'].encode())}<" in r.text
    sc = ('<d:sync-collection xmlns:d="DAV:"><d:sync-token/><d:sync-level>1</d:sync-level><d:prop><d:getetag/></d:prop></d:sync-collection>')
    assert row["etag"] in dav("REPORT", BASE, sc).text
    full = sc.replace("<d:getetag/>", '<d:getetag/><c:calendar-data xmlns:c="urn:ietf:params:xml:ns:caldav"/>')
    assert "SUMMARY:Piano" in dav("REPORT", BASE, full).text
    # the subscription and the export are built from the parsed objects
    text = model.export_text([model.calendar(family_id)], "Family")
    assert text.count("BEGIN:VEVENT") == 1 and "SUMMARY:Piano" in text
    assert "SUMMARY:Piano" in client.get("/api/events", params={"format": "ics"}).text
