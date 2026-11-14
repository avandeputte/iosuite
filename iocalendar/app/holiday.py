"""Public holidays: shared, read-only Holidays calendars (kind 'holidays'), one per country the family follows.

The dates come from the `holidays` package, worked out on the server (nothing is fetched): last year to a few years
ahead, as all-day events marked free, made again every day so the years move along. Settings › Holidays and birthdays picks the
countries and, for each, the region (a state, province...) and the language of the names; HOLIDAYS_COUNTRY (one code or
several, comma-separated) / HOLIDAYS_REGION / HOLIDAYS_LANGUAGE in the environment give the first ones. Until an admin
chooses, the country is the one of the family's time zone (Europe/Brussels: Belgium), else the United States. Because each is an ordinary calendar here, the web app, CalDAV, the
subscription links, the REST API and MCP all show them, and each account can hide any of them like any other calendar.
"""
import datetime as dt
import functools
import hashlib
import importlib.resources
import json
import logging
import re
import threading
import time
from pathlib import Path

from icalendar import Event

from app import config, db, ical, model
from iosuite_shared.errors import Invalid

log = logging.getLogger("iocalendar.holidays")
SYNC_EVERY = 24 * 3600
YEARS_BACK, YEARS_AHEAD = 1, 3
COLORS = ("#1e8e3e", "#c26401", "#7b1fa2", "#00838f", "#ad1457", "#5d4037")  # one per country, in order
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
        raise Invalid(f"No holidays known for country '{code}'")
    h = _lib().country_holidays(code)
    names = {}
    for alias, sub in (getattr(h, "subdivisions_aliases", None) or {}).items():
        names.setdefault(sub, alias)
    regions = [{"code": s, "name": names.get(s) or s} for s in getattr(h, "subdivisions", ())]
    regions.sort(key=lambda r: r["name"].lower())
    return {"code": code, "name": next((c["name"] for c in countries() if c["code"] == code), code), "regions": regions,
            "languages": list(getattr(h, "supported_languages", ()) or ()), "defaultLanguage": getattr(h, "default_language", None)}


# ------------------------------------------------------------------ settings

OFF = ("OFF", "NONE", "0", "NO")


def _from_env() -> tuple[list[dict], bool]:
    """HOLIDAYS_COUNTRY (one code or several, comma-separated; HOLIDAYS_REGION and HOLIDAYS_LANGUAGE go with the first),
    else the country of the family's time zone, else the United States."""
    codes = [c.strip().upper() for c in (config.HOLIDAYS_COUNTRY or "").split(",") if c.strip()]
    if any(c in OFF for c in codes):
        return [], False
    if not codes:
        return [{"country": country_for_tz(ical.default_tz()) or "US", "region": None, "language": None}], True
    items = [{"country": c, "region": None, "language": None} for c in codes]
    items[0].update(region=config.HOLIDAYS_REGION or None, language=config.HOLIDAYS_LANGUAGE or None)
    return items, False


def _clean(items) -> list[dict]:
    """Known countries only, once each; a region or language the country does not have is dropped."""
    out, seen = [], set()
    for it in items or []:
        c = str((it or {}).get("country") or "").upper()
        if c not in supported() or c in seen:
            continue
        seen.add(c)
        r = (it.get("region") or "").upper() or None
        out.append({"country": c, "region": r if r in supported()[c] else None, "language": it.get("language") or None})
    return out


def settings() -> dict:
    """{items: [{country, region, language}], guessed}: one Holidays calendar per item; no items, none."""
    raw = db.get_setting("holidays_countries")
    guessed = False
    if raw is None:  # never chosen: the environment, else the time zone's country
        items, guessed = _from_env()
    else:
        try:
            items = json.loads(raw)
        except ValueError:
            items = []
    items = _clean(items)
    return {"items": items, "guessed": guessed and bool(items)}


def _where(it: dict) -> str:
    info = country_info(it["country"])
    region = next((r["name"] for r in info["regions"] if r["code"] == it["region"]), it["region"]) if it["region"] else None
    return info["name"] + (f", {region}" if region else "")


def public_settings() -> dict:
    s = settings()
    cals = {c["slug"]: c["id"] for c in holiday_calendars()}
    items = []
    for it in s["items"]:
        info = country_info(it["country"])
        items.append({**it, "countryName": info["name"], "where": _where(it), "calendar": cals.get(_slug(it["country"])),
                      "regionName": next((r["name"] for r in info["regions"] if r["code"] == it["region"]), None)})
    return {"items": items, "guessed": s["guessed"], "lastSync": dict(_state)}


