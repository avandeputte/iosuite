"""The REST API (JSON; iCalendar by content negotiation) and the settings the web app uses. OpenAPI docs at /api/docs.
Who may call a route is declared on it (app/access.py); what an account may change is a list's business
(app/model.py), checked in the route.

Clients authenticate with the web session cookie, HTTP Basic (name + password or app password) or
`Authorization: Bearer <app password>`. Tasks are JSON by default; ask for text/calendar with Accept or ?format=ics,
and send either (or JSON) to create or change one.
"""
import datetime as dt
import json
import re
from urllib.parse import urlsplit

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

from app import access, config, ical, members, model, quick, users
from iosuite_shared import appleprofile, users as shared_users
from iosuite_shared.access import json_body

router = APIRouter()

ICS_TYPE = "text/calendar"


# ------------------------------------------------------------------ helpers

def readable_list(u: dict, lid) -> dict:
    c = model.task_list(int(lid)) if str(lid).isdigit() else None
    if not model.can_read(u, c):
        raise HTTPException(404, "No such list")
    return c


def writable_list(u: dict, lid) -> dict:
    c = readable_list(u, lid)
    if not model.can_write(u, c):
        raise HTTPException(403, "You can see this list but not change it")
    return c


def readable_task(u: dict, tid: int) -> tuple[dict, dict]:
    r = model.get_row(tid)
    c = model.task_list(r["list_id"]) if r else None
    if not r or r["deleted"] or not model.can_read(u, c):
        raise HTTPException(404, "No such task")
    return r, c


def writable_task(u: dict, tid: int) -> tuple[dict, dict]:
    r, c = readable_task(u, tid)
    if not model.can_write(u, c):
        raise HTTPException(403, "You can see this task but not change it")
    return r, c


def visible(u: dict, ids: str | None = None) -> list[dict]:
    lists = model.lists_for(u)
    if ids:
        want = {int(x) for x in re.split(r"[,\s]+", ids) if x.strip().isdigit()}
        lists = [c for c in lists if c["id"] in want]
    return lists


def member_filter(member: str | None) -> set[int] | None:
    """?member= (ids or names, comma-separated) as member ids; None when not asked."""
    if not member or not member.strip():
        return None
    return {m["id"] for m in members.resolve(member)}


def wants_ics(request: Request, fmt: str | None) -> bool:
    if fmt:
        return fmt.lower() in ("ics", "ical", "icalendar")
    return ICS_TYPE in request.headers.get("accept", "")


def base_url(request: Request) -> str:
    """The address links are made with: PUBLIC_URL, else what the proxy (or the client) says, kept to a scheme and a
    host[:port] (a forged header only changes the links in that client's own answer, but it stays an address)."""
    if config.PUBLIC_URL:
        return config.PUBLIC_URL
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "").split(",")[0].strip().lower()
    proto = proto if proto in ("http", "https") else "http"
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc or "").split(",")[0].strip()
    if not re.fullmatch(r"[A-Za-z0-9.\-]+(:\d{1,5})?|\[[0-9A-Fa-f:.]+\](:\d{1,5})?", host):
        host = request.url.netloc if re.fullmatch(r"[A-Za-z0-9.\-:\[\]]+", request.url.netloc or "") else "localhost"
    return f"{proto}://{host}"


async def body_object(request: Request) -> tuple[dict | None, object | None]:
    """The request body as (JSON fields, None) or (None, a parsed iCalendar object)."""
    ct = request.headers.get("content-type", "").split(";")[0].strip().lower()
    raw = await request.body()
    if len(raw) > config.MAX_TASK_BYTES:
        raise HTTPException(413, "That task is too large")
    if ct in (ICS_TYPE, "application/ics") or raw.lstrip()[:15].upper() == b"BEGIN:VCALENDAR":
        cal = ical.parse(raw)
        if ical.kinds_of(cal) != {"VTODO"}:
            raise HTTPException(400, "Expected one task (a VTODO), nothing else")
        return None, cal
    try:
        data = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "Expected a task as JSON or iCalendar")
    if not isinstance(data, dict):
        raise HTTPException(400, "Expected a task object")
    return data, None


