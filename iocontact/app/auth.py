"""The shared ioThing accounts (iosuite-shared), as ioContacts uses them.

Accounts, passwords, sessions, app passwords and roles live in the Shared ioSuite database (IOSUITE_DB_* in
config.env), shared by every app of the suite: one sign-in serves every app on the domain (COOKIE_DOMAIN).
What is ioContacts' own stays per app: the role an account holds here, and which contact is "me" (the account's
`me_contact_id` value in its iocontacts data). The rest of the app sees an account as the row dict it always did
(id, name, display_name, email, role, pw_hash, me_contact_id); `row_of` makes one from a shared account.
"""
from iosuite_shared.fastapi import Auth
from iosuite_shared import users as shared
from iosuite_shared.updates import Updater

from . import __version__, config, db

APP = "iocontacts"

# the version, address, description and colour also go into the suite's list of apps (ios_apps), which the
# start page and the other apps read: written on the first request
auth = Auth(APP, app_label="ioContacts", basic_realm="ioContacts", version=__version__, public_url=config.PUBLIC_URL or None,
            description="Contacts", color="#4f2f7d")
# a proxy identity with no account here is refused, except where clients sign in themselves (CardDAV and MCP with an
# app password, their discovery, and the calendar feed's secret link)
auth.deny_exempt = ("/mcp", "/dav", "/.well-known/", "/cal/")


def row_of(u):
    """The dict the app works with, from a shared account (with its role here)."""
    if u is None:
        return None
    return {"id": u["id"], "name": u["name"], "display_name": u["displayName"] if u["displayName"] != u["name"] else None,
            "email": u["email"] or None, "role": u.get("role", "viewer"), "pw_hash": None if u["passwordless"] else "set",
            "me_contact_id": shared.get_value(u["id"], APP, "me_contact_id"), "suite_admin": u["suiteAdmin"], "listed": u["listed"]}


auth.decorate = row_of

# updates (the daily check, update.sh, restart), the MCP token and the server log, as in every app of the suite
# (iosuite_shared.updates); the daily-check switch is kept with ioContacts' own settings
updater = Updater(APP, __version__, config.ROOT, settings=(db.get_setting, db.set_setting), user_agent="iocontacts")
