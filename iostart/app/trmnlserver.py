"""A TRMNL server inside the start page: a TRMNL e-ink device (or anything running TRMNL's firmware) set to this
server asks here what to show, and gets the suite's screens as a picture, with no TRMNL cloud, plugin import, polling
or webhook in between. app/trmnl.py has the screens' data and markup, app/trmnldraw.py draws them (no browser).

What a device does (TRMNL's open firmware, github.com/usetrmnl/firmware; its Wi-Fi setup page takes the address of a
server of one's own). It cannot sign in through Cloudflare Access or with an account, so these four answer without a
sign-in, and the device has to reach the start page inside the network (its LAN address, Settings › TRMNL shows it):

    GET  /api/setup      ID: <MAC>                      -> {api_key, friendly_id, image_url, message}: the device's key
    GET  /api/display    ID, Access-Token, battery...   -> {image_url, filename, refresh_rate, ...}: what to show next
    POST /api/log        ID, Access-Token               the device's own log lines, the last few kept
    GET  /api/trmnl/image/<key>.png                     the picture image_url names

Whose screens. A MAC address is no secret, so a device that turns up shows only a code, and belongs to nobody until a
signed-in person types that code in Settings › TRMNL (claim). From then on it shows that person's screens, read as
them with their own "TRMNL" app password (trmnlpush.asker: the one pushing uses, in the suite's keys and tokens), and
nothing more than they may see. The device's key is kept there too (trmnl_device_<id>), not in this app's tables. A
claimed device that asks for /api/setup again (a factory reset) gets a new key only while its owner has "Pair again"
open (ten minutes): otherwise anyone on the network who knows the MAC could read that person's day.

What it shows: the device's playlist, one entry after the other at each wake: a layout (full, or one of TRMNL's
mashups) and the screen in each of its places. A picture that did not change keeps its filename, which is how the
firmware knows to skip the download; it is drawn again after RESEND minutes anyway, so "updated" on it stays true.
"""
import functools
import hashlib
import hmac
import json
import logging
import re
import secrets
import threading
import time

from iosuite_shared import credentials, suite
from iosuite_shared.errors import Invalid

from app import config, db, trmnl, trmnldraw, trmnlpush

log = logging.getLogger("iostart.trmnl")
APP = config.APP
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I: it is read off an e-ink screen
MAC = re.compile(r"[0-9A-F]{2}(:[0-9A-F]{2}){5}|[0-9A-F]{12}")
PENDING_MAX = 16        # devices nobody claimed yet (the endpoints are open to the network): the oldest go first
PENDING_EVERY = 120     # seconds between a waiting device's looks
PAIR_AGAIN = 10 * 60    # seconds "Pair again" stays open
RESEND = 180            # minutes after which an unchanged picture is drawn again anyway
REFRESH = (300, 600, 900, 1800, 3600, 7200, 14400)  # seconds a device may sleep between two looks
LOG_KEEP = 20
PATHS = ("/api/setup", "/api/display", "/api/log", "/api/trmnl/image/")  # what a device asks, without a sign-in (main.py)
# what TRMNL's firmware calls itself (its Model header) -> (name, grays it can show, how many of its pixels one of the
# framework's is). Anything else: its Width and Height headers, black and white.
MODELS = {
    "og": ("TRMNL", (1, 2), 1.0), "og_png": ("TRMNL", (1, 2), 1.0), "og_plus": ("TRMNL", (1, 2), 1.0), "og_4clr": ("TRMNL", (1, 2), 1.0),
    "x": ("TRMNL X", (4, 2, 1), 1.8), "v2": ("TRMNL X", (4, 2, 1), 1.8),
    "m5_papers3": ("M5PaperS3", (4, 2, 1), 1.0), "seeed_e1001": ("Seeed E1001", (2, 1), 1.0),
}


class NotFound(Exception):
    """Not a device (or picture) this server knows: a 404, in the shape TRMNL's firmware reads."""


_lock = threading.Lock()
_images = {}  # device id -> (key, PNG bytes): the picture its last answer named


def _mac(v) -> str:
    m = str(v or "").strip().upper().replace("-", ":")
    if not MAC.fullmatch(m):
        raise NotFound("Not a device this server knows (no MAC address in the ID header)")
    return m if ":" in m else ":".join(m[i:i + 2] for i in range(0, 12, 2))


