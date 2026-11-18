"""The suite's standard endpoints (/api/suite/*), answered through ioDocs' own API as the viewer."""
import datetime as dt


def test_search_item_and_tile(client):
    soon = (dt.date.today() + dt.timedelta(days=10)).isoformat()
    r = client.post("/api/documents", json={"title": "Ava's passport", "kind": "passport", "expiresOn": soon})
    assert r.status_code in (200, 201), r.text
    did = r.json()["id"]
    x = client.get("/api/suite/search", params={"q": "passport"}).json()["items"][0]
    assert (x["kind"], x["id"], x["title"], x["href"]) == ("document", str(did), "Ava's passport", f"#/doc/{did}")
    assert f"expires {soon}" in x["text"]
    assert client.get(f"/api/suite/items/document/{did}").json()["title"] == "Ava's passport"
    assert client.get("/api/suite/items/document/999999").status_code == 404
    t = client.get("/api/suite/tile").json()
    assert [d["title"] for d in t["items"]] == ["Ava's passport"] and t["items"][0]["days"] == 10 and t["more"] == 0
