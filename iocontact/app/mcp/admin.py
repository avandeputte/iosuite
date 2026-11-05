"""The server itself, for admins: health, accounts, the version check and the update (update.sh, as in iopix)."""
import platform
import sys
from typing import Optional

from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from app import __version__, config, db, iopix, users
from app.auth import auth, updater
from app.mcp.base import READ_ONLY, need_admin, server

UPDATES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)  # reaches GitHub


@server.tool(annotations=READ_ONLY)
def diagnostics() -> dict:
    """Admins: the server's health: version and commit, Python and platform, the database (server version, tables,
    rows), the LDAP directory, ioPix, the MCP switch, the last update check and update, and the accounts."""
    need_admin()
    out = {"version": __version__, "commit": updater.local_commit()[:7], "docker": updater.in_docker(),
           "python": sys.version.split()[0], "platform": platform.platform(), "appDir": str(config.ROOT),
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
    from app.api import mcp_enabled
    out["mcp"] = {"enabled": mcp_enabled(), "forcedByEnv": config.MCP_FORCED}
    ip = iopix.public_settings()
    out["iopix"] = {"url": ip.get("url") or None, "signIn": bool(ip.get("user")), "serviceToken": bool(ip.get("cfId"))}
    out["accounts"] = [{"name": u["name"], "role": u["role"]} for u in users.all_users()]
    return out


@server.tool(annotations=READ_ONLY)
def test_iopix() -> dict:
    """Admins: whether ioPix answers with the address and sign-in in Settings › ioPix, and how many people it has."""
    need_admin()
    if not iopix.settings()["url"]:
        raise ToolError("ioPix is not set up (Settings › ioPix in the web app)")
    return iopix.test()


@server.tool(annotations=UPDATES)
def check_for_update() -> dict:
    """Admins: the installed version and commit against GitHub's main branch (status: current, update or error), and
    the outcome of the last update (lastUpdate: ok, text, at)."""
    need_admin()
    return {**updater.check(), "lastUpdate": updater.last_result(), "canUpdateHere": updater.can_run(), "docker": updater.in_docker()}


@server.tool(annotations=UPDATES)
def update_server(ref: Optional[str] = None) -> dict:
    """Admins: update ioContacts to the newest version on GitHub and restart it (update.sh: the code and its packages;
    the settings and the database stay, and the database is brought up to date as it starts). ref: a commit id or
    branch to install instead of the tip of main. Nothing happens when that commit is already installed. The
    connection drops while it restarts (about a minute); call check_for_update afterwards: lastUpdate says what
    happened. Not in Docker (pull the image there)."""
    need_admin()
    try:
        updater.run(ref or "")
    except RuntimeError as e:
        raise ToolError(str(e))
    return {"started": True, "installed": updater.local_commit()[:7], "ref": ref or updater.branch,
            "note": "update.sh is running; ioContacts restarts when it finishes. Then call check_for_update."}


@server.tool(annotations=READ_ONLY)
def list_accounts() -> list:
    """Admins: the accounts, with their roles (viewer, editor, admin)."""
    need_admin()
    return [{"name": u["name"], "displayName": u.get("display_name"), "email": u.get("email"), "role": u["role"]} for u in users.all_users()]