def task_response(request: Request, r: dict, fmt: str | None = None, status: int = 200, undo: str | None = None):
    """A task as JSON or iCalendar. undo: the step that made it so (POST /api/undo/<it> takes the step back)."""
    headers = {"ETag": f'"{r["etag"]}"'}
    if wants_ics(request, fmt):
        return Response(r["ics"], status_code=status, media_type="text/calendar; charset=utf-8", headers=headers)
    j = model.task_out(r, model.subtask_counts([r["list_id"]]))
    if undo:
        j["undo"] = undo
    return JSONResponse(j, status_code=status, headers=headers)


def _check_match(request: Request, r: dict) -> None:
    h = request.headers.get("if-match")
    if h and h.strip() != "*" and r["etag"] not in [t.strip().removeprefix("W/").strip('"') for t in h.split(",")]:
        raise HTTPException(412, "The task was changed meanwhile (If-Match does not match its ETag); load it again")


# ------------------------------------------------------------------ lists

def zone_name(tz: str | None) -> str | None:
    """?tz=Europe/Brussels: whose "today" is meant (the web app sends the browser's); else the server's time zone."""
    return tz if ical.valid_tz(tz) else None


@router.get("/api/lists", dependencies=[access.signed_in])
def list_lists(request: Request, tz: str | None = None):
    """The lists you see, each with its open tasks (count) and how many of them are overdue (tz: see /api/tasks)."""
    u = request.state.user
    return {"items": [model.list_public(c, u) for c in model.lists_for(u, zone_name(tz))]}


@router.post("/api/lists", dependencies=[access.signed_in])
async def add_list(request: Request):
    """{name, color?, description?, shared?}: shared lists are made by editors and admins."""
    u = request.state.user
    b = await json_body(request)
    shared = bool(b.get("shared"))
    if shared and not shared_users.can_write(u):
        raise HTTPException(403, "Only editors make shared lists")
    if not shared and not shared_users.is_member(u):
        raise HTTPException(403, "A viewer only looks; a member keeps lists of their own")
    if not (b.get("name") or "").strip():
        raise HTTPException(400, "A name, please")

    def make():
        lid = model.create_list(None if shared else u["id"], b["name"], b.get("description"), b.get("color"))
        c = model.task_list(lid)
        c["n"] = c["late"] = 0
        return c
    c = await run_in_threadpool(make)
    return JSONResponse({"list": model.list_public(c, u)}, status_code=201)


@router.post("/api/lists/order", dependencies=[access.signed_in])
async def order_lists(request: Request):
    """{ids: [list ids]}: the lists in this order (the ones you may change; shared lists stay ahead of private ones)."""
    u = request.state.user
    b = await json_body(request)
    ids = [int(i) for i in (b.get("ids") or []) if str(i).isdigit()]
    await run_in_threadpool(model.order_lists, u, ids)
    return {"items": [model.list_public(c, u) for c in await run_in_threadpool(model.lists_for, u)]}


@router.post("/api/lists/{lid}/order", dependencies=[access.signed_in])
async def order_tasks(lid: int, request: Request):
    """{ids: [task ids]}: these tasks of the list in this order (the tasks of one level: the list's own, or one task's
    subtasks). Kept as X-APPLE-SORT-ORDER, the order by hand of Apple Reminders; ask for it with /api/tasks?sort=manual."""
    u = request.state.user
    b = await json_body(request)
    ids = [int(i) for i in (b.get("ids") or []) if str(i).isdigit()]

    def run():
        writable_list(u, lid)
        return {"changed": model.reorder(lid, ids, u["id"])}
    return await run_in_threadpool(run)


@router.patch("/api/lists/{lid}", dependencies=[access.signed_in])
async def edit_list(lid: int, request: Request):
    """{name?, description?, color?, sort?}"""
    u = request.state.user
    b = await json_body(request)

    def edit():
        writable_list(u, lid)
        model.update_list(lid, **{k: b[k] for k in ("name", "description", "color", "sort") if k in b})
        return model.task_list(lid)
    return {"list": model.list_public(await run_in_threadpool(edit), u)}


@router.delete("/api/lists/{lid}", dependencies=[access.signed_in])
def del_list(lid: int, request: Request):
    """Delete a list and its tasks. Shared lists: admins only; the last shared list and your last private list stay."""
    u = request.state.user
    c = writable_list(u, lid)
    if model.is_shared(c) and not shared_users.is_admin(u):
        raise HTTPException(403, "Only an admin deletes a shared list")
    if model.is_shared(c) and len([x for x in model.lists_for(u) if x["owner_id"] is None]) <= 1:
        raise HTTPException(400, "The last shared list stays")
    if not model.is_shared(c) and members.in_family(u["id"]) and len([x for x in model.lists_for(u) if x["owner_id"] == u["id"]]) <= 1:
        raise HTTPException(400, "Your last private list stays")
    model.delete_list(lid)
    return {"ok": True}


