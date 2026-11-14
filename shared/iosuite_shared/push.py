"""Notifications: web push from any app of the suite to the people who turned it on.

A person turns notifications on once per device, in any app (Settings › Account › Notifications): the browser or the
home-screen app makes a push subscription, which is kept in the Shared ioSuite database with the account. From then on
every app reaches that device, whichever app it was turned on in, and a tap opens the app the notification is about.
Each person picks what they get; the choices are the account's, for every device.

    from iosuite_shared import push
    for u in push.recipients("tasks"):                      # who wants this kind and has a device for it
        push.notify(u["id"], "tasks", "Pack the swim bag", "Due now", url=push.link("iotask", "#/today"),
                    once=f"task:{uid}:{due}")               # once: never twice for this key (all apps, restarts)
    push.notify_admins("backups", "Backup failed", "...")   # every suite admin who wants it

The kinds (KINDS) say which app a kind belongs to: somebody who does not use ioHealth is not offered, and never
sent, its goal alerts; the admin kinds (a failed backup, a new version) are for suite admins only.

The sender's key pair (VAPID, RFC 8292) is made the first time it is needed and kept with the suite's keys and tokens
(Settings › Global settings › Keys and tokens, "Notifications sender key"); clearing it there makes a new one, and every
device has to turn notifications on again. Messages are encrypted for the device (RFC 8291, aes128gcm), so the push
service in between (Apple's, Google's, Mozilla's) cannot read them. No extra package: `cryptography` and `pyjwt` come
with proxy sign-in already.
"""
import base64
import datetime as dt
import hashlib
import json
import logging
import os
import re
import struct
import time
import urllib.error
import urllib.parse
import urllib.request

import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from iosuite_shared import credentials, db, outbound, suite, users
from iosuite_shared.errors import Invalid

log = logging.getLogger("iosuite_shared.push")

KEY_APP, KEY_NAME = "", "push_vapid"   # the suite's own key (Keys and tokens, "Whole suite")
PREFS = "notifications"                  # ios_user_data (app '') of each account: {"off": [kinds], "morning": "HH:MM"}
MORNING = "08:00"
SUBJECT = "https://github.com/avandeputte/iosuite"  # who sends, for the push services (a URL or a mailto:)

# What there is to get. app: the app it comes from (offered only to people who use it); admin: suite admins only.
KINDS = [
    {"kind": "tasks", "app": "iotask", "label": "Tasks", "hint": "When a task with a time is due, and in the morning what is due today"},
    {"kind": "events", "app": "iocalendar", "label": "Event reminders", "hint": "The reminders set on events"},
    {"kind": "birthdays", "app": "iocontact", "label": "Birthdays", "hint": "In the morning, whose birthday or anniversary it is"},
    {"kind": "health", "app": "iohealth", "label": "Health goals", "hint": "When you reach one of your daily goals"},
    {"kind": "backups", "app": "iobackup", "label": "Failed backups", "hint": "When a backup does not finish", "admin": True},
    {"kind": "updates", "app": None, "label": "New version", "hint": "When a newer version of the suite is out", "admin": True},
]
KIND = {k["kind"]: k for k in KINDS}

FAILURES_TO_DROP = 10     # sends in a row a device did not take (and nothing taken for a week): it is gone
SENT_KEEP_DAYS = 120      # how long a `once` key is remembered
TIMEOUT = 10


# ------------------------------------------------------------------ helpers

def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def b64u_decode(s: str) -> bytes:
    s = str(s or "").strip()
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _hkdf(salt: bytes, ikm: bytes, info: bytes, n: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=n, salt=salt, info=info).derive(ikm)


def _raw_public(pub) -> bytes:
    return pub.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


# ------------------------------------------------------------------ the sender's key (VAPID)

def _private_key():
    """The suite's sender key; made (once, by whichever app gets there first) when there is none."""
    pem = credentials.get(KEY_APP, KEY_NAME)
    if not pem:
        new = ec.generate_private_key(ec.SECP256R1()).private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
        declare()
        if db.ex("UPDATE ios_credentials SET value = %s, updated_at = %s, updated_by = %s WHERE app = %s AND name = %s AND value = ''",
                 (new, int(time.time()), "made by itself", KEY_APP, KEY_NAME)):
            n = db.ex("DELETE FROM ios_push_devices")  # they were made for the old key: they would be refused
            if n:
                log.warning("a new notifications sender key: %d device(s) have to turn notifications on again", n)
        credentials.forget()
        pem = credentials.get(KEY_APP, KEY_NAME)
    try:
        return serialization.load_pem_private_key(pem.encode(), password=None)
    except (ValueError, TypeError) as e:
        raise Invalid("The notifications sender key is not a valid key; clear it under Keys and tokens to make a new one") from e


