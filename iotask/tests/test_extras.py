"""Beyond the basics: smart quick add through the API, postponing, repeating after completion, the order by hand,
the activity log with undo, templates, and tasks by a range of due dates."""
import datetime as dt
from zoneinfo import ZoneInfo

from tests.test_api import new
from tests.test_caldav import TODO

NY = ZoneInfo("America/New_York")


def today():
    return dt.datetime.now(NY).date()


def test_quick_add_reads_the_line(client, family_id):
    lists = client.get("/api/lists").json()["items"]
    personal = next(c["id"] for c in lists if not c["shared"])
    p = client.get("/api/quick", params={"text": "Call the bank tomorrow 5pm !high #pers", "tz": "America/New_York"}).json()
    tomorrow = (today() + dt.timedelta(days=1)).isoformat()
    assert p == {"title": "Call the bank", "due": f"{tomorrow}T17:00", "priority": "high", "listId": personal}
    # the line wins over what came with it (the open list, "due today" of the Today view); the rest is kept
    t = new(client, text="Call the bank tomorrow 5pm !high #pers", listId=family_id, due=today().isoformat(), timezone="America/New_York", notes="n")
    assert (t["title"], t["listId"], t["priority"], t["notes"]) == ("Call the bank", personal, "high", "n")
    assert t["due"].startswith(f"{tomorrow}T17:00:00-0") and t["undo"]
    # a line without any of it is a plain task where it was typed
    t = new(client, text="Read 1984", listId=family_id, due=today().isoformat())
    assert (t["title"], t["listId"], t["due"]) == ("Read 1984", family_id, today().isoformat())
    t = new(client, text="Water the plants every 3 days after done", listId=family_id, timezone="America/New_York")
    assert t["repeatAfter"] == "P3D" and t["rrule"] is None and t["due"] == today().isoformat()


def test_postpone_keeps_the_time_and_moves_the_alert(client, family_id):
    a = new(client, title="Timed", due="2026-11-10T17:00", timezone="Europe/Brussels", alarms=["2026-11-10T16:30+01:00"], listId=family_id)
    b = new(client, title="All day", due="2026-11-09", listId=family_id)
    r = client.post("/api/tasks/postpone", json={"ids": [a["id"], b["id"]], "due": "2026-11-14"}).json()
    assert r["moved"] == 2
    a2, b2 = client.get(f"/api/tasks/{a['id']}").json(), client.get(f"/api/tasks/{b['id']}").json()
    assert a2["due"] == "2026-11-14T17:00:00+01:00" and a2["alarms"] == ["2026-11-14T15:30:00+00:00"] and b2["due"] == "2026-11-14"
    # a new due date in the form moves the alert too, unless the form sets the alerts itself
    a3 = client.patch(f"/api/tasks/{a['id']}", json={"due": "2026-11-16T09:00", "timezone": "Europe/Brussels"}).json()
    assert a3["alarms"] == ["2026-11-16T07:30:00+00:00"]
    # one step back: both are due when they were
    assert client.post(f"/api/undo/{a3['undo']}").status_code == 200
    assert client.post(f"/api/undo/{r['undo']}").json()["undone"] == 2
    assert client.get(f"/api/tasks/{a['id']}").json()["due"] == "2026-11-10T17:00:00+01:00"
    assert client.get(f"/api/tasks/{b['id']}").json()["due"] == "2026-11-09"
    assert client.post("/api/tasks/postpone", json={"ids": [a["id"]], "due": "soon"}).status_code == 400


