"""Round four of the 14 November 2026 review: DB_WRITE=0 is kept in the write layer itself, so a route or MCP tool
that forgets its own check still writes nothing to digiKam's database."""
import pytest

from app import config
from app.digikam import dbsync, dkdb


def test_db_write_off_refuses_every_write(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_WRITE", False)
    with pytest.raises(dbsync.SyncError, match="DB_WRITE=0"):
        with dbsync.write_transaction(tmp_path / "digikam4.db"):
            pass
    with pytest.raises(dbsync.SyncError, match="DB_WRITE=0"):
        dbsync.preflight(tmp_path / "digikam4.db", require_digikam_closed=False)
    with pytest.raises(dbsync.SyncError, match="DB_WRITE=0"):
        dbsync.apply_pending(tmp_path / "digikam4.db", {"1": {"rating": 3}}, require_digikam_closed=False)
    assert dkdb.stamp_files([(1, str(tmp_path / "x.jpg"))]) == 0
