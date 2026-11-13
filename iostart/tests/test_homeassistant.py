"""Home Assistant (its REST API mocked: no network): the settings, the Home card's entities and their wording, the
allowlist for switching, the search, and what needs attention."""
import json

from app import homeassistant as ha

STATES = [
    {"entity_id": "light.kitchen", "state": "on", "attributes": {"friendly_name": "Kitchen", "brightness": 128}, "last_changed": "2026-11-06T04:00:00+00:00"},
    {"entity_id": "switch.heater", "state": "off", "attributes": {"friendly_name": "Heater"}},
    {"entity_id": "lock.front_door", "state": "locked", "attributes": {"friendly_name": "Front door"}},
    {"entity_id": "binary_sensor.garage", "state": "on", "attributes": {"friendly_name": "Garage door", "device_class": "garage_door"}},
    {"entity_id": "sensor.living_temp", "state": "21.46", "attributes": {"friendly_name": "Living room temperature", "unit_of_measurement": "°C", "device_class": "temperature"}},
    {"entity_id": "sensor.remote_battery", "state": "9", "attributes": {"friendly_name": "Remote battery", "unit_of_measurement": "%", "device_class": "battery"}},
    {"entity_id": "binary_sensor.sink_leak", "state": "on", "attributes": {"friendly_name": "Sink leak", "device_class": "moisture"}},
    {"entity_id": "scene.movie", "state": "unknown", "attributes": {"friendly_name": "Movie night"}},
    {"entity_id": "person.alex", "state": "not_home", "attributes": {"friendly_name": "Alex"}},
]


def _fake_ha(calls):
    def call(method, path, body=None, base="", tok=""):
        calls.append((method, path, body))
        if path == "/api/config":
            return {"location_name": "Casa", "version": "2026.11.1"}
        if path == "/api/states":
            return [dict(s) for s in STATES]
        if path.startswith("/api/states/"):
            eid = path.split("/api/states/", 1)[1]
            st = next((s for s in STATES if s["entity_id"] == eid), None)
            return {**st, "state": "off" if st["state"] == "on" else "on"} if st else None
        if path.startswith("/api/services/"):
            return []
        if path == "/api/template":
            ids = json.loads(body["template"].split("{{ ", 1)[1].split(" | map", 1)[0])
            return json.dumps([("dev_" + e.split(".")[1]) if e in ("lock.front_door", "sensor.living_temp", "light.kitchen") else None for e in ids])
        raise AssertionError(path)
    return call


def _setup(client, monkeypatch):
    calls = []
    monkeypatch.setattr(ha, "_call", _fake_ha(calls))
    ha.forget()
    s = client.post("/api/ha/settings", json={"url": "http://ha.lan:8123/", "token": "s3cret-token"}).json()
    assert s["enabled"] and s["url"] == "http://ha.lan:8123" and s["hasToken"] and "token" not in s and "s3cret" not in str(s)
    return calls


def test_off_until_set_up(client):
    assert client.get("/api/ha").json() == {"enabled": False}
    s = client.get("/api/ha/settings").json()
    assert s["enabled"] is False and s["hasToken"] is False and s["entities"] == [] and s["builtinAlerts"] is True
    assert client.post("/api/ha/settings", json={"url": "ha.lan"}).status_code == 400  # http:// first
    assert client.post("/api/ha/test", json={}).status_code == 400
    assert client.get("/api/ha/search?q=kitchen").json() == {"items": []}


