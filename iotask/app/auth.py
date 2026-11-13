"""The shared ioThing accounts (iosuite-shared), as ioTask uses them.

Accounts, passwords, sessions, app passwords and roles live in the Shared ioSuite database (IOSUITE_DB_* in
config.env), with the suite-wide settings, shared with the other apps of the suite: one sign-in serves every app on the
domain (COOKIE_DOMAIN). What is ioTask's own stays per app: the role an account holds here and its settings.
"""
from iosuite_shared.fastapi import Auth
from iosuite_shared.updates import Updater

from app import __version__, config, db

APP = config.APP

# version, address, description and color go into the suite's list of apps (iosuite_shared.suite, read by ioStart)
auth = Auth(APP, app_label="ioTask", basic_realm="ioTask", version=__version__, public_url=config.PUBLIC_URL or None,
            description="Tasks", color="#146b5e")
auth.deny_exempt = ("/mcp", "/dav", "/.well-known/")  # apps sign in with app passwords, whatever got them through a proxy
# a sync-only app password (the Apple profile's, or "Reminders apps only" in Settings › Account) opens these and
# nothing else: 403 on the REST API, MCP and the web app (iosuite-shared enforces it)
auth.scope_paths = {"dav": ("/dav", "/.well-known/caldav")}


def _account_changed(user_id, body) -> None:
    """After someone changed their display name (Settings › Account) or an admin changed an account: the family list
    shows names, so it is read again."""
    from app import members
    members.forget()


auth.on_update = _account_changed

# updates (the daily check, update.sh, restart) and the server log, as in every app of the suite (iosuite_shared.updates);
# the daily-check switch is kept with ioTask's own settings
updater = Updater(APP, __version__, config.APP_DIR, settings=(db.get_setting, db.set_setting), result_file=config.DATA_DIR / ".update-result",
                  user_agent=APP)
