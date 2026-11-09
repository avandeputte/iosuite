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
