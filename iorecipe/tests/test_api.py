"""The REST API: a recipe's fields, the search and the tags, who sees and changes what, and the photo."""
import io

from PIL import Image

from conftest import sign_in

COOKIES = {"title": "Oat cookies", "description": "Chewy.", "servings": "24 cookies", "prepMinutes": 15, "cookMinutes": 12,
           "ingredients": ["For the dough:", "200 g oats", "100 g butter", "1 egg"], "steps": ["Mix.", "Bake 12 minutes at 180 °C."],
           "notes": "Freeze the dough.", "tags": ["Dessert", "cookies"], "sourceUrl": "https://example.com/oat", "sourceName": "Example"}


def new(client, **f):
    r = client.post("/api/recipes", json={**COOKIES, **f})
    assert r.status_code == 201, r.text
    return r.json()


def png(w=800, h=600, color=(200, 80, 40)):
    out = io.BytesIO()
    Image.new("RGB", (w, h), color).save(out, "PNG")
    return out.getvalue()


def test_recipe_fields_round_trip(client):
    r = new(client)
    assert r["family"] is True and r["writable"] is True  # an admin's new recipe is the family's unless said otherwise
    for k, v in COOKIES.items():
        assert r[k] == v, k
    assert r["totalMinutes"] == 27 and r["photo"] is None
    assert client.get(f"/api/recipes/{r['id']}").json() == r
    # one text with a line each is a list too; only what is given changes
    r2 = client.patch(f"/api/recipes/{r['id']}", json={"steps": "Mix.\n\nShape.\r\nBake.", "totalMinutes": 40, "tags": "dessert, Quick ,dessert"}).json()
    assert r2["steps"] == ["Mix.", "Shape.", "Bake."] and r2["totalMinutes"] == 40 and r2["tags"] == ["dessert", "Quick"]
    assert r2["ingredients"] == COOKIES["ingredients"] and r2["title"] == "Oat cookies"
    assert client.patch(f"/api/recipes/{r['id']}", json={"title": " "}).status_code == 400
    assert client.patch(f"/api/recipes/{r['id']}", json={"prepMinutes": "soon"}).status_code == 400
    assert client.patch(f"/api/recipes/{r['id']}", json={"sourceUrl": "javascript:alert(1)"}).json()["sourceUrl"] is None
    assert client.post("/api/recipes", json={"ingredients": ["x"]}).status_code == 400  # no title
    assert client.delete(f"/api/recipes/{r['id']}").json()["ok"]
    assert client.get(f"/api/recipes/{r['id']}").status_code == 404


def test_search_tags_and_counts(client):
    new(client)
    new(client, title="Lemon chicken", ingredients=["1 chicken", "2 lemons"], steps=["Roast."], tags=["Dinner"], family=False)
    new(client, title="Brownies", ingredients=["200 g chocolate"], steps=["Bake."], tags=["dessert"])
    d = client.get("/api/recipes").json()
    assert [r["title"] for r in d["items"]] == ["Brownies", "Lemon chicken", "Oat cookies"]
    assert "ingredients" not in d["items"][0]
    assert d["counts"] == {"all": 3, "family": 2, "mine": 1}
    assert d["tags"][0] == {"tag": "Dessert", "count": 2} or d["tags"][0] == {"tag": "dessert", "count": 2}
    titles = lambda **q: [r["title"] for r in client.get("/api/recipes", params=q).json()["items"]]  # noqa: E731
    assert titles(q="LEMON chick") == ["Lemon chicken"]        # every word, in the ingredients too
    assert titles(q="butter") == ["Oat cookies"]
    assert titles(q="100%") == []                                # a % is a %, not "anything"
    assert titles(tag="dessert") == ["Brownies", "Oat cookies"]
    assert titles(scope="mine") == ["Lemon chicken"] and titles(scope="family") == ["Brownies", "Oat cookies"]


