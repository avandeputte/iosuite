"""The wall display on a device (app/wall.py): its pairing, its feed, its photos and its taps. The apps are stood in for
by their own providers over a table (conftest.via_providers); no network."""
import datetime as dt
import io

import pytest

from iosuite_shared import apppasswords, users

from app import wall, widgets
from conftest import via_providers


@pytest.fixture()
def apps_answer(monkeypatch):
    table, asked, sent = {}, [], []
    monkeypatch.setattr(widgets, "fetch", via_providers(table, asked, sent))
    wall.forget()
    return table, asked, sent


def _pair(client, label="Kitchen wall"):
    c = client.post("/api/wall/pair", json={"label": label})
    assert c.status_code == 200, c.text
    return c.json()


def test_pairing(client):
    p = _pair(client)
    assert len(p["code"]) == 8 and p["approveUrl"].endswith(f"/#/pair/{p['code']}") and p["every"] == 3
    # nobody approved yet: the device waits; the code is not found by the poll's own token by mistake
    cookies = dict(client.cookies)
    client.cookies.clear()
    assert client.get(f"/api/wall/pair/{p['token']}").status_code == 202
    assert client.get("/api/wall/pair/code/" + p["code"]).status_code == 401  # approving takes a signed-in person
    assert client.get("/api/wall/pair/nonsense").status_code == 404
    client.cookies.update(cookies)
    info = client.get("/api/wall/pair/code/" + p["code"].lower()).json()  # typed in lower case, with a dash: still it
    assert info["label"] == "Kitchen wall"
    assert client.post(f"/api/wall/pair/code/{p['code'][:4]}-{p['code'][4:]}").json() == {"ok": True, "label": "Kitchen wall"}
    assert client.post(f"/api/wall/pair/code/{p['code']}").status_code == 404  # once
    client.cookies.clear()
    got = client.get(f"/api/wall/pair/{p['token']}").json()
    assert got["name"] == "alex" and got["password"].startswith("iostart-")
    assert client.get(f"/api/wall/pair/{p['token']}").status_code == 404  # handed over once
    # the password signs the device in as alex, and Settings › Account lists it under the device's name
    h = {"Authorization": f"Bearer {got['password']}"}
    assert client.get("/api/me/layout", headers=h).status_code == 200
    alex = users.find("alex")
    assert [x["label"] for x in apppasswords.list_for(alex["id"], "iostart")] == ["Kitchen wall"]


def test_pairing_limits(client, monkeypatch):
    for _ in range(wall.PAIR_MAX + 5):
        _pair(client)
    assert len(wall._pairs) == wall.PAIR_MAX
    p = _pair(client, "  ")
    assert wall._pairs[p["token"]]["label"] == "Wall display"
    monkeypatch.setattr(wall.time, "time", lambda: 10 ** 10)
    assert client.get(f"/api/wall/pair/{p['token']}").status_code == 404  # expired


def test_posix_tz():
    assert wall.posix_tz("America/New_York") == "EST5EDT,M3.2.0,M11.1.0"
    assert wall.posix_tz("Europe/Brussels") == "CET-1CEST,M3.5.0,M10.5.0/3"
    assert wall.posix_tz("UTC") in ("UTC0", "<UTC>0")
    assert wall.server_zone()


def test_feed(client, apps_answer):
    table, asked, _ = apps_answer
    zone = dt.timezone(dt.timedelta(hours=-5))
    now = dt.datetime.now(dt.timezone.utc).astimezone(zone)
    soon = now + dt.timedelta(hours=1)
    table[("iocalendar", "/api/calendars")] = {"items": [{"id": 1, "color": "#963522"}]}
    table[("iocalendar", "/api/occurrences")] = lambda p: {"items": [
        {"calendarId": 1, "title": "Dinner", "start": soon.isoformat(), "end": (soon + dt.timedelta(hours=2)).isoformat(), "allDay": False,
         "location": "Nan Xiang Dumpling, 38-12 Prince St, Flushing"}]}
    table[("iotask", "/api/lists")] = {"items": [{"id": 3, "color": "#2266aa"}]}
    table[("iotask", "/api/tasks")] = lambda p: {"items": [{"id": 41, "title": "Take out the bins", "due": now.date().isoformat(), "dueAllDay": True, "listId": 3}]
                                                if p.get("due") == "today" else []}
    table[("iocontact", "/api/upcoming")] = {"items": [{"contactId": 5, "fn": "Ava", "label": "birthday", "turns": 9, "inDays": 1, "date": "x"},
                                                       {"contactId": 6, "fn": "Far", "label": "birthday", "inDays": 20, "date": "y"}]}
    table[("iopix", "/api/random")] = {"id": [7, 8], "ts": [None, None], "w": [600, 1600], "h": [900, 900]}
    d = client.get("/api/wall/feed?tz=America/New_York").json()
    assert d["v"] == 1 and d["zone"] == {"name": "America/New_York", "posix": "EST5EDT,M3.2.0,M11.1.0"}
    assert d["bg"] == "photos" and d["every"] == 60 and d["user"]["name"] == "alex"
    ev = d["today"][0]
    assert ev["title"] == "Dinner" and ev["place"] == "Nan Xiang Dumpling" and ev["s"] == int(soon.timestamp()) and ev["color"] == "#963522"
    assert "who" not in ev and "notes" not in ev  # nothing more to say of it
    assert d["tasks"]["items"] == [{"id": 41, "title": "Take out the bins", "late": False, "color": "#2266aa", "due": now.date().isoformat(), "allDay": True}]
    assert d["birthdays"] == [{"name": "Ava", "in": 1, "label": "birthday", "turns": 9}]  # the next week only
    assert [p["id"] for p in d["photos"]] == ["8", "7"]  # landscape first
    assert d["weather"] is None and d["home"] is None  # neither set up
    assert d["can"] == {"addTask": True, "addEvent": True, "favorite": True, "home": True}
    assert all(p.get("tz") == "America/New_York" for _, path, p, _ in asked if path == "/api/tasks")
    # an app that does not answer leaves the rest
    del table[("iotask", "/api/tasks")]
    d = client.get("/api/wall/feed").json()
    assert d["tasks"] is None and "tasks" in d["errors"] and d["today"][0]["title"] == "Dinner"


