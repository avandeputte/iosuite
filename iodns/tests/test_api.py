"""The API end to end against MariaDB, with in-memory DNS servers (tests/fake.py)."""
from app.providers import record
from tests import fake


def add_server(client, name, url, view="internal", **opts):
    r = client.post("/api/servers", json={"kind": "fake", "name": name, "url": url, "view": view, "secret": "pw", "options": opts})
    assert r.status_code == 200, r.text
    return r.json()


def entry(client, name, **records):
    r = client.post("/api/entries", json={"name": name, "records": {k: v for k, v in records.items()}})
    assert r.status_code == 200, r.text
    return r.json()


def test_views_seeded_and_entries_per_view(client):
    assert [v["slug"] for v in client.get("/api/views").json()["items"]] == ["internal", "external", "tailscale"]
    e = entry(client, "Cal.Example.com", internal=[{"type": "A", "value": "192.168.1.151"}], external=[{"type": "CNAME", "value": "home.example.net"}])
    assert e["name"] == "cal.example.com"
    assert e["records"] == {"internal": [{"type": "A", "value": "192.168.1.151", "ttl": None, "source": None}],
                            "external": [{"type": "CNAME", "value": "home.example.net", "ttl": None, "source": None}]}
    r = client.post("/api/entries", json={"name": "cal.example.com", "records": {}})
    assert r.status_code == 400 and "already" in r.json()["detail"]
    r = client.post("/api/entries", json={"name": "x.lan", "records": {"internal": [{"type": "A", "value": "1.2.3.4"}, {"type": "CNAME", "value": "y.lan"}]}})
    assert r.status_code == 400
    r = client.put(f"/api/entries/{e['id']}", json={"name": "cal.example.com", "records": {"internal": [{"type": "A", "value": "192.168.1.152"}]}})
    assert r.json()["records"] == {"internal": [{"type": "A", "value": "192.168.1.152", "ttl": None, "source": None}]}  # PUT replaces every view


def test_secret_is_never_shown_and_lives_in_the_suites_keys(client):
    s = add_server(client, "AG1", "http://ag1")
    assert s["secretSet"] is True and "secret" not in s and "pw" not in str(client.get("/api/servers").json())
    keys = client.get("/api/suite-admin/keys?app=iodns").json()
    items = keys["items"] if isinstance(keys, dict) else keys
    assert any(k["name"] == f"server_{s['id']}" and k["set"] for k in items)
    assert client.post(f"/api/servers/{s['id']}/test").json()["ok"] is True
    r = client.post("/api/servers/test", json={"kind": "fake", "url": "http://ag1", "secret": "nope"})
    assert r.json() == {"ok": False, "message": "http://ag1: wrong password"}


def test_compare_resolve_and_push(client):
    a, b = add_server(client, "AG1", "http://ag1"), add_server(client, "AG2", "http://ag2")
    add_server(client, "CF", "http://cf", view="external", zone="example.com")
    entry(client, "nas.lan", internal=[{"type": "A", "value": "192.168.1.10"}])
    entry(client, "cal.example.com", internal=[{"type": "A", "value": "192.168.1.151"}], external=[{"type": "A", "value": "203.0.113.5"}])
    fake.SERVERS["http://ag1"] = [record("nas.lan", "A", "192.168.1.10"), record("cal.example.com", "A", "192.168.1.99"), record("old.lan", "A", "10.0.0.1")]
    fake.SERVERS["http://ag2"] = [record("nas.lan", "A", "192.168.1.10")]
    st = client.get("/api/sync/internal").json()
    rows = {r["name"]: r for r in st["rows"]}
    assert rows["cal.example.com"]["state"] == "different" and rows["old.lan"]["state"] == "extra" and rows["nas.lan"]["state"] == "ok"
    assert {s["name"]: s["differences"] for s in st["servers"]} == {"AG1": 2, "AG2": 1}
    # dry run changes nothing
    pre = client.post("/api/sync/internal/apply", json={"decisions": {"cal.example.com": "server:%d" % a["id"], "old.lan": "delete"}, "dryRun": True}).json()
    assert pre["master"] == {"cal.example.com": [{"name": "cal.example.com", "type": "A", "value": "192.168.1.99"}]}
    assert len(fake.SERVERS["http://ag1"]) == 3
    res = client.post("/api/sync/internal/apply", json={"decisions": {"cal.example.com": "server:%d" % a["id"], "old.lan": "delete"}}).json()
    assert all(not s["errors"] for s in res["servers"])
    assert sorted(r.key for r in fake.SERVERS["http://ag1"]) == [("cal.example.com", "A", "192.168.1.99"), ("nas.lan", "A", "192.168.1.10")]
    assert sorted(r.key for r in fake.SERVERS["http://ag2"]) == [("cal.example.com", "A", "192.168.1.99"), ("nas.lan", "A", "192.168.1.10")]
    e = client.get("/api/entries").json()["items"]
    cal = next(x for x in e if x["name"] == "cal.example.com")
    assert cal["records"]["internal"][0]["value"] == "192.168.1.99" and cal["records"]["external"][0]["value"] == "203.0.113.5"  # the other view untouched
    # the external view: only names in the zone, and push all
    client.post("/api/sync/external/push", json={})
    assert [r.key for r in fake.SERVERS["http://cf"]] == [("cal.example.com", "A", "203.0.113.5")]
    assert all(r["state"] == "ok" for r in client.get("/api/sync/external").json()["rows"])
    assert b["id"] and any(x["action"] == "push" for x in client.get("/api/history").json()["items"])


