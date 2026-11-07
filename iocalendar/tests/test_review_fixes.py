"""What the code review of v0.2.3 found: splitting a series keeps what came after, links are links, search takes
% and _ as they are, CalDAV matches CATEGORIES text and bumps the sync token once per PROPPATCH, and the rest."""
import re
from urllib.parse import quote

import pytest

from app import db, ical, model
from tests.test_api import mk, occ

ICS = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//EN\r\nBEGIN:VEVENT\r\nUID:{uid}\r\nDTSTAMP:20260101T000000Z\r\n"
       "DTSTART;TZID=Europe/Brussels:{start}\r\nDTEND;TZID=Europe/Brussels:{end}\r\nSUMMARY:{title}\r\n{extra}END:VEVENT\r\nEND:VCALENDAR\r\n")


@pytest.fixture()
def dav(client):
    pw = client.post("/api/auth/app-passwords", json={"label": "iPhone"}).json()["password"]
    client.cookies.clear()
    return lambda method, path, body=None, **h: client.request(method, path, content=body, auth=("alex", pw), headers=h)


def test_following_keeps_later_changes(client, family_id):
    e = mk(client, family_id, title="Standup", start="2026-11-02T09:00", end="2026-11-02T09:15", timezone="America/New_York", rrule="FREQ=DAILY;COUNT=10")
    items = occ(client)
    rid8, rid9 = items[7]["recurrenceId"], items[8]["recurrenceId"]
    assert client.patch(f"/api/events/{e['id']}?scope=this&recurrenceId={rid8}", json={"title": "Late standup", "start": "2026-11-09T15:00", "end": "2026-11-09T15:15"}).status_code == 200
    assert client.delete(f"/api/events/{e['id']}?scope=this&recurrenceId={rid9}").status_code == 200
    # a split before them, with the same schedule: the moved one and the left-out one stay so, and get the new title too
    rid4 = items[3]["recurrenceId"]
    r = client.patch(f"/api/events/{e['id']}?scope=following&recurrenceId={rid4}", json={"title": "New standup"})
    assert r.status_code == 201, r.text
    items = occ(client)
    assert len(items) == 9 and [i["title"] for i in items].count("New standup") == 6
    late = [i for i in items if i["start"] == "2026-11-09T15:00:00-05:00"]
    assert late and late[0]["title"] == "New standup" and late[0]["id"] == r.json()["id"]
    assert rid9 not in [i["recurrenceId"] for i in items]


def test_override_alarms_are_its_own(client, family_id):
    e = mk(client, family_id, title="Gym", start="2026-11-02T18:00", end="2026-11-02T19:00", timezone="UTC", rrule="FREQ=WEEKLY;COUNT=4", reminders=[30])
    rid = quote(occ(client)[1]["recurrenceId"])
    assert client.patch(f"/api/events/{e['id']}?scope=this&recurrenceId={rid}", json={"reminders": [10]}).status_code == 200
    j = client.get(f"/api/events/{e['id']}").json()
    assert j["reminders"] == [30]
    assert client.get(f"/api/events/{e['id']}?recurrenceId={rid}").json()["reminders"] == [10]


def test_links_are_links(client, family_id):
    assert mk(client, family_id, title="Bad", start="2026-11-02T18:00", url="javascript:alert(1)")["url"] is None
    assert mk(client, family_id, title="Good", start="2026-11-02T19:00", url=" https://example.org/x ")["url"] == "https://example.org/x"
    assert ical.safe_url("mailto:a@b.c") == "mailto:a@b.c" and ical.safe_url("data:text/html,x") is None


def test_search_takes_wildcards_literally(client, family_id):
    mk(client, family_id, title="100% done", start="2026-11-02T10:00")
    mk(client, family_id, title="1000 doors", start="2026-11-03T10:00")
    mk(client, family_id, title="a_b", start="2026-11-04T10:00")
    mk(client, family_id, title="aXb", start="2026-11-05T10:00")
    assert [i["title"] for i in client.get("/api/events", params={"q": "100%"}).json()["items"]] == ["100% done"]
    assert [i["title"] for i in client.get("/api/events", params={"q": "a_b"}).json()["items"]] == ["a_b"]
    assert model._like("50\\%_x") == "%50\\\\\\%\\_x%"


