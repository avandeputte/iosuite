"""ioTask, when it is part of the suite: the tasks that are due show on their day, beside the events, and are ticked
off from the calendar.

Nothing to set up: ioTask is found in the suite's list of apps. Unlike the contacts (app/contacts.py), tasks are asked
for on the viewer's behalf: the request goes out from this server with the viewer's own credentials (the suite's shared
session cookie, or the Authorization header they came with), so ioTask answers with the lists that person sees there
and takes a tick only from someone who may change the list. Nothing is kept here.

ioTask is asked at the addresses the apps use for each other (iosuite_shared.links: localhost on this machine, its
address inside the network, its public one), with the suite's Cloudflare Access service token when one is set. One
that did not answer is left alone for BREAK_S seconds, so a calendar without its tasks draws at once.
"""
import datetime as dt
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from fastapi import Request
from iosuite_shared import links, sessions

APP, PROVIDER = "iocalendar", "iotask"
TIMEOUT = 5    # seconds, per request
BREAK_S = 30   # seconds ioTask is left alone after it did not answer
MAX_TASKS = 2000
_state = {"down": 0.0, "good": None}  # until when it is left alone (time.monotonic); the address that answered last


class Unavailable(Exception):
    """ioTask could not be asked, or would not answer: (status, why)."""

    def __init__(self, status: int, why: str):
        super().__init__(why)
        self.status = status


def enabled() -> bool:
    try:
        return links.available(PROVIDER)
    except Exception:  # noqa: BLE001 - no database yet
        return False


def url() -> str:
    """Where the browser opens ioTask ('' when it is not part of the suite)."""
    try:
        return links.url(PROVIDER) or ""
    except Exception:  # noqa: BLE001
        return ""


def forget() -> None:
    """ioTask may be asked again, from its first address on (the tests)."""
    _state.update(down=0.0, good=None)


def _headers(request: Request) -> dict:
    """The viewer's credentials, passed on as they came, and the suite's Cloudflare Access service token."""
    h = {"User-Agent": "ioCalendar", "Accept": "application/json", "Accept-Encoding": "identity"}
    tok = request.cookies.get(sessions.COOKIE)
    if tok:
        h["Cookie"] = f"{sessions.COOKIE}={tok}"
    elif request.headers.get("authorization"):
        h["Authorization"] = request.headers["authorization"]
    try:
        h.update(links.headers(APP, "", sign_in=False))
    except Exception:  # noqa: BLE001 - the shared database is away: without the token
        pass
    return h


def _open(req, timeout: float):
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - an http(s) address from the suite's list
        return json.loads(r.read())


def ask(request: Request, path: str, params: dict | None = None, body: dict | None = None):
    """GET path from ioTask as the viewer (with body: POST that JSON); its JSON answer, or Unavailable."""
    if not enabled():
        raise Unavailable(404, "ioTask is not part of the suite")
    if _state["down"] > time.monotonic():
        raise Unavailable(502, "ioTask did not answer a moment ago")
    try:
        bases = links.addresses(PROVIDER)
    except Exception:  # noqa: BLE001
        bases = []
    if _state["good"] in bases:
        bases = [_state["good"]] + [b for b in bases if b != _state["good"]]
    headers = _headers(request)
    data = None
    if body is not None:
        data, headers = json.dumps(body).encode(), {**headers, "Content-Type": "application/json"}
    query = "?" + urllib.parse.urlencode(params) if params else ""
    why = "no address"
    for base in bases:
        req = urllib.request.Request(base + path + query, data=data, headers=headers, method="POST" if body is not None else "GET")
        try:
            got = _open(req, TIMEOUT)
            _state["good"] = base
            return got
        except urllib.error.HTTPError as e:  # it answered
            _state["good"] = base
            if e.code in (401, 403) and body is None:
                raise Unavailable(403, "ioTask does not let this account in: open it once and sign in there")
            try:
                detail = json.loads(e.read()).get("detail")
            except (ValueError, AttributeError):
                detail = None
            if e.code in (400, 403, 404, 409, 412) and isinstance(detail, str):
                raise Unavailable(e.code, detail)  # its own word on what it would not take
            if e.code in (404, 405):
                raise Unavailable(502, "This ioTask is too old for that: update it")
            raise Unavailable(502, f"ioTask answered {e.code}")
        except (urllib.error.URLError, OSError, ValueError) as e:
            why = type(e).__name__
    _state["down"] = time.monotonic() + BREAK_S
    raise Unavailable(502, f"ioTask is not reachable ({why})")


def _tz(tz: str | None) -> str | None:
    return tz if tz and re.fullmatch(r"[A-Za-z0-9_+\-/]{1,64}", tz) else None


def between(request: Request, start: dt.date, end: dt.date, tz: str | None = None) -> list[dict]:
    """The tasks due from start up to end (end not included), open and done, over the lists the viewer sees in ioTask:
    [{id, title, due, allDay, done, listId, list, color, writable, priority, members (ids), repeats}], by day, the ones without a time first."""
    q = {"status": "all", "from": start.isoformat(), "to": (end - dt.timedelta(days=1)).isoformat(), "limit": MAX_TASKS}
    if _tz(tz):
        q["tz"] = tz
    lists = {c["id"]: c for c in ask(request, "/api/lists").get("items", [])}
    out = []
    for t in ask(request, "/api/tasks", q).get("items", []):
        due = t.get("due")
        # a day (or a time) to show it on; the days are checked here too (an ioTask from before from= and to= sends every task)
        if not due or not (start - dt.timedelta(days=1)).isoformat() <= due[:10] <= end.isoformat():
            continue
        c = lists.get(t.get("listId")) or {}
        out.append({"id": t.get("id"), "title": t.get("title") or "(no title)", "due": due, "allDay": bool(t.get("dueAllDay")),
                    "done": bool(t.get("done")), "listId": t.get("listId"), "list": c.get("name"), "color": c.get("color"),
                    "writable": bool(c.get("writable")), "priority": t.get("priority"),
                    "members": [m.get("id") for m in t.get("members") or []],
                    "repeats": bool(t.get("rrule") or t.get("repeatAfter"))})
    out.sort(key=lambda t: (t["due"][:10], not t["allDay"], t["due"], t["title"].lower()))
    return out


def complete(request: Request, tid: int, done: bool = True, tz: str | None = None) -> dict:
    """Tick a task off (or open it again) in ioTask, as the viewer: {done, due, moved, title}. moved: a repeating task
    went on to its next day (due) instead of closing."""
    body = {"done": bool(done)}
    if _tz(tz):
        body["tz"] = tz
    t = ask(request, f"/api/tasks/{int(tid)}/complete", body=body)
    return {"id": t.get("id"), "title": t.get("title"), "done": bool(t.get("done")), "due": t.get("due"),
            "allDay": bool(t.get("dueAllDay")), "moved": bool(t.get("moved"))}
