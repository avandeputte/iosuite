"""Who may call a route, declared on the route itself: `dependencies=[access.signed_in]` (or admin, admin_write,
public). The markers come from iosuite-shared (app/auth.py). Every /api route carries one, and a test fails when one
is missing. ioBackup is an admin tool, so only suite admins (admin everywhere) get past any of them; the levels still
say what each route does.

- signed_in: the jobs, their schedule and last run, the history of runs and the list of backups (never a password)
- editor_write: run a job now, verify a backup
- admin / admin_write: the servers, destinations and jobs; download, delete and restore backups (a backup holds every
  row and password hash of the databases in it)
"""
from app.auth import auth

public = auth.access.public
signed_in = auth.access.signed_in
editor_write = auth.access.editor_write
admin = auth.access.admin
admin_write = auth.access.admin_write
declared = auth.access.declared
