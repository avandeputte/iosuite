"""The browser extension's sync API (/dav/ext, app/bookmarkext.py), and the extension's own sync engine
(static/extension/sync.js) run by node against this app: browsers in memory that add, change, move and delete, a server that
deletes, and every browser ending the same."""
import base64
import os
import shutil
import socket
import subprocess
import threading
import time

import pytest

EXT = "/dav/ext"
HERE = os.path.dirname(os.path.dirname(__file__))


def _basic(name, pw):
    return {"Authorization": "Basic " + base64.b64encode(f"{name}:{pw}".encode()).decode()}


def _anon():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def _app_password(client, scope="dav"):
    r = client.post("/api/auth/app-passwords", json={"label": "Extension", "scope": scope})
    assert r.status_code == 200, r.text
    return r.json()["password"]


def _show(tree):
    return ",".join(f"{n['title']}[{_show(n['children'])}]" if n["folder"] else n["title"] for n in tree)


def test_sync_api(client):
    anon, auth = _anon(), _basic("alex", _app_password(client))
    assert anon.get(EXT).status_code == 401 and anon.get(EXT + "/tree").status_code == 401
    assert anon.post(EXT + "/sync", json={"base": 0, "ops": []}).status_code == 401
    me = anon.get(EXT, headers=auth).json()
    assert me["user"] == "alex" and me["canWrite"] is True
    rev0 = anon.get(EXT + "/rev", headers=auth).json()["rev"]
    # nothing to do moves nothing on
    assert anon.post(EXT + "/sync", headers=auth, json={"base": rev0, "ops": []}).json() == {"rev": rev0, "tree": [], "ids": {}}
    r = anon.post(EXT + "/sync", headers=auth, json={"base": rev0, "ops": [
        {"op": "create", "ref": "bar", "parent": None, "folder": True, "title": "Bookmarks bar"},
        {"op": "create", "ref": "a", "parent": "bar", "folder": False, "title": "A", "url": "https://a.example/"},
        {"op": "create", "ref": "b", "parent": "bar", "folder": False, "title": "B", "url": "javascript:void(0)"},
        {"op": "create", "ref": "f", "parent": "bar", "folder": True, "title": "F"},
        {"op": "create", "ref": "c", "parent": "f", "folder": False, "title": "C", "url": "https://c.example/"},
        {"op": "create", "ref": "bad", "parent": "bar", "folder": False, "title": "no address", "url": ""},  # skipped
        {"op": "create", "ref": "orphan", "parent": "bad", "folder": False, "title": "x", "url": "https://x.example/"},  # its folder was not made
        {"op": "create", "ref": "lost", "parent": 99999, "folder": False, "title": "y", "url": "https://y.example/"},
        {"op": "order", "parent": "bar", "ids": ["f", "b", "a", "bad"]},
        "nonsense", {"op": "unknown"},
    ]}).json()
    assert _show(r["tree"]) == "Bookmarks bar[F[C],B,A]" and set(r["ids"]) == {"bar", "a", "b", "f", "c"} and r["rev"] > rev0
    ids, rev1 = r["ids"], r["rev"]
    assert anon.get(EXT + "/tree", headers=auth).json() == {"rev": rev1, "tree": r["tree"]}
    # rename, re-address, move (an order names what comes from elsewhere), delete; what is gone is skipped
    r = anon.post(EXT + "/sync", headers=auth, json={"base": rev1, "ops": [
        {"op": "update", "id": ids["a"], "title": "A2", "url": "https://a2.example/"},
        {"op": "update", "id": 99999, "title": "gone"},
        {"op": "order", "parent": None, "ids": [ids["c"]]},
        {"op": "order", "parent": ids["c"], "ids": [ids["a"]]},  # not a folder
        {"op": "order", "parent": ids["f"], "ids": [ids["bar"]]},  # a folder into itself
        {"op": "delete", "id": ids["b"]}, {"op": "delete", "id": 99999}, {"op": "delete"},
    ]}).json()
    assert _show(r["tree"]) == "Bookmarks bar[F[],A2],C" and r["tree"][0]["children"][1]["url"] == "https://a2.example/"
    rev2 = r["rev"]
    # a delete of something changed since the browser's copy is skipped (alone, or anywhere in a folder); then it is not
    client.patch(f"/api/bookmarks/links/{ids['a']}", json={"name": "A3"})
    r = anon.post(EXT + "/sync", headers=auth, json={"base": rev2, "ops": [{"op": "delete", "id": ids["a"]}, {"op": "delete", "id": ids["bar"]}]}).json()
    assert _show(r["tree"]) == "Bookmarks bar[F[],A3],C"
    r = anon.post(EXT + "/sync", headers=auth, json={"base": r["rev"], "ops": [{"op": "delete", "id": ids["bar"]}]}).json()
    assert _show(r["tree"]) == "C"
    # while another sync app holds its lock the extension waits
    nc = "/dav/nextcloud/index.php/apps/bookmarks/public/rest/v2"
    anon.post(nc + "/lock", headers=auth)
    assert anon.post(EXT + "/sync", headers=auth, json={"base": 0, "ops": []}).status_code == 423
    assert anon.get(EXT + "/tree", headers=auth).status_code == 200
    anon.delete(nc + "/lock", headers=auth)
    assert anon.post(EXT + "/sync", headers=auth, json=[1]).status_code == 400
    assert anon.post(EXT + "/sync", headers=auth, json={"base": 0, "ops": "x"}).status_code == 400


