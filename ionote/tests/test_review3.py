"""The lower findings of the code review of 10 November 2026: a download keeps a title in any script, what a deletion
leaves behind goes after a while, the export is sent in pieces, an import finds its pictures in one pass, and the tags
are counted once per change."""
import io
import json
import time
import zipfile

from app import backup, db, images, notes
from helpers import NID, NID2, png


# ---- N-4
def test_a_download_keeps_a_title_in_any_script(client, admin):
    client.put(f"/api/notes/{NID}", json={"title": "買い物リスト", "updatedAt": 1})
    client.put(f"/api/notes/{NID}/image", content=png(), headers={"content-type": "image/png"})
    r = client.get(f"/api/notes/{NID}/image", params={"download": 1})
    assert r.status_code == 200
    cd = r.headers["content-disposition"]
    assert cd.startswith('attachment; filename="______.png"') and "filename*=UTF-8''%E8%B2%B7%E3%81%84%E7%89%A9%E3%83%AA%E3%82%B9%E3%83%88.png" in cd


# ---- N-6
def test_what_a_deletion_leaves_behind_goes_after_a_while(client, admin):
    f = client.post("/api/folders", json={"name": "Old project"}).json()
    client.put(f"/api/notes/{NID}", json={"title": "Secret", "body": "the plan", "tags": ["x"], "folderID": f["id"], "updatedAt": 1})
    client.put(f"/api/notes/{NID2}", json={"title": "Kept", "updatedAt": 1})
    assert client.delete(f"/api/notes/{NID}").status_code == 200
    assert client.delete(f"/api/folders/{f['id']}").status_code == 200
    notes.housekeeping()  # deleted just now: the trash still has the note, the folder's marker its name
    assert client.get("/api/trash").json()["notes"][0]["title"] == "Secret"
    assert notes.purge_deleted() == {"folders": 0, "changes": 0}
    long_ago = time.time() - 200 * 86400
    with db.tx() as con:
        con.execute("UPDATE nts_notes SET updated_at = ? WHERE uuid = ?", (long_ago, NID))
        con.execute("UPDATE nts_folders SET updated_at = ? WHERE uuid = ?", (long_ago, f["id"]))
        con.execute("UPDATE nts_change_log SET created_at = ? WHERE uuid = ?", (int(long_ago), NID))
    notes.housekeeping()
    with db.connect() as con:
        r = con.execute("SELECT title, body, tags, deleted FROM nts_notes WHERE uuid = ?", (NID,)).fetchone()
        assert (r["title"], r["body"], r["tags"], r["deleted"]) == ("", "", "[]", notes.PURGED)
        assert con.execute("SELECT name FROM nts_folders WHERE uuid = ?", (f["id"],)).fetchone()[0] == ""
        assert con.execute("SELECT count(*) FROM nts_change_counter").fetchone()[0] == 1
    # a device that syncs from the start still learns of the deletion, and the rev goes on from where it was
    s = client.get("/api/sync").json()
    rev = s["rev"]
    assert {n["id"]: n["deleted"] for n in s["notes"]} == {NID: True, NID2: False}
    assert not any("Secret" in (c["summary"] or "") for c in client.get("/api/changes").json()["changes"])
    assert client.put(f"/api/notes/{NID2}", json={"title": "Kept on"}).json()["rev"] > rev
    assert notes.purge_deleted() == {"folders": 0, "changes": 0}
    # an export with the trash leaves the emptied note out
    z = zipfile.ZipFile(io.BytesIO(client.get("/api/export.zip", params={"trash": 1}).content))
    assert [n["id"] for n in json.loads(z.read("notes.json"))["notes"]] == [NID2]


# ---- N-7
def test_the_export_is_a_file_sent_in_pieces(client, admin):
    client.put(f"/api/notes/{NID}", json={"title": "With picture", "updatedAt": 1})
    client.put(f"/api/notes/{NID}/image", content=png(), headers={"content-type": "image/png"})
    token = notes.current_owner.set(admin["id"])
    try:
        f = backup.export_zip()
    finally:
        notes.current_owner.reset(token)
    assert f.tell() == 0 and not isinstance(f, (bytes, bytearray))
    got = list(backup.pieces(f, size=64))
    assert len(got) > 1 and f.closed and zipfile.ZipFile(io.BytesIO(b"".join(got))).testzip() is None
    r = client.get("/api/export.zip")
    assert r.status_code == 200 and "With picture.md" in zipfile.ZipFile(io.BytesIO(r.content)).namelist()


def test_an_import_finds_its_pictures_in_one_pass(client, admin):
    buf = io.BytesIO()
    ids = [f"{i:08d}-1D2B-4F3A-9C1A-1234567890AB" for i in range(30)]
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("notes.json", json.dumps({"format": "ionote-export", "notes": [{"id": i, "title": f"Note {n}", "updatedAt": 1} for n, i in enumerate(ids)]}))
        for n, i in enumerate(ids):
            z.writestr(f"Note {n}.md", f"---\nid: {i}\n---\n")
            if n % 2:
                z.writestr(f"Note {n}.png", png(8, 8))
        z.writestr("Note 2.v2.png", png(8, 8))  # not the picture of "Note 2"
    r = client.post("/api/import", files={"file": ("x.zip", buf.getvalue(), "application/zip")}).json()
    assert r["notes"] == 30 and r["pictures"] == 15
    assert client.get(f"/api/notes/{ids[2]}").json()["hasImage"] is False and client.get(f"/api/notes/{ids[3]}").json()["hasImage"] is True


def test_the_tags_are_counted_once_per_change(client, admin, monkeypatch):
    client.put(f"/api/notes/{NID}", json={"title": "a", "tags": ["Work"], "updatedAt": 1})
    counted = []
    real = notes._count_tags
    monkeypatch.setattr(notes, "_count_tags", lambda: counted.append(1) or real())
    first = client.get("/api/meta").json()["tags"]
    assert client.get("/api/meta").json()["tags"] == first == [{"name": "Work", "count": 1, "color": None}] and len(counted) == 1
    client.put(f"/api/notes/{NID2}", json={"title": "b", "tags": ["work", "Home"], "updatedAt": 1})
    assert [(t["name"], t["count"]) for t in client.get("/api/meta").json()["tags"]] == [("Home", 1), ("Work", 2)] and len(counted) == 2
    client.put("/api/tags/Work/color", json={"color": "blue"})
    assert client.get("/api/meta").json()["tags"][1]["color"] == "blue" and len(counted) == 3


def test_a_picture_larger_than_the_cap_is_refused():
    assert images.MAX_PIXELS == 40_000_000


# ---- N-8 and the bodies
def test_a_body_that_is_not_an_object_is_a_400(client, admin):
    for body in ("[1]", '"x"', "{no"):
        r = client.request("PUT", f"/api/notes/{NID}", content=body, headers={"Content-Type": "application/json"})
        assert r.status_code == 400, (body, r.status_code)
