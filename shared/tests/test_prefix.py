"""An app served in a folder of an address (iosuite_shared.prefix): which folder a request came through, the path the
routes see, and the addresses made from it."""
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from iosuite_shared import prefix, suite
from iosuite_shared.fastapi import Auth
from iosuite_shared.proxyauth import Forwarded


def make_app():
    auth = Auth("iocalendar")
    app = FastAPI(docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.middleware("http")(auth.middleware(open_paths=("/", "/api/where", "/api/docs", "/api/openapi.json")))
    auth.install(app)

    @app.get("/api/where", dependencies=[auth.access.public])
    def where(request: Request):
        return {"folder": prefix.of(request), "path": request.url.path, "base": prefix.base_url(request), "origin": suite.origin_of(request)}
    return app


def test_clean():
    assert prefix.clean("calendar/") == "/calendar" and prefix.clean(" /a/b ") == "/a/b"
    for bad in ("", "/", None, "/a b", "/a/../b", "/a?x", "//evil.example.com", "/a\r\nX: y", "/" + "a" * 200):
        assert prefix.clean(bad) == "", bad
    assert prefix.of_url("https://Home.Example.com/calendar/") == ("home.example.com", 443, "/calendar")
    assert prefix.of_url("http://server.lan:9000/a") == ("server.lan", 9000, "/a")
    assert prefix.of_url("https://calendar.example.com") == ("", 0, "") and prefix.of_url("nonsense") == ("", 0, "")


def test_folder_of_public_url(monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "https://home.example.com/calendar")
    c = TestClient(make_app(), base_url="https://home.example.com")
    want = {"folder": "/calendar", "path": "/api/where", "base": "https://home.example.com/calendar", "origin": "https://home.example.com/calendar"}
    assert c.get("/calendar/api/where").json() == want, "the proxy left the folder on the path"
    assert c.get("/api/where").json() == want, "the proxy took it off"
    r = c.get("/calendar", follow_redirects=False)
    assert r.status_code == 308 and r.headers["location"] == "/calendar/"
    assert c.get("/calendarx/api/where").status_code == 404
    assert "/calendar/api/openapi.json" in c.get("/calendar/api/docs").text
    assert c.get("/calendar/api/openapi.json").json()["servers"] == [{"url": "/calendar"}]
    # straight to the app's port (another app on this server, the LAN): no folder
    lan = TestClient(make_app(), base_url="http://192.168.1.5:8620")
    assert lan.get("/api/where").json() == {"folder": "", "path": "/api/where", "base": "http://192.168.1.5:8620", "origin": "http://192.168.1.5:8620"}
    assert lan.get("/calendar/api/where").status_code == 404
    # the same name on the app's own port is not the public address; without a port (nginx's $host) it is
    assert lan.get("/api/where", headers={"host": "home.example.com:8620"}).json()["folder"] == ""
    assert lan.get("/api/where", headers={"host": "home.example.com:443"}).json()["folder"] == "/calendar"
    # through a proxy that names the public host in X-Forwarded-Host
    assert lan.get("/api/where", headers={"x-forwarded-host": "home.example.com"}).json()["folder"] == "/calendar"


def test_folder_of_the_proxys_header(monkeypatch):
    monkeypatch.delenv("PUBLIC_URL", raising=False)
    c = TestClient(make_app(), base_url="http://192.168.1.5:8630")
    h = {"x-forwarded-prefix": "/notes"}
    assert c.get("/api/where", headers=h).json()["folder"] == "", "only from this machine or a listed reverse proxy"
    monkeypatch.setattr(Forwarded, "allows", staticmethod(lambda peer: True))
    assert c.get("/api/where", headers=h).json() == {"folder": "/notes", "path": "/api/where", "base": "http://192.168.1.5:8630/notes", "origin": "http://192.168.1.5:8630/notes"}
    assert c.get("/notes/api/where", headers=h).json()["path"] == "/api/where"
    assert c.get("/api/where", headers={"x-forwarded-prefix": "//evil.example.com"}).json()["folder"] == ""
    monkeypatch.setenv("PUBLIC_URL", "https://home.example.com/calendar")  # the header wins over PUBLIC_URL's folder
    assert c.get("/api/where", headers={**h, "host": "home.example.com"}).json()["folder"] == "/notes"


def test_an_address_with_a_folder_ranks_like_its_host():
    assert suite._rank("https://home.example.com/calendar") == suite._rank("https://home.example.com")
    assert suite._rank("http://127.0.0.1:8620/calendar") == -1
    assert suite.clean_url("https://home.example.com/calendar/") == "https://home.example.com/calendar"


def test_the_shared_panels_ask_with_relative_addresses():
    from pathlib import Path
    import iosuite_shared
    from iosuite_shared import testing
    testing.check_relative(Path(iosuite_shared.__file__).parent)  # account, suite admin, server, related, the push worker
