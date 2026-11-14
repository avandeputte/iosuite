import io
import urllib.error

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from iosuite_shared import admin, apppasswords, credentials, links, suite, users
from iosuite_shared.fastapi import Auth


def provider_app():
    auth = Auth("iocontact", register=False)
    app = FastAPI()
    app.middleware("http")(auth.middleware())

    @app.get("/api/contacts")
    def contacts(request: Request):
        return {"who": auth.current_user(request)["name"]}

    @app.post("/api/contacts")
    def add(request: Request):
        return {"ok": True}

    @app.get("/face/1")
    def face(request: Request):
        return {"ok": True}

    @app.get("/dav/x")
    def dav(request: Request):
        return {"ok": True}
    return app


def test_service_account_and_read_only_app_password():
    users.create("alex", "secret123", suite_admin=True)
    assert links.url("iocontact") is None and not links.available("iocontact")
    suite.register("iocontact", name="ioContact", url="https://contacts.example.com/", version="1")
    assert links.url("iocontact") == "https://contacts.example.com"
    h = links.headers("iocalendar", "iocontact")
    svc = users.service_account("iocalendar")
    assert svc["name"] == "iocalendar-app" and svc["service"] == "iocalendar" and not svc["listed"]
    assert users.role_of(users.get(svc["id"]), "iocontact") == "viewer"
    assert links.headers("iocalendar", "iocontact") == h  # kept, not made again
    assert [u["name"] for u in users.list_users()] == ["alex"]  # people only
    assert "iocalendar-app" in [u["name"] for u in users.list_users(services=True)]
    assert users.authenticate("iocalendar-app", "anything") is None
    assert credentials.listing() == [] or all(not k["name"].startswith("link_") for k in credentials.listing())
    from iosuite_shared import db
    assert [(r["app"], r["scope"]) for r in db.q("SELECT app, scope FROM ios_app_passwords WHERE user_id = %s", (svc["id"],))] == [("iocontact", "read")]
    # the suite looks after its own accounts: the Security panel neither shows nor changes them
    assert admin.app_passwords() == [] and [u["name"] for u in admin.accounts()] == ["alex"]
    pid = db.one("SELECT id FROM ios_app_passwords WHERE user_id = %s", (svc["id"],))["id"]
    for change in (lambda: admin.revoke_app_password(pid), lambda: admin.set_app_password_scope(pid, ""),
                   lambda: admin.new_app_password(svc["id"], "iopix", "x"), lambda: admin.update(None, svc["id"], {"email": "a@b.c"}),
                   lambda: admin.delete(None, svc["id"]), lambda: admin.end_sessions(svc["id"])):
        with pytest.raises(LookupError):
            change()
    assert admin.overview()["scopes"] == ["", "dav"]
    c = TestClient(provider_app(), base_url="http://contacts.example.com")
    auth_h = {"Authorization": h["Authorization"]}
    assert c.get("/api/contacts", headers=auth_h).json() == {"who": "iocalendar-app"}
    assert c.post("/api/contacts", headers=auth_h).status_code == 403
    assert c.get("/dav/x", headers=auth_h).status_code == 403 and c.get("/face/1", headers=auth_h).status_code == 200
    assert users.any_users()


def test_first_run_is_not_spoiled_by_a_service_account():
    users.service_account("iopix")
    assert not users.any_users()


def test_revoked_password_is_made_again(monkeypatch):
    suite.register("iopix", name="ioPix", url="https://photo.example.com", version="1")
    first = links.password("iocontact", "iopix")[1]
    seen = []

    def fake(req, timeout=None):
        seen.append(req.headers["Authorization"])
        if len(seen) == 1:
            raise urllib.error.HTTPError(req.full_url, 401, "no", {}, io.BytesIO(b""))
        return io.BytesIO(b'{"ok": 1}')
    monkeypatch.setattr(links, "call", fake)
    assert links.json("iocontact", "iopix", "/api/meta") == {"ok": 1}
    second = links.password("iocontact", "iopix")[1]
    assert second != first and len(seen) == 2 and seen[0] != seen[1]
    assert apppasswords.authenticate(None, first, "iopix") is None and apppasswords.authenticate(None, second, "iopix")
    with pytest.raises(RuntimeError):
        links.get("iocontact", "nothere", "/api/x")


