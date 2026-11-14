"""The shopping list, when ioTask is part of the suite: a recipe's ingredients become tasks in one of the viewer's
lists there.

Nothing to set up: ioTask is found in the suite's list of apps. It is asked on the viewer's behalf: the request goes
out from this server with the viewer's own credentials (the suite's shared session cookie, or the Authorization header
they came with), so ioTask offers the lists that person may add to and takes the tasks as theirs. Nothing is kept here.

ioTask is asked on the viewer's behalf (iosuite_shared.links.as_viewer: localhost on this machine, its
address inside the network, its public one), with the suite's Cloudflare Access service token when one is set. One
that did not answer is left alone for links.BREAK_S seconds.
"""
import json
import urllib.error

from fastapi import Request
from iosuite_shared import links
from iosuite_shared.errors import Invalid

PROVIDER = "iotask"
TIMEOUT = 8     # seconds, per request
MAX_LINES = 200


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
    links.ask_again(PROVIDER)


def ask(request: Request, path: str, params: dict | None = None, body: dict | None = None):
    """GET path from ioTask as the viewer (with body: POST that JSON); its JSON answer, or Unavailable."""
    if not enabled():
        raise Unavailable(404, "ioTask is not part of the suite")
    if links.resting(PROVIDER):
        raise Unavailable(502, "ioTask did not answer a moment ago")
    try:
        return links.as_viewer(request, PROVIDER, path, params, body, timeout=TIMEOUT, user_agent="ioRecipe")
    except urllib.error.HTTPError as e:  # it answered
        if e.code in (401, 403) and body is None:
            raise Unavailable(403, "ioTask does not let this account in: open it once and sign in there")
        try:
            detail = json.loads(e.read()).get("detail")
        except (ValueError, AttributeError):
            detail = None
        if e.code in (400, 403, 404, 409, 412) and isinstance(detail, str):
            raise Unavailable(e.code, detail)  # its own word on what it would not take
        raise Unavailable(502, f"ioTask answered {e.code}")
    except links.Unreachable as e:
        raise Unavailable(502, f"ioTask is not reachable ({type(e.why).__name__ if e.why else 'no address'})")


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