def test_test_and_card(client, monkeypatch):
    calls = _setup(client, monkeypatch)
    t = client.post("/api/ha/test", json={}).json()
    assert t == {"ok": True, "name": "Casa", "version": "2026.11.1", "entities": len(STATES)}
    ents = [{"id": "light.kitchen", "control": True}, {"id": "lock.front_door", "name": "Front", "control": True, "wall": True},
            {"id": "binary_sensor.garage", "wall": True, "alert": "on"}, {"id": "sensor.living_temp", "wall": True},
            {"id": "scene.movie", "control": True}, {"id": "person.alex"}, {"id": "light.gone"}]
    s = client.post("/api/ha/settings", json={"entities": ents}).json()
    assert [e["id"] for e in s["entities"]] == [e["id"] for e in ents] and s["entities"][1] == {"id": "lock.front_door", "name": "Front", "control": True, "wall": True, "alert": ""}
    d = client.get("/api/ha").json()
    assert d["enabled"] and d["name"] == "Casa" and d["url"] == "http://ha.lan:8123" and d["wall"] == ["lock.front_door", "binary_sensor.garage", "sensor.living_temp"]
    by = {i["id"]: i for i in d["items"]}
    assert by["light.kitchen"]["text"] == "On · 50%" and by["light.kitchen"]["on"] is True and by["light.kitchen"]["control"] is True
    assert by["lock.front_door"]["name"] == "Front" and by["lock.front_door"]["text"] == "Locked" and by["lock.front_door"]["on"] is False
    assert by["binary_sensor.garage"]["text"] == "Open" and by["binary_sensor.garage"]["control"] is False
    assert by["sensor.living_temp"]["text"] == "21.5°C" and by["scene.movie"]["text"] == "Tap to run" and by["person.alex"]["text"] == "Away"
    assert by["light.gone"]["state"] == "missing" and by["light.gone"]["control"] is False
    # the device each belongs to (for the link to its page), asked once through the template API
    assert by["lock.front_door"]["device"] == "dev_front_door" and "device" not in by["person.alex"]
    assert sum(1 for c in calls if c[1] == "/api/template") == 1
    # what needs attention: the garage (its "alert when"), and built in: the leak and the low battery
    assert [(a["id"], a["text"]) for a in d["alerts"]] == [("binary_sensor.garage", "Open"), ("binary_sensor.sink_leak", "Leak"), ("sensor.remote_battery", "Battery 9%")]
    client.post("/api/ha/settings", json={"builtinAlerts": False})
    assert [a["id"] for a in client.get("/api/ha").json()["alerts"]] == ["binary_sensor.garage"]
    # one call to Home Assistant for the states, however many pages ask within a few seconds
    n = sum(1 for c in calls if c[1] == "/api/states")
    client.get("/api/ha"); client.get("/api/ha")
    assert sum(1 for c in calls if c[1] == "/api/states") == n


def test_switching_needs_the_admins_tick(client, monkeypatch):
    calls = _setup(client, monkeypatch)
    client.post("/api/ha/settings", json={"entities": [{"id": "light.kitchen", "control": True}, {"id": "switch.heater"}, {"id": "scene.movie", "control": True}, {"id": "lock.front_door", "control": True}]})
    r = client.post("/api/ha/light.kitchen/toggle")
    assert r.status_code == 200 and r.json()["state"] == "off", r.text
    assert ("POST", "/api/services/homeassistant/toggle", {"entity_id": "light.kitchen"}) in calls
    assert client.post("/api/ha/switch.heater/toggle").status_code == 403       # on the card, not ticked
    assert client.post("/api/ha/sensor.living_temp/toggle").status_code == 403  # not on the card
    assert client.post("/api/ha/light.kitchen/dim").status_code == 400
    assert client.post("/api/ha/scene.movie/off").status_code == 400            # a scene has no off
    assert client.post("/api/ha/scene.movie/toggle").status_code == 200
    assert ("POST", "/api/services/scene/turn_on", {"entity_id": "scene.movie"}) in calls
    assert client.post("/api/ha/lock.front_door/off").status_code == 200
    assert ("POST", "/api/services/lock/unlock", {"entity_id": "lock.front_door"}) in calls
    assert [i["control"] for i in client.get("/api/ha").json()["items"]] == [True, False, True, True]
    # an editor switches the ticked ones too; a viewer reads the states and switches nothing
    client.post("/api/users", json={"name": "mum", "password": "secret123", "role": "editor"})
    client.post("/api/users", json={"name": "kid", "password": "secret123", "role": "viewer"})
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"name": "mum", "password": "secret123"}).status_code == 200
    assert client.post("/api/ha/light.kitchen/toggle").status_code == 200
    assert client.get("/api/ha").json()["items"][0]["control"] is True
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"name": "kid", "password": "secret123"}).status_code == 200
    d = client.get("/api/ha").json()
    assert d["enabled"] is True and d["items"][0]["state"] and not any(i["control"] for i in d["items"])
    n = len(calls)
    assert client.post("/api/ha/light.kitchen/toggle").status_code == 403
    assert client.post("/api/ha/lock.front_door/off").status_code == 403
    assert client.post("/api/ha/light.kitchen/set", json={"temperature": 20}).status_code == 403
    assert len(calls) == n, "nothing reached Home Assistant"
    with client.stream("GET", "/api/ha/events?once=1") as r:  # the stream is the viewer's copy as well
        line = next(l for l in r.iter_lines() if l.startswith("data: "))
        assert not any(i["control"] for i in json.loads(line[6:])["items"])
    assert client.get("/api/ha/settings").status_code == 403
    assert client.post("/api/ha/settings", json={"entities": []}).status_code == 403
    assert client.post("/api/ha/test", json={}).status_code == 403


