"""ioDocs' answers to the suite's standard endpoints (iosuite_shared.suiteitems): documents found, one document, its
small picture, and the start page's tile (the papers to renew)."""
import re

from iosuite_shared.suiteitems import Provider, item


def _cover(x: dict) -> str | None:
    m = re.search(r"/files/(\d+)$", str(x.get("cover") or ""))
    return m.group(1) if m else None


def _people(x: dict) -> list[str]:
    return [p.get("displayName") for p in (x.get("people") or []) if isinstance(p, dict) and p.get("displayName")]


def _document(x: dict) -> dict:
    """What kind of paper it is, whose, and until when it runs."""
    until = f"expires {x['expiresOn']}" if x.get("expiresOn") else ""
    return item("iodocs", "document", x.get("id"), x.get("title"),
                " · ".join(p for p in (x.get("kindLabel") or "", ", ".join(_people(x)), until) if p),
                image=_cover(x), icon="doc", expiresOn=x.get("expiresOn"))


def search(local, q, n, tz, kinds):
    """The documents with every word of q in their title, kind, number, issuer, notes, own fields, people or the text
    read off their scans."""
    if kinds and "document" not in kinds:
        return []
    rows = local.get("/api/documents", {"q": q, "limit": n + 1}).get("items", [])
    return {"items": [_document(r) for r in rows[:n]], "more": len(rows) > n}


def get(local, kind, item_id):
    if kind != "document" or not item_id.isdigit():
        return None
    return _document(local.get(f"/api/documents/{item_id}"))


def image(local, kind, item_id, p):
    if kind != "document" or not item_id.isdigit() or not p.isdigit():
        return None
    return local.raw(f"/api/documents/{item_id}/files/{p}", {"size": "small"})


def tile(local, tz, n, kind):
    """{items: [{id, title, kind, photo, expiresOn, days, state, people}], more, expired}: the documents this person sees that
    have expired or come within their reminder, the soonest first (n of them, 3 unless asked); more: how many are left
    out; expired: how many of them have."""
    n = min(n or 3, 12)
    rows = []
    for r in local.get("/api/documents", {"status": "expiring", "sort": "expires", "limit": 100}).get("items", []):
        e = r.get("expiry") if isinstance(r.get("expiry"), dict) else {}
        rows.append({"id": r.get("id"), "title": r.get("title") or "(no title)", "kind": r.get("kindLabel") or "", "photo": int(_cover(r)) if _cover(r) else None,
                     "expiresOn": r.get("expiresOn"), "days": e.get("days"), "state": e.get("state"), "people": _people(r)})
    return {"items": rows[:n], "more": max(0, len(rows) - n), "expired": sum(1 for r in rows if r["state"] == "expired")}


PROVIDER = Provider(search=search, get=get, image=image, tile=tile)
