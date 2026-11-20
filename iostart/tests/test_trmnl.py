"""TRMNL screens (app/trmnl.py) and the start page's pushes to TRMNL's cloud (app/trmnlpush.py). The apps are stood in
for by their own providers over a table (conftest.apps_answer); TRMNL is never called."""
import base64
import datetime as dt
import io
import json
import re
import zipfile
from zoneinfo import ZoneInfo

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
    assert [trmnl.short(v) for v in (85.4, -701, 1000, 1234, 2450, 9960, 12000)] == ["85", "701", "1k", "1.2k", "2.5k", "10k", "12k"]
    # a calendar's or a list's colour as the ink of a colour screen nearest it; grays have none
    assert [trmnl.ink(c) for c in ("#e53935", "#fb8c00", "#fdd835", "#7cb342", "#00897b", "#1e88e5", "#8e24aa", "#d81b60")] == [
        "red", "red", "yellow", "green", "blue", "blue", "blue", "red"]
    assert [trmnl.ink(c) for c in ("#9e9e9e", "#000000", "#ffffff", None, "", "red", "#12")] == [""] * 7


def test_screens(client, apps_answer):
    today = client.get(f"/api/trmnl/today?tz={TZ}").json()
    assert today["screen"] == "today" and today["weekday"] and today["updated"]
    first, ahead = today["list"][0], today["list"][1:]
    assert first["label"] == "Today \u00b7 1 late" and first["more"] == 0
    # the order of the start page's Today card: what is late, then what has an hour, then the tasks without one
    assert [(r["title"], r["when"]) for r in first["rows"]][0] == ("Pay the water bill", "Late") and first["rows"][0]["late"]
    assert first["rows"][1]["title"] == "Dinner" and first["rows"][1]["when"].endswith(("AM", "PM")) and first["rows"][1]["note"] == "@ Nan Xiang Dumpling"
    assert first["rows"][2] == {"title": "Take out the bins", "when": "To do", "note": "", "late": False, "ink": "blue"}
    # the coming days, each under its name: ioContact's birthday first, the events, ioTask's coming week on its day
    assert ahead[0]["label"].startswith("Tomorrow \u00b7 ")
    assert [(r["title"], r["when"], r["note"]) for r in ahead[0]["rows"]] == [("Ava", "Birthday", "\u00b7 turns 9"), ("Dentist", "9:30 AM", "")]
    assert ("Book flights", "To do") in [(r["title"], r["when"]) for g in ahead for r in g["rows"]]
    assert today["none"] == "Nothing planned or due today" and today["weather"] is None
    assert client.get(f"/api/trmnl/today?tz={TZ}&clock=24").json()["list"][1]["rows"][1]["when"] == "09:30"
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
    # the graph: the week from today, what falls due each day against the heaviest day
    assert len(money["days"]) == 7 and money["days"][0] == {"day": dt.datetime.now(ZoneInfo(TZ)).strftime("%a"), "amount": "142", "pct": 100}
    assert all(d == {"day": d["day"], "amount": "", "pct": 0} for d in money["days"][1:])
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
            a = [{**a[0], "DateTime": (today + dt.timedelta(hours=i + 1)).isoformat(), "Temperature": {"Value": 14.0 - i}} for i in range(12)]
        return a
    monkeypatch.setattr(weather, "_get", get)
    client.post("/api/weather/settings", json={"key": "abc", "units": "imperial", "locationKey": "349727", "locationName": "New York, United States"})
    assert "weather" in {x["key"] for x in client.get("/api/trmnl").json()["screens"]}
    w = client.get(f"/api/trmnl/weather?tz={TZ}").json()
    assert "missing" not in w and w["place"] == "New York" and w["temp"] == "68°" and w["text"] == "Sunny" and w["feels"] == "70°"
    assert w["icon"] == trmnl.WX.index("sun") and w["wind"] == "6 mph" and w["humidity"] == "40%" and w["uv"] == "3"
    assert w["hi"] == "64°" and w["lo"] == "50°" and w["rain"] == "" and w["note"].startswith("Rain ")
    assert len(w["hours"]) == 8 and w["hours"][0]["icon"] == trmnl.WX.index("rain") and w["hours"][0]["rain"] == "70%" and w["hours"][0]["time"].endswith(("AM", "PM"))
    ys = [h["y"] for h in w["hours"]]  # the curve: from the warmest hour (0) down to the coolest (100)
    assert ys[0] == 0 and ys[-1] == 100 and ys == sorted(ys)
    assert [d["day"] for d in w["days"]][0] == "Today" and len(w["days"]) == 5 and w["days"][0]["rain"] == "" and w["days"][1] | {"day": ""} == {
        "day": "", "icon": trmnl.WX.index("rain"), "text": "Showers", "hi": "64°", "lo": "50°", "rain": "60%"}
    assert len(json.dumps(trmnl.fit(w)).encode()) <= trmnl.LIMIT
    z = zipfile.ZipFile(io.BytesIO(client.get("/api/trmnl/weather/plugin.zip").content))
    assert "base64_encode" in z.read("full.liquid").decode() and "capture wx_all" in z.read("shared.liquid").decode()


