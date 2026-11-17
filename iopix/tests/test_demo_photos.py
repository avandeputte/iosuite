"""The demo photos (app/demo.py): drawn pictures with their date and place in Exif and a digiKam sidecar with faces,
keywords, a caption and a rating, in a folder of their own. The file scanner taking them in is test_no_digikam's."""
from PIL import Image

from app import demo


def test_the_demo_photos_are_written(tmp_path):
    n = demo.write_photos(tmp_path)
    jpgs = sorted((tmp_path / demo.FOLDER).rglob("*.jpg"))
    assert n == len(jpgs) == sum(e[2] for e in demo._events())
    first = jpgs[0]
    side = first.with_name(first.name + ".xmp").read_text(encoding="utf-8")
    assert "digiKam:TagsList" in side and "mwg-rs:Regions" in side or "People/" not in side
    ex = Image.open(first).getexif()
    assert ex.get_ifd(0x8769).get(0x9003) and ex.get_ifd(0x8825)
    assert demo.write_photos(tmp_path) == n  # the same files again, not twice as many
    assert len(list((tmp_path / demo.FOLDER).rglob("*.jpg"))) == n
