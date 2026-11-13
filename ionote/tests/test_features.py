"""Attachments (PDFs and other files, with their text searchable), the trash being emptied for good, templates, and
related notes with tag and folder suggestions."""
import time
import zipfile
import io

from helpers import NID, NID2, pdf, png

AID = "AAAAAAAA-1D2B-4F3A-9C1A-1234567890AB"


def test_a_pdf_attached_is_listed_with_the_note_and_its_text_found_by_search(client, admin):
    n0 = client.put(f"/api/notes/{NID}", json={"title": "Receipts", "updatedAt": 1}).json()
    r = client.post(f"/api/notes/{NID}/attachments", files={"file": ("acme.pdf", pdf(), "application/pdf")})
    assert r.status_code == 200, r.text
    n = r.json()
    assert n["rev"] > n0["rev"] and len(n["attachments"]) == 1
    a = n["attachments"][0]
    assert a["name"] == "acme.pdf" and a["mime"] == "application/pdf" and a["bytes"] == len(pdf())
    assert "Acme" in client.get(f"/api/notes/{NID}/attachments/{a['id']}/text").json()["text"]
    q = lambda s: {x["id"] for x in client.get("/api/notes", params={"q": s}).json()["notes"]}
    assert q("acme corporation") == {NID}
    assert q("receipts") == {NID}
    assert q("acme receipts") == set()  # every word in the note, or every word in one file
    got = client.get(f"/api/notes/{NID}/attachments/{a['id']}")
    assert got.status_code == 200 and got.content == pdf() and got.headers["content-type"] == "application/pdf"
    assert got.headers["content-disposition"].startswith("inline")
    assert client.get(f"/api/notes/{NID}/attachments/{a['id']}?download=1").headers["content-disposition"].startswith("attachment")
    # the devices learn of it through sync, with the note
    s = client.get("/api/sync", params={"since": n0["rev"]}).json()
    assert [x["attachments"][0]["id"] for x in s["notes"]] == [a["id"]]
    n = client.delete(f"/api/notes/{NID}/attachments/{a['id']}").json()
    assert n["attachments"] == [] and q("acme") == set()


def test_a_device_puts_a_file_with_its_own_id_and_again_is_a_no_op(client, admin):
    client.put(f"/api/notes/{NID}", json={"title": "x", "updatedAt": 1})
    h = {"content-type": "image/png", "x-ionote-text": "Hello%20world"}
    a = client.put(f"/api/notes/{NID}/attachments/{AID}", params={"name": "shot.png"}, content=png(), headers=h).json()
    b = client.put(f"/api/notes/{NID}/attachments/{AID}", params={"name": "shot.png"}, content=png(), headers=h).json()
    assert a["rev"] == b["rev"] and a["attachments"][0]["width"] == 320
    assert client.get(f"/api/notes/{NID}/attachments/{AID}/text").json()["text"] == "Hello world"
    assert client.get(f"/api/notes/{NID}/attachments/{AID}/thumb").headers["content-type"] == "image/jpeg"
    # another note's id is refused
    client.put(f"/api/notes/{NID2}", json={"title": "y", "updatedAt": 1})
    assert client.put(f"/api/notes/{NID2}/attachments/{AID}", params={"name": "x.png"}, content=png(10, 10), headers=h).status_code == 404


def test_html_is_never_served_inline(client, admin):
    client.put(f"/api/notes/{NID}", json={"title": "x", "updatedAt": 1})
    n = client.post(f"/api/notes/{NID}/attachments", files={"file": ("page.html", b"<script>alert(1)</script>", "text/html")}).json()
    r = client.get(f"/api/notes/{NID}/attachments/{n['attachments'][0]['id']}")
    assert r.headers["content-disposition"].startswith("attachment") and "html" not in r.headers["content-type"]
    assert "sandbox" in r.headers["content-security-policy"]


def test_emptying_the_trash_keeps_a_tombstone_and_restore_is_refused(client, admin):
    client.put(f"/api/notes/{NID}", json={"title": "Secret", "body": "gone soon", "tags": ["x"], "updatedAt": 1})
    client.post(f"/api/notes/{NID}/attachments", files={"file": ("a.txt", b"hello", "text/plain")})
    client.put(f"/api/notes/{NID2}", json={"title": "Keep", "updatedAt": 1})
    client.delete(f"/api/notes/{NID}")
    assert client.get("/api/meta").json()["trash"] == 1
    rev = client.get("/api/meta").json()["rev"]
    assert client.post("/api/trash/empty").json() == {"purged": 1}
    assert client.get("/api/trash").json()["notes"] == [] and client.get("/api/meta").json()["trash"] == 0
    s = client.get("/api/sync", params={"since": rev}).json()["notes"]
    assert [(x["id"], x["deleted"], x["title"], x["body"], x["attachments"]) for x in s] == [(NID, True, "", "", [])]
    assert client.post(f"/api/notes/{NID}/restore").status_code == 404
    assert client.get(f"/api/notes/{NID2}").json()["deleted"] is False


