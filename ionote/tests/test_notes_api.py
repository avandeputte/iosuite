"""Notes, folders, tags, pictures and search through the HTTP API, as the apps and the web app use it."""
import time

from helpers import NID, NID2, png


def test_create_read_update_with_the_apps_ids(client, admin):
    r = client.put(f"/api/notes/{NID}", json={"title": "Hello", "body": "Quarterly budget review", "tags": ["#Work", "work", " ai "],
                                              "source": "clipboard", "sourceApp": "Safari", "createdAt": 1000, "updatedAt": 1000})
    assert r.status_code == 200, r.text
    n = r.json()
    assert n["id"] == NID and n["tags"] == ["Work", "ai"] and n["source"] == "clipboard" and n["createdAt"] == 1000
    n2 = client.put(f"/api/notes/{NID}", json={"body": "changed", "updatedAt": 2000}).json()
    assert n2["body"] == "changed" and n2["title"] == "Hello" and n2["rev"] > n["rev"]


def test_an_older_edit_gets_the_servers_copy(client, admin):
    client.put(f"/api/notes/{NID}", json={"title": "new", "updatedAt": 2000})
    r = client.put(f"/api/notes/{NID}", json={"title": "old", "updatedAt": 1000})
    assert r.status_code == 409 and r.json()["current"]["title"] == "new"


def test_empty_ocr_text_never_erases_text_read_earlier(client, admin):
    client.put(f"/api/notes/{NID}", json={"ocrText": "Invoice 42", "updatedAt": 1})
    n = client.put(f"/api/notes/{NID}", json={"ocrText": "", "title": "t", "updatedAt": 2}).json()
    assert n["ocrText"] == "Invoice 42"


def test_search_matches_every_word_by_prefix_in_title_text_ocr_and_tags(client, admin):
    client.put(f"/api/notes/{NID}", json={"title": "Planning", "body": "budget meeting on Friday", "updatedAt": 1})
    client.put(f"/api/notes/{NID2}", json={"ocrText": "Revenue dashboard", "tags": ["finance"], "updatedAt": 1})
    q = lambda s: {n["id"] for n in client.get("/api/notes", params={"q": s}).json()["notes"]}
    assert q("budg") == {NID}
    assert q("budget frid") == {NID}
    assert q("revenue") == {NID2}
    assert q("financ") == {NID2}
    assert q("budget revenue") == set()
    assert q("on") == {NID}  # short words fall back to LIKE (MariaDB's full-text index skips them)


def test_filters_and_sorting_with_pinned_first(client, admin):
    f = client.post("/api/folders", json={"name": "Work", "color": "teal"}).json()
    client.put(f"/api/notes/{NID}", json={"title": "B", "folderID": f["id"], "tags": ["x"], "updatedAt": 1})
    client.put(f"/api/notes/{NID2}", json={"title": "A", "pinned": True, "updatedAt": 2})
    ids = lambda **p: [n["id"] for n in client.get("/api/notes", params=p).json()["notes"]]
    assert ids() == [NID2, NID]
    assert ids(sort="title") == [NID2, NID]
    assert ids(folder=f["id"]) == [NID] and ids(folder="none") == [NID2]
    assert ids(tag="X") == [NID] and ids(pinned=1) == [NID2]
    meta = client.get("/api/meta").json()
    assert meta["total"] == 2 and meta["pinned"] == 1 and meta["folders"][0]["count"] == 1 and meta["tags"] == [{"name": "x", "count": 1, "color": None}]


def test_delete_is_a_tombstone_the_devices_sync_and_restore_brings_it_back(client, admin):
    client.put(f"/api/notes/{NID}", json={"title": "gone soon", "updatedAt": 1})
    rev = client.get("/api/sync").json()["rev"]
    assert client.delete(f"/api/notes/{NID}").json()["deleted"] is True
    s = client.get("/api/sync", params={"since": rev}).json()
    assert [n["id"] for n in s["notes"]] == [NID] and s["notes"][0]["deleted"] is True
    assert client.get("/api/notes").json()["total"] == 0
    assert [n["id"] for n in client.get("/api/trash").json()["notes"]] == [NID]
    assert client.post(f"/api/notes/{NID}/restore").json()["deleted"] is False


