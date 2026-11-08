"""Settings and viewer state live in the viewer's own database: defaults,
round trips and the read cache."""
from app.data import state


def test_setting_default_and_roundtrip():
    assert state.get_setting("no-such-key", "dflt") == "dflt"
    state.set_setting("probe", "1")
    assert state.get_setting("probe") == "1"
    state.set_setting("probe", "2")
    assert state.get_setting("probe") == "2"


def test_favorites_and_albums_roundtrip():
    # items are (photo id, file hash) pairs so a favorite survives a re-import under a new id
    state.set_favorites([(1, "h1"), (2, "h2")], True)
    assert {1, 2} <= set(state.summary()["favorites"])  # a plain list of photo ids, newest first
    state.set_favorites([(1, "h1")], False)
    assert 1 not in state.summary()["favorites"] and 2 in state.summary()["favorites"]
    aid = state.create_album("tests")
    state.set_album_items(aid, [(1, "h1"), (2, "h2")], True)
    albums = {a["name"]: a for a in state.summary()["albums"]}
    assert "tests" in albums and albums["tests"]["n"] == 2
    state.set_album_items(aid, [(2, "h2")], False)
    assert {a["name"]: a for a in state.summary()["albums"]}["tests"]["n"] == 1
    state.rename_album(aid, "tests2")
    assert "tests2" in {a["name"] for a in state.summary()["albums"]}
    state.delete_album(aid)
    assert "tests2" not in {a["name"] for a in state.summary()["albums"]}
