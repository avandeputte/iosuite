"""The shared ioThing accounts (iosuite_shared), seen from iopix: what the rest of the app asks of them.

The suite's role ladder (viewer, member, editor, admin; iosuite_shared.users): a viewer browses with their own settings
kept on the server, favorites and viewer albums; an editor makes every library write (edits, tags, faces, place tags,
GPX, sync, database apply); an admin also settings and maintenance. A suite admin is admin everywhere. Anyone not
signed in browses read-only with display settings in the browser, and until the first account exists the viewer stays
open, so a fresh install is not locked out. Accounts, passwords and sessions live in the Shared ioSuite database.
"""
from iosuite_shared import db as authdb, users as shared

from app.auth import APP, decorate, person_tag, set_person

__all__ = ["person_tag", "set_person", "decorate", "APP"]  # re-exported for the rest of the app

any_users, is_signed_in, is_member, can_write, is_admin = shared.any_users, shared.is_signed_in, shared.is_member, shared.can_write, shared.is_admin


def init():
    """The Shared ioSuite database's tables, and the admin named by ADMIN_USER / ADMIN_PASSWORD on a first start with no accounts yet."""
    shared.init()


def list_users() -> list:
    return [decorate(u) for u in shared.list_users(APP)]


def get(user_id: int):
    return decorate(shared.get(user_id, APP))


def create(name: str, password: str, role: str, email: str = "") -> dict:
    """A new account with this role in iopix; ValueError with the message to show."""
    return decorate(shared.create(name, password, role, APP, email=email))


def linked_persons() -> set:
    """The person tags listed accounts are linked to: their face badges are the account picker's avatars."""
    rows = authdb.q("SELECT d.value FROM ios_user_data d JOIN ios_users u ON u.id = d.user_id WHERE d.app = %s AND d.name = 'person' AND u.listed = 1", (APP,))
    return {int(v) for v in (authdb.json_load(r["value"]) for r in rows) if v}


def require_login() -> bool:
    """Sign-in required (Settings › Suite › Apps, suite admins): nothing but the sign-in screen for visitors."""
    return shared.require_login(APP)


if __name__ == "__main__":
    import sys
    init()
    if len(sys.argv) >= 4 and sys.argv[1] == "create":
        print(create(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "admin"))
    elif sys.argv[1:] == ["list"]:
        for u in list_users():
            print(u)
    else:
        print("usage: python -m app.users create <name> <password> [viewer|editor|admin] | list")
