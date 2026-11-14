"""One rule for a photo's sidecar names (paths.sidecars, paths.sidecar_beside): which belong to it, and where each
goes when the photo is moved, trashed or put back."""
from app.photos import paths


def test_which_sidecars_belong_to_a_photo(tmp_path):
    jpg = tmp_path / "beach.jpg"
    jpg.write_bytes(b"x")
    assert paths.sidecars(str(jpg)) == []
    (tmp_path / "beach.jpg.xmp").write_text("a")
    (tmp_path / "beach.xmp").write_text("b")
    assert paths.sidecars(str(jpg)) == [str(jpg) + ".xmp", str(tmp_path / "beach.xmp")]
    (tmp_path / "beach.cr2").write_bytes(b"raw")  # beach.xmp is now the raw's as much as the jpg's: not this one's alone
    assert paths.sidecars(str(jpg)) == [str(jpg) + ".xmp"]


def test_a_sidecar_keeps_its_naming_scheme_beside_the_new_name():
    assert paths.sidecar_beside("/a/beach.jpg.xmp", "/a/beach.jpg", "/t/beach (2).jpg") == "/t/beach (2).jpg.xmp"
    assert paths.sidecar_beside("/a/beach.xmp", "/a/beach.jpg", "/t/beach (2).jpg") == "/t/beach (2).xmp"
    assert paths.sidecar_beside("/t/my.xmp", "/t/my.photo.jpg", "/a/my.photo.jpg") == "/a/my.photo.xmp"  # an older trash name