def test_search(client, monkeypatch):
    _setup(client, monkeypatch)
    client.post("/api/ha/settings", json={"entities": [{"id": "lock.front_door", "control": True}]})
    found = client.get("/api/ha/search?q=door").json()["items"]
    assert [f["id"] for f in found] == ["lock.front_door", "binary_sensor.garage"]  # the card's first, then by name
    assert found[0]["control"] is True and found[0]["chosen"] is True and found[1]["control"] is False
    assert found[0]["device"] == "dev_front_door" and "device" not in found[1]
    assert [f["id"] for f in client.get("/api/ha/search?q=living temp").json()["items"]] == ["sensor.living_temp"]
    assert client.get("/api/ha/search?q=").json()["items"] == []


def test_layout_has_the_home_card(client):
    L = client.put("/api/me/layout", json={"hidden": ["home"], "cards": ["home", "bookmarks"]}).json()
    assert L["hidden"] == ["home"] and L["cards"] == ["home", "bookmarks"]


def test_switching_waits_for_a_slow_device(client, monkeypatch):
    """A Zigbee bulb reports its new state a moment after the service call: the answer is the new state, not the old."""
    calls = []
    state = {"v": "off", "reads": 0}

    def call(method, path, body=None, base="", tok=""):
        calls.append((method, path))
        if path == "/api/states":
            return [{"entity_id": "light.slow", "state": state["v"], "attributes": {"friendly_name": "Slow"}, "last_updated": "t0"}]
        if path == "/api/states/light.slow":
            state["reads"] += 1
            if state["reads"] >= 3:   # the device answers on the third read only
                state["v"] = "on"
            return {"entity_id": "light.slow", "state": state["v"], "attributes": {"friendly_name": "Slow"}, "last_updated": "t0" if state["v"] == "off" else "t1"}
        if path.startswith("/api/services/"):
            return []   # nothing changed yet, as far as Home Assistant knows
        if path == "/api/template":
            return "[null]"
        raise AssertionError(path)
    monkeypatch.setattr(ha, "_call", call)
    monkeypatch.setattr(ha.time, "sleep", lambda s: None)
    ha.forget()
    client.post("/api/ha/settings", json={"url": "http://ha.lan:8123", "token": "s3cret-token", "entities": [{"id": "light.slow", "control": True}]})
    assert client.get("/api/ha").json()["items"][0]["text"] == "Off"
    r = client.post("/api/ha/light.slow/toggle").json()
    assert r["state"] == "on" and r["text"] == "On", r
    assert state["reads"] == 3


