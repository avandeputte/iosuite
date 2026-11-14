"""The suite's apps: one row per installed app, which each app writes itself, so the others can find it.

Every app installs on its own (its own box, port, database), so nothing but this table knows where the others are.
An app registers when it starts (`Auth(..., version=..., public_url=...)` does it, or `suite.register()` by hand) and
the middleware notes the address it is reached at. The start page (and any app switcher) reads `suite.apps()` or
`GET /api/auth/suite` and links to each one without anybody typing an address.

Where an app is (`url` in what `apps()` answers), in this order:
  1. the address an app's configuration names (its PUBLIC_URL): `configured_url`;
  2. failing that, the address one of its admins reached it at, as their browser sees it (`seen_url`): a host under
     the suite's cookie domain over HTTPS beats a LAN name, which beats an IP address; loopback and test hosts are
     never kept. Only an admin's request counts (before the first account: one from inside the network), because the
     address is the request's Host header, which any client may set to anything.

Each app also says where it is inside the network (`internal_url`, `internalUrl` in what `apps()` answers): plain
http(s)://LAN-address:port, which works without the public domain, a reverse proxy or Cloudflare. The app's INTERNAL_URL
names it; failing that, `local_url()` makes it from the host's LAN address and the app's PORT (not inside a Docker
container, whose own address the network cannot reach: there INTERNAL_URL has to say it; and with HOST=127.0.0.1,
behind a reverse proxy on the same server, the loopback address, which only the apps on that server can use). Nothing links people to it
(`url` stays PUBLIC_URL or the address the app is reached at); only the apps' own server-to-server calls use it
(iosuite_shared.links: localhost when it is on the same machine, then it, then PUBLIC_URL; never the address the app
was merely reached at, since those calls carry credentials).

Who sees which app (`visible(user)`, and `GET /api/auth/suite`): only the apps the account has a role in (not
"none": its own role there, else that app's default role), so somebody without ioHealth does not see ioHealth. An app
that registers as an admin tool (`Auth(..., admin_tool=True)`; `adminTool` in what `apps()` answers: ioDNS, ioBackup, things
behind the scenes) is for suite admins only (`is_admin_tool`: users.role_of gives everybody else none there, whatever
role row or default role says), and a switcher shows it apart from the others.

A suite admin may forget an app that was uninstalled (`DELETE /api/auth/suite/{app}`); it comes back the next time it
starts.
"""
import ipaddress
import os
import socket
import threading
import time
from urllib.parse import urlsplit

from iosuite_shared import config, db, prefix
from iosuite_shared.errors import Invalid

# Every app's default port: different for each, so all of them can run on one host. The apps' tests check theirs.
PORTS = {"iopix": 8600, "ionote": 8610, "iocalendar": 8620, "iostart": 8630, "iocontact": 8640, "iohealth": 8650, "iodns": 8660, "iotask": 8670, "iobackup": 8680, "iorecipe": 8690}

FIELDS = ("name", "description", "version", "color", "icon")
# Where every app serves its mark (static/icons/mark.svg in its repo, the web app's files under /static/): the same in
# every app, so it is not something an app passes.
ICON = "static/icons/mark.svg"
SEEN_EVERY_S = 3600  # last_seen is refreshed at most this often per app (the address itself is written when it changes)

_lock = threading.Lock()
_seen: dict = {}  # app -> (seen_url as stored, rank, at)


def _clip(v, n: int):
    v = (str(v).strip() if v is not None else "")[:n]
    return v or None


def clean_url(url) -> str | None:
    """http(s)://host[:port][/path] without a trailing slash, or None. Raises ValueError for anything else."""
    u = (url or "").strip().rstrip("/")
    if not u:
        return None
    if not (u.startswith("http://") or u.startswith("https://")) or len(u) > 512 or any(c in u for c in " \"'<>"):
        raise Invalid(f"not an http(s) address: {u[:80]}")
    return u


