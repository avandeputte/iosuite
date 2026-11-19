"""TRMNL screens (app/trmnl.py) and the start page's pushes to TRMNL's cloud (app/trmnlpush.py). The apps are stood in
for by their own providers over a table (conftest.via_providers); TRMNL is never called."""
import datetime as dt
import io
import json
import zipfile

import pytest

from iosuite_shared import apppasswords, credentials, outbound, users

from app import trmnl, trmnlpush, wall, widgets
from conftest import via_providers

TZ = "America/New_York"


@pytest.fixture()
def apps_answer(monkeypatch):
    table, asked, sent = {}, [], []
    monkeypatch.setattr(widgets, "fetch", via_providers(table, asked, sent))
    wall.forget()
    zone = dt.timezone(dt.timedelta(hours=-5))
    now = dt.datetime.now(dt.timezone.utc).astimezone(zone)
    soon = (now + dt.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    today = now.date()
    table[("iocalendar", "/api/calendars")] = {"items": [{"id": 1, "color": "#963522"}]}
    table[("iocalendar", "/api/occurrences")] = lambda p: {"items": [
        {"calendarId": 1, "title": "Dinner", "start": soon.isoformat(), "end": (soon + dt.timedelta(hours=2)).isoformat(), "allDay": False,
         "location": "Nan Xiang Dumpling, 38-12 Prince St, Flushing"}] if p["start"][:10] == today.isoformat() else [
        {"calendarId": 1, "title": "Dentist", "start": f"{(today + dt.timedelta(days=1)).isoformat()}T09:30:00-05:00",
         "end": f"{(today + dt.timedelta(days=1)).isoformat()}T10:30:00-05:00", "allDay": False, "location": ""}]}
    table[("iotask", "/api/lists")] = {"items": [{"id": 3, "color": "#2266aa"}]}
    due = [{"id": 41, "title": "Take out the bins", "due": today.isoformat(), "dueAllDay": True, "listId": 3},
           {"id": 42, "title": "Pay the water bill", "due": (today - dt.timedelta(days=2)).isoformat(), "dueAllDay": True, "listId": 3}]
    table[("iotask", "/api/tasks")] = lambda p: {"items": due if p.get("due") == "today" else [{"id": 42}] if p.get("due") == "overdue" else []}
    table[("iocontact", "/api/upcoming")] = {"items": [{"contactId": 5, "fn": "Ava", "label": "birthday", "turns": 9, "inDays": 1, "date": "x"}]}
    table[("iopix", "/api/random")] = {"id": [], "ts": []}
    table[("iodocs", "/api/documents")] = {"items": [
        {"id": 1, "title": "Morgan's passport", "kindLabel": "Passport", "expiresOn": (today - dt.timedelta(days=7)).isoformat(),
         "expiry": {"days": -7, "state": "expired"}, "people": []},
        {"id": 2, "title": "Car registration", "kindLabel": "Registration", "expiresOn": (today + dt.timedelta(days=12)).isoformat(),
         "expiry": {"days": 12, "state": "soon"}, "people": []}]}
    table[("iohealth", "/api/series")] = lambda p: {"points": [{"t": int(dt.datetime.combine(today - dt.timedelta(days=i), dt.time(12)).replace(tzinfo=dt.timezone.utc).timestamp()),
                                                                "v": 1000 * (i + 1)} for i in range(7)]}
    table[("iohealth", "/api/sleep")] = {"items": [{"date": today.isoformat(), "asleep": 431, "inBed": 470}]}
    table[("iohealth", "/api/activity")] = {"items": [{"move": 180, "moveGoal": 500, "exercise": 12, "exerciseGoal": 30, "stand": 3, "standGoal": 12}]}
    table[("iomoney", "/api/bills")] = {"currency": "USD", "items": [{"day": today.isoformat(), "merchant": "Con Edison", "amount": -142.17, "currency": "USD"},
                                                                     {"day": today.isoformat(), "merchant": "Netflix", "amount": -22.99, "currency": "USD", "paid": True}]}
    table[("iomoney", "/api/forecast")] = {"items": []}
    table[("iomoney", "/api/summary")] = {"monarch": {"stale": [{"name": "Checking", "institution": "Chase"}]}}
    return table, asked, sent


def test_wording():
    d = dt.datetime(2026, 11, 19, 18, 0)
    assert trmnl.clock(d, False) == "6 PM" and trmnl.clock(d.replace(minute=5), False) == "6:05 PM" and trmnl.clock(d, True) == "18:00"
    assert trmnl.clock(d.replace(hour=0), False) == "12 AM"
    assert trmnl.in_days(0) == "today" and trmnl.in_days(1) == "tomorrow" and trmnl.in_days(12) == "in 12 days" and trmnl.in_days(-7) == "7 days ago"
    assert trmnl.money(-2450, "USD") == "-$2,450.00" and trmnl.money(9.5, "CHF") == "9.50 CHF"
    assert trmnl.minutes(431) == "7 h 11 min" and trmnl.minutes(45) == "45 min"


def test_screens(client, apps_answer):
    today = client.get(f"/api/trmnl/today?tz={TZ}").json()
    assert today["screen"] == "today" and today["weekday"] and today["updated"]
    assert today["events"][0]["title"] == "Dinner" and today["events"][0]["place"] == "Nan Xiang Dumpling"
    assert today["events"][0]["time"].endswith(("AM", "PM"))
    assert today["tomorrow"] == [{"time": "9:30 AM", "title": "Dentist", "place": ""}]
    assert [t["title"] for t in today["tasks"]] == ["Take out the bins", "Pay the water bill"] and today["tasks"][1]["when"] == "Late"
    assert today["overdue"] == 1 and today["birthdays"] == ["Ava: turns 9 tomorrow"] and today["weather"] is None
    assert client.get(f"/api/trmnl/today?tz={TZ}&clock=24").json()["tomorrow"][0]["time"] == "09:30"
    cal = client.get(f"/api/trmnl/calendar?tz={TZ}").json()
    assert cal["days"][0]["label"] == "Today" and cal["days"][1]["label"] == "Tomorrow" and cal["days"][1]["events"][0]["title"] == "Dentist"
    tasks = client.get(f"/api/trmnl/tasks?tz={TZ}").json()
    assert len(tasks["tasks"]) == 2 and tasks["overdue"] == 1
    docs = client.get(f"/api/trmnl/docs?tz={TZ}").json()
    assert docs["items"][0] == {"title": "Morgan's passport", "kind": "Passport", "who": "", "when": "Expired 7 days ago",
                                "date": docs["items"][0]["date"], "expired": True}
    assert docs["items"][1]["when"] == "Expires in 12 days" and docs["expired"] == 1
    health = client.get(f"/api/trmnl/health?tz={TZ}").json()
    assert health["steps"] == "1,000" and health["sleep"] == "7 h 11 min" and len(health["week"]) == 7
    assert health["rings"][0] == {"name": "Move", "value": "180", "goal": "500", "unit": "kcal", "pct": 36}
    money = client.get(f"/api/trmnl/money?tz={TZ}").json()
    assert money["bills"] == [{"day": "Today", "name": "Con Edison", "amount": "$142.17"}] and money["behind"] == ["Chase"]
    for d in (today, cal, tasks, docs, health, money):
        assert len(json.dumps(d).encode()) <= trmnl.LIMIT
    assert client.get("/api/trmnl/nothing").status_code == 404


def test_screen_with_an_app_away(client, apps_answer):
    table, _, _ = apps_answer
    del table[("iodocs", "/api/documents")]
    d = client.get("/api/trmnl/docs").json()
    assert d["items"] == [] and d["missing"]


def test_trmnl_signs_in_with_an_app_password(client, apps_answer):
    pw = client.post("/api/auth/app-passwords", json={"label": "TRMNL"}).json()["password"]
    client.cookies.clear()
    assert client.get("/api/trmnl/tasks").status_code == 401
    r = client.get(f"/api/trmnl/tasks?tz={TZ}", headers={"Authorization": f"Bearer {pw}"})
    assert r.status_code == 200 and r.json()["tasks"][0]["title"] == "Take out the bins"


def test_fit_under_the_limit():
    d = {"screen": "tasks", "tasks": [{"title": "x" * 70, "when": ""} for _ in range(200)], "more": 0}
    out = trmnl.fit(d)
    assert len(json.dumps(out).encode()) <= trmnl.LIMIT and out["more"] == 200 - len(out["tasks"])


def test_plugin_zip(client):
    r = client.get("/api/trmnl/today/plugin.zip")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(z.namelist()) == ["full.liquid", "half_horizontal.liquid", "half_vertical.liquid", "quadrant.liquid", "settings.yml", "shared.liquid"]
    s = z.read("settings.yml").decode()
    assert "strategy: polling" in s and "/api/trmnl/today?tz={{ trmnl.user.time_zone_iana }}" in s and "Bearer {{ app_password }}" in s
    assert not __import__("re").search(r"iostart-[0-9a-f]{8}-", s)  # no password in the file
    for size in trmnl.SIZES:
        m = z.read(f"{size}.liquid").decode()
        assert 'class="layout' in m and 'class="title_bar"' in m and "view--" not in m
    push = zipfile.ZipFile(io.BytesIO(client.get("/api/trmnl/money/plugin.zip?mode=push").content)).read("settings.yml").decode()
    assert "strategy: webhook" in push and "polling_url" not in push
    assert client.get("/api/trmnl/nothing/plugin.zip").status_code == 404


def test_markup_renders():
    """Every size of every screen, filled with sample data, is valid Liquid (python-liquid, as close to TRMNL's as there is)."""
    liquid = pytest.importorskip("liquid")
    env = liquid.Environment()
    sample = {"weekday": "Thursday", "date": "November 19", "date_short": "Thu, Nov 19", "updated": "8:05 AM", "weather": None, "has_calendar": True,
              "has_tasks": True, "events": [{"time": "6 PM", "title": "Dinner", "place": "Nan Xiang"}], "events_more": 0, "next": "", "tomorrow": [],
              "tasks": [{"title": "Bins", "when": "Late", "late": True}], "tasks_more": 0, "overdue": 1, "birthdays": [], "days": [], "more": 0,
              "items": [], "expired": 0, "steps": "1,000", "rings": [], "sleep": "", "in_bed": "", "week": [], "average": "", "bills": [],
              "total": "", "low": [], "behind": []}
    for screen in trmnl.SCREENS:
        m = trmnl.markup(screen)
        for size in trmnl.SIZES:
            html = env.parse(m["shared"] + m[size]).render(sample)
            assert 'class="title_bar"' in html and "{{" not in html and "{%" not in html, (screen, size)


@pytest.fixture()
def trmnl_cloud(monkeypatch):
    posted = []
    monkeypatch.setattr(outbound, "check", lambda url, allowed=None: "203.0.113.5")
    monkeypatch.setattr(trmnlpush, "_post", lambda url, data, user: posted.append((url, data)))
    return posted


HOOK = "https://trmnl.com/api/custom_plugins/0a1b2c3d-0000-4000-8000-123456789abc"


def test_push(client, apps_answer, trmnl_cloud):
    posted = trmnl_cloud
    alex = users.find("alex")
    s = client.get("/api/trmnl").json()
    assert {x["key"] for x in s["screens"]} == set(trmnl.SCREENS) and not any(x["push"] for x in s["screens"]) and not s["passwordSet"]
    s = client.put("/api/trmnl", json={"tz": TZ, "clock": 24, "hooks": {"tasks": HOOK}}).json()
    assert s["passwordSet"] and s["clock"] == 24 and [x["key"] for x in s["screens"] if x["push"]] == ["tasks"]
    assert HOOK not in json.dumps(s)  # the address is not handed back
    assert credentials.get("iostart", f"trmnl_{alex['id']}_tasks") == HOOK
    assert [p["label"] for p in apppasswords.list_for(alex["id"], "iostart")] == ["TRMNL"]
    keys = {k["name"]: k for k in credentials.listing("iostart")}
    assert keys[f"trmnl_{alex['id']}_tasks"]["label"] == "TRMNL webhook: Tasks (alex)" and keys[f"trmnl_{alex['id']}_pw"]["set"]
    # the loop makes it and sends it, read as alex with the app password, through the apps
    trmnlpush.tick()
    assert len(posted) == 1 and posted[0][0] == HOOK and posted[0][1]["tasks"][0]["title"] == "Take out the bins"
    # not due again for 15 minutes; and unchanged, not sent again until RESEND
    trmnlpush.tick()
    assert len(posted) == 1
    trmnlpush.push(alex["id"], now=__import__("time").time() + 16 * 60)
    assert len(posted) == 1
    assert client.post("/api/trmnl/tasks/send").json()["ok"] is True and len(posted) == 2  # Send now: always
    assert client.post("/api/trmnl/docs/send").status_code == 400  # not pushed
    st = next(x for x in client.get("/api/trmnl").json()["screens"] if x["key"] == "tasks")
    assert st["push"] and st["sent"]["ok"] and st["sent"]["at"]
    # the app password revoked in Settings › Account: pushing stops and says why
    pid = apppasswords.list_for(alex["id"], "iostart")[0]["id"]
    client.delete(f"/api/auth/app-passwords/{pid}")
    apppasswords.forget()
    r = client.post("/api/trmnl/tasks/send").json()
    assert r["ok"] is False and "revoked" in r["error"] and len(posted) == 2
    # the last screen stopped: its key and the app password's go
    client.put("/api/trmnl", json={"hooks": {"tasks": ""}})
    assert not credentials.get("iostart", f"trmnl_{alex['id']}_tasks") and not credentials.get("iostart", f"trmnl_{alex['id']}_pw")


def test_push_stop_revokes_its_app_password(client, trmnl_cloud):
    alex = users.find("alex")
    client.put("/api/trmnl", json={"hooks": {"tasks": HOOK, "docs": HOOK}})
    assert len(apppasswords.list_for(alex["id"], "iostart")) == 1
    client.put("/api/trmnl", json={"hooks": {"tasks": ""}})
    assert len(apppasswords.list_for(alex["id"], "iostart")) == 1  # docs still pushed
    client.put("/api/trmnl", json={"hooks": {"docs": ""}})
    assert apppasswords.list_for(alex["id"], "iostart") == []


def test_push_addresses(client, monkeypatch):
    from iosuite_shared import testing
    assert client.put("/api/trmnl", json={"hooks": {"tasks": "http://127.0.0.1:8630/x"}}).status_code == 400  # never this machine
    assert client.put("/api/trmnl", json={"hooks": {"nothing": HOOK}}).status_code == 400
    testing.add_account(client, {"name": "kid", "password": "secret123", "role": "viewer"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "kid", "password": "secret123"})
    monkeypatch.setattr(outbound, "check", lambda url, allowed=None: "203.0.113.5")
    assert client.put("/api/trmnl", json={"hooks": {"tasks": "http://trmnl.example.com/x"}}).status_code == 400  # https only, but for admins
    assert client.put("/api/trmnl", json={"hooks": {"tasks": HOOK}}).status_code == 200


def test_deleting_a_person_takes_their_trmnl(client, trmnl_cloud):
    from app import persondata
    alex = users.find("alex")
    client.put("/api/trmnl", json={"hooks": {"tasks": HOOK}})
    got = {x["what"]: x["count"] for x in persondata.of(alex["id"], False)}
    assert got["TRMNL screens pushed"] == 1
    persondata.of(alex["id"], True)
    assert not credentials.get("iostart", f"trmnl_{alex['id']}_tasks") and apppasswords.list_for(alex["id"], "iostart") == []
