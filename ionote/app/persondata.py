"""What a person keeps in ioNote, counted or removed when their account is deleted (iosuite_shared.persondata):
everything, since every note is its owner's alone: notes (with their pictures and attachments), folders, tag colours,
templates and their change log."""
from iosuite_shared import related

from app import db

TABLES = (("nts_folders", "folders", "folder"), ("nts_templates", "templates", "template"), ("nts_tag_colors", "tag colours", "tag colour"))


def of(user_id: int, remove: bool) -> list:
    uid = int(user_id)
    if uid <= 0:  # 0: the records made before the first account, nobody's to delete
        return []
    with db.tx() if remove else db.connect() as con:
        n = lambda sql: int(con.execute(sql, (uid,)).fetchone()[0])  # noqa: E731
        out = [{"what": "notes", "one": "note", "count": n("SELECT count(*) FROM nts_notes WHERE user_id = ? AND deleted < 2")},
               {"what": "attachments", "one": "attachment", "count": n("SELECT count(*) FROM nts_attachments WHERE user_id = ?")}]
        out += [{"what": what, "one": one, "count": n(f"SELECT count(*) FROM {t} WHERE user_id = ? AND deleted = 0")} for t, what, one in TABLES]
        out.append({"what": "change log entries", "one": "change log entry", "count": n("SELECT count(*) FROM nts_change_log WHERE user_id = ?")})
        gone = [r[0] for r in con.execute("SELECT uuid FROM nts_notes WHERE user_id = ?", (uid,)).fetchall()] if remove else []
        if remove:
            con.execute("DELETE FROM nts_note_images WHERE uuid IN (SELECT uuid FROM nts_notes WHERE user_id = ?)", (uid,))
            for t in ("nts_attachments", "nts_notes", "nts_change_log") + tuple(t for t, _, _ in TABLES):
                con.execute(f"DELETE FROM {t} WHERE user_id = ?", (uid,))
    related.forget_many("note", gone)  # their links to other items of the suite go too (after the commit)
    return out
