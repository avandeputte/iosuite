"""A document's scans and files: the front and back of a license, the photo page of a passport, a policy's PDF.

The bytes are kept in the database (doc_file_parts, in parts of PART_BYTES), so the suite's database backup (ioBackup)
holds them too and nothing lives beside the app. A picture (and a PDF's first page) also gets a small JPEG for the
cards (thumb); the first file with one is the document's cover. Each file can be read (app/ocr.py): its text goes
into the search, and the facts made of it fill in the document (app/model.py apply_found). A file is served as it
came, with its own type, except for the kinds a page could run (HTML, SVG, XML...), which are sent as a download.
"""
import datetime as dt
import hashlib
import io
import json
import logging
import mimetypes
import re

from PIL import Image, ImageOps, UnidentifiedImageError

from iosuite_shared.errors import Invalid

from app import config, db, ocr
from app.model import NotFound, need_write, rewords

log = logging.getLogger("iodocs.files")
PART_BYTES = 4 * 1024 * 1024
MAX_FILES = 100           # of one document
THUMB_SIDE = 640
MAX_PIXELS = 80_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
INLINE = {"application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp", "image/heic", "image/avif", "text/plain"}


def _name(v: str | None, mime: str) -> str:
    s = re.sub(r"[\x00-\x1f/\\]+", " ", str(v or "")).strip()[:255]
    return s or "scan" + (mimetypes.guess_extension(mime) or "")


def _mime(name: str, given: str | None, raw: bytes) -> str:
    if raw[:4] == b"%PDF":
        return "application/pdf"
    g = (given or "").split(";")[0].strip().lower()
    if g and g != "application/octet-stream" and re.fullmatch(r"[a-z0-9.+-]+/[a-z0-9.+-]+", g):
        return g
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def _small(im: Image.Image) -> bytes:
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        back = Image.new("RGB", im.size, (255, 255, 255))
        back.paste(im, mask=im.split()[-1])
        im = back
    else:
        im = im.convert("RGB")
    im.thumbnail((THUMB_SIDE, THUMB_SIDE), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=80, optimize=True)
    return out.getvalue()


def thumb(raw: bytes, mime: str) -> bytes | None:
    """A small JPEG of a picture (turned upright) or of a PDF's first page; None otherwise."""
    try:
        if mime == "application/pdf":
            pages = ocr.pdf_pages(raw, pages=1, dpi=72)
            return _small(pages[0]) if pages else None
        im = Image.open(io.BytesIO(raw))
        if im.width * im.height > MAX_PIXELS:
            return None
        return _small(ImageOps.exif_transpose(im))
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None


def _public(r: dict) -> dict:
    try:
        found = json.loads(r["found"]) if r.get("found") else None
    except ValueError:
        found = None
    return {"id": r["id"], "name": r["name"], "mime": r["mime"], "size": int(r["size"]), "thumb": bool(r.get("has_thumb")),
            "url": f"api/documents/{r['doc_id']}/files/{r['id']}", "added": r["created_at"].isoformat() if r.get("created_at") else None,
            "read": r["read_at"].isoformat() if r.get("read_at") else None, "found": found,
            "hasText": bool(r.get("has_text"))}


_COLS = "id, doc_id, name, mime, size, thumb IS NOT NULL AS has_thumb, created_at, read_at, found, (text IS NOT NULL AND text <> '') AS has_text"


def listed(doc_id: int) -> list[dict]:
    return [_public(r) for r in db.q(f"SELECT {_COLS} FROM doc_files WHERE doc_id = %s ORDER BY position, id", (doc_id,))]


def _cover(doc_id: int) -> None:
    p = db.one("SELECT id FROM doc_files WHERE doc_id = %s AND thumb IS NOT NULL ORDER BY position, id LIMIT 1", (doc_id,))
    db.ex("UPDATE doc_documents SET cover = %s, updated_at = updated_at WHERE id = %s", (p["id"] if p else 0, doc_id))


