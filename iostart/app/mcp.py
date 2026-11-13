"""The start page's MCP server (/mcp): updating every app of the suite at once, for suite admins
(iosuite_shared.mcp.add_suite_update_tools). An assistant signs in with a user name and an ioStart app password
(Settings › Account), like any other MCP client of the suite; the switch is at Settings › Server."""
from iosuite_shared import mcp as shared_mcp

from app import __version__, config

server = shared_mcp.make_server(
    config.APP, "ioStart", __version__,
    instructions=(
        "The start page of the ioThing suite (ioStart). It keeps the suite up to date: the suite has one version, the "
        "same for every app. suite_version gives the installed version, the newest on GitHub and status (current, "
        "update, updating or error), with every app's own line under apps; update_suite updates every app that is "
        "behind. Each app updates and restarts within a minute or two; then call suite_version(check=False) to see "
        "status current, or which apps failed and why. Suite admins only."
    ),
)
current_user = shared_mcp.current_user
shared_mcp.add_suite_update_tools(server)
