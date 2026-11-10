"""Home Assistant on the start page: the Home card (chosen entities, their state, a tap to toggle), sensors on the wall
display, entities in the search box, and what needs attention (a leak, smoke, a low battery, a door left open).

Settings › Home Assistant (admins) takes the address of Home Assistant and a long-lived access token (Home Assistant:
your profile › Security › Long-lived access tokens; HA_URL and HA_TOKEN in the environment do the same and win), and
the entities the page shows. The browser never talks to Home Assistant and never sees the token: every call goes
through this server, with the one token, so what the page can do is what the admin picked here, no more:

- every entity's state may be read by anyone signed in (the card, the wall, the search box);
- an entity is switched (a light, a switch, a scene, a script, a lock, a cover…) only when the admin ticked
  "control" for it, and only by an editor or an admin of the start page: a viewer sees the state and switches nothing
  (app/api.py). Home Assistant itself decides nothing per person.

Home Assistant is on the local network and quick: all its states are fetched in one call and kept STATES_TTL seconds
here, so a houseful of open pages refreshing at once costs one call. The settings come from the database once every
SETTINGS_TTL seconds, the card is built once per change for every open page, and the pages are woken only by a change
to something they show (a chosen entity, or one the built-in alerts watch), not by every sensor in the house.
"""
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from iosuite_shared import credentials

from app import config, db

APP = config.APP
from app.ha_feed import Feed

STATES_TTL = 5          # seconds the states are kept (the card redraws every minute, the search box types faster)
SETTINGS_TTL = 10       # seconds the settings read from the database are kept (save() drops them at once)
TIMEOUT = 6
MAX_ENTITIES = 40       # on the card
LOW_BATTERY = 15        # percent
_lock = threading.Lock()
_cache = {"at": 0.0, "items": None, "live": False}   # live: fed by the websocket (app/ha_feed.py), never stale
feed = Feed(sys.modules[__name__])
_ENTITY_RE = re.compile(r"^[a-z_0-9]+\.[a-z0-9_]+$")

# what a tap does per domain: the service called for toggle / on / off (None: the domain cannot be switched)
CONTROLS = {
    "light": ("homeassistant.toggle", "homeassistant.turn_on", "homeassistant.turn_off"),
    "switch": ("homeassistant.toggle", "homeassistant.turn_on", "homeassistant.turn_off"),
    "fan": ("homeassistant.toggle", "homeassistant.turn_on", "homeassistant.turn_off"),
    "input_boolean": ("homeassistant.toggle", "homeassistant.turn_on", "homeassistant.turn_off"),
    "humidifier": ("homeassistant.toggle", "homeassistant.turn_on", "homeassistant.turn_off"),
    "media_player": ("media_player.media_play_pause", "media_player.turn_on", "media_player.turn_off"),
    "scene": ("scene.turn_on", "scene.turn_on", None),
    "script": ("script.turn_on", "script.turn_on", "script.turn_off"),
    "automation": ("automation.trigger", "automation.turn_on", "automation.turn_off"),
    "button": ("button.press", "button.press", None),
    "input_button": ("input_button.press", "input_button.press", None),
    "lock": ("lock.toggle", "lock.lock", "lock.unlock"),
    "cover": ("cover.toggle", "cover.open_cover", "cover.close_cover"),
    "vacuum": ("vacuum.toggle", "vacuum.start", "vacuum.return_to_base"),
    "siren": ("siren.toggle", "siren.turn_on", "siren.turn_off"),
    "climate": ("climate.toggle", "climate.turn_on", "climate.turn_off"),  # the card opens its own popup (set_climate) instead
}
ACTIONS = ("toggle", "on", "off")
# a binary sensor of one of these kinds that is on needs attention wherever it is (the built-in alerts)
URGENT_CLASSES = {"moisture": "Leak", "smoke": "Smoke", "gas": "Gas", "carbon_monoxide": "Carbon monoxide",
                  "safety": "Unsafe", "problem": "Problem", "tamper": "Tampered"}
