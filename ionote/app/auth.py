"""The shared ioThing accounts (iosuite-shared), as ionote uses them.

Accounts, passwords, sessions and roles live in the Shared ioSuite database (IOSUITE_DB_* in config.env, app/suitedb.py),
shared by every app of the suite: one sign-in serves every app on the domain (COOKIE_DOMAIN). What is
ionote' own stays per app: the role an account holds here and its display settings.
"""
from iosuite_shared.fastapi import Auth
from iosuite_shared.updates import Updater

from app import __version__, config

APP = config.APP


# app_label, version, public_url, description and color: ionote' row in the suite's list of apps (ioStart, the start page)
auth = Auth(APP, app_label="ioNote",
            version=__version__, public_url=config.PUBLIC_URL or None, description="Notes", color="#1c5a5e")
auth.write_role = "member"  # every note is its owner's own: a member writes theirs (canWrite in /api/auth/me), a viewer only reads
auth.deny_exempt = ("/mcp",)  # MCP clients sign in with an app password, whatever Cloudflare service token got them through

# updates (the daily check, update.sh, restart) and the server log, as in every app of the suite (iosuite_shared.updates);
# the daily-check switch is kept with ionote' own settings
updater = Updater(APP, __version__, config.APP_DIR, result_file=config.DATA_DIR / ".update-result",
                  user_agent="ionote")
