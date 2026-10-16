"""Face management, mirroring digiKam's FaceTagsEditor row for row.

Face data lives in digiKam's database (ImageTagProperties + ImageTags), so
every operation here writes it, with the same safeguards as the tag manager:
digiKam closed, database backed up first, one transaction, integrity check.

Row shapes (digiKam 9.1, see facetagseditor.cpp / facetagsiface.cpp):
  confirmed  (image, person, 'tagRegion', rect) + (image, person, 'faceToTrain', rect) + ImageTags(image, person)
  unknown    (image, Unknown tag, 'autodetectedFace', rect)
  suggested  (image, person, 'autodetectedFace', rect)
             + (image, Unconfirmed tag, 'autodetectedPerson', "<person>,autodetectedFace,<rect>")
  ignored    (image, Ignored tag, 'ignoredFace', rect)
A region is '<rect x=".." y=".." width=".." height=".."/>' in upright pixels.

After a change the photo's sidecar gets digiKam's face-region XMP rewritten
(MetadataHub::writeFaceTagsMap / DMetadata::setItemFacesMap): every confirmed
face as an mwg-rs region and an MP region, with the rectangle rotated back to
the file's own orientation and normalised to its unrotated size.
"""
import threading
from pathlib import Path

from . import dbsync, dkdb, edits, index, tagmanager
from .dbsync import SyncError

# which ImageTagProperties row holds the rectangle of each kind of face
REGION_PROP = {"confirmed": "tagRegion", "unknown": "autodetectedFace", "suggested": "autodetectedFace", "ignored": "ignoredFace"}
_lock = threading.Lock()


def rect_xml(x, y, w, h) -> str:
    return f'<rect x="{int(x)}" y="{int(y)}" width="{int(w)}" height="{int(h)}"/>'


def _special(con) -> dict:
    out = {}
    for tid, prop in con.execute("SELECT tagid, property FROM TagProperties WHERE property IN ('unknownPerson', 'ignoredPerson', 'unconfirmedPerson')"):
        out[prop] = tid
    if len(out) < 3:
        raise SyncError("digiKam's Unknown / Unconfirmed / Ignored face tags were not found in the database")
    return out


def _is_person(con, tid: int) -> bool:
    return bool(con.execute("SELECT 1 FROM TagProperties WHERE tagid = ? AND property = 'person'", (tid,)).fetchone())


def _full(con, tid: int) -> str:
    return dkdb.tag_path(dkdb.tag_tree(con), tid)


def _ensure_person(con, tid: int):
    """FaceTags::ensureIsPerson: a tag used for a face carries the 'person' property (its name)."""
    if not _is_person(con, tid):
        name = con.execute("SELECT name FROM Tags WHERE id = ?", (tid,)).fetchone()[0]
        con.execute("INSERT INTO TagProperties (tagid, property, value) VALUES (?, 'person', ?)", (tid, name))


def _add_prop(con, image, tag, prop, value):
    if not con.execute("SELECT 1 FROM ImageTagProperties WHERE imageid = ? AND tagid = ? AND property = ? AND value = ?",
                       (image, tag, prop, value)).fetchone():
        con.execute("INSERT INTO ImageTagProperties (imageid, tagid, property, value) VALUES (?,?,?,?)", (image, tag, prop, value))


def _remove_prop(con, image, tag, prop, value):
    con.execute("DELETE FROM ImageTagProperties WHERE imageid = ? AND tagid = ? AND property = ? AND value = ?", (image, tag, prop, value))


def _remove_face(con, sp, image, tag, kind, rect, touch_tags: bool):
    """FaceTagsEditor::removeFaceAndTag."""
    _remove_prop(con, image, tag, REGION_PROP[kind], rect)
    _remove_prop(con, image, tag, "faceTagExtendedData", rect)
    if kind == "confirmed":
        _remove_prop(con, image, tag, "faceToTrain", rect)
    if kind == "suggested":
        _remove_prop(con, image, sp["unconfirmedPerson"], "autodetectedPerson", f"{tag},autodetectedFace,{rect}")
    if touch_tags and kind == "confirmed":
        still = con.execute("SELECT 1 FROM ImageTagProperties WHERE imageid = ? AND tagid = ? AND property = 'tagRegion'", (image, tag)).fetchone()
        if not still:
            con.execute("DELETE FROM ImageTags WHERE imageid = ? AND tagid = ?", (image, tag))


