"""Duplicates (scored, with reasons), merging with choices, undo, and the data quality checks and fixes."""
from tests.test_api import mk as _mk


def mk(client, book, **kw):
    return _mk(client, book, **kw)["id"]


def groups(client):
    return client.get("/api/duplicates").json()["groups"]


def names(g):
    return sorted(c["fn"] for c in g["contacts"])


def test_duplicates_scored_with_reasons(client, family_id):
    mk(client, family_id, name={"given": "Robert", "family": "Smith"}, birthday={"year": 1970, "month": 5, "day": 1})
    mk(client, family_id, name={"given": "Bob", "family": "Smith"}, birthday={"month": 5, "day": 1})
    mk(client, family_id, fn="Jonathan Appleseed", emails=[{"value": "jon@apple.example"}])
    mk(client, family_id, fn="Jonathon Appleseed")
    # one household: a last name, an address, the home phone and a family email shared, other first names: not duplicates
    home = {"addresses": [{"street": "Kerkstraat 1", "city": "Gent", "label": "home"}], "emails": [{"value": "fam@vdp.example"}]}
    for given in ("Jan", "Jef", "Mary", "Mark", "Anna", "Hanne", "Lies", "Lien", "Elise", "Eline"):
        mk(client, family_id, name={"given": given, "family": "Vandeputte"}, phones=[{"value": "+32 9 123 45 67" if given < "K" else "09 123 45 67"}], **home)
    # a father and son with one name
    mk(client, family_id, name={"given": "Paul", "family": "Maes", "suffix": "Sr."}, phones=[{"value": "+32 3 111 22 33"}])
    mk(client, family_id, name={"given": "Paul", "family": "Maes", "suffix": "Jr."}, phones=[{"value": "+32 3 111 22 33"}])
    # same name, other birthdays: two people
    mk(client, family_id, fn="Jan Peeters", birthday={"year": 1950, "month": 1, "day": 2})
    mk(client, family_id, fn="Jan Peeters", birthday={"year": 1985, "month": 8, "day": 9})
    # the same name, one birthday a year only: the other year says two people; the same year still says one
    mk(client, family_id, fn="Piet Claes", birthday={"year": 1950})
    mk(client, family_id, fn="Piet Claes", birthday={"year": 1985, "month": 8, "day": 9})
    mk(client, family_id, fn="Lotte Claes", birthday={"year": 1990})
    mk(client, family_id, fn="Lotte Claes", birthday={"year": 1990, "month": 2, "day": 3})
    gs = {tuple(names(g)): g for g in groups(client)}
    assert ("Piet Claes", "Piet Claes") not in gs
    assert "same birth year" in gs[("Lotte Claes", "Lotte Claes")]["pairs"][0]["reasons"]
    bob = gs[("Bob Smith", "Robert Smith")]
    assert bob["level"] == "very likely" and any("short for" in r for r in bob["pairs"][0]["reasons"])
    assert gs[("Jonathan Appleseed", "Jonathon Appleseed")]["level"] in ("possible", "likely")
    assert not any("Vandeputte" in n for key in gs for n in key), list(gs)
    assert not any("Maes" in n for key in gs for n in key)
    assert ("Jan Peeters", "Jan Peeters") not in gs
    # not duplicates: never offered again
    ids = [c["id"] for c in bob["contacts"]]
    assert client.post("/api/duplicates/dismiss", json={"ids": ids}).json()["pairs"] == 1
    assert ("Bob Smith", "Robert Smith") not in {tuple(names(g)) for g in groups(client)}


