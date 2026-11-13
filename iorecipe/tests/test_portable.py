"""Recipes in and out as files, from text and from a photo: the text of a recipe as a draft, the text on a photo
(where Tesseract is installed), an export that comes back whole, Mealie's recipes and backup, and the shopping list
in ioTask."""
import io
import json
import zipfile

import pytest
from PIL import Image, ImageDraw, ImageFont

from app import ocr, shopping, textimport
from conftest import sign_in
from test_api import COOKIES, new, png

TEXT = """Grandma's oat cookies

Chewy, and gone in a day.

Makes 24 cookies
Prep time: 15 min
Cook time: 1 hr 10 minutes

INGREDIENTS
- 200 g oats
- 1 1/2 cups flour
For the icing
• 150 g icing sugar

Instructions:
1. Heat the oven to 180 °C
   and line a tray.
2) Mix everything.
Step 3: Bake for 12 minutes.

Notes
Freeze the dough.
"""


def test_text_with_headings():
    r = textimport.parse(TEXT)
    assert r["title"] == "Grandma's oat cookies" and r["description"] == "Chewy, and gone in a day."
    assert r["servings"] == "24 cookies" and r["prepMinutes"] == 15 and r["cookMinutes"] == 70
    assert r["ingredients"] == ["200 g oats", "1 1/2 cups flour", "For the icing:", "150 g icing sugar"]
    assert r["steps"] == ["Heat the oven to 180 °C and line a tray.", "Mix everything.", "Bake for 12 minutes."]
    assert r["notes"] == "Freeze the dough."


def test_text_without_headings_and_in_dutch():
    r = textimport.parse("Pancakes\n250 g flour\n2 eggs\n½ l milk\npinch of salt\nWhisk it all into a smooth batter and let it rest for half an hour.\nFry in butter, thin.")
    assert r["title"] == "Pancakes" and r["ingredients"] == ["250 g flour", "2 eggs", "½ l milk", "pinch of salt"]
    assert r["steps"] == ["Whisk it all into a smooth batter and let it rest for half an hour.", "Fry in butter, thin."]
    r = textimport.parse("Wafels\nVoor 4 personen\nBereidingstijd: 20 minuten\n\nIngrediënten\n250 g bloem\n\nBereiding\nMeng alles.\n\nBak de wafels\ngoudbruin.")
    assert r["servings"] == "4" and r["cookMinutes"] == 20 and r["ingredients"] == ["250 g bloem"]
    assert r["steps"] == ["Meng alles.", "Bak de wafels goudbruin."]
    assert [textimport.duration(x) for x in ("1 h 30", "1 hour 15 minutes", "45 min", "1:30", "1½ hours", "90", "soon")] == [90, 75, 45, 90, 90, 90, None]


def test_import_text_is_a_draft(client):
    r = client.post("/api/import/text", json={"text": TEXT})
    assert r.status_code == 200 and r.json()["draft"]["title"] == "Grandma's oat cookies"
    assert client.get("/api/recipes").json()["items"] == []  # nothing was saved
    assert client.post("/api/import/text", json={"text": "  "}).status_code == 400
    j = client.post("/api/recipes", json=r.json()["draft"]).json()  # the draft is what POST /api/recipes takes
    assert j["cookMinutes"] == 70 and len(j["steps"]) == 3


@pytest.mark.skipif(not ocr.available(), reason="Tesseract is not installed")
def test_import_photo_reads_the_text(client):
    im = Image.new("RGB", (1500, 1100), "white")
    d = ImageDraw.Draw(im)
    font = ImageFont.load_default(size=44)
    for n, line in enumerate(["Lemon cake", "", "Ingredients", "200 g flour", "3 eggs", "", "Instructions", "1. Mix the flour and the eggs.", "2. Bake for 40 minutes."]):
        d.text((80, 70 + n * 90), line, fill="black", font=font)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    assert client.get("/api/import").json()["photo"] is True
    r = client.post("/api/import/photo", content=buf.getvalue())
    assert r.status_code == 200, r.text
    draft = r.json()["draft"]
    assert draft["title"] == "Lemon cake" and draft["ingredients"] == ["200 g flour", "3 eggs"]
    assert draft["steps"] == ["Mix the flour and the eggs.", "Bake for 40 minutes."]
    assert client.post("/api/import/photo", content=b"not a picture").status_code == 400
    assert client.post("/api/import/photo", content=png()).status_code == 400  # a picture without a word on it


