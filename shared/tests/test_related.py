"""Linked items (iosuite_shared.related): the links themselves in ios_related, and the routes every app mounts, with the
other apps faked (related.ask: what each app would answer the viewer)."""
import io
import urllib.error
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from iosuite_shared import related, suite, suiteitems, testing, users
from iosuite_shared.fastapi import Auth

ROOT = Path(__file__).resolve().parents[2]
PROVIDERS = {}

NOTE = "0F8FAD5B-D9CB-469F-A165-70867728950E"


def test_a_link_works_both_ways_and_once():
    a = related.add(("task", 12), ("note", NOTE.lower()))
    assert related.add(("note", NOTE), ("task", "12")) == a, "the same two items, either way round: one link"
    assert related.of("task", 12) == [{"link": a, "kind": "note", "id": NOTE, "createdAt": related.of("task", 12)[0]["createdAt"], "createdBy": None}]
    assert [(x["kind"], x["id"]) for x in related.of("note", NOTE)] == [("task", "12")]
    b = related.add(("task", 12), ("recipe", 3))
    assert [x["link"] for x in related.of("task", 12)] == [b, a], "the newest first"
    assert not related.remove("recipe", 3, a), "a link is removed from one of its own items only"
    assert related.remove("recipe", 3, b) and [x["kind"] for x in related.of("task", 12)] == ["note"]
    assert related.forget("note", NOTE) == 1 and related.of("task", 12) == []


def test_a_moved_item_takes_its_links_along():
    """An event moved to another calendar gets a new id there: its links follow, with who made them and when."""
    related.add(("event", 7), ("note", NOTE))
    related.add(("event", 7), ("task", 5))
    related.add(("event", 8), ("task", 5))  # the new id already has this link: kept once
    when = {x["kind"]: x["createdAt"] for x in related.of("event", 7)}
    assert related.move("event", 7, 8) == 2
    assert related.of("event", 7) == []
    got = {x["kind"]: x for x in related.of("event", 8)}
    assert set(got) == {"note", "task"} and got["note"]["createdAt"] == when["note"]
    assert related.move("event", "nope", 9) == 0  # never raises: the app's move has happened


@pytest.mark.parametrize("a, b", [(("task", 1), ("task", "1")), (("thing", 1), ("task", 2)), (("task", "1; DROP"), ("note", NOTE)),
                                  (("note", "12"), ("task", 1)), (("event", "0"), ("task", 1))])
def test_bad_links_are_refused(a, b):
    with pytest.raises(ValueError):
        related.add(a, b)


def test_forget_never_fails():
    assert related.forget("thing", "x") == 0
    assert related.forget_many("task", [1, 2]) == 0


# ------------------------------------------------------------------ the routes

SEEN = {  # (app, path) -> what that app answers the viewer; anything else: 404 (gone, or not theirs to see)
    ("iotask", "/api/tasks/12"): {"id": 12, "title": "Buy flour", "due": "2026-11-20", "dueAllDay": True, "done": False},
    ("iorecipe", "/api/recipes/3"): {"id": 3, "title": "Pancakes", "totalMinutes": 25, "photo": "/api/recipes/3/photos/7"},
    ("iocalendar", "/api/events/5"): {"id": 5, "title": "School meeting", "start": "2026-11-18T19:00:00+01:00", "allDay": False, "location": "School"},
    ("iorecipe", "/api/recipes"): {"items": [{"id": 3, "title": "Pancakes", "photo": "/api/recipes/3/photos/7"}]},
    ("iocalendar", "/api/events"): {"items": [
        {"id": 4, "title": "Past meeting", "allDay": False, "next": {"start": "2020-01-01T10:00:00+00:00"}},
        {"id": 5, "title": "School meeting", "allDay": False, "next": {"start": "2099-11-18T19:00:00+01:00"}}]},
}


@pytest.fixture()
def suite_apps(monkeypatch):
    for app in ("iotask", "iorecipe", "iocalendar", "ionote"):
        suite.register(app, name=app, url=f"https://{app}.example.com")
    calls = []

    def ask(request, app, path, params=None, image=False, timeout=5):
        """The app's /api/suite/* answered by its own provider (app/suiteitems.py), over the answers of its API in SEEN."""
        if app == "ionote":
            raise related.Unavailable(502, "ionote does not answer")

        def inner(p, prm, raw):
            calls.append((app, p, prm))
            if (app, p) in SEEN:
                return SEEN[(app, p)]
            raise suiteitems.Unavailable(404, f"{app} answered 404")
        try:
            return testing.suite_answer(PROVIDERS.setdefault(app, testing.suite_provider(ROOT, app)), path, params or {}, inner)
        except suiteitems.Unavailable as e:
            raise related.Unavailable(e.status, str(e)) from None
    monkeypatch.setattr(related, "ask", ask)
    return calls


