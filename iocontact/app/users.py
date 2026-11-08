"""Accounts, roles, sessions and app passwords: the shared ioThing accounts (iosuite-shared), seen from ioContacts.

Roles as in iopix: viewer (reads), editor (changes contacts), admin (also settings and users); an account holds a
role per app, a suite admin is admin everywhere. Each account gets its own private address book; the Family book is
shared by everyone. Web sessions are the suite's cookie (shared by the apps on the domain). CardDAV / LDAP clients
use HTTP Basic or an LDAP bind with either the account password or an app password (one per device, revocable,
shown once). This module keeps ioContacts' old names; the work is done by iosuite_shared.
"""
import secrets

from iosuite_shared import apppasswords, db as authdb, sessions, users as shared

from app import db
from app.auth import APP, row_of

COOKIE = sessions.COOKIE
SESSION_DAYS = sessions.SESSION_DAYS
ROLES = shared.APP_ROLES


def public(u: dict | None) -> dict | None:
    """The account as the web app sees it: the fields /api/status carries in every app of the suite, and the "me" card."""
    if not u:
        return None
    return {"id": u["id"], "name": u["name"], "displayName": u.get("display_name") or u["name"], "email": u.get("email"),
            "role": u["role"], "suiteAdmin": bool(u.get("suite_admin")), "passwordless": bool(u.get("passwordless")),
            "meContactId": u.get("me_contact_id")}


def get(uid: int) -> dict | None:
    return row_of(shared.get(uid, APP))


def find(name_or_email: str) -> dict | None:
    return row_of(shared.find(name_or_email, APP))


def all_users() -> list[dict]:
    return sorted((row_of(u) for u in shared.list_users(APP)), key=lambda u: u["name"].lower())


def passwordless(u: dict | None) -> bool:
    return bool(u) and bool(u.get("passwordless"))


def any_users() -> bool:
    return shared.any_users()


def names_of(ids: set) -> dict:
    """{id: name} for these account ids (the merge history and suggestions say who did what)."""
    return {u["id"]: u["name"] for u in shared.list_users() if u["id"] in ids} if ids else {}


def create(name: str, password: str | None, role: str = "editor", display_name: str | None = None, email: str | None = None) -> dict:
    """A new account with this role here, and its private address book. ValueError with the message to show."""
    u = shared.create(name, password or "", role, APP, email=email or "", display_name=display_name or "")
    personal_book(get(u["id"]))
    return get(u["id"])


def personal_book(u: dict) -> None:
    """Every account gets its own private address book, whichever way the account was made (here, Settings › Accounts and access,
    the shared setup or the command line): made the first time the account's books are listed (one small query)."""
    if not db.one("SELECT 1 AS x FROM con_address_books WHERE owner_id = %s LIMIT 1", (u["id"],)):
        db.ex("INSERT INTO con_address_books (owner_id, slug, name, description) VALUES (%s, 'personal', 'Personal', %s)",
              (u["id"], f"{u.get('display_name') or u['name']}'s private contacts"))


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
    if fields.get("password") is not None:
        kw["password"] = fields["password"]  # "" removes it: one-click sign-in, viewers only
    if kw:
        shared.update(uid, **kw)
    return get(uid)


def forget_me_contact(cid: int) -> None:
    """A deleted contact is nobody's "me" any more."""
    import json
    authdb.ex("DELETE FROM ios_user_data WHERE app = %s AND name = 'me_contact_id' AND value = %s", (APP, json.dumps(int(cid))))


def delete(uid: int) -> None:
    shared.delete(uid)
    forget_gone(uid)


def forget_gone(*uids: int) -> None:
    """The private address book (with its contacts) and the calendar link of accounts that are gone."""
    for uid in uids:
        for b in db.q("SELECT id FROM con_address_books WHERE owner_id = %s", (uid,)):
            db.ex("DELETE FROM con_contacts WHERE address_book_id = %s", (b["id"],))
        db.ex("DELETE FROM con_address_books WHERE owner_id = %s", (uid,))
        db.ex("DELETE FROM con_feed_tokens WHERE user_id = %s", (uid,))


def init() -> None:
    """The Shared ioSuite database's tables, and the ADMIN_USER / ADMIN_PASSWORD account on a first start with no accounts.
    Accounts deleted elsewhere (Settings › Accounts and access in any app, the command line) leave their books here: swept at start."""
    shared.init()
    alive = {u["id"] for u in shared.list_users()}
    owners = {r["owner_id"] for r in db.q("SELECT DISTINCT owner_id FROM con_address_books WHERE owner_id IS NOT NULL")}
    forget_gone(*(owners - alive))


def can_write(u: dict | None) -> bool:
    return shared.can_write(u)


def is_admin(u: dict | None) -> bool:
    return shared.is_admin(u)


# ---------------------------------------------------------------- app passwords

def create_app_password(uid: int, label: str, protocols_only: bool = False) -> str:
    """Returns the password (shown once): iocontacts-XXXXXXXX-<secret>. protocols_only: scope 'dav', it works for CardDAV
    and LDAP only, not for the web app, the REST API or MCP (what a phone or a configuration profile needs, and no more).
    The scope lives with the password in the Shared ioSuite database; iosuite-shared's middleware enforces it by path."""
    return apppasswords.create(uid, APP, label, apppasswords.DAV if protocols_only else "")


def authenticate(name: str, password: str, protocol: bool = False) -> dict | None:
    """Account password or app password; for LDAP binds (protocol=True) and the sign-in form. A protocol-only ('dav')
    app password is refused unless protocol is set. (HTTP Basic and Bearer go through iosuite-shared's middleware,
    which keeps such passwords to /dav.)"""
    user, scope = apppasswords.authenticate_scoped(name, password, APP)
    if user and scope and not (protocol and scope == apppasswords.DAV):
        return None
    return row_of(user)


def forget_cached_auth() -> None:
    apppasswords.forget()
    shared.invalidate()


# repeated wrong passwords are slowed down, per visitor and name, as the shared sign-in routes do (the LDAP bind uses these)
attempt_wait, attempt_failed, attempt_succeeded = shared.attempt_wait, shared.attempt_failed, shared.attempt_succeeded


# ---------------------------------------------------------------- calendar feed tokens (ioContacts' own)

def calendar_token(uid: int) -> str:
    r = db.one("SELECT token FROM con_feed_tokens WHERE user_id = %s ORDER BY id LIMIT 1", (uid,))
    if r:
        return r["token"]
    tok = secrets.token_hex(20)
    db.ex("INSERT INTO con_feed_tokens (user_id, token) VALUES (%s, %s)", (uid, tok))
    return tok


def reset_calendar_token(uid: int) -> str:
    db.ex("DELETE FROM con_feed_tokens WHERE user_id = %s", (uid,))
    return calendar_token(uid)


def user_from_calendar_token(tok: str) -> dict | None:
    r = db.one("SELECT user_id FROM con_feed_tokens WHERE token = %s", (tok,))
    u = get(r["user_id"]) if r else None
    return u if u and u["role"] != "none" else None  # an account whose access here was taken away loses the feed too
