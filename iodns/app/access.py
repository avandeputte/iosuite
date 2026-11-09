"""Who may call a route, declared on the route itself: `dependencies=[access.signed_in]` (or editor_write, admin_write,
public). The markers come from iosuite-shared (app/auth.py). Every /api route carries one, and a test fails when one
is missing.

- signed_in: the master list, the views, the servers (never their secrets), the differences and the log
- editor_write: change the master list, push it to the servers, import from one
- admin / admin_write: the DNS servers (addresses and keys) and the views
"""
from app.auth import auth

public = auth.access.public
signed_in = auth.access.signed_in
editor_write = auth.access.editor_write
admin = auth.access.admin
admin_write = auth.access.admin_write
declared = auth.access.declared
