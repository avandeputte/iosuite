"""The REST API: lists and roles, every task field round-tripping through JSON and iCalendar, due filters, ticking off
(and a repeating task moving on), subtasks, family members, import and export, the Apple profile."""
import datetime as dt
import plistlib
from zoneinfo import ZoneInfo
from iosuite_shared import testing


def new(client, **f):
    r = client.post("/api/tasks", json=f)
    assert r.status_code == 201, r.text
    return r.json()


def test_lists_and_a_private_list_per_person(client, family_id):
    items = client.get("/api/lists").json()["items"]
    assert [(c["name"], c["shared"]) for c in items] == [("Family", True), ("Personal", False)]
    r = client.post("/api/lists", json={"name": "Groceries", "shared": True, "color": "#e0426a"})
    assert r.status_code == 201 and r.json()["list"]["slug"] == "groceries"
    lid = r.json()["list"]["id"]
    assert client.patch(f"/api/lists/{lid}", json={"name": "Shopping"}).json()["list"]["name"] == "Shopping"
    assert client.delete(f"/api/lists/{lid}").json()["ok"]
    personal = next(c["id"] for c in items if not c["shared"])
    assert client.delete(f"/api/lists/{personal}").status_code == 400  # the last private list stays


def test_task_fields_round_trip(client, family_id):
    t = new(client, title="Renew passport", notes="Photos first", due="2026-11-20T17:00", timezone="Europe/Brussels",
            priority="high", url="https://example.com/passport", location="Town hall", categories=["Errands"],
            alarms=["2026-11-20T09:00"], listId=family_id)
    assert t["title"] == "Renew passport" and t["notes"] == "Photos first"
    assert t["due"] == "2026-11-20T17:00:00+01:00" and t["dueAllDay"] is False
    assert t["priority"] == "high" and t["priorityValue"] == 1 and t["done"] is False and t["status"] == "needs-action"
    assert t["url"] == "https://example.com/passport" and t["location"] == "Town hall" and t["categories"] == ["Errands"]
    assert t["alarms"] == ["2026-11-20T08:00:00+00:00"]
    ics = client.get(f"/api/tasks/{t['id']}", headers={"Accept": "text/calendar"}).text
    assert "BEGIN:VTODO" in ics and "PRIORITY:1" in ics and "DUE;TZID=Europe/Brussels:20261120T170000" in ics
    assert "TRIGGER;VALUE=DATE-TIME:20261120T080000Z" in ics and "BEGIN:VTIMEZONE" in ics
    # a day without a time, then no due date at all
    t2 = client.patch(f"/api/tasks/{t['id']}", json={"due": "2026-11-21", "priority": "none"}).json()
    assert t2["due"] == "2026-11-21" and t2["dueAllDay"] and t2["priority"] is None
    assert client.patch(f"/api/tasks/{t['id']}", json={"due": ""}).json()["due"] is None
    # PUT clears what is left out; a javascript: link is not kept
    t3 = client.put(f"/api/tasks/{t['id']}", json={"title": "Passport", "url": "javascript:alert(1)"}).json()
    assert t3["notes"] is None and t3["url"] is None and t3["categories"] == []


def test_due_filters_and_counts(client, family_id):
    today = dt.datetime.now(ZoneInfo("America/New_York")).date()
    new(client, title="late", due=(today - dt.timedelta(days=2)).isoformat())
    new(client, title="today", due=today.isoformat())
    new(client, title="next week", due=(today + dt.timedelta(days=5)).isoformat())
    new(client, title="later", due=(today + dt.timedelta(days=30)).isoformat())
    new(client, title="someday")
    titles = lambda **q: [t["title"] for t in client.get("/api/tasks", params=q).json()["items"]]  # noqa: E731
    assert titles() == ["late", "today", "next week", "later", "someday"]  # soonest due first, undated last
    assert titles(due="today") == ["late", "today"]
    assert titles(due="overdue") == ["late"]
    assert titles(due="week") == ["late", "today", "next week"]
    assert titles(due="none") == ["someday"]
    assert titles(due=today.isoformat()) == ["today"]
    assert titles(q="WEEK") == ["next week"]
    assert client.get("/api/counts").json() == {"today": 2, "overdue": 1, "scheduled": 4, "all": 5}
    assert client.get("/api/tasks", params={"due": "soon"}).status_code == 400


def test_complete_and_reopen(client):
    t = new(client, title="Take out the bins")
    r = client.post(f"/api/tasks/{t['id']}/complete", json={}).json()
    assert r["done"] and r["status"] == "completed" and r["completedAt"] and r["moved"] is False
    assert client.get("/api/tasks").json()["items"] == []
    assert [x["title"] for x in client.get("/api/tasks", params={"status": "done"}).json()["items"]] == ["Take out the bins"]
    assert "COMPLETED:" in client.get(f"/api/tasks/{t['id']}?format=ics").text
    r = client.patch(f"/api/tasks/{t['id']}", json={"done": False}).json()
    assert not r["done"] and r["completedAt"] is None


