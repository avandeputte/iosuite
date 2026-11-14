"""Family members on tasks: a task on the Family list (or any list) can be for one or more people of the family
("Emma: pack the swim bag", "Dad: renew the passport").

The family is the suite's one list (iosuite_shared.family, Settings › Security › Family for suite admins), less the
accounts with no role in ioTask: the same people, colours and initials as in every app. Only a member of the family
gets a private list of their own here. The tag is kept in the task itself as an iCalendar CATEGORIES value with the member's
display name, so reminders apps that show categories show it, and a category typed there with a member's name (or
account name, in any case) tags the task here too. The other categories of a task stay as they are.
"""
import time

from app import users
from iosuite_shared import family as suite_family
from iosuite_shared.errors import Invalid

_cache: dict = {"at": 0.0, "list": None}
TTL = 30


def in_family(uid: int) -> bool:
    return suite_family.in_family(uid)


def family() -> list[dict]:
    """[{id, name, displayName, initials, color, hasFace}] of the suite's family members who may use this app, by display name."""
    now = time.monotonic()
    if _cache["list"] is None or now - _cache["at"] > TTL:
        if TTL <= 0:
            suite_family.forget()
        here = {u["id"] for u in users.all_users() if u.get("role") in users.ROLES}
        _cache.update(at=now, list=[suite_family.public(m) for m in suite_family.members() if m["id"] in here])
    return _cache["list"]


def forget() -> None:
    _cache.update(at=0.0, list=None)
    suite_family.forget()


def _keys(m: dict) -> set[str]:
    return {m["displayName"].strip().lower(), m["name"].strip().lower()}


def of(categories: list[str] | None, fam: list[dict] | None = None) -> list[dict]:
    """The members a task is for, from its categories (in the order of the family list)."""
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
    raise Invalid(f"No family member '{ref}'. The family: " + ", ".join(m["displayName"] for m in fam))


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
    and the categories that are not a member's name stay (those given in data, else the task's current ones)."""
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
    return [suite_family.public(m) for m in ms]
