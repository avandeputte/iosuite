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