def declare() -> None:
    """The key's row under Keys and tokens (every app does this as it starts; the value is made when first needed)."""
    credentials.declare(KEY_APP, [{"name": KEY_NAME, "label": "Notifications sender key",
                                   "hint": "made by itself; clearing it makes a new one and every device turns notifications on again"}])


def public_key() -> str:
    """The applicationServerKey a browser subscribes with (base64url, uncompressed point)."""
    return b64u(_raw_public(_private_key().public_key()))


def _key_id() -> str:
    return hashlib.sha256(public_key().encode()).hexdigest()[:16]


def _vapid_header(endpoint: str) -> str:
    u = urllib.parse.urlsplit(endpoint)
    key = _private_key()
    token = jwt.encode({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600, "sub": SUBJECT}, key, algorithm="ES256")
    return f"vapid t={token}, k={b64u(_raw_public(key.public_key()))}"


# ------------------------------------------------------------------ encryption (RFC 8291)

def encrypt(p256dh: str, auth: str, payload: bytes, salt: bytes = None, server_key=None) -> bytes:
    """The body of a push message for this subscription: aes128gcm, one record."""
    ua_pub = b64u_decode(p256dh)
    secret = b64u_decode(auth)
    as_key = server_key or ec.generate_private_key(ec.SECP256R1())
    as_pub = _raw_public(as_key.public_key())
    shared = as_key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub))
    ikm = _hkdf(secret, shared, b"WebPush: info\x00" + ua_pub + as_pub, 32)
    salt = salt or os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    body = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    return salt + struct.pack("!I", 4096) + bytes([len(as_pub)]) + as_pub + body


# ------------------------------------------------------------------ devices

def _label(ua: str, standalone: bool) -> str:
    """'Vivaldi on Mac', 'Home-screen app on iPhone'..., from the User-Agent."""
    ua = ua or ""
    os_ = next((n for k, n in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Mac OS X", "Mac"), ("Macintosh", "Mac"),
                                ("Windows", "Windows"), ("CrOS", "ChromeOS"), ("Linux", "Linux")) if k in ua), "")
    br = next((n for k, n in (("Vivaldi", "Vivaldi"), ("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("FxiOS", "Firefox"),
                               ("CriOS", "Chrome"), ("Chrome/", "Chrome"), ("Safari/", "Safari")) if k in ua), "Browser")
    if standalone or (os_ in ("iPhone", "iPad") and br == "Safari" and "Safari/" not in ua):
        br = "Home-screen app"
    return f"{br} on {os_}" if os_ else br


def _endpoint_ok(endpoint: str) -> str:
    endpoint = str(endpoint or "").strip()
    if not endpoint.startswith("https://") or len(endpoint) > 1024:
        raise Invalid("Not a push subscription")
    outbound.check(endpoint)  # an address on the internet: the server posts to it
    return endpoint


def add_device(user_id: int, sub: dict, app: str, user_agent: str = "", standalone: bool = False) -> dict:
    """Keep a browser's push subscription ({endpoint, keys: {p256dh, auth}}) for this account. The same subscription
    again (or another account's on the same browser) replaces the row."""
    endpoint = _endpoint_ok((sub or {}).get("endpoint"))
    keys = (sub or {}).get("keys") or {}
    try:
        p256dh, auth = b64u_decode(keys.get("p256dh")), b64u_decode(keys.get("auth"))
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), p256dh)
    except (ValueError, TypeError) as e:
        raise Invalid("Not a push subscription") from e
    if len(auth) < 16:
        raise Invalid("Not a push subscription")
    h = hashlib.sha256(endpoint.encode()).hexdigest()
    now = int(time.time())
    db.ex("INSERT INTO ios_push_devices (user_id, endpoint, endpoint_hash, p256dh, auth, label, app, key_id, created_at) "
          "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE user_id = VALUES(user_id), p256dh = VALUES(p256dh), "
          "auth = VALUES(auth), label = VALUES(label), app = VALUES(app), key_id = VALUES(key_id), failures = 0",
          (user_id, endpoint, h, b64u(p256dh), b64u(auth), _label(user_agent, standalone)[:128], str(app or "")[:32], _key_id(), now))
    return next(d for d in devices(user_id) if d["endpointHash"] == h)


