"""The REST API: a recipe's fields, the search and the tags, who sees and changes what, the photos, favourites and
ratings, and the cookbooks."""
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
    assert d["counts"] == {"all": 3, "family": 2, "mine": 1, "favourites": 0}
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
    assert client.post(f"/api/recipes/{fam['id']}/photos", content=png()).status_code == 403
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


def test_photos(client):
    r = new(client, steps=["Mix.", "Shape.", "Bake."])
    rid = r["id"]
    assert r["photo"] is None and r["photos"] == []
    assert client.post(f"/api/recipes/{rid}/photos", content=b"<svg onload=alert(1)>").status_code == 400
    j = client.post(f"/api/recipes/{rid}/photos", content=png(3000, 2000))
    assert j.status_code == 201
    j = j.json()
    first = j["photos"][0]
    assert j["photo"] == first["url"] == f"/api/recipes/{rid}/photos/{first['id']}" and first["step"] is None
    got = client.get(j["photo"])
    assert got.headers["content-type"] == "image/jpeg" and "immutable" in got.headers["cache-control"]
    assert Image.open(io.BytesIO(got.content)).size == (1600, 1067)
    assert Image.open(io.BytesIO(client.get(j["photo"] + "?size=small").content)).size == (520, 347)
    # a second one, then the order: the first is the one the cards show
    j = client.post(f"/api/recipes/{rid}/photos", content=png(color=(0, 90, 200))).json()
    second = j["photos"][1]
    assert j["photo"] == first["url"]
    j = client.put(f"/api/recipes/{rid}/photos/order", json={"ids": [second["id"], first["id"]]}).json()
    assert [p["id"] for p in j["photos"]] == [second["id"], first["id"]] and j["photo"] == second["url"]
    assert client.get("/api/recipes").json()["items"][0]["photo"] == second["url"]
    # a step's picture: one per step, it follows its step when the steps change, and is not the cards'
    assert client.post(f"/api/recipes/{rid}/photos?step=9", content=png()).status_code == 400
    j = client.post(f"/api/recipes/{rid}/photos?step=2", content=png()).json()
    assert [p["step"] for p in j["photos"]] == [None, None, 2]
    j = client.post(f"/api/recipes/{rid}/photos?step=2", content=png()).json()
    assert [p["step"] for p in j["photos"]] == [None, None, 2]  # it took the place of the one before
    j = client.patch(f"/api/recipes/{rid}", json={"steps": ["Heat the oven.", "Mix.", "Shape.", "Bake."]}).json()
    assert [p["step"] for p in j["photos"]] == [None, None, 3]
    j = client.patch(f"/api/recipes/{rid}", json={"steps": ["Mix."]}).json()
    assert [p["step"] for p in j["photos"]] == [None, None, None]  # its step is gone: one of the recipe's own now
    # taking the first away: the next is the one the cards show
    assert client.delete(f"/api/recipes/{rid}/photos/{second['id']}").json()["photo"] == first["url"]
    assert client.get(second["url"]).status_code == 404
    assert client.delete(f"/api/recipes/{rid}/photos/{second['id']}").status_code == 404
    client.cookies.clear()
    assert client.get(first["url"]).status_code == 401


def test_favourites_and_ratings(client, as_user):
    a, b = new(client), new(client, title="Brownies")
    mine = new(client, title="Secret", family=False)
    assert a["favourite"] is False and a["rating"] is None and a["ratingAverage"] is None and a["ratingCount"] == 0
    j = client.put(f"/api/recipes/{a['id']}/mark", json={"favourite": True, "rating": 4}).json()
    assert j["favourite"] is True and j["rating"] == 4 and j["ratingAverage"] == 4.0 and j["ratingCount"] == 1
    assert client.put(f"/api/recipes/{a['id']}/mark", json={"rating": 6}).status_code == 400
    client.put(f"/api/recipes/{mine['id']}/mark", json={"favourite": True})
    d = client.get("/api/recipes", params={"scope": "favourites"}).json()
    assert [r["title"] for r in d["items"]] == ["Oat cookies", "Secret"] and d["counts"]["favourites"] == 2
    as_user("mia", "member")
    j = client.put(f"/api/recipes/{a['id']}/mark", json={"rating": 5}).json()
    assert j["favourite"] is False and j["rating"] == 5 and j["ratingAverage"] == 4.5 and j["ratingCount"] == 2
    client.put(f"/api/recipes/{b['id']}/mark", json={"rating": 5})
    assert [r["title"] for r in client.get("/api/recipes", params={"sort": "rating"}).json()["items"]] == ["Brownies", "Oat cookies"]
    assert client.get("/api/recipes", params={"scope": "favourites"}).json()["items"] == []  # alex's are alex's
    assert client.put(f"/api/recipes/{a['id']}/mark", json={"rating": None}).json()["ratingAverage"] == 4.0
    sign_in(client, "alex")
    as_user("vera", "viewer")
    assert client.put(f"/api/recipes/{a['id']}/mark", json={"favourite": True}).status_code == 403
    # a recipe made private keeps its owner's marks only
    sign_in(client, "mia")
    client.put(f"/api/recipes/{b['id']}/mark", json={"favourite": True})
    sign_in(client, "alex")
    client.put(f"/api/recipes/{b['id']}/mark", json={"rating": 3})
    j = client.patch(f"/api/recipes/{b['id']}", json={"family": False}).json()
    assert j["ratingCount"] == 1 and j["ratingAverage"] == 3.0
    assert [r["title"] for r in client.get("/api/recipes", params={"sort": "new"}).json()["items"]][0] == "Secret"


