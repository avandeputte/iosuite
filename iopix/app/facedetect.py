"""Face detection on request: a photo, a folder or the whole library.

The detector is OpenCV's YuNet (face_detection_yunet_2023mar.onnx, 230 KB, run with onnxruntime).
Every face it finds is compared with the face regions the photo already has, of any kind and from any
tool (named, unknown, suggested or ignored, digiKam's or the viewer's): a detection that overlaps an
existing region is the same face, even when the two rectangles differ in size or position, and is left
alone. Only faces nothing else marked become new regions, written the way digiKam writes a face it
found but could not name (an "Unknown" region), so they show up under People › Unnamed faces, get a
"looks like" suggestion from face grouping, and can be named there or in digiKam.

Nothing runs on its own: the library job starts only from Maintenance, a folder or a photo. Each photo
checked is remembered (ai_faces_scanned) so a library run picks up only new and changed photos; a run
on one photo or one folder always looks again. A face removed after a run is not brought back by the
next library run, since that photo is not looked at again unless it changes.
"""
import json
import logging
import threading
import time
import urllib.request

from . import analysis, config, index, jobs, thumbs, vdb

try:
    import numpy as np
except ImportError:  # optional: the AI packages
    np = None

log = logging.getLogger("app.facedetect")
MODEL = config.DATA_DIR / "models" / "face_detection_yunet_2023mar.onnx"
URL = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
SIDE = 640           # the model's fixed input
SCORE = 0.85         # YuNet's own default is 0.9; a little lower finds more turned and partly hidden faces
NMS_IOU = 0.3
MIN_FACE = 28        # pixels at full resolution: smaller detections are mostly noise
OVERLAP = 0.3        # a detection covering this much of an existing region (or the other way round) is that face
progress = {"running": False, "done": 0, "total": 0, "added": 0, "photos_with_new": 0, "errors": 0, "started": None, "scope": None}
_lock = threading.Lock()
_session = None
_run = {"gen": 0}


def download():
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    tmp = MODEL.with_suffix(".part")
    urllib.request.urlretrieve(URL, tmp)
    tmp.replace(MODEL)


def available() -> bool:
    if np is None or not MODEL.exists():
        return False
    try:
        import onnxruntime
        return bool(onnxruntime.__version__)
    except ImportError:
        return False


def _sess():
    global _session
    with _lock:
        if _session is None:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = max(1, jobs.threads())
            _session = ort.InferenceSession(str(MODEL), sess_options=opts, providers=["CPUExecutionProvider"])
        return _session


def reset_session():
    global _session
    with _lock:
        _session = None


# ---- the detector
def _run_square(img) -> list:
    """One pass over a PIL image letterboxed into 640x640: [(x, y, w, h, score)] in the image's pixels."""
    from PIL import Image
    s = min(SIDE / img.width, SIDE / img.height)
    w, h = max(1, round(img.width * s)), max(1, round(img.height * s))
    canvas = Image.new("RGB", (SIDE, SIDE))
    canvas.paste(img.convert("RGB").resize((w, h), Image.Resampling.BILINEAR), (0, 0))
    arr = np.asarray(canvas, dtype=np.float32)[:, :, ::-1]  # RGB -> BGR, values 0..255 as the model expects
    blob = np.ascontiguousarray(np.transpose(arr, (2, 0, 1))[None])
    sess = _sess()
    names = [o.name for o in sess.get_outputs()]
    out = dict(zip(names, sess.run(None, {sess.get_inputs()[0].name: blob})))
    found = []
    for stride in (8, 16, 32):
        cols = SIDE // stride
        cls, obj, box = out[f"cls_{stride}"][0, :, 0], out[f"obj_{stride}"][0, :, 0], out[f"bbox_{stride}"][0]
        score = np.sqrt(np.clip(cls, 0, 1) * np.clip(obj, 0, 1))
        for i in np.nonzero(score >= SCORE)[0]:
            r, c = divmod(int(i), cols)
            cx, cy = (c + box[i, 0]) * stride, (r + box[i, 1]) * stride
            bw, bh = float(np.exp(box[i, 2])) * stride, float(np.exp(box[i, 3])) * stride
            found.append(((cx - bw / 2) / s, (cy - bh / 2) / s, bw / s, bh / s, float(score[i])))
    return found


