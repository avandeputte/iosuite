"""Sign-in by a reverse proxy: the user header is believed only from the proxy (or a verified Cloudflare Access
token), matched to an account by email or name, optionally creating one."""
import time

import pytest

from app import users
from iosuite_shared import db, proxyauth
from app.auth import auth as auth_shared


def opt(name: str, value: str = ""):
    """A proxy sign-in setting: suite-wide, in the Shared ioSuite database (the environment is not read)."""
    db.set_setting(name.lower(), value, "")


@pytest.fixture(autouse=True)
def no_proxy_settings():
    for k in proxyauth.KEYS:
        opt(k)
    yield
    for k in proxyauth.KEYS:
        opt(k)


@pytest.fixture
def account(fresh):
    u = users.create("proxy-probe", "longpassword1", "editor", email="probe@example.com")
    proxyauth._cache.clear()
    yield u
    proxyauth._cache.clear()


def test_off_by_default(monkeypatch, account):
    opt("AUTH_PROXY")
    assert auth_shared.proxy.identity({"Remote-User": "proxy-probe"}, "127.0.0.1") is None


@pytest.mark.parametrize("preset", ["haproxy", "nginx", "caddy", "traefik", "header"])
def test_header_from_the_proxy_only(monkeypatch, account, preset):
    opt("AUTH_PROXY", preset)
    opt("AUTH_PROXY_TRUSTED", "127.0.0.1,::1")  # this machine: the proxy (a proxy mode with no address listed signs nobody in)
    assert auth_shared.proxy.identity({"Remote-User": "proxy-probe"}, "127.0.0.1") == "proxy-probe"
    assert auth_shared.proxy.identity({"X-Auth-Request-Email": "probe@example.com"}, "::ffff:127.0.0.1") == "probe@example.com"
    assert auth_shared.proxy.identity({"Remote-User": "proxy-probe"}, "192.168.1.50") is None, "not from the proxy: ignored"
    opt("AUTH_PROXY_TRUSTED", "192.168.1.0/24")
    assert auth_shared.proxy.identity({"Remote-User": "proxy-probe"}, "192.168.1.50") == "proxy-probe"
    opt("AUTH_PROXY_HEADER", "X-Custom-User")
    assert auth_shared.proxy.identity({"Remote-User": "x", "X-Custom-User": "proxy-probe"}, "192.168.1.50") == "proxy-probe"
    assert auth_shared.proxy.user_for("PROBE@example.com")["id"] == account["id"] and auth_shared.proxy.user_for("Proxy-Probe")["id"] == account["id"]


def test_unknown_people_are_created_only_when_allowed(monkeypatch, account):
    opt("AUTH_PROXY_CREATE")
    assert auth_shared.proxy.user_for("new-person@example.com") is None
    opt("AUTH_PROXY_CREATE", "editor")
    u = auth_shared.proxy.user_for("new-person@example.com")
    assert u and u["role"] == "editor" and u["email"] == "new-person@example.com"


def test_cloudflare_access_token_is_verified(monkeypatch, account):
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    key, other = (rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2))
    opt("AUTH_PROXY", "cloudflare")
    opt("CF_ACCESS_TEAM", "myteam.cloudflareaccess.com")
    opt("CF_ACCESS_AUD", "aud-tag")

    class Signing:  # the team's published keys, as PyJWKClient gives them (proxyauth._cf_key picks one by its kid)
        def __init__(self, k, kid):
            self.key, self.key_id = k, kid
    monkeypatch.setattr(jwt.PyJWKClient, "get_signing_keys", lambda self, refresh=False: [Signing(key.public_key(), "k1")])
    proxyauth._jwks.update(team=None, client=None, refreshed_at=0.0)

    def token(k=key, **over):
        claims = {"email": "probe@example.com", "aud": ["aud-tag"], "iss": "https://myteam.cloudflareaccess.com", "exp": int(time.time()) + 300} | over
        return jwt.encode(claims, k, algorithm="RS256", headers={"kid": "k1"})
    hdr = proxyauth.CF_JWT_HEADER
    # from anywhere: the token is the proof, and the email comes from it, not from a header someone could set
    assert auth_shared.proxy.identity({hdr: token(), proxyauth.CF_HEADER: "someone@else"}, "203.0.113.9") == "probe@example.com"
    assert auth_shared.proxy.identity({hdr: token(k=other)}, "127.0.0.1") is None, "signed by someone else"
    assert auth_shared.proxy.identity({hdr: token(aud=["another-app"])}, "127.0.0.1") is None
    assert auth_shared.proxy.identity({hdr: token(exp=int(time.time()) - 600)}, "127.0.0.1") is None
    assert auth_shared.proxy.identity({proxyauth.CF_HEADER: "probe@example.com"}, "127.0.0.1") is None, "no token: nobody"
    # without the team settings nobody is signed in: for Cloudflare the signed token is the only proof (a plain
    # header from the tunnel's address could be set by anything on that machine)
    opt("CF_ACCESS_TEAM")
    assert auth_shared.proxy.identity({proxyauth.CF_HEADER: "probe@example.com"}, "127.0.0.1") is None
    assert auth_shared.proxy.identity({proxyauth.CF_HEADER: "probe@example.com"}, "203.0.113.9") is None


