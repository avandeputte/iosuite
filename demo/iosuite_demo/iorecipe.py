"""Demo data for iorecipe (the iosuite_demo package): the Calloways' recipes. Family recipes, each with a photo of the
dish from Wikimedia Commons (recipes/ beside this file, credited in recipes/credits.json and in the recipe's notes; a
drawn picture when a recipe has none), a family cookbook for weeknights and one for holidays, Ava's own baking,
favourites and ratings from each of them."""
import json
import re
from importlib import resources

import iosuite_demo as demo

from app import model, users

RECIPES = [
    {"title": "Weeknight chicken tacos", "tags": ["dinner", "quick", "kids"], "servings": "4", "prepMinutes": 15, "cookMinutes": 15,
     "description": "Theo's favourite. Everyone builds their own.",
     "ingredients": ["500 g chicken thighs", "1 tbsp taco spice", "8 small tortillas", "1 avocado", "1 cup shredded lettuce",
                     "1/2 cup grated cheddar", "Salsa", "1 lime"],
     "steps": ["Toss the chicken with the spice and a little oil.", "Cook in a hot pan 6 minutes a side, then slice.",
               "Warm the tortillas in a dry pan.", "Serve with everything in bowls on the table."], "color": "#e8710a"},
    {"title": "Grandma Eleanor's apple crumble", "tags": ["dessert", "family classic"], "servings": "6", "prepMinutes": 20, "cookMinutes": 40,
     "description": "Written down from Eleanor's card. Best with vanilla ice cream.",
     "ingredients": ["6 apples (Honeycrisp)", "1 tsp cinnamon", "2 tbsp sugar", "150 g flour", "100 g cold butter", "80 g brown sugar",
                     "50 g oats"],
     "steps": ["Heat the oven to 180 °C.", "Slice the apples, toss with cinnamon and sugar, put in a dish.",
               "Rub the butter into the flour, then stir in the brown sugar and oats.", "Scatter over the apples and bake 40 minutes."],
     "notes": "Eleanor uses a pinch of nutmeg too.", "color": "#b5452f"},
    {"title": "Sunday pancakes", "tags": ["breakfast", "kids"], "servings": "4 (12 pancakes)", "prepMinutes": 10, "cookMinutes": 20,
     "ingredients": ["2 cups flour", "2 tbsp sugar", "2 tsp baking powder", "1/2 tsp salt", "2 eggs", "1 3/4 cups milk", "3 tbsp melted butter"],
     "steps": ["Whisk the dry things together.", "Whisk the eggs, milk and butter, pour into the dry and stir until just mixed.",
               "Cook 1/4 cup at a time on a buttered pan until bubbles show, flip."], "color": "#e8a100"},
    {"title": "Minestrone", "tags": ["dinner", "soup", "vegetarian"], "servings": "6", "prepMinutes": 20, "cookMinutes": 45,
     "ingredients": ["1 onion", "2 carrots", "2 celery stalks", "2 cloves garlic", "1 can tomatoes", "1 can cannellini beans",
                     "1 litre vegetable stock", "100 g small pasta", "2 handfuls spinach", "Parmesan"],
     "steps": ["Soften the onion, carrot and celery in olive oil for 10 minutes.", "Add the garlic, tomatoes and stock; simmer 20 minutes.",
               "Add the beans and pasta; cook until the pasta is done.", "Stir in the spinach, serve with parmesan."], "color": "#1e8e3e"},
    {"title": "Sheet-pan salmon and potatoes", "tags": ["dinner", "quick", "fish"], "servings": "4", "prepMinutes": 10, "cookMinutes": 30,
     "ingredients": ["4 salmon fillets", "600 g baby potatoes", "1 bunch asparagus", "2 tbsp olive oil", "1 lemon", "Dill"],
     "steps": ["Roast the halved potatoes at 220 °C for 15 minutes.", "Add the asparagus and salmon, drizzle with oil and lemon.",
               "Roast 12 more minutes. Finish with dill."], "color": "#e0426a"},
    {"title": "Thanksgiving stuffing", "tags": ["holiday", "side"], "servings": "8", "prepMinutes": 30, "cookMinutes": 45,
     "ingredients": ["1 loaf day-old bread, cubed", "1 onion", "3 celery stalks", "2 tsp sage", "1 tsp thyme", "2 cups stock", "2 eggs", "80 g butter"],
     "steps": ["Dry the bread cubes in a low oven.", "Cook the onion and celery in the butter with the herbs.",
               "Mix everything with the stock and eggs.", "Bake covered 30 minutes, uncovered 15."], "color": "#8e44d6"},
    {"title": "Lemon ricotta pancakes", "tags": ["breakfast"], "servings": "3", "prepMinutes": 10, "cookMinutes": 15,
     "description": "Priya's recipe.", "sourceName": "Priya Raman",
     "ingredients": ["1 cup ricotta", "2 eggs", "Zest of 1 lemon", "3/4 cup flour", "1 tsp baking powder", "Splash of milk"],
     "steps": ["Whisk ricotta, eggs and zest.", "Fold in the flour and baking powder, loosen with milk.", "Cook on low heat."],
     "color": "#0b8a9e"},
]
AVA = [
    {"title": "Chocolate chip cookies (Ava's)", "tags": ["baking", "dessert"], "servings": "24 cookies", "prepMinutes": 15, "cookMinutes": 11,
     "ingredients": ["225 g butter, soft", "200 g brown sugar", "100 g sugar", "2 eggs", "1 tsp vanilla", "330 g flour",
                     "1 tsp baking soda", "1/2 tsp salt", "300 g chocolate chips"],
     "steps": ["Cream the butter and sugars.", "Beat in the eggs and vanilla.", "Stir in the dry things, then the chips.",
               "Chill 30 minutes. Bake at 175 °C for 10 to 11 minutes."], "notes": "Take them out when the middle still looks soft!",
     "color": "#4b53c7"},
]