def test_climate_and_cover_popups(client, monkeypatch):
    """The popups' /set: a thermostat's temperature, mode, fan and preset, a cover's open / close / stop / position,
    each checked against what the entity offers and against the admin's control tick."""
    calls = []
    states = {
        "climate.living": {"entity_id": "climate.living", "state": "heat", "attributes": {"friendly_name": "Thermostat", "current_temperature": 20.5, "temperature": 21.0, "min_temp": 7, "max_temp": 30,
                                                                                          "hvac_modes": ["off", "heat", "cool", "auto"], "hvac_action": "heating", "fan_modes": ["auto", "low", "high"], "fan_mode": "auto", "preset_modes": ["home", "away"], "preset_mode": "home"}},
        "cover.garage": {"entity_id": "cover.garage", "state": "closed", "attributes": {"friendly_name": "Garage", "supported_features": 11}},   # open, close, stop; no position
        "cover.blind": {"entity_id": "cover.blind", "state": "open", "attributes": {"friendly_name": "Blind", "supported_features": 15, "current_position": 60}},
    }

    def call(method, path, body=None, base="", tok=""):
        calls.append((method, path, body))
        if path == "/api/config":
            return {"location_name": "Casa", "version": "2026.11.1", "unit_system": {"temperature": "°F"}}
        if path == "/api/states":
            return list(states.values())
        if path.startswith("/api/states/"):
            return states.get(path.split("/api/states/", 1)[1])
        if path == "/api/template":
            return "[null, null, null]"
        if path.startswith("/api/services/climate/"):
            a = states["climate.living"]["attributes"]
            a.update({k: v for k, v in body.items() if k != "entity_id"} if "temperature" in body else {})
            if "hvac_mode" in body:
                states["climate.living"]["state"] = body["hvac_mode"]
            if "fan_mode" in body:
                a["fan_mode"] = body["fan_mode"]
            return [states["climate.living"]]
        if path.startswith("/api/services/cover/"):
            st = states[body["entity_id"]]
            svc = path.rsplit("/", 1)[1]
            st["state"] = {"open_cover": "opening", "close_cover": "closing", "stop_cover": st["state"], "set_cover_position": "open"}[svc]
            if svc == "set_cover_position":
                st["attributes"]["current_position"] = body["position"]
            return [st]
        raise AssertionError(path)
    monkeypatch.setattr(ha, "_call", call)
    monkeypatch.setattr(ha.time, "sleep", lambda s: None)
    ha.forget(devices=True)
    ha._unit["v"] = ""
    client.post("/api/ha/settings", json={"url": "http://ha.lan:8123", "token": "s3cret-token",
                                           "entities": [{"id": "climate.living", "control": True}, {"id": "cover.garage", "control": True}, {"id": "cover.blind"}]})
    by = {i["id"]: i for i in client.get("/api/ha").json()["items"]}
    assert by["climate.living"]["climate"] == {"mode": "heat", "modes": ["off", "heat", "cool", "auto"], "action": "heating", "current": 20.5, "target": 21.0, "low": None, "high": None,
                                               "min": 7, "max": 30, "step": 0.5, "humidity": None, "fan": "auto", "fans": ["auto", "low", "high"], "preset": "home", "presets": ["home", "away"], "unit": "°F"}
    assert by["cover.garage"]["cover"] == {"position": None, "canOpen": True, "canClose": True, "canPosition": False, "canStop": True, "moving": False}
    assert by["cover.blind"]["cover"]["canPosition"] is True and by["cover.blind"]["cover"]["position"] == 60
    # the thermostat
    r = client.post("/api/ha/climate.living/set", json={"temperature": 22.5}).json()
    assert r["climate"]["target"] == 22.5 and ("POST", "/api/services/climate/set_temperature", {"entity_id": "climate.living", "temperature": 22.5}) in calls
    assert client.post("/api/ha/climate.living/set", json={"temperature": 40}).status_code == 400
    assert client.post("/api/ha/climate.living/set", json={"mode": "dry"}).status_code == 400
    assert client.post("/api/ha/climate.living/set", json={"mode": "cool"}).json()["climate"]["mode"] == "cool"
    assert client.post("/api/ha/climate.living/set", json={"fan": "high"}).json()["climate"]["fan"] == "high"
    assert client.post("/api/ha/climate.living/set", json={"low": 18}).status_code == 400          # low and high together
    assert client.post("/api/ha/climate.living/set", json={}).status_code == 400
    # the covers
    assert client.post("/api/ha/cover.garage/set", json={"action": "open"}).json()["state"] == "opening"
    assert client.post("/api/ha/cover.garage/set", json={"action": "stop"}).status_code == 200
    assert client.post("/api/ha/cover.garage/set", json={"position": 50}).status_code == 400       # it takes none
    assert client.post("/api/ha/cover.blind/set", json={"action": "close"}).status_code == 403      # not ticked
    client.post("/api/ha/settings", json={"entities": [{"id": "climate.living", "control": True}, {"id": "cover.garage", "control": True}, {"id": "cover.blind", "control": True}]})
    assert client.post("/api/ha/cover.blind/set", json={"position": 25}).json()["cover"]["position"] == 25
    assert client.post("/api/ha/light.kitchen/set", json={"action": "open"}).status_code == 400    # not a popup entity


