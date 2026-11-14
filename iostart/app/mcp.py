"""The suite's one MCP server (/mcp on the start page): ioStart's own tools (updating every app at once, suite admins:
iosuite_shared.mcp.add_suite_update_tools) and every other app's tools, so an assistant connected here can do a job
that spans apps ("put Friday's dinner ingredients on the shopping list") with one connection and one app password.

An assistant signs in with a user name and an ioStart app password (Settings › Account), like any other MCP client of
the suite; the switch is at Settings › Server. The other apps' tools are listed under the app's key and an underscore
(iocalendar_add_event, iotask_add_task...). A call is passed on to that app's own MCP server as the same person,
with the same sign-in: every app takes an ioStart app password at its /mcp (iosuite_shared.apppasswords.HUB), so each
app still decides what this person may see and change there, exactly as when the assistant talks to it directly. An
app whose MCP server is switched off (its own Settings › Server), or where the person has no role, offers nothing.
The start page reaches each app as iosuite_shared.links does: localhost on the same machine, then its internal
address, then its public one, with the suite's Cloudflare Access service token when there is one.
"""
import contextvars
import hashlib
import logging
import time

import anyio
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp.shared.exceptions import MCPError
from mcp_types import CallToolResult, TextContent, Tool

from iosuite_shared import links, suite
from iosuite_shared import mcp as shared_mcp

from app import __version__, config

log = logging.getLogger("iostart.mcp")

LIST_TIMEOUT_S = 8      # an app that does not list its tools by then is left out of this listing
CALL_TIMEOUT_S = 300    # a tool may take a while (suite updates, a photo search)
CACHE_S = 60            # each person's view of each app's tools, kept this long
SEP = "_"               # iocalendar_add_event: app keys have no underscore, so the first one splits

current_user = shared_mcp.current_user
# the Authorization header the assistant signed in here with, passed on to the other apps (set by Auth.mcp_gate)
signed_in_with: contextvars.ContextVar = contextvars.ContextVar("iostart_mcp_authorization", default=None)

_views: dict = {}  # (sign-in hash, app) -> (at, view)


def remember_sign_in(request) -> None:
    signed_in_with.set(request.headers.get("authorization"))


class SuiteServer(MCPServer):
    """An MCP server whose tool list is its own tools plus every other app's, for the person asking."""

    async def list_tools(self) -> list[Tool]:
        own = await super().list_tools()
        views = await _all_views()
        return own + [t for v in views for t in v["tools"]]

    async def call_tool(self, name, arguments, context=None):
        if self._tool_manager.get_tool(name) is not None:
            return await super().call_tool(name, arguments, context)
        app, _, tool = name.partition(SEP)
        if not tool or app not in {a["app"] for a in _apps()}:
            raise ToolError(f"Unknown tool: {name}")
        return await _call(app, tool, arguments or {})


INSTRUCTIONS = (
    "The ioThing suite in one place: the start page (ioStart) and every app of the suite (ioCalendar, ioTask, "
    "ioRecipe, ioNote, ioContact, ioPix...). Each app's tools are named after the app: iocalendar_..., iotask_..., "
    "iorecipe_... and act as you in that app, with your role there, so a job can span apps (read a recipe, then add "
    "its ingredients to a shopping list). suite_apps lists the apps you can use here, how to use each one (its own "
    "instructions) and why an app offers no tools (its MCP server is switched off there, or you have no access). "
    "ioStart's own: suite_version gives the installed version of the suite (one for every app), the newest on GitHub "
    "and status; update_suite updates every app that is behind (suite admins only)."
)

server = SuiteServer(config.APP, title="ioSuite", version=__version__, instructions=INSTRUCTIONS)
shared_mcp.add_suite_update_tools(server)


@server.tool(annotations=shared_mcp.READ_ONLY)
async def suite_apps() -> dict:
    """apps: the apps of the suite this MCP server passes calls on to, one line each: app (the prefix of its tools), name,
    status (ok; off: its MCP server is switched off in that app's Settings › Server; no_access: you have no role
    there; no_mcp: it has no MCP server; unreachable: it did not answer; sign_in: connect here with an ioStart app
    password so calls can be passed on), tools (how many), and instructions (how that app's tools fit together: read
    them before using an app's tools for the first time)."""
    shared_mcp.who()
    return {"apps": [{"app": v["app"], "name": v["name"], "status": v["status"], "detail": v.get("detail") or "",
             "tools": len(v["tools"]), "instructions": v.get("instructions") or ""} for v in await _all_views(fresh=True)]}


# ---- the other apps

def _apps() -> list:
    """The apps the person may use, other than the start page itself."""
    u = current_user.get()
    if not u:
        return []
    return [a for a in suite.visible(u) if a["app"] != config.APP]


def _key(app: str) -> tuple:
    h = hashlib.sha256(f"{(current_user.get() or {}).get('id')}\0{signed_in_with.get() or ''}".encode()).hexdigest()
    return h, app


async def _all_views(fresh: bool = False) -> list:
    apps = await anyio.to_thread.run_sync(_apps)
    out: list = [None] * len(apps)

    async def one(i, a):
        out[i] = await _view(a, fresh)

    async with anyio.create_task_group() as tg:
        for i, a in enumerate(apps):
            tg.start_soon(one, i, a)
    return out