def test_a_repeating_task_moves_on(client):
    t = new(client, title="Water the plants", due="2026-11-14", rrule="FREQ=WEEKLY;COUNT=3", alarms=["2026-11-14T08:00"])
    r = client.post(f"/api/tasks/{t['id']}/complete", json={}).json()
    assert r["moved"] and not r["done"] and r["due"] == "2026-11-21" and r["rrule"] == "FREQ=WEEKLY;COUNT=2"
    assert r["alarms"][0].startswith("2026-11-21")
    r = client.post(f"/api/tasks/{t['id']}/complete", json={}).json()
    assert r["due"] == "2026-11-28" and r["rrule"] == "FREQ=WEEKLY;COUNT=1"
    r = client.post(f"/api/tasks/{t['id']}/complete", json={}).json()  # the last one: done for good
    assert r["done"] and not r["moved"]
    assert client.post("/api/tasks", json={"title": "x", "rrule": "FREQ=DAILY"}).status_code == 400  # no due date
    assert client.post("/api/tasks", json={"title": "x", "due": "2026-11-14", "rrule": "FREQ=HOURLY"}).status_code == 400


def test_subtasks(client, family_id):
    p = new(client, title="Plan the party", listId=family_id)
    a = new(client, title="Invitations", parent=p["id"])
    new(client, title="Cake", parent=p["id"])
    assert a["listId"] == family_id and a["parent"] == p["uid"]
    client.post(f"/api/tasks/{a['id']}/complete", json={})
    got = client.get(f"/api/tasks/{p['id']}").json()
    assert got["subtasks"] == {"open": 1, "total": 2} and [c["title"] for c in got["children"]] == ["Cake", "Invitations"]
    other = client.post("/api/lists", json={"name": "Other"}).json()["list"]["id"]
    moved = client.patch(f"/api/tasks/{p['id']}", json={"listId": other}).json()
    assert moved["listId"] == other
    assert {t["listId"] for t in client.get("/api/tasks", params={"status": "all", "list": other}).json()["items"]} == {other}
    assert client.delete(f"/api/tasks/{moved['id']}").json()["deleted"] == 3


def test_members(client, family_id):
    testing.add_account(client, {"name": "emma", "password": "secret123", "role": "editor"})
    fam = client.get("/api/members").json()["items"]
    emma = next(m for m in fam if m["name"] == "emma")
    t = new(client, title="Pack the swim bag", members=["emma"], categories=["Sport"])
    assert [m["name"] for m in t["members"]] == ["emma"] and set(t["categories"]) == {"Sport", emma["displayName"]}
    new(client, title="Not for Emma")
    assert [x["title"] for x in client.get("/api/tasks", params={"member": "emma"}).json()["items"]] == ["Pack the swim bag"]


def test_roles(client, family_id):
    testing.add_account(client, {"name": "vic", "password": "secret123", "role": "viewer"})
    t = new(client, title="Shared", listId=family_id)
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": "vic", "password": "secret123"}).status_code == 200
    assert client.get(f"/api/tasks/{t['id']}").status_code == 200
    assert client.patch(f"/api/tasks/{t['id']}", json={"title": "x"}).status_code == 403
    assert client.post("/api/tasks", json={"title": "x", "listId": family_id}).status_code == 403
    assert client.post("/api/tasks", json={"title": "x"}).status_code == 403  # a viewer keeps nothing of their own
    assert client.post("/api/lists", json={"name": "Mine"}).status_code == 403
    assert all(c["shared"] for c in client.get("/api/lists").json()["items"])  # and gets no Personal list


def test_member_keeps_own_lists(client, family_id):
    testing.add_account(client, {"name": "meg", "password": "secret123", "role": "member"})
    t = new(client, title="Shared", listId=family_id)
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": "meg", "password": "secret123"}).status_code == 200
    assert client.patch(f"/api/tasks/{t['id']}", json={"title": "x"}).status_code == 403  # the shared list: read only
    assert client.post("/api/lists", json={"name": "Groceries", "shared": True}).status_code == 403
    mine = new(client, title="My own")  # into meg's own Personal list
    assert mine["listId"] != family_id
    assert client.post("/api/lists", json={"name": "Groceries"}).status_code == 201


