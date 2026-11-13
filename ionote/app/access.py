"""Who may call a route, declared on the route itself: `dependencies=[access.admin]` (or member, member_write,
signed_in, public). The server's middleware only works out who is asking and whether sign-in is required at all;
every API route carries one of these markers, and a test fails when one is missing, so a new route can never be
open to everyone by mistake. The markers come from iosuite-shared (app/auth.py).

- public: anyone the sign-in rule lets in (reads for everyone, and routes that decide finer inside)
- signed_in: an account (its own settings)
- member: a member or more (reads that are not for everyone: one's own change log)
- member_write: a change to one's own notes, folders, tags or templates. Every note is private to its account, so a
  member writes their own and a viewer only reads (there is nothing shared for an editor to change)
- admin: settings, users, logs, backups
- admin_write: a change to the notes only admins make (an import that replaces, emptying the trash)
"""
from app.auth import auth

ROLES = ("public", "signed_in", "member", "admin")

public = auth.access.public
signed_in = auth.access.signed_in
member = auth.access.member
member_write = auth.access.member_write
admin = auth.access.admin
admin_write = auth.access.admin_write
require = auth.access.require
declared = auth.access.declared
