"""The weather on the start page, from AccuWeather (developer.accuweather.com).

Settings › Weather (admins) takes an API key and a place: the city is looked up with the Locations API and its location
key kept (ACCUWEATHER_API_KEY and ACCUWEATHER_LOCATION in the environment do the same and win). The page asks this
server, never AccuWeather, and the server asks AccuWeather only when its copy is older than the refresh interval, so a
free key (50 calls a day) lasts: the current conditions every hour at most, the next 12 hours every 90 minutes, the
5-day forecast every 6 hours (44 calls on a day the page stays open from morning to night), and nothing at all while
nobody opens the page. What was last fetched is kept in the database (prt_settings), so a restart does
not spend a call either.
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from iosuite_shared import credentials

from app import config, db

APP = config.APP

BASE = "https://dataservice.accuweather.com"
CURRENT_TTL = 60 * 60
HOURLY_TTL = 90 * 60
FORECAST_TTL = 6 * 3600
_lock = threading.Lock()


class WeatherError(Exception):
    pass


# ------------------------------------------------------------------ settings

def api_key() -> str:
    """ACCUWEATHER_API_KEY in the environment, else the key kept with the suite's keys and tokens."""
    if config.ACCUWEATHER_API_KEY:
        return config.ACCUWEATHER_API_KEY
    try:
        return credentials.get(APP, "accuweather_key").strip()
    except Exception:  # noqa: BLE001 - the shared database is away
        return ""


def location_key() -> str:
    return config.ACCUWEATHER_LOCATION or (db.get_setting("accuweather_location") or "").strip()


def settings() -> dict:
    """What Settings › Weather shows (the key itself never leaves the server)."""
    return {"hasKey": bool(api_key()), "keyFromEnv": bool(config.ACCUWEATHER_API_KEY),
            "locationKey": location_key(), "locationFromEnv": bool(config.ACCUWEATHER_LOCATION),
            "locationName": db.get_setting("accuweather_location_name") or "",
            "units": db.get_setting("weather_units") or "metric", "enabled": bool(api_key() and location_key())}


def save(changes: dict, by: str = None) -> None:
    """{key?, locationKey?, locationName?, units?}: an empty key or location clears it; a change empties the cache.
    `by`: who changed the key."""
    if "key" in changes and not config.ACCUWEATHER_API_KEY:
        credentials.put(APP, "accuweather_key", (changes["key"] or "").strip(), by=by)
    if "locationKey" in changes and not config.ACCUWEATHER_LOCATION:
        db.set_setting("accuweather_location", str(changes["locationKey"] or "").strip() or None)
        db.set_setting("accuweather_location_name", (changes.get("locationName") or "").strip() or None)
    if "units" in changes:
        if changes["units"] not in ("metric", "imperial"):
            raise WeatherError("units: metric or imperial")
        db.set_setting("weather_units", changes["units"])
    forget()


def forget() -> None:
    for k in ("weather_current", "weather_forecast", "weather_hourly"):
        db.set_setting(k, None)


# ------------------------------------------------------------------ AccuWeather

def _get(path: str, **params) -> object:
    """One call to AccuWeather. Replaced in the tests."""
    params["apikey"] = api_key()
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "iostart"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise WeatherError("AccuWeather refused the API key")
        if e.code == 503:
            raise WeatherError("AccuWeather: the key's daily allowance is used up (try again tomorrow)")
        raise WeatherError(f"AccuWeather answered {e.code}")
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise WeatherError(f"Could not reach AccuWeather: {str(e)[:120]}")


def search(q: str, key: str = "") -> list[dict]:
    """Places matching a city name (Settings › Weather), with the key the forecast is fetched by."""
    q = (q or "").strip()
    if not q:
        return []
    if not (key or api_key()):
        raise WeatherError("An API key first")
    if key:  # trying a key before it is saved
        params = {"q": q, "apikey": key}
        url = f"{BASE}/locations/v1/cities/search?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "iostart"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                found = json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            raise WeatherError("AccuWeather refused the API key" if e.code == 401 else f"AccuWeather answered {e.code}")
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            raise WeatherError(f"Could not reach AccuWeather: {str(e)[:120]}")
    else:
        found = _get("/locations/v1/cities/search", q=q)
    out = []
    for p in found if isinstance(found, list) else []:
        out.append({"key": str(p.get("Key")), "name": p.get("LocalizedName") or "",
                    "region": (p.get("AdministrativeArea") or {}).get("LocalizedName") or "",
                    "country": (p.get("Country") or {}).get("LocalizedName") or ""})
    return out[:10]


