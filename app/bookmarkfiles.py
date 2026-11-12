"""Bookmark files: XBEL (the XML Bookmark Exchange Language) and the Netscape bookmarks HTML every browser exports
and imports. Written as Floccus writes them (ids on the items, its highest-id comment), so the file a sync client
fetches over WebDAV (app/bookmarkdav.py) is one it could have written itself; read leniently, whoever wrote them.

A parsed file is a list of items: {type: 'folder', id, title, children} and {type: 'bookmark', id, title, url, tags};
id is an int, or None where the file gave none.
"""
import re
import xml.etree.ElementTree as ET
from html import escape as _esc
from html.parser import HTMLParser

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring as parse_xml

XBEL_HEAD = '<?xml version="1.0" encoding="UTF-8"?>'
HTML_HEAD = "<!DOCTYPE NETSCAPE-Bookmark-file-1>"
_HIGHEST = re.compile(r"<!--- highestId :(\d+):")
# what XML 1.0 cannot carry at all (a title pasted with a control character must not make the file unreadable)
_BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


class BadFile(ValueError):
    pass


def highest_id(text: str) -> int:
    """The highest id Floccus says it has used, from its comment in the file; 0 without one."""
    m = _HIGHEST.search(text or "")
    return int(m.group(1)) if m else 0


def _id(v) -> int | None:
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        return None
    return n if 0 < n < 2 ** 31 else None


def _x(s) -> str:
    return _esc(_BAD_XML.sub("", str(s or "")), quote=True).replace("&#x27;", "&apos;")


# ------------------------------------------------------------------ XBEL

def to_xbel(items: list[dict], highest: int) -> str:
    out = [XBEL_HEAD,
           '<!DOCTYPE xbel PUBLIC "+//IDN python.org//DTD XML Bookmark Exchange Language 1.0//EN//XML" "http://pyxml.sourceforge.net/topics/dtds/xbel.dtd">',
           '<xbel version="1.0">',
           f"<!--- highestId :{int(highest)}: for Floccus bookmark sync browser extension -->"]

    def level(items, indent):
        for it in items:
            if it["type"] == "folder":
                out.append(f'{indent}<folder id="{it["id"]}">')
                out.append(f'{indent}  <title>{_x(it["title"])}</title>')
                level(it.get("children") or [], indent + "  ")
                out.append(f"{indent}</folder>")
            else:
                out.append(f'{indent}<bookmark href="{_x(it["url"])}" id="{it["id"]}">')
                out.append(f'{indent}  <title>{_x(it["title"])}</title>')
                out.append(f"{indent}</bookmark>")

    level(items, "")
    out.append("</xbel>")
    return "\n".join(out)


def parse_xbel(text: str) -> list[dict]:
    try:
        root = parse_xml((text or "").lstrip("﻿"))
    except (ET.ParseError, DefusedXmlException, ValueError) as e:
        raise BadFile(f"Not a readable XBEL file: {str(e)[:120]}")
    if root.tag != "xbel":
        raise BadFile("Not an XBEL file (the root element is not <xbel>)")

    def level(el):
        out = []
        for c in el:
            title = (c.findtext("title") or "").strip()
            if c.tag == "folder":
                out.append({"type": "folder", "id": _id(c.get("id")), "title": title, "children": level(c)})
            elif c.tag == "bookmark" and (c.get("href") or "").strip():
                out.append({"type": "bookmark", "id": _id(c.get("id")), "title": title, "url": c.get("href").strip(), "tags": []})
        return out

    return level(root)


# ------------------------------------------------------------------ Netscape bookmarks HTML

def to_html(items: list[dict], highest: int | None = None, title: str = "Bookmarks") -> str:
    """`highest` given: as Floccus writes the file it syncs (its comment, an ID on every item). None: a plain export
    for a browser's import."""
    out = [HTML_HEAD, '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">', f"<TITLE>{_esc(title)}</TITLE>"]
    if highest is not None:
        out[-1] += f"<!--- highestId :{int(highest)}: for Floccus bookmark sync browser extension -->"
    else:
        out.append(f"<H1>{_esc(title)}</H1>")
    ident = (lambda it: f' ID="{it["id"]}"') if highest is not None else (lambda it: "")

    def level(items, indent):
        out.append(f"{indent}<DL><p>")
        for it in items:
            if it["type"] == "folder":
                out.append(f'{indent}  <DT><H3{ident(it)}>{_esc(it["title"] or "")}</H3>')
                level(it.get("children") or [], indent + "  ")
            else:
                tags = ",".join(it.get("tags") or [])
                out.append(f'{indent}  <DT><A HREF="{_esc(it["url"] or "", quote=True)}"' + (f' TAGS="{_esc(tags, quote=True)}"' if tags else "")
                           + f'{ident(it)}>{_esc(it["title"] or "")}</A>')
        out.append(f"{indent}</DL><p>")

    level(items, "")
    if highest is not None:
        out.append("</html>")
    return "\n".join(out) + "\n"


class _Netscape(HTMLParser):
    """<DT><H3>folder</H3><DL><p> … </DL><p> and <DT><A HREF>link</A>, nested; everything else is skipped."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root: list = []
        self.stack = [self.root]   # the list items go into, per open <DL>
        self.pending = None        # the folder an <H3> just named: the next <DL> is its contents
        self.text = None           # the text of the <H3> or <A> being read
        self.cur = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "dl":
            self.stack.append(self.pending["children"] if self.pending else self.stack[-1])
            self.pending = None
        elif tag == "h3":
            self.cur, self.text = {"type": "folder", "id": _id(a.get("id")), "title": "", "children": []}, []
        elif tag == "a":
            self.cur, self.text = {"type": "bookmark", "id": _id(a.get("id")), "title": "", "url": (a.get("href") or "").strip(),
                                   "tags": [t.strip() for t in (a.get("tags") or "").split(",") if t.strip()]}, []

    def handle_endtag(self, tag):
        if tag == "dl":
            if len(self.stack) > 1:
                self.stack.pop()
            self.pending = None
        elif tag in ("h3", "a") and self.cur is not None and self.cur["type"] == ("folder" if tag == "h3" else "bookmark"):
            self.cur["title"] = "".join(self.text or []).strip()
            if tag == "h3":
                self.stack[-1].append(self.cur)
                self.pending = self.cur
            elif self.cur["url"]:
                self.stack[-1].append(self.cur)
            self.cur = self.text = None

    def handle_data(self, data):
        if self.text is not None:
            self.text.append(data)


def parse_html(text: str) -> list[dict]:
    if "<a" not in (text or "").lower() and "<h3" not in (text or "").lower() and HTML_HEAD.lower() not in (text or "").lower():
        raise BadFile("Not a bookmarks file: export one from a browser (Bookmarks › Export)")
    p = _Netscape()
    p.feed(text)
    p.close()
    return p.root


def parse(text: str) -> list[dict]:
    """Either kind, by what the file starts with."""
    head = (text or "").lstrip("﻿ \t\r\n")[:2000].lower()
    if head.startswith("<?xml") or "<xbel" in head:
        return parse_xbel(text)
    return parse_html(text)


def count(items: list[dict]) -> tuple[int, int]:
    """(folders, links) in a parsed file."""
    f = l = 0
    for it in items:
        if it["type"] == "folder":
            a, b = count(it.get("children") or [])
            f, l = f + 1 + a, l + b
        else:
            l += 1
    return f, l
