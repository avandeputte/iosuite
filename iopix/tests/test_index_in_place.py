"""The search index updated in place: a change to a few photos rewrites their rows (and the counts and covers that
hang on them) instead of building the whole index, and what is left is, table for table, what a full build gives.
Anything the index cannot tell the extent of (a change made elsewhere, a tag renamed) still builds it whole."""
import os
import sqlite3
import time

import pytest

from app import config
from app.data import index
from app.faces import facemgr
from app.photos import edits
from helpers import need_tool, wait_for

TABLES = ("photos", "fts", "tags", "tag_closure", "photo_tags", "albums", "album_closure", "faces", "pending_seen")


def _meta(path=None) -> dict:
    con = index.open_index(path or config.INDEX_DB)
    try:
        return dict(con.execute("SELECT key, value FROM meta"))
    finally:
        con.close()


def _tables(path) -> dict:
    con = index.open_index(path)
    try:
        return {t: sorted(con.execute(f"SELECT {'rowid, ' if t == 'fts' else ''}* FROM {t}").fetchall(), key=repr) for t in TABLES}
    finally:
        con.close()


def _row(pid: int) -> dict:
    con = index.open_index()
    con.row_factory = sqlite3.Row
    try:
        r = con.execute("SELECT * FROM photos WHERE id = ?", (pid,)).fetchone()
        return dict(r) if r else None
    finally:
        con.close()


def _one(sql: str, *args):
    con = index.open_index()
    try:
        r = con.execute(sql, args).fetchone()
        return r[0] if r else None
    finally:
        con.close()


class _file:
    """The index file as it is now: a full build swaps another file in, an update in place keeps this one."""

    def __init__(self):
        self.fd = os.open(config.INDEX_DB, os.O_RDONLY)

    def kept(self) -> bool:
        return os.fstat(self.fd).st_nlink > 0

    def __del__(self):
        os.close(self.fd)


def _settled():
    """The index up to date, with nothing in the background still to come (sidecars being written, the watcher's own look)."""
    assert wait_for(lambda: facemgr.sidecars_pending() == 0, 30)
    index.ensure_fresh()


def _assert_like_a_full_build(tmp_path, but=()):
    """The index as it stands holds what a full build made right now would hold (`but`: photo columns left out)."""
    _settled()
    full = tmp_path / f"full-{time.time_ns()}.db"
    index.build(full)
    live, fresh = _tables(config.INDEX_DB), _tables(full)
    skip = [index._COLS.index(c) for c in but]
    for t in TABLES:
        a, b = live[t], fresh[t]
        if t == "photos" and skip:
            a, b = ([tuple(v for k, v in enumerate(r) if k not in skip) for r in rows] for rows in (a, b))
        assert len(a) == len(b), f"{t}: {len(a)} rows in the index updated in place, {len(b)} in a full build"
        diff = [(x, y) for x, y in zip(a, b) if x != y]
        assert not diff, f"{t}: {len(diff)} rows differ from a full build, the first: {diff[0]}"
    lm, fm = _meta(), _meta(full)
    assert lm["version"] == fm["version"] and lm["photos"] == fm["photos"]


@pytest.fixture
def clean(client, lib):
    """Start from a full build with no edits waiting, and leave the library that way."""
    need_tool("exiftool")

    def no_edits():
        pend = list(edits.pending())  # what a test (here or in a module before this one) left behind
        if pend:
            client.post("/api/edit/revert", json={"ids": pend})
            edits.forget(list(edits.pending()))
        assert wait_for(lambda: facemgr.sidecars_pending() == 0, 30)
        index.build()

    no_edits()
    yield
    no_edits()
    from app import main
    main.refresh(initial=True)  # the server's own view of the index, for the tests that follow


def _edit(client, pid, **changes):
    r = client.post("/api/edit", json={"ids": [pid], "changes": changes})
    assert r.status_code == 200 and r.json()["edited"] == 1, r.text
    index.ensure_fresh()


def test_an_edit_rewrites_only_that_photo(client, lib, clean, tmp_path):
    pid, file = lib["ids"][0], _file()
    _edit(client, pid, rating=4, title="Zz in place title")
    assert file.kept() and int(_meta()["patches"]) >= 1, "the index was updated where it is, not built anew"
    row = _row(pid)
    assert (row["rating"], row["title"], row["edited"]) == (4, "Zz in place title", 1)
    assert _one("SELECT rowid FROM fts WHERE fts MATCH 'title:zz'") == pid, "the new title is searchable"
    _assert_like_a_full_build(tmp_path)

    # a tag the photo did not have: the tag's counts (and its parents') follow
    tag = _one("SELECT t.id FROM tags t WHERE t.person = 0 AND t.id NOT IN (SELECT tag_id FROM photo_tags WHERE photo_id = ?) ORDER BY t.id", pid)
    n = _one("SELECT n FROM tags WHERE id = ?", tag)
    _edit(client, pid, add_tags=[tag])
    assert _one("SELECT n FROM tags WHERE id = ?", tag) == n + 1 and _one("SELECT 1 FROM photo_tags WHERE tag_id = ? AND photo_id = ?", tag, pid)
    _assert_like_a_full_build(tmp_path)

    # a place: the photo moves on the map and its place names change
    _edit(client, pid, gps={"lat": 50.8467, "lon": 4.3525})
    assert abs(_row(pid)["lat"] - 50.8467) < 1e-6
    _assert_like_a_full_build(tmp_path)
    assert file.kept(), "three edits, no full build"

    # undone: the row is digiKam's again
    assert client.post("/api/edit/revert", json={"ids": [pid]}).status_code == 200
    index.ensure_fresh()
    row = _row(pid)
    assert row["edited"] == 0 and row["title"] != "Zz in place title" and file.kept()
    assert _one("SELECT n FROM tags WHERE id = ?", tag) == n
    _assert_like_a_full_build(tmp_path)


