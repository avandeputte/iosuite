"""One app of the suite reading from another, with nothing to set up: ioCalendar's and ioPix's birthdays from
ioContact, ioContact's faces from ioPix.

    from iosuite_shared import links
    if links.available("iocontact"):                       # it is in the suite's list of apps, with an address
        r = links.get("iocalendar", "iocontact", "/api/contacts?q=ann")   # a urllib response; links.json(...) for JSON
    links.url("iocontact")                                  # its address, for links people click

The other app is found in the suite's list (ios_apps). The server calls it on localhost when it runs on the same
machine (its recorded internal address is one of this machine's), then at its address inside the network (the
internal URL it records at every start) when it has one, and at the address its configuration names (PUBLIC_URL)
otherwise, or when the internal one does not answer. These calls carry an app password and the Cloudflare Access
service token, so they only go to addresses the other app's own configuration gave, never to the address it was
merely reached at (a request's Host header); an app with neither (in a container without INTERNAL_URL or PUBLIC_URL)
cannot be read from. url() is the public one, for links people click. The reader signs in as its own service account (users.service_account:
<app>-app, on no sign-in screen) with an app password of the other app that may only read (scope 'read'),
and a viewer role there. Both are made the first time they are needed; the password is kept in the keys and tokens
store (iosuite_shared.credentials) under the reader, and made again when the other app stops taking it (revoked from
Settings › Security, say). When the other app sits behind Cloudflare Access, the suite-wide Cloudflare Access service
token (keys `cf_access_client_id` and `cf_access_client_secret` of the whole suite, Settings › Global settings › Keys and tokens)
goes with every request.

The other way to ask: on a person's behalf, as_viewer(). A page that shows something of another app (the start page's
tiles, the calendar's tasks, a recipe's shopping list, the linked items, what a person keeps in each app) asks with
that person's own sign-in instead of an app password, so the other app answers with what they may see there:

    tasks = links.as_viewer(request, "iotask", "/api/tasks", {"status": "open"}, user_agent="ioCalendar")
    body, ctype = links.as_viewer(request, "iopix", "/thumb/5", raw=True)

Both ways send through call(): a redirect to another host is never followed, since the sign-in would travel with it.
"""
import base64
import ipaddress
import json as _json
import logging
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from iosuite_shared import apppasswords, credentials, db, sessions, suite, users

log = logging.getLogger("iosuite_shared.links")
_lock = threading.Lock()
SUITE_KEYS = [
    {"name": "cf_access_client_id", "label": "Cloudflare Access service token: client id",
     "hint": "for the apps reading from each other when they sit behind Cloudflare Access"},
    {"name": "cf_access_client_secret", "label": "Cloudflare Access service token: client secret",
     "hint": "goes with the client id"},
    # the edge check of app passwords (iosuite_shared.edge, cloudflare/edge-auth/)
    {"name": "cf_kv_account_id", "label": "Edge check: Cloudflare account id", "env": "CF_KV_ACCOUNT_ID",
     "hint": "the account the edge-auth Worker and its KV namespace are in"},
    {"name": "cf_kv_namespace_id", "label": "Edge check: KV namespace id", "env": "CF_KV_NAMESPACE_ID",
     "hint": "the APP_PASSWORDS namespace the Worker is bound to"},
    {"name": "cf_kv_api_token", "label": "Edge check: Cloudflare API token", "env": "CF_KV_API_TOKEN",
     "hint": "Account › Workers KV Storage › Edit, nothing else"},
]
_declared = False


def _key(provider: str) -> str:
    return f"link_{provider}"


def url(provider: str) -> str | None:
    """The other app's public address, or None while it is not in the suite's list."""
    try:
        u = suite.url_of(provider)
    except Exception:  # noqa: BLE001  the shared database is away
        return None
    return u.rstrip("/") if u else None


def available(provider: str) -> bool:
    """Whether the other app is in the suite's list with an address the server may call it at."""
    return bool(addresses(provider))


def _this_machine(host: str) -> bool:
    """Whether the address is one of this machine's own (it can be bound to here)."""
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False  # a name: not guessed at
    if ip.is_loopback:
        return True
    try:
        with socket.socket(socket.AF_INET6 if ip.version == 6 else socket.AF_INET, socket.SOCK_DGRAM) as sk:
            sk.bind((str(ip), 0))
        return True
    except OSError:
        return False


def _local(internal: str | None) -> str | None:
    """The other app on localhost, when its internal address is on this machine: same scheme and port."""
    if not internal:
        return None
    u = urllib.parse.urlsplit(internal)
    if not u.hostname or not u.port or not _this_machine(u.hostname):
        return None
    return f"{u.scheme}://{'[::1]' if ':' in u.hostname else '127.0.0.1'}:{u.port}"


