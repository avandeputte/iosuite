"""A note's picture, kept in the database as a BLOB (note_images), with a small JPEG for lists.

The bytes are stored as sent (PNG from a screenshot, JPEG from a phone, HEIC is converted to JPEG so every
browser can show it). imageSHA on the note changes whenever the picture does, which is how a device knows to
fetch it again.
"""
import hashlib
import io
import time

from PIL import Image, ImageOps

from app import config, db
from app.notes import check_uuid, get_note, log_change, display_title

try:
    import pillow_heif  # optional: HEIC from iPhones
    pillow_heif.register_heif_opener()
except ImportError:  # pragma: no cover
    pillow_heif = None

KINDS = {"PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif", "WEBP": "image/webp", "TIFF": "image/tiff", "BMP": "image/bmp"}


MAX_PIXELS = 100_000_000  # a long scrolling screenshot fits; ~400 MB once unpacked
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class BadImage(ValueError):
    pass


def _thumb(img: Image.Image) -> bytes:
    t = ImageOps.exif_transpose(img)
    t.thumbnail((config.THUMB_SIZE, config.THUMB_SIZE))
    if t.mode not in ("RGB", "L"):
        bg = Image.new("RGB", t.size, (255, 255, 255))
        t = t.convert("RGBA")
        bg.paste(t, mask=t.split()[-1])
        t = bg
    out = io.BytesIO()
    t.save(out, "JPEG", quality=config.THUMB_QUALITY, optimize=True)
    return out.getvalue()


def prepare(data: bytes):
    """(bytes to store, mime, width, height, thumbnail) for an uploaded picture; BadImage when it is not one."""
    if not data:
        raise BadImage("The image is empty")
    if len(data) > config.MAX_IMAGE_MB << 20:
        raise BadImage(f"Images up to {config.MAX_IMAGE_MB} MB")
    try:
        img = Image.open(io.BytesIO(data))  # reads the header only
    except Exception:
        raise BadImage("That is not an image ionotes can read")
    if img.width * img.height > MAX_PIXELS:  # a small file can unpack to gigabytes (a decompression bomb)
        raise BadImage(f"Images up to {MAX_PIXELS // 1_000_000} megapixels")
    try:
        img.load()
    except Exception:
        raise BadImage("That is not an image ionotes can read")
    fmt = img.format or ""
    if fmt not in KINDS:  # HEIC and the like: stored as JPEG
        rgb = ImageOps.exif_transpose(img).convert("RGB")
        out = io.BytesIO()
        rgb.save(out, "JPEG", quality=90)
        data, mime = out.getvalue(), "image/jpeg"
    else:
        mime = KINDS[fmt]
    w, h = img.size
    return data, mime, w, h, _thumb(img)


def put(uid: str, data: bytes, user: str) -> dict:
    """Store the picture of a note (which must exist) and return the note."""
    uid = check_uuid(uid)
    blob, mime, w, h, thumb = prepare(data)
    sha = hashlib.sha256(blob).hexdigest()
    with db.tx() as con:
        n = get_note(uid, con)
        if not n or n["deleted"]:
            raise KeyError(uid)
        if sha == n["imageSHA"]:  # the same picture again (a device retrying): nothing changed
            return n
        con.execute("INSERT OR REPLACE INTO note_images (uuid, mime, data, thumb, width, height, bytes, sha, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (uid, mime, blob, thumb, w, h, len(blob), sha, time.time()))
        if n["source"] == "web":
            # a new picture on a note made in the web app: the text read from the old one goes, so the server reads
            # the new one (routes/notes.py _store), and the note counts as edited now. A device sends the text of
            # its picture and the edit time itself (its clock decides conflicts, so the server's is left out).
            con.execute("UPDATE notes SET has_image = 1, image_sha = ?, ocr_text = '', updated_at = ?, rev = ?, changed_by = ? WHERE uuid = ?",
                        (sha, max(n["updatedAt"], time.time()), db.next_rev(con), user, uid))
        else:
            con.execute("UPDATE notes SET has_image = 1, image_sha = ?, rev = ?, changed_by = ? WHERE uuid = ?", (sha, db.next_rev(con), user, uid))
        log_change(con, user, "image", "note", uid, f"{display_title(n)} ({w}×{h}, {len(blob) // 1024} KB)")
        return get_note(uid, con)


def remove(uid: str, user: str) -> dict:
    uid = check_uuid(uid)
    with db.tx() as con:
        n = get_note(uid, con)
        if not n:
            raise KeyError(uid)
        con.execute("DELETE FROM note_images WHERE uuid = ?", (uid,))
        # the text read from the picture goes with it (it would still be found by searches otherwise)
        con.execute("UPDATE notes SET has_image = 0, image_sha = NULL, ocr_text = '', updated_at = ?, rev = ?, changed_by = ? WHERE uuid = ?",
                    (max(n["updatedAt"], time.time()), db.next_rev(con), user, uid))
        log_change(con, user, "image-removed", "note", uid, display_title(n))
        return get_note(uid, con)


def get(uid: str, thumb: bool = False):
    """(bytes, mime, sha) or None."""
    with db.connect() as con:
        r = con.execute(f"SELECT {'thumb' if thumb else 'data'}, mime, sha FROM note_images WHERE uuid = ?", (check_uuid(uid),)).fetchone()
    if not r or r[0] is None:
        return None
    return bytes(r[0]), ("image/jpeg" if thumb else r[1]), r[2]


def info(uid: str):
    with db.connect() as con:
        r = con.execute("SELECT mime, width, height, bytes, sha FROM note_images WHERE uuid = ?", (check_uuid(uid),)).fetchone()
    return {"mime": r[0], "width": r[1], "height": r[2], "bytes": r[3], "sha": r[4]} if r else None


def stats() -> dict:
    with db.connect() as con:
        n, size = con.execute("SELECT count(*), coalesce(sum(bytes), 0) FROM note_images").fetchone()
    return {"images": int(n), "bytes": int(size)}