def test_a_date_edit_moves_the_folder_dates_and_asks_for_the_full_build_soon(client, lib, clean, tmp_path):
    pid, file = lib["ids"][1], _file()
    album = _row(pid)["album_id"]
    _edit(client, pid, taken="1971-02-03T04:05:06")
    assert file.kept()
    assert _row(pid)["day"] == "1971-02-03" and _one("SELECT ts_min FROM albums WHERE id = ?", album) == _row(pid)["ts"]
    assert index._patched["soon"], "bursts are found from the dates: the full build follows within a minute, not ten"
    _assert_like_a_full_build(tmp_path, but=("burst", "burst_best", "reject"))
    assert not index._full_build_due()
    index._patched["at"] -= index.RECONCILE_SOON_S + 1  # a minute later
    assert index._full_build_due() and index.ensure_fresh() and not file.kept(), "the full build that follows"
    assert "patches" not in _meta() and not index._full_build_due()


def test_edits_written_to_digikam_update_the_index_in_place(client, lib, clean, tmp_path):
    pid, file = lib["ids"][2], _file()
    was = _row(pid)["rating"]
    _edit(client, pid, rating=(was % 5) + 1 if was and was > 0 else 3)
    want = _row(pid)["rating"]
    try:
        r = client.post("/api/edits/db", json={})
        assert r.status_code == 200 and r.json()["applied"] == 1, r.text
        row = _row(pid)
        assert file.kept(), "the database changed by this viewer's own, named write: no full build"
        assert (row["rating"], row["edited"]) == (want, 0) and not edits.pending_count(), "digiKam's database has it: nothing waits any more"
        _assert_like_a_full_build(tmp_path)
        assert file.kept() and not index.ensure_fresh(), "and the index knows it is up to date"
    finally:
        _edit(client, pid, rating=max(was, 0))
        client.post("/api/edits/db", json={})


def test_a_face_change_updates_the_index_in_place(client, lib, clean, tmp_path):
    con = index.open_index()
    try:
        face = con.execute("SELECT photo_id, x, y, w, h FROM faces WHERE kind = 'confirmed' AND w > 20 AND h > 20 ORDER BY photo_id").fetchone()
    finally:
        con.close()
    if not face:
        pytest.skip("no named face in this library")
    pid, rect = face[0], list(face[1:])
    moved = [rect[0] + 1, rect[1] + 1, rect[2] - 2, rect[3] - 2]
    file = _file()
    r = client.post("/api/faces/op", json={"op": "move", "image": pid, "rect": rect, "new_rect": moved})
    assert r.status_code == 200, r.text
    try:
        _settled()
        assert file.kept(), "a face moved: that photo's rows, not the whole index"
        assert _one("SELECT 1 FROM faces WHERE photo_id = ? AND x = ? AND y = ? AND w = ? AND h = ?", pid, *moved)
        _assert_like_a_full_build(tmp_path)
    finally:
        assert client.post("/api/faces/op", json={"op": "move", "image": pid, "rect": moved, "new_rect": rect}).status_code == 200
        _settled()


def _digikam(lib, sql, *args):
    con = sqlite3.connect(lib["db"], timeout=15)
    try:
        con.execute(sql, args)
        con.commit()
    finally:
        con.close()


def test_a_change_made_elsewhere_builds_the_whole_index(client, lib, clean):
    pid, file = lib["ids"][3], _file()
    was = _row(pid)["rating"]
    _digikam(lib, "UPDATE ImageInformation SET rating = ? WHERE imageid = ?", 5 if was != 5 else 4, pid)  # as digiKam would
    try:
        assert index.ensure_fresh() and not file.kept(), "which photos changed is not known: everything is read again"
        assert _row(pid)["rating"] == (5 if was != 5 else 4)
    finally:
        _digikam(lib, "UPDATE ImageInformation SET rating = ? WHERE imageid = ?", was, pid)
        index.ensure_fresh()