def addresses(provider: str) -> list:
    """Where the server calls the other app, in order: localhost (on the same machine), its internal address (when
    recorded), then the public one its configuration names (PUBLIC_URL)."""
    try:
        r = suite.get(provider)
    except Exception:  # noqa: BLE001  the shared database is away
        return []
    internal = (r or {}).get("internalUrl")
    out = []
    for u in (_local(internal), internal, (r or {}).get("configuredUrl")):
        u = (u or "").rstrip("/")
        if u and u not in out and urllib.parse.urlsplit(u).scheme in ("http", "https"):
            out.append(u)
    return out


class _SameHost(urllib.request.HTTPRedirectHandler):
    """A redirect is followed on the host that was asked (http to https, a missing slash) and nowhere else: urllib
    would send every header along, the Cookie, the Authorization and the Cloudflare Access secret among them, and the
    sign-in page a proxy in front of the app redirects to is not the app. A redirect to another host is the answer
    itself: an HTTPError with its 3xx."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        asked, to = urllib.parse.urlsplit(req.full_url).hostname, urllib.parse.urlsplit(newurl).hostname
        if not to or (asked or "").lower() != to.lower():
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_SameHost)


def call(req, timeout: float):
    """Send a request to another app of the suite (a urllib response): every such request goes out here."""
    return _opener.open(req, timeout=timeout)


def _declare_suite_keys():
    global _declared
    if not _declared:
        credentials.declare("", SUITE_KEYS)
        _declared = True


def account(reader: str) -> dict:
    return users.service_account(reader)


def password(reader: str, provider: str, fresh: bool = False) -> tuple[str, str]:
    """(user name, app password) the reader signs in to the provider with; made on first use (or with fresh, again:
    the old one is revoked)."""
    with _lock:
        svc = account(reader)
        pw = "" if fresh else credentials.get(reader, _key(provider))
        if pw:
            return svc["name"], pw
        for r in db.q("SELECT id FROM ios_app_passwords WHERE user_id = %s AND app = %s", (svc["id"], provider)):
            apppasswords.delete(svc["id"], r["id"])
        if not db.one("SELECT 1 AS x FROM ios_user_roles WHERE user_id = %s AND app = %s", (svc["id"], provider)):
            users.set_role(svc["id"], provider, "viewer")  # a role a suite admin gave it later (none, say) is kept
        pw = apppasswords.create(svc["id"], provider, f"{reader} reads {provider} (automatic)", apppasswords.READ)
        credentials.put(reader, _key(provider), pw, by="automatic")
        log.info("%s: made an app password to read %s as %s", reader, provider, svc["name"])
        return svc["name"], pw


def headers(reader: str, provider: str, fresh: bool = False, sign_in: bool = True) -> dict:
    """The headers that sign the reader in at the provider (HTTP Basic, and Cloudflare Access when the suite has a
    service token). sign_in False: Cloudflare Access only (an address that carries its own token, such as a feed)."""
    h = {}
    if sign_in:
        name, pw = password(reader, provider, fresh)
        h["Authorization"] = "Basic " + base64.b64encode(f"{name}:{pw}".encode()).decode()
    _declare_suite_keys()
    cid, sec = credentials.get("", "cf_access_client_id"), credentials.get("", "cf_access_client_secret")
    if cid and sec:
        h.update({"CF-Access-Client-Id": cid, "CF-Access-Client-Secret": sec})
    return h


def get(reader: str, provider: str, path: str, timeout: float = 15, accept: str = "application/json", user_agent: str = None,
        sign_in: bool = True):
    """GET path at the provider as the reader (a urllib response). RuntimeError when the provider is not in the suite;
    urllib's HTTPError and URLError otherwise. A 401 makes the app password again once (it was revoked). For an
    address that carries its own token (a feed), sign_in=False sends no app password."""
    bases = addresses(provider)
    if not bases:
        raise RuntimeError(f"{provider} is not in the suite's list of apps")
    fresh = False
    for i, base in enumerate(bases):
        last = i == len(bases) - 1
        for attempt in (0, 1):
            h = {"Accept": accept, "User-Agent": user_agent or reader, **headers(reader, provider, fresh=fresh, sign_in=sign_in)}
            fresh = False
            try:
                return call(urllib.request.Request(base + path, headers=h), timeout)  # noqa: S310  http(s), checked in addresses()
            except urllib.error.HTTPError as e:
                if e.code != 401 or attempt or not sign_in:
                    raise
                log.info("%s: %s did not take its app password; making a new one", reader, provider)
                fresh = True
            except (urllib.error.URLError, OSError) as e:
                if last:
                    raise
                log.info("%s: %s does not answer at %s (%s); trying %s", reader, provider, base, e, bases[i + 1])
                break


def json(reader: str, provider: str, path: str, timeout: float = 15):
    with get(reader, provider, path, timeout) as r:
        return _json.loads(r.read())


# ------------------------------------------------------------------ asking another app as the viewer

BREAK_S = 30          # seconds an app that answered at none of its addresses is left alone
_resting: dict = {}   # app -> until when it is left alone (time.monotonic)
_answered: dict = {}  # app -> the address that answered last: asked first


class Unreachable(urllib.error.URLError):
    """The app answered at none of its addresses (why: what the last one raised; at: the first one asked), or has none
    (why and at None)."""

    def __init__(self, app: str, why: Exception = None, at: str = None):
        self.app, self.why, self.at = app, why, at
        super().__init__(f"{app} does not answer ({type(why).__name__})" if why else f"{app} has no address to ask it at")


def viewer_headers(request, user_agent: str = "ioSuite", accept: str = "application/json") -> dict:
    """The headers of a request made on a person's behalf: their own sign-in, passed on as it came (the suite's session
    cookie, else the Authorization header they sent), and the suite's Cloudflare Access service token when one is set.
    No app password. request None: nobody's sign-in."""
    h = {"User-Agent": user_agent, "Accept": accept, "Accept-Encoding": "identity"}
    if request is not None:
        tok = request.cookies.get(sessions.COOKIE)
        if tok:
            h["Cookie"] = f"{sessions.COOKIE}={tok}"
        elif request.headers.get("authorization"):
            h["Authorization"] = request.headers["authorization"]
    try:
        h.update(headers("", "", sign_in=False))
    except Exception:  # noqa: BLE001  the shared database is away: without the token
        pass
    return h


