"""Request size limits: a body is read up to its limit, never all of it into memory first."""
from fastapi import HTTPException, Request

MAX_BODY = 16 * 1024 * 1024    # a contact (JSON or vCard, a photo inline) or a CardDAV request
MAX_IMPORT = 64 * 1024 * 1024  # an imported .vcf / .csv / .json file


def too_big(limit: int) -> HTTPException:
    return HTTPException(413, f"Too large (the limit is {limit // (1024 * 1024)} MB)")


async def body(request: Request, limit: int | None = None) -> bytes:
    limit = limit or MAX_BODY
    n = request.headers.get("content-length")
    if n and n.isdigit() and int(n) > limit:
        raise too_big(limit)
    out = bytearray()
    async for chunk in request.stream():
        out += chunk
        if len(out) > limit:
            raise too_big(limit)
    return bytes(out)
