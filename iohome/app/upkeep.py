"""Upkeep and the maintenance log.

Upkeep is what a thing needs every so often: the boiler's service every year, the car's MOT, the water filter every
three months. Each has the day it is due next. When ioTask is part of the suite, an upkeep can also be a repeating task
there, in a list of the person who sets it up (nothing to configure: ioTask is found in the suite's list of apps, and
asked with that person's own sign-in, as ioRecipe does for the shopping list). The task repeats on the same rhythm and
links back to the thing; ticking it off in ioTask moves it on there, and ioHome reads its next due day from ioTask
whenever it shows the upkeep.

"Done" on an upkeep in ioHome writes a line in the thing's maintenance log, moves the upkeep on to its next day, and
ticks the task off in ioTask as well. The log also takes one-off lines (a repair, a part replaced), with a cost.
"""
import calendar
import datetime as dt
import json
import logging
import urllib.error

from fastapi import Request
from iosuite_shared import links
from iosuite_shared.errors import Invalid

from app import config, db
from app.model import Forbidden, NotFound, day, may_add, money, need_add, need_write, text, whole

log = logging.getLogger("iohome.upkeep")

UNITS = {"day": ("DAILY", "days"), "week": ("WEEKLY", "weeks"), "month": ("MONTHLY", "months"), "year": ("YEARLY", "years")}
TASKS = "iotask"
TIMEOUT = 8


# ------------------------------------------------------------------ the rhythm

def step(d: dt.date, n: int, unit: str) -> dt.date:
    """The day n units after d (a month later from the 31st: the last day of that month)."""
    if unit == "day":
        return d + dt.timedelta(days=n)
    if unit == "week":
        return d + dt.timedelta(weeks=n)
    months = n * (12 if unit == "year" else 1)
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def rhythm(n: int, unit: str) -> str:
    """How people say it: every year, every 3 months."""
    one = {"day": "day", "week": "week", "month": "month", "year": "year"}[unit]
    return f"every {one}" if n == 1 else f"every {n} {UNITS[unit][1]}"


def rrule(n: int, unit: str) -> str:
    return f"FREQ={UNITS[unit][0]};INTERVAL={int(n)}"


def _clean(data: dict, partial: bool = False) -> dict:
    out = {}
    if "title" in data or not partial:
        out["title"] = text(data.get("title"), 255, "What it is")
        if not out["title"]:
            raise Invalid("What needs doing, please (Service, MOT, Replace the filter)")
    if "everyN" in data or not partial:
        out["every_n"] = whole(data.get("everyN") or 1, "How often", 1, 1000)
    if "everyUnit" in data or not partial:
        u = str(data.get("everyUnit") or "year").lower().rstrip("s")
        if u not in UNITS:
            raise Invalid("everyUnit: day, week, month or year")
        out["every_unit"] = u
    if "nextDue" in data or not partial:
        out["next_due"] = day(data.get("nextDue"), "Next due") or dt.date.today()
    if "notes" in data:
        out["notes"] = text(data.get("notes"), 4000, "The notes", True)
    return out


# ------------------------------------------------------------------ ioTask, asked as the viewer

class Unavailable(Exception):
    """ioTask could not be asked, or would not do it: (status, why)."""

    def __init__(self, status: int, why: str):
        super().__init__(why)
        self.status = status


def tasks_enabled() -> bool:
    try:
        return links.available(TASKS)
    except Exception:  # noqa: BLE001 - no database yet
        return False


def tasks_url() -> str:
    try:
        return links.url(TASKS) or ""
    except Exception:  # noqa: BLE001
        return ""


