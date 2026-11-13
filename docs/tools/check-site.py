#!/usr/bin/env python3
"""Check that every local link and image in the built site points at a file.

    python3 tools/check-site.py [site]

`mkdocs build --strict` checks the links it rewrites -- Markdown links and
images -- but not raw HTML: an <img src="img/x.png"> is copied as it is, and on
a page served from /docs/first-run/ it then asks for
/docs/first-run/img/x.png. Every screenshot on the site was broken that way
once, and the build passed. This reads the finished HTML instead, so it sees
what a browser will ask for, however the page was written.

External links are not fetched: this is about files the build itself must
produce.
"""
import html
import pathlib
import re
import sys
import urllib.parse

SITE = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "site").resolve()
if not SITE.is_dir():
    sys.exit("no built site at %s -- run mkdocs build first" % SITE)

ATTR = re.compile(r'\b(?:src|href|srcset)="([^"]*)"')
problems = []
checked = 0


def target(page, ref):
    """The file a reference on `page` resolves to, or None for an external one."""
    ref = html.unescape(ref).split("#", 1)[0].split("?", 1)[0]
    if not ref or re.match(r"^[a-z][a-z0-9+.-]*:", ref, re.I) or ref.startswith("//"):
        return None
    if ref.startswith("/"):
        path = SITE / ref.lstrip("/")
    else:
        path = page.parent / ref
    path = pathlib.Path(urllib.parse.unquote(str(path)))
    if path.is_dir() or str(ref).endswith("/"):
        path = path / "index.html"
    return path


for page in sorted(SITE.rglob("*.html")):
    text = page.read_text(errors="replace")
    for ref in ATTR.findall(text):
        for one in ([r.strip().split(" ")[0] for r in ref.split(",")] if " " in ref else [ref]):
            path = target(page, one)
            if path is None:
                continue
            checked += 1
            if not path.resolve().is_file():
                problems.append("%s -> %s" % (page.relative_to(SITE), one))

print("checked %d local references in %d pages" % (checked, len(list(SITE.rglob("*.html")))))
if problems:
    print("\n%d broken:" % len(problems))
    for p in problems:
        print("  - " + p)
    sys.exit(1)
print("every local link and image resolves")
