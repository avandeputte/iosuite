"""The files the apps keep in their databases, written out beside the dump: each app's tables made from its own SCHEMA
(read out of its db.py, so a change there that this would miss shows here), filled, backed up, and the files in the
backup compared with what went in, by name and by content. Also the names alone (no database)."""
import ast
import hashlib
import io
import os
import tarfile
import tempfile
import zipfile

import pytest

from app import blobfiles, engine
from tests import conftest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DBS = {"bkt_things": "iothings", "bkt_docs": "iodocs", "bkt_money": "iomoney", "bkt_notes": "ionote",
       "bkt_recipes": "iorecipe", "bkt_start": "iostart", "bkt_suite": "shared/iosuite_shared"}


def sql(statements, database=None):
    import pymysql
    s = conftest.SERVER
    con = pymysql.connect(host=s["host"], port=s["port"], user=s["user"], password=s["password"], database=database, autocommit=True)
    try:
        with con.cursor() as cur:
            cur.execute("SET SESSION sql_mode = ''")  # the columns the test does not fill take their type's default
            for st in statements:
                cur.execute(*st) if isinstance(st, tuple) else cur.execute(st)
    finally:
        con.close()


def schema_of(app):
    path = os.path.join(REPO, app, "db.py") if app.startswith("shared") else os.path.join(REPO, app, "app", "db.py")
    tree = ast.parse(open(path).read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "SCHEMA" for t in node.targets):
            return [s if isinstance(s, str) else s[0] for s in ast.literal_eval(node.value)]
    raise AssertionError("no SCHEMA in " + path)


def test_names():
    assert blobfiles.clean('a/b:c*?"<>|d') == "a_b_c_d"
    assert blobfiles.clean("  ..hidden. ") == "hidden"
    assert blobfiles.clean("") == "file" and blobfiles.clean("CON.txt") == "_CON.txt"
    long = blobfiles.clean("x" * 300 + ".pdf")
    assert len(long) == blobfiles.MAX_SEGMENT and long.endswith(".pdf")
    assert blobfiles.with_ext("scan", "application/pdf") == "scan.pdf"
    assert blobfiles.with_ext("scan.png", "application/pdf") == "scan.png"
    assert blobfiles.with_ext("pic", "image/jpeg") == "pic.jpg"
    n = blobfiles.Names()
    assert n.path("ioThings", [("Boiler", 1)], "a.jpg") == "files/ioThings/Boiler/a.jpg"
    assert n.path("ioThings", [("Boiler", 1)], "A.jpg") == "files/ioThings/Boiler/A (2).jpg"
    assert n.path("ioThings", [("boiler", 2)], "a.jpg") == "files/ioThings/boiler (2)/a.jpg"
    assert n.path("ioThings", [("Boiler", 1)], "b.jpg") == "files/ioThings/Boiler/b.jpg"


