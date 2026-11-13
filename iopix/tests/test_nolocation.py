"""Metadata quality: photos without a location are listed, can be accepted as they are, and shown again."""
import sqlite3


def test_no_location_list_and_accept(client, lib):
    q = client.get("/api/quality").json()
    nl = q["nolocation"]
    con = sqlite3.connect(lib["db"])
    without = con.execute("SELECT count(*) FROM Images i WHERE i.status = 1 AND i.id NOT IN (SELECT imageid FROM ImagePositions WHERE latitudeNumber IS NOT NULL)").fetchone()[0]
    con.close()
    assert nl["count"] + nl["accepted"] == without and nl["count"] > 0
    pid = nl["items"][0]["photo"]
    assert nl["items"][0]["name"] and "ts" in nl["items"][0]
    assert client.post("/api/quality/accept", json={"photos": [pid], "check": "nolocation"}).status_code == 200
    q2 = client.get("/api/quality").json()["nolocation"]
    assert q2["count"] == nl["count"] - 1 and q2["accepted"] == nl["accepted"] + 1 and pid not in [x["photo"] for x in q2["items"]]
    assert pid in client.get("/api/quality/accepted?check=nolocation").json()["photos"]
    page = client.get("/api/quality/items?check=nolocation&offset=0&limit=5").json()
    assert page["total"] == q2["count"] and len(page["items"]) <= 5
    client.post("/api/quality/accept", json={"photos": [pid], "check": "nolocation", "on": False})
    assert client.get("/api/quality").json()["nolocation"]["count"] == nl["count"]