def ask(request: Request, path: str, params: dict | None = None, body: dict | None = None, method: str | None = None):
    """ioTask's answer to path, asked as the viewer; Unavailable when it is not in the suite or would not answer."""
    if not tasks_enabled():
        raise Unavailable(404, "ioTask is not part of the suite")
    if links.resting(TASKS):
        raise Unavailable(502, "ioTask did not answer a moment ago")
    try:
        return links.as_viewer(request, TASKS, path, params, body, method=method, timeout=TIMEOUT, user_agent="ioHome")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403) and body is None and method is None:
            raise Unavailable(403, "ioTask does not let this account in: open it once and sign in there") from None
        try:
            detail = json.loads(e.read()).get("detail")
        except (ValueError, AttributeError):
            detail = None
        if e.code in (400, 403, 404, 409, 412) and isinstance(detail, str):
            raise Unavailable(e.code, detail) from None
        raise Unavailable(502, f"ioTask answered {e.code}") from None
    except links.Unreachable as e:
        raise Unavailable(502, f"ioTask is not reachable ({type(e.why).__name__ if e.why else 'no address'})") from None


def task_lists(request: Request) -> list[dict]:
    """The viewer's lists in ioTask that take new tasks: [{id, name, shared}]."""
    got = ask(request, "/api/lists")
    return [{"id": c["id"], "name": c["name"], "shared": bool(c.get("shared"))} for c in got.get("items") or [] if c.get("writable")]


def _link(item_id: int) -> str | None:
    return f"{config.PUBLIC_URL}/#/item/{item_id}" if config.PUBLIC_URL else None


def _task_body(k: dict, item_name: str) -> dict:
    body = {"title": f"{item_name}: {k['title']}"[:255], "due": k["next_due"].isoformat(), "rrule": rrule(k["every_n"], k["every_unit"]),
            "notes": "\n".join(x for x in (k.get("notes"), f"Upkeep of {item_name} in ioHome ({rhythm(k['every_n'], k['every_unit'])})") if x)}
    link = _link(k["item_id"])
    if link:
        body["url"] = link
    return body


# ------------------------------------------------------------------ reading

def _out(k: dict, task: dict | None = None) -> dict:
    out = {"id": k["id"], "itemId": k["item_id"], "title": k["title"], "everyN": k["every_n"], "everyUnit": k["every_unit"],
           "every": rhythm(k["every_n"], k["every_unit"]), "nextDue": k["next_due"].isoformat(), "notes": k["notes"],
           "daysLeft": (k["next_due"] - dt.date.today()).days, "task": None}
    if k.get("task_id"):
        out["task"] = {"id": k["task_id"], "list": k["task_list"], "url": f"{tasks_url()}/#/task/{k['task_id']}" if tasks_url() else None}
    if "item_name" in k:
        out["item"] = {"id": k["item_id"], "name": k["item_name"], "photo": f"api/items/{k['item_id']}/files/{k['photo']}" if k.get("photo") else None}
    if task:
        out["task"].update(task)
    return out


def get(kid) -> dict:
    k = db.one("SELECT * FROM hom_upkeep WHERE id = %s", (int(kid),)) if str(kid).isdigit() else None
    if not k:
        raise NotFound("No such upkeep")
    return k


def of_item(item_id: int) -> list[dict]:
    return [_out(k) for k in db.q("SELECT * FROM hom_upkeep WHERE item_id = %s ORDER BY next_due, id", (item_id,))]


def all_due(within_days: int | None = None, include_archived: bool = False) -> list[dict]:
    """Every upkeep, the soonest first (within_days: only those due by then, the late ones included)."""
    where, args = [], []
    if not include_archived:
        where.append("i.archived = 0")
    if within_days is not None:
        where.append("k.next_due <= %s")
        args.append(dt.date.today() + dt.timedelta(days=int(within_days)))
    rows = db.q("SELECT k.*, i.name AS item_name, i.photo FROM hom_upkeep k JOIN hom_items i ON i.id = k.item_id "
                f"{'WHERE ' + ' AND '.join(where) if where else ''} ORDER BY k.next_due, i.name, k.id", args)
    return [_out(k) for k in rows]


