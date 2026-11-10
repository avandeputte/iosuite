"""The WebDAV plumbing ioCalendar and ioContacts share (iosuite_shared.dav)."""
import datetime as dt
import xml.etree.ElementTree as ET

from iosuite_shared import dav

C = "urn:ietf:params:xml:ns:caldav"


def test_a_propfind_body_is_read_without_trusting_it():
    assert dav.requested(b"") == ("allprop", []) and dav.requested(b"  ") == ("allprop", []) and dav.requested(b"<not xml") == ("allprop", [])
    assert dav.requested(b'<d:propfind xmlns:d="DAV:"><d:propname/></d:propfind>') == ("propname", [])
    assert dav.requested(b'<d:propfind xmlns:d="DAV:"><d:prop><d:getetag/><d:displayname/></d:prop></d:propfind>') == ("prop", ["{DAV:}getetag", "{DAV:}displayname"])
    bomb = b'<!DOCTYPE x [<!ENTITY a "aaaa">]><d:propfind xmlns:d="DAV:"><d:prop><d:getetag>&a;</d:getetag></d:prop></d:propfind>'
    assert dav.requested(bomb) == ("allprop", [])  # entities are refused, not expanded


def test_a_multistatus_response_separates_found_and_missing():
    ms = ET.Element(dav.q(dav.D, "multistatus"))
    ok = ET.Element(dav.q(dav.D, "prop"))
    dav.sub(ok, dav.D, "getetag", '"abc"')
    dav.response(ms, "/dav/x/1.ics", ok, [dav.q(C, "calendar-data")])
    r = dav.xml(ms)
    text = r.body.decode()
    assert r.status_code == 207 and r.media_type.startswith("application/xml")
    assert text.count("propstat>") == 4 and "200 OK" in text and "404 Not Found" in text and "/dav/x/1.ics" in text
    names = ET.Element(dav.q(dav.D, "prop"))
    dav.sub(names, dav.D, "getetag", '"abc"')
    dav.response(ET.Element("x"), "/dav/x/", names, [], names_only=True)
    assert names[0].text is None


def test_privileges_preconditions_and_headers():
    el = ET.Element("x")
    dav.privileges(el, False, also=[(C, "read-free-busy")])
    assert [p[0].tag for p in el[0]] == [dav.q(dav.D, "read"), dav.q(dav.D, "read-acl"), dav.q(dav.D, "read-current-user-privilege-set"), dav.q(C, "read-free-busy")]
    el = ET.Element("x")
    dav.privileges(el, True)
    assert dav.q(dav.D, "write-content") in [p[0].tag for p in el[0]] and len(el[0]) == 9
    r = dav.precondition(C, "no-uid-conflict", 409, "/dav/x/2.ics")
    assert r.status_code == 409 and b"no-uid-conflict" in r.body and b"/dav/x/2.ics" in r.body
    assert dav.precondition(dav.D, "valid-sync-token").status_code == 403
    assert dav.etag_match(None, "a") and dav.etag_match('"a", "b"', "b") and dav.etag_match("*", None) and dav.etag_match('W/"a"', "a")
    assert not dav.etag_match('"a"', "b") and not dav.etag_match('"a"', None)
    assert dav.parts_of("/dav/calendars/alex/My%20cal/") == ["calendars", "alex", "My cal"] and dav.parts_of("/") == []
    assert dav.http_date(dt.datetime(2026, 11, 10, 4, 30)) == "Tue, 10 Nov 2026 04:30:00 GMT" and dav.http_date(None) == ""
    u = dav.unauthorized("ioCalendar", "an app password")
    assert u.status_code == 401 and u.headers["www-authenticate"] == 'Basic realm="ioCalendar", charset="UTF-8"'
    assert dav.options("1, 2, 3, calendar-access", ["OPTIONS", "GET"]) == {"DAV": "1, 2, 3, calendar-access", "Allow": "OPTIONS, GET", "MS-Author-Via": "DAV"}
    assert dav.sync_token("urn:x:sync:", {"id": 4, "sync_token": 17}) == "urn:x:sync:4-17"
