"""Response helpers the route modules share: JSON answers with an ETag and gzip, and the download header."""
import gzip
import hashlib
from urllib.parse import quote

import orjson
from fastapi import Request
from fastapi.responses import Response


def jresp(request: Request, data) -> Response:
    """JSON, gzipped when large, with an ETag: a client that sends it back (If-None-Match) gets 304 and no body
    while the answer is unchanged."""
    body = orjson.dumps(data)
    etag = 'W/"' + hashlib.blake2b(body, digest_size=12).hexdigest() + '"'
    headers = {"Cache-Control": "private, no-cache", "ETag": etag, "Vary": "Accept-Encoding, Cookie"}
    if etag in [t.strip() for t in request.headers.get("if-none-match", "").split(",")]:
        return Response(status_code=304, headers=headers)
    if len(body) > 2048 and "gzip" in request.headers.get("accept-encoding", ""):
        body = gzip.compress(body, compresslevel=3)
        headers["Content-Encoding"] = "gzip"
    return Response(body, media_type="application/json", headers=headers)


def attachment(name: str) -> dict:
    """The header that makes a browser save the answer under this name. A header is Latin-1 only, so a name with other
    characters goes twice (RFC 6266): an ASCII stand-in, and the real name as filename*=UTF-8''..."""
    plain = "".join(c if c.isascii() and c not in '"\\' and c.isprintable() else "_" for c in name)
    return {"Content-Disposition": f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(name, safe='')}"}


def user_name(request: Request) -> str:
    u = getattr(request.state, "user", None)
    return u["name"] if u else "visitor"
