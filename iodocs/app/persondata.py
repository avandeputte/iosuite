"""What a person keeps in ioDocs, when a suite admin deletes their account (iosuite_shared.persondata).

Their papers go with them: the documents that are theirs alone (they are its only person, or they added it and it
is nobody's in particular) and the private ones they added, with their scans. A document they share with others (the
family's passports page, a policy for two) stays, without them; what they added for the family (visibility family)
stays as the household's."""
from iosuite_shared import related

from app import db


def _theirs(user_id: int) -> list[int]:
    rows = db.q("SELECT d.id FROM doc_documents d WHERE "
                "(EXISTS (SELECT 1 FROM doc_people p WHERE p.doc_id = d.id AND p.user_id = %s) "
                " AND NOT EXISTS (SELECT 1 FROM doc_people p WHERE p.doc_id = d.id AND p.user_id <> %s)) "
                "OR (d.created_by = %s AND d.visibility <> 'family' AND NOT EXISTS (SELECT 1 FROM doc_people p WHERE p.doc_id = d.id AND p.user_id <> %s))",
                (user_id, user_id, user_id, user_id))
    return [r["id"] for r in rows]


def of(user_id: int, remove: bool) -> list:
    gone = _theirs(user_id)
    shared = db.one("SELECT count(*) AS n FROM doc_people WHERE user_id = %s" + (f" AND doc_id NOT IN ({db.marks(len(gone))})" if gone else ""),
                    (user_id, *gone))["n"]
    kept = db.one("SELECT count(*) AS n FROM doc_documents WHERE created_by = %s" + (f" AND id NOT IN ({db.marks(len(gone))})" if gone else ""),
                  (user_id, *gone))["n"]
    if remove:
        with db.tx():
            if gone:
                db.ex(f"UPDATE doc_documents SET renewed_by = NULL WHERE renewed_by IN ({db.marks(len(gone))})", gone)
                db.ex(f"DELETE FROM doc_documents WHERE id IN ({db.marks(len(gone))})", gone)
            db.ex("DELETE FROM doc_people WHERE user_id = %s", (user_id,))
            db.ex("UPDATE doc_documents SET created_by = NULL, updated_at = updated_at WHERE created_by = %s", (user_id,))
            db.ex("UPDATE doc_files SET created_by = NULL WHERE created_by = %s", (user_id,))
        if gone:
            related.forget_many("document", [str(i) for i in gone])
    return [{"what": "documents of theirs, with their scans", "one": "document of theirs, with its scans", "count": len(gone), "kept": False},
            {"what": "documents they share with others (the documents stay, without them)",
             "one": "document they share with others (the document stays, without them)", "count": shared, "kept": False},
            {"what": "documents they added for the family", "one": "document they added for the family", "count": kept, "kept": True}]