def _lan_ip() -> str | None:
    """This host's address on the network it reaches others through (the interface of its default route), or None.
    A UDP socket's connect() only picks the route: nothing is sent."""
    for target in (("192.0.2.1", 9), ("2001:db8::1", 9)):  # documentation addresses: never answered, only routed
        fam = socket.AF_INET6 if ":" in target[0] else socket.AF_INET
        try:
            with socket.socket(fam, socket.SOCK_DGRAM) as s:
                s.connect(target)
                ip = ipaddress.ip_address(s.getsockname()[0])
        except (OSError, ValueError):
            continue
        if not (ip.is_loopback or ip.is_unspecified or ip.is_link_local):
            return str(ip)
    return None


def in_container() -> bool:
    """Inside a Docker / Podman container: its own address is not one the network can reach."""
    return os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv")


def local_url(app: str = None, port: int = None, host: str = None, https: bool = None) -> str | None:
    """Where the app is inside the network: INTERNAL_URL when set, else http(s)://<address>:<PORT>, the address being
    HOST when it names one (of several, the first the network reaches), else the host's LAN address. With HOST on loopback (HOST=127.0.0.1, localhost or ::1:
    everything through a reverse proxy on the same server) it is the loopback address itself: the apps on the same
    server go on calling it directly (iosuite_shared.links), and the ones elsewhere find nobody at their own
    loopback and go on to PUBLIC_URL. None when there is none to give: a container without INTERNAL_URL. https when
    the app serves TLS itself (TLS_CERT_FILE and TLS_KEY_FILE)."""
    from iosuite_shared.config import env
    named = env("INTERNAL_URL")
    if named:
        return named.rstrip("/")
    if port is None:
        try:
            port = int(env("PORT", str(PORTS.get(app, 0))))
        except ValueError:
            return None
    if not port:
        return None
    from iosuite_shared import serve
    named = [h.strip("[]") for h in serve.hosts(env("HOST") if host is None else host)]

    def kind(h):  # 0: every address, 1: one the network reaches, 2: loopback
        if h.lower() == "localhost":
            return 2
        try:
            ip = ipaddress.ip_address(h)
        except ValueError:
            return 1
        return 0 if ip.is_unspecified else 2 if ip.is_loopback else 1
    host = min(named, key=kind)  # of several (HOST=127.0.0.1,192.168.1.151), the one the other machines can use too
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:  # a name: as it is
        ip = None
    if host.lower() == "localhost" or (ip is not None and ip.is_loopback):
        if in_container():
            return None
        host = "::1" if ip is not None and ip.version == 6 else "127.0.0.1"
    elif ip is not None and ip.is_unspecified:
        if in_container():
            return None
        host = _lan_ip()
        if not host:
            return None
    if ":" in host:
        host = f"[{host}]"
    if https is None:
        https = bool(env("TLS_CERT_FILE") and env("TLS_KEY_FILE"))
    return f"{'https' if https else 'http'}://{host}:{port}"


def register(app: str, name: str = None, url: str = None, version: str = None, description: str = None,
             color: str = None, internal_url: str = None, admin_tool: bool = False) -> dict:
    """Write (or refresh) this app's row: its display name, the address its configuration names (None: none, the
    address it is reached at is used), its address inside the network (local_url()), its version, a line on what it
    is and its colour (#rrggbb), and whether it is an admin tool (seen only by its admins); the icon is ICON on the app. Called at every start; whatever the app no longer says is
    cleared."""
    if not app or len(app) > 32:
        raise Invalid("an app key of 1 to 32 characters")
    with _lock:
        _seen.pop(app, None)
        _tools["at"] = 0.0
        if admin_tool:
            _declared.add(app)
        else:
            _declared.discard(app)
    now = int(time.time())
    row = {"name": _clip(name or app, 64), "description": _clip(description, 255), "version": _clip(version, 32),
           "color": _clip(color, 16), "icon": ICON, "configured_url": clean_url(url), "internal_url": clean_url(internal_url),
           "admin_tool": 1 if admin_tool else 0}
    db.ex("""INSERT INTO ios_apps (app, name, description, version, color, icon, configured_url, internal_url, admin_tool, created_at, updated_at, last_seen_at)
             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
             ON DUPLICATE KEY UPDATE name = VALUES(name), description = VALUES(description), version = VALUES(version),
               color = VALUES(color), icon = VALUES(icon), configured_url = VALUES(configured_url),
               internal_url = VALUES(internal_url), admin_tool = VALUES(admin_tool), updated_at = VALUES(updated_at), last_seen_at = VALUES(last_seen_at)""",
          (app, row["name"], row["description"], row["version"], row["color"], row["icon"], row["configured_url"],
           row["internal_url"], row["admin_tool"], now, now, now))
    return get(app)


