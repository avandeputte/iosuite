"""What the code review of 10 November 2026 found in ioPix: the pictures made on request come in a fixed set of
shapes and sizes and their cache folders are pruned, a video frame is asked for at a real time, and the routes and
the MCP tool that set up sign-in at the proxy for one app's admins are gone (a suite admin does it, in Settings).
The database set-up endpoints, for the local network only, are in test_review_2026_11.py."""
import os
import time

import pytest
from fastapi import HTTPException

from app import config, thumbs
from app.routes import images, settings

PHOTO = {"id": 7, "path": "", "video": 0, "duration": None, "w": 4000, "h": 3000, "hash": "abc", "size": 10, "modified": "2026-01-01", "focus": None}


def test_a_fitted_thumbnail_comes_in_a_fixed_set_of_shapes(monkeypatch):
    asked = []
    monkeypatch.setattr(images, "photo_row", lambda pid, cols=None: dict(PHOTO))
    monkeypatch.setattr(thumbs, "make_fit", lambda row, aspect: asked.append(aspect) or __file__)
    for fit in ("square", "1000x999", "999x1000", "16x9", "1601x900", "3x2", "7x5", "5x1", "1x5"):
        images.thumb(7, fit=fit)
    assert asked == [1.0, 1.0, 1.0, 16 / 9, 16 / 9, 3 / 2, 7 / 5, 3.0, 1 / 3]
    assert set(asked) <= set(thumbs.FIT_ASPECTS)
    with pytest.raises(HTTPException):
        images.thumb(7, fit="6x1")
    # every aspect the route lets through lands on one of the thirteen
    assert {thumbs.nearest_aspect(w / 1000) for w in range(200, 5001)} == set(thumbs.FIT_ASPECTS)


def test_a_small_thumbnail_comes_in_a_fixed_set_of_heights(monkeypatch):
    asked = []
    monkeypatch.setattr(images, "photo_row", lambda pid, cols=None: dict(PHOTO))
    monkeypatch.setattr(thumbs, "make_small", lambda row, height: asked.append(height) or __file__)
    for h in (1, 60, 61, 120, 121, 160, 239, 240, 100000):
        images.thumb(7, h=h)
    assert asked == [60, 60, 80, 120, 160, 160, 240, 240, 240]
    assert {thumbs.at_least(h, thumbs.SMALL_HEIGHTS) for h in range(-5, 2000)} == set(thumbs.SMALL_HEIGHTS)


def test_a_video_frame_is_asked_for_at_a_whole_second_inside_the_video(monkeypatch, tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")
    runs = []

    def fake_frame(src, dst, height, duration, at=None):
        runs.append((at, height))
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"jpeg")
        return True
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(images, "photo_row", lambda pid, cols=None: dict(PHOTO, video=1, duration=12.4, path=str(video)))
    monkeypatch.setattr(thumbs, "video_frame", fake_frame)
    for t, h in ((0.31, 120), (0.72, 100), (1.0, 120), (0.0, 120), (11.9, 121), (500.0, 200), (1e12, 240), (-3.0, 120)):
        images.video_frame_at(7, t=t, h=h)
    assert runs == [(1, 120), (0, 120), (12, 240)], "one ffmpeg run and one file per second and height"
    assert len(list((tmp_path / "cache" / "vf").rglob("*.jpg"))) == 3
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(HTTPException) as e:
            images.video_frame_at(7, t=bad)
        assert e.value.status_code == 400
    assert len(runs) == 3


def test_the_cut_down_thumbnails_are_pruned_past_their_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(config, "VARIANT_CACHE_MAX_MB", 1)
    monkeypatch.setattr(config, "PREVIEW_CACHE_MAX_MB", 1)
    now = time.time()
    for n, kind in enumerate(("c", "s", "vf", "c", "s", "vf", "p", "t")):
        f = tmp_path / kind / "07" / f"7-abc-{n}.jpg"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x" * 300_000)
        os.utime(f, (now - 1000 + n, now - 1000 + n))
    thumbs.prune_variants()
    left = sorted(f.name for kind in ("c", "s", "vf") for f in (tmp_path / kind).rglob("*.jpg"))
    assert left == ["7-abc-3.jpg", "7-abc-4.jpg", "7-abc-5.jpg"], "the oldest go first, across the three folders"
    assert (tmp_path / "p" / "07" / "7-abc-6.jpg").exists() and (tmp_path / "t" / "07" / "7-abc-7.jpg").exists()
    # a changed picture drops what was cut from the old one, the video frames too
    thumbs.forget(7)
    assert not [f for kind in ("c", "s", "vf", "p", "t") for f in (tmp_path / kind).rglob("*.jpg")]


def test_the_caches_are_pruned_again_while_the_server_runs(monkeypatch):
    import threading
    calls = []
    stop = threading.Event()

    def previews():
        calls.append("p")
        raise OSError("the share went away")  # one failing pass does not end the loop

    def variants():
        calls.append("v")
        if len(calls) >= 4:
            stop.set()
    monkeypatch.setattr(thumbs, "prune_previews", previews)
    monkeypatch.setattr(thumbs, "prune_variants", variants)
    monkeypatch.setattr(thumbs, "PRUNE_EVERY_S", 0.01)
    thumbs.keep_pruned(stop)
    assert calls == ["p", "v", "p", "v"]


def test_sign_in_at_the_proxy_is_not_set_up_per_app():
    paths = {r.path for r in settings.router.routes}
    assert "/api/settings/proxy" not in paths
    from app.mcp import files
    assert not hasattr(files, "proxy_signin")
