"""What a person keeps in ioHealth, counted or removed when their account is deleted (iosuite_shared.persondata):
everything, since all health data is its owner's alone: every hlt_ table with a user_id column (samples, workouts
with their routes and heartbeats, activity rings, the hourly figures, settings, the sync log)."""
from app import db

SHOWN = (("hlt_samples", "health samples", "health sample"), ("hlt_workouts", "workouts", "workout"),
         ("hlt_activity_summaries", "days of activity rings", "day of activity rings"))


def _tables() -> list:
    return [r[0] for r in db.q("SELECT c.table_name FROM information_schema.columns c JOIN information_schema.tables t "
                               "ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
                               "WHERE c.table_schema = DATABASE() AND t.table_type = 'BASE TABLE' "  # not the views
                               "AND c.column_name = 'user_id' AND c.table_name LIKE 'hlt\\_%%' ORDER BY c.table_name")]


def of(user_id: int, remove: bool) -> list:
    uid = int(user_id)
    if uid <= 0:
        return []
    tables = _tables()
    count = {t: int(db.one(f"SELECT count(*) FROM {t} WHERE user_id = %s", (uid,))[0]) for t in tables}
    out = [{"what": what, "one": one, "count": count.get(t, 0)} for t, what, one in SHOWN]
    rest = sum(n for t, n in count.items() if t not in {s[0] for s in SHOWN})
    out.append({"what": "other records (workout details, hourly figures, settings, sync log)", "one": "other record", "count": rest})
    if remove:
        for t in tables:
            db.ex(f"DELETE FROM {t} WHERE user_id = %s", (uid,))
    return out
