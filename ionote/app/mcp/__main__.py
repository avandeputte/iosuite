"""python -m app.mcp: the MCP server on stdio, on the same database as the web app.

Whoever can start it can already read the database, so it works as the HTTP endpoint does with the admin token:
on the notes of Settings › MCP server › Notes of (the first admin by default). Writes still take the token."""
from app import db, notes, owners, users
from app.mcp import base, server

if __name__ == "__main__":
    db.init()
    users.init()
    if users.any_users():
        notes.claim_unowned(owners.first_admin_id())
    notes.current_owner.set(owners.mcp_owner())
    base.token_given.set(True)
    server.run()
