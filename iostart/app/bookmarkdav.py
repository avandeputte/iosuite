"""The bookmarks as one file over WebDAV: /dav/bookmarks/bookmarks.xbel (XBEL) and /dav/bookmarks/bookmarks.html
(the bookmarks HTML browsers export), for Floccus's "WebDAV" kind of account and anything else that keeps its
bookmarks in such a file. Any name ending in .xbel or .html in that folder is the same tree.

There is no file: a GET writes the tree out, a PUT (or a PUT to <name>.temp and a MOVE, as Floccus does it) is read
and becomes the tree (app/bookmarksync.replace). A client checks the size of what it uploaded and fetched (PROPFIND
getcontentlength), so the text of an upload is kept and served back byte for byte while the tree is still what it
said; once the tree changed (the start page, another client), the file is written out anew. <name>.lock is the lock
both sync protocols share: Floccus puts it there while it syncs and takes it away after.

A file encrypted by the client (Floccus's passphrase) cannot be read here and is refused: leave the passphrase empty.
"""
import datetime as dt
import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from iosuite_shared import dav

from app import bookmarkfiles, bookmarks, bookmarksync as sync, config, db

BASE = "/dav/bookmarks"
router = APIRouter()
NAMES = ("bookmarks.xbel", "bookmarks.html")  # what a listing of the folder shows
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,63}\.(xbel|html)$")
METHODS = ("OPTIONS", "GET", "HEAD", "PUT", "DELETE", "MOVE", "PROPFIND")
MAX_FILE = config.MAX_IMPORT_BYTES // 2


def _kind(name: str) -> tuple[str, str, str]:
    """(the file's name, 'xbel' | 'html', '' | 'lock' | 'temp') or 404."""
    part = ""
    for suffix in ("lock", "temp"):
        if name.endswith("." + suffix):
            name, part = name[: -len(suffix) - 1], suffix
    m = _NAME.match(name)
    if not m:
        raise HTTPException(404, "The bookmarks are at bookmarks.xbel and bookmarks.html")
    return name, m.group(1), part


def _key(what: str, name: str) -> str:
    """A file's state is the account's: each one's file is their own tree (their bookmarks and the shared ones)."""
    v = bookmarks.viewer()
    return f"{what}:{v.uid if v else ''}:{name}"


def _state(name: str) -> dict | None:
    try:
        return json.loads(db.get_setting(_key("bookmarkfile", name)) or "null")
    except ValueError:
        return None


def _write_out(name: str, kind: str) -> str:
    t = bookmarks.Tree()
    rev = bookmarks.revision()
    its = sync.items(t)
    body = bookmarkfiles.to_xbel(its, bookmarks.highest_id()) if kind == "xbel" else bookmarkfiles.to_html(its, bookmarks.highest_id())
    db.set_setting(_key("bookmarkfile", name), json.dumps({"rev": rev, "body": body, "fresh": True}))
    return body


def body_of(name: str, kind: str, for_size: bool = False) -> str:
    """The file as a client gets it now. for_size: an upload the tree could not take word for word still counts as
    the file until something else changes (the client checks the size of what it just sent)."""
    st = _state(name)
    if st and st.get("rev") == bookmarks.revision() and (st.get("fresh") or for_size):
        return st["body"]
    return _write_out(name, kind)


def take(name: str, kind: str, text: str) -> None:
    """An uploaded file becomes the tree."""
    if len(text.encode("utf-8")) > MAX_FILE:
        raise HTTPException(413, "That bookmarks file is too large")
    head = bookmarkfiles.XBEL_HEAD if kind == "xbel" else bookmarkfiles.HTML_HEAD
    if head not in text:
        raise HTTPException(415, "Not a bookmarks file this server can read. If the sync app encrypts the file with a passphrase, "
                                 "leave the passphrase empty: the start page has to read the bookmarks.")
    try:
        new = bookmarkfiles.parse_xbel(text) if kind == "xbel" else bookmarkfiles.parse_html(text)
    except bookmarkfiles.BadFile as e:
        raise HTTPException(400, str(e))
    with bookmarks.writing() as rev:
        base = int(db.get_setting(_key("bookmarkfile-base", name)) or 0)
        bookmarks.saw_id(bookmarkfiles.highest_id(text))
        exact = sync.replace(new, base)
        db.set_setting(_key("bookmarkfile", name), json.dumps({"rev": rev, "body": text, "fresh": exact}))
        db.set_setting(_key("bookmarkfile-base", name), str(rev))
    sync.alive()


def _ctype(kind: str) -> str:
    return "application/xml; charset=utf-8" if kind == "xbel" else "text/html; charset=utf-8"


def _now():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _props(ms, href: str, size: int | None, ctype: str | None, modified=None):
    p = ET.Element(dav.q(dav.D, "prop"))
    rt = dav.sub(p, dav.D, "resourcetype")
    if size is None:
        dav.sub(rt, dav.D, "collection")
    else:
        dav.sub(p, dav.D, "getcontentlength", size)
        dav.sub(p, dav.D, "getcontenttype", ctype)
    dav.sub(p, dav.D, "getlastmodified", dav.http_date(modified or _now()))
    dav.response(ms, href, p, [])