def test_requests_through_the_proxy_are_signed_in(client, monkeypatch, account):
    opt("AUTH_PROXY", "nginx")
    monkeypatch.setattr("iosuite_shared.proxyauth.Proxy.from_trusted", lambda self, peer: True)
    me = client.get("/api/auth/me", headers={"Remote-User": "proxy-probe"}).json()
    assert me["user"]["name"] == "proxy-probe" and me["viaProxy"] and me["canWrite"]
    client.cookies.clear()  # (the session the proxy sign-in started would keep this browser signed in)
    assert client.get("/api/auth/me").json()["user"] is None, "no header: not signed in"


def test_the_real_peer_survives_the_forwarded_rewrite():
    """iosuite-shared's Forwarded middleware (uvicorn runs with proxy_headers=False) takes the visitor's address from
    X-Forwarded-For only for a connection from a listed reverse proxy, and keeps the address the connection really
    came from, which proxy sign-in and the throttles trust."""
    import asyncio
    seen = {}

    async def inner(scope, receive, send):
        seen.update(client=scope["client"][0], peer=scope.get("iothing.peer"), scheme=scope["scheme"])
    headers = [(b"x-forwarded-for", b"203.0.113.9"), (b"x-forwarded-proto", b"https")]
    mw = proxyauth.Forwarded(inner)  # this machine is always believed; other proxies are the ones listed in Settings
    asyncio.run(mw({"type": "http", "client": ("127.0.0.1", 5000), "headers": headers, "scheme": "http"}, None, None))
    assert seen == {"client": "203.0.113.9", "peer": "127.0.0.1", "scheme": "https"}, seen
    asyncio.run(mw({"type": "http", "client": ("10.9.9.9", 5000), "headers": headers, "scheme": "http"}, None, None))
    assert seen == {"client": "10.9.9.9", "peer": "10.9.9.9", "scheme": "http"}, "not from an allowed proxy: the headers are ignored"


def test_settings_from_the_app_and_the_token_seen(monkeypatch, account):
    """Proxy sign-in is set up suite-wide (the environment is not read), and the Cloudflare team and application
    of the requests are noted (unverified) so they can be set up from them."""
    import jwt
    proxyauth.save_suite({"AUTH_PROXY": "nginx", "AUTH_PROXY_TRUSTED": "10.0.0.0/8"})
    try:
        assert auth_shared.proxy.mode() == "nginx" and auth_shared.proxy.identity({"Remote-User": "proxy-probe"}, "10.1.2.3") == "proxy-probe"
        monkeypatch.setenv("AUTH_PROXY", "off")
        assert auth_shared.proxy.mode() == "nginx", "the environment is not read: the setting is the suite's"
        tok = jwt.encode({"iss": "https://myteam.cloudflareaccess.com", "aud": ["aud-x"], "email": "probe@example.com"}, "k", algorithm="HS256")
        auth_shared.proxy.note({proxyauth.CF_JWT_HEADER: tok}, "10.1.2.3")  # from the proxy's own address: anyone else's header is ignored
        proxyauth.seen.clear(); auth_shared.proxy.note({proxyauth.CF_JWT_HEADER: tok}, "203.0.113.9"); assert not proxyauth.seen, "not from the proxy: not noted"
        auth_shared.proxy.note({proxyauth.CF_JWT_HEADER: tok}, "10.1.2.3")
        assert proxyauth.seen["iss"] == "https://myteam.cloudflareaccess.com" and proxyauth.seen["aud"] == ["aud-x"]
    finally:
        proxyauth.save_suite({k: "" for k in proxyauth.KEYS})


