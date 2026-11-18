"""The shared ioThing accounts (iosuite-shared), as ioMoney uses them.

Accounts, passwords, sessions, app passwords and roles live in the Shared ioSuite database (IOSUITE_DB_* in
config.env), with the suite-wide settings and keys, shared with the other apps of the suite: one sign-in serves every
app on the domain (COOKIE_DOMAIN). What is ioMoney's own stays per app: the role an account holds here and its settings.
"""
from iosuite_shared.fastapi import Auth
from iosuite_shared.updates import Updater

from app import __version__, config

APP = config.APP

# the version and address (the name, description and colour: app.json) go into the suite's list of apps (read by ioStart)
auth = Auth(APP, version=__version__, public_url=config.PUBLIC_URL or None)
auth.deny_exempt = ("/mcp",)  # assistants sign in with app passwords, whatever got them through a proxy

# updates (the daily check, update.sh, restart) and the server log, as in every app of the suite (iosuite_shared.updates)
updater = Updater(APP, __version__, config.APP_DIR, result_file=config.DATA_DIR / ".update-result",
                  user_agent=APP)


def _person_data(user_id: int, remove: bool) -> list:
    """What the person keeps here, when a suite admin deletes their account (iosuite_shared.persondata)."""
    from app import persondata
    return persondata.of(user_id, remove)


auth.person_data = _person_data
