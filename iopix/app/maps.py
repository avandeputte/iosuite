"""Map provider: OpenStreetMap tiles (default, no account) or Google Maps through the
Map Tiles API and the Geocoding API, with the owner's own API key.

The key comes from the `google_maps_key` setting (entered in Settings) or the
GOOGLE_MAPS_API_KEY environment variable; the `map_provider` setting picks the provider.
Google tiles need a session token: the server creates it with the key and hands the
browser a tile URL template. The key appears in that template, as Google's design
expects (restrict the key to this viewer's address in the Google Cloud console); the
server never prints it back in Settings.
"""
import json
import os
import threading
import time
import urllib.parse
import urllib.request

from . import state

SESSION_URL = "https://tile.googleapis.com/v1/createSession"
TILE_URL = "https://tile.googleapis.com/v1/2dtiles/{z}/{x}/{y}"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_session = {"token": None, "expires": 0}
_lock = threading.Lock()


def provider() -> str:
    p = state.get_setting("map_provider", "osm")
    return "google" if p == "google" and key() else "osm"


def key() -> str:
    return state.get_setting("google_maps_key", "") or os.environ.get("GOOGLE_MAPS_API_KEY", "")


def _create_session(k: str) -> dict:
    body = json.dumps({"mapType": "roadmap", "language": "en-US", "region": "US"}).encode()
    req = urllib.request.Request(SESSION_URL + "?key=" + urllib.parse.quote(k), data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def config() -> dict:
    """What the browser needs to draw maps: provider, tile URL template, attribution, max zoom."""
    if provider() != "google":
        return {"provider": "osm", "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png", "attribution": "© OpenStreetMap contributors", "maxZoom": 19,
                "link": "https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=15/{lat}/{lon}", "linkLabel": "OpenStreetMap"}
    k = key()
    with _lock:
        if not _session["token"] or time.time() > _session["expires"] - 3600:
            try:
                s = _create_session(k)
            except Exception as e:
                return {"provider": "osm", "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png", "attribution": "© OpenStreetMap contributors", "maxZoom": 19,
                        "link": "https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=15/{lat}/{lon}", "linkLabel": "OpenStreetMap",
                        "error": f"Google Maps session failed ({str(e)[:120]}); showing OpenStreetMap"}
            _session.update(token=s["session"], expires=int(s.get("expiry", time.time() + 14 * 86400)))
        token = _session["token"]
    return {"provider": "google", "url": TILE_URL + "?session=" + urllib.parse.quote(token) + "&key=" + urllib.parse.quote(k), "attribution": "© Google", "maxZoom": 22,
            "link": "https://www.google.com/maps/search/?api=1&query={lat},{lon}", "linkLabel": "Google Maps"}


def geocode(q: str) -> list:
    """Google Geocoding API: addresses and landmarks, in the shape geocode.search returns."""
    req = urllib.request.Request(GEOCODE_URL + "?" + urllib.parse.urlencode({"address": q, "key": key()}))
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.load(r)
    if data.get("status") not in ("OK", "ZERO_RESULTS"):
        raise RuntimeError(data.get("error_message") or data.get("status"))
    out = []
    for x in data.get("results", [])[:8]:
        name, _, detail = x.get("formatted_address", "").partition(", ")
        loc = x["geometry"]["location"]
        kinds = set(x.get("types", []))
        out.append({"name": name, "detail": detail[:110], "lat": loc["lat"], "lon": loc["lng"],
                    "zoom": 16 if kinds & {"establishment", "point_of_interest", "premise", "street_address", "school"} else 13 if kinds & {"locality", "sublocality"} else 14})
    return out


def reset_session():
    with _lock:
        _session.update(token=None, expires=0)
