"""The MCP server instance (iosuite_shared.mcp: who is asking, the annotations, the limits) and what every tool module
shares: finding lists and tasks."""
from mcp.server.mcpserver.exceptions import ToolError

from iosuite_shared import mcp as shared_mcp
from iosuite_shared.mcp import ADDS, DELETES, READ_ONLY, UPDATES, WRITES, clamp, current_user, need_admin, who

from app import __version__, config, members, model

# what the tool modules take from here: the suite's pieces (iosuite_shared.mcp) and ioTasks' own helpers
__all__ = ["server", "ADDS", "DELETES", "READ_ONLY", "UPDATES", "WRITES", "clamp", "current_user", "need_admin", "who", "task_link",
           "lists", "find_list", "default_list", "list_names", "find_task", "task_out", "member_ids"]

server = shared_mcp.make_server(
    config.APP, "ioTasks", __version__,
    instructions=(
        "The family's task lists (ioTasks). Start with overview: it says who you are, the lists you can see and change, "
        "the time zone, and the open tasks that are overdue or due today. list_tasks lists tasks (open by default; by "
        "list, by due date: today, overdue, week, scheduled, none, or a date; by family member); search_tasks finds them "
        "by words; get_task has everything about one, with its subtasks. Due dates are ISO 8601: '2026-11-03' is a day, "
        "'2026-11-03T17:00' a time in the server's time zone (or the timezone argument). complete_task ticks a task off; "
        "a repeating task then moves on to its next due date instead. A task can be for family members (members: names "
        "from overview's family) and can have subtasks (parent: the parent task's id). A task can repeat on fixed dates (repeat) or come back "
        "some time after it was ticked off (repeat_after). recent_activity says who did what, and undo takes a change "
        "back. The same tasks show in Apple Reminders on the family's phones. Ask before deleting tasks or lists."
    ),
)


def task_link(tid: int) -> str | None:
    return f"{config.PUBLIC_URL}/#/task/{tid}" if config.PUBLIC_URL else None


# ---- lists

def lists(u: dict) -> list[dict]:
    return model.lists_for(u)


def find_list(u: dict, ref, writable: bool = False) -> dict:
    """A list by id, name or slug ("Family", "Personal")."""
    ls = lists(u)
    s = str(ref).strip()
    hit = [c for c in ls if str(c["id"]) == s] or [c for c in ls if c["name"].lower() == s.lower() or c["slug"] == s.lower()]
    if not hit:
        raise ToolError(f"No list '{ref}'. These are yours: " + ", ".join(f"{c['name']} (id {c['id']})" for c in ls))
    if len(hit) > 1:
        raise ToolError(f"'{ref}' names more than one list: " + ", ".join(f"{c['name']} (id {c['id']})" for c in hit))
    c = hit[0]
    if writable and not model.can_write(u, c):
        raise ToolError(f"You can read '{c['name']}' but not change it (viewers change only their own private lists)")
    return c


def default_list(u: dict) -> dict:
    """Where a new task goes when no list is named: the first shared list this account may change, else its own."""
    ls = [c for c in lists(u) if model.can_write(u, c)]
    if not ls:
        raise ToolError("This account cannot add tasks anywhere")
    return ls[0]


def list_names(u: dict) -> dict:
    return {c["id"]: c["name"] for c in lists(u)}


# ---- tasks

def find_task(u: dict, ref, writable: bool = False) -> tuple[dict, dict]:
    """A task (row, list) by id, or by a title that matches exactly one task."""
    ls = {c["id"]: c for c in lists(u)}
    s = str(ref).strip()
    if not s:
        raise ToolError("Name a task (its id or its title)")
    if s.isdigit():
        r = model.get_row(int(s))
        if not r or r["deleted"] or r["list_id"] not in ls:
            raise ToolError(f"No task with id {s}")
    else:
        found = model.find(list(ls), s, "all", limit=20)
        rows = [x for x in found if x["summary"].lower() == s.lower()] or found
        open_ = [x for x in rows if not x["done"]]
        rows = open_ if len(open_) == 1 else rows
        if not rows:
            raise ToolError(f"No task matches '{s}'. Try search_tasks or list_tasks.")
        if len(rows) > 1:
            raise ToolError(f"'{s}' matches several tasks; give the id: " + "; ".join(f"{x['summary']} (id {x['id']})" for x in rows[:10]))
        r = rows[0]
    c = ls[r["list_id"]]
    if writable and not model.can_write(u, c):
        raise ToolError(f"You can read '{r['summary']}' but not change it (list {c['name']})")
    return r, c


def task_out(u: dict, r: dict, subs: dict | None = None) -> dict:
    j = model.task_out(r, subs)
    for k in ("href", "etag", "priorityValue", "status"):
        j.pop(k, None)
    j["list"] = list_names(u).get(r["list_id"])
    j["members"] = [m["displayName"] for m in j.get("members") or []]
    if j.get("subtasks") and not j["subtasks"]["total"]:
        j.pop("subtasks")
    link = task_link(r["id"])
    if link:
        j["webUrl"] = link
    return {k: v for k, v in j.items() if v not in (None, "", [], {}, False) or k == "done"}


def member_ids(refs) -> set[int] | None:
    """A member argument (a name, or a list of names or ids) as member ids; None when not given."""
    if refs in (None, "", []):
        return None
    try:
        return {m["id"] for m in members.resolve(refs)}
    except ValueError as e:
        raise ToolError(str(e))
