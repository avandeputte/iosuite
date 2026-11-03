"""MCP server for ionotes, in the same shape as iopix's.

Lets an MCP client such as Claude search the notes, read any note (and look at its picture), list folders and
tags, and, with the admin token, write: create, edit, file, tag, pin and delete notes, manage folders and tag
colours, plus the operator's tools (diagnostics, the server log, the change log, proxy sign-in, the updater).
It is served at /mcp by the web app (main.py) and can also run on its own with `python -m app.mcp` (stdio),
on the same database.

  base.py   the MCPServer instance, the admin-token gate and the helpers the tool modules share
  read.py   the read-only tools anyone the sign-in rule lets in may call
  write.py  the tools that change notes, folders and tags (admin token)
  files.py  the operator's diagnostics and the updater (admin token)
"""
from app.mcp.base import server, token_given
from app.mcp import read, write, files  # noqa: F401  importing them registers the tools on `server`

__all__ = ["server", "token_given", "read", "write", "files"]
