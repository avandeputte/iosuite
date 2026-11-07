"""The start page's keys and tokens live in the Shared ioSuite database (app/keys.py)."""
from iosuite_shared import credentials

from app import keys, weather


def test_keys_are_kept_in_the_suite_and_listed(client):
    keys.declare()
    credentials.put("iosuite", "ha_token", "old-ha-token")
    credentials.put("iosuite", "accuweather_key", "old-aw-key")
    assert weather.api_key() == "old-aw-key"
    items = {k["name"]: k for k in client.get("/api/suite-admin/keys").json()["items"] if k["app"] == "iosuite"}
    assert items["ha_token"]["set"] and items["accuweather_key"]["label"] == "AccuWeather API key"
    assert "old-ha-token" not in str(items)
    assert client.put("/api/suite-admin/keys/iosuite/accuweather_key", json={"value": "new-aw"}).json()["updatedBy"] == "alex"
    assert weather.api_key() == "new-aw"
    client.post("/api/weather/settings", json={"key": ""})
    assert weather.api_key() == "" and credentials.get("iosuite", "ha_token") == "old-ha-token"
    credentials.put("iosuite", "ha_token", "")
