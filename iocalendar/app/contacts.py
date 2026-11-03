"""ioContacts, optionally: names (and email addresses) for the people on an event, and a Birthdays calendar with the
birthdays and anniversaries of the contacts.

The server talks to ioContacts, never the browser: with an ioContacts account and an app password made there
(Settings › Apps and devices in ioContacts), as HTTP Basic, and a Cloudflare Access service token when ioContacts sits
behind Cloudflare Access. Settings › ioContacts stores them; IOCONTACTS_* in the environment wins. The contacts the
account sees there (the shared books and its own) are the ones offered here.

The Birthdays calendar is a shared, read-only calendar here (kind 'birthdays'), so the web app, CalDAV and the
subscription links all show it. It is filled from ioContacts' own birthday feed (yearly events), again every few hours
and when an admin asks.
"""
import base64
import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from app import config, db, ical, model

log = logging.getLogger("iocalendar.contacts")
SYNC_EVERY = 6 * 3600
_lock = threading.Lock()
_state: dict = {"synced": None, "error": None, "count": None}


def settings() -> dict:
    return {"url": (config.IOCONTACTS_URL or db.get_setting("iocontacts_url") or "").rstrip("/"),
            "user": config.IOCONTACTS_USER or db.get_setting("iocontacts_user") or "",
            "password": config.IOCONTACTS_PASSWORD or db.get_setting("iocontacts_password") or "",
            "cfId": config.IOCONTACTS_CF_CLIENT_ID or db.get_setting("iocontacts_cf_id") or "",
            "cfSecret": config.IOCONTACTS_CF_CLIENT_SECRET or db.get_setting("iocontacts_cf_secret") or "",
            "birthdays": (db.get_setting("iocontacts_birthdays") or "1") == "1"}


def enabled() -> bool:
    try:
        return bool(settings()["url"])
    except Exception:  # noqa: BLE001 - no database yet
        return False


def public_settings() -> dict:
    s = settings()
    return {"url": s["url"], "user": s["user"], "hasPassword": bool(s["password"]), "cfId": s["cfId"],
            "hasCfSecret": bool(s["cfSecret"]), "enabled": bool(s["url"]), "birthdays": s["birthdays"],
            "fromEnv": bool(config.IOCONTACTS_URL), "lastSync": dict(_state)}


def save_settings(url=None, user=None, password=None, cf_id=None, cf_secret=None, birthdays=None) -> None:
    for k, v in (("iocontacts_url", url), ("iocontacts_user", user), ("iocontacts_password", password), ("iocontacts_cf_id", cf_id),
                 ("iocontacts_cf_secret", cf_secret)):
        if v is not None:
            db.set_setting(k, v.strip() or None)
    if birthdays is not None:
        db.set_setting("iocontacts_birthdays", "1" if birthdays else "0")


def _req(path: str, timeout: float = 15, accept: str = "application/json"):
    s = settings()
    if not s["url"]:
        raise RuntimeError("ioContacts is not set up (Settings › ioContacts)")
    headers = {"Accept": accept, "User-Agent": "ioCalendar"}
    if s["user"] and s["password"]:
        headers["Authorization"] = "Basic " + base64.b64encode(f"{s['user']}:{s['password']}".encode()).decode()
    if s["cfId"] and s["cfSecret"]:
        headers.update({"CF-Access-Client-Id": s["cfId"], "CF-Access-Client-Secret": s["cfSecret"]})
    return urllib.request.urlopen(urllib.request.Request(s["url"] + path, headers=headers), timeout=timeout)


def _json(path: str, timeout: float = 15):
    return json.loads(_req(path, timeout).read())


def search(q: str, limit: int = 12) -> list[dict]:
    """Contacts matching q: [{contactId, name, email, url}] (one row per email address the contact has, the first
    one first; a contact without one is offered by name)."""
    r = _json(f"/api/contacts?q={urllib.parse.quote(q)}&limit={int(limit)}")
    out = []
    base = settings()["url"]
    for c in r.get("items", [])[:limit]:
        out.append({"contactId": c["id"], "name": c.get("fn") or "", "email": c.get("email") or None, "url": f"{base}/#/c/{c['id']}"})
    return out


