#!/bin/sh
# Read-only MCP server (stdio) for the digiKam library. Point an MCP client at this script;
# it uses the same .venv and data/ as the web app and does not need the web app running.
# Nothing is installed or downloaded.
cd "$(dirname "$0")" || exit 1
exec .venv/bin/python -m app.mcp_server "$@"
