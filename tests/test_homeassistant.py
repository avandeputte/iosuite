"""Home Assistant (its REST API mocked: no network): the settings, the Home card's entities and their wording, the
allowlist for switching, the search, and what needs attention."""
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
    # a viewer may read and switch the ticked ones, but not change the settings
    client.post("/api/users", json={"name": "kid", "password": "secret123", "role": "viewer"})
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"name": "kid", "password": "secret123"}).status_code == 200
    assert client.get("/api/ha").json()["enabled"] is True
    assert client.post("/api/ha/light.kitchen/toggle").status_code == 200
    assert client.get("/api/ha/settings").status_code == 403
    assert client.post("/api/ha/settings", json={"entities": []}).status_code == 403
    assert client.post("/api/ha/test", json={}).status_code == 403


def test_search(client, monkeypatch):
    _setup(client, monkeypatch)
    client.post("/api/ha/settings", json={"entities": [{"id": "lock.front_door", "control": True}]})
    found = client.get("/api/ha/search?q=door").json()["items"]
    assert [f["id"] for f in found] == ["lock.front_door", "binary_sensor.garage"]  # the card's first, then by name
    assert found[0]["control"] is True and found[0]["chosen"] is True and found[1]["control"] is False
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
        raise AssertionError(path)
    monkeypatch.setattr(ha, "_call", call)
    monkeypatch.setattr(ha.time, "sleep", lambda s: None)
    ha.forget()
    client.post("/api/ha/settings", json={"url": "http://ha.lan:8123", "token": "s3cret-token", "entities": [{"id": "light.slow", "control": True}]})
    assert client.get("/api/ha").json()["items"][0]["text"] == "Off"
    r = client.post("/api/ha/light.slow/toggle").json()
    assert r["state"] == "on" and r["text"] == "On", r
    assert state["reads"] == 3
