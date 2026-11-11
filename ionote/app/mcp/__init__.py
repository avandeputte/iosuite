"""MCP server for ionotes, in the same shape as iopix's.

Lets an MCP client such as Claude search the notes, read any note (and look at its picture), list folders and
tags, and, as a member, write: create, edit, file, tag, pin and delete notes, manage folders and tag
colours, plus the operator's tools (diagnostics, the server log, the change log, proxy sign-in, the updater).
It is served at /mcp by the web app (main.py) and can also run on its own with `python -m app.mcp` (stdio),
on the same database.

  base.py   the MCPServer instance, the admin-token gate and the helpers the tool modules share
  read.py   the read-only tools, on the signed-in account's own notes
  write.py  the tools that change notes, folders and tags (members)
  files.py  the operator's diagnostics and the updater (admins)
  prompts.py  ready-made requests (summarise a note, a weekly review, tidy up)
"""
from app.mcp.base import server, current_user
from app.mcp import read, write, files, prompts  # noqa: F401  importing them registers the tools and prompts on `server`

__all__ = ["server", "current_user", "read", "write", "files", "prompts"]