def test_sync_pages_through_changes_in_rev_order(client, admin):
    for i in range(5):
        client.put(f"/api/notes/AAAAAAAA-0000-0000-0000-00000000000{i}", json={"title": str(i), "updatedAt": 1})
    s = client.get("/api/sync", params={"limit": 2}).json()
    assert s["more"] and len(s["notes"]) == 2
    seen = [n["title"] for n in s["notes"]]
    while s["more"]:
        s = client.get("/api/sync", params={"since": s["rev"], "limit": 2}).json()
        seen += [n["title"] for n in s["notes"]]
    assert seen == ["0", "1", "2", "3", "4"]
    assert client.get("/api/sync", params={"since": s["rev"]}).json()["notes"] == []


def test_push_applies_a_devices_queue_in_one_request(client, admin):
    client.put(f"/api/notes/{NID2}", json={"title": "server", "updatedAt": 5000})
    r = client.post("/api/sync/push", json={
        "folders": [{"id": "FFFFFFFF-0000-0000-0000-000000000001", "name": "AI", "updatedAt": 10}],
        "notes": [{"id": NID, "title": "offline", "folderID": "FFFFFFFF-0000-0000-0000-000000000001", "updatedAt": 10},
                  {"id": NID2, "title": "stale", "updatedAt": 10}],
        "tags": [{"name": "Work", "color": "red", "updatedAt": 10}]}).json()
    assert [x["status"] for x in r["notes"]] == ["ok", "stale"] and r["notes"][1]["item"]["title"] == "server"
    assert r["folders"][0]["status"] == "ok" and r["tags"][0]["item"]["color"] == "red"


def test_pictures_are_stored_in_the_database_with_a_thumbnail(client, admin):
    client.put(f"/api/notes/{NID}", json={"title": "shot", "source": "screenshot", "updatedAt": 1})
    r = client.put(f"/api/notes/{NID}/image", content=png(1600, 900), headers={"content-type": "image/png"})
    assert r.status_code == 200 and r.json()["hasImage"] and len(r.json()["imageSHA"]) == 64
    full = client.get(f"/api/notes/{NID}/image")
    assert full.headers["content-type"] == "image/png" and full.content[:4] == b"\x89PNG"
    th = client.get(f"/api/notes/{NID}/thumb")
    assert th.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/notes/{NID}/thumb", headers={"if-none-match": th.headers["etag"]}).status_code == 304
    assert client.get(f"/api/notes/{NID}").json()["image"]["width"] == 1600
    assert client.put(f"/api/notes/{NID}/image", content=b"not an image", headers={"content-type": "image/png"}).status_code == 400
    assert client.delete(f"/api/notes/{NID}/image").json()["hasImage"] is False


def test_a_picture_for_a_note_that_does_not_exist_is_refused(client, admin):
    assert client.put(f"/api/notes/{NID}/image", content=png(), headers={"content-type": "image/png"}).status_code == 404


def test_folders_delete_leaves_their_notes_in_no_folder(client, admin):
    f = client.post("/api/folders", json={"name": "Old"}).json()
    client.put(f"/api/notes/{NID}", json={"folderID": f["id"], "updatedAt": 1})
    assert client.delete(f"/api/folders/{f['id']}").json()["deleted"] is True
    assert client.get(f"/api/notes/{NID}").json()["folderID"] is None
    assert client.get("/api/folders").json()["folders"] == []


def test_tag_rename_merges_and_remove_takes_it_off(client, admin):
    client.put(f"/api/notes/{NID}", json={"tags": ["ml", "AI"], "updatedAt": 1})
    client.put(f"/api/notes/{NID2}", json={"tags": ["ML"], "updatedAt": 1})
    assert client.post("/api/tags/rename", json={"from": "ml", "to": "ai"}).json()["changed"] == 2
    assert client.get(f"/api/notes/{NID}").json()["tags"] == ["ai"]
    assert client.post("/api/tags/remove", json={"name": "AI"}).json()["changed"] == 2
    assert client.get("/api/tags").json()["tags"] == []


