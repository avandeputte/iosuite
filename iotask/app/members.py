"""Family members on tasks: a task on the Family list (or any list) can be for one or more people of the family
("Emma: pack the swim bag", "Dad: renew the passport").

The family is the accounts that use ioTask (the suite's shared accounts, iosuite-shared), except the ones an admin
took out of it (Settings › Family: an "admin" or service account is not a person). Those cannot be picked and get no
private list of their own here. The tag is kept in the task itself as an iCalendar CATEGORIES value with the member's
display name, so reminders apps that show categories show it, and a category typed there with a member's name (or
account name, in any case) tags the task here too. The other categories of a task stay as they are.
"""
import time

from app import db, users
from iosuite_shared.errors import Invalid

_cache: dict = {"at": 0.0, "list": None}
TTL = 30


def left_out() -> set[int]:
    """The accounts an admin took out of the family."""
    try:
        return {int(x) for x in (db.get_setting("family_left_out") or "").split(",") if x.strip().isdigit()}
    except Exception:  # noqa: BLE001 - no database yet
        return set()


def in_family(uid: int) -> bool:
    return int(uid) not in left_out()


def set_in_family(uid: int, yes: bool) -> None:
    ids = left_out()
    ids.discard(int(uid)) if yes else ids.add(int(uid))
    db.set_setting("family_left_out", ",".join(str(i) for i in sorted(ids)) or None)
    if not yes:  # its empty private lists go (one with tasks stays: nothing is lost)
        db.ex("DELETE FROM tsk_lists WHERE owner_id = %s AND NOT EXISTS (SELECT 1 FROM tsk_tasks t WHERE t.list_id = tsk_lists.id AND t.deleted = 0)",
              (int(uid),))
    forget()


def family() -> list[dict]:
    """[{id, name, displayName}] of every account that may use ioTask and is in the family, by display name."""
    now = time.monotonic()
    if _cache["list"] is None or now - _cache["at"] > TTL:
        out_ = left_out()
        out = [{"id": u["id"], "name": u["name"], "displayName": u.get("displayName") or u["name"]}
               for u in users.all_users() if u.get("role") in users.ROLES and u["id"] not in out_]
        out.sort(key=lambda m: m["displayName"].lower())
        _cache.update(at=now, list=out)
    return _cache["list"]


def forget() -> None:
    _cache.update(at=0.0, list=None)


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
    return [{"id": m["id"], "name": m["name"], "displayName": m["displayName"]} for m in ms]
