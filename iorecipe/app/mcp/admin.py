"""The server itself, for admins: health."""
import platform
import sys

from app import __version__, config, db, users
from app.auth import updater
from app.mcp.base import READ_ONLY, need_admin, server


@server.tool(annotations=READ_ONLY)
def diagnostics() -> dict:
    """Admins: the server's health: version and commit, Python and platform, the database (server
    version, recipes, photos, cookbooks), the MCP switch, the last update check and update, and the accounts."""
    need_admin()
    out = {"version": __version__, "commit": updater.local_commit()[:7], "docker": updater.in_docker(),
           "python": sys.version.split()[0], "platform": platform.platform(), "appDir": str(config.APP_DIR),
           "publicUrl": config.PUBLIC_URL or None, "update": updater.status()}
    try:
        out["database"] = {"host": f"{config.DB_HOST}:{config.DB_PORT}", "name": config.DB_NAME,
                           "server": db.one("SELECT version() AS v")["v"],
                           "schema": db.schema_version(),
                           "recipes": db.one("SELECT count(*) AS n FROM rcp_recipes")["n"],
                           "photos": db.one("SELECT count(*) AS n FROM rcp_photos")["n"],
                           "cookbooks": db.one("SELECT count(*) AS n FROM rcp_books")["n"],
                           "photoBytes": int(db.one("SELECT COALESCE(SUM(LENGTH(picture) + LENGTH(thumb)), 0) AS n FROM rcp_photos")["n"])}
    except Exception as e:  # noqa: BLE001
        out["database"] = {"error": str(e)[:200]}
    from app.main import mcp_enabled
    out["mcp"] = {"enabled": mcp_enabled(), "forcedByEnv": config.MCP_FORCED}
    out["accounts"] = [{"name": u["name"], "role": u.get("role")} for u in users.all_users()]
    return out


@server.tool(annotations=READ_ONLY)
def list_accounts() -> list:
    """Admins: the accounts, with their roles here (viewer, member, editor, admin)."""
    need_admin()
    return [{"name": u["name"], "displayName": u.get("displayName"), "email": u.get("email") or None, "role": u.get("role")}
            for u in users.all_users()]
