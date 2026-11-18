"""The script that sets the suite's version on main (.github/scripts/version.py): which number goes up, and what
counts as a change that reaches an install."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "version.py"
pytestmark = pytest.mark.skipif(not SCRIPT.is_file(), reason="not a checkout of the suite's repository")


@pytest.fixture(scope="module")
def version():
    spec = importlib.util.spec_from_file_location("version_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_reads_the_line_the_updater_reads(version):
    from iosuite_shared import __version__, updates
    text = (SCRIPT.parents[2] / version.VERSION_FILE).read_text()
    assert "%d.%d.%d" % version.version_in(text) == __version__ == updates.VERSION_RE.search(text).group(1)
    assert version.VERSION_FILE == updates.VERSION_FILE


def test_which_number_goes_up(version):
    assert version.raised((3, 19, 1), 2) == (3, 19, 2)
    assert version.raised((3, 19, 1), 1) == (3, 20, 0)
    assert version.raised((3, 19, 1), 0) == (4, 0, 0)
    labels = {7: ["feature"], 8: ["Major", "feature"], 9: ["docs"]}
    ask = lambda n: [x.lower() for x in labels.get(n, [])]  # noqa: E731
    assert version.part_for([{"number": 9}, {"number": None}], ask) == 2
    assert version.part_for([{"number": 9}, {"number": 7}], ask) == 1
    assert version.part_for([{"number": 7}, {"number": 8}], ask) == 0


def test_what_reaches_an_install(version):
    for path in ("iomoney/app/api.py", "shared/iosuite_shared/db.py", "demo/iosuite_demo/iotask.py", "install.sh",
                 "docker-compose.yml", "iocalendar/README.md", "iopix/site/build.sh"):
        assert version.reaches_installs(path), path
    for path in ("docs/docs/index.md", ".github/workflows/iotask.yml", ".github/scripts/version.py", "README.md",
                 "LICENSE", ".gitignore", ".dockerignore"):
        assert not version.reaches_installs(path), path
