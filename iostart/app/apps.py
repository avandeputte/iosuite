"""The apps of the suite: what the start page shows a tile for, and where each one is.

Every io app registers itself, with its address, in the suite's list of apps in the Shared ioSuite database
(iosuite_shared.suite, table `ios_apps`); the page reads that list and nothing else. An app that has not registered
(not installed, or never started) has no tile. Nobody types an address.

Each tile shows what the app registered: its name, line, colour and icon (served by the app itself, at
/static/icons/mark.svg). A person sees only the apps they may use (iosuite_shared.suite.visible: a role there that is not
"none"), and an admin tool (ioDNS) only where they are its admin (listed in the gear menu, not as a tile). ORDER is only where the apps the page has widgets for come; any other app follows by name.
"""
import logging
import re
import time

from iosuite_shared import suite, users

from app import db
from iosuite_shared.errors import Invalid

log = logging.getLogger("iostart.apps")
SELF = "iostart"
REGISTRY_TTL = 30  # seconds the suite's list is kept here (asked on every tile, widget and status call)
_registry = {"at": 0.0, "items": {}}

# the apps the page has widgets for, in the order their tiles come; any other registered app follows by name
ORDER = ["iopix", "iohealth", "iocalendar", "iotask", "iocontact", "ionote"]
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


def url_for(key: str) -> str:
    """The address the app registered, or "" when it has not registered."""
    e = registered().get(key)
    return ((e or {}).get("url") or "").rstrip("/")


def name_of(key: str) -> str:
    e = registered().get(key)
    return (e or {}).get("name") or key


def may_see(user, entry: dict) -> bool:
    """Whether this person sees the app: a role there that is not "none" (an admin tool is none for everybody but the
    suite admins; the same rule as iosuite_shared.suite.visible, on the list kept here)."""
    return users.role_of(user, entry["app"]) != "none"


def tiles(user=None) -> list[dict]:
    """What the page draws: the registered apps with an address (the ones `user` may see, when given), those in ORDER
    first, then the others by name. {key, name, tagline, color, icon, url, version, adminTool}, all as the app
    registered them."""
    reg = {k: e for k, e in registered().items() if k != SELF and e.get("url") and (user is None or may_see(user, e))}
    keys = [k for k in ORDER if k in reg] + sorted((k for k in reg if k not in ORDER), key=lambda k: (reg[k].get("name") or k).lower())
    return [{"key": k, "name": reg[k].get("name") or k, "tagline": reg[k].get("description") or "",
             "color": reg[k].get("color") or "#2f3a5a", "icon": reg[k].get("icon") or "static/icons/mark.svg",
             "url": url_for(k), "version": reg[k].get("version"), "adminTool": bool(reg[k].get("adminTool"))} for k in keys]


STRIPS = ("rediscover", "onthisday", "off")


def photo_strip() -> str:
    """The photo strip under the tiles for everyone (Settings › Home page): rediscover (a row of photos at random),
    onthisday, or off; each person may pick another in Customize."""
    v = db.get_setting("photo_strip") or "rediscover"
    return v if v in STRIPS else "rediscover"


def set_photo_strip(v: str) -> None:
    if v not in STRIPS:
        raise Invalid("The photo strip is rediscover, onthisday or off")
    db.set_setting("photo_strip", None if v == "rediscover" else v)
