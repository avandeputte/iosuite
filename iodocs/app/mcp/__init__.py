"""The MCP server: lets an AI assistant (Claude, for example) look up the family's documents and when they expire.

Served at /mcp by the web app (main.py) over streamable HTTP, and with `python -m app.mcp` over stdio. Every call acts as
one ioDocs account and sees and may do what that account may in the web app; the server tools need an admin.

  base.py     the MCPServer instance, who is asking, and the shared helpers (finding a document by title)
  docs.py     the tools: overview, documents, what expires, adding and changing them
  admin.py    the server: diagnostics
"""
from app.mcp.base import server, current_user
from app.mcp import docs, admin  # noqa: F401  importing them registers the tools on `server`

__all__ = ["server", "current_user", "docs", "admin"]