def test_cookbooks(client, as_user):
    a, b = new(client), new(client, title="Brownies")
    mine = new(client, title="Secret", family=False)
    fam = client.post("/api/books", json={"name": "Baking", "description": "Sweet things"})
    assert fam.status_code == 201 and fam.json()["family"] is True and fam.json()["count"] == 0
    fam = fam.json()
    own = client.post("/api/books", json={"name": "To try", "family": False}).json()
    assert client.post("/api/books", json={"name": " "}).status_code == 400
    for r in (a, b):
        assert client.put(f"/api/books/{fam['id']}/recipes/{r['id']}").json()["ok"]
    assert client.put(f"/api/books/{fam['id']}/recipes/{mine['id']}").status_code == 400  # a family cookbook, a private recipe
    for r in (a, mine):
        client.put(f"/api/books/{own['id']}/recipes/{r['id']}")
    d = client.get("/api/recipes", params={"book": fam["id"]}).json()
    assert [r["title"] for r in d["items"]] == ["Brownies", "Oat cookies"]
    assert [(k["name"], k["family"], k["count"]) for k in d["books"]] == [("Baking", True, 2), ("To try", False, 2)]
    assert client.get(f"/api/recipes/{a['id']}").json()["books"] == [fam["id"], own["id"]]
    assert client.patch(f"/api/books/{fam['id']}", json={"name": "Baked"}).json()["name"] == "Baked"
    assert client.delete(f"/api/books/{own['id']}/recipes/{a['id']}").json()["ok"]
    assert [r["title"] for r in client.get("/api/recipes", params={"book": own["id"]}).json()["items"]] == ["Secret"]
    # a recipe made private leaves the family's cookbooks
    client.patch(f"/api/recipes/{b['id']}", json={"family": False})
    assert [r["title"] for r in client.get("/api/recipes", params={"book": fam["id"]}).json()["items"]] == ["Oat cookies"]
    # a member sees the family's cookbook, not alex's own, and keeps their own
    as_user("mia", "member")
    assert [k["name"] for k in client.get("/api/books").json()["items"]] == ["Baked"]
    assert client.get("/api/recipes", params={"book": own["id"]}).status_code == 404
    assert client.put(f"/api/books/{fam['id']}/recipes/{a['id']}").status_code == 403
    assert client.patch(f"/api/books/{fam['id']}", json={"name": "x"}).status_code == 403
    assert client.post("/api/books", json={"name": "Family favourites", "family": True}).status_code == 403
    hers = client.post("/api/books", json={"name": "Mia's"}).json()
    assert hers["family"] is False and client.put(f"/api/books/{hers['id']}/recipes/{a['id']}").json()["ok"]
    sign_in(client, "alex")
    as_user("vera", "viewer")
    assert client.post("/api/books", json={"name": "x", "family": False}).status_code == 403
    sign_in(client, "alex")
    assert client.delete(f"/api/books/{fam['id']}").json()["ok"]
    assert client.get(f"/api/recipes/{a['id']}").status_code == 200  # the recipes stay


def test_the_shell_its_files_and_the_icon_are_public(client):
    client.cookies.clear()
    page = client.get("/")
    assert page.status_code == 200 and "static/app.js?v=" in page.text and "static/app.css?v=" in page.text
    for path, kind in (("/static/app.js", "javascript"), ("/static/app.css", "css"), ("/static/icons/mark.svg", "svg"),
                       ("/static/icons/icon-192.png", "png"), ("/manifest.webmanifest", "manifest")):
        r = client.get(path)
        assert r.status_code == 200 and kind in r.headers["content-type"], path
    assert client.get("/api/recipes").status_code == 401
