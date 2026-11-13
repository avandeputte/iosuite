"""The tools that change tasks and lists, with the same permissions as the web app: a viewer only reads, a member
changes their own private lists, editors and admins the shared ones too. Every change reaches phones at their next sync."""
from typing import Literal, Optional

from iosuite_shared import users as shared_users
from mcp.server.mcpserver.exceptions import ToolError

from app import ical, members as fam, model
from app.mcp.base import ADDS, DELETES, WRITES, default_list, find_list, find_task, server, task_out, who

TASK_FIELDS = """
    due: '2026-11-03' (a day) or '2026-11-03T17:00' (a time, in timezone or the server's); '' removes it.
    priority: high, medium, low or none.
    members: the family members the task is for (names from overview's family); [] removes them.
    repeat: an RFC 5545 RRULE such as 'FREQ=WEEKLY;BYDAY=SA', 'FREQ=MONTHLY;BYMONTHDAY=1' or 'FREQ=DAILY;COUNT=5'
    (needs a due date); '' stops the repeating.
    repeat_after: instead of repeat, for a task that comes back some time after it was ticked off (not on fixed
    dates): an ISO 8601 duration of days, weeks, months or years, 'P2W' is two weeks after the day it is done; ''
    stops it.
    alerts: when to remind, ISO date-times such as ['2026-11-03T08:00']; [] removes them.
    parent: the id of the task this one is a subtask of (same list).
"""


def fields(fn):
    fn.__doc__ = (fn.__doc__ or "") + TASK_FIELDS
    return fn


def _data(u, title=None, notes=None, due=None, timezone=None, priority=None, repeat=None, alerts=None, url=None,
          members=None, parent=None, repeat_after=None) -> dict:
    d = {}
    for k, v in (("title", title), ("notes", notes), ("due", due), ("timezone", timezone), ("priority", priority),
                 ("rrule", repeat), ("repeatAfter", repeat_after), ("alarms", alerts), ("url", url)):
        if v is not None:
            d[k] = v
    if "timezone" in d and d["timezone"] and not ical.valid_tz(d["timezone"]):
        raise ToolError(f"Unknown time zone '{d['timezone']}' (an IANA name such as Europe/Brussels or America/New_York)")
    if members is not None:
        try:
            d["members"] = [m["id"] for m in fam.resolve(members)]
        except ValueError as e:
            raise ToolError(str(e))
    if parent not in (None, ""):
        p, _ = find_task(u, parent)
        d["parent"] = p["id"]
    return d


@server.tool(annotations=ADDS)
@fields
def create_task(title: str, list: Optional[str] = None, notes: Optional[str] = None, due: Optional[str] = None,
                timezone: Optional[str] = None, priority: Optional[Literal["high", "medium", "low", "none"]] = None,
                repeat: Optional[str] = None, alerts: Optional[list[str]] = None, url: Optional[str] = None,
                members: Optional[list[str]] = None, parent: Optional[str] = None, repeat_after: Optional[str] = None) -> dict:
    """Add a task. list: a name or id (else the parent's list, or the Family list, or your own when you may not change it)."""
    from app.api import _create_task
    u = who()
    d = _data(u, title, notes, due, timezone, priority, repeat, alerts, url, members, parent, repeat_after)
    c = find_list(u, list, writable=True) if list else None
    try:
        with model.step("mcp"):
            r = _create_task(u, d, None, str(c["id"]) if c else (None if "parent" in d else str(default_list(u)["id"])))
    except ValueError as e:
        raise ToolError(str(e))
    except Exception as e:  # noqa: BLE001 - HTTPException from the shared code path
        raise ToolError(getattr(e, "detail", None) or str(e))
    return task_out(u, r)


@server.tool(annotations=WRITES)
@fields
def update_task(task: str, title: Optional[str] = None, notes: Optional[str] = None, due: Optional[str] = None,
                timezone: Optional[str] = None, priority: Optional[Literal["high", "medium", "low", "none"]] = None,
                repeat: Optional[str] = None, alerts: Optional[list[str]] = None, url: Optional[str] = None,
                members: Optional[list[str]] = None, parent: Optional[str] = None, repeat_after: Optional[str] = None) -> dict:
    """Change a task (by id or title); only the fields given change ('' clears a text field or the due date)."""
    from app.api import change
    u = who()
    r, c = find_task(u, task, writable=True)
    d = _data(u, title, notes, due, timezone, priority, repeat, alerts, url, members, parent, repeat_after)
    if not d:
        raise ToolError("Nothing to change")
    try:
        with model.step("mcp"):
            r2 = change(u, r, c, d, True)
    except (ValueError, PermissionError) as e:
        raise ToolError(str(e))
    except Exception as e:  # noqa: BLE001
        raise ToolError(getattr(e, "detail", None) or str(e))
    return task_out(u, r2)


