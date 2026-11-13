"""Accounts, roles, sessions and app passwords: the shared ioThing accounts (iosuite-shared), seen from ioRecipe.

Roles as in the rest of the suite: viewer (reads the family's recipes), member (also keeps private recipes of their
own), editor (changes the family's recipes too), admin (also settings and users); an account holds a role per app, a
suite admin is admin everywhere. Web sessions are the suite's cookie (shared by the apps on the domain). The REST API
and MCP use HTTP Basic or a bearer app password (one per program, revocable, shown once).
"""
from iosuite_shared import users as shared

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