def _cred(dev_id: int) -> str:
    return f"trmnl_device_{int(dev_id)}"


def _row(r: dict) -> dict:
    r = dict(r)
    for k in ("settings", "state"):
        try:
            r[k] = json.loads(r.get(k) or "{}")
        except ValueError:
            r[k] = {}
    return r


def _by_mac(mac: str):
    r = db.one("SELECT * FROM prt_trmnl_devices WHERE mac = %s", (mac,))
    return _row(r) if r else None


def get(dev_id: int):
    r = db.one("SELECT * FROM prt_trmnl_devices WHERE id = %s", (int(dev_id),))
    return _row(r) if r else None


def _save(d: dict, *fields) -> None:
    for f in fields or ("settings", "state"):
        v = json.dumps(d[f]) if f in ("settings", "state") else d[f]
        db.ex(f"UPDATE prt_trmnl_devices SET {f} = %s WHERE id = %s", (v, d["id"]))


def devices_of(uid: int) -> list:
    return [_row(r) for r in db.q("SELECT * FROM prt_trmnl_devices WHERE owner = %s ORDER BY id", (int(uid),))]


def _code() -> str:
    while True:
        c = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        if not db.one("SELECT id FROM prt_trmnl_devices WHERE code = %s", (c,)):
            return c


def _key_ok(d: dict, token: str) -> bool:
    have = credentials.get(APP, _cred(d["id"]))
    return bool(have and token) and hmac.compare_digest(have.encode(), str(token).encode())


def _new(mac: str, headers, token: str = None) -> dict:
    """A device nobody knows yet: kept as waiting (no owner), with a key of its own and the code its screen shows."""
    with _lock:
        waiting = db.q("SELECT id FROM prt_trmnl_devices WHERE owner IS NULL ORDER BY seen_at DESC, id DESC")
        for r in waiting[PENDING_MAX - 1:]:
            _drop(r["id"])
        db.ex("INSERT INTO prt_trmnl_devices (mac, code, name, model, width, height, settings, state, seen_at) VALUES (%s, %s, '', %s, %s, %s, '{}', '{}', %s)",
              (mac, _code(), _model(headers), *_dims(headers), time.time()))
        d = _by_mac(mac)
        name = _cred(d["id"])
        credentials.declare(APP, [{"name": name, "label": f"TRMNL screen {mac}: its key",
                                   "hint": "made when the device first asked this server (Settings › TRMNL on the start page); removed with the device"}])
        credentials.put(APP, name, token or secrets.token_urlsafe(16), by="TRMNL device")
    return d


def _drop(dev_id: int) -> None:
    credentials.remove(APP, _cred(dev_id))
    db.ex("DELETE FROM prt_trmnl_devices WHERE id = %s", (int(dev_id),))
    _images.pop(int(dev_id), None)


def _model(headers) -> str:
    return re.sub(r"[^a-z0-9_]", "", str(headers.get("model") or "").lower())[:40]


def _dims(headers) -> tuple:
    def n(k, d):
        try:
            v = int(float(headers.get(k) or 0))
        except ValueError:
            v = 0
        return v if 100 <= v <= 4000 else d
    return n("width", 800), n("height", 480)


def _note(d: dict, headers) -> None:
    """What the device says about itself with every look: battery, signal, firmware, its screen."""
    def num(k):
        try:
            return round(float(headers.get(k)), 2)
        except (TypeError, ValueError):
            return None
    st = d["state"]
    st["seen"] = time.time()
    for key, name in (("battery-voltage", "volts"), ("percent-charged", "percent"), ("rssi", "rssi")):
        v = num(key)
        if v is not None:
            st[name] = v
    if headers.get("fw-version"):
        st["firmware"] = str(headers.get("fw-version"))[:40]
    model, (w, h) = _model(headers), _dims(headers)
    if model and model != d["model"]:
        d["model"] = model
        _save(d, "model")
    if headers.get("width") and (w, h) != (d["width"], d["height"]):
        d["width"], d["height"] = w, h
        _save(d, "width", "height")
    db.ex("UPDATE prt_trmnl_devices SET seen_at = %s WHERE id = %s", (st["seen"], d["id"]))


