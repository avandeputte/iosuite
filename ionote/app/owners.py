"""Whose notes: the first admin (who gets the notes made before accounts existed) and the account the MCP tools
work as (Settings › MCP server › Notes of)."""
from app import db, notes, users


def first_admin_id():
    """The account that gets the notes made before accounts existed, and that MCP works as by default: the first
    admin of ionotes (lowest id)."""
    ids = [u["id"] for u in users.list_users() if u.get("role") == "admin" or u.get("suiteAdmin")]
    return min(ids) if ids else None


def mcp_owner():
    """Whose notes the MCP tools read and change: Settings › MCP server › Notes of (an account), else the first admin."""
    try:
        chosen = int(db.get_setting("mcp_user", "0") or 0)
    except ValueError:
        chosen = 0
    if chosen and users.get(chosen):
        return chosen
    return first_admin_id() or (0 if not users.any_users() else notes.NOBODY)
