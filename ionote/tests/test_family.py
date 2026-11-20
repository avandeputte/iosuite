"""The Family space: a note marked family is everyone's who has a role here. Viewers and members read it; editors and
admins add, change, delete and un-share. Everything else stays each account's own."""
import io
import json
import zipfile

from helpers import NID, NID2, pdf, png
from iosuite_shared import testing, users

from app import db

OWN = "BBBBBBBB-1111-2222-3333-444444444444"


def _as(client, name, password):
    client.cookies.clear()
    r = client.post("/api/auth/login", json={"name": name, "password": password})
    assert r.status_code == 200, r.text


def _family(client, admin):
    """alex (admin, signed in), eve (editor), sam (member) and vic (viewer); alex's family note NID, private NID2."""
    for name, pw, role in (("eve", "secretpw2", "editor"), ("sam", "secretpw3", "member"), ("vic", "secretpw4", "viewer")):
        r = testing.add_account(client, {"name": name, "password": pw, "role": role})
        assert r.status_code == 200, r.text
    assert client.post("/api/folders", json={"name": "Alex folder"}).status_code == 200
    folder = client.get("/api/folders").json()["folders"][0]["id"]
    r = client.put(f"/api/notes/{NID}", json={"title": "Wifi password", "body": "hunter2 for guests", "tags": ["home"], "folderID": folder,
                                              "family": True, "updatedAt": 1})
    assert r.status_code == 200, r.text
    assert r.json()["family"] is True and r.json()["folderID"] is None  # folders are each account's own
    assert client.put(f"/api/notes/{NID2}", json={"title": "alex private", "updatedAt": 1}).status_code == 200


def test_everyone_with_a_role_reads_family_notes(client, admin):
    _family(client, admin)
    for name, pw in (("eve", "secretpw2"), ("sam", "secretpw3"), ("vic", "secretpw4")):
        _as(client, name, pw)
        assert [n["title"] for n in client.get("/api/notes").json()["notes"]] == ["Wifi password"], name
        assert client.get(f"/api/notes/{NID}").json()["family"] is True
        assert client.get(f"/api/notes/{NID2}").status_code == 404
        assert client.get("/api/notes?q=hunter2").json()["total"] == 1
        assert client.get("/api/notes?family=1").json()["total"] == 1
        assert client.get("/api/notes?family=0").json()["total"] == 0
        assert client.get("/api/notes?folder=none").json()["total"] == 0  # "No folder" is for one's own notes
        m = client.get("/api/meta").json()
        assert m["family"] == 1 and m["total"] == 1 and m["noFolder"] == 0 and m["trash"] == 0
        assert m["familyWrite"] is (name == "eve")
        assert [t["name"] for t in m["tags"]] == ["home"]
        s = client.get("/api/sync").json()
        assert [n["id"] for n in s["notes"]] == [NID] and s["familyWrite"] is (name == "eve")
    _as(client, "alex", "secretpw1")
    m = client.get("/api/meta").json()
    assert m["total"] == 2 and m["family"] == 1 and m["noFolder"] == 1 and m["familyWrite"] is True


def test_members_read_but_do_not_change_family_notes(client, admin):
    _family(client, admin)
    client.put(f"/api/notes/{NID}/image", content=png(), headers={"content-type": "image/png"})
    a = client.post(f"/api/notes/{NID}/attachments", files={"file": ("bill.pdf", pdf(), "application/pdf")}).json()
    aid = a["attachments"][0]["id"]
    _as(client, "sam", "secretpw3")
    # the picture and the attachment are read
    assert client.get(f"/api/notes/{NID}/image").status_code == 200
    assert client.get(f"/api/notes/{NID}/attachments/{aid}").status_code == 200
    assert client.get("/api/notes?q=acme").json()["total"] == 1  # the attachment's text is searched
    # a change is answered like an older edit: 409 with the server's copy, which a device takes
    r = client.put(f"/api/notes/{NID}", json={"title": "changed", "updatedAt": 9e9, "force": True})
    assert r.status_code == 409 and r.json()["current"]["title"] == "Wifi password"
    assert "editors" in r.json()["detail"]
    assert client.delete(f"/api/notes/{NID}").status_code == 409
    assert client.put(f"/api/notes/{NID}", json={"family": False, "updatedAt": 9e9}).status_code == 409
    assert client.put(f"/api/notes/{NID}/image", content=png(), headers={"content-type": "image/png"}).status_code == 409
    assert client.delete(f"/api/notes/{NID}/image").status_code == 409
    assert client.post(f"/api/notes/{NID}/attachments", files={"file": ("x.pdf", pdf(), "application/pdf")}).status_code == 409
    assert client.delete(f"/api/notes/{NID}/attachments/{aid}").status_code == 409
    push = client.post("/api/sync/push", json={"notes": [{"id": NID, "title": "via push", "updatedAt": 9e9}]}).json()
    assert push["notes"][0]["status"] == "stale" and push["notes"][0]["item"]["title"] == "Wifi password"
    # nor does a member put a note of their own in the Family space
    assert client.put(f"/api/notes/{OWN}", json={"title": "sam's", "family": True, "updatedAt": 2}).status_code == 400
    assert client.put(f"/api/notes/{OWN}", json={"title": "sam's", "tags": ["home"], "updatedAt": 2}).status_code == 200
    assert client.put(f"/api/notes/{OWN}", json={"family": True, "updatedAt": 3}).status_code == 400
    # renaming a tag changes only one's own notes
    assert client.post("/api/tags/rename", json={"from": "home", "to": "house"}).status_code == 200
    assert client.get(f"/api/notes/{OWN}").json()["tags"] == ["house"]
    assert client.get(f"/api/notes/{NID}").json()["tags"] == ["home"]
    _as(client, "alex", "secretpw1")
    n = client.get(f"/api/notes/{NID}").json()
    assert n["title"] == "Wifi password" and n["hasImage"] and len(n["attachments"]) == 1 and n["family"]