# how a binary sensor's on/off reads, per device class: (on, off)
BINARY_WORDS = {"door": ("Open", "Closed"), "garage_door": ("Open", "Closed"), "window": ("Open", "Closed"), "opening": ("Open", "Closed"),
                "lock": ("Unlocked", "Locked"), "motion": ("Motion", "Clear"), "occupancy": ("Occupied", "Clear"), "presence": ("Home", "Away"),
                "moisture": ("Wet", "Dry"), "smoke": ("Smoke", "Clear"), "gas": ("Gas", "Clear"), "carbon_monoxide": ("CO", "Clear"),
                "problem": ("Problem", "OK"), "safety": ("Unsafe", "Safe"), "battery": ("Low", "OK"), "battery_charging": ("Charging", "Not charging"),
                "connectivity": ("Connected", "Disconnected"), "plug": ("Plugged in", "Unplugged"), "power": ("On", "Off"),
                "running": ("Running", "Not running"), "update": ("Update", "Up to date"), "vibration": ("Vibration", "Clear"),
                "cold": ("Cold", "OK"), "heat": ("Hot", "OK"), "light": ("Light", "Dark"), "sound": ("Sound", "Quiet"),
                "tamper": ("Tampered", "OK"), "moving": ("Moving", "Still")}


class HAError(Exception):
    """(status, why): what the API answers; 502 when Home Assistant cannot be reached."""

    def __init__(self, why: str, status: int = 502):
        super().__init__(why)
        self.status = status


# ------------------------------------------------------------------ settings

_conf = {"at": 0.0, "v": None}   # the settings as last read, and when
_home = {"key": None, "v": None}  # the card as last built, and from what


def _saved() -> dict:
    """{url, token, entities, builtin, name} as saved (the database, and the token with the suite's keys), read together
    and kept SETTINGS_TTL seconds. Every open page asks for the card on every change, and the card needs all five."""
    now = time.monotonic()
    c = _conf["v"]
    if c is not None and now - _conf["at"] < SETTINGS_TTL:
        return c
    rows = {r["name"]: r["value"] for r in db.q("SELECT name, value FROM prt_settings WHERE name IN "
                                                "('ha_url', 'ha_entities', 'ha_builtin_alerts', 'ha_name')")}
    try:
        tok = "" if config.HA_TOKEN else credentials.get(APP, "ha_token").strip()
    except Exception:  # noqa: BLE001 - the shared database is away
        tok = ""
    try:
        items = json.loads(rows["ha_entities"]) if rows.get("ha_entities") else []
    except ValueError:
        items = []
    chosen = [_clean(e) for e in items if isinstance(e, dict) and _ENTITY_RE.match(str(e.get("id", "")))]
    c = {"url": rows.get("ha_url") or "", "token": tok, "entities": chosen, "ids": {e["id"] for e in chosen},
         "builtin": rows.get("ha_builtin_alerts") != "0", "name": rows.get("ha_name") or ""}
    _conf.update(at=now, v=c)
    return c


def reload() -> None:
    """The settings changed: read them again."""
    _conf["v"] = None
    _home["key"] = None


def url() -> str:
    return (config.HA_URL or _saved()["url"]).strip().rstrip("/")


def token() -> str:
    """HA_TOKEN in the environment, else the token kept with the suite's keys and tokens (the Shared ioSuite database)."""
    return config.HA_TOKEN or _saved()["token"]


def enabled() -> bool:
    return bool(url() and token())


def entities() -> list[dict]:
    """The admin's list, in order: [{id, name, control, wall, alert}]. name: what the card calls it ("" for Home
    Assistant's own name); control: a tap switches it; wall: shown on the wall display; alert: the state (text, as Home
    Assistant writes it: "on", "open", "unlocked"…) that needs attention, or ""."""
    return [dict(e) for e in _saved()["entities"]]


