"""Who may call a route, declared on the route itself: `dependencies=[access.signed_in]` (or admin, public). The
markers come from iosuite-shared (app/auth.py). Every /api route carries one, and a test fails when one is missing.

- public: the sign-in endpoints, /v1/health, and the upload routes (which check the bearer token themselves)
- signed_in: an account: everything in the web app (there is nothing to see without one; each account sees its own data)
- admin: accounts and the sign-in settings
"""
from iosuite_shared import users as shared_users

from app.auth import auth

public = auth.access.public
signed_in = auth.access.signed_in
admin = auth.access.admin
# the phone's uploads (/v1/*): the user name and password (or an app password) of an account that is a member or more here
# (what is sent becomes that account's own data, so a member sends theirs; a viewer only looks). Enforced by the marker
# like the levels above, so the route bodies hold no access logic and check_access_declared counts the routes.
uploader = auth.access.custom("uploader", lambda u, _r: bool(u) and shared_users.is_member(u), write=True,
                              message="sign in as an account that is a member or more here (an admin can make the account a member)")
declared = auth.access.declared
