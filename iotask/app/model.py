"""Lists and tasks in MariaDB: who may see and change which list, saving task objects (with the columns the app sorts
and filters on), finding tasks (open, due, overdue, done, by member, by words), import and export, and the sync tokens
CalDAV clients use.

Lists: the shared ones (owner_id NULL, Family first) that everyone sees, and each account's own private ones (Personal,
made the first time a member uses ioTask). Viewers only read the shared lists; members also keep their own private
lists; editors change the shared ones too; admins also manage settings and users.
"""
import contextlib
import contextvars
import datetime as dt
import json
import re
import secrets
import threading
from collections import OrderedDict

from app import config, db, ical, members, users
from iosuite_shared import users as shared_users
from iosuite_shared.errors import Invalid

PALETTE = ["#146b5e", "#1a73e8", "#e0426a", "#8e44d6", "#e8710a", "#0b8a9e", "#1e8e3e", "#4b53c7", "#e8a100", "#5f6b7a"]


class NotFound(Exception):
    pass


# ------------------------------------------------------------------ lists

def task_list(lid: int) -> dict | None:
    return db.one("SELECT * FROM tsk_lists WHERE id = %s", (lid,))


def is_shared(c: dict) -> bool:
    return c["owner_id"] is None


def can_read(u: dict | None, c: dict | None) -> bool:
    return bool(u and c) and (c["owner_id"] is None or c["owner_id"] == u["id"])


def can_write(u: dict | None, c: dict | None) -> bool:
    """A shared list: editors and admins. One's own private list: members and more (a viewer only looks)."""
    if not can_read(u, c):
        return False
    if c["owner_id"] is None:
        return shared_users.can_write(u)
    return shared_users.is_member(u)


def ensure_personal(u: dict) -> None:
    """Every member gets their private Personal list the first time they use ioTask (accounts are made in any app of the
    suite, so not necessarily here). A viewer keeps nothing of their own."""
    if not u or not u.get("id") or not members.in_family(u["id"]):  # not in the suite's family (Settings › Security › Family): no list of its own
        return
    if not shared_users.is_member(u):
        return
    if not db.one("SELECT id FROM tsk_lists WHERE owner_id = %s LIMIT 1", (u["id"],)):
        who = u.get("displayName") or u.get("display_name") or u.get("name")
        create_list(u["id"], "Personal", f"{who}'s private list", "#1a73e8")


def lists_for(u: dict | None, tzname: str | None = None) -> list[dict]:
    """The lists this account sees: the shared ones first (Family, then by position and name), then its own, each with
    how many open tasks it has (n) and how many of them are overdue (late)."""
    if not u:
        return []
    ensure_personal(u)
    # a timed task is late once its time passed; an all-day one once its day did (in tzname, else the server's zone)
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    today = dt.datetime.combine(dt.datetime.now(ical.zone(tzname)).date(), dt.time())
    return db.q("SELECT c.*, (SELECT count(*) FROM tsk_tasks t WHERE t.list_id = c.id AND t.deleted = 0 AND t.done = 0) AS n, "
                "(SELECT count(*) FROM tsk_tasks t WHERE t.list_id = c.id AND t.deleted = 0 AND t.done = 0 "
                "AND ((t.due_all_day = 0 AND t.due < %s) OR (t.due_all_day = 1 AND t.due < %s))) AS late "
                "FROM tsk_lists c WHERE c.owner_id IS NULL OR c.owner_id = %s "
                "ORDER BY c.owner_id IS NOT NULL, c.position, c.slug <> 'family', c.slug <> 'personal', lower(c.name)",
                (now, today, u["id"]))


def list_public(c: dict, u: dict) -> dict:
    return {"id": c["id"], "name": c["name"], "slug": c["slug"], "description": c.get("description"), "color": c.get("color") or PALETTE[0],
            "shared": c["owner_id"] is None, "writable": can_write(u, c), "count": c.get("n"), "overdue": c.get("late"),
            "mine": c["owner_id"] == (u or {}).get("id")}


def by_slug(u: dict, slug: str) -> dict | None:
    for c in lists_for(u):
        if c["slug"] == slug:
            return c
    return None


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:48]
    return s or "list"


def _color(c: str | None) -> str | None:
    c = (c or "").strip()
    m = re.fullmatch(r"#([0-9a-fA-F]{6})([0-9a-fA-F]{2})?", c)
    return f"#{m.group(1).lower()}" if m else None


