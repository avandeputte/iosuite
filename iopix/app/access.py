"""Who may call a route, declared on the route itself: `dependencies=[access.admin]` (or member, editor, editor_write,
signed_in, public). The server's middleware only works out who is asking and whether sign-in is required at all;
every API route carries one of these markers, and a test fails when one is missing, so a new route can never be
open to everyone by mistake. The markers come from iosuite-shared (app/auth.py), with iopix's read-only switch.

- public: anyone the sign-in rule lets in (reads for everyone, and routes that decide finer inside)
- signed_in: an account, a viewer included (its own settings; saved searches, which check for an editor inside)
- member: a member or more (their own favorites and albums; a viewer only looks)
- editor: an editor or admin (reads that are not for everyone: the change log, metadata, imports)
- editor_write: a change to the library (refused for everyone in read-only mode)
- admin: settings, maintenance, users, logs, backups
- admin_write: a library change only admins make (merging a library, repairing files)
- downloads: the zip downloads (/api/zip*): anyone while there are no accounts, then signed-in accounts
The image routes (/thumb, /preview, /face, /orig, /facecrop) are public: the sign-in rule alone decides.
"""
from app.auth import auth


def _downloads_allowed(user, _request) -> bool:
    from app import users  # zips re-encode and ship whole folders: once accounts exist they are for signed-in users
    return not users.any_users() or users.is_signed_in(user)

ROLES = ("public", "signed_in", "member", "editor", "admin")

public = auth.access.public
signed_in = auth.access.signed_in
member = auth.access.member
editor = auth.access.editor
editor_write = auth.access.editor_write
admin = auth.access.admin
admin_write = auth.access.admin_write
require = auth.access.require
downloads = auth.access.custom("downloads", _downloads_allowed, message="Sign in to download photos")  # /api/zip*
declared = auth.access.declared
