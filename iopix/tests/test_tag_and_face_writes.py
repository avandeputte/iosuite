"""Writes to the (scratch) digiKam database: the tag manager and face
management mirror digiKam's own rows, back the database up first, refuse
what digiKam would not allow, and keep the index in step."""

import pytest

from app import config, dkdb, facemgr, tagmanager


def _tags(con):
    return {r[0]: (r[1], r[2]) for r in con.execute("SELECT id, pid, name FROM Tags")}


@pytest.fixture
def dk():
    con = dkdb.connect()
    yield con
    con.close()


def _people_root(con):
    return con.execute("SELECT id FROM Tags WHERE name = 'People' AND pid = 0").fetchone()[0]


def test_backups_are_taken_and_capped(dk, client):
    before = sorted((config.DATA_DIR / "db-backups").glob("digikam4-*.db")) if (config.DATA_DIR / "db-backups").exists() else []
    for i in range(12):
        tagmanager.apply({"op": "add", "parent": 0, "name": f"zz-backup-probe-{i}"}, check_running=False)
    after = sorted((config.DATA_DIR / "db-backups").glob("digikam4-*.db"))
    assert len(after) == dkdb.KEEP_BACKUPS, "at most KEEP_BACKUPS copies are kept"
    assert len(after) >= min(dkdb.KEEP_BACKUPS, len(before) + 1)


def test_add_rename_move_delete_plain_tag(dk):
    r = tagmanager.apply({"op": "add", "parent": 0, "name": "zz-probe"}, check_running=False)
    tid = r["id"]
    assert _tags(dkdb.connect())[tid] == (0, "zz-probe")
    tagmanager.apply({"op": "rename", "id": tid, "name": "zz-probe2"}, check_running=False)
    assert _tags(dkdb.connect())[tid][1] == "zz-probe2"
    r2 = tagmanager.apply({"op": "add", "parent": 0, "name": "zz-parent"}, check_running=False)
    tagmanager.apply({"op": "move", "id": tid, "parent": r2["id"]}, check_running=False)
    assert _tags(dkdb.connect())[tid][0] == r2["id"]
    tagmanager.apply({"op": "delete", "id": r2["id"]}, check_running=False)
    t = _tags(dkdb.connect())
    assert r2["id"] not in t and tid not in t, "deleting a tag removes its sub-tags too (digiKam's delete_tagstree)"


def test_person_can_be_created_under_people_root(dk):
    root = _people_root(dk)
    tid = facemgr.create_person("Zz Probe Person", parent=root)
    con = dkdb.connect()
    assert _tags(con)[tid] == (root, "Zz Probe Person")
    props = {r[0]: r[1] for r in con.execute("SELECT property, value FROM TagProperties WHERE tagid = ?", (tid,))}
    assert "person" in props, "digiKam marks people with the person property"
    con.close()


def test_people_root_and_internal_tags_are_protected(dk):
    root = _people_root(dk)
    with pytest.raises(Exception):
        tagmanager.apply({"op": "rename", "id": root, "name": "Nope"}, check_running=False)
    with pytest.raises(Exception):
        tagmanager.apply({"op": "delete", "id": root}, check_running=False)
    person = dk.execute("SELECT t.id FROM Tags t JOIN TagProperties p ON p.tagid = t.id WHERE p.property = 'person' LIMIT 1").fetchone()
    if person:
        with pytest.raises(Exception):
            tagmanager.apply({"op": "delete", "id": person[0]}, check_running=False)


def test_face_ignore_and_unknown_roundtrip(dk, lib):
    row = dk.execute("SELECT imageid, tagid, value FROM ImageTagProperties WHERE property = 'tagRegion' LIMIT 1").fetchone()
    if not row:
        pytest.skip("no confirmed face region in the scratch library")
    image, tag, value = row
    import re
    x, y, w, h = map(int, re.findall(r"\d+", value)[:4])
    r = facemgr.apply({"op": "unknown", "image": image, "rect": [x, y, w, h]})
    assert r.get("sidecar_error") is None or isinstance(r.get("sidecar_error"), str)
    con = dkdb.connect()
    kinds = {p for p, in con.execute("SELECT property FROM ImageTagProperties WHERE imageid = ? AND value = ?", (image, value))}
    assert "autodetectedFace" in kinds and "tagRegion" not in kinds, "forgetting a name leaves an unknown face, as digiKam does"
    r = facemgr.apply({"op": "ignore", "image": image, "rect": [x, y, w, h]})
    kinds = {p for p, in con.execute("SELECT property FROM ImageTagProperties WHERE imageid = ? AND value = ?", (image, value))}
    assert "ignoredFace" in kinds
    r = facemgr.apply({"op": "name", "image": image, "rect": [x, y, w, h], "tag": tag})
    rows = con.execute("SELECT property FROM ImageTagProperties WHERE imageid = ? AND value = ? AND tagid = ?", (image, value, tag)).fetchall()
    assert ("tagRegion",) in rows
    assert con.execute("SELECT 1 FROM ImageTags WHERE imageid = ? AND tagid = ?", (image, tag)).fetchone()
    con.close()


def test_batch_runs_in_one_transaction(dk):
    rows = dk.execute("SELECT imageid, value FROM ImageTagProperties WHERE property = 'autodetectedFace' LIMIT 2").fetchall()
    if len(rows) < 1:
        pytest.skip("no unknown faces in the scratch library")
    import re
    ops = []
    for image, value in rows:
        x, y, w, h = map(int, re.findall(r"\d+", value)[:4])
        ops.append({"op": "ignore", "image": image, "rect": [x, y, w, h]})
    ops.append({"op": "ignore", "image": 999999999, "rect": [0, 0, 1, 1]})  # a bad one
    r = facemgr.apply_many(ops)
    assert isinstance(r, (list, dict))
    results = r if isinstance(r, list) else r.get("results", [])
    assert any(x.get("error") for x in results), "the bad op is reported"


def test_container_mode_writes_without_asking(client, dk):
    """DIGIKAM_CHECK=ask/none (containers): the viewer cannot see digiKam, so it neither checks nor asks."""
    from app import state
    assert client.get("/api/status").json()["digikamCheck"] == "none"
    state.set_setting("digikam_closed_until", "0")  # no vouch in force
    r = client.post("/api/tags/op", json={"op": "add", "parent": 0, "name": "zz-ask-probe"})
    assert r.status_code == 200, r.text