def _cached(name: str, ttl: int, fetch):
    """The stored answer while it is younger than ttl; else a fresh one, stored. A failed fetch keeps the old answer
    (marked stale) rather than a hole on the page."""
    raw = db.get_setting(name)
    old = json.loads(raw) if raw else None
    now = int(time.time())
    if old and now - old.get("at", 0) < ttl:
        return old
    with _lock:
        raw = db.get_setting(name)  # another request may have fetched it meanwhile
        old = json.loads(raw) if raw else None
        if old and now - old.get("at", 0) < ttl:
            return old
        try:
            data = fetch()
        except WeatherError as e:
            if old:
                return {**old, "stale": True, "error": str(e)}
            raise
        fresh = {"at": now, "data": data}
        db.set_setting(name, json.dumps(fresh))
        return fresh


def _temp(t: dict | None, units: str) -> float | None:
    if not t:
        return None
    v = (t.get("Metric") if units == "metric" else t.get("Imperial")) or {}
    return v.get("Value")


def _fetch_current() -> dict:
    data = _get(f"/currentconditions/v1/{location_key()}", details="true")
    c = data[0] if isinstance(data, list) and data else {}
    return {"text": c.get("WeatherText"), "icon": c.get("WeatherIcon"), "isDay": c.get("IsDayTime", True),
            "temp": {"metric": _temp(c.get("Temperature"), "metric"), "imperial": _temp(c.get("Temperature"), "imperial")},
            "feels": {"metric": _temp(c.get("RealFeelTemperature"), "metric"), "imperial": _temp(c.get("RealFeelTemperature"), "imperial")},
            "humidity": c.get("RelativeHumidity"), "uv": c.get("UVIndex"),
            "wind": {"metric": (((c.get("Wind") or {}).get("Speed") or {}).get("Metric") or {}).get("Value"),
                     "imperial": (((c.get("Wind") or {}).get("Speed") or {}).get("Imperial") or {}).get("Value")},
            "observed": c.get("LocalObservationDateTime"), "link": c.get("Link")}


def _fetch_forecast() -> dict:
    data = _get(f"/forecasts/v1/daily/5day/{location_key()}", metric="true")
    days = []
    for d in (data.get("DailyForecasts") or []) if isinstance(data, dict) else []:
        t = d.get("Temperature") or {}
        day = d.get("Day") or {}
        days.append({"date": (d.get("Date") or "")[:10], "min": (t.get("Minimum") or {}).get("Value"), "max": (t.get("Maximum") or {}).get("Value"),
                     "icon": day.get("Icon"), "text": day.get("IconPhrase"), "rain": day.get("PrecipitationProbability")})
    return {"headline": ((data.get("Headline") or {}).get("Text") if isinstance(data, dict) else None), "days": days,
            "link": (data.get("Headline") or {}).get("Link") if isinstance(data, dict) else None}


def _fetch_hourly() -> dict:
    data = _get(f"/forecasts/v1/hourly/12hour/{location_key()}", metric="true")
    hours = []
    for x in data if isinstance(data, list) else []:
        hours.append({"t": x.get("DateTime"), "icon": x.get("WeatherIcon"), "text": x.get("IconPhrase"),
                      "temp": (x.get("Temperature") or {}).get("Value"), "rain": x.get("PrecipitationProbability"),
                      "wet": bool(x.get("HasPrecipitation")), "kind": x.get("PrecipitationType")})
    return {"hours": hours}


def current() -> dict:
    """What the widget draws: {enabled, location, units, current, forecast, hourly}. The forecasts' temperatures come in °C
    (AccuWeather gives one unit per call); the page converts for imperial."""
    s = settings()
    if not s["enabled"]:
        return {"enabled": False}
    cur = _cached("weather_current", CURRENT_TTL, _fetch_current)
    fc = _cached("weather_forecast", FORECAST_TTL, _fetch_forecast)
    try:  # the next hours are a bonus: a key or plan without them still shows the rest
        hr = _cached("weather_hourly", HOURLY_TTL, _fetch_hourly)
    except WeatherError:
        hr = None
    return {"enabled": True, "location": s["locationName"], "units": s["units"],
            "current": cur["data"], "currentAt": cur["at"], "forecast": fc["data"], "forecastAt": fc["at"],
            "hourly": hr["data"]["hours"] if hr else [],
            "stale": bool(cur.get("stale") or fc.get("stale")), "error": cur.get("error") or fc.get("error")}
