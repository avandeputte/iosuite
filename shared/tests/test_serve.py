import socket
import sys
import types

import pytest

from iosuite_shared import serve


def test_hosts():
    assert serve.hosts("") == ["0.0.0.0"] and serve.hosts(None) == ["0.0.0.0"]
    assert serve.hosts("127.0.0.1") == ["127.0.0.1"]
    assert serve.hosts(" 127.0.0.1, 192.168.1.151 ,[::1]") == ["127.0.0.1", "192.168.1.151", "[::1]"]


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_run(monkeypatch):
    calls = []

    class Server:
        def __init__(self, config):
            self.config = config

        def run(self, sockets=None):
            calls.append(("server", self.config, [s.getsockname()[0] for s in sockets]))
            for s in sockets:
                s.close()
    fake = types.SimpleNamespace(run=lambda target, **kw: calls.append(("run", target, kw)), Server=Server,
                                 Config=lambda target, **kw: (target, kw))
    monkeypatch.setitem(sys.modules, "uvicorn", fake)
    serve.run("app.main:app", "127.0.0.1", 8630, proxy_headers=False)
    assert calls == [("run", "app.main:app", {"host": "127.0.0.1", "port": 8630, "proxy_headers": False})]
    port = _free_port()
    serve.run("app.main:app", "127.0.0.1,127.0.0.2", port, proxy_headers=False)
    assert calls[1] == ("server", ("app.main:app", {"host": "127.0.0.1", "port": port, "proxy_headers": False}), ["127.0.0.1", "127.0.0.2"])
    with pytest.raises(SystemExit) as e:
        serve.run("app.main:app", "127.0.0.1,192.0.2.77", port)  # not an address of this machine
    assert "192.0.2.77" in str(e.value)


def test_every_app_starts_the_same_way(monkeypatch):
    got = []
    monkeypatch.setattr(serve, "run", lambda target, host, port, **kw: got.append((target, host, port, kw)))
    cfg = types.SimpleNamespace(HOST="127.0.0.1", PORT=8640, TLS_CERT_FILE="", TLS_KEY_FILE="")
    serve.app(cfg, timeout_keep_alive=120)
    assert got == [("app.main:app", "127.0.0.1", 8640, {"proxy_headers": False, "ssl_certfile": None, "ssl_keyfile": None,
                                                         "timeout_keep_alive": 120})]


def test_the_page_its_manifest_and_static_folder(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from iosuite_shared import pages
    (tmp_path / "index.html").write_text('<script src="static/app.js"></script><link href="static/app.css">')
    (tmp_path / "manifest.webmanifest").write_text("{}")
    (tmp_path / "sw.js").write_text("// sw")
    a, b = FastAPI(), FastAPI()
    pages.mount(a, tmp_path, "3.9.0")
    pages.mount(b, tmp_path, "3.9.0", service_worker=True)
    c = TestClient(a)
    r = c.get("/")
    assert '"static/app.js?v=3.9.0"' in r.text and '"static/app.css?v=3.9.0"' in r.text and r.headers["cache-control"] == "no-cache"
    assert c.get("/manifest.webmanifest").headers["content-type"] == "application/manifest+json"
    assert c.get("/static/sw.js").text == "// sw" and c.get("/sw.js").status_code == 404
    assert TestClient(b).get("/sw.js").headers["content-type"].startswith("text/javascript")


def test_the_mcp_switch_and_its_box():
    from iosuite_shared import mcp
    store = {}
    s = mcp.Switch(lambda k, d: store.get(k, d), store.__setitem__, False, "Lets an assistant in.")
    assert s.info() == {"mcpEnabled": False, "mcpLocked": False, "mcpAbout": "Lets an assistant in."}
    s.apply({"other": 1})
    assert not s.enabled()
    s.apply({"mcpEnabled": True})
    assert s.enabled() and store == {"mcp_enabled": "1"}
    locked = mcp.Switch(lambda k, d: d, store.__setitem__, True, "")
    assert locked.enabled() and locked.info()["mcpLocked"]
    with pytest.raises(ValueError):
        locked.apply({"mcpEnabled": False})


def test_page_modules_are_never_kept_stale(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from iosuite_shared import pages
    (tmp_path / "js").mkdir()
    (tmp_path / "js" / "main.js").write_text("export const a = 1;")
    (tmp_path / "app.css").write_text("body{}")
    (tmp_path / "index.html").write_text("<p>")
    app = FastAPI()
    pages.mount(app, tmp_path, "1.0")
    c = TestClient(app)
    assert c.get("/static/js/main.js").headers["cache-control"] == "no-cache"
    assert "cache-control" not in c.get("/static/app.css").headers
