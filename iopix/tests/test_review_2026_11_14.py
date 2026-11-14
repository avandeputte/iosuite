"""What the code review of 14 November 2026 settled for the digiKam writers (these need the test library, like the
rest of the library tests): a background trash names who did it, a half-failed move goes back, "restore original"
waits for the rotates and crops from that entry on to be undone, and the scanner rereads a file the viewer changed."""
import os
import shutil
import sqlite3

from app.data import index
from app.photos import edits, lossless, organize, scanner
from helpers import _face_jpeg, need_tool


def _path(pid):
    ic = index.open_index()
    try:
        r = ic.execute("SELECT path FROM photos WHERE id = ?", (pid,)).fetchone()
        return r[0] if r else None
    finally:
        ic.close()


def _row(db, pid):
    con = sqlite3.connect(db)
    try:
        return con.execute("SELECT album, name, status, modificationDate, uniqueHash FROM Images WHERE id = ?", (pid,)).fetchone()
    finally:
        con.close()


def test_a_trash_in_the_background_names_who_did_it(client, lib):
    pid = lib["ids"][43]
    r = client.post("/api/photos/trash", json={"ids": [pid], "background": True})
    j = client.get(f"/api/photos/trash/{r.json()['job']}?wait=20").json()
    assert j["trashed"] == [pid], j
    e = client.get(f"/api/history?photo={pid}&limit=1").json()["entries"][0]
    assert e["action"] == "trashed" and e["user"] == "visitor", e  # open mode: the request's name, not "system"
    index.build()
    assert client.post("/api/trash/restore", json={"infos": j["infos"]}).json()["restored"] == [pid]


def test_a_move_whose_sidecar_cannot_follow_goes_back(client, lib, monkeypatch):
    pid = lib["ids"][44]
    path = _path(pid)
    side = path + ".xmp"
    made = not os.path.exists(side)
    if made:
        open(side, "w").write("<x:xmpmeta xmlns:x='adobe:ns:meta/'/>\n")
    before = _row(lib["db"], pid)
    folders = client.get("/api/folders").json()["folders"]
    other = next(f for f in folders if f["id"] != before[0] and f["rel"] != "/")
    real = shutil.move

    def move(src, dst):
        if str(src).endswith(".xmp") and str(src) == side:
            raise OSError("no room for the sidecar")
        return real(src, dst)
    monkeypatch.setattr(organize.shutil, "move", move)
    try:
        r = client.post("/api/photos/move", json={"ids": [pid], "album": other["id"]})
        assert r.status_code == 200 and r.json()["failed"] and not r.json()["moved"], r.text
        assert os.path.exists(path) and os.path.exists(side), "the file came back beside its sidecar"
        assert _row(lib["db"], pid)[:3] == before[:3]
    finally:
        monkeypatch.undo()
        if made:
            os.remove(side)


def test_restore_original_waits_for_the_rotates_from_there_on(client, lib):
    need_tool("jpegtran", lossless.jpegtran())
    from app.photos import history as h
    pid, path, _face, _dims = _face_jpeg(lib)
    path = str(path)
    b = edits.file_backup_path(path)
    b.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, b)
    try:
        h.record([{"photo_id": pid, "action": "face", "summary": "Face region removed", "details": {"op": "remove", "rect": [1, 2, 3, 4]}}])
        face = client.get(f"/api/history?photo={pid}&limit=1").json()["entries"][0]
        assert client.post("/api/photos/transform", json={"ids": [pid], "op": "right"}).status_code == 200
        turn = client.get(f"/api/history?photo={pid}&limit=1").json()["entries"][0]
        assert turn["action"] == "lossless" and "original" not in turn["restore"] and "undo" in turn["restore"]
        r = client.post(f"/api/history/{face['id']}/restore", json={"kind": "original"})
        assert r.status_code in (400, 409) and "Undo the 1" in r.text, r.text
        assert client.post(f"/api/history/{turn['id']}/restore", json={"kind": "undo"}).status_code == 200
        r = client.post(f"/api/history/{face['id']}/restore", json={"kind": "original"})
        assert r.status_code == 200, r.text
        assert open(path, "rb").read() == open(b, "rb").read()
    finally:
        b.unlink(missing_ok=True)


def test_the_scanner_rereads_a_file_the_viewer_changed(client, lib):
    """A rotate leaves the row without its stamp ("look at this file again"); without digiKam the scanner does that."""
    need_tool("jpegtran", lossless.jpegtran())
    pid, path, _face, _dims = _face_jpeg(lib)
    assert client.post("/api/photos/transform", json={"ids": [pid], "op": "left"}).status_code == 200
    e = client.get(f"/api/history?photo={pid}&limit=1").json()["entries"][0]
    try:
        assert _row(lib["db"], pid)[3] is None
        s = scanner.scan()
        assert s["error"] is None and s["modified"] >= 1, s
        row = _row(lib["db"], pid)
        con = sqlite3.connect(lib["db"])
        version = scanner.hash_version(con)
        con.close()
        assert row[3] and row[4] == scanner.unique_hash(str(path), version)
    finally:
        client.post(f"/api/history/{e['id']}/restore", json={"kind": "undo"})
