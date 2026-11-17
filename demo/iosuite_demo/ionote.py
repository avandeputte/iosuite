"""Demo data for ionote (the iosuite_demo package): each Calloway's own notes (notes are private to their account). Folders, tags,
pinned notes, a few weeks of history: Morgan's work and house notes, Riley's lesson ideas and the car, Ava's school
notes, Theo's lists."""
import time

import iosuite_demo as demo

from app import notes

NOTES = {
    "morgan": {
        "folders": [("Work", "blue"), ("House", "green"), ("Recipes to try", "orange")],
        "notes": [
            ("Work", "Juniper Park: client feedback", "- Keep the big oak by the playground\n- More benches along the east path\n"
             "- Native plants only in the rain garden\n- Next review: bring the planting plan and costs", ["juniper-park"], True, 2),
            ("Work", "Hillside Gardens site visit checklist", "Measuring tape, camera, soil test kit, drainage map, boots", ["site-visit"], False, 6),
            ("House", "Paint colours", "Living room: Soft Sage (eggshell)\nKitchen: Warm White\nTheo's room: Ocean Blue, he picked it",
             ["house"], False, 30),
            ("House", "Wi-Fi for guests", "Network: Calloway-Guest\nPassword: on the fridge card (changed every few months)", ["house"], True, 45),
            ("Recipes to try", "Lemon ricotta pancakes", "From Priya. 1 cup ricotta, 2 eggs, zest of a lemon, 3/4 cup flour, "
             "1 tsp baking powder, splash of milk. Low heat.", ["breakfast"], False, 12),
            (None, "Gift ideas", "Eleanor: garden gloves, the new mystery novel\nWalter: bird feeder\nGrace: framed photo of the kids\n"
             "Daniel: hot sauce sampler", ["gifts"], False, 3),
            (None, "Books to read", "- The Overstory\n- Braiding Sweetgrass\n- Project Hail Mary (Riley says yes)", ["books"], False, 20),
        ],
    },
    "riley": {
        "folders": [("School", "teal"), ("Car", "gray")],
        "notes": [
            ("School", "Lab ideas for next term", "1. Elephant toothpaste (catalase)\n2. Red cabbage pH indicator\n"
             "3. Flame tests with salts\n4. Make a battery from lemons", ["chemistry", "labs"], True, 4),
            ("School", "Parent emails to answer", "Mrs. Fischer: about the field trip\nMr. Grant: tutoring times", ["todo"], False, 1),
            ("Car", "Car service history", "Oil change: 3 months ago, 41,200 miles\nTyres rotated: same visit\n"
             "Next: brake pads check", ["car"], False, 60),
            (None, "Soccer team snack rota", "Week 1 Calloway, week 2 Raman, week 3 Becker, week 4 Fischer", ["soccer"], False, 15),
            (None, "Camping packing list", "Tent, sleeping bags, headlamps, stove, gas, first aid kit, rain jackets, marshmallows",
             ["trip"], False, 90),
        ],
    },
    "ava": {
        "folders": [("School", "purple")],
        "notes": [
            ("School", "Science fair: plant growth and music", "Question: do plants grow faster with music?\n"
             "3 pots: silence, classical, rock. Measure every 2 days.\nDay 1: all 2 cm", ["science-fair"], True, 9),
            ("School", "The Giver: reading notes", "Ch 5: the dreams. Ch 6: the ceremony. Who chooses the jobs?", ["reading"], False, 2),
            (None, "Songs to learn on piano", "Clair de lune (slow!), River flows in you, the Ghibli medley", ["piano"], False, 25),
        ],
    },
    "theo": {
        "folders": [],
        "notes": [
            (None, "My Lego sets", "Rocket (not done)\nFire station\nPirate ship\nSpace rover", ["lego"], True, 7),
            (None, "Birthday wish list", "Telescope, soccer ball, a book about volcanoes, a puppy friend for Biscuit", ["birthday"], False, 14),
        ],
    },
}


def seed(people: dict) -> None:
    now = time.time()
    for key, mine in NOTES.items():
        p = people[key]
        token = notes.current_owner.set(p["id"])
        try:
            folders = {}
            for name, color in mine["folders"]:
                folders[name] = notes.save_folder(None, {"name": name, "color": color}, p["name"])["id"]
            for folder, title, body, tags, pinned, days_ago in mine["notes"]:
                when = now - days_ago * 86400
                notes.save_note(None, {"title": title, "body": body, "tags": tags, "pinned": pinned, "createdAt": when,
                                       "updatedAt": when, "folderID": folders.get(folder)}, p["name"])
        finally:
            notes.current_owner.reset(token)
    demo.log.info("ioNote: notes for %d people", len(NOTES))
