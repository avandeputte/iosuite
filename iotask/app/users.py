"""Accounts, roles, sessions and app passwords: the shared ioThing accounts (iosuite-shared), seen from ioTasks.

Roles as in the rest of the suite: viewer (reads the shared lists), member (also keeps their own private lists),
editor (changes the shared lists too), admin (also settings and users); an account holds a role per app, a suite admin is admin everywhere. Web
sessions are the suite's cookie (shared by the apps on the domain). Reminders apps (CalDAV), the REST API and MCP use
HTTP Basic or a bearer app password (one per device, revocable, shown once).
"""
from iosuite_shared import apppasswords, users as shared

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


def create_app_password(uid: int, label: str, sync_only: bool = False) -> str:
    """A new app password for this account; sync_only: it works for CalDAV and nothing else (not the REST API, MCP or
    the web app), the kind the Apple profile puts on a phone. The scope is kept with the password in the Shared ioSuite
    database (ios_app_passwords.scope) and enforced by iosuite-shared's middleware."""
    return apppasswords.create(uid, APP, label, apppasswords.DAV if sync_only else "")
