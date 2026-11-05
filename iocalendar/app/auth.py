"""The shared ioThing accounts (iosuite-shared), as ioCalendar uses them.

Accounts, passwords, sessions, app passwords and roles live in the Shared ioSuite database (IOSUITE_DB_* in
config.env), with the suite-wide settings, shared with the other apps of the suite: one sign-in serves every app on the
domain (COOKIE_DOMAIN). What is ioCalendar's own stays per app: the role an account holds here and its settings
(first day of the week, default view, time zone).
"""
from iosuite_shared.fastapi import Auth
from iosuite_shared.updates import Updater

from app import __version__, config, db

APP = "iocalendar"

# version, address, description and color go into the suite's list of apps (iosuite_shared.suite, read by ioSuite)
auth = Auth(APP, app_label="ioCalendar", basic_realm="ioCalendar", version=__version__, public_url=config.PUBLIC_URL or None,
            description="Calendar", color="#963522")
auth.deny_exempt = ("/mcp", "/dav", "/.well-known/")  # apps sign in with app passwords, whatever got them through a proxy

# updates (the daily check, update.sh, restart), the MCP token and the server log, as in every app of the suite
# (iosuite_shared.updates); the daily-check switch is kept with ioCalendar's own settings
updater = Updater(APP, __version__, config.ROOT, settings=(db.get_setting, db.set_setting), user_agent="iocalendar")