def devices(user_id: int) -> list:
    rows = db.q("SELECT d.id, d.label, d.app, d.created_at, d.last_ok_at, d.endpoint_hash, a.name AS app_name FROM ios_push_devices d "
                "LEFT JOIN ios_apps a ON a.app = d.app WHERE d.user_id = %s ORDER BY d.created_at", (user_id,))
    return [{"id": r["id"], "label": r["label"], "app": r["app"], "appName": r["app_name"] or r["app"], "created": r["created_at"],
             "lastOk": r["last_ok_at"], "endpointHash": r["endpoint_hash"]} for r in rows]


def remove_device(user_id: int, device_id: int = None, endpoint: str = None) -> int:
    if endpoint:
        return db.ex("DELETE FROM ios_push_devices WHERE user_id = %s AND endpoint_hash = %s",
                     (user_id, hashlib.sha256(str(endpoint).strip().encode()).hexdigest()))
    return db.ex("DELETE FROM ios_push_devices WHERE user_id = %s AND id = %s", (user_id, int(device_id or 0)))


# ------------------------------------------------------------------ what each person wants

def prefs(user_id: int) -> dict:
    p = users.get_value(user_id, "", PREFS, {}) or {}
    off = [k for k in (p.get("off") or []) if k in KIND]
    m = str(p.get("morning") or MORNING)
    return {"off": off, "morning": m if re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", m) else MORNING}


def set_prefs(user_id: int, kinds: dict = None, morning: str = None) -> dict:
    p = prefs(user_id)
    off = set(p["off"])
    for k, on in (kinds or {}).items():
        if k not in KIND:
            raise Invalid(f"Unknown kind of notification: {k}")
        (off.discard if on else off.add)(k)
    if morning is not None:
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(morning)):
            raise Invalid("The morning time is HH:MM")
        p["morning"] = str(morning)
    p["off"] = sorted(off)
    users.set_value(user_id, "", PREFS, p)
    return prefs(user_id)


def offered(user: dict) -> list:
    """The kinds this account may get: the ones of the apps it uses (and that are installed); the admin kinds for
    suite admins."""
    if not user:
        return []
    installed = {a["app"] for a in suite.apps()}
    out = []
    for k in KINDS:
        if k.get("admin") and not user.get("suiteAdmin"):
            continue
        if k["app"] and (k["app"] not in installed or users.role_of(user, k["app"]) == "none"):
            continue
        out.append(k)
    return out


def may_get(user: dict, kind: str) -> bool:
    return any(k["kind"] == kind for k in offered(user))


def wants(user_id: int, kind: str) -> bool:
    return kind not in prefs(user_id)["off"]


def recipients(kind: str) -> list:
    """The accounts that have a device, may get this kind and did not turn it off: [user dicts]."""
    if kind not in KIND:
        raise Invalid(f"Unknown kind of notification: {kind}")
    out = []
    for r in db.q("SELECT DISTINCT user_id FROM ios_push_devices"):
        u = users.get(r["user_id"], KIND[kind]["app"] or None)
        if u and wants(u["id"], kind) and may_get(u, kind):
            out.append(u)
    return out


def is_morning(user_id: int, now: dt.datetime = None, hours: float = 6) -> bool:
    """Whether this person's morning time (the server's local time) has come today, and not more than `hours` ago (a
    server that was off all morning does not send the morning summary in the evening)."""
    now = now or dt.datetime.now()
    hh, mm = (int(x) for x in prefs(user_id)["morning"].split(":"))
    at = dt.datetime.combine(now.date(), dt.time(hh, mm))
    return at <= now < at + dt.timedelta(hours=hours)


def was_sent(user_id: int, key: str) -> bool:
    """Whether a `once` key went out to this account already (to skip the work of making the message again)."""
    return bool(db.one("SELECT 1 FROM ios_push_sent WHERE user_id = %s AND tag = %s", (user_id, _tag(key))))


def link(app: str, path: str = "") -> str | None:
    """Where a tap takes the person: the app's address and a path or #route in it."""
    base = suite.url_of(app)
    if not base:
        return None
    return base.rstrip("/") + "/" + str(path or "").lstrip("/")


# ------------------------------------------------------------------ sending

