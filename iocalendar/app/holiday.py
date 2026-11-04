"""Public holidays: a shared, read-only Holidays calendar (kind 'holidays') for the family's country and region.

The dates come from the `holidays` package, worked out on the server (nothing is fetched): last year to a few years
ahead, as all-day events marked free, made again every day so the years move along. Settings › Holidays picks the
country, the region (a state, province...) and the language of the names; HOLIDAYS_COUNTRY / HOLIDAYS_REGION /
HOLIDAYS_LANGUAGE in the environment give the first ones. Until an admin chooses, the country is the one of the family's
time zone (Europe/Brussels: Belgium), else the United States. Because it is an ordinary calendar here, the web app, CalDAV, the
subscription links, the REST API and MCP all show it, and each account can hide it like any other calendar.
"""
import datetime as dt
import functools
import hashlib
import importlib.resources
import logging
import re
import threading
import time
from pathlib import Path

from icalendar import Event

from app import config, db, ical, model

log = logging.getLogger("iocalendar.holidays")
SYNC_EVERY = 24 * 3600
YEARS_BACK, YEARS_AHEAD = 1, 3
COLOR = "#1e8e3e"
_lock = threading.Lock()
_state: dict = {"synced": None, "error": None, "count": None}


def _lib():
    import holidays  # imported when needed: a few hundred country modules
    return holidays


# ------------------------------------------------------------------ countries and regions

def _tab(name: str) -> str:
    for p in (Path("/usr/share/zoneinfo") / name,):
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
    try:
        return (importlib.resources.files("tzdata") / "zoneinfo" / name).read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - no tzdata either: no guesses, no names
        return ""


@functools.lru_cache(maxsize=1)
def _country_names() -> dict:
    out = {}
    for line in _tab("iso3166.tab").splitlines():
        if line and not line.startswith("#") and "\t" in line:
            code, name = line.split("\t", 1)
            out[code.strip()] = name.strip()
    return out


def country_for_tz(tzname: str | None) -> str | None:
    """The country of a time zone (zone.tab), when the holidays package knows it."""
    if not tzname:
        return None
    for line in _tab("zone.tab").splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and not line.startswith("#") and parts[2].strip() == tzname:
            code = parts[0].strip()
            return code if code in supported() else None
    return None


@functools.lru_cache(maxsize=1)
def supported() -> dict:
    """{code: [region codes]} for every country the package knows (two-letter codes only)."""
    return {k: list(v) for k, v in _lib().list_supported_countries(include_aliases=False).items()}


@functools.lru_cache(maxsize=1)
def countries() -> list[dict]:
    """[{code, name}] sorted by name, for the Settings list."""
    names = _country_names()
    reg = {v[1]: re.sub(r"(?<=[a-z])(?=[A-Z])", " ", v[0]) for v in _lib().registry.COUNTRIES.values()}
    return sorted(({"code": c, "name": names.get(c) or reg.get(c) or c} for c in supported()), key=lambda x: x["name"].lower())


@functools.lru_cache(maxsize=256)
def country_info(code: str) -> dict:
    """{code, name, regions: [{code, name}], languages: [...], defaultLanguage} of one country."""
    code = (code or "").upper()
    if code not in supported():
        raise ValueError(f"No holidays known for country '{code}'")
    h = _lib().country_holidays(code)
    names = {}
    for alias, sub in (getattr(h, "subdivisions_aliases", None) or {}).items():
        names.setdefault(sub, alias)
    regions = [{"code": s, "name": names.get(s) or s} for s in getattr(h, "subdivisions", ())]
    regions.sort(key=lambda r: r["name"].lower())
    return {"code": code, "name": next((c["name"] for c in countries() if c["code"] == code), code), "regions": regions,
            "languages": list(getattr(h, "supported_languages", ()) or ()), "defaultLanguage": getattr(h, "default_language", None)}


# ------------------------------------------------------------------ settings

def settings() -> dict:
    """{country, region, language, enabled, guessed}: country None means switched off."""
    stored = db.get_setting("holidays_country")
    guessed = False
    if stored is None:  # never chosen: the environment, else the time zone's country
        country = (config.HOLIDAYS_COUNTRY or "").upper() or None
        if country in ("OFF", "NONE", "0", "NO"):
            country = None
        elif not country:
            country, guessed = country_for_tz(ical.default_tz()) or "US", True
    else:
        country = stored.upper() or None
    region = db.get_setting("holidays_region", config.HOLIDAYS_REGION or "") or None
    language = db.get_setting("holidays_language", config.HOLIDAYS_LANGUAGE or "") or None
    if country and country not in supported():
        country = None
    if country and region and region not in supported().get(country, []):
        region = None
    return {"country": country, "region": region, "language": language, "enabled": bool(country), "guessed": guessed and bool(country)}


def public_settings() -> dict:
    s = settings()
    out = {**s, "lastSync": dict(_state)}
    if s["country"]:
        info = country_info(s["country"])
        out.update(countryName=info["name"], regions=info["regions"], languages=info["languages"],
                   regionName=next((r["name"] for r in info["regions"] if r["code"] == s["region"]), None))
    return out