def test_from_outside_a_password_is_required(client, monkeypatch, account):
    opt("AUTH_PROXY")
    users.create("oneclick-probe", "", "viewer")
    outside = {"Cf-Ray": "abc-EWR", "Cf-Connecting-Ip": "203.0.113.9"}
    names = lambda hd: {a["name"] for a in client.get("/api/auth/accounts", headers=hd).json()["accounts"]}
    assert {"oneclick-probe", "proxy-probe"} <= names({})
    assert names(outside) == set(), "from outside the sign-in screen asks for a name: no account is listed"
    assert client.post("/api/auth/login", json={"name": "oneclick-probe"}, headers=outside).status_code == 403
    r = client.post("/api/auth/login", json={"name": "oneclick-probe"})  # on the LAN: one click still works
    assert r.status_code == 200
    assert client.get("/api/auth/me").json().get("user", {}).get("name") == "oneclick-probe"
    assert not (client.get("/api/auth/me", headers=outside).json().get("user") or {}).get("name"), "its session does not work from outside"
    assert client.post("/api/auth/login", json={"name": "proxy-probe", "password": "longpassword1"}, headers=outside).status_code == 200
    client.post("/api/auth/logout", json={})


def test_sign_ins_are_logged(client, monkeypatch, account, caplog):
    import logging
    opt("AUTH_PROXY")
    with caplog.at_level(logging.INFO, logger="iosuite_shared.auth"):
        assert client.post("/api/auth/login", json={"name": "proxy-probe", "password": "nope"}, headers={"Cf-Connecting-Ip": "203.0.113.9"}).status_code == 401
        assert client.post("/api/auth/login", json={"name": "proxy-probe", "password": "longpassword1"}).status_code == 200
        client.post("/api/auth/logout", json={})
        opt("AUTH_PROXY", "nginx")
        monkeypatch.setattr("iosuite_shared.proxyauth.Proxy.from_trusted", lambda self, peer: True)
        proxyauth._logged.clear()
        for _ in range(3):
            client.get("/api/auth/me", headers={"Remote-User": "proxy-probe"})
            proxyauth._cache.clear()
    msgs = [r.getMessage() for r in caplog.records if r.name == "iosuite_shared.auth"]
    assert any("failed sign-in as 'proxy-probe' from 203.0.113.9 through Cloudflare" in m for m in msgs), msgs
    assert any(m.startswith("signed in: proxy-probe (editor, password)") for m in msgs)
    assert any(m.startswith("signed out: proxy-probe") for m in msgs)
    assert sum("signed in by the proxy (nginx): proxy-probe as proxy-probe" in m for m in msgs) == 1, "once, not per request"


def test_a_proxy_sign_in_carries_over_to_the_home_network(client, monkeypatch, account):
    opt("AUTH_PROXY", "nginx")
    monkeypatch.setattr("iosuite_shared.proxyauth.Proxy.from_trusted", lambda self, peer: True)
    client.cookies.clear()
    outside = {"Remote-User": "proxy-probe", "Cf-Ray": "abc-EWR"}
    me = client.get("/api/auth/me", headers=outside).json()
    assert me["viaProxy"] and me["signedInBy"] == "proxy" and me["throughCloudflare"]
    assert client.cookies.get(users.COOKIE), "a session for this browser"
    me = client.get("/api/auth/me").json()  # back home: no proxy header, the session does it
    assert me["user"]["name"] == "proxy-probe" and not me["viaProxy"] and me["signedInBy"] == "proxy" and not me["throughCloudflare"]
    r = client.post("/api/auth/logout", json={}, headers={"Cf-Ray": "x"})
    assert r.json()["cloudflareLogout"] == "/cdn-cgi/access/logout"
    assert client.post("/api/auth/logout", json={}).json()["cloudflareLogout"] is None
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": "proxy-probe", "password": "longpassword1"}).status_code == 200
    opt("AUTH_PROXY", "off")
    assert client.get("/api/auth/me").json()["signedInBy"] == "password"
    client.post("/api/auth/logout", json={})


def test_someone_with_no_account_can_be_denied(client, monkeypatch, account):
    opt("AUTH_PROXY", "nginx")
    monkeypatch.setattr("iosuite_shared.proxyauth.Proxy.from_trusted", lambda self, peer: True)
    client.cookies.clear()
    stranger = {"Remote-User": "stranger@example.com"}
    assert client.get("/api/auth/me", headers=stranger).json()["user"] is None, "default: the sign-in screen"
    opt("AUTH_PROXY_CREATE", "deny")
    proxyauth._cache.clear()
    r = client.get("/api/auth/accounts", headers=stranger)
    assert r.status_code == 403 and r.json()["noAccess"]
    assert client.post("/api/auth/login", json={"name": "proxy-probe", "password": "longpassword1"}, headers=stranger).status_code == 403
    page = client.get("/", headers=stranger)
    assert page.status_code == 403 and "No access" in page.text and "stranger@example.com" in page.text
    assert client.get("/api/auth/me", headers={"Remote-User": "proxy-probe"}).json()["user"]["name"] == "proxy-probe", "people with an account still get in"
    client.cookies.clear()
    assert client.get("/api/auth/accounts").status_code == 200, "no proxy sign-in (the home network): unaffected"
