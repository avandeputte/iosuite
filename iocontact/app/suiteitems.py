"""ioContact's answers to the suite's standard endpoints (iosuite_shared.suiteitems): people found, one contact, their
face, and the birthdays ahead (the start page's Birthdays card)."""
from iosuite_shared.suiteitems import Provider, Unavailable, item


def _contact(c: dict) -> dict:
    """A contact's face: their own photo, else the one of their ioPix person, which ioContact hands out too."""
    has_face = bool(c.get("hasPhoto") or c.get("iopixPersonId"))
    return item("iocontact", "contact", c.get("id"), c.get("fn"), " · ".join(x for x in (c.get("title"), c.get("org")) if x),
                image="" if has_face else None, round=True, icon="person")


def search(local, q, n, tz, kinds):
    """The contacts whose name, email, phone, address… match q."""
    if kinds and "contact" not in kinds:
        return []
    got = local.get("/api/contacts", {"q": q, "limit": n})
    return {"items": [_contact(x) for x in got.get("items", [])[:n]], "more": int(got.get("total") or 0) > n}


def get(local, kind, item_id):
    if kind != "contact" or not item_id.isdigit():
        return None
    return _contact(local.get(f"/api/contacts/{item_id}"))


def image(local, kind, item_id, p):
    if kind != "contact" or not item_id.isdigit():
        return None
    try:
        return local.raw(f"/api/contacts/{item_id}/photo")
    except Unavailable as e:
        if e.status != 404:
            raise
    pid = local.get(f"/api/contacts/{item_id}").get("iopixPersonId")
    return local.raw(f"/api/iopix/face/{int(pid)}") if pid else None


def tile(local, tz, n, kind):
    """{items: [{id, name, hasPhoto, iopixPersonId, label, turns, in, date}], more}: the family's birthdays and other
    dates in the next 30 days, soonest first, up to n (8). A birthday whose "Remind me" box is unchecked (remind
    false) is left out; other dates carry no such box (remind null) and always show."""
    n = n or 8
    got = local.get("/api/upcoming", {"days": 30})
    items = [{"id": x.get("contactId"), "name": x.get("fn"), "hasPhoto": bool(x.get("hasPhoto")),
              "iopixPersonId": x.get("iopixPersonId"), "label": x.get("label") or "birthday",
              "turns": x.get("turns"), "in": x.get("inDays"), "date": x.get("date")}
             for x in got.get("items", []) if x.get("remind") is not False]
    return {"items": items[:n], "more": max(0, len(items) - n)}


PROVIDER = Provider(search=search, get=get, image=image, tile=tile)
