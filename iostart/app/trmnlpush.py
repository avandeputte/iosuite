"""TRMNL push: the start page sends a person's TRMNL screens to TRMNL's webhooks itself, for a TRMNL cloud that cannot
reach the suite (inside the network only, or behind Cloudflare Access). app/trmnl.py has the screens.

What a person set (Settings › TRMNL): for each screen, the Webhook URL of the TRMNL plugin they imported for it (TRMNL:
the plugin's settings), their time zone and 12/24-hour clock. The webhook URLs and the app password the data is read
with are kept with the suite's keys and tokens (iosuite_shared.credentials, app iostart):

    trmnl_<user id>_<screen>   the screen's webhook URL
    trmnl_<user id>_pw         an ioStart app password of the person's (label "TRMNL"), made when they first add one

so a suite admin sees them (Settings › Global settings › Keys and tokens), and the person can revoke the app password
in Settings › Account like any other (pushing then stops, and says so). The rest (time zone, clock, what was sent
when) is the person's own setting (prt_settings user:<id>:trmnl), gone with their account.

A screen is made every SCREENS[...]["every"] minutes (15 at least) and sent when it changed, or after RESEND minutes
anyway: TRMNL takes 12 pushes an hour per plugin (30 with TRMNL+) and 5 KB each (trmnl.LIMIT).
"""
import hashlib
import json
import logging
import threading
import time
import urllib.error
import urllib.request

from iosuite_shared import apppasswords, credentials, outbound, users
from iosuite_shared.errors import Invalid

from app import config, db, trmnl

log = logging.getLogger("iostart.trmnl")
APP = config.APP
TICK = 60          # seconds between looks at what is due
MIN_EVERY = 15     # minutes: the shortest wait between two makes of a screen
RESEND = 180       # minutes: a screen that did not change is sent again after this long anyway
TIMEOUT = 15
_lock = threading.Lock()
_thread = {"t": None, "stop": None}


def _key(uid: int) -> str:
    return f"user:{int(uid)}:trmnl"


def _cred(uid: int, what: str) -> str:
    return f"trmnl_{int(uid)}_{what}"


def settings(uid: int) -> dict:
    """{tz, clock, sent: {screen: {at, ok, error, hash}}}."""
    try:
        d = json.loads(db.get_setting(_key(uid)) or "{}")
    except ValueError:
        d = {}
    return {"tz": d.get("tz") or "", "clock": 24 if d.get("clock") == 24 else 12, "sent": d.get("sent") or {}}


def _save(uid: int, s: dict) -> None:
    db.set_setting(_key(uid), json.dumps(s))


def hooks(uid: int) -> dict:
    """{screen: webhook URL} the person set."""
    return {k: v for k in trmnl.SCREENS if (v := credentials.get(APP, _cred(uid, k)))}


def state(user) -> dict:
    """What Settings › TRMNL shows: the screens this person may have, each with whether it is pushed (never the URL
    itself, which is a secret of sorts: anyone with it can write to that plugin) and how its last push went."""
    uid = user["id"]
    s, h = settings(uid), hooks(uid)
    return {"tz": s["tz"], "clock": s["clock"], "passwordSet": bool(credentials.get(APP, _cred(uid, "pw"))),
            "screens": [{**x, "push": x["key"] in h, "sent": {k: v for k, v in (s["sent"].get(x["key"]) or {}).items() if k not in ("hash", "made")}}
                        for x in trmnl.screens(user)]}


def _allowed(user):
    """Where this person's pushes may go: the internet; a server admin's also to the home network (a TRMNL server of
    their own that takes webhooks), never this machine."""
    return outbound.not_this_machine if user.get("role") == "admin" else outbound.public


def configure(user, b: dict) -> dict:
    """Body: {tz?, clock? (12|24), hooks?: {screen: URL | ''}}. An empty URL stops pushing that screen; the first URL
    makes the app password the screens are read with, the last one gone revokes it."""
    uid = user["id"]
    s = settings(uid)
    if "tz" in b:
        tz = str(b.get("tz") or "")
        s["tz"] = tz if trmnl.wall._zone_ok(tz) else ""
    if "clock" in b:
        s["clock"] = 24 if str(b.get("clock")) == "24" else 12
    for screen, url in (b.get("hooks") or {}).items():
        if screen not in trmnl.SCREENS:
            raise Invalid(f"No TRMNL screen {screen!r}")
        url = str(url or "").strip()
        if url:
            if len(url) > 500:
                raise Invalid("That webhook address is too long")
            outbound.check(url, _allowed(user))
            if not url.startswith("https://") and user.get("role") != "admin":
                raise Invalid("TRMNL's webhook addresses start with https://")
        credentials.declare(APP, [{"name": _cred(uid, screen), "label": f"TRMNL webhook: {trmnl.SCREENS[screen]['name']} ({user.get('name')})",
                                   "hint": "the webhook URL of a TRMNL plugin (Settings › TRMNL on the start page)"}])
        credentials.put(APP, _cred(uid, screen), url or None, by=user.get("name"))
        s["sent"].pop(screen, None)
    have = hooks(uid)
    if have and not credentials.get(APP, _cred(uid, "pw")):
        if user.get("passwordless"):
            raise Invalid("A one-click account cannot have app passwords, which pushing to TRMNL reads with; give the account a password first")
        pw = apppasswords.create(uid, apppasswords.HUB, "TRMNL", "")
        credentials.declare(APP, [{"name": _cred(uid, "pw"), "label": f"TRMNL: app password of {user.get('name')}",
                                   "hint": "made by Settings › TRMNL; revoked there, or in Settings › Account › App passwords"}])
        credentials.put(APP, _cred(uid, "pw"), pw, by=user.get("name"))
    if not have:
        stop(uid)
    _save(uid, s)
    return state(user)


