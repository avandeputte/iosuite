"""Import from a web page: the schema.org Recipe data in its shapes (JSON-LD on its own, in an @graph, with sections
and HTML in the values; microdata), the pages that have none, and the addresses the server will not fetch."""
import json

import pytest
from iosuite_shared.errors import Invalid

from app import scrape
from test_api import png

LD = {"@context": "https://schema.org", "@type": "Recipe", "name": "Grandma&#39;s cookies", "description": "<p>Soft &amp; chewy.</p>",
      "image": ["https://img.example.com/a.jpg", "https://img.example.com/b.jpg"], "recipeYield": ["24", "24 cookies"],
      "prepTime": "PT15M", "cookTime": "PT12M", "totalTime": "PT1H27M",
      "recipeIngredient": ["200 g  oats", "100&nbsp;g butter"],
      "recipeInstructions": [{"@type": "HowToSection", "name": "Dough", "itemListElement": [
          {"@type": "HowToStep", "text": "Mix <b>everything</b>."}, {"@type": "HowToStep", "text": "Chill."}]},
          {"@type": "HowToStep", "text": "Bake."}],
      "recipeCategory": "Dessert", "keywords": "cookies, oats", "author": {"@type": "Person", "name": "Grandma"}}


def page(ld, extra=""):
    return f'<html><head><title>T</title><meta property="og:site_name" content="Example Kitchen">{extra}' \
           f'<script type="application/ld+json">{json.dumps(ld)}</script></head><body></body></html>'


def test_jsonld_recipe():
    r = scrape.parse(page(LD), "https://example.com/cookies")
    assert r["title"] == "Grandma's cookies" and r["description"] == "Soft & chewy."
    assert r["servings"] == "24 cookies" and (r["prepMinutes"], r["cookMinutes"], r["totalMinutes"]) == (15, 12, 87)
    assert r["ingredients"] == ["200 g oats", "100 g butter"]
    assert r["steps"] == ["Dough:", "Mix everything.", "Chill.", "Bake."]
    assert r["tags"] == ["Dessert", "cookies", "oats"]
    assert r["image"] == "https://img.example.com/a.jpg" and r["sourceUrl"] == "https://example.com/cookies"
    assert r["sourceName"] == "Grandma"


def test_jsonld_in_a_graph_with_plain_instructions():
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebSite", "name": "Site"},
        {"@type": ["Recipe", "NewsArticle"], "headline": "Soup", "image": {"@type": "ImageObject", "url": "/img/soup.jpg"},
         "recipeYield": 4, "recipeIngredient": ["1 onion"], "recipeInstructions": "Chop.<br>Simmer.\nServe."}]}
    r = scrape.parse(page(ld), "https://example.com/soup/")
    assert r["title"] == "Soup" and r["servings"] == "4" and r["steps"] == ["Chop.", "Simmer.", "Serve."]
    assert r["image"] == "https://example.com/img/soup.jpg" and r["sourceName"] == "Example Kitchen"


def test_microdata_recipe():
    html = """<html><head><title>Pancakes | Site</title><meta property="og:image" content="https://example.com/p.jpg"></head><body>
      <div itemscope itemtype="https://schema.org/Recipe"><h1 itemprop="name">Pancakes</h1>
      <meta itemprop="prepTime" content="PT10M"><span itemprop="recipeYield">8 pancakes</span>
      <ul><li itemprop="recipeIngredient">250 g <a href="/flour">flour</a></li><li itemprop="recipeIngredient">2 eggs</li></ul>
      <div itemprop="recipeInstructions"><p>Whisk.</p><p>Fry.</p></div></div>
      <p itemprop="recipeIngredient">not part of the recipe</p></body></html>"""
    r = scrape.parse(html, "https://example.com/pancakes")
    assert r["title"] == "Pancakes" and r["servings"] == "8 pancakes" and r["prepMinutes"] == 10
    assert r["ingredients"] == ["250 g flour", "2 eggs"] and r["steps"] == ["Whisk.", "Fry."]
    assert r["image"] == "https://example.com/p.jpg"


