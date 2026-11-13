"""The shared ioThing accounts (iosuite-shared), as ioContact uses them.

Accounts, passwords, sessions, app passwords and roles live in the Shared ioSuite database (IOSUITE_DB_* in
config.env), shared by every app of the suite: one sign-in serves every app on the domain (COOKIE_DOMAIN).
What is ioContact's own stays per app: the role an account holds here, and which contact is "me" (the account's
`me_contact_id` value in its iocontact data). The rest of the app sees an account as the row dict it always did
(id, name, display_name, email, role, passwordless, me_contact_id); `row_of` makes one from a shared account.
"""
from iosuite_shared.fastapi import Auth
from iosuite_shared import users as shared
from iosuite_shared.updates import Updater

from . import __version__, config

APP = config.APP

# the version, address, description and colour also go into the suite's list of apps (ios_apps), which the
# start page and the other apps read: written on the first request
auth = Auth(APP, app_label="ioContact", basic_realm="ioContact", version=__version__, public_url=config.PUBLIC_URL or None,
            description="Contacts", color="#4f2f7d")
# a proxy identity with no account here is refused, except where clients sign in themselves (CardDAV and MCP with an
# app password, their discovery, and the calendar feed's secret link)
auth.deny_exempt = ("/mcp", "/dav", "/.well-known/", "/cal/")


def row_of(u):
    """The dict the app works with, from a shared account (with its role here): the shared fields as they are (what the
    shared routes serve: displayName, passwordless, suiteAdmin, ...) plus the row names ioContact's own code uses and
    the account's "me" contact. Tolerant of partial dicts (the sign-in picker's entries carry no role or email)."""
    if u is None:
        return None
    out = dict(u)
    me_id = shared.get_value(u["id"], APP, "me_contact_id")
    out.update(display_name=u["displayName"] if u.get("displayName") and u["displayName"] != u["name"] else None,
               email=u.get("email") or None, role=u.get("role", "viewer"), passwordless=bool(u.get("passwordless")),
               me_contact_id=me_id, meContactId=me_id, suite_admin=bool(u.get("suiteAdmin")), suiteAdmin=bool(u.get("suiteAdmin")))
    return out


auth.decorate = row_of

# updates (the daily check, update.sh, restart) and the server log, as in every app of the suite (iosuite_shared.updates);
# the daily-check switch is kept with ioContact's own settings
updater = Updater(APP, __version__, config.APP_DIR, result_file=config.DATA_DIR / ".update-result",
                  user_agent=APP)