def create_list(owner_id: int | None, name: str, description: str | None = None, color: str | None = None, slug: str | None = None) -> int:
    name = (name or "").strip()[:128] or "List"
    base = (slug or _slug(name))[:56]
    taken = {r["slug"] for r in db.q("SELECT slug FROM tsk_lists WHERE " + ("owner_id IS NULL" if owner_id is None else "owner_id = %s"),
                                     () if owner_id is None else (owner_id,))}
    # a private list's address must not hide a shared one's (CalDAV lists both under the same home)
    taken |= {r["slug"] for r in db.q("SELECT slug FROM tsk_lists WHERE owner_id IS NULL")}
    s, i = base, 2
    while s in taken:
        s, i = f"{base}-{i}", i + 1
    if not _color(color):
        n = db.one("SELECT count(*) AS n FROM tsk_lists")["n"]
        color = PALETTE[n % len(PALETTE)]
    last = db.one("SELECT COALESCE(MAX(position), 0) AS p FROM tsk_lists WHERE " + ("owner_id IS NULL" if owner_id is None else "owner_id = %s"),
                  () if owner_id is None else (owner_id,))["p"]  # a new list comes last among its kind
    return db.ex("INSERT INTO tsk_lists (owner_id, slug, name, description, color, position) VALUES (%s, %s, %s, %s, %s, %s)",
                 (owner_id, s, name, (description or "").strip()[:512] or None, _color(color), last + 1))


def order_lists(u: dict, ids: list[int]) -> None:
    """The lists in this order (those of ids this account may change; the shared ones stay ahead of the private)."""
    with db.tx():
        n = 0
        for lid in ids:
            c = task_list(int(lid))
            if can_write(u, c):
                n += 1
                update_list(c["id"], sort=n)


def update_list(lid: int, **f) -> None:
    sets, args = [], []
    if f.get("name") is not None and str(f["name"]).strip():
        sets.append("name = %s"); args.append(str(f["name"]).strip()[:128])
    if "description" in f:
        sets.append("description = %s"); args.append((f["description"] or "").strip()[:512] or None)
    if f.get("color") is not None and _color(f["color"]):
        sets.append("color = %s"); args.append(_color(f["color"]))
    if f.get("sort") is not None:
        sets.append("position = %s"); args.append(int(f["sort"]))
    if sets:
        db.ex(f"UPDATE tsk_lists SET {', '.join(sets)}, sync_token = sync_token + 1 WHERE id = %s", (*args, lid))


def delete_list(lid: int) -> None:
    with db.tx():
        db.ex("DELETE FROM tsk_lists WHERE id = %s", (lid,))
        db.set_setting(f"{PURGED}{lid}", None)
    _cache_clear()


def bump(lid: int) -> int:
    """The list's next sync token (every change gets one; CalDAV's sync-collection and getctag follow it)."""
    with db.tx() as con, con.cursor() as cur:
        cur.execute("UPDATE tsk_lists SET sync_token = sync_token + 1 WHERE id = %s", (lid,))
        cur.execute("SELECT sync_token FROM tsk_lists WHERE id = %s", (lid,))
        return cur.fetchone()["sync_token"]


# ------------------------------------------------------------------ task objects

_cache: "OrderedDict[str, object]" = OrderedDict()
_cache_lock = threading.Lock()


def _cache_clear():
    with _cache_lock:
        _cache.clear()


def parsed(row: dict):
    """The row's iCalendar object, parsed (kept by etag: the same object is read again and again)."""
    key = f"{row['id']}:{row['etag']}"
    with _cache_lock:
        c = _cache.get(key)
        if c is not None:
            _cache.move_to_end(key)
            return c
    c = ical.parse(row["ics"])
    with _cache_lock:
        _cache[key] = c
        while len(_cache) > 3000:
            _cache.popitem(last=False)
    return c


def get_row(tid: int) -> dict | None:
    return db.one("SELECT * FROM tsk_tasks WHERE id = %s", (tid,))


def by_href(lid: int, href: str) -> dict | None:
    return db.one("SELECT * FROM tsk_tasks WHERE list_id = %s AND href = %s", (lid, href))


def by_uid(lid: int, uid: str) -> dict | None:
    return db.one("SELECT * FROM tsk_tasks WHERE list_id = %s AND uid = %s AND deleted = 0", (lid, uid))


def href_for(uid: str) -> str:
    s = re.sub(r"[^A-Za-z0-9@._-]", "-", uid)[:200]
    return f"{s}.ics"


