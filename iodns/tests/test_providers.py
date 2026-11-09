"""Each provider against a stand-in of its server's API (httpx.MockTransport): what it reads and what it sends."""
import json
from urllib.parse import unquote

import httpx

from app.providers import adguard, cloudflare, pihole, record, tailscale, unifi


def wire(p, handler):
    p._http = httpx.Client(transport=httpx.MockTransport(handler))
    return p


def test_adguard_reads_types_and_skips_what_it_cannot_hold():
    calls = []

    def h(req):
        calls.append((req.method, req.url.path, req.content and json.loads(req.content)))
        assert req.headers["authorization"].startswith("Basic ")
        if req.url.path == "/control/rewrite/list":
            return httpx.Response(200, json=[{"domain": "nas.lan", "answer": "192.168.1.10"}, {"domain": "v6.lan", "answer": "fd00::1"},
                                             {"domain": "www.lan", "answer": "nas.lan"}, {"domain": "keep.lan", "answer": "A"},
                                             {"domain": "off.lan", "answer": "1.2.3.4", "enabled": False}])
        return httpx.Response(200, json={})
    p = wire(adguard.AdGuardHome({"url": "http://ag:3000", "options": {"username": "admin"}}, "pw"), h)
    got = [(r.name, r.type, r.value) for r in p.list()]
    assert got == [("nas.lan", "A", "192.168.1.10"), ("v6.lan", "AAAA", "fd00::1"), ("www.lan", "CNAME", "nas.lan")]
    p.replace(p.list()[0], record("nas.lan", "A", "192.168.1.20"))
    assert calls[-1] == ("PUT", "/control/rewrite/update", {"target": {"domain": "nas.lan", "answer": "192.168.1.10"}, "update": {"domain": "nas.lan", "answer": "192.168.1.20"}})


def test_pihole_session_hosts_and_cnames():
    seen = []

    def h(req):
        path = unquote(req.url.raw_path.decode())
        seen.append((req.method, path, req.headers.get("x-ftl-sid")))
        if path == "/api/auth" and req.method == "POST":
            return httpx.Response(200, json={"session": {"valid": True, "sid": "S1"}})
        if path == "/api/config/dns/hosts":
            return httpx.Response(200, json={"config": {"dns": {"hosts": ["192.168.1.10 nas.lan nas2.lan"]}}})
        if path == "/api/config/dns/cnameRecords":
            return httpx.Response(200, json={"config": {"dns": {"cnameRecords": ["www.lan,nas.lan,300"]}}})
        return httpx.Response(200, json={})
    with wire(pihole.PiHole({"url": "http://ph", "options": {}}, "pw"), h) as p:
        recs = p.list()
        assert [(r.name, r.type, r.value, r.ttl) for r in recs] == [("nas.lan", "A", "192.168.1.10", None), ("nas2.lan", "A", "192.168.1.10", None),
                                                                      ("www.lan", "CNAME", "nas.lan", 300)]
        p.delete(recs[0])
        p.add(record("x.lan", "CNAME", "nas.lan"))
    assert ("DELETE", "/api/config/dns/hosts/192.168.1.10 nas.lan nas2.lan", "S1") in seen
    assert ("PUT", "/api/config/dns/hosts/192.168.1.10 nas2.lan", "S1") in seen  # the other name on the line goes back
    assert ("PUT", "/api/config/dns/cnameRecords/x.lan,nas.lan", "S1") in seen
    assert seen[-1][:2] == ("DELETE", "/api/auth")


