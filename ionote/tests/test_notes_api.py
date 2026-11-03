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
        for t in ("notes", "note_images", "folders"):
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