def test_unreachable_server_is_reported_not_fatal(client):
    add_server(client, "AG1", "http://ag1")
    add_server(client, "AG2", "http://down")
    fake.DOWN.add("http://down")
    entry(client, "nas.lan", internal=[{"type": "A", "value": "192.168.1.10"}])
    st = client.get("/api/sync/internal").json()
    assert {s["name"]: s["ok"] for s in st["servers"]} == {"AG1": True, "AG2": False}
    res = client.post("/api/sync/internal/push", json={}).json()
    assert [s["name"] for s in res["servers"]] == ["AG1"] and fake.SERVERS["http://ag1"][0].value == "192.168.1.10"


def test_import_modes(client):
    s = add_server(client, "AG1", "http://ag1")
    entry(client, "nas.lan", internal=[{"type": "A", "value": "192.168.1.10"}])
    entry(client, "keep.lan", internal=[{"type": "A", "value": "192.168.1.5"}], external=[{"type": "A", "value": "203.0.113.9"}])
    fake.SERVERS["http://ag1"] = [record("nas.lan", "A", "192.168.1.11"), record("new.lan", "A", "192.168.1.12")]
    assert client.post(f"/api/servers/{s['id']}/import", json={"mode": "merge"}).json()["added"] == 1
    names = {e["name"]: e for e in client.get("/api/entries").json()["items"]}
    assert names["nas.lan"]["records"]["internal"][0]["value"] == "192.168.1.10"
    assert client.post(f"/api/servers/{s['id']}/import", json={"mode": "overwrite"}).json()["changed"] == 1
    r = client.post(f"/api/servers/{s['id']}/import", json={"mode": "replace"}).json()
    assert r["removed"] == 1
    names = {e["name"]: e for e in client.get("/api/entries").json()["items"]}
    assert set(names) == {"nas.lan", "new.lan", "keep.lan"} and "internal" not in names["keep.lan"]["records"]  # its external record stays


def test_export_and_import_file(client):
    entry(client, "nas.lan", internal=[{"type": "A", "value": "192.168.1.10"}])
    data = client.get("/api/export").json()
    client.delete(f"/api/entries/{client.get('/api/entries').json()['items'][0]['id']}")
    r = client.post("/api/import/file", json={"data": data}).json()
    assert r == {"entries": 1, "removed": 0} and client.get("/api/entries").json()["items"][0]["name"] == "nas.lan"


