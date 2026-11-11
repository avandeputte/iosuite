"""Tasks from ioTasks on the calendar: asked for as the viewer, shown on the day they are due, ticked off from here."""
import io
import json
import urllib.error

import pytest
from iosuite_shared import sessions, suite

from app import tasks

LISTS = {"items": [{"id": 1, "name": "Family", "color": "#146b5e", "writable": True},
                   {"id": 2, "name": "School", "color": "#1a73e8", "writable": False}]}
TASKS = {"items": [
    {"id": 7, "title": "Bins out", "due": "2026-11-12", "dueAllDay": True, "done": False, "listId": 1, "priority": None,
     "members": [{"id": 1, "name": "alex", "displayName": "alex"}], "rrule": "FREQ=WEEKLY", "repeatAfter": None},
    {"id": 8, "title": "Hand in the form", "due": "2026-11-11T09:30:00-05:00", "dueAllDay": False, "done": True, "listId": 2,
     "priority": "high", "members": [], "rrule": None, "repeatAfter": None},
    {"id": 9, "title": "Some day", "due": None, "dueAllDay": False, "done": False, "listId": 1, "members": []},
    {"id": 10, "title": "Long ago", "due": "2026-01-02", "dueAllDay": True, "done": False, "listId": 1, "members": []}]}


@pytest.fixture()
def iotasks(client, monkeypatch):
    """ioTasks in the suite's list of apps, answering from here: the requests it got, and what it answers per path."""
    tasks.forget()
    suite.register("iotasks", name="ioTasks", url="https://tasks.example.org", version="1")
    seen, answers = [], {"/api/lists": LISTS, "/api/tasks": TASKS}

    def fake(req, timeout):
        path = req.full_url.split("example.org", 1)[1]
        seen.append({"method": req.get_method(), "path": path, "headers": {k.lower(): v for k, v in req.header_items()},
                     "body": json.loads(req.data) if req.data else None})
        got = answers[path.split("?")[0]]
        if isinstance(got, Exception):
            raise got
        return got
    monkeypatch.setattr(tasks, "_open", fake)
    yield seen, answers
    tasks.forget()


def refusal(code: int, detail: str):
    return urllib.error.HTTPError("https://tasks.example.org", code, "no", {}, io.BytesIO(json.dumps({"detail": detail}).encode()))


def test_without_iotasks_the_calendar_has_no_tasks(client):
    tasks.forget()
    assert client.get("/api/status").json()["iotasks"] is False
    r = client.get("/api/tasks?start=2026-11-09&end=2026-11-16").json()
    assert r["available"] is False and r["items"] == [] and "not part of the suite" in r["reason"]
    assert client.post("/api/tasks/7/complete", json={}).status_code == 404


def test_due_tasks_are_asked_for_as_the_viewer(client, iotasks):
    seen, _ = iotasks
    assert client.get("/api/status").json()["iotasks"] is True
    r = client.get("/api/tasks?start=2026-11-09&end=2026-11-16&tz=Europe/Brussels").json()
    assert r["available"] is True and r["url"] == "https://tasks.example.org"
    assert [t["id"] for t in r["items"]] == [8, 7]  # by day; the one without a due date and the one outside these days are left out
    form, bins = r["items"]
    assert bins == {"id": 7, "title": "Bins out", "due": "2026-11-12", "allDay": True, "done": False, "listId": 1, "list": "Family",
                    "color": "#146b5e", "writable": True, "priority": None, "members": [1], "repeats": True}
    assert form["done"] is True and form["allDay"] is False and form["writable"] is False and form["list"] == "School"
    asked = [s for s in seen if s["path"].startswith("/api/tasks?")][0]
    assert "from=2026-11-09" in asked["path"] and "to=2026-11-15" in asked["path"] and "status=all" in asked["path"]
    assert "tz=Europe%2FBrussels" in asked["path"]
    # the viewer's own session goes along, nothing of ioCalendar's
    assert all(s["headers"]["cookie"].startswith(sessions.COOKIE + "=") and "authorization" not in s["headers"] for s in seen)
    assert client.get("/api/tasks?start=2026-11-16&end=2026-11-09").status_code == 400
    assert client.get("/api/tasks?start=soon&end=2026-11-09").status_code == 400


def test_an_app_password_goes_along_as_it_came(client, iotasks):
    seen, _ = iotasks
    pw = client.post("/api/auth/app-passwords", json={"label": "script"}).json()["password"]
    client.cookies.clear()
    assert client.get("/api/tasks?start=2026-11-09&end=2026-11-16", auth=("alex", pw)).json()["available"] is True
    assert seen[0]["headers"]["authorization"].startswith("Basic ") and "cookie" not in seen[0]["headers"]


def test_ticking_a_task_off_from_the_calendar(client, iotasks):
    seen, answers = iotasks
    answers["/api/tasks/7/complete"] = {"id": 7, "title": "Bins out", "done": False, "due": "2026-11-19", "dueAllDay": True, "moved": True}
    r = client.post("/api/tasks/7/complete", json={"done": True, "tz": "America/New_York"})
    assert r.status_code == 200 and r.json() == {"id": 7, "title": "Bins out", "done": False, "due": "2026-11-19", "allDay": True, "moved": True}
    assert seen[-1]["method"] == "POST" and seen[-1]["body"] == {"done": True, "tz": "America/New_York"}
    answers["/api/tasks/8/complete"] = refusal(403, "You can see this task but not change it")
    r = client.post("/api/tasks/8/complete", json={"done": False})
    assert r.status_code == 403 and r.json()["detail"] == "You can see this task but not change it"
    assert seen[-1]["body"] == {"done": False}


def test_an_iotasks_that_refuses_or_is_away(client, iotasks):
    seen, answers = iotasks
    answers["/api/lists"] = refusal(401, "Sign in first")
    r = client.get("/api/tasks?start=2026-11-09&end=2026-11-16").json()
    assert r["available"] is False and r["items"] == [] and "does not let this account in" in r["reason"]
    answers["/api/lists"] = urllib.error.URLError("refused")
    n = len(seen)
    r = client.get("/api/tasks?start=2026-11-09&end=2026-11-16").json()
    assert r["available"] is False and "not reachable" in r["reason"] and len(seen) > n
    # left alone for a moment: the calendar draws without waiting for it again
    n = len(seen)
    assert client.get("/api/tasks?start=2026-11-09&end=2026-11-16").json()["available"] is False and len(seen) == n
    assert client.post("/api/tasks/7/complete", json={}).status_code == 502
