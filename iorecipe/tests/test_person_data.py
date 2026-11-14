"""Deleting someone in Settings › Security removes their private recipes, cookbooks and marks here; family recipes
they added stay."""
from iosuite_shared import users

from app import db
from conftest import sign_in
from test_api import new


def test_deleting_someone_removes_their_recipes_and_keeps_the_familys(client, as_user):
    as_user("ann", "editor")
    ann = users.find("ann")["id"]
    mine = new(client, title="My soup", family=False)
    fam = new(client, title="Family pie", family=True)
    assert client.post("/api/books", json={"name": "Mine", "family": False}).status_code == 201
    assert client.put(f"/api/recipes/{fam['id']}/mark", json={"favourite": True}).status_code == 200
    sign_in(client, "alex")
    got = client.get(f"/api/suite-admin/person-data/{ann}").json()["items"]
    assert {i["what"]: (i["count"], i["kept"]) for i in got} == {
        "private recipe": (1, False), "private cookbook": (1, False), "favourite or rating": (1, False),
        "family recipe they added": (1, True)}
    assert client.delete(f"/api/suite-admin/users/{ann}").status_code == 200
    assert not db.q("SELECT id FROM rcp_recipes WHERE id = %s", (mine["id"],))
    assert db.q("SELECT id FROM rcp_recipes WHERE id = %s", (fam["id"],))
    assert not db.q("SELECT 1 AS x FROM rcp_books WHERE owner_id = %s", (ann,)) and not db.q("SELECT 1 AS x FROM rcp_marks WHERE user_id = %s", (ann,))