@router.get("/api/lists/{lid}/export", dependencies=[access.signed_in])
def export_list(lid: int, request: Request):
    """The whole list as one .ics file (its tasks as VTODOs)."""
    c = readable_list(request.state.user, lid)
    name = re.sub(r"[^A-Za-z0-9 _-]", "", c["name"]).strip() or "tasks"
    return Response(model.export_text([c], c["name"]), media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}-{dt.date.today().isoformat()}.ics"'})


@router.post("/api/lists/{lid}/import", dependencies=[access.signed_in])
async def import_list(lid: int, request: Request, replace: bool = True):
    """An .ics file with to-dos (multipart field `file`, or a text/calendar body) into this list. Tasks whose UID the
    list has already are updated (replace=false: skipped); events in the file are left out."""
    u = request.state.user
    await run_in_threadpool(writable_list, u, lid)
    if request.headers.get("content-type", "").startswith("multipart/"):
        form = await request.form()
        f = form.get("file")
        if f is None or not hasattr(f, "read"):
            raise HTTPException(400, "No file")
        raw = await f.read()
    else:
        raw = await request.body()
    if len(raw) > config.MAX_IMPORT_BYTES:
        raise HTTPException(413, "That file is too large")
    return await run_in_threadpool(model.import_text, lid, raw.decode("utf-8", "replace"), u["id"], replace)


# ------------------------------------------------------------------ tasks

def _day(s: str | None, name: str) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        raise HTTPException(400, f"{name} is a date (YYYY-MM-DD)")


@router.get("/api/tasks", dependencies=[access.signed_in])
def list_tasks(request: Request, list: str | None = None, q: str = "", status: str = "open", due: str | None = None,
               member: str | None = None, limit: int = 500, format: str | None = None, tz: str | None = None,
               sort: str = "due", from_: str | None = Query(None, alias="from"), to: str | None = None):
    """Tasks from the lists named (ids, comma-separated) or all you see. status: open (default), done or all. due:
    today (due today or before), overdue, week, scheduled, none, or a date; from and to: due on these days or between
    them. q: words in the title or notes. member: only the tasks for these family members (ids or names). Open tasks
    come soonest due first (sort=manual: in the order they were put in by hand); done ones latest first. Each has
    `subtasks`: {open, total}. tz: the time zone "today" is in (the server's unless given). With Accept: text/calendar
    (or ?format=ics), one .ics with all of them."""
    u = request.state.user
    lists = visible(u, list)
    rows = model.find([c["id"] for c in lists], q, status, due, member_filter(member), max(1, min(limit, 5000)), zone_name(tz),
                      sort, _day(from_, "from"), _day(to, "to"))
    if wants_ics(request, format):
        return Response(ical.feed(model.objects(rows), "ioTask"), media_type="text/calendar; charset=utf-8")
    subs = model.subtask_counts([c["id"] for c in lists])
    return {"items": [model.task_out(r, subs) for r in rows]}


@router.get("/api/counts", dependencies=[access.signed_in])
def counts(request: Request, tz: str | None = None):
    """How many open tasks are due today (or before), overdue, scheduled and in all, over the lists you see."""
    u = request.state.user
    ids = [c["id"] for c in model.lists_for(u)]
    return {k: len(model.find(ids, "", "open", d, None, 100000, zone_name(tz))) for k, d in
            (("today", "today"), ("overdue", "overdue"), ("scheduled", "scheduled"), ("all", None))}


def _quick(u: dict, text: str, tz: str | None) -> dict:
    """A line of plain English as task fields (app/quick.py), read as of now in tz."""
    return quick.parse(str(text)[:1000], dt.datetime.now(ical.zone(tz)), [c for c in model.lists_for(u) if model.can_write(u, c)], members.family())


@router.get("/api/quick", dependencies=[access.signed_in])
def quick_preview(request: Request, text: str = "", tz: str | None = None):
    """What a line of plain English would become as a task ("Pay rent every month on the 1st 9am !high"): {title} and,
    when the line says so, due, rrule, repeatAfter, priority, listId (#name) and members (@name). Nothing is saved:
    POST /api/tasks with {text} adds it."""
    return _quick(request.state.user, text, zone_name(tz))


