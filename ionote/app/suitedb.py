"""The Shared ioSuite database: the MariaDB database the ioThing apps share (accounts, sessions, roles, the suite's
list of apps and suite-wide settings), used through the iothing-auth library.

ionotes names it with IOSUITE_DB_HOST, _PORT, _NAME, _USER and _PASSWORD (ionotes.env); the default database and
user are `iosuite`. The library's own names (IOTHING_AUTH_DB_*) still work, so an install set up before the rename
keeps its settings; IOSUITE_DB_* wins when both are set. An install that never named the database and still relies
on the library's old default (`auth`, user `auth`) keeps using it: when `iosuite` cannot be signed in to and `auth`
can, `auth` is used and the log says so. Live databases are never renamed.

apply() runs from app/__init__.py, before the rest of ionotes imports iothing_auth (which reads IOTHING_AUTH_DB_*).
"""
import os
import sys

KEYS = ("HOST", "PORT", "NAME", "USER", "PASSWORD")
NEW, OLD = "IOSUITE_DB_", "IOTHING_AUTH_DB_"
DEFAULT = {"HOST": "127.0.0.1", "PORT": "3306", "NAME": "iosuite", "USER": "iosuite", "PASSWORD": "iosuite"}
LEGACY = {"NAME": "auth", "USER": "auth", "PASSWORD": "auth"}  # iothing-auth's defaults before the rename
source: dict = {}  # KEY -> the variable it came from ("" for a default)
note = ""  # set when an install on the old defaults was found, for the log


def _env(k: str):
    v = os.environ.get(k)
    return v if v not in (None, "") else None


def _reaches(s: dict):
    """None when these settings reach the database, else the MariaDB error code (0: no answer at all)."""
    try:
        import pymysql
        pymysql.connect(host=s["HOST"], port=int(s["PORT"]), user=s["USER"], password=s["PASSWORD"], database=s["NAME"],
                        connect_timeout=4).close()
        return None
    except Exception as e:  # noqa: BLE001
        code = e.args[0] if e.args else 0
        return code if isinstance(code, int) else 0


def apply() -> None:
    """Set IOTHING_AUTH_DB_* (what iothing-auth reads) from IOSUITE_DB_*, the old names, or the defaults."""
    global note
    s = {}
    for k in KEYS:
        name = NEW + k if _env(NEW + k) else OLD + k if _env(OLD + k) else ""
        source[k] = name
        s[k] = _env(name) if name else DEFAULT[k]
    unnamed = [k for k in LEGACY if not source[k]]
    if unnamed and _env("IOSUITE_DB_PROBE") != "0" and _reaches(s) in (1044, 1045, 1049):
        old = dict(s, **{k: LEGACY[k] for k in unnamed})  # access denied / no such database: an install on the old defaults?
        if _reaches(old) is None:
            s = old
            note = (f"Shared ioSuite database: using the old default `{s['NAME']}` (user {s['USER']}) at {s['HOST']}:{s['PORT']}; "
                    "name it with IOSUITE_DB_NAME / _USER / _PASSWORD in ionotes.env")
    for k in KEYS:
        os.environ[OLD + k] = s[k]
    cfg = sys.modules.get("iothing_auth.config")
    if cfg is not None:  # already imported (it reads the environment once): give it the same values
        cfg.DB_HOST, cfg.DB_PORT, cfg.DB_NAME, cfg.DB_USER, cfg.DB_PASSWORD = s["HOST"], int(s["PORT"]), s["NAME"], s["USER"], s["PASSWORD"]


def public() -> dict:
    """Where the Shared ioSuite database is (no password), for Settings › Storage and backups."""
    return {"host": os.environ.get(OLD + "HOST", ""), "port": int(os.environ.get(OLD + "PORT") or 3306),
            "database": os.environ.get(OLD + "NAME", ""), "user": os.environ.get(OLD + "USER", ""),
            "fromEnv": [v for v in source.values() if v]}
