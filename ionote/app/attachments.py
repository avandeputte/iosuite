"""Files attached to a note beside its picture: PDFs, more pictures, documents (nts_attachments).

The bytes are kept as sent, in the database like the pictures. What search needs is pulled out as the file arrives:
a PDF's text (pypdf), a text file's text; a picture gets a small JPEG for the lists and, when RapidOCR is installed,
its text read in the background (app/ocr.py). Each change gives the note a new rev, and the note lists its
attachments (notes.with_attachments), so the devices learn of them with the note itself and fetch the bytes when
they are wanted.
"""
import hashlib
import io
import logging
import mimetypes
import time

from PIL import Image

from app import config, db, images
from app.notes import NotFound, check_uuid, display_title, get_note, log_change, new_uuid, owner

log = logging.getLogger("app.attachments")
MAX_PER_NOTE = 50
MAX_TEXT = 2 << 20      # the text kept from one file (a long PDF's)
MAX_PDF_PAGES = 500
TEXT_TYPES = ("text/plain", "text/markdown", "text/csv", "application/json", "text/x-python", "application/xml", "text/xml")
TEXT_EXT = (".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".log", ".xml", ".yaml", ".yml", ".py", ".js", ".sh", ".swift")
# shown in the browser instead of downloaded: never HTML or SVG (a page of someone's could run as this site)
INLINE = ("image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf", "text/plain")


class BadFile(ValueError):
    pass


def _clean_name(name: str) -> str:
    name = "".join(c for c in str(name or "") if c >= " " and c not in '\\/:*?"<>|').strip().strip(".")
    return name[:200] or "file"


def _kind(data: bytes, name: str, hint: str):
    """(mime, Image or None) for these bytes."""
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > images.MAX_PIXELS:
            raise BadFile(f"Pictures up to {images.MAX_PIXELS // 1_000_000} megapixels")
        img.load()
        return images.KINDS.get(img.format or "", "image/heic" if (img.format or "").upper() in ("HEIF", "HEIC") else "image/" + (img.format or "x-unknown").lower()), img
    except BadFile:
        raise
    except Exception:
        pass
    if data[:5] == b"%PDF-":
        return "application/pdf", None
    guess = mimetypes.guess_type(name)[0]
    hint = (hint or "").split(";")[0].strip().lower()
    if hint in ("text/html", "image/svg+xml") or guess in ("text/html", "image/svg+xml"):
        return "application/octet-stream", None  # kept, but only ever downloaded
    if hint and hint not in ("application/octet-stream", "") and "/" in hint:
        return hint[:128], None
    return (guess or "application/octet-stream")[:128], None


def _pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(data))
        out, size = [], 0
        for i, page in enumerate(r.pages):
            if i >= MAX_PDF_PAGES or size > MAX_TEXT:
                break
            t = page.extract_text() or ""
            out.append(t)
            size += len(t)
        return "\n".join(out).strip()[:MAX_TEXT]
    except Exception as e:  # a damaged or encrypted PDF: kept, without its text
        log.info("no text from a PDF: %s", e)
        return ""


def _text_of(data: bytes, mime: str, name: str) -> str:
    if mime == "application/pdf":
        return _pdf_text(data)
    if mime.startswith("text/") or mime in TEXT_TYPES or name.lower().endswith(TEXT_EXT):
        return data[:MAX_TEXT].decode("utf-8", "replace").replace("\x00", "")
    return ""