def battery(st: dict):
    """0..100 from what the device said: its own percentage, else from the volts of a LiPo cell (3.0 empty, 4.1 full)."""
    if st.get("percent") is not None:
        return max(0, min(100, round(st["percent"])))
    v = st.get("volts")
    if not v:
        return None
    return max(0, min(100, round((v - 3.0) / 1.1 * 100)))


# ---- what a device asks ---------------------------------------------------------------------------------------------

def setup(headers, base: str) -> dict:
    """GET /api/setup: the device's key. A new device waits for someone to claim it; one still waiting that asks again
    gets a new key and a new code (so the code on a screen always goes with the key that screen's device holds, and
    never with one somebody else asked for with its MAC address); a claimed one is given a key again only while its
    owner has Pair again open."""
    mac = _mac(headers.get("id"))
    d = _by_mac(mac)
    if d is None:
        d = _new(mac, headers)
    elif d["owner"] is None:
        d["code"], d["state"] = _code(), {}
        _save(d, "code")
        credentials.put(APP, _cred(d["id"]), secrets.token_urlsafe(16), by="TRMNL device")
    else:
        if d["state"].get("pairUntil", 0) < time.time():
            raise NotFound("This device belongs to someone here already: open Settings › TRMNL on the start page and choose Pair again")
        credentials.put(APP, _cred(d["id"]), secrets.token_urlsafe(16), by="TRMNL device")
        d["state"].pop("pairUntil", None)
    _note(d, headers)
    _save(d, "state")
    return {"status": 200, "api_key": credentials.get(APP, _cred(d["id"])), "friendly_id": d["code"],
            "image_url": _picture(d, base, waiting=d["owner"] is None)["image_url"], "message": "Welcome to ioSuite"}


def _device(headers) -> dict:
    """The device a request is from: its MAC address and its key. One this server never saw that brings a key (it was
    set up with another server, or removed here) is taken in as waiting, with that key."""
    mac, token = _mac(headers.get("id")), str(headers.get("access-token") or "")
    d = _by_mac(mac)
    if d is None:
        if not 16 <= len(token) <= 64:
            raise NotFound("Not a device this server knows: let it ask /api/setup first")
        return _new(mac, headers, token)
    if not _key_ok(d, token):
        raise NotFound("Wrong key for this device: reset it, or open Settings › TRMNL on the start page and choose Pair again")
    return d


def display(headers, base: str) -> dict:
    """GET /api/display: what the device shows next and how long it sleeps after."""
    d = _device(headers)
    _note(d, headers)
    pic = _picture(d, base, waiting=d["owner"] is None)
    _save(d, "state")
    return {"status": 0, "image_url": pic["image_url"], "filename": pic["filename"],
            "refresh_rate": PENDING_EVERY if d["owner"] is None else refresh(d),
            "reset_firmware": False, "update_firmware": False, "firmware_url": None, "special_function": "sleep"}


def add_log(headers, body) -> None:
    d = _by_mac(_mac(headers.get("id")))
    if d is None or not _key_ok(d, str(headers.get("access-token") or "")):
        raise NotFound("Not a device this server knows")
    body = body if isinstance(body, dict) else {}
    lines = body.get("logs") or body.get("log") or []
    if isinstance(lines, dict):
        lines = lines.get("logs_array") or [lines]
    keep = d["state"].get("log") or []
    for x in lines[:LOG_KEEP] if isinstance(lines, list) else []:
        if isinstance(x, dict):
            text = str(x.get("log_message") or x.get("message") or x.get("msg") or "")[:300]
            at = x.get("creation_timestamp") or x.get("created_at")
        else:
            text, at = str(x)[:300], None
        if text:
            keep.append({"at": at if isinstance(at, (int, float)) else time.time(), "text": text})
    d["state"]["log"] = keep[-LOG_KEEP:]
    _save(d, "state")


def image(key: str) -> bytes:
    """GET /api/trmnl/image/<key>.png: the picture an answer named. Drawn again when this process no longer has it
    (a restart between the device's two requests)."""
    m = re.fullmatch(r"(\d+)-([A-Za-z0-9_-]{8,40})", key or "")
    if not m:
        raise NotFound("No such picture")
    dev_id = int(m.group(1))
    got = _images.get(dev_id)
    if got and hmac.compare_digest(got[0], key):
        return got[1]
    d = get(dev_id)
    if d is None or not hmac.compare_digest(str(d["state"].get("image") or ""), key):
        raise NotFound("No such picture")
    return _draw(d, d["state"].get("at", 0), d["owner"] is None)[0]