def sync(request: Request, item_id: int | None = None) -> None:
    """The next due day of each upkeep that is a task in ioTask, as ioTask has it now (the task may have been ticked off
    there, or moved). Only the tasks the viewer may see are asked; quietly nothing when ioTask does not answer."""
    if not tasks_enabled() or links.resting(TASKS):
        return
    rows = db.q("SELECT id, task_id, next_due FROM hom_upkeep WHERE task_id IS NOT NULL" + (" AND item_id = %s" if item_id else ""),
                (item_id,) if item_id else ())
    for k in rows[:50]:
        try:
            t = ask(request, f"/api/tasks/{k['task_id']}")
        except Unavailable as e:
            if e.status == 404:  # gone from ioTask: the upkeep goes on here without it
                db.ex("UPDATE hom_upkeep SET task_id = NULL, task_list = NULL, task_by = NULL WHERE id = %s", (k["id"],))
            if e.status == 502:
                return
            continue
        due = str(t.get("due") or "")[:10]
        try:
            d = dt.date.fromisoformat(due)
        except ValueError:
            continue
        if d != k["next_due"]:
            db.ex("UPDATE hom_upkeep SET next_due = %s WHERE id = %s", (d, k["id"]))


# ------------------------------------------------------------------ changing

def _item(item_id: int) -> dict:
    it = db.one("SELECT id, name, created_by FROM hom_items WHERE id = %s", (item_id,))
    if not it:
        raise NotFound("No such thing")
    return it


def add(request: Request | None, u: dict, item_id: int, data: dict) -> dict:
    """{title, everyN, everyUnit, nextDue, notes?, listId?}: listId puts it in that list of yours in ioTask as a
    repeating task (an error from ioTask is passed on and nothing is kept)."""
    need_add(u)
    it = _item(item_id)
    k = _clean(data)
    k["item_id"] = it["id"]
    lid = data.get("listId")
    task = None
    if lid not in (None, "", 0):
        if request is None or not str(lid).isdigit():
            raise Invalid("listId: the id of one of your lists in ioTask")
        task = ask(request, "/api/tasks", {"list": str(lid)}, _task_body(k, it["name"]))
    kid = db.ex("INSERT INTO hom_upkeep (item_id, title, every_n, every_unit, next_due, notes, task_id, task_list, task_by, created_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (it["id"], k["title"], k["every_n"], k["every_unit"], k["next_due"], k.get("notes"),
                 str(task["id"]) if task else None, int(lid) if task else None, u.get("id") if task else None, u.get("id")))
    return _out(get(kid))


def _may_change(u: dict, k: dict) -> None:
    if not may_add(u):
        raise Forbidden("A viewer only looks")


def change(request: Request | None, u: dict, kid, data: dict) -> dict:
    """Change the fields given; the task in ioTask follows (when this account may change it there)."""
    k = get(kid)
    _may_change(u, k)
    f = _clean(data, partial=True)
    if f:
        db.ex(f"UPDATE hom_upkeep SET {', '.join(c + ' = %s' for c in f)} WHERE id = %s", [*f.values(), k["id"]])
    k = get(kid)
    if k["task_id"] and request is not None and f:
        try:
            ask(request, f"/api/tasks/{k['task_id']}", body=_task_body(k, _item(k["item_id"])["name"]), method="PATCH")
        except Unavailable as e:
            log.info("upkeep %s: the task in ioTask was not changed: %s", k["id"], e)
    return _out(k)


def remove(request: Request | None, u: dict, kid, keep_task: bool = False) -> None:
    k = get(kid)
    _may_change(u, k)
    if k["task_id"] and request is not None and not keep_task:
        try:
            ask(request, f"/api/tasks/{k['task_id']}", method="DELETE")
        except Unavailable as e:
            log.info("upkeep %s: the task in ioTask stays: %s", k["id"], e)
    db.ex("DELETE FROM hom_upkeep WHERE id = %s", (k["id"],))


def drop_tasks(request: Request | None, item_id: int) -> None:
    """The thing is going: its upkeep's tasks in ioTask go too, where the viewer may delete them (best effort)."""
    if request is None or not tasks_enabled():
        return
    for k in db.q("SELECT id, task_id FROM hom_upkeep WHERE item_id = %s AND task_id IS NOT NULL", (item_id,)):
        try:
            ask(request, f"/api/tasks/{k['task_id']}", method="DELETE")
        except Unavailable as e:
            log.info("upkeep %s: the task in ioTask stays: %s", k["id"], e)