def test_unifi_api_key_policies():
    sent = []

    def h(req):
        assert req.headers["x-api-key"] == "KEY"
        if req.url.path.endswith("/sites"):
            return httpx.Response(200, json={"data": [{"id": "uuid-1", "internalReference": "default", "name": "Default"}]})
        if req.url.path.endswith("/dns/policies") and req.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "p1", "type": "A_RECORD", "domain": "nas.lan", "ipv4Address": "192.168.1.10", "enabled": True},
                                                      {"id": "p2", "type": "CNAME", "domain": "www.lan", "targetDomain": "nas.lan"},
                                                      {"id": "p3", "type": "FORWARD_DOMAIN", "domain": "corp", "ipAddress": "10.0.0.1"}], "totalCount": 3})
        sent.append((req.method, req.url.path, req.content and json.loads(req.content)))
        return httpx.Response(200, json={})
    with wire(unifi.UniFi({"url": "https://gw", "options": {"mode": "apikey"}}, "KEY"), h) as p:
        recs = p.list()
        assert [(r.name, r.type, r.value, r.ref) for r in recs] == [("nas.lan", "A", "192.168.1.10", "p1"), ("www.lan", "CNAME", "nas.lan", "p2")]
        p.add(record("x.lan", "AAAA", "fd00::2"))
        p.delete(recs[0])
    assert sent[0] == ("POST", "/proxy/network/integration/v1/sites/uuid-1/dns/policies",
                       {"type": "AAAA_RECORD", "enabled": True, "domain": "x.lan", "ipv6Address": "fd00::2", "ttlSeconds": 0})
    assert sent[1][:2] == ("DELETE", "/proxy/network/integration/v1/sites/uuid-1/dns/policies/p1")


def test_unifi_name_it_answers_itself():
    def h(req):
        if req.url.path.endswith("/sites"):
            return httpx.Response(200, json={"data": [{"id": "uuid-1", "internalReference": "default"}]})
        return httpx.Response(400, json={"statusCode": 400, "code": "api.dns.policy.validation.overlap-with-local-dns",
                                         "message": "DNS policy overlaps with local DNS settings"})
    with wire(unifi.UniFi({"name": "Unifi", "url": "https://gw", "options": {"mode": "apikey"}}, "KEY"), h) as p:
        try:
            p.add(record("beast.iothing.net", "A", "192.168.1.101"))
            raise AssertionError("no error")
        except unifi.AnsweredElsewhere as e:
            assert e.name == "beast.iothing.net" and "answers beast.iothing.net itself" in str(e)


def test_unifi_local_account_static_dns():
    sent = []

    def h(req):
        if req.url.path == "/api/auth/login":
            return httpx.Response(200, json={}, headers={"X-CSRF-Token": "C"})
        if req.url.path.endswith("/static-dns") and req.method == "GET":
            return httpx.Response(200, json=[{"_id": "a1", "key": "nas.lan", "value": "192.168.1.10", "record_type": "A", "enabled": True},
                                             {"_id": "a2", "key": "mx.lan", "value": "mail", "record_type": "MX"}])
        sent.append((req.method, req.url.path, req.headers.get("x-csrf-token")))
        return httpx.Response(200, json={})
    with wire(unifi.UniFi({"url": "https://gw", "options": {"mode": "login", "username": "u"}}, "pw"), h) as p:
        assert [r.name for r in p.list()] == ["nas.lan"]
        p.delete(p.list()[0])
    assert sent[0] == ("DELETE", "/proxy/network/v2/api/site/default/static-dns/a1", "C")


