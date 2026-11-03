"""Response helpers the route modules share: JSON answers with an ETag and gzip, and JSON request bodies."""
import gzip
import hashlib

import orjson
from fastapi import HTTPException, Request
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


async def json_body(request) -> dict:
    """The request's JSON body, which must be an object: anything else is the client's mistake (400)."""
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, "The body is not valid JSON")
    if not isinstance(body, dict):
        raise HTTPException(400, "The body must be a JSON object")
    return body


def user_name(request: Request) -> str:
    u = getattr(request.state, "user", None)
    return u["name"] if u else "visitor"