def test_today_lists_what_the_card_lists(monkeypatch):
    """The Today screen from the wall's feed: a birthday from ioContact and ioCalendar's all-day event for it are one line,
    a task with an hour goes among the events by the hour, nothing today or this week shows the next event."""
    import datetime as dt
    from zoneinfo import ZoneInfo
    z = ZoneInfo(TZ)
    now = dt.datetime(2026, 11, 19, 8, 5, tzinfo=z)
    at = lambda d, h, m=0: int(dt.datetime(2026, 11, d, h, m, tzinfo=z).timestamp())  # noqa: E731
    feed = {"today": [{"title": "Riley's dentist", "allDay": False, "s": at(19, 9, 30), "place": "Bayside Dental", "color": "#1e88e5"},
                      {"title": "Theo: no school", "allDay": True, "day": "2026-11-19", "place": ""}],
            "todayMore": 0, "next": None,
            "days": [{"date": "2026-11-21", "items": [{"title": "Grandma Joan's birthday", "allDay": True, "day": "2026-11-21", "place": ""},
                                                      {"title": "Soccer", "allDay": False, "s": at(21, 10), "place": ""}]}],
            "tasks": {"items": [{"title": "Sign the form", "due": "2026-11-19T15:00:00-05:00"}, {"title": "Call the plumber"}], "more": 2, "overdue": 0},
            "birthdays": [{"name": "Grandma Joan", "in": 2, "label": "birthday", "turns": 80}, {"name": "Ann & Rob", "in": 0, "label": "anniversary", "turns": 25}]}
    monkeypatch.setattr(trmnl.wall, "feed", lambda request, tz="": feed)
    monkeypatch.setattr(trmnl, "_ask", lambda request, key, **kw: {"week": [{"title": "Book flights", "due": "2026-11-24", "allDay": True}]})
    d = trmnl._today(None, z, now, False)
    first = d["list"][0]
    assert first["label"] == "Today" and first["more"] == 2
    assert [(r["title"], r["when"]) for r in first["rows"]] == [("Ann & Rob", "Anniversary"), ("Theo: no school", "All day"), ("Riley's dentist", "9:30 AM"),
                                                                 ("Sign the form", "Due 3 PM"), ("Call the plumber", "To do")]
    assert [r["ink"] for r in first["rows"]] == ["", "", "blue", "", ""]  # the calendar's colour, for a colour screen
    assert [g["label"] for g in d["list"][1:]] == ["Saturday \u00b7 Nov 21", "Tuesday \u00b7 Nov 24"]
    assert [(r["title"], r["note"]) for r in d["list"][1]["rows"]] == [("Grandma Joan", "\u00b7 turns 80"), ("Soccer", "")]
    feed.update(today=[], days=[], tasks={"items": [], "more": 0, "overdue": 0}, birthdays=[],
                next={"title": "Car service", "allDay": False, "s": at(30, 8), "place": ""})
    monkeypatch.setattr(trmnl, "_ask", lambda request, key, **kw: {"week": []})
    d = trmnl._today(None, z, now, False)
    assert len(d["list"]) == 1 and d["list"][0]["rows"][0]["title"] == "Car service" and d["list"][0]["rows"][0]["when"] == "Next"


