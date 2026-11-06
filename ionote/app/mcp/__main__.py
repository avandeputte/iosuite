"""`python -m app.mcp [--user NAME]`: the MCP server over stdio, for clients that start a local process, on the same
database as the web app. It acts as the account named by --user or MCP_USER (or the only admin, when there is just
one), on that account's own notes, as the HTTP endpoint does for a client signed in with an app password."""
import sys

from app import config, db, notes, owners, users
from app.mcp import current_user, server


def _pick_user():
    name = config.MCP_USER
    if "--user" in sys.argv[1:]:
        i = sys.argv.index("--user")
        name = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
    accounts = users.list_users()
    if name:
        u = next((u for u in accounts if u["name"].lower() == name.lower()), None)
        if not u:
            sys.exit(f"no ioNotes account named {name!r}")
        return u
    admins = [u for u in accounts if u.get("role") == "admin" or u.get("suiteAdmin")]
    if len(admins) == 1:
        return admins[0]
    sys.exit("name the account: python -m app.mcp --user NAME (or MCP_USER=NAME)")


if __name__ == "__main__":
    db.init()
    users.init()
    if users.any_users():
        notes.claim_unowned(owners.first_admin_id())
    u = _pick_user()
    current_user.set(u)
    notes.current_owner.set(int(u["id"]))
    server.run()
