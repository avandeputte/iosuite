"""The Shared ioSuite database: the MariaDB database the ioThing apps share (accounts, sessions, roles, the suite's
list of apps and suite-wide settings), used through the iosuite-shared library.

ionotes names it with IOSUITE_DB_HOST, _PORT, _NAME, _USER and _PASSWORD (ionotes.env), which the library reads
itself; the default database and user are `iosuite`.
"""
import os

from iosuite_shared import config

KEYS = ("HOST", "PORT", "NAME", "USER", "PASSWORD")


def public() -> dict:
    """Where the Shared ioSuite database is (no password), for Settings › Storage and backups."""
    return {"host": config.DB_HOST, "port": config.DB_PORT, "database": config.DB_NAME, "user": config.DB_USER,
            "fromEnv": [config.PREFIX + k for k in KEYS if os.environ.get(config.PREFIX + k)]}
