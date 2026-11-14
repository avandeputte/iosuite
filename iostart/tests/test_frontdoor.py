"""The suite on one address (app/frontdoor.py): the start page passes /calendar/… on to ioCalendar, as it came. The
"app" passed on to here is a small server of the test's own on a port of this machine, which answers what it was
asked."""
import hashlib
import json
import socket
import threading
import time

import pytest
import uvicorn
from iosuite_shared import proxyauth, suite

from app import frontdoor
from app.auth import auth


async def _echo(scope, receive, send):
    """Answers what it was asked: {method, path, raw, query, headers, size, sha}; /stream in three pieces; /moved a
    redirect; /cookies two cookies."""
    if scope["type"] != "http":
        return
    body = b""
    while True:
        m = await receive()
        body += m.get("body") or b""
        if not m.get("more_body"):
            break
    path = scope["path"]
    if path == "/stream":
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/event-stream")]})
        for part in (b"one ", b"two ", b"three"):
            await send({"type": "http.response.body", "body": part, "more_body": True})
        return await send({"type": "http.response.body", "body": b""})
    if path == "/moved":
        await send({"type": "http.response.start", "status": 302, "headers": [(b"location", b"/calendar/there"), (b"content-length", b"0")]})
        return await send({"type": "http.response.body", "body": b""})
    out = json.dumps({"method": scope["method"], "path": path, "raw": scope["raw_path"].decode(), "query": scope["query_string"].decode(),
                      "headers": [[k.decode(), v.decode()] for k, v in scope["headers"]], "size": len(body),
                      "sha": hashlib.sha256(body).hexdigest()}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(out)).encode()), (b"x-app", b"echo")]
    if path == "/cookies":
        headers += [(b"set-cookie", b"a=1; Path=/"), (b"set-cookie", b"b=2; Path=/")]
    await send({"type": "http.response.start", "status": 207 if scope["method"] == "PROPFIND" else 200, "headers": headers})
    await send({"type": "http.response.body", "body": b"" if scope["method"] == "HEAD" else out})


@pytest.fixture(scope="module")
def upstream():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(_echo, log_level="warning", lifespan="off"))
    t = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{sock.getsockname()[1]}"
    server.should_exit = True
    t.join(5)


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def door(client, upstream):
    """The switch on, ioCalendar and ioContact where the test's server is, ioTask where nobody answers; ioNote keeps
    the conftest's row, with no address inside the network."""
    suite.register("iostart", "ioStart", url="http://testserver", internal_url="http://127.0.0.1:8630")
    suite.register("iocalendar", "ioCalendar", url="https://calendar.example.com", internal_url=upstream)
    suite.register("iocontact", "ioContact", url="https://contacts.example.com", internal_url=upstream)
    suite.register("iotask", "ioTask", internal_url=f"http://127.0.0.1:{_closed_port()}")
    suite.set_one_address(True)
    yield client
    suite.set_one_address(False)


def headers_of(answer) -> dict:
    return {k.lower(): v for k, v in answer["headers"]}


def test_off_the_start_page_answers_everything_itself(client, upstream):
    suite.register("iocalendar", "ioCalendar", internal_url=upstream)
    frontdoor.forget()
    assert client.get("/calendar/echo").status_code == 404
    assert client.get("/calendar", follow_redirects=False).status_code == 404
    assert client.get("/.well-known/caldav", follow_redirects=False).status_code == 404


def test_a_folder_is_passed_on_as_it_came(door):
    r = door.get("/calendar/api/events?from=2026-01-01&q=a%2Fb", headers={"Accept-Language": "nl"})
    assert r.status_code == 200 and r.headers["x-app"] == "echo"
    a = r.json()
    assert a["method"] == "GET" and a["path"] == "/api/events" and a["query"] == "from=2026-01-01&q=a%2Fb"
    h = headers_of(a)
    assert h["x-forwarded-prefix"] == "/calendar" and h["host"] == "testserver" and h["x-forwarded-host"] == "testserver"
    assert h["x-forwarded-proto"] == "http" and h["x-forwarded-for"] == "testclient" and h["accept-language"] == "nl"
    assert [k for k, _ in a["headers"]].count("x-forwarded-prefix") == 1
    assert len(r.headers.get_list("date")) <= 1 and len(r.headers.get_list("server")) <= 1
    # what was encoded stays encoded: a name with a slash in it is one part of the path
    assert door.get("/calendar/dav/a%2Fb%20c/x.ics").json()["raw"] == "/dav/a%2Fb%20c/x.ics"
    assert door.get("/calendar/").json()["path"] == "/"


def test_the_start_page_itself_stays_where_it_was(door):
    assert door.get("/api/status").json()["app"] == "iostart"
    assert door.get("/").status_code == 200 and "<title>ioStart</title>" in door.get("/").text
    assert door.get("/static/app.js").status_code == 200
    assert door.get("/nothing/here").status_code == 404
    assert door.get("/notes/").status_code == 404  # recorded no address inside the network: no folder here


def test_the_folder_without_its_slash(door):
    r = door.get("/calendar", follow_redirects=False)
    assert r.status_code == 308 and r.headers["location"] == "/calendar/"
    assert door.get("/calendar?x=1", follow_redirects=False).headers["location"] == "/calendar/?x=1"