def _photos() -> dict:
    """{recipe title: (JPEG bytes, credit line)} of the photos in recipes/ (readable from the release's zip too)."""
    folder = resources.files(demo).joinpath("recipes")
    try:
        credits = json.loads(folder.joinpath("credits.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, NotADirectoryError):
        return {}
    return {c["recipe"]: (folder.joinpath(c["file"]).read_bytes(),
                          f"Photo: {c['title'].removeprefix('File:')} by {c['author']}, {c['license']}, via Wikimedia Commons ({c['page']})")
            for c in credits}


def _with_photo(data: dict, photos: dict, label: str):
    """The recipe's fields (its photo's credit added to the notes) and the photo: the real one, else drawn."""
    rec = {k: v for k, v in data.items() if k != "color"}
    key = re.sub(r" \(.*\)$", "", data["title"])
    if key in photos:
        raw, credit = photos[key]
        rec["notes"] = (rec.get("notes", "") + "\n\n" + credit).strip()
        return rec, raw
    return rec, demo.picture(label, data["color"], (1200, 800))


def seed(people: dict) -> None:
    m, r, a, t = (users.get(people[k]["id"]) for k in ("morgan", "riley", "ava", "theo"))
    made, photos = {}, _photos()
    for i, data in enumerate(RECIPES):
        fields, raw = _with_photo(data, photos, data["title"])
        rec = model.create(m if i % 2 == 0 else r, fields, True)
        made[data["title"]] = rec
        model.add_photo(m, rec, raw)
    for data in AVA:
        fields, raw = _with_photo(data, photos, "Cookies!")
        rec = model.create(a, fields, False)
        model.add_photo(a, rec, raw)

    week = model.create_book(m, {"name": "Weeknight dinners", "description": "Quick ones for school nights"}, True)
    hol = model.create_book(m, {"name": "Holidays", "description": "Thanksgiving, Christmas and birthdays"}, True)
    for title in ("Weeknight chicken tacos", "Minestrone", "Sheet-pan salmon and potatoes"):
        model.book_add(m, week, made[title])
    for title in ("Thanksgiving stuffing", "Grandma Eleanor's apple crumble"):
        model.book_add(m, hol, made[title])

    for who, title, fav, rating in [
        (t, "Weeknight chicken tacos", True, 5), (t, "Sunday pancakes", True, 5), (a, "Grandma Eleanor's apple crumble", True, 5),
        (a, "Minestrone", False, 3), (m, "Sheet-pan salmon and potatoes", True, 4), (r, "Grandma Eleanor's apple crumble", True, 5),
        (r, "Weeknight chicken tacos", False, 4), (m, "Lemon ricotta pancakes", True, 5),
    ]:
        model.mark(who, made[title], {"favourite": fav, "rating": rating})