def _clean(e: dict) -> dict:
    return {"id": str(e["id"]), "name": str(e.get("name") or "")[:64].strip(), "control": bool(e.get("control")),
            "wall": bool(e.get("wall")), "alert": str(e.get("alert") or "")[:32].strip().lower()}


def builtin_alerts() -> bool:
    return _saved()["builtin"]


def house() -> str:
    """What Home Assistant calls the house (learned when the connection is tested)."""
    return _saved()["name"]


def settings() -> dict:
    """What Settings › Home Assistant shows (the token never leaves the server)."""
    return {"enabled": enabled(), "url": url(), "urlFromEnv": bool(config.HA_URL), "hasToken": bool(token()),
            "tokenFromEnv": bool(config.HA_TOKEN), "entities": entities(), "builtinAlerts": builtin_alerts(),
            "name": house(), "live": feed.live, "liveError": feed.error}


def save(changes: dict, by: str = None) -> None:
    """{url?, token?, entities?, builtinAlerts?}: an empty url or token clears it. `by`: who changed the token."""
    if "url" in changes and not config.HA_URL:
        u = str(changes["url"] or "").strip().rstrip("/")
        if u and not re.match(r"^https?://[^\s/]+", u):
            raise HAError("The address starts with http:// or https://", 400)
        db.set_setting("ha_url", u or None)
    if "token" in changes and not config.HA_TOKEN:
        credentials.put(APP, "ha_token", str(changes["token"] or "").strip(), by=by)
    if "entities" in changes:
        items = changes["entities"]
        if not isinstance(items, list) or len(items) > MAX_ENTITIES:
            raise HAError(f"entities: a list of up to {MAX_ENTITIES}", 400)
        seen = set()
        out = []
        for e in items:
            if not isinstance(e, dict) or not _ENTITY_RE.match(str(e.get("id", ""))):
                raise HAError("entities: each with an id like light.kitchen", 400)
            if e["id"] in seen:
                continue
            seen.add(e["id"])
            out.append(_clean(e))
        db.set_setting("ha_entities", json.dumps(out))
    if "builtinAlerts" in changes:
        db.set_setting("ha_builtin_alerts", "1" if changes["builtinAlerts"] else "0")
    reload()
    if "url" in changes or "token" in changes:
        feed.restart()
        feed_down()
    forget(devices=True)


def forget(devices: bool = False) -> None:
    """The REST copy is dropped (the live one stays: the feed keeps it right), and the card is built afresh."""
    _home["key"] = None
    if not _cache["live"]:
        _cache.update(at=0.0, items=None)
    if devices:
        _devices.clear()


def prime(states: list[dict]) -> None:
    """The feed connected: its full list becomes the copy, and the copy is live from now on."""
    with _lock:
        _cache.update(at=time.time(), items=list(states), live=True)
    _home["key"] = None


def apply(entity_id: str, new_state: dict | None) -> bool:
    """One state_changed from the feed folded into the copy; True when the pages may show the change (the feed wakes
    them only then: a house has hundreds of sensors that change all day and are on no card)."""
    with _lock:
        items = _cache["items"]
        if items is None or not _cache["live"]:
            return False
        old = None
        for i, st in enumerate(items):
            if st.get("entity_id") == entity_id:
                old = st
                if new_state is None:
                    del items[i]
                else:
                    items[i] = new_state
                break
        else:
            if new_state is None:
                return False
            items.append(new_state)
        _cache["at"] = time.time()
    if _shown(entity_id, old, new_state):
        _home["key"] = None
        return True
    return False


def _watched(st: dict | None) -> bool:
    """Whether the built-in alerts look at this entity (a leak, smoke or problem sensor, a battery)."""
    if not st:
        return False
    dom, cls = _domain(st.get("entity_id") or ""), (st.get("attributes") or {}).get("device_class") or ""
    return (dom == "binary_sensor" and (cls in URGENT_CLASSES or cls == "battery")) or (dom == "sensor" and cls == "battery")


