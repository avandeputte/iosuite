"""Sign-in at a reverse proxy (Cloudflare Access, Authelia, Authentik, oauth2-proxy...), as in iopix.

The proxy passes who signed in in a header; it is believed only from AUTH_PROXY_TRUSTED addresses, or, for
Cloudflare Access with CF_ACCESS_TEAM and CF_ACCESS_AUD set, from the signed Cf-Access-Jwt-Assertion token.
The person is matched to an account by email, then by name.
"""
import ipaddress
import logging

from app import config, users

log = logging.getLogger("iocontacts.auth")
_jwks = None


def mode() -> str:
    return config.AUTH_PROXY if config.AUTH_PROXY in ("cloudflare", "haproxy", "nginx", "caddy", "traefik", "header") else "off"


def headers() -> list[str]:
    if config.AUTH_PROXY_HEADER:
        return [h.strip().lower() for h in config.AUTH_PROXY_HEADER.split(",") if h.strip()]
    if mode() == "cloudflare":
        return ["cf-access-authenticated-user-email"]
    return ["remote-user", "x-forwarded-user", "x-auth-request-user", "x-auth-request-email", "x-forwarded-email", "remote-email"]


def _trusted(peer: str) -> bool:
    try:
        ip = ipaddress.ip_address(peer)
    except ValueError:
        return False
    for part in config.AUTH_PROXY_TRUSTED.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if ip in ipaddress.ip_network(part, strict=False):
                return True
        except ValueError:
            continue
    return False


def _cf_email(token: str) -> str | None:
    global _jwks
    try:
        import jwt
        if _jwks is None:
            _jwks = jwt.PyJWKClient(f"https://{config.CF_ACCESS_TEAM}/cdn-cgi/access/certs")
        key = _jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=config.CF_ACCESS_AUD)
        return claims.get("email")
    except Exception as e:  # noqa: BLE001 - a bad token is simply not believed
        log.info("Cloudflare Access token refused: %s", e)
        return None


def identity(request) -> str | None:
    if mode() == "off":
        return None
    if mode() == "cloudflare" and config.CF_ACCESS_TEAM and config.CF_ACCESS_AUD:
        tok = request.headers.get("cf-access-jwt-assertion")
        return _cf_email(tok) if tok else None
    peer = request.client.host if request.client else ""
    if not _trusted(peer):
        return None
    for h in headers():
        v = request.headers.get(h)
        if v:
            return v.strip()
    return None


def user(request) -> dict | None:
    ident = identity(request)
    return users.find(ident) if ident else None
