"""The conventions every app of the suite follows (iosuite_shared.testing): the port, one version, config.env, and an
access marker on every API route."""
import os
from pathlib import Path

from iosuite_shared import testing

from app import __version__, access, config

ROOT = Path(__file__).resolve().parent.parent


def test_suite_conventions():
    testing.check_conventions(ROOT, "ionotes", __version__, config)


def test_every_api_route_declares_who_may_call_it(app):
    testing.check_access_declared(app, access.declared)


def test_standard_paths():
    assert config.APP_DIR == ROOT and config.STATIC_DIR == ROOT / "static"
    assert config.DATA_DIR == Path(os.environ["DATA_DIR"]).resolve()  # the tests' scratch folder
    assert config.LOG_FILE is None  # LOG_FILE= in the tests' environment
