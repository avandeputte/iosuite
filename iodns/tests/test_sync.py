"""The comparison and the plan (app/sync.py), without a database or a server."""
from app.providers import Record, record
from app.sync import compare, plan


def R(name, type_, value, ttl=None):
    return record(name, type_, value, ttl)


def snap(*recs, ok=True, types=("A", "AAAA", "CNAME"), covers=None):
    return {"ok": ok, "records": list(recs), "types": list(types), "covers": covers, "error": None if ok else "down"}


MASTER = [R("nas.lan", "A", "192.168.1.10"), R("cal.example.com", "A", "192.168.1.151"), R("www.example.com", "CNAME", "cal.example.com")]


def rows(out):
    return {r["name"]: r for r in out["rows"]}


def test_states_per_server_and_row():
    out = compare(MASTER, {
        1: snap(R("nas.lan", "A", "192.168.1.10"), R("cal.example.com", "A", "192.168.1.99"), R("old.lan", "A", "10.0.0.1")),
        2: snap(R("nas.lan", "A", "192.168.1.10"), R("cal.example.com", "A", "192.168.1.151"), R("www.example.com", "CNAME", "cal.example.com")),
    })
    r = rows(out)
    assert r["nas.lan"]["state"] == "ok"
    assert r["cal.example.com"]["state"] == "different"
    assert r["cal.example.com"]["servers"][1]["state"] == "different" and r["cal.example.com"]["servers"][2]["state"] == "same"
    assert r["www.example.com"]["state"] == "missing" and r["www.example.com"]["servers"][1]["state"] == "missing"
    assert r["old.lan"]["state"] == "extra" and r["old.lan"]["default"] == "skip"
    assert r["cal.example.com"]["default"] == "master"
    assert out["differences"] == {1: 3, 2: 0}


def test_two_servers_that_disagree_on_a_name_the_master_lacks_conflict():
    out = compare([], {1: snap(R("x.lan", "A", "10.0.0.1")), 2: snap(R("x.lan", "A", "10.0.0.2"))})
    assert rows(out)["x.lan"]["state"] == "different"


def test_unreachable_server_and_types_it_does_not_keep():
    out = compare([R("v6.lan", "AAAA", "fd00::1"), R("nas.lan", "A", "192.168.1.10")],
                  {1: snap(R("nas.lan", "A", "192.168.1.10"), types=("A",)), 2: snap(ok=False)})
    r = rows(out)
    assert r["v6.lan"]["state"] == "ok"  # the server keeps no AAAA: nothing to compare
    assert r["nas.lan"]["servers"][2]["state"] == "unreachable" and r["nas.lan"]["state"] == "ok"


def test_names_outside_a_servers_zones_are_not_compared():
    out = compare(MASTER, {1: snap(R("cal.example.com", "A", "192.168.1.151"), R("www.example.com", "CNAME", "cal.example.com"), covers=["example.com"])})
    r = rows(out)
    assert r["nas.lan"]["servers"][1]["state"] == "outside" and r["nas.lan"]["state"] == "ok"
    assert out["differences"] == {1: 0}


def test_plan_master_adds_deletes_and_updates_in_place():
    snaps = {1: snap(R("cal.example.com", "A", "192.168.1.99"), R("nas.lan", "A", "192.168.1.10"), R("nas.lan", "A", "192.168.1.11"))}
    p = plan(MASTER, snaps, {"cal.example.com": "master", "nas.lan": "master", "www.example.com": "master"})
    ops = [(o["op"], o["record"].name, o["record"].value, o["old"].value if o["old"] else None) for o in p["ops"][1]]
    assert ("update", "cal.example.com", "192.168.1.151", "192.168.1.99") in ops
    assert ("delete", "nas.lan", "192.168.1.11", None) in ops
    assert ("add", "www.example.com", "cal.example.com", None) in ops
    assert len(ops) == 3 and p["master"] == {}


def test_plan_take_a_servers_records_and_delete_everywhere():
    snaps = {1: snap(R("cal.example.com", "A", "192.168.1.99")), 2: snap(R("cal.example.com", "A", "192.168.1.151"), R("old.lan", "A", "10.0.0.1"))}
    p = plan(MASTER, snaps, {"cal.example.com": "server:1", "old.lan": "delete", "nas.lan": "skip"})
    assert [r.value for r in p["master"]["cal.example.com"]] == ["192.168.1.99"]
    assert "old.lan" not in p["master"]  # the master list never had it
    assert [(o["op"], o["record"].value) for o in p["ops"][2]] == [("update", "192.168.1.99"), ("delete", "10.0.0.1")]
    assert 1 not in p["ops"]  # server 1 holds it already


def test_a_cname_replacing_an_a_is_a_delete_and_an_add():
    p = plan([R("www.lan", "CNAME", "nas.lan")], {1: snap(R("www.lan", "A", "192.168.1.10"))}, {"www.lan": "master"})
    assert sorted(o["op"] for o in p["ops"][1]) == ["add", "delete"]


def test_record_normalises():
    r = record("NAS.Lan.", "a", " 192.168.1.10 ")
    assert (r.name, r.type, r.value) == ("nas.lan", "A", "192.168.1.10")
    assert record("x.lan", "AAAA", "FD00:0:0::1").value == "fd00::1"
    assert record("*.apps.lan", "CNAME", "Ingress.LAN.").value == "ingress.lan"
    for bad in [("x lan", "A", "1.2.3.4"), ("x.lan", "A", "1.2.3"), ("x.lan", "MX", "a"), ("x.lan", "AAAA", "1.2.3.4")]:
        try:
            record(*bad)
        except ValueError:
            continue
        raise AssertionError(bad)
    assert Record("a", "A", "1.1.1.1", ref="x") == Record("a", "A", "1.1.1.1", ref="y")