def test_feed_background_and_photo_kind(client, apps_answer):
    table, asked, _ = apps_answer
    table[("iopix", "/api/random")] = {"id": [], "ts": []}
    assert client.put("/api/me/layout", json={"wallBg": "black"}).status_code == 200
    d = client.get("/api/wall/feed").json()
    assert d["bg"] == "black" and d["photos"] is None and not any(k == "iopix" for k, *_ in asked)
    assert wall.photo_kind({"strip": "off"}) == "rediscover" and wall.photo_kind({"wallPhotos": "album:12"}) == "album:12"
    assert wall.photo_kind({"wallPhotos": "x;y"}) == "rediscover"


def test_photo_cut_to_the_screen(client, apps_answer, monkeypatch):
    from PIL import Image
    src = io.BytesIO()
    Image.new("RGB", (2560, 1920), (200, 30, 30)).save(src, "JPEG", progressive=True)
    calls = []

    def image(request, key, kind, item_id, p=""):
        calls.append((key, kind, item_id, p))
        return src.getvalue(), "image/jpeg"
    monkeypatch.setattr(widgets, "image", image)
    r = client.get("/api/wall/photo/42.jpg?w=1280&h=720")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    im = Image.open(io.BytesIO(r.content))
    assert im.size == (1280, 720) and not im.info.get("progressive") and not im.info.get("progression")
    assert calls == [("iopix", "photo", "42", "preview")]
    client.get("/api/wall/photo/42.jpg?w=1280&h=720")
    assert len(calls) == 1  # kept
    assert Image.open(io.BytesIO(client.get("/api/wall/photo/42.jpg?w=99999&h=99999").content)).size == wall.PHOTO_MAX
    assert client.get("/api/wall/photo/..%2Fx.jpg").status_code == 404


def test_taps(client, apps_answer):
    table, _, sent = apps_answer
    table[("iotask", "/api/tasks/41/complete")] = {"ok": True}
    table[("iopix", "/api/favorites")] = {"ok": True}
    assert client.post("/api/wall/tasks/41/done").status_code == 200
    assert client.post("/api/wall/photos/8/favorite", json={"on": True}).json() == {"ok": True, "on": True}
    assert client.post("/api/wall/photos/8/favorite", json={"on": False}).json()["on"] is False
    assert sent == [("iotask", "/api/tasks/41/complete", {}), ("iopix", "/api/favorites", {"ids": [8], "on": True}),
                    ("iopix", "/api/favorites", {"ids": [8], "on": False})]
    assert client.post("/api/wall/tasks/a%20b/done").status_code == 404


def test_feed_event_details(client, apps_answer):
    """What a tap on an event shows: who of the family it is for, the other people, its calendar, its notes."""
    table, asked, _ = apps_answer
    soon = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
    table[("iocalendar", "/api/calendars")] = {"items": [{"id": 1, "color": "#963522", "name": "Family"}]}
    table[("iocalendar", "/api/members")] = {"items": [{"id": 7, "name": "ava", "displayName": "Ava", "color": "#2266aa"},
                                                       {"id": 8, "name": "theo", "displayName": "Theo", "color": "#33aa55"}]}
    table[("iocalendar", "/api/occurrences")] = lambda p: {"items": [
        {"calendarId": 1, "title": "Swimming", "start": soon.isoformat(), "end": (soon + dt.timedelta(hours=1)).isoformat(), "allDay": False,
         "location": "", "members": [8, 7, 99], "people": ["Coach Kim"], "notes": "Bring   goggles\nand a towel", "recurring": True}]}
    ev = client.get("/api/wall/feed?tz=America/New_York").json()["today"][0]
    assert ev["who"] == [{"name": "Theo", "color": "#33aa55"}, {"name": "Ava", "color": "#2266aa"}]
    assert ev["people"] == ["Coach Kim"] and ev["calendar"] == "Family" and ev["recurring"] is True
    assert ev["notes"] == "Bring goggles\nand a towel"
    assert any(path == "/api/occurrences" and p.get("notes") == 1 for _, path, p, _ in asked)