def test_cloudflare_service_token_goes_along():
    suite.register("iopix", name="ioPix", url="https://photo.example.com", version="1")
    assert "CF-Access-Client-Id" not in links.headers("iocontact", "iopix")
    assert links.headers("iocontact", "iopix", sign_in=False) == {}
    me = users.create("alex", "secret123", suite_admin=True)
    admin.set_key(me, "_suite", "cf_access_client_id", "id.access")
    admin.set_key(me, "_suite", "cf_access_client_secret", "sec")
    h = links.headers("iocontact", "iopix")
    assert h["CF-Access-Client-Id"] == "id.access" and h["CF-Access-Client-Secret"] == "sec"
    assert set(links.headers("iocontact", "iopix", sign_in=False)) == {"CF-Access-Client-Id", "CF-Access-Client-Secret"}
    assert {k["name"] for k in admin.keys("_suite")} == {"cf_access_client_id", "cf_access_client_secret", "cf_kv_account_id",
                                                         "cf_kv_namespace_id", "cf_kv_api_token"}
    links.forget("iocontact")
    assert admin.app_passwords() == []


def test_internal_address_first_then_public(monkeypatch):
    suite.register("iopix", name="ioPix", url="https://photo.example.com", version="1", internal_url="http://192.168.1.5:8600")
    assert links.addresses("iopix") == ["http://192.168.1.5:8600", "https://photo.example.com"]
    assert links.url("iopix") == "https://photo.example.com"
    seen = []

    def fake(req, timeout=None):
        seen.append(req.full_url)
        if "192.168" in req.full_url:
            raise urllib.error.URLError("refused")
        return io.BytesIO(b'{"ok": 2}')
    monkeypatch.setattr(links, "call", fake)
    assert links.json("iocontact", "iopix", "/api/meta") == {"ok": 2}
    assert seen == ["http://192.168.1.5:8600/api/meta", "https://photo.example.com/api/meta"]


def test_same_machine_goes_over_localhost(monkeypatch):
    suite.register("iocontact", name="ioContact", url="https://contacts.example.com", version="1", internal_url="http://127.0.0.1:8640")
    assert links.addresses("iocontact") == ["http://127.0.0.1:8640", "https://contacts.example.com"]
    monkeypatch.setattr(links, "_this_machine", lambda host: host == "192.168.1.9")
    suite.register("iocontact", name="ioContact", url="https://contacts.example.com", version="1", internal_url="http://192.168.1.9:8640")
    assert links.addresses("iocontact") == ["http://127.0.0.1:8640", "http://192.168.1.9:8640", "https://contacts.example.com"]
    monkeypatch.setattr(links, "_this_machine", lambda host: False)
    assert links.addresses("iocontact") == ["http://192.168.1.9:8640", "https://contacts.example.com"]
    monkeypatch.undo()
    assert not links._this_machine("203.0.113.7") and links._this_machine("127.0.0.1") and not links._this_machine("a.lan")


# ---- asking as the viewer, and where a request to another app may go

class Asker:
    """A request as an app's route sees it: the viewer's session cookie, or the Authorization header they sent."""

    def __init__(self, cookie=None, authorization=None):
        self.cookies = {"iothing_session": cookie} if cookie else {}
        self.headers = {"authorization": authorization} if authorization else {}


class Answer(io.BytesIO):
    headers = {"Content-Type": "application/json"}


def test_as_viewer_passes_the_persons_own_sign_in_on(monkeypatch):
    suite.register("iotask", name="ioTask", url="https://tasks.example.com", version="1", internal_url="http://192.168.1.5:8670")
    me = users.create("alex", "secret123", suite_admin=True)
    admin.set_key(me, "_suite", "cf_access_client_id", "id.access")
    admin.set_key(me, "_suite", "cf_access_client_secret", "sec")
    links.ask_again()
    seen = []

    def fake(req, timeout=None):
        seen.append((req.get_method(), req.full_url, {k.lower(): v for k, v in req.header_items()}, req.data))
        if "192.168" in req.full_url:
            raise urllib.error.URLError("refused")
        return Answer(b'{"items": [1]}')
    monkeypatch.setattr(links, "call", fake)
    assert links.as_viewer(Asker(cookie="tok"), "iotask", "/api/tasks", {"status": "open"}, user_agent="ioCalendar") == {"items": [1]}
    assert [u for _, u, _, _ in seen] == ["http://192.168.1.5:8670/api/tasks?status=open", "https://tasks.example.com/api/tasks?status=open"]
    h = seen[-1][2]
    assert h["cookie"] == "iothing_session=tok" and "authorization" not in h and h["user-agent"] == "ioCalendar"
    assert h["cf-access-client-id"] == "id.access" and h["cf-access-client-secret"] == "sec"  # never an app password
    # the address that answered is asked first from now on; a body is POSTed as JSON; without a cookie, the header they sent
    del seen[:]
    assert links.as_viewer(Asker(authorization="Basic abc"), "iotask", "/api/tasks", body={"title": "x"}) == {"items": [1]}
    (method, where, h, data), = seen
    assert (method, where, data) == ("POST", "https://tasks.example.com/api/tasks", b'{"title": "x"}')
    assert h["authorization"] == "Basic abc" and "cookie" not in h and h["content-type"] == "application/json"
    assert links.as_viewer(Asker(cookie="tok"), "iotask", "/thumb/1", raw=True, method="DELETE") == (b'{"items": [1]}', "application/json")
    assert seen[-1][0] == "DELETE" and seen[-1][2]["accept"] == "*/*"
    assert "Cookie" not in links.viewer_headers(None) and links.viewer_headers(None)["CF-Access-Client-Id"] == "id.access"


