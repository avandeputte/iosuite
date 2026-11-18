"""Accounts, roles, sessions and app passwords: the shared ioThing accounts (iosuite-shared), seen from ioDocs.

Roles as in the rest of the suite: viewer (looks at the documents they may see), member (adds documents and changes
the ones they added or that are theirs), editor (changes every document they may see, and sees the family's except
the private ones), admin (also the server and users); an account holds a role per app, a suite admin is admin
everywhere. Nobody has a role here until one is given (the default role is none): which documents each one then sees
is app/model.py's. The REST API and MCP use HTTP Basic or a bearer app password (one per program, revocable, shown once).
"""
from iosuite_shared import db as shared_db, users as shared

from app.auth import APP

ROLES = shared.APP_ROLES


def get(uid: int) -> dict | None:
    return shared.get(uid, APP)


def find(name_or_email: str) -> dict | None:
    return shared.find(name_or_email, APP)


def all_users() -> list[dict]:
    return sorted(shared.list_users(APP), key=lambda u: u["name"].lower())


def init() -> None:
    """The Shared ioSuite database's tables, the ADMIN_USER / ADMIN_PASSWORD account on a first start with no accounts,
    and ioDocs' default role: none, until a suite admin says otherwise (Settings › Global settings › Apps). Passports
    and policies are not for everyone with an account, so each person is given a role here by name."""
    shared.init()
    if not shared_db.one("SELECT 1 AS x FROM ios_settings WHERE app = %s AND name = 'default_role'", (APP,)):
        shared_db.set_setting("default_role", "none", APP)