def done(request: Request | None, u: dict, kid, data: dict) -> dict:
    """{date?, notes?, cost?, doneBy?}: the upkeep was done (on that day; today when left out). A line in the log,
    the upkeep moves on to the next day after that, and the task in ioTask is ticked off (it moves on there too)."""
    k = get(kid)
    if not may_add(u):
        raise Forbidden("A viewer only looks")
    on = day(data.get("date"), "The day it was done") or dt.date.today()
    nxt = step(on, k["every_n"], k["every_unit"])  # early or late, the next one counts from the day it was done
    entry = log_add(u, k["item_id"], {"date": on.isoformat(), "title": k["title"], "notes": data.get("notes"),
                                      "cost": data.get("cost"), "doneBy": data.get("doneBy")}, upkeep_id=k["id"])
    db.ex("UPDATE hom_upkeep SET next_due = %s WHERE id = %s", (nxt, k["id"]))
    k = get(kid)
    if k["task_id"] and request is not None:
        try:
            ask(request, f"/api/tasks/{k['task_id']}", body={"due": nxt.isoformat()}, method="PATCH")
        except Unavailable as e:
            log.info("upkeep %s: the task in ioTask was not moved on: %s", k["id"], e)
    return {"upkeep": _out(k), "logged": entry}


# ------------------------------------------------------------------ the maintenance log

def _log_out(r: dict) -> dict:
    return {"id": r["id"], "itemId": r["item_id"], "upkeepId": r["upkeep_id"], "date": r["done_on"].isoformat(), "title": r["title"],
            "notes": r["notes"], "cost": float(r["cost"]) if r["cost"] is not None else None, "doneBy": r["done_by"]}


def log_of(item_id: int) -> list[dict]:
    return [_log_out(r) for r in db.q("SELECT * FROM hom_maintenance WHERE item_id = %s ORDER BY done_on DESC, id DESC", (item_id,))]


def log_add(u: dict, item_id: int, data: dict, upkeep_id: int | None = None) -> dict:
    """{date?, title, notes?, cost?, doneBy?}: a line in the thing's maintenance log."""
    need_add(u)
    it = _item(item_id)
    title = text(data.get("title"), 255, "What was done")
    if not title:
        raise Invalid("What was done, please")
    mid = db.ex("INSERT INTO hom_maintenance (item_id, upkeep_id, done_on, title, notes, cost, done_by, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (it["id"], upkeep_id, day(data.get("date"), "The day") or dt.date.today(), title,
                 text(data.get("notes"), 4000, "The notes", True), money(data.get("cost"), "The cost"),
                 text(data.get("doneBy"), 255, "Who did it"), u.get("id")))
    return _log_out(db.one("SELECT * FROM hom_maintenance WHERE id = %s", (mid,)))


def _entry(mid) -> dict:
    r = db.one("SELECT * FROM hom_maintenance WHERE id = %s", (int(mid),)) if str(mid).isdigit() else None
    if not r:
        raise NotFound("No such line in the log")
    return r


def log_change(u: dict, mid, data: dict) -> dict:
    r = _entry(mid)
    if r["created_by"] != u.get("id"):
        need_write(u, _item(r["item_id"]))
    sets = {}
    if "date" in data:
        sets["done_on"] = day(data.get("date"), "The day") or r["done_on"]
    if "title" in data:
        sets["title"] = text(data.get("title"), 255, "What was done") or r["title"]
    if "notes" in data:
        sets["notes"] = text(data.get("notes"), 4000, "The notes", True)
    if "cost" in data:
        sets["cost"] = money(data.get("cost"), "The cost")
    if "doneBy" in data:
        sets["done_by"] = text(data.get("doneBy"), 255, "Who did it")
    if sets:
        db.ex(f"UPDATE hom_maintenance SET {', '.join(c + ' = %s' for c in sets)} WHERE id = %s", [*sets.values(), r["id"]])
    return _log_out(_entry(mid))


def log_remove(u: dict, mid) -> None:
    r = _entry(mid)
    if r["created_by"] != u.get("id"):
        need_write(u, _item(r["item_id"]))
    db.ex("DELETE FROM hom_maintenance WHERE id = %s", (r["id"],))