# ------------------------------------------------------------------ the activity log

_via = contextvars.ContextVar("iotask_via", default="web")
_batch = contextvars.ContextVar("iotask_batch", default=None)


@contextlib.contextmanager
def step(via: str | None = None):
    """One step in the activity log: everything saved and deleted inside shares a batch id (yielded) and is undone
    together. via: what made the change (web: the web app and the API; caldav: a reminders app; mcp: an assistant)."""
    tv = _via.set(via) if via else None
    b, tb = _batch.get(), None
    if b is None:
        b = secrets.token_hex(8)
        tb = _batch.set(b)
    try:
        yield b
    finally:
        if tb is not None:
            _batch.reset(tb)
        if tv is not None:
            _via.reset(tv)


CHANGES = (("summary", "title"), ("due", "due"), ("due_all_day", "due"), ("priority", "priority"), ("description", "notes"),
           ("rrule", "repeat"), ("parent_uid", "subtask"), ("status", "status"))


def _log(lid: int, action: str, uid: str, title: str, task_id: int | None, user_id: int | None, before: str | None,
         etag_after: str | None, detail: str | None = None) -> None:
    db.ex("INSERT INTO tsk_activity (list_id, task_id, uid, title, user_id, action, via, detail, before_ics, etag_after, batch, at) "
          "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, UTC_TIMESTAMP(3))",
          (lid, task_id, uid[:255], (title or "")[:512], user_id, action, _via.get(), (detail or "")[:255] or None, before, etag_after,
           _batch.get() or secrets.token_hex(8)))


def save(lid: int, cal, task_id: int | None = None, href: str | None = None, user_id: int | None = None,
         action: str | None = None, detail: str | None = None, log: bool = True) -> dict:
    """Store a task object in a list: a new task, or the one with task_id (or the deletion marker at href). The
    activity log gets what happened (action and detail say it when the caller knows better; log=False: nothing)."""
    ix = ical.index(cal)
    ics = ical.text(cal)
    etag = ical.etag_of(ics)
    with db.tx():  # the sync token, the row and the log change together: a failure leaves none of them
        tok = bump(lid)
        cols = dict(ix, ics=ics, etag=etag, changed_token=tok, deleted=0)
        cols["uid"] = cols["uid"][:255]
        if task_id is None:
            if not href:
                href = href_for(ix["uid"])
                old = by_href(lid, href)
                if old and not old["deleted"]:  # an app reusing a name: a new one
                    href, old = href_for(ical.new_uid()), None
            else:
                old = by_href(lid, href)
            task_id = old["id"] if old else None
        else:
            old = get_row(task_id)
        if task_id:
            db.ex(f"UPDATE tsk_tasks SET {', '.join(f'{k} = %s' for k in cols)}, list_id = %s WHERE id = %s", (*cols.values(), lid, task_id))
        else:
            task_id = db.ex(f"INSERT INTO tsk_tasks ({', '.join(cols)}, list_id, href, created_by) VALUES "
                            f"({', '.join(['%s'] * len(cols))}, %s, %s, %s)", (*cols.values(), lid, href, user_id))
        was = old if old and not old["deleted"] and old["list_id"] == lid else None
        if log and not (was and was["etag"] == etag):
            if was:
                what = list(dict.fromkeys(label for col, label in CHANGES if was[col] != cols[col]))
                if not action:
                    action = "done" if cols["done"] and not was["done"] else "reopened" if was["done"] and not cols["done"] else "changed"
                    detail = detail or ", ".join(w for w in what if w != "status") or None
            _log(lid, action or "added", cols["uid"], cols["summary"], task_id, user_id, was["ics"] if was else None, etag, detail)
    return get_row(task_id)


def delete(tid: int, user_id: int | None = None, action: str = "deleted", detail: str | None = None) -> None:
    """A deletion marker: CalDAV clients learn of the deletion from the next sync. Kept for KEEP_DELETED_DAYS (purge_deleted)."""
    with db.tx():
        r = get_row(tid)
        if not r or r["deleted"]:
            return
        tok = bump(r["list_id"])
        db.ex("UPDATE tsk_tasks SET deleted = 1, ics = '', changed_token = %s WHERE id = %s", (tok, tid))
        _log(r["list_id"], action, r["uid"], r["summary"], tid, user_id, r["ics"], None, detail)


