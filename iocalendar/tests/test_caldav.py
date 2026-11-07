"""CalDAV: discovery, PUT with preconditions and UID conflicts, multiget, calendar-query with a time range,
sync-collection with deletions, MKCALENDAR, PROPPATCH, free-busy-query."""
import re

import pytest

ICS = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Apple Inc.//iOS 18//EN\r\nBEGIN:VEVENT\r\nUID:{uid}\r\nDTSTAMP:20260101T000000Z\r\n"
       "DTSTART;TZID=Europe/Brussels:{start}\r\nDTEND;TZID=Europe/Brussels:{end}\r\nSUMMARY:{title}\r\n{extra}"
       "BEGIN:VALARM\r\nACTION:DISPLAY\r\nTRIGGER:-PT10M\r\nX-WR-ALARMUID:A1\r\nEND:VALARM\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")


@pytest.fixture()
def dav(client):
    pw = client.post("/api/auth/app-passwords", json={"label": "iPhone"}).json()["password"]
    client.cookies.clear()
    return lambda method, path, body=None, **h: client.request(method, path, content=body, auth=("alex", pw), headers=h)


def test_discovery(client, dav):
    assert client.request("PROPFIND", "/.well-known/caldav", follow_redirects=False).status_code == 301
    assert client.request("OPTIONS", "/dav/").headers["DAV"].startswith("1, 2, 3, calendar-access")
    assert client.request("PROPFIND", "/dav/").status_code == 401
    body = '<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/></d:prop></d:propfind>'
    r = dav("PROPFIND", "/dav/", body, Depth="0")
    assert r.status_code == 207 and "/dav/principals/alex/" in r.text
    body = '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><c:calendar-home-set/></d:prop></d:propfind>'
    assert "/dav/calendars/alex/" in dav("PROPFIND", "/dav/principals/alex/", body, Depth="0").text
    body = ('<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav" xmlns:cs="http://calendarserver.org/ns/" '
            'xmlns:a="http://apple.com/ns/ical/"><d:prop><d:displayname/><d:resourcetype/><cs:getctag/><d:sync-token/>'
            '<c:supported-calendar-component-set/><a:calendar-color/><d:current-user-privilege-set/><c:calendar-timezone/></d:prop></d:propfind>')
    r = dav("PROPFIND", "/dav/calendars/alex/", body, Depth="1")
    assert r.status_code == 207
    assert "/dav/calendars/alex/family/" in r.text and "/dav/calendars/alex/personal/" in r.text
    assert "<cal:calendar" in r.text and 'name="VEVENT"' in r.text and "BEGIN:VTIMEZONE" in r.text
    assert dav("PROPFIND", "/dav/calendars/bob/", body).status_code == 403


