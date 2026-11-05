"""`python -m app.mcp [--user NAME]`: the MCP server over stdio, for clients that start a local process.
It acts as the account named by --user or IOCONTACTS_MCP_USER (or the only admin, when there is just one)."""
import sys

from app import config, db, users
from app.mcp import server, current_user


def _pick_user():
    name = config.MCP_USER
    if "--user" in sys.argv[1:]:
        i = sys.argv.index("--user")
        name = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
    if name:
        u = users.find(name)
        if not u:
            sys.exit(f"no ioContacts account named {name!r}")
        if u["role"] == "none":
            sys.exit(f"the account {name!r} has no access to ioContacts")
        return u
    admins = [u for u in users.all_users() if u["role"] == "admin"]
    if len(admins) == 1:
        return admins[0]
    sys.exit("name the account: python -m app.mcp --user NAME (or IOCONTACTS_MCP_USER=NAME)")


db.migrate()
current_user.set(_pick_user())
server.run()
