"""What comes with a thing: its photos, the manual, the receipt, the warranty card, anything else.

The bytes are kept in the database (hom_file_parts, in parts of PART_BYTES), so the suite's database backup (ioBackup)
holds them too and nothing lives beside the app. A picture also gets a small JPEG for the cards (thumb); the first
photo of a thing is the one the cards show (hom_items.photo). A file is served as it came, with its own type, except
for the kinds a page could run (HTML, SVG, XML...), which are sent as a download.
"""
import hashlib
import io
import mimetypes
import re

from PIL import Image, ImageOps, UnidentifiedImageError

from iosuite_shared.errors import Invalid

from app import config, db
from app.model import NotFound, need_write, may_add, Forbidden

KINDS = ("photo", "manual", "receipt", "warranty", "other")
PART_BYTES = 4 * 1024 * 1024
MAX_FILES = 200           # of one thing
THUMB_SIDE = 520
MAX_PIXELS = 80_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
# shown in the browser as they are; anything else is a download
INLINE = {"application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp", "image/heic", "image/avif",
          "text/plain", "video/mp4", "audio/mpeg"}


def _name(v: str | None, mime: str) -> str:
    s = re.sub(r"[\x00-\x1f/\\]+", " ", str(v or "")).strip()[:255]
    return s or "file" + (mimetypes.guess_extension(mime) or "")


def _mime(name: str, given: str | None, raw: bytes) -> str:
    if raw[:4] == b"%PDF":
        return "application/pdf"
    g = (given or "").split(";")[0].strip().lower()
    if g and g != "application/octet-stream" and re.fullmatch(r"[a-z0-9.+-]+/[a-z0-9.+-]+", g):
        return g
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def thumb(raw: bytes) -> bytes | None:
    """A small JPEG of a picture (turned upright); None when the bytes are not a picture this server reads."""
    try:
        im = Image.open(io.BytesIO(raw))
        if im.width * im.height > MAX_PIXELS:
            return None
        im = ImageOps.exif_transpose(im)
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
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None


def _public(r: dict) -> dict:
    return {"id": r["id"], "kind": r["kind"], "name": r["name"], "mime": r["mime"], "size": int(r["size"]),
            "thumb": bool(r.get("has_thumb")), "url": f"api/items/{r['item_id']}/files/{r['id']}",
            "added": r["created_at"].isoformat() if r.get("created_at") else None}


def listed(item_id: int) -> list[dict]:
    rows = db.q("SELECT id, item_id, kind, name, mime, size, thumb IS NOT NULL AS has_thumb, created_at FROM hom_files "
                "WHERE item_id = %s ORDER BY FIELD(kind, 'photo', 'manual', 'receipt', 'warranty', 'other'), position, id", (item_id,))
    return [_public(r) for r in rows]


def _cover(item_id: int) -> None:
    """The picture the cards show: the first photo (one with a small picture)."""
    p = db.one("SELECT id FROM hom_files WHERE item_id = %s AND kind = 'photo' AND thumb IS NOT NULL ORDER BY position, id LIMIT 1", (item_id,))
    db.ex("UPDATE hom_items SET photo = %s, updated_at = updated_at WHERE id = %s", (p["id"] if p else 0, item_id))


def may_attach(u: dict, it: dict) -> None:
    """Files: the ones who may change the thing, and any member (a receipt, a photo of the label)."""
    if not may_add(u):
        raise Forbidden("A viewer only looks: a member or more adds files")


