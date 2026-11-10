"""Accounts, roles, sessions and app passwords: the shared ioThing accounts (iosuite-shared), seen from ioContacts.

Roles as in iopix: viewer (reads), editor (changes contacts), admin (also settings and users); an account holds a
role per app, a suite admin is admin everywhere. Each account gets its own private address book; the Family book is
shared by everyone. Web sessions are the suite's cookie (shared by the apps on the domain). CardDAV / LDAP clients
use HTTP Basic or an LDAP bind with either the account password or an app password (one per device, revocable,
shown once). What is here is ioContacts' own: an account as the app sees it (with its "me" contact), its private
address book, the LDAP bind, and the birthday calendar's private link. The rest is asked of iosuite_shared directly.
"""
import logging
import re
import secrets

from iosuite_shared import apppasswords, db as authdb, users as shared

from app import db
from app.auth import APP, row_of


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


def names_of(ids: set) -> dict:
    """{id: name} for these account ids (the merge history and suggestions say who did what)."""
    return {u["id"]: u["name"] for u in shared.list_users() if u["id"] in ids} if ids else {}


def create(name: str, password: str | None, role: str = "editor", display_name: str | None = None, email: str | None = None) -> dict:
    """A new account with this role here, and its private address book. ValueError with the message to show."""
    u = shared.create(name, password or "", role, APP, email=email or "", display_name=display_name or "")
    personal_book(get(u["id"]))
    return get(u["id"])


def personal_book(u: dict) -> None:
    """Every account gets its own private address book, whichever way the account was made (here, Settings › Security,
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


def forget_gone(*uids: int) -> None:
    """The private address book (with its contacts) and the calendar link of accounts that are gone."""
    for uid in uids:
        for b in db.q("SELECT id FROM con_address_books WHERE owner_id = %s", (uid,)):
            db.ex("DELETE FROM con_contacts WHERE address_book_id = %s", (b["id"],))
        db.ex("DELETE FROM con_address_books WHERE owner_id = %s", (uid,))
        db.ex("DELETE FROM con_feed_tokens WHERE user_id = %s", (uid,))


SUITE_ID = "suite_id"             # in the Shared ioSuite database (ios_settings, suite-wide): which one it is
KNOWN_SUITE = "shared_database"   # in ioContacts' own settings: the Shared ioSuite database its books belong to


def init() -> None:
    """The Shared ioSuite database's tables, and the ADMIN_USER / ADMIN_PASSWORD account on a first start with no accounts.
    Accounts deleted elsewhere (Settings › Security in any app, the command line) leave their books here: swept at start."""
    shared.init()
    sweep_gone()


def sweep_gone() -> int:
    """Remove the private address books of accounts that no longer exist; how many accounts' books went.

    An account that is missing from the Shared ioSuite database looks the same whether it was deleted or the app was
    pointed at another database (a new one, an empty one, a restored old one), and in the second case every private
    book would go. So the Shared ioSuite database carries an id (made here the first time), ioContacts remembers the
    one its books belong to, and the sweep runs only while the two agree and that database has accounts. On the
    first start with this check nothing is removed: the id is only noted."""
    log = logging.getLogger("iocontacts.users")
    here = authdb.get_setting(SUITE_ID, "", "")
    if not here:
        here = secrets.token_hex(16)
        authdb.set_setting(SUITE_ID, here, "")
    known = db.get_setting(KNOWN_SUITE)
    alive = {u["id"] for u in shared.list_users()}
    owners = {r["owner_id"] for r in db.q("SELECT DISTINCT owner_id FROM con_address_books WHERE owner_id IS NOT NULL")}
    gone = owners - alive
    if known is None:
        db.set_setting(KNOWN_SUITE, here)
        if gone:
            log.warning("%d private address book owner(s) have no account in the Shared ioSuite database; their books are kept "
                        "(they are removed at a later start, once this database is known to be the one they belong to)", len(gone))
        return 0
    if known != here or not alive:
        if gone:
            log.error("the Shared ioSuite database is not the one these address books belong to (or it has no accounts): "
                      "%d owner(s) are missing from it and their private address books are KEPT. If this is the right database, "
                      "remove the '%s' row from con_settings and restart.", len(gone), KNOWN_SUITE)
        return 0
    forget_gone(*gone)
    return len(gone)


# ---------------------------------------------------------------- app passwords

def create_app_password(uid: int, label: str, protocols_only: bool = False) -> str:
    """Returns the password (shown once): iocontacts-XXXXXXXX-<secret>. protocols_only: scope 'dav', it works for CardDAV
    and LDAP only, not for the web app, the REST API or MCP (what a phone or a configuration profile needs, and no more).
    The scope lives with the password in the Shared ioSuite database; iosuite-shared's middleware enforces it by path."""
    return apppasswords.create(uid, APP, label, apppasswords.DAV if protocols_only else "")


def authenticate(name: str, password: str) -> dict | None:
    """Account password or an app password without a scope (a protocol-only one is for CardDAV and LDAP: HTTP Basic
    and Bearer go through iosuite-shared's middleware, which keeps such passwords to /dav; LDAP binds: ldap_bind)."""
    user, scope = apppasswords.authenticate_scoped(name, password, APP)
    return None if scope else row_of(user)


APP_PASSWORD = re.compile(r"^[a-z0-9]+-([0-9a-f]{8})-")  # how every app password starts: <app>-<8 hex>-<secret>


def ldap_bind(name: str, password: str) -> dict | None:
    """The account for an LDAP bind, which takes an app password only (one for everything, or a CardDAV/LDAP-only
    one). The directory is not encrypted, so the account's own password, which opens every app of the suite, is
    never accepted here: what can be read off the network is one device's password, revocable on its own."""
    m = APP_PASSWORD.match(password or "")
    if not m:
        return None
    user, scope = apppasswords.authenticate_scoped(name, password, APP)
    if not user or scope not in ("", apppasswords.DAV):
        return None
    if not authdb.one("SELECT 1 AS x FROM ios_app_passwords WHERE user_id = %s AND app = %s AND prefix = %s", (user["id"], APP, m.group(1))):
        return None  # an account password that merely looks like an app password
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
