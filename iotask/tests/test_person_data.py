"""Deleting someone in Settings › Security removes their private lists and templates here; their tasks on a shared
list stay."""
from iosuite_shared import users

from app import db
from iosuite_shared import testing


def _as(client, name, password="secret123"):
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": name, "password": password}).status_code == 200
    return users.find(name)["id"]


def test_deleting_someone_removes_their_lists_and_keeps_the_shared_ones(client, family_id):
    assert testing.add_account(client, {"name": "ann", "password": "secret123", "role": "editor"}).status_code == 200
    ann = _as(client, "ann")
    mine = next(c["id"] for c in client.get("/api/lists").json()["items"] if c["mine"])
    for t in ("Call the bank", "Gym"):
        assert client.post("/api/tasks", json={"title": t, "listId": mine}).status_code == 201
    assert client.post("/api/tasks", json={"title": "Milk", "listId": family_id}).status_code == 201
    db.ex("INSERT INTO tsk_templates (owner_id, name, items, created_by) VALUES (%s, 'Packing', '[]', %s)", (ann, ann))
    _as(client, "alex")
    got = client.get(f"/api/suite-admin/person-data/{ann}").json()["items"]
    assert {i["what"]: (i["count"], i["kept"]) for i in got} == {
        "private list": (1, False), "tasks in them": (2, False), "own template": (1, False), "task they added to a shared list": (1, True)}
    assert client.delete(f"/api/suite-admin/users/{ann}").status_code == 200
    assert not db.q("SELECT id FROM tsk_lists WHERE owner_id = %s", (ann,))
    assert not db.q("SELECT id FROM tsk_templates WHERE owner_id = %s", (ann,))
    assert [r["summary"] for r in db.q("SELECT summary FROM tsk_tasks WHERE list_id = %s AND deleted = 0", (family_id,))] == ["Milk"]