def test_repeat_after_completion(client, family_id):
    t = new(client, title="Water the plants", due="2026-11-01T09:00", timezone="America/New_York", repeatAfter="P2W", listId=family_id)
    assert t["repeatAfter"] == "P2W" and t["rrule"] is None
    assert "X-IOTASKS-AFTER-DONE:P2W" in client.get(f"/api/tasks/{t['id']}?format=ics").text
    r = client.post(f"/api/tasks/{t['id']}/complete", json={"tz": "America/New_York"}).json()
    again = today() + dt.timedelta(days=14)  # two weeks after today, not after the old due date; at its usual time
    assert r["moved"] and not r["done"] and r["due"].startswith(f"{again.isoformat()}T09:00:00-0")
    # one way of repeating at a time
    r = client.patch(f"/api/tasks/{t['id']}", json={"rrule": "FREQ=DAILY"}).json()
    assert r["rrule"] == "FREQ=DAILY" and r["repeatAfter"] is None
    r = client.patch(f"/api/tasks/{t['id']}", json={"repeatAfter": "P1M"}).json()
    assert r["rrule"] is None and r["repeatAfter"] == "P1M"
    assert client.patch(f"/api/tasks/{t['id']}", json={"repeatAfter": "PT2H"}).status_code == 400
    # without a due date it gets one when it is ticked off
    n = new(client, title="Descale the kettle", repeatAfter="P3M", listId=family_id)
    r = client.post(f"/api/tasks/{n['id']}/complete", json={"tz": "America/New_York"}).json()
    assert r["moved"] and r["dueAllDay"] and r["due"] > today().isoformat()


def test_a_reminders_app_ticks_off_a_task_that_repeats_after_completion(client, family_id, dav):  # noqa: F811
    client.post("/api/auth/login", json={"name": "alex", "password": "secret123"})
    t = new(client, title="Change the filter", due="2026-11-01", repeatAfter="P1M", listId=family_id)
    client.cookies.clear()
    href = f"/dav/calendars/alex/family/{t['href']}"
    # the phone ticks it off and, as an app that does not know the property, leaves the rule out
    r = dav("PUT", href, TODO.format(uid=t["uid"], title="Change the filter", extra="DUE;VALUE=DATE:20261101\r\nSTATUS:COMPLETED\r\nCOMPLETED:20261111T080000Z\r\n"))
    assert r.status_code == 204 and "ETag" not in r.headers  # the server changed it: the app fetches it again
    got = dav("GET", href).text
    assert "X-IOTASKS-AFTER-DONE:P1M" in got and "STATUS:NEEDS-ACTION" in got and "DUE;VALUE=DATE:20261101" not in got
    # an edit from the phone that leaves the task open keeps the rule too
    r = dav("PUT", href, TODO.format(uid=t["uid"], title="Change the water filter", extra="DUE;VALUE=DATE:20261220\r\n"))
    assert "X-IOTASKS-AFTER-DONE:P1M" in dav("GET", href).text and "DUE;VALUE=DATE:20261220" in dav("GET", href).text


def test_order_by_hand(client, family_id):
    ids = [new(client, title=x, listId=family_id)["id"] for x in "abcd"]
    titles = lambda: [t["title"] for t in client.get(f"/api/tasks?list={family_id}&sort=manual").json()["items"]]  # noqa: E731
    assert titles() == ["a", "b", "c", "d"]  # as they were added
    # one task moves: only that one is written
    r = client.post(f"/api/lists/{family_id}/order", json={"ids": [ids[3], ids[0], ids[1], ids[2]]}).json()
    assert r["changed"] == 1 and titles() == ["d", "a", "b", "c"]
    assert "X-APPLE-SORT-ORDER:" in client.get(f"/api/tasks/{ids[3]}?format=ics").text
    # again and again between the same two: when no number is left between them, all are numbered anew
    for _ in range(12):
        client.post(f"/api/lists/{family_id}/order", json={"ids": [ids[3], ids[2], ids[0], ids[1]]})
        client.post(f"/api/lists/{family_id}/order", json={"ids": [ids[3], ids[1], ids[2], ids[0]]})
    assert titles() == ["d", "b", "c", "a"]
    assert client.post(f"/api/lists/{family_id}/order", json={"ids": [ids[3], ids[1], ids[2], ids[0]]}).json()["changed"] == 0
    # by due date stays the default (the order by hand then only decides between tasks due alike); putting tasks in
    # order is not in the activity log
    client.patch(f"/api/tasks/{ids[0]}", json={"due": "2026-11-12"})
    assert [t["title"] for t in client.get(f"/api/tasks?list={family_id}").json()["items"]] == ["a", "d", "b", "c"]
    assert {a["action"] for a in client.get("/api/activity").json()["items"]} == {"added", "changed"}