def _check(it) -> dict:
    if not isinstance(it, dict):
        raise Invalid("Each entry is {country, region?, language?}")
    c = str(it.get("country") or "").strip().upper()
    if c not in supported():
        raise Invalid(f"No holidays known for country '{it.get('country') or ''}'")
    r = str(it.get("region") or "").strip().upper() or None
    if r and r not in supported()[c]:
        raise Invalid(f"'{it.get('region')}' is not a region of {c}")
    lang = str(it.get("language") or "").strip() or None
    if lang and lang not in country_info(c)["languages"]:
        raise Invalid(f"Holiday names for {c} come in: " + ", ".join(country_info(c)["languages"]))
    return {"country": c, "region": r, "language": lang}


def save_settings(items) -> None:
    """The whole list: [{country, region?, language?}], one Holidays calendar each; [] switches them all off."""
    if not isinstance(items, list):
        raise Invalid("items: a list of {country, region?, language?}")
    out = [_check(it) for it in items]
    dup = {c for c in (x["country"] for x in out) if [x["country"] for x in out].count(c) > 1}
    if dup:
        raise Invalid("Each country once: " + ", ".join(sorted(dup)))
    db.set_setting("holidays_countries", json.dumps(out))


def set_country(country: str, region=None, language=None) -> None:
    """Add a country, or change the region or language of one already there."""
    items = [x for x in settings()["items"] if x["country"] != str(country or "").strip().upper()]
    new = _check({"country": country, "region": region, "language": language})
    old = [x["country"] for x in settings()["items"]]
    items.insert(old.index(new["country"]) if new["country"] in old else len(items), new)
    save_settings(items)


def remove_country(country: str) -> None:
    c = str(country or "").strip().upper()
    items = settings()["items"]
    if c not in [x["country"] for x in items]:
        raise Invalid(f"No Holidays calendar for '{country}'")
    save_settings([x for x in items if x["country"] != c])


# ------------------------------------------------------------------ the Holidays calendars

def _slug(country: str) -> str:
    return f"holidays-{country.lower()}"


def holiday_calendars() -> list[dict]:
    return db.q("SELECT * FROM cal_calendars WHERE kind = 'holidays' AND owner_id IS NULL ORDER BY id")


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


def _fill(it: dict, cal: dict | None, n: int) -> tuple[int, int]:
    """One country's calendar (made when missing): (holidays, changes)."""
    found = dates(it["country"], it["region"], it["language"])
    where = _where(it)
    want = f"Public holidays: {where}"
    if not cal:
        name = f"Holidays ({country_info(it['country'])['name']})"
        cid = model.create_calendar(None, name, want, COLORS[n % len(COLORS)], kind="holidays", slug=_slug(it["country"]))
        cal = model.calendar(cid)
    elif cal.get("description") != want and (cal.get("description") or "").startswith("Public holidays"):
        model.update_calendar(cal["id"], description=want)
    have = {r["uid"]: r for r in model.rows(cal["id"], listing=True)}
    seen, changed = set(), 0
    for d, name in found:
        uid = _uid(it["country"], it["region"], d, name)
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
    return len(seen), changed


def sync() -> dict:
    """Bring the Holidays calendars up to date with the settings: one per country, made when missing, removed when
    its country is no longer in the list."""
    with _lock:
        items = settings()["items"]
        cals = {c["slug"]: c for c in holiday_calendars()}
        count, changed, errors = 0, 0, []
        for n, it in enumerate(items):
            try:
                k, ch = _fill(it, cals.pop(_slug(it["country"]), None), n)
                count, changed = count + k, changed + ch
            except Exception as e:  # noqa: BLE001 - the other countries still fill
                errors.append(f"{it['country']}: {type(e).__name__}: {e}")
        for cal in cals.values():  # countries taken off the list
            model.delete_calendar(cal["id"])
            changed += 1
        error = "; ".join(errors)[:300] or None
        if error:
            log.warning("holidays: %s", error)
        _state.update(synced=int(time.time()) if items else None, error=error, count=count if items else None)
        return {"ok": not errors, "count": count, "changed": changed, "calendars": len(items), **({"error": error} if error else {})}


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
