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
    assert client.get("/api/recipes").json()["counts"] == {"all": 2, "family": 1, "mine": 1}
