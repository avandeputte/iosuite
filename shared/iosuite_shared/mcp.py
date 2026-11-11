"""What every app's MCP server shares: the server instance, the annotations, who is asking, and the HTTP mount.

    from iosuite_shared import mcp as shared_mcp
    server = shared_mcp.make_server("iocalendar", "ioCalendar", __version__, instructions="...")
    current_user = shared_mcp.current_user                      # set per request by Auth.mcp_gate(on_user=current_user.set)
    @server.tool(annotations=shared_mcp.READ_ONLY)
    def overview(): u = shared_mcp.who(); ...
    shared_mcp.mount(app, server)                                # /mcp (streamable HTTP) ahead of the app's routes
    async with shared_mcp.running(server): yield                 # in the app's lifespan

MCP clients sign in like any other client of the suite: HTTP Basic with the user name and an app password, or a bearer
app password (Settings › Account); every tool acts as that account. The switch is a setting of the app
(`enabled(get_setting, forced)`): off until an admin turns it on under Settings › Server, or MCP=1 in the environment.
"""
import contextvars
import time
from contextlib import asynccontextmanager

import anyio

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from iosuite_shared import suiteupdates, users
from iosuite_shared.errors import Invalid

PATH = "/mcp"
SETTING = "mcp_enabled"
SETTINGS_PAGE = "Settings › Server"

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
# a tool that changes something but can be repeated with the same outcome (an edit, a setting)
WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
ADDS = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
DELETES = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)
UPDATES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)  # reaches GitHub

current_user: contextvars.ContextVar = contextvars.ContextVar("iosuite_mcp_user", default=None)  # set per request


def make_server(app: str, label: str, version: str, instructions: str) -> MCPServer:
    return MCPServer(app, title=label, version=version, instructions=instructions)


def who() -> dict:
    """The account the request acts as, or a ToolError that says how to sign in."""
    u = current_user.get()
    if not u:
        raise ToolError("Not signed in: connect with your user name and an app password (Settings › Account)")
    return u


def need_admin() -> dict:
    u = who()
    if not users.is_admin(u):
        raise ToolError("Only an admin can do this")
    return u


def need_suite_admin() -> dict:
    u = who()
    if not users.is_suite_admin(u):
        raise ToolError("Only a suite admin can do this")
    return u


def need_member() -> dict:
    """A member or more: may change their own private things."""
    u = who()
    if not users.is_member(u):
        raise ToolError("A viewer can only look; a member, editor or admin can change their own")
    return u


def need_writer() -> dict:
    """An editor or more: may change what is shared with everyone."""
    u = who()
    if not users.can_write(u):
        raise ToolError("Only an editor or admin can change this")
    return u


def add_suite_update_tools(server: MCPServer) -> None:
    """The start page's tools for updating every app of the suite at once (iosuite_shared.suiteupdates), suite admins
    only: suite_versions and update_suite_apps."""

    @server.tool(annotations=UPDATES)
    async def suite_versions(check: bool = True) -> dict:
        """Suite admins: every app of the suite with its installed version, the newest version on GitHub (status:
        current, update or error), whether it can update itself, and how its last update went (state: running, ok or
        failed, with a message). check True (the default) first has every app ask GitHub again, which takes up to half
        a minute; False answers from the last check."""
        u = need_suite_admin()

        def work():
            if check:
                since = time.time()
                asked = suiteupdates.request("check", None, by=u["name"])
                suiteupdates.wait_checked(asked, since)
            return suiteupdates.overview()
        apps = await anyio.to_thread.run_sync(work)
        return {"apps": apps, "updatesWaiting": [a["app"] for a in apps if a["status"] == "update"],
                "notWatching": [a["app"] for a in apps if not a["watching"]]}

    @server.tool(annotations=UPDATES)
    async def update_suite_apps(apps: list[str] | None = None) -> dict:
        """Suite admins: update apps of the suite to the newest version on GitHub. apps: their keys (iocalendar,
        ionotes...); left out, every app whose last check found a newer version (run suite_versions first). Each app
        runs its own update.sh within ten seconds and restarts (settings and data stay; its database is brought up to
        date as it starts). Call suite_versions(check=False) a minute or two later: state ok or failed, and the new
        version. Apps in Docker cannot update themselves (pull the image there)."""
        u = need_suite_admin()
        try:
            asked = await anyio.to_thread.run_sync(lambda: suiteupdates.request("update", apps, by=u["name"]))
        except Invalid as e:
            raise ToolError(str(e))
        if not asked:
            return {"asked": [], "note": "No app has an update waiting (suite_versions checks GitHub again)."}
        return {"asked": asked, "note": "Each app runs update.sh within ten seconds and restarts; call suite_versions(check=False) in a minute or two."}


def clamp(n, lo: int, hi: int) -> int:
    """A number a client asked for, kept between lo and hi (a page size: each tool's cap keeps its answer readable)."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = lo
    return max(lo, min(n, hi))


def enabled(get_setting, forced: bool = False) -> bool:
    """The switch: MCP=1 in the environment (`forced`) keeps it on; otherwise the app's `mcp_enabled` setting, off by
    default; off too while the settings cannot be read."""
    if forced:
        return True
    try:
        return get_setting(SETTING, "0") == "1"
    except Exception:  # noqa: BLE001  the database is away
        return False


def set_enabled(set_setting, on: bool, forced: bool = False) -> None:
    """Save the switch from POST /api/server {mcpEnabled}; ValueError when MCP=1 keeps it on."""
    if forced and not on:
        raise Invalid("MCP=1 in the environment keeps the MCP server on")
    set_setting(SETTING, "1" if on else "0")


def mount(app, server: MCPServer, path: str = PATH) -> None:
    """Serve the MCP server over streamable HTTP at `path` on the app's own port, ahead of every other route. The MCP
    library's own DNS rebinding protection is off: it takes a fixed list of hosts, and the apps are reached by LAN
    name, IP or a public name. Auth.mcp_gate does the check instead, with the names the app is known by, and every
    request is signed in anyway."""
    asgi = server.streamable_http_app(streamable_http_path=path, stateless_http=True,
                                      transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
    app.router.routes[:0] = list(asgi.routes)


@asynccontextmanager
async def running(server: MCPServer):
    """The server's session manager, for the app's lifespan. It may be started again in the same process (a test
    suite that starts the app once per test)."""
    sm = server.session_manager
    sm._has_started = False
    async with sm.run():
        yield