def delete_with_subtasks(tid: int, user_id: int | None = None) -> int:
    """A task and the subtasks under it (all levels, in the same list): how many went."""
    r = get_row(tid)
    if not r or r["deleted"]:
        return 0
    n, todo, seen = 0, [r], set()
    with step():
        while todo:
            x = todo.pop(0)
            if x["id"] in seen:
                continue
            seen.add(x["id"])
            todo += db.q("SELECT * FROM tsk_tasks WHERE list_id = %s AND parent_uid = %s AND deleted = 0", (x["list_id"], x["uid"]))
            delete(x["id"], user_id)
            n += 1
    return n


def _name_of(uid: int | None) -> str | None:
    u = users.get(uid) if uid else None
    return (u.get("displayName") or u.get("display_name") or u.get("name")) if u else None


def activity(lids: list[int], writable: set[int], limit: int = 100, before: int | None = None) -> list[dict]:
    """The latest steps in these lists, newest first: [{id, batch, at, action, title, taskId, listId, user, via,
    detail, count, undone, canUndo}]. A step with several tasks (count) shows its first. canUndo: every task of the
    step is still as the step left it, and this account may change its lists."""
    if not lids:
        return []
    marks = db.marks(len(lids))
    rows = db.q(f"SELECT a.id, a.batch, a.at, a.action, a.title, a.task_id, a.list_id, a.user_id, a.via, a.detail, g.n FROM tsk_activity a "
                f"JOIN (SELECT min(id) AS first, count(*) AS n FROM tsk_activity WHERE list_id IN ({marks}) GROUP BY batch) g ON g.first = a.id "
                f"{'WHERE a.id < %s ' if before else ''}ORDER BY a.id DESC LIMIT %s", (*lids, *([before] if before else []), int(limit)))
    if not rows:
        return []
    state = {r["batch"]: r for r in db.q(
        f"SELECT a.batch, max(a.undone) AS undone, GROUP_CONCAT(DISTINCT a.list_id) AS lists, "
        f"sum(a.id <> (SELECT max(x.id) FROM tsk_activity x WHERE x.list_id = a.list_id AND x.uid = a.uid)) AS stale "
        f"FROM tsk_activity a WHERE a.batch IN ({db.marks(len(rows))}) GROUP BY a.batch", [r["batch"] for r in rows])}
    out = []
    for r in rows:
        st = state[r["batch"]]
        out.append({"id": r["id"], "batch": r["batch"], "at": r["at"].replace(tzinfo=dt.timezone.utc).isoformat(timespec="seconds"),
                    "action": r["action"], "title": r["title"], "taskId": r["task_id"], "listId": r["list_id"],
                    "user": _name_of(r["user_id"]), "userId": r["user_id"], "via": r["via"], "detail": r["detail"], "count": int(r["n"]),
                    "undone": bool(st["undone"]),
                    "canUndo": not st["undone"] and not int(st["stale"] or 0) and all(int(x) in writable for x in str(st["lists"]).split(","))})
    return out


def undo(batch: str, u: dict) -> dict:
    """Take a step back: what it added goes, what it changed or deleted is as it was before. Refused when a task was
    changed again since (undoing would lose that change). The undoing is a step itself ({undo}: its batch), so it can
    be undone too."""
    steps = db.q("SELECT * FROM tsk_activity WHERE batch = %s ORDER BY id DESC", (batch,))
    if not steps or not all(can_read(u, task_list(a["list_id"])) for a in steps):
        raise NotFound("No such step")
    if not all(can_write(u, task_list(a["list_id"])) for a in steps):
        raise PermissionError("You can see this list but not change it")
    if any(a["undone"] for a in steps):
        raise Invalid("That was undone already")
    gone = Invalid("The task was changed again since, so this cannot be undone any more")
    with db.tx(), step() as b:
        for a in steps:
            cur = get_row(a["task_id"]) if a["task_id"] else None
            if cur and cur["list_id"] != a["list_id"]:
                cur = None
            there = bool(cur and not cur["deleted"])
            if a["before_ics"] is None:  # it was added: it goes
                if there:
                    if cur["etag"] != a["etag_after"]:
                        raise gone
                    delete(cur["id"], u["id"], "deleted", "undo")
            elif a["etag_after"] is None:  # it was deleted: it comes back
                if there or by_uid(a["list_id"], a["uid"]):
                    raise gone
                save(a["list_id"], ical.parse(a["before_ics"]), cur["id"] if cur else None, cur["href"] if cur else None, u["id"], "added", "undo")
            else:  # it was changed: as it was before
                if not there or cur["etag"] != a["etag_after"]:
                    raise gone
                save(a["list_id"], ical.parse(a["before_ics"]), cur["id"], None, u["id"], None, "undo")
        db.ex("UPDATE tsk_activity SET undone = 1 WHERE batch = %s", (batch,))
    _cache_clear()
    return {"undone": len(steps), "undo": b}


