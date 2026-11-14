"""Shared and personal bookmarks: each person's own (only they see them) and the shared ones (everyone sees them, an
admin of the start page manages them), in one tree; the Bookmarks page, the start page and the sync clients alike."""
import base64

from app import bookmarks, db
from iosuite_shared import testing

EXT = "/dav/ext"


def _as(name, role, admin_client):
    """A client signed in as a new account with this role on the start page."""
    from fastapi.testclient import TestClient
    from app.main import app
    r = testing.add_account(admin_client, {"name": name, "password": "secret123", "role": role})
    assert r.status_code == 200, r.text
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"name": name, "password": "secret123"}).status_code == 200
    return c


def _names(items):
    return [x["name"] + ("/" if x["type"] == "folder" else "") for x in items]


def _find(items, name):
    for x in items:
        if x["name"] == name:
            return x
        if x["type"] == "folder":
            f = _find(x["items"], name)
            if f:
                return f
    return None


def test_own_and_shared(client):
    work = client.post("/api/bookmarks/groups", json={"name": "Work"}).json()
    client.post(f"/api/bookmarks/groups/{work['id']}/links", json={"name": "Mail", "href": "https://mail.example"})
    family = client.post("/api/bookmarks/groups", json={"name": "Family"}).json()
    client.post(f"/api/bookmarks/groups/{family['id']}/links", json={"name": "Photos", "href": "https://photos.example"})
    bob = _as("bob", "member", client)
    # alex's are alex's: bob sees nothing of them
    assert bob.get("/api/bookmarks/tree").json()["items"] == [] and bob.get("/api/bookmarks").json()["groups"] == []
    assert bob.patch(f"/api/bookmarks/groups/{work['id']}", json={"name": "x"}).status_code == 404
    t = client.get("/api/bookmarks/tree").json()
    assert t["canShare"] is True and _find(t["items"], "Work")["shared"] is False
    # sharing is for admins
    assert bob.patch(f"/api/bookmarks/groups/{family['id']}", json={"shared": True}).status_code == 404
    r = client.patch(f"/api/bookmarks/groups/{family['id']}", json={"shared": True})
    assert r.status_code == 200, r.text
    t = bob.get("/api/bookmarks/tree").json()
    assert t["canShare"] is False and t["canEdit"] is True
    assert _names(t["items"]) == ["Family/"] and _find(t["items"], "Photos")["shared"] is True
    assert _find(t["items"], "Family")["canChange"] is False
    assert [g["name"] for g in bob.get("/api/bookmarks").json()["groups"]] == ["Family"]
    # bob cannot change a shared one
    photos = _find(t["items"], "Photos")
    assert bob.patch(f"/api/bookmarks/links/{photos['id']}", json={"name": "Mine"}).status_code == 403
    assert bob.delete(f"/api/bookmarks/links/{photos['id']}").status_code == 403
    assert bob.delete(f"/api/bookmarks/groups/{family['id']}").status_code == 403
    assert bob.patch(f"/api/bookmarks/groups/{family['id']}", json={"shared": False}).status_code == 403
    # but keeps his own, in his tree and in the shared folder; alex does not see them
    own = bob.post("/api/bookmarks/groups/0/links", json={"name": "Bob's", "href": "https://bob.example"}).json()
    inside = bob.post(f"/api/bookmarks/groups/{family['id']}/links", json={"name": "Bob's photos", "href": "https://bobphotos.example"}).json()
    assert own["shared"] is False and inside["shared"] is False and inside["canChange"] is True
    assert _find(client.get("/api/bookmarks/tree").json()["items"], "Bob's photos") is None
    fam = _find(bob.get("/api/bookmarks/tree").json()["items"], "Family")
    assert [x["name"] for x in fam["items"]] == ["Photos", "Bob's photos"]
    # what alex adds in a shared folder is shared, as the folder is
    games = client.post(f"/api/bookmarks/groups/{family['id']}/links", json={"name": "Games", "href": "https://games.example"}).json()
    assert games["shared"] is True
    # bob reorders: his own move, the shared ones stay where they are
    bob.post(f"/api/bookmarks/groups/{family['id']}/order", json={"ids": [inside["id"], games["id"], photos["id"]]})
    fam = _find(bob.get("/api/bookmarks/tree").json()["items"], "Family")
    assert [x["name"] for x in fam["items"]] == ["Photos", "Bob's photos", "Games"]
    # a viewer reads, and keeps nothing of their own
    kid = _as("kid", "viewer", client)
    assert _names(kid.get("/api/bookmarks/tree").json()["items"]) == ["Family/"]
    assert kid.post("/api/bookmarks/groups/0/links", json={"name": "x", "href": "https://x.example"}).status_code == 403
    # alex takes the folder back: bob's own link in it goes to the top of bob's tree
    assert client.patch(f"/api/bookmarks/groups/{family['id']}", json={"shared": False}).json()["shared"] is False
    assert _names(bob.get("/api/bookmarks/tree").json()["items"]) == ["Bob's", "Bob's photos"]
    assert kid.get("/api/bookmarks/tree").json()["items"] == []
    assert all(not r["shared"] for r in db.q("SELECT shared FROM prt_bookmark_nodes WHERE name IN ('Family', 'Photos', 'Games')"))


