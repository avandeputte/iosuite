"""Deleting someone in Settings › Security removes their own bookmarks and layout here; shared bookmarks stay."""
from iosuite_shared import users

from app import db
from test_shared_bookmarks import _as


def test_deleting_someone_removes_their_bookmarks_and_keeps_the_shared_ones(client):
    family = client.post("/api/bookmarks/groups", json={"name": "Family"}).json()
    assert client.patch(f"/api/bookmarks/groups/{family['id']}", json={"shared": True}).status_code == 200
    bob = _as("bob", "member", client)
    b = users.find("bob")["id"]
    mine = bob.post("/api/bookmarks/groups", json={"name": "Bob's"}).json()
    bob.post(f"/api/bookmarks/groups/{mine['id']}/links", json={"name": "Mail", "href": "https://mail.example"})
    bob.post(f"/api/bookmarks/groups/{family['id']}/links", json={"name": "Bob's photos", "href": "https://bobphotos.example"})
    assert bob.put("/api/me/layout", json={"hidden": ["ionote"]}).status_code == 200
    got = client.get(f"/api/suite-admin/person-data/{b}").json()["items"]
    assert {i["what"]: i["count"] for i in got} == {"own bookmarks and folders": 3, "home page layout": 1}
    assert client.delete(f"/api/suite-admin/users/{b}").status_code == 200
    assert not db.q("SELECT id FROM prt_bookmark_nodes WHERE owner = %s", (b,))
    assert db.q("SELECT id FROM prt_bookmark_nodes WHERE id = %s", (family["id"],))
    assert db.get_setting(f"user:{b}:layout") is None
