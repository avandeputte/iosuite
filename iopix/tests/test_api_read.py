"""The read side of the API against the scratch library: status, metadata,
photo lists and details, facets, map, zip planning, and the shapes the
front end relies on."""
import pytest


def test_status_shape(client):
    s = client.get("/api/status").json()
    for k in ("version", "app", "editing", "dbWrite", "readOnly", "readOnlyLocked", "analysis", "jobs", "pendingEdits"):
        assert k in s, k
    assert s["jobs"]["running"] is None or isinstance(s["jobs"]["running"], str)


def test_meta_lists_tags_and_albums(client, lib):
    m = client.get("/api/meta").json()
    assert m["version"]
    assert any(t["full"].startswith("People") for t in m["tags"])
    assert len(m["albums"]) >= len(lib["albums"]) - 1


def test_photos_compact_columns(client, lib):
    d = client.get("/api/photos").json()
    assert d["count"] == len(d["id"]) == len(lib["ids"])
    assert set(d["id"]) == set(lib["ids"])
    for col in ("ts", "w", "h", "video", "geo", "faces"):
        assert col in d, col
    # video is {index: duration}, geo/faces are index arrays (compact form the grid consumes)
    assert len(d["video"]) == len(lib["videos"]) and all(isinstance(v, int) for v in d["video"].values())
    assert all(isinstance(i, int) for i in d["geo"] + d["faces"])


def test_photo_detail(client, lib):
    pid = lib["with_faces"][0]
    d = client.get(f"/api/photo/{pid}").json()
    assert d["id"] == pid and d["w"] > 0 and d["h"] > 0
    assert "faces" in d and "faces_other" in d and "tags" in d
    assert d["faces"] or d["faces_other"], "a photo chosen for its face regions has none in the detail"
    assert client.get("/api/photo/999999999").status_code == 404


def test_filters_narrow_results(client, lib):
    allp = client.get("/api/photos").json()["count"]
    vids = client.get("/api/photos?type=video").json()["count"]
    assert vids == len(lib["videos"]) < allp
    geo = client.get("/api/photos?geo=1").json()["count"]
    assert 0 < geo <= allp
    faces = client.get("/api/photos?faces=confirmed").json()["count"]
    assert faces <= len(lib["with_faces"])


def test_text_search(client, lib):
    m = client.get("/api/meta").json()
    person = next(t for t in m["tags"] if t.get("person") and t["full"] != "People")
    d = client.get("/api/photos", params={"q": person["name"]}).json()
    assert d["count"] >= 0  # may be zero when the name is not on any kept photo, but must not error


def test_facets_and_map(client):
    f = client.get("/api/facets").json()
    assert isinstance(f, dict) and f
    m = client.get("/api/map").json()
    assert isinstance(m, (dict, list))


def test_zip_refuses_whole_library_and_plans_parts(client):
    r = client.post("/api/zip/plan", data={})
    assert r.status_code in (400, 409, 422)
    r = client.post("/api/zip/plan", data={"type": "video"})
    assert r.status_code == 200
    assert r.json()["parts"]


def test_thumbnail_and_preview_are_served(client, lib):
    pid = next(i for i in lib["ids"] if i not in lib["videos"])
    r = client.get(f"/thumb/{pid}")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/")
    r = client.get(f"/preview/{pid}")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/")


def test_models_and_analysis_endpoints(client):
    assert set(m["key"] for m in client.get("/api/models").json()["models"]) >= {"clip", "yolox", "geonames"}
    a = client.get("/api/analysis").json()
    assert [j["key"] for j in a["jobs"]][:2] == ["thumbs", "embeddings"]
    assert "queue" in a