def test_a_change_elsewhere_next_to_a_named_write_builds_the_whole_index(client, lib, clean):
    """The viewer names the photos it writes; a change by someone else just before is not theirs, and is not missed."""
    a, b = lib["ids"][3], lib["ids"][4]
    was_a, was_b, file = _row(a)["rating"], _row(b)["rating"], _file()
    _digikam(lib, "UPDATE ImageInformation SET rating = ? WHERE imageid = ?", 5 if was_a != 5 else 4, a)  # digiKam, unseen so far
    time.sleep(0.01)
    try:
        with index.writing([b]):
            _digikam(lib, "UPDATE ImageInformation SET rating = ? WHERE imageid = ?", 5 if was_b != 5 else 4, b)
        assert index.ensure_fresh() and not file.kept()
        assert _row(a)["rating"] == (5 if was_a != 5 else 4) and _row(b)["rating"] == (5 if was_b != 5 else 4)
    finally:
        _digikam(lib, "UPDATE ImageInformation SET rating = ? WHERE imageid = ?", was_a, a)
        _digikam(lib, "UPDATE ImageInformation SET rating = ? WHERE imageid = ?", was_b, b)
        index.ensure_fresh()


def test_a_named_write_alone_is_taken_in_place(client, lib, clean, tmp_path):
    b = lib["ids"][4]
    was, file = _row(b)["rating"], _file()
    try:
        with index.writing([b]):
            _digikam(lib, "UPDATE ImageInformation SET rating = ? WHERE imageid = ?", 5 if was != 5 else 4, b)
        assert index.ensure_fresh() and file.kept() and _row(b)["rating"] == (5 if was != 5 else 4)
        _assert_like_a_full_build(tmp_path)
    finally:
        with index.writing([b]):
            _digikam(lib, "UPDATE ImageInformation SET rating = ? WHERE imageid = ?", was, b)
        index.ensure_fresh()


def test_a_renamed_tag_builds_the_whole_index(client, lib, clean):
    """A tag's name is in the text of every photo that carries it: not something to patch photo by photo."""
    con = index.open_index()
    try:
        tag, name, pid = con.execute("SELECT t.id, t.name, pt.photo_id FROM tags t JOIN photo_tags pt ON pt.tag_id = t.id ORDER BY t.person, t.id").fetchone()
    finally:
        con.close()
    file = _file()
    try:
        with index.writing([pid]):
            _digikam(lib, "UPDATE Tags SET name = ? WHERE id = ?", name + " zzrenamed", tag)
        assert index.ensure_fresh() and not file.kept()
        assert _one("SELECT name FROM tags WHERE id = ?", tag) == name + " zzrenamed"
        assert _one("SELECT count(*) FROM fts WHERE fts MATCH 'zzrenamed'") >= _one("SELECT n FROM tags WHERE id = ?", tag) >= 1, "every photo that carries it says so"
    finally:
        _digikam(lib, "UPDATE Tags SET name = ? WHERE id = ?", name, tag)
        index.ensure_fresh()


def test_an_update_cut_short_builds_the_index_anew(client, lib, clean):
    """The marker an update in place leaves while it writes: found afterwards, the file is not trusted."""
    file = _file()
    marker = index._marker(config.INDEX_DB)
    marker.touch()
    assert index.ensure_fresh() and not file.kept() and not marker.exists()


def test_what_is_ranked_across_the_library_is_kept_until_the_full_build(client, lib, clean):
    pid = lib["ids"][5]
    con = sqlite3.connect(str(config.INDEX_DB))
    try:
        con.execute("PRAGMA journal_mode = MEMORY")
        con.execute("UPDATE photos SET sharpn = 0.5, focusn = 0.25, aesthn = 0.75, burst = 7, burst_best = 1, reject = 'blur', ocr = 'kept words' WHERE id = ?", (pid,))
        con.commit()
    finally:
        con.close()
    file = _file()
    _edit(client, pid, title="Zz ranked")
    row = _row(pid)
    assert file.kept() and row["title"] == "Zz ranked"
    assert [row[c] for c in index._CARRIED] == [0.5, 0.25, 0.75, 7, 1, "blur", "kept words"]
    assert _one("SELECT ocr FROM fts WHERE rowid = ?", pid) == "kept words"


def test_the_full_build_follows_once_things_are_quiet(client, lib, clean):
    pid, file = lib["ids"][6], _file()
    _edit(client, pid, title="Zz quiet")
    assert file.kept() and not index._full_build_due()
    index._patched["at"] -= index.RECONCILE_S + 1  # ten minutes later
    assert index._full_build_due()
    index._patched["n"] = None  # a restart in between: the index file remembers
    con = sqlite3.connect(str(config.INDEX_DB))
    try:
        con.execute("PRAGMA journal_mode = MEMORY")
        con.execute("UPDATE meta SET value = ? WHERE key = 'patched'", (str(time.time() - index.RECONCILE_S - 1),))
        con.commit()
    finally:
        con.close()
    assert index._full_build_due() and index.ensure_fresh() and not file.kept()
    assert _row(pid)["title"] == "Zz quiet" and not index._full_build_due() and not index.ensure_fresh()


def test_switched_off_every_change_builds_the_index(client, lib, clean, monkeypatch):
    monkeypatch.setattr(config, "INDEX_PATCH", False)
    pid, file = lib["ids"][7], _file()
    _edit(client, pid, title="Zz whole")
    assert not file.kept() and "patches" not in _meta() and _row(pid)["title"] == "Zz whole"
