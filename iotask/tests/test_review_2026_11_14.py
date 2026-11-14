"""What the code review of 14 November 2026 settled: links to other items of the suite follow a task (and its
subtasks) to another list, and go with a deleted list."""
from iosuite_shared import related

NOTE = "8F6C1E2A-0000-4000-8000-000000000001"


def test_links_follow_a_task_to_another_list_and_go_with_a_list(client, family_id):
    p = client.post(f"/api/tasks?list={family_id}", json={"title": "Party"}).json()
    kid = client.post(f"/api/tasks?list={family_id}", json={"title": "Cake", "parent": p["uid"]}).json()
    related.add(("task", p["id"]), ("note", NOTE))
    related.add(("task", kid["id"]), ("event", "42"))
    other = client.post("/api/lists", json={"name": "Other"}).json()["list"]["id"]
    moved = client.patch(f"/api/tasks/{p['id']}", json={"listId": other}).json()
    assert [(x["kind"], x["id"]) for x in related.of("task", moved["id"])] == [("note", NOTE)]
    assert related.of("task", p["id"]) == [] and related.of("task", kid["id"]) == []
    new_kid = next(t for t in client.get("/api/tasks", params={"status": "all", "list": other}).json()["items"] if t["title"] == "Cake")
    assert [(x["kind"], x["id"]) for x in related.of("task", new_kid["id"])] == [("event", "42")]
    assert client.delete(f"/api/lists/{other}").status_code == 200
    assert related.of("task", moved["id"]) == [] and related.of("task", new_kid["id"]) == []