def test_roles(client, as_user):
    fam = new(client)
    mine = new(client, title="Alex's secret", family=False)
    for name, role in (("vera", "viewer"), ("mia", "member"), ("ed", "editor")):
        as_user(name, role)
        sign_in(client, "alex")
    # a viewer reads the family's recipes and nothing else
    sign_in(client, "vera")
    assert [r["title"] for r in client.get("/api/recipes").json()["items"]] == ["Oat cookies"]
    assert client.get(f"/api/recipes/{fam['id']}").json()["writable"] is False
    assert client.get(f"/api/recipes/{mine['id']}").status_code == 404
    assert client.post("/api/recipes", json=COOKIES).status_code == 403
    assert client.post("/api/recipes", json={**COOKIES, "family": False}).status_code == 403
    assert client.patch(f"/api/recipes/{fam['id']}", json={"title": "x"}).status_code == 403
    assert client.delete(f"/api/recipes/{fam['id']}").status_code == 403
    assert client.put(f"/api/recipes/{fam['id']}/photo", content=png()).status_code == 403
    # a member keeps private recipes; the family's are read-only
    sign_in(client, "mia")
    r = client.post("/api/recipes", json={**COOKIES, "title": "Mia's"})
    assert r.status_code == 201 and r.json()["family"] is False  # where a member's new recipe goes
    own = r.json()["id"]
    assert client.post("/api/recipes", json={**COOKIES, "family": True}).status_code == 403
    assert client.patch(f"/api/recipes/{fam['id']}", json={"title": "x"}).status_code == 403
    assert client.patch(f"/api/recipes/{own}", json={"title": "Mia's best"}).json()["title"] == "Mia's best"
    assert client.patch(f"/api/recipes/{own}", json={"family": True}).status_code == 403
    assert client.get(f"/api/recipes/{mine['id']}").status_code == 404
    # an editor changes the family's, and shares a private one
    sign_in(client, "ed")
    assert client.patch(f"/api/recipes/{fam['id']}", json={"title": "Oat cookies 2"}).json()["title"] == "Oat cookies 2"
    assert client.get(f"/api/recipes/{own}").status_code == 404  # Mia's stays Mia's
    e = client.post("/api/recipes", json={**COOKIES, "title": "Ed's", "family": False}).json()
    assert client.patch(f"/api/recipes/{e['id']}", json={"family": True}).json()["family"] is True
    sign_in(client, "vera")
    assert "Ed's" in [r["title"] for r in client.get("/api/recipes").json()["items"]]


def test_photo(client):
    r = new(client)
    assert client.get(f"/api/recipes/{r['id']}/photo").status_code == 404
    assert client.put(f"/api/recipes/{r['id']}/photo", content=b"<svg onload=alert(1)>").status_code == 400
    j = client.put(f"/api/recipes/{r['id']}/photo", content=png(3000, 2000)).json()
    assert j["photo"] == f"/api/recipes/{r['id']}/photo?v=1"
    got = client.get(j["photo"])
    assert got.headers["content-type"] == "image/jpeg" and "immutable" in got.headers["cache-control"]
    assert Image.open(io.BytesIO(got.content)).size == (1600, 1067)
    assert Image.open(io.BytesIO(client.get(j["photo"] + "&size=small").content)).size == (520, 347)
    assert client.put(f"/api/recipes/{r['id']}/photo", content=png()).json()["photo"].endswith("?v=2")  # a new address
    assert client.get("/api/recipes").json()["items"][0]["photo"].endswith("?v=2")
    assert client.delete(f"/api/recipes/{r['id']}/photo").json()["photo"] is None
    assert client.get(f"/api/recipes/{r['id']}/photo").status_code == 404
    client.cookies.clear()
    assert client.get(f"/api/recipes/{r['id']}/photo").status_code == 401


def test_the_shell_its_files_and_the_icon_are_public(client):
    client.cookies.clear()
    page = client.get("/")
    assert page.status_code == 200 and "static/app.js?v=" in page.text and "static/app.css?v=" in page.text
    for path, kind in (("/static/app.js", "javascript"), ("/static/app.css", "css"), ("/static/icons/mark.svg", "svg"),
                       ("/static/icons/icon-192.png", "png"), ("/manifest.webmanifest", "manifest")):
        r = client.get(path)
        assert r.status_code == 200 and kind in r.headers["content-type"], path
    assert client.get("/api/recipes").status_code == 401