def _rank(origin: str) -> int:
    """How good an address is for the others to link to: -1 never (loopback, test hosts), 0 an IP address, 1 a LAN
    name, 2 a host under the cookie domain; +1 over HTTPS."""
    scheme, _, rest = origin.partition("://")
    host = rest.split("/", 1)[0].rsplit("@", 1)[-1]
    host = host[1:].split("]")[0] if host.startswith("[") else host.split(":")[0]
    host = host.lower()
    if not host or host in ("localhost", "testserver", "testclient") or host.endswith(".localhost"):
        return -1
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback or ip.is_unspecified:
            return -1
        r = 0
    except ValueError:
        d = config.COOKIE_DOMAIN
        r = 2 if d and (host == d or host.endswith("." + d)) else 1
    return r + (1 if scheme == "https" else 0)


def origin_of(request) -> str:
    """scheme://host[:port] as the browser used it (through a proxy: X-Forwarded-Proto / -Host), with the folder the
    app is served in when the suite shares one address (https://home.example.com/calendar)."""
    h = request.headers
    host = (h.get("x-forwarded-host") or h.get("host") or "").split(",")[0].strip()
    proto = (h.get("x-forwarded-proto") or "").split(",")[0].strip().lower() or request.url.scheme
    return f"{proto}://{host}{prefix.of(request)}" if host else ""


def note_seen(app: str, request, take_address: bool = True) -> None:
    """The middleware calls this on every request: keep the best address the app is reached at, and when it was last
    up. Cheap: a database write only when the address gets better or once an hour. `take_address` False only notes
    that the app is up: the address comes from the Host header, which is whatever the client sends, so the caller
    passes True for an admin's request only (Auth.note), never for a visitor's."""
    origin = origin_of(request) if take_address else ""
    if take_address and not origin:
        return
    rank, now = (_rank(origin) if origin else -1), time.time()
    with _lock:
        known = _seen.get(app)
        if known is None:
            r = db.one("SELECT seen_url FROM ios_apps WHERE app = %s", (app,))
            stored = r["seen_url"] if r else None
            known = (stored, _rank(stored) if stored else -1, 0.0)
        better = rank >= 0 and origin != known[0] and rank >= known[1]
        if not better and now - known[2] < SEEN_EVERY_S:
            return
        _seen[app] = (origin if better else known[0], rank if better else known[1], now)
    if better:
        n = db.ex("UPDATE ios_apps SET seen_url = %s, last_seen_at = %s WHERE app = %s", (origin, int(now), app))
    else:
        n = db.ex("UPDATE ios_apps SET last_seen_at = %s WHERE app = %s", (int(now), app))
    if not n:  # not registered (yet): try again on a later request
        with _lock:
            _seen.pop(app, None)


def _out(r: dict) -> dict:
    url = r["configured_url"] or r["seen_url"]
    icon = r["icon"]
    if icon and url and not icon.startswith(("http://", "https://")):
        icon = url + "/" + icon.lstrip("/")
    return {"app": r["app"], "name": r["name"], "description": r["description"], "version": r["version"],
            "color": r["color"], "icon": icon, "url": url, "configuredUrl": r["configured_url"], "seenUrl": r["seen_url"],
            "internalUrl": r.get("internal_url"), "adminTool": bool(r.get("admin_tool")), "registered": r["created_at"], "updated": r["updated_at"], "lastSeen": r["last_seen_at"]}


