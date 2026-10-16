"""The change log: every change is recorded with before/after, and can be undone or restored from backups."""
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from app import edits, index


def test_an_edit_is_logged_and_can_be_undone(client, lib):
    if not edits.available():
        pytest.skip("exiftool not available")
    index.ensure_fresh()
    con = index.open_index()
    pid, title = con.execute("SELECT id, title FROM photos WHERE video = 0 AND id IN (%s) LIMIT 1" % ",".join(map(str, lib["ids"][3:]))).fetchone()
    con.close()
    assert client.post("/api/edit", json={"ids": [pid], "changes": {"title": "History probe"}}).status_code == 200
    h = client.get("/api/history", params={"photo": pid}).json()
    e = h["entries"][0]
    assert e["action"] == "edit" and "History probe" in e["summary"] and "undo" in e["restore"], e
    assert "sidecar" in e["restore"] or not os.path.exists(e.get("path", "") + ".xmp")
    r = client.post(f"/api/history/{e['id']}/restore", json={"kind": "undo"})
    assert r.status_code == 200, r.text
    assert (client.get(f"/api/photo/{pid}").json()["title"] or "") == (title or ""), "the title is back (the edit resolved itself: digiKam agrees again)"
    assert client.get("/api/history", params={"photo": pid}).json()["entries"][0]["action"] == "restore"
    client.post("/api/edit/revert", json={"ids": [pid]})


def test_a_deleted_photo_can_be_restored(client, lib):
    index.ensure_fresh()
    con = index.open_index()
    # a still nobody else relies on: no faces, no GPS, the lowest id (the restored photo gets a new id)
    # a still no other test names: not among the first ids (the fixtures), not one with faces; the restored
    # photo gets a new id, which takes the old one's place in lib["ids"] for the tests that follow
    candidates = [i for i in lib["ids"][4:] if i not in lib["with_faces"][:2]]
    row = con.execute(f"SELECT id, path, album_id FROM photos WHERE video = 0 AND id IN ({','.join(map(str, candidates))}) ORDER BY id DESC LIMIT 1").fetchone()
    pid, path, album = row
    con.close()
    keep = Path(path + ".keep"); shutil.copy2(path, keep)
    r = client.post("/api/photos/delete", json={"ids": [pid], "confirm": True})
    assert r.status_code == 200 and r.json()["deleted"] == 1, r.text
    backup = r.json()["backup"]
    e = client.get("/api/history", params={"photo": pid, "action": "deleted"}).json()["entries"][0]
    assert "deleted" in e["restore"], e
    r = client.post(f"/api/history/{e['id']}/restore", json={"kind": "deleted"})
    assert r.status_code == 200, r.text
    new_id = r.json()["id"]
    assert os.path.exists(path)
    db = sqlite3.connect(lib["db"])
    assert db.execute("SELECT album, name FROM Images WHERE id = ?", (new_id,)).fetchone()[0] == album
    db.close()
    lib["ids"][lib["ids"].index(pid)] = new_id
    if pid in lib["with_faces"]:
        lib["with_faces"][lib["with_faces"].index(pid)] = new_id
    acts = [x["action"] for x in client.get("/api/history", params={"photo": new_id}).json()["entries"]]
    assert acts[:2] == ["restore", "deleted"], "the history follows the photo to its new id"
    keep.unlink()
    shutil.rmtree(backup, ignore_errors=True)