def test_export_comes_back_whole(client, as_user):
    a = new(client, steps=["Mix.", "Bake."])
    b = new(client, title="Secret", family=False, tags=["quick"])
    client.post(f"/api/recipes/{a['id']}/photos", content=png())
    client.post(f"/api/recipes/{a['id']}/photos?step=1", content=png(color=(0, 0, 200)))
    client.put(f"/api/recipes/{a['id']}/mark", json={"favourite": True, "rating": 4})
    book = client.post("/api/books", json={"name": "Baking"}).json()
    client.put(f"/api/books/{book['id']}/recipes/{a['id']}")
    r = client.get("/api/export")
    assert r.headers["content-type"] == "application/zip" and "attachment" in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    doc = json.loads(z.read("recipes.json"))
    assert doc["format"] == "iorecipe" and [x["title"] for x in doc["recipes"]] == ["Oat cookies", "Secret"]
    assert [p["step"] for p in doc["recipes"][0]["photos"]] == [None, 1] and doc["cookbooks"][0]["recipes"] == [0]
    assert len(json.loads(zipfile.ZipFile(io.BytesIO(client.get(f"/api/recipes/{b['id']}/export").content)).read("recipes.json"))["recipes"]) == 1
    assert len(json.loads(zipfile.ZipFile(io.BytesIO(client.get(f"/api/export?book={book['id']}").content)).read("recipes.json"))["recipes"]) == 1
    # into another account's private recipes: the fields, the photos, the marks, the cookbook
    as_user("mia", "member")
    assert client.post("/api/import/file?family=true", content=r.content).status_code == 403
    got = client.post("/api/import/file", content=r.content)
    assert got.status_code == 200, got.text
    assert [x["title"] for x in got.json()["imported"]] == ["Oat cookies", "Secret"] and got.json()["skipped"] == []
    j = client.get(f"/api/recipes/{got.json()['imported'][0]['id']}").json()
    for k, v in COOKIES.items():
        assert j[k] == (["Mix.", "Bake."] if k == "steps" else v), k
    assert j["family"] is False and j["favourite"] is True and j["rating"] == 4 and [p["step"] for p in j["photos"]] == [None, 1]
    books = client.get("/api/books").json()["items"]
    assert [(k["name"], k["family"], k["count"]) for k in books if not k["family"]] == [("Baking", False, 1)]
    assert client.post("/api/import/file", content=b"hello").status_code == 400
    assert client.post("/api/import/file", content=b"PK\x03\x04 not a zip").status_code == 400
    sign_in(client, "alex")
    as_user("vera", "viewer")
    assert client.post("/api/import/file", content=r.content).status_code == 403
    assert client.post("/api/import/text", json={"text": TEXT}).status_code == 403


MEALIE = {"name": "Chili", "slug": "chili", "description": "Warm.", "recipeYield": "6 servings", "totalTime": "1 hour 30 minutes",
          "prepTime": "20 minutes", "performTime": "PT1H10M", "orgURL": "https://example.com/chili", "rating": 4,
          "recipeCategory": [{"name": "Dinner"}], "tags": [{"name": "Spicy"}],
          "recipeIngredient": [
              {"title": "Base", "quantity": 1.5, "unit": {"name": "tablespoon"}, "food": {"name": "olive oil"}, "note": "", "display": ""},
              {"quantity": 2, "unit": None, "food": {"name": "onions"}, "note": "diced"},
              {"quantity": 0, "unit": None, "food": None, "note": "salt to taste", "disableAmount": True},
              {"display": "400 g kidney beans, drained"}],
          "recipeInstructions": [{"title": "Start", "text": "Fry the onions."}, {"title": "", "text": "Add the rest.\n\nSimmer for an hour."}],
          "notes": [{"title": "Tip", "text": "Better the next day."}]}


