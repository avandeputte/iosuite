"""ioThings' answers to the suite's standard endpoints (iosuite_shared.suiteitems): things found, one thing, its
picture."""
import re

from iosuite_shared.suiteitems import Provider, item


def _thing(x: dict) -> dict:
    """Where it is (or who made it) and how long its warranty runs."""
    m = re.search(r"/files/(\d+)$", str(x.get("photo") or ""))
    where = (x.get("location") or {}).get("path") if isinstance(x.get("location"), dict) else None
    warranty = "lifetime warranty" if x.get("lifetimeWarranty") else f"warranty to {x['warrantyExpires']}" if x.get("warrantyExpires") else ""
    return item("iothings", "item", x.get("id"), x.get("name"), " · ".join(p for p in (where or x.get("manufacturer") or "", warranty) if p),
                image=m.group(1) if m else None, icon="box")


def search(local, q, n, tz, kinds):
    """The things with every word of q in their name, maker, model or serial number, notes, place, labels or fields."""
    if kinds and "item" not in kinds:
        return []
    rows = local.get("/api/items", {"q": q, "limit": n + 1}).get("items", [])
    return {"items": [_thing(r) for r in rows[:n]], "more": len(rows) > n}


def get(local, kind, item_id):
    if kind != "item" or not item_id.isdigit():
        return None
    return _thing(local.get(f"/api/items/{item_id}"))


def image(local, kind, item_id, p):
    if kind != "item" or not item_id.isdigit() or not p.isdigit():
        return None
    return local.raw(f"/api/items/{item_id}/files/{p}", {"size": "small"})


PROVIDER = Provider(search=search, get=get, image=image)