def _modified():
    r = db.one("SELECT updated_at FROM prt_settings WHERE name = 'bookmarks_rev'")
    return r["updated_at"] if r else _now()


@router.api_route(BASE, methods=["OPTIONS", "PROPFIND", "GET"], include_in_schema=False)
@router.api_route(BASE + "/", methods=["OPTIONS", "PROPFIND", "GET"], include_in_schema=False)
async def folder(request: Request):
    if request.method == "OPTIONS":
        return Response(status_code=200, headers=dav.options("1", METHODS))
    sync.user(request)
    if request.method == "GET":
        return Response("Your bookmarks and the shared ones, for sync apps: bookmarks.xbel and bookmarks.html in this folder.\n", media_type="text/plain; charset=utf-8")

    def work():
        ms = ET.Element(dav.q(dav.D, "multistatus"))
        _props(ms, BASE + "/", None, None, _modified())
        if request.headers.get("depth", "0") != "0":
            for n in NAMES:
                kind = _kind(n)[1]
                _props(ms, f"{BASE}/{n}", len(body_of(n, kind, True).encode("utf-8")), _ctype(kind), _modified())
        return dav.xml(ms)
    return await run_in_threadpool(work)


@router.api_route(BASE + "/{name}", methods=list(METHODS), include_in_schema=False)
async def file(name: str, request: Request):
    m = request.method
    if m == "OPTIONS":
        return Response(status_code=200, headers=dav.options("1", METHODS))
    sync.user(request, write=m in ("PUT", "DELETE", "MOVE"))
    name, kind, part = _kind(name)
    data = await request.body() if m == "PUT" else b""

    def text() -> str:
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(400, "The file is not UTF-8 text")

    def lock_file():
        at = sync.locked_at()
        if m == "PUT":
            sync.lock()
            return Response(status_code=201 if not at else 204)
        if m == "DELETE":
            sync.unlock()
            return Response(status_code=204)
        if not at:
            raise HTTPException(404, "Not locked")
        when = dt.datetime.fromtimestamp(at, dt.timezone.utc).replace(tzinfo=None)
        body = "<html><body>I am a lock file</body></html>"
        if m == "PROPFIND":
            ms = ET.Element(dav.q(dav.D, "multistatus"))
            _props(ms, f"{BASE}/{name}.lock", len(body), "text/html", when)
            return dav.xml(ms)
        return Response(body, media_type="text/html", headers={"Last-Modified": dav.http_date(when)})

    def temp_file():
        key = _key("bookmarkfile-temp", name)
        if m == "PUT":
            if len(data) > MAX_FILE:
                raise HTTPException(413, "That bookmarks file is too large")
            db.set_setting(key, text())
            sync.alive()
            return Response(status_code=201)
        kept = db.get_setting(key)
        if m == "DELETE":
            db.set_setting(key, None)
            return Response(status_code=204)
        if kept is None:
            raise HTTPException(404, "No such file")
        if m == "MOVE":
            target = _kind(unquote(urlsplit(request.headers.get("destination", "")).path.rsplit("/", 1)[-1]))
            if target[2] or target[0] != name:
                raise HTTPException(403, "A .temp file moves onto the bookmarks file it was uploaded for")
            take(name, kind, kept)
            db.set_setting(key, None)
            return Response(status_code=204)
        raw = kept.encode("utf-8")
        if m == "PROPFIND":
            ms = ET.Element(dav.q(dav.D, "multistatus"))
            _props(ms, f"{BASE}/{name}.temp", len(raw), _ctype(kind))
            return dav.xml(ms)
        return Response(raw, media_type=_ctype(kind))

    def main_file():
        if m == "PUT":
            take(name, kind, text())
            return Response(status_code=204)
        if m == "DELETE":  # the tree is not a file to delete: only the kept copy of the last upload goes
            db.set_setting(_key("bookmarkfile", name), None)
            return Response(status_code=204)
        if m == "MOVE":
            raise HTTPException(403, "The bookmarks file stays where it is")
        if m == "PROPFIND":
            ms = ET.Element(dav.q(dav.D, "multistatus"))
            _props(ms, f"{BASE}/{name}", len(body_of(name, kind, True).encode("utf-8")), _ctype(kind), _modified())
            return dav.xml(ms)
        rev = bookmarks.revision()
        raw = body_of(name, kind).encode("utf-8")
        if m == "GET":
            db.set_setting(_key("bookmarkfile-base", name), str(rev))  # what this client now knows
        return Response(raw, media_type=_ctype(kind), headers={"Last-Modified": dav.http_date(_modified()), "Cache-Control": "no-store"})

    return await run_in_threadpool({"lock": lock_file, "temp": temp_file}.get(part, main_file))
