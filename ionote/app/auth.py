"""The shared ioThing accounts (iothing-auth), as ionotes uses them.

Accounts, passwords, sessions and roles live in the suite's auth database (IOTHING_AUTH_DB_* in ionotes.env),
shared with ioPix and ioContacts: one sign-in serves every app on the domain (IOTHING_COOKIE_DOMAIN). What is
ionotes' own stays per app: the role an account holds here and its display settings.
"""
from iothing_auth.fastapi import Auth

from app import __version__, config

APP = "ionotes"


def _read_only() -> bool:
    from app import db
    return db.read_only()


# app_label, version, public_url, description, color and icon: ionotes' row in the suite's list of apps (ioSuite's start page)
auth = Auth(APP, read_only=_read_only, read_only_message="ionotes is in read-only mode; nothing can be changed.", app_label="ioNotes",
            version=__version__, public_url=config.PUBLIC_URL or None, description="Notes", color="#1c5a5e",
            icon="/static/icons/mark.svg")
auth.deny_exempt = ("/mcp",)  # MCP clients sign in with the admin token, whatever Cloudflare service token got them through