@pytest.fixture()
def apps():
    conftest.need_db()
    for d, app in DBS.items():
        sql(["DROP DATABASE IF EXISTS " + d, "CREATE DATABASE " + d])
        sql(schema_of(app), d)
    big = os.urandom(5000)
    sql(["INSERT INTO ios_users (id, name, display_name, created_at) VALUES (7, 'morgan', 'Morgan Calloway', 0)"], "bkt_suite")
    sql(["INSERT INTO thg_items (id, name) VALUES (1, 'Boiler'), (2, 'Boiler'), (3, 'Car/Van')",
         "INSERT INTO thg_files (id, item_id, kind, name, mime, size, sha256) VALUES "
         "(1, 1, 'photo', 'front.jpg', 'image/jpeg', 5003, ''), (2, 1, 'receipt', 'invoice', 'application/pdf', 3, ''), "
         "(3, 2, 'photo', 'front.jpg', 'image/jpeg', 2, ''), (4, 3, 'manual', 'm.pdf', 'application/pdf', 0, '')",
         ("INSERT INTO thg_file_parts (file_id, n, data) VALUES (1, 0, %s), (1, 1, 'xyz'), (2, 0, 'pdf'), (3, 0, 'hi')",
          (big,))], "bkt_things")
    sql(["INSERT INTO doc_documents (id, title, kind, fields, words, archived) VALUES (1, 'Passport Morgan', 'passport', '{}', '', 0), "
         "(2, 'Passport Morgan', 'passport', '{}', '', 1)",
         "INSERT INTO doc_files (id, doc_id, name, mime, size, sha256) VALUES (1, 1, 'front.png', 'image/png', 3, ''), "
         "(2, 2, 'old.png', 'image/png', 3, '')",
         "INSERT INTO doc_file_parts VALUES (1, 0, 'png'), (2, 0, 'old')"], "bkt_docs")
    sql(["INSERT INTO mny_accounts (id, name, kind) VALUES (1, 'Checking', 'checking')",
         "INSERT INTO mny_transactions (id, account_id, day, amount, merchant, words) VALUES (1, 1, '2026-03-04', -12.50, 'Bakery', '')",
         "INSERT INTO mny_receipts (id, transaction_id, name, mime, size) VALUES (1, 1, 'receipt.jpg', 'image/jpeg', 4)",
         "INSERT INTO mny_receipt_parts VALUES (1, 0, 'rcpt')"], "bkt_money")
    sql(["INSERT INTO nts_notes (uuid, title, body, ocr_text, created_at, updated_at, tags, user_id, deleted) VALUES "
         "('n1', '', '# Groceries\nmilk', '', 1, 1, '', 7, 0), ('n2', 'Gone', '', '', 2, 2, '', 7, 1)",
         ("INSERT INTO nts_note_images (uuid, mime, data) VALUES ('n1', 'image/png', %s), ('n2', 'image/png', 'x')", (big,)),
         "INSERT INTO nts_attachments (uuid, note_uuid, user_id, name, mime, data, text, created_at) VALUES "
         "('a1', 'n1', 7, 'list.txt', 'text/plain', 'eggs', '', 1)"], "bkt_notes")
    sql(["INSERT INTO rcp_recipes (id, title, words) VALUES (1, 'Pancakes', '')",
         "INSERT INTO rcp_photos (recipe_id, step, position, picture, thumb, width, height) VALUES "
         "(1, NULL, 0, 'p1', '', 1, 1), (1, 2, 0, 's3', '', 1, 1)"], "bkt_recipes")
    sql(["INSERT INTO prt_bookmark_nodes (id, name) VALUES (1, 'Home Assistant')",
         "INSERT INTO prt_bookmark_node_icons VALUES (1, '<svg/>', 'e')"], "bkt_start")
    yield big
    sql(["DROP DATABASE IF EXISTS " + d for d in DBS])


def test_the_files_come_out_as_files(apps, monkeypatch, tmp_path):
    big = apps
    monkeypatch.setattr(blobfiles, "CHUNK", 1000)  # several pieces per file, and per part
    s = conftest.SERVER
    server = {"host": s["host"], "port": s["port"], "user": s["user"], "password": s["password"]}
    lines = []
    tar, manifest = engine.run_backup(server, list(DBS), include_users=False, workdir=str(tmp_path), label="t", log=lines.append)
    want = {
        "files/ioThings/Boiler/front.jpg": big + b"xyz",
        "files/ioThings/Boiler/Receipt - invoice.pdf": b"pdf",
        "files/ioThings/Boiler (2)/front.jpg": b"hi",
        "files/ioThings/Car_Van/Manual - m.pdf": b"",
        "files/ioDocs/Passport Morgan/front.png": b"png",
        "files/ioDocs/Archived/Passport Morgan/old.png": b"old",
        "files/ioMoney/2026/2026-03-04 Bakery -12.50 - receipt.jpg": b"rcpt",
        "files/ioNote/Morgan Calloway/Groceries/Picture.png": big,
        "files/ioNote/Morgan Calloway/Groceries/list.txt": b"eggs",
        "files/ioRecipe/Pancakes/Photo 1.jpg": b"p1",
        "files/ioRecipe/Pancakes/Step 3.jpg": b"s3",
        "files/ioStart/Bookmark icons/Home Assistant.svg": b"<svg/>",
    }
    with tarfile.open(tar) as t:
        got = {m.name: t.extractfile(m).read() for m in t.getmembers() if m.name.startswith("files/")}
    assert got == want, "\n".join(lines)
    with engine.Connection(server) as conn:  # the big ones came in several pieces
        assert max(len(f["reads"]) for _, _, fs in blobfiles.plan(conn, list(DBS)) for f in fs) == 6  # 5000 bytes + 3 in a second part
    f = manifest["files"]
    assert f["count"] == len(want) and f["apps"]["ioNote"] == 2 and f["bytes"] == sum(map(len, want.values()))
    assert all(i["sha256"] == hashlib.sha256(want[i["file"]]).hexdigest() for i in f["items"])

    with engine.Archive(tar) as a:
        assert a.contents()["files"]["count"] == len(want)
        n, problems = a.verify()
        assert problems == [] and n >= len(want)
        z = a.write_files_zip(str(tmp_path / "f.zip"))
        out = tmp_path / "out"
        assert a.extract_files(str(out)) == len(want)
    with zipfile.ZipFile(z) as zf:
        assert {k[len("files/"):]: v for k, v in want.items()} == {i: zf.read(i) for i in zf.namelist()}
    assert (out / "ioNote" / "Morgan Calloway" / "Groceries" / "list.txt").read_bytes() == b"eggs"

    # a restore still reads the dump alone, and a backup without the files has none
    tar2, m2 = engine.run_backup(server, ["bkt_money"], include_users=False, workdir=str(tmp_path), label="u", files=False)
    assert "files" not in m2
    with tarfile.open(tar2) as t:
        assert not [m for m in t.getnames() if m.startswith("files/")]


