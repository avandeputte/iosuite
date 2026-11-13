"""The shopping list, when ioTask is part of the suite: a recipe's ingredients become tasks in one of the viewer's
lists there.

Nothing to set up: ioTask is found in the suite's list of apps. It is asked on the viewer's behalf: the request goes
out from this server with the viewer's own credentials (the suite's shared session cookie, or the Authorization header
they came with), so ioTask offers the lists that person may add to and takes the tasks as theirs. Nothing is kept here.

ioTask is asked at the addresses the apps use for each other (iosuite_shared.links: localhost on this machine, its
address inside the network, its public one), with the suite's Cloudflare Access service token when one is set. One
that did not answer is left alone for BREAK_S seconds.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from fastapi import Request
from iosuite_shared import links, sessions
from iosuite_shared.errors import Invalid

APP, PROVIDER = "iorecipe", "iotask"
TIMEOUT = 8     # seconds, per request
BREAK_S = 30    # seconds ioTask is left alone after it did not answer
MAX_LINES = 200
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
    h = {"User-Agent": "ioRecipe", "Accept": "application/json", "Accept-Encoding": "identity"}
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
            raise Unavailable(502, f"ioTask answered {e.code}")
        except (urllib.error.URLError, OSError, ValueError) as e:
            why = type(e).__name__
    _state["down"] = time.monotonic() + BREAK_S
    raise Unavailable(502, f"ioTask is not reachable ({why})")


def lists(request: Request) -> list[dict]:
    """The viewer's lists in ioTask that take new tasks: [{id, name, shared}]."""
    got = ask(request, "/api/lists")
    return [{"id": c["id"], "name": c["name"], "shared": bool(c.get("shared"))} for c in got.get("items") or [] if c.get("writable")]


def add(request: Request, list_id, lines, recipe_title: str, link: str | None = None) -> int:
    """Each line a task in that list, with the recipe it is for in its notes (and its address). How many were added."""
    if not isinstance(lines, list):
        raise Invalid("lines: a list of ingredients is expected")
    todo = [" ".join(str(x).split())[:500] for x in lines if isinstance(x, str) and x.strip()]
    if not todo:
        raise Invalid("Nothing to add: tick at least one ingredient")
    if len(todo) > MAX_LINES:
        raise Invalid("That is too many lines for one go")
    if not str(list_id or "").isdigit():
        raise Invalid("Which list?")
    n = 0
    for line in todo:
        ask(request, "/api/tasks", {"list": str(list_id)}, {"title": line, "notes": f"For {recipe_title}", **({"url": link} if link else {})})
        n += 1
    return n
