"""ioNote's answers to the suite's standard endpoints (iosuite_shared.suiteitems): the viewer's notes found, one note,
its picture."""
import datetime as dt
import re

from iosuite_shared.suiteitems import Provider, item, lines

_UUID = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")


def _note(n: dict) -> dict:
    """As ioNote shows a note: its title, else its first line; the line after it under it."""
    body = lines(n.get("body")) or lines(n.get("ocrText"))
    title = str(n.get("title") or "").strip()
    if not title:
        title, body = (body[0], body[1:]) if body else ("Picture" if n.get("hasImage") else "Untitled", [])
    when = dt.datetime.fromtimestamp(float(n["updatedAt"]), dt.timezone.utc).isoformat(timespec="minutes") if n.get("updatedAt") else None
    return item("ionote", "note", n.get("id"), title[:80], body[0] if body else "", when, image="" if n.get("hasImage") else None,
                icon="note", pinned=bool(n.get("pinned")) or None)


def search(local, q, n, tz, kinds):
    """The viewer's own notes with every word of q, pinned first, then the last changed first."""
    if kinds and "note" not in kinds:
        return []
    got = local.get("/api/notes", {"q": q, "limit": n})
    return {"items": [_note(x) for x in got.get("notes", [])[:n]], "more": int(got.get("total") or 0) > n}


def get(local, kind, item_id):
    if kind != "note" or not _UUID.fullmatch(item_id):
        return None
    n = local.get(f"/api/notes/{item_id}")
    return None if n.get("deleted") else _note(n)  # in the trash: not shown


def image(local, kind, item_id, p):
    if kind != "note" or not _UUID.fullmatch(item_id):
        return None
    return local.raw(f"/api/notes/{item_id}/thumb")


PROVIDER = Provider(search=search, get=get, image=image)
