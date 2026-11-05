"""The shared ioThing accounts (iothing-auth), as ionotes uses them.

Accounts, passwords, sessions and roles live in the Shared ioSuite database (IOSUITE_DB_* in ionotes.env, app/suitedb.py),
shared with ioPix and ioContacts: one sign-in serves every app on the domain (IOTHING_COOKIE_DOMAIN). What is
ionotes' own stays per app: the role an account holds here and its display settings.
"""
from iothing_auth.fastapi import Auth
from iothing_auth.updates import Updater

from app import __version__, config, db

APP = "ionotes"


def _read_only() -> bool:
    from app import db
    return db.read_only()


# app_label, version, public_url, description, color and icon: ionotes' row in the suite's list of apps (ioSuite's start page)
auth = Auth(APP, read_only=_read_only, read_only_message="ionotes is in read-only mode; nothing can be changed.", app_label="ioNotes",
            version=__version__, public_url=config.PUBLIC_URL or None, description="Notes", color="#1c5a5e",
            icon="/static/icons/mark.svg")
auth.deny_exempt = ("/mcp",)  # MCP clients sign in with the admin token, whatever Cloudflare service token got them through

# updates (the daily check, update.sh, restart), the MCP admin token and the server log, as in every app of the suite
# (iothing_auth.updates); the daily-check switch and the token are kept with ionotes' own settings
updater = Updater(APP, __version__, config.APP_DIR, settings=(db.get_setting, db.set_setting), result_file=config.DATA_DIR / ".update-result",
                  user_agent="ionotes")