@router.post("/api/tasks", dependencies=[access.signed_in])
async def create_task(request: Request, list: str | None = None):
    """A new task in ?list= (or the listId field; else the first list you may change), from JSON fields (title, notes,
    due, start, priority, done, url, location, parent, rrule, repeatAfter, alarms, members, categories) or iCalendar (a
    VTODO). due: a date (2026-11-12) or a time (2026-11-12T17:00, in timezone or the server's). members: the family
    members it is for (ids or names), kept as CATEGORIES. parent: the UID (or id) of the task it is a subtask of.
    rrule repeats from the due date; repeatAfter (P2W: two weeks) that long after the day the task is ticked off. Or
    {text}: one line of plain English (see GET /api/quick), with the other fields as what it falls back on."""
    u = request.state.user
    data, cal = await body_object(request)

    def run():
        with model.step() as b:
            return _create_task(u, data, cal, list), b
    r, b = await run_in_threadpool(run)
    return task_response(request, r, None, 201, b)


def _resolve_parent(u: dict, data: dict, lid: int) -> dict:
    """parent given as a task id: its UID (a subtask lives in its parent's list)."""
    p = data.get("parent")
    if p not in (None, "") and str(p).isdigit():
        r, _ = readable_task(u, int(p))
        if r["list_id"] != lid:
            raise HTTPException(400, "A subtask lives in the same list as its parent")
        data = {**data, "parent": r["uid"]}
    return data


def _create_task(u: dict, data: dict | None, cal, lst: str | None) -> dict:
    if data and data.get("text"):  # smart quick add: what the line says wins over what came with it
        tz = zone_name(data.get("timezone"))
        said = _quick(u, data["text"], tz)
        if "listId" in said:
            lst = None
        data = {**{k: v for k, v in data.items() if k != "text"}, **said}
    lid = lst or (data or {}).get("listId")
    if not lid and data and str(data.get("parent") or "").isdigit():
        pr, _ = readable_task(u, int(data["parent"]))
        lid = pr["list_id"]
    if not lid:
        mine = [c for c in model.lists_for(u) if model.can_write(u, c)]
        if not mine:
            raise HTTPException(403, "You cannot add tasks anywhere")
        lid = mine[0]["id"]
    c = writable_list(u, lid)
    if cal is None:
        data = _resolve_parent(u, members.fold(data), c["id"])
        cal = ical.build(data)
    else:
        ical.finish(cal)
    uid = ical.index(cal)["uid"]
    if model.by_uid(c["id"], uid):
        raise HTTPException(409, "That list already has a task with this UID")
    return model.save(c["id"], cal, None, None, u["id"])


@router.get("/api/tasks/{tid}", dependencies=[access.signed_in])
def get_task(tid: int, request: Request, format: str | None = None):
    """One task (JSON, or iCalendar with Accept: text/calendar or ?format=ics), with its subtasks (JSON only)."""
    r, _ = readable_task(request.state.user, tid)
    if wants_ics(request, format):
        return task_response(request, r, format)
    subs = model.subtask_counts([r["list_id"]])
    j = model.task_out(r, subs)
    j["children"] = [model.task_out(x, subs) for x in model.subtasks_of(r)]
    return JSONResponse(j, headers={"ETag": f'"{r["etag"]}"'})


def change(u: dict, r: dict, c: dict, data: dict, partial: bool = True) -> dict:
    """Change a task from JSON fields. listId moves it (with its subtasks); done: true on a repeating task moves it on
    to its next occurrence. PermissionError when a list may not be changed."""
    if data.get("listId") not in (None, "") and int(data["listId"]) != r["list_id"]:
        target = model.task_list(int(data["listId"]))
        if not model.can_write(u, target):
            raise PermissionError("You cannot add tasks to that list")
        r = model.move(r["id"], target["id"], u["id"])
        c = target
    cal = ical.parse(r["ics"])
    if "members" in data:
        data = members.fold(data, ical.categories_of(ical.todo(cal)))
    data = _resolve_parent(u, data, c["id"])
    done = data.pop("done", None)
    data = {k: v for k, v in data.items() if k in ical.EDITABLE}
    if not partial:  # a full replacement: fields left out are cleared
        for k in ("notes", "due", "start", "priority", "url", "location", "categories", "parent", "rrule", "alarms"):
            data.setdefault(k, None)
    ical.edit(cal, data)
    moved = False
    if done is not None and bool(done) != ical.todo_json(cal)["done"]:
        moved = ical.complete(cal, bool(done), zone_name(data.get("timezone")))
    return model.save(r["list_id"], ical.finish(cal), r["id"], None, u["id"], *_next(cal, moved))


