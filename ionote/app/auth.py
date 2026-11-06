"""The shared ioThing accounts (iosuite-shared), as ionotes uses them.

Accounts, passwords, sessions and roles live in the Shared ioSuite database (IOSUITE_DB_* in config.env, app/suitedb.py),
shared by every app of the suite: one sign-in serves every app on the domain (COOKIE_DOMAIN). What is
ionotes' own stays per app: the role an account holds here and its display settings.
"""
from iosuite_shared.fastapi import Auth
from iosuite_shared.updates import Updater

from app import __version__, config, db

APP = config.APP


def _read_only() -> bool:
    from app import db
    return db.read_only()


# app_label, version, public_url, description and color: ionotes' row in the suite's list of apps (ioSuite's start page)
auth = Auth(APP, read_only=_read_only, read_only_message="ioNotes is in read-only mode; nothing can be changed.", app_label="ioNotes",
            version=__version__, public_url=config.PUBLIC_URL or None, description="Notes", color="#1c5a5e")
auth.deny_exempt = ("/mcp",)  # MCP clients sign in with an app password, whatever Cloudflare service token got them through

# updates (the daily check, update.sh, restart) and the server log, as in every app of the suite (iosuite_shared.updates);
# the daily-check switch is kept with ionotes' own settings
updater = Updater(APP, __version__, config.APP_DIR, settings=(db.get_setting, db.set_setting), result_file=config.DATA_DIR / ".update-result",
                  user_agent="ionotes")
