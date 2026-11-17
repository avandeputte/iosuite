"""The demo photos (iopix's module of the iosuite_demo package, the repository's demo/): the real photos unpacked from
their zip into a folder of their own (nothing outside it), and the drawn pictures, with their date and place in Exif
and a digiKam sidecar with faces, keywords, a caption and a rating, when that download is not there. The file scanner
taking them in is test_no_digikam's."""
import zipfile

import pytest
from PIL import Image

from iosuite_shared import demo


@pytest.fixture
def photos():
    with demo.package():
        from iosuite_demo import iopix
        yield iopix


def test_the_drawn_photos_are_written(tmp_path, photos):
    n = photos.write_photos(tmp_path)
    jpgs = sorted((tmp_path / photos.FOLDER).rglob("*.jpg"))
    assert n == len(jpgs) == sum(e[2] for e in photos._events())
    first = jpgs[0]
    side = first.with_name(first.name + ".xmp").read_text(encoding="utf-8")
    assert "digiKam:TagsList" in side and "mwg-rs:Regions" in side or "People/" not in side
    ex = Image.open(first).getexif()
    assert ex.get_ifd(0x8769).get(0x9003) and ex.get_ifd(0x8825)
    assert photos.write_photos(tmp_path) == n  # the same files again, not twice as many
    assert len(list((tmp_path / photos.FOLDER).rglob("*.jpg"))) == n


def test_the_real_photos_are_unpacked_into_their_folder(tmp_path, photos, monkeypatch):
    archive = tmp_path / "demo.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("photos/2024/2024-08-03 Lake house/IMG_1.jpg", b"jpeg")
        z.writestr("photos/2024/2024-08-03 Lake house/IMG_1.jpg.xmp", "<x/>")
        z.writestr("CREDITS.md", "# credits")
        z.writestr("README.txt", "not taken")
    root = tmp_path / "photos"
    assert photos.unpack_photos(archive, root) == 1
    folder = root / photos.FOLDER
    assert sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()) == [
        "2024/2024-08-03 Lake house/IMG_1.jpg", "2024/2024-08-03 Lake house/IMG_1.jpg.xmp", "CREDITS.md"]
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("photos/../../evil.jpg", b"x")
    with pytest.raises(ValueError):
        photos.unpack_photos(archive, root)
    assert not (tmp_path / "evil.jpg").exists()
    monkeypatch.setenv("DEMO_PHOTOS_URL", archive.as_uri())  # a download that is not the release's: no checksum to match
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("photos/2025/Trip/IMG_2.jpg", b"jpeg")
    monkeypatch.setattr("app.config.DATA_DIR", tmp_path)
    assert photos.download_photos(tmp_path / "other") == 1
    monkeypatch.setenv("DEMO_PHOTOS_URL", "")
    assert photos.download_photos(tmp_path / "none") == 0  # no URL: the drawn photos
