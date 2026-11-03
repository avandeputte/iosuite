"""Accounts, roles, sessions and app passwords: the shared ioThing accounts (iothing-auth), seen from ioContacts.

Roles as in iopix: viewer (reads), editor (changes contacts), admin (also settings and users); an account holds a
role per app, a suite admin is admin everywhere. Each account gets its own private address book; the Family book is
shared by everyone. Web sessions are the suite's cookie (shared by the apps on the domain). CardDAV / LDAP clients
use HTTP Basic or an LDAP bind with either the account password or an app password (one per device, revocable,
shown once). This module keeps ioContacts' old names; the work is done by iothing_auth.
"""
import datetime as dt
import secrets

from iothing_auth import apppasswords, db as authdb, sessions, users as shared

from app import db
from app.auth import APP, row_of

COOKIE = sessions.COOKIE
SESSION_DAYS = sessions.SESSION_DAYS
ROLES = shared.APP_ROLES


def public(u: dict | None) -> dict | None:
    if not u:
        return None
    return {"id": u["id"], "name": u["name"], "displayName": u.get("display_name") or u["name"], "email": u.get("email"),
            "role": u["role"], "hasPassword": bool(u.get("pw_hash")), "meContactId": u.get("me_contact_id")}


def get(uid: int) -> dict | None:
    return row_of(shared.get(uid, APP))


def find(name_or_email: str) -> dict | None:
    return row_of(shared.find(name_or_email, APP))


def all_users() -> list[dict]:
    return sorted((row_of(u) for u in shared.list_users(APP)), key=lambda u: u["name"].lower())


def any_users() -> bool:
    return shared.any_users()


def names_of(ids: set) -> dict:
    """{id: name} for these account ids (the merge history and suggestions say who did what)."""
    return {u["id"]: u["name"] for u in shared.list_users() if u["id"] in ids} if ids else {}


def create(name: str, password: str | None, role: str = "editor", display_name: str | None = None, email: str | None = None) -> dict:
    """A new account with this role here, and its private address book. ValueError with the message to show."""
    u = shared.create(name, password or "", role, APP, email=email or "", display_name=display_name or "")
    db.ex("INSERT INTO addressbooks (owner_id, slug, name, description) VALUES (%s, 'personal', 'Personal', %s)",
          (u["id"], f"{display_name or name}'s private contacts"))
    return get(u["id"])


def update(uid: int, **fields) -> dict:
    """display_name, email, role, me_contact_id and/or password (None clears display_name / email)."""
    if "me_contact_id" in fields:
        shared.set_value(uid, APP, "me_contact_id", fields["me_contact_id"])
    kw = {}
    if "display_name" in fields:
        kw["display_name"] = fields["display_name"] or ""
    if "email" in fields:
        kw["email"] = fields["email"] or ""
    if fields.get("role") is not None:
        kw["role"], kw["app"] = fields["role"], APP
    if fields.get("password"):
        kw["password"] = fields["password"]
    if kw:
        shared.update(uid, **kw)
    return get(uid)


def forget_me_contact(cid: int) -> None:
    """A deleted contact is nobody's "me" any more."""
    import json
    authdb.ex("DELETE FROM user_data WHERE app = %s AND k = 'me_contact_id' AND v = %s", (APP, json.dumps(int(cid))))


def delete(uid: int) -> None:
    db.ex("DELETE FROM addressbooks WHERE owner_id = %s", (uid,))
    db.ex("DELETE FROM calendar_tokens WHERE user_id = %s", (uid,))
    shared.delete(uid)


def ensure_admin_from_env() -> None:
    shared.init()


def can_write(u: dict | None) -> bool:
    return shared.can_write(u)


def is_admin(u: dict | None) -> bool:
    return shared.is_admin(u)


# ---------------------------------------------------------------- app passwords

def create_app_password(uid: int, label: str) -> str:
    """Returns the password (shown once): iocontacts-XXXXXXXX-<secret>."""
    return apppasswords.create(uid, APP, label)


def _iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat() if ts else None


def list_app_passwords(uid: int) -> list[dict]:
    return [{"id": r["id"], "label": r["label"], "created": _iso(r["created"]), "lastUsed": _iso(r["lastUsed"])} for r in apppasswords.list_for(uid, APP)]


def delete_app_password(uid: int, pid: int) -> None:
    apppasswords.delete(uid, pid)


def authenticate(name: str, password: str) -> dict | None:
    """Account password or app password; for CardDAV (HTTP Basic), LDAP binds and the sign-in form."""
    return row_of(apppasswords.authenticate(name, password, APP))


def forget_cached_auth() -> None:
    apppasswords.forget()
    shared.invalidate()


# ---------------------------------------------------------------- calendar feed tokens (ioContacts' own)

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
