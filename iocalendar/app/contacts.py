"""ioContacts, when it is part of the suite: names (and email addresses) for the people on an event, and a Birthdays
calendar with the birthdays and anniversaries of the contacts.

Nothing to set up: ioContacts is found in the suite's list of apps, and the server reads from it as ioCalendar's own
service account with a read-only app password, both made by itself the first time (iosuite_shared.links). The contacts
that account sees there (the shared books) are the ones offered here.

The Birthdays calendar is a shared, read-only calendar here (kind 'birthdays'), so the web app, CalDAV and the
subscription links all show it. It is filled from ioContacts' own birthday feed (yearly events), again every few hours
and when an admin asks.
"""
import json
import logging
import threading
import time
import urllib.error
import urllib.parse

from iosuite_shared import links

from app import db, ical, model

log = logging.getLogger("iocalendar.contacts")
APP, PROVIDER = "iocalendar", "iocontacts"
SYNC_EVERY = 6 * 3600
_lock = threading.Lock()
_state: dict = {"synced": None, "error": None, "count": None}
def settings() -> dict:
    return {"url": links.url(PROVIDER) or "", "birthdays": (db.get_setting("iocontacts_birthdays") or "1") == "1"}


def enabled() -> bool:
    try:
        return links.available(PROVIDER)
    except Exception:  # noqa: BLE001 - no database yet
        return False


def public_settings() -> dict:
    s = settings()
    return {"url": s["url"], "enabled": bool(s["url"]), "birthdays": s["birthdays"], "lastSync": dict(_state)}


def save_settings(birthdays=None) -> None:
    if birthdays is not None:
        db.set_setting("iocontacts_birthdays", "1" if birthdays else "0")


def _req(path: str, timeout: float = 15, accept: str = "application/json", sign_in: bool = True):
    if not enabled():
        raise RuntimeError("ioContacts is not part of the suite (it has not started on this Shared ioSuite database)")
    return links.get(APP, PROVIDER, path, timeout=timeout, accept=accept, user_agent="ioCalendar", sign_in=sign_in)


def _json(path: str, timeout: float = 15):
    with _req(path, timeout) as r:
        return json.loads(r.read())


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
            return {"ok": False, "error": "ioContacts answered, but did not accept ioCalendar's app password"}
        n = _json("/api/contacts?limit=1").get("total")
        return {"ok": True, "user": st["user"].get("name"), "contacts": n, "version": st.get("version")}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"ioContacts answered {e.code} {e.reason}"}
    except Exception as e:  # noqa: BLE001 - reported to the admin as is
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# ------------------------------------------------------------------ the Birthdays calendar

def birthday_calendar() -> dict | None:
    return db.one("SELECT * FROM cal_calendars WHERE kind = 'birthdays' AND owner_id IS NULL LIMIT 1")


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
            with _req(path, timeout=60, accept="text/calendar", sign_in=False) as r:  # the feed's address carries its own token
                text = r.read().decode("utf-8", "replace")
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