def test_tag_colours_sync_and_clear(client, admin):
    assert client.put("/api/tags/Work/color", json={"color": "blue"}).json()["color"] == "blue"
    s = client.get("/api/sync").json()
    assert s["tags"][0]["name"] == "Work" and s["tags"][0]["color"] == "blue"
    assert client.put("/api/tags/work/color", json={"color": None}).json()["deleted"] is True


def test_export_then_import_keeps_ids_pictures_and_folders(client, admin):
    f = client.post("/api/folders", json={"name": "Work"}).json()
    client.put(f"/api/notes/{NID}", json={"title": "With picture", "folderID": f["id"], "tags": ["x"], "updatedAt": 1})
    client.put(f"/api/notes/{NID}/image", content=png(), headers={"content-type": "image/png"})
    z = client.get("/api/export.zip").content
    from app import db
    with db.connect() as con:
        for t in ("nts_notes", "nts_note_images", "nts_folders"):
            con.execute(f"DELETE FROM {t}")
        con.commit()
    r = client.post("/api/import", files={"file": ("x.zip", z, "application/zip")}).json()
    assert r["notes"] == 1 and r["pictures"] == 1 and r["folders"] == 1
    n = client.get(f"/api/notes/{NID}").json()
    assert n["hasImage"] and n["folderID"] == f["id"] and n["tags"] == ["x"]


def test_the_change_log_records_who_did_what(client, admin):
    client.put(f"/api/notes/{NID}", json={"title": "logged", "updatedAt": time.time()})
    ch = client.get("/api/changes").json()["changes"]
    assert ch[0]["user"] == "alex" and ch[0]["action"] == "create" and ch[0]["summary"] == "logged"


def test_import_takes_a_device_notes_json_without_the_format_line(client, admin):
    import base64, json
    doc = {"notes": [{"id": NID, "title": "From the Mac", "body": "b", "createdAt": 1, "updatedAt": 2, "tags": ["t"],
                      "imageData": base64.b64encode(png()).decode()}], "tags": [{"name": "t", "color": "red", "updatedAt": 2}]}
    r = client.post("/api/import", files={"file": ("notes.json", json.dumps(doc).encode(), "application/json")}).json()
    assert r["notes"] == 1 and r["pictures"] == 1 and r["tags"] == 1
    assert client.get(f"/api/notes/{NID}").json()["hasImage"]
    bad = client.post("/api/import", files={"file": ("x.json", b'{"format": "something-else", "notes": []}', "application/json")})
    assert bad.status_code == 400


def test_a_tag_with_an_underscore_counts_only_its_own_notes(client, admin):
    """_ and % are LIKE wildcards: escaped, the count matches the notes listed (no endless "Show more")."""
    client.put(f"/api/notes/{NID}", json={"title": "a", "tags": ["project_a"], "updatedAt": 1})
    client.put(f"/api/notes/{NID2}", json={"title": "b", "tags": ["projectXa"], "updatedAt": 1})
    r = client.get("/api/notes", params={"tag": "project_a"}).json()
    assert r["total"] == 1 and [n["id"] for n in r["notes"]] == [NID]
    client.put(f"/api/notes/{NID}", json={"tags": ["café"], "updatedAt": 2})
    assert client.get("/api/notes", params={"tag": "Café"}).json()["total"] == 1


def test_a_tags_colour_follows_a_rename_and_goes_with_remove(client, admin):
    client.put(f"/api/notes/{NID}", json={"title": "a", "tags": ["old"], "updatedAt": 1})
    client.put("/api/tags/old/color", json={"color": "red"})
    client.post("/api/tags/rename", json={"from": "old", "to": "new"})
    assert {t["name"]: t["color"] for t in client.get("/api/tags").json()["tags"]} == {"new": "red"}
    assert {t["name"] for t in client.get("/api/sync").json()["tags"] if t["deleted"]} == {"old"}
    client.post("/api/tags/remove", json={"name": "new"})
    client.put(f"/api/notes/{NID}", json={"tags": ["new"], "updatedAt": time.time() + 5})
    assert {t["name"]: t["color"] for t in client.get("/api/tags").json()["tags"]} == {"new": None}