# ---- the picture ----------------------------------------------------------------------------------------------------

def grays(d: dict) -> int:
    """Bits a pixel of the picture this device gets: its setting when the model can show it, else the model's own."""
    can = MODELS.get(d["model"], ("", (1, 2), 1.0))[1]
    want = d["settings"].get("bits")
    return want if want in can else can[0]


def scale(d: dict) -> float:
    known = MODELS.get(d["model"])
    if known:
        return known[2]
    return 1.0 if d["width"] <= 1000 else d["width"] / 1040


def refresh(d: dict) -> int:
    r = d["settings"].get("refresh")
    return r if r in REFRESH else 900


def playlist(d: dict, user=None) -> list:
    """[{layout, screens}] as set, kept to layouts and screens there are; one full Today when nothing is set."""
    out = []
    for it in d["settings"].get("playlist") or []:
        layout = it.get("layout") if isinstance(it, dict) else None
        if layout not in trmnldraw.LAYOUTS:
            continue
        want = [s for s in (it.get("screens") or []) if s in trmnl.SCREENS]
        if len(want) == len(trmnldraw.LAYOUTS[layout]):
            out.append({"layout": layout, "screens": want})
    return out or [{"layout": "full", "screens": ["today"]}]


@functools.lru_cache(maxsize=64)
def _template(screen: str, size: str):
    import liquid
    m = trmnl.markup(screen)
    return liquid.Environment().parse(m["shared"] + "\n" + m[size])


def render(datas: list, layout: str, bits: int = 1, s: float = 1.0, width: int = None, height: int = None):
    """The picture of one playlist entry: datas = what trmnl.build gave for each of its screens, [(screen, data)]."""
    views = [_template(screen, size).render(data) for (screen, data), size in zip(datas, trmnldraw.sizes(layout))]
    return trmnldraw.Drawer(s, bits).screen(views, layout, width, height)


NOTICE = """<div class="layout layout--col layout--center gap--large">
  <span class="title">{{ title }}</span>
  {% if code %}<span class="value value--xxlarge">{{ code }}</span>{% endif %}
  <span class="label">{{ text }}</span>
</div>
<div class="title_bar">
  <img class="image" src="">
  <span class="title">ioSuite</span>
  <span class="instance">{{ instance }}</span>
</div>"""


def _notice(d: dict, title: str, text: str, code: str = "") -> bytes:
    """A screen of its own words: the code of a device nobody took yet, or why its owner's screens cannot be read."""
    import liquid
    bits = grays(d)
    view = liquid.Environment().parse(NOTICE).render({"title": title, "text": text, "code": " ".join(code), "instance": d["name"] or d["mac"]})
    return trmnldraw.png(trmnldraw.Drawer(scale(d), bits).screen([view], "full", d["width"], d["height"]), bits)


def _draw(d: dict, at: int, waiting: bool):
    """(PNG, digest) of what the device shows at playlist position `at`."""
    if waiting:
        return _notice(d, "This screen is not yours yet", "Open the start page, Settings › TRMNL, and type this code under Add a screen", d["code"]), "waiting-" + d["code"]
    bits, s = grays(d), scale(d)
    items = playlist(d)
    item = items[at % len(items)]
    conf = trmnlpush.settings(d["owner"])
    try:
        who = trmnlpush.asker(d["owner"])
    except Invalid:  # the app password was revoked: say so on the screen, where its owner looks
        return _notice(d, "This screen cannot read your ioSuite any more",
                       "Open the start page, Settings › TRMNL, and save this screen again"), "revoked"
    datas = [(k, trmnl.build(who, k, conf["tz"], conf["clock"] == 24)) for k in item["screens"]]
    digest = hashlib.sha256(json.dumps([item["layout"], bits, d["width"], d["height"],
                                        [[k, {a: v for a, v in x.items() if a != "updated"}] for k, x in datas]], sort_keys=True).encode()).hexdigest()
    return trmnldraw.png(render(datas, item["layout"], bits, s, d["width"], d["height"]), bits), digest