def test_a_page_without_a_recipe():
    with pytest.raises(Invalid, match="No recipe"):
        scrape.parse("<html><head><title>News</title><script type='application/ld+json'>{\"@type\": \"Article\"}</script></head></html>", "https://example.com/")
    with pytest.raises(Invalid):
        scrape.parse("<html><script type='application/ld+json'>{broken</script>", "https://example.com/")


def test_durations():
    assert [scrape.minutes(x) for x in ("PT1H30M", "P1DT2H", "PT45M", "pt90s", "25", "20 min", "", None, "soon", "PT0M")] == \
        [90, 1560, 45, 2, 25, 20, None, None, None, None]


def test_only_addresses_on_the_internet_are_fetched():
    for url in ("http://127.0.0.1:8690/api/status", "http://localhost/", "http://192.168.1.1/", "http://169.254.169.254/latest/meta-data/",
                "file:///etc/passwd", "ftp://example.com/x"):
        with pytest.raises(Invalid):
            scrape.fetch(url, 1000)


def test_import_keeps_the_recipe_and_its_picture(client, monkeypatch):
    asked = []

    def fetch(url, limit, accept="", allowed=None):
        asked.append(url)
        if url.endswith(".jpg"):
            return png(), "image/png", url
        return page(LD).encode(), "text/html; charset=utf-8", "https://example.com/cookies"
    monkeypatch.setattr(scrape, "fetch", fetch)
    r = client.post("/api/import", json={"url": "example.com/cookies?utm=1"})
    assert r.status_code == 201, r.text
    j = r.json()
    assert asked == ["https://example.com/cookies?utm=1", "https://img.example.com/a.jpg"]
    assert j["readBy"] == "data" and client.get("/api/import").json()["ai"] is False
    assert j["title"] == "Grandma's cookies" and j["family"] is True and j["sourceUrl"] == "https://example.com/cookies"
    assert j["photo"] and client.get(j["photo"]).headers["content-type"] == "image/jpeg"
    # a picture that cannot be had or is not one: the recipe without it
    monkeypatch.setattr(scrape, "fetch", lambda url, limit, accept="", allowed=None:
                        (b"<html>not a picture</html>", "text/html", url) if url.endswith(".jpg") else fetch(url, limit))
    assert client.post("/api/import", json={"url": "https://example.com/cookies", "family": False}).json()["photo"] is None
    # no recipe there, no address
    monkeypatch.setattr(scrape, "fetch", lambda *a, **k: (b"<html><title>x</title></html>", "text/html", "https://example.com/"))
    r = client.post("/api/import", json={"url": "https://example.com/"})
    assert r.status_code == 400 and "No recipe" in r.json()["detail"]
    assert client.post("/api/import", json={"url": " "}).status_code == 400
    assert client.get("/api/recipes").json()["counts"] == {"all": 2, "family": 1, "mine": 1, "favourites": 0}


# ---- pages without recipe data: read as a person would, and with AI where a key is set

PLUGIN = """<html><head><title>Lemon bars - Site</title><meta property="og:title" content="Lemon bars">
  <style>.wprm-recipe-ingredients{color:red}</style></head><body>
  <nav><ul><li>Home</li><li>All recipes</li></ul></nav><h1>Lemon bars</h1><p>A long story about lemons.</p>
  <div class="wprm-recipe-container"><span>Prep time: 20 min</span><p>Serves 12</p>
  <div class="wprm-recipe-ingredients-container"><h3>Ingredients</h3><ul class="wprm-recipe-ingredients">
    <li class="wprm-recipe-ingredient"><span class="wprm-recipe-ingredient-amount">200</span> <span>g</span> <span>flour</span></li>
    <li class="wprm-recipe-ingredient"><span>3</span> <span>lemons</span></li></ul></div>
  <div class="wprm-recipe-instructions-container"><h3>Instructions</h3><ol>
    <li class="wprm-recipe-instruction"><div class="wprm-recipe-instruction-text"><p>Bake the base.</p></div></li>
    <li class="wprm-recipe-instruction"><div><p>Pour over the curd and bake again.</p></div></li></ol></div></div>
  <script>var ingredients = ["not this"];</script><footer><p>1 cup of nonsense</p></footer></body></html>"""

