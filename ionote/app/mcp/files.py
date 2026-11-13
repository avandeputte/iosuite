"""The operator's tools, for admins: ioNote's health and its log."""
import platform
import sys
from typing import Literal

from mcp.server.mcpserver.exceptions import ToolError

from app import __version__, config, db, images, ocr
from app.auth import updater
from iosuite_shared import users
from iosuite_shared.updates import tail
from app.mcp.base import READ_ONLY, need_admin, server

LOG_LINES_MAX = 2000


@server.tool(annotations=READ_ONLY)
def diagnostics() -> dict:
    """ionote' own health: version and commit, Python and platform, the database (type, server version,
    reachable), the stored pictures, text recognition, accounts, and the switches that are on."""
    need_admin()
    s = db.public_settings()
    out = {"version": __version__, "commit": updater.local_commit()[:7], "python": sys.version.split()[0], "platform": platform.platform(),
           "docker": updater.in_docker(), "database": {k: s[k] for k in ("type", "host", "port", "database", "user") if k in s},
           "pictures": images.stats(), "ocr": ocr.status(), "accounts": len(users.list_users(config.APP)), "rev": db.current_rev(),
           "require_login": users.require_login(config.APP), "data_dir": str(config.DATA_DIR), "app_url": config.BASE_URL}
    if s["type"] == "mysql":
        t = db.test({})
        out["database"].update({"reachable": t["ok"], "server": t.get("version"), "max_allowed_packet": t.get("maxAllowedPacket"),
                                "warning": t.get("warning"), "error": t.get("error")})
    return {k: v for k, v in out.items() if v is not None}


@server.tool(annotations=READ_ONLY)
def server_log(lines: int = 200, contains: str = "", level: Literal["any", "warning", "error", "auth"] = "any") -> dict:
    """The last lines of ionote' own log (data/ionote.log, rotating). `contains` keeps only lines with that text;
    `level` keeps only WARNING+ or ERROR+ lines, or the sign-ins (auth)."""
    need_admin()
    if not config.LOG_FILE:
        raise ToolError("no server log: LOG_FILE is empty in config.env")
    try:
        return tail(config.LOG_FILE, min(int(lines), LOG_LINES_MAX), contains, level)
    except OSError as e:
        raise ToolError(f"cannot read the log: {e}")
