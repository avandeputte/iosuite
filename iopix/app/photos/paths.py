"""Where a photo's companions live: its sidecar (digiKam's two naming schemes) and the viewer's backup copies of
the sidecar and of the file. A leaf module: edits, scanner, metaedit, versions, importer and the rest import it
without pulling the whole editing machinery (and its imports) in."""
import os
from pathlib import Path

from app import config
from app.data import state

BACKUP_DIR = config.DATA_DIR / "sidecar-backups"
FILE_BACKUP_DIR = config.DATA_DIR / "file-backups"  # originals of image files before their metadata is rewritten


def rel(path: str) -> Path:
    """Where a library file sits below PHOTOS_ROOT (or below the filesystem root, for
    files outside it): the layout both backup folders mirror."""
    try:
        return Path(path).resolve().relative_to(config.PHOTOS_ROOT)
    except ValueError:
        return Path(*Path(path).resolve().parts[1:])


def backup_path(photo_path: str) -> Path:
    return BACKUP_DIR / (str(rel(photo_path)) + ".xmp")


def file_backup_path(photo_path: str) -> Path:
    return FILE_BACKUP_DIR / rel(photo_path)


def sidecar_candidates(photo_path: str) -> tuple:
    """(photo.jpg.xmp, photo.xmp): digiKam's default sidecar name, and its "compatible file name" option."""
    return photo_path + ".xmp", os.path.splitext(photo_path)[0] + ".xmp"


def compat_naming() -> bool:
    """Write new sidecars as photo.xmp (digiKam's "compatible file name" setting): SIDECAR_COMPAT=1 or the setting."""
    if config.sidecar_compat_env():
        return True
    try:
        return state.get_setting("sidecar_compat", "0") == "1"
    except Exception:
        return False


def compat_owner(photo_path: str) -> bool:
    """Whether photo.xmp belongs to this photo alone: not when photo.jpg and photo.cr2 would share it."""
    base, _ext = os.path.splitext(photo_path)
    stem, folder = os.path.basename(base), os.path.dirname(photo_path) or "."
    try:
        for f in os.listdir(folder):
            if f != os.path.basename(photo_path) and os.path.splitext(f)[0] == stem and not f.lower().endswith(".xmp"):
                return False
    except OSError:
        return False
    return True


def sidecars(photo_path: str) -> list:
    """The sidecar files on disk that belong to this photo: photo.jpg.xmp, and photo.xmp when no other file
    (photo.cr2 beside photo.jpg) would share it."""
    a, b = sidecar_candidates(photo_path)
    out = [a] if os.path.isfile(a) else []
    if b != a and os.path.isfile(b) and compat_owner(photo_path):
        out.append(b)
    return out


def sidecar_beside(sidecar, photo, new_photo) -> str:
    """Where a sidecar goes when its photo becomes new_photo (moved, renamed, trashed, put back): photo.jpg.xmp
    becomes new.jpg.xmp, photo.xmp becomes new.xmp."""
    sidecar, photo, new_photo = str(sidecar), str(photo), str(new_photo)
    if sidecar.startswith(photo):
        return new_photo + sidecar[len(photo):]
    return os.path.splitext(new_photo)[0] + ".xmp"


def sidecar_path(photo_path: str) -> str:
    """The sidecar this photo uses: the one that exists (photo.jpg.xmp first, then photo.xmp when it is this
    photo's alone), else the name a new one gets (compatible naming when that setting is on)."""
    a, b = sidecar_candidates(photo_path)
    if os.path.isfile(a):
        return a
    if os.path.isfile(b) and compat_owner(photo_path):
        return b
    return b if compat_naming() else a
