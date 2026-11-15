"""Accounts, roles, sessions and app passwords: the shared ioThing accounts (iosuite-shared), seen from ioMoney.

Roles as in the rest of the suite, read for money: viewer (sees the household's accounts, net worth and portfolio),
member (also keeps private accounts, holdings and things of their own), editor (changes the household's: categories,
values of the house and cars, holdings, transactions), admin (also the Monarch Money sync, settings and users); an
account with no role here sees nothing, so the finances stay with the people given a role. A suite admin is admin
everywhere. Web sessions are the suite's cookie (shared by the apps on the domain). The REST API and MCP use HTTP Basic
or a bearer app password (one per program, revocable, shown once).
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
    and ioMoney's default role: none, until a suite admin says otherwise (Settings › Global settings › Apps). Money is
    not for everyone in the family, so each person is given a role here by name."""
    shared.init()
    if not shared_db.one("SELECT 1 AS x FROM ios_settings WHERE app = %s AND name = 'default_role'", (APP,)):
        shared_db.set_setting("default_role", "none", APP)
