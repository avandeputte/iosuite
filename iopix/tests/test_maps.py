"""Map provider: OpenStreetMap by default; Google Maps when chosen with a key, with the tile
session created server-side and place search going to Google's geocoder; a failing session
falls back to OpenStreetMap with a message; the key is never shown back."""
from app import geocode, maps, state


def _reset():
    state.set_setting("map_provider", "osm"); state.set_setting("google_maps_key", ""); maps.reset_session(); geocode._cache.clear()


def test_default_is_openstreetmap(client):
    _reset()
    c = client.get("/api/maps").json()
    assert c["provider"] == "osm" and "openstreetmap" in c["url"] and c["linkLabel"] == "OpenStreetMap"


def test_google_needs_a_key_and_never_shows_it(client):
    _reset()
    assert client.post("/api/settings", json={"map_provider": "google"}).status_code == 200
    assert maps.provider() == "osm", "without a key the provider stays OSM"
    client.post("/api/settings", json={"google_maps_key": "AIza-secret"})
    s = client.get("/api/settings").json() if client.get("/api/settings").status_code == 200 else client.get("/api/maintenance").json()
    assert "AIza-secret" not in str(s) and (s.get("google_maps_key_set") or s.get("googleMapsKeySet"))
    assert client.post("/api/settings", json={"map_provider": "nope"}).status_code == 400
    _reset()


def test_google_tiles_use_a_server_created_session(client, monkeypatch):
    _reset()
    state.set_setting("map_provider", "google"); state.set_setting("google_maps_key", "AIza-secret")
    monkeypatch.setattr(maps, "_create_session", lambda k: {"session": "tok123", "expiry": 9999999999})
    c = client.get("/api/maps").json()
    assert c["provider"] == "google" and "session=tok123" in c["url"] and "key=AIza-secret" in c["url"] and c["linkLabel"] == "Google Maps"
    calls = []
    monkeypatch.setattr(maps, "_create_session", lambda k: calls.append(k) or {"session": "tok456"})
    client.get("/api/maps")
    assert calls == [], "the session is cached until it nears expiry"
    _reset()


def test_google_session_failure_falls_back_to_osm(client, monkeypatch):
    _reset()
    state.set_setting("map_provider", "google"); state.set_setting("google_maps_key", "AIza-secret")
    def boom(k):
        raise OSError("403 forbidden")
    monkeypatch.setattr(maps, "_create_session", boom)
    c = client.get("/api/maps").json()
    assert c["provider"] == "osm" and "403" in c["error"]
    _reset()


def test_place_search_uses_google_when_chosen(client, monkeypatch):
    _reset()
    state.set_setting("map_provider", "google"); state.set_setting("google_maps_key", "AIza-secret")
    monkeypatch.setattr(maps, "geocode", lambda q: [{"name": "Mt Lebanon High School", "detail": "Pittsburgh, PA", "lat": 40.37, "lon": -80.05, "zoom": 16}])
    monkeypatch.setattr(geocode, "_fetch", lambda q: (_ for _ in ()).throw(AssertionError("Nominatim must not be asked")))
    geocode._offline_until[0] = 0
    r = client.get("/api/geocode?q=Mt+Lebanon+High+School").json()
    assert r["source"] == "google" and r["results"][0]["lat"] == 40.37
    _reset()
