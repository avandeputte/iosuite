"""The API against the test MariaDB: servers, destinations and jobs, a backup run end to end with retention, the
backup's contents and checksums, a restore under another name, and who may do what."""
import tempfile

import pymysql
import pytest

from tests import conftest


def sql(statements, database=None):
    s = conftest.SERVER
    con = pymysql.connect(host=s["host"], port=s["port"], user=s["user"], password=s["password"], database=database, autocommit=True)
    try:
        with con.cursor() as cur:
            out = None
            for st in statements:
                cur.execute(st)
                out = cur.fetchall()
            return out
    finally:
        con.close()


@pytest.fixture()
def source():
    sql(["DROP DATABASE IF EXISTS bkt_shop", "DROP DATABASE IF EXISTS bkt_shop_copy", "CREATE DATABASE bkt_shop",
         "CREATE TABLE bkt_shop.orders (id INT PRIMARY KEY, what VARCHAR(40)) ENGINE=InnoDB",
         "INSERT INTO bkt_shop.orders VALUES (1, 'tea'), (2, 'cake')",
         "CREATE VIEW bkt_shop.v_orders AS SELECT what FROM bkt_shop.orders"])
    yield "bkt_shop"
    sql(["DROP DATABASE IF EXISTS bkt_shop", "DROP DATABASE IF EXISTS bkt_shop_copy"])


def setup_all(client, keep=2):
    s = conftest.SERVER
    srv = client.post("/api/servers", json={"name": "test db", "host": s["host"], "port": s["port"], "user": s["user"], "password": s["password"]})
    assert srv.status_code == 200, srv.text
    assert srv.json()["passwordSet"] and "password" not in srv.json()
    folder = tempfile.mkdtemp(prefix="iobackup-dest-")
    dst = client.post("/api/destinations", json={"name": "here", "kind": "local", "path": folder})
    assert dst.status_code == 200, dst.text
    job = client.post("/api/jobs", json={"name": "Nightly shop", "serverId": srv.json()["id"], "destinationId": dst.json()["id"],
                                         "databases": ["bkt_shop"], "includeUsers": True, "keep": keep,
                                         "schedule": {"mode": "daily", "time": "02:30"}})
    assert job.status_code == 200, job.text
    assert job.json()["cron"] == "30 2 * * *"
    return srv.json(), dst.json(), job.json()


def run_now(client, job_id):
    from app import tasks
    r = client.post(f"/api/jobs/{job_id}/run")
    assert r.status_code == 200, r.text
    tasks.execute(r.json()["runId"])
    run = client.get(f"/api/runs/{r.json()['runId']}").json()
    assert run["status"] == "ok", "\n".join(run["log"])
    return run


def test_backup_retention_verify_and_restore(client, source):
    from app import tasks
    srv, dst, job = setup_all(client, keep=2)
    names = []
    for i in range(3):
        run = run_now(client, job["id"])
        names.append(run["result"]["file"])
        if i < 2:  # backups are named by the second: two in the same second would be one file
            import time
            time.sleep(1.1)
    assert run["result"]["databases"] == ["bkt_shop"] and len(run["result"]["pruned"]) == 1
    listed = client.get(f"/api/destinations/{dst['id']}/backups").json()["items"]
    assert [b["name"] for b in listed] == names[:0:-1] and listed[0]["label"] == "Nightly_shop"

    ov = client.get("/api/overview").json()
    j = ov["jobs"][0]
    assert j["lastRun"]["status"] == "ok" and j["nextRun"] and not j["pending"]

    name = listed[0]["name"]
    c = client.get(f"/api/destinations/{dst['id']}/backups/{name}").json()
    db = c["databases"][0]
    assert db["name"] == "bkt_shop" and db["tables"] == ["orders"] and db["views"] == ["v_orders"]
    v = client.post(f"/api/destinations/{dst['id']}/backups/{name}/verify").json()
    assert v["files"] > 0 and v["problems"] == []

    plan = {"databases": [{"name": "bkt_shop", "target": "bkt_shop_copy", "objects": None}], "users": [], "roles": []}
    pv = client.post(f"/api/destinations/{dst['id']}/backups/{name}/preview", json={"serverId": srv["id"], "plan": plan})
    assert pv.status_code == 200, pv.text
    assert any("bkt_shop_copy" in line for line in pv.json()["lines"])
    r = client.post(f"/api/destinations/{dst['id']}/backups/{name}/restore", json={"serverId": srv["id"], "plan": plan})
    assert r.status_code == 200, r.text
    tasks.execute(r.json()["runId"])
    run = client.get(f"/api/runs/{r.json()['runId']}").json()
    assert run["status"] == "ok", "\n".join(run["log"])
    assert sql(["SELECT what FROM bkt_shop_copy.v_orders ORDER BY what"]) == (("cake",), ("tea",))

    hist = client.get("/api/runs").json()["items"]
    assert [x["kind"] for x in hist[:2]] == ["restore", "backup"] and hist[0]["user"] == "alex"

    assert client.delete(f"/api/destinations/{dst['id']}/backups/{name}").status_code == 200
    assert len(client.get(f"/api/destinations/{dst['id']}/backups").json()["items"]) == 1