def test_editors_change_family_notes(client, admin):
    _family(client, admin)
    _as(client, "eve", "secretpw2")
    r = client.put(f"/api/notes/{NID}", json={"title": "Wifi password (new)", "updatedAt": 9e9})
    assert r.status_code == 200 and r.json()["family"] is True and r.json()["changedBy"] == "eve"
    assert client.put(f"/api/notes/{NID}/image", content=png(), headers={"content-type": "image/png"}).status_code == 200
    a = client.post(f"/api/notes/{NID}/attachments", files={"file": ("bill.pdf", pdf(), "application/pdf")})
    assert a.status_code == 200 and len(a.json()["attachments"]) == 1
    # an editor's own new family note
    assert client.put(f"/api/notes/{OWN}", json={"title": "Bin days", "family": True, "updatedAt": 5}).status_code == 200
    # into the trash and back, by any editor
    assert client.delete(f"/api/notes/{NID}").status_code == 200
    assert [n["id"] for n in client.get("/api/trash").json()["notes"]] == [NID]
    _as(client, "sam", "secretpw3")
    assert client.get("/api/trash").json()["notes"] == []  # a member's trash holds their own notes only
    assert client.post(f"/api/notes/{NID}/restore").status_code == 409
    assert client.delete(f"/api/trash/{NID}").status_code == 404
    _as(client, "alex", "secretpw1")
    assert [n["id"] for n in client.get("/api/trash").json()["notes"]] == [NID]
    r = client.post(f"/api/notes/{NID}/restore")
    assert r.status_code == 200 and r.json()["family"] is True and r.json()["hasImage"]
    assert sorted(n["title"] for n in client.get("/api/notes?family=1").json()["notes"]) == ["Bin days", "Wifi password (new)"]


def test_unsharing_makes_the_note_the_editors_own_and_tells_the_others(client, admin):
    _family(client, admin)
    _as(client, "sam", "secretpw3")
    since = client.get("/api/sync").json()["rev"]
    _as(client, "alex", "secretpw1")
    alex_since = client.get("/api/sync").json()["rev"]
    _as(client, "eve", "secretpw2")
    r = client.put(f"/api/notes/{NID}", json={"family": False, "updatedAt": 9e9})
    assert r.status_code == 200 and r.json()["family"] is False
    assert client.get("/api/notes?family=0").json()["total"] == 1  # eve's own now
    # sam's device is told the note is gone, and so is alex's (it was alex's before it was the family's)
    for name, pw, rev in (("sam", "secretpw3", since), ("alex", "secretpw1", alex_since)):
        _as(client, name, pw)
        assert client.get(f"/api/notes/{NID}").status_code == 404
        assert client.get("/api/meta").json()["rev"] > rev  # the web app notices too
        s = client.get(f"/api/sync?since={rev}").json()
        gone = [n for n in s["notes"] if n["id"] == NID]
        assert len(gone) == 1 and gone[0]["deleted"] is True and gone[0]["title"] == "" and gone[0]["body"] == "", name
        assert client.get(f"/api/sync?since={s['rev']}").json()["notes"] == []
        assert NID not in [n["id"] for n in client.get("/api/sync").json()["notes"]]  # a device starting from nothing never had it
    # eve's own devices keep it, as an edit
    _as(client, "eve", "secretpw2")
    mine = [n for n in client.get(f"/api/sync?since={since}").json()["notes"] if n["id"] == NID]
    assert len(mine) == 1 and mine[0]["deleted"] is False and mine[0]["family"] is False and mine[0]["title"] == "Wifi password"
    # and shares it again
    assert client.put(f"/api/notes/{NID}", json={"family": True, "updatedAt": 9e9 + 1}).status_code == 200
    _as(client, "sam", "secretpw3")
    assert client.get(f"/api/notes/{NID}").json()["title"] == "Wifi password"
    back = [n for n in client.get(f"/api/sync?since={since}").json()["notes"] if n["id"] == NID]
    assert len(back) == 1 and back[0]["deleted"] is False and back[0]["family"] is True