async def _view(a: dict, fresh: bool = False) -> dict:
    """What one app offers this person: {app, name, status, detail, instructions, tools (named with the app's prefix)}."""
    key, now = _key(a["app"]), time.time()
    hit = _views.get(key)
    if hit and not fresh and now - hit[0] < CACHE_S:
        return hit[1]
    view = {"app": a["app"], "name": a["name"] or a["app"], "status": "ok", "detail": "", "instructions": "", "tools": []}
    if not signed_in_with.get():
        view.update(status="sign_in", detail="Connect to ioStart's MCP server with an ioStart app password (Settings › Account) "
                                             "so calls can be passed on to the other apps.")
    else:
        try:
            with anyio.fail_after(LIST_TIMEOUT_S):
                async with _client(a["app"], LIST_TIMEOUT_S) as c:
                    listed = await c.list_tools()
                    view["instructions"] = c.instructions or ""
            prefix = f"[{view['name']}] "
            view["tools"] = [t.model_copy(update={"name": a["app"] + SEP + t.name,
                                                  "title": prefix + (t.title or t.name),
                                                  "description": prefix + (t.description or "")}) for t in listed.tools]
        except Exception as e:  # noqa: BLE001  the app is off, away, or this person may not use it
            view.update(await _why(a["app"], e))
    if len(_views) > 500:
        _views.clear()
    _views[key] = (now, view)
    return view


async def _headers(app: str) -> dict:
    h = await anyio.to_thread.run_sync(lambda: links.headers(config.APP, app, sign_in=False))  # Cloudflare Access only
    h["Authorization"] = signed_in_with.get() or ""
    h["User-Agent"] = f"ioStart/{__version__} (the suite's MCP server)"
    return h


class _client:
    """An MCP client of one app's /mcp, signed in as the person asking: localhost, then its internal address, then its
    public one (links.addresses), moving on when an address does not answer."""

    def __init__(self, app: str, read_s: float):
        self.app, self.read_s, self.http, self.client = app, read_s, None, None

    async def __aenter__(self) -> Client:
        bases = await anyio.to_thread.run_sync(links.addresses, self.app)
        if not bases:
            raise LookupError("no_address")
        headers = await _headers(self.app)
        last = None
        for base in bases:
            http = create_mcp_http_client(headers=headers, timeout=httpx2.Timeout(10, read=self.read_s))
            client = Client(streamable_http_client(base + shared_mcp.PATH, http_client=http), read_timeout_seconds=self.read_s,
                            client_info=None, cache=None)
            try:
                await http.__aenter__()
                await client.__aenter__()
            except Exception as e:  # noqa: BLE001
                last = e
                await http.__aexit__(None, None, None)
                if not _unreachable(e):
                    raise
                log.info("MCP: %s does not answer at %s (%s)", self.app, base, e)
                continue
            self.http, self.client = http, client
            return client
        raise last or LookupError("unreachable")

    async def __aexit__(self, *exc):
        try:
            await self.client.__aexit__(*exc)
        finally:
            await self.http.__aexit__(*exc)


def _unreachable(e: BaseException) -> bool:
    """Whether the address did not answer at all (so the next one is worth trying)."""
    for x in _chain(e):
        if isinstance(x, (httpx2.ConnectError, httpx2.ConnectTimeout, OSError)):
            return True
    return False


def _chain(e: BaseException):
    seen = set()
    stack = [e]
    while stack:
        x = stack.pop()
        if x is None or id(x) in seen:
            continue
        seen.add(id(x))
        yield x
        stack.extend(getattr(x, "exceptions", ()) or ())
        stack.extend([x.__cause__, x.__context__])


async def _why(app: str, e: BaseException) -> dict:
    """Why an app offers nothing: asks its /mcp once more with a plain request to tell the cases apart."""
    if isinstance(e, LookupError) and str(e).strip("'") == "no_address":
        return {"status": "unreachable", "detail": "It has no address the start page may call (INTERNAL_URL or PUBLIC_URL)."}
    if isinstance(e, TimeoutError) or _unreachable(e):
        return {"status": "unreachable", "detail": "It did not answer."}
    try:
        bases = await anyio.to_thread.run_sync(links.addresses, app)
        async with httpx2.AsyncClient(timeout=5) as http:
            r = await http.post(bases[0] + shared_mcp.PATH, headers={**await _headers(app), "Content-Type": "application/json",
                                                                      "Accept": "application/json, text/event-stream"},
                                json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
        detail = ""
        try:
            detail = str(r.json().get("detail") or "")
        except Exception:  # noqa: BLE001
            pass
        if r.status_code == 404:
            if "switched off" in detail:
                return {"status": "off", "detail": "Its MCP server is switched off (Settings › Server in that app)."}
            return {"status": "no_mcp", "detail": "It has no MCP server."}
        if r.status_code in (401, 403):
            return {"status": "no_access", "detail": detail[:200] or "It did not take your sign-in."}
    except Exception:  # noqa: BLE001
        pass
    log.info("MCP: %s offers no tools: %r", app, e)
    return {"status": "unreachable", "detail": str(e)[:200] or type(e).__name__}


async def _call(app: str, tool: str, arguments: dict) -> CallToolResult:
    if not signed_in_with.get():
        raise ToolError("Connect to ioStart's MCP server with an ioStart app password (Settings › Account) to use the other apps' tools")
    try:
        with anyio.fail_after(CALL_TIMEOUT_S):
            async with _client(app, CALL_TIMEOUT_S) as c:
                return await c.call_tool(tool, arguments)
    except MCPError as e:  # the app answered with an error of its own
        return CallToolResult(content=[TextContent(type="text", text=f"{app}: {e}")], is_error=True)
    except Exception as e:  # noqa: BLE001
        why = await _why(app, e)
        log.info("MCP: %s_%s could not be passed on: %s", app, tool, why)
        return CallToolResult(content=[TextContent(type="text", text=f"{app}: {why['detail']}")], is_error=True)


def forget() -> None:
    _views.clear()