def _add_confirmed(con, image, tag, rect, train=True):
    """FaceTagsEditor::add / confirmName: a named face, trained, with the tag assigned."""
    _ensure_person(con, tag)
    _add_prop(con, image, tag, "tagRegion", rect)
    if train:
        _add_prop(con, image, tag, "faceToTrain", rect)
    con.execute("REPLACE INTO ImageTags (imageid, tagid) VALUES (?,?)", (image, tag))


def _find(con, sp, image, rect):
    """Which face (tag, kind) sits at this exact rectangle on this image."""
    for tag, prop in con.execute("SELECT tagid, property FROM ImageTagProperties WHERE imageid = ? AND value = ? "
                                 "AND property IN ('tagRegion', 'autodetectedFace', 'ignoredFace')", (image, rect)):
        if prop == "tagRegion":
            return tag, "confirmed"
        if prop == "ignoredFace":
            return tag, "ignored"
        return tag, ("unknown" if tag == sp["unknownPerson"] else "suggested")
    return None, None


def apply(op: dict, db_path=None, check_running: bool = True) -> dict:
    """One face change (see apply_many for the operations)."""
    return apply_many([op], db_path, check_running)[0]


def apply_many(ops: list, db_path=None, check_running: bool = True) -> list:
    """Several face changes in one transaction with one backup. Each op:
    {op: name|confirm|ignore|unknown|remove|add|move, image, rect: [x,y,w,h], tag?, new_rect?}
    name:    give the face at rect (unknown, suggested or confirmed) the person `tag`
    confirm: accept a suggestion as it is
    ignore:  mark the face as not a person to name (digiKam's Ignored)
    unknown: forget the name, keep the region as an unknown face
    remove:  delete the region entirely
    add:     a new region for person `tag`
    detected: a new unknown face (face detection), unless a face already sits at that exact rectangle
    move:    change the rectangle of an existing face to new_rect
    Returns one summary per op; a failed op has an "error" and the others still apply."""
    db_path = Path(db_path or dkdb.sqlite_path())
    if not ops:
        return []
    for op in ops:
        if op.get("op") not in ("name", "confirm", "ignore", "unknown", "remove", "add", "move", "detected"):
            raise SyncError("Unknown face operation")
    dbsync.preflight(db_path, check_running, "faces")
    results, touched = [], []
    with _lock:
        backup = dkdb.backup(db_path, force=len(ops) > 20)  # a big batch gets its own fresh dump
        with dbsync.write_transaction(db_path, check_running) as con:
            sp = _special(con)
            for op in ops:
                try:
                    results.append(_apply_one(con, sp, op))
                    touched.append(int(op.get("image") or 0))
                except SyncError as e:
                    results.append({"op": op.get("op"), "image": op.get("image"), "error": str(e)})
            if not any("error" not in r for r in results):
                raise SyncError(results[0]["error"])
    for image in dict.fromkeys(touched):
        try:
            status = write_regions(image, db_path)
        except Exception as e:  # the database change stands; the sidecar can be rewritten later
            status = "error: " + str(e)[:200]
        for r in results:
            if r.get("image") == image and "error" not in r:
                r["sidecar"] = status
                r["backup"] = str(backup) if backup else None
    return results


