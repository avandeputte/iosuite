"""The apps of the suite: what the start page shows a tile for, and where each one is.

Every io app registers itself, with its address, in the suite's list of apps in the Shared ioSuite database
(iosuite_shared.suite, table `ios_apps`); the page reads that list and nothing else. An app that has not registered
(not installed, or never started) has no tile. Nobody types an address.

The catalogue below knows the apps the page has widgets for (their icon, colour and line, the page's own); an app it
does not know that registered itself gets a plain tile too, with the name, line, colour and icon it registered.
"""
import logging
import re
import time

from iosuite_shared import suite

from app import db

log = logging.getLogger("iosuite.apps")
SELF = "iosuite"
REGISTRY_TTL = 30  # seconds the suite's list is kept here (asked on every tile, widget and status call)
_registry = {"at": 0.0, "items": {}}

# key, name (as the app writes it), what it is, and the colour of its name on the page (the app's own)
CATALOGUE = [
    {"key": "iopix", "name": "ioPix", "tagline": "Photos", "color": "#3b4a8c", "icon": "static/icons/apps/iopix.svg"},
    {"key": "iohealth", "name": "ioHealth", "tagline": "Health and fitness", "color": "#e8445a", "icon": "static/icons/apps/iohealth.svg"},
    {"key": "iocalendar", "name": "ioCalendar", "tagline": "Calendar", "color": "#963522", "icon": "static/icons/apps/iocalendar.svg"},
    {"key": "iocontacts", "name": "ioContacts", "tagline": "Contacts", "color": "#4f2f7d", "icon": "static/icons/apps/iocontacts.svg"},
    {"key": "ionotes", "name": "ioNotes", "tagline": "Notes", "color": "#1c5a5e", "icon": "static/icons/apps/ionotes.svg"},
]
KEYS = [a["key"] for a in CATALOGUE]
_KEY_RE = re.compile(r"[a-z0-9_-]{1,32}")


def is_key(k) -> bool:
    """An app key as the suite's list writes them (a person's layout may name one that is not registered right now)."""
    return isinstance(k, str) and bool(_KEY_RE.fullmatch(k)) and k != SELF


def registered() -> dict:
    """{app key: entry} from the suite's list (iosuite_shared.suite.apps()), kept REGISTRY_TTL seconds; the last list
    known when the Shared ioSuite database does not answer."""
    now = time.time()
    if now - _registry["at"] > REGISTRY_TTL:
        try:
            _registry["items"] = {a["app"]: a for a in suite.apps()}
        except Exception as e:  # noqa: BLE001 - the Shared ioSuite database is down: the last list known
            log.warning("the suite's list of apps: %s", e)
        _registry["at"] = now
    return _registry["items"]


def forget_registry() -> None:
    _registry["at"] = 0.0


def url_for(key: str, host: str = "") -> str:
    """The address the app registered, or "" when it has not registered (`host` is not used any more)."""
    e = registered().get(key)
    return ((e or {}).get("url") or "").rstrip("/")


def name_of(key: str) -> str:
    known = next((a for a in CATALOGUE if a["key"] == key), None)
    if known:
        return known["name"]
    e = registered().get(key)
    return (e or {}).get("name") or key


def tiles(host: str = "") -> list[dict]:
    """What the page draws: the registered apps with an address, those the page knows first (in its order), then the
    others by name. {key, name, tagline, color, icon, url, version}."""
    reg = registered()
    out = []
    for a in CATALOGUE:
        e = reg.get(a["key"])
        if e and e.get("url"):
            out.append({**a, "url": url_for(a["key"]), "version": e.get("version")})
    for key, e in sorted(reg.items(), key=lambda kv: (kv[1].get("name") or kv[0]).lower()):
        if key in KEYS or key == SELF or not e.get("url"):
            continue
        icon = e.get("icon") or ""
        out.append({"key": key, "name": e.get("name") or key, "tagline": e.get("description") or "",
                    "color": e.get("color") or "#2f3a5a", "icon": icon if icon.startswith("https://") else "static/icons/mark.svg",
                    "url": url_for(key), "version": e.get("version")})
    return out


STRIPS = ("rediscover", "onthisday", "off")


def photo_strip() -> str:
    """The photo strip under the tiles for everyone (Settings › Home page): rediscover (a row of photos at random),
    onthisday, or off; each person may pick another in Customize."""
    v = db.get_setting("photo_strip") or "rediscover"
    return v if v in STRIPS else "rediscover"


def set_photo_strip(v: str) -> None:
    if v not in STRIPS:
        raise ValueError("The photo strip is rediscover, onthisday or off")
    db.set_setting("photo_strip", None if v == "rediscover" else v)
