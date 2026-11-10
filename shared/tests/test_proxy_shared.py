"""Proxy sign-in settings live once, suite-wide, in the Shared ioSuite database; the suite admin API changes them."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from iosuite_shared import db, proxyauth, users
from iosuite_shared.fastapi import Auth

AUD1, AUD2 = "a" * 64, "b" * 64


def make_app():
    auth = Auth("iosuite", register=False)
    app = FastAPI()
    app.middleware("http")(auth.middleware(open_prefixes=("/api/auth/",)))
    app.include_router(auth.router())
    app.include_router(auth.admin_router())
    return app


def signed_in(app, name, password):
    c = TestClient(app, base_url="http://home.example.com")
    assert c.post("/api/auth/login", json={"name": name, "password": password}).status_code == 200
    return c


def test_helpers():
    assert proxyauth.clean_team("https://MyTeam.cloudflareaccess.com/") == "myteam.cloudflareaccess.com"
    assert proxyauth.aud_tags(f" {AUD1}, {AUD2} {AUD1}") == [AUD1, AUD2]


def test_only_the_suite_wide_rows_count(monkeypatch):
    db.set_setting("cf_access_team", "t.cloudflareaccess.com", "")
    db.set_setting("cf_access_aud", f"{AUD1}, {AUD2}", "")
    db.set_setting("auth_proxy", "cloudflare", "")
    db.set_setting("auth_proxy_trusted", "10.0.0.0/8", "iocontacts")  # a per-app row: never read
    monkeypatch.setenv("CF_ACCESS_TEAM", "x.cloudflareaccess.com")  # nor the environment
    monkeypatch.setenv("AUTH_PROXY", "nginx")
    pr = proxyauth.Proxy("iocontacts")
    assert pr.mode() == "cloudflare" and pr.cf_settings() == ("t.cloudflareaccess.com", [AUD1, AUD2])
    assert pr.opt("AUTH_PROXY_TRUSTED") is None


def test_suite_admin_api(monkeypatch):
    for k in proxyauth.KEYS:
        monkeypatch.delenv(k, raising=False)
    app = make_app()
    users.create("alex", "secret123", suite_admin=True)
    users.create("ann", "secret123", "admin", "iosuite")
    c = signed_in(app, "alex", "secret123")
    assert c.get("/api/suite-admin/proxy").json()["values"]["AUTH_PROXY"] == ""
    assert c.put("/api/suite-admin/proxy", json={"AUTH_PROXY": "cloudflare", "CF_ACCESS_TEAM": "t.cloudflareaccess.com"}).status_code == 400
    r = c.put("/api/suite-admin/proxy", json={"AUTH_PROXY": "cloudflare", "CF_ACCESS_TEAM": "https://t.cloudflareaccess.com/", "CF_ACCESS_AUD": f"{AUD1} {AUD2}"}).json()
    assert r["values"]["CF_ACCESS_TEAM"] == "t.cloudflareaccess.com" and r["auds"] == [AUD1, AUD2] and r["here"]["cloudflareVerified"]
    assert c.put("/api/suite-admin/proxy", json={"AUTH_PROXY": "squid"}).status_code == 400
    assert signed_in(app, "ann", "secret123").get("/api/suite-admin/proxy").status_code == 403
    assert TestClient(app).get("/api/suite-admin/proxy").status_code == 401
    # the settings are the suite's: an admin of one app has no route to them (he could name himself the proxy)
    ann = signed_in(app, "ann", "secret123")
    assert ann.put("/api/suite-admin/proxy", json={"AUTH_PROXY_CREATE": "viewer"}).status_code == 403
    assert ann.post("/api/auth/proxy", json={"AUTH_PROXY": "header", "AUTH_PROXY_TRUSTED": "10.0.0.5"}).status_code in (404, 405)
    assert ann.get("/api/auth/proxy").status_code in (404, 405)
    assert not hasattr(proxyauth.Proxy("iopix"), "save")
    proxyauth.save_suite({"AUTH_PROXY_CREATE": "viewer"})
    assert db.settings_of("")["auth_proxy_create"] == "viewer" and not db.settings_of("iopix")
