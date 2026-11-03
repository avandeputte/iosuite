"""python -m app.mcp: the MCP server on stdio, on the same database as the web app."""
from app.mcp import server

if __name__ == "__main__":
    server.run()
