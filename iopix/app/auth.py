"""The shared ioThing accounts (iosuite-shared), as iopix uses them.

Accounts, passwords, sessions and roles live in the Shared ioSuite database (IOSUITE_DB_* in config.env), shared
with ioNote and ioContact: one sign-in serves every app on the domain (COOKIE_DOMAIN). What is iopix's
own stays per app: the role an account holds here, its display settings, and the digiKam person it is linked to
(the face badge on the sign-in screen), kept as the "person" value of the account's iopix data.
"""
from iosuite_shared.fastapi import Auth
from iosuite_shared import users as shared
from iosuite_shared.updates import Updater

from app import __version__, config
from iosuite_shared.errors import Invalid

APP = config.APP


# the version, address, colour and icon register iopix in the suite's list of apps (suite_apps, at the first request),
# where the start page and the other apps find it
auth = Auth(APP, app_label="ioPix",
            version=__version__, public_url=config.PUBLIC_URL or None, description="Photos", color="#3b4a8c")
auth.deny_exempt = ("/mcp",)  # MCP clients sign in with an app password, whatever Cloudflare service token got them through


# updates (the daily check, update.sh, restart) and the server log, as in every app of the suite (iosuite_shared.updates)
updater = Updater(APP, __version__, config.APP_DIR, repo=config.IOPIX_REPO, branch=config.IOPIX_BRANCH, result_file=config.DATA_DIR / ".update-result", user_agent="iopix")


def decorate(u):
    """The user dict iopix serves: the shared fields plus the linked person tag."""
    if u is None:
        return None
    u = dict(u)
    u["person"] = shared.get_value(u["id"], APP, "person")
    return u


auth.decorate = decorate


def person_tag(tag_id) -> bool:
    """Is this a person tag in the index (a tag under People with digiKam's person property)?"""
    if not tag_id:
        return True
    from app.runtime import db
    con = db()
    try:
        r = con.execute("SELECT person FROM tags WHERE id = ?", (int(tag_id),)).fetchone()
        return bool(r and r[0])
    finally:
        con.close()


def set_person(user_id: int, tag_id):
    """Link the account to a digiKam person tag (None unlinks). The caller checks the tag is a person."""
    shared.set_value(user_id, APP, "person", int(tag_id) if tag_id else None)
    shared.invalidate()


def _on_update(user_id: int, body: dict):
    """The old /api/users/{id} may also send {person}: the account's face badge (now set from Settings › Security › People)."""
    if "person" in body:
        if not person_tag(body["person"]):
            raise Invalid("That tag is not a person")
        set_person(user_id, body["person"])


auth.on_update = _on_update


def _person_data(user_id: int, remove: bool) -> list:
    """What the person keeps here, when a suite admin deletes their account (iosuite_shared.persondata)."""
    from app import persondata
    return persondata.of(user_id, remove)


auth.person_data = _person_data
