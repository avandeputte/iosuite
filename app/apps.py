"""The apps of the suite: what the start page shows a tile for, and where each one is.

Where an app lives comes, in this order, from the environment (IOPIX_URL and friends: wins, and Settings shows it as
read-only), from what an admin saved in Settings › Apps, or, failing both, from the host the page was reached on with
the app's usual port (the Proxmox and standalone installs on one box). The list is static here; the dynamic content
each tile may show later (today's events, the newest photos…) is meant to come from a per-app module beside this one
that asks the app over its API with the shared session.
"""
from urllib.parse import urlsplit

from app import config, db

# key, name (as the app writes it), what it is, its usual port, and the colour of its name on the page (the app's own)
CATALOGUE = [
    {"key": "iopix", "name": "ioPix", "tagline": "Photos", "port": 8600, "color": "#3b4a8c", "icon": "static/icons/apps/iopix.svg"},
    {"key": "iohealth", "name": "ioHealth", "tagline": "Health and fitness", "port": 47800, "color": "#e8445a", "icon": "static/icons/apps/iohealth.svg"},
    {"key": "iocalendar", "name": "ioCalendar", "tagline": "Calendar", "port": 8620, "color": "#963522", "icon": "static/icons/apps/iocalendar.svg"},
    {"key": "iocontacts", "name": "ioContacts", "tagline": "Contacts", "port": 8610, "color": "#4f2f7d", "icon": "static/icons/apps/iocontacts.svg"},
    {"key": "ionotes", "name": "ioNotes", "tagline": "Notes", "port": 8610, "color": "#1c5a5e", "icon": "static/icons/apps/ionotes.svg"},
]
KEYS = [a["key"] for a in CATALOGUE]


def saved_url(key: str) -> str:
    return (db.get_setting(f"{key}_url") or "").strip().rstrip("/")


def url_for(key: str, host: str = "") -> str:
    """The address of an app: the environment, Settings, or this host with the app's usual port."""
    if config.APP_URLS.get(key):
        return config.APP_URLS[key]
    saved = saved_url(key)
    if saved:
        return saved
    app = next(a for a in CATALOGUE if a["key"] == key)
    hostname = urlsplit(f"//{host}").hostname or "localhost"
    if ":" in hostname:  # IPv6
        hostname = f"[{hostname}]"
    return f"http://{hostname}:{app['port']}"


def tiles(host: str = "") -> list[dict]:
    """What the page draws: every app of the catalogue with its address. An admin can hide one in Settings
    ("<key>_hidden"); hidden tiles stay in the list, marked, so Settings can show them again."""
    out = []
    for a in CATALOGUE:
        out.append({**a, "url": url_for(a["key"], host), "hidden": db.get_setting(f"{a['key']}_hidden") == "1"})
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
    """Settings › Apps: per app, the saved address (if any), whether the environment overrides it, and visibility."""
    return [{"key": a["key"], "name": a["name"], "url": saved_url(a["key"]), "envUrl": config.APP_URLS.get(a["key"]) or None,
             "port": a["port"], "hidden": db.get_setting(f"{a['key']}_hidden") == "1"} for a in CATALOGUE]


def save(changes: dict) -> None:
    """{iopix: {url?, hidden?}, ...}: a URL (http or https, no path needed; empty: back to the default) and the switch."""
    for key, c in changes.items():
        if key not in KEYS or not isinstance(c, dict):
            raise ValueError(f"no such app: {key}")
        if "url" in c:
            u = (c["url"] or "").strip().rstrip("/")
            if u and not (u.startswith("http://") or u.startswith("https://")):
                raise ValueError(f"{key}: the address starts with http:// or https://")
            db.set_setting(f"{key}_url", u or None)
        if "hidden" in c:
            db.set_setting(f"{key}_hidden", "1" if c["hidden"] else None)
