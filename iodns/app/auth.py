"""The shared ioThing accounts (iosuite-shared), as ioDNS uses them.

Accounts, passwords, sessions, app passwords and roles live in the Shared ioSuite database (IOSUITE_DB_* in
config.env), shared with the other apps of the suite: one sign-in serves every app on the domain (COOKIE_DOMAIN).
Roles here: viewer (sees the master list and the differences), editor (changes the list, pushes it, imports),
admin (also the DNS servers and the views); a suite admin is admin everywhere.
"""
from iosuite_shared.fastapi import Auth
from iosuite_shared.updates import Updater

from app import __version__, config, db

APP = config.APP

# version, address, description and color go into the suite's list of apps (iosuite_shared.suite, read by ioSuite);
# ioDNS is an admin tool: only its admins and the suite admins see it in the start page and the app switchers
auth = Auth(APP, app_label="ioDNS", basic_realm="ioDNS", version=__version__, public_url=config.PUBLIC_URL or None,
            description="Local DNS", color="#0e7c86", admin_tool=True)


def admins_only_by_default() -> None:
    """An account without a role here gets none (not the suite's usual viewer): ioDNS is for the people who run the
    house's network. Set once; an admin can change it in Settings › Global settings."""
    from iosuite_shared import db as shared_db
    if not shared_db.one("SELECT 1 AS x FROM ios_settings WHERE name = %s AND app = %s", ("default_role", APP)):
        shared_db.set_setting("default_role", "none", APP)

# updates (the daily check, update.sh, restart) and the server log, as in every app of the suite (iosuite_shared.updates);
# the daily-check switch is kept with ioDNS's own settings
updater = Updater(APP, __version__, config.APP_DIR, settings=(db.get_setting, db.set_setting), result_file=config.DATA_DIR / ".update-result",
                  user_agent=APP)
