"""Face detection: existing face regions, from digiKam or any tool, are honoured even when the detector's
rectangle differs; only faces nothing marked become new unknown regions in digiKam's database."""
import sqlite3
from pathlib import Path

import pytest

from app import facedetect, index

YUNET = Path("/private/tmp/claude-501/-Users-alex-Pictures/cd6ab508-dd1f-4df1-999c-d6fe0a83fe5c/scratchpad/yunet/yunet.onnx")


def test_same_face_tolerates_different_rectangles():
    digikam = (1000, 400, 180, 220)               # a loose box around the head
    assert facedetect.same_face((1040, 450, 100, 120), digikam)   # the detector's tight box inside it
    assert facedetect.same_face((1100, 380, 160, 200), digikam)   # shifted: centres still inside each other
    assert not facedetect.same_face((1600, 420, 100, 120), digikam)  # someone else
    found = [(1040, 450, 100, 120, 0.9), (1600, 420, 100, 120, 0.9)]
    assert facedetect.new_faces(found, [digikam]) == [found[1]]


def test_detector_finds_the_faces_digikam_marked(client, lib):
    if not YUNET.exists() or facedetect.np is None:
        pytest.skip("YuNet model not available here")
    facedetect.MODEL = YUNET
    facedetect.reset_session()
    con = index.open_index()
    rows = con.execute("SELECT p.id, p.path, p.w, p.h FROM photos p WHERE p.video = 0 AND EXISTS "
                       "(SELECT 1 FROM faces f WHERE f.photo_id = p.id AND f.kind = 'confirmed') LIMIT 12").fetchall()
    matched = total = 0
    for pid, path, w, h in rows:
        found = facedetect.detect_photo(path, w, h)
        for e in con.execute("SELECT x, y, w, h FROM faces WHERE photo_id = ? AND kind = 'confirmed'", (pid,)).fetchall():
            total += 1
            matched += any(facedetect.same_face(f, e) for f in found)
    con.close()
    assert total and matched / total >= 0.7, (matched, total)


def test_detect_endpoint_adds_only_unmarked_faces(client, lib, monkeypatch):
    pid = lib["with_faces"][0]
    con = index.open_index()
    ex = con.execute("SELECT x, y, w, h FROM faces WHERE photo_id = ?", (pid,)).fetchall()
    con.close()
    x, y, w, h = ex[0]
    overlapping = (x + w // 4, y + h // 4, w // 2, h // 2, 0.95)     # the same face, drawn smaller
    fresh = (5, 5, 60, 60, 0.9)
    if any(facedetect.same_face(fresh, e) for e in ex):
        fresh = (x + 3 * w, y, w, h, 0.9)
    monkeypatch.setattr(facedetect, "available", lambda: True)
    monkeypatch.setattr(facedetect, "detect_photo", lambda path, W, H: [overlapping, fresh])
    db = Path(lib["db"])
    c = sqlite3.connect(db)
    before = c.execute("SELECT count(*) FROM ImageTagProperties WHERE imageid = ?", (pid,)).fetchone()[0]
    c.close()
    r = client.post("/api/faces/detect", json={"ids": [pid]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["done"] and j["found"] == 2 and j["added"] == 1, j
    c = sqlite3.connect(db)
    rows = c.execute("SELECT property, value FROM ImageTagProperties WHERE imageid = ?", (pid,)).fetchall()
    assert len(rows) == before + 1
    assert any(p == "autodetectedFace" and f'x="{fresh[0]}" y="{fresh[1]}"' in v for p, v in rows), rows
    c.execute("DELETE FROM ImageTagProperties WHERE imageid = ? AND property = 'autodetectedFace' AND value LIKE ?",
              (pid, f'%x="{fresh[0]}" y="{fresh[1]}"%'))  # put the scratch library back
    c.commit()
    c.close()
    index.build()