def test_cloudflare_zones_list_and_update_in_place():
    sent = []

    def h(req):
        assert req.headers["authorization"] == "Bearer T"
        if req.url.path == "/client/v4/zones":
            return httpx.Response(200, json={"success": True, "result": [{"id": "z1", "name": "example.com"}, {"id": "z2", "name": "other.net"}], "result_info": {"total_pages": 1}})
        if req.url.path == "/client/v4/zones/z1/dns_records" and req.method == "GET":
            return httpx.Response(200, json={"success": True, "result": [{"id": "r1", "type": "A", "name": "cal.example.com", "content": "1.2.3.4", "ttl": 1},
                                                                         {"id": "r2", "type": "MX", "name": "example.com", "content": "mx", "ttl": 1}], "result_info": {"total_pages": 1}})
        sent.append((req.method, req.url.path, json.loads(req.content) if req.content else None))
        return httpx.Response(200, json={"success": True})
    with wire(cloudflare.Cloudflare({"url": "", "options": {"zones": "example.com", "proxied": True}}, "T"), h) as p:
        assert p.covers() == ["example.com"]
        recs = p.list()
        assert [(r.name, r.type, r.value, r.ttl) for r in recs] == [("cal.example.com", "A", "1.2.3.4", None)]
        p.replace(recs[0], record("cal.example.com", "A", "5.6.7.8"))
        p.add(record("new.example.com", "CNAME", "x.cfargotunnel.com"))
    assert sent[0] == ("PATCH", "/client/v4/zones/z1/dns_records/r1", {"content": "5.6.7.8", "ttl": 1})
    assert sent[1] == ("POST", "/client/v4/zones/z1/dns_records", {"type": "CNAME", "name": "new.example.com", "content": "x.cfargotunnel.com", "ttl": 1, "proxied": True})


def test_tailscale_devices_and_split_dns():
    sent = []

    def h(req):
        if req.url.path.endswith("/devices"):
            return httpx.Response(200, json={"devices": [{"id": "1", "name": "nas.tail1234.ts.net", "hostname": "NAS", "addresses": ["100.101.1.2", "fd7a:115c::2"]}]})
        sent.append((req.method, req.url.path, json.loads(req.content) if req.content else None))
        return httpx.Response(200, json={"example.com": ["100.101.1.2"]})
    with wire(tailscale.Tailscale({"url": "", "options": {}}, "tskey"), h) as p:
        devs = p.devices()
        assert devs[0]["name"] == "nas" and devs[0]["ipv4"] == "100.101.1.2" and devs[0]["ipv6"] == "fd7a:115c::2"
        assert tailscale.Tailscale.address(devs, "NAS", "A") == "100.101.1.2"
        assert tailscale.Tailscale.address(devs, "nas.tail1234.ts.net", "AAAA") == "fd7a:115c::2"
        assert tailscale.Tailscale.address(devs, "printer", "A") is None
        p.set_split_dns("Example.com", ["100.101.1.2"])
    assert sent[0] == ("PATCH", "/api/v2/tailnet/-/dns/split-dns", {"example.com": ["100.101.1.2"]})


class FakeCloudflare:
    """Zones, DNS records and tunnels with their ingress, as Cloudflare's API keeps them."""

    def __init__(self):
        self.dns = {"r1": {"id": "r1", "type": "CNAME", "name": "old.example.com", "content": "t1.cfargotunnel.com", "ttl": 1},
                    "r2": {"id": "r2", "type": "A", "name": "nas.example.com", "content": "1.2.3.4", "ttl": 1}}
        self.ingress = {"t1": [{"hostname": "old.example.com", "service": "http://10.0.0.5:80", "originRequest": {"noTLSVerify": True}},
                               {"hostname": "old.example.com", "path": "/api", "service": "http://10.0.0.6:80"},
                               {"service": "http_status:404"}]}
        self.n = 2

    def __call__(self, req):
        path, m = req.url.path.removeprefix("/client/v4"), req.method
        body = json.loads(req.content) if req.content else None
        ok = lambda result: httpx.Response(200, json={"success": True, "result": result, "result_info": {"total_pages": 1}})
        if path == "/zones":
            return ok([{"id": "z1", "name": "example.com"}])
        if path == "/accounts":
            return ok([{"id": "acc", "name": "Alex"}])
        if path == "/accounts/acc/cfd_tunnel":
            return ok([{"id": "t1", "name": "home", "status": "healthy", "remote_config": True},
                       {"id": "t2", "name": "lab", "status": "down", "remote_config": False, "config_src": "local"}])
        if path == "/accounts/acc/cfd_tunnel/t1/configurations":
            if m == "PUT":
                self.ingress["t1"] = body["config"]["ingress"]
            return ok({"config": {"ingress": self.ingress["t1"]}})
        if path == "/zones/z1/dns_records" and m == "GET":
            name = req.url.params.get("name")
            return ok([r for r in self.dns.values() if not name or r["name"] == name])
        if path == "/zones/z1/dns_records" and m == "POST":
            self.n += 1
            self.dns[f"r{self.n}"] = {"id": f"r{self.n}", **body}
            return ok(self.dns[f"r{self.n}"])
        rid = path.rsplit("/", 1)[-1]
        if m == "PATCH":
            self.dns[rid].update(body)
            return ok(self.dns[rid])
        if m == "DELETE":
            del self.dns[rid]
            return ok({"id": rid})
        raise AssertionError(f"{m} {path}")


