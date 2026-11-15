"""The weather on the calendar: the forecast on each of the next seven days, and on an event that has a place.

Nothing to set up. The place is the start page's (Settings › Weather on ioStart, asked for at ioStart's
/api/weather/place through the suite's list of apps, as this app's own service account), and the forecast comes from
Open-Meteo (open-meteo.com: free, no key, seven days and more, by the hour). The start page's AccuWeather key is not
spent here: a free key's 50 calls a day already go to the start page, and it has five days only.

An event's place is written by people ("Dentist, Kerkstraat 12, Gent"), so it is looked up with OpenStreetMap's
Nominatim, as ioPix does: an identifying User-Agent, one request a second, and every answer kept (in cal_settings,
a place not found too, asked again after a month), so a place is looked up once. Only the place text leaves the
server, never the event.

Forecasts are kept in memory for an hour per place (rounded to about a kilometre), so a page that redraws does not ask
again. Everything comes back in °C and km/h; the page converts when the start page is set to imperial.
"""
import datetime as dt
import hashlib
import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from iosuite_shared import links

from app import config, db

log = logging.getLogger("iocalendar.weather")
APP = config.APP
PROVIDER = "iostart"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "ioCalendar/1.0 (https://github.com/avandeputte/iosuite/tree/main/iocalendar)"
DAYS = 7
FORECAST_TTL = 3600            # a place's forecast, in memory
HOME_TTL = 6 * 3600            # the start page's place, in memory
MISS_TTL = 30 * 86400          # a place Nominatim did not find is asked again after this long
MAX_PLACE = 300                # characters of a place sent to Nominatim
TIMEOUT = 8

_forecasts: dict = {}          # (lat, lon) rounded -> {"at", "data"}
_home: dict = {}               # {"at", "data"}
_lock = threading.Lock()       # the caches
_net_lock = threading.Lock()   # Nominatim: one request a second, one at a time
_last_geo = [0.0]


class WeatherError(Exception):
    pass


def forget() -> None:
    """Drop what is kept in memory (the tests)."""
    with _lock:
        _forecasts.clear()
        _home.clear()


def _fetch_json(url: str, headers: dict = None):
    """GET one JSON answer. Replaced in the tests."""
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310  fixed https addresses
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise WeatherError(f"{urllib.parse.urlsplit(url).hostname} answered {e.code}")
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        raise WeatherError(f"Could not reach {urllib.parse.urlsplit(url).hostname}: {str(e)[:120]}")


# ------------------------------------------------------------------ places

def geocode(place: str) -> dict | None:
    """{lat, lon, name} for what people typed as a place, or None when OpenStreetMap does not know it. Kept for good."""
    q = " ".join((place or "").split())[:MAX_PLACE]
    if not q or q.lower().startswith(("http://", "https://")):  # a meeting link is not a place
        return None
    key = "wx_place:" + hashlib.sha1(q.lower().encode()).hexdigest()
    raw = db.get_setting(key)
    if raw:
        got = json.loads(raw)
        if got.get("lat") is not None or time.time() - got.get("at", 0) < MISS_TTL:
            return got if got.get("lat") is not None else None
    with _net_lock:
        raw = db.get_setting(key)  # looked up meanwhile by another request
        if raw:
            got = json.loads(raw)
            if got.get("lat") is not None or time.time() - got.get("at", 0) < MISS_TTL:
                return got if got.get("lat") is not None else None
        wait = _last_geo[0] + 1.05 - time.time()
        if wait > 0:
            time.sleep(wait)
        try:
            rows = _fetch_json(f"{GEOCODE_URL}?{urllib.parse.urlencode({'q': q, 'format': 'jsonv2', 'limit': 1})}",
                               {"Accept-Language": "en"})
        finally:
            _last_geo[0] = time.time()
    row = rows[0] if isinstance(rows, list) and rows else None
    try:
        got = {"lat": round(float(row["lat"]), 4), "lon": round(float(row["lon"]), 4),
               "name": (row.get("display_name") or q).split(", ")[0]} if row else {}
    except (KeyError, TypeError, ValueError):
        got = {}
    got["at"] = int(time.time())
    db.set_setting(key, json.dumps(got))
    return got if got.get("lat") is not None else None