def test_sharing_a_link_shares_its_folders_and_moving_out_unshares(client):
    a = client.post("/api/bookmarks/groups", json={"name": "A"}).json()
    b = client.post("/api/bookmarks/groups", json={"name": "B", "parentId": a["id"]}).json()
    l1 = client.post(f"/api/bookmarks/groups/{b['id']}/links", json={"name": "One", "href": "https://one.example"}).json()
    client.post(f"/api/bookmarks/groups/{b['id']}/links", json={"name": "Two", "href": "https://two.example"})
    client.patch(f"/api/bookmarks/links/{l1['id']}", json={"shared": True})
    bob = _as("bob", "member", client)
    t = bob.get("/api/bookmarks/tree").json()["items"]
    assert _names(t) == ["A/"] and _names(t[0]["items"]) == ["B/"] and _names(t[0]["items"][0]["items"]) == ["One"]
    # moved by alex into a folder of his own, it is his again
    mine = client.post("/api/bookmarks/groups", json={"name": "Mine"}).json()
    client.patch(f"/api/bookmarks/links/{l1['id']}", json={"groupId": mine["id"]})
    assert _find(bob.get("/api/bookmarks/tree").json()["items"], "One") is None
    assert _find(client.get("/api/bookmarks/tree").json()["items"], "One")["shared"] is False


def test_deleting_a_shared_folder_keeps_what_others_put_in_it(client):
    f = client.post("/api/bookmarks/groups", json={"name": "Shared stuff"}).json()
    client.patch(f"/api/bookmarks/groups/{f['id']}", json={"shared": True})
    bob = _as("bob", "member", client)
    bob.post(f"/api/bookmarks/groups/{f['id']}/links", json={"name": "Keep me", "href": "https://keep.example"})
    client.delete(f"/api/bookmarks/groups/{f['id']}")
    assert _names(bob.get("/api/bookmarks/tree").json()["items"]) == ["Keep me"]


def test_own_start_page_choice_on_a_shared_folder(client):
    f = client.post("/api/bookmarks/groups", json={"name": "News", "start": True}).json()
    client.post(f"/api/bookmarks/groups/{f['id']}/links", json={"name": "Paper", "href": "https://paper.example"})
    client.patch(f"/api/bookmarks/groups/{f['id']}", json={"shared": True})
    bob = _as("bob", "member", client)
    kid = _as("kid", "viewer", client)
    assert [g["name"] for g in bob.get("/api/bookmarks").json()["groups"]] == ["News"]
    # bob takes it off his start page: only his
    r = bob.patch(f"/api/bookmarks/groups/{f['id']}", json={"start": False})
    assert r.status_code == 200 and r.json()["start"] is False
    assert bob.get("/api/bookmarks").json()["groups"] == []
    assert [g["name"] for g in client.get("/api/bookmarks").json()["groups"]] == ["News"]
    assert [g["name"] for g in kid.get("/api/bookmarks").json()["groups"]] == ["News"]
    # a viewer may choose too (it is their start page), and the tree did not change
    rev = bookmarks.revision()
    assert kid.patch(f"/api/bookmarks/groups/{f['id']}", json={"start": False}).status_code == 200
    assert kid.get("/api/bookmarks").json()["groups"] == [] and bookmarks.revision() == rev
    # alex takes it off for everyone; bob turns it back on for himself
    client.patch(f"/api/bookmarks/groups/{f['id']}", json={"start": False})
    bob.patch(f"/api/bookmarks/groups/{f['id']}", json={"start": True})
    assert [g["name"] for g in bob.get("/api/bookmarks").json()["groups"]] == ["News"]
    assert client.get("/api/bookmarks").json()["groups"] == []


