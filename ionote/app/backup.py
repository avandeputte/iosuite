"""Export and import: every note as Markdown with its picture, plus one JSON file that holds everything.

ionote-export.zip:
  notes.json            every folder, tag colour and note (live ones; with ?trash=1 the trash too) with its fields
  <Folder>/<title>.md   each note as Markdown (front matter: id, dates, tags, source), in its folder's directory
  <Folder>/<title>.png  its picture, next to it
  <Folder>/<title> files/<name>  its attached files (notes.json lists them under each note's "attachments", with "file")
  templates             in notes.json too
A zip made here imports again on any ionote server (Settings › Export and import), notes and pictures alike: records
keep their ids, and a record that is newer on the server is left as it is.
"""
import base64
import io
import json
import re
import tempfile
import time
import zipfile

from app import attachments, config, db, images, notes
from iosuite_shared.errors import Invalid

EXT = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp", "image/tiff": "tiff", "image/bmp": "bmp"}


def _safe(name: str, fallback: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", name or "").strip().strip(".")
    return (name or fallback)[:80]


def _markdown(n: dict) -> str:
    fm = ["---", f"id: {n['id']}", f"created: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(n['createdAt']))}",
          f"updated: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(n['updatedAt']))}", f"source: {n['source']}"]
    if n["sourceApp"]:
        fm.append(f"source_app: {n['sourceApp']}")
    if n["tags"]:
        fm.append("tags: [" + ", ".join(json.dumps(t, ensure_ascii=False) for t in n["tags"]) + "]")
    if n["pinned"]:
        fm.append("pinned: true")
    fm.append("---")
    parts = ["\n".join(fm), ""]
    if n["title"]:
        parts.append(f"# {n['title']}\n")
    if n["body"]:
        parts.append(n["body"] + "\n")
    if n["ocrText"]:
        parts.append("## Text in the picture\n\n" + n["ocrText"] + "\n")
    return "\n".join(parts)


def export_zip(include_trash: bool = False, pictures: bool = True):
    """The export as a file: written to a temporary file (in memory while small) and handed back at its start, for the
    caller to send in pieces and close. The pictures go in one at a time, so the whole export is never in memory."""
    folders = notes.list_folders()
    fname = {f["id"]: _safe(f["name"], "Folder") for f in folders}
    with db.connect() as con:
        rows = con.execute(f"SELECT {notes.NOTE_COLS} FROM nts_notes WHERE user_id = ? AND deleted {'< 2' if include_trash else '= 0'} ORDER BY created_at",
                           (notes.owner(),)).fetchall()
        all_notes = notes.with_attachments(con, [notes.note_dict(r) for r in rows])
    buf = tempfile.SpooledTemporaryFile(max_size=8 << 20)
    used = set()
    stems = {}
    for n in all_notes:
        d = "Trash/" if n["deleted"] else (fname.get(n["folderID"], "") + "/" if n["folderID"] in fname else "")
        base = d + _safe(notes.display_title(n), "Note")
        stem, i = base, 2
        while stem.lower() in used:
            stem, i = f"{base} {i}", i + 1
        used.add(stem.lower())
        stems[n["id"]] = stem
        if pictures:
            seen = set()
            for a in n.get("attachments") or []:
                fn = _safe(a["name"], "file")
                k, j = fn, 2
                while k.lower() in seen:
                    stem_a, dot, ext = fn.rpartition(".")
                    k, j = (f"{stem_a} {j}.{ext}" if dot else f"{fn} {j}"), j + 1
                seen.add(k.lower())
                a["file"] = f"{stem} files/{k}"
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("notes.json", json.dumps({"format": "ionote-export", "version": 1, "exported": time.time(),
                                             "folders": folders, "tags": notes.tag_colors(), "templates": notes.list_templates(),
                                             "notes": all_notes}, ensure_ascii=False, indent=1))
        for n in all_notes:
            stem = stems[n["id"]]
            md = _markdown(n)
            if pictures and n["hasImage"]:
                got = images.get(n["id"])
                if got:
                    ext = EXT.get(got[1], "img")
                    z.writestr(f"{stem}.{ext}", got[0])
                    md += f"\n![]({stem.rsplit('/', 1)[-1]}.{ext})\n".replace(" ", "%20")
            for a in n.get("attachments") or []:
                if "file" in a:
                    got = attachments.get(n["id"], a["id"])
                    if got:
                        z.writestr(a["file"], got[0])
                        md += f"\n- [{a['name']}](<{a['file'].rsplit('/', 1)[-1]}>)\n"
            z.writestr(f"{stem}.md", md)
    buf.seek(0)
    return buf


def pieces(f, size: int = 1 << 20):
    """A file's bytes a piece at a time; the file is closed at the end (or when the download is given up)."""
    try:
        while chunk := f.read(size):
            yield chunk
    finally:
        f.close()


MAX_JSON = 256 << 20  # notes.json (a device's can carry its pictures inline)
MAX_MD = 16 << 20  # one note as Markdown: its text and the text in its picture


def _member(z: zipfile.ZipFile, name: str, limit: int) -> bytes:
    """One file of the zip, refused when it would unpack to more than limit bytes (a zip bomb)."""
    if z.getinfo(name).file_size > limit:
        raise Invalid(f"{name} is too large")
    with z.open(name) as f:
        data = f.read(limit + 1)
    if len(data) > limit:
        raise Invalid(f"{name} is too large")
    return data


def import_zip(src, user: str) -> dict:
    """Import an export (zip, or its notes.json alone), from bytes or a file. Records keep their ids; newer
    server copies win. An id another account on this server has (its export, imported here) gets a new one."""
    f = io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else src
    pics = {}
    if f.read(2) == b"PK":
        f.seek(0)
        try:
            z = zipfile.ZipFile(f)
        except zipfile.BadZipFile:
            raise Invalid("That is not a zip ioNote can read")
        doc = json.loads(_member(z, "notes.json", MAX_JSON))
        names = z.namelist()
    else:
        f.seek(0)
        data = f.read(MAX_JSON + 1)
        if len(data) > MAX_JSON:
            raise Invalid("notes.json is too large")
        z, doc, names = None, json.loads(data), []
    # an export says what it is; a notes.json written by hand or by a device may leave that out
    if not isinstance(doc, dict) or doc.get("format", "ionote-export") != "ionote-export" or not isinstance(doc.get("notes", []), list):
        raise Invalid("That is not an ioNote export")
    out = {"folders": 0, "notes": 0, "tags": 0, "pictures": 0, "files": 0, "templates": 0, "skipped": 0}
    fmap = {}  # a folder id another account has -> the new id it gets here
    for fo in doc.get("folders") or []:
        try:
            notes.save_folder(fo["id"], fo, user)
            out["folders"] += 1
        except notes.Stale:
            out["skipped"] += 1
        except notes.NotFound:  # another account's id: imported as a new folder
            fmap[fo["id"]] = notes.save_folder(None, {k: v for k, v in fo.items() if k != "id"}, user)["id"]
            out["folders"] += 1
    for t in doc.get("tags") or []:
        try:
            notes.set_tag_color(t["name"], t.get("color"), user, t.get("updatedAt"))
            out["tags"] += 1
        except notes.Stale:
            out["skipped"] += 1
    for t in doc.get("templates") or []:
        try:
            fields = {k: v for k, v in t.items() if k not in ("rev",)}
            if fields.get("folderID") in fmap:
                fields["folderID"] = fmap[fields["folderID"]]
            try:
                notes.save_template(t["id"], fields, user)
            except notes.NotFound:
                notes.save_template(None, {k: v for k, v in fields.items() if k != "id"}, user)
            out["templates"] += 1
        except notes.Stale:
            out["skipped"] += 1
        except (KeyError, ValueError, TypeError):
            out["skipped"] += 1
    if z:  # pictures by the note's id, from the Markdown that points at them
        # exactly <stem>.<ext>: "Meeting.png" is not the picture of "Meeting.v2"'s neighbour "Meeting"
        by_stem = {}
        for x in names:
            stem, _, ext = x.rpartition(".")
            if ext in EXT.values():
                by_stem.setdefault(stem, x)
        for name in names:
            if name.endswith(".md") and name[:-3] in by_stem:
                m = re.search(r"^id: (\S+)$", _member(z, name, MAX_MD).decode("utf-8", "replace"), re.M)
                if m:
                    pics[m.group(1)] = by_stem[name[:-3]]
    for n in doc.get("notes") or []:
        img = n.get("imageData")  # a notes.json from a device can carry the picture inline (base64)
        fields = {k: v for k, v in n.items() if k not in ("hasImage", "imageSHA", "rev", "imageData", "attachments", "image")}
        if fields.get("folderID") in fmap:
            fields["folderID"] = fmap[fields["folderID"]]
        try:
            uid = notes.save_note(n["id"], fields, user)["id"]
            out["notes"] += 1
        except notes.Stale:  # newer here
            out["skipped"] += 1
            continue
        except notes.NotFound:  # the id is another account's: imported as a new note
            uid = notes.save_note(None, fields, user)["id"]
            out["notes"] += 1
        if n.get("deleted"):
            continue
        try:
            blob = base64.b64decode(img) if img else (_member(z, pics[n["id"]], config.MAX_IMAGE_MB << 20) if z and n["id"] in pics else None)
            if blob:
                images.put(uid, blob, user)
                out["pictures"] += 1
        except (images.BadImage, KeyError, ValueError):  # not a picture ionote can read, or too large: the note without it
            pass
        for a in (n.get("attachments") or []) if z else []:
            if not isinstance(a, dict) or a.get("file") not in names:
                continue
            try:
                blob = _member(z, a["file"], config.MAX_IMAGE_MB << 20)
                try:
                    attachments.put(uid, blob, a.get("name") or a["file"].rsplit("/", 1)[-1], user, a.get("mime") or "", a.get("id"))
                except notes.NotFound:  # the id is another account's or another note's: a new one
                    attachments.put(uid, blob, a.get("name") or a["file"].rsplit("/", 1)[-1], user, a.get("mime") or "")
                out["files"] += 1
            except (attachments.BadFile, KeyError, ValueError):
                pass
    return out
