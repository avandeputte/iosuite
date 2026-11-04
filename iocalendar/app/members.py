"""Family members on events: an event on the Family calendar (or any calendar) can be tagged with the people of the
family it is for ("Emma's swimming", "Dad's dentist").

The family is the accounts that use ioCalendar (the suite's shared accounts, iothing-auth). A tag is kept in the event
itself as an iCalendar CATEGORIES value with the member's display name, so calendar apps (Apple Calendar, Thunderbird,
DAVx5...) show it, and a category typed there with a member's name (or account name, in any case) tags the event here
too. The other categories of an event stay as they are.
"""
import time

from app import users

_cache: dict = {"at": 0.0, "list": None}
TTL = 30


def family() -> list[dict]:
    """[{id, name, displayName}] of every account that may use ioCalendar, by display name."""
    now = time.monotonic()
    if _cache["list"] is None or now - _cache["at"] > TTL:
        out = [{"id": u["id"], "name": u["name"], "displayName": u.get("displayName") or u["name"]}
               for u in users.all_users() if u.get("role") in users.ROLES]
        out.sort(key=lambda m: m["displayName"].lower())
        _cache.update(at=now, list=out)
    return _cache["list"]


def forget() -> None:
    _cache.update(at=0.0, list=None)


def _keys(m: dict) -> set[str]:
    return {m["displayName"].strip().lower(), m["name"].strip().lower()}


def of(categories: list[str] | None, fam: list[dict] | None = None) -> list[dict]:
    """The members an event is tagged with, from its categories (in the order of the family list)."""
    if not categories:
        return []
    have = {str(c).strip().lower() for c in categories}
    return [m for m in (fam if fam is not None else family()) if _keys(m) & have]


def ids_of(categories: list[str] | None, fam: list[dict] | None = None) -> list[int]:
    return [m["id"] for m in of(categories, fam)]


def find(ref, fam: list[dict] | None = None) -> dict:
    """A member by id, account name or display name. ValueError when there is no such member."""
    fam = fam if fam is not None else family()
    s = str(ref.get("id") if isinstance(ref, dict) else ref).strip()
    for m in fam:
        if s.isdigit() and m["id"] == int(s):
            return m
    for m in fam:
        if s.lower() in _keys(m):
            return m
    raise ValueError(f"No family member '{ref}'. The family: " + ", ".join(m["displayName"] for m in fam))


def resolve(refs, fam: list[dict] | None = None) -> list[dict]:
    """Member refs (ids or names, or one comma-separated string) as members, each once."""
    if refs is None:
        return []
    if isinstance(refs, (str, int)):
        refs = [x for x in str(refs).split(",") if x.strip()]
    out = []
    for r in refs:
        m = find(r, fam)
        if m not in out:
            out.append(m)
    return out


def fold(data: dict, current_categories: list[str] | None = None) -> dict:
    """JSON fields with `members` (ids or names) turned into categories: the member tags replace the old member tags,
    and the categories that are not a member's name stay (those given in data, else the event's current ones)."""
    if "members" not in data:
        return data
    fam = family()
    want = resolve(data.get("members") or [], fam)
    base = data["categories"] if "categories" in data else (current_categories or [])
    member_keys = set().union(*(_keys(m) for m in fam)) if fam else set()
    cats = [c for c in (base or []) if str(c).strip().lower() not in member_keys]
    out = {k: v for k, v in data.items() if k != "members"}
    out["categories"] = cats + [m["displayName"] for m in want]
    return out


def public(ms: list[dict]) -> list[dict]:
    return [{"id": m["id"], "name": m["name"], "displayName": m["displayName"]} for m in ms]
