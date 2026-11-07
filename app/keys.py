"""The start page's keys and tokens, kept with every other app's in the Shared ioSuite database
(iosuite_shared.credentials), so Settings › Suite › Keys and tokens lists them all. Settings › Home Assistant and
Settings › Weather still set them; HA_TOKEN and ACCUWEATHER_API_KEY in the environment win as before."""
import logging

from iosuite_shared import credentials

from app import config

log = logging.getLogger("iosuite.keys")
KEYS = [
    {"name": "ha_token", "label": "Home Assistant token", "env": "HA_TOKEN",
     "hint": "a long-lived access token (Home Assistant: your profile › Security)"},
    {"name": "accuweather_key", "label": "AccuWeather API key", "env": "ACCUWEATHER_API_KEY",
     "hint": "from developer.accuweather.com, for the weather card"},
]


def declare() -> None:
    """At start: say which keys the start page keeps."""
    try:
        credentials.declare(config.APP, KEYS)
    except Exception as e:  # noqa: BLE001 - the shared database is away: tried again next start
        log.warning("keys and tokens: %s", e)