def test_bare_dates_are_local_days(client, family_id):
    mk(client, family_id, title="Late", start="2026-11-10T23:30", end="2026-11-10T23:45", timezone="America/New_York")
    assert [i["title"] for i in occ(client, "2026-11-10", "2026-11-11")] == ["Late"]  # the server's zone, not UTC
    assert occ(client, "2026-11-11", "2026-11-12") == []


def test_jcal_params_and_freebusy_names_stay_on_their_line(client, family_id):
    j = ["vcalendar", [["prodid", {}, "text", "x"], ["version", {}, "text", "2.0"]], [["vevent", [
        ["uid", {}, "text", "j1@test"], ["dtstart", {"tzid": "Europe/Brussels\"\r\nSUMMARY:injected"}, "date-time", "2026-11-10T10:00:00"],
        ["summary", {}, "text", "Lunch"], ["attendee", {"cn": "Ann; Lee"}, "cal-address", "mailto:ann@x.org"]], []]]]
    r = client.post(f"/api/events?calendar={family_id}", json=j)
    assert r.status_code == 201, r.text
    assert r.json()["title"] == "Lunch" and r.json()["people"][0]["name"] == "Ann; Lee"
    assert ical._param('a"b\nc;d') == '"abc;d"'
    client.patch("/api/auth/me", json={"displayName": "Alex; the \"first\"\r\nATTENDEE:x", "email": "alex@x.org"})
    tok = re.search(r"/ics/([^/]+)/", client.get("/api/connect").json()["all"]).group(1)
    vfb = client.get(f"/ics/{tok}/freebusy.vfb").text
    assert 'ORGANIZER;CN="Alex; the firstATTENDEE:x":mailto:alex@x.org' in vfb


def test_orphan_override_survives_its_own_deletion(client, family_id):
    ics = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//EN\r\nBEGIN:VEVENT\r\nUID:orphan@test\r\nDTSTAMP:20260101T000000Z\r\n"
           "RECURRENCE-ID:20261110T100000Z\r\nDTSTART:20261110T110000Z\r\nDTEND:20261110T120000Z\r\nSUMMARY:Moved\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
    r = client.post(f"/api/events?calendar={family_id}", content=ics, headers={"Content-Type": "text/calendar"})
    assert r.status_code == 201, r.text
    cal = ical.parse(ics)
    ical.remove_occurrence(cal, "2026-11-10T10:00:00Z")
    ical.end_series_before(cal, "2026-11-10T10:00:00Z")
    assert len(ical.events_of(cal)) == 1
    # an import puts the series before its changed occurrences, whatever order the file had
    text = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//EN\r\n"
            "BEGIN:VEVENT\r\nUID:s@test\r\nDTSTAMP:20260101T000000Z\r\nRECURRENCE-ID:20261111T100000Z\r\nDTSTART:20261111T120000Z\r\nSUMMARY:Later\r\nEND:VEVENT\r\n"
            "BEGIN:VEVENT\r\nUID:s@test\r\nDTSTAMP:20260101T000000Z\r\nDTSTART:20261110T100000Z\r\nRRULE:FREQ=DAILY;COUNT=3\r\nSUMMARY:Series\r\nEND:VEVENT\r\n"
            "END:VCALENDAR\r\n")
    (obj,) = ical.split_by_uid(ical.parse(text))
    assert "RECURRENCE-ID" not in ical.events_of(obj)[0]


