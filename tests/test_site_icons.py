"""A bookmark's icon by default: the site's own, fetched by the server (app/siteicons.py). The sites are mocked."""
import pytest

from app import config, siteicons

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
ICO = b"\x00\x00\x01\x00\x01\x00" + b"\x10" * 40
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><rect width="1" height="1"/></svg>'


@pytest.fixture()
def web(client, monkeypatch):
    """{address: bytes} the mocked sites answer with (anything else: no answer); web.asked lists what was fetched."""
    class Web(dict):
        asked = []

    w = Web()
    w.asked = []

    def get(url, limit, accept):
        w.asked.append(url)
        if url not in w:
            raise OSError("no answer")
        return w[url], url

    monkeypatch.setattr(siteicons, "_get", get)
    monkeypatch.setattr(config, "SITE_ICONS", True)
    return w


def _links(client):
    return {l["name"]: l for g in client.get("/api/bookmarks").json()["groups"] for l in g["links"]}


def test_a_link_shows_its_sites_icon(client, web):
    web["https://news.example.org/today"] = b"""<html><head><base href="/assets/">
        <link rel="shortcut icon" href="small.ico"><link rel="icon" type="image/png" sizes="96x96" href="big.png">
        <link rel="mask-icon" href="mask.svg"><link rel="stylesheet" href="x.css"></head></html>"""
    web["https://news.example.org/assets/big.png"] = PNG
    web["https://news.example.org/assets/small.ico"] = ICO
    g = client.post("/api/bookmarks/groups", json={"name": "Read"}).json()
    made = client.post(f"/api/bookmarks/groups/{g['id']}/links", json={"name": "News", "href": "https://news.example.org/today"}).json()
    assert made["siteIcon"] == "" and made["iconPending"] is True  # asked for, not there yet
    client.post(f"/api/bookmarks/groups/{g['id']}/links", json={"name": "Sport", "href": "https://news.example.org/sport"})
    siteicons.settle()
    assert web.asked == ["https://news.example.org/today", "https://news.example.org/assets/big.png"]  # the best one, once per site
    l = _links(client)
    assert l["News"]["iconPending"] is False and l["News"]["siteIcon"] == l["Sport"]["siteIcon"] != ""
    r = client.get("/" + l["News"]["siteIcon"])
    assert r.status_code == 200 and r.content == PNG and r.headers["content-type"] == "image/png"
    assert r.headers["x-content-type-options"] == "nosniff" and "immutable" in r.headers["cache-control"]
    tree = client.get("/api/bookmarks/tree").json()
    assert tree["items"][0]["items"][0]["siteIcon"] == l["News"]["siteIcon"]
    siteicons.settle()
    assert len(web.asked) == 2  # nothing is asked again while the answer is fresh


def test_favicon_ico_and_sites_without_an_icon(client, web):
    web["http://nas.lan:5000/favicon.ico"] = ICO            # no page answers; the usual place does
    web["https://plain.example.org/"] = b"<html><head><link rel=icon href='/i.png'></head></html>"
    web["https://plain.example.org/i.png"] = b"<html>not found</html>"   # not an image, whatever it is called
    web["https://plain.example.org/favicon.ico"] = b"<html>not found</html>"
    web["https://evil.example.org/"] = b'<link rel="icon" href="x.svg">'
    web["https://evil.example.org/x.svg"] = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    web["https://inline.example.org/"] = b'<link rel="icon" href="data:image/svg+xml,' + SVG.replace(b'"', b"%22").replace(b"<", b"%3C").replace(b">", b"%3E").replace(b" ", b"%20") + b'">'
    g = client.post("/api/bookmarks/groups", json={"name": "Home"}).json()
    for name, href in (("NAS", "http://nas.lan:5000/app"), ("Plain", "https://plain.example.org/"), ("Evil", "https://evil.example.org/"),
                       ("Inline", "https://inline.example.org/"), ("Mail", "mailto:a@example.org")):
        client.post(f"/api/bookmarks/groups/{g['id']}/links", json={"name": name, "href": href})
    siteicons.settle()
    l = _links(client)
    assert "site=http%3A%2F%2Fnas.lan%3A5000" in l["NAS"]["siteIcon"]
    assert client.get("/" + l["NAS"]["siteIcon"]).headers["content-type"] == "image/x-icon"
    for name in ("Plain", "Evil", "Mail"):  # the badge stays
        assert l[name]["siteIcon"] == "" and l[name]["iconPending"] is False, name
    r = client.get("/" + l["Inline"]["siteIcon"])
    assert r.headers["content-type"] == "image/svg+xml" and r.content == SVG
    assert client.get("/api/bookmarks/site-icon", params={"site": "https://plain.example.org"}).status_code == 404
    n = len(web.asked)
    _links(client)
    siteicons.settle()
    assert len(web.asked) == n  # a site without an icon is not asked again right away


def test_a_links_own_icon_wins(client, web):
    web["https://a.example.org/favicon.ico"] = ICO
    g = client.post("/api/bookmarks/groups", json={"name": "G"}).json()
    own = client.post(f"/api/bookmarks/groups/{g['id']}/links", json={"name": "Own", "href": "https://a.example.org/", "icon": "github.png"}).json()
    up = client.post(f"/api/bookmarks/groups/{g['id']}/links", json={"name": "Up", "href": "https://b.example.org/"}).json()
    assert own["siteIcon"] == "" and own["iconPending"] is False
    siteicons.settle()
    assert web.asked and all("a.example.org" not in a for a in web.asked)  # not even fetched
    r = client.put(f"/api/bookmarks/links/{up['id']}/icon", content=SVG)
    assert r.status_code == 200 and r.json()["iconUrl"] and r.json()["siteIcon"] == ""
    back = client.patch(f"/api/bookmarks/links/{own['id']}", json={"icon": ""}).json()  # the icon field emptied: the site's again
    assert back["iconPending"] is True
    siteicons.settle()
    assert _links(client)["Own"]["siteIcon"]


def test_which_icon_is_best():
    html = """<link rel="icon" href="/16.png" sizes="16x16"><link rel="icon" href="/512.png" sizes="512x512">
              <link rel="apple-touch-icon" href="/touch.png"><link rel="icon" href="/i.svg" type="image/svg+xml">
              <link rel="icon" href="/64.png" sizes="64x64"><link rel="preload" href="/no.png">"""
    assert [c.rsplit("/", 1)[1] for c in siteicons.candidates(html, "https://x.example/p/q")] == ["i.svg", "64.png", "touch.png", "512.png", "16.png"]
    assert siteicons.site("HTTPS://Example.org:443/a?b") == "https://example.org" and siteicons.site("http://h:8080/") == "http://h:8080"
    assert siteicons.site("javascript:alert(1)") is None and siteicons.site("") is None
    assert siteicons.image(b"GIF89a" + b"0" * 20)[1] == "image/gif" and siteicons.image(b"<!doctype html>") is None
