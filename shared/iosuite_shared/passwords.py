"""Account passwords: Argon2id (argon2-cffi, RFC 9106's low-memory profile: 64 MiB, 3 passes, 4 lanes). The parameters
are stored in the hash ($argon2id$v=19$m=...,t=...,p=...$salt$hash), so they can be raised later: a hash made with
other parameters, or an scrypt2$ hash from before 0.29, is replaced the next time its password is seen (needs_rehash).

App passwords and other random secrets do not come here: see token_hash.
"""
import base64
import hashlib
import hmac

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

HASHER = PasswordHasher()  # the tests swap in a cheap one


def hash_password(pw: str) -> str:
    return HASHER.hash(pw)


def check_password(pw: str, stored: str) -> bool:
    """Whether pw matches the stored hash; False, never an exception, for a malformed hash."""
    if (stored or "").startswith("scrypt2$"):
        return _check_scrypt2(pw, stored)
    try:
        return HASHER.verify(stored, pw)
    except (VerificationError, InvalidHashError, TypeError, ValueError):
        return False


def needs_rehash(stored: str) -> bool:
    try:
        return bool(stored) and HASHER.check_needs_rehash(stored)
    except (InvalidHashError, ValueError):
        return True


def _check_scrypt2(pw: str, stored: str) -> bool:
    """scrypt2$n$r$p$salt$hash (0.28 and before): read only, so an account moves to Argon2id at its next sign-in."""
    try:
        _, n, r, p, s, h = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=base64.b64decode(s), n=int(n), r=int(r), p=int(p), dklen=32,
                             maxmem=256 * 1024 * 1024)
        return hmac.compare_digest(got, base64.b64decode(h))
    except Exception:
        return False


def token_hash(secret: str) -> str:
    """A random, high-entropy secret (an app password) needs no slow hash: SHA-256, hex."""
    return hashlib.sha256(secret.encode()).hexdigest()


def check_token(secret: str, stored: str) -> bool:
    return hmac.compare_digest(token_hash(secret), stored or "")


_DUMMY = None


def burn(pw: str):
    """The work of a real check, for an unknown name: a miss costs the same as a wrong password."""
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password("not a real password")
    check_password(pw, _DUMMY)
