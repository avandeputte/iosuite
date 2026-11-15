"""What a person keeps in ioHome, counted when their account is deleted (iosuite_shared.persondata). Everything here
is the household's: the things they added, the files and the log lines stay, whoever added them. Only the account
that made an upkeep's task in ioTask is forgotten (the task itself is that person's, in ioTask, which purges it)."""
from app import db


def of(user_id: int, remove: bool) -> list:
    items = db.one("SELECT count(*) AS n FROM hom_items WHERE created_by = %s", (user_id,))["n"]
    files = db.one("SELECT count(*) AS n FROM hom_files WHERE created_by = %s", (user_id,))["n"]
    lines = db.one("SELECT count(*) AS n FROM hom_maintenance WHERE created_by = %s", (user_id,))["n"]
    if remove:
        with db.tx():
            db.ex("UPDATE hom_upkeep SET task_id = NULL, task_list = NULL, task_by = NULL WHERE task_by = %s", (user_id,))
            db.ex("UPDATE hom_items SET created_by = NULL, updated_at = updated_at WHERE created_by = %s", (user_id,))
            db.ex("UPDATE hom_files SET created_by = NULL WHERE created_by = %s", (user_id,))
            db.ex("UPDATE hom_maintenance SET created_by = NULL WHERE created_by = %s", (user_id,))
            db.ex("UPDATE hom_upkeep SET created_by = NULL WHERE created_by = %s", (user_id,))
    return [{"what": "things they added", "one": "thing they added", "count": items, "kept": True},
            {"what": "files they added", "one": "file they added", "count": files, "kept": True},
            {"what": "maintenance log lines they wrote", "one": "maintenance log line they wrote", "count": lines, "kept": True}]