def claim(user_id: int, key: str) -> bool:
    """Take the key for this account: True the first time (whichever app, process or restart asks), False after."""
    return bool(db.ex("INSERT IGNORE INTO ios_push_sent (user_id, tag, sent_at) VALUES (%s, %s, %s)", (user_id, _tag(key), int(time.time()))))


def _tag(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest() if len(key) > 191 else key


def _post(endpoint: str, body: bytes, headers: dict) -> int:
    """POST to the push service: its status code."""
    req = urllib.request.Request(endpoint, data=body, method="POST", headers=headers)
    try:
        with outbound.opener(redirects=False).open(req, timeout=TIMEOUT) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def deliver(device: dict, message: dict, ttl: int = 86400, urgency: str = "normal") -> int:
    """Send one message to one device row: the push service's status (0 when it could not be reached)."""
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode()
    body = encrypt(device["p256dh"], device["auth"], payload)
    headers = {"TTL": str(int(ttl)), "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream",
               "Urgency": urgency, "Authorization": _vapid_header(device["endpoint"])}
    try:
        return _post(device["endpoint"], body, headers)
    except Exception as e:  # noqa: BLE001 - one device that cannot be reached does not stop the others
        log.info("push to %s failed: %s", urllib.parse.urlsplit(device["endpoint"]).netloc, e)
        return 0


def _send(rows: list, message: dict, ttl: int, urgency: str) -> int:
    ok, now = 0, int(time.time())
    for d in rows:
        code = deliver(d, message, ttl, urgency)
        if 200 <= code < 300:
            ok += 1
            db.ex("UPDATE ios_push_devices SET last_ok_at = %s, failures = 0 WHERE id = %s", (now, d["id"]))
        elif code in (404, 410, 401, 403):  # unsubscribed, expired, or made for another sender key: gone for good
            db.ex("DELETE FROM ios_push_devices WHERE id = %s", (d["id"],))
            log.info("push device %s (%s) removed: the push service answered %s", d["id"], d["label"], code)
        else:
            db.ex("UPDATE ios_push_devices SET failures = failures + 1 WHERE id = %s", (d["id"],))
            if d["failures"] + 1 >= FAILURES_TO_DROP and (d["last_ok_at"] or d["created_at"]) < now - 7 * 86400:
                db.ex("DELETE FROM ios_push_devices WHERE id = %s", (d["id"],))
    return ok


def notify(user_id: int, kind: str, title: str, body: str = "", url: str = None, once: str = None, tag: str = None,
           ttl: int = 86400, urgency: str = "normal", check: bool = True) -> int:
    """Send one notification to every device of this account, if it wants this kind (check=False: it asked, as for a
    test). once: a key that is sent at most once per account. tag: a notification with the same tag replaces the one
    on the screen. How many devices took it."""
    if kind not in KIND and kind != "test":
        raise Invalid(f"Unknown kind of notification: {kind}")
    if check:
        u = users.get(user_id, (KIND[kind]["app"] or None) if kind in KIND else None)
        if not u or not wants(user_id, kind) or not may_get(u, kind):
            return 0
    rows = db.q("SELECT * FROM ios_push_devices WHERE user_id = %s", (user_id,))
    if not rows:
        return 0
    if once and not claim(user_id, once):
        return 0
    message = {"title": str(title or "")[:120], "body": str(body or "")[:600], "kind": kind, "url": url or None,
               "tag": (tag or once or "")[:64] or None, "app": KIND.get(kind, {}).get("app")}
    return _send(rows, message, ttl, urgency)


def notify_admins(kind: str, title: str, body: str = "", url: str = None, once: str = None, **kw) -> int:
    """notify() every suite admin who wants this kind."""
    return sum(notify(u["id"], kind, title, body, url, once, **kw) for u in recipients(kind))


def purge() -> int:
    """Forget the `once` keys after SENT_KEEP_DAYS (a daily chore of any app)."""
    return db.ex("DELETE FROM ios_push_sent WHERE sent_at < %s", (int(time.time()) - SENT_KEEP_DAYS * 86400,))


def overview(user: dict) -> dict:
    """For Settings › Account › Notifications: the key to subscribe with, the kinds this account is offered with
    whether each is on, the morning time, and its devices."""
    p = prefs(user["id"])
    return {"key": public_key(), "morning": p["morning"],
            "kinds": [{"kind": k["kind"], "label": k["label"], "hint": k["hint"], "on": k["kind"] not in p["off"], "admin": bool(k.get("admin"))}
                      for k in offered(user)],
            "devices": devices(user["id"])}
