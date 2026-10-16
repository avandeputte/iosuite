"""Face quality: a person's face stored twice a few pixels apart is found and cleaned up (one kept, sidecar
rewritten from the database, file date recorded, change log written); separate regions and broken rectangles
are only reported; the viewer itself refuses to make such a duplicate."""
import re
import sqlite3
import time

import pytest

from app import dkdb, edits, facemgr, facequality, index


def _regions(db, pid, tag):
    con = sqlite3.connect(db)
    try:
        return [r[0] for r in con.execute("SELECT value FROM ImageTagProperties WHERE imageid = ? AND tagid = ? AND property = 'tagRegion'", (pid, tag))]
    finally:
        con.close()


def test_near_duplicates_are_found_and_removed(client, lib):
    if not edits.available():
        pytest.skip("exiftool is not available here")
    pid = lib["with_faces"][1]
    con = sqlite3.connect(lib["db"])
    tag, val = con.execute("SELECT tagid, value FROM ImageTagProperties WHERE imageid = ? AND property = 'tagRegion' LIMIT 1", (pid,)).fetchone()
    x, y, w, h = map(int, re.search(r'x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)"', val).groups())
    dup = f'<rect x="{x + 1}" y="{y}" width="{w}" height="{h}"/>'
    far = f'<rect x="{x + 3 * w}" y="{y}" width="{w}" height="{h}"/>'
    con.execute("INSERT INTO ImageTagProperties (imageid, tagid, property, value) VALUES (?,?,?,?)", (pid, tag, "tagRegion", dup))
    con.execute("INSERT INTO ImageTagProperties (imageid, tagid, property, value) VALUES (?,?,?,?)", (pid, tag, "tagRegion", far))
    con.commit(); con.close()
    s = facequality.scan()
    assert any(n["photo"] == pid and n["tag"] == tag and n["drop"] == [dup] and n["apart"] == 1 for n in s["near"]), s["near"][:3]
    assert any(x_["photo"] == pid for x_ in s["separate"]), "the region three widths away is a separate one: reported only"
    # the viewer will not make one itself
    with pytest.raises(dkdb.SyncError, match="already has a face there"):
        facemgr.apply({"op": "add", "image": pid, "rect": [x, y + 2, w, h], "tag": tag}, check_running=False)
    n = facequality.fix_near_duplicates(check_running=False)
    assert n >= 1
    for _ in range(200):
        if not facequality.progress["running"]:
            break
        time.sleep(0.1)
    p = facequality.progress
    assert p["error"] is None and p["removed"] >= 1, p
    left = _regions(lib["db"], pid, tag)
    assert val in left and dup not in left and far in left, left
    assert not [n for n in facequality.scan()["near"] if n["photo"] == pid]
    # the sidecar says what the database says, and digiKam's file date follows it
    ic = index.open_index(); path = ic.execute("SELECT path FROM photos WHERE id = ?", (pid,)).fetchone()[0]; ic.close()
    side = open(path + ".xmp", encoding="utf-8").read()
    assert side.count("mwg-rs:Name") or side.count("<mwg-rs:Name>"), "regions written"
    con = sqlite3.connect(lib["db"]); md = con.execute("SELECT modificationDate FROM Images WHERE id = ?", (pid,)).fetchone()[0]; con.close()
    assert md == dkdb.file_stamp(path)[0]
    h_ = client.get(f"/api/history?photo={pid}").json()
    assert any("Duplicate face regions removed" in e["summary"] and "sidecar" in e["restore"] for e in h_["entries"]), h_
    con = sqlite3.connect(lib["db"])
    con.execute("DELETE FROM ImageTagProperties WHERE imageid = ? AND tagid = ? AND value = ?", (pid, tag, far)); con.commit(); con.close()


def test_report_endpoint_is_for_admins_and_lists_counts(client, lib):
    r = client.get("/api/quality")
    assert r.status_code == 200, r.text
    q = r.json()
    assert {"near", "separate", "invalid", "progress", "checked"} <= set(q) and q["checked"] > 0


def test_image_files_with_the_duplicates_are_rewritten_too(client, lib):
    if not edits.available():
        pytest.skip("exiftool is not available here")
    from app import vdb
    ic = index.open_index()
    jpegs = {r[0] for r in ic.execute("SELECT id FROM photos WHERE lower(path) LIKE '%.jpg' OR lower(path) LIKE '%.jpeg'")}
    ic.close()
    cand = [i for i in lib["with_faces"][2:] if i in jpegs]
    if not cand:
        pytest.skip("no JPEG with faces in the fixture")
    pid = cand[0]
    con = sqlite3.connect(lib["db"])
    tag, val = con.execute("SELECT tagid, value FROM ImageTagProperties WHERE imageid = ? AND property = 'tagRegion' LIMIT 1", (pid,)).fetchone()
    x, y, w, h = map(int, re.search(r'x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)"', val).groups())
    dup = f'<rect x="{x}" y="{y + 1}" width="{w}" height="{h}"/>'
    con.execute("INSERT INTO ImageTagProperties (imageid, tagid, property, value) VALUES (?,?,?,?)", (pid, tag, "tagRegion", dup))
    con.commit(); con.close()
    ic = index.open_index(); path = ic.execute("SELECT path FROM photos WHERE id = ?", (pid,)).fetchone()[0]; ic.close()
    if not edits.can_write_file(path):
        pytest.skip("not a JPEG")
    assert facemgr.write_regions_many([pid], files=True, sidecars=False)[pid] == "written"  # the file now carries the pair, as digiKam wrote it
    mwg, mp = facequality._file_regions([path])[path]
    assert facequality._has_duplicates(mwg, mp)
    assert facequality.fix_near_duplicates(check_running=False) >= 1
    for _ in range(200):
        if not facequality.progress["running"]:
            break
        time.sleep(0.1)
    assert facequality._has_duplicates(*facequality._file_regions([path])[path]), "the first pass leaves the image files alone"
    n = facequality.fix_files()
    assert n >= 1
    for _ in range(300):
        if not facequality.progress["running"]:
            break
        time.sleep(0.1)
    p = facequality.progress
    assert p["files"] and p["error"] is None and p["photos"] >= 1 and p["errors"] == 0, p
    mwg, mp = facequality._file_regions([path])[path]
    assert not facequality._has_duplicates(mwg, mp) and len(mwg) >= 1
    assert edits.file_backup_path(path).exists(), "the original file is kept in file-backups"
    con = vdb.connect()
    try:
        assert con.execute("SELECT count(*) FROM photo_history WHERE photo_id = ? AND summary = ?", (pid, facequality.FILE_DONE)).fetchone()[0] == 1
    finally:
        con.close()
    assert facequality.fix_files() == 0 or facequality.progress["photos"] == 0, "a second run finds nothing left to do"
