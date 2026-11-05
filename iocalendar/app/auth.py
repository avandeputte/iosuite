"""The shared ioThing accounts (iothing-auth), as ioCalendar uses them.

Accounts, passwords, sessions, app passwords and roles live in the Shared ioSuite database (IOSUITE_DB_* in
iocalendar.env; the older IOTHING_AUTH_DB_* still work), with the suite-wide settings, shared with ioPix, ioNotes and ioContacts: one sign-in serves every app on the domain
(IOTHING_COOKIE_DOMAIN). What is ioCalendar's own stays per app: the role an account holds here and its settings
(first day of the week, default view, time zone).
"""
from iothing_auth.fastapi import Auth
from iothing_auth.updates import Updater

from app import APP_VERSION, config, db

APP = "iocalendar"

# version, address, description, color and icon go into the suite's list of apps (iothing_auth.suite, read by ioSuite)
auth = Auth(APP, app_label="ioCalendar", basic_realm="ioCalendar", version=APP_VERSION, public_url=config.PUBLIC_URL or None,
            description="Calendar", color="#963522", icon="/static/icons/mark.svg")
auth.deny_exempt = ("/mcp", "/dav", "/.well-known/")  # apps sign in with app passwords, whatever got them through a proxy

# updates (the daily check, update.sh, restart), the MCP token and the server log, as in every app of the suite
# (iothing_auth.updates); the daily-check switch is kept with ioCalendar's own settings
updater = Updater(APP, APP_VERSION, config.ROOT, settings=(db.get_setting, db.set_setting), user_agent="iocalendar")
