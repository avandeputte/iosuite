"""Demo data (iosuite_shared.demo): the Calloways' address book. The four of them (each account's "This is me" card),
grandparents, an uncle, friends, the children's friends, and the people and places a family calls: the school, the
dentist, the vet, a plumber. The relations are set (Riley's mother, Ava's brother, ...), so the family tree and the
birthdays (ioCalendar's Birthdays calendar) have something to show."""
from iosuite_shared import demo

from app import model, users

GENDER = {"female": "F", "male": "M"}


def _date(t: tuple) -> dict:
    return {"year": t[0], "month": t[1], "day": t[2]}


def _home(label: str = "home", **kw) -> dict:
    h = demo.HOME
    return {"label": label, "street": h["street"], "city": h["city"], "region": h["region"], "postcode": h["postcode"],
            "country": h["country"], **kw}


def seed(people: dict) -> None:
    fam = model.db.one("SELECT id FROM con_address_books WHERE owner_id IS NULL ORDER BY id LIMIT 1")
    book = fam["id"] if fam else model.create_book(None, "Family", "Shared with everyone in the family", slug="family")
    s = demo.SURNAME
    ids = {}

    def add(key, data):
        ids[key] = model.save(book, data)
        return ids[key]

    for p in demo.FAMILY:
        add(p["key"], {"name": {"given": p["first"], "family": s}, "gender": GENDER[p["gender"]], "birthday": _date(p["born"]),
                       "emails": [{"label": "home", "value": demo.email_of(p["key"]), "pref": 1}],
                       "phones": [{"label": "mobile", "value": p["phone"], "pref": 1}] if p["phone"] else [],
                       "addresses": [_home(pref=1)], "org": p["employer"] or None, "title": p["job"] or None,
                       "tags": ["Family"], "favorite": True,
                       "nickname": {"theo": "Teddy"}.get(p["key"])})
    for r in demo.RELATIVES:
        key = r["first"].lower()
        add(key, {"name": {"given": r["first"], "family": r["last"]}, "birthday": _date(r["born"]),
                  "gender": "F" if r["first"] in ("Eleanor", "Grace", "Priya", "Zoe") else "M",
                  "phones": [{"label": "mobile", "value": r["phone"]}] if r["phone"] else [],
                  "emails": [{"label": "home", "value": f"{key}.{r['last'].lower()}@example.com"}] if r["phone"] else [],
                  "addresses": [{"label": "home", "city": r["city"], "region": "OR", "country": "United States"}],
                  "tags": ["Family"] if r["relation"] in ("mother", "father", "brother") else ["Friends"],
                  "favorite": r["relation"] in ("mother", "father")})

    rel = []  # (contact, type, related)
    for a, b in (("morgan", "riley"),):
        rel.append((a, "spouse", b))
    for parent in ("morgan", "riley"):
        for child in ("ava", "theo"):
            rel.append((child, "parent", parent))
    rel += [("ava", "sibling", "theo"), ("riley", "parent", "eleanor"), ("riley", "parent", "walter"),
            ("eleanor", "spouse", "walter"), ("morgan", "parent", "grace"), ("morgan", "sibling", "daniel"),
            ("lucas", "parent", "priya")]
    by_contact: dict = {}
    for c, t, other in rel:
        by_contact.setdefault(c, []).append({"type": t, "relatedId": ids[other]})
    for c, rels in by_contact.items():
        full = model.full(ids[c])
        model.save(book, {**_as_input(full), "relations": (_as_input(full).get("relations") or []) + rels}, ids[c])

    for data in [
        {"kind": "org", "org": "Juniper Hill Middle School", "phones": [{"label": "work", "value": "+1 541 555 0150"}],
         "emails": [{"label": "work", "value": "office@juniperhill-ms.example.com"}], "tags": ["School"],
         "addresses": [{"label": "work", "street": "300 School Road", "city": demo.HOME["city"], "region": "OR"}]},
        {"name": {"given": "Hannah", "family": "Lee"}, "title": "Ava's homeroom teacher", "org": "Juniper Hill Middle School",
         "emails": [{"label": "work", "value": "h.lee@juniperhill-ms.example.com"}], "tags": ["School"]},
        {"name": {"given": "Marcus", "family": "Whitfield"}, "title": "Soccer coach (Theo's team)", "phones": [{"label": "mobile", "value": "+1 541 555 0151"}],
         "tags": ["School", "Sports"]},
        {"kind": "org", "org": "Bright Smiles Dental", "phones": [{"label": "work", "value": "+1 541 555 0152"}],
         "urls": [{"label": "homepage", "value": "https://dentist.example.com"}], "tags": ["Services"],
         "notes": "Dr. Patel. Check-ups every six months."},
        {"kind": "org", "org": "Willow Creek Animal Clinic", "phones": [{"label": "work", "value": "+1 541 555 0153"}],
         "tags": ["Services"], "notes": "Biscuit's vet. Rabies booster due every 3 years."},
        {"name": {"given": "Tony", "family": "Alvarez"}, "org": "Alvarez Plumbing", "phones": [{"label": "work", "value": "+1 541 555 0154"}],
         "tags": ["Services"], "notes": "Fixed the water heater last spring."},
        {"kind": "org", "org": "Luigi's Pizzeria", "phones": [{"label": "work", "value": "+1 541 555 0155"}], "tags": ["Takeout"]},
        {"name": {"given": "Nora", "family": "Jensen"}, "title": "Babysitter", "phones": [{"label": "mobile", "value": "+1 541 555 0156"}],
         "birthday": {"year": 2006, "month": 1, "day": 8}, "tags": ["Friends"]},
        {"name": {"given": "Oliver", "family": "Grant"}, "title": "Neighbour", "phones": [{"label": "mobile", "value": "+1 541 555 0157"}],
         "addresses": [{"label": "home", "street": "44 Juniper Lane", "city": demo.HOME["city"], "region": "OR"}], "tags": ["Neighbours"],
         "birthday": {"month": demo.day(6).month, "day": demo.day(6).day}},
    ]:
        model.save(book, data)

    for p in people.values():
        users.update(p["id"], me_contact_id=ids[p["key"]])


def _as_input(full: dict) -> dict:
    """A loaded contact as save() takes it again (its relations by id)."""
    out = dict(full)
    out["relations"] = [{"type": r.get("type"), "relatedId": r.get("relatedId"), "relatedName": r.get("relatedName")}
                        for r in full.get("relations") or [] if r.get("type")]
    return out