def test_lists_in_the_order_you_put_them(client, family_id):
    a = client.post("/api/lists", json={"name": "Work"}).json()["list"]["id"]
    b = client.post("/api/lists", json={"name": "Garden"}).json()["list"]["id"]
    names = lambda: [c["name"] for c in client.get("/api/lists").json()["items"]]  # noqa: E731
    assert names() == ["Family", "Personal", "Work", "Garden"]  # a new list comes last
    personal = next(c["id"] for c in client.get("/api/lists").json()["items"] if c["name"] == "Personal")
    r = client.post("/api/lists/order", json={"ids": [b, personal, a]})
    assert [c["name"] for c in r.json()["items"]] == ["Family", "Garden", "Personal", "Work"] == names()


def test_activity_and_undo(client, family_id):
    t = new(client, title="Book the dentist", listId=family_id)
    sub = new(client, title="Find the number", parent=t["id"])
    client.patch(f"/api/tasks/{t['id']}", json={"title": "Book the dentist for Emma", "due": "2026-11-20"})
    done = client.post(f"/api/tasks/{t['id']}/complete", json={}).json()
    log = client.get("/api/activity").json()["items"]
    assert [(a["action"], a["title"], a["detail"], a["user"]) for a in log] == [
        ("done", "Book the dentist for Emma", None, "alex"), ("changed", "Book the dentist for Emma", "title, due", "alex"),
        ("added", "Find the number", None, "alex"), ("added", "Book the dentist", None, "alex")]
    assert [a["canUndo"] for a in log] == [True, False, True, False]  # only the latest step of a task can go back
    # undo the tick: open again; then the undoing is the latest step, and undoing that ticks it off again
    r = client.post(f"/api/undo/{done['undo']}").json()
    assert not client.get(f"/api/tasks/{t['id']}").json()["done"]
    assert client.post(f"/api/undo/{done['undo']}").status_code == 400  # once
    assert client.post(f"/api/undo/{r['undo']}").status_code == 200 and client.get(f"/api/tasks/{t['id']}").json()["done"]
    # deleting a task takes its subtask along, as one step; undo brings both back as they were
    d = client.delete(f"/api/tasks/{t['id']}").json()
    assert d["deleted"] == 2 and client.get(f"/api/tasks/{sub['id']}").status_code == 404
    first = client.get("/api/activity").json()["items"][0]
    assert (first["action"], first["count"], first["batch"]) == ("deleted", 2, d["undo"])
    assert client.post(f"/api/undo/{d['undo']}").json()["undone"] == 2
    back = client.get(f"/api/tasks/{t['id']}").json()
    assert back["title"] == "Book the dentist for Emma" and back["done"] and [c["title"] for c in back["children"]] == ["Find the number"]
    # a step cannot go back once the task was changed again
    e = client.patch(f"/api/tasks/{sub['id']}", json={"title": "Find the phone number"}).json()
    client.patch(f"/api/tasks/{sub['id']}", json={"priority": "high"})
    assert client.post(f"/api/undo/{e['undo']}").status_code == 400
    assert client.post("/api/undo/nope").status_code == 404
    # clear completed, undone
    c = client.post(f"/api/lists/{family_id}/clear-completed").json()
    assert c["deleted"] == 1 and client.post(f"/api/undo/{c['undo']}").json()["undone"] == 1
    assert client.get(f"/api/tasks/{t['id']}").json()["done"]
    # a list's own log; a move to another list is in both
    personal = next(c["id"] for c in client.get("/api/lists").json()["items"] if not c["shared"])
    m = client.patch(f"/api/tasks/{sub['id']}", json={"parent": None, "listId": personal}).json()
    assert [(a["action"], a["detail"]) for a in client.get(f"/api/activity?list={personal}").json()["items"]][-1] == ("added", "from Family")
    assert client.get(f"/api/activity?list={family_id}&limit=1").json()["items"][0]["action"] == "moved"
    assert m["listId"] == personal