def _picture(d: dict, base: str, waiting: bool) -> dict:
    """Draws what comes next for the device, and names it: {image_url, filename}. The filename is what TRMNL's
    firmware keeps a picture under (a kind, six characters for which screen, the time it was drawn): the same name
    again means "you have it", so an unchanged picture keeps its name until RESEND minutes passed."""
    st = d["state"]
    now = time.time()
    if waiting:
        at = 0
    else:
        at = (st.get("at", -1) + 1) % len(playlist(d))
    body, digest = _draw(d, at, waiting)
    shown = st.setdefault("shown", {})
    last = shown.get(str(at)) or {}
    if last.get("digest") != digest or now - last.get("drawn", 0) >= RESEND * 60:
        last = {"digest": digest, "drawn": max(int(now), last.get("drawn", 0) + 1)}  # never the name it had: a name is a second
        shown[str(at)] = last
    for k in [k for k in shown if int(k) >= len(playlist(d))]:
        shown.pop(k)
    key = f"{d['id']}-{secrets.token_urlsafe(12)}"
    st["at"], st["image"] = at, key
    _images[d["id"]] = (key, body)
    kind = "screen-" if waiting else "plugin-" if playlist(d)[at]["layout"] == "full" else "mashup-"
    which = hashlib.md5(f"{d['id']}:{'w' if waiting else at}".encode()).hexdigest()[:6]
    return {"image_url": f"{base.rstrip('/')}/api/trmnl/image/{key}.png", "filename": f"{kind}{which}-{last['drawn']:010d}"}


# ---- what a person does with their devices (Settings › TRMNL) ---------------------------------------------------------

def public(d: dict, user=None) -> dict:
    st = d["state"]
    known = MODELS.get(d["model"])
    return {"id": d["id"], "name": d["name"] or (known[0] if known else "TRMNL"), "mac": d["mac"], "model": known[0] if known else (d["model"] or "TRMNL firmware"),
            "width": d["width"], "height": d["height"], "seen": st.get("seen"), "battery": battery(st), "rssi": st.get("rssi"),
            "firmware": st.get("firmware"), "refresh": refresh(d), "bits": grays(d), "canBits": list(MODELS.get(d["model"], ("", (1, 2), 1.0))[1]),
            "playlist": playlist(d), "pairing": st.get("pairUntil", 0) >= time.time(), "log": (st.get("log") or [])[-LOG_KEEP:]}


def state(user) -> dict:
    """What Settings › TRMNL shows of this: the person's devices, the layouts and how many screens each takes."""
    return {"devices": [public(d) for d in devices_of(user["id"])],
            "layouts": [{"key": k, "places": trmnldraw.sizes(k)} for k in trmnldraw.LAYOUTS], "refreshes": list(REFRESH),
            "deviceServer": address(), "devicePaths": list(PATHS)}


def claim(user, code: str) -> dict:
    """The signed-in person takes the device whose screen shows this code: it shows their screens from its next look."""
    c = re.sub(r"[^A-Z0-9]", "", str(code or "").upper())
    r = db.one("SELECT * FROM prt_trmnl_devices WHERE code = %s AND owner IS NULL", (c,)) if len(c) == 6 else None
    if not r:
        raise NotFound("No screen is waiting with this code (it shows it until someone takes it)")
    trmnlpush.ensure_password(user)  # what its screens are read with: the person's own "TRMNL" app password
    d = _row(r)
    have = [s["key"] for s in trmnl.screens(user)]
    d["settings"] = {"playlist": [{"layout": "full", "screens": [k]} for k in have] or [{"layout": "full", "screens": ["today"]}], "refresh": 900}
    d["state"] = {k: v for k, v in d["state"].items() if k in ("seen", "volts", "percent", "rssi", "firmware")}
    db.ex("UPDATE prt_trmnl_devices SET owner = %s, settings = %s, state = %s WHERE id = %s AND owner IS NULL",
          (user["id"], json.dumps(d["settings"]), json.dumps(d["state"]), d["id"]))
    credentials.declare(APP, [{"name": _cred(d["id"]), "label": f"TRMNL screen {d['mac']} ({user.get('name')}): its key",
                               "hint": "the key the device signs its requests with (Settings › TRMNL on the start page); removed with the device"}])
    return public(get(d["id"]))


