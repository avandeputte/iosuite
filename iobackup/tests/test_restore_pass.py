"""The second pass over backup and restore (code review of 14 November 2026): a stored routine cannot cut the dump into
the wrong pieces, views that read another database restore, a damaged file is refused before anything is restored, the
stage folder goes whatever happens, and a run whose outcome cannot be saved never stays "running"."""
import os
import shutil
import tarfile
import tempfile

import pytest

from app import engine
from tests import conftest
from tests.test_api import sql

BODY = """CREATE PROCEDURE bkt_a.p()
BEGIN
  SELECT '
-- Current Database: `bkt_ghost`
-- Table structure for table `ghost`
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;
DELIMITER ;
' AS x;
END"""


def server():
    s = conftest.SERVER
    return {"host": s["host"], "port": s["port"], "user": s["user"], "password": s["password"]}


@pytest.fixture()
def work():
    d = tempfile.mkdtemp(prefix="iobackup-work-")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def two():
    names = ("bkt_a", "bkt_b", "bkt_b2", "bkt_a2", "bkt_ghost", "bkt_app", "bkt_core")
    sql([f"DROP DATABASE IF EXISTS {n}" for n in names])
    yield
    sql([f"DROP DATABASE IF EXISTS {n}" for n in names])


def test_a_routine_body_cannot_cut_the_dump_apart(two, work):
    sql(["CREATE DATABASE bkt_a", "CREATE TABLE bkt_a.t (id INT PRIMARY KEY)", BODY,
         "CREATE DATABASE bkt_b", "CREATE TABLE bkt_b.orders (id INT PRIMARY KEY)", "INSERT INTO bkt_b.orders VALUES (7)"])
    tar, manifest = engine.run_backup(server(), ["bkt_a", "bkt_b"], include_users=False, workdir=work, label="t")
    assert [d["name"] for d in manifest["databases"]] == ["bkt_a", "bkt_b"], "no phantom database, none swallowed by the footer"
    with engine.Archive(tar) as a:
        assert a.contents()["databases"][1]["tables"] == ["orders"]
        assert b"bkt_b" not in a.read("footer.sql")
        plan = {"databases": [{"name": "bkt_b", "target": "bkt_b2"}, {"name": "bkt_a", "target": "bkt_a2"}]}
        assert engine.run_restore(server(), a, plan) == []
    assert sql(["SELECT id FROM bkt_b2.orders"]) == ((7,),)
    body = sql(["SELECT ROUTINE_DEFINITION FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA = 'bkt_a2'"])[0][0]
    assert "bkt_ghost" in body and "TIME_ZONE" in body and "DELIMITER ;" in body, "the body came back whole"
    assert not sql(["SHOW DATABASES LIKE 'bkt_ghost'"])


def test_a_dump_that_does_not_come_apart_as_asked_is_not_kept(work, monkeypatch):
    sql(["DROP DATABASE IF EXISTS bkt_a", "CREATE DATABASE bkt_a", "CREATE TABLE bkt_a.t (id INT PRIMARY KEY)"])
    real = engine.split_dump
    monkeypatch.setattr(engine, "split_dump", lambda *a, **k: (lambda h, f, d, n: (h, f, [], n))(*real(*a, **k)))
    try:
        with pytest.raises(engine.EngineError, match="did not come apart"):
            engine.run_backup(server(), ["bkt_a"], include_users=False, workdir=work, label="t")
    finally:
        sql(["DROP DATABASE IF EXISTS bkt_a"])
    assert os.listdir(work) == [], "neither a backup nor its stage folder is left"


def test_views_that_read_another_database_restore(two, work):
    sql(["CREATE DATABASE bkt_core", "CREATE TABLE bkt_core.users (name VARCHAR(20))", "INSERT INTO bkt_core.users VALUES ('ann')",
         "CREATE DATABASE bkt_app", "CREATE VIEW bkt_app.v_users AS SELECT name FROM bkt_core.users"])
    tar, _ = engine.run_backup(server(), ["bkt_app", "bkt_core"], include_users=False, workdir=work, label="t")
    sql(["DROP DATABASE bkt_app", "DROP DATABASE bkt_core"])
    with engine.Archive(tar) as a:
        plan = {"databases": [{"name": "bkt_app"}, {"name": "bkt_core"}]}
        order = [(db["name"], [s["kind"] for s in secs]) for db, _, secs, _ in engine.restore_passes(engine.normalize_plan(a, plan))]
        assert order[-1] == ("bkt_app", ["view"]), "the final views come after every database's tables"
        assert engine.run_restore(server(), a, plan) == []
    assert sql(["SELECT name FROM bkt_app.v_users"]) == (("ann",),)


def test_a_damaged_backup_is_refused_before_anything_is_restored(two, work):
    sql(["CREATE DATABASE bkt_b", "CREATE TABLE bkt_b.orders (id INT PRIMARY KEY)", "INSERT INTO bkt_b.orders VALUES (7)"])
    tar, manifest = engine.run_backup(server(), ["bkt_b"], include_users=False, workdir=work, label="t")
    unpacked = os.path.join(work, "unpacked")
    with tarfile.open(tar) as t:
        t.extractall(unpacked, filter="data")
    with open(os.path.join(unpacked, "footer.sql"), "ab") as f:
        f.write(b"DROP DATABASE mysql;\n")
    with engine.Archive(unpacked) as a:
        assert any("footer.sql" in p for p in a.verify()[1]), "the footer is under the checksums too"
        with pytest.raises(engine.EngineError, match="damaged, nothing was restored"):
            engine.run_restore(server(), a, {"databases": [{"name": "bkt_b", "target": "bkt_b2"}]})
    assert not sql(["SHOW DATABASES LIKE 'bkt_b2'"])


def test_the_stage_folder_goes_when_a_backup_fails(work):
    with pytest.raises(engine.EngineError, match="not on the server"):
        engine.run_backup(server(), ["bkt_not_there"], include_users=False, workdir=work, label="t")
    assert os.listdir(work) == []


def test_a_run_whose_outcome_cannot_be_saved_does_not_stay_running(client, monkeypatch):
    from app import db, tasks
    rid = tasks.enqueue("backup", "Backup: x", {"job_id": 0}, job_id=None)
    tasks._update(rid, status="running")
    real_ex = db.ex

    def down(*a, **k):
        raise OSError("the database went away")
    monkeypatch.setattr(db, "ex", down)
    tasks._logger(rid)("this line cannot be saved")  # a log line is not worth failing a backup over
    tasks._finish(rid, tries=2, wait=0, status="failed", finished=tasks._now())
    assert tasks._unsaved[rid]["status"] == "failed"
    tasks.save_unsaved()  # still away: kept
    assert rid in tasks._unsaved
    monkeypatch.setattr(db, "ex", real_ex)
    tasks.save_unsaved()
    assert rid not in tasks._unsaved and tasks.run(rid)["status"] == "failed"
    assert rid not in tasks.pending_jobs() and not tasks.busy()


def test_a_local_destination_is_kept_apart_from_the_work_folder(client):
    from app import config
    for inside in (config.WORK_DIR, config.WORK_DIR / "keep", config.CACHE_DIR / "1"):
        r = client.post("/api/destinations", json={"name": "bad", "kind": "local", "path": str(inside)})
        assert r.status_code == 400 and "apart from" in r.json()["detail"], inside
