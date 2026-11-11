"""Accounts, roles, sessions and app passwords: the shared ioThing accounts (iosuite-shared), seen from ioCalendar.

Roles as in the rest of the suite: viewer (reads the shared calendars), member (also keeps their own), editor (changes the shared
calendars too), admin (also settings and users); an account holds a role per app, a suite admin is admin everywhere.
Web sessions are the suite's cookie (shared by the apps on the domain). CalDAV clients, the REST API and MCP use HTTP
Basic or a bearer app password (one per device, revocable, shown once). The subscription links (/ics/...) carry a
private token per account instead, since calendar apps cannot sign in to a subscription.

What is here is ioCalendar's own: the accounts with their role here, app passwords with the CalDAV-only scope, and the
subscription links. Whether an account may write or is an admin is asked of iosuite_shared.users directly.
"""
import secrets

from iosuite_shared import apppasswords, users as shared

from app import db
from app.auth import APP

ROLES = shared.APP_ROLES


def get(uid: int) -> dict | None:
    return shared.get(uid, APP)


def find(name_or_email: str) -> dict | None:
    return shared.find(name_or_email, APP)


def all_users() -> list[dict]:
    return sorted(shared.list_users(APP), key=lambda u: u["name"].lower())


def init() -> None:
    """The Shared ioSuite database's tables, and the ADMIN_USER / ADMIN_PASSWORD account on a first start with no accounts."""
    shared.init()


def create_app_password(uid: int, label: str, caldav_only: bool = False) -> str:
    """A new app password for this account; caldav_only: it works for CalDAV and nothing else (not the REST API, MCP
    or the web app), the kind the Apple profile puts on a phone. The scope is kept with the password in the Shared
    ioSuite database (ios_app_passwords.scope) and enforced by iosuite-shared's middleware."""
    return apppasswords.create(uid, APP, label, apppasswords.DAV if caldav_only else "")


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
