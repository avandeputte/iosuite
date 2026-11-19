"""TRMNL screens (app/trmnl.py) and the start page's pushes to TRMNL's cloud (app/trmnlpush.py). The apps are stood in
for by their own providers over a table (conftest.apps_answer); TRMNL is never called."""
import base64
import datetime as dt
import io
import json
import re
import zipfile

import pytest

from iosuite_shared import apppasswords, credentials, outbound, users

from app import trmnl, trmnlpush, weather

TZ = "America/New_York"


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


def test_weather_screen(client, apps_answer, monkeypatch):
    """The start page's own weather as a screen: listed once the weather is set up, and until then it says where to."""
    from tests.test_widgets import _fake_accuweather
    off = client.get(f"/api/trmnl/weather?tz={TZ}").json()
    assert off["screen"] == "weather" and "Settings › Weather" in off["missing"] and off["hours"] == [] and off["days"] == []
    assert "weather" not in {x["key"] for x in client.get("/api/trmnl").json()["screens"]}
    fake = _fake_accuweather([])
    today = dt.datetime.now(dt.timezone.utc).astimezone(__import__("zoneinfo").ZoneInfo(TZ)).replace(minute=0, second=0, microsecond=0)

    def get(path, **params):  # the same answers, dated today so that they are still ahead
        a = fake(path, **params)
        if "daily" in path:
            a["DailyForecasts"] = [{**a["DailyForecasts"][0], "Date": (today + dt.timedelta(days=i)).isoformat(),
                                    "Day": {"Icon": 12 if i else 2, "IconPhrase": "Showers" if i else "Mostly sunny", "PrecipitationProbability": 60 if i else 5}} for i in range(5)]
        if "hourly" in path:
            a = [{**a[0], "DateTime": (today + dt.timedelta(hours=i + 1)).isoformat()} for i in range(12)]
        return a
    monkeypatch.setattr(weather, "_get", get)
    client.post("/api/weather/settings", json={"key": "abc", "units": "imperial", "locationKey": "349727", "locationName": "New York, United States"})
    assert "weather" in {x["key"] for x in client.get("/api/trmnl").json()["screens"]}
    w = client.get(f"/api/trmnl/weather?tz={TZ}").json()
    assert "missing" not in w and w["place"] == "New York" and w["temp"] == "68°" and w["text"] == "Sunny" and w["feels"] == "70°"
    assert w["icon"] == trmnl.WX.index("sun") and w["wind"] == "6 mph" and w["humidity"] == "40%" and w["uv"] == "3"
    assert w["hi"] == "64°" and w["lo"] == "50°" and w["rain"] == "" and w["note"].startswith("Rain ")
    assert len(w["hours"]) == 8 and w["hours"][0]["icon"] == trmnl.WX.index("rain") and w["hours"][0]["rain"] == "70%" and w["hours"][0]["time"].endswith(("AM", "PM"))
    assert [d["day"] for d in w["days"]][0] == "Today" and len(w["days"]) == 5 and w["days"][0]["rain"] == "" and w["days"][1] | {"day": ""} == {
        "day": "", "icon": trmnl.WX.index("rain"), "text": "Showers", "hi": "64°", "lo": "50°", "rain": "60%"}
    assert len(json.dumps(trmnl.fit(w)).encode()) <= trmnl.LIMIT
    z = zipfile.ZipFile(io.BytesIO(client.get("/api/trmnl/weather/plugin.zip").content))
    assert "base64_encode" in z.read("full.liquid").decode() and "capture wx_all" in z.read("shared.liquid").decode()


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
    assert not re.search(r"iostart-[0-9a-f]{8}-", s)  # no password in the file
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
    forecast = {"place": "New York", "temp": "68°", "text": "Sunny", "icon": 0, "feels": "70°", "hi": "72°", "lo": "55°", "rain": "", "note": "Rain from 3 PM",
                "wind": "6 mph", "humidity": "40%", "uv": "3", "hours": [{"time": "3 PM", "icon": 5, "temp": "66°", "rain": "70%"}],
                "days": [{"day": "Today", "icon": 3, "text": "Mostly sunny", "hi": "72°", "lo": "55°", "rain": ""}]}
    for screen in trmnl.SCREENS:
        m = trmnl.markup(screen)
        for size in trmnl.SIZES:
            html = env.parse(m["shared"] + m[size]).render(sample | forecast if screen == "weather" else sample)
            assert 'class="title_bar"' in html and "{{" not in html and "{%" not in html, (screen, size)
            if screen == "weather":  # each glyph is a whole picture of its own, written out by Liquid
                pics = re.findall(r'src="data:image/svg\+xml;base64,([^"]+)"', html)
                assert pics and all(base64.b64decode(x).startswith(b"<svg ") and base64.b64decode(x).endswith(b"</svg>") for x in pics), size


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
    assert {x["key"] for x in s["screens"]} == set(trmnl.SCREENS) - {"weather"} and not any(x["push"] for x in s["screens"]) and not s["passwordSet"]
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
