"""Lists and tasks in MariaDB: who may see and change which list, saving task objects (with the columns the app sorts
and filters on), finding tasks (open, due, overdue, done, by member, by words), import and export, and the sync tokens
CalDAV clients use.

Lists: the shared ones (owner_id NULL, Family first) that everyone sees, and each account's own private ones (Personal,
made the first time the account uses ioTasks). Viewers read the shared lists and change only their own; editors change
the shared ones too; admins also manage settings and users.
"""
import datetime as dt
import re
import threading
from collections import OrderedDict

from app import config, db, ical, members
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
    if not can_read(u, c):
        return False
    if c["owner_id"] is None:
        return u.get("role") in ("editor", "admin")
    return True


def ensure_personal(u: dict) -> None:
    """Every account gets its private Personal list the first time it uses ioTasks (accounts are made in any app of the
    suite, so not necessarily here)."""
    if not u or not u.get("id") or not members.in_family(u["id"]):  # not a person (Settings › Family): no list of its own
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
    return db.ex("INSERT INTO tsk_lists (owner_id, slug, name, description, color) VALUES (%s, %s, %s, %s, %s)",
                 (owner_id, s, name, (description or "").strip()[:512] or None, _color(color)))


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


def save(lid: int, cal, task_id: int | None = None, href: str | None = None, user_id: int | None = None) -> dict:
    """Store a task object in a list: a new task, or the one with task_id (or the deletion marker at href)."""
    ix = ical.index(cal)
    ics = ical.text(cal)
    etag = ical.etag_of(ics)
    with db.tx():  # the sync token and the row change together: a failure leaves neither
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
        if task_id:
            db.ex(f"UPDATE tsk_tasks SET {', '.join(f'{k} = %s' for k in cols)}, list_id = %s WHERE id = %s", (*cols.values(), lid, task_id))
        else:
            task_id = db.ex(f"INSERT INTO tsk_tasks ({', '.join(cols)}, list_id, href, created_by) VALUES "
                            f"({', '.join(['%s'] * len(cols))}, %s, %s, %s)", (*cols.values(), lid, href, user_id))
    return get_row(task_id)


def delete(tid: int) -> None:
    """A deletion marker: CalDAV clients learn of the deletion from the next sync. Kept for KEEP_DELETED_DAYS (purge_deleted)."""
    with db.tx():
        r = get_row(tid)
        if not r or r["deleted"]:
            return
        tok = bump(r["list_id"])
        db.ex("UPDATE tsk_tasks SET deleted = 1, ics = '', changed_token = %s WHERE id = %s", (tok, tid))


def delete_with_subtasks(tid: int) -> int:
    """A task and the subtasks under it (all levels, in the same list): how many went."""
    r = get_row(tid)
    if not r or r["deleted"]:
        return 0
    n, todo, seen = 0, [r], set()
    while todo:
        x = todo.pop()
        if x["id"] in seen:
            continue
        seen.add(x["id"])
        todo += db.q("SELECT * FROM tsk_tasks WHERE list_id = %s AND parent_uid = %s AND deleted = 0", (x["list_id"], x["uid"]))
        delete(x["id"])
        n += 1
    return n


PURGED = "purged_token:"  # tsk_settings: per list, the newest change among the deletion markers that were purged


def purge_deleted(days: int | None = None) -> int:
    """Remove the deletion markers older than `days` (KEEP_DELETED_DAYS); how many went. Each list remembers how far
    its purged markers reached, so a client that last synced before that is told to start over (purged_before)."""
    days = config.KEEP_DELETED_DAYS if days is None else days
    with db.tx():
        old = db.q("SELECT list_id AS lst, max(changed_token) AS tok FROM tsk_tasks WHERE deleted = 1 "
                   "AND updated_at < NOW() - INTERVAL %s DAY GROUP BY list_id", (days,))
        for r in old:
            db.set_setting(f"{PURGED}{r['lst']}", str(max(r["tok"], purged_before(r["lst"]))))
        return db.ex("DELETE FROM tsk_tasks WHERE deleted = 1 AND updated_at < NOW() - INTERVAL %s DAY", (days,)) if old else 0


def purged_before(lid: int) -> int:
    """The sync token up to which this list's deletion markers are gone (0: none were purged)."""
    return int(db.get_setting(f"{PURGED}{lid}") or 0)


def move(tid: int, to_lid: int) -> dict:
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
        delete(tid)
        new = save(to_lid, cal, None, None, r.get("created_by"))
        for k in kids:
            move(k["id"], to_lid)
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


def find(lids: list[int], q: str = "", status: str = "open", due: str | None = None, member_ids: set[int] | None = None,
         limit: int = 500, tzname: str | None = None) -> list[dict]:
    """Tasks in these lists. status: open (not done), done (completed or cancelled, the latest first) or all. due:
    today (due today or earlier: what is on today), overdue, week (the next seven days and earlier), scheduled (any
    due date), none (no due date) or a date YYYY-MM-DD. q: every word in the title or the notes. member_ids: only the
    tasks for one of these family members."""
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
    for w in (q or "").split()[:8]:
        like = _like(w)
        where.append("(t.summary LIKE %s OR t.description LIKE %s)")
        args += [like, like]
    if member_ids is not None:
        where.append("t.ics LIKE '%%CATEGORIES%%'")
    order = "t.completed_at IS NULL, t.completed_at DESC, t.updated_at DESC" if status == "done" else SORT
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
    return db.q(f"SELECT t.* FROM tsk_tasks t WHERE t.list_id = %s AND t.parent_uid = %s AND t.deleted = 0 ORDER BY {SORT}", (r["list_id"], r["uid"]))


# ------------------------------------------------------------------ import and export

def import_text(lid: int, text: str, user_id: int | None = None, replace: bool = True) -> dict:
    """An .ics file (one task or a whole list) into a list: every UID becomes a task; a UID the list has already is
    updated (replace) or skipped. Events in the file are left out. {created, updated, skipped, errors}."""
    cal = ical.parse(text)
    out = {"created": 0, "updated": 0, "skipped": 0, "errors": []}
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
        save(lid, ical.finish(obj), old["id"] if old else None, None, user_id)
        out["updated" if old else "created"] += 1
    return out


def export_text(lists: list[dict], name: str) -> str:
    objs = []
    for c in lists:
        objs += objects(rows(c["id"]))
    return ical.feed(objs, name, color=lists[0].get("color") if len(lists) == 1 else None)
