"""Sign-in at a reverse proxy (Cloudflare Access, Authelia, Authentik, oauth2-proxy...): iothing_auth.proxyauth does
the work, with the settings stored once for the whole suite in the Shared ioSuite database; the environment (iocontacts.env)
still wins. The person is matched to an account by email, then by name."""
from app.auth import auth

_proxy = auth.proxy


def mode() -> str:
    return _proxy.mode()


def user(request) -> dict | None:
    return auth.decorate(_proxy.user(request))


def status() -> dict:
    return _proxy.status()