def _apply_one(con, sp: dict, op: dict) -> dict:
    kind_op = op.get("op")
    image = int(op.get("image") or 0)
    rect = rect_xml(*op["rect"]) if op.get("rect") else None
    if not con.execute("SELECT 1 FROM Images WHERE id = ? AND status = 1", (image,)).fetchone():
        raise SyncError("That photo is not in the digiKam database.")
    tag, kind = _find(con, sp, image, rect) if rect else (None, None)
    summary = {"op": kind_op, "image": image}
    if kind_op == "detected":  # FaceTagsEditor::add for an unnamed face: the Unknown tag's autodetectedFace row
        if kind is not None:
            summary.update(skipped=True)
            return summary
        _add_prop(con, image, sp["unknownPerson"], "autodetectedFace", rect)
        return summary
    if kind_op == "add":
        new_tag = int(op.get("tag") or 0)
        if new_tag in sp.values() or not con.execute("SELECT 1 FROM Tags WHERE id = ?", (new_tag,)).fetchone():
            raise SyncError("Choose a person for the new face.")
        if kind is not None:
            raise SyncError("There is already a face at exactly that rectangle.")
        _add_confirmed(con, image, new_tag, rect)
        summary.update(tag=new_tag, name=_full(con, new_tag))
        return summary
    if kind is None:
        raise SyncError("No face was found at that rectangle; the photo may have changed in digiKam.")
    if kind_op == "name":
        new_tag = int(op.get("tag") or 0)
        if new_tag in sp.values() or not con.execute("SELECT 1 FROM Tags WHERE id = ?", (new_tag,)).fetchone():
            raise SyncError("Choose a person.")
        _remove_face(con, sp, image, tag, kind, rect, touch_tags=(tag != new_tag))
        _add_confirmed(con, image, new_tag, rect)
        summary.update(tag=new_tag, name=_full(con, new_tag), was=kind)
    elif kind_op == "confirm":
        if kind != "suggested":
            raise SyncError("Only a suggested face can be confirmed.")
        _remove_face(con, sp, image, tag, kind, rect, touch_tags=False)
        _add_confirmed(con, image, tag, rect)
        summary.update(tag=tag, name=_full(con, tag))
    elif kind_op == "ignore":
        _remove_face(con, sp, image, tag, kind, rect, touch_tags=(kind == "confirmed"))
        _add_prop(con, image, sp["ignoredPerson"], "ignoredFace", rect)
    elif kind_op == "unknown":
        _remove_face(con, sp, image, tag, kind, rect, touch_tags=(kind == "confirmed"))
        _add_prop(con, image, sp["unknownPerson"], "autodetectedFace", rect)
    elif kind_op == "remove":
        _remove_face(con, sp, image, tag, kind, rect, touch_tags=True)
    elif kind_op == "move":
        new_rect = rect_xml(*op["new_rect"])
        _remove_face(con, sp, image, tag, kind, rect, touch_tags=False)
        _add_prop(con, image, tag, REGION_PROP[kind], new_rect)
        if kind == "confirmed":
            _add_prop(con, image, tag, "faceToTrain", new_rect)
            con.execute("REPLACE INTO ImageTags (imageid, tagid) VALUES (?,?)", (image, tag))
        elif kind == "suggested":
            _add_prop(con, image, sp["unconfirmedPerson"], "autodetectedPerson", f"{tag},autodetectedFace,{new_rect}")
    summary.update(was=kind, from_tag=tag)
    return summary


def create_person(name: str, parent: int = 0) -> int:
    """A new person tag (under People/<family> usually), marked as a person. Returns its id."""
    r = tagmanager.apply({"op": "add", "parent": parent, "name": name})
    tid = int(r["id"])
    # tagmanager.apply just ran every check and took the backup; this follow-up row is tiny
    con = dkdb.connect(write=True)
    try:
        con.begin_write()
        _ensure_person(con, tid)
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()
    return tid


# --------------------------------------------------------------------------
# sidecar regions (what digiKam writes with "Save face tags" on)
# --------------------------------------------------------------------------

def _unrotate(x, y, w, h, up_w, up_h, orientation):
    """TagRegion::reverseToOrientation: an upright rectangle back to the file's own pixel grid."""
    o = orientation or 1
    if o == 1:
        return x, y, w, h, up_w, up_h
    if o == 2:
        return up_w - x - w, y, w, h, up_w, up_h
    if o == 3:
        return up_w - x - w, up_h - y - h, w, h, up_w, up_h
    if o == 4:
        return x, up_h - y - h, w, h, up_w, up_h
    if o == 5:
        return y, x, h, w, up_h, up_w
    if o == 6:
        return y, up_w - x - w, h, w, up_h, up_w
    if o == 7:
        return up_h - y - h, up_w - x - w, h, w, up_h, up_w
    if o == 8:
        return up_h - y - h, x, h, w, up_h, up_w
    return x, y, w, h, up_w, up_h