# a blog post as Blogger writes one: lines parted by <br>, the ingredients under a bold line, the method in a video
BLOG = """<html><head><title>Food Blog: American Goulash - Just Like the Lunch Lady Used to Make</title>
  <meta property="og:title" content="American Goulash - Just Like the Lunch Lady Used to Make"><meta property="og:image" content="https://img.example.com/g.jpg">
  </head><body><h1 class="title">Food Blog</h1><h3 class="post-title entry-title">American Goulash - Just Like the Lunch Lady Used to Make</h3>
  <div class="post-body entry-content">I ate this at school, and so did everyone I know. Begin checking the macaroni after ten minutes, since it should be tender and not falling apart, which is easier said than done.<br /><br />
  <iframe src="https://video.example.com/x"></iframe><br />
  <b>Ingredients for 6 portions:</b><br />2 tablespoons olive oil<br />2 pounds ground beef<br />1 large onion, diced<br />
  salt and freshly ground black pepper<br />4 cloves garlic, minced<br />2 bay leaves<br />1 quart chicken broth<br />2 cups elbow macaroni<br />
  1 cup shredded white cheddar<br />freshly chopped Italian parsley<br /></div>
  <div class="post-footer">Posted by Chef at 12:00 PM</div><div>Labels: Beef, Pasta</div>
  <h4>52 comments:</h4><p>2 cups of beans would be nice in this.</p><p>1 question: which beans?</p></body></html>"""

HEADED = """<html><head><title>Erwtensoep | Oma kookt</title></head><body><header><h1>Erwtensoep</h1></header>
  <p>Voor 6 personen</p><p>Bereidingstijd: 2 uur</p>
  <h2>Ingrediënten</h2><p>500 g spliterwten<br>1 rookworst<br>2 preien</p>
  <h2>Bereiding</h2><p>Kook de erwten gaar in twee liter water.</p><p>Voeg de prei en de worst toe en laat nog een half uur trekken.</p>
  <h2>Reacties</h2><p>3 keer gemaakt, heerlijk!</p></body></html>"""


def test_a_recipe_plugins_lists():
    r = scrape.parse(PLUGIN, "https://example.com/lemon-bars")
    assert r["readBy"] == "page" and r["title"] == "Lemon bars"
    assert r["ingredients"] == ["200 g flour", "3 lemons"]
    assert r["steps"] == ["Bake the base.", "Pour over the curd and bake again."]
    assert r["servings"] == "12" and r["prepMinutes"] == 20 and r["sourceUrl"] == "https://example.com/lemon-bars"


def test_a_blog_post_with_the_ingredients_only():
    r = scrape.parse(BLOG, "https://blog.example.com/2019/08/american-goulash.html?m=1")
    assert r["readBy"] == "page" and r["title"] == "American Goulash - Just Like the Lunch Lady Used to Make"
    assert r["servings"] == "6 portions" and r["steps"] == []
    assert r["ingredients"][0] == "2 tablespoons olive oil" and r["ingredients"][-1] == "freshly chopped Italian parsley"
    assert len(r["ingredients"]) == 10 and "salt and freshly ground black pepper" in r["ingredients"]
    assert r["image"] == "https://img.example.com/g.jpg" and r["sourceName"] == "blog.example.com"


def test_a_page_with_headings_in_dutch():
    r = scrape.parse(HEADED, "https://example.nl/erwtensoep")
    assert r["readBy"] == "page" and r["title"] == "Erwtensoep" and r["servings"] == "6" and r["cookMinutes"] == 120
    assert r["ingredients"] == ["500 g spliterwten", "1 rookworst", "2 preien"]
    assert r["steps"] == ["Kook de erwten gaar in twee liter water.", "Voeg de prei en de worst toe en laat nog een half uur trekken."]


