"""The MCP server: lets an AI assistant (Claude, for example) read and keep the household's finances.

Served at /mcp by the web app (main.py) over streamable HTTP, and with `python -m app.mcp` over stdio. Every call acts as
one ioMoney account, so it sees what that account sees (nothing without a role here) and may change what the account
may change in the web app; the server tools need an admin.

  base.py   the MCPServer instance, who is asking, and the shared helpers (finding an account by name)
  money.py  the tools: overview, net worth, transactions, spending, portfolio and quotes, accounts, values, bills, sync
  admin.py  the server: diagnostics
"""
from app.mcp.base import server, current_user
from app.mcp import money, admin  # noqa: F401  importing them registers the tools on `server`

__all__ = ["server", "current_user", "money", "admin"]
