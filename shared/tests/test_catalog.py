"""The apps' manifests (<app>/app.json) and what is made from them, without a database."""
import json
from pathlib import Path

import pytest

from iosuite_shared import catalog, install, push, related, suite

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def fresh_db():
    """Overrides conftest's autouse database fixture: nothing here needs MariaDB."""
    yield


def test_every_app_folder_has_a_manifest_and_apps_json_holds_them():
    folders = sorted(p.parents[1].name for p in ROOT.glob("io*/app/__init__.py"))
    assert sorted(catalog.APPS) == folders
    assert catalog.dumps(catalog.gather(ROOT)) == catalog.FILE.read_text(), "run shared/templates/render.py"


def test_the_lists_read_the_manifests():
    assert suite.PORTS == {k: m["port"] for k, m in catalog.APPS.items()}
    assert suite.FOLDERS["iocalendar"] == "calendar" and "iostart" not in suite.FOLDERS
    assert list(install.APPS) == catalog.install_order() and list(install.APPS)[-1] == "iopix"
    assert install.APPS["iocalendar"] == {"label": "ioCalendar", "port": 8620, "env": "IOCALENDAR"}
    assert install.APPS["iopix"]["photos"] is True
    assert related.KINDS["note"] == {"app": "ionote", "label": "Note", "plural": "Notes", "href": "#/note/{id}", "id": "uuid"}
    assert {k["kind"] for k in push.KINDS} >= {"events", "tasks", "birthdays", "backups", "updates"}
    assert push.KIND["backups"]["admin"] and push.KIND["backups"]["app"] == "iobackup"


def test_validate_refuses_clashes():
    a = {"key": "ioone", "name": "ioOne", "description": "One", "color": "#123456", "port": 8800, "order": 1}
    b = dict(a, key="iotwo", name="ioTwo")
    with pytest.raises(ValueError, match="port 8800"):
        catalog.validate([a, b])
    with pytest.raises(ValueError, match="folder 'x'"):
        catalog.validate([dict(a, folder="x")])
    with pytest.raises(ValueError, match="kind event"):
        catalog.validate([dict(a, items=[{"kind": "event", "label": "E", "plural": "Es", "href": "#/e/{id}"}]),
                          dict(b, port=8801, items=[{"kind": "event", "label": "E", "plural": "Es", "href": "#/e/{id}"}])])
    with pytest.raises(ValueError, match="color"):
        catalog.validate([dict(a, color="red")])
    assert [m["key"] for m in catalog.validate([dict(b, port=8801, order=0), a])] == ["iotwo", "ioone"]


def test_the_docker_stack_has_every_app():
    """The whole suite in one stack (the repository's docker-compose.yml): every app but the admin tools."""
    stack = (ROOT / "docker-compose.yml").read_text()
    for k in (k for k, m in catalog.APPS.items() if not m.get("adminTool")):
        assert f"\n  {k}:" in stack, f"docker-compose.yml has no service {k}"
        assert f"CREATE DATABASE IF NOT EXISTS {k} " in stack, f"docker-compose.yml makes no database {k}"


def test_every_app_has_its_files():
    for k, m in catalog.APPS.items():
        assert (ROOT / k / "proxmox" / "ct" / f"{k}.sh").is_file(), f"{k} has no Proxmox script"
        assert (ROOT / k / "docker-compose.yml").is_file(), f"{k} has no docker-compose.yml"
        assert json.loads((ROOT / k / "app.json").read_text())["key"] == k