def test_ics_create_import_export(client, family_id):
    ics = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:x\r\nBEGIN:VTODO\r\nUID:abc-1\r\nSUMMARY:From a file\r\nDUE;VALUE=DATE:20261201\r\n"
           "X-APPLE-SORT-ORDER:12345\r\nEND:VTODO\r\nEND:VCALENDAR\r\n")
    r = client.post(f"/api/tasks?list={family_id}", content=ics, headers={"Content-Type": "text/calendar"})
    assert r.status_code == 201 and r.json()["due"] == "2026-12-01"
    assert client.post(f"/api/tasks?list={family_id}", content=ics, headers={"Content-Type": "text/calendar"}).status_code == 409
    ev = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:x\r\nBEGIN:VEVENT\r\nUID:e\r\nDTSTART:20261201T100000Z\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    assert client.post("/api/tasks", content=ev, headers={"Content-Type": "text/calendar"}).status_code == 400
    two = ics.replace("abc-1", "abc-2").replace("From a file", "Second").replace("END:VCALENDAR\r\n", "") + \
        "BEGIN:VTODO\r\nUID:abc-1\r\nSUMMARY:Changed\r\nEND:VTODO\r\n" + ev.split("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:x\r\n")[1]
    out = client.post(f"/api/lists/{family_id}/import", files={"file": ("x.ics", two, "text/calendar")}).json()
    assert (out["created"], out["updated"]) == (1, 1)
    exp = client.get(f"/api/lists/{family_id}/export").text
    assert exp.count("BEGIN:VTODO") == 2 and "X-APPLE-SORT-ORDER:12345" not in exp or "Changed" in exp
    assert client.post(f"/api/lists/{family_id}/clear-completed").json()["deleted"] == 0


def test_apple_profile(client):
    r = client.post("/api/apple-profile", data={"label": "iPhone", "password": "new"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-apple-aspen-config")
    p = plistlib.loads(r.content)
    acct = p["PayloadContent"][0]
    assert acct["PayloadType"] == "com.apple.caldav.account" and acct["CalDAVPrincipalURL"] == "/dav/principals/alex/"
    pw = acct["CalDAVPassword"]
    client.cookies.clear()
    assert client.get("/api/lists", auth=("alex", pw)).status_code == 403  # sync only: not the REST API
    assert client.request("PROPFIND", "/dav/", auth=("alex", pw), headers={"Depth": "0"}).status_code == 207


def test_today_is_where_the_client_is(client, family_id):
    """?tz= says whose today is meant: a task due on the day that has begun in Kiritimati (UTC+14) is on today there
    and not yet in Honolulu, and it is overdue in neither."""
    day = dt.datetime.now(ZoneInfo("Pacific/Kiritimati")).date().isoformat()
    r = client.post("/api/tasks", json={"title": "far east", "listId": family_id, "due": day})
    assert r.status_code == 201, r.text
    there = client.get("/api/tasks", params={"due": "today", "tz": "Pacific/Kiritimati"}).json()["items"]
    assert "far east" in [t["title"] for t in there]
    if dt.datetime.now(ZoneInfo("Pacific/Honolulu")).date().isoformat() != day:
        here = client.get("/api/tasks", params={"due": "today", "tz": "Pacific/Honolulu"}).json()["items"]
        assert "far east" not in [t["title"] for t in here]
    fam = next(c for c in client.get("/api/lists", params={"tz": "Pacific/Kiritimati"}).json()["items"] if c["id"] == family_id)
    assert fam["overdue"] == 0


def test_profile_for_all_apps_that_sync(client):
    """With another app that syncs in the suite, one profile sets up both, each account with an app password of its
    own app; this app's own profile stays, and with no other app there is no such choice."""
    import plistlib
    from iosuite_shared import suite
    assert [a["app"] for a in client.get("/api/apple-profile/suite").json()["apps"]] == ["iotask"]
    assert client.post("/api/apple-profile/suite/link", json={}).status_code == 409
    suite.register("iocontact", name="ioContact", url="https://other.example.com")
    assert sorted(a["app"] for a in client.get("/api/apple-profile/suite").json()["apps"]) == sorted(["iotask", "iocontact"])
    r = client.post("/api/apple-profile/suite/link", json={"label": "iPhone", "password": "new"}).json()
    assert r["url"].endswith("/iosuite-alex.mobileconfig")
    p = plistlib.loads(client.get(r["url"]).content)
    assert p["PayloadDisplayName"].startswith("ioSuite for ")
    own = next(x for x in p["PayloadContent"] if x.get("CalDAVAccountDescription") == "ioTask")
    other = next(x for x in p["PayloadContent"] if x is not own)
    assert other["CardDAVHostName"] == "other.example.com" and other["CardDAVPassword"].startswith("iocontact-")
    pw = own["CalDAVPassword"]
    assert pw.startswith("iotask-")
    client.cookies.clear()
    assert client.request("PROPFIND", "/dav/", auth=("alex", pw), headers={"Depth": "0"}).status_code == 207
    assert client.request("PROPFIND", "/dav/", auth=("alex", other["CardDAVPassword"]), headers={"Depth": "0"}).status_code == 401


def test_a_shared_list_never_takes_the_address_of_a_private_one(client):
    """CalDAV lists a person's own lists and the shared ones under one home: two with one address, and one hides the other."""
    from iosuite_shared import users
    from app import db, model
    ann = users.create("ann", "secret123", "member", "iotask")["id"]
    mine = model.create_list(ann, "Trips")
    shared = model.create_list(None, "Trips")
    again = model.create_list(ann, "Trips")
    slugs = {r["id"]: r["slug"] for r in db.q("SELECT id, slug FROM tsk_lists WHERE id IN (%s, %s, %s)", (mine, shared, again))}
    assert slugs[mine] == "trips" and len(set(slugs.values())) == 3, slugs