def test_merge_with_choices_and_undo(client, family_id):
    a = mk(client, family_id, name={"given": "Ann", "family": "Lee"}, org="Acme", emails=[{"value": "ann@a.example"}], tags=["family"])
    b = mk(client, family_id, name={"given": "Annie", "family": "Lee"}, org="Globex", emails=[{"value": "ann@b.example"}],
           phones=[{"value": "+1 555 0101"}], birthday={"year": 1990, "month": 3, "day": 3})
    c = mk(client, family_id, fn="Kid Lee", relations=[{"type": "parent", "relatedId": b}])
    pv = client.get(f"/api/merge/preview?ids={a},{b}&keep={a}").json()
    assert set(pv["choices"]) >= {"name", "org"} and len(pv["merged"]["emails"]) == 2 and pv["merged"]["birthday"]["year"] == 1990
    result = {**pv["merged"], "org": "Globex", "name": {"given": "Annie", "family": "Lee"}, "fn": ""}
    out = client.post("/api/contacts/merge", json={"keep": a, "others": [b], "result": result}).json()
    assert out["org"] == "Globex" and out["fn"] == "Annie Lee" and len(out["emails"]) == 2 and out["phones"]
    assert client.get(f"/api/contacts/{b}").status_code == 404
    kid = client.get(f"/api/contacts/{c}").json()
    assert kid["relations"][0]["relatedId"] == a  # the relation moved to the kept contact
    hist = client.get("/api/merges").json()["items"]
    assert hist[0]["canUndo"] and hist[0]["keepId"] == a
    assert client.post(f"/api/merges/{hist[0]['id']}/undo").status_code == 200
    back_a, back_b = client.get(f"/api/contacts/{a}").json(), client.get(f"/api/contacts/{b}").json()
    assert back_a["org"] == "Acme" and len(back_a["emails"]) == 1 and back_b["fn"] == "Annie Lee" and back_b["phones"]
    assert client.get(f"/api/contacts/{c}").json()["relations"][0]["relatedId"] == b
    assert client.post(f"/api/merges/{hist[0]['id']}/undo").status_code == 409


def test_quality_checks_and_fixes(client, family_id):
    caps = mk(client, family_id, name={"given": "ANN-MARIE", "family": "VAN DER BERG"})
    rep = mk(client, family_id, fn="Rep Eat", emails=[{"value": "a@b.example"}, {"value": "A@B.example"}],
             phones=[{"value": "0475 12 34 56"}, {"value": "+32 475 12 34 56"}, {"value": "12"}])
    mk(client, family_id, fn="Bad Mail", emails=[{"value": "not-an-email"}], birthday={"year": 2999, "month": 1, "day": 1})
    lonely = mk(client, family_id, fn="Lonely Person", relations=[{"type": "sibling", "relatedName": "Later Person"}])
    later = mk(client, family_id, fn="Later Person", phones=[{"value": "016 22 33 44"}])
    # the relation was linked when Later Person was made; an unlinked one appears when a name is entered by hand
    q = {x["check"]: x for x in client.get("/api/quality").json()["checks"]}
    assert [i["contactId"] for i in q["name_case"]["items"]] == [caps]
    assert q["bad_email"]["count"] == 1 and q["bad_birthday"]["count"] == 1 and q["bad_phone"]["items"][0]["detail"] == "12"
    assert {i["contactId"] for i in q["repeats"]["items"]} == {rep}
    assert later in {i["contactId"] for i in q["national_phone"]["items"]}
    client.post("/api/quality/fix", json={"check": "name_case"})
    assert client.get(f"/api/contacts/{caps}").json()["fn"] == "Ann-Marie van der Berg"
    client.post("/api/quality/fix", json={"check": "repeats"})
    r = client.get(f"/api/contacts/{rep}").json()
    assert len(r["emails"]) == 1 and len(r["phones"]) == 2
    out = client.post("/api/quality/fix", json={"check": "national_phone", "countryCode": "+32", "ids": [later]}).json()
    assert out["fixed"] == ["Later Person"] and client.get(f"/api/contacts/{later}").json()["phones"][0]["value"] == "+32 16 22 33 44"
    assert client.post("/api/quality/fix", json={"check": "bad_email"}).status_code == 400
    assert lonely
