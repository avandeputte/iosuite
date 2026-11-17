"""The demo switch: what every install carries of the suite's demo data (a made-up family of four, the Calloways,
with something in every app). The demo data itself is a package of its own, iosuite_demo (the repository's demo/
folder), never installed: an app fetches it only when it needs it.

  * The switch is one suite-wide setting in the Shared ioSuite database (ios_settings 'demo'), set by
    `iosuite-shared demo` (an installed server) or `iosuite-shared stack --demo` (a Docker stack, what the compose file
    builder's "Fill it with demo data" box writes).
  * At start, after its tables are made, every app calls `at_start(APP)`: while the switch is on and the app has not
    been seeded yet (ios_settings 'demo_seeded' for the app), it fetches the package (`package()`), runs the app's
    seed from it (the family's accounts are made when missing) and removes the download. A package that cannot be
    fetched (no internet) leaves the app unseeded: it tries again at its next start.
  * Turning the switch off (`iosuite-shared demo --off`) stops further seeding; it removes nothing.

Where the package comes from: DEMO_PACKAGE (a folder holding iosuite_demo/, a zip or a URL) when set; else the demo/
folder of the repository when this library runs from a git checkout; else iosuite-demo.zip of the suite's GitHub
release of this version (PACKAGE_URL), which the release workflow builds from demo/.
"""
import contextlib
import logging
import os
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

log = logging.getLogger("iosuite_shared.demo")

SWITCH = "demo"          # ios_settings, app '': "1" while the demo is wanted
SEEDED = "demo_seeded"   # ios_settings, app <app>: when its seed ran (epoch seconds)
DEMO_PASSWORD = "calloway"
FAMILY_KEYS = ("morgan", "riley", "ava", "theo")  # the demo's account names (iosuite_demo.FAMILY)
PACKAGE_URL = "https://github.com/avandeputte/iosuite/releases/download/v{version}/iosuite-demo.zip"


# ---- the switch
def wanted() -> bool:
    from iosuite_shared import db
    return db.get_setting(SWITCH, "", "") == "1"


def switch(on: bool) -> None:
    from iosuite_shared import db
    db.set_setting(SWITCH, "1" if on else None, "")


def seeded(app: str) -> bool:
    from iosuite_shared import db
    return bool(db.settings_of(app).get(SEEDED))


# ---- the package
def _checkout() -> Path | None:
    """demo/ of the repository when this library runs from a git checkout (shared/iosuite_shared/ beside it)."""
    d = Path(__file__).resolve().parents[2] / "demo"
    return d if (d / "iosuite_demo" / "__init__.py").is_file() else None


@contextlib.contextmanager
def package():
    """The iosuite_demo package, importable while inside (on sys.path); a download is removed afterwards."""
    from iosuite_shared import __version__
    where = os.environ.get("DEMO_PACKAGE", "").strip()
    tmp = None
    if not where:
        local = _checkout()
        where = str(local) if local else PACKAGE_URL.format(version=__version__)
    try:
        if "://" in where:
            tmp = tempfile.mkdtemp(prefix="iosuite-demo-")
            path = os.path.join(tmp, "iosuite-demo.zip")
            with urllib.request.urlopen(where, timeout=60) as r, open(path, "wb") as out:  # noqa: S310 - our own release, or what DEMO_PACKAGE names
                shutil.copyfileobj(r, out)
            where = path
        sys.path.insert(0, where)
        yield
    finally:
        with contextlib.suppress(ValueError):
            sys.path.remove(where)
        for name in [m for m in sys.modules if m == "iosuite_demo" or m.startswith("iosuite_demo.")]:
            del sys.modules[name]  # the next fetch reads the package anew
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def at_start(app: str) -> None:
    """At an app's start, after its tables: seed it when the demo switch is on and it has not been seeded. Never stops
    the app from starting: a seed that fails is logged."""
    try:
        from iosuite_shared import users
        if not (users.init() and wanted()) or seeded(app):
            return
        try:
            ctx = package()
            ctx.__enter__()
        except Exception as e:  # noqa: BLE001 - no internet, or no package for this version: the next start tries again
            log.warning("the demo data for %s could not be fetched (%s); it is added at a later start", app, e)
            return
        try:
            import iosuite_demo
            iosuite_demo.seed(app)
        finally:
            ctx.__exit__(None, None, None)
    except Exception:  # noqa: BLE001
        log.exception("the demo data for %s could not be added", app)


# ---- the command: iosuite-shared demo
def add_parser(sub):
    p = sub.add_parser("demo", help="fill the suite with demo data: a made-up family of four, something in every app")
    p.add_argument("--off", action="store_true", help="stop adding demo data to apps that start (removes nothing)")
    p.add_argument("--no-restart", action="store_true", help="do not restart the apps installed here (they add theirs at their next start)")
    return p


def main(a, log=print) -> int:
    from iosuite_shared import users
    if not users.init():
        from iosuite_shared import db
        raise SystemExit(f"error: the Shared ioSuite database cannot be reached: {db.error}")
    if a.off:
        switch(False)
        log("ok: no more demo data is added (what was added stays)")
        return 0
    switch(True)
    log(f"  the Calloway family: {', '.join(FAMILY_KEYS)} (password: {DEMO_PASSWORD}), made by the first app that adds its demo data")
    if not a.no_restart and a.config:
        from iosuite_shared import install
        base = install.base_dir(a.config)
        for name in install.installed(base, a.config):
            install.restart_service(name, base / name / "app", log=log)
    log("ok: every app fetches the demo data and adds its share at its next start"
        + ("" if a.no_restart or not a.config else " (the apps here were restarted)"))
    return 0