def _next(cal, moved: bool) -> tuple:
    """What the activity log says of a repeating task that was ticked off and moved on: (action, detail)."""
    return ("done", f"next {(ical.todo_json(cal)['due'] or '')[:10]}") if moved else (None, None)


async def _change(request: Request, tid: int, partial: bool):
    u = request.state.user
    data, newcal = await body_object(request)

    def run():
        with model.step() as b:
            return _change_sync(request, u, tid, data, newcal, partial), b
    r2, b = await run_in_threadpool(run)
    return task_response(request, r2, undo=b)


def _change_sync(request: Request, u: dict, tid: int, data, newcal, partial: bool):
    r, c = writable_task(u, tid)
    _check_match(request, r)
    if newcal is not None:  # a whole new object for the task
        if ical.index(newcal)["uid"] != r["uid"]:
            raise HTTPException(400, "The UID of a task cannot change")
        return model.save(r["list_id"], ical.finish(newcal), r["id"], None, u["id"])
    try:
        return change(u, r, c, data, partial)
    except PermissionError as e:
        raise HTTPException(403, str(e))


@router.put("/api/tasks/{tid}", dependencies=[access.signed_in])
async def replace_task(tid: int, request: Request):
    """Replace a task: JSON fields (those left out are cleared) or iCalendar. If-Match with the ETag refuses a change
    made on an old copy."""
    return await _change(request, tid, False)


@router.patch("/api/tasks/{tid}", dependencies=[access.signed_in])
async def patch_task(tid: int, request: Request):
    """Change some fields of a task (the others stay). listId moves it; done ticks it off (a repeating task moves on to
    its next occurrence) or opens it again."""
    return await _change(request, tid, True)


@router.post("/api/tasks/{tid}/complete", dependencies=[access.signed_in])
async def complete_task(tid: int, request: Request):
    """{done: true} (the default) ticks a task off, {done: false} opens it again. A repeating task moves on to its next
    occurrence instead of being closed ({moved: true}); one that repeats after completion comes back that long after
    today (tz: whose today). {undo}: the step, for POST /api/undo."""
    u = request.state.user
    b = await json_body(request)

    def run():
        r, _ = writable_task(u, tid)
        cal = ical.parse(r["ics"])
        moved = ical.complete(cal, bool(b.get("done", True)), zone_name(b.get("tz")))
        with model.step() as step:
            r2 = model.save(r["list_id"], ical.finish(cal), r["id"], None, u["id"], *_next(cal, moved))
        return {**model.task_out(r2, model.subtask_counts([r2["list_id"]])), "moved": moved, "undo": step}
    return await run_in_threadpool(run)


@router.post("/api/tasks/postpone", dependencies=[access.signed_in])
async def postpone_tasks(request: Request):
    """{ids: [task ids], due: "2026-11-12"}: these tasks are due on that day instead, each at the time it had; their
    alerts move along. One step: {moved, undo}."""
    u = request.state.user
    b = await json_body(request)
    day = _day(str(b.get("due") or ""), "due")
    if day is None:
        raise HTTPException(400, "due: the day to move them to (YYYY-MM-DD)")
    ids = [int(i) for i in (b.get("ids") or []) if str(i).isdigit()][:2000]

    def run():
        n = 0
        with model.step() as step:
            for tid in ids:
                r, _ = writable_task(u, tid)
                cal = ical.parse(r["ics"])
                ical.postpone(cal, day, zone_name(b.get("tz")))
                model.save(r["list_id"], ical.finish(cal), r["id"], None, u["id"], "changed", "postponed")
                n += 1
        return {"moved": n, "undo": step}
    return await run_in_threadpool(run)


@router.delete("/api/tasks/{tid}", dependencies=[access.signed_in])
def delete_task(tid: int, request: Request):
    """Delete a task and its subtasks ({undo}: the step, for POST /api/undo)."""
    u = request.state.user
    r, _ = writable_task(u, tid)
    _check_match(request, r)
    with model.step() as step:
        return {"ok": True, "deleted": model.delete_with_subtasks(r["id"], u["id"]), "undo": step}