def save_settings(country=None, region=None, language=None) -> None:
    """country "" switches the Holidays calendar off; region and language "" go back to the country's own."""
    if country is not None:
        c = str(country).strip().upper()
        if c and c not in supported():
            raise ValueError(f"No holidays known for country '{country}'")
        if c != (settings()["country"] or ""):
            db.set_setting("holidays_region", "")  # another country's regions differ
            db.set_setting("holidays_language", "")
        db.set_setting("holidays_country", c)
    c = settings()["country"]
    if region is not None:
        r = str(region).strip().upper()
        if r and (not c or r not in supported().get(c, [])):
            raise ValueError(f"'{region}' is not a region of {c}")
        db.set_setting("holidays_region", r)
    if language is not None:
        lang = str(language).strip()
        if lang and c and lang not in country_info(c)["languages"]:
            raise ValueError(f"Holiday names for {c} come in: " + ", ".join(country_info(c)["languages"]))
        db.set_setting("holidays_language", lang)


# ------------------------------------------------------------------ the Holidays calendar

def holiday_calendar() -> dict | None:
    return db.one("SELECT * FROM calendars WHERE kind = 'holidays' AND owner_id IS NULL LIMIT 1")


def dates(country: str, region: str | None = None, language: str | None = None, years=None) -> list[tuple[dt.date, str]]:
    if years is None:
        y = dt.date.today().year
        years = range(y - YEARS_BACK, y + YEARS_AHEAD + 1)
    h = _lib().country_holidays(country, subdiv=region or None, years=list(years), language=language or None)
    out = []
    for d, names in sorted(h.items()):
        for n in str(names).split("; "):  # two holidays on one day: one event each
            if n.strip():
                out.append((d, n.strip()))
    return out


def _uid(country: str, region: str | None, d: dt.date, name: str) -> str:
    k = hashlib.sha1(f"{country}/{region or ''}/{d.isoformat()}/{name}".encode()).hexdigest()[:12]
    return f"holiday-{d:%Y%m%d}-{k}@iocalendar"


def _event(uid: str, d: dt.date, name: str, where: str):
    cal = ical.new_calendar()
    ev = Event()
    ev.add("UID", uid)
    ev.add("DTSTAMP", dt.datetime(2000, 1, 1, tzinfo=ical.UTC))  # the same object every time: no change to sync
    ev.add("DTSTART", d)
    ev.add("DTEND", d + dt.timedelta(days=1))
    ev.add("SUMMARY", name)
    ev.add("TRANSP", "TRANSPARENT")
    ev.add("CATEGORIES", ["Holidays"])
    ev.add("DESCRIPTION", f"Public holiday ({where})")
    ev.add("SEQUENCE", 0)
    cal.add_component(ev)
    return ical.finish(cal)


def sync() -> dict:
    """Bring the Holidays calendar up to date with the settings (made when missing; removed when switched off)."""
    with _lock:
        s = settings()
        cal = holiday_calendar()
        if not s["country"]:
            if cal:
                model.delete_calendar(cal["id"])
            _state.update(synced=None, error=None, count=None)
            return {"ok": True, "count": 0, "removed": bool(cal)}
        try:
            info = country_info(s["country"])
            found = dates(s["country"], s["region"], s["language"])
        except Exception as e:  # noqa: BLE001
            _state.update(error=f"{type(e).__name__}: {e}"[:300])
            log.warning("holidays: %s", _state["error"])
            return {"ok": False, "error": _state["error"]}
        where = info["name"] + (f", {next((r['name'] for r in info['regions'] if r['code'] == s['region']), s['region'])}" if s["region"] else "")
        if not cal:
            cid = model.create_calendar(None, "Holidays", f"Public holidays: {where}", COLOR, kind="holidays", slug="holidays")
            cal = model.calendar(cid)
        else:
            want = f"Public holidays: {where}"
            if cal.get("description") != want and (cal.get("description") or "").startswith("Public holidays"):
                model.update_calendar(cal["id"], description=want)
        have = {r["uid"]: r for r in model.rows(cal["id"])}
        seen, changed = set(), 0
        for d, name in found:
            uid = _uid(s["country"], s["region"], d, name)
            if uid in seen:
                continue
            seen.add(uid)
            obj = _event(uid, d, name, where)
            old = have.get(uid)
            if old and old["etag"] == ical.etag_of(ical.text(obj)):
                continue
            model.save(cal["id"], obj, old["id"] if old else None)
            changed += 1
        for uid, r in have.items():
            if uid not in seen:
                model.delete(r["id"])
                changed += 1
        _state.update(synced=int(time.time()), error=None, count=len(seen))
        return {"ok": True, "count": len(seen), "changed": changed}


def start_sync() -> None:
    """Every day (the first a little after start), so the years roll along."""
    def loop():
        time.sleep(5)
        while True:
            try:
                sync()
            except Exception as e:  # noqa: BLE001
                log.warning("holiday sync failed: %s", e)
            time.sleep(SYNC_EVERY)
    threading.Thread(target=loop, name="holidays", daemon=True).start()
