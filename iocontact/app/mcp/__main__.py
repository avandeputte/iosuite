"""`python -m app.mcp [--user NAME]`: the MCP server over stdio, for clients that start a local process.
It acts as the account named by --user or MCP_USER (or the only admin, when there is just one), as it is when
the server starts: a role changed later counts from the next start (anyone who can start it holds the database password)."""
import sys

from app import config, db, model, users
from app.mcp import server, current_user


def _pick_user():
    name = config.MCP_USER
    if "--user" in sys.argv[1:]:
        i = sys.argv.index("--user")
        name = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
    if name:
        u = users.find(name)
        if not u:
            sys.exit(f"no ioContact account named {name!r}")
        if u["role"] == "none":
            sys.exit(f"the account {name!r} has no access to ioContact")
        return u
    admins = [u for u in users.all_users() if u["role"] == "admin"]
    if len(admins) == 1:
        return admins[0]
    sys.exit("name the account: python -m app.mcp --user NAME (or MCP_USER=NAME)")


db.migrate()
me = _pick_user()
current_user.set(me)
model.viewer.set(me)  # relations into somebody else's private book stay hidden, as over HTTP
server.run()
