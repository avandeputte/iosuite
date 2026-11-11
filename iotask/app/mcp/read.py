"""The read-only tools: what any signed-in account may ask about the lists it can see."""
import datetime as dt
from typing import Literal, Optional

from mcp.server.mcpserver.exceptions import ToolError

from app import __version__, config, ical, members, model
from app.mcp.base import READ_ONLY, clamp, find_list, find_task, lists, member_ids, server, task_out, who


def _pick(u: dict, names: Optional[list[str]]) -> list[dict]:
    if not names:
        return lists(u)
    return [find_list(u, n) for n in names]


@server.tool(annotations=READ_ONLY)
def overview() -> dict:
    """Who you are signed in as, the lists you can see (with their open tasks and whether you may change them), the
    family members tasks can be for, the server's time zone and today's date there, and the open tasks that are overdue
    or due today. Start here."""
    u = who()
    tz = ical.default_tz()
    now = dt.datetime.now(ical.zone(tz))
    ls = lists(u)
    ids = [c["id"] for c in ls]
    subs = model.subtask_counts(ids)
    return {
        "you": {"name": u["name"], "displayName": u.get("displayName"), "role": u.get("role")},
        "lists": [{"id": c["id"], "name": c["name"], "shared": c["owner_id"] is None, "openTasks": c.get("n"), "overdue": c.get("late"),
                   "youCanChange": model.can_write(u, c)} for c in ls],
        "timezone": tz, "now": now.isoformat(timespec="minutes"), "today": now.date().isoformat(), "weekday": now.strftime("%A"),
        "dueToday": [task_out(u, r, subs) for r in model.find(ids, "", "open", "today", limit=200)],
        "family": [m["displayName"] for m in members.family()],
        "version": __version__, "webApp": config.PUBLIC_URL or None,
    }


@server.tool(annotations=READ_ONLY)
def list_family_members() -> list:
    """The family members a task can be for (the accounts that use ioTasks)."""
    who()
    return members.public(members.family())


@server.tool(annotations=READ_ONLY)
def list_lists() -> list:
    """The lists you can see: the shared Family list (and other shared ones) and your private ones."""
    u = who()
    return [{"id": c["id"], "name": c["name"], "description": c.get("description"), "color": c.get("color"), "shared": c["owner_id"] is None,
             "openTasks": c.get("n"), "overdue": c.get("late"), "youCanChange": model.can_write(u, c)} for c in lists(u)]


@server.tool(annotations=READ_ONLY)
def list_tasks(lists: Optional[list[str]] = None, status: Literal["open", "done", "all"] = "open", due: Optional[str] = None,
               member: Optional[list[str]] = None, limit: int = 200) -> dict:
    """Tasks, soonest due first (done ones: the latest done first). lists: names or ids (all when left out). due:
    'today' (due today or before), 'overdue', 'week' (the next seven days or before), 'scheduled' (any due date),
    'none' (no due date) or a date (YYYY-MM-DD). member: only the tasks for these family members (names)."""
    u = who()
    ls = _pick(u, lists)
    try:
        rows = model.find([c["id"] for c in ls], "", status, due, member_ids(member), clamp(limit, 1, 2000))
    except ValueError as e:
        raise ToolError(str(e))
    subs = model.subtask_counts([c["id"] for c in ls])
    return {"total": len(rows), "items": [task_out(u, r, subs) for r in rows]}


@server.tool(annotations=READ_ONLY)
def search_tasks(text: str, lists: Optional[list[str]] = None, status: Literal["open", "done", "all"] = "all", limit: int = 50) -> list:
    """Tasks whose title or notes contain every word of text (open and done ones unless status says otherwise)."""
    u = who()
    ls = _pick(u, lists)
    rows = model.find([c["id"] for c in ls], text, status, limit=clamp(limit, 1, 500))
    subs = model.subtask_counts([c["id"] for c in ls])
    return [task_out(u, r, subs) for r in rows]


@server.tool(annotations=READ_ONLY)
def get_task(task: str) -> dict:
    """Everything about one task (by id or title): title, notes, due date or time, priority, whether it is done (and
    when), the repeat rule, alerts, link, the family members it is for, and its subtasks."""
    u = who()
    r, _ = find_task(u, task)
    subs = model.subtask_counts([r["list_id"]])
    out = task_out(u, r, subs)
    kids = model.subtasks_of(r)
    if kids:
        out["children"] = [task_out(u, k, subs) for k in kids]
    return out


@server.tool(annotations=READ_ONLY)
def get_ics(task: str) -> str:
    """One task as iCalendar text (a VTODO, RFC 5545), exactly as reminders apps get it."""
    u = who()
    r, _ = find_task(u, task)
    return r["ics"]


@server.tool(annotations=READ_ONLY)
def connection_details() -> dict:
    """What to type into a reminders app for your account: the CalDAV address and user name (with an app password from
    Settings › Account), and each list's address."""
    u = who()
    base = config.PUBLIC_URL or "(this server's address)"
    return {"user": u["name"], "caldav": f"{base}/dav/", "lists": {c["name"]: f"{base}/dav/calendars/{u['name']}/{c['slug']}/" for c in lists(u)},
            "api": f"{base}/api/docs", "apple": "Settings › Apps and devices › Download the profile (adds the account to Reminders)"}