@router.post("/api/lists/{lid}/clear-completed", dependencies=[access.signed_in])
def clear_completed(lid: int, request: Request):
    """Delete the done tasks of a list ({undo}: the step, for POST /api/undo)."""
    u = request.state.user
    writable_list(u, lid)
    rows = model.find([lid], status="done", limit=100000)
    with model.step() as step:
        for r in rows:
            model.delete(r["id"], u["id"])
    return {"deleted": len(rows), "undo": step if rows else None}


# ------------------------------------------------------------------ activity and undo

@router.get("/api/activity", dependencies=[access.signed_in])
def activity(request: Request, list: str | None = None, limit: int = 100, before: int | None = None):
    """Who did what, newest first, in the lists named (ids, comma-separated) or all you see: [{id, batch, at (UTC),
    action (added, changed, done, reopened, moved, deleted), title, taskId, listId, user, via (web, caldav: a reminders
    app, mcp: an assistant), detail, count (the tasks of the step), undone, canUndo}]. before: the id to continue from.
    Kept for KEEP_DELETED_DAYS days."""
    u = request.state.user
    lists = visible(u, list)
    return {"items": model.activity([c["id"] for c in lists], {c["id"] for c in lists if model.can_write(u, c)}, max(1, min(limit, 500)), before)}


@router.post("/api/undo/{batch}", dependencies=[access.signed_in])
def undo(batch: str, request: Request):
    """Take a step back (the `undo` of a change, or the `batch` of an activity entry): what it added goes, what it
    changed or deleted is as it was. 400 when a task was changed again since. {undone, undo}: undo again to redo."""
    try:
        return model.undo(batch, request.state.user)
    except PermissionError as e:
        raise HTTPException(403, str(e))


# ------------------------------------------------------------------ templates

def _template(u: dict, tid: int, write: bool = False) -> dict:
    t = model.template(u, tid)
    if write and not model.template_public(t, u)["writable"]:
        raise HTTPException(403, "Editors and admins change shared templates; members their own")
    return t


@router.get("/api/templates", dependencies=[access.signed_in])
def templates(request: Request):
    """The templates you see (the shared ones and your own): [{id, name, shared, count, writable}]."""
    u = request.state.user
    return {"items": [model.template_public(t, u) for t in model.templates_for(u)]}


@router.get("/api/templates/{tid}", dependencies=[access.signed_in])
def get_template(tid: int, request: Request):
    """One template with its items: [{title, notes?, priority?, url?, categories?, children?}]."""
    u = request.state.user
    return model.template_public(_template(u, tid), u, items=True)


@router.post("/api/templates", dependencies=[access.signed_in])
async def add_template(request: Request):
    """{name, listId, shared?}: the tasks of a list as a template (titles, notes, priorities, links, who they are for
    and subtasks; not the due dates), or {name, items, shared?}. Shared templates are made by editors and admins."""
    u = request.state.user
    b = await json_body(request)
    shared = bool(b.get("shared"))
    if shared and not shared_users.can_write(u):
        raise HTTPException(403, "Only editors make shared templates")
    if not shared_users.is_member(u):
        raise HTTPException(403, "A viewer can only look; ask an admin to make you a member to keep your own")
    if not (b.get("name") or "").strip():
        raise HTTPException(400, "A name, please")

    def make():
        items = b.get("items") if isinstance(b.get("items"), list) else model.template_items(readable_list(u, b.get("listId"))["id"])
        return model.template(u, model.create_template(None if shared else u["id"], b["name"], items, u["id"]))
    return JSONResponse({"template": model.template_public(await run_in_threadpool(make), u)}, status_code=201)


@router.patch("/api/templates/{tid}", dependencies=[access.signed_in])
async def edit_template(tid: int, request: Request):
    """{name}"""
    u = request.state.user
    b = await json_body(request)

    def edit():
        _template(u, tid, True)
        if (b.get("name") or "").strip():
            model.db.ex("UPDATE tsk_templates SET name = %s WHERE id = %s", (b["name"].strip()[:128], tid))
        return model.template(u, tid)
    return {"template": model.template_public(await run_in_threadpool(edit), u)}


@router.delete("/api/templates/{tid}", dependencies=[access.signed_in])
def del_template(tid: int, request: Request):
    _template(request.state.user, tid, True)
    model.db.ex("DELETE FROM tsk_templates WHERE id = %s", (tid,))
    return {"ok": True}