def put(note_uid: str, data: bytes, name: str, user: str, mime_hint: str = "", att_uid: str = None, text: str = None) -> dict:
    """Attach a file to a note (which must exist and not be in the trash) and return the note. att_uid: the id a device
    chose (the same file sent again is a no-op); text: what a device read from it itself (Vision), else the server reads it."""
    note_uid = check_uuid(note_uid)
    if not data:
        raise BadFile("The file is empty")
    if len(data) > config.MAX_IMAGE_MB << 20:
        raise BadFile(f"Files up to {config.MAX_IMAGE_MB} MB")
    name = _clean_name(name)
    att_uid = check_uuid(att_uid) if att_uid else new_uuid()
    sha = hashlib.sha256(data).hexdigest()
    mime, img = _kind(data, name, mime_hint)
    thumb = w = h = None
    if img is not None:
        w, h = img.size
        thumb = images._thumb(img)
    found = (text or "").strip()[:MAX_TEXT] if text is not None else _text_of(data, mime, name)
    with db.tx() as con:
        n = get_note(note_uid, con)
        if not n or n["deleted"]:
            raise NotFound("No such note")
        r = con.execute("SELECT note_uuid, user_id, sha FROM nts_attachments WHERE uuid = ?", (att_uid,)).fetchone()
        if r and (r["user_id"] != owner() or r["note_uuid"] != note_uid):
            raise NotFound("No such attachment")  # another note's or account's id
        if r and r["sha"] == sha:
            return n  # a device sending it again
        if not r and len(n["attachments"]) >= MAX_PER_NOTE:
            raise BadFile(f"A note holds up to {MAX_PER_NOTE} files")
        con.execute("INSERT OR REPLACE INTO nts_attachments (uuid, note_uuid, user_id, name, mime, size_bytes, sha, width, height, data, thumb, text, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (att_uid, note_uid, owner(), name, mime, len(data), sha, w, h, data, thumb, found, time.time()))
        con.execute("UPDATE nts_notes SET rev = ?, changed_by = ? WHERE uuid = ?", (db.next_rev(con), user, note_uid))
        log_change(con, user, "attach", "note", note_uid, f"{display_title(n)}: {name} ({len(data) // 1024} KB)")
        out = get_note(note_uid, con)
    out["attachmentQueued"] = None
    if img is not None and text is None:
        from app import ocr
        out["attachmentQueued"] = ocr.enqueue_attachment(att_uid)
    return out


def rename(note_uid: str, att_uid: str, name: str, user: str) -> dict:
    note_uid, att_uid = check_uuid(note_uid), check_uuid(att_uid)
    with db.tx() as con:
        if not con.execute("SELECT 1 FROM nts_attachments WHERE uuid = ? AND note_uuid = ? AND user_id = ?", (att_uid, note_uid, owner())).fetchone():
            raise NotFound("No such attachment")
        con.execute("UPDATE nts_attachments SET name = ? WHERE uuid = ?", (_clean_name(name), att_uid))
        con.execute("UPDATE nts_notes SET rev = ?, changed_by = ? WHERE uuid = ?", (db.next_rev(con), user, note_uid))
        return get_note(note_uid, con)


def remove(note_uid: str, att_uid: str, user: str) -> dict:
    note_uid, att_uid = check_uuid(note_uid), check_uuid(att_uid)
    with db.tx() as con:
        n = get_note(note_uid, con)
        r = con.execute("SELECT name FROM nts_attachments WHERE uuid = ? AND note_uuid = ? AND user_id = ?", (att_uid, note_uid, owner())).fetchone()
        if not n or not r:
            raise NotFound("No such attachment")
        con.execute("DELETE FROM nts_attachments WHERE uuid = ?", (att_uid,))
        con.execute("UPDATE nts_notes SET rev = ?, changed_by = ? WHERE uuid = ?", (db.next_rev(con), user, note_uid))
        log_change(con, user, "detach", "note", note_uid, f"{display_title(n)}: {r['name']}")
        return get_note(note_uid, con)


def get(note_uid: str, att_uid: str, thumb: bool = False):
    """(bytes, mime, sha, name) of this account's attachment, or None."""
    with db.connect() as con:
        r = con.execute(f"SELECT {'thumb' if thumb else 'data'}, mime, sha, name FROM nts_attachments WHERE uuid = ? AND note_uuid = ? AND user_id = ?",
                        (check_uuid(att_uid), check_uuid(note_uid), owner())).fetchone()
    if not r or r[0] is None:
        return None
    return bytes(r[0]), ("image/jpeg" if thumb else r[1]), r[2], r[3]


def text(note_uid: str, att_uid: str):
    with db.connect() as con:
        r = con.execute("SELECT text FROM nts_attachments WHERE uuid = ? AND note_uuid = ? AND user_id = ?",
                        (check_uuid(att_uid), check_uuid(note_uid), owner())).fetchone()
    return r[0] if r else None


def raw_for_ocr(att_uid: str):
    """(bytes, sha) for the OCR thread, whoever owns it."""
    with db.connect() as con:
        r = con.execute("SELECT data, sha FROM nts_attachments WHERE uuid = ?", (att_uid,)).fetchone()
    return (bytes(r[0]), r[1]) if r else None


def set_text(att_uid: str, found: str, sha: str):
    """Text the OCR thread read from a picture attachment (the one with this sha); the note gets a new rev."""
    with db.tx() as con:
        r = con.execute("SELECT note_uuid FROM nts_attachments WHERE uuid = ? AND sha = ? AND (text = '' OR text IS NULL)", (att_uid, sha)).fetchone()
        if r:
            con.execute("UPDATE nts_attachments SET text = ? WHERE uuid = ?", (found[:MAX_TEXT], att_uid))
            con.execute("UPDATE nts_notes SET rev = ? WHERE uuid = ?", (db.next_rev(con), r[0]))


def stats() -> dict:
    with db.connect() as con:
        n, size = con.execute("SELECT count(*), coalesce(sum(size_bytes), 0) FROM nts_attachments").fetchone()
    return {"files": int(n), "bytes": int(size)}