def test_caldav_matches_categories_and_overrides_and_bumps_once(client, dav):
    ics = ICS.format(uid="c1", start="20261110T100000", end="20261110T110000", title="Piano", extra="CATEGORIES:Emma,Music\r\n")
    assert dav("PUT", "/dav/calendars/alex/family/c1.ics", ics).status_code == 201
    ics2 = (ICS.format(uid="c2", start="20261112T100000", end="20261112T110000", title="Swim", extra="RRULE:FREQ=DAILY;COUNT=3\r\n")
            .replace("END:VCALENDAR", "BEGIN:VEVENT\r\nUID:c2\r\nDTSTAMP:20260101T000000Z\r\nRECURRENCE-ID;TZID=Europe/Brussels:20261113T100000\r\n"
                     "DTSTART;TZID=Europe/Brussels:20261113T110000\r\nDTEND;TZID=Europe/Brussels:20261113T120000\r\nSUMMARY:Swim (later)\r\nEND:VEVENT\r\nEND:VCALENDAR"))
    assert dav("PUT", "/dav/calendars/alex/family/c2.ics", ics2).status_code == 201

    def query(prop, needle, **attrs):
        a = "".join(f' {k.replace("_", "-")}="{v}"' for k, v in attrs.items())
        q = ('<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:getetag/></d:prop>'
             f'<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT"><c:prop-filter name="{prop}">'
             f'<c:text-match{a}>{needle}</c:text-match></c:prop-filter></c:comp-filter></c:comp-filter></c:filter></c:calendar-query>')
        return re.findall(r"/family/(c\d)\.ics", dav("REPORT", "/dav/calendars/alex/family/", q, Depth="1").text)
    assert query("CATEGORIES", "music") == ["c1"]
    assert query("SUMMARY", "(later)") == ["c2"]  # a changed occurrence counts
    assert query("SUMMARY", "pia", match_type="starts-with") == ["c1"] and query("SUMMARY", "pia", match_type="ends-with") == []
    tok = lambda: re.search(r"<cs:getctag>(\d+)</cs:getctag>", dav("PROPFIND", "/dav/calendars/alex/family/", '<d:propfind xmlns:d="DAV:" xmlns:cs="http://calendarserver.org/ns/"><d:prop><cs:getctag/></d:prop></d:propfind>', Depth="0").text).group(1)
    before = int(tok())
    pp = ('<d:propertyupdate xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav" xmlns:a="http://apple.com/ns/ical/"><d:set><d:prop>'
          '<d:displayname>Us</d:displayname><c:calendar-description>all of us</c:calendar-description><a:calendar-color>#00FF00FF</a:calendar-color>'
          '</d:prop></d:set></d:propertyupdate>')
    assert dav("PROPPATCH", "/dav/calendars/alex/family/", pp).status_code == 207
    assert int(tok()) == before + 1
    assert dav("PROPFIND", "/dav/", b"x" * (3 * 1024 * 1024), Depth="0").status_code == 413


def test_shared_slugs_are_unique(client):
    import pymysql
    db.ex("INSERT INTO cal_calendars (owner_id, slug, name) VALUES (NULL, 'twice', 'One')")
    with pytest.raises(pymysql.err.IntegrityError):
        db.ex("INSERT INTO cal_calendars (owner_id, slug, name) VALUES (NULL, 'twice', 'Two')")
    db.ex("INSERT INTO cal_calendars (owner_id, slug, name) VALUES (1, 'twice', 'Mine')")


def test_iocontacts_is_found_in_the_suite(client, monkeypatch):
    from iosuite_shared import links, suite
    from app import contacts, db
    db.set_setting("iocontacts_url", "https://old.example.org")
    db.set_setting("iocontacts_password", "old")
    contacts.forget_old_settings()
    assert db.get_setting("iocontacts_url") is None and db.get_setting("iocontacts_password") is None
    assert client.get("/api/iocontacts/settings").json()["enabled"] is False
    suite.register("iocontacts", name="ioContacts", url="https://contacts.example.org", version="1")
    s = client.get("/api/iocontacts/settings").json()
    assert s["enabled"] and s["url"] == "https://contacts.example.org"
    seen = []

    class R:
        def __init__(self, b):
            self.b = b

        def read(self):
            return self.b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(app, provider, path, **kw):
        seen.append((app, provider, path, kw.get("sign_in", True)))
        return R(b'{"items": [{"id": 3, "fn": "Ann", "email": "a@x.org"}]}')
    monkeypatch.setattr(links, "get", fake)
    assert contacts.search("ann")[0] == {"contactId": 3, "name": "Ann", "email": "a@x.org", "url": "https://contacts.example.org/#/c/3"}
    assert seen[0][:2] == ("iocalendar", "iocontacts")
    assert client.post("/api/iocontacts/settings", json={"birthdays": False}).json()["birthdays"] is False


def test_base_url_is_an_address(client):
    r = client.get("/api/connect", headers={"X-Forwarded-Proto": "javascript", "X-Forwarded-Host": "evil.example/x\"<"})
    assert r.json()["server"].startswith("http://") and "evil" not in r.json()["server"]
    r = client.get("/api/connect", headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "cal.example.org:8443"})
    assert r.json()["server"] == "https://cal.example.org:8443"
