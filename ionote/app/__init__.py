__version__ = "1.4.1"

from app import suitedb as _suitedb  # noqa: E402

_suitedb.apply()  # the Shared ioSuite database's settings, before anything imports iothing_auth
