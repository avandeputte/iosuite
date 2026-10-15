"""Look-alike face groups and near-duplicate sets are connected components over stored
similarities; the viewer proposes no names (groups only), both pages degrade without data."""
import numpy as np

from app import facevecs, index, neardups, vdb


def _unknown_faces(n):
    con = index.open_index()
    try:
        return con.execute("SELECT f.photo_id, f.x, f.y, f.w, f.h FROM faces f JOIN photos p ON p.id = f.photo_id "
                           "WHERE f.kind = 'unknown' AND p.video = 0 LIMIT ?", (n,)).fetchall()
    finally:
        con.close()


def _vec(seed, like=None, noise=0.0):
    rng = np.random.default_rng(seed)
    v = like + rng.normal(0, noise, 128) if like is not None else rng.normal(0, 1, 128)
    return (v / np.linalg.norm(v)).astype(np.float32)


def test_face_groups_from_vectors(client):
    faces = _unknown_faces(4)
    if len(faces) < 3:
        import pytest
        pytest.skip("the scratch library has fewer than 3 unnamed faces")
    base = _vec(1)
    vecs = [base, _vec(2, base, 0.05), _vec(3)] + ([_vec(4)] if len(faces) > 3 else [])  # two alike, the rest on their own
    con = vdb.connect()
    try:
        con.execute("DELETE FROM face_vecs")
        con.executemany("INSERT INTO face_vecs (photo_id, x, y, w, h, vec) VALUES (?,?,?,?,?,?)",
                        [(*f, vecs[i].tobytes()) for i, f in enumerate(faces)])
        con.commit()
    finally:
        con.close()
    g = facevecs.groups("unknown", 0.45)
    assert g["groups"] and g["groups"][0]["n"] == 2, g["groups"][:1]
    pair = {(f["photo"], f["x"]) for f in g["groups"][0]["faces"]}
    assert pair == {(faces[0][0], faces[0][1]), (faces[1][0], faces[1][1])}
    assert all("name" in f for f in g["groups"][0]["faces"]), "the face facts come from the index; no proposed names are added"
    assert len(g["ungrouped"]) >= 1
    r = client.get("/api/faces/groups?kind=unknown").json()
    assert r["groups"][0]["n"] == 2 and "available" in r and "progress" in r
    assert client.get("/api/faces/groups?kind=nope").status_code == 400
    con = vdb.connect(); con.execute("DELETE FROM face_vecs"); con.commit(); con.close()
    assert facevecs.groups("unknown")["groups"] == [] and len(facevecs.groups("unknown")["missing"]) >= 3


def test_near_duplicate_sets(client, lib):
    ids = lib["ids"][:5]
    con = vdb.connect()
    try:
        con.execute("DELETE FROM near_dups")
        con.executemany("INSERT INTO near_dups (a, b, score) VALUES (?,?,?)", [(ids[0], ids[1], 0.98), (ids[1], ids[2], 0.95), (ids[3], ids[4], 0.91)])
        con.commit()
    finally:
        con.close()
    from app import state
    state.set_setting("near_dups_gen", "x"); state.set_setting("near_dups_level", "normal")
    g = neardups.groups()
    assert [x["n"] for x in g] == [3, 2] and g[0]["score"] == 0.98
    assert {x["id"] for x in g[0]["items"]} == set(ids[:3]) and all("album" in x and "name" in x for x in g[0]["items"])
    r = client.get("/api/neardups").json()
    assert len(r["groups"]) == 2 and r["levels"]["normal"] == 0.94 and r["current"] is False, "computed for another index generation"
    assert client.post("/api/neardups", json={"level": "weird"}).status_code == 400
    assert client.post("/api/neardups", json={"level": "normal"}).status_code == 409, "content search is off in the test environment"
    con = vdb.connect(); con.execute("DELETE FROM near_dups"); con.commit(); con.close()
    state.set_setting("near_dups_gen", "")
    assert client.get("/api/neardups").json()["groups"] == []
