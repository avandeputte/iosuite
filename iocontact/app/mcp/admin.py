"""The server itself, for admins: health, accounts."""
import platform
import sys

from mcp.server.mcpserver.exceptions import ToolError

from app import __version__, config, db, iopix, users
from app.auth import auth, updater
from app.mcp.base import READ_ONLY, need_admin, server


@server.tool(annotations=READ_ONLY)
def diagnostics() -> dict:
    """Admins: the server's health: version and commit, Python and platform, the database (server version, tables,
    rows), the LDAP directory, ioPix, the MCP switch, the last update check and update, and the accounts."""
    need_admin()
    out = {"version": __version__, "commit": updater.local_commit()[:7], "docker": updater.in_docker(),
           "python": sys.version.split()[0], "platform": platform.platform(), "appDir": str(config.APP_DIR),
           "publicUrl": config.PUBLIC_URL or None,
           "ldap": {"port": config.LDAP_PORT, "base": config.LDAP_BASE} if config.LDAP_PORT else "off",
           "proxySignIn": auth.proxy.mode(), "update": updater.status()}
    try:
        out["database"] = {"host": f"{config.DB_HOST}:{config.DB_PORT}", "name": config.DB_NAME,
                           "server": db.one("SELECT version() AS v")["v"],
                           "schema": db.schema_version(),
                           "contacts": db.one("SELECT count(*) AS n FROM con_contacts WHERE deleted = 0")["n"],
                           "tombstones": db.one("SELECT count(*) AS n FROM con_contacts WHERE deleted = 1")["n"],
                           "relations": db.one("SELECT count(*) AS n FROM con_contact_relations")["n"],
                           "addressBooks": db.one("SELECT count(*) AS n FROM con_address_books")["n"]}
    except Exception as e:  # noqa: BLE001
        out["database"] = {"error": str(e)[:200]}
    from app.main import mcp_enabled
    out["mcp"] = {"enabled": mcp_enabled(), "forcedByEnv": config.MCP_FORCED}
    ip = iopix.public_settings()
    out["iopix"] = {"url": ip.get("url") or None, "connected": ip["enabled"]}
    out["accounts"] = [{"name": u["name"], "role": u["role"]} for u in users.all_users()]
    return out


@server.tool(annotations=READ_ONLY)
def test_iopix() -> dict:
    """Admins: whether ioPix (found in the suite by itself) answers, and how many people it has."""
    need_admin()
    if not iopix.settings()["url"]:
        raise ToolError("ioPix is not part of the suite (it connects by itself once it runs on the same Shared ioSuite database)")
    return iopix.test()


@server.tool(annotations=READ_ONLY)
def list_accounts() -> list:
    """Admins: the accounts, with their roles (viewer, member, editor, admin)."""
    need_admin()
    return [{"name": u["name"], "displayName": u.get("display_name"), "email": u.get("email"), "role": u["role"]} for u in users.all_users()]