def _iou(a, b) -> float:
    ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / max(a[2] * a[3] + b[2] * b[3] - inter, 1e-9)


def _nms(boxes: list) -> list:
    keep = []
    for b in sorted(boxes, key=lambda x: -x[4]):
        if all(_iou(b, k) < NMS_IOU for k in keep):
            keep.append(b)
    return keep


def detect_image(img) -> list:
    """Faces in an upright PIL image: [(x, y, w, h, score)] in its pixels. Large pictures also get a
    2x2 pass of overlapping tiles, so small faces in group photos are not lost to the 640 px input."""
    boxes = _run_square(img)
    if max(img.width, img.height) > 1.6 * SIDE:
        tw, th = int(img.width * 0.6), int(img.height * 0.6)
        for ox in (0, img.width - tw):
            for oy in (0, img.height - th):
                boxes += [(x + ox, y + oy, w, h, sc) for x, y, w, h, sc in _run_square(img.crop((ox, oy, ox + tw, oy + th)))]
    return _nms(boxes)


def detect_photo(path: str, full_w: int, full_h: int) -> list:
    """Faces in a photo file, in upright full-resolution pixels (digiKam's region coordinates)."""
    img, _ = thumbs._open_oriented(path, 2400, 2400)
    sx = full_w / img.width if full_w and full_w > 8 else 1.0
    sy = full_h / img.height if full_h and full_h > 8 else 1.0
    out = []
    for x, y, w, h, sc in detect_image(img):
        X, Y, W, H = max(0, round(x * sx)), max(0, round(y * sy)), round(w * sx), round(h * sy)
        W, H = min(W, (full_w or img.width) - X), min(H, (full_h or img.height) - Y)
        if min(W, H) >= MIN_FACE:
            out.append((X, Y, W, H, round(sc, 3)))
    return out


def same_face(a, b) -> bool:
    """Whether two rectangles mark the same face: one's centre inside the other, or a large share of the
    smaller one covered. Tools draw faces differently (tight around the features, or the whole head), so
    neither size nor position has to agree."""
    ax, ay, aw, ah = a[:4]
    bx, by, bw, bh = b[:4]
    acx, acy, bcx, bcy = ax + aw / 2, ay + ah / 2, bx + bw / 2, by + bh / 2
    if bx <= acx <= bx + bw and by <= acy <= by + bh or ax <= bcx <= ax + aw and ay <= bcy <= ay + ah:
        return True
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    return ix * iy >= OVERLAP * max(1, min(aw * ah, bw * bh))


def new_faces(found: list, existing: list) -> list:
    """The detections no existing region already marks."""
    return [f for f in found if not any(same_face(f, e) for e in existing)]


