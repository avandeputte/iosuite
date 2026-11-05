"""The REST API: calendars, events, repeating events and their occurrences, scopes, formats, roles, feeds."""
import io


def mk(client, cal, **kw):
    r = client.post(f"/api/events?calendar={cal}", json=kw)
    assert r.status_code == 201, r.text
    return r.json()


def occ(client, start="2026-11-01", end="2026-12-01", **kw):
    r = client.get("/api/occurrences", params={"start": start, "end": end, **kw})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_calendars_family_and_personal(client):
    cals = client.get("/api/calendars").json()["items"]
    assert [(c["name"], c["shared"]) for c in cals] == [("Family", True), ("Personal", False)]
    r = client.post("/api/calendars", json={"name": "Soccer", "color": "#FF0000", "shared": True})
    assert r.status_code == 201 and r.json()["calendar"]["color"] == "#ff0000"
    cid = r.json()["calendar"]["id"]
    assert client.patch(f"/api/calendars/{cid}", json={"name": "Football"}).json()["calendar"]["name"] == "Football"
    assert client.delete(f"/api/calendars/{cid}").status_code == 200


def test_event_fields_round_trip(client, family_id):
    e = mk(client, family_id, title="Dentist", start="2026-11-05T14:00", end="2026-11-05T15:00", timezone="Europe/Brussels",
           location="Rue de la Loi 1, Brussels", notes="Bring the card", people=[{"name": "Ann Lee", "email": "ann@x.org"}, "Bob"],
           reminders=[30, 1440])
    assert e["start"] == "2026-11-05T14:00:00+01:00" and e["timezone"] == "Europe/Brussels"
    assert [p["name"] for p in e["people"]] == ["Ann Lee", "Bob"] and e["reminders"] == [30, 1440]
    got = client.get(f"/api/events/{e['id']}").json()
    assert got["location"] == "Rue de la Loi 1, Brussels" and got["notes"] == "Bring the card"
    # iCalendar and jCal by content negotiation
    ics = client.get(f"/api/events/{e['id']}", headers={"Accept": "text/calendar"}).text
    assert "BEGIN:VALARM" in ics and "TRIGGER:-PT30M" in ics and "Ann Lee" in ics and "mailto:ann@x.org" in ics.replace("\r\n ", "") and "BEGIN:VTIMEZONE" in ics
    j = client.get(f"/api/events/{e['id']}?format=jcal").json()
    assert j[0] == "vcalendar"
    # search finds it by a person, a place and the notes
    assert [x["id"] for x in client.get("/api/events?q=ann").json()["items"]] == [e["id"]]
    assert client.get("/api/events?q=brussels card").json()["items"][0]["title"] == "Dentist"
    # PATCH changes only what it names; If-Match refuses a stale copy
    r = client.patch(f"/api/events/{e['id']}", json={"title": "Dentist (Dr. Smith)"}, headers={"If-Match": '"nope"'})
    assert r.status_code == 412
    r = client.patch(f"/api/events/{e['id']}", json={"title": "Dentist (Dr. Smith)"}, headers={"If-Match": got["etag"]})
    assert r.status_code == 200 and r.json()["location"] == "Rue de la Loi 1, Brussels" and r.json()["sequence"] == 1
    # moving keeps the length
    r = client.patch(f"/api/events/{e['id']}", json={"start": "2026-11-06T09:30"}).json()
    assert r["start"] == "2026-11-06T09:30:00+01:00" and r["end"] == "2026-11-06T10:30:00+01:00"
    assert client.delete(f"/api/events/{e['id']}").status_code == 200
    assert client.get(f"/api/events/{e['id']}").status_code == 404


def test_all_day_and_occurrences(client, family_id):
    mk(client, family_id, title="Holiday", allDay=True, start="2026-11-20", end="2026-11-23")
    mk(client, family_id, title="Lunch", start="2026-11-20T12:00", timezone="America/New_York")
    items = occ(client, "2026-11-20", "2026-11-21")
    assert [(i["title"], i["allDay"]) for i in items] == [("Holiday", True), ("Lunch", False)]
    assert items[0]["start"] == "2026-11-20" and items[0]["end"] == "2026-11-23"
    assert items[1]["end"] == "2026-11-20T13:00:00-05:00"  # an hour unless said otherwise
    assert occ(client, "2026-11-24", "2026-11-30") == []