def add(u: dict, it: dict, raw: bytes, name: str | None, mime: str | None, kind: str | None) -> dict:
    """Keep a file with the thing; kind left out: a photo for a picture, a manual for a PDF, other otherwise."""
    may_attach(u, it)
    if not raw:
        raise Invalid("The file is empty")
    if len(raw) > config.MAX_FILE_BYTES:
        raise Invalid(f"Files up to {config.MAX_FILE_BYTES // (1024 * 1024)} MB")
    mime = _mime(name or "", mime, raw)
    name = _name(name, mime)
    small = thumb(raw) if mime.startswith("image/") or kind == "photo" else None
    if kind not in KINDS:
        kind = "photo" if small else "manual" if mime == "application/pdf" else "other"
    if kind == "photo" and not small:
        raise Invalid("That is not a picture this server can read (JPEG, PNG, WebP or GIF): add it as another kind of file")
    with db.tx():
        n = db.one("SELECT COUNT(*) AS n, COALESCE(MAX(position), -1) AS last FROM hom_files WHERE item_id = %s", (it["id"],))
        if n["n"] >= MAX_FILES:
            raise Invalid(f"A thing holds at most {MAX_FILES} files")
        fid = db.ex("INSERT INTO hom_files (item_id, kind, name, mime, size, sha256, thumb, position, created_by) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (it["id"], kind, name, mime, len(raw), hashlib.sha256(raw).hexdigest(), small, n["last"] + 1, u.get("id")))
        for i in range(0, len(raw), PART_BYTES):
            db.ex("INSERT INTO hom_file_parts (file_id, n, data) VALUES (%s, %s, %s)", (fid, i // PART_BYTES, raw[i:i + PART_BYTES]))
        _cover(it["id"])
    return one(it["id"], fid)


def one(item_id: int, fid) -> dict:
    r = db.one("SELECT id, item_id, kind, name, mime, size, thumb IS NOT NULL AS has_thumb, created_at FROM hom_files "
               "WHERE id = %s AND item_id = %s", (int(fid), int(item_id)))
    if not r:
        raise NotFound("This thing has no such file")
    return _public(r)


def content(item_id: int, fid, small: bool = False) -> tuple[bytes, str, str]:
    """(bytes, type, name) of the file, or of its small picture."""
    if small:
        r = db.one("SELECT thumb, name FROM hom_files WHERE id = %s AND item_id = %s", (int(fid), int(item_id)))
        if not r or r["thumb"] is None:
            raise NotFound("This file has no small picture")
        return bytes(r["thumb"]), "image/jpeg", r["name"]
    f = one(item_id, fid)
    parts = db.q("SELECT data FROM hom_file_parts WHERE file_id = %s ORDER BY n", (f["id"],))
    return b"".join(bytes(p["data"]) for p in parts), f["mime"], f["name"]


def inline(mime: str) -> bool:
    return mime in INLINE


def change(u: dict, it: dict, fid, data: dict) -> dict:
    """{name?, kind?, first?: true to make it the first of its kind (a photo: the one the cards show)}"""
    may_attach(u, it)
    f = one(it["id"], fid)
    sets = {}
    if "name" in data:
        sets["name"] = _name(data.get("name"), f["mime"])
    if "kind" in data:
        k = str(data.get("kind") or "")
        if k not in KINDS:
            raise Invalid(f"kind: one of {', '.join(KINDS)}")
        if k == "photo" and not f["thumb"]:
            raise Invalid("Only a picture can be a photo")
        sets["kind"] = k
    if data.get("first"):
        low = db.one("SELECT COALESCE(MIN(position), 0) AS p FROM hom_files WHERE item_id = %s", (it["id"],))["p"]
        sets["position"] = low - 1
    with db.tx():
        if sets:
            db.ex(f"UPDATE hom_files SET {', '.join(k + ' = %s' for k in sets)} WHERE id = %s", [*sets.values(), f["id"]])
        _cover(it["id"])
    return one(it["id"], fid)


def remove(u: dict, it: dict, fid) -> None:
    """Members remove what they added; editors and the one who added the thing remove any of its files."""
    f = db.one("SELECT id, created_by FROM hom_files WHERE id = %s AND item_id = %s", (int(fid), it["id"]))
    if not f:
        raise NotFound("This thing has no such file")
    if f["created_by"] != u.get("id"):
        need_write(u, it)
    with db.tx():
        db.ex("DELETE FROM hom_files WHERE id = %s", (f["id"],))
        _cover(it["id"])
