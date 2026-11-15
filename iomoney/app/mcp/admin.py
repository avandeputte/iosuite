"""The server itself, for admins: health."""
import platform
import sys

from app import __version__, config, db, monarch, users
from app.auth import updater
from app.mcp.base import READ_ONLY, need_admin, server


@server.tool(annotations=READ_ONLY)
def diagnostics() -> dict:
    """Admins: the server's health: version and commit, Python and platform, the database (server version, accounts,
    transactions, holdings, quotes), the Monarch sync, the MCP switch, the last update check and update, and the
    accounts with a role here."""
    need_admin()
    out = {"version": __version__, "commit": updater.local_commit()[:7], "docker": updater.in_docker(),
           "python": sys.version.split()[0], "platform": platform.platform(), "appDir": str(config.APP_DIR),
           "publicUrl": config.PUBLIC_URL or None, "update": updater.status()}
    try:
        out["database"] = {"host": f"{config.DB_HOST}:{config.DB_PORT}", "name": config.DB_NAME,
                           "server": db.one("SELECT version() AS v")["v"], "schema": db.schema_version(),
                           **{t: db.one(f"SELECT count(*) AS n FROM mny_{t}")["n"] for t in ("accounts", "transactions", "holdings", "quotes", "bills")}}
        out["monarch"] = monarch.status()
    except Exception as e:  # noqa: BLE001
        out["database"] = {"error": str(e)[:200]}
    from app.main import mcp_enabled
    out["mcp"] = {"enabled": mcp_enabled(), "forcedByEnv": config.MCP_FORCED}
    out["accounts"] = [{"name": u["name"], "role": u.get("role")} for u in users.all_users()]
    return out