def _shown(entity_id: str, old: dict | None, new: dict | None) -> bool:
    """Whether a change to this entity can change the card, the wall or the alerts."""
    try:
        c = _saved()
    except Exception:  # noqa: BLE001 - the database is away: wake the pages, they ask again
        return True
    return entity_id in c["ids"] or (c["builtin"] and (_watched(old) or _watched(new)))


def feed_down() -> None:
    """The feed lost its connection: back to the REST copy, fetched afresh."""
    with _lock:
        _cache.update(at=0.0, items=None, live=False)
    _home["key"] = None


# ------------------------------------------------------------------ Home Assistant's REST API

def _call(method: str, path: str, body: dict | None = None, base: str = "", tok: str = "") -> object:
    """One call to Home Assistant's REST API (/api/…). Replaced in the tests."""
    base, tok = base or url(), tok or token()
    if not base or not tok:
        raise HAError("Home Assistant is not set up", 400)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{base}{path}", data=data, method=method,
                                 headers={"Authorization": f"Bearer {tok}", "Accept": "application/json",
                                          "Content-Type": "application/json", "User-Agent": "iosuite"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise HAError("Home Assistant refused the token", 502)
        if e.code == 404:
            raise HAError("Home Assistant: not found (is the address its root, e.g. http://homeassistant.local:8123?)", 502)
        raise HAError(f"Home Assistant answered {e.code}", 502)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        raise HAError(f"Could not reach Home Assistant: {str(e)[:120]}", 502)


def test(base: str = "", tok: str = "") -> dict:
    """Tries the address and token (the saved ones when empty): {ok, name, version, entities}. Keeps the instance's
    name for the card's title."""
    base = (base or "").strip().rstrip("/") or url()
    tok = (tok or "").strip() or token()
    if not base or not tok:
        raise HAError("An address and a token first", 400)
    cfg = _call("GET", "/api/config", base=base, tok=tok)
    if not isinstance(cfg, dict):
        raise HAError("That is not Home Assistant's API", 502)
    states = _call("GET", "/api/states", base=base, tok=tok)
    name = str(cfg.get("location_name") or "Home")
    if base == url() and tok == token():
        db.set_setting("ha_name", name)
        reload()
    return {"ok": True, "name": name, "version": cfg.get("version"), "entities": len(states) if isinstance(states, list) else 0}


_unit = {"v": ""}


def temp_unit() -> str:
    """°C or °F, as Home Assistant is set (its /api/config), asked once."""
    if not _unit["v"]:
        try:
            cfg = _call("GET", "/api/config")
            _unit["v"] = str(((cfg or {}).get("unit_system") or {}).get("temperature") or "°C") if isinstance(cfg, dict) else "°C"
        except HAError:
            return "°C"
    return _unit["v"]


def all_states() -> list[dict]:
    """Every entity, as Home Assistant lists them: the live copy the feed keeps, else the REST copy kept STATES_TTL seconds."""
    now = time.time()
    if _cache["items"] is not None and (_cache["live"] or now - _cache["at"] < STATES_TTL):
        return _cache["items"]
    with _lock:
        if _cache["items"] is not None and time.time() - _cache["at"] < STATES_TTL:
            return _cache["items"]
        items = _call("GET", "/api/states")
        _cache.update(at=time.time(), items=items if isinstance(items, list) else [])
        return _cache["items"]


_devices: dict[str, str] = {}   # entity id → device id ("" when it has none), asked once per entity


def device_ids(entity_ids: list[str]) -> dict[str, str]:
    """{entity id: device id} for the ones that belong to a device, by way of the template API (the REST API does not
    list the device registry). A link to the device page lets a person change what a tile cannot (a thermostat)."""
    missing = [e for e in dict.fromkeys(entity_ids) if e not in _devices and _ENTITY_RE.match(e)]
    if missing:
        try:
            got = _call("POST", "/api/template", {"template": "{{ " + json.dumps(missing) + " | map('device_id') | list | to_json }}"})
        except HAError:
            got = None
        if isinstance(got, str):
            try:
                got = json.loads(got)
            except ValueError:
                got = None
        for e, d in zip(missing, got if isinstance(got, list) and len(got) == len(missing) else [None] * len(missing)):
            _devices[e] = d if isinstance(d, str) else ""
    return {e: _devices[e] for e in entity_ids if _devices.get(e)}


# ------------------------------------------------------------------ what the page shows

def _domain(entity_id: str) -> str:
    return entity_id.split(".", 1)[0]


def _title(s: str) -> str:
    return s.replace("_", " ").strip().capitalize() if s else s


def describe(st: dict, chosen: dict | None = None) -> dict:
    """One entity for the page: {id, domain, name, state, text, unit, on, icon, class, control, attrs}. `text` is the
    state as people read it ("Open", "21.5 °C", "Playing"); `on` says whether a switchable thing is on."""
    eid = st.get("entity_id") or ""
    a = st.get("attributes") or {}
    dom = _domain(eid)
    state = str(st.get("state", ""))
    unit = a.get("unit_of_measurement") or ""
    cls = a.get("device_class") or ""
    chosen = chosen or {}
    name = chosen.get("name") or a.get("friendly_name") or _title(eid.split(".", 1)[-1])
    on = None
    if dom in ("light", "switch", "fan", "input_boolean", "humidifier", "siren", "automation", "script", "binary_sensor"):
        on = state == "on"
    elif dom == "media_player":
        on = state in ("playing", "on", "paused")
    elif dom == "lock":
        on = state == "unlocked"
    elif dom == "cover":
        on = state in ("open", "opening")
    elif dom == "vacuum":
        on = state in ("cleaning", "returning")
    if dom in ("scene", "button", "input_button") and state != "unavailable":  # their state is when they last ran
        text = "Tap to run" if chosen.get("control") else ""
    elif dom == "script" and state != "unavailable":
        text = "Running" if state == "on" else ("Tap to run" if chosen.get("control") else "")
    elif state in ("unavailable", "unknown"):
        text = "Unavailable" if state == "unavailable" else "Unknown"
    elif dom == "binary_sensor":
        text = (BINARY_WORDS.get(cls) or ("On", "Off"))[0 if state == "on" else 1]
    elif unit:
        try:
            v = float(state)
            text = f"{v:g} {unit}".replace(" %", "%").replace(" °", "°")
            if unit in ("°C", "°F"):
                text = f"{round(v, 1):g}{unit}"
        except ValueError:
            text = f"{state} {unit}"
    elif dom == "lock":
        text = _title(state)
    elif dom == "climate":
        cur, target = a.get("current_temperature"), a.get("temperature")
        text = f"{_title(state)}" + (f" · {cur:g}°" if isinstance(cur, (int, float)) else "") + (f" → {target:g}°" if isinstance(target, (int, float)) else "")
    elif dom == "weather":
        text = _title(state) + (f" · {a['temperature']:g}°" if isinstance(a.get("temperature"), (int, float)) else "")
    elif dom == "media_player" and state in ("playing", "paused") and a.get("media_title"):
        text = f"{_title(state)} · {a['media_title']}"
    elif dom == "person" or dom == "device_tracker":
        text = "Home" if state == "home" else ("Away" if state == "not_home" else _title(state))
    elif dom == "light" and state == "on" and isinstance(a.get("brightness"), (int, float)):
        text = f"On · {round(a['brightness'] / 255 * 100)}%"
    else:
        text = _title(state)
    out = {"id": eid, "domain": dom, "name": name, "state": state, "text": text, "unit": unit, "on": on, "class": cls,
           "icon": a.get("icon") or "", "control": bool(chosen.get("control")) and dom in CONTROLS and state != "unavailable",
           "changed": st.get("last_changed")}
    bat = a.get("battery_level")
    if isinstance(bat, (int, float)):
        out["battery"] = bat
    if dom == "cover":  # what the cover popup needs: open / close / stop / a position, as the cover supports them
        feat = a.get("supported_features") if isinstance(a.get("supported_features"), int) else 0
        out["cover"] = {"position": a.get("current_position") if isinstance(a.get("current_position"), (int, float)) else None,
                        "canOpen": bool(feat & 1), "canClose": bool(feat & 2), "canPosition": bool(feat & 4), "canStop": bool(feat & 8), "moving": state in ("opening", "closing")}
    if dom == "climate":  # what the climate popup needs
        num = lambda k: a.get(k) if isinstance(a.get(k), (int, float)) else None  # noqa: E731
        out["climate"] = {"mode": state, "modes": [m for m in (a.get("hvac_modes") or []) if isinstance(m, str)], "action": a.get("hvac_action"),
                          "current": num("current_temperature"), "target": num("temperature"), "low": num("target_temp_low"), "high": num("target_temp_high"),
                          "min": num("min_temp") if num("min_temp") is not None else 7, "max": num("max_temp") if num("max_temp") is not None else 35,
                          "step": num("target_temp_step") or 0.5, "humidity": num("current_humidity"),
                          "fan": a.get("fan_mode"), "fans": [m for m in (a.get("fan_modes") or []) if isinstance(m, str)],
                          "preset": a.get("preset_mode"), "presets": [m for m in (a.get("preset_modes") or []) if isinstance(m, str)],
                          "unit": temp_unit()}
    return out


def home() -> dict:
    """The Home card and the wall: {enabled, name, url, items: [describe…], wall: [ids], alerts: [{id, name, text, why}]}."""
    if not enabled():
        return {"enabled": False}
    feed.ensure()
    chosen = entities()
    try:
        states = all_states()
    except HAError as e:
        return {"enabled": True, "name": house() or "Home", "url": url(), "error": str(e), "items": [], "wall": [], "alerts": []}
    # built once per change, for every page that asks: live, the feed's version says when something shown changed;
    # otherwise the REST copy's age does
    devs = device_ids([c["id"] for c in chosen])  # asked once per entity
    key = (feed.version, feed.live) if _cache["live"] else (_cache["at"], feed.live)
    key = (*key, _conf["at"], len(_devices))
    if _home["key"] == key:
        return _home["v"]
    by = {s.get("entity_id"): s for s in states}
    items = []
    for c in chosen:
        st = by.get(c["id"])
        items.append(describe(st, c) if st else {"id": c["id"], "domain": _domain(c["id"]), "name": c["name"] or _title(c["id"].split(".", 1)[-1]),
                                                   "state": "missing", "text": "Not in Home Assistant", "on": None, "control": False, "unit": "", "class": "", "icon": ""})
    for it in items:
        if devs.get(it["id"]):
            it["device"] = devs[it["id"]]
    out = {"enabled": True, "name": house() or "Home", "url": url(), "items": items, "live": feed.live,
           "wall": [c["id"] for c in chosen if c["wall"]], "alerts": alerts(states, chosen, by)}
    _home.update(key=key, v=out)
    return out  # shared between the pages: read, never changed (app/api.py copies what it changes)


def alerts(states: list[dict], chosen: list[dict], by: dict | None = None) -> list[dict]:
    """What needs attention: a chosen entity in the state its "alert when" names, and (built-in, every entity) a leak,
    smoke, gas, CO, safety or problem sensor that is on, and a battery at LOW_BATTERY% or under."""
    by = by if by is not None else {s.get("entity_id"): s for s in states}
    out, seen = [], set()
    for c in chosen:
        st = by.get(c["id"])
        if not c["alert"] or not st or str(st.get("state", "")).lower() != c["alert"]:
            continue
        d = describe(st, c)
        out.append({"id": c["id"], "name": d["name"], "text": d["text"], "why": "state"})
        seen.add(c["id"])
    if builtin_alerts():
        names = {c["id"]: c["name"] for c in chosen}
        for st in states:
            eid = st.get("entity_id") or ""
            if eid in seen:
                continue
            a = st.get("attributes") or {}
            dom, state, cls = _domain(eid), str(st.get("state", "")), a.get("device_class") or ""
            name = names.get(eid) or a.get("friendly_name") or eid
            if dom == "binary_sensor" and state == "on" and cls in URGENT_CLASSES:
                out.append({"id": eid, "name": name, "text": URGENT_CLASSES[cls], "why": cls})
            elif dom == "binary_sensor" and state == "on" and cls == "battery":
                out.append({"id": eid, "name": name, "text": "Low battery", "why": "battery"})
            elif dom == "sensor" and cls == "battery":
                try:
                    if float(state) <= LOW_BATTERY:
                        out.append({"id": eid, "name": name, "text": f"Battery {float(state):g}%", "why": "battery"})
                except ValueError:
                    pass
    # the admin's own first, then the urgent sensors, then the batteries
    rank = {"state": 0, "battery": 2}
    out.sort(key=lambda a: rank.get(a["why"], 1))
    return out[:12]


def search(q: str, limit: int = 8) -> list[dict]:
    """Entities whose name or id contains every word of q (the search box; Settings' picker with a higher limit)."""
    words = [w for w in re.split(r"\s+", (q or "").lower().strip()) if w]
    if not words or not enabled():
        return []
    chosen = {c["id"]: c for c in entities()}
    out = []
    for st in all_states():
        eid = st.get("entity_id") or ""
        hay = f"{eid.replace('_', ' ').replace('.', ' ')} {(st.get('attributes') or {}).get('friendly_name') or ''}".lower()
        if all(w in hay for w in words):
            d = describe(st, chosen.get(eid))
            d["chosen"] = eid in chosen
            out.append(d)
    # the ones on the card first, then by name
    out.sort(key=lambda d: (not d["chosen"], d["name"].lower()))
    out = out[:limit]
    devs = device_ids([d["id"] for d in out])
    for d in out:
        if devs.get(d["id"]):
            d["device"] = devs[d["id"]]
    return out


def _allowed(entity_id: str) -> dict:
    c = next((c for c in entities() if c["id"] == entity_id), None)
    if not c or not c["control"]:
        raise HAError("The page may not control that entity (Settings › Home Assistant)", 403)
    return c


def _service(entity_id: str, c: dict, service: str, data: dict | None = None, expects_change: bool = True) -> dict:
    """Calls `service` (domain.name) on the entity and answers with its state after. Home Assistant answers with the
    states the call changed; a device that reports back later (Zigbee, Z-Wave, a cloud bulb) is not among them yet,
    and reading its state straight away gives the old one, which would make the tile say the opposite of what just
    happened. So: the answer when it names the entity, else a few short reads until the state differs from before (a
    scene or button changes nothing: one read)."""
    dom, svc = service.split(".", 1)
    before = next((s for s in (_cache["items"] or []) if s.get("entity_id") == entity_id), None)
    changed = _call("POST", f"/api/services/{dom}/{svc}", {"entity_id": entity_id, **(data or {})})
    forget()
    st = next((s for s in changed if isinstance(s, dict) and s.get("entity_id") == entity_id), None) if isinstance(changed, list) else None
    for i in range(6 if expects_change and before else 1):
        if st is not None:
            break
        if i:
            time.sleep(0.35)
        try:
            got = _call("GET", f"/api/states/{urllib.parse.quote(entity_id)}")
        except HAError:
            got = None
        if isinstance(got, dict) and (not expects_change or not before or got.get("state") != before.get("state") or got.get("last_updated") != before.get("last_updated")):
            st = got
    if st is None:
        try:
            st = _call("GET", f"/api/states/{urllib.parse.quote(entity_id)}")
        except HAError:
            st = None
    return describe(st, c) if isinstance(st, dict) else {"id": entity_id, "ok": True}


def act(entity_id: str, action: str) -> dict:
    """toggle | on | off on an entity the admin lets the page control; the entity's state right after."""
    if action not in ACTIONS:
        raise HAError("action: toggle, on or off", 400)
    c = _allowed(entity_id)
    services = CONTROLS.get(_domain(entity_id))
    if not services:
        raise HAError("That kind of entity cannot be switched from here", 400)
    service = services[ACTIONS.index(action)]
    if not service:
        raise HAError(f"{_domain(entity_id)}: no '{action}'", 400)
    return _service(entity_id, c, service, expects_change=_domain(entity_id) not in ("scene", "script", "button", "input_button", "automation"))


def set_entity(entity_id: str, body: dict) -> dict:
    """The popups. A thermostat: {temperature? | low? + high?, mode?, fan?, preset?}; a cover: {action: open | close |
    stop} or {position: 0-100}. On an entity the admin lets the page control, each checked against what it offers;
    its state right after."""
    dom = _domain(entity_id)
    if dom not in ("climate", "cover"):
        raise HAError("A climate or cover entity, please", 400)
    c = _allowed(entity_id)
    st = next((s for s in all_states() if s.get("entity_id") == entity_id), None)
    if not st:
        raise HAError("Not in Home Assistant", 404)
    body = body if isinstance(body, dict) else {}
    if dom == "cover":
        cv = describe(st, c)["cover"]
        if body.get("position") is not None:
            try:
                pos = int(body["position"])
            except (TypeError, ValueError):
                raise HAError("position: 0 to 100", 400)
            if not cv["canPosition"] or not 0 <= pos <= 100:
                raise HAError("position: 0 to 100, on a cover that takes one", 400)
            return _service(entity_id, c, "cover.set_cover_position", {"position": pos})
        act_ = body.get("action")
        if act_ not in ("open", "close", "stop") or not cv["can" + act_.capitalize()]:
            raise HAError(f"action: {', '.join(a for a in ('open', 'close', 'stop') if cv['can' + a.capitalize()])}", 400)
        return _service(entity_id, c, f"cover.{act_}_cover", expects_change=act_ != "stop")
    cl = describe(st, c)["climate"]
    out = None
    if body.get("mode") is not None:
        if body["mode"] not in cl["modes"]:
            raise HAError(f"mode: one of {', '.join(cl['modes']) or 'none'}", 400)
        out = _service(entity_id, c, "climate.set_hvac_mode", {"hvac_mode": body["mode"]})
    if body.get("fan") is not None:
        if body["fan"] not in cl["fans"]:
            raise HAError(f"fan: one of {', '.join(cl['fans']) or 'none'}", 400)
        out = _service(entity_id, c, "climate.set_fan_mode", {"fan_mode": body["fan"]})
    if body.get("preset") is not None:
        if body["preset"] not in cl["presets"]:
            raise HAError(f"preset: one of {', '.join(cl['presets']) or 'none'}", 400)
        out = _service(entity_id, c, "climate.set_preset_mode", {"preset_mode": body["preset"]})
    temps = {}
    for k, hk in (("temperature", "temperature"), ("low", "target_temp_low"), ("high", "target_temp_high")):
        if body.get(k) is not None:
            try:
                v = float(body[k])
            except (TypeError, ValueError):
                raise HAError(f"{k}: a number", 400)
            if not cl["min"] <= v <= cl["max"]:
                raise HAError(f"{k}: between {cl['min']:g} and {cl['max']:g}", 400)
            temps[hk] = v
    if temps:
        if ("target_temp_low" in temps) != ("target_temp_high" in temps):
            raise HAError("low and high together", 400)
        out = _service(entity_id, c, "climate.set_temperature", temps)
    if out is None:
        raise HAError("Nothing to set: temperature, low + high, mode, fan or preset", 400)
    return out
