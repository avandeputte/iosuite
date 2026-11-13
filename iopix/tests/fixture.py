"""A small, self-contained digiKam library for the tests, cut from a real one.

`build(src_db, src_root, dst)` copies the digiKam database, keeps a few
hundred photos from a handful of albums (JPEG, HEIC, PNG and a video, with
faces, tags and GPS positions among them), lets digiKam's own
`delete_image` / `delete_album` triggers cascade the rest away, and copies
the kept files (and their XMP sidecars) into `dst/photos`. The source is
only read. Set DIGIKAM_TEST_DB / DIGIKAM_TEST_ROOT to point at another
library; the defaults are the viewer's own configuration.
"""
import os
import shutil
import sqlite3
from pathlib import Path

KEEP = int(os.environ.get("DIGIKAM_TEST_KEEP", "240"))


def build(src_db: Path, src_root: Path, dst: Path) -> dict:
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "db").mkdir(exist_ok=True)
    (dst / "photos").mkdir(exist_ok=True)
    db = dst / "db" / "digikam4.db"
    shutil.copy2(src_db, db)
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys = OFF")
    rows = con.execute("""
        SELECT i.id, a.relativePath, i.name, i.category,
          (SELECT count(*) FROM ImageTagProperties p WHERE p.imageid = i.id) AS faces,
          (SELECT count(*) FROM ImageTags t WHERE t.imageid = i.id) AS tags,
          (SELECT count(*) FROM ImagePositions g WHERE g.imageid = i.id) AS gps
        FROM Images i JOIN Albums a ON a.id = i.album WHERE i.status = 1 ORDER BY i.id DESC LIMIT 2500""").fetchall()
    present = [r for r in rows if (src_root / r[1].lstrip("/") / r[2]).exists()]
    # a mix: faces and tags first, then GPS, then the rest, a few videos, from at most 8 albums
    albums = []
    for r in present:
        if r[1] not in albums and len(albums) < 8:
            albums.append(r[1])
    pool = [r for r in present if r[1] in albums]
    pool.sort(key=lambda r: (-(r[4] > 0) * 4 - (r[5] > 0) * 2 - (r[6] > 0), r[3] == 2, -r[0]))
    stills = [r for r in pool if r[3] != 2][:KEEP - 6]
    videos = [r for r in pool if r[3] == 2][:6]
    keep = stills + videos
    keep_ids = {r[0] for r in keep}
    for rid, in con.execute("SELECT id FROM Images").fetchall():
        if rid not in keep_ids:
            con.execute("DELETE FROM Images WHERE id = ?", (rid,))  # delete_image trigger cascades
    for aid, in con.execute("SELECT id FROM Albums WHERE id NOT IN (SELECT DISTINCT album FROM Images)").fetchall():
        con.execute("DELETE FROM Albums WHERE id = ?", (aid,))
    con.commit()
    con.execute("VACUUM")
    con.close()
    copied = 0
    for _, rel, name, _, _, _, _ in keep:
        s = src_root / rel.lstrip("/") / name
        d = dst / "photos" / rel.lstrip("/") / name
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
        side = Path(str(s) + ".xmp")
        if side.exists():
            shutil.copy2(side, Path(str(d) + ".xmp"))
        copied += 1
    ids = sorted(keep_ids)
    return {"db": db, "root": dst / "photos", "ids": ids, "n": copied, "albums": albums,
            "with_faces": [r[0] for r in keep if r[4]], "with_tags": [r[0] for r in keep if r[5]],
            "with_gps": [r[0] for r in keep if r[6]], "videos": [r[0] for r in videos]}


if __name__ == "__main__":
    import sys
    info = build(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    print({k: (v if not isinstance(v, list) else len(v)) for k, v in info.items()})
