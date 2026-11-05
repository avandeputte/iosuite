__version__ = "1.5.0"

from app import suitedb as _suitedb  # noqa: E402

_suitedb.apply()  # the Shared ioSuite database's settings, before anything imports iothing_auth