def resting(app: str) -> float:
    """The seconds the app is still left alone after it did not answer (0: it is asked)."""
    return max(0.0, _resting.get(app, 0.0) - time.monotonic())


def ask_again(app: str = None) -> None:
    """The app (or every app) is asked again at once, from its first address on (an admin changed the addresses; the tests)."""
    for d in (_resting, _answered):
        if app is None:
            d.clear()
        else:
            d.pop(app, None)


def as_viewer(request, app: str, path: str, params: dict = None, body: dict = None, method: str = None, raw: bool = False,
              timeout: float = 5, user_agent: str = "ioSuite", accept: str = None, patient: bool = False, public: bool = False,
              limit: int = 64 << 20):
    """Ask the app on the viewer's behalf (viewer_headers): GET path, with params as its query; with body, POST that
    JSON; method for another one. The answer's JSON, or with raw (the body, its content type).

    The app's addresses are asked in turn (addresses(); public: the address it is known by when it recorded no other),
    the one that answered last first. An answer that is not a 2xx is urllib's HTTPError, as the app gave it (so is a
    redirect to another host: call()). Unreachable when it answered nowhere; it is then left alone for BREAK_S seconds:
    resting() says so, for a caller that would rather not wait for it again. patient: this request does not count
    (a picture that took too long says nothing about the app)."""
    try:
        bases = addresses(app)
    except Exception:  # noqa: BLE001  the shared database is away
        bases = []
    if not bases and public and url(app):
        bases = [url(app)]
    if not bases:
        raise Unreachable(app)
    last = _answered.get(app)
    if last in bases:
        bases = [last] + [b for b in bases if b != last]
    h = viewer_headers(request, user_agent, accept or ("*/*" if raw else "application/json"))
    data = None
    if body is not None:
        data, h["Content-Type"] = _json.dumps(body).encode(), "application/json"
    query = "?" + urllib.parse.urlencode(params) if params else ""
    why = None
    for base in bases:
        req = urllib.request.Request(base + path + query, data=data, headers=h, method=method or ("POST" if body is not None else "GET"))
        try:
            with call(req, timeout) as r:  # noqa: S310  http(s), checked in addresses()
                got = r.read(limit)
                out = (got, r.headers.get("Content-Type") or "application/octet-stream") if raw else _json.loads(got or b"null")
        except urllib.error.HTTPError:
            _answered[app] = base
            _resting.pop(app, None)
            raise  # it answered
        except (urllib.error.URLError, OSError, ValueError) as e:  # ValueError: not JSON, so not the app
            why = e
            continue
        _answered[app] = base
        _resting.pop(app, None)
        return out
    if not patient:
        _resting[app] = time.monotonic() + BREAK_S
    raise Unreachable(app, why, bases[0])


def forget(reader: str, provider: str = None) -> None:
    """Revoke the reader's app passwords (at one provider, or everywhere) and drop the stored copies."""
    svc = db.one("SELECT id FROM ios_users WHERE service = %s", (reader,))
    if not svc:
        return
    for r in db.q("SELECT id, app FROM ios_app_passwords WHERE user_id = %s" + (" AND app = %s" if provider else ""),
                  (svc["id"], provider) if provider else (svc["id"],)):
        apppasswords.delete(svc["id"], r["id"])
        credentials.put(reader, _key(r["app"]), "")
