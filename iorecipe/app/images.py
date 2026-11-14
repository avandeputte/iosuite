"""A recipe's photo: whatever was uploaded or found on a web page is opened, checked, turned upright and kept as two
JPEGs (the picture the recipe shows and a small one for the cards), so nothing but pixels is ever stored or served."""
import io

from PIL import Image, ImageOps, UnidentifiedImageError

from iosuite_shared.errors import Invalid

MAX_PIXELS = 80_000_000  # a larger picture is refused instead of filling the memory (~320 MB once unpacked)
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
PICTURE_SIDE = 1600
THUMB_SIDE = 520


def _jpeg(im: Image.Image, side: int, quality: int) -> bytes:
    im = im.copy()
    im.thumbnail((side, side), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
    return out.getvalue()


def opened(raw: bytes) -> Image.Image:
    """The picture in these bytes, unpacked. Invalid when it is not one, or larger than MAX_PIXELS: Pillow itself
    refuses only at twice its limit, and a file of a few kilobytes can say it is that large."""
    try:
        im = Image.open(io.BytesIO(raw))
        large = im.width * im.height > MAX_PIXELS
        if not large:
            im.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as e:
        raise Invalid("That is not a picture this server can read (JPEG, PNG, WebP or GIF)") from e
    if large:
        raise Invalid(f"Pictures up to {MAX_PIXELS // 1_000_000} megapixels")
    return im


def prepare(raw: bytes) -> dict:
    """{picture, thumb, width, height} from the bytes of an image (JPEG, PNG, WebP, GIF...). Invalid when it is not one."""
    if not raw:
        raise Invalid("That is not a picture")
    im = ImageOps.exif_transpose(opened(raw))
    if im.mode in ("RGBA", "LA", "P"):  # see-through parts become white
        im = im.convert("RGBA")
        back = Image.new("RGB", im.size, (255, 255, 255))
        back.paste(im, mask=im.split()[-1])
        im = back
    else:
        im = im.convert("RGB")
    picture = _jpeg(im, PICTURE_SIDE, 84)
    w, h = Image.open(io.BytesIO(picture)).size
    return {"picture": picture, "thumb": _jpeg(im, THUMB_SIDE, 80), "width": w, "height": h}
