"""The shared ioThing accounts (iothing-auth), as ioContacts uses them.

Accounts, passwords, sessions, app passwords and roles live in the Shared ioSuite database (IOSUITE_DB_* in
iocontacts.env, see app/config.py), shared with ioPix and ioNotes: one sign-in serves every app on the domain (IOTHING_COOKIE_DOMAIN).
What is ioContacts' own stays per app: the role an account holds here, and which contact is "me" (the account's
`me_contact_id` value in its iocontacts data). The rest of the app sees an account as the row dict it always did
(id, name, display_name, email, role, pw_hash, me_contact_id); `row_of` makes one from a shared account.
"""
from iothing_auth.fastapi import Auth
from iothing_auth import users as shared

from . import APP_VERSION, config

APP = "iocontacts"

# the version, address, description, colour and icon also go into the suite's list of apps (suite_apps), which the
# start page and the other apps read: written on the first request
auth = Auth(APP, app_label="ioContacts", basic_realm="ioContacts", version=APP_VERSION, public_url=config.PUBLIC_URL or None,
            description="Contacts", color="#4f2f7d", icon="/static/icons/mark.svg")


def row_of(u):
    """The dict the app works with, from a shared account (with its role here)."""
    if u is None:
        return None
    return {"id": u["id"], "name": u["name"], "display_name": u["displayName"] if u["displayName"] != u["name"] else None,
            "email": u["email"] or None, "role": u.get("role", "viewer"), "pw_hash": None if u["passwordless"] else "set",
            "me_contact_id": shared.get_value(u["id"], APP, "me_contact_id"), "suite_admin": u["suiteAdmin"], "listed": u["listed"]}


auth.decorate = row_of
