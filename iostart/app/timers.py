"""Kitchen timers: "timer 10m pasta" in the search box starts one.

A timer is the family's, not one person's: every start page and the wall display show the running timers counting
down, with who started them, and anyone can add a minute or dismiss one (the kitchen tablet, the phone of whoever is
stirring). When a timer ends, the page that started it and the wall display ring; the person who started it gets a
notification (kind "timers", Settings › Account › Notifications) on their phone, from the loop here, so it arrives
with every page closed.

    GET    /api/timers                 {now, items}: the running timers and the ones that ended a moment ago
    POST   /api/timers                 {seconds, label?}: a new one
    POST   /api/timers/{id}/more       {seconds}: more time (an ended one starts again from now)
    DELETE /api/timers/{id}            dismissed (stopped, or silenced once ended)

`now` is the server's clock, so a device whose clock is off still counts down to the same second.
"""
import logging
import threading
import time

from iosuite_shared import push, users

from app import config, db

log = logging.getLogger("iostart.timers")

MAX_SECONDS = 24 * 3600
MAX_RUNNING = 20
KEEP_AFTER_END = 15 * 60  # an ended timer nobody dismissed goes after this
TICK = 2                  # seconds between the loop's looks (the notification is at most this late)
_thread = {"t": None, "stop": None}


class BadTimer(ValueError):
    pass


def _name(uid: int) -> str:
    u = users.get(uid)
    return (u.get("displayName") or u["name"]).split()[0] if u else ""


def _item(r: dict) -> dict:
    return {"id": r["id"], "label": r["label"], "seconds": r["seconds"], "endsAt": r["ends_at"], "byId": r["user_id"], "by": _name(r["user_id"])}


def listing(now: float = None) -> dict:
    now = time.time() if now is None else now
    db.ex("DELETE FROM prt_timers WHERE ends_at < %s", (now - KEEP_AFTER_END,))
    return {"now": now, "items": [_item(r) for r in db.q("SELECT * FROM prt_timers ORDER BY ends_at, id")]}


def _seconds(v) -> int:
    try:
        s = int(round(float(v)))
    except (TypeError, ValueError):
        raise BadTimer("How long: seconds, please")
    if not 1 <= s <= MAX_SECONDS:
        raise BadTimer("A timer runs from a second to 24 hours")
    return s


def start(user: dict, b: dict) -> dict:
    if not isinstance(b, dict):
        raise BadTimer("An object, please")
    s = _seconds(b.get("seconds"))
    label = " ".join(str(b.get("label") or "").split())[:80] or "Timer"
    now = time.time()
    if db.one("SELECT count(*) AS n FROM prt_timers WHERE ends_at > %s", (now,))["n"] >= MAX_RUNNING:
        raise BadTimer(f"{MAX_RUNNING} timers are running already")
    tid = db.ex("INSERT INTO prt_timers (user_id, label, seconds, ends_at) VALUES (%s, %s, %s, %s)", (user["id"], label, s, now + s))
    return _item(db.one("SELECT * FROM prt_timers WHERE id = %s", (tid,)))


def _get(tid: int) -> dict:
    r = db.one("SELECT * FROM prt_timers WHERE id = %s", (int(tid),))
    if not r:
        raise LookupError("That timer is gone")
    return r


def more(tid: int, b: dict) -> dict:
    s = _seconds((b or {}).get("seconds", 60))
    r, now = _get(tid), time.time()
    ends = (r["ends_at"] if r["ends_at"] > now else now) + s
    if ends - now > MAX_SECONDS:
        raise BadTimer("A timer runs up to 24 hours")
    total = r["seconds"] + s if r["ends_at"] > now else s
    db.ex("UPDATE prt_timers SET ends_at = %s, seconds = %s, notified = 0 WHERE id = %s", (ends, total, r["id"]))
    return _item(_get(tid))


def dismiss(tid: int) -> None:
    _get(tid)
    db.ex("DELETE FROM prt_timers WHERE id = %s", (int(tid),))


def _length(s: int) -> str:
    h, m, sec = s // 3600, s % 3600 // 60, s % 60
    return " ".join(p for p in (f"{h} h" if h else "", f"{m} min" if m else "", f"{sec} s" if sec else "") if p)


def tick(now: float = None) -> int:
    """The timers that ended and whose notification has not gone out: it goes to who started each. How many were sent."""
    now = time.time() if now is None else now
    sent = 0
    for r in db.q("SELECT * FROM prt_timers WHERE notified = 0 AND ends_at <= %s", (now,)):
        db.ex("UPDATE prt_timers SET notified = 1 WHERE id = %s", (r["id"],))
        try:
            sent += push.notify(r["user_id"], "timers", f"⏰ {r['label']}", f"Your {_length(r['seconds'])} timer is done",
                                url=push.link(config.APP, "#/"), once=f"timer:{r['id']}:{int(r['ends_at'])}",
                                tag=f"timer-{r['id']}", ttl=900, urgency="high")
        except Exception as e:  # noqa: BLE001  no sender key, a push service away: the pages still ring
            log.warning("timer %s: notification not sent: %s", r["id"], e)
    return sent


def person_data(user_id: int, remove: bool) -> int:
    n = db.one("SELECT count(*) AS n FROM prt_timers WHERE user_id = %s", (user_id,))["n"]
    if remove:
        db.ex("DELETE FROM prt_timers WHERE user_id = %s", (user_id,))
    return n


def run() -> None:
    """The loop, in a thread of its own (main.py at start; TIMERS_LOOP=0 leaves it off: the tests)."""
    if not config.TIMERS_LOOP or _thread["t"]:
        return
    stop_ev = threading.Event()

    def loop():
        while not stop_ev.wait(TICK):
            try:
                tick()
            except Exception as e:  # noqa: BLE001  the database away for a moment: the next look
                log.warning("timers: %s", e)

    _thread["stop"] = stop_ev
    _thread["t"] = threading.Thread(target=loop, name="timers", daemon=True)
    _thread["t"].start()


def halt() -> None:
    if _thread["stop"]:
        _thread["stop"].set()
    _thread["t"] = None
