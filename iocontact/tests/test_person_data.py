"""Deleting someone in Settings › Security removes their private address book here; the shared one stays."""
from iosuite_shared import users

from app import db


def _as(client, name, password="secret123"):
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": name, "password": password}).status_code == 200
    return users.find(name)["id"]


def test_deleting_someone_removes_their_address_book(client, family_id):
    assert client.post("/api/users", json={"name": "ann", "password": "secret123", "role": "editor"}).status_code == 200
    ann = _as(client, "ann")
    mine = next(b["id"] for b in client.get("/api/books").json()["items"] if not b["shared"])
    for fn in ("Dr Who", "Hair salon"):
        assert client.post(f"/api/contacts?book={mine}", json={"fn": fn}).status_code == 201
    assert client.post(f"/api/contacts?book={family_id}", json={"fn": "Grandma"}).status_code == 201
    _as(client, "alex")
    got = client.get(f"/api/suite-admin/person-data/{ann}").json()["items"]
    assert {i["what"]: i["count"] for i in got} == {"private address book": 1, "contacts in them": 2}
    assert client.delete(f"/api/suite-admin/users/{ann}").status_code == 200
    assert not db.q("SELECT id FROM con_address_books WHERE owner_id = %s", (ann,))
    assert [r["fn"] for r in db.q("SELECT fn FROM con_contacts WHERE address_book_id = %s AND deleted = 0", (family_id,))] == ["Grandma"]