PURGED = "purged_token:"  # tsk_settings: per list, the newest change among the deletion markers that were purged


def purge_deleted(days: int | None = None) -> int:
    """Remove the deletion markers (and the activity log) older than `days` (KEEP_DELETED_DAYS); how many markers
    went. Each list remembers how far
    its purged markers reached, so a client that last synced before that is told to start over (purged_before)."""
    days = config.KEEP_DELETED_DAYS if days is None else days
    with db.tx():
        old = db.q("SELECT list_id AS lst, max(changed_token) AS tok FROM tsk_tasks WHERE deleted = 1 "
                   "AND updated_at < NOW() - INTERVAL %s DAY GROUP BY list_id", (days,))
        for r in old:
            db.set_setting(f"{PURGED}{r['lst']}", str(max(r["tok"], purged_before(r["lst"]))))
        db.ex("DELETE FROM tsk_activity WHERE at < UTC_TIMESTAMP() - INTERVAL %s DAY", (days,))  # the log is kept as long
        return db.ex("DELETE FROM tsk_tasks WHERE deleted = 1 AND updated_at < NOW() - INTERVAL %s DAY", (days,)) if old else 0


def purged_before(lid: int) -> int:
    """The sync token up to which this list's deletion markers are gone (0: none were purged)."""
    return int(db.get_setting(f"{PURGED}{lid}") or 0)


def move(tid: int, to_lid: int, user_id: int | None = None) -> dict:
    """To another list: a deletion in the old one and a new task in the new one (as CalDAV sees it), in one
    transaction. Its subtasks go along."""
    with db.tx():
        r = get_row(tid)
        if r["list_id"] == to_lid:
            return r
        if by_uid(to_lid, r["uid"]):
            raise Invalid("That list already has this task")
        kids = db.q("SELECT id FROM tsk_tasks WHERE list_id = %s AND parent_uid = %s AND deleted = 0", (r["list_id"], r["uid"]))
        cal = parsed(r)
        with step():
            delete(tid, user_id, "moved", f"to {task_list(to_lid)['name']}")
            new = save(to_lid, cal, None, None, r.get("created_by") if user_id is None else user_id, "added", f"from {task_list(r['list_id'])['name']}")
            for k in kids:
                move(k["id"], to_lid, user_id)
        return new


LISTED = ("id, list_id, uid, href, etag, summary, status, done, priority, due, due_all_day, start, completed_at, parent_uid, rrule, "
          "sort_order, changed_token, deleted, created_by, created_at, updated_at, LENGTH(ics) AS ics_bytes")


def rows(lid: int, since: int | None = None, listing: bool = False) -> list[dict]:
    """A list's tasks (since: what changed after that sync token, deletions included). listing: without the objects
    themselves (ics_bytes says how long each is), for the replies that name tasks and their etags only."""
    cols = LISTED if listing else "*"
    if since is None:
        return db.q(f"SELECT {cols} FROM tsk_tasks WHERE list_id = %s AND deleted = 0 ORDER BY id", (lid,))
    return db.q(f"SELECT {cols} FROM tsk_tasks WHERE list_id = %s AND changed_token > %s ORDER BY changed_token", (lid, since))


def objects(rows_: list[dict]) -> list:
    """The parsed objects of these rows, one that cannot be read left out."""
    out = []
    for r in rows_:
        try:
            out.append(parsed(r))
        except ValueError:
            continue
    return out


def _like(w: str) -> str:
    """A word as a LIKE pattern that matches it anywhere, with its own % and _ taken literally."""
    return "%" + re.sub(r"([\\%_])", r"\\\1", w) + "%"


def day_bounds(day: dt.date, tzname: str | None = None) -> tuple[dt.datetime, dt.datetime]:
    """A local day as naive UTC [start, end) for the due column, padded for all-day tasks (kept at UTC midnight)."""
    z = ical.zone(tzname)
    a = dt.datetime.combine(day, dt.time(), z).astimezone(dt.timezone.utc).replace(tzinfo=None)
    return a, a + dt.timedelta(days=1)


