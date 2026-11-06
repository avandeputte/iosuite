"""Who may call a route, declared on the route itself: `dependencies=[access.signed_in]` (or admin, public). The
markers come from iosuite-shared (app/auth.py). Every /api route carries one, and a test fails when one is missing.

- public: the sign-in endpoints, the status, the subscription links (their own secret) and CalDAV (it challenges itself)
- signed_in: an account: everything else (what it may change is a calendar's business: app/model.py)
- admin: users, the server, ioContacts and the holidays
"""
from app.auth import auth

public = auth.access.public
signed_in = auth.access.signed_in
admin = auth.access.admin
declared = auth.access.declared
