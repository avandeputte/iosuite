"""Notifications from ioTask (iosuite_shared.push): a task's alerts when they go off (a task with a time and no alert:
when it falls due), and at each person's morning time what is on today (due today, and what is late), for the people
who turned notifications on.

A task is for the family members it is tagged with; untagged, for the owner of its private list, else (a shared list)
for whoever added it. Run every minute by the app (chores.start); it does nothing while nobody has a device.
"""
import datetime as dt

from iosuite_shared import push

from app import db, ical, members, model

APP = "iotask"
LATE = dt.timedelta(minutes=15)   # a task that fell due while the server was off: still said, up to this late
MORNING_LIST = 5                   # titles named in the morning summary; the rest are counted


def for_whom(r: dict, owner_id, fam: list) -> set[int]:
    try:
        ids = set(members.ids_of(ical.categories_of(ical.todo(model.parsed(r))), fam))
    except Exception:  # noqa: BLE001 - an object that cannot be read: its list says whose it is
        ids = set()
    if ids:
        return ids
    if owner_id is not None:
        return {owner_id}
    return {r["created_by"]} if r.get("created_by") else set()


def run(now: dt.datetime = None) -> int:
    """Send what is due; how many notifications went out."""
    people = {u["id"] for u in push.recipients("tasks")}
    if not people:
        return 0
    now = now or dt.datetime.now(dt.timezone.utc)
    utc = now.astimezone(dt.timezone.utc).replace(tzinfo=None)
    fam = members.family()
    sent = 0
    rows = db.q("SELECT t.*, l.owner_id, l.name AS list_name FROM tsk_tasks t JOIN tsk_lists l ON l.id = t.list_id "
                "WHERE t.deleted = 0 AND t.done = 0 AND (t.ics LIKE '%%VALARM%%' OR (t.due_all_day = 0 AND t.due > %s AND t.due <= %s))",
                (utc - LATE, utc))
    for r in rows:
        try:
            alerts = [dt.datetime.fromisoformat(a) for a in ical.alarms_of(ical.todo(model.parsed(r)))]
        except Exception:  # noqa: BLE001 - an object that cannot be read
            alerts = []
        when = [a.astimezone(dt.timezone.utc).replace(tzinfo=None) for a in alerts] if alerts else [r["due"]] if not r["due_all_day"] and r["due"] else []
        for at in when:
            if not (utc - LATE < at <= utc):
                continue
            body = (f"Due now · {r['list_name']}" if not alerts else
                    f"Due {_due_text(r)} · {r['list_name']}" if r["due"] else r["list_name"])
            for uid in for_whom(r, r["owner_id"], fam) & people:
                sent += push.notify(uid, "tasks", r["summary"] or "A task", body, url=push.link(APP, f"#/task/{r['id']}"),
                                    once=f"task:{r['uid']}:{at:%Y%m%dT%H%M}")
    local = now.astimezone(ical.zone(None)).replace(tzinfo=None)
    for uid in people:
        key = f"tasks:morning:{local.date()}"
        if push.is_morning(uid, local) and not push.was_sent(uid, key):
            sent += morning(uid, key, fam)
    return sent


def _due_text(r: dict) -> str:
    if r["due_all_day"]:
        return "today" if r["due"].date() == dt.datetime.now(ical.zone(None)).date() else f"{r['due']:%a %d %b}"
    local = r["due"].replace(tzinfo=dt.timezone.utc).astimezone(ical.zone(None))
    return f"at {local:%H:%M}" if local.date() == dt.datetime.now(ical.zone(None)).date() else f"{local:%a %d %b %H:%M}"


def morning(uid: int, key: str, fam: list) -> int:
    """The morning summary for one person: what is due today and what is late, in the lists they see."""
    lists = {r["id"]: r["owner_id"] for r in db.q("SELECT id, owner_id FROM tsk_lists WHERE owner_id IS NULL OR owner_id = %s", (uid,))}
    today = [r for r in model.find(list(lists), due="today", limit=500) if uid in for_whom(r, lists[r["list_id"]], fam)]
    if not today:
        push.claim(uid, key)  # nothing today: nothing to say, and nothing to work out again this morning
        return 0
    day = dt.datetime.now(ical.zone(None)).date()
    midnight, day_start = dt.datetime.combine(day, dt.time()), model.day_bounds(day)[0]
    late = [r for r in today if r["due"] is not None and r["due"] < (midnight if r["due_all_day"] else day_start)]
    names = [r["summary"] or "A task" for r in today]
    body = ", ".join(names[:MORNING_LIST]) + (f" and {len(names) - MORNING_LIST} more" if len(names) > MORNING_LIST else "")
    title = f"{len(today)} task{'s' if len(today) != 1 else ''} today" + (f", {len(late)} late" if late else "")
    return push.notify(uid, "tasks", title, body, url=push.link(APP, "#/"), once=key, tag="tasks-morning")