SORT = "t.done, t.due IS NULL, t.due, t.priority = 0, t.priority, t.sort_order IS NULL, t.sort_order, t.id"


MANUAL = "t.done, COALESCE(t.sort_order, TIMESTAMPDIFF(SECOND, '2001-01-01 00:00:00', t.created_at)), t.id"


def find(lids: list[int], q: str = "", status: str = "open", due: str | None = None, member_ids: set[int] | None = None,
         limit: int = 500, tzname: str | None = None, sort: str = "due", due_from: dt.date | None = None,
         due_to: dt.date | None = None) -> list[dict]:
    """Tasks in these lists. status: open (not done), done (completed or cancelled, the latest first) or all. due:
    today (due today or earlier: what is on today), overdue, week (the next seven days and earlier), scheduled (any
    due date), none (no due date) or a date YYYY-MM-DD. due_from, due_to: due on these days or between them. q: every
    word in the title or the notes. member_ids: only the tasks for one of these family members. sort: due (soonest
    first, then by priority) or manual (the order they were put in by hand: X-APPLE-SORT-ORDER)."""
    if not lids:
        return []
    where, args = [f"t.list_id IN ({db.marks(len(lids))})", "t.deleted = 0"], list(lids)
    if status == "open":
        where.append("t.done = 0")
    elif status == "done":
        where.append("t.done = 1")
    elif status != "all":
        raise Invalid("status is open, done or all")
    if due:
        today = dt.datetime.now(ical.zone(tzname)).date()
        if due == "overdue":
            now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
            # a timed task is late once its time passed; an all-day one once its day did
            where.append("((t.due_all_day = 0 AND t.due < %s) OR (t.due_all_day = 1 AND t.due < %s))")
            args += [now, dt.datetime.combine(today, dt.time())]
        elif due in ("today", "week"):
            end = day_bounds(today + dt.timedelta(days=0 if due == "today" else 6), tzname)[1]
            where.append("((t.due_all_day = 0 AND t.due < %s) OR (t.due_all_day = 1 AND t.due <= %s))")
            args += [end, dt.datetime.combine(today + dt.timedelta(days=0 if due == "today" else 6), dt.time())]
        elif due == "scheduled":
            where.append("t.due IS NOT NULL")
        elif due == "none":
            where.append("t.due IS NULL")
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", due):
            d = dt.date.fromisoformat(due)
            a, b = day_bounds(d, tzname)
            where.append("((t.due_all_day = 0 AND t.due >= %s AND t.due < %s) OR (t.due_all_day = 1 AND t.due = %s))")
            args += [a, b, dt.datetime.combine(d, dt.time())]
        else:
            raise Invalid("due is today, overdue, week, scheduled, none or a date (YYYY-MM-DD)")
    if due_from is not None:
        where.append("((t.due_all_day = 0 AND t.due >= %s) OR (t.due_all_day = 1 AND t.due >= %s))")
        args += [day_bounds(due_from, tzname)[0], dt.datetime.combine(due_from, dt.time())]
    if due_to is not None:
        where.append("((t.due_all_day = 0 AND t.due < %s) OR (t.due_all_day = 1 AND t.due <= %s))")
        args += [day_bounds(due_to, tzname)[1], dt.datetime.combine(due_to, dt.time())]
    if sort not in ("due", "manual"):
        raise Invalid("sort is due or manual")
    for w in (q or "").split()[:8]:
        like = _like(w)
        where.append("(t.summary LIKE %s OR t.description LIKE %s)")
        args += [like, like]
    if member_ids is not None:
        where.append("t.ics LIKE '%%CATEGORIES%%'")
    order = "t.completed_at IS NULL, t.completed_at DESC, t.updated_at DESC" if status == "done" else MANUAL if sort == "manual" else SORT
    out = db.q(f"SELECT t.* FROM tsk_tasks t WHERE {' AND '.join(where)} ORDER BY {order} LIMIT %s",
               (*args, int(limit) if member_ids is None else 100000))
    if member_ids is not None:
        out = [r for r in out if tagged(r, member_ids)][:limit]
    return out


def tagged(r: dict, member_ids: set[int] | None) -> bool:
    """Whether a task is for one of these members (None: any task)."""
    if member_ids is None:
        return True
    try:
        return bool(member_ids.intersection(members.ids_of(ical.categories_of(ical.todo(parsed(r))))))
    except Exception:  # noqa: BLE001
        return False


