"""The apps of the suite: what the start page shows a tile for, and where each one is.

Where an app lives comes, in this order, from the environment (IOPIX_URL and friends: wins, and Settings shows it as
read-only), from what an admin saved in Settings › Apps, from the suite's list of apps in the Shared ioSuite database
(each app registers itself there with its address: iothing_auth.suite), or, failing all three, from the host the page
was reached on with the app's usual port (the Proxmox and standalone installs on one box).

The catalogue below knows the suite's apps the page has widgets for; an app it does not know that registered itself
gets a plain tile too (its name, line, colour and icon as it registered them).
"""
import logging
import time
from urllib.parse import urlsplit

from iothing_auth import suite

from app import config, db

log = logging.getLogger("iosuite.apps")
SELF = "iosuite"
REGISTRY_TTL = 30  # seconds the suite's list is kept here (asked on every tile, widget and status call)
_registry = {"at": 0.0, "items": {}}

# key, name (as the app writes it), what it is, its usual port, and the colour of its name on the page (the app's own)
CATALOGUE = [
    {"key": "iopix", "name": "ioPix", "tagline": "Photos", "port": 8600, "color": "#3b4a8c", "icon": "static/icons/apps/iopix.svg"},
    {"key": "iohealth", "name": "ioHealth", "tagline": "Health and fitness", "port": 47800, "color": "#e8445a", "icon": "static/icons/apps/iohealth.svg"},
    {"key": "iocalendar", "name": "ioCalendar", "tagline": "Calendar", "port": 8620, "color": "#963522", "icon": "static/icons/apps/iocalendar.svg"},
    {"key": "iocontacts", "name": "ioContacts", "tagline": "Contacts", "port": 8610, "color": "#4f2f7d", "icon": "static/icons/apps/iocontacts.svg"},
    {"key": "ionotes", "name": "ioNotes", "tagline": "Notes", "port": 8610, "color": "#1c5a5e", "icon": "static/icons/apps/ionotes.svg"},
]
KEYS = [a["key"] for a in CATALOGUE]


def registered() -> dict:
    """{app key: entry} from the suite's list (iothing_auth.suite.apps()), kept REGISTRY_TTL seconds; the last list
    known when the Shared ioSuite database does not answer."""
    now = time.time()
    if now - _registry["at"] > REGISTRY_TTL:
        try:
            _registry["items"] = {a["app"]: a for a in suite.apps()}
        except Exception as e:  # noqa: BLE001 - an older Shared ioSuite database (no suite_apps yet), or down
            log.debug("the suite's list of apps: %s", e)
        _registry["at"] = now
    return _registry["items"]


def forget_registry() -> None:
    _registry["at"] = 0.0


def catalogue() -> list[dict]:
    """The known apps, then any other app that registered itself (with an address) in the suite's list."""
    out = list(CATALOGUE)
    for key, e in sorted(registered().items(), key=lambda kv: (kv[1]["name"] or kv[0]).lower()):
        if key in KEYS or key == SELF or not e.get("url"):
            continue
        icon = e.get("icon") or ""
        out.append({"key": key, "name": e["name"] or key, "tagline": e.get("description") or "", "port": None,
                    "color": e.get("color") or "#2f3a5a", "icon": icon if icon.startswith("https://") else "static/icons/mark.svg"})
    return out


def _find(key: str) -> dict | None:
    return next((a for a in catalogue() if a["key"] == key), None)


def name_of(key: str) -> str:
    a = _find(key)
    return a["name"] if a else key


def registered_url(key: str) -> str:
    e = registered().get(key)
    return ((e or {}).get("url") or "").rstrip("/")


def saved_url(key: str) -> str:
    return (db.get_setting(f"{key}_url") or "").strip().rstrip("/")


def url_for(key: str, host: str = "") -> str:
    """The address of an app: the environment, Settings, the suite's list, or this host with the app's usual port."""
    if config.APP_URLS.get(key):
        return config.APP_URLS[key]
    saved = saved_url(key)
    if saved:
        return saved
    found = registered_url(key)
    if found:
        return found
    app = _find(key)
    if not app or not app.get("port"):
        return ""
    hostname = urlsplit(f"//{host}").hostname or "localhost"
    if ":" in hostname:  # IPv6
        hostname = f"[{hostname}]"
    return f"http://{hostname}:{app['port']}"


def tiles(host: str = "") -> list[dict]:
    """What the page draws: every app of the catalogue with its address. An admin can hide one in Settings
    ("<key>_hidden"); hidden tiles stay in the list, marked, so Settings can show them again."""
    out, reg = [], registered()
    for a in catalogue():
        e = reg.get(a["key"]) or {}
        out.append({**a, "url": url_for(a["key"], host), "hidden": db.get_setting(f"{a['key']}_hidden") == "1",
                    "registered": bool(e), "version": e.get("version")})
    return out


STRIPS = ("rediscover", "onthisday", "off")


def photo_strip() -> str:
    """The photo strip under the tiles (Settings › Apps): rediscover (a row of photos at random), onthisday, or off."""
    v = db.get_setting("photo_strip") or "rediscover"
    return v if v in STRIPS else "rediscover"


def set_photo_strip(v: str) -> None:
    if v not in STRIPS:
        raise ValueError("The photo strip is rediscover, onthisday or off")
    db.set_setting("photo_strip", None if v == "rediscover" else v)


def settings() -> list[dict]:
    """Settings › Apps: per app, the saved address (if any), whether the environment overrides it, the address the app
    registered in the suite's list (and when it was last up there), and visibility."""
    reg = registered()
    return [{"key": a["key"], "name": a["name"], "icon": a["icon"], "url": saved_url(a["key"]),
             "envUrl": config.APP_URLS.get(a["key"]) or None, "suiteUrl": registered_url(a["key"]) or None,
             "version": (reg.get(a["key"]) or {}).get("version"), "lastSeen": (reg.get(a["key"]) or {}).get("lastSeen"),
             "port": a["port"], "hidden": db.get_setting(f"{a['key']}_hidden") == "1"} for a in catalogue()]


def save(changes: dict) -> None:
    """{iopix: {url?, hidden?}, ...}: a URL (http or https, no path needed; empty: back to the default) and the switch."""
    keys = [a["key"] for a in catalogue()]
    for key, c in changes.items():
        if key not in keys or not isinstance(c, dict):
            raise ValueError(f"no such app: {key}")
        if "url" in c:
            u = (c["url"] or "").strip().rstrip("/")
            if u and not (u.startswith("http://") or u.startswith("https://")):
                raise ValueError(f"{key}: the address starts with http:// or https://")
            db.set_setting(f"{key}_url", u or None)
        if "hidden" in c:
            db.set_setting(f"{key}_hidden", "1" if c["hidden"] else None)