def test_live_feed_keeps_the_copy_and_streams_the_card(client, monkeypatch):
    """The websocket feed (app/ha_feed.py) primes the copy and folds each state_changed into it; while it is live the
    REST copy is never refetched; /api/ha/events sends the card as server-sent events."""
    calls = []
    monkeypatch.setattr(ha, "_call", _fake_ha(calls))
    ha.feed_down(); ha.forget(devices=True)
    client.post("/api/ha/settings", json={"url": "http://ha.lan:8123", "token": "s3cret-token", "entities": [{"id": "light.kitchen", "control": True}]})
    assert client.get("/api/ha").json()["items"][0]["text"] == "On · 50%" and not client.get("/api/ha").json()["live"]
    n = sum(1 for c in calls if c[1] == "/api/states")
    # the feed connects: its list is the copy from now on, and its events change it
    ha.prime([dict(s) for s in STATES])
    ha.feed.live = True
    assert ha.apply("light.kitchen", {"entity_id": "light.kitchen", "state": "off", "attributes": {"friendly_name": "Kitchen"}}) is True
    # an entity that is on no card is kept in the copy, and wakes no page
    assert ha.apply("light.new", {"entity_id": "light.new", "state": "on", "attributes": {}}) is False
    assert any(s["entity_id"] == "light.new" for s in ha.all_states())
    assert ha.apply("light.nothere", None) is False
    # one the built-in alerts watch does wake them (a leak sensor, a battery)
    leak = {"entity_id": "binary_sensor.cellar_leak", "state": "on", "attributes": {"device_class": "moisture", "friendly_name": "Cellar"}}
    assert ha.apply("binary_sensor.cellar_leak", leak) is True
    assert any(a["id"] == "binary_sensor.cellar_leak" for a in client.get("/api/ha").json()["alerts"])
    assert ha.apply("binary_sensor.cellar_leak", None) is True
    monkeypatch.setattr(ha, "STATES_TTL", 0)   # even a stale-by-the-clock copy is not refetched while live
    d = client.get("/api/ha").json()
    assert d["live"] and d["items"][0]["text"] == "Off"
    assert sum(1 for c in calls if c[1] == "/api/states") == n, "no REST fetch while the feed is live"
    assert client.get("/api/ha/settings").json()["live"] is True
    # the event stream: the first message is the card as it stands
    with client.stream("GET", "/api/ha/events?once=1") as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("data: "):
                assert json.loads(line[6:])["items"][0]["text"] == "Off"
                break
    # the feed drops: back to REST
    ha.feed.live = False
    ha.feed_down()
    assert client.get("/api/ha").json()["live"] is False
    assert sum(1 for c in calls if c[1] == "/api/states") == n + 1
    # a new address retires the feed's connection
    ha.feed.live = True
    client.post("/api/ha/settings", json={"url": "http://other.lan:8123"})
    assert ha.feed.live is False


def test_event_stream_waits_without_a_thread():
    """The event streams wait on an asyncio event the feed sets from its thread (loop.call_soon_threadsafe), so a
    hundred open pages hold no threads of the pool; the wait ends on a change or the timeout."""
    import asyncio
    import threading
    import time

    async def run():
        v = ha.feed.version
        t0 = time.monotonic()
        assert await ha.feed.wait_async(v, 0.2) == v and time.monotonic() - t0 >= 0.15   # nothing moved: the timeout
        threading.Timer(0.05, ha.feed.bump).start()
        t0 = time.monotonic()
        assert await ha.feed.wait_async(v, 5) == v + 1 and time.monotonic() - t0 < 2     # woken by the feed's thread
        assert await ha.feed.wait_async(v, 5) == v + 1                                    # already moved: at once
        assert not ha.feed._waiters
    asyncio.run(run())


def test_the_card_is_built_once_and_the_settings_read_once(client, monkeypatch):
    """Many open pages ask for the card on every change: the settings come from the database once (not five queries a
    page), and the card is built once per change."""
    from app import db
    _setup(client, monkeypatch)
    client.post("/api/ha/settings", json={"entities": [{"id": "light.kitchen", "control": True}]})
    first = ha.home()
    asked, built = [], []
    real_q, real_describe = db.q, ha.describe
    monkeypatch.setattr(db, "q", lambda sql, args=None: (asked.append(sql), real_q(sql, args))[1])
    monkeypatch.setattr(ha, "describe", lambda *a, **kw: (built.append(1), real_describe(*a, **kw))[1])
    for _ in range(50):
        assert ha.home() is first or ha.home() == first
    assert not [s for s in asked if "prt_settings" in s] and not built
    # a change of the settings shows at once
    client.post("/api/ha/settings", json={"entities": [{"id": "light.kitchen", "name": "Stove light", "control": True}]})
    assert ha.home()["items"][0]["name"] == "Stove light"