def test_tailscale_and_public_ip_sources(client, monkeypatch):
    from app import ddns
    from app.providers import tailscale
    devices = [{"id": "1", "name": "nas", "fqdn": "nas.t.ts.net", "hostname": "nas", "ipv4": "100.64.0.1", "ipv6": None, "os": "linux", "online": True}]
    monkeypatch.setattr(tailscale.Tailscale, "devices", lambda self: devices)
    monkeypatch.setattr(ddns, "detect", lambda: {"ipv4": "203.0.113.5", "ipv6": None})
    ts = client.post("/api/servers", json={"kind": "tailscale", "name": "Tailnet", "secret": "tskey"}).json()
    assert ts["target"] is False and ts["view"] is None
    cf = add_server(client, "CF", "http://cf", view="external")
    e = entry(client, "nas.example.com", tailscale=[{"type": "A", "source": f"tailscale:{ts['id']}:nas"}], external=[{"type": "A", "source": "publicip"}])
    assert e["records"]["tailscale"][0]["value"] == "100.64.0.1" and e["records"]["external"][0]["value"] == "203.0.113.5"
    client.post("/api/sync/external/push", json={})
    assert [r.value for r in fake.SERVERS["http://cf"]] == ["203.0.113.5"]
    # the device and the public address move: the records follow, and dynamic DNS pushes at once
    devices[0]["ipv4"] = "100.64.0.9"
    monkeypatch.setattr(ddns, "detect", lambda: {"ipv4": "198.51.100.7", "ipv6": None})
    r = client.post("/api/ddns/run", json={}).json()
    assert r["changed"] is True and r["pushed"][0]["view"] == "external"
    assert [r.value for r in fake.SERVERS["http://cf"]] == ["198.51.100.7"]
    e = client.get(f"/api/entries/{e['id']}").json()
    assert e["records"]["tailscale"][0]["value"] == "100.64.0.9" and e["records"]["tailscale"][0]["source"] == f"tailscale:{ts['id']}:nas"
    r = client.post("/api/entries", json={"name": "x.lan", "records": {"external": [{"type": "A", "source": f"tailscale:{ts['id']}:printer"}]}})
    assert r.status_code == 400 and "printer" in r.json()["detail"]
    assert cf["id"]


def test_a_name_the_server_answers_itself_is_left_out(client):
    ag, uni = add_server(client, "AG1", "http://ag1"), add_server(client, "UniFi", "http://gw", exclude="*.guest.lan")
    entry(client, "beast.iothing.net", internal=[{"type": "A", "value": "192.168.1.101"}])
    entry(client, "tv.guest.lan", internal=[{"type": "A", "value": "192.168.2.5"}])
    fake.SERVERS["http://ag1"], fake.SERVERS["http://gw"] = [], []
    fake.LOCAL["http://gw"] = {"beast.iothing.net"}
    try:
        res = client.post("/api/sync/internal/push", json={}).json()
    finally:
        fake.LOCAL.clear()
    errs = {s["name"]: s["errors"] for s in res["servers"]}
    assert errs["AG1"] == [] and len(errs["UniFi"]) == 1 and "itself" in errs["UniFi"][0]
    assert [r.name for r in fake.SERVERS["http://gw"]] == []  # tv.guest.lan is left out by the setting
    assert next(x for x in client.get("/api/servers").json()["items"] if x["id"] == uni["id"])["options"]["exclude"] == "*.guest.lan, beast.iothing.net"
    rows = {r["name"]: r for r in client.get("/api/sync/internal").json()["rows"]}
    assert rows["beast.iothing.net"]["state"] == "ok" and rows["beast.iothing.net"]["servers"][str(uni["id"])]["state"] == "leftout"
    assert ag["id"]


def test_tunnel_records_stand_alone_and_reach_only_tunnel_servers(client):
    cf = add_server(client, "CF", "http://cf", view="external")
    e = entry(client, "cal.example.com", internal=[{"type": "A", "value": "192.168.1.151"}],
              external=[{"type": "TUNNEL", "value": "home|http://192.168.1.151:8620/", "source": "publicip"}])
    assert e["records"]["external"] == [{"type": "TUNNEL", "value": "home|http://192.168.1.151:8620", "ttl": None, "source": None}]
    for bad in ([{"type": "TUNNEL", "value": "home|http://a:1"}, {"type": "A", "value": "1.2.3.4"}],
                [{"type": "TUNNEL", "value": "home|http://a:1"}, {"type": "TUNNEL", "value": "lab|http://a:1"}],
                [{"type": "TUNNEL", "value": "http://a:1"}]):
        r = client.post("/api/entries", json={"name": "x.example.com", "records": {"external": bad}})
        assert r.status_code == 400, bad
    # a DNS server is not asked to hold a tunnel record
    rows = client.get("/api/sync/external").json()["rows"]
    row = [r for r in rows if r["name"] == "cal.example.com"][0]
    assert row["state"] == "ok" and row["servers"][str(cf["id"])]["state"] == "same"