def test_put_get_query_sync_delete(client, dav):
    base = "/dav/calendars/alex/family/"
    r = dav("PROPFIND", base, '<d:propfind xmlns:d="DAV:"><d:prop><d:sync-token/></d:prop></d:propfind>', Depth="0")
    tok0 = re.search(r"<d:sync-token>([^<]+)<", r.text).group(1)
    ics = ICS.format(uid="ev1", start="20261110T100000", end="20261110T110000", title="Piano", extra="")
    r = dav("PUT", base + "ev1.ics", ics, **{"If-None-Match": "*", "Content-Type": "text/calendar"})
    assert r.status_code == 201
    etag = r.headers["ETag"]
    assert dav("PUT", base + "ev1.ics", ics, **{"If-None-Match": "*"}).status_code == 412
    assert dav("PUT", base + "other.ics", ics).status_code == 409  # the same UID under another name
    got = dav("GET", base + "ev1.ics")
    assert got.headers["ETag"] == etag and "X-WR-ALARMUID:A1" in got.text  # kept as the app sent it
    # calendar-query with a time range
    q = ('<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:getetag/><c:calendar-data/></d:prop>'
         '<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT"><c:time-range start="{s}" end="{e}"/>'
         '</c:comp-filter></c:comp-filter></c:filter></c:calendar-query>')
    assert "ev1.ics" in dav("REPORT", base, q.format(s="20261110T000000Z", e="20261111T000000Z"), Depth="1").text
    assert "ev1.ics" not in dav("REPORT", base, q.format(s="20261111T000000Z", e="20261112T000000Z"), Depth="1").text
    # multiget
    mg = ('<c:calendar-multiget xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:getetag/><c:calendar-data/></d:prop>'
          f'<d:href>{base}ev1.ics</d:href><d:href>{base}missing.ics</d:href></c:calendar-multiget>')
    r = dav("REPORT", base, mg, Depth="1")
    assert "SUMMARY:Piano" in r.text and "404 Not Found" in r.text
    # update with If-Match, then sync-collection reports the change and later the deletion
    ics2 = ics.replace("Piano", "Piano lesson")
    assert dav("PUT", base + "ev1.ics", ics2, **{"If-Match": '"stale"'}).status_code == 412
    assert dav("PUT", base + "ev1.ics", ics2, **{"If-Match": etag}).status_code == 204
    sc = ('<d:sync-collection xmlns:d="DAV:"><d:sync-token>{t}</d:sync-token><d:sync-level>1</d:sync-level>'
          '<d:prop><d:getetag/></d:prop></d:sync-collection>')
    r = dav("REPORT", base, sc.format(t=tok0))
    assert "ev1.ics" in r.text
    tok1 = re.search(r"<d:sync-token>([^<]+)<", r.text).group(1)
    assert dav("DELETE", base + "ev1.ics").status_code == 204
    r = dav("REPORT", base, sc.format(t=tok1))
    assert "ev1.ics" in r.text and "404 Not Found" in r.text
    assert dav("REPORT", base, sc.format(t="http://bogus/1")).status_code == 403
    assert tok1.startswith("urn:x-iocalendar:sync:")
    legacy = tok1.replace("urn:x-iocalendar:sync:", "http://iocalendar." + "iothing" + ".net/ns/sync/")
    assert dav("REPORT", base, sc.format(t=legacy)).status_code == 207  # tokens from before 0.18.1 keep working
    # a VTODO is refused (this server keeps events)
    todo = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:x\r\nBEGIN:VTODO\r\nUID:t1\r\nSUMMARY:x\r\nEND:VTODO\r\nEND:VCALENDAR\r\n"
    assert dav("PUT", base + "t1.ics", todo).status_code == 403


def test_mkcalendar_proppatch_and_free_busy(client, dav):
    body = ('<c:mkcalendar xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav" xmlns:a="http://apple.com/ns/ical/"><d:set><d:prop>'
            '<d:displayname>Work</d:displayname><a:calendar-color>#1A73E8FF</a:calendar-color></d:prop></d:set></c:mkcalendar>')
    assert dav("MKCALENDAR", "/dav/calendars/alex/work-1/", body).status_code == 201
    pp = ('<d:propertyupdate xmlns:d="DAV:"><d:set><d:prop><d:displayname>Work stuff</d:displayname></d:prop></d:set></d:propertyupdate>')
    assert dav("PROPPATCH", "/dav/calendars/alex/work-1/", pp).status_code == 207
    r = dav("PROPFIND", "/dav/calendars/alex/work-1/", '<d:propfind xmlns:d="DAV:"><d:prop><d:displayname/></d:prop></d:propfind>', Depth="0")
    assert "Work stuff" in r.text
    ics = ICS.format(uid="w1", start="20261110T100000", end="20261110T110000", title="Meeting", extra="RRULE:FREQ=WEEKLY;COUNT=3\r\n")
    assert dav("PUT", "/dav/calendars/alex/work-1/w1.ics", ics).status_code == 201
    fb = ('<c:free-busy-query xmlns:c="urn:ietf:params:xml:ns:caldav"><c:time-range start="20261101T000000Z" end="20261201T000000Z"/>'
          '</c:free-busy-query>')
    r = dav("REPORT", "/dav/calendars/alex/work-1/", fb, Depth="1")
    assert r.text.count("FREEBUSY;FBTYPE=BUSY") == 3
    # expand: the occurrences one by one, in UTC
    q = ('<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><c:calendar-data>'
         '<c:expand start="20261101T000000Z" end="20261201T000000Z"/></c:calendar-data></d:prop>'
         '<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT"/></c:comp-filter></c:filter></c:calendar-query>')
    r = dav("REPORT", "/dav/calendars/alex/work-1/", q, Depth="1")
    assert r.text.count("BEGIN:VEVENT") == 3 and "DTSTART:20261110T090000Z" in r.text
    assert dav("DELETE", "/dav/calendars/alex/work-1/").status_code == 204
