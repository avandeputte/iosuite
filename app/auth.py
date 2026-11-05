"""The shared ioThing accounts (the iosuite-shared library), as ioSuite uses them.

Accounts, passwords, sessions, app passwords and roles live in the Shared ioSuite database (IOSUITE_DB_* in
config.env), shared with ioPix, ioNotes, ioContacts, ioCalendar and ioHealth: one sign-in serves every app on the
domain (COOKIE_DOMAIN). Signed in on the start page, a person is signed in everywhere it links to.
What is ioSuite's own stays per app: the role an account holds here (admins set the weather and the home page) and its settings.

ioSuite registers itself in the suite's list of apps (the `suite_apps` table of the Shared ioSuite database) like every app, and
reads the others' addresses from it (app/apps.py).
"""
from iosuite_shared.fastapi import Auth
from iosuite_shared.updates import Updater

from app import __version__, config, db

APP = "iosuite"

auth = Auth(APP, app_label="ioSuite", basic_realm="ioSuite", version=__version__, public_url=config.PUBLIC_URL or None,
            description="Start page", color="#2f3a5a", icon="/static/icons/mark.svg")

# the version check and the self-update (update.sh), shared with the suite: Maintenance › Updates and logs,
# GET/POST /api/server and GET /api/log (main.py mounts the router)
updater = Updater(APP, __version__, config.ROOT, settings=(db.get_setting, db.set_setting), user_agent="iosuite")
