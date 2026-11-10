"""Backups: a download of digiKam's database or of iopix's own data."""
import shutil
import sqlite3
import time
import zipfile
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app import access, config
from app.digikam import dbsync, dkdb
from app.data import appdb

router = APIRouter()


@router.post("/api/backup/{which}", dependencies=[access.admin])
def api_backup(which: str):
    """Make a backup and send it: digiKam's database (a consistent copy of the SQLite file, or a fresh mysqldump) or
    ioPix's own data (a mysqldump plus the content-search index). Admins only; the copy is also kept in db-backups.
    A POST, since it writes a dump of hundreds of megabytes: a link on another site cannot start one."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dkdb.BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    def snapshot(db_file, dst):
        """A consistent copy of a SQLite database that may be in use."""
        src = sqlite3.connect(f"file:{quote(str(db_file))}?mode=ro", uri=True)
        try:
            out = sqlite3.connect(str(dst))
            try:
                src.backup(out)
            finally:
                out.close()
        finally:
            src.close()

    if which == "app":  # everything the viewer keeps: its database (state and AI results) plus the content-search index
        dst = dkdb.BACKUP_DIR / f"viewer-backup-{stamp}.zip"
        tmp = dkdb.BACKUP_DIR / f".snap-{stamp}"
        tmp.mkdir(exist_ok=True)
        try:
            with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
                appdb.dump(tmp / "iopix.sql")  # mysqldump of ioPix's own database
                z.write(tmp / "iopix.sql", "iopix.sql")
                for f in sorted(config.DATA_DIR.glob("embeddings*.npz")) + sorted(config.DATA_DIR.glob("embeddings*.npz.complete")):
                    z.write(f, f.name)
                z.writestr("README.txt", "iopix backup. Restore by stopping iopix, loading iopix.sql into its MariaDB database "
                           "(mariadb <database> < iopix.sql: albums, favorites, settings, pending edits, and the analysis results: sharpness, "
                           "text, objects, captions, consistency report) and copying embeddings*.npz (the content-search index) into its data folder. "
                           "digiKam's own database is a separate download.\n")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        dkdb.prune("viewer-backup-*.zip")
        return FileResponse(dst, media_type="application/zip", filename=f"iopix-backup-{stamp}.zip", content_disposition_type="attachment")
    if which != "digikam":
        raise HTTPException(404, "backup is 'digikam' or 'app'")
    if dkdb.no_digikam():
        raise HTTPException(404, "There is no digiKam database; the library is in the app backup")
    if dkdb.is_mysql():
        try:
            dst = dkdb.backup(force=True)
        except dbsync.SyncError as e:
            raise HTTPException(409, str(e))
        if dst is None:
            raise HTTPException(400, "Database backups are switched off (DIGIKAM_DB_BACKUP=skip)")
        return FileResponse(dst, media_type="application/sql", filename=dst.name, content_disposition_type="attachment")
    dst = dkdb.BACKUP_DIR / f"digikam4-download-{stamp}.db"
    snapshot(dkdb.sqlite_path(), dst)  # a consistent copy even while digiKam writes
    dkdb.prune("digikam4-download-*.db")
    return FileResponse(dst, media_type="application/vnd.sqlite3", filename=f"digikam4-{stamp}.db", content_disposition_type="attachment")
