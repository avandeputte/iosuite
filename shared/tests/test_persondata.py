"""Deleting someone removes what they kept in every app (iosuite_shared.persondata): the panel shows it first, each
app removes its part, shared things stay, and an app that was away removes it at its next start."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from iosuite_shared import apppasswords, db, links, persondata, sessions, suite, users
from iosuite_shared.fastapi import Auth


class Store:
    """An app's data: per account, private things and things it added to something shared."""

    def __init__(self):
        self.private, self.shared = {}, {}

    def person_data(self, uid, remove):
        out = [{"what": "private lists", "count": self.private.get(uid, 0)},
               {"what": "tasks they added to shared lists", "count": self.shared.get(uid, 0), "kept": True}]
        if remove:
            self.private.pop(uid, None)
        return out


def make_app(key, store):
    auth = Auth(key, app_label=key.capitalize(), register=False)
    auth.person_data = store.person_data
    app = FastAPI()
    app.middleware("http")(auth.middleware(open_prefixes=("/api/auth/",)))
    app.include_router(auth.router())
    app.include_router(auth.users_router())
    app.include_router(auth.admin_router())
    return auth, app


@pytest.fixture
def suite_of_two(monkeypatch):
    """ioStart (where the panel is open) and ioTask (asked over its API, here through a test client)."""
    start, task = Store(), Store()
    start_auth, start_app = make_app("iostart", start)
    task_auth, task_app = make_app("iotask", task)
    suite.register("iotask", name="ioTask", url="https://tasks.example.com")
    suite.register("iodns", name="ioDNS", url="https://dns.example.com", admin_tool=True)  # keeps nothing per person: not asked
    away = set()

    def ask(request, app, method, uid):
        assert app == "iotask"
        if app in away:
            raise RuntimeError("it did not answer (URLError)")
        r = TestClient(task_app, base_url="http://tasks.example.com").request(method, f"{persondata.PATH}{uid}", headers=links.viewer_headers(request))
        if r.status_code != 200:
            raise RuntimeError(f"it answered {r.status_code}")
        return persondata.clean(r.json()["items"])
    monkeypatch.setattr(persondata, "_ask", ask)
    return {"start": start, "task": task, "start_app": start_app, "task_auth": task_auth, "task_app": task_app, "away": away}


def signed_in(app, name, password="secret123"):
    c = TestClient(app, base_url="http://home.example.com")
    assert c.post("/api/auth/login", json={"name": name, "password": password}).status_code == 200
    return c


def test_the_panel_shows_what_goes_then_deletes_it_everywhere(suite_of_two):
    s = suite_of_two
    alex = users.create("alex", "secret123", suite_admin=True)
    ann = users.create("ann", "secret123")
    bob = users.create("bob", "secret123")
    apppasswords.create(ann["id"], "iotask", "Phone")
    s["start"].private.update({ann["id"]: 3, bob["id"]: 1})
    s["task"].private.update({ann["id"]: 2, bob["id"]: 5})
    s["task"].shared[ann["id"]] = 7
    c = signed_in(s["start_app"], "alex")
    signed_in(s["start_app"], "ann")  # a session of hers

    d = c.get(f"/api/suite-admin/users/{ann['id']}/data").json()
    by = {a["app"]: a for a in d["apps"]}
    assert set(by) == {"iostart", "iotask"}  # the admin tool is not asked
    assert by["iostart"]["items"] == [{"what": "private lists", "count": 3, "kept": False}]
    assert by["iotask"]["items"] == [{"what": "private lists", "count": 2, "kept": False},
                                     {"what": "tasks they added to shared lists", "count": 7, "kept": True}]
    shared = {i["what"]: i["count"] for i in d["shared"]}
    assert shared["app password"] == 1 and shared["session"] == 1  # one: the singular
    assert users.get(ann["id"]) and s["task"].private[ann["id"]] == 2  # looking changes nothing

    r = c.delete(f"/api/suite-admin/users/{ann['id']}")
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["ok"] and {a["app"]: a["error"] for a in got["apps"]} == {"iostart": None, "iotask": None}
    assert users.get(ann["id"]) is None
    assert ann["id"] not in s["start"].private and ann["id"] not in s["task"].private
    assert s["task"].shared[ann["id"]] == 7  # shared things stay
    assert s["start"].private[bob["id"]] == 1 and s["task"].private[bob["id"]] == 5  # nobody else's
    assert not db.q("SELECT 1 FROM ios_app_passwords WHERE user_id = %s", (ann["id"],))
    assert alex["id"]


