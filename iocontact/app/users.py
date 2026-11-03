"""Accounts, roles, sessions and app passwords.

Roles as in iopix: viewer (reads), editor (changes contacts), admin (also settings and users).
Each account gets its own private address book; the Family book is shared by everyone.
Web sessions are signed HttpOnly cookies valid 30 days. CardDAV / LDAP clients use HTTP Basic or an LDAP bind with
either the account password or an app password (one per device, revocable, shown once).
"""
import base64
import hashlib
import hmac
import os
import re
import secrets
import time

from app import config, db

COOKIE = "ioc_session"
SESSION_DAYS = 30
ROLES = ("viewer", "editor", "admin")
_secret_cache: bytes | None = None


# ---------------------------------------------------------------- passwords

def hash_pw(pw: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${base64.b64encode(salt).decode()}${base64.b64encode(h).decode()}"


def check_pw(pw: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, salt, h = stored.split("$")
    got = hashlib.scrypt(pw.encode(), salt=base64.b64decode(salt), n=2 ** 14, r=8, p=1, dklen=32)
    return hmac.compare_digest(got, base64.b64decode(h))


def secret() -> bytes:
    global _secret_cache
    if _secret_cache is None:
        r = db.one("SELECT v FROM meta WHERE k = 'secret'")
        if not r:
            db.ex("INSERT IGNORE INTO meta (k, v) VALUES ('secret', %s)", (secrets.token_hex(32),))
            r = db.one("SELECT v FROM meta WHERE k = 'secret'")
        _secret_cache = bytes.fromhex(r["v"])
    return _secret_cache


# ---------------------------------------------------------------- accounts

NAME_RE = re.compile(r"^[A-Za-z0-9._@-]{1,64}$")


def public(u: dict | None) -> dict | None:
    if not u:
        return None
    return {"id": u["id"], "name": u["name"], "displayName": u.get("display_name") or u["name"], "email": u.get("email"),
            "role": u["role"], "hasPassword": bool(u.get("pw_hash")), "meContactId": u.get("me_contact_id")}


def get(uid: int) -> dict | None:
    return db.one("SELECT * FROM users WHERE id = %s", (uid,))


def find(name_or_email: str) -> dict | None:
    s = (name_or_email or "").strip()
    if not s:
        return None
    return (db.one("SELECT * FROM users WHERE name = %s", (s,))
            or db.one("SELECT * FROM users WHERE email = %s ORDER BY id LIMIT 1", (s,)))


def all_users() -> list[dict]:
    return db.q("SELECT * FROM users ORDER BY name")


def any_users() -> bool:
    return bool(db.one("SELECT 1 AS x FROM users LIMIT 1"))


def create(name: str, password: str | None, role: str = "editor", display_name: str | None = None, email: str | None = None) -> dict:
    if not NAME_RE.match(name or ""):
        raise ValueError("A user name of letters, digits and . _ @ - (64 at most)")
    if role not in ROLES:
        raise ValueError("Unknown role")
    if password is not None and len(password) < 8:
        raise ValueError("Passwords need 8 characters or more")
    if find(name):
        raise ValueError("That name is taken")
    with db.tx():
        uid = db.ex("INSERT INTO users (name, display_name, email, role, pw_hash) VALUES (%s, %s, %s, %s, %s)",
                    (name, display_name or None, email or None, role, hash_pw(password) if password else None))
        db.ex("INSERT INTO addressbooks (owner_id, slug, name, description) VALUES (%s, 'personal', 'Personal', %s)",
              (uid, f"{display_name or name}'s private contacts"))
    return get(uid)


def update(uid: int, **fields) -> dict:
    allowed = {"display_name", "email", "role", "me_contact_id"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if "role" in sets and sets["role"] not in ROLES:
        raise ValueError("Unknown role")
    if sets:
        db.ex("UPDATE users SET " + ", ".join(f"{k} = %s" for k in sets) + " WHERE id = %s", (*sets.values(), uid))
    if fields.get("password"):
        if len(fields["password"]) < 8:
            raise ValueError("Passwords need 8 characters or more")
        db.ex("UPDATE users SET pw_hash = %s WHERE id = %s", (hash_pw(fields["password"]), uid))
    return get(uid)


def delete(uid: int) -> None:
    db.ex("DELETE FROM users WHERE id = %s", (uid,))


def ensure_admin_from_env() -> None:
    if config.ADMIN_USER and config.ADMIN_PASSWORD and not any_users():
        create(config.ADMIN_USER, config.ADMIN_PASSWORD, "admin")


def can_write(u: dict | None) -> bool:
    return bool(u) and u["role"] in ("editor", "admin")


def is_admin(u: dict | None) -> bool:
    return bool(u) and u["role"] == "admin"


# ---------------------------------------------------------------- sessions

def make_session(uid: int) -> str:
    exp = int(time.time()) + SESSION_DAYS * 86400
    body = f"{uid}.{exp}"
    sig = hmac.new(secret(), body.encode(), hashlib.sha256).hexdigest()[:40]
    return f"{body}.{sig}"


def user_from_session(token: str | None) -> dict | None:
    try:
        uid, exp, sig = (token or "").split(".")
        if int(exp) < time.time():
            return None
        good = hmac.new(secret(), f"{uid}.{exp}".encode(), hashlib.sha256).hexdigest()[:40]
        if not hmac.compare_digest(sig, good):
            return None
        return get(int(uid))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------- app passwords

def create_app_password(uid: int, label: str) -> str:
    """Returns the password (shown once): ioc-XXXXXXXX-<secret>."""
    prefix = secrets.token_hex(4)
    pw = f"ioc-{prefix}-{secrets.token_urlsafe(18)}"
    db.ex("INSERT INTO app_passwords (user_id, label, prefix, pw_hash) VALUES (%s, %s, %s, %s)",
          (uid, (label or "Device")[:128], prefix, hash_pw(pw)))
    return pw


def list_app_passwords(uid: int) -> list[dict]:
    return [{"id": r["id"], "label": r["label"], "created": r["created"].isoformat() if r["created"] else None,
             "lastUsed": r["last_used"].isoformat() if r["last_used"] else None}
            for r in db.q("SELECT * FROM app_passwords WHERE user_id = %s ORDER BY created", (uid,))]


def delete_app_password(uid: int, pid: int) -> None:
    db.ex("DELETE FROM app_passwords WHERE id = %s AND user_id = %s", (pid, uid))


_auth_cache: dict = {}


def authenticate(name: str, password: str) -> dict | None:
    """Account password or app password; for CardDAV (HTTP Basic), LDAP binds and the sign-in form.
    Successful checks are cached for a minute: scrypt is slow on purpose and DAV clients send Basic on every request."""
    key = hashlib.sha256(f"{name}\0{password}".encode()).hexdigest()
    hit = _auth_cache.get(key)
    if hit and hit[0] > time.time():
        return get(hit[1])
    u = find(name)
    if not u or not password:
        return None
    ok = False
    m = re.match(r"^ioc-([0-9a-f]{8})-", password)
    if m:
        for r in db.q("SELECT * FROM app_passwords WHERE user_id = %s AND prefix = %s", (u["id"], m.group(1))):
            if check_pw(password, r["pw_hash"]):
                db.ex("UPDATE app_passwords SET last_used = NOW() WHERE id = %s", (r["id"],))
                ok = True
                break
    if not ok:
        ok = check_pw(password, u.get("pw_hash"))
    if ok:
        if len(_auth_cache) > 500:
            _auth_cache.clear()
        _auth_cache[key] = (time.time() + 60, u["id"])
        return u
    return None


def forget_cached_auth() -> None:
    _auth_cache.clear()


# ---------------------------------------------------------------- calendar feed tokens

def calendar_token(uid: int) -> str:
    r = db.one("SELECT token FROM calendar_tokens WHERE user_id = %s ORDER BY id LIMIT 1", (uid,))
    if r:
        return r["token"]
    tok = secrets.token_hex(20)
    db.ex("INSERT INTO calendar_tokens (user_id, token) VALUES (%s, %s)", (uid, tok))
    return tok


def reset_calendar_token(uid: int) -> str:
    db.ex("DELETE FROM calendar_tokens WHERE user_id = %s", (uid,))
    return calendar_token(uid)


def user_from_calendar_token(tok: str) -> dict | None:
    r = db.one("SELECT user_id FROM calendar_tokens WHERE token = %s", (tok,))
    return get(r["user_id"]) if r else None