def add(u: dict, d: dict, raw: bytes, name: str | None, mime: str | None) -> dict:
    need_write(u, d)
    if not raw:
        raise Invalid("The file is empty")
    if len(raw) > config.MAX_FILE_BYTES:
        raise Invalid(f"Files up to {config.MAX_FILE_BYTES // (1024 * 1024)} MB")
    mime = _mime(name or "", mime, raw)
    name = _name(name, mime)
    small = thumb(raw, mime) if mime.startswith("image/") or mime == "application/pdf" else None
    with db.tx():
        n = db.one("SELECT COUNT(*) AS n, COALESCE(MAX(position), -1) AS last FROM doc_files WHERE doc_id = %s", (d["id"],))
        if n["n"] >= MAX_FILES:
            raise Invalid(f"A document holds at most {MAX_FILES} files")
        fid = db.ex("INSERT INTO doc_files (doc_id, name, mime, size, sha256, thumb, position, created_by) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (d["id"], name, mime, len(raw), hashlib.sha256(raw).hexdigest(), small, n["last"] + 1, u.get("id")))
        for i in range(0, len(raw), PART_BYTES):
            db.ex("INSERT INTO doc_file_parts (file_id, n, data) VALUES (%s, %s, %s)", (fid, i // PART_BYTES, raw[i:i + PART_BYTES]))
        _cover(d["id"])
    return one(d["id"], fid)


def one(doc_id: int, fid) -> dict:
    r = db.one(f"SELECT {_COLS} FROM doc_files WHERE id = %s AND doc_id = %s", (int(fid), int(doc_id)))
    if not r:
        raise NotFound("This document has no such file")
    return _public(r)


def content(doc_id: int, fid, small: bool = False) -> tuple[bytes, str, str]:
    """(bytes, type, name) of the file, or of its small picture."""
    if small:
        r = db.one("SELECT thumb, name FROM doc_files WHERE id = %s AND doc_id = %s", (int(fid), int(doc_id)))
        if not r or r["thumb"] is None:
            raise NotFound("This file has no small picture")
        return bytes(r["thumb"]), "image/jpeg", r["name"]
    f = one(doc_id, fid)
    parts = db.q("SELECT data FROM doc_file_parts WHERE file_id = %s ORDER BY n", (f["id"],))
    return b"".join(bytes(p["data"]) for p in parts), f["mime"], f["name"]


def text_of(doc_id: int, fid) -> str:
    r = db.one("SELECT text FROM doc_files WHERE id = %s AND doc_id = %s", (int(fid), int(doc_id)))
    if not r:
        raise NotFound("This document has no such file")
    return r["text"] or ""


def inline(mime: str) -> bool:
    return mime in INLINE


def _json(v):
    return v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else str(v)


def read(u: dict, d: dict, fid, apply: bool = True) -> dict:
    """Read the file (OCR, the passport's zone, the license's barcode), keep its text and facts, and (apply) fill in
    the document where it says nothing yet. {file, found, source, filled, differs, available}"""
    need_write(u, d)
    can = ocr.available()
    raw, mime, _ = content(d["id"], fid)
    if not (mime.startswith("image/") or mime == "application/pdf"):
        raise Invalid("Only pictures and PDFs can be read")
    if not can["ocr"] and mime != "application/pdf" and not can["barcodes"]:
        raise Invalid("Reading scans needs Tesseract on the server (apt install tesseract-ocr)")
    got = ocr.read(raw, mime)
    found = {k: (_json(v) if isinstance(v, (dt.date, dt.datetime)) else v) for k, v in got["found"].items()}
    if got["source"]:
        found["source"] = got["source"]
    db.ex("UPDATE doc_files SET text = %s, found = %s, read_at = CURRENT_TIMESTAMP WHERE id = %s AND doc_id = %s",
          (got["text"], json.dumps(found, ensure_ascii=False, default=_json) if found else None, int(fid), d["id"]))
    rewords(d["id"])
    out = {"found": found, "source": got["source"], "filled": [], "differs": [], "available": can}
    if apply and found:
        from app import model
        out.update(model.apply_found(u, model.get(d["id"]), got["found"]))
    out["file"] = one(d["id"], fid)
    return out


def change(u: dict, d: dict, fid, data: dict) -> dict:
    """{name?, first?: true to put it first (with a picture: the cover)}"""
    need_write(u, d)
    f = one(d["id"], fid)
    sets = {}
    if "name" in data:
        sets["name"] = _name(data.get("name"), f["mime"])
    if data.get("first"):
        low = db.one("SELECT COALESCE(MIN(position), 0) AS p FROM doc_files WHERE doc_id = %s", (d["id"],))["p"]
        sets["position"] = low - 1
    with db.tx():
        if sets:
            db.ex(f"UPDATE doc_files SET {', '.join(k + ' = %s' for k in sets)} WHERE id = %s", [*sets.values(), f["id"]])
        _cover(d["id"])
    return one(d["id"], fid)


def remove(u: dict, d: dict, fid) -> None:
    need_write(u, d)
    f = one(d["id"], fid)
    with db.tx():
        db.ex("DELETE FROM doc_files WHERE id = %s", (f["id"],))
        _cover(d["id"])
    rewords(d["id"])