def test_one_note_deleted_for_good_and_expired_trash_purged(client, admin):
    from app import notes
    client.put(f"/api/notes/{NID}", json={"title": "a", "updatedAt": 1})
    client.put(f"/api/notes/{NID2}", json={"title": "b", "updatedAt": 1})
    assert client.delete(f"/api/trash/{NID}").status_code == 404  # not in the trash
    client.delete(f"/api/notes/{NID}")
    client.delete(f"/api/notes/{NID2}", params={"ts": time.time() - 40 * 86400})
    assert notes.purge_expired() == 1
    assert [x["id"] for x in client.get("/api/trash").json()["notes"]] == [NID]
    assert client.delete(f"/api/trash/{NID}").json() == {"purged": 1}


def test_templates_sync_and_fill_in_new_notes(client, admin):
    f = client.post("/api/folders", json={"name": "Meetings"}).json()
    t = client.post("/api/templates", json={"name": "Meeting", "title": "Meeting {{date}}", "body": "## Agenda\n- [ ] \n\n{{weekday}}",
                                            "tags": ["meeting"], "folderID": f["id"]}).json()
    assert t["id"] in [x["id"] for x in client.get("/api/templates").json()["templates"]]
    assert "Meeting" in [x["name"] for x in client.get("/api/sync").json()["templates"]]
    assert t["id"] in [x["id"] for x in client.get("/api/meta").json()["templates"]]
    n = client.post("/api/notes", json={"template": t["id"]}).json()
    assert n["title"] == "Meeting " + time.strftime("%Y-%m-%d") and n["tags"] == ["meeting"] and n["folderID"] == f["id"]
    assert "{{" not in n["body"] and n["body"].startswith("## Agenda")
    # filled in by the browser (its own clock): the body wins
    n = client.post("/api/notes", json={"template": t["id"], "title": "Mine"}).json()
    assert n["title"] == "Mine"
    assert client.post("/api/notes", json={"template": NID}).status_code == 404
    client.delete(f"/api/templates/{t['id']}")
    assert t["id"] not in [x["id"] for x in client.get("/api/templates").json()["templates"]]


def test_standard_templates_come_once_and_stay_deleted(client, admin):
    from app import notes
    names = lambda: sorted(x["name"] for x in client.get("/api/templates").json()["templates"])  # noqa: E731
    standard = sorted(t["name"] for t in notes.STANDARD_TEMPLATES)
    assert names() == standard
    assert sorted(x["name"] for x in client.get("/api/sync").json()["templates"]) == standard  # the apps get them too
    meeting = next(x for x in client.get("/api/templates").json()["templates"] if x["name"] == "Meeting notes")
    assert "- [ ] " in meeting["body"] and "{{date}}" in meeting["title"]
    n = client.post("/api/notes", json={"template": meeting["id"]}).json()
    assert n["title"] == "Meeting " + time.strftime("%Y-%m-%d") and "{{" not in n["body"]
    # a deleted one stays deleted, also once the server forgets what it knew (a restart)
    client.delete(f"/api/templates/{meeting['id']}")
    notes._seeded.clear()
    assert "Meeting notes" not in names()
    # the button brings it back, as itself, and leaves a template of the same name alone
    shop = next(x for x in client.get("/api/templates").json()["templates"] if x["name"] == "Shopping list")
    client.delete(f"/api/templates/{shop['id']}")
    mine = client.post("/api/templates", json={"name": "Shopping list", "body": "- [ ] milk"}).json()
    r = client.post("/api/templates/standard").json()
    assert r["added"] == 1 and names() == standard
    assert meeting["id"] in [x["id"] for x in r["templates"]] and mine["id"] in [x["id"] for x in r["templates"]]
    assert client.post("/api/templates/standard").json()["added"] == 0


def test_related_notes_and_suggestions(client, admin):
    f = client.post("/api/folders", json={"name": "Garden"}).json()
    client.put(f"/api/notes/{NID}", json={"title": "Tomato seedlings", "body": "Water the tomato seedlings in the greenhouse", "tags": ["garden"],
                                          "folderID": f["id"], "updatedAt": 1})
    client.put(f"/api/notes/{NID2}", json={"title": "Taxes", "body": "Quarterly tax return", "updatedAt": 1})
    new = client.post("/api/notes", json={"body": "Repot the tomato plants from the greenhouse, garden work"}).json()
    r = client.get(f"/api/notes/{new['id']}/related").json()
    assert [x["id"] for x in r["notes"]][:1] == [NID]
    assert NID2 not in [x["id"] for x in r["notes"]]
    assert "garden" in r["tags"] and r["folder"] == {"id": f["id"], "name": "Garden"}


def test_export_and_import_carry_files_and_templates(client, admin):
    client.put(f"/api/notes/{NID}", json={"title": "With file", "updatedAt": 1})
    client.post(f"/api/notes/{NID}/attachments", files={"file": ("acme.pdf", pdf(), "application/pdf")})
    client.post("/api/templates", json={"name": "Daily", "body": "{{date}}"})
    z = client.get("/api/export.zip").content
    names = zipfile.ZipFile(io.BytesIO(z)).namelist()
    assert "With file files/acme.pdf" in names
    from app import db
    with db.connect() as con:
        for t in ("nts_notes", "nts_attachments", "nts_templates"):
            con.execute(f"DELETE FROM {t}")
        con.commit()
    r = client.post("/api/import", files={"file": ("x.zip", z, "application/zip")})
    assert r.status_code == 200, r.text
    n = client.get(f"/api/notes/{NID}").json()
    assert [a["name"] for a in n["attachments"]] == ["acme.pdf"]
    assert "Daily" in [t["name"] for t in client.get("/api/templates").json()["templates"]]
