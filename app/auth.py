"""The shared ioThing accounts (iothing-auth), as ioSuite uses them.

Accounts, passwords, sessions, app passwords and roles live in the Shared ioSuite database (IOSUITE_SHARED_DB_* in
iosuite.env), shared with ioPix, ioNotes, ioContacts, ioCalendar and ioHealth: one sign-in serves every app on the
domain (IOTHING_COOKIE_DOMAIN). Signed in on the start page, a person is signed in everywhere it links to.
What is ioSuite's own stays per app: the role an account holds here (admins set the apps' addresses) and its settings.

ioSuite registers itself in the suite's list of apps (the `suite_apps` table of the Shared ioSuite database) like every app, and
reads the others' addresses from it (app/apps.py).
"""
from iothing_auth.fastapi import Auth

from app import APP_VERSION, config

APP = "iosuite"

auth = Auth(APP, app_label="ioSuite", basic_realm="ioSuite", version=APP_VERSION, public_url=config.PUBLIC_URL or None,
            description="Start page", color="#2f3a5a", icon="/static/icons/mark.svg")