def client(role="member"):
    auth = Auth("iotask")
    app = FastAPI()
    app.middleware("http")(auth.middleware())
    app.include_router(auth.router())
    app.include_router(auth.related_router())
    if not users.find("alex"):
        users.create("alex", "secret123", "admin", "iotask", suite_admin=True)
    users.create("sam", "secret123", role, "iotask")
    for a in ("iorecipe", "iocalendar", "ionote"):
        users.set_role(users.find("sam")["id"], a, "member")
    c = TestClient(app, base_url="http://tasks.example.com")
    assert c.post("/api/auth/login", json={"name": "sam", "password": "secret123"}).status_code == 200
    return c


def test_link_list_and_unlink(suite_apps):
    c = client()
    r = c.post("/api/related/task/12", json={"kind": "recipe", "id": 3})
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["title"] == "Pancakes" and got["text"] == "25 min" and got["image"] == "7"
    assert got["url"] == "https://iorecipe.example.com/#/recipe/3"
    related.add(("task", 12), ("event", 99))  # an event this person may not see: never listed to them
    lst = c.get("/api/related/task/12").json()
    assert lst["canEdit"] and [x["title"] for x in lst["items"]] == ["Pancakes"]
    assert c.get("/api/related/recipe/3").json()["items"][0]["title"] == "Buy flour", "the recipe links back"
    assert c.post("/api/related/task/12", json={"kind": "event", "id": 99}).status_code == 404, "both items must be seen"
    assert c.post("/api/related/task/13", json={"kind": "recipe", "id": 3}).status_code == 404
    assert c.post("/api/related/task/12", json={"kind": "task", "id": 12}).status_code == 400
    assert c.delete(f"/api/related/task/12/{got['link']}").status_code == 200
    assert c.get("/api/related/task/12").json()["items"] == []
    assert c.delete(f"/api/related/task/12/{got['link']}").status_code == 404


def test_another_apps_item_has_its_links_changed_there(suite_apps, monkeypatch):
    """A recipe's links are changed in ioRecipe, where this person's role there counts: from here the change is passed
    on to it as the viewer (ioCalendar showing the ioMoney transaction that paid a bill)."""
    sent = []

    def as_viewer(request, app, path, params=None, body=None, method=None, **kw):
        sent.append((app, method or ("POST" if body is not None else "GET"), path, body))
        if path.endswith("/404"):
            raise urllib.error.HTTPError(path, 404, "Not Found", {}, io.BytesIO(b'{"detail": "No such link"}'))
        return {"ok": True} if method == "DELETE" else {"kind": "event", "id": "5", "title": "School meeting", "link": 9}
    monkeypatch.setattr(related.links, "as_viewer", as_viewer)
    c = client()
    related.add(("recipe", 3), ("task", 12))
    assert c.get("/api/related/recipe/3").json()["canEdit"], "a member of ioRecipe too"
    assert c.post("/api/related/recipe/3", json={"kind": "event", "id": 5}).json()["link"] == 9
    assert c.delete("/api/related/recipe/3/9").json() == {"ok": True}
    r = c.delete("/api/related/recipe/3/404")
    assert r.status_code == 404 and r.json()["detail"] == "No such link", "ioRecipe's answer, as it gave it"
    assert sent == [("iorecipe", "POST", "/api/related/recipe/3", {"kind": "event", "id": "5"}),
                    ("iorecipe", "DELETE", "/api/related/recipe/3/9", None), ("iorecipe", "DELETE", "/api/related/recipe/3/404", None)]
    assert related.of("recipe", 3)[0]["kind"] == "task", "nothing changed here: ioRecipe does it"
    users.set_role(users.find("sam")["id"], "iorecipe", "viewer")
    assert not c.get("/api/related/recipe/3").json()["canEdit"], "only a viewer in ioRecipe: shown, not changed"


def test_a_viewer_sees_links_but_does_not_change_them(suite_apps):
    related.add(("task", 12), ("recipe", 3))
    c = client("viewer")
    lst = c.get("/api/related/task/12").json()
    assert not lst["canEdit"] and len(lst["items"]) == 1
    assert c.post("/api/related/task/12", json={"kind": "event", "id": 5}).status_code == 403
    assert c.delete(f"/api/related/task/12/{lst['items'][0]['link']}").status_code == 403


def test_search_asks_every_app_the_coming_events_first(suite_apps):
    c = client()
    suite.register("iotask", name="iotask", url="https://iotask.example.com")  # its own Auth registered it without an address
    suite.invalidate()
    groups = {g["kind"]: g for g in c.get("/api/related/search", params={"q": "meet"}).json()["groups"]}
    assert set(groups) == {"task", "recipe", "event", "note"}, "the apps in the suite that let this person in"
    assert [x["title"] for x in groups["event"]["items"]] == ["School meeting", "Past meeting"]
    assert groups["note"]["items"] == [] and "does not answer" in groups["note"]["error"]
    only = c.get("/api/related/search", params={"q": "pan", "kinds": "recipe"}).json()["groups"]
    assert [g["kind"] for g in only] == ["recipe"] and only[0]["items"][0]["id"] == "3"
    assert c.get("/api/related/search", params={"q": " "}).json() == {"groups": []}
    assert c.get("/api/related/kinds").json()["items"][0]["kind"] in related.KINDS


