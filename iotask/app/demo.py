"""Demo data (iosuite_shared.demo): the Calloways' lists. The shared Family list and a Groceries list, everyone's
Personal list, chores for the children, a few done, some repeating, one with subtasks."""
from iosuite_shared import demo

from app import ical, model


def _add(lid: int, who: dict, data: dict) -> dict:
    return model.save(lid, ical.build(data), None, None, who["id"])


def seed(people: dict) -> None:
    m, r, a, t = (people[k] for k in ("morgan", "riley", "ava", "theo"))
    d = lambda n: demo.day(n).isoformat()  # noqa: E731
    fam = model.db.one("SELECT id FROM tsk_lists WHERE owner_id IS NULL AND slug = 'family'")
    fam = fam["id"] if fam else model.create_list(None, "Family", "Shared with everyone in the family", "#146b5e", "family")
    shop = model.create_list(None, "Groceries", "What we need from the store", "#e8710a")
    house = model.create_list(None, "House", "Repairs and the yard", "#8e44d6")
    own = {p["key"]: model.create_list(p["id"], "Personal", f"{p['displayName']}'s private list", "#1a73e8") for p in (m, r, a, t)}

    for title, who, due, extra in [
        ("Book Theo's dentist check-up", m, d(3), {"members": ["Theo Calloway"], "priority": 1}),
        ("Sign Ava's field trip form", r, d(1), {"members": ["Ava Calloway"]}),
        ("Plan Eleanor's birthday dinner", m, d(12), {"notes": "Her favourite: the Italian place on Main Street. Book for 8."}),
        ("Renew the car registration", r, d(20), {"priority": 5}),
        ("Pay the piano lessons", m, d(-2), {"members": ["Ava Calloway"]}),
        ("Pick up the photos from the print shop", r, d(-5), {"done": True}),
        ("Take Biscuit to the vet for shots", m, d(9), {"location": "Willow Creek Animal Clinic"}),
    ]:
        _add(fam, who, {"title": title, "due": due, **extra})
    trip = _add(fam, m, {"title": "Get ready for the coast weekend", "due": d(16)})
    for title in ("Book the cabin", "Pack the beach toys", "Check the tyres", "Download offline maps"):
        _add(fam, m, {"title": title, "parent": trip["uid"], "done": title == "Book the cabin"})

    for title in ("Milk", "Eggs", "Sourdough bread", "Bananas", "Greek yogurt", "Coffee beans", "Dog food", "Tortillas",
                  "Cheddar", "Spinach"):
        _add(shop, r, {"title": title, "done": title in ("Eggs", "Bananas")})

    for title, due, extra in [
        ("Clean the gutters", d(6), {}),
        ("Replace the furnace filter", d(25), {"rrule": "FREQ=MONTHLY;INTERVAL=3"}),
        ("Mow the lawn", d(2), {"rrule": "FREQ=WEEKLY", "members": ["Riley Calloway"]}),
        ("Fix the squeaky back door", d(-3), {"priority": 9}),
        ("Test the smoke alarms", d(40), {"rrule": "FREQ=MONTHLY;INTERVAL=6"}),
    ]:
        _add(house, r, {"title": title, "due": due, **extra})

    for key, items in {
        "morgan": [("Send the Juniper Park plans to the client", d(1), 1), ("Call Grace about Thanksgiving", d(4), 0),
                   ("Running shoes: find a new pair", None, 0)],
        "riley": [("Grade the chemistry lab reports", d(2), 1), ("Order new goggles for the lab", d(7), 0),
                  ("Book a haircut", None, 0)],
        "ava": [("Science fair poster", d(10), 1), ("Read chapters 5-7 of The Giver", d(3), 0), ("Practise piano 20 min", d(0), 0)],
        "theo": [("Feed Biscuit", d(0), 0), ("Library books back", d(5), 0), ("Build the Lego rocket", None, 0)],
    }.items():
        who = people[key]
        for title, due, prio in items:
            data = {"title": title, "priority": prio}
            if due:
                data["due"] = due
            if title in ("Feed Biscuit", "Practise piano 20 min"):
                data["rrule"] = "FREQ=DAILY"
            _add(own[key], who, data)
    _add(own["theo"], t, {"title": "Tidy my room", "due": d(-1), "done": True})
    _add(own["ava"], a, {"title": "Return Zoe's hoodie", "due": d(-4), "done": True})
