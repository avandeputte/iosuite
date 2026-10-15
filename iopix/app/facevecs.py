"""Face grouping for the work queue: an embedding per face digiKam has not named (its
"Unknown" faces and its own suggestions), so the Faces page can show look-alike faces
together and they can be named or ignored in one go.

The embeddings come from OpenCV's SFace model (ONNX, run locally with onnxruntime) on the
square crops the face queue already shows. They are used only to group: the viewer never
proposes a name for a face on its own; naming stays with digiKam's suggestions and the owner.
Vectors live in the viewer database (face_vecs) and are pruned when a face is decided.
"""
import logging
import threading
import time

import numpy as np

from . import config, index, jobs, thumbs, vdb

log = logging.getLogger("app.facevecs")
MODEL = config.DATA_DIR / "models" / "face_recognition_sface_2021dec.onnx"
URL = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
SIZE = 112
KINDS = ("unknown", "suggested")
GROUP_THRESHOLD = 0.45  # cosine; OpenCV's own same-identity threshold for SFace is 0.363, a little stricter here
progress = {"running": False, "done": 0, "total": 0}
_lock = threading.Lock()
_session = None
_run = {"gen": 0}


def download():
    import urllib.request
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    tmp = MODEL.with_suffix(".part")
    urllib.request.urlretrieve(URL, tmp)
    tmp.replace(MODEL)


def available() -> bool:
    if not MODEL.exists():
        return False
    try:
        import onnxruntime  # noqa: F401
        return True
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


def embed_paths(paths: list) -> np.ndarray:
    """Unit vectors (128-d) for face crop files; SFace takes 112x112 BGR, pixel values as they are."""
    from PIL import Image
    s = _sess()
    name = s.get_inputs()[0].name
    out = []
    for p in paths:
        im = Image.open(p).convert("RGB").resize((SIZE, SIZE), Image.Resampling.BILINEAR)
        arr = np.asarray(im, dtype=np.float32)[:, :, ::-1]  # RGB -> BGR
        blob = np.transpose(arr, (2, 0, 1))[None]
        v = s.run(None, {name: np.ascontiguousarray(blob)})[0][0]
        out.append(v / max(float(np.linalg.norm(v)), 1e-9))
    return np.asarray(out, dtype=np.float32)


def _faces():
    """Every undecided face from the index with what the crop needs: [(photo, x, y, w, h, path, pw, ph)]."""
    con = index.open_index()
    try:
        return con.execute("SELECT f.photo_id, f.x, f.y, f.w, f.h, p.path, p.w, p.h FROM faces f JOIN photos p ON p.id = f.photo_id "
                           f"WHERE f.kind IN ({','.join('?' * len(KINDS))}) AND p.video = 0", KINDS).fetchall()
    finally:
        con.close()


def _have() -> set:
    con = vdb.connect()
    try:
        return {tuple(r) for r in con.execute("SELECT photo_id, x, y, w, h FROM face_vecs")}
    finally:
        con.close()


def coverage() -> tuple:
    """(faces with a vector, undecided faces) for the Maintenance row."""
    try:
        return len(_have()), len(_faces())
    except Exception:
        return 0, 0


def start():
    """Embed the undecided faces that have no vector yet, and drop vectors of faces since decided."""
    if not config.ANALYSIS or not available():
        return
    _run["gen"] += 1
    gen = _run["gen"]
    jobs.submit("faces", lambda: _job(gen))


