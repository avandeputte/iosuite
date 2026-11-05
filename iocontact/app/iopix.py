"""ioPix: the People list (people tags with their face), to link a contact to a person.

The server talks to ioPix, never the browser, so ioPix's sign-in stays on the server: optionally an ioPix account
(when Require sign-in is on there) and a Cloudflare Access service token (when ioPix sits behind Cloudflare Access).
Settings > ioPix stores them; IOPIX_* in the environment wins.
"""
import json
import threading
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

from app import config, db

_lock = threading.Lock()
_cache: dict = {"at": 0, "people": None}
_jar = CookieJar()


def settings() -> dict:
    return {"url": (config.IOPIX_URL or db.get_setting("iopix_url") or "").rstrip("/"),
            "user": config.IOPIX_USER or db.get_setting("iopix_user") or "",
            "password": config.IOPIX_PASSWORD or db.get_setting("iopix_password") or "",
            "cfId": config.IOPIX_CF_CLIENT_ID or db.get_setting("iopix_cf_id") or "",
            "cfSecret": config.IOPIX_CF_CLIENT_SECRET or db.get_setting("iopix_cf_secret") or ""}


def public_settings() -> dict:
    s = settings()
    return {"url": s["url"], "user": s["user"], "hasPassword": bool(s["password"]), "cfId": s["cfId"],
            "hasCfSecret": bool(s["cfSecret"]), "enabled": bool(s["url"]),
            "fromEnv": bool(config.IOPIX_URL)}


def save_settings(url=None, user=None, password=None, cf_id=None, cf_secret=None) -> None:
    if url and url.strip() and not url.strip().lower().startswith(("http://", "https://")):
        raise ValueError("The ioPix address starts with http:// or https://")
    for k, v in (("iopix_url", url), ("iopix_user", user), ("iopix_password", password), ("iopix_cf_id", cf_id),
                 ("iopix_cf_secret", cf_secret)):
        if v is not None:
            db.set_setting(k, v.strip() or None)
    _cache.update(at=0, people=None)
    _jar.clear()


def _opener():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))


def _req(path: str, data: dict | None = None, timeout: float = 10):
    s = settings()
    if not s["url"]:
        raise RuntimeError("ioPix is not set up (Settings > ioPix)")
    if not s["url"].lower().startswith(("http://", "https://")):
        raise RuntimeError("The ioPix address must start with http:// or https://")
    headers = {"Accept": "application/json", "User-Agent": "ioContacts"}
    if s["cfId"] and s["cfSecret"]:
        headers.update({"CF-Access-Client-Id": s["cfId"], "CF-Access-Client-Secret": s["cfSecret"]})
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
        headers["Origin"] = s["url"]
    req = urllib.request.Request(s["url"] + path, data=body, headers=headers, method="POST" if body else "GET")
    return _opener().open(req, timeout=timeout)


def _login() -> None:
    s = settings()
    if s["user"] and s["password"]:
        _req("/api/auth/login", {"name": s["user"], "password": s["password"]}).read()


def _get(path: str, timeout: float = 10):
    try:
        return _req(path, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403) and settings()["user"]:
            _login()
            return _req(path, timeout=timeout)
        raise


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
    try:
        r = _get(f"/face/{person_id}", timeout=20)
        return r.read(), r.headers.get("Content-Type", "image/jpeg")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


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