def test_repeating_events_and_scopes(client, family_id):
    e = mk(client, family_id, title="Standup", start="2026-11-02T09:00", end="2026-11-02T09:15", timezone="America/New_York",
           rrule="FREQ=DAILY;COUNT=10")
    items = occ(client, "2026-11-01", "2026-11-30")
    assert len(items) == 10 and all(i["recurring"] for i in items)
    rid3 = items[2]["recurrenceId"]
    # one occurrence moved
    r = client.patch(f"/api/events/{e['id']}?scope=this&recurrenceId={rid3}", json={"start": "2026-11-04T15:00", "end": "2026-11-04T15:15", "title": "Late standup"})
    assert r.status_code == 200, r.text
    items = occ(client)
    assert items[2]["title"] == "Late standup" and items[2]["start"] == "2026-11-04T15:00:00-05:00"
    assert items[2]["recurrenceId"] == rid3
    # one occurrence deleted
    rid5 = items[4]["recurrenceId"]
    assert client.delete(f"/api/events/{e['id']}?scope=this&recurrenceId={rid5}").status_code == 200
    items = occ(client)
    assert len(items) == 9 and rid5 not in [i["recurrenceId"] for i in items]
    # this and following: split in two series with the same number of occurrences in all
    rid7 = items[5]["recurrenceId"]  # the 7th day
    r = client.patch(f"/api/events/{e['id']}?scope=following&recurrenceId={rid7}", json={"title": "New standup", "start": "2026-11-08T10:00", "end": "2026-11-08T10:15"})
    assert r.status_code == 201, r.text
    items = occ(client)
    titles = [i["title"] for i in items]
    assert titles.count("New standup") == 4 and len(items) == 9
    assert [i["start"][11:16] for i in items if i["title"] == "New standup"] == ["10:00"] * 4
    old = client.get(f"/api/events/{e['id']}").json()
    assert "UNTIL=" in old["rrule"] and "COUNT" not in old["rrule"]
    # all: moving one occurrence's time moves the series
    first = [i for i in items if i["id"] == e["id"]][0]
    r = client.patch(f"/api/events/{e['id']}?scope=all&recurrenceId={first['recurrenceId']}", json={"start": "2026-11-02T08:00", "end": "2026-11-02T08:15"})
    assert r.status_code == 200
    assert [i["start"][11:16] for i in occ(client) if i["id"] == e["id"]][:2] == ["08:00", "08:00"]


def test_ics_and_jcal_bodies(client, family_id):
    ics = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//EN\r\nBEGIN:VEVENT\r\nUID:abc-1@test\r\nDTSTAMP:20260101T000000Z\r\n"
           "DTSTART;VALUE=DATE:20261225\r\nSUMMARY:Christmas\r\nRRULE:FREQ=YEARLY\r\nX-CUSTOM:kept\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
    r = client.post(f"/api/events?calendar={family_id}", content=ics, headers={"Content-Type": "text/calendar"})
    assert r.status_code == 201 and r.json()["title"] == "Christmas" and r.json()["allDay"]
    eid = r.json()["id"]
    assert client.post(f"/api/events?calendar={family_id}", content=ics, headers={"Content-Type": "text/calendar"}).status_code == 409
    client.patch(f"/api/events/{eid}", json={"notes": "Family dinner"})
    assert "X-CUSTOM:kept" in client.get(f"/api/events/{eid}?format=ics").text  # what an app put there stays
    assert [i["start"] for i in occ(client, "2026-01-01", "2028-01-01") if i["id"] == eid] == ["2026-12-25", "2027-12-25"]
    j = client.get(f"/api/events/{eid}?format=jcal").json()
    j[2] = [c for c in j[2] if c[0] == "vevent"]
    for p in j[2][0][1]:
        if p[0] == "uid":
            p[3] = "abc-2@test"
        if p[0] == "summary":
            p[3] = "Boxing day"
        if p[0] == "dtstart":
            p[3] = "2026-12-26"
    r = client.post(f"/api/events?calendar={family_id}", json=j, headers={"Content-Type": "application/calendar+json"})
    assert r.status_code == 201, r.text
    assert r.json()["title"] == "Boxing day" and r.json()["start"] == "2026-12-26" and r.json()["rrule"] == "FREQ=YEARLY"


def test_import_export_and_feeds(client, family_id):
    ics = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:x\r\n"
           "BEGIN:VEVENT\r\nUID:i1\r\nDTSTAMP:20260101T000000Z\r\nDTSTART:20261110T150000Z\r\nDTEND:20261110T160000Z\r\nSUMMARY:One\r\nEND:VEVENT\r\n"
           "BEGIN:VEVENT\r\nUID:i2\r\nDTSTAMP:20260101T000000Z\r\nDTSTART;VALUE=DATE:20261111\r\nSUMMARY:Two\r\nEND:VEVENT\r\n"
           "BEGIN:VEVENT\r\nUID:i2\r\nDTSTAMP:20260101T000000Z\r\nRECURRENCE-ID;VALUE=DATE:20261111\r\nDTSTART;VALUE=DATE:20261112\r\nSUMMARY:Two moved\r\nEND:VEVENT\r\n"
           "END:VCALENDAR\r\n")
    r = client.post(f"/api/calendars/{family_id}/import", files={"file": ("x.ics", io.BytesIO(ics.encode()), "text/calendar")})
    assert r.json() == {"created": 2, "updated": 0, "skipped": 0, "errors": []}
    r = client.post(f"/api/calendars/{family_id}/import", content=ics, headers={"Content-Type": "text/calendar"})
    assert r.json()["updated"] == 2
    out = client.get(f"/api/calendars/{family_id}/export").text
    assert out.count("BEGIN:VEVENT") == 3 and "X-WR-CALNAME:Family" in out
    info = client.get("/api/connect").json()
    fam = next(c for c in info["calendars"] if c["name"] == "Family")
    client.cookies.clear()
    feed = client.get(fam["ics"].split("testserver", 1)[1])
    assert feed.status_code == 200 and feed.text.count("BEGIN:VEVENT") == 3
    assert client.get(info["all"].split("testserver", 1)[1]).status_code == 200
    fb = client.get(info["freebusy"].split("testserver", 1)[1]).text
    assert "BEGIN:VFREEBUSY" in fb
    assert client.get("/ics/" + "0" * 40 + "/all.ics").status_code == 404
    assert client.get("/api/calendars").status_code == 401


