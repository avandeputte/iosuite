"""Contacts keep no photos: the start-up migration deletes the copies still stored elsewhere."""
import json

from app import db


def test_stored_photo_copies_are_deleted_at_start(client, family_id):
    """Photo suggestions and the photo columns in merge-undo snapshots go; everything else stays as it was."""
    c = client.post(f"/api/contacts?book={family_id}", json={"fn": "Old Photo"}).json()
    snap = {"contacts": [{"id": c["id"], "fn": "Old Photo", "photo": {"$b64": "/9j/4AAQ"}, "photo_type": "image/jpeg"}], "relations": []}
    plain = {"contacts": [{"id": c["id"], "fn": "No Photo"}], "relations": []}
    mid = db.ex("INSERT INTO con_contact_merges (kept_contact_id, other_ids, names, snapshot) VALUES (%s, '', 'Old Photo', %s)",
                (c["id"], json.dumps(snap)))
    other = db.ex("INSERT INTO con_contact_merges (kept_contact_id, other_ids, names, snapshot) VALUES (%s, '', 'No Photo', %s)",
                  (c["id"], json.dumps(plain)))
    for field, value, vkey in (("photo", "{}", "photo:x"), ("title", '"Chef"', "chef")):
        db.ex("INSERT INTO con_contact_suggestions (contact_id, field, value, vkey, source) VALUES (%s, %s, %s, %s, 'gravatar')",
              (c["id"], field, value, vkey))
    db.migrate()
    kept = json.loads(db.one("SELECT snapshot FROM con_contact_merges WHERE id = %s", (mid,))["snapshot"])
    assert kept == {"contacts": [{"id": c["id"], "fn": "Old Photo"}], "relations": []}
    assert json.loads(db.one("SELECT snapshot FROM con_contact_merges WHERE id = %s", (other,))["snapshot"]) == plain
    assert [r["field"] for r in db.q("SELECT field FROM con_contact_suggestions WHERE contact_id = %s", (c["id"],))] == ["title"]
    db.migrate()  # again: nothing left to do
