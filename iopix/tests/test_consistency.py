"""Metadata consistency: a scan of the scratch library compares database, sidecar and file,
stores the results, reports progress while it runs and a summary when it is done."""
import time

from app import consistency


def _wait_done(timeout=60):
    end = time.time() + timeout
    while time.time() < end and consistency.progress["running"]:
        time.sleep(0.2)
    return not consistency.progress["running"]


def test_whole_library_scan_reports_and_stores(client, lib):
    r = client.post("/api/consistency/scan", content="rescan_all=1", headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200 and r.json()["queued"] > 0, r.text
    assert _wait_done(), "the scan finishes"
    d = client.get("/api/consistency?field=&offset=0&limit=60").json()
    p, s = d["progress"], d["summary"]
    assert p["error"] is None and p["failed"] == 0 and p["rescan_all"] is True and p["done"] == p["total"] > 0, p
    assert s["scanned"] == p["total"] and s["scanned_at"], s
    assert d["total"] == s["mismatched"] == len(d["items"][:60]) or d["total"] > 60


def test_a_failing_batch_is_counted_and_reported(client, monkeypatch):
    def boom(batch):
        raise RuntimeError("exiftool exploded")
    monkeypatch.setattr(consistency, "compare", boom)
    r = client.post("/api/consistency/scan", content="rescan_all=1", headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200
    assert _wait_done()
    p = client.get("/api/consistency").json()["progress"]
    assert p["failed"] == p["total"] > 0 and "exiftool exploded" in p["error"] and p["done"] == p["total"], p


def test_check_new_only_reports_nothing_to_do(client):
    client.post("/api/consistency/scan", content="rescan_all=1", headers={"content-type": "application/x-www-form-urlencoded"})
    assert _wait_done()
    client.post("/api/consistency/scan", content="rescan_all=0", headers={"content-type": "application/x-www-form-urlencoded"})
    assert _wait_done()
    p = client.get("/api/consistency").json()["progress"]
    assert p["total"] == 0 and p["rescan_all"] is False and p["started"], "nothing changed since the full check"
