"""The text on a photo of a recipe (a page of a cookbook, a handwritten card that is neat enough, a screenshot), read
by Tesseract on this server: the picture goes nowhere else. Tesseract is a program of its own (`tesseract`, with a
data file per language); where it is not installed, reading a photo is simply not offered.

OCR_LANGUAGES picks the languages to read (eng+nld+fra); left out, every language installed is tried.
"""
import io
import shutil
import subprocess

from PIL import Image, ImageOps, UnidentifiedImageError

from iosuite_shared.errors import Invalid

from app import config

TIMEOUT = 90     # seconds for one photo
SIDE = 2600      # the longest side handed to Tesseract: enough for a page, quick enough
_langs: list[str] | None = None


def program() -> str | None:
    return shutil.which("tesseract")


def languages() -> list[str]:
    """The languages Tesseract can read here (their codes: eng, nld, fra...), [] when it is not installed."""
    global _langs
    if _langs is None:
        exe = program()
        if not exe:
            return []
        try:
            out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=15).stdout
            _langs = sorted(x.strip() for x in out.splitlines()[1:] if x.strip() and x.strip() not in ("osd", "equ"))
        except (OSError, subprocess.SubprocessError):
            _langs = []
    return _langs


def available() -> bool:
    return bool(program() and languages())


def _wanted() -> str:
    have = languages()
    asked = [x for x in config.OCR_LANGUAGES.replace(",", "+").split("+") if x.strip() in have]
    return "+".join(asked or have[:6])


def read(raw: bytes) -> str:
    """The text on the picture. Invalid when it is not a picture, when nothing can be read, or without Tesseract."""
    if not available():
        raise Invalid("This server cannot read photos: Tesseract is not installed on it")
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as e:
        raise Invalid("That is not a picture this server can read (JPEG, PNG, WebP or GIF)") from e
    im = ImageOps.exif_transpose(im).convert("L")
    if max(im.size) > SIDE:
        im.thumbnail((SIDE, SIDE), Image.LANCZOS)
    elif max(im.size) < 1400:  # small print reads better enlarged
        f = 1400 / max(im.size)
        im = im.resize((round(im.width * f), round(im.height * f)), Image.LANCZOS)
    im = ImageOps.autocontrast(im)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    try:
        p = subprocess.run([program(), "stdin", "stdout", "-l", _wanted(), "--psm", "3"], input=buf.getvalue(), capture_output=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired as e:
        raise Invalid("Reading that photo took too long") from e
    except OSError as e:
        raise Invalid("Tesseract could not be started on this server") from e
    text = p.stdout.decode("utf-8", errors="replace").replace("\x0c", "").strip()
    if p.returncode != 0 or not text:
        raise Invalid("No text could be read on that photo")
    return text
