"""Notes are private to each account: every read, search, sync, export and change works on the signed-in
account's notes only; ids never reach across accounts; notes made before accounts existed become the first admin's."""
import io
import json
import zipfile

from helpers import NID, png

OTHER = "BBBBBBBB-1111-2222-3333-444444444444"


def _as(client, name, password):
    client.cookies.clear()
    r = client.post("/api/auth/login", json={"name": name, "password": password})
    assert r.status_code == 200, r.text


def _two(client, admin):
    """alex (admin, signed in) and sam (editor)."""
    r = client.post("/api/users", json={"name": "sam", "password": "secretpw2", "role": "editor"})
    assert r.status_code == 200, r.text


def test_each_account_sees_only_its_own_notes(client, admin):
    _two(client, admin)
    client.put(f"/api/notes/{NID}", json={"title": "alex private", "tags": ["work"], "updatedAt": 1})
    client.post("/api/folders", json={"name": "Alex folder"})
    client.put("/api/tags/work/color", json={"color": "red"})
    _as(client, "sam", "secretpw2")
    assert client.get("/api/notes").json()["total"] == 0
    assert client.get(f"/api/notes/{NID}").status_code == 404
    assert client.get("/api/notes?q=private").json()["total"] == 0
    s = client.get("/api/sync").json()
    assert s["notes"] == [] and s["folders"] == [] and s["tags"] == []
    m = client.get("/api/meta").json()
    assert m["total"] == 0 and m["folders"] == [] and m["tags"] == []
    assert client.get("/api/changes").json()["changes"] == []
    # sam's own note, with the same tag coloured differently
    client.put(f"/api/notes/{OTHER}", json={"title": "sam's", "tags": ["work"], "updatedAt": 2})
    client.put("/api/tags/work/color", json={"color": "blue"})
    assert [n["title"] for n in client.get("/api/notes").json()["notes"]] == ["sam's"]
    assert client.get("/api/meta").json()["tags"][0]["color"] == "blue"
    _as(client, "alex", "secretpw1")
    assert [n["title"] for n in client.get("/api/notes").json()["notes"]] == ["alex private"]
    assert client.get("/api/meta").json()["tags"][0]["color"] == "red"


def test_ids_never_reach_another_accounts_note(client, admin):
    _two(client, admin)
    client.put(f"/api/notes/{NID}", json={"title": "alex's", "updatedAt": 1})
    client.put(f"/api/notes/{NID}/image", content=png(), headers={"content-type": "image/png"})
    _as(client, "sam", "secretpw2")
    assert client.put(f"/api/notes/{NID}", json={"title": "taken over", "updatedAt": 9e9, "force": True}).status_code == 404
    assert client.delete(f"/api/notes/{NID}").status_code == 404
    assert client.get(f"/api/notes/{NID}/image").status_code == 404
    assert client.get(f"/api/notes/{NID}/thumb").status_code == 404
    assert client.put(f"/api/notes/{NID}/image", content=png(), headers={"content-type": "image/png"}).status_code == 404
    assert client.delete(f"/api/notes/{NID}/image").status_code == 404
    push = client.post("/api/sync/push", json={"notes": [{"id": NID, "title": "via push", "updatedAt": 9e9}]}).json()
    assert push["notes"][0]["status"] == "error"
    _as(client, "alex", "secretpw1")
    n = client.get(f"/api/notes/{NID}").json()
    assert n["title"] == "alex's" and n["hasImage"]


def test_visitors_see_no_notes_once_accounts_exist(client, admin):
    client.put(f"/api/notes/{NID}", json={"title": "mine", "updatedAt": 1})
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.get("/api/notes").json()["total"] == 0
    assert client.get(f"/api/notes/{NID}").status_code == 404
    assert client.get("/api/sync").json()["notes"] == []


def test_notes_from_before_accounts_go_to_the_first_admin(client):
    assert client.put(f"/api/notes/{NID}", json={"title": "made while open", "updatedAt": 1}).status_code == 200
    client.post("/api/folders", json={"name": "Old"})
    r = client.post("/api/auth/setup", json={"name": "alex", "password": "secretpw1"})
    assert r.status_code == 200
    assert client.get(f"/api/notes/{NID}").json()["title"] == "made while open"
    assert [f["name"] for f in client.get("/api/folders").json()["folders"]] == ["Old"]
    client.post("/api/users", json={"name": "sam", "password": "secretpw2", "role": "editor"})
    _as(client, "sam", "secretpw2")
    assert client.get("/api/notes").json()["total"] == 0


def test_export_and_import_are_per_account(client, admin):
    _two(client, admin)
    client.put(f"/api/notes/{NID}", json={"title": "alex's", "updatedAt": 1})
    z = client.get("/api/export.zip").content
    assert [n["title"] for n in json.loads(zipfile.ZipFile(io.BytesIO(z)).read("notes.json"))["notes"]] == ["alex's"]
    _as(client, "sam", "secretpw2")
    assert json.loads(zipfile.ZipFile(io.BytesIO(client.get("/api/export.zip").content)).read("notes.json"))["notes"] == []
    # importing alex's export as sam takes nothing of alex's (the id is alex's)
    r = client.post("/api/import", files={"file": ("x.zip", z, "application/zip")}).json()
    assert r["notes"] == 0 and r["skipped"] == 1
    doc = {"notes": [{"id": OTHER, "title": "sam imports", "createdAt": 1, "updatedAt": 2}]}
    assert client.post("/api/import", files={"file": ("n.json", json.dumps(doc).encode(), "application/json")}).json()["notes"] == 1
    assert [n["title"] for n in client.get("/api/notes").json()["notes"]] == ["sam imports"]


def test_an_admin_gives_one_accounts_notes_to_another(client, admin):
    """Maintenance › Who owns the notes: when the old notes went to the wrong account, an admin moves them all."""
    _two(client, admin)
    _as(client, "sam", "secretpw2")
    client.put(f"/api/notes/{OTHER}", json={"title": "old note", "tags": ["work"], "updatedAt": 1})
    client.post("/api/folders", json={"name": "Old folder"})
    client.put("/api/tags/work/color", json={"color": "blue"})
    sam = client.get("/api/auth/me").json()["user"]["id"]
    assert client.get("/api/owners").status_code == 403
    _as(client, "alex", "secretpw1")
    me = client.get("/api/auth/me").json()["user"]["id"]
    rev = client.get("/api/sync").json()["rev"]
    owners = {o["id"]: o for o in client.get("/api/owners").json()["owners"]}
    assert owners[sam]["notes"] == 1 and owners[sam]["name"] == "sam"
    assert client.post("/api/owners/move", json={"from": sam, "to": me}).json()["moved"] == 1
    assert [n["title"] for n in client.get("/api/notes").json()["notes"]] == ["old note"]
    s = client.get(f"/api/sync?since={rev}").json()   # the devices of the new owner sync them in
    assert [n["title"] for n in s["notes"]] == ["old note"] and [f["name"] for f in s["folders"]] == ["Old folder"]
    assert client.get("/api/meta").json()["tags"][0]["color"] == "blue"
    _as(client, "sam", "secretpw2")
    assert client.get("/api/notes").json()["total"] == 0