def _struct(v) -> str:
    """exiftool's inline structure syntax, with its escapes for the separators."""
    if isinstance(v, dict):
        return "{" + ",".join(f"{k}={_struct(x)}" for k, x in v.items()) + "}"
    if isinstance(v, list):
        return "[" + ",".join(_struct(x) for x in v) + "]"
    s = str(v)
    return s.replace("|", "||").replace(",", "|,").replace("}", "|}").replace("]", "|]")


def write_regions(image: int, db_path=None) -> str:
    """Rewrite the sidecar's (and file's, if enabled) face regions from the database."""
    db_path = Path(db_path or dkdb.sqlite_path())
    src = dkdb.connect(write=False, db_path=db_path)
    try:
        row = src.execute(
            "SELECT i.name, a.albumRoot, a.relativePath, ii.width, ii.height, ii.orientation FROM Images i "
            "JOIN Albums a ON a.id = i.album LEFT JOIN ImageInformation ii ON ii.imageid = i.id WHERE i.id = ?", (image,)).fetchone()
        if not row:
            return "no such image"
        path = dkdb.root_paths(src).get(row[1], "") + row[2].rstrip("/") + "/" + row[0]
        tags = dkdb.tag_tree(src)
        faces = []
        for tid, val in src.execute("SELECT tagid, value FROM ImageTagProperties WHERE imageid = ? AND property = 'tagRegion'", (image,)):
            m = index.RECT_RE.search(val or "")
            if m:
                faces.append((dkdb.tag_path(tags, tid).split("/")[-1], tuple(map(int, m.groups()))))
        # people assigned without a region are written as name-only MP regions, as digiKam does
        with_region = {n for n, _ in faces}
        persons = {r[0] for r in src.execute("SELECT tagid FROM TagProperties WHERE property = 'person'")}
        for (tid,) in src.execute("SELECT tagid FROM ImageTags WHERE imageid = ?", (image,)):
            if tid in persons:
                n = dkdb.tag_path(tags, tid).split("/")[-1]
                if n not in with_region:
                    faces.append((n, None))
        w, h, orient = row[3] or 0, row[4] or 0, row[5] or 1
    finally:
        src.close()
    if not w or not h:
        return "no image size known"
    # the database stores the unrotated size; the regions are upright
    up_w, up_h = (h, w) if orient in (5, 6, 7, 8) else (w, h)
    mwg, mp = [], []
    for name, r in faces:
        if r is None:
            mp.append({"PersonDisplayName": name})
            continue
        x, y, rw, rh, fw, fh = _unrotate(*r, up_w, up_h, orient)
        mwg.append({"Area": {"X": round((x + rw / 2) / fw, 6), "Y": round((y + rh / 2) / fh, 6), "W": round(rw / fw, 6), "H": round(rh / fh, 6), "Unit": "normalized"}, "Name": name, "Type": "Face"})
        mp.append({"PersonDisplayName": name, "Rectangle": f"{x / fw:.6g}, {y / fh:.6g}, {rw / fw:.6g}, {rh / fh:.6g}"})
    args = []
    if mwg:
        args += [f"-XMP-mwg-rs:RegionInfo={_struct({'AppliedToDimensions': {'W': w, 'H': h, 'Unit': 'pixel'}, 'RegionList': mwg})}"]
    else:
        args += ["-XMP-mwg-rs:RegionInfo="]
    args += [f"-XMP-MP:RegionInfoMP={_struct({'Regions': mp})}" if mp else "-XMP-MP:RegionInfoMP="]
    side = edits._prepare(path)
    jobs = [(side, args)]
    if edits.writes_files() and edits.can_write_file(path):
        jobs.append((path, args))
    failed = edits.run_exiftool(jobs)
    return "failed" if failed else "written"