def test_mealie_recipe_and_zip(client):
    r = client.post("/api/import/file", content=json.dumps(MEALIE).encode())
    assert r.status_code == 200, r.text
    j = client.get(f"/api/recipes/{r.json()['imported'][0]['id']}").json()
    assert j["title"] == "Chili" and j["servings"] == "6 servings" and (j["prepMinutes"], j["cookMinutes"], j["totalMinutes"]) == (20, 70, 90)
    assert j["ingredients"] == ["Base:", "1 1/2 tablespoon olive oil", "2 onions, diced", "salt to taste", "400 g kidney beans, drained"]
    assert j["steps"] == ["Start:", "Fry the onions.", "Add the rest.", "Simmer for an hour."]
    assert j["tags"] == ["Dinner", "Spicy"] and j["notes"] == "Tip\nBetter the next day." and j["rating"] == 4
    assert j["sourceUrl"] == "https://example.com/chili" and j["sourceName"] == "example.com"
    # Mealie's own layout in a .zip: the recipe's folder holds its JSON and the three sizes of its picture
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("recipes/chili/chili.json", json.dumps(MEALIE))
        z.writestr("recipes/chili/images/min-original.webp", png(40, 30))
        z.writestr("recipes/chili/images/original.webp", png(900, 600))
        z.writestr("recipes/soup/soup.json", json.dumps({**MEALIE, "name": "Soup", "rating": None}))
        z.writestr("readme.json", json.dumps({"hello": "there"}))
    got = client.post("/api/import/file?family=false", content=buf.getvalue()).json()
    assert [x["title"] for x in got["imported"]] == ["Chili", "Soup"] and got["skipped"] == ["readme.json: not a recipe"]
    j = client.get(f"/api/recipes/{got['imported'][0]['id']}").json()
    assert j["family"] is False and j["photos"][0]["width"] == 900
    assert client.get(f"/api/recipes/{got['imported'][1]['id']}").json()["photo"] is None


def test_mealie_backup(client):
    rid = "0b7e7c1e-1111-4222-8333-444455556666"
    db = {"recipes": [{"id": rid, "name": "Stew", "recipe_yield": "4", "prep_time": "10 min", "org_url": None, "rating": 5}],
          "recipes_ingredients": [{"recipe_id": rid, "position": 1, "quantity": 2, "unit_id": "u1", "food_id": "f1", "note": "chopped"},
                                  {"recipe_id": rid, "position": 0, "title": "Meat", "quantity": 0.5, "unit_id": "u2", "food_id": "f2", "note": ""}],
          "ingredient_units": [{"id": "u1", "name": "cup"}, {"id": "u2", "name": "kilogram", "abbreviation": "kg", "use_abbreviation": True}],
          "ingredient_foods": [{"id": "f1", "name": "carrots"}, {"id": "f2", "name": "beef"}],
          "recipe_instructions": [{"recipe_id": rid, "position": 1, "text": "Simmer."}, {"recipe_id": rid, "position": 0, "text": "Brown the beef."}],
          "notes": [], "tags": [{"id": "t1", "name": "Winter"}], "recipes_to_tags": [{"recipe_id": rid, "tag_id": "t1"}]}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("database.json", json.dumps(db))
        z.writestr(f"data/recipes/{rid}/images/original.webp", png(640, 480))
        z.writestr(f"data/recipes/{rid}/images/tiny-original.webp", png(64, 48))
    got = client.post("/api/import/file", content=buf.getvalue())
    assert got.status_code == 200, got.text
    j = client.get(f"/api/recipes/{got.json()['imported'][0]['id']}").json()
    assert j["title"] == "Stew" and j["ingredients"] == ["Meat:", "1/2 kg beef", "2 cup carrots, chopped"]
    assert j["steps"] == ["Brown the beef.", "Simmer."] and j["tags"] == ["Winter"] and j["prepMinutes"] == 10 and j["rating"] == 5
    assert j["photos"][0]["width"] == 640