def test_signed_out_gets_nothing(suite_apps):
    auth = Auth("iotask")
    app = FastAPI()
    app.middleware("http")(auth.middleware())
    app.include_router(auth.related_router())
    users.create("alex", "secret123", "admin", "iotask", suite_admin=True)
    c = TestClient(app, base_url="http://tasks.example.com")
    assert c.get("/api/related/task/12").status_code == 401
    assert c.get("/api/related/ui.js").status_code in (200, 401)


def test_a_house_in_iomoney(suite_apps, monkeypatch):
    suite.register("iomoney", name="iomoney", url="https://iomoney.example.com")
    suite.invalidate()
    monkeypatch.setitem(SEEN, ("iomoney", "/api/accounts/4"), {"id": 4, "name": "12 Oak Lane", "kindLabel": "Real estate",
                                                                "balance": 585000.0, "estimate": None, "currency": "USD"})
    monkeypatch.setitem(SEEN, ("iomoney", "/api/accounts"), {"items": [{"id": 4, "name": "12 Oak Lane", "kindLabel": "Real estate", "balance": 585000.0, "currency": "USD"}]})
    c = client()
    got = c.post("/api/related/task/12", json={"kind": "asset", "id": 4}).json()
    assert got["title"] == "12 Oak Lane" and got["text"] == "Real estate · USD 585,000"
    assert got["url"] == "https://iomoney.example.com/#/account/4"
    found = c.get("/api/related/search", params={"q": "oak", "kinds": "asset"}).json()["groups"]
    assert found and found[0]["items"][0]["title"] == "12 Oak Lane"


def test_a_transaction_in_iomoney_and_a_thing_with_its_warranty(suite_apps, monkeypatch):
    suite.register("iomoney", name="iomoney", url="https://iomoney.example.com")
    suite.register("iothings", name="iothings", url="https://iothings.example.com")
    suite.invalidate()
    tx = {"id": 31, "merchant": "Corner Appliances", "amount": -1299.0, "currency": "USD", "day": "2026-03-02",
          "category": "Home", "account": "Joint checking"}
    monkeypatch.setitem(SEEN, ("iomoney", "/api/transactions/31"), tx)
    monkeypatch.setitem(SEEN, ("iomoney", "/api/transactions"), {"items": [tx]})
    monkeypatch.setitem(SEEN, ("iothings", "/api/items/7"), {"id": 7, "name": "Dishwasher", "location": {"path": "Kitchen"},
                                                             "warrantyExpires": "2028-03-02", "lifetimeWarranty": False})
    c = client()
    got = c.post("/api/related/task/12", json={"kind": "transaction", "id": 31}).json()
    assert got["title"] == "Corner Appliances" and got["text"] == "USD -1,299.00 · Home · Joint checking"
    assert got["when"] == "2026-03-02" and got["allDay"] and got["url"] == "https://iomoney.example.com/#/transaction/31"
    found = c.get("/api/related/search", params={"q": "appliances", "kinds": "transaction"}).json()["groups"]
    assert found and found[0]["label"] == "Transactions" and found[0]["items"][0]["id"] == "31"
    thing = c.post("/api/related/task/12", json={"kind": "item", "id": 7}).json()
    assert thing["text"] == "Kitchen · warranty to 2028-03-02"
    # which of many items have links (an app that removes them asks first), and forgetting them
    assert related.having("transaction", [30, 31, 32]) == ["31"] and related.having("transaction", []) == []
    assert related.forget_many("transaction", related.having("transaction", [31])) == 1
    assert related.having("transaction", [31]) == []


def test_a_passport_in_iodocs(suite_apps, monkeypatch):
    suite.register("iodocs", name="iodocs", url="https://iodocs.example.com")
    suite.invalidate()
    doc = {"id": 9, "title": "Ava’s passport", "kindLabel": "Passport", "expiresOn": "2031-12-28", "cover": "api/documents/9/files/3",
           "people": [{"id": 3, "displayName": "Ava Calloway"}]}
    monkeypatch.setitem(SEEN, ("iodocs", "/api/documents/9"), doc)
    monkeypatch.setitem(SEEN, ("iodocs", "/api/documents"), {"items": [doc]})
    c = client()
    got = c.post("/api/related/task/12", json={"kind": "document", "id": 9}).json()
    assert got["title"] == "Ava’s passport" and got["text"] == "Passport · Ava Calloway · expires 2031-12-28"
    assert got["url"] == "https://iodocs.example.com/#/doc/9"
    found = c.get("/api/related/search", params={"q": "passport", "kinds": "document"}).json()["groups"]
    assert found and found[0]["label"] == "Documents" and found[0]["items"][0]["id"] == "9"