def subtask_counts(lids: list[int]) -> dict:
    """(list id, parent uid) -> [open, all] subtasks."""
    if not lids:
        return {}
    out = {}
    for r in db.q(f"SELECT list_id, parent_uid, sum(done = 0) AS open_, count(*) AS n FROM tsk_tasks WHERE list_id IN ({db.marks(len(lids))}) "
                  "AND deleted = 0 AND parent_uid IS NOT NULL GROUP BY list_id, parent_uid", lids):
        out[(r["list_id"], r["parent_uid"])] = [int(r["open_"] or 0), int(r["n"])]
    return out


def task_out(r: dict, subs: dict | None = None) -> dict:
    """A task as the REST API and the web app see it."""
    j = ical.todo_json(parsed(r))
    j.update(id=r["id"], listId=r["list_id"], href=r["href"], etag=r["etag"],
             members=members.public(members.of(j["categories"])),
             updated=r["updated_at"].isoformat() if r.get("updated_at") else None,
             created=r["created_at"].isoformat() if r.get("created_at") else None)
    if subs is not None:
        o, n = subs.get((r["list_id"], r["uid"]), [0, 0])
        j["subtasks"] = {"open": o, "total": n}
    return j


def subtasks_of(r: dict) -> list[dict]:
    """A task's subtasks, in the order they were put in (by hand, else as they were added)."""
    return db.q(f"SELECT t.* FROM tsk_tasks t WHERE t.list_id = %s AND t.parent_uid = %s AND t.deleted = 0 ORDER BY {MANUAL}", (r["list_id"], r["uid"]))


# ------------------------------------------------------------------ the order by hand

STEP = 1000


def _stays(vals: list) -> set[int]:
    """The places of a longest rising run in vals: the tasks that keep their number when the others move around them."""
    best, prev, tails = [], [-1] * len(vals), []
    for i, v in enumerate(vals):
        lo, hi = 0, len(tails)
        while lo < hi:
            mid = (lo + hi) // 2
            if vals[tails[mid]] < v:
                lo = mid + 1
            else:
                hi = mid
        prev[i] = tails[lo - 1] if lo else -1
        if lo == len(tails):
            tails.append(i)
        else:
            tails[lo] = i
    i = tails[-1] if tails else -1
    while i >= 0:
        best.append(i)
        i = prev[i]
    return set(best)


def reorder(lid: int, ids: list[int], user_id: int | None = None) -> int:
    """Put these tasks of a list in this order (the tasks of one level: the list's own, or one task's subtasks). The
    order is X-APPLE-SORT-ORDER, as Apple Reminders keeps it; only the tasks that moved get a new number (all of them
    when there is no room left between two). How many tasks were written."""
    ids = list(dict.fromkeys(int(i) for i in ids))
    if not ids:
        return 0
    found = {r["id"]: r for r in db.q(f"SELECT * FROM tsk_tasks WHERE list_id = %s AND deleted = 0 AND id IN ({db.marks(len(ids))})", (lid, *ids))}
    rows_ = [found[i] for i in ids if i in found]
    epoch = dt.datetime(2001, 1, 1)
    was = [r["sort_order"] if r["sort_order"] is not None else int((r["created_at"] - epoch).total_seconds()) for r in rows_]
    keep, new, n = _stays([(v, r["id"]) for v, r in zip(was, rows_)]), list(was), len(rows_)  # equal numbers: by id
    i = 0
    while i < n:
        if i in keep:
            i += 1
            continue
        j = i
        while j < n and j not in keep:
            j += 1
        lo, hi, k = (new[i - 1] if i else None), (was[j] if j < n else None), j - i
        if lo is not None and hi is not None and hi - lo <= k:  # no room between the two: number them all anew
            new = [min(was) + STEP * x for x in range(n)]
            break
        for x in range(k):
            new[i + x] = hi - STEP * (k - x) if lo is None else lo + STEP * (x + 1) if hi is None else lo + (hi - lo) * (x + 1) // (k + 1)
        i = j
    done = 0
    with db.tx():
        for r, a, b in zip(rows_, was, new):
            if a != b or r["sort_order"] is None:
                cal = ical.parse(r["ics"])
                ical.set_sort(cal, b)
                save(lid, ical.finish(cal), r["id"], None, user_id, log=False)
                done += 1
    return done


# ------------------------------------------------------------------ templates

MAX_TEMPLATE_ITEMS = 1000


