"""Public holidays (the read-only Holidays calendar) and family members tagged on events."""
from app import members

from test_mcp import app_password, call
from iosuite_shared import testing


def holidays_cals(client):
    return [c for c in client.get("/api/calendars").json()["items"] if c["kind"] == "holidays"]


def titles(client, cal, start, end):
    return [i["title"] for i in client.get("/api/occurrences", params={"start": start, "end": end, "calendars": cal["id"]}).json()["items"]]


def test_holidays_calendars(client, family_id):
    assert holidays_cals(client) == []  # HOLIDAYS_COUNTRY=off in the tests
    assert any(c["code"] == "BE" for c in client.get("/api/holidays/countries").json()["items"])
    us = client.get("/api/holidays/countries/US").json()
    assert {"code": "NY", "name": "New York"} in us["regions"]
    r = client.post("/api/holidays/settings", json={"items": [{"country": "US", "region": "NY"}]})
    assert r.status_code == 200 and r.json()["sync"]["ok"] and r.json()["items"][0]["regionName"] == "New York", r.text
    [c] = holidays_cals(client)
    assert c["shared"] and not c["writable"] and c["name"] == "Holidays (United States)"
    assert r.json()["items"][0]["calendar"] == c["id"]
    items = client.get("/api/occurrences", params={"start": "2026-07-01", "end": "2026-07-10", "calendars": c["id"]}).json()["items"]
    assert [(i["title"], i["start"], i["allDay"], i["busy"]) for i in items] == [
        ("Independence Day (observed)", "2026-07-03", True, False), ("Independence Day", "2026-07-04", True, False)]  # a Saturday
    # read-only for everyone, but an admin may rename and recolor it
    assert client.post(f"/api/events?calendar={c['id']}", json={"title": "x", "start": "2026-07-05"}).status_code == 403
    assert client.patch(f"/api/calendars/{c['id']}", json={"color": "#00aa00"}).status_code == 200
    assert client.post("/api/holidays/sync").json()["changed"] == 0  # syncing again changes nothing
    # a second country: its own calendar, the first one stays as it was
    r = client.post("/api/holidays/settings", json={"items": [{"country": "US", "region": "NY"}, {"country": "BE", "language": "nl"}]}).json()
    assert [x["country"] for x in r["items"]] == ["US", "BE"] and r["sync"]["ok"] and r["sync"]["calendars"] == 2
    us_cal, be_cal = sorted(holidays_cals(client), key=lambda x: x["id"])
    assert us_cal["id"] == c["id"] and us_cal["color"] == "#00aa00" and be_cal["name"] == "Holidays (Belgium)"
    assert titles(client, be_cal, "2026-07-20", "2026-07-23") == ["Nationale feestdag"]
    assert titles(client, us_cal, "2026-07-20", "2026-07-23") == []
    # wrong entries are refused as a whole
    assert client.post("/api/holidays/settings", json={"items": [{"country": "XX"}]}).status_code == 400
    assert client.post("/api/holidays/settings", json={"items": [{"country": "BE"}, {"country": "be"}]}).status_code == 400
    assert client.post("/api/holidays/settings", json={"items": [{"country": "BE", "region": "NY"}]}).status_code == 400
    assert client.post("/api/holidays/settings", json={"country": "BE"}).status_code == 400
    assert len(holidays_cals(client)) == 2
    # also over CalDAV and the subscription links: an ordinary (read-only) calendar
    feeds = client.get("/api/connect").json()
    ics = client.get(next(f["ics"] for f in feeds["calendars"] if f["id"] == be_cal["id"]).split("testserver", 1)[1]).text
    assert "Nationale feestdag" in ics and "TRANSP:TRANSPARENT" in ics
    # a country taken off the list loses its calendar; none left: no Holidays calendars
    client.post("/api/holidays/settings", json={"items": [{"country": "BE", "language": "nl"}]})
    assert [x["id"] for x in holidays_cals(client)] == [be_cal["id"]]
    r = client.post("/api/holidays/settings", json={"items": []}).json()
    assert r["items"] == [] and holidays_cals(client) == []


def test_holidays_from_the_environment(monkeypatch):
    from app import config, holiday
    monkeypatch.setattr(config, "HOLIDAYS_COUNTRY", "be, nl")
    monkeypatch.setattr(config, "HOLIDAYS_REGION", "")
    monkeypatch.setattr(config, "HOLIDAYS_LANGUAGE", "fr")
    assert holiday._from_env() == ([{"country": "BE", "region": None, "language": "fr"}, {"country": "NL", "region": None, "language": None}], False)
    monkeypatch.setattr(config, "HOLIDAYS_COUNTRY", "")
    assert holiday._from_env()[1] is True