def stop(uid: int) -> None:
    """No screen pushed any more: the app password goes (revoked) and so do the keys."""
    pw = credentials.get(APP, _cred(uid, "pw"))
    parts = pw.split("-")
    if len(parts) >= 3:
        from iosuite_shared import db as shared_db
        for r in shared_db.q("SELECT id FROM ios_app_passwords WHERE user_id = %s AND app = %s AND prefix = %s", (uid, apppasswords.HUB, parts[1])):
            apppasswords.delete(uid, r["id"])
    for k in [*trmnl.SCREENS, "pw"]:
        credentials.remove(APP, _cred(uid, k))


class Asker:
    """What widgets.fetch and wall.feed read of a request (headers, cookies, state.user), for a push that no request
    started: the person's TRMNL app password, passed on to each app as their own sign-in."""

    class _State:
        pass

    def __init__(self, user: dict, password: str):
        self.headers = {"authorization": f"Bearer {password}"}
        self.cookies = {}
        self.state = Asker._State()
        self.state.user = user


def _asker(uid: int):
    pw = credentials.get(APP, _cred(uid, "pw"))
    if not pw:
        raise Invalid("No app password to read with (open Settings › TRMNL and save a webhook address again)")
    user = apppasswords.authenticate(None, pw, apppasswords.HUB)
    if not user:
        raise Invalid("The TRMNL app password was revoked (Settings › Account); save a webhook address again in Settings › TRMNL")
    from app.auth import auth
    return Asker(auth.decorate(user), pw)


def _post(url: str, data: dict, user) -> None:
    body = json.dumps({"merge_variables": data}, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json", "User-Agent": "ioSuite TRMNL"})
    try:
        with outbound.opener(_allowed(user), redirects=False).open(req, timeout=TIMEOUT) as r:
            r.read(2048)
    except urllib.error.HTTPError as e:
        why = {403: "TRMNL refused it (the plugin's strategy must be Webhook)", 404: "TRMNL has no such plugin (was it deleted?)",
               422: "TRMNL would not take it (too big?)", 429: "TRMNL says too many pushes this hour"}.get(e.code, f"TRMNL answered {e.code}")
        raise Invalid(why)
    except (urllib.error.URLError, OSError) as e:
        raise Invalid(f"TRMNL did not answer ({type(getattr(e, 'reason', e)).__name__})")


def push(uid: int, only: str = None, force: bool = False, now: float = None) -> dict:
    """Make and send what is due of this person's screens (only: that one; force: whether due or not, and sent even
    unchanged). {screen: {at, ok, error}} for those it tried."""
    now = now or time.time()
    s = settings(uid)
    h = hooks(uid)
    tried = {}
    due = [k for k in h if (not only or k == only)
           and (force or now - (s["sent"].get(k) or {}).get("made", 0) >= 60 * max(MIN_EVERY, trmnl.SCREENS[k]["every"]) - 5)]
    if not due:
        return tried
    try:
        asker = _asker(uid)
    except Invalid as e:
        for k in due:
            s["sent"][k] = {**(s["sent"].get(k) or {}), "made": now, "ok": False, "error": str(e)}
            tried[k] = {"ok": False, "error": str(e)}
        _save(uid, s)
        return tried
    for k in due:
        last = s["sent"].get(k) or {}
        try:
            data = trmnl.build(asker, k, s["tz"], s["clock"] == 24)
            # the time it was made changes every time: what counts as a change is the rest
            digest = hashlib.sha256(json.dumps({a: v for a, v in data.items() if a != "updated"}, sort_keys=True).encode()).hexdigest()
            if force or digest != last.get("hash") or now - (last.get("at") or 0) >= 60 * RESEND or not last.get("ok"):
                _post(h[k], data, asker.state.user)
                last = {"at": now, "ok": True, "error": None, "hash": digest}
            last["made"] = now
        except Invalid as e:
            last = {**last, "made": now, "ok": False, "error": str(e)}
        except Exception as e:  # noqa: BLE001  one screen failing leaves the others
            log.warning("TRMNL push of %s for user %s: %s", k, uid, e)
            last = {**last, "made": now, "ok": False, "error": type(e).__name__}
        s["sent"][k] = last
        tried[k] = {kk: v for kk, v in last.items() if kk not in ("hash", "made")}
    _save(uid, s)
    return tried


def _people() -> list:
    rows = db.q("SELECT name FROM prt_settings WHERE name LIKE %s", ("user:%:trmnl",))
    return [int(r["name"].split(":")[1]) for r in rows if r["name"].split(":")[1].isdigit()]


def tick() -> None:
    for uid in _people():
        if not users.get(uid, APP):
            continue
        try:
            push(uid)
        except Exception as e:  # noqa: BLE001
            log.warning("TRMNL push for user %s: %s", uid, e)


def start() -> None:
    """The loop that pushes, in a thread of its own (main.py, at start; TRMNL_PUSH=0 leaves it off: the tests)."""
    if not config.TRMNL_PUSH or _thread["t"]:
        return
    stop_ev = threading.Event()

    def loop():
        while not stop_ev.wait(TICK):
            try:
                tick()
            except Exception as e:  # noqa: BLE001  the database away for a moment: next minute
                log.warning("TRMNL push: %s", e)

    _thread["stop"] = stop_ev
    _thread["t"] = threading.Thread(target=loop, name="trmnl-push", daemon=True)
    _thread["t"].start()


def halt() -> None:
    if _thread["stop"]:
        _thread["stop"].set()
    _thread["t"] = None
