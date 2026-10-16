"""Face work queue: an embedding per face digiKam has not named (its "Unknown" faces and its
own suggestions), so the Faces page shows look-alikes together and they can be named or
ignored in one go, plus a few embeddings per named person (their most recent confirmed
faces, the prototypes) so each group and face can carry a "looks like" suggestion with a
one-click name. The suggestion is the viewer's own and is never written anywhere until
the owner accepts it; accepting goes through the same face operations as naming by hand.

The embeddings come from OpenCV's SFace model (ONNX, run locally with onnxruntime) on the
square crops the face queue already shows. Vectors live in the viewer database (face_vecs
for undecided faces, face_protos for the named prototypes) and are pruned as faces are decided.
"""
import logging
import threading

try:
    import numpy as np
except ImportError:  # numpy comes with the search/objects extras; without it these features are simply off
    np = None

from . import config, index, jobs, thumbs, vdb

log = logging.getLogger("app.facevecs")
MODEL = config.DATA_DIR / "models" / "face_recognition_sface_2021dec.onnx"
URL = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
SIZE = 112
KINDS = ("unknown", "suggested")
GROUP_THRESHOLD = 0.45  # cosine; OpenCV's own same-identity threshold for SFace is 0.363, a little stricter here
SUGGEST_THRESHOLD = 0.40  # a group or face "looks like" a person when its best prototype match is at least this
PROTOS_PER_PERSON = 12  # the most recent confirmed faces of each person become their prototypes
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


def embed_paths(paths: list):
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


def _proto_faces():
    """The newest confirmed faces of every person, a few each: [(tag, photo, x, y, w, h, path, pw, ph)]."""
    con = index.open_index()
    try:
        rows = con.execute("SELECT f.tag_id, f.photo_id, f.x, f.y, f.w, f.h, p.path, p.w, p.h FROM faces f JOIN photos p ON p.id = f.photo_id "
                           "JOIN tags t ON t.id = f.tag_id WHERE f.kind = 'confirmed' AND t.person = 1 AND p.video = 0 ORDER BY f.tag_id, p.ts DESC").fetchall()
    finally:
        con.close()
    out, seen = [], {}
    for r in rows:
        if seen.get(r[0], 0) < PROTOS_PER_PERSON:
            seen[r[0]] = seen.get(r[0], 0) + 1
            out.append(r)
    return out


def _have_protos() -> dict:
    con = vdb.connect()
    try:
        return {(r[1], r[2], r[3], r[4], r[5]): r[0] for r in con.execute("SELECT tag_id, photo_id, x, y, w, h FROM ai_person_references")}
    finally:
        con.close()


def _have() -> set:
    con = vdb.connect()
    try:
        return {tuple(r) for r in con.execute("SELECT photo_id, x, y, w, h FROM ai_face_embeddings")}
    finally:
        con.close()


def coverage() -> tuple:
    """(faces with a vector, faces to embed) for the Maintenance row: undecided faces plus the prototypes."""
    try:
        return len(_have()) + len(_have_protos()), len(_faces()) + len(_proto_faces())
    except Exception:
        return 0, 0


def start():
    """Embed the undecided faces that have no vector yet, and drop vectors of faces since decided."""
    if not config.ANALYSIS or not available():
        return
    _run["gen"] += 1
    gen = _run["gen"]
    jobs.submit("faces", lambda: _job(gen))


def _embed_into(gen: int, todo: list, table: str, offset: int):
    """todo: [(key..., path, pw, ph)] where key is (photo, x, y, w, h) or (tag, photo, x, y, w, h); rows go to `table`."""
    tagged = table == "ai_person_references"
    for i in range(0, len(todo), 32):
        if gen != _run["gen"]:
            return False
        batch, paths = [], []
        for row in todo[i:i + 32]:
            key, (path, pw, ph) = row[:-3], row[-3:]
            pid = key[1] if tagged else key[0]
            rect = key[2:6] if tagged else key[1:5]
            try:
                paths.append(str(thumbs.make_face(0, {"id": pid, "path": path, "w": pw, "h": ph}, tuple(rect))))
                batch.append(tuple(key))
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
                if tagged:
                    con.executemany("INSERT OR REPLACE INTO ai_person_references (tag_id, photo_id, x, y, w, h, vec) VALUES (?,?,?,?,?,?,?)",
                                    [(*key, vecs[k].astype(np.float32).tobytes()) for k, key in enumerate(batch)])
                else:
                    con.executemany("INSERT OR REPLACE INTO ai_face_embeddings (photo_id, x, y, w, h, vec) VALUES (?,?,?,?,?,?)",
                                    [(*key, vecs[k].astype(np.float32).tobytes()) for k, key in enumerate(batch)])
                con.commit()
            finally:
                con.close()
        progress["done"] = offset + min(len(todo), i + 32)
    return True


