"""The suite's list of apps (the Shared ioSuite database's ios_apps): ioSuite registers itself and finds the others there."""
from iosuite_shared import suite

from app import apps


def _registered(**kw):
    for key, e in kw.items():
        suite.register(key, **e)
    apps.forget_registry()


def test_iosuite_registers_itself(client):
    client.get("/api/apps")
    me = suite.get("iosuite")
    from app import __version__
    assert me["name"] == "ioSuite" and me["version"] == __version__ and me["description"] == "Start page"


def test_only_registered_apps_have_a_tile(client):
    suite.forget("iocalendar")
    _registered(iopix={"name": "ioPix", "url": "https://photo.example.com", "version": "2.1.0"}, ionotes={"name": "ioNotes"})
    by = {t["key"]: t for t in client.get("/api/apps", headers={"host": "home.lan:8630"}).json()["items"]}
    assert by["iopix"]["url"] == "https://photo.example.com" and by["iopix"]["version"] == "2.1.0"
    assert "iocalendar" not in by and "ionotes" not in by  # not registered, or registered without an address


def test_an_app_the_page_does_not_know_gets_a_tile(client):
    _registered(iorecipes={"name": "ioRecipes", "url": "https://recipes.example.com", "description": "Recipes",
                           "color": "#aa5500"},
                ioblank={"name": "ioBlank"})  # no address: no tile
    items = client.get("/api/apps").json()["items"]
    assert [t["key"] for t in items][-1] == "iorecipes" and "ioblank" not in [t["key"] for t in items]
    t = items[-1]
    assert t["url"] == "https://recipes.example.com" and t["tagline"] == "Recipes" and t["icon"] == "https://recipes.example.com/static/icons/mark.svg"
    assert "iosuite" not in [t["key"] for t in items]
    r = client.put("/api/me/layout", json={"hidden": ["iorecipes"]})  # a person hides it for themselves
    assert r.status_code == 200 and r.json()["hidden"] == ["iorecipes"]


def test_a_known_app_tile_is_what_it_registered(client):
    """No copy of the apps' icons or colours here: the tile is the app's own row, its icon served by the app."""
    _registered(iopix={"name": "ioPix", "url": "http://nas.lan:8600", "description": "Photos", "color": "#3b4a8c"})
    t = next(t for t in client.get("/api/apps").json()["items"] if t["key"] == "iopix")
    assert (t["name"], t["tagline"], t["color"], t["icon"]) == ("ioPix", "Photos", "#3b4a8c", "http://nas.lan:8600/static/icons/mark.svg")