def test_fit_under_the_limit():
    d = {"screen": "tasks", "tasks": [{"title": "x" * 70, "when": ""} for _ in range(200)], "more": 0}
    out = trmnl.fit(d)
    assert len(json.dumps(out).encode()) <= trmnl.LIMIT and out["more"] == 200 - len(out["tasks"])
    rows = lambda n: [{"title": "y" * 70, "when": "To do", "note": "", "late": False} for _ in range(n)]  # noqa: E731
    d = {"screen": "today", "list": [{"label": "Today", "rows": rows(30), "more": 0}, {"label": "Tomorrow", "rows": rows(30), "more": 0},
                                     {"label": "Saturday", "rows": rows(30), "more": 0}]}
    out = trmnl.fit(d)  # the furthest days give way first, today's own lines never
    assert len(json.dumps(out).encode()) <= trmnl.LIMIT and len(out["list"][0]["rows"]) == 30 and len(out["list"]) == 2 and 0 < len(out["list"][1]["rows"]) < 30


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
              "has_tasks": True, "list": [{"label": "Today", "more": 1, "rows": [{"title": "Bins", "when": "Late", "note": "", "late": True}]},
                                             {"label": "Tomorrow", "more": 0, "rows": [{"title": "Dinner", "when": "6 PM", "note": "@ Nan Xiang", "late": False}]}],
              "none": "Nothing planned or due today", "tasks": [{"title": "Bins", "when": "Late", "late": True}], "overdue": 1, "days": [], "more": 0,
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
    # the pictures Liquid writes from the numbers: the rings (an arc as long as the day is far), the bars, the curve
    pics = lambda screen, size, data: [base64.b64decode(x).decode() for x in re.findall(  # noqa: E731
        r'src="data:image/svg\+xml;base64,([^"]+)"', env.parse(trmnl.markup(screen)["shared"] + trmnl.markup(screen)[size]).render(sample | data))]
    rings = {"rings": [{"name": "Move", "value": "300", "goal": "600", "unit": "kcal", "pct": 50}, {"name": "Stand", "value": "0", "goal": "12", "unit": "h", "pct": 0}],
             "week": [{"day": "Fri", "steps": "8,214", "pct": 64}, {"day": "Sat", "steps": "12,880", "pct": 100}]}
    for size in trmnl.SIZES:
        ring = pics("health", size, rings)[0]
        assert ring.count("<circle") == 3 and 'stroke-dasharray="163.36 400"' in ring and 'transform="rotate(-90 60 60)"' in ring, size  # half of 2 pi 52
        inked = pics("health", size, rings)[1]  # each picture twice: in black, then in a colour screen's inks
        assert inked.replace(' stroke="#f00"', "").replace(' stroke="#0f0"', "") == ring.replace('<g fill="none" stroke="#000">', '<g fill="none">'), size
    week = pics("health", "full", rings)[2]
    assert week.count("<rect") == 2 and 'y="36" width="7" height="64"' in week and 'preserveAspectRatio="none"' in week
    assert pics("health", "full", rings)[3].count('<rect fill="#00f" ') == 2
    days = pics("money", "full", {"total": "$50.00", "days": [{"day": "Thu", "amount": "40", "pct": 100}, {"day": "Fri", "amount": "", "pct": 0}]})
    assert len(days) == 3 and days[0].count("<rect") == 2 and 'height="100"' in days[0] and days[1].count('<rect fill="#00f" ') == 2  # and the suite's mark in the bar
    hours = [{"time": f"{i + 1} PM", "icon": 5, "temp": "66°", "rain": "", "y": 25 * i} for i in range(5)]
    curve = [x for x in pics("weather", "full", forecast | {"hours": hours}) if "<polygon" in x]
    points = re.search(r'points="([^"]+)"', curve[0]).group(1).split()
    assert '<polygon fill="#f00" ' in curve[1]
    assert len(curve) == 2 and len(points) == 2 * (len(hours) + 2) and points[0] == "0,3.0" and points[1] == "5,3.0" and points[5] == "45,83.0"


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