def test_any_method_and_a_body_larger_than_the_start_page_takes(door):
    data = bytes(range(256)) * 40000  # 10 MB: past ioStart's own cap, which is not its to apply
    r = door.put("/calendar/upload", content=data, headers={"Content-Type": "application/octet-stream"})
    a = r.json()
    assert a["method"] == "PUT" and a["size"] == len(data) and a["sha"] == hashlib.sha256(data).hexdigest()
    assert headers_of(a)["content-length"] == str(len(data))

    def pieces():
        yield b"a" * 70000
        yield b"b" * 70000
    a = door.post("/calendar/upload", content=pieces()).json()  # no length given: as it arrives
    assert a["size"] == 140000 and a["sha"] == hashlib.sha256(b"a" * 70000 + b"b" * 70000).hexdigest()
    r = door.request("PROPFIND", "/calendar/dav/", content=b"<propfind/>", headers={"Depth": "1"})
    assert r.status_code == 207 and r.json()["method"] == "PROPFIND" and headers_of(r.json())["depth"] == "1"
    r = door.head("/calendar/x")
    assert r.status_code == 200 and r.content == b"" and int(r.headers["content-length"]) > 0
    assert door.delete("/calendar/api/events/3").json()["method"] == "DELETE"


def test_the_answer_as_the_app_gave_it(door):
    r = door.get("/calendar/stream")
    assert r.text == "one two three" and r.headers["content-type"] == "text/event-stream"
    r = door.get("/calendar/moved", follow_redirects=False)  # the app's own redirect, not followed here
    assert r.status_code == 302 and r.headers["location"] == "/calendar/there"
    assert door.get("/calendar/cookies").headers.get_list("set-cookie") == ["a=1; Path=/", "b=2; Path=/"]


def test_nobody_names_the_signed_in_person_but_a_trusted_proxy(door):
    r = door.get("/calendar/x", headers={"Remote-User": "alex", "X-Forwarded-User": "alex", "Cf-Access-Authenticated-User-Email": "a@example.com",
                                         "X-Forwarded-Prefix": "/evil", "X-Forwarded-For": "10.0.0.9", "Cf-Access-Jwt-Assertion": "signed",
                                         "Cf-Connecting-Ip": "10.0.0.9"})
    h = headers_of(r.json())
    assert "remote-user" not in h and "x-forwarded-user" not in h and "cf-access-authenticated-user-email" not in h
    assert "cf-connecting-ip" not in h and h[proxyauth.OUTSIDE_HEADER] == "1"  # not the address the sign-in throttle counts by
    assert h["x-forwarded-prefix"] == "/calendar" and h["x-forwarded-for"] == "10.0.0.9, testclient"
    assert h["cf-access-jwt-assertion"] == "signed"  # every app checks its signature itself


def scope(peer, headers, scheme="http"):
    return {"type": "http", "scheme": scheme, "client": (peer, 1), "iothing.peer": peer,
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]}


def test_headers_from_this_machine_from_home_and_from_outside(client):
    # a reverse proxy on this machine (Caddy in front of the start page): its word is passed on
    h = dict(frontdoor._headers(scope("127.0.0.1", {"Host": "home.example.com", "Remote-User": "alex", "X-Forwarded-For": "8.8.8.8",
                                                    "Connection": "keep-alive, X-Mine", "X-Mine": "1", "Expect": "100-continue"}, "https"),
                                "/calendar", auth.proxy))
    assert h["remote-user"] == "alex" and h["x-forwarded-for"] == "8.8.8.8, 127.0.0.1" and h["x-forwarded-proto"] == "https"
    assert h[proxyauth.OUTSIDE_HEADER] == "1"  # the visitor behind the proxy is outside: the app is told
    assert "x-mine" not in h and "connection" not in h and "expect" not in h
    # someone at home, straight to the start page
    h = dict(frontdoor._headers(scope("192.168.1.50", {"Host": "192.168.1.10:8630", "Remote-User": "alex"}), "/calendar", auth.proxy))
    assert "remote-user" not in h and proxyauth.OUTSIDE_HEADER not in h and h["x-forwarded-for"] == "192.168.1.50"
    assert h["host"] == "192.168.1.10:8630" and h["x-forwarded-host"] == "192.168.1.10:8630"
    # someone outside, straight to the start page, saying they are not
    h = dict(frontdoor._headers(scope("8.8.8.8", {"Host": "home.example.com", proxyauth.OUTSIDE_HEADER: "", "X-Real-Ip": "127.0.0.1"}), "/calendar", auth.proxy))
    assert h[proxyauth.OUTSIDE_HEADER] == "1" and "x-real-ip" not in h and h["x-forwarded-for"] == "8.8.8.8"


def test_an_app_that_is_not_answering(door):
    r = door.get("/tasks/api/status")
    assert r.status_code == 502 and "/tasks/ is not answering" in r.text
    assert door.get("/calendar/x").status_code == 200  # the others go on


def test_phones_find_calendar_and_contacts_at_the_root(door):
    r = door.get("/.well-known/caldav", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/calendar/dav/"
    r = door.request("PROPFIND", "/.well-known/carddav", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/contacts/dav/"
    suite.forget("iocontact")
    assert door.get("/.well-known/carddav", follow_redirects=False).status_code == 404


def test_the_tiles_follow_the_switch(door):
    by = {a["app"]: a for a in door.get("/api/auth/suite").json()["items"]}
    assert by["iocalendar"]["url"] == "http://testserver/calendar" and by["iostart"]["url"] == "http://testserver"
    assert door.put("/api/suite-admin/address", json={"on": False}).json()["on"] is False
    assert door.get("/calendar/x").status_code == 404  # at once, in the start page itself
    by = {a["app"]: a for a in door.get("/api/auth/suite").json()["items"]}
    assert by["iocalendar"]["url"] == "https://calendar.example.com"
