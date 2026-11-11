"""The server itself, for admins: health, the version check and the update (update.sh, as in the rest of the suite),
the Birthdays calendar from ioContacts and the Holidays calendars."""
import platform
import sys
from typing import Optional

from mcp.server.mcpserver.exceptions import ToolError

from app import __version__, config, contacts, db, holiday, ical, users
from app.auth import updater
from app.mcp.base import READ_ONLY, UPDATES, WRITES, need_admin, server


@server.tool(annotations=READ_ONLY)
def diagnostics() -> dict:
    """Admins: the server's health: version and commit, Python and platform, the time zone, the database (server
    version, tables, rows), ioContacts, the MCP switch, the last update check and update, and the accounts."""
    need_admin()
    out = {"version": __version__, "commit": updater.local_commit()[:7], "docker": updater.in_docker(),
           "python": sys.version.split()[0], "platform": platform.platform(), "appDir": str(config.APP_DIR),
           "publicUrl": config.PUBLIC_URL or None, "timezone": ical.default_tz(), "update": updater.status()}
    try:
        out["database"] = {"host": f"{config.DB_HOST}:{config.DB_PORT}", "name": config.DB_NAME,
                           "server": db.one("SELECT version() AS v")["v"],
                           "schema": db.schema_version(),
                           "calendars": db.one("SELECT count(*) AS n FROM cal_calendars")["n"],
                           "events": db.one("SELECT count(*) AS n FROM cal_events WHERE deleted = 0")["n"],
                           "tombstones": db.one("SELECT count(*) AS n FROM cal_events WHERE deleted = 1")["n"]}
    except Exception as e:  # noqa: BLE001
        out["database"] = {"error": str(e)[:200]}
    from app.main import mcp_enabled
    out["mcp"] = {"enabled": mcp_enabled(), "forcedByEnv": config.MCP_FORCED}
    s = contacts.public_settings()
    out["iocontacts"] = {"url": s.get("url") or None, "connected": s["enabled"], "birthdays": s["birthdays"], "lastSync": s["lastSync"]}
    h = holiday.public_settings()
    out["holidays"] = {"countries": [{k: x[k] for k in ("country", "region", "language")} for x in h["items"]], "lastSync": h["lastSync"]}
    out["accounts"] = [{"name": u["name"], "role": u.get("role")} for u in users.all_users()]
    return out


@server.tool(annotations=UPDATES)
def sync_birthdays() -> dict:
    """Admins: bring the Birthdays calendar up to date from ioContacts now (it also happens every few hours)."""
    need_admin()
    if not contacts.enabled():
        raise ToolError("ioContacts is not part of the suite (it connects by itself once it runs on the same Shared ioSuite database)")
    return contacts.sync_birthdays()


@server.tool(annotations=WRITES)
def set_holidays(country: str, region: Optional[str] = None, language: Optional[str] = None, remove: bool = False) -> dict:
    """Admins: add a shared Holidays calendar for a country, or change the region or language of one already there
    (each country has its own calendar; others stay). country: a two-letter code (US, BE, NL, GB...); region: a state or
    province code of that country (US: NY, CA...; BE: none); language: of the holiday names (e.g. nl, fr), else the
    country's own; remove: true takes that country's calendar away. Use holiday_regions to see the choices."""
    need_admin()
    try:
        if remove:
            holiday.remove_country(country)
        else:
            holiday.set_country(country, region, language)
    except ValueError as e:
        raise ToolError(str(e))
    sync = holiday.sync()
    return {"countries": [{k: x[k] for k in ("country", "countryName", "region", "language")} for x in holiday.public_settings()["items"]],
            "sync": sync}


@server.tool(annotations=READ_ONLY)
def holiday_regions(country: str) -> dict:
    """The regions (states, provinces...) of a country and the languages its holiday names come in."""
    try:
        return holiday.country_info(country)
    except ValueError as e:
        raise ToolError(str(e))


@server.tool(annotations=UPDATES)
def check_for_update() -> dict:
    """Admins: the installed version and commit against GitHub's main branch (status: current, update or error), and
    the outcome of the last update (lastUpdate: ok, text, at)."""
    need_admin()
    return {**updater.check(), "lastUpdate": updater.last_result(), "canUpdateHere": updater.can_run(), "docker": updater.in_docker()}


@server.tool(annotations=UPDATES)
def update_server() -> dict:
    """Admins: update ioCalendar to the newest version on GitHub and restart it (update.sh: the code and its packages;
    the settings and the database stay, and the database is brought up to date as it starts). The connection drops
    while it restarts (about a minute); call check_for_update afterwards: lastUpdate says what happened. Not in
    Docker (pull the image there)."""
    need_admin()
    try:
        updater.run()
    except RuntimeError as e:
        raise ToolError(str(e))
    return {"started": True, "installed": updater.local_commit()[:7], "ref": updater.branch,
            "note": "update.sh is running; ioCalendar restarts when it finishes. Then call check_for_update."}


@server.tool(annotations=READ_ONLY)
def list_accounts() -> list:
    """Admins: the accounts, with their roles here (viewer, member, editor, admin)."""
    need_admin()
    return [{"name": u["name"], "displayName": u.get("displayName"), "email": u.get("email") or None, "role": u.get("role")}
            for u in users.all_users()]