def apps() -> list:
    """Every registered app: {app, name, description, version, color, icon (absolute), url, configuredUrl, seenUrl,
    internalUrl, adminTool, registered, updated, lastSeen}, in the suite's one order (ioStart, the start page, first,
    then the others by name), so every app switcher lists them alike. What one account may see: visible()."""
    rows = db.q("SELECT * FROM ios_apps ORDER BY name, app")
    return [_out(r) for r in sorted(rows, key=lambda r: r["app"] != "iostart")]


def visible(user) -> list:
    """The apps this account may use, for the start page and the app switchers: those it has a role in (not "none"),
    so an admin tool only for a suite admin. Before the first account exists
    (everything is open then), every app."""
    from iosuite_shared import users
    if not users.any_users():  # before the first account, everything is open to whoever asks: every app
        return apps()
    out = []
    for a in apps():
        if users.role_of(user, a["app"]) == "none":  # an admin tool is none for everybody but the suite admins
            continue
        out.append(a)
    return out


def get(app: str) -> dict | None:
    r = db.one("SELECT * FROM ios_apps WHERE app = %s", (app,))
    return _out(r) if r else None


def url_of(app: str) -> str | None:
    r = get(app)
    return r["url"] if r else None


LOCAL_SUFFIXES = (".local", ".lan", ".home", ".internal", ".home.arpa", ".localdomain", ".localhost")
_hosts: dict = {}  # app -> (the hosts of its known addresses, at)


def known_host(app: str, host: str) -> bool:
    """Whether `host` (a Host header) is a name this app is known by: an IP address, localhost, a name of the local
    network (no dot, or .local, .lan, .home, .internal...), a host under COOKIE_DOMAIN, or the host of one of the app's
    addresses in the suite's list (PUBLIC_URL, the address an admin reached it at, INTERNAL_URL). A page on another
    site that points its own name at this server's address (DNS rebinding) arrives under a name that is none of these."""
    host = (host or "").split(",")[0].strip().lower()
    if host.startswith("["):
        host = host[1:].split("]")[0]
    elif host.count(":") == 1:
        host = host.split(":")[0]
    host = host.rstrip(".")
    if not host:
        return False
    try:
        ipaddress.ip_address(host.split("%")[0])
        return True
    except ValueError:
        pass
    if "." not in host or host == "localhost" or host.endswith(LOCAL_SUFFIXES):
        return True
    d = config.COOKIE_DOMAIN
    if d and (host == d or host.endswith("." + d)):
        return True
    hit = _hosts.get(app)
    if not hit or time.time() - hit[1] > 30:
        r = get(app) or {}
        names = {(urlsplit(u).hostname or "").lower() for u in (r.get("configuredUrl"), r.get("seenUrl"), r.get("internalUrl")) if u}
        hit = _hosts[app] = (names, time.time())
    return host in hit[0]


_tools = {"set": frozenset(), "at": 0.0}  # the admin tools in the registry, read at most every TOOLS_S
_declared: set = set()  # admin tools this process registered (its own app, before the registry has its row)
TOOLS_S = 30.0


def admin_tools() -> frozenset:
    """The apps that are admin tools (for suite admins only): the registry's, and the one this process declared."""
    now = time.time()
    if now - _tools["at"] >= TOOLS_S:
        try:
            got = frozenset(r["app"] for r in db.q("SELECT app FROM ios_apps WHERE admin_tool = 1"))
        except Exception:  # noqa: BLE001 - no database yet: what this process knows
            got = _tools["set"]
        with _lock:
            _tools.update(set=got, at=now)
    return _tools["set"] | frozenset(_declared)


def is_admin_tool(app: str) -> bool:
    return app in admin_tools()


def declare_admin_tool(app: str) -> None:
    """This process is an admin tool (Auth(admin_tool=True)): known before its row reaches the registry."""
    with _lock:
        _declared.add(app)


def forget(app: str) -> bool:
    """Remove an app (uninstalled); it registers again when it starts."""
    with _lock:
        _seen.pop(app, None)
        _tools["at"] = 0.0
    return db.ex("DELETE FROM ios_apps WHERE app = %s", (app,)) > 0


def invalidate():
    """Tests: forget what was noted in memory."""
    with _lock:
        _seen.clear()
        _declared.clear()
        _tools.update(set=frozenset(), at=0.0)
    _hosts.clear()
