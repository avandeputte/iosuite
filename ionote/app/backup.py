"""Export and import: every note as Markdown with its picture, plus one JSON file that holds everything.

ionotes-export.zip:
  notes.json            every folder, tag colour and note (live ones; with ?trash=1 the trash too) with its fields
  <Folder>/<title>.md   each note as Markdown (front matter: id, dates, tags, source), in its folder's directory
  <Folder>/<title>.png  its picture, next to it
A zip made here imports again on any ionotes server (Maintenance › Import), notes and pictures alike: records
keep their ids, and a record that is newer on the server is left as it is.
"""
import base64
import io
import json
import re
import time
import zipfile

from app import db, images, notes

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


def export_zip(include_trash: bool = False, pictures: bool = True) -> bytes:
    folders = notes.list_folders()
    fname = {f["id"]: _safe(f["name"], "Folder") for f in folders}
    with db.connect() as con:
        rows = con.execute(f"SELECT {notes.NOTE_COLS} FROM notes {'' if include_trash else 'WHERE deleted = 0'} ORDER BY created_at").fetchall()
    all_notes = [notes.note_dict(r) for r in rows]
    buf = io.BytesIO()
    used = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("notes.json", json.dumps({"format": "ionotes-export", "version": 1, "exported": time.time(),
                                             "folders": folders, "tags": notes.tag_colors(), "notes": all_notes}, ensure_ascii=False, indent=1))
        for n in all_notes:
            d = "Trash/" if n["deleted"] else (fname.get(n["folderID"], "") + "/" if n["folderID"] in fname else "")
            base = d + _safe(notes.display_title(n), "Note")
            stem, i = base, 2
            while stem.lower() in used:
                stem, i = f"{base} {i}", i + 1
            used.add(stem.lower())
            md = _markdown(n)
            if pictures and n["hasImage"]:
                got = images.get(n["id"])
                if got:
                    ext = EXT.get(got[1], "img")
                    z.writestr(f"{stem}.{ext}", got[0])
                    md += f"\n![]({stem.rsplit('/', 1)[-1]}.{ext})\n".replace(" ", "%20")
            z.writestr(f"{stem}.md", md)
    return buf.getvalue()


def import_zip(data: bytes, user: str) -> dict:
    """Import an export (zip, or its notes.json alone). Records keep their ids; newer server copies win."""
    pics = {}
    if data[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(data))
        doc = json.loads(z.read("notes.json"))
        names = z.namelist()
    else:
        z, doc, names = None, json.loads(data), []
    # an export says what it is; a notes.json written by hand or by a device may leave that out
    if not isinstance(doc, dict) or doc.get("format", "ionotes-export") != "ionotes-export" or not isinstance(doc.get("notes", []), list):
        raise ValueError("That is not an ionotes export")
    out = {"folders": 0, "notes": 0, "tags": 0, "pictures": 0, "skipped": 0}
    for f in doc.get("folders") or []:
        try:
            notes.save_folder(f["id"], f, user)
            out["folders"] += 1
        except notes.Stale:
            out["skipped"] += 1
    for t in doc.get("tags") or []:
        try:
            notes.set_tag_color(t["name"], t.get("color"), user, t.get("updatedAt"))
            out["tags"] += 1
        except notes.Stale:
            out["skipped"] += 1
    if z:  # pictures by the note's id, from the Markdown that points at them
        for name in names:
            if name.endswith(".md"):
                m = re.search(r"^id: (\S+)$", z.read(name).decode("utf-8", "replace"), re.M)
                if m:
                    stem = name[:-3]
                    pic = next((x for x in names if x.startswith(stem + ".") and not x.endswith(".md")), None)
                    if pic:
                        pics[m.group(1)] = pic
    for n in doc.get("notes") or []:
        img = n.get("imageData")  # a notes.json from a device can carry the picture inline (base64)
        try:
            notes.save_note(n["id"], {k: v for k, v in n.items() if k not in ("hasImage", "imageSHA", "rev", "imageData")}, user)
            out["notes"] += 1
        except notes.Stale:
            out["skipped"] += 1
            continue
        blob = base64.b64decode(img) if img else (z.read(pics[n["id"]]) if z and n["id"] in pics else None)
        if blob and not n.get("deleted"):
            try:
                images.put(n["id"], blob, user)
                out["pictures"] += 1
            except (images.BadImage, KeyError):
                pass
    return out
