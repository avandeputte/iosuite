"""Things marked as the family's: whose a thing is (the suite's one family list), the filter, the search, the MCP view."""
from iosuite_shared import family, testing

from app import model
from conftest import sign_in


def new(client, **kw):
    r = client.post("/api/items", json={"name": "A thing", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_whose_a_thing_is(client):
    testing.add_account(client, {"name": "emma", "password": "secret123", "role": "member", "displayName": "Emma Smith"})
    testing.add_account(client, {"name": "sam", "password": "secret123", "role": "none"})  # no role here: still family
    fam = {m["name"]: m for m in client.get("/api/summary").json()["family"]}
    assert {"alex", "emma", "sam"} <= set(fam) and fam["emma"]["initials"] == "ES" and fam["emma"]["count"] == 0
    bike = new(client, name="Bike", people=["emma", fam["sam"]["id"]])
    assert [m["name"] for m in bike["people"]] == ["emma", "sam"]
    new(client, name="Laptop", people="Emma Smith")
    new(client, name="Boiler")
    assert client.get("/api/summary").json()["family"][[m["name"] for m in client.get("/api/summary").json()["family"]].index("emma")]["count"] == 2
    names = lambda **p: sorted(x["name"] for x in client.get("/api/items", params=p).json()["items"])  # noqa: E731
    assert names(person="emma") == ["Bike", "Laptop"]
    assert names(person=str(fam["sam"]["id"])) == ["Bike"]
    assert names(q="emma's") == ["Bike", "Laptop"] and names(q="emma bike") == ["Bike"] and names(q="boiler") == ["Boiler"]
    assert client.get("/api/items", params={"person": "nobody"}).status_code == 400
    # the list shows them; changing people replaces them; leaving people out keeps them
    listed = {x["name"]: x for x in client.get("/api/items").json()["items"]}
    assert [m["displayName"] for m in listed["Laptop"]["people"]] == ["Emma Smith"] and listed["Boiler"]["people"] == []
    assert [m["name"] for m in client.patch(f"/api/items/{bike['id']}", json={"people": ["sam"]}).json()["people"]] == ["sam"]
    assert [m["name"] for m in client.patch(f"/api/items/{bike['id']}", json={"name": "Red bike"}).json()["people"]] == ["sam"]
    assert [m["name"] for m in client.post(f"/api/items/{bike['id']}/duplicate").json()["people"]] == ["sam"]
    assert client.patch(f"/api/items/{bike['id']}", json={"people": []}).json()["people"] == []
    assert client.post("/api/items", json={"name": "X", "people": ["ghost"]}).status_code == 400


def test_out_of_the_family_and_a_deleted_account(client):
    testing.add_account(client, {"name": "emma", "password": "secret123", "role": "member"})
    emma = next(m for m in client.get("/api/summary").json()["family"] if m["name"] == "emma")
    it = new(client, name="Bike", people=["emma"])
    family.update(emma["id"], {"inFamily": False})  # a suite admin takes the account out of the family
    assert client.get(f"/api/items/{it['id']}").json()["people"] == []
    assert "emma" not in {m["name"] for m in client.get("/api/summary").json()["family"]}
    family.update(emma["id"], {"inFamily": True})
    assert [m["name"] for m in client.get(f"/api/items/{it['id']}").json()["people"]] == ["emma"]
    from app import persondata
    got = persondata.of(emma["id"], True)
    assert any(x["count"] == 1 and not x["kept"] for x in got)
    assert client.get(f"/api/items/{it['id']}").json()["people"] == []
    assert model.get(it["id"])["name"] == "Bike"  # the thing stays


def test_a_member_marks_their_own_thing(client, as_user):
    testing.add_account(client, {"name": "emma", "password": "secret123", "role": "member"})
    c = as_user("vic", "viewer")
    assert c.post("/api/items", json={"name": "Mine", "people": ["vic"]}).status_code == 403
    sign_in(client, "emma")
    it = new(client, name="Phone", people=["emma"])
    assert [m["name"] for m in it["people"]] == ["emma"]