PROSE = """<html><head><title>My goulash</title></head><body><h1>My goulash</h1><p>Brown two pounds of beef in a little oil with a diced
  onion, add four cloves of garlic, a quart of broth and two cups of macaroni, and simmer until the pasta is tender.</p></body></html>"""


def test_ai_reads_what_the_page_does_not_lay_out(monkeypatch):
    from app import ai, config
    with pytest.raises(Invalid):  # no key: nothing to make it out with
        scrape.parse(PROSE, "https://example.com/goulash")
    asked = []

    def answer(text, url):
        asked.append(text)
        return {"found": True, "title": "My  goulash", "description": "", "servings": "", "prepMinutes": 0, "cookMinutes": 0, "totalMinutes": 0,
                "ingredients": ["2 pounds beef", "1 onion, diced", " "], "steps": ["Brown the beef with the onion.", "Simmer with the rest."], "tags": []}
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(ai, "_ask", answer)
    r = scrape.parse(PROSE, "https://example.com/goulash")
    assert r["readBy"] == "ai" and r["title"] == "My goulash" and r["ingredients"] == ["2 pounds beef", "1 onion, diced"]
    assert r["steps"] == ["Brown the beef with the onion.", "Simmer with the rest."] and r["prepMinutes"] is None
    assert "Brown two pounds of beef" in asked[0] and len(asked) == 1
    # the ingredients alone were made out: the AI is asked for the steps too, and what the page gave stands when it finds nothing
    r = scrape.parse(BLOG, "https://blog.example.com/g")
    assert r["readBy"] == "ai" and len(asked) == 2 and "52 comments" in asked[1]
    monkeypatch.setattr(ai, "_ask", lambda text, url: {"found": False})
    r = scrape.parse(BLOG, "https://blog.example.com/g")
    assert r["readBy"] == "page" and len(r["ingredients"]) == 10
    with pytest.raises(Invalid):
        scrape.parse(PROSE, "https://example.com/goulash")
    # a page that says what its recipe is, or lays it out, is never sent anywhere
    monkeypatch.setattr(ai, "_ask", lambda text, url: pytest.fail("asked"))
    assert scrape.parse(page(LD), "https://example.com/cookies")["readBy"] == "data"
    assert scrape.parse(PLUGIN, "https://example.com/lemon-bars")["readBy"] == "page"
    assert scrape.parse(HEADED, "https://example.nl/erwtensoep")["readBy"] == "page"


def test_a_page_is_asked_for_as_a_browser_does(monkeypatch):
    from iosuite_shared import outbound
    sent = []

    class Answer:
        headers = {"Content-Type": "text/html"}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n): return b"<html></html>"
        def geturl(self): return "https://example.com/x"

    class Opener:
        def open(self, req, timeout=None):
            sent.append(dict(req.header_items()))
            if req.full_url.endswith("/refused"):
                raise scrape.urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
            return Answer()
    monkeypatch.setattr(outbound, "check", lambda url, allowed=None: None)
    monkeypatch.setattr(outbound, "opener", lambda allowed=None: Opener())
    scrape.fetch("https://example.com/x", 1000)
    h = {k.lower(): v for k, v in sent[0].items()}
    assert "Chrome/" in h["user-agent"] and h["sec-fetch-mode"] == "navigate" and h["sec-fetch-dest"] == "document"
    assert h["accept"].startswith("text/html") and h["accept-language"] and h["upgrade-insecure-requests"] == "1" and "sec-ch-ua" in h
    scrape.fetch("https://example.com/x.jpg", 1000, accept="image/*")
    h = {k.lower(): v for k, v in sent[1].items()}
    assert h["sec-fetch-dest"] == "image" and h["accept"] == "image/*" and "upgrade-insecure-requests" not in h
    with pytest.raises(Invalid, match="Pasted text"):  # a site that tests for a browser: said so, with the way around
        scrape.fetch("https://example.com/refused", 1000)
