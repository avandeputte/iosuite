"""What a person keeps in ioTask, counted or removed when their account is deleted (iosuite_shared.persondata):
their private lists with every task in them, and their own templates. Tasks they put on a shared list stay: the
family still needs them."""

from app import db, model


def of(user_id: int, remove: bool) -> list:
    lists = [r["id"] for r in db.q("SELECT id FROM tsk_lists WHERE owner_id = %s", (user_id,))]
    tasks = db.one("SELECT count(*) AS n FROM tsk_tasks t JOIN tsk_lists l ON l.id = t.list_id "
                   "WHERE l.owner_id = %s AND t.deleted = 0", (user_id,))["n"]
    templates = db.one("SELECT count(*) AS n FROM tsk_templates WHERE owner_id = %s", (user_id,))["n"]
    shared = db.one("SELECT count(*) AS n FROM tsk_tasks t JOIN tsk_lists l ON l.id = t.list_id "
                    "WHERE l.owner_id IS NULL AND t.created_by = %s AND t.deleted = 0", (user_id,))["n"]
    if remove:
        for lid in lists:
            model.delete_list(lid)  # its tasks' links to other items of the suite go too
        db.ex("DELETE FROM tsk_templates WHERE owner_id = %s", (user_id,))
    return [{"what": "private lists", "one": "private list", "count": len(lists)},
            {"what": "tasks in them", "one": "task in it", "count": tasks},
            {"what": "own templates", "one": "own template", "count": templates},
            {"what": "tasks they added to shared lists", "one": "task they added to a shared list", "count": shared, "kept": True}]
