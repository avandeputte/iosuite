"""The MCP server: lets an AI assistant (Claude, for example) read and keep the family's calendars.

Served at /mcp by the web app (main.py) over streamable HTTP, and with `python -m app.mcp` over stdio. Every call acts as
one ioCalendar account, so it sees that account's calendars (the shared ones and its own private ones) and may change
what the account may change in the web app; the server tools need an admin.

  base.py   the MCPServer instance, who is asking, and the shared helpers (finding a calendar or an event by name)
  read.py   the read-only tools: overview, calendars, the agenda, search, one event, free/busy, connection details
  write.py  the tools that change events and calendars: create, update (series, one occurrence, or from one on),
            delete, move, new calendar, import
  admin.py  the server: diagnostics, the version check and the update, the Birthdays calendar from ioContacts
"""
from app.mcp.base import server, current_user
from app.mcp import read, write, admin  # noqa: F401  importing them registers the tools on `server`

__all__ = ["server", "current_user", "read", "write", "admin"]
