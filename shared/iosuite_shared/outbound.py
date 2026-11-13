"""Requests the server makes to an address somebody else chose (a profile's link, a bookmark): which hosts they may
reach, and a connection that goes to the address that was checked.

The name is resolved once, where the connection is made, and the connection goes to that address: a name that answers
with an allowed address for the check and another for the request gets nowhere. Every connection of an opener() is made
this way, a redirect's too, and no proxy from the environment is used.
"""
import http.client
import ipaddress
import socket
import ssl
import urllib.parse
import urllib.request

from .errors import Invalid

_TLS = ssl.create_default_context()


class NotAllowed(Invalid):
    """The host is one the server may not reach."""


def public(ip) -> bool:
    """An address on the internet: not this machine, the home network, or a multicast group."""
    return ip.is_global and not ip.is_multicast


def not_this_machine(ip) -> bool:
    """Any address but this machine's own and the link-local ones (where the cloud metadata services live): the home
    network is fine."""
    return not (ip.is_loopback or ip.is_link_local or ip.is_unspecified)


def address(host: str, port: int, allowed=public) -> str:
    """The address `host` resolves to, once every address it resolves to is an allowed one: NotAllowed otherwise,
    Invalid for a name that does not resolve."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError) as e:
        raise Invalid(f"unknown host {host}") from e
    for info in infos:
        if not allowed(ipaddress.ip_address(info[4][0].split("%")[0])):
            raise NotAllowed(f"{host} is not an address the server may reach")
    return infos[0][4][0]


def check(url: str, allowed=public) -> str:
    """The address to connect to for this http(s) URL; Invalid when it is not one, or its host is not allowed."""
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise Invalid(f"not a web address: {url[:80]}")
    return address(u.hostname, u.port or (443 if u.scheme == "https" else 80), allowed)


def opener(allowed=public, redirects: bool = True) -> urllib.request.OpenerDirector:
    """An urllib opener whose connections go to the address that was checked. redirects False: a 3xx is the answer
    (never followed); True: each hop is checked like the first."""
    class HTTP(http.client.HTTPConnection):
        def connect(self):
            self.sock = socket.create_connection((address(self.host, self.port, allowed), self.port), self.timeout)

    class HTTPS(http.client.HTTPSConnection):
        def connect(self):
            sock = socket.create_connection((address(self.host, self.port, allowed), self.port), self.timeout)
            self.sock = _TLS.wrap_socket(sock, server_hostname=self.host)

    class Pinned(urllib.request.HTTPSHandler):
        def http_open(self, req):
            return self.do_open(HTTP, req)

        def https_open(self, req):
            return self.do_open(HTTPS, req)

    class Redirects(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not redirects:
                return None
            check(newurl, allowed)  # http(s) only, and refused before anything is sent
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    o = urllib.request.OpenerDirector()
    for h in (urllib.request.UnknownHandler(), urllib.request.HTTPDefaultErrorHandler(), Redirects(), urllib.request.HTTPErrorProcessor(), Pinned()):
        o.add_handler(h)
    return o