def test_roles_viewers_keep_their_own(client, family_id):
    assert client.post("/api/users", json={"name": "kid", "password": "kidpass99", "role": "viewer"}).status_code == 200
    e = mk(client, family_id, title="Family thing", start="2026-11-10T10:00")
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": "kid", "password": "kidpass99"}).status_code == 200
    cals = client.get("/api/calendars").json()["items"]
    mine = next(c for c in cals if not c["shared"])
    fam = next(c for c in cals if c["shared"])
    assert mine["writable"] and not fam["writable"]
    assert client.patch(f"/api/events/{e['id']}", json={"title": "x"}).status_code == 403
    assert client.post(f"/api/events?calendar={family_id}", json={"title": "x", "start": "2026-11-10T10:00"}).status_code == 403
    assert mk(client, mine["id"], title="My own", start="2026-11-10T11:00")["title"] == "My own"
    assert len(occ(client, "2026-11-10", "2026-11-11")) == 2
    # alex does not see kid's private calendar
    client.cookies.clear()
    client.post("/api/auth/login", json={"name": "alex", "password": "secret123"})
    assert [i["title"] for i in occ(client, "2026-11-10", "2026-11-11")] == ["Family thing"]


def test_free_busy(client, family_id):
    mk(client, family_id, title="A", start="2026-11-10T10:00", end="2026-11-10T11:00", timezone="UTC")
    mk(client, family_id, title="B", start="2026-11-10T10:30", end="2026-11-10T12:00", timezone="UTC")
    mk(client, family_id, title="C", start="2026-11-10T13:00", end="2026-11-10T14:00", timezone="UTC", busy=False)
    r = client.get("/api/free-busy", params={"start": "2026-11-10T00:00Z", "end": "2026-11-11T00:00Z"}).json()
    assert r["busy"] == [{"start": "2026-11-10T10:00:00+00:00", "end": "2026-11-10T12:00:00+00:00"}]


def test_status_and_app_passwords(client):
    s = client.get("/api/status").json()
    assert s["app"] == "ioCalendar" and s["user"]["name"] == "alex" and s["user"]["role"] == "admin"
    pw = client.post("/api/auth/app-passwords", json={"label": "phone"}).json()["password"]
    client.cookies.clear()
    assert client.get("/api/calendars", headers={"Authorization": f"Bearer {pw}"}).status_code == 200
    assert client.get("/api/calendars", auth=("alex", pw)).status_code == 200
    assert client.get("/api/calendars", auth=("alex", "wrong")).status_code == 401


def test_registers_in_the_suite_list(client):
    from iosuite_shared import suite
    from app import __version__
    client.get("/api/calendars")
    row = suite.get("iocalendar")
    assert row and row["name"] == "ioCalendar" and row["version"] == __version__
    assert row["description"] == "Calendar" and row["color"] == "#963522"


def test_suite_apps_for_the_app_switcher(client):
    """The app mark becomes a menu of the suite's other apps: the page has the phone's button, may show their icons
    (other origins), and /api/auth/suite lists them with an address and an absolute icon."""
    from iosuite_shared import suite
    html = client.get("/").text
    assert 'id="suitebtn"' in html and "img-src 'self' data: blob: https:" in html
    client.get("/api/calendars")
    suite.register("iocontacts", name="ioContacts", url="https://contacts.example.net", color="#4f2f7d")
    r = client.get("/api/auth/suite").json()
    assert r["app"] == "iocalendar"
    other = [a for a in r["items"] if a["app"] != r["app"]]
    assert [(a["name"], a["url"], a["icon"]) for a in other] == [("ioContacts", "https://contacts.example.net", "https://contacts.example.net/static/icons/mark.svg")]


def test_the_shell_its_files_and_the_icon_are_public(client):
    """The suite's layout: the page at /, every file it names under /static/, the mark at suite.ICON."""
    import re
    from iosuite_shared import suite
    html = client.get("/").text
    paths = re.findall(r'(?:src|href)="(static/[^"?]+)', html)
    paths += [i["src"] for i in client.get("/manifest.webmanifest").json()["icons"]]
    assert paths and all(p.startswith("static/") for p in paths)
    for p in ["/" + p for p in paths] + [suite.ICON, "/static/icons/apple-touch-icon.png"]:
        assert client.get(p).status_code == 200, p
