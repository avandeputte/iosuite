"""Sign-in: login, logout, the signed-in account's own settings and password, first-run setup: iothing-auth's
routes, shared with the other ioThing apps."""

from app.auth import auth

router = auth.router()