def test_bookmarks_nobody_owns_become_the_first_admins(client):
    client.post("/api/bookmarks/groups", json={"name": "Old"})
    db.ex("UPDATE prt_bookmark_nodes SET owner = NULL")
    bookmarks.claim_unowned()
    from iosuite_shared import users
    uid = users.find("alex")["id"]
    assert [r["owner"] for r in db.q("SELECT owner FROM prt_bookmark_nodes")] == [uid]


def _basic(name, pw):
    return {"Authorization": "Basic " + base64.b64encode(f"{name}:{pw}".encode()).decode()}


def test_extension_sees_shared_read_only(client):
    f = client.post("/api/bookmarks/groups", json={"name": "Bookmarks bar"}).json()
    l = client.post(f"/api/bookmarks/groups/{f['id']}/links", json={"name": "Wiki", "href": "https://wiki.example"}).json()
    client.patch(f"/api/bookmarks/groups/{f['id']}", json={"shared": True})
    bob = _as("bob", "member", client)
    pw = bob.post("/api/auth/app-passwords", json={"label": "Extension", "scope": "dav"}).json()["password"]
    from fastapi.testclient import TestClient
    from app.main import app
    anon, auth = TestClient(app), _basic("bob", pw)
    me = anon.get(EXT, headers=auth).json()
    assert me["canWrite"] is True and me["canShare"] is False
    st = anon.get(EXT + "/tree", headers=auth).json()
    assert st["tree"][0]["shared"] is True and st["tree"][0]["readOnly"] is True and st["tree"][0]["children"][0]["readOnly"] is True
    # bob renames the shared link and deletes the folder in his browser; adds a link of his own to the bar
    r = anon.post(EXT + "/sync", headers=auth, json={"base": st["rev"], "ops": [
        {"op": "update", "id": l["id"], "title": "Bob's wiki"},
        {"op": "create", "ref": "n1", "parent": f["id"], "folder": False, "title": "Mine", "url": "https://mine.example"},
        {"op": "delete", "id": f["id"]}]}).json()
    assert r["refused"] == 2
    bar = r["tree"][0]
    assert bar["title"] == "Bookmarks bar" and [c["title"] for c in bar["children"]] == ["Wiki", "Mine"]
    assert "readOnly" not in bar["children"][1]
    # alex's browser does not get bob's link
    pw2 = client.post("/api/auth/app-passwords", json={"label": "Extension", "scope": "dav"}).json()["password"]
    t2 = anon.get(EXT + "/tree", headers=_basic("alex", pw2)).json()["tree"]
    assert [c["title"] for c in t2[0]["children"]] == ["Wiki"] and t2[0]["readOnly"] is False


def test_webdav_file_is_each_ones_own(client):
    f = client.post("/api/bookmarks/groups", json={"name": "Private"}).json()
    client.post(f"/api/bookmarks/groups/{f['id']}/links", json={"name": "Secret", "href": "https://secret.example"})
    s = client.post("/api/bookmarks/groups", json={"name": "Everyone"}).json()
    client.patch(f"/api/bookmarks/groups/{s['id']}", json={"shared": True})
    bob = _as("bob", "member", client)
    pw = bob.post("/api/auth/app-passwords", json={"label": "Floccus", "scope": "dav"}).json()["password"]
    from fastapi.testclient import TestClient
    from app.main import app
    anon = TestClient(app)
    body = anon.get("/dav/bookmarks/bookmarks.html", headers=_basic("bob", pw)).text
    assert "Everyone" in body and "Secret" not in body and "Private" not in body
    # a file without the shared folder leaves it be
    up = body.replace("Everyone", "Renamed")
    assert anon.put("/dav/bookmarks/bookmarks.html", headers=_basic("bob", pw), content=up.encode()).status_code in (200, 201, 204)
    assert _names(client.get("/api/bookmarks/tree").json()["items"]) == ["Private/", "Everyone/"]