@server.tool(annotations=WRITES)
def complete_task(task: str, done: bool = True) -> dict:
    """Tick a task off (by id or title), or with done=false open it again. A repeating task moves on to its next due
    date instead of closing (moved: true)."""
    u = who()
    r, _ = find_task(u, task, writable=True)
    cal = ical.parse(r["ics"])
    moved = ical.complete(cal, done)
    with model.step("mcp"):
        r2 = model.save(r["list_id"], ical.finish(cal), r["id"], None, u["id"], "done" if moved else None,
                        f"next {(ical.todo_json(cal)['due'] or '')[:10]}" if moved else None)
    return {**task_out(u, r2), "moved": moved}


@server.tool(annotations=DELETES)
def delete_task(task: str) -> dict:
    """Delete a task (by id or title) and its subtasks. Ask the person first."""
    u = who()
    r, _ = find_task(u, task, writable=True)
    with model.step("mcp"):
        return {"deleted": r["summary"], "id": r["id"], "count": model.delete_with_subtasks(r["id"], u["id"])}


@server.tool(annotations=WRITES)
def move_task(task: str, list: str) -> dict:
    """Move a task (with its subtasks) to another list."""
    u = who()
    r, _ = find_task(u, task, writable=True)
    c = find_list(u, list, writable=True)
    try:
        with model.step("mcp"):
            r2 = model.move(r["id"], c["id"], u["id"])
    except ValueError as e:
        raise ToolError(str(e))
    return task_out(u, r2)


@server.tool(annotations=ADDS)
def create_list(name: str, shared: bool = False, color: Optional[str] = None, description: Optional[str] = None) -> dict:
    """A new list: private (only you see it) or shared with everyone (editors and admins). color: #rrggbb."""
    u = who()
    if shared and not shared_users.can_write(u):
        raise ToolError("Only editors make shared lists")
    if not shared and not shared_users.is_member(u):
        raise ToolError("A viewer only looks; a member keeps lists of their own")
    lid = model.create_list(None if shared else u["id"], name, description, color)
    c = model.task_list(lid)
    return {"id": c["id"], "name": c["name"], "shared": shared, "color": c["color"]}


@server.tool(annotations=ADDS)
def import_ics(ics: str, list: Optional[str] = None, replace: bool = True) -> dict:
    """Tasks from iCalendar text (VTODOs: one task or a whole export) into a list. A task whose UID the list has already
    is updated (replace=false: left as it is)."""
    u = who()
    c = find_list(u, list, writable=True) if list else default_list(u)
    try:
        with model.step("mcp"):
            return model.import_text(c["id"], ics, u["id"], replace)
    except ValueError as e:
        raise ToolError(str(e))


@server.tool(annotations=WRITES)
def undo(step: str) -> dict:
    """Take a change back: `step` is what recent_activity gives for it. What the step added goes, what it changed or
    deleted is as it was before (a task with its subtasks, as one). Refused once a task was changed again since."""
    u = who()
    try:
        with model.step("mcp"):
            return model.undo(step, u)
    except (ValueError, PermissionError, model.NotFound) as e:
        raise ToolError(str(e))


@server.tool(annotations=ADDS)
def apply_template(template: str, list: str, due: Optional[str] = None) -> dict:
    """Add a template's tasks (by its name or id, see list_templates) to a list. due: a day they are all due on
    ('2026-11-20'); without it they have no due date."""
    u = who()
    s = str(template).strip().lower()
    hit = [t for t in model.templates_for(u) if str(t["id"]) == s or t["name"].lower() == s]
    if len(hit) != 1:
        raise ToolError(f"No template '{template}'. There are: " + (", ".join(t["name"] for t in model.templates_for(u)) or "none yet"))
    c = find_list(u, list, writable=True)
    try:
        with model.step("mcp") as step:
            return {"created": model.apply_template(hit[0], c["id"], u["id"], ical.parse_when(due).isoformat()[:10] if due else None),
                    "list": c["name"], "step": step}
    except ValueError as e:
        raise ToolError(str(e))
