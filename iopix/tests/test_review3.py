"""The lower findings of the code review of 10 November 2026 that need no library: making a backup is a POST, every
route carries its access marker (tests/test_access.py holds the table), and the names from before the rename are gone."""
from fastapi.routing import APIRoute

from app import access
from app.routes import backup, images, organize, settings, tools


def test_a_backup_is_made_by_a_post():
    """It writes a dump of hundreds of megabytes: a link or an image on another site cannot start one."""
    routes = [r for r in backup.router.routes if isinstance(r, APIRoute)]
    assert [(r.path, sorted(r.methods)) for r in routes] == [("/api/backup/{which}", ["POST"])]
    assert access.declared(routes[0])[0] == "admin"


def test_the_video_and_share_routes_declare_their_access():
    paths = {r.path: r for mod in (images, organize) for r in mod.router.routes if isinstance(r, APIRoute)}
    for p in ("/video/{photo_id}/frame", "/video/{photo_id}.mp4", "/share"):
        assert access.declared(paths[p]) is not None, p


def test_the_names_from_before_the_rename_are_gone():
    paths = [r.path for mod in (settings, tools) for r in mod.router.routes if isinstance(r, APIRoute)]
    assert not [p for p in paths if "viewerdb" in p or "maintenance" in p]
    assert {"/api/database", "/api/database/test", "/api/database/switch", "/api/database/retry", "/api/tools"} <= set(paths)
    from app.mcp import files
    assert not hasattr(files, "update_viewer") and not hasattr(files, "update_server")  # updating is the suite's
