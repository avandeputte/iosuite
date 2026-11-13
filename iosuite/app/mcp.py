"""The start page's MCP server (/mcp): updating every app of the suite at once, for suite admins
(iosuite_shared.mcp.add_suite_update_tools). An assistant signs in with a user name and an ioSuite app password
(Settings › Account), like any other MCP client of the suite; the switch is at Settings › Server."""
from iosuite_shared import mcp as shared_mcp

from app import __version__, config

server = shared_mcp.make_server(
    config.APP, "ioSuite", __version__,
    instructions=(
        "The start page of the ioThing suite (ioSuite). It keeps every io app up to date: suite_versions lists each app "
        "with its installed version, the newest on GitHub (status: current, update or error), whether it can update "
        "itself and how its last update went; update_suite_apps updates the apps that have an update waiting (or the "
        "ones named). Each app updates and restarts within a minute or two; then call suite_versions(check=False) to "
        "see state ok or failed and the new version. Suite admins only."
    ),
)
current_user = shared_mcp.current_user
shared_mcp.add_suite_update_tools(server)
