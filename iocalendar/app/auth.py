"""The shared ioThing accounts (iothing-auth), as ioCalendar uses them.

Accounts, passwords, sessions, app passwords and roles live in the Shared ioSuite database (IOSUITE_DB_* in
iocalendar.env; the older IOTHING_AUTH_DB_* still work), with the suite-wide settings, shared with ioPix, ioNotes and ioContacts: one sign-in serves every app on the domain
(IOTHING_COOKIE_DOMAIN). What is ioCalendar's own stays per app: the role an account holds here and its settings
(first day of the week, default view, time zone).
"""
from iothing_auth.fastapi import Auth

from app import APP_VERSION, config

APP = "iocalendar"

# version, address, description, color and icon go into the suite's list of apps (iothing_auth.suite, read by ioSuite)
auth = Auth(APP, app_label="ioCalendar", basic_realm="ioCalendar", version=APP_VERSION, public_url=config.PUBLIC_URL or None,
            description="Calendar", color="#963522", icon="/static/icons/mark.svg")
auth.deny_exempt = ("/mcp", "/dav", "/.well-known/")  # apps sign in with app passwords, whatever got them through a proxy