def home() -> dict | None:
    """The start page's weather place: {name, units, lat, lon}, or None while ioStart has none (or is not in the suite)."""
    now = time.time()
    with _lock:
        if _home and now - _home["at"] < HOME_TTL:
            return _home["data"]
    try:
        if not links.available(PROVIDER):
            return None
        s = links.json(APP, PROVIDER, "/api/weather/place", timeout=TIMEOUT)
    except Exception as e:  # noqa: BLE001 - ioStart away or older: no weather on the days for now
        log.info("the start page's weather place: %s", e)
        with _lock:
            if _home:
                return _home["data"]
        return None
    data = None
    name = (s.get("name") or "").strip() if isinstance(s, dict) else ""
    if name:
        g = geocode(name)
        if g:
            data = {"name": name.split(", ")[0], "units": s.get("units") or "metric", "lat": g["lat"], "lon": g["lon"]}
    with _lock:
        _home.update(at=now, data=data)
    return data


# ------------------------------------------------------------------ forecasts

def forecast(lat: float, lon: float) -> dict:
    """The next days at a place: {days: [{date, min, max, code, rain}], hours: [{t (epoch s), temp, code, rain}]},
    dates and hours in the place's own time."""
    k = (round(lat, 2), round(lon, 2))
    now = time.time()
    with _lock:
        got = _forecasts.get(k)
        if got and now - got["at"] < FORECAST_TTL:
            return got["data"]
    params = {"latitude": k[0], "longitude": k[1], "timezone": "auto", "forecast_days": DAYS, "timeformat": "unixtime",
              "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
              "hourly": "weather_code,temperature_2m,precipitation_probability"}
    try:
        raw = _fetch_json(f"{FORECAST_URL}?{urllib.parse.urlencode(params)}")
    except WeatherError:
        if got:  # an older answer beats a hole
            return got["data"]
        raise
    off = int(raw.get("utc_offset_seconds") or 0)
    d, hr = raw.get("daily") or {}, raw.get("hourly") or {}
    days = [{"date": dt.datetime.fromtimestamp(t + off, dt.timezone.utc).date().isoformat(), "code": c, "max": hi, "min": lo, "rain": p}
            for t, c, hi, lo, p in zip(d.get("time") or [], d.get("weather_code") or [], d.get("temperature_2m_max") or [],
                                       d.get("temperature_2m_min") or [], d.get("precipitation_probability_max") or [None] * DAYS)]
    hours = [{"t": t, "code": c, "temp": tp, "rain": p}
             for t, c, tp, p in zip(hr.get("time") or [], hr.get("weather_code") or [], hr.get("temperature_2m") or [],
                                    hr.get("precipitation_probability") or [None] * 400)]
    data = {"days": days, "hours": hours, "offset": off}
    with _lock:
        if len(_forecasts) > 500:
            _forecasts.clear()
        _forecasts[k] = {"at": now, "data": data}
    return data


def days() -> dict:
    """What the day headers show: {enabled, place, units, days}."""
    h = home()
    if not h:
        return {"enabled": False, "days": []}
    return {"enabled": True, "place": h["name"], "units": h["units"], "days": forecast(h["lat"], h["lon"])["days"]}


def at_event(place: str, start: str, all_day: bool) -> dict:
    """The weather where and when an event is: {found, place, units, day?, hour?}. `start`: the event's start (a date
    for an all-day event, else an ISO time). Nothing for a place OpenStreetMap does not know, or a day outside the
    forecast."""
    h = home()
    units = h["units"] if h else "metric"
    g = geocode(place)
    if not g:
        return {"found": False, "units": units}
    fc = forecast(g["lat"], g["lon"])
    out = {"found": True, "place": g["name"], "units": units}
    try:
        if all_day:
            date = dt.date.fromisoformat(start[:10]).isoformat()
            t = None
        else:
            t = dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
            if t.tzinfo is None:
                raise ValueError("a time with its offset")
            t = t.timestamp()
            date = None
    except ValueError:
        raise WeatherError("start: a date or an ISO time with its offset")
    if t is not None:
        hour = min((x for x in fc["hours"] if abs(x["t"] - t) <= 1800), key=lambda x: abs(x["t"] - t), default=None)
        if hour:
            out["hour"] = hour
        # the event's day where it is (the daily dates are in the place's time)
        date = dt.datetime.fromtimestamp(t + fc.get("offset", 0), dt.timezone.utc).date().isoformat()
    day = next((x for x in fc["days"] if x["date"] == date), None)
    if day:
        out["day"] = day
    return out