def test_a_viewer_reads_but_does_not_change(client):
    r = client.post("/api/users", json={"name": "vera", "password": "secret123", "role": "viewer"})
    assert r.status_code in (200, 201), r.text
    from iosuite_shared import apppasswords
    from app.auth import auth as a
    pw = apppasswords.create(r.json()["id"], a.app, "Extension", apppasswords.DAV)
    anon, auth = _anon(), _basic("vera", pw)
    assert anon.get(EXT, headers=auth).json()["canWrite"] is False
    assert anon.get(EXT + "/tree", headers=auth).status_code == 200
    assert anon.post(EXT + "/sync", headers=auth, json={"base": 0, "ops": []}).status_code == 403


def test_the_extension_names_itself_when_it_signs_in(client):
    anon = _anon()
    f = anon.post("/dav/nextcloud/index.php/login/v2?client=ioSuite%20Bookmarks%20in%20Firefox", headers={"Host": "start.example.com"}).json()
    page = f["login"].replace("http://start.example.com", "")
    assert "ioSuite Bookmarks in Firefox" in client.get(page).text
    client.post("/dav/nextcloud/index.php/login/v2/grant", data={"page": page.rsplit("/", 1)[-1]})
    assert [p["label"] for p in client.get("/api/auth/app-passwords").json()["items"]] == ["Bookmark sync: ioSuite Bookmarks in Firefox"]


def test_the_extension_itself_syncs_browsers_both_ways(client, app):
    """tests/extension/e2e.js: the extension's sync engine, in node, against this app over HTTP."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    import uvicorn
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        r = subprocess.run([node, os.path.join(HERE, "tests", "extension", "e2e.js")], capture_output=True, text=True, timeout=120,
                           env={**os.environ, "SERVER": f"http://127.0.0.1:{port}", "SYNC_USER": "alex", "SYNC_PASSWORD": _app_password(client)})
        assert r.returncode == 0, r.stdout + r.stderr
        assert r.stdout.startswith("ok: Bookmarks bar[")
    finally:
        server.should_exit = True
        t.join(5)


def test_the_bookmarks_page_hands_out_the_extension(client):
    import io
    import json
    import zipfile
    v = client.get("/api/bookmarks/sync").json()["extension"]
    r = client.get("/api/bookmarks/extension.zip")
    assert r.status_code == 200 and f"iosuite-bookmarks-{v}.zip" in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(z.namelist())
    assert {"iosuite-bookmarks/" + n for n in ("manifest.json", "sync.js", "background.js", "options.html", "popup.html", "icons/128.png")} <= names
    m = json.loads(z.read("iosuite-bookmarks/manifest.json"))
    assert m["version"] == v and m["manifest_version"] == 3 and "bookmarks" in m["permissions"] and "host_permissions" not in m
    assert _anon().get("/api/bookmarks/extension.zip").status_code == 401
