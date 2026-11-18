"""The shared ioThing accounts (iosuite-shared), as ioBackup uses them.

Accounts, passwords, sessions, app passwords and roles live in the Shared ioSuite database (IOSUITE_DB_* in
config.env), shared with the other apps of the suite: one sign-in serves every app on the domain (COOKIE_DOMAIN).
ioBackup is an admin tool: it is for the suite admins only (a backup holds everybody's data; iosuite_shared gives
everybody else none here, whatever role row or default role says), and a suite admin is admin everywhere.
"""
from iosuite_shared.fastapi import Auth
from iosuite_shared.updates import Updater

from app import __version__, config

APP = config.APP

# the version and address (the name, description and colour: app.json) go into the suite's list of apps (read by ioStart);
# ioBackup is an admin tool (app.json): only the suite admins reach it and see it in the start page and the app switchers
auth = Auth(APP, version=__version__, public_url=config.PUBLIC_URL or None)


# updates (the daily check, update.sh, restart) and the server log, as in every app of the suite (iosuite_shared.updates);
# the daily-check switch is kept with ioBackup's own settings
updater = Updater(APP, __version__, config.APP_DIR, result_file=config.DATA_DIR / ".update-result",
                  user_agent=APP)
