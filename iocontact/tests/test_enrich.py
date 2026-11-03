"""Enrichment: lookups file suggestions; nothing changes until a person accepts one. Also over MCP."""
import json

from app import enrich
from tests.test_api import mk
from tests.test_mcp import app_password, call

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def fake_get(url, accept="application/json", limit=2_000_000):
    if "gravatar.com/avatar/" in url or url.startswith("https://avatars.example/"):
        return PNG, "image/png"
    if "api.gravatar.com/v3/profiles/" in url:
        return json.dumps({"display_name": "Ann Lee", "job_title": "Engineer", "company": "Acme", "location": "Ghent",
                           "verified_accounts": [{"url": "https://www.linkedin.com/in/annlee", "service_label": "LinkedIn"}]}).encode(), "application/json"
    if "api.github.com/users/annlee" in url:
        return json.dumps({"name": "Ann Lee", "company": "@acme", "blog": "ann.example", "html_url": "https://github.com/annlee",
                           "avatar_url": "https://avatars.example/ann", "twitter_username": "ann_x"}).encode(), "application/json"
    raise OSError("not reachable in tests")


def test_lookup_suggest_accept_dismiss(client, family_id, monkeypatch):
    monkeypatch.setattr(enrich, "_get", fake_get)
    c = mk(client, family_id, fn="Ann Lee", org="Acme", emails=[{"value": "ann@example.com"}], social=[{"service": "github", "value": "annlee"}])
    out = client.post(f"/api/contacts/{c['id']}/lookup").json()
    assert out["added"] >= 5 and set(out["sources"]) == {"gravatar", "github"}
    items = client.get(f"/api/suggestions?contact={c['id']}").json()["items"]
    fields = {(x["field"], json.dumps(x["value"], sort_keys=True)) for x in items}
    assert ("title", '"Engineer"') in fields and not any(f == "org" for f, _ in fields)  # Acme is known already
    assert any(f == "social" and "linkedin" in v for f, v in fields) and any(f == "social" and "ann_x" in v for f, v in fields)
    assert client.get(f"/api/contacts/{c['id']}").json().get("title") is None  # nothing changed yet
    title = next(x for x in items if x["field"] == "title")
    client.post(f"/api/suggestions/{title['id']}/accept")
    assert client.get(f"/api/contacts/{c['id']}").json()["title"] == "Engineer"
    photos = [x for x in items if x["field"] == "photo"]
    client.post(f"/api/suggestions/{photos[0]['id']}/accept")
    assert client.get(f"/api/contacts/{c['id']}").json()["hasPhoto"]
    li = next(x for x in items if x["field"] == "social" and "linkedin" in json.dumps(x["value"]))
    client.post(f"/api/suggestions/{li['id']}/dismiss")
    client.post(f"/api/contacts/{c['id']}/lookup")  # again: what was dismissed or accepted is not offered again
    again = client.get(f"/api/suggestions?contact={c['id']}").json()["items"]
    assert not any(x["field"] in ("title", "photo") for x in again) and not any("linkedin" in json.dumps(x["value"]) for x in again)
    assert client.get("/api/status").json()["suggestions"] == len(again)


def test_mcp_suggestions_wait_for_a_person(client, family_id):
    auth, _ = app_password(client)
    client.post("/api/server", json={"mcpEnabled": True})
    c = mk(client, family_id, fn="Tim Ray")
    out = call(client, auth, "suggest_contact_update", contact="Tim Ray", source="Claude, web search",
               suggestions=[{"field": "title", "value": "Teacher", "evidence": "https://school.example/staff"},
                            {"field": "social", "value": {"service": "linkedin", "value": "https://www.linkedin.com/in/timray"}},
                            {"field": "birthday", "value": "1990-04-05"}, {"field": "shoe_size", "value": "44"}])
    assert out["added"] == 3 and len(out["errors"]) == 1
    assert client.get(f"/api/contacts/{c['id']}").json().get("title") is None
    assert {x["field"] for x in call(client, auth, "list_suggestions", contact="Tim Ray")} == {"title", "social", "birthday"}
    names = {t["name"] for t in __import__("tests.test_mcp", fromlist=["rpc"]).rpc(client, "tools/list", auth=auth)[1]["result"]["tools"]}
    assert "create_app_password" not in names and not any("accept" in n for n in names)


def test_mcp_duplicates_merge_undo_quality(client, family_id):
    auth, _ = app_password(client)
    client.post("/api/server", json={"mcpEnabled": True})
    mk(client, family_id, name={"given": "Robert", "family": "Smith"}, org="Acme")
    mk(client, family_id, name={"given": "Bob", "family": "Smith"}, org="Globex", phones=[{"value": "+1 555 0100"}])
    groups = call(client, auth, "find_duplicates")
    groups = groups if isinstance(groups, list) else [groups]
    assert len(groups) == 1 and groups[0]["level"] == "possible"  # a nickname alone, and other companies
    pv = call(client, auth, "preview_merge", contacts=["Robert Smith", "Bob Smith"])
    assert "org" in pv["choices"]
    out = call(client, auth, "merge_contacts", keep="Robert Smith", others=["Bob Smith"], choices={"org": "Bob Smith"})
    assert out["into"]["org"] == "Globex" and out["into"]["phones"]
    assert call(client, auth, "undo_merge", merge_id=out["mergeId"])["restored"] == ["Robert Smith", "Bob Smith"]
    call(client, auth, "mark_not_duplicates", contacts=["Robert Smith", "Bob Smith"])
    assert call(client, auth, "find_duplicates") == []
    mk(client, family_id, fn="SHOUTY PERSON")
    rep = {x["check"]: x for x in call(client, auth, "data_quality_report")}
    assert rep["name_case"]["count"] == 1
    assert call(client, auth, "fix_data_quality", check="name_case")["fixed"] == ["SHOUTY PERSON"]
