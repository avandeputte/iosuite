"""ioTask's answers to the suite's standard endpoints (iosuite_shared.suiteitems): tasks found, one task, the tile."""
from iosuite_shared.suiteitems import Provider, item


def _task(t: dict, colors: dict) -> dict:
    return item("iotask", "task", t.get("id"), t.get("title") or t.get("summary"), "", t.get("due"), t.get("dueAllDay"),
                done=bool(t.get("done") or t.get("completed")), color=colors.get(t.get("listId")), icon="task")


def _colors(local) -> dict:
    return {c["id"]: c.get("color") for c in local.get("/api/lists").get("items", [])}


def search(local, q, n, tz, kinds):
    """The open tasks that match, soonest due first, then the done ones (done: the search box leaves them out)."""
    if kinds and "task" not in kinds:
        return []
    p = {"q": q, "limit": n + 1, "tz": tz or None}
    lists, open_, done = local.together(lambda: local.get("/api/lists"), lambda: local.get("/api/tasks", {**p, "status": "open"}),
                                        lambda: local.get("/api/tasks", {**p, "status": "done", "limit": n}))
    if isinstance(open_, Exception):
        raise open_
    colors = {} if isinstance(lists, Exception) else {c["id"]: c.get("color") for c in lists.get("items", [])}
    rows = [t for t in open_.get("items", []) if not t.get("done")]
    gone = [] if isinstance(done, Exception) else done.get("items", [])
    return {"items": [_task(t, colors) for t in rows[:n] + gone[:n]], "more": len(rows) > n}


def get(local, kind, item_id):
    if kind != "task" or not item_id.isdigit():
        return None
    colors, t = local.together(lambda: _colors(local), lambda: local.get(f"/api/tasks/{item_id}"))
    if isinstance(t, Exception):
        raise t
    return _task({**t, "id": item_id}, {} if isinstance(colors, Exception) else colors)  # no colour without the lists


def tile(local, tz, n, kind):
    """{today: [task], more, overdue}: the open tasks due today or before (the viewer's today), the overdue ones first
    as ioTask sorts them, up to n, each with its list's colour; overdue is how many of them all are late.
    kind "week": {week: [task], more}, the open tasks due on the six days after today, the soonest first, up to n (12)."""
    q = {"due": "today", "status": "open", "limit": 200, "tz": tz or None}
    if kind == "week":
        n = n or 12
        lists, soon, due = local.both(lambda: local.get("/api/lists"), lambda: local.get("/api/tasks", {**q, "due": "week"}),
                                      lambda: local.get("/api/tasks", q))
        colors = {c["id"]: c.get("color") for c in lists.get("items", [])}
        by_today = {t.get("id") for t in due.get("items", [])}  # due today or before: the tile's own list
        items = sorted((t for t in soon.get("items", []) if t.get("id") not in by_today and t.get("due")), key=lambda t: str(t["due"]))
        return {"week": [{"id": t.get("id"), "title": t.get("title") or "(no title)", "due": t.get("due"), "allDay": bool(t.get("dueAllDay")),
                          "color": colors.get(t.get("listId"))} for t in items[:n]], "more": max(0, len(items) - n)}
    n = n or 3
    lists, due, over = local.both(lambda: local.get("/api/lists"), lambda: local.get("/api/tasks", q),
                                  lambda: local.get("/api/tasks", {**q, "due": "overdue"}))
    colors = {c["id"]: c.get("color") for c in lists.get("items", [])}
    late_ids = {t.get("id") for t in over.get("items", [])}
    items = due.get("items", [])
    return {"today": [{"id": t.get("id"), "title": t.get("title") or "(no title)", "due": t.get("due"), "allDay": bool(t.get("dueAllDay")),
                       "late": t.get("id") in late_ids, "color": colors.get(t.get("listId"))} for t in items[:n]],
            "more": max(0, len(items) - n), "overdue": len(late_ids)}


PROVIDER = Provider(search=search, get=get, tile=tile)
