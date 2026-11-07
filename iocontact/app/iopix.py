"""ioPix: the People list (people tags with their face), to link a contact to a person.

A linked person's face is the contact's only photo: ioContacts stores none of its own, and serves the ioPix face
wherever a photo goes (the web app, vCards, CardDAV, LDAP jpegPhoto, the account tiles).

Nothing to set up: ioPix is found in the suite's list of apps, and the server reads from it (never the browser) as
ioContacts' own service account with a read-only app password, both made by itself the first time
(iosuite_shared.links).
"""
import json
import logging
import threading
import time
import urllib.error

from iosuite_shared import links

from app import db

log = logging.getLogger("iocontacts.iopix")
APP, PROVIDER = "iocontacts", "iopix"
_lock = threading.Lock()
_cache: dict = {"at": 0, "people": None}
_faces: dict = {}  # person id -> (when, (bytes, type) or None): ioPix is the only source of contact photos, so they are asked often
FACE_TTL, FACE_MISS_TTL, FACE_ERROR_TTL, FACE_MAX = 3600, 600, 60, 4000
# what Settings › ioPix used to keep before the suite found ioPix by itself (removed at start)
OLD_SETTINGS = ("iopix_url", "iopix_user", "iopix_password", "iopix_cf_id", "iopix_cf_secret")


def forget_old_settings() -> None:
    try:
        for k in OLD_SETTINGS:
            if db.get_setting(k) is not None:
                db.set_setting(k, None)
    except Exception as e:  # noqa: BLE001 - tried again next start
        log.debug("old ioPix settings: %s", e)


def settings() -> dict:
    try:
        return {"url": links.url(PROVIDER) or ""}
    except Exception:  # noqa: BLE001 - no database yet
        return {"url": ""}


def public_settings() -> dict:
    s = settings()
    return {"url": s["url"], "enabled": bool(s["url"])}


def _get(path: str, timeout: float = 10):
    if not settings()["url"]:
        raise RuntimeError("ioPix is not part of the suite (it has not started on this Shared ioSuite database)")
    return links.get(APP, PROVIDER, path, timeout=timeout, user_agent="ioContacts")


def people(force: bool = False) -> list[dict]:
    """[{id, name, path, count, hasFace}] from ioPix's /api/meta (people tags), cached five minutes."""
    with _lock:
        if not force and _cache["people"] is not None and time.time() - _cache["at"] < 300:
            return _cache["people"]
        meta = json.loads(_get("/api/meta", timeout=30).read())
        tags = meta.get("tags", [])
        parents = {t.get("pid") for t in tags}
        # leaf person tags with photos, as on ioPix's People page (a person tag with children is a family or group)
        out = [{"id": t["id"], "name": t["name"], "path": t.get("full"), "count": t.get("nAll") or t.get("n") or 0,
                "hasFace": bool(t.get("face")), "icon": t.get("icon")}
               for t in tags if t.get("person") and (t.get("n") or 0) > 0 and t["id"] not in parents and t.get("name")]
        out.sort(key=lambda p: p["name"].lower())
        _cache.update(at=time.time(), people=out)
        return out


def face(person_id: int) -> tuple[bytes, str] | None:
    """The person's face from ioPix (bytes, content type), or None when ioPix has none. Kept an hour (a miss ten
    minutes, a failure a minute), so address book syncs and exports do not ask ioPix for every contact every time."""
    hit = _faces.get(person_id)
    if hit:
        ttl = FACE_TTL if hit[1] else FACE_ERROR_TTL if hit[2] else FACE_MISS_TTL
        if time.time() - hit[0] < ttl:
            if hit[2]:
                raise hit[2]
            return hit[1]
    try:
        r = _get(f"/face/{person_id}", timeout=20)
        got = (r.read(), r.headers.get("Content-Type", "image/jpeg").split(";")[0].strip() or "image/jpeg")
        err = None
    except urllib.error.HTTPError as e:
        if e.code != 404:
            _remember(person_id, None, e)
            raise
        got, err = None, None
    except Exception as e:  # noqa: BLE001 - remembered briefly, then raised as is
        _remember(person_id, None, e)
        raise
    _remember(person_id, got, err)
    return got


def _remember(person_id: int, got, err) -> None:
    if len(_faces) >= FACE_MAX:
        _faces.clear()
    _faces[person_id] = (time.time(), got, err)


def photo(person_id: int | None) -> tuple[bytes, str] | None:
    """A linked contact's photo: the ioPix face, or None (not linked, ioPix not set up, no face, or ioPix not answering)."""
    if not person_id or not settings()["url"]:
        return None
    try:
        return face(person_id)
    except Exception:  # noqa: BLE001 - then the contact shows its initials
        return None


def person_url(person_id: int, name: str | None = None) -> str | None:
    s = settings()
    if not s["url"]:
        return None
    return f"{s['url']}/#/photos?tag={person_id}"


def test() -> dict:
    try:
        n = len(people(force=True))
        return {"ok": True, "people": n}
    except Exception as e:  # noqa: BLE001 - reported to the admin as is
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
