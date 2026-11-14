"""iosuite-shared: one user database for the ioThing apps.

Every app (ioPix, ioNote, ioContact) signs its users in against the same MariaDB database (the Shared ioSuite database, `iosuite` by default), so one
account, one password and one session serve the whole suite: signed in at photo.example.com is signed in at
notes.example.com. What differs per app is kept per app: the role an account holds there (viewer, member, editor, admin, or
none), its settings there, and its app passwords.

  from iosuite_shared import users, sessions, roles, settings, proxyauth   # the parts
  from iosuite_shared import credentials                                   # every app's keys and tokens
  from iosuite_shared.fastapi import Auth                                  # the FastAPI glue (middleware, access, routes)
  from iosuite_shared.updates import Updater                               # self-update, restart, the log

Configuration (environment): IOSUITE_DB_HOST, _PORT, _NAME, _USER, _PASSWORD (the database), and
COOKIE_DOMAIN (the domain the session cookie is shared on, e.g. example.com; a request from a host outside it,
such as a LAN address, gets a cookie for that host only).
"""
# The version of the suite: one number for every app (each app's __version__ is this one) and for this library.
# Bump it with every change that reaches users; an install is offered an update when this line is higher on GitHub.
__version__ = "3.4.0"

from iosuite_shared.errors import Invalid

__all__ = ["Invalid"]