def test_the_log_says_what_a_reminders_app_did(client, family_id, dav):  # noqa: F811
    base = "/dav/calendars/alex/family/"
    dav("PUT", base + "T9.ics", TODO.format(uid="T9", title="From the phone", extra=""))
    dav("DELETE", base + "T9.ics")
    client.post("/api/auth/login", json={"name": "alex", "password": "secret123"})
    log = client.get("/api/activity").json()["items"]
    assert [(a["action"], a["via"]) for a in log] == [("deleted", "caldav"), ("added", "caldav")]
    assert client.post(f"/api/undo/{log[0]['batch']}").status_code == 200  # back, for the phone too
    client.cookies.clear()
    assert "From the phone" in dav("GET", base + "T9.ics").text


def test_viewers_see_the_log_but_do_not_undo(client, family_id):
    t = new(client, title="Shared thing", listId=family_id)
    client.post("/api/users", json={"name": "kid", "password": "kidpass123", "role": "viewer"})
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": "kid", "password": "kidpass123"}).status_code == 200
    log = client.get("/api/activity").json()["items"]
    assert log[0]["title"] == "Shared thing" and not log[0]["canUndo"]
    assert client.post(f"/api/undo/{t['undo']}").status_code == 403


def test_templates(client, family_id):
    trip = client.post("/api/lists", json={"name": "Trip", "shared": True}).json()["list"]["id"]
    bag = new(client, title="Pack the bag", notes="The blue one", priority="high", due="2026-11-20", listId=trip)
    new(client, title="Socks", parent=bag["id"])
    done = new(client, title="Passports", listId=trip)
    client.post(f"/api/tasks/{done['id']}/complete", json={})
    r = client.post("/api/templates", json={"name": "Packing", "listId": trip, "shared": True})
    assert r.status_code == 201 and r.json()["template"]["count"] == 3 and r.json()["template"]["shared"]
    tid = r.json()["template"]["id"]
    items = client.get(f"/api/templates/{tid}").json()["items"]
    assert items == [{"title": "Pack the bag", "notes": "The blue one", "priority": "high", "children": [{"title": "Socks"}]}, {"title": "Passports"}]
    # stamped out on another list: all open, no due dates unless one is given
    r = client.post(f"/api/templates/{tid}/apply", json={"listId": family_id, "due": "2026-12-01"}).json()
    assert r["created"] == 3
    got = client.get(f"/api/tasks?list={family_id}&sort=manual").json()["items"]
    assert [(t["title"], t["done"], t["due"]) for t in got] == [("Pack the bag", False, "2026-12-01"), ("Socks", False, None), ("Passports", False, "2026-12-01")]
    assert got[1]["parent"] == got[0]["uid"] and got[0]["notes"] == "The blue one" and got[0]["priority"] == "high"
    assert client.post(f"/api/undo/{r['undo']}").json()["undone"] == 3 and not client.get(f"/api/tasks?list={family_id}").json()["items"]
    assert client.patch(f"/api/templates/{tid}", json={"name": "Holiday packing"}).json()["template"]["name"] == "Holiday packing"
    assert [t["name"] for t in client.get("/api/templates").json()["items"]] == ["Holiday packing"]
    assert client.post("/api/templates", json={"name": "Empty", "listId": family_id}).status_code == 400
    assert client.delete(f"/api/templates/{tid}").json()["ok"] and client.get(f"/api/templates/{tid}").status_code == 404


def test_tasks_between_two_days(client, family_id):
    for title, due in (("a", "2026-11-09"), ("b", "2026-11-10T23:30"), ("c", "2026-11-11"), ("d", "2026-11-12T00:15"), ("e", None)):
        new(client, title=title, listId=family_id, **({"due": due, "timezone": "America/New_York"} if due else {}))
    got = client.get("/api/tasks", params={"from": "2026-11-10", "to": "2026-11-11", "tz": "America/New_York"}).json()["items"]
    assert sorted(t["title"] for t in got) == ["b", "c"]
    assert client.get("/api/tasks?from=nope").status_code == 400
