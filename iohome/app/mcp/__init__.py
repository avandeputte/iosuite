"""The MCP server: lets an AI assistant (Claude, for example) look up the things in the house and keep their upkeep.

Served at /mcp by the web app (main.py) over streamable HTTP, and with `python -m app.mcp` over stdio. Every call acts as
one ioHome account and may do what that account may do in the web app; the server tools need an admin.

  base.py     the MCPServer instance, who is asking, and the shared helpers (finding a thing by name)
  items.py    the tools: overview, things, places, labels, upkeep and the maintenance log
  admin.py    the server: diagnostics
"""
from app.mcp.base import server, current_user
from app.mcp import items, admin  # noqa: F401  importing them registers the tools on `server`

__all__ = ["server", "current_user", "items", "admin"]