def _mine(user, dev_id: int) -> dict:
    d = get(dev_id)
    if d is None or d["owner"] != user["id"]:
        raise NotFound("No such TRMNL screen of yours")
    return d


def configure(user, dev_id: int, b: dict) -> dict:
    """Body: {name?, refresh? (seconds, one of REFRESH), bits? (1|2|4), playlist? [{layout, screens}], pair? (true:
    open Pair again for ten minutes)}."""
    d = _mine(user, dev_id)
    trmnlpush.ensure_password(user)  # revoked in Settings › Account since: saving the device makes it again
    if "name" in b:
        d["name"] = " ".join(str(b.get("name") or "").split())[:60]
        _save(d, "name")
    if "refresh" in b:
        if b["refresh"] not in REFRESH:
            raise Invalid("A screen looks again every 5, 10, 15 or 30 minutes, or every 1, 2 or 4 hours")
        d["settings"]["refresh"] = b["refresh"]
    if "bits" in b:
        if b["bits"] not in MODELS.get(d["model"], ("", (1, 2), 1.0))[1]:
            raise Invalid("This screen cannot show that many grays")
        d["settings"]["bits"] = b["bits"]
    if "playlist" in b:
        items = b["playlist"] if isinstance(b["playlist"], list) else []
        if not 1 <= len(items) <= 12:
            raise Invalid("A screen shows 1 to 12 things in turn")
        may = {s["key"] for s in trmnl.screens(user)}
        out = []
        for it in items:
            layout = it.get("layout") if isinstance(it, dict) else None
            if layout not in trmnldraw.LAYOUTS:
                raise Invalid(f"No layout {layout!r}")
            want = it.get("screens") if isinstance(it.get("screens"), list) else []
            if len(want) != len(trmnldraw.LAYOUTS[layout]) or any(s not in may for s in want):
                raise Invalid(f"Layout {layout} takes {len(trmnldraw.LAYOUTS[layout])} of your screens")
            out.append({"layout": layout, "screens": want})
        d["settings"]["playlist"] = out
        d["state"].pop("shown", None)
        d["state"]["at"] = -1
    if "pair" in b:
        if b["pair"]:
            d["state"]["pairUntil"] = time.time() + PAIR_AGAIN
        else:
            d["state"].pop("pairUntil", None)
    _save(d)
    return public(d)


def address():
    """The address to give a device (its Wi-Fi setup page, "custom server"): the start page inside the network, since
    a device cannot sign in through Cloudflare Access or a reverse proxy's sign-in. None when the start page listens
    on this machine only (HOST=127.0.0.1) or is in a container without INTERNAL_URL: the page then says what to do."""
    u = suite.local_url(APP)
    if not u or re.match(r"https?://(127\.|localhost|\[::1\])", u):
        return None
    return u


def preview(user, dev_id: int, at: int = 0, layout: str = "", screens: list = None) -> bytes:
    """What the device would show now (Settings › TRMNL's picture): entry `at` of its playlist, or, while its
    playlist is being edited, any layout with any of the person's screens."""
    d = _mine(user, dev_id)
    if not layout:
        return _draw(d, max(0, int(at)), False)[0]
    may = {s["key"] for s in trmnl.screens(user)}
    screens = screens or []
    if layout not in trmnldraw.LAYOUTS or len(screens) != len(trmnldraw.LAYOUTS[layout]) or any(k not in may for k in screens):
        raise NotFound("No such layout, or not that many of your screens")
    conf = trmnlpush.settings(user["id"])
    who = trmnlpush.asker(user["id"])
    datas = [(k, trmnl.build(who, k, conf["tz"], conf["clock"] == 24)) for k in screens]
    bits = grays(d)
    return trmnldraw.png(render(datas, layout, bits, scale(d), d["width"], d["height"]), bits)


def remove(user, dev_id: int) -> None:
    """The device is forgotten: its key goes, and it shows a code again at its next look (it is nobody's)."""
    d = _mine(user, dev_id)
    _drop(d["id"])
    trmnlpush.release(user["id"])


def forget_person(uid: int) -> int:
    """Deleting a person (app/persondata.py): their devices go with them. Returns how many."""
    mine = devices_of(uid)
    for d in mine:
        _drop(d["id"])
    return len(mine)