def test_change_log_says_shared_and_unshared(client, admin):
    _family(client, admin)
    client.put(f"/api/notes/{NID2}", json={"family": True, "updatedAt": 5})
    client.put(f"/api/notes/{NID2}", json={"family": False, "updatedAt": 6})
    acts = [c["action"] for c in client.get("/api/changes").json()["changes"] if c["kind"] == "note" and c["uuid"] == NID2]
    assert "share" in acts and "unshare" in acts


def test_export_puts_family_notes_in_a_family_folder(client, admin):
    _family(client, admin)
    _as(client, "sam", "secretpw3")
    client.put(f"/api/notes/{OWN}", json={"title": "sam's", "updatedAt": 2})
    blob = client.get("/api/export.zip").content
    z = zipfile.ZipFile(io.BytesIO(blob))
    names = z.namelist()
    assert any(n.startswith("Family/Wifi password") for n in names), names
    assert not any("alex private" in n for n in names)
    data = json.loads(z.read("notes.json"))
    assert sorted(n["title"] for n in data["notes"]) == ["Wifi password", "sam's"]
    # imported back by a member, the family's note is left as it is
    r = client.post("/api/import", files={"file": ("export.zip", blob, "application/zip")})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/notes/{NID}").json()["family"] is True


def test_deleting_someone_keeps_what_they_put_in_the_family_space(client, admin):
    _family(client, admin)
    _as(client, "eve", "secretpw2")
    eve = users.find("eve")["id"]
    client.put(f"/api/notes/{OWN}", json={"title": "Bin days", "family": True, "updatedAt": 5})
    client.post(f"/api/notes/{OWN}/attachments", files={"file": ("bins.pdf", pdf(), "application/pdf")})
    client.put("/api/notes/CCCCCCCC-1111-2222-3333-444444444444", json={"title": "eve private", "updatedAt": 6})
    _as(client, "alex", "secretpw1")
    items = {i["what"]: i for i in client.get(f"/api/suite-admin/person-data/{eve}").json()["items"]}
    assert items["note"]["count"] == 1 and not items["note"]["kept"]
    assert items["note they put in the Family space"]["kept"] is True
    assert "attachment" not in items  # the family note's attachment is not hers to lose
    assert client.delete(f"/api/suite-admin/users/{eve}").status_code == 200
    n = client.get(f"/api/notes/{OWN}").json()
    assert n["title"] == "Bin days" and n["family"] and len(n["attachments"]) == 1
    with db.connect() as con:
        assert con.execute("SELECT count(*) FROM nts_notes WHERE user_id = %s", (eve,)).fetchone()[0] == 0
        assert con.execute("SELECT count(*) FROM nts_notes WHERE title = 'eve private'").fetchone()[0] == 0


def test_visitors_see_no_family_notes(client, admin):
    _family(client, admin)
    assert client.patch("/api/suite-admin/apps/ionote", json={"requireLogin": False}).status_code == 200
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.get("/api/notes").json()["total"] == 0
    assert client.get(f"/api/notes/{NID}").status_code == 404
    assert client.get("/api/sync").json()["notes"] == []
    assert client.get("/api/meta").json()["family"] == 0


def test_assistants_read_family_notes_and_only_editors_change_them(client, admin):
    from test_mcp import _call, anon, app_password, signed_in
    _family(client, admin)
    client.post("/api/server", json={"mcpEnabled": True})
    sam = app_password(signed_in("sam", "secretpw3"), "sam's")
    eve = app_password(signed_in("eve", "secretpw2"), "eve's")
    a = anon()
    o = _call(a, "notes_overview", {}, headers=sam)["structuredContent"]
    assert o["family_notes"] == 1 and o["may_change_family_notes"] is False
    found = _call(a, "search_notes", {"family": True}, headers=sam)["structuredContent"]["notes"]
    assert [n["id"] for n in found] == [NID] and found[0]["family"] is True
    assert _call(a, "get_note", {"note_id": NID}, headers=sam)["structuredContent"]["family"] is True
    bad = _call(a, "update_note", {"note_id": NID, "title": "changed"}, headers=sam)
    assert bad["isError"] and "family" in bad["content"][0]["text"].lower()
    assert _call(a, "delete_note", {"note_id": NID}, headers=sam)["isError"]
    assert _call(a, "create_note", {"text": "mine for all", "family": True}, headers=sam)["isError"]
    ok = _call(a, "update_note", {"note_id": NID, "title": "Wifi (new)"}, headers=eve)
    assert not ok.get("isError"), ok
    made = _call(a, "create_note", {"title": "Bin days", "text": "Tuesday", "family": True}, headers=eve)
    assert not made.get("isError"), made
    assert _call(a, "notes_overview", {}, headers=sam)["structuredContent"]["family_notes"] == 2
    mine = _call(a, "update_note", {"note_id": NID, "family": False}, headers=eve)
    assert not mine.get("isError"), mine
    assert _call(a, "get_note", {"note_id": NID}, headers=sam)["isError"]
