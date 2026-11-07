"""Accounts, roles, sessions and app passwords: the shared ioThing accounts (iosuite-shared), seen from ioCalendar.

Roles as in the rest of the suite: viewer (reads the shared calendars and keeps their own), editor (changes the shared
calendars too), admin (also settings and users); an account holds a role per app, a suite admin is admin everywhere.
Web sessions are the suite's cookie (shared by the apps on the domain). CalDAV clients, the REST API and MCP use HTTP
Basic or a bearer app password (one per device, revocable, shown once). The subscription links (/ics/...) carry a
private token per account instead, since calendar apps cannot sign in to a subscription.
"""
import base64
import binascii
import re
import secrets

from iosuite_shared import apppasswords, db as shared_db, users as shared
from iosuite_shared.fastapi import public_user

from app import db
from app.auth import APP

ROLES = shared.APP_ROLES


def public(u: dict | None) -> dict | None:
    """The account as the web app sees it: the same fields /api/status carries in every app of the suite."""
    return public_user(u)


def get(uid: int) -> dict | None:
    return shared.get(uid, APP)


def find(name_or_email: str) -> dict | None:
    return shared.find(name_or_email, APP)


def all_users() -> list[dict]:
    return sorted(shared.list_users(APP), key=lambda u: u["name"].lower())


def any_users() -> bool:
    return shared.any_users()


def create(name: str, password: str | None, role: str = "editor", display_name: str | None = None, email: str | None = None) -> dict:
    return shared.create(name, password or "", role, APP, email=email or "", display_name=display_name or "")


def update(uid: int, **f) -> dict:
    kw = {}
    if "display_name" in f:
        kw["display_name"] = f["display_name"] or ""
    if "email" in f:
        kw["email"] = f["email"] or ""
    if f.get("role") is not None:
        kw["role"], kw["app"] = f["role"], APP
    if f.get("password") is not None:
        kw["password"] = f["password"]
    if kw:
        shared.update(uid, **kw)
    return get(uid)


def init() -> None:
    """The Shared ioSuite database's tables, and the ADMIN_USER / ADMIN_PASSWORD account on a first start with no accounts."""
    shared.init()


def can_write(u: dict | None) -> bool:
    return bool(u) and u.get("role") in ("editor", "admin")


def is_admin(u: dict | None) -> bool:
    return bool(u) and u.get("role") == "admin"


def settings(uid: int) -> dict:
    return shared.get_settings(uid, APP)


def authenticate(name: str, password: str) -> dict | None:
    return apppasswords.authenticate(name, password, APP)


def create_app_password(uid: int, label: str, caldav_only: bool = False) -> str:
    """A new app password for this account; caldav_only: it works for CalDAV and nothing else (not the REST API, MCP
    or the web app), the kind the Apple profile puts on a phone."""
    pw = apppasswords.create(uid, APP, label)
    if caldav_only:
        prefix = pw.split("-")[1]
        row = shared_db.one("SELECT id FROM ios_app_passwords WHERE prefix = %s AND app = %s", (prefix, APP))
        db.ex("INSERT INTO cal_app_password_scopes (prefix, password_id, scope) VALUES (%s, %s, 'caldav')",
              (prefix, row["id"] if row else None))
    return pw


_PW = re.compile(r"^[a-z0-9]+-([0-9a-f]{8})-")


def caldav_only(authorization: str | None) -> bool:
    """Whether the Authorization header (Basic or Bearer) carries an app password that is for CalDAV only."""
    if not authorization:
        return False
    kind, _, val = authorization.partition(" ")
    pw = val.strip()
    if kind.lower() == "basic":
        try:
            pw = base64.b64decode(pw).decode("utf-8", "replace").partition(":")[2]
        except (ValueError, binascii.Error):
            return False
    elif kind.lower() != "bearer":
        return False
    m = _PW.match(pw)
    return bool(m) and db.one("SELECT 1 AS x FROM cal_app_password_scopes WHERE prefix = %s AND scope = 'caldav'", (m.group(1),)) is not None


def caldav_only_ids(uid: int) -> list[int]:
    """The ids (as /api/auth/app-passwords lists them) of this account's CalDAV-only app passwords."""
    ids = [r["password_id"] for r in db.q("SELECT password_id FROM cal_app_password_scopes WHERE password_id IS NOT NULL")]
    if not ids:
        return []
    mine = {r["id"] for r in shared_db.q(f"SELECT id FROM ios_app_passwords WHERE user_id = %s AND id IN ({db.marks(len(ids))})", (uid, *ids))}
    return [i for i in ids if i in mine]


def forget_cached_auth() -> None:
    apppasswords.forget()
    shared.invalidate()
    from app import members
    members.forget()


# ---------------------------------------------------------------- subscription links (ioCalendar's own)

def feed_token(uid: int) -> str:
    r = db.one("SELECT token FROM cal_feed_tokens WHERE user_id = %s ORDER BY id LIMIT 1", (uid,))
    if r:
        return r["token"]
    tok = secrets.token_hex(20)
    db.ex("INSERT INTO cal_feed_tokens (user_id, token) VALUES (%s, %s)", (uid, tok))
    return tok


def reset_feed_token(uid: int) -> str:
    db.ex("DELETE FROM cal_feed_tokens WHERE user_id = %s", (uid,))
    return feed_token(uid)


def user_from_feed_token(tok: str) -> dict | None:
    r = db.one("SELECT user_id FROM cal_feed_tokens WHERE token = %s", (tok,))
    if not r:
        return None
    u = get(r["user_id"])
    return u if u and u.get("role") != "none" else None
