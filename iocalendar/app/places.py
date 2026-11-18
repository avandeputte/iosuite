"""Place suggestions while you type an event's place, from Google Places (Autocomplete, Places API (New)).

Nothing to set up here: the key is the suite's Google key that ioPix keeps in the Shared ioSuite database (Settings ›
Security › Keys and tokens: ioPix's "Google server key" when there is one, else its "Google Maps API key"). Without
one the place field stays a plain text field. The key never leaves the server: the page asks /api/places, and this
app asks Google. Since a browser-facing key is usually restricted by HTTP referrer to ioPix's address, the request
carries ioPix's address as its Referer, as ioPix's own server-side calls do. The key needs "Places API (New)" enabled
(ioPix's place search already uses it).

Only the typed text leaves the server, with a bias towards the start page's weather place when there is one (so
"Kerkstraat" means the one nearby). Answers are kept in memory for ten minutes, so typing back and forth does not ask
again. Each event dialog sends one session token, which Google uses to group the keystrokes of one search.
"""
import json
import logging
import threading
import time
import urllib.error
import urllib.request

from iosuite_shared import credentials, suite

from app import weather

log = logging.getLogger("iocalendar.places")
KEY_APP = "iopix"                       # the app whose keys and tokens hold the suite's Google keys
AUTOCOMPLETE_URL = "https://places.googleapis.com/v1/places:autocomplete"
MIN_CHARS = 3
MAX_CHARS = 200
LIMIT = 6
BIAS_RADIUS = 50000.0                   # metres around the start page's place (the most Google allows)
TTL = 600
TIMEOUT = 6

_cache: dict = {}                       # (text, near) -> (at, items)
_lock = threading.Lock()


class PlacesError(Exception):
    pass


def forget() -> None:
    with _lock:
        _cache.clear()


def key() -> str:
    """The key for calls from this server: ioPix's server key, else its browser key ('' when the suite has none)."""
    try:
        return (credentials.get(KEY_APP, "google_server_key") or credentials.get(KEY_APP, "google_maps_key")).strip()
    except Exception:  # noqa: BLE001 - the shared database is away: no suggestions for now
        return ""


def enabled() -> bool:
    return bool(key())


def _referer() -> str:
    try:
        return suite.url_of(KEY_APP) or ""
    except Exception:  # noqa: BLE001
        return ""


def _near() -> tuple | None:
    """(lat, lon) of the start page's weather place, when it has one (app/weather.py keeps it for hours)."""
    try:
        h = weather.home()
    except Exception:  # noqa: BLE001 - no bias then
        return None
    return (h["lat"], h["lon"]) if h else None


def _post(body: dict, k: str) -> dict:
    """POST one request to Google. Replaced in the tests."""
    headers = {"Content-Type": "application/json", "X-Goog-Api-Key": k,
               "X-Goog-FieldMask": "suggestions.placePrediction.text,suggestions.placePrediction.structuredFormat"}
    ref = _referer()
    if ref:
        headers["Referer"] = ref
    req = urllib.request.Request(AUTOCOMPLETE_URL, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310  a fixed https address
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8", "replace")).get("error", {}).get("message") or ""
        except Exception:  # noqa: BLE001
            msg = ""
        raise PlacesError(f"Google Places answered {e.code}" + (f": {msg[:200]}" if msg else ""))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        raise PlacesError(f"Could not reach Google Places: {str(e)[:120]}")


def suggest(text: str, session: str = None, language: str = None) -> dict:
    """{enabled, items: [{text, main, secondary}]} for what was typed so far. text is the whole place as Google writes
    it ("Ghent Airport, Gent, Belgium"), what the field takes when one is picked."""
    k = key()
    if not k:
        return {"enabled": False, "items": []}
    q = " ".join((text or "").split())[:MAX_CHARS]
    if len(q) < MIN_CHARS or q.lower().startswith(("http://", "https://")):
        return {"enabled": True, "items": []}
    near = _near()
    ck = (q.lower(), near, language or "")
    now = time.time()
    with _lock:
        hit = _cache.get(ck)
        if hit and now - hit[0] < TTL:
            return {"enabled": True, "items": hit[1]}
    body = {"input": q}
    if session:
        body["sessionToken"] = str(session)[:64]
    if language:
        body["languageCode"] = str(language)[:16]
    if near:
        body["locationBias"] = {"circle": {"center": {"latitude": near[0], "longitude": near[1]}, "radius": BIAS_RADIUS}}
    data = _post(body, k)
    items = []
    for s in (data.get("suggestions") or [])[:LIMIT]:
        p = s.get("placePrediction") or {}
        full = ((p.get("text") or {}).get("text") or "").strip()
        if not full:
            continue
        fmt = p.get("structuredFormat") or {}
        main = ((fmt.get("mainText") or {}).get("text") or "").strip() or full
        items.append({"text": full, "main": main, "secondary": ((fmt.get("secondaryText") or {}).get("text") or "").strip()})
    with _lock:
        if len(_cache) > 500:
            _cache.clear()
        _cache[ck] = (now, items)
    return {"enabled": True, "items": items}