def test_as_viewer_an_answer_is_an_answer_and_silence_is_remembered(monkeypatch):
    suite.register("iotask", name="ioTask", url="https://tasks.example.com", version="1", internal_url="http://192.168.1.5:8670")
    links.ask_again()
    tried = []

    def refuses(req, timeout=None):
        tried.append(req.full_url)
        raise urllib.error.HTTPError(req.full_url, 403, "no", {}, io.BytesIO(b'{"detail": "Members only"}'))
    monkeypatch.setattr(links, "call", refuses)
    with pytest.raises(urllib.error.HTTPError) as e:
        links.as_viewer(Asker(cookie="tok"), "iotask", "/api/tasks")
    assert e.value.code == 403 and len(tried) == 1 and not links.resting("iotask")  # it answered: the next address is not tried

    def down(req, timeout=None):
        tried.append(req.full_url)
        raise urllib.error.URLError("refused")
    monkeypatch.setattr(links, "call", down)
    del tried[:]
    with pytest.raises(links.Unreachable) as e:
        links.as_viewer(Asker(cookie="tok"), "iotask", "/thumb/1", raw=True, patient=True)
    assert len(tried) == 2 and isinstance(e.value.why, urllib.error.URLError) and not links.resting("iotask")  # a picture does not count
    with pytest.raises(links.Unreachable):
        links.as_viewer(Asker(cookie="tok"), "iotask", "/api/tasks")
    assert 0 < links.resting("iotask") <= links.BREAK_S and not links.resting("iopix")
    monkeypatch.setattr(links, "call", lambda req, timeout=None: Answer(b"<html>not the app</html>"))
    with pytest.raises(links.Unreachable) as e:  # something else answers there: not JSON, not the app
        links.as_viewer(Asker(cookie="tok"), "iotask", "/api/tasks")
    assert isinstance(e.value.why, ValueError)
    monkeypatch.setattr(links, "call", lambda req, timeout=None: Answer(b"{}"))
    assert links.as_viewer(Asker(cookie="tok"), "iotask", "/api/tasks") == {} and not links.resting("iotask")
    # an app that is not in the suite's list: nothing to ask (public: the address it is known by, when it has no other)
    with pytest.raises(links.Unreachable) as e:
        links.as_viewer(Asker(cookie="tok"), "ionote", "/api/notes")
    assert e.value.why is None and "no address" in str(e.value.reason)
    links.ask_again()


def test_a_redirect_to_another_host_is_not_followed():
    """urllib sends every header along with a redirect: the session cookie, the app password and the Cloudflare Access
    secret must not go to the sign-in page of a proxy in front of the app, or anywhere but the host that was asked."""
    import http.server
    import threading
    import urllib.request

    got = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            got.append((self.path, self.headers.get("Cookie"), self.headers.get("Authorization"), self.headers.get("CF-Access-Client-Secret")))
            if self.path == "/elsewhere":
                self.send_response(302)
                self.send_header("Location", f"http://localhost:{self.server.server_port}/login")
            elif self.path == "/slash":
                self.send_response(301)
                self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/slash/")
            else:
                self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    secrets = {"Cookie": "iothing_session=tok", "Authorization": "Basic abc", "CF-Access-Client-Secret": "sec"}
    try:
        with pytest.raises(urllib.error.HTTPError) as e:
            links.call(urllib.request.Request(base + "/elsewhere", headers=secrets), 5)
        assert e.value.code == 302 and [p for p, *_ in got] == ["/elsewhere"]  # localhost is another host than 127.0.0.1: never asked
        with links.call(urllib.request.Request(base + "/slash", headers=secrets), 5) as r:  # the same host: followed
            assert r.status == 200
        assert got[-1] == ("/slash/", "iothing_session=tok", "Basic abc", "sec")
    finally:
        server.shutdown()
        server.server_close()