def test_cloudflare_tunnel_hostnames_ingress_and_cname():
    from app.providers import cftunnel
    api = FakeCloudflare()
    with wire(cftunnel.CloudflareTunnel({"url": "", "options": {}}, "T"), api) as p:
        assert [(t["name"], t["remote"]) for t in p.tunnel_list()] == [("home", True), ("lab", False)]
        assert [(r.name, r.type, r.value) for r in p.list()] == [("old.example.com", "TUNNEL", "home|http://10.0.0.5:80")]
        p.add(record("cal.example.com", "TUNNEL", "home|HTTP://192.168.1.151:8620/"))
        assert api.ingress["t1"][0] == {"hostname": "cal.example.com", "service": "http://192.168.1.151:8620"}
        assert api.ingress["t1"][-1] == {"service": "http_status:404"}
        cname = [r for r in api.dns.values() if r["name"] == "cal.example.com"]
        assert cname == [{"id": "r3", "type": "CNAME", "name": "cal.example.com", "content": "t1.cfargotunnel.com", "ttl": 1, "proxied": True}]
        # a new service: the rule changes in place and keeps its origin settings; the rule with a path stays
        p.replace(p.list()[1], record("old.example.com", "TUNNEL", "home|https://10.0.0.5:443"))
        old = [r for r in api.ingress["t1"] if r.get("hostname") == "old.example.com"]
        assert old == [{"hostname": "old.example.com", "service": "https://10.0.0.5:443", "originRequest": {"noTLSVerify": True}},
                       {"hostname": "old.example.com", "path": "/api", "service": "http://10.0.0.6:80"}]
        p.delete(record("cal.example.com", "TUNNEL", "home|http://192.168.1.151:8620"))
        assert not any(r.get("hostname") == "cal.example.com" for r in api.ingress["t1"])
        assert not any(r["name"] == "cal.example.com" for r in api.dns.values())
        try:
            p.add(record("nas.example.com", "TUNNEL", "home|http://10.0.0.9:80"))
            raise AssertionError("a name with an A record cannot go behind a tunnel")
        except cftunnel.ProviderError as e:
            assert "A 1.2.3.4" in str(e)
        try:
            p.add(record("x.example.com", "TUNNEL", "lab|http://10.0.0.9:80"))
            raise AssertionError("a locally managed tunnel is not changed")
        except cftunnel.ProviderError as e:
            assert "config file" in str(e)
    # the Cloudflare DNS entry leaves the tunnel's CNAMEs alone (unless asked)
    with wire(cloudflare.Cloudflare({"url": "", "options": {}}, "T"), api) as d:
        assert [r.name for r in d.list()] == ["nas.example.com"]
    with wire(cloudflare.Cloudflare({"url": "", "options": {"tunnels": False}}, "T"), api) as d:
        assert sorted(r.name for r in d.list()) == ["nas.example.com", "old.example.com"]


def test_tunnel_values():
    from app.providers import norm_value
    assert norm_value("TUNNEL", " home | Http://cal:8620/ ") == "home|http://cal:8620"
    assert norm_value("TUNNEL", "home|http_status:404") == "home|http_status:404"
    for bad in ("http://cal:8620", "home|", "home|ftp://x", "|http://x"):
        try:
            norm_value("TUNNEL", bad)
            raise AssertionError(bad)
        except ValueError:
            pass