# ---- which photos, what they already have
def _photos(ids: list = None, album: int = None) -> list:
    con = index.open_index()
    con.row_factory = __import__("sqlite3").Row
    try:
        sql = "SELECT p.id, p.path, p.name, p.w, p.h, p.hash, p.size, p.modified FROM photos p WHERE p.video = 0"
        if ids is not None:
            rows = []
            for i in range(0, len(ids), 500):
                chunk = ",".join(str(int(x)) for x in ids[i:i + 500])
                rows += con.execute(sql + f" AND p.id IN ({chunk})").fetchall()
        elif album is not None:
            rows = con.execute(sql + " AND p.album_id IN (SELECT album FROM album_closure WHERE anc = ?) ORDER BY p.ts DESC", (int(album),)).fetchall()
        else:
            rows = con.execute(sql + " ORDER BY p.ts DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def _existing(ids: list) -> dict:
    """{photo: [(x, y, w, h)]} every face region the index knows, of every kind."""
    out = {}
    con = index.open_index()
    try:
        for i in range(0, len(ids), 500):
            chunk = ",".join(str(int(x)) for x in ids[i:i + 500])
            for pid, x, y, w, h in con.execute(f"SELECT photo_id, x, y, w, h FROM faces WHERE photo_id IN ({chunk})"):
                out.setdefault(pid, []).append((x, y, w, h))
    finally:
        con.close()
    return out


def _scanned() -> dict:
    con = vdb.connect()
    try:
        return dict(con.execute("SELECT photo_id, stamp FROM ai_faces_scanned").fetchall())
    finally:
        con.close()


def coverage() -> int:
    from . import vdb as v
    if not v.exists():
        return 0
    con = v.connect()
    try:
        return con.execute("SELECT count(*) FROM ai_faces_scanned").fetchone()[0]
    except Exception:
        return 0
    finally:
        con.close()


def reset():
    """Forget which photos were looked at, so the next library run looks at all of them again."""
    _run["gen"] += 1
    with analysis._write_lock:
        con = vdb.connect()
        try:
            con.execute("DELETE FROM ai_faces_scanned")
            con.commit()
        finally:
            con.close()


# ---- running
def _write(found: dict) -> int:
    """{photo: [(x, y, w, h)]} new unknown faces into digiKam's database, one transaction per batch."""
    from . import facemgr
    ops = [{"op": "detected", "image": pid, "rect": list(r[:4])} for pid, rects in found.items() for r in rects]
    if not ops:
        return 0
    added = 0
    for i in range(0, len(ops), 200):
        res = facemgr.apply_many(ops[i:i + 200])
        added += sum(1 for r in res if "error" not in r and not r.get("skipped"))
    return added


def _record(rows: list):
    if not rows:
        return
    with analysis._write_lock:
        con = vdb.connect()
        try:
            con.executemany("INSERT OR REPLACE INTO ai_faces_scanned (photo_id, stamp, found, added, checked) VALUES (?,?,?,?,?)", rows)
            con.commit()
        finally:
            con.close()


def detect(photos: list, gen: int = None, on_batch=None) -> dict:
    """Look for faces in these photos (rows from _photos), write the new ones, remember the photos."""
    from concurrent.futures import ThreadPoolExecutor
    total = {"checked": 0, "found": 0, "added": 0, "photos_with_new": 0, "errors": 0}
    n = max(1, jobs.threads())
    for i in range(0, len(photos), 48):
        if gen is not None and gen != _run["gen"]:
            break
        batch = photos[i:i + 48]
        existing = _existing([p["id"] for p in batch])

        def one(p):
            try:
                return p, detect_photo(p["path"], p["w"], p["h"])
            except Exception as e:
                log.warning("face detection: %s: %s", p["path"], e)
                return p, None
        with ThreadPoolExecutor(n, thread_name_prefix="facedetect") as pool:
            results = list(pool.map(one, batch))
        new, rows, now = {}, [], int(time.time())
        for p, found in results:
            if found is None:
                total["errors"] += 1
                continue
            fresh = new_faces(found, existing.get(p["id"], []))
            total["found"] += len(found)
            if fresh:
                new[p["id"]] = fresh
            rows.append((p["id"], analysis._stamp(p), len(found), len(fresh), now))
        added = _write(new)
        _record(rows)
        total["checked"] += len(rows)
        total["added"] += added
        total["photos_with_new"] += len(new)
        if on_batch:
            on_batch(len(batch), added, len(new), total["errors"])
    if total["added"]:
        log.info("face detection: %d new faces in %d of %d photos", total["added"], total["photos_with_new"], total["checked"])
    return total


def start(ids: list = None, album: int = None, redo: bool = False, after=None) -> int:
    """The background job for a folder or the whole library (or a large selection). Returns how many
    photos it will look at; the library run skips photos looked at since they last changed."""
    photos = _photos(ids, album)
    if ids is None and album is None and not redo:
        seen = _scanned()
        photos = [p for p in photos if seen.get(p["id"]) != analysis._stamp(p)]
    _run["gen"] += 1
    gen = _run["gen"]
    scope = "photos" if ids is not None else "folder" if album is not None else "library"
    progress.update(running=bool(photos), done=0, total=len(photos), added=0, photos_with_new=0, errors=0, started=int(time.time()), scope=scope)
    if not photos:
        return 0

    def on_batch(n, added, with_new, errors):
        progress["done"] += n
        progress["added"] += added
        progress["photos_with_new"] += with_new
        progress["errors"] = errors

    def job():
        try:
            detect(photos, gen, on_batch)
        except Exception as e:
            log.warning("face detection stopped: %s", e, exc_info=True)
            progress["error"] = str(e)[:300]
        finally:
            if gen == _run["gen"]:
                progress["running"] = False
            if after:
                after()
    jobs.submit("facedetect", job)
    return len(photos)


def summary_json() -> str:
    return json.dumps(progress)
