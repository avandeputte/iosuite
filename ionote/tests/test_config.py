"""The settings conventions every app of the suite shares."""
from pathlib import Path

from iosuite_shared import suite

from app import __version__, config

ROOT = Path(__file__).resolve().parent.parent


def test_default_port_is_the_suites():
    assert config.PORT == suite.PORTS["ionotes"] == 8610
    for f in ("Dockerfile", "docker-compose.yml", "config.env.example", "run.sh"):
        assert "8610" in (ROOT / f).read_text(), f


def test_one_version_everywhere():
    assert f'version = "{__version__}"' in (ROOT / "pyproject.toml").read_text()


def test_settings_file_is_config_env():
    assert "config.env" in (ROOT / ".gitignore").read_text().split()
    for f in ("setup.sh", "update.sh", "README.md"):
        assert "ionotes.env" not in (ROOT / f).read_text(), f
