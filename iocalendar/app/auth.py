"""The shared ioThing accounts (iothing-auth), as ioCalendar uses them.

Accounts, passwords, sessions, app passwords and roles live in the suite's auth database (IOTHING_AUTH_DB_* in
iocalendar.env), shared with ioPix, ioNotes and ioContacts: one sign-in serves every app on the domain
(IOTHING_COOKIE_DOMAIN). What is ioCalendar's own stays per app: the role an account holds here and its settings
(first day of the week, default view, time zone).
"""
from iothing_auth.fastapi import Auth

APP = "iocalendar"

auth = Auth(APP, app_label="ioCalendar", basic_realm="ioCalendar")
auth.deny_exempt = ("/mcp", "/dav", "/.well-known/")  # apps sign in with app passwords, whatever got them through a proxy
