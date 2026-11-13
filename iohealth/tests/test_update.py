"""Settings › Server (iosuite_shared's server_router): admins only. Updating is the suite's (Settings › Global settings ›
Updates), so the app's status carries no update of its own and its Server page only restarts."""
from app import __version__


def test_status_has_the_version_and_no_update_of_its_own(client, admin):
    s = client.get("/api/status").json()
    assert s["version"] == __version__ and s["commit"] and "update" not in s


def test_a_viewer_gets_no_server_page(client, admin):
    client.post("/api/users", json={"name": "bo", "password": "secretpw2", "role": "viewer"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "bo", "password": "secretpw2"})
    assert client.get("/api/server").status_code == 403
    assert client.post("/api/server", json={"action": "restart"}).status_code == 403


def test_server_status(client, admin):
    s = client.get("/api/server").json()
    assert s["version"] == __version__ and s["installed"] and isinstance(s["canRun"], bool)
    assert s["progress"]["running"] is False and s["repo"] and s["branch"] and "about" not in s and "autoCheck" not in s
    assert client.post("/api/server", json={"action": "update"}).status_code == 400  # one update, for the suite

    assert client.get("/api/log").status_code in (200, 404)  # the server log, when the test writes one


def test_the_server_log_is_for_admins_only(client, admin):
    client.post("/api/users", json={"name": "bo", "password": "secretpw2", "role": "viewer"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "bo", "password": "secretpw2"})
    assert client.get("/api/log").status_code in (403, 404)  # 404: the route is not registered without a log file (LOG_FILE= in the tests)


def test_settings_server_is_the_shared_panel(client, admin):
    """Settings › Server is iosuite-shared's panel: its module, with no This server box."""
    assert "export async function mount" in client.get("/api/server/ui.js").text
    s = client.get("/api/server").json()
    assert s["name"] == "ioHealth" and "about" not in s
    assert client.post("/api/auth/logout_all").status_code in (404, 405)  # Sign out is the only sign out