def test_country_from_time_zone():
    from app import holiday
    assert holiday.country_for_tz("America/New_York") == "US"
    assert holiday.country_for_tz("Europe/Brussels") == "BE"
    assert holiday.country_for_tz("Nowhere/Else") is None


def test_family_member_tags(client, family_id):
    members.TTL = 0
    assert testing.add_account(client, {"name": "emma", "password": "emmapass99", "role": "viewer", "displayName": "Emma"}).status_code == 200
    fam = client.get("/api/members").json()["items"]
    emma = next(m for m in fam if m["name"] == "emma")
    alex = next(m for m in fam if m["name"] == "alex")
    e = client.post(f"/api/events?calendar={family_id}", json={"title": "Swimming", "start": "2026-11-10T16:00", "rrule": "FREQ=WEEKLY;COUNT=4",
                                                              "members": ["emma"], "categories": ["Sport"]}).json()
    assert [m["id"] for m in e["members"]] == [emma["id"]] and e["categories"] == ["Sport", emma["displayName"]]
    other = client.post(f"/api/events?calendar={family_id}", json={"title": "Dentist", "start": "2026-11-11T09:00", "members": [alex["id"]]}).json()
    client.post(f"/api/events?calendar={family_id}", json={"title": "Dinner", "start": "2026-11-12T19:00"})
    # the tag is a CATEGORIES value, so calendar apps see it
    ics = client.get(f"/api/events/{e['id']}?format=ics").text
    assert f"CATEGORIES:Sport,{emma['displayName']}" in ics
    # filters
    p = {"start": "2026-11-01", "end": "2026-12-05"}
    assert [i["title"] for i in client.get("/api/occurrences", params={**p, "member": "emma"}).json()["items"]] == ["Swimming"] * 4
    both = client.get("/api/occurrences", params={**p, "member": f"emma,{alex['id']}"}).json()["items"]
    assert sorted({i["title"] for i in both}) == ["Dentist", "Swimming"]
    assert [x["title"] for x in client.get("/api/events", params={"member": "alex"}).json()["items"]] == ["Dentist"]
    assert client.get("/api/occurrences", params={**p, "member": "nobody"}).status_code == 400
    all_ = client.get("/api/occurrences", params=p).json()["items"]
    assert next(i for i in all_ if i["title"] == "Dinner")["members"] == []
    # changing the tags keeps the other categories; one occurrence can have its own
    r = client.patch(f"/api/events/{e['id']}", json={"members": ["emma", "alex"]}).json()
    assert r["categories"] == ["Sport", emma["displayName"], alex["displayName"]]
    occ = [i for i in client.get("/api/occurrences", params={**p, "member": "emma"}).json()["items"]]
    rid = occ[1]["recurrenceId"]
    client.patch(f"/api/events/{e['id']}?scope=this&recurrenceId={rid}", json={"members": ["alex"]})
    assert len(client.get("/api/occurrences", params={**p, "member": "emma"}).json()["items"]) == 3
    assert client.patch(f"/api/events/{other['id']}", json={"members": []}).json()["categories"] == []
    # a category typed in another app with a member's name tags the event too
    raw = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//t//EN\r\nBEGIN:VEVENT\r\nUID:piano@x\r\nDTSTAMP:20261101T000000Z\r\n"
           "DTSTART:20261113T170000Z\r\nDTEND:20261113T180000Z\r\nSUMMARY:Piano\r\nCATEGORIES:EMMA\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
    assert client.post(f"/api/events?calendar={family_id}", content=raw, headers={"Content-Type": "text/calendar"}).status_code == 201
    titles = [i["title"] for i in client.get("/api/occurrences", params={**p, "member": "emma"}).json()["items"]]
    assert "Piano" in titles
    # one person's own subscription link
    tok_url = client.get("/api/connect").json()["calendars"][0]["ics"].split("testserver", 1)[1]
    feed = client.get(tok_url, params={"member": "emma"}).text
    assert "Swimming" in feed and "Piano" in feed and "Dinner" not in feed


