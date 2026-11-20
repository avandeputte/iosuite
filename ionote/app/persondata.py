"""What a person keeps in ioNote, counted or removed when their account is deleted (iosuite_shared.persondata):
their own notes (with their pictures and attachments), folders, tag colours, templates and their change log. The
notes they put in the Family space stay: the family still needs them.

Whose a note is says nts_notes.user_id, for its picture and attachments too; a family note is nobody's."""
from iosuite_shared import related

from app import db

TABLES = (("nts_folders", "folders", "folder"), ("nts_templates", "templates", "template"), ("nts_tag_colors", "tag colours", "tag colour"))


def of(user_id: int, remove: bool) -> list:
    uid = int(user_id)
    if uid <= 0:  # 0: the records made before the first account, nobody's to delete
        return []
    with db.tx() if remove else db.connect() as con:
        n = lambda sql: int(con.execute(sql, (uid,)).fetchone()[0])  # noqa: E731
        own = "SELECT uuid FROM nts_notes WHERE user_id = %s AND family = 0"
        out = [{"what": "notes", "one": "note", "count": n("SELECT count(*) FROM nts_notes WHERE user_id = %s AND family = 0 AND deleted < 2")},
               {"what": "attachments", "one": "attachment", "count": n(f"SELECT count(*) FROM nts_attachments WHERE note_uuid IN ({own})")}]
        out += [{"what": what, "one": one, "count": n(f"SELECT count(*) FROM {t} WHERE user_id = %s AND deleted = 0")} for t, what, one in TABLES]
        out.append({"what": "change log entries", "one": "change log entry", "count": n("SELECT count(*) FROM nts_change_log WHERE user_id = %s")})
        out.append({"what": "notes they put in the Family space", "one": "note they put in the Family space", "kept": True,
                    "count": n("SELECT count(*) FROM nts_notes WHERE user_id = %s AND family = 1 AND deleted = 0")})
        gone = [r[0] for r in con.execute(own, (uid,)).fetchall()] if remove else []
        if remove:
            con.execute(f"DELETE FROM nts_note_images WHERE uuid IN ({own})", (uid,))
            con.execute(f"DELETE FROM nts_attachments WHERE note_uuid IN ({own})", (uid,))
            con.execute("DELETE FROM nts_notes WHERE user_id = %s AND family = 0", (uid,))
            con.execute("UPDATE nts_notes SET user_id = 0 WHERE user_id = %s", (uid,))             # the family's: nobody's now
            con.execute("UPDATE nts_attachments SET user_id = 0 WHERE user_id = %s", (uid,))       # what they attached to those
            for t in ("nts_change_log",) + tuple(t for t, _, _ in TABLES):
                con.execute(f"DELETE FROM {t} WHERE user_id = %s", (uid,))
    related.forget_many("note", gone)  # their links to other items of the suite go too (after the commit)
    return out