@router.post("/api/templates/{tid}/apply", dependencies=[access.signed_in])
async def apply_template(tid: int, request: Request):
    """{listId, due?}: add the template's tasks to a list (due: a day they are all due on). {created, undo}."""
    u = request.state.user
    b = await json_body(request)
    due = _day(str(b.get("due") or "") or None, "due")

    def run():
        t = _template(u, tid)
        c = writable_list(u, b.get("listId"))
        with model.step() as step:
            return {"created": model.apply_template(t, c["id"], u["id"], due.isoformat() if due else None), "undo": step}
    return await run_in_threadpool(run)


# ------------------------------------------------------------------ family members

@router.get("/api/members", dependencies=[access.signed_in])
def family_members(request: Request):
    """The family members a task can be for (the accounts that use ioTask, less the ones taken out of the family):
    [{id, name, displayName}]. Filter with ?member= on /api/tasks. Admins also get leftOut."""
    u = request.state.user
    out = {"items": members.public(members.family())}
    if shared_users.is_admin(u):
        out["leftOut"] = sorted(members.left_out())
    return out


@router.put("/api/members/{uid}", dependencies=[access.admin])
async def set_family_member(uid: int, request: Request):
    """Admins: {inFamily: bool}. An account out of the family (an admin or service account, not a person) is not
    offered as a member and gets no private list here."""
    b = await json_body(request)

    def set_():
        if not users.get(uid):
            raise HTTPException(404, "No such account")
        members.set_in_family(uid, bool(b.get("inFamily", True)))
        return {"id": uid, "inFamily": members.in_family(uid), "items": members.public(members.family())}
    return await run_in_threadpool(set_)


# ------------------------------------------------------------------ connection details, Apple profile

@router.get("/api/connect", dependencies=[access.signed_in])
def connect_info(request: Request):
    """What to type into a reminders app: CalDAV, each list's address, the API and MCP."""
    u = request.state.user
    base = base_url(request)
    return {"user": u["name"], "server": base, "caldav": f"{base}/dav/", "principal": f"{base}/dav/principals/{u['name']}/",
            "lists": [{"id": c["id"], "name": c["name"], "caldav": f"{base}/dav/calendars/{u['name']}/{c['slug']}/"} for c in model.lists_for(u)],
            "api": f"{base}/api/docs", "mcp": f"{base}/mcp"}


def _apple_profile(request: Request, label: str, password: str) -> tuple:
    """A configuration profile (.mobileconfig) that adds the account to Reminders on an iPhone, iPad or Mac in one go:
    (bytes, file name). password: "new" puts a new app password (named after label) in it; "ask" leaves it out. The
    profile for all the apps that sync is iosuite-shared's (auth.profile_router in main.py)."""
    u = request.state.user
    if u.get("passwordless"):
        raise HTTPException(403, "A one-click account cannot have app passwords")
    base = base_url(request)
    host = urlsplit(base).hostname or "localhost"
    secret = appleprofile.new_password(u, config.APP, label) if password == "new" else None
    who = u.get("displayName") or u["name"]
    body = appleprofile.build(appleprofile.ident(config.APP, base, u), f"ioTask for {who}",
                              f"Adds {who}'s ioTask lists from {host} to Reminders." + appleprofile.asks(secret), "ioTask",
                              [appleprofile.account(config.APP, "ioTask", base, u, secret)])
    return body, appleprofile.file_name(config.APP, u)


@router.post("/api/apple-profile", dependencies=[access.signed_in])
def apple_profile(request: Request, label: str = Form("iPhone"), password: str = Form("new")):
    """The profile itself, as the answer to a form post (a browser tab that downloads in place: Safari, a Mac)."""
    return appleprofile.response(*_apple_profile(request, label, password))


@router.post("/api/apple-profile/link", dependencies=[access.signed_in])
async def apple_profile_link(request: Request):
    """{label, password} -> {url}: the profile behind a short-lived download link (/profile/<token>) that needs no
    cookie. The app on the Home Screen hands a download to a separate browser sheet that has none of its cookies; a
    link it can open by itself works. The link gives the same profile, with one app password, for a few minutes."""
    b = await json_body(request)
    return appleprofile.link(*await run_in_threadpool(_apple_profile, request, str(b.get("label") or ""), str(b.get("password") or "new")))
