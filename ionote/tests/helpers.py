import io

from PIL import Image


def png(w=320, h=200, color=(28, 90, 94)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


NID = "0F8C6F1E-1D2B-4F3A-9C1A-1234567890AB"
NID2 = "1F8C6F1E-1D2B-4F3A-9C1A-1234567890AB"
