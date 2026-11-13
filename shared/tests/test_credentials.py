import pytest
from fastapi.testclient import TestClient

from iosuite_shared import admin, credentials, db, suite, users
from tests.test_admin import make_app, signed_in


def test_declare_lists_without_values(monkeypatch):
    monkeypatch.setenv("ACCUWEATHER_API_KEY", "from-env")
    items = [{"name": "ha_token", "label": "Home Assistant token", "hint": "long-lived", "env": "HA_TOKEN"},
             {"name": "accuweather_key", "label": "AccuWeather key", "env": "ACCUWEATHER_API_KEY"}]
    credentials.declare("iostart", items)
    credentials.put("iostart", "ha_token", "abc123")
    credentials.declare("iostart", items)  # every start: the value stays
    assert credentials.get("iostart", "ha_token") == "abc123"
    ls = {k["name"]: k for k in credentials.listing()}
    assert ls["ha_token"]["set"] and not ls["accuweather_key"]["set"] and ls["accuweather_key"]["envSet"]
    assert "abc123" not in str(ls)
    credentials.put("iostart", "ha_token", "")
    assert credentials.get("iostart", "ha_token") == "" and len(credentials.listing("iostart")) == 2
    with pytest.raises(ValueError):
        credentials.put("iostart", "Bad Name", "x")


def test_admin_keys_and_forget_app():
    suite.register("iocalendar", name="ioCalendar", url="https://cal.example.com", version="1.0")
    credentials.declare("iocalendar", [{"name": "iocontact_password", "label": "ioContact password"}])
    me = users.create("alex", "secret123", suite_admin=True)
    k = admin.set_key(me, "iocalendar", "iocontact_password", "pw")
    assert k["set"] and k["updatedBy"] == "alex" and k["appName"] == "ioCalendar"
    with pytest.raises(LookupError):
        admin.set_key(me, "iocalendar", "undeclared", "x")
    assert {a["app"]: a for a in admin.apps()}["iocalendar"]["credentials"] == 1
    assert admin.forget_app("iocalendar", data=True) and credentials.listing("iocalendar") == []


def test_api_keys_suite_admins_only():
    app = make_app()
    users.create("alex", "secret123", suite_admin=True)
    users.create("ann", "secret123", "admin", "iostart")
    credentials.declare("iostart", [{"name": "ha_token", "label": "Home Assistant token"}])
    c = signed_in(app, "alex", "secret123")
    items = c.get("/api/suite-admin/keys").json()["items"]
    assert {(k["app"], k["name"]) for k in items} == {("iostart", "ha_token"), ("", "cf_access_client_id"), ("", "cf_access_client_secret"),
                                                     ("", "cf_kv_account_id"), ("", "cf_kv_namespace_id"), ("", "cf_kv_api_token")}
    assert signed_in(app, "ann", "secret123").get("/api/suite-admin/keys").status_code == 403
    assert TestClient(app, base_url="http://home.example.com").put("/api/suite-admin/keys/iostart/ha_token", json={"value": "x"}).status_code == 401
    r = c.put("/api/suite-admin/keys/iostart/ha_token", json={"value": "s3cret"})
    assert r.status_code == 200 and r.json()["set"] and "s3cret" not in r.text
    assert credentials.get("iostart", "ha_token") == "s3cret"
    assert c.put("/api/suite-admin/keys/iostart/nope", json={"value": "x"}).status_code == 404
    assert c.put("/api/suite-admin/keys/iostart/ha_token", json={"value": 5}).status_code == 400
    assert c.delete("/api/suite-admin/keys/iostart/ha_token").status_code == 200 and not credentials.get("iostart", "ha_token")
    assert db
