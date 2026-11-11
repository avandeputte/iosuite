"""The server itself, for admins: health, the version check and the update (update.sh, as in the rest of the suite)."""
import platform
import sys

from mcp.server.mcpserver.exceptions import ToolError

from app import __version__, config, db, ical, users
from app.auth import updater
from app.mcp.base import READ_ONLY, UPDATES, need_admin, server


@server.tool(annotations=READ_ONLY)
def diagnostics() -> dict:
    """Admins: the server's health: version and commit, Python and platform, the time zone, the database (server
    version, tables, rows), the MCP switch, the last update check and update, and the accounts."""
    need_admin()
    out = {"version": __version__, "commit": updater.local_commit()[:7], "docker": updater.in_docker(),
           "python": sys.version.split()[0], "platform": platform.platform(), "appDir": str(config.APP_DIR),
           "publicUrl": config.PUBLIC_URL or None, "timezone": ical.default_tz(), "update": updater.status()}
    try:
        out["database"] = {"host": f"{config.DB_HOST}:{config.DB_PORT}", "name": config.DB_NAME,
                           "server": db.one("SELECT version() AS v")["v"],
                           "schema": db.schema_version(),
                           "lists": db.one("SELECT count(*) AS n FROM tsk_lists")["n"],
                           "tasks": db.one("SELECT count(*) AS n FROM tsk_tasks WHERE deleted = 0")["n"],
                           "open": db.one("SELECT count(*) AS n FROM tsk_tasks WHERE deleted = 0 AND done = 0")["n"],
                           "tombstones": db.one("SELECT count(*) AS n FROM tsk_tasks WHERE deleted = 1")["n"]}
    except Exception as e:  # noqa: BLE001
        out["database"] = {"error": str(e)[:200]}
    from app.main import mcp_enabled
    out["mcp"] = {"enabled": mcp_enabled(), "forcedByEnv": config.MCP_FORCED}
    out["accounts"] = [{"name": u["name"], "role": u.get("role")} for u in users.all_users()]
    return out


@server.tool(annotations=UPDATES)
def check_for_update() -> dict:
    """Admins: the installed version and commit against GitHub's main branch (status: current, update or error), and
    the outcome of the last update (lastUpdate: ok, text, at)."""
    need_admin()
    return {**updater.check(), "lastUpdate": updater.last_result(), "canUpdateHere": updater.can_run(), "docker": updater.in_docker()}


@server.tool(annotations=UPDATES)
def update_server() -> dict:
    """Admins: update ioTasks to the newest version on GitHub and restart it (update.sh: the code and its packages;
    the settings and the database stay, and the database is brought up to date as it starts). The connection drops
    while it restarts (about a minute); call check_for_update afterwards: lastUpdate says what happened. Not in
    Docker (pull the image there)."""
    need_admin()
    try:
        updater.run()
    except RuntimeError as e:
        raise ToolError(str(e))
    return {"started": True, "installed": updater.local_commit()[:7], "ref": updater.branch,
            "note": "update.sh is running; ioTasks restarts when it finishes. Then call check_for_update."}


@server.tool(annotations=READ_ONLY)
def list_accounts() -> list:
    """Admins: the accounts, with their roles here (viewer, member, editor, admin)."""
    need_admin()
    return [{"name": u["name"], "displayName": u.get("displayName"), "email": u.get("email") or None, "role": u.get("role")}
            for u in users.all_users()]