def test_shopping_list(client, monkeypatch):
    r = new(client)
    assert client.get("/api/shopping").json() == {"available": False, "url": "", "lists": []}
    asked = []

    def ask(request, path, params=None, body=None):
        asked.append((path, params, body))
        if path == "/api/lists":
            return {"items": [{"id": 3, "name": "Groceries", "shared": True, "writable": True}, {"id": 4, "name": "Read only", "writable": False}]}
        return {"id": len(asked)}
    monkeypatch.setattr(shopping, "enabled", lambda: True)
    monkeypatch.setattr(shopping, "url", lambda: "https://tasks.example.com")
    monkeypatch.setattr(shopping, "ask", ask)
    assert client.get("/api/shopping").json() == {"available": True, "url": "https://tasks.example.com", "lists": [{"id": 3, "name": "Groceries", "shared": True}]}
    got = client.post(f"/api/recipes/{r['id']}/shopping", json={"listId": 3, "lines": ["400 g oats", " ", "2 eggs"]})
    assert got.status_code == 200 and got.json() == {"added": 2}
    assert asked[-2:] == [("/api/tasks", {"list": "3"}, {"title": "400 g oats", "notes": "For Oat cookies"}),
                          ("/api/tasks", {"list": "3"}, {"title": "2 eggs", "notes": "For Oat cookies"})]
    assert client.post(f"/api/recipes/{r['id']}/shopping", json={"listId": 3, "lines": []}).status_code == 400
    assert client.post(f"/api/recipes/{r['id']}/shopping", json={"lines": ["x"]}).status_code == 400

    def down(request, path, params=None, body=None):
        raise shopping.Unavailable(502, "ioTask is not reachable (URLError)")
    monkeypatch.setattr(shopping, "ask", down)
    assert client.get("/api/shopping").json()["error"].startswith("ioTask is not reachable")
    assert client.post(f"/api/recipes/{r['id']}/shopping", json={"listId": 3, "lines": ["x"]}).status_code == 502


WAFFLES = """Sponge:
2 packages active dry yeast
1 1/3 cups warm milk
1 tablespoon granulated sugar
1 3/4 cups flour
1 egg, beaten

1. In a small bowl, sprinkle the yeast over the milk. Add 1 tablespoon of flour and the sugar; set aside for 5 minutes or until foamy.

2. Sift the remaining flour into a large mixing bowl. Make a well in the center and add the yeast mixture and egg.

3. Cover and set aside in a warm place for 2 hours to rise until the batter has doubled or tripled in bulk.

Batter:
9 tablespoons unsalted butter, at room temperature
1/4 cup flour
Pinch of salt
3/4 cup pearl sugar

1. In a bowl with a wooden spoon, work the butter, flour, salt and pearl sugar into a paste.

2. Work the butter mixture into the sponge mixture until well combined. Cover, and set aside for 10 minutes.

3. With floured hands, shape the dough into 10 balls. (If the dough seems too wet to handle, that&#39;s OK.)"""


def test_text_in_parts_with_numbered_steps_and_no_headings():
    r = textimport.parse(WAFFLES)
    assert r["title"] == "Recipe" and r["description"] is None
    assert r["ingredients"] == ["Sponge:", "2 packages active dry yeast", "1 1/3 cups warm milk", "1 tablespoon granulated sugar", "1 3/4 cups flour",
                                "1 egg, beaten", "Batter:", "9 tablespoons unsalted butter, at room temperature", "1/4 cup flour", "Pinch of salt",
                                "3/4 cup pearl sugar"]
    assert [s[:22] for s in r["steps"]] == ["Sponge:", "In a small bowl, sprin", "Sift the remaining flo", "Cover and set aside in", "Batter:",
                                            "In a bowl with a woode", "Work the butter mixtur", "With floured hands, sh"]
    assert r["steps"][-1].endswith("that's OK.)")
    # a title and an introduction before it, amounts written 1.5, steps as plain sentences
    r = textimport.parse("Oat cookies\nMy gran's, soft and chewy.\n\n1.5 cups oats\n100 g butter\na pinch of salt\n\nHeat the oven to 180 degrees and line a tray.\nMix everything, shape and bake for 12 minutes.")
    assert r["title"] == "Oat cookies" and r["description"] == "My gran's, soft and chewy."
    assert r["ingredients"] == ["1.5 cups oats", "100 g butter", "a pinch of salt"] and len(r["steps"]) == 2
