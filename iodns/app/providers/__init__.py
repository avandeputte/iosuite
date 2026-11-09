"""DNS providers: what ioDNS knows about each kind of DNS server, behind one small interface.

A provider lists the local records a server holds, adds one and deletes one; ioDNS works out the rest (what differs
from the master list, what to add and remove) the same way for all of them. A new kind of server is one module here
with a Provider subclass registered in KINDS:

    class Technitium(Provider):
        kind, label = "technitium", "Technitium DNS"
        types = ("A", "AAAA", "CNAME")
        fields = [...]                       # what Settings › Servers asks for (url, user, secret, options)
        def list(self) -> list[Record]: ...
        def add(self, r: Record) -> None: ...
        def delete(self, r: Record) -> None: ...   # r as list() returned it (r.ref is the server's own id, if any)

A Provider is made per use (a sync, a test) with the server's row and its secret, and closed afterwards (`with`).
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field

import httpx

DNS_TYPES = ("A", "AAAA", "CNAME")  # what a DNS server holds
TYPES = DNS_TYPES + ("TUNNEL",)     # what the master list holds: TUNNEL is a Cloudflare Tunnel public hostname
SERVICE = re.compile(r"^((https?|tcp|ssh|rdp|smb|unix|unix\+tls)://\S+|http_status:[1-5][0-9][0-9]|hello_world)$")
HOST = re.compile(r"^(\*\.)?([a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9_])?\.)*[a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9_])?$")
TIMEOUT = 10.0


def under(name: str, domains) -> bool:
    """Whether name is one of domains or under one (domains None: any name)."""
    return domains is None or any(name == d or name.endswith("." + d) for d in domains)


class ProviderError(Exception):
    """A server answered with an error, or could not be reached: shown to the person as it is."""


@dataclass
class Record:
    name: str
    type: str
    value: str
    ttl: int | None = None
    ref: str | None = field(default=None, compare=False)  # the server's own id or raw line, for delete

    @property
    def key(self) -> tuple:
        return (self.name, self.type, self.value)

    def as_dict(self) -> dict:
        d = {"name": self.name, "type": self.type, "value": self.value}
        if self.ttl:
            d["ttl"] = self.ttl
        return d


def norm_name(name: str) -> str:
    n = str(name or "").strip().lower().rstrip(".")
    if not n or len(n) > 253 or not HOST.match(n):
        raise ValueError(f"Not a host name: {name!r}")
    return n


def norm_value(type_: str, value: str) -> str:
    """The value as ioDNS compares it: an address in its canonical form, a CNAME target lower case without the dot."""
    v = str(value or "").strip()
    if type_ == "A":
        try:
            return str(ipaddress.IPv4Address(v))
        except ValueError:
            raise ValueError(f"Not an IPv4 address: {value!r}") from None
    if type_ == "AAAA":
        try:
            return str(ipaddress.IPv6Address(v))
        except ValueError:
            raise ValueError(f"Not an IPv6 address: {value!r}") from None
    if type_ == "CNAME":
        return norm_name(v)
    if type_ == "TUNNEL":
        tunnel, service = tunnel_value(v)
        return f"{tunnel}|{service}"
    raise ValueError(f"Unknown record type: {type_!r}")


def tunnel_value(value: str) -> tuple[str, str]:
    """A TUNNEL record's value, "<tunnel name>|<service>" (home|http://192.168.1.151:8620), in its two parts."""
    tunnel, sep, service = str(value or "").partition("|")
    tunnel, service = tunnel.strip(), service.strip()
    if not sep or not tunnel or len(tunnel) > 64:
        raise ValueError(f"A tunnel record is <tunnel>|<service>: {value!r}")
    scheme, colon, rest = service.partition(":")
    service = (scheme.lower() + colon + rest) if colon else service.lower()
    if "://" in service and service.count("/") == 3:
        service = service.rstrip("/")  # http://host:port/ and http://host:port are one service
    if not SERVICE.match(service):
        raise ValueError(f"Not a tunnel service (http://host:port, https://, tcp://, ssh://, http_status:404…): {service!r}")
    return tunnel, service


def record(name: str, type_: str, value: str, ttl=None, ref=None) -> Record:
    t = str(type_ or "").strip().upper()
    return Record(norm_name(name), t, norm_value(t, value), int(ttl) if ttl else None, ref)


def guess_type(answer: str) -> str:
    """AdGuard Home and Pi-hole hold an answer without its type: an address says which, anything else is a CNAME."""
    try:
        return "AAAA" if ipaddress.ip_address(answer.strip()).version == 6 else "A"
    except ValueError:
        return "CNAME"


class Provider:
    kind = ""
    label = ""
    types: tuple = DNS_TYPES
    target = True   # records are pushed to it (False: a source of addresses only, such as Tailscale)
    # what the server form asks for: {key, label, type: text|url|password|select|check, hint?, options?, default?}
    # key "secret" is kept in the Shared ioSuite database's keys and tokens, never shown back
    fields: list = []

    def __init__(self, server: dict, secret: str = ""):
        self.server = server
        self.url = str(server.get("url") or "").rstrip("/")
        self.options = server.get("options") or {}
        self.secret = secret or ""
        self._http: httpx.Client | None = None

    @property
    def http(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=TIMEOUT, verify=bool(self.options.get("verifyTls", False)), follow_redirects=False)
        return self._http

    def request(self, method: str, path: str, **kw) -> httpx.Response:
        url = path if path.startswith("http") else self.url + path
        try:
            r = self.http.request(method, url, **kw)
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.server.get('name') or self.url}: {e.__class__.__name__}: {e}") from None
        if r.status_code >= 400:
            text = r.text.strip().replace("\n", " ")[:300]
            raise ProviderError(f"{self.server.get('name') or self.url}: HTTP {r.status_code} on {method} {path}: {text}")
        return r

    def open(self) -> None:
        """Sign in, when the server needs a session."""

    def close(self) -> None:
        if self._http is not None:
            self._http.close()
            self._http = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        try:
            self.close()
        except Exception:  # signing out of a server that went away
            pass

    def test(self) -> str:
        """Reach the server and read its records: a line for the person ('AdGuard Home v0.107.62, 14 rewrites')."""
        return f"{len(self.list())} records"

    def covers(self) -> list[str] | None:
        """The domains whose names this server holds (Cloudflare: its zones); None: any name. Names outside are not
        compared with it, so a public DNS host is not asked to hold the house's .lan names."""
        return None

    def list(self) -> list[Record]:
        raise NotImplementedError

    def add(self, r: Record) -> None:
        raise NotImplementedError

    def delete(self, r: Record) -> None:
        raise NotImplementedError

    def replace(self, old: Record, new: Record) -> None:
        """One record for another (same name): delete then add unless the provider can do it in one call."""
        self.delete(old)
        self.add(new)

    @classmethod
    def describe(cls) -> dict:
        return {"kind": cls.kind, "label": cls.label, "types": list(cls.types), "fields": cls.fields, "target": cls.target}


KINDS: dict[str, type[Provider]] = {}


def register(cls: type[Provider]) -> type[Provider]:
    KINDS[cls.kind] = cls
    return cls


def get(kind: str) -> type[Provider]:
    try:
        return KINDS[kind]
    except KeyError:
        raise ValueError(f"Unknown kind of DNS server: {kind!r}") from None


# the providers register themselves when imported: one module per kind of server
import importlib  # noqa: E402

for _m in ("adguard", "pihole", "unifi", "cloudflare", "cftunnel", "tailscale"):
    importlib.import_module(f"app.providers.{_m}")
