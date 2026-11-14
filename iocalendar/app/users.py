"""Accounts, roles, sessions and app passwords: the shared ioThing accounts (iosuite-shared), seen from ioCalendar.

Roles as in the rest of the suite: viewer (reads the shared calendars), member (also keeps their own), editor (changes the shared
calendars too), admin (also settings and users); an account holds a role per app, a suite admin is admin everywhere.
Web sessions are the suite's cookie (shared by the apps on the domain). CalDAV clients, the REST API and MCP use HTTP
Basic or a bearer app password (one per device, revocable, shown once). The subscription links (/ics/...) carry a
private token per account instead, since calendar apps cannot sign in to a subscription.

What is here is ioCalendar's own: the accounts with their role here, app passwords with the CalDAV-only scope, and the
subscription links. Whether an account may write or is an admin is asked of iosuite_shared.users directly.
"""

from iosuite_shared import feeds, users as shared

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


# ---------------------------------------------------------------- subscription links (iosuite_shared.feeds)

def user_from_feed(secret: str) -> dict | None:
    """The account a subscription link (/ics/<secret>/...) reads as; None when the link is unknown or stopped, or the
    account may no longer use ioCalendar."""
    uid = feeds.user_id(APP, secret)
    u = get(uid) if uid else None
    return u if u and u.get("role") != "none" else None