def test_an_admin_tool_for_suite_admins_only(client):
    from iosuite_shared import suite, users
    client.get("/api/auth/me")                    # the middleware registers the app
    assert suite.get("iodns")["adminTool"] is True
    assert users.default_role("iodns") == "none"
    ed = client.post("/api/users", json={"name": "ed", "password": "secret123", "role": "admin"})
    assert ed.status_code == 400                  # takes no roles: suite admins only
    ed = users.create("ed", "secret123")
    users.set_role(ed["id"], "iodns", "admin")    # a role from before the rule: ignored
    client.cookies.clear()
    client.post("/api/auth/login", json={"name": "ed", "password": "secret123"})
    assert client.get("/api/entries").status_code in (401, 403)
    assert client.post("/api/entries", json={"name": "x.lan", "records": {}}).status_code in (401, 403)


def test_push_right_after_a_change_reaches_every_view_and_only_those_names(client):
    """What the web app offers once an entry is saved, renamed or deleted: those names, in every view, nothing else."""
    add_server(client, "AG1", "http://ag1")
    add_server(client, "CF", "http://cf", view="external", zone="example.com")
    fake.SERVERS["http://ag1"] = [record("other.lan", "A", "10.0.0.9")]  # an extra the push leaves alone
    fake.SERVERS["http://cf"] = []
    e = entry(client, "app.example.com", internal=[{"type": "A", "value": "192.168.1.20"}], external=[{"type": "A", "value": "203.0.113.5"}])
    pre = client.post("/api/push", json={"names": ["app.example.com"], "dryRun": True}).json()
    assert pre["dryRun"] and [v["view"] for v in pre["views"]] == ["internal", "external"]
    assert fake.SERVERS["http://cf"] == []  # a dry run changes nothing
    res = client.post("/api/push", json={"names": ["app.example.com"]}).json()
    assert all(not s["errors"] for v in res["views"] for s in v["servers"])
    assert sorted(r.key for r in fake.SERVERS["http://ag1"]) == [("app.example.com", "A", "192.168.1.20"), ("other.lan", "A", "10.0.0.9")]
    assert [r.key for r in fake.SERVERS["http://cf"]] == [("app.example.com", "A", "203.0.113.5")]
    assert client.post("/api/push", json={"names": ["app.example.com"], "dryRun": True}).json()["views"] == []  # in step now
    # renamed: the new name added, the old one removed
    client.put(f"/api/entries/{e['id']}", json={"name": "web.example.com", "records": {"external": [{"type": "A", "value": "203.0.113.5"}]}})
    client.post("/api/push", json={"names": ["web.example.com", "app.example.com"]})
    assert [r.key for r in fake.SERVERS["http://cf"]] == [("web.example.com", "A", "203.0.113.5")]
    assert [r.name for r in fake.SERVERS["http://ag1"]] == ["other.lan"]  # no internal record any more: gone from AG1
    # deleted: gone from the servers too
    client.delete(f"/api/entries/{e['id']}")
    client.post("/api/push", json={"names": ["web.example.com"]})
    assert fake.SERVERS["http://cf"] == [] and [r.name for r in fake.SERVERS["http://ag1"]] == ["other.lan"]
    # after an import: every difference, no extras removed
    entry(client, "a.lan", internal=[{"type": "A", "value": "10.0.0.1"}])
    client.post("/api/push", json={"names": None})
    assert sorted(r.name for r in fake.SERVERS["http://ag1"]) == ["a.lan", "other.lan"]
    assert client.post("/api/push", json={"names": "x"}).status_code == 400


def test_a_dynamic_dns_run_does_not_wait_for_itself(client, monkeypatch):
    """A record on the public IPv6 address while none is known (an import on a new server): placing the records
    looked for the address again, from inside the run that holds the lock."""
    import threading
    from app import db, ddns
    monkeypatch.setattr(ddns, "detect", lambda: {"ipv4": "203.0.113.5", "ipv6": "2001:db8::5"})
    add_server(client, "CF", "http://cf", view="external")
    entry(client, "nas.example.com", external=[{"type": "A", "source": "publicip"}, {"type": "AAAA", "source": "publicip6"}])
    db.set_setting("public_ipv6", None)
    monkeypatch.setattr(ddns, "detect", lambda: {"ipv4": "198.51.100.7", "ipv6": None})
    got = {}
    t = threading.Thread(target=lambda: got.update(ddns.run()), daemon=True)
    t.start()
    t.join(20)
    assert not t.is_alive(), "the run is waiting for its own lock"
    assert got["changed"] is True and got["ipv4"] == "198.51.100.7"
    assert not ddns.running()
