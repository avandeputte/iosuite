"""CalDAV for to-dos, as Apple Reminders uses it: discovery, VTODO-only lists, PUT with preconditions and UID
conflicts, multiget, calendar-query for the open tasks, sync-collection with deletions, MKCALENDAR, PROPPATCH."""
import re


TODO = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Apple Inc.//iOS 18//EN\r\nBEGIN:VTODO\r\nUID:{uid}\r\nDTSTAMP:20260101T000000Z\r\n"
        "SUMMARY:{title}\r\n{extra}X-APPLE-SORT-ORDER:790000000\r\nEND:VTODO\r\nEND:VCALENDAR\r\n")


def test_discovery_shows_lists_of_todos(client, dav):
    assert client.request("PROPFIND", "/.well-known/caldav", follow_redirects=False).status_code == 301
    assert client.request("OPTIONS", "/dav/").headers["DAV"].startswith("1, 2, 3, calendar-access")
    assert client.request("PROPFIND", "/dav/").status_code == 401
    body = '<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/></d:prop></d:propfind>'
    assert "/dav/principals/alex/" in dav("PROPFIND", "/dav/", body, Depth="0").text
    body = ('<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav" xmlns:cs="http://calendarserver.org/ns/" '
            'xmlns:a="http://apple.com/ns/ical/"><d:prop><d:displayname/><d:resourcetype/><cs:getctag/><d:sync-token/>'
            '<c:supported-calendar-component-set/><a:calendar-color/><d:current-user-privilege-set/></d:prop></d:propfind>')
    r = dav("PROPFIND", "/dav/calendars/alex/", body, Depth="1")
    assert r.status_code == 207
    assert "/dav/calendars/alex/family/" in r.text and "/dav/calendars/alex/personal/" in r.text
    assert 'name="VTODO"' in r.text and 'name="VEVENT"' not in r.text
    assert dav("PROPFIND", "/dav/calendars/bob/", body).status_code == 403


def test_put_get_query_sync_delete(client, dav):
    base = "/dav/calendars/alex/family/"
    r = dav("PROPFIND", base, '<d:propfind xmlns:d="DAV:"><d:prop><d:sync-token/></d:prop></d:propfind>', Depth="0")
    tok0 = re.search(r"<d:sync-token>([^<]+)<", r.text).group(1)
    ics = TODO.format(uid="T1", title="Milk", extra="DUE;VALUE=DATE:20261112\r\nPRIORITY:5\r\n")
    r = dav("PUT", base + "T1.ics", ics, **{"If-None-Match": "*", "Content-Type": "text/calendar"})
    assert r.status_code == 201
    etag = r.headers["ETag"]
    assert dav("PUT", base + "T1.ics", ics, **{"If-None-Match": "*"}).status_code == 412
    assert dav("PUT", base + "other.ics", ics).status_code == 409  # the same UID under another name
    got = dav("GET", base + "T1.ics")
    assert got.headers["ETag"] == etag and "X-APPLE-SORT-ORDER:790000000" in got.text  # kept as the app sent it
    # the web app sees it
    # the open tasks, as Reminders asks (COMPLETED is-not-defined), and a time range on the due date
    q = ('<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:getetag/><c:calendar-data/></d:prop>'
         '<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VTODO">{inner}</c:comp-filter></c:comp-filter></c:filter></c:calendar-query>')
    open_q = q.format(inner='<c:prop-filter name="COMPLETED"><c:is-not-defined/></c:prop-filter>')
    assert "T1.ics" in dav("REPORT", base, open_q, Depth="1").text
    assert "T1.ics" in dav("REPORT", base, q.format(inner='<c:time-range start="20261112T000000Z" end="20261113T000000Z"/>'), Depth="1").text
    assert "T1.ics" not in dav("REPORT", base, q.format(inner='<c:time-range start="20261201T000000Z" end="20261202T000000Z"/>'), Depth="1").text
    ev_q = q.replace('name="VTODO"', 'name="VEVENT"').format(inner="")
    assert "T1.ics" not in dav("REPORT", base, ev_q, Depth="1").text
    # ticked off on the phone: no longer open
    done = ics.replace("PRIORITY:5\r\n", "PRIORITY:5\r\nSTATUS:COMPLETED\r\nCOMPLETED:20261111T080000Z\r\n")
    assert dav("PUT", base + "T1.ics", done, **{"If-Match": '"stale"'}).status_code == 412
    assert dav("PUT", base + "T1.ics", done, **{"If-Match": etag}).status_code == 204
    assert "T1.ics" not in dav("REPORT", base, open_q, Depth="1").text
    # multiget
    mg = ('<c:calendar-multiget xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:getetag/><c:calendar-data/></d:prop>'
          f'<d:href>{base}T1.ics</d:href><d:href>{base}missing.ics</d:href></c:calendar-multiget>')
    r = dav("REPORT", base, mg, Depth="1")
    assert "SUMMARY:Milk" in r.text and "404 Not Found" in r.text
    # sync-collection reports the change and later the deletion
    sc = ('<d:sync-collection xmlns:d="DAV:"><d:sync-token>{t}</d:sync-token><d:sync-level>1</d:sync-level>'
          '<d:prop><d:getetag/></d:prop></d:sync-collection>')
    r = dav("REPORT", base, sc.format(t=tok0))
    assert "T1.ics" in r.text
    tok1 = re.search(r"<d:sync-token>([^<]+)<", r.text).group(1)
    assert tok1.startswith("urn:x-iotasks:sync:")
    assert dav("DELETE", base + "T1.ics").status_code == 204
    r = dav("REPORT", base, sc.format(t=tok1))
    assert "T1.ics" in r.text and "404 Not Found" in r.text
    assert dav("REPORT", base, sc.format(t="http://bogus/1")).status_code == 403
    # an event is refused: events belong in ioCalendar
    ev = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:x\r\nBEGIN:VEVENT\r\nUID:e1\r\nDTSTART:20261110T100000Z\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    assert dav("PUT", base + "e1.ics", ev).status_code == 403


