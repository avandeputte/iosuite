"""Accounts, roles and sessions: the shared ioThing accounts (iosuite-shared), seen from ioSuite.

Roles as in the rest of the suite: viewer (sees the page), editor (the same, for now), admin (also sets the apps'
addresses and manages accounts); an account holds a role per app, a suite admin is admin everywhere. Web sessions are
the suite's cookie (shared by the apps on the domain), so signing in here signs in everywhere the page links to.
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


def any_users() -> bool:
    return shared.any_users()


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


def is_admin(u: dict | None) -> bool:
    return bool(u) and u.get("role") == "admin"


def settings(uid: int) -> dict:
    return shared.get_settings(uid, APP)


def forget_cached_auth() -> None:
    apppasswords.forget()
    shared.invalidate()