def test_mcp_members(client, family_id):
    members.TTL = 0
    client.post("/api/server", json={"mcpEnabled": True})
    testing.add_account(client, {"name": "emma", "password": "emmapass99", "role": "viewer", "displayName": "Emma"})
    auth, _ = app_password(client)
    ov = call(client, auth, "overview")
    assert "Emma" in ov["family"]
    e = call(client, auth, "create_event", title="Recital", start="2026-11-20T18:00", members=["Emma"])
    assert e["members"] == ["Emma"]
    got = call(client, auth, "agenda", start="2026-11-20", end="2026-11-21", member=["emma"])
    assert [i["title"] for i in got["items"]] == ["Recital"] and got["items"][0]["members"] == ["Emma"]
    assert call(client, auth, "agenda", start="2026-11-20", end="2026-11-21", member=["alex"])["items"] == []
    assert call(client, auth, "update_event", event=str(e["id"]), members=[]).get("members") is None
    assert "error" in call(client, auth, "create_event", title="x", start="2026-11-20", members=["ghost"])
    r = call(client, auth, "set_holidays", country="US", region="CA")
    assert [x["country"] for x in r["countries"]] == ["US"] and r["sync"]["ok"]
    r = call(client, auth, "set_holidays", country="NL")
    assert [(x["country"], x["region"]) for x in r["countries"]] == [("US", "CA"), ("NL", None)]
    r = call(client, auth, "set_holidays", country="US")  # the region changes; the order stays
    assert [(x["country"], x["region"]) for x in r["countries"]] == [("US", None), ("NL", None)]
    assert call(client, auth, "overview")["holidays"] == ["United States", "Netherlands"]
    r = call(client, auth, "set_holidays", country="US", remove=True)
    assert [x["country"] for x in r["countries"]] == ["NL"]
    assert "error" in call(client, auth, "set_holidays", country="FR", remove=True)


def test_leave_accounts_out_of_the_family(client, family_id):
    """The family is the suite's (Settings › Security › Family, iosuite_shared.family): taking someone out there takes
    them out of ioCalendar's tags and filters too."""
    members.TTL = 0
    testing.add_account(client, {"name": "admin2", "password": "adminpass99", "role": "admin"})
    testing.add_account(client, {"name": "emma", "password": "emmapass99", "role": "viewer", "displayName": "Emma"})
    fam = client.get("/api/members").json()["items"]
    admin2 = next(m for m in fam if m["name"] == "admin2")
    assert {"initials", "color", "hasFace"} <= set(admin2) and admin2["color"].startswith("#")
    assert len({m["color"] for m in fam}) == len(fam)  # no two alike
    # out of the family (a suite admin, in the shared panel)
    r = client.patch(f"/api/suite-admin/family/{admin2['id']}", json={"inFamily": False})
    assert r.status_code == 200 and r.json()["inFamily"] is False
    assert "admin2" not in [m["name"] for m in client.get("/api/members").json()["items"]]
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": "admin2", "password": "adminpass99"}).status_code == 200
    assert [c for c in client.get("/api/calendars").json()["items"] if not c["shared"]] == []  # no private calendar made
    # it can no longer be a tag or a filter
    r = client.post(f"/api/events?calendar={family_id}", json={"title": "x", "start": "2026-11-20T10:00", "members": ["admin2"]})
    assert r.status_code == 400
    assert client.get("/api/occurrences", params={"start": "2026-11-01", "end": "2026-12-01", "member": "admin2"}).status_code == 400
    # only suite admins change the family; ioCalendar has no screen of its own for it
    client.cookies.clear()
    client.post("/api/auth/login", json={"name": "emma", "password": "emmapass99"})
    assert client.patch(f"/api/suite-admin/family/{admin2['id']}", json={"inFamily": True}).status_code == 403
    assert client.put(f"/api/members/{admin2['id']}", json={"inFamily": True}).status_code in (404, 405)
    # a picked colour shows here as it does in every app
    client.cookies.clear()
    client.post("/api/auth/login", json={"name": "alex", "password": "secret123"})
    emma = next(m for m in client.get("/api/members").json()["items"] if m["name"] == "emma")
    assert client.patch(f"/api/suite-admin/family/{emma['id']}", json={"color": "#123456"}).status_code == 200
    assert next(m for m in client.get("/api/members").json()["items"] if m["name"] == "emma")["color"] == "#123456"
    assert client.get("/api/auth/family").json()["items"] == client.get("/api/members").json()["items"]
    # back in, it gets its calendar again
    client.patch(f"/api/suite-admin/family/{admin2['id']}", json={"inFamily": True})
    client.cookies.clear()
    client.post("/api/auth/login", json={"name": "admin2", "password": "adminpass99"})
    assert [c["name"] for c in client.get("/api/calendars").json()["items"] if not c["shared"]] == ["Personal"]

