"""The shared ioThing accounts (iosuite-shared), as ioDNS uses them.

Accounts, passwords, sessions, app passwords and roles live in the Shared ioSuite database (IOSUITE_DB_* in
config.env), shared with the other apps of the suite: one sign-in serves every app on the domain (COOKIE_DOMAIN).
ioDNS is an admin tool: it is for the suite admins only (iosuite_shared gives everybody else none here, whatever role
row or default role says), and a suite admin is admin everywhere.
"""
from iosuite_shared.fastapi import Auth
from iosuite_shared.updates import Updater

from app import __version__, config, db

APP = config.APP

# version, address, description and color go into the suite's list of apps (iosuite_shared.suite, read by ioSuite);
# ioDNS is an admin tool: only the suite admins reach it and see it in the start page and the app switchers
auth = Auth(APP, app_label="ioDNS", basic_realm="ioDNS", version=__version__, public_url=config.PUBLIC_URL or None,
            description="Local DNS", color="#0e7c86", admin_tool=True)


# updates (the daily check, update.sh, restart) and the server log, as in every app of the suite (iosuite_shared.updates);
# the daily-check switch is kept with ioDNS's own settings
updater = Updater(APP, __version__, config.APP_DIR, settings=(db.get_setting, db.set_setting), result_file=config.DATA_DIR / ".update-result",
                  user_agent=APP)