def _job(gen: int):
    faces, protos = _faces(), _proto_faces()
    have, have_p = _have(), _have_protos()
    todo = [f for f in faces if (f[0], f[1], f[2], f[3], f[4]) not in have]
    todo_p = [f for f in protos if (f[1], f[2], f[3], f[4], f[5]) not in have_p or have_p[(f[1], f[2], f[3], f[4], f[5])] != f[0]]
    progress.update(running=True, done=0, total=len(todo) + len(todo_p))
    try:
        if not _embed_into(gen, todo_p, "ai_person_references", 0):  # the prototypes first: they make the suggestions possible
            return
        if not _embed_into(gen, todo, "ai_face_embeddings", len(todo_p)):
            return
        # faces decided since (named, ignored, removed) no longer need a vector; prototypes follow the newest faces
        current = {(f[0], f[1], f[2], f[3], f[4]) for f in faces}
        stale = [k for k in have if k not in current]
        current_p = {(f[1], f[2], f[3], f[4], f[5]) for f in protos}
        stale_p = [k for k in have_p if k not in current_p]
        if stale or stale_p:
            con = vdb.connect()
            try:
                if stale:
                    con.executemany("DELETE FROM ai_face_embeddings WHERE photo_id = ? AND x = ? AND y = ? AND w = ? AND h = ?", stale)
                if stale_p:
                    con.executemany("DELETE FROM ai_person_references WHERE photo_id = ? AND x = ? AND y = ? AND w = ? AND h = ?", stale_p)
                con.commit()
            finally:
                con.close()
    finally:
        progress["running"] = False


def reset():
    _run["gen"] += 1
    con = vdb.connect()
    try:
        con.execute("DELETE FROM ai_face_embeddings")
        con.execute("DELETE FROM ai_person_references")
        con.commit()
    finally:
        con.close()


def _prototypes() -> tuple:
    """(matrix of prototype vectors, their tag ids, {tag: name}) for the suggestions; empty when none."""
    con = vdb.connect()
    try:
        rows = [(r[0], np.frombuffer(r[1], dtype=np.float32)) for r in con.execute("SELECT tag_id, vec FROM ai_person_references")]
    finally:
        con.close()
    if not rows:
        return None, None, {}
    icon = index.open_index()
    try:
        names = dict(icon.execute("SELECT id, name FROM tags WHERE person = 1").fetchall())
    finally:
        icon.close()
    rows = [r for r in rows if r[0] in names]
    if not rows:
        return None, None, {}
    return np.stack([v for _, v in rows]), np.asarray([t for t, _ in rows]), names


def _suggest(vec, pm, ptags, names):
    """The person whose prototypes match this vector best: {tag, name, score}, or None below the threshold."""
    if pm is None:
        return None
    sims = pm @ vec
    best = {}
    for t, sc in zip(ptags.tolist(), sims.tolist()):
        best[t] = max(best.get(t, -1), sc)
    t, sc = max(best.items(), key=lambda kv: kv[1])
    return {"tag": int(t), "name": names.get(int(t)), "score": round(float(sc), 3)} if sc >= SUGGEST_THRESHOLD else None


def groups(kind: str = "unknown", threshold: float = GROUP_THRESHOLD, tag: int = None) -> dict:
    """Undecided faces of one kind, look-alikes together: {groups: [{faces: [...], n, suggest}], ungrouped: [...],
    missing: faces without a vector yet}. Groups are connected components of pairs above the threshold; each group
    and each face carries the viewer's own "looks like" suggestion when a named person's prototypes match."""
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
        vecs = {(r[0], r[1], r[2], r[3], r[4]): np.frombuffer(r[5], dtype=np.float32) for r in vcon.execute("SELECT photo_id, x, y, w, h, vec FROM ai_face_embeddings")}
    finally:
        vcon.close()
    keyed = [(f, vecs.get((f["photo"], f["x"], f["y"], f["w"], f["h"]))) for f in faces]
    missing = [f for f, v in keyed if v is None]
    have = [(f, v) for f, v in keyed if v is not None]
    out = {"groups": [], "ungrouped": [], "missing": missing, "total": len(faces), "threshold": threshold}
    if not have:
        return out
    pm, ptags, names = _prototypes()
    out["people"] = len(set(ptags.tolist())) if ptags is not None else 0
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
            f = dict(have[idx[0]][0])
            f["suggest"] = _suggest(m[idx[0]], pm, ptags, names)
            out["ungrouped"].append(f)
            continue
        c = m[idx].mean(axis=0)
        c = c / max(float(np.linalg.norm(c)), 1e-9)
        order = sorted(idx, key=lambda k: -float(m[k] @ c))  # the most typical face first
        out["groups"].append({"n": len(idx), "faces": [have[k][0] for k in order], "suggest": _suggest(c, pm, ptags, names)})
    out["groups"].sort(key=lambda g: -g["n"])
    return out