def test_nothing_goes_when_the_account_cannot_be_deleted(suite_of_two):
    s = suite_of_two
    alex = users.create("alex", "secret123", suite_admin=True)
    s["start"].private[alex["id"]] = 4
    s["task"].private[alex["id"]] = 4
    c = signed_in(s["start_app"], "alex")
    assert c.delete(f"/api/suite-admin/users/{alex['id']}").status_code == 400  # your own
    assert c.delete("/api/suite-admin/users/9999").status_code == 404
    assert s["start"].private == {alex["id"]: 4} and s["task"].private == {alex["id"]: 4}


def test_an_app_that_was_away_removes_it_at_its_next_start(suite_of_two):
    s = suite_of_two
    users.create("alex", "secret123", suite_admin=True)
    ann = users.create("ann", "secret123")
    bob = users.create("bob", "secret123")
    s["task"].private.update({ann["id"]: 2, bob["id"]: 5})
    s["away"].add("iotask")
    c = signed_in(s["start_app"], "alex")
    d = c.get(f"/api/suite-admin/users/{ann['id']}/data").json()
    assert next(a for a in d["apps"] if a["app"] == "iotask")["error"].startswith("it did not answer")
    got = c.delete(f"/api/suite-admin/users/{ann['id']}").json()
    t = next(a for a in got["apps"] if a["app"] == "iotask")
    assert t["pending"] and users.get(ann["id"]) is None and s["task"].private[ann["id"]] == 2
    persondata.note_pending("iotask", bob["id"])  # an id whose account is still there is never acted on
    assert persondata.pending("iotask") == [ann["id"], bob["id"]]
    assert persondata.run_pending(s["task_auth"]) == 1
    assert ann["id"] not in s["task"].private and s["task"].private[bob["id"]] == 5
    assert persondata.pending("iotask") == []


def test_only_suite_admins_see_or_remove_anyones_data(suite_of_two):
    s = suite_of_two
    users.create("alex", "secret123", suite_admin=True)
    ann = users.create("ann", "secret123", "admin", "iotask")
    s["task"].private[ann["id"]] = 2
    c = signed_in(s["task_app"], "ann")  # an admin of the app, not of the suite
    assert c.get(f"{persondata.PATH}{ann['id']}").status_code == 403
    assert c.delete(f"{persondata.PATH}{ann['id']}").status_code == 403
    assert c.delete(f"/api/users/{ann['id']}").status_code == 403
    assert s["task"].private[ann["id"]] == 2


def test_the_old_users_route_deletes_the_data_too(suite_of_two):
    s = suite_of_two
    users.create("alex", "secret123", suite_admin=True)
    ann = users.create("ann", "secret123")
    s["start"].private[ann["id"]] = 1
    s["task"].private[ann["id"]] = 1
    r = signed_in(s["start_app"], "alex").delete(f"/api/users/{ann['id']}")
    assert r.status_code == 200 and users.get(ann["id"]) is None
    assert ann["id"] not in s["start"].private and ann["id"] not in s["task"].private


def test_an_app_without_an_address_says_so():
    suite.register("ionote", name="ioNote")
    with pytest.raises(RuntimeError, match="no address"):
        persondata._ask({}, "ionote", "GET", 1)
    assert persondata.clean([{"what": "x", "count": 0}, {"what": "y", "count": "3"}, "junk"]) == [{"what": "y", "count": 3, "kept": False}]
    assert persondata.clean([{"what": "lists", "one": "list", "count": 1}, {"what": "lists", "one": "list", "count": 2}]) == [
        {"what": "list", "count": 1, "kept": False}, {"what": "lists", "count": 2, "kept": False}]
    assert sessions.COOKIE
