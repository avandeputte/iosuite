"""The operator's tools, behind the admin token: ionotes' health, its log, sign-in at a proxy, and the updater."""
import platform
import sys
from typing import Literal, Optional

from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from app import __version__, config, db, images, ocr, proxyauth, users
from app.auth import updater
from iosuite_shared.updates import tail
from app.mcp.base import READ_ONLY, WRITES, need_token, server

LOG_LINES_MAX = 2000


@server.tool(annotations=READ_ONLY)
def diagnostics(token: str) -> dict:
    """ionotes' own health: version and commit, Python and platform, the database (type, server version,
    reachable), the stored pictures, text recognition, accounts, and the switches that are on."""
    need_token(token)
    s = db.public_settings()
    out = {"version": __version__, "commit": updater.local_commit()[:7], "python": sys.version.split()[0], "platform": platform.platform(),
           "docker": updater.in_docker(), "database": {k: s[k] for k in ("type", "host", "port", "database", "user") if k in s},
           "pictures": images.stats(), "ocr": ocr.status(), "accounts": len(users.list_users()), "rev": db.current_rev(),
           "read_only": db.read_only(), "require_login": users.require_login(), "data_dir": str(config.DATA_DIR), "app_url": config.BASE_URL}
    if s["type"] == "mysql":
        t = db.test({})
        out["database"].update({"reachable": t["ok"], "server": t.get("version"), "max_allowed_packet": t.get("maxAllowedPacket"),
                                "warning": t.get("warning"), "error": t.get("error")})
    return {k: v for k, v in out.items() if v is not None}


@server.tool(annotations=READ_ONLY)
def server_log(token: str, lines: int = 200, contains: str = "", level: Literal["any", "warning", "error", "auth"] = "any") -> dict:
    """The last lines of ionotes' own log (data/ionotes.log, rotating). `contains` keeps only lines with that text;
    `level` keeps only WARNING+ or ERROR+ lines, or the sign-ins (auth)."""
    need_token(token)
    if not config.LOG_FILE:
        raise ToolError("no server log: LOG_FILE is empty in config.env")
    try:
        return tail(config.LOG_FILE, min(int(lines), LOG_LINES_MAX), contains, level)
    except OSError as e:
        raise ToolError(f"cannot read the log: {e}")


@server.tool(annotations=WRITES)
def proxy_signin(token: str, mode: Optional[str] = None, cf_access_team: Optional[str] = None, cf_access_aud: Optional[str] = None,
                 trusted: Optional[str] = None, create_role: Optional[str] = None) -> dict:
    """Sign-in at a reverse proxy (Cloudflare Access, Authelia behind HAProxy/nginx/Caddy/Traefik): with no settings
    given, how it is set up and the Cloudflare Access team and application last seen in requests; with settings, saves
    them (mode: off|cloudflare|haproxy|nginx|caddy|traefik|header; an empty string clears one; config.env still wins)."""
    need_token(token)
    changes = {k: v for k, v in (("AUTH_PROXY", mode), ("CF_ACCESS_TEAM", cf_access_team), ("CF_ACCESS_AUD", cf_access_aud),
                                 ("AUTH_PROXY_TRUSTED", trusted), ("AUTH_PROXY_CREATE", create_role)) if v is not None}
    if "AUTH_PROXY" in changes and changes["AUTH_PROXY"] not in ("", "off", *proxyauth.PRESETS):
        raise ToolError("mode: off, cloudflare, haproxy, nginx, caddy, traefik or header")
    if changes:
        proxyauth.save(changes)
    out = proxyauth.status()
    out["accounts"] = [{"name": u["name"], "role": u["role"], "email": u.get("email") or None} for u in users.list_users()]
    if out["seen"].get("email"):
        u = proxyauth.user_for(out["seen"]["email"]) if proxyauth.mode() != "off" else None
        out["seen"]["account"] = u["name"] if u else None
    return out


@server.tool(annotations=READ_ONLY)
def check_for_update() -> dict:
    """Installed version and commit versus GitHub's main branch (network), and the outcome of the last update run."""
    return {"version": __version__, **updater.check(), "lastUpdate": updater.last_result()}


@server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def update_ionotes(token: str, ref: str = "") -> dict:
    """Update ionotes to the latest commit on GitHub and restart it (update.sh: code, packages, service; settings and
    data are kept). ref: the commit sha (or branch) to install. The connection drops when ionotes restarts; call
    check_for_update afterwards. Not available in Docker (pull the image)."""
    if not updater.token_ok(token):
        raise ToolError("Wrong or missing admin token (the web app's Maintenance › MCP server shows it to an admin)")
    try:
        updater.run(ref)
    except RuntimeError as e:
        raise ToolError(str(e))
    return {"started": True, "installed": updater.local_commit()[:7], "ref": ref or "main",
            "note": "update.sh is running; ioNotes restarts when it finishes. Then call check_for_update."}