def test_deleting_a_folder_that_does_not_exist_is_a_404(client, admin):
    assert client.delete(f"/api/folders/{NID}").status_code == 404
    assert client.get("/api/sync").json()["folders"] == []


def test_removing_a_picture_takes_its_text_and_a_new_web_picture_is_read_again(client, admin):
    client.put(f"/api/notes/{NID}", json={"title": "shot", "ocrText": "old words", "source": "web", "updatedAt": 1})
    client.put(f"/api/notes/{NID}/image", content=png(), headers={"content-type": "image/png"})
    n = client.get(f"/api/notes/{NID}").json()
    assert n["ocrText"] == "" and n["updatedAt"] > 1  # a new picture on a web note: its old text goes
    client.put(f"/api/notes/{NID}", json={"ocrText": "read from it", "updatedAt": time.time() + 5})
    n = client.delete(f"/api/notes/{NID}/image").json()
    assert not n["hasImage"] and n["ocrText"] == ""
    assert client.get("/api/notes", params={"q": "read"}).json()["total"] == 0
    # a device's picture keeps the text the device read and its edit time
    client.put(f"/api/notes/{NID2}", json={"title": "mac", "ocrText": "from vision", "source": "screenshot", "updatedAt": 7})
    n = client.put(f"/api/notes/{NID2}/image", content=png(), headers={"content-type": "image/png"}).json()
    assert n["ocrText"] == "from vision" and n["updatedAt"] == 7


def test_status_rev_moves_only_with_this_accounts_changes(client, admin):
    client.put(f"/api/notes/{NID}", json={"title": "a", "updatedAt": 1})
    rev = client.get("/api/status").json()["rev"]
    client.post("/api/users", json={"name": "sam", "password": "secretpw2", "role": "editor"})
    client.cookies.clear()
    client.post("/api/auth/login", json={"name": "sam", "password": "secretpw2"})
    client.put(f"/api/notes/{NID2}", json={"title": "sam's", "updatedAt": 1})
    client.cookies.clear()
    client.post("/api/auth/login", json={"name": "alex", "password": "secretpw1"})
    assert client.get("/api/status").json()["rev"] == rev


def test_a_chunked_body_is_held_to_the_size_limit(client, admin):
    def chunks():
        for _ in range(10):
            yield b"x" * (1 << 20)
    r = client.put(f"/api/notes/{NID}", content=chunks(), headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_the_saved_database_password_only_goes_to_its_own_server(client, admin):
    r = client.post("/api/db/test", json={"type": "mysql", "host": "203.0.113.9", "port": 3306, "user": "x", "keep_password": True}).json()
    assert not r["ok"] and "password" in r["error"]
    assert client.post("/api/db/save", json={"type": "mysql", "host": "203.0.113.9"}).status_code == 400


def test_an_import_does_not_take_a_neighbours_picture(client, admin):
    """Work/Meeting.md has no picture; Work/Meeting.v2.png belongs to Meeting.v2."""
    import io as _io
    import json as _json
    import zipfile as _zip
    buf = _io.BytesIO()
    with _zip.ZipFile(buf, "w") as z:
        z.writestr("notes.json", _json.dumps({"notes": [{"id": NID, "title": "Meeting", "updatedAt": 1}, {"id": NID2, "title": "Meeting.v2", "updatedAt": 1}]}))
        z.writestr("Meeting.md", f"---\nid: {NID}\n---\n")
        z.writestr("Meeting.v2.md", f"---\nid: {NID2}\n---\n")
        z.writestr("Meeting.v2.png", png())
    r = client.post("/api/import", files={"file": ("x.zip", buf.getvalue(), "application/zip")}).json()
    assert r["pictures"] == 1
    assert not client.get(f"/api/notes/{NID}").json()["hasImage"] and client.get(f"/api/notes/{NID2}").json()["hasImage"]
