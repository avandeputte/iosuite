"""Public holidays (the read-only Holidays calendar) and family members tagged on events."""
from app import members

from test_mcp import app_password, call


def holidays_cal(client):
    return next((c for c in client.get("/api/calendars").json()["items"] if c["kind"] == "holidays"), None)


def test_holidays_calendar(client, family_id):
    assert holidays_cal(client) is None  # HOLIDAYS_COUNTRY=off in the tests
    assert any(c["code"] == "BE" for c in client.get("/api/holidays/countries").json()["items"])
    us = client.get("/api/holidays/countries/US").json()
    assert {"code": "NY", "name": "New York"} in us["regions"]
    r = client.post("/api/holidays/settings", json={"country": "US", "region": "NY"})
    assert r.status_code == 200 and r.json()["sync"]["ok"] and r.json()["regionName"] == "New York", r.text
    c = holidays_cal(client)
    assert c and c["shared"] and not c["writable"] and c["name"] == "Holidays"
    items = client.get("/api/occurrences", params={"start": "2026-07-01", "end": "2026-07-10", "calendars": c["id"]}).json()["items"]
    assert [(i["title"], i["start"], i["allDay"], i["busy"]) for i in items] == [
        ("Independence Day (observed)", "2026-07-03", True, False), ("Independence Day", "2026-07-04", True, False)]  # a Saturday
    # read-only for everyone, but an admin may rename and recolor it
    assert client.post(f"/api/events?calendar={c['id']}", json={"title": "x", "start": "2026-07-05"}).status_code == 403
    assert client.patch(f"/api/calendars/{c['id']}", json={"color": "#00aa00"}).status_code == 200
    # syncing again changes nothing; another country replaces the dates
    assert client.post("/api/holidays/sync").json()["changed"] == 0
    r = client.post("/api/holidays/settings", json={"country": "BE", "language": "nl"}).json()
    assert r["country"] == "BE" and r["region"] is None and r["sync"]["changed"] > 0
    items = client.get("/api/occurrences", params={"start": "2026-07-20", "end": "2026-07-23", "calendars": c["id"]}).json()["items"]
    assert [i["title"] for i in items] == ["Nationale feestdag"]
    assert client.post("/api/holidays/settings", json={"country": "XX"}).status_code == 400
    # also over CalDAV and the subscription links: an ordinary (read-only) calendar
    feeds = client.get("/api/connect").json()
    ics = client.get(next(f["ics"] for f in feeds["calendars"] if f["id"] == c["id"]).split("testserver", 1)[1]).text
    assert "Nationale feestdag" in ics and "TRANSP:TRANSPARENT" in ics
    # switched off: gone
    client.post("/api/holidays/settings", json={"country": ""})
    assert holidays_cal(client) is None


def test_country_from_time_zone():
    from app import holiday
    assert holiday.country_for_tz("America/New_York") == "US"
    assert holiday.country_for_tz("Europe/Brussels") == "BE"
    assert holiday.country_for_tz("Nowhere/Else") is None


def test_family_member_tags(client, family_id):
    members.TTL = 0
    assert client.post("/api/users", json={"name": "emma", "password": "emmapass99", "role": "viewer", "displayName": "Emma"}).status_code == 200
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
    client.post("/api/users", json={"name": "emma", "password": "emmapass99", "role": "viewer", "displayName": "Emma"})
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
    assert r["country"] == "US" and r["sync"]["ok"]


def test_leave_accounts_out_of_the_family(client, family_id):
    members.TTL = 0
    client.post("/api/users", json={"name": "admin2", "password": "adminpass99", "role": "admin"})
    client.post("/api/users", json={"name": "emma", "password": "emmapass99", "role": "viewer", "displayName": "Emma"})
    fam = client.get("/api/members").json()
    admin2 = next(m for m in fam["items"] if m["name"] == "admin2")
    assert fam["leftOut"] == []
    # signing in makes a Personal calendar; leaving the family removes it while it is empty
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": "admin2", "password": "adminpass99"}).status_code == 200
    assert [c["name"] for c in client.get("/api/calendars").json()["items"] if not c["shared"]] == ["Personal"]
    r = client.put(f"/api/members/{admin2['id']}", json={"inFamily": False})
    assert r.status_code == 200 and r.json()["inFamily"] is False
    assert "admin2" not in [m["name"] for m in r.json()["items"]]
    assert [c for c in client.get("/api/calendars").json()["items"] if not c["shared"]] == []  # and none is made again
    assert client.get("/api/members").json()["leftOut"] == [admin2["id"]]
    # it can no longer be a tag or a filter
    r = client.post(f"/api/events?calendar={family_id}", json={"title": "x", "start": "2026-11-20T10:00", "members": ["admin2"]})
    assert r.status_code == 400
    assert client.get("/api/occurrences", params={"start": "2026-11-01", "end": "2026-12-01", "member": "admin2"}).status_code == 400
    # viewers may not change the family; back in, it gets its calendar again
    client.cookies.clear()
    client.post("/api/auth/login", json={"name": "emma", "password": "emmapass99"})
    assert client.put(f"/api/members/{admin2['id']}", json={"inFamily": True}).status_code == 403
    assert "leftOut" not in client.get("/api/members").json()
    client.cookies.clear()
    client.post("/api/auth/login", json={"name": "admin2", "password": "adminpass99"})
    assert client.put(f"/api/members/{admin2['id']}", json={"inFamily": True}).json()["inFamily"] is True
    assert [c["name"] for c in client.get("/api/calendars").json()["items"] if not c["shared"]] == ["Personal"]