def test_a_failed_backup_says_why(client, source, monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import ec
    from iosuite_shared import push, users

    from app import tasks
    sent = []
    monkeypatch.setattr(push, "_post", lambda endpoint, body, headers: sent.append(endpoint) or 201)
    monkeypatch.setattr(push.outbound, "check", lambda url, allowed=None: "142.250.0.1")
    k = ec.generate_private_key(ec.SECP256R1())
    push.add_device(users.find("alex")["id"], {"endpoint": "https://fcm.googleapis.com/fcm/send/b",
                    "keys": {"p256dh": push.b64u(push._raw_public(k.public_key())), "auth": push.b64u(b"0123456789abcdef")}}, "iobackup")
    srv, dst, job = setup_all(client)
    assert client.put(f"/api/servers/{srv['id']}", json={**srv, "password": "wrong"}).status_code == 200
    rid = client.post(f"/api/jobs/{job['id']}/run").json()["runId"]
    tasks.execute(rid)
    run = client.get(f"/api/runs/{rid}").json()
    assert run["status"] == "failed" and any("FAILED" in line for line in run["log"])
    assert sent == ["https://fcm.googleapis.com/fcm/send/b"], "the suite admin hears of it (Failed backups)"


def test_secrets_go_to_keys_and_tokens(client):
    from iosuite_shared import credentials
    srv, dst, job = setup_all(client)
    assert credentials.get("iobackup", f"server_{srv['id']}_password") == conftest.SERVER["password"]
    # an edit without a password keeps it
    r = client.put(f"/api/servers/{srv['id']}", json={"name": "renamed", "host": srv["host"], "port": srv["port"], "user": srv["user"]})
    assert r.status_code == 200 and r.json()["passwordSet"]
    assert "password" not in str(client.get("/api/overview").json()).lower().replace("passwordset", "")
    # a server or destination in use by a job stays
    assert client.delete(f"/api/servers/{srv['id']}").status_code == 400
    assert client.delete(f"/api/destinations/{dst['id']}").status_code == 400
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 200
    assert client.delete(f"/api/servers/{srv['id']}").status_code == 200
    assert not credentials.is_set("iobackup", f"server_{srv['id']}_password")


def test_job_checks(client):
    srv, dst, job = setup_all(client)
    base = {"serverId": srv["id"], "destinationId": dst["id"], "databases": "all", "schedule": {"mode": "manual"}}
    assert client.post("/api/jobs", json={**base, "name": "Nightly_shop"}).status_code == 400  # same file names as "Nightly shop"
    assert client.post("/api/jobs", json={**base, "name": "x", "schedule": {"mode": "cron", "cron": "61 * * * *"}}).status_code == 400
    assert client.post("/api/jobs", json={**base, "name": "x", "keep": -1}).status_code == 400
    r = client.post("/api/jobs", json={**base, "name": "weekly", "schedule": {"mode": "weekly", "time": "03:00", "days": [0, 6]}})
    assert r.status_code == 200 and r.json()["cron"] == "0 3 * * 0,6"
    assert client.post("/api/destinations", json={"name": "rel", "kind": "local", "path": "backups"}).status_code == 400


def test_for_suite_admins_only(client):
    import pytest
    from iosuite_shared import users
    srv, dst, job = setup_all(client)
    with pytest.raises(ValueError):
        users.create("vera", "secret123", role="admin", app="iobackup")  # takes no roles
    vera = users.create("vera", "secret123")
    users.set_role(vera["id"], "iobackup", "admin")  # a role from before the rule: ignored
    client.cookies.clear()
    client.post("/api/auth/login", json={"name": "vera", "password": "secret123"})
    assert client.get("/api/overview").status_code in (401, 403)
    assert client.post(f"/api/jobs/{job['id']}/run").status_code in (401, 403)


def test_no_role_by_default(client):
    from iosuite_shared import users
    users.create("nora", "secret123")
    client.cookies.clear()
    r = client.post("/api/auth/login", json={"name": "nora", "password": "secret123"})
    assert r.status_code == 403 or client.get("/api/overview").status_code == 403