def test_a_tampered_path_stays_in(tmp_path):
    stage = tmp_path / "s"
    stage.mkdir()
    (stage / "evil").write_bytes(b"x")
    manifest = {"format": engine.FORMAT_VERSION, "created": "x", "server_version": "x", "databases": [], "accounts": None,
                "files": {"count": 1, "bytes": 1, "apps": {}, "items": [{"file": "files/../../evil", "bytes": 1, "sha256": ""}]}}
    p = tmp_path / "b.mdbk.tar"
    with tarfile.open(p, "w") as t:
        data = __import__("json").dumps(manifest).encode()
        ti = tarfile.TarInfo("manifest.json")
        ti.size = len(data)
        t.addfile(ti, io.BytesIO(data))
        t.add(stage / "evil", arcname="files/../../evil")
    with engine.Archive(str(p)) as a:
        assert a.stored_files() == []


def test_the_job_says_whether_and_the_zip_downloads(client, apps):
    from tests.test_api import run_now
    s = conftest.SERVER
    srv = client.post("/api/servers", json={"name": "db", "host": s["host"], "port": s["port"], "user": s["user"], "password": s["password"]}).json()
    dst = client.post("/api/destinations", json={"name": "here", "kind": "local", "path": tempfile.mkdtemp(prefix="iobackup-dest-")}).json()
    base = {"name": "Money", "serverId": srv["id"], "destinationId": dst["id"], "databases": ["bkt_money"], "includeUsers": False,
            "keep": 0, "schedule": {"mode": "manual"}}
    job = client.post("/api/jobs", json=base).json()
    assert job["files"] is True
    run = run_now(client, job["id"])
    assert any("Files: 1" in line for line in client.get(f"/api/runs/{run['id']}").json()["log"])
    name = run["result"]["file"]
    c = client.get(f"/api/destinations/{dst['id']}/backups/{name}").json()
    assert c["files"] == {"count": 1, "bytes": 4, "apps": {"ioMoney": 1}}
    r = client.get(f"/api/destinations/{dst['id']}/backups/{name}/files.zip")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert "Money-" in r.headers["content-disposition"] and "-files.zip" in r.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert zf.read("ioMoney/2026/2026-03-04 Bakery -12.50 - receipt.jpg") == b"rcpt"

    job = client.put(f"/api/jobs/{job['id']}", json={**base, "files": False}).json()
    assert job["files"] is False
    import time
    time.sleep(1.1)
    run = run_now(client, job["id"])
    c = client.get(f"/api/destinations/{dst['id']}/backups/{run['result']['file']}").json()
    assert c["files"] is None
    assert client.get(f"/api/destinations/{dst['id']}/backups/{run['result']['file']}/files.zip").status_code == 400