def template_items(lid: int) -> list[dict]:
    """A list's tasks as a template: each task's title, notes, priority, link and who it is for, with its subtasks
    under it, in the order by hand. Due dates, repeats, alerts and what is ticked off stay behind."""
    rows_ = db.q(f"SELECT t.* FROM tsk_tasks t WHERE t.list_id = %s AND t.deleted = 0 ORDER BY {MANUAL.replace('t.done, ', '')}", (lid,))
    by_parent: dict = {}
    uids = {r["uid"] for r in rows_}
    for r in rows_:
        by_parent.setdefault(r["parent_uid"] if r["parent_uid"] in uids else None, []).append(r)

    def item(r: dict, depth: int) -> dict:
        j = ical.todo_json(parsed(r))
        it = {k: j[k] for k in ("title", "notes", "priority", "url", "categories") if j.get(k)}
        kids = [item(k, depth + 1) for k in by_parent.get(r["uid"], [])] if depth < 8 else []
        if kids:
            it["children"] = kids
        return it
    return [item(r, 0) for r in by_parent.get(None, [])]


def _count(items: list) -> int:
    return sum(1 + _count(i.get("children") or []) for i in items)


def templates_for(u: dict) -> list[dict]:
    """The templates this account sees: the shared ones and its own."""
    return db.q("SELECT * FROM tsk_templates WHERE owner_id IS NULL OR owner_id = %s ORDER BY owner_id IS NOT NULL, lower(name)", (u["id"],))


def template(u: dict, tid: int) -> dict:
    t = db.one("SELECT * FROM tsk_templates WHERE id = %s AND (owner_id IS NULL OR owner_id = %s)", (tid, u["id"]))
    if not t:
        raise NotFound("No such template")
    return t


def template_public(t: dict, u: dict, items: bool = False) -> dict:
    its = json.loads(t["items"])
    out = {"id": t["id"], "name": t["name"], "shared": t["owner_id"] is None, "count": _count(its),
           "writable": (t["owner_id"] == u["id"] and shared_users.is_member(u)) or (t["owner_id"] is None and shared_users.can_write(u))}
    if items:
        out["items"] = its
    return out


def create_template(owner_id: int | None, name: str, items: list, user_id: int | None = None) -> int:
    if not items:
        raise Invalid("That list has no tasks to make a template of")
    if _count(items) > MAX_TEMPLATE_ITEMS:
        raise Invalid(f"A template holds {MAX_TEMPLATE_ITEMS} tasks at most")
    return db.ex("INSERT INTO tsk_templates (owner_id, name, items, created_by) VALUES (%s, %s, %s, %s)",
                 (owner_id, (name or "").strip()[:128] or "Template", json.dumps(items, ensure_ascii=False), user_id))


def apply_template(t: dict, lid: int, user_id: int | None = None, due: str | None = None) -> int:
    """Add a template's tasks to a list (one step in the activity log); due: a day they are all due on. How many."""
    n = 0

    def add(it: dict, parent: str | None) -> None:
        nonlocal n
        cal = ical.build({**{k: it[k] for k in ("title", "notes", "priority", "url", "categories") if it.get(k)},
                          **({"parent": parent} if parent else {}), **({"due": due} if due and not parent else {})})
        save(lid, cal, None, None, user_id, "added", f"template {t['name']}"[:255])
        n += 1
        for k in it.get("children") or []:
            add(k, ical.index(cal)["uid"])
    with db.tx(), step():
        for it in json.loads(t["items"]):
            add(it, None)
    return n


# ------------------------------------------------------------------ import and export

def import_text(lid: int, text: str, user_id: int | None = None, replace: bool = True) -> dict:
    """An .ics file (one task or a whole list) into a list: every UID becomes a task; a UID the list has already is
    updated (replace) or skipped. Events in the file are left out. {created, updated, skipped, errors}."""
    cal = ical.parse(text)
    out = {"created": 0, "updated": 0, "skipped": 0, "errors": []}
    with step():
        for obj in ical.split_by_uid(cal):
            try:
                ix = ical.index(obj)
            except ValueError as e:
                out["errors"].append(str(e))
                continue
            old = by_uid(lid, ix["uid"])
            if old and not replace:
                out["skipped"] += 1
                continue
            save(lid, ical.finish(obj), old["id"] if old else None, None, user_id, None, "import")
            out["updated" if old else "created"] += 1
    return out


def export_text(lists: list[dict], name: str) -> str:
    objs = []
    for c in lists:
        objs += objects(rows(c["id"]))
    return ical.feed(objs, name, color=lists[0].get("color") if len(lists) == 1 else None)
