"""Accounts, roles, sessions and app passwords: the shared ioThing accounts (iosuite-shared), seen from ioCalendar.

Roles as in the rest of the suite: viewer (reads the shared calendars and keeps their own), editor (changes the shared
calendars too), admin (also settings and users); an account holds a role per app, a suite admin is admin everywhere.
Web sessions are the suite's cookie (shared by the apps on the domain). CalDAV clients, the REST API and MCP use HTTP
Basic or a bearer app password (one per device, revocable, shown once). The subscription links (/ics/...) carry a
private token per account instead, since calendar apps cannot sign in to a subscription.
"""
import secrets

from iosuite_shared import apppasswords, users as shared
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
    adopt_old_scopes()


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
    or the web app), the kind the Apple profile puts on a phone. The scope is kept with the password in the Shared
    ioSuite database (ios_app_passwords.scope) and enforced by iosuite-shared's middleware."""
    return apppasswords.create(uid, APP, label, apppasswords.DAV if caldav_only else "")


def adopt_old_scopes() -> None:
    """0.13.0: the CalDAV-only marks 0.11.0 kept in ioCalendar's own cal_app_password_scopes move to the shared
    column, once, and that table goes. Remove once every server has run 0.13.0."""
    if not db.one("SELECT 1 AS x FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'cal_app_password_scopes'"):
        return
    for r in db.q("SELECT prefix FROM cal_app_password_scopes"):
        apppasswords.set_scope(APP, r["prefix"], apppasswords.DAV)
    db.ex("DROP TABLE cal_app_password_scopes")


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