def test_a_task_from_the_phone_shows_in_the_web_app(client):
    pw = client.post("/api/auth/app-passwords", json={"label": "iPhone"}).json()["password"]
    ics = TODO.format(uid="P1", title="Call the plumber", extra="DUE;TZID=Europe/Brussels:20261112T090000\r\nDTSTART;TZID=Europe/Brussels:20261112T090000\r\n"
                      "RELATED-TO;RELTYPE=PARENT:P0\r\n")
    assert client.request("PUT", "/dav/calendars/alex/personal/P1.ics", content=ics, auth=("alex", pw)).status_code == 201
    t = client.get("/api/tasks").json()["items"][0]
    assert t["title"] == "Call the plumber" and t["due"] == "2026-11-12T09:00:00+01:00" and t["parent"] == "P0"
    # changed in the web app: the start goes with the due time, the phone's own properties stay
    t2 = client.patch(f"/api/tasks/{t['id']}", json={"due": "2026-11-13T10:00"}).json()
    got = client.request("GET", "/dav/calendars/alex/personal/P1.ics", auth=("alex", pw)).text
    assert "X-APPLE-SORT-ORDER:790000000" in got and t2["start"] == t2["due"]


def test_mkcalendar_and_proppatch(client, dav):
    body = ('<c:mkcalendar xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav" xmlns:a="http://apple.com/ns/ical/"><d:set><d:prop>'
            '<d:displayname>Groceries</d:displayname><a:calendar-color>#1A73E8FF</a:calendar-color>'
            '<c:supported-calendar-component-set><c:comp name="VTODO"/></c:supported-calendar-component-set></d:prop></d:set></c:mkcalendar>')
    assert dav("MKCALENDAR", "/dav/calendars/alex/A1B2/", body).status_code == 201
    pp = '<d:propertyupdate xmlns:d="DAV:"><d:set><d:prop><d:displayname>Shopping</d:displayname></d:prop></d:set></d:propertyupdate>'
    assert dav("PROPPATCH", "/dav/calendars/alex/A1B2/", pp).status_code == 207
    r = dav("PROPFIND", "/dav/calendars/alex/A1B2/", '<d:propfind xmlns:d="DAV:"><d:prop><d:displayname/></d:prop></d:propfind>', Depth="0")
    assert "Shopping" in r.text
    events = body.replace('name="VTODO"', 'name="VEVENT"')
    assert dav("MKCALENDAR", "/dav/calendars/alex/cal/", events).status_code == 403
    # the placeholder calendar iOS makes for an account without one: not made
    plain = '<c:mkcalendar xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:set><d:prop><d:displayname>DEFAULT_CALENDAR_NAME</d:displayname></d:prop></d:set></c:mkcalendar>'
    assert dav("MKCALENDAR", "/dav/calendars/alex/x1/", plain).status_code == 403
    assert dav("DELETE", "/dav/calendars/alex/A1B2/").status_code == 204


def test_caldav_refuses_xml_entities(client, dav):
    base = "/dav/calendars/alex/family/"
    bomb = ('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
            '<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav"><D:prop><D:getetag>&b;</D:getetag></D:prop></C:calendar-query>')
    assert dav("REPORT", base, bomb, Depth="1").status_code == 400
