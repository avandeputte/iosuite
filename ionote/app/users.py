"""Users, sessions and permissions: the shared ioThing accounts (iosuite-shared), seen from ionotes.

Three roles here: viewer (reads and searches the notes; own settings kept on the server), editor (viewer plus
every change to notes, folders and tags: the Mac and iPhone apps sign in as an editor) and admin (editor plus
settings, maintenance and user management). An account holds a role per app; a suite admin is admin everywhere.
Anyone not signed in browses read-only. A viewer may have no password at all: such an account signs in with one
click from the account picker (on the home network only) and can never be more than a viewer. Until the first
account exists ionotes stays open, so a fresh install is not locked out.

Passwords are scrypt-hashed and sessions are random tokens in an HttpOnly cookie (30 days, renewed in use), both
in the Shared ioSuite database, so a session begun in another ioThing app is a session here too. This module keeps ionotes'
old names for the rest of the code; the work is done by iosuite_shared.
"""
from iosuite_shared import db as authdb, sessions, users as shared

from app.auth import APP

ROLES = shared.APP_ROLES
COOKIE = sessions.COOKIE
VIA_COOKIE = sessions.VIA_COOKIE
SESSION_DAYS = sessions.SESSION_DAYS
CACHE_S = shared.CACHE_S
_attempts = shared._attempts
LOCK_AFTER, LOCK_AFTER_NAME, LOCK_BASE, LOCK_MAX = shared.LOCK_AFTER, shared.LOCK_AFTER_NAME, shared.LOCK_BASE, shared.LOCK_MAX
login_wait, login_failed, login_succeeded = shared.login_wait, shared.login_failed, shared.login_succeeded
any_users, delete, is_signed_in, can_write, is_admin = shared.any_users, shared.delete, shared.is_signed_in, shared.can_write, shared.is_admin
end_all_sessions = sessions.end_all


def init():
    """The Shared ioSuite database's tables, and the admin named by ADMIN_USER / ADMIN_PASSWORD on a first start with no accounts yet."""
    shared.init()


def invalidate():
    shared.invalidate()


def list_users() -> list:
    return shared.list_users(APP)


def get(user_id: int):
    return shared.get(user_id, APP)


def create(name: str, password: str, role: str, email: str = "") -> dict:
    """A new account with this role in ionotes; ValueError with the message to show."""
    return shared.create(name, password, role, APP, email=email)


def update(user_id: int, role: str = None, password: str = None, name: str = None, email: str = None, listed: bool = None):
    shared.update(user_id, role=role, app=APP, password=password, name=name, email=email, listed=listed)


def authenticate(name: str, password: str):
    return shared.authenticate(name, password, APP)


def accounts() -> list:
    return shared.accounts(APP)


def require_login() -> bool:
    """Settings › Require sign-in: nothing but the sign-in screen for visitors."""
    return shared.require_login(APP)


def set_require_login(on: bool):
    authdb.set_setting("require_login", "1" if on else "0", APP)


def get_settings(user_id: int) -> dict:
    return shared.get_settings(user_id, APP)


def set_settings(user_id: int, changes: dict) -> dict:
    return shared.set_settings(user_id, APP, changes)


def user_from_token(token: str):
    return sessions.user_from_token(token, APP)
