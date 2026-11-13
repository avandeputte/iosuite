"""The MCP server: lets an AI assistant (Claude, for example) search, read and keep the family's contacts.

Served at /mcp by the web app (main.py) over streamable HTTP, and with `python -m app.mcp` over stdio. Every call acts as
one ioContact account, so it sees that account's books (the shared ones and its own private ones) and may change what
the account may change in the web app; the server tools need an admin.

  base.py   the MCPServer instance, who is asking, and the shared helpers (finding a contact or a book by name)
  read.py   the read-only tools: overview, search, one contact, relations and the family tree, birthdays, exports
  write.py  the tools that change contacts: create, update, relations, labels, favorites, move, merge, import, ioPix
  admin.py  the server: diagnostics, accounts
"""
from app.mcp.base import server, current_user
from app.mcp import read, write, admin  # noqa: F401  importing them registers the tools on `server`

__all__ = ["server", "current_user", "read", "write", "admin"]
