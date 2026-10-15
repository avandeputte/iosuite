"""The viewer's copy of the library (the lib_* tables): the index is built from it when digiKam's
database cannot be read or Sync with digiKam is off, editing keeps working meanwhile and the queued
edits reach digiKam's database when it is back, and photo_ids lets viewer data follow a photo that
digiKam renumbered."""
import shutil
import sqlite3
import time
from pathlib import Path

import pytest

from app import dbsync, dkdb, edits, index, state


def _count(table: str) -> int:
    con = state.connect()
    try:
        return con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    finally:
        con.close()


def _index_photos() -> int:
    con = index.open_index()
    try:
        return con.execute("SELECT count(*) FROM photos").fetchone()[0]
    finally:
        con.close()


def _renumber(db: Path, old: int, new: int):
    """What a re-import does to one photo: the same file under another image id, in every table."""
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys = OFF")
    con.execute("UPDATE Images SET id = ? WHERE id = ?", (new, old))
    for t in ("ImageInformation", "ImageMetadata", "ImagePositions", "ImageComments", "ImageCopyright", "ImageProperties",
              "ImageTags", "ImageTagProperties", "VideoMetadata", "ImageHistory"):
        try:
            con.execute(f"UPDATE {t} SET imageid = ? WHERE imageid = ?", (new, old))
        except sqlite3.OperationalError:
            pass
    con.commit()
    con.close()


def test_copy_follows_digikam_and_every_photo_has_a_viewer_id(client):
    index.ensure_fresh()
    m = index.mirror_info()
    assert m and m["source"] == dkdb.source_version()
    assert m["photos"] == _count("lib_images") > 0
    assert _count("photo_ids") == m["photos"]
    assert _count("lib_tags") > 0 and _count("lib_imagetags") > 0 and _count("lib_albums") > 0
    s = client.get("/api/status").json()["digikam"]
    assert s["sync"] and s["reachable"] and s["source"] == "digikam" and s["mirror"]["photos"] == m["photos"]


def test_index_builds_from_the_copy_while_digikam_is_unreachable_and_edits_still_work(client, lib, photo_id, monkeypatch):
    index.ensure_fresh()
    n = _index_photos()
    dbf = Path(lib["db"])
    gone = Path(str(dbf) + ".gone")
    shutil.move(dbf, gone)
    try:
        assert index.probe()[0] == "mirror" and index.offline["since"]
        assert index.ensure_fresh() is False, "the copy is what the index was last built from: nothing changed"
        stats = index.build()
        assert stats["photos"] == n and index.last_source["kind"] == "mirror"
        s = client.get("/api/status").json()["digikam"]
        assert s["sync"] and not s["reachable"] and s["source"] == "mirror"
        assert edits.digikam_tag_paths([photo_id])[photo_id] is not None, "tag paths come from the copy"
        if edits.available():
            r = client.post("/api/edit", json={"ids": [photo_id], "changes": {"rating": 4}})
            assert r.status_code == 200, r.text
            assert edits.pending().get(photo_id, {}).get("rating") == 4
    finally:
        shutil.move(gone, dbf)
    assert index.probe()[0] == "digikam" and index.offline["since"] is None
    if not edits.available():
        return
    # back online and digiKam closed (vouched, DIGIKAM_CHECK=ask): the queued edit goes into digiKam's database
    from app import main
    main._auto["at"] = 0
    monkeypatch.setattr(edits, "newest_pending", lambda: int(time.time()) - 120)
    main._refresh(initial=True)  # initial: no 'digiKam wrote seconds ago' wait, the scratch file is brand new
    assert main.state["error"] is None, main.state["error"]
    assert main._auto["at"] > 0, "the automatic apply ran"
    con = sqlite3.connect(dbf)
    assert con.execute("SELECT rating FROM ImageInformation WHERE imageid = ?", (photo_id,)).fetchone()[0] == 4
    con.close()
    index.ensure_fresh()  # digiKam now agrees, so the remembered edit is dropped
    assert photo_id not in edits.pending()


def test_sync_off_keeps_digikam_closed_and_the_viewer_on_its_copy(client, photo_id):
    index.ensure_fresh()
    assert client.post("/api/settings", json={"digikam_sync": False}).status_code == 200
    try:
        assert client.get("/api/status").json()["digikam"]["sync"] is False
        assert client.get("/api/settings").json()["digikam_sync"] is False
        with pytest.raises(dkdb.SyncError):
            dkdb.connect()
        with pytest.raises(dkdb.SyncError):
            with dbsync.write_transaction():
                pass
        stats = index.build()
        assert stats["photos"] > 0 and index.last_source["kind"] == "mirror"
        assert isinstance(edits.digikam_tag_paths([photo_id])[photo_id], list)
    finally:
        client.post("/api/settings", json={"digikam_sync": True})
    assert index.probe()[0] == "digikam"


def test_viewer_data_follows_a_photo_digikam_renumbered(client, lib):
    index.ensure_fresh()
    pid = lib["ids"][1]
    con = state.connect()
    try:
        vid, uhash = con.execute("SELECT vid, hash FROM photo_ids WHERE dk_id = ?", (pid,)).fetchone()
        new = con.execute("SELECT max(dk_id) FROM photo_ids").fetchone()[0] + 1000
    finally:
        con.close()
    state.set_favorites([(pid, uhash)], True)
    assert pid in state.favorite_ids()
    _renumber(Path(lib["db"]), pid, new)
    try:
        index.build()
        assert new in state.favorite_ids() and pid not in state.favorite_ids(), "the favorite followed the file"
        con = state.connect()
        try:
            assert con.execute("SELECT dk_id FROM photo_ids WHERE vid = ?", (vid,)).fetchone()[0] == new, "same viewer id, new digiKam id"
            assert con.execute("SELECT count(*) FROM photo_ids WHERE dk_id = ?", (pid,)).fetchone()[0] == 0
        finally:
            con.close()
    finally:
        _renumber(Path(lib["db"]), new, pid)
        index.build()
    assert pid in state.favorite_ids()
    state.set_favorites([(pid, uhash)], False)