def _job(gen: int):
    faces = _faces()
    have = _have()
    todo = [f for f in faces if (f[0], f[1], f[2], f[3], f[4]) not in have]
    progress.update(running=True, done=0, total=len(todo))
    try:
        for i in range(0, len(todo), 32):
            if gen != _run["gen"]:
                return
            batch, paths = [], []
            for pid, x, y, w, h, path, pw, ph in todo[i:i + 32]:
                try:
                    paths.append(str(thumbs.make_face(0, {"id": pid, "path": path, "w": pw, "h": ph}, (x, y, w, h))))
                    batch.append((pid, x, y, w, h))
                except Exception as e:
                    log.warning("faces: no crop for photo %s (%s)", pid, e)
            if batch:
                try:
                    vecs = embed_paths(paths)
                except Exception as e:
                    log.warning("faces: embedding failed (%s)", e)
                    continue
                con = vdb.connect()
                try:
                    con.executemany("INSERT OR REPLACE INTO face_vecs (photo_id, x, y, w, h, vec) VALUES (?,?,?,?,?,?)",
                                    [(*key, vecs[k].astype(np.float32).tobytes()) for k, key in enumerate(batch)])
                    con.commit()
                finally:
                    con.close()
            progress["done"] = min(len(todo), i + 32)
        # faces decided since (named, ignored, removed) no longer need a vector
        current = {(f[0], f[1], f[2], f[3], f[4]) for f in faces}
        stale = [k for k in have if k not in current]
        if stale:
            con = vdb.connect()
            try:
                con.executemany("DELETE FROM face_vecs WHERE photo_id = ? AND x = ? AND y = ? AND w = ? AND h = ?", stale)
                con.commit()
            finally:
                con.close()
    finally:
        progress["running"] = False


def reset():
    _run["gen"] += 1
    con = vdb.connect()
    try:
        con.execute("DELETE FROM face_vecs")
        con.commit()
    finally:
        con.close()


def groups(kind: str = "unknown", threshold: float = GROUP_THRESHOLD, tag: int = None) -> dict:
    """Undecided faces of one kind, look-alikes together: {groups: [{faces: [...], n}], ungrouped: [...],
    missing: faces without a vector yet}. Groups are connected components of pairs above the threshold."""
    con = index.open_index()
    con.row_factory = __import__("sqlite3").Row
    try:
        where, params = "f.kind = ? AND p.video = 0", [kind]
        if tag:
            where += " AND f.tag_id = ?"
            params.append(tag)
        rows = con.execute(f"SELECT f.photo_id AS photo, f.tag_id AS tag, f.x, f.y, f.w, f.h, p.ts, p.name AS file, p.w AS pw, p.h AS ph, "
                           f"(SELECT name FROM tags t WHERE t.id = f.tag_id) AS name FROM faces f JOIN photos p ON p.id = f.photo_id "
                           f"WHERE {where} ORDER BY p.ts DESC", params).fetchall()
    finally:
        con.close()
    faces = [dict(r) for r in rows]
    vcon = vdb.connect()
    try:
        vecs = {(r[0], r[1], r[2], r[3], r[4]): np.frombuffer(r[5], dtype=np.float32) for r in vcon.execute("SELECT photo_id, x, y, w, h, vec FROM face_vecs")}
    finally:
        vcon.close()
    keyed = [(f, vecs.get((f["photo"], f["x"], f["y"], f["w"], f["h"]))) for f in faces]
    missing = [f for f, v in keyed if v is None]
    have = [(f, v) for f, v in keyed if v is not None]
    out = {"groups": [], "ungrouped": [], "missing": missing, "total": len(faces), "threshold": threshold}
    if not have:
        return out
    m = np.stack([v for _, v in have])
    sims = m @ m.T
    n = len(have)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    ii, jj = np.nonzero(np.triu(sims, 1) >= threshold)
    for i, j in zip(ii.tolist(), jj.tolist()):
        a, b = find(i), find(j)
        if a != b:
            parent[b] = a
    members = {}
    for i in range(n):
        members.setdefault(find(i), []).append(i)
    for root, idx in members.items():
        if len(idx) == 1:
            out["ungrouped"].append(have[idx[0]][0])
            continue
        c = m[idx].mean(axis=0)
        order = sorted(idx, key=lambda k: -float(m[k] @ c))  # the most typical face first
        out["groups"].append({"n": len(idx), "faces": [have[k][0] for k in order]})
    out["groups"].sort(key=lambda g: -g["n"])
    return out