def contact_url(cid: int) -> str | None:
    s = settings()
    return f"{s['url']}/#/c/{int(cid)}" if s["url"] and cid else None


def test() -> dict:
    try:
        st = _json("/api/status")
        if not st.get("user"):
            return {"ok": False, "error": "ioContacts answered, but did not accept the user name and app password"}
        n = _json("/api/contacts?limit=1").get("total")
        return {"ok": True, "user": st["user"].get("name"), "contacts": n, "version": st.get("version")}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"ioContacts answered {e.code} {e.reason}"}
    except Exception as e:  # noqa: BLE001 - reported to the admin as is
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# ------------------------------------------------------------------ the Birthdays calendar

def birthday_calendar() -> dict | None:
    return db.one("SELECT * FROM calendars WHERE kind = 'birthdays' AND owner_id IS NULL LIMIT 1")


def sync_birthdays() -> dict:
    """Bring the Birthdays calendar up to date with ioContacts (made when missing; removed when switched off)."""
    with _lock:
        s = settings()
        cal = birthday_calendar()
        if not s["url"] or not s["birthdays"]:
            if cal:
                model.delete_calendar(cal["id"])
            _state.update(synced=None, error=None, count=None)
            return {"ok": True, "count": 0, "removed": bool(cal)}
        try:
            info = _json("/api/connect")
            path = urllib.parse.urlsplit(info["calendar"]["all"]).path
            text = _req(path, timeout=60, accept="text/calendar").read().decode("utf-8", "replace")
            feed = ical.parse(text)
        except Exception as e:  # noqa: BLE001
            _state.update(error=f"{type(e).__name__}: {e}"[:300])
            log.warning("birthdays from ioContacts: %s", _state["error"])
            return {"ok": False, "error": _state["error"]}
        if not cal:
            cid = model.create_calendar(None, "Birthdays", "Birthdays and anniversaries from ioContacts", "#e0426a", kind="birthdays", slug="birthdays")
            cal = model.calendar(cid)
        have = {r["uid"]: r for r in model.rows(cal["id"])}
        seen = set()
        changed = 0
        for obj in ical.split_by_uid(feed):
            ev = ical.master_of(ical.events_of(obj))
            # the link back goes to the contact in ioContacts
            url = ev.get("URL")
            if url is not None and "/#/c/" in str(url):
                ev["URL"] = s["url"] + "/#/c/" + str(url).rsplit("/#/c/", 1)[1]
            for k in ("DTSTAMP",):  # changes on every fetch; not a change of the event
                if k in ev:
                    del ev[k]
            ev.add("DTSTAMP", ical.dt.datetime(2000, 1, 1, tzinfo=ical.UTC))
            uid = str(ev.get("UID"))
            seen.add(uid)
            obj = ical.finish(obj)
            text1 = ical.text(obj)
            old = have.get(uid)
            if old and old["etag"] == ical.etag_of(text1):
                continue
            model.save(cal["id"], obj, old["id"] if old else None)
            changed += 1
        for uid, r in have.items():
            if uid not in seen:
                model.delete(r["id"])
                changed += 1
        _state.update(synced=int(time.time()), error=None, count=len(seen))
        return {"ok": True, "count": len(seen), "changed": changed}


def start_sync() -> None:
    """Every few hours (the first a little after start), while ioContacts is set up."""
    def loop():
        time.sleep(20)
        while True:
            try:
                if enabled() or birthday_calendar():
                    sync_birthdays()
            except Exception as e:  # noqa: BLE001
                log.warning("birthday sync failed: %s", e)
            time.sleep(SYNC_EVERY)
    threading.Thread(target=loop, name="birthdays", daemon=True).start()
