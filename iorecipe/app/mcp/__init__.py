"""The MCP server: lets an AI assistant (Claude, for example) look up and keep the family's recipes.

Served at /mcp by the web app (main.py) over streamable HTTP, and with `python -m app.mcp` over stdio. Every call acts as
one ioRecipe account, so it sees that account's recipes (the family's and its own private ones) and may change what the
account may change in the web app; the server tools need an admin.

  base.py     the MCPServer instance, who is asking, and the shared helpers (finding a recipe by name)
  recipes.py  the recipe tools: overview, list, search, one recipe, add, change, delete, import from a web page
  admin.py    the server: diagnostics, the version check and the update
"""
from app.mcp.base import server, current_user
from app.mcp import recipes, admin  # noqa: F401  importing them registers the tools on `server`

__all__ = ["server", "current_user", "recipes", "admin"]
