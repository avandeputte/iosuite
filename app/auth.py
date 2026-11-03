"""The shared ioThing accounts (iothing-auth), as ioSuite uses them.

Accounts, passwords, sessions, app passwords and roles live in the suite's auth database (IOTHING_AUTH_DB_* in
iosuite.env), shared with ioPix, ioNotes, ioContacts, ioCalendar and ioHealth: one sign-in serves every app on the
domain (IOTHING_COOKIE_DOMAIN). Signed in on the start page, a person is signed in everywhere it links to.
What is ioSuite's own stays per app: the role an account holds here (admins set the apps' addresses) and its settings.
"""
from iothing_auth.fastapi import Auth

APP = "iosuite"

auth = Auth(APP, app_label="ioSuite", basic_realm="ioSuite")
