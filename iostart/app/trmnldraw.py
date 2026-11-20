"""TRMNL screens as pictures: the image a TRMNL device shows, drawn here from the same markup TRMNL's cloud renders
(app/trmnl_markup, TRMNL's design framework), without a browser. For the TRMNL server inside the start page
(app/trmnlserver.py): a device asks for a picture, not a page.

What TRMNL's framework does with CSS and its plugins.js, this does for the part of the framework the suite's screens
use, to the pixel where it could be measured against Chromium (tests/test_trmnl_draw.py lists what is covered):

    view, layout (row/col, top, center, stretch-x), grid + col--span-N, flex (row/col, left/center/right/between,
    top), gap in its sizes, w--full, w--N on a box, hidden, item/meta/content, columns with data-overflow (columns
    filled in turn, a group's header repeated in gray where the group goes on, "and N more"), progress-bar,
    title_bar, value/title/label/description in the sizes used, text--xlarge/--xxlarge/--bold,
    label--gray/--inverted/--outline/--underline, data-clamp, data-fit-value, data-pixel-perfect, the mashup
    layouts, the classes for the large screen (lg:x, see classes()), and an img sized with w--N h--N or w--full
    (image--fill: stretched) whose src is an SVG in a data: address, drawn by the small part of SVG the suite's
    glyphs and graphs are written in (glyph: circle with a dashed stroke turned by rotate, rect, polygon, path with
    M L H V A Z, g with fill and stroke, preserveAspectRatio="none").

The fonts are the framework's own (app/trmnl_fonts: TRMNL12/16/21 and Inter, SIL Open Font License), the grays are
its dither patterns for 1-bit and 2-bit screens and plain grays from 4 bits up. A denser screen (the TRMNL X: 1.8 of
its pixels to one of the framework's) is laid out at the framework's size and drawn larger, in Inter throughout, as
the framework does there: lengths in the framework's pixels fall between the screen's, so letters are set where
they fall (drawn four times as large and brought down, a browser's way) and pictures on whole pixels of the
framework's. A class this does not know is laid out as a plain box, so markup using more of the framework needs it
added here (the test compares every screen).
"""
import base64
import functools
import html.parser
import io
import math
import os
import re
import struct
import zlib

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, features

RAQM = features.check("raqm")  # sets a font's features: tabular figures (value--tnums); without it the figures keep their own widths
FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trmnl_fonts")
W, H = 800, 480          # the framework's own screen, in its pixels; another screen is this times its scale
GAP = 10
INF = 10 ** 9

# layout name -> each view's cell in the mashup's 2x2 grid (column, row, columns, rows), as in the framework
LAYOUTS = {
    "full": [(0, 0, 2, 2)],
    "1Lx1R": [(0, 0, 1, 2), (1, 0, 1, 2)],
    "1Tx1B": [(0, 0, 2, 1), (0, 1, 2, 1)],
    "1Lx2R": [(0, 0, 1, 2), (1, 0, 1, 1), (1, 1, 1, 1)],
    "2Lx1R": [(0, 0, 1, 1), (0, 1, 1, 1), (1, 0, 1, 2)],
    "2Tx1B": [(0, 0, 1, 1), (1, 0, 1, 1), (0, 1, 2, 1)],
    "1Tx2B": [(0, 0, 2, 1), (0, 1, 1, 1), (1, 1, 1, 1)],
    "2x2": [(0, 0, 1, 1), (1, 0, 1, 1), (0, 1, 1, 1), (1, 1, 1, 1)],
}


def sizes(layout: str) -> list:
    """The size of markup each view of a layout takes: full, half_vertical, half_horizontal or quadrant."""
    return [{(2, 2): "full", (1, 2): "half_vertical", (2, 1): "half_horizontal", (1, 1): "quadrant"}[(c[2], c[3])] for c in LAYOUTS[layout]]


# ---- the markup, as a tree ---------------------------------------------------------------------------------------

class Node:
    def __init__(self, tag, attrs=None, parent=None):
        self.tag = tag
        self.attrs = dict(attrs or {})
        self.cls = set((self.attrs.get("class") or "").split())
        self.own = {c for c in self.cls if ":" not in c}  # its plain classes, whatever the screen (cls: what counts on this one)
        self.kids = []
        self.text = ""
        self.parent = parent
        self.box = None
        self.st = None
        self.lines = None
        self.font = None
        self.cols = None

    def has(self, *names):
        return any(n in self.cls for n in names)

    def up(self, name):
        p = self.parent
        while p is not None:
            if name in p.cls:
                return p
            p = p.parent
        return None


class _Parser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs, self.cur)
        if tag != "style":  # a style sheet is the browser's: what it says, the drawing does of itself
            self.cur.kids.append(n)
        if tag not in ("img", "br", "svg", "circle", "rect", "path"):
            self.cur = n

    def handle_endtag(self, tag):
        p = self.cur
        while p is not self.root and p.tag != tag:
            p = p.parent
        if p is not self.root:
            self.cur = p.parent

    def handle_data(self, data):
        if self.cur.tag == "span":
            self.cur.text += data


def parse(markup: str) -> list:
    p = _Parser()
    p.feed(markup)
    for n in _walk(p.root):
        n.text = " ".join(n.text.replace("\xa0", "\ue000").split()).replace("\ue000", "\xa0")  # a no-break space holds its line
    return p.root.kids


def _walk(n):
    yield n
    for k in n.kids:
        yield from _walk(k)


# ---- the classes that count on this screen -----------------------------------------------------------------------

# the coloured inks of a Spectra 6 panel (black and white besides), as the framework names them (text--red, bg--blue),
# and their place in the picture's palette; in the picture as it is drawn each is one value of its own (INK)
INKS = ("red", "green", "blue", "yellow")
TONES = ("black", "white") + INKS
INK = {k: i + 1 for i, k in enumerate(INKS)}
PALETTE = [(255, 255, 255), (0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]  # white, black, then INKS
STEPS = {"xxsmall", "xsmall", "small", "base", "large", "xlarge", "xxlarge", "xxxlarge", "mega", "giga"}


def _family(c: str):
    """The group a class belongs to where an element takes one of the group (a size of text, a gap, a width...), or None."""
    if c == "gap" or c.startswith("gap--"):
        return "gap"
    m = re.fullmatch(r"([wh])--(?:\d+(?:\.5)?|full)", c)
    if m:
        return m.group(1)
    base, _, step = c.partition("--")
    if base in ("title", "label", "value", "description", "text", "progress-bar") and step in STEPS:
        return base
    if base in ("text", "bg") and step in TONES:
        return base + "-color"
    return None


def classes(cls, large: bool, bits: int = 1, inks: bool = False) -> set:
    """An element's classes as they count on this screen. The framework's classes for one size of screen (lg:gap--large:
    on a large screen, the TRMNL X) take the place of the element's plain class of the same group there and are
    nothing elsewhere; lg:flex and lg:block show there what `hidden` hides elsewhere. The same for one depth of gray
    (1bit:, 2bit:, 4bit:), which no screen of coloured inks is: that is how the markup gives a colour to such a screen
    alone (text--red 1bit:text--black 2bit:text--black 4bit:text--black). The suite's markup has no sm: or md: (the
    TRMNL itself is md: its look is the plain classes)."""
    out = {c for c in cls if ":" not in c}
    mine = ([] if not large else ["lg:"]) + ([] if inks else [f"{bits}bit:"])
    for c in cls:
        at = next((m for m in mine if c.startswith(m)), None)
        if at is None:
            continue
        c = c[len(at):]
        if c in ("flex", "block", "inline"):
            out.discard("hidden")
            continue
        group = _family(c)
        if group:
            out = {o for o in out if _family(o) != group}
        out.add(c)
    return out


# ---- fonts and text ----------------------------------------------------------------------------------------------

@functools.lru_cache(maxsize=8)
def _rise(name: str):
    """How far a font's line rises above and falls below the baseline, as parts of its size (the font file's hhea
    table, which is what a browser on Linux lays lines out by)."""
    with open(os.path.join(FONTS, name + ".ttf"), "rb") as f:
        data = f.read()
    tables = {data[12 + 16 * i:16 + 16 * i]: struct.unpack(">II", data[20 + 16 * i:28 + 16 * i]) for i in range(struct.unpack(">H", data[4:6])[0])}
    em = struct.unpack(">H", data[tables[b"head"][0] + 18:tables[b"head"][0] + 20])[0]
    up, down = struct.unpack(">hh", data[tables[b"hhea"][0] + 4:tables[b"hhea"][0] + 8])
    return up / em, -down / em


@functools.lru_cache(maxsize=256)
def _font(name: str, size: float, weight: int = 0, optical: float = 0):
    f = ImageFont.truetype(os.path.join(FONTS, name + ".ttf"), size)
    if name == "Inter":  # one file for every weight; the optical size follows the font size, as a browser sets it
        f.set_variation_by_axes([max(14, min(32, optical or size)), weight])
    return f


# class -> (font file, size, line height, weight) at the framework's own scale: TRMNL's pixel typefaces, which a screen
# of the framework's own density (the TRMNL: 800 x 480) shows crisp
TEXT = {
    "value": ("Inter", 38, 42, 450), "value--xsmall": ("Inter", 20, 24, 550), "value--small": ("Inter", 26, 29, 500),
    "value--large": ("Inter", 58, 70, 400), "value--xlarge": ("Inter", 74, 86, 375), "value--xxlarge": ("Inter", 96, 108, 350),
    "title": ("TRMNL21-Regular", 21, 21, 0), "title--small": ("TRMNL16-Bold", 16, 16, 0),
    "label": ("TRMNL16-Bold", 16, 20, 0), "label--small": ("TRMNL12-Regular", 12, 12, 0),
    "label--small-bold": ("TRMNL12-Bold", 12, 12, 0),
    "description": ("TRMNL12-Regular", 12, 12, 0), "bar": ("TRMNL16-Bold", 16, 16, 0),
}
# and on a denser screen (the TRMNL X: 1872 x 1404, 1.8 of its pixels to one of the framework's), where the framework
# sets everything in Inter
TEXT_DENSE = {
    **TEXT, "value--small": ("Inter", 26, 29, 475), "value--xxxlarge": ("Inter", 128, 128, 300),
    "title": ("Inter", 21, 25.2, 400), "title--small": ("Inter", 16, 19.2, 700), "title--large": ("Inter", 30, 36, 425),
    "title--xlarge": ("Inter", 35, 42, 400),
    "label": ("Inter", 16, 20, 500), "label--small": ("Inter", 13, 13, 500), "label--small-bold": ("Inter", 13, 13, 500),
    "label--large": ("Inter", 21, 25.2, 500), "label--xlarge": ("Inter", 26, 31.2, 475),
    "description": ("Inter", 13, 15.6, 400), "description--xlarge": ("Inter", 21, 25.2, 500), "description--xxlarge": ("Inter", 24, 28.8, 475),
    "bar": ("Inter", 16, 22, 700),
}
# text--SIZE on any text of a dense screen: the size and the line of the letters, whatever the element is
TEXT_SIZE = {"text--xlarge": (26, 29), "text--xxlarge": (38, 42)}


class Style:
    """What the framework's classes come to for one element. Lengths are in the framework's pixels (times scale)."""

    def __init__(self):
        self.dir = "col"
        self.gap = 0.0
        self.ai = "stretch"     # start | center | end | stretch
        self.jc = "start"       # start | center | end | between
        self.pt = self.pr = self.pb = self.pl = 0.0
        self.mt = self.mb = self.mr = 0.0
        self.w = None           # a fixed width
        self.h = None
        self.full = False       # as wide as it may be
        self.grow = False       # takes what is left on its parent's main axis
        self.shrink = False     # in a row: gives way when the row is too wide
        self.text = None        # a key of TEXT
        self.spec = None        # (font file, size, line height, weight): the key's, as text--SIZE and text--bold change it
        self.stretch = False    # a picture drawn over its whole box (image--fill), not in its own proportions
        self.color = "black"    # black | white | gray
        self.bg = None          # light | dark | black | white
        self.radius = 0.0
        self.border = 0
        self.underline = False
        self.clamp = 0
        self.fit = False
        self.even = False       # data-pixel-perfect: a whole number of pixels wide, even or odd as its place is
        self.align = "left"
        self.halo = False
        self.hidden = False
        self.line = 0           # the border's gray
        self.foot = False       # a title bar with the rounder foot it has where there are grays
        self.feat = None        # font features (tabular figures; no forms that follow the neighbours)
        self.kind = "box"       # box | text | icon | columns | grid | track | fill


def _style(n: Node, s: float, bits: int = 1, dense: bool = False) -> Style:
    st = Style()
    c, p = n.cls, n.parent
    px = lambda v: v * s  # noqa: E731
    T = TEXT_DENSE if dense else TEXT
    st.hidden = "hidden" in c
    if n.tag == "img" and not n.up("title_bar"):  # a picture of its own size (w--N h--N: N times 4 of the framework's pixels; w--full: as wide as its place)
        side = lambda axis: next((px(4 * float(x[3:])) for x in c if re.fullmatch(axis + r"--\d+(\.5)?", x)), None)  # noqa: E731
        st.kind, st.full, st.stretch = "image", "w--full" in c, "image--fill" in c
        st.w, st.h = None if st.full else side("w") or side("h") or px(24), side("h") or side("w") or px(24)
        return st
    if n.tag == "img":
        big = bits >= 2 and n.up("view--full") is not None  # where there are grays, the full view's bar has a larger mark
        st.kind, st.w, st.h, st.halo = "icon", px(28 if big else 24), px(28 if big else 24), bool(n.up("title_bar")) and (bits < 4 or dense)
        return st
    if n.tag == "span":
        st.kind = "text"
        bar = p is not None and "title_bar" in p.cls
        if bar:
            st.text, st.halo = "bar", bits < 4 or dense  # on a plain gray bar the letters need no white around them (a dense screen keeps it)
            if "instance" in c:
                st.grow, st.align, st.shrink = True, "right", True
                st.color = "dim" if bits >= 2 else "black"
        else:
            for base in ("value", "title", "label", "description"):
                if base in c:
                    sized = [k for k in T if k.startswith(base + "--") and k in c]
                    st.text = sized[0] if sized else base
                    break
            else:
                st.text = "label"
        st.spec = T[st.text]
        if dense and not bar:
            for k, (size, line) in TEXT_SIZE.items():
                if k in c:
                    st.spec = (st.spec[0], size, line, st.spec[3])
            if "text--bold" in c:
                st.spec = st.spec[:3] + (700,)
        in_item = n.up("item") is not None
        # the room around the letters is the plain class's: a size for the large screen changes the letters alone
        if "label" in n.own and "label--small" in n.own:
            st.pt, st.pb = (px(2), px(1)) if in_item else (px(1), px(1))
        if "description" in n.own and not any(_family(x) == "description" for x in n.own):
            st.pt = px(1)
        if st.text == "label--small" and bits >= 2 and p is not None and "content" in p.cls and p.parent is not None and "progress-bar" in p.parent.cls:
            st.text = "label--small-bold"
            st.spec = T[st.text]
        if "label--gray" in c:
            st.color = "gray"
        if "label" in c and in_item and bits >= 2:  # where there are grays, what stands under an item's title is dark gray
            st.color = "dim"
        for name, ink in (("label--error", "red"), ("label--primary", "blue"), ("label--inverted", "black")):  # inverted last: it is what a screen of grays puts back
            if name in c:
                st.color, st.bg, st.radius, st.pl, st.pr = "white", ink, px(4), px(5), px(5)
        if {"label--inverted", "label--error", "label--primary"} & c:
            if not any(_family(x) == "label" for x in n.own):  # the full-size label has a pixel of black above and below its line
                st.pt, st.pb = px(1), px(1)
        if "label--outline" in c:
            st.border, st.radius, st.pl, st.pr, st.pt = (px(1) if dense else 1), px(4), px(2), px(2), 0  # a line of one of the framework's pixels
        if "label--underline" in c:
            st.underline = True
        if "group-header" in c:
            st.full = True
        try:
            st.clamp = max(0, int(n.attrs.get("data-clamp") or 0))
        except ValueError:
            st.clamp = 0
        st.fit = n.attrs.get("data-fit-value") == "true"
        st.even = n.attrs.get("data-pixel-perfect") == "true"
        if RAQM and st.spec[0] == "Inter":
            # the framework has font-variant-ligatures: none, which leaves out the forms a letter takes from its
            # neighbours too (Inter raises @ and : beside capitals and figures)
            st.feat = ["-liga", "-clig", "-calt"] + (["tnum"] if "value--tnums" in c else [])
        elif RAQM and "value--tnums" in c:
            st.feat = ["tnum"]  # the pixel typefaces have figures of one width too
        st.shrink = st.shrink or bool(st.clamp) or st.fit
        if "w--full" in c:
            st.full = True
        return st
    # boxes
    if "view" in c:
        st.dir, st.ai = "col", "stretch"
    elif "layout" in c:
        st.dir = "col" if "layout--col" in c else "row"
        st.gap, st.grow = px(GAP), True
        st.ai = st.jc = "center"
        if "layout--top" in c:
            if st.dir == "row":
                st.ai, st.jc = "start", "start"
            else:
                st.jc = "start"
        if "layout--left" in c:
            if st.dir == "row":
                st.jc = "start"
            else:
                st.ai = "start"
        if "layout--stretch-x" in c or "layout--stretch" in c:
            if st.dir == "col":
                st.ai = "stretch"
            else:
                st.jc = "stretch"
    elif "grid" in c:
        st.kind, st.dir, st.ai, st.gap = "grid", "row", "stretch", px(GAP)
    elif "columns" in c:
        st.kind, st.dir, st.ai, st.gap, st.full = "columns", "row", "start", px(GAP), True
    elif "column" in c:
        st.dir, st.gap = "col", px(GAP)
    elif "item" in c:
        st.dir, st.ai, st.gap = "row", "stretch", px(2)
    elif "meta" in c:
        st.w, st.mr, st.bg, st.radius = px(10), px(7), "light", px(4 if bits >= 4 else 3)
    elif "progress-bar" in c:
        st.dir = "col"
    elif "track" in c:
        st.kind, st.full, st.bg, st.border, st.radius = "track", True, "light", 1, px(10)
        bar = p.cls if p is not None else set()
        st.h = px(6 if "progress-bar--xsmall" in bar else 12 if "progress-bar--small" in bar else 20 if "progress-bar--large" in bar else 16)
        if bits >= 4:
            st.radius = st.h / 3
        st.line = 0 if bits == 1 else 0xCC
    elif "fill" in c:
        st.kind, st.bg = "fill", "dark"
    elif "title_bar" in c:
        st.dir, st.ai, st.gap, st.pl, st.pr, st.bg = "row", "center", px(GAP), px(GAP), px(GAP), "light"
    elif "content" in c:
        if p is not None and "progress-bar" in p.cls:
            st.dir, st.ai, st.jc, st.mb = "row", "end", "between", px(5)
        else:
            st.dir, st.ai, st.jc, st.shrink = "col", "start", "end", True
    elif "flex" in c:
        st.gap = px(GAP)
        if "flex--col" in c:
            st.dir, st.ai = "col", "center"
            if "flex--left" in c:
                st.ai, st.jc = "start", "center"
            if "flex--right" in c:
                st.ai, st.jc = "end", "center"
            if "flex--center" in c:
                st.ai, st.jc = "center", "center"
            if "flex--top" in c:
                st.jc = "start"
        else:
            st.dir = "row"
            if "flex--row" in c:
                st.ai, st.jc = "center", "center"
            if "flex--left" in c:
                st.jc = "start"
            if "flex--right" in c:
                st.jc = "end"
            if "flex--center" in c:
                st.ai, st.jc = "center", "center"
            if "flex--top" in c:
                st.ai = "start"
        if "flex--between" in c:
            st.jc = "between"
        st.shrink = True
    for g, v in (("gap--xsmall", 5), ("gap--small", 7), ("gap--base", 10), ("gap--medium", 16), ("gap--large", 20), ("gap--xlarge", 30), ("gap--none", 0)):
        if g in c and st.kind in ("box", "grid", "columns"):
            st.gap = px(v)
    exact = next((x for x in c if re.fullmatch(r"gap--\[\d+px\]", x)), None)  # a gap of so many of the framework's pixels
    if exact and st.kind in ("box", "grid", "columns"):
        st.gap = px(int(exact[6:-3]))
    for tone in TONES:
        if f"bg--{tone}" in c:
            st.bg = tone
        if f"text--{tone}" in c and st.kind == "text":
            st.color = tone
    if "w--full" in c:
        st.full = True
    if "h--full" in c and st.kind == "box":  # as tall as its place (a box in a column: in the suite's markup, the colour of an item's meta)
        st.grow = True
    wide = next((x for x in c if re.fullmatch(r"w--\d+", x)), None)  # a box of a set width: N times 4 of the framework's pixels
    if wide and st.kind == "box":
        st.w = px(4 * int(wide[3:]))
    return st


class Drawer:
    def __init__(self, scale: float = 1.0, bits: int = 1, dense: bool = None, inks: bool = False):
        """inks: a panel of coloured inks (Spectra 6), which prints each pixel in the nearest ink and no grays: it is
        drawn as a 1-bit screen (the grays as the framework's patterns) where the markup's colours are inks."""
        self.s = scale
        self.inks = inks
        bits = 1 if inks else bits
        self.bits = bits
        self.dense = scale >= 1.5 if dense is None else dense  # the framework's own rule: from 1.5 device pixels to one of its own
        self.T = TEXT_DENSE if self.dense else TEXT

    # -- text ----
    def font(self, n: Node, shrink: int = 0):
        name, size, lh, weight = n.st.spec
        size, lh = size - shrink, math.floor((lh - shrink) * 64) / 64  # a browser counts lengths in 64ths of a pixel
        # where the baseline is in a line, worked out at the framework's own size as a browser does (whole pixels
        # there), then scaled: on a denser screen the page is laid out first and magnified after
        if name == "Inter":  # each to its nearest whole pixel, as a browser does (FreeType, which Pillow asks, rounds both up)
            asc, desc = (math.floor(v * size + 0.5) for v in _rise(name))
        else:
            asc, desc = _font(name, size, weight, size).getmetrics()
        n.base = (math.floor((lh - (asc + desc)) / 2) + asc) * self.s
        # a pixel typeface at whole sizes; Inter at the very size (a denser screen: 16 becomes 28.8)
        return _font(name, size * self.s if name == "Inter" else round(size * self.s), weight, size), lh * self.s

    def _text(self, n: Node, aw: float):
        """Lays a text element out in aw: n.lines, n.font; returns (width, height) of the text itself."""
        st = n.st
        font, lh = self.font(n)
        text = n.text
        if not text:
            n.lines, n.font = [], (font, lh)
            return 0, 0
        width = lambda t: font.getlength(t, features=st.feat)  # noqa: E731
        if st.fit:  # a number that does not fit is set smaller until it does
            shrink = 0
            while width(text) > aw and st.spec[1] - shrink > 8:
                shrink += 1
                font, lh = self.font(n, shrink)
                width = lambda t: font.getlength(t, features=st.feat)  # noqa: E731
        if st.clamp == 1 or st.text == "bar":
            if width(text) > aw:
                lo, hi, best = 0, len(text), 0
                while lo <= hi:
                    mid = (lo + hi) // 2
                    if width(text[:mid] + "...") <= aw:
                        best, lo = mid, mid + 1
                    else:
                        hi = mid - 1
                text = text[:best] + "..."
            lines = [text]
        else:
            lines, line = [], ""
            for word in text.split(" "):
                t = (line + " " + word) if line else word
                if line and width(t) > aw:
                    lines.append(line)
                    line = word
                else:
                    line = t
            lines.append(line)
            if st.clamp and len(lines) > st.clamp:
                last = " ".join(lines[st.clamp - 1:])
                k = len(last)
                while k > 0 and width(last[:k] + "...") > aw:
                    k -= 1
                lines = lines[:st.clamp - 1] + [last[:k] + "..."]
        n.lines, n.font = lines, (font, lh)
        return max(width(x) for x in lines), lh * len(lines)

    # -- sizes ----
    def kids(self, n: Node):
        return [k for k in n.kids if not k.st.hidden]

    def size(self, n: Node, aw: float, full: bool = False):
        """(width, height) of an element given the width it may take; full: it takes all of it."""
        st = n.st
        if st.w is not None:
            aw = st.w
        b = st.border
        inner = max(0.0, aw - st.pl - st.pr - 2 * b)
        if st.kind == "text":
            cw, ch = self._text(n, inner)
            if st.even and self.bits <= 2 and not self.dense and cw:
                # data-pixel-perfect, where there are no grays to soften a letter that falls between two pixels: the
                # framework makes the text a whole number of pixels wide, even where its place is even and odd where
                # that is odd, so that set in the middle it starts on a whole pixel. (Not on a magnified screen,
                # where the framework's pixels are not the screen's.)
                cw = math.ceil(cw - 1e-6)
                cw += (cw - round(aw)) % 2
        elif st.kind in ("icon", "image"):
            return (aw if st.w is None else st.w), st.h
        elif st.kind in ("track", "fill"):
            cw, ch = inner, 0
        elif st.kind == "columns":
            cw, ch = inner, self._columns(n, inner)
        elif st.dir == "row":
            sz = self._row(n, inner)
            ks = self.kids(n)
            cw = sum(w for w, _ in sz) + st.gap * max(0, len(sz) - 1) + sum(k.st.mr for k in ks)
            ch = max([h for _, h in sz], default=0)
        else:
            ks = self.kids(n)
            sz = [self.size(k, inner, st.ai == "stretch") for k in ks]
            # a picture as wide as its place (w--full) takes the width the others come to, and adds none of its own
            cw = max([w for k, (w, _) in zip(ks, sz) if not (k.st.kind == "image" and k.st.w is None)], default=0)
            ch = sum(h for _, h in sz) + st.gap * max(0, len(sz) - 1) + sum(k.st.mt + k.st.mb for k in ks)
        w = st.w if st.w is not None else aw if (full or st.full) else min(aw, cw + st.pl + st.pr + 2 * b)
        h = st.h if st.h is not None else ch + st.pt + st.pb + 2 * b
        return w, h

    def _row(self, n: Node, inner: float):
        """The (width, height) of each child of a row that is `inner` wide: fixed ones keep theirs, the ones that
        may give way (clamped text, boxes) share what is left when the row is too wide, a growing one takes the rest."""
        st, ks = n.st, self.kids(n)
        if st.kind == "grid":
            colw, gap = self._grid(n, inner)
            out = []
            for k in ks:
                span = next((int(x.split("-")[-1]) for x in k.cls if x.startswith("col--span-") and x.split("-")[-1].isdigit()), 1)
                w = colw * span + gap * (span - 1)
                out.append((w, self.size(k, w, True)[1]))
            return out
        room = inner - st.gap * max(0, len(ks) - 1) - sum(k.st.mr for k in ks)
        if st.jc == "stretch" and ks:
            each = room / len(ks)
            return [(each, self.size(k, each, True)[1]) for k in ks]
        nat = [self.size(k, room, False) for k in ks]
        widths = [w for w, _ in nat]
        for i, k in enumerate(ks):
            if k.st.full or k.st.grow:
                widths[i] = 0 if k.st.grow else room
        over = sum(widths) - room
        if over > 0:
            soft = sorted((i for i, k in enumerate(ks) if k.st.shrink or k.st.full), key=lambda i: widths[i])
            left = max(0.0, room - sum(w for i, w in enumerate(widths) if i not in soft))
            for at, i in enumerate(soft):  # the narrow ones keep their width, the widest give way
                widths[i] = min(widths[i], left / (len(soft) - at))
                left -= widths[i]
        grow = [i for i, k in enumerate(ks) if k.st.grow]
        if grow:
            rest = max(0.0, room - sum(widths))
            for i in grow:
                widths[i] = rest / len(grow)
        return [(w, self.size(k, w, True)[1]) for k, w in zip(ks, widths)]

    def _grid(self, n: Node, inner: float):
        cols = next((int(x.split("-")[-1]) for x in n.cls if x.startswith("grid--cols-") and x.split("-")[-1].isdigit()), max(1, len(self.kids(n))))
        colw = round((inner - n.st.gap * (cols - 1)) / cols / self.s) * self.s  # whole pixels (the framework's) a column, the gap takes the rest
        gap = (inner - cols * colw) / (cols - 1) if cols > 1 else 0
        return colw, gap

    # -- columns that overflow ----
    def _columns(self, n: Node, inner: float) -> float:
        """Fills the columns of a .columns[data-overflow] as the framework does: the fewest columns that hold
        everything (data-overflow-max-cols at most), a group's header never left alone at the foot of one and said
        again in gray where its group goes on, and "and N more" for what did not fit. Sets n.cols; returns the height."""
        src = [k for col in n.kids if "column" in col.cls for k in col.kids if not k.st.hidden]
        layout = n.up("layout")
        budget = getattr(layout, "budget", INF) if layout is not None else INF
        if budget < INF and n.parent is layout and layout.st.dir != "row":
            # what stands above and below the columns in their layout (a header line) is not theirs to fill
            for k in self.kids(layout):
                if k is not n:
                    budget -= self.size(k, layout.room, layout.st.ai == "stretch")[1] + k.st.mt + k.st.mb + layout.st.gap
        try:
            most = max(1, int(n.attrs.get("data-overflow-max-cols") or 1))
        except ValueError:
            most = 1
        if n.attrs.get("data-overflow") != "true":
            most, budget = max(1, len([c for c in n.kids if "column" in c.cls])), INF
        gap = self.s * GAP  # between a column's lines; between the columns it is the gap the element asks for
        head = lambda k: "group-header" in k.cls  # noqa: E731
        best = None
        for count in range(1, most + 1):
            colw = round((inner - n.st.gap * (count - 1)) / count / self.s) * self.s
            hs = [self.size(k, colw, True)[1] for k in src]
            cols, y, hidden, group, i = [[]], 0.0, 0, None, 0
            while i < len(src):
                k = src[i]
                top = (gap if cols[-1] else 0) + (16 * self.s if head(k) and cols[-1] else 0)
                need = top + hs[i]
                if head(k) and i + 1 < len(src) and not head(src[i + 1]):
                    need += gap + hs[i + 1]
                if y + need <= budget + 0.01:
                    cols[-1].append((k, y + top, hs[i]))
                    y += top + hs[i]
                    if head(k):
                        group = k
                    i += 1
                    continue
                if len(cols) == count or not cols[-1]:
                    hidden = len([x for x in src[i:] if not head(x)])
                    break
                cols.append([])
                y = 0.0
                if not head(k) and group is not None:  # the group goes on: its header again, in gray
                    again = Node("span", {"class": "label label--base label--gray group-header"}, group.parent)
                    again.text = group.text
                    again.st = _style(again, self.s, self.bits, self.dense)
                    h = self.size(again, colw, True)[1]
                    cols[-1].append((again, 0.0, h))
                    y = h
            if hidden and n.attrs.get("data-overflow-counter") == "true":
                more_h = 20 * self.s
                last = cols[-1]
                while last and last[-1][1] + last[-1][2] + gap + more_h > budget + 0.01:
                    if not head(last[-1][0]):
                        hidden += 1
                    last.pop()
                while last and head(last[-1][0]):
                    last.pop()
                more = Node("div", {"class": "item"}, n)
                meta, content = Node("div", {"class": "meta"}, more), Node("div", {"class": "content"}, more)
                label = Node("span", {"class": "label label--gray"}, content)
                label.text = f"and {hidden} more"
                more.kids, content.kids = [meta, content], [label]
                for x in (more, meta, content, label):
                    x.st = _style(x, self.s, self.bits, self.dense)
                top = (last[-1][1] + last[-1][2] + gap) if last else 0.0
                last.append((more, top, self.size(more, colw, True)[1]))
            best = (cols, colw, count)
            if not hidden:
                break
        cols, colw, count = best
        n.cols = (cols, colw, (inner - count * colw) / (count - 1) if count > 1 else 0)
        return max([c[-1][1] + c[-1][2] for c in cols if c], default=0)

    # -- places ----
    def place(self, n: Node, x: float, y: float, w: float, h: float):
        st = n.st
        n.box = (x, y, w, h)
        b = st.border
        ix, iy, iw, ih = x + st.pl + b, y + st.pt + b, w - st.pl - st.pr - 2 * b, h - st.pt - st.pb - 2 * b
        if "layout" in n.cls:
            n.budget, n.room = ih, iw
        if st.kind == "text":
            self._text(n, max(0.0, iw))
            return
        if st.kind == "track":
            for k in n.kids:
                try:
                    pct = float((k.attrs.get("style") or "").split("width:")[1].split("%")[0])
                except (IndexError, ValueError):
                    pct = 0.0
                k.box = (ix, iy, iw * max(0.0, min(100.0, pct)) / 100, ih)
            return
        if st.kind == "columns":
            self._columns(n, iw)
            cols, colw, gap = n.cols
            for ci, col in enumerate(cols):
                for k, top, kh in col:
                    self.place(k, ix + ci * (colw + gap), iy + top, colw, kh)
            return
        ks = self.kids(n)
        if not ks:
            return
        if st.dir == "row":
            sz = self._row(n, iw)
            gap = self._grid(n, iw)[1] if st.kind == "grid" else st.gap
            used = sum(sw for sw, _ in sz) + gap * (len(ks) - 1) + sum(k.st.mr for k in ks)
            free = max(0.0, iw - used)
            cx = ix + (free / 2 if st.jc == "center" else free if st.jc == "end" else 0)
            step = free / (len(ks) - 1) if st.jc == "between" and len(ks) > 1 else 0
            for k, (kw, kh) in zip(ks, sz):
                if (st.ai == "stretch" or "item" in k.cls) and k.st.h is None:  # an item is as tall as its row, whatever the row says
                    kh, ky = ih, iy
                else:
                    ky = iy + (0 if st.ai == "start" else ih - kh if st.ai == "end" else (ih - kh) / 2)
                self.place(k, cx, ky, kw, kh)
                cx += kw + gap + k.st.mr + step
        else:
            sz = []
            for k in ks:
                if k.st.grow:
                    sz.append(None)
                    continue
                kw, kh = self.size(k, iw, st.ai == "stretch")
                sz.append((kw, kh))
            fixed = sum(s[1] for s in sz if s) + st.gap * (len(ks) - 1) + sum(k.st.mt + k.st.mb for k in ks)
            grow = [i for i, s in enumerate(sz) if s is None]
            for i in grow:
                sz[i] = (iw, max(0.0, ih - fixed) / len(grow))
            free = 0 if grow else max(0.0, ih - fixed)
            cy = iy + (free / 2 if st.jc == "center" else free if st.jc == "end" else 0)
            step = free / (len(ks) - 1) if st.jc == "between" and len(ks) > 1 else 0
            for k, (kw, kh) in zip(ks, sz):
                kx = ix + (0 if st.ai in ("start", "stretch") else iw - kw if st.ai == "end" else (iw - kw) / 2)
                cy += k.st.mt
                self.place(k, kx, cy, kw, kh)
                cy += kh + k.st.mb + st.gap + step

    # -- paint ----
    def tile(self, tone: str) -> Image.Image:
        return _tile(tone, self.bits)

    def value(self, tone: str) -> int:
        """The value of black, white or an ink in the picture as it is drawn (an ink is black where there is none)."""
        return 255 if tone == "white" else INK[tone] if tone in INK and self.inks else 0

    def put(self, img: Image.Image, v, at, mask: Image.Image = None):
        """img.paste, but where inks are drawn a pixel is all one thing or another (the panel has nothing between),
        so that an ink keeps its own value: the mask is cut at its middle, where a 1-bit screen's would be."""
        if self.inks and mask is not None:
            mask = mask.point(lambda x: 255 if x >= 128 else 0)
        img.paste(v, at, mask)

    def fill(self, img: Image.Image, mask: Image.Image, at, tone: str, origin: int = 0):
        """Paints `tone` (black, white, an ink, light, dark) through a mask placed at `at`; the grays are the
        framework's dither patterns, starting at the element's own corner (inside its border: origin) as a CSS
        background does."""
        if tone in TONES:
            self.put(img, self.value(tone), at, mask)
            return
        t = self.tile(tone)
        pat = Image.new("L", mask.size)
        for ty in range(origin % 16 - 16 if origin % 16 else 0, mask.size[1], 16):
            for tx in range(origin % 16 - 16 if origin % 16 else 0, mask.size[0], 16):
                pat.paste(t, (tx, ty))
        self.put(img, pat, at, mask)

    def paint(self, img: Image.Image, n: Node):
        st = n.st
        if st.hidden or n.box is None:
            return
        x, y, w, h = n.box
        X, Y = _r(x), _r(y)
        Wd, Ht = max(0, _r(x + w) - X), max(0, _r(y + h) - Y)
        if st.bg and Wd and Ht and st.kind != "fill":
            self.fill(img, _rounded(Wd, Ht, _radius(n, self.s), _corners(n)), (X, Y), st.bg, _r(st.border))
        if st.border and Wd and Ht:
            b = max(1, _r(st.border))
            ring = ImageChops.subtract(_rounded(Wd, Ht, st.radius), _inset(_rounded(Wd - 2 * b, Ht - 2 * b, max(0, st.radius - b)), Wd, Ht, b))
            self.put(img, st.line, (X, Y), ring)
        if st.kind == "track":
            for k in n.kids:  # the fill, inside the track's rounded shape
                kx, ky, kw, kh = k.box
                KX, KY, KW, KH = _r(kx), _r(ky), _r(kx + kw) - _r(kx), _r(ky + kh) - _r(ky)
                if KW > 0 and KH > 0:
                    self.fill(img, _rounded(Wd - 2, Ht - 2, max(0, st.radius - 1)).crop((0, 0, KW, KH)), (KX, KY), "dark")
            return
        if st.kind == "icon":
            self._icon(img, X, Y, _r(w), st.halo)
            return
        if st.kind == "image":
            src, at = n.attrs.get("src") or "", (0.0, 0.0)
            if self.dense:  # a browser sets a picture on whole pixels of the framework's, which fall between the screen's
                s = self.s
                left, top, right, foot = (_r(v / s + 1e-6) * s for v in (x, y, x + w, y + h))
                X, Y = math.floor(left), math.floor(top)
                at, Wd, Ht = (round((left - X) * 8) / 8, round((top - Y) * 8) / 8), round((right - left) * 8) / 8, round((foot - top) * 8) / 8
            if self.inks:  # each shape in its own colour, the later over the earlier
                for tone, mask in glyph_inks(src, max(1, Wd), max(1, Ht), st.stretch, at):
                    self.put(img, self.value(tone), (X, Y), mask)
                return
            mask = glyph(src, max(1, Wd), max(1, Ht), st.stretch, at)
            if mask is not None:
                img.paste(0, (X, Y), mask)
            return
        if st.kind == "text":
            self._paint_text(img, n)
            return
        if st.kind == "columns" and n.cols:
            for col in n.cols[0]:
                for k, _, _ in col:
                    self.paint(img, k)
            return
        for k in n.kids:
            self.paint(img, k)

    def _paint_text(self, img: Image.Image, n: Node):
        st = n.st
        x, y, w, h = n.box
        font, lh = n.font
        b = st.border
        left, top = x + st.pl + b, y + st.pt + b
        if st.text == "bar":  # the title bar's text sits in the middle of the bar
            top = y + (h - lh) / 2 + (0.5 * self.s if st.halo and not self.dense else 0)
        X, Y, Wd, Ht = _r(x), _r(y), _r(x + w) - _r(x), _r(y + h) - _r(y)
        if st.underline and Wd and Ht:  # a line under the whole element: dotted where there is no gray
            thick = max(1, round(self.s)) if self.dense else 1  # one of the framework's pixels
            for dx in range(0, Wd, 2 if self.bits == 1 else 1):
                for dy in range(thick):
                    img.putpixel((X + dx, Y + Ht - 1 - dy), 0 if self.bits == 1 else 0xAA if self.bits < 4 else 0x99)
        for i, line in enumerate(n.lines or []):
            tw = font.getlength(line, features=st.feat)
            lx = left if st.align == "left" else x + w - st.pr - tw
            base = top + i * lh + n.base
            pos = (_r(lx), _r(base))
            if self.dense and not st.halo:
                self._fine(img, line, font, st, lx, base)
                continue
            if (st.color == "gray" and self.bits < 4) or self.inks:
                mask = Image.new("L", (Wd, Ht), 0)
                if st.halo and self.inks:
                    halo = Image.new("L", (Wd, Ht), 0)
                    ImageDraw.Draw(halo).text((pos[0] - X, pos[1] - Y), line, font=font, fill=255, anchor="ls", features=st.feat,
                                              stroke_width=max(1, round((1 if self.dense else 2) * self.s)), stroke_fill=255)
                    self.put(img, 255, (X, Y), halo)
                ImageDraw.Draw(mask).text((pos[0] - X, pos[1] - Y), line, font=font, fill=255, anchor="ls", features=st.feat)
                self.fill(img, mask, (X, Y), "dark" if st.color == "gray" else st.color if st.color in TONES else "black")
                continue
            d = ImageDraw.Draw(img)
            if st.halo:  # white around the letters, so they stand out from the bar's pattern
                d.text(pos, line, font=font, fill=255, anchor="ls", stroke_width=max(1, round((1 if self.dense else 2) * self.s)), stroke_fill=255, features=st.feat)
            d.text(pos, line, font=font, fill={"gray": 0x77, "dim": 0x55}.get(st.color) or self.value(st.color), anchor="ls", features=st.feat)

    def _fine(self, img: Image.Image, line: str, font, st: Style, x: float, base: float):
        """A line of letters on a dense screen, as a browser sets them there: each letter where it falls along the
        line, between pixels too, with stems of their own width. Drawn four times as large and brought down, since
        FreeType at the size itself fits every stem and every step to whole pixels, which makes the letters heavier
        and shifts them."""
        k = 4
        name, _, _, weight = st.spec
        big = _font(name, font.size * k, weight, font.size / self.s)
        base = _r(_r(base / self.s + 1e-6) * self.s)  # the baseline on a whole pixel of the framework's (a half goes down the page), then on one of the screen's
        X, Y = math.floor(x), math.floor(base)
        fx, fy = (x - X) * k, (base - Y) * k
        l, t, r, b = big.getbbox(line, anchor="ls", features=st.feat)
        x0, y0, x1, y1 = math.floor((l + fx) / k) - 1, math.floor((t + fy) / k) - 1, math.ceil((r + fx) / k) + 1, math.ceil((b + fy) / k) + 1
        mask = Image.new("L", ((x1 - x0) * k, (y1 - y0) * k), 0)
        ImageDraw.Draw(mask).text((fx - x0 * k, fy - y0 * k), line, font=big, fill=255, anchor="ls", features=st.feat)
        mask = mask.resize((x1 - x0, y1 - y0), Image.BOX)
        if st.color == "gray" and self.bits < 4:
            self.fill(img, mask, (X + x0, Y + y0), "dark")
        else:
            self.put(img, {"gray": 0x77, "dim": 0x55}.get(st.color) or self.value(st.color), (X + x0, Y + y0), mask)

    def _icon(self, img: Image.Image, X: int, Y: int, size: int, halo: bool):
        """The suite's mark (common.liquid's SVG: four tiles, a narrow one and the sun)."""
        k = 8
        big = Image.new("L", (24 * k, 24 * k), 0)
        d = ImageDraw.Draw(big)
        d.ellipse((16 * k, 2 * k, 22 * k - 1, 8 * k - 1), fill=255)
        for rx, ry, rw in ((2, 9, 6), (10, 9, 6), (2, 17, 6), (10, 17, 6), (18, 17, 4)):
            d.rounded_rectangle((rx * k, ry * k, (rx + rw) * k - 1, (ry + 6) * k - 1), radius=1.5 * k, fill=255)
        mask = big.resize((size, size), Image.LANCZOS)
        if halo:
            r = max(1, round((1 if self.dense else 3) * self.s))
            wide = Image.new("L", (size + 2 * r, size + 2 * r), 0)
            wide.paste(mask.point(lambda v: 255 if v >= 128 else 0), (r, r))
            self.put(img, 255, (X - r, Y - r), wide.filter(ImageFilter.MaxFilter(2 * r + 1)))
        self.put(img, 0, (X, Y), mask)

    # -- a whole screen ----
    def view(self, markup: str, size: str, w: float, h: float) -> Image.Image:
        """One view (the markup of one screen in one size), w x h of the framework's pixels, as its own picture."""
        s = self.s
        root = Node("div", {"class": "view view--" + size})
        root.kids = parse(markup)
        for k in root.kids:
            k.parent = root
        for n in _walk(root):
            n.cls = classes(n.cls, self.dense, self.bits, self.inks)  # a dense screen is the large one (the TRMNL X)
        for n in _walk(root):
            n.st = _style(n, s, self.bits, self.dense)
        full = size == "full"
        bars = [k for k in root.kids if "title_bar" in k.cls]
        for k in root.kids:
            if "layout" in k.cls:
                if full:
                    k.st.mb = s * GAP if bars else 0
                else:
                    k.st.pt = k.st.pr = k.st.pb = k.st.pl = s * GAP
            if "title_bar" in k.cls:
                k.st.h = s * (40 if full else 32)
                k.st.foot = self.bits >= 2
        img = Image.new("L", (round(w * s), round(h * s)), 255)
        self.place(root, 0, 0, w * s, h * s)
        for k in root.kids:
            if "title_bar" not in k.cls:
                self.paint(img, k)
        for k in bars:  # over whatever ran past the layout
            self.paint(img, k)
        return img

    def screen(self, views: list, layout: str = "full", width: int = None, height: int = None) -> Image.Image:
        """The picture of a whole screen: views = the markup of each view of the layout, in order (sizes(layout)
        says which size of markup each takes). width/height: the device's pixels (default: the framework's 800x480
        times the scale)."""
        s = self.s
        width, height = width or round(W * s), height or round(H * s)
        img = Image.new("L", (width, height), 255)
        cells = LAYOUTS[layout]
        g = s * GAP
        aw, ah = width - 2 * g, height - 2 * g
        cw, ch = (aw - g) / 2, (ah - g) / 2
        for markup, size, (cx, cy, cs, rs) in zip(views, sizes(layout), cells):
            x, y = g + cx * (cw + g), g + cy * (ch + g)
            w, h = (aw if cs == 2 else cw), (ah if rs == 2 else ch)
            X, Y = _r(x), _r(y)
            Wd, Ht = round(x + w) - X, round(y + h) - Y
            pic = self.view(markup, size, Wd / s, Ht / s).crop((0, 0, Wd, Ht))
            if size == "full":
                img.paste(pic, (X, Y))
                continue
            r = round(7 * s)
            self.put(img, pic, (X, Y), _rounded(Wd, Ht, r))
            self._frame(img, X, Y, Wd, Ht, r)
        return inked(img) if self.inks else quantize(img, self.bits)

    def _frame(self, img: Image.Image, X: int, Y: int, Wd: int, Ht: int, r: int):
        """The line around a mashup's view: dotted on a 1-bit screen, light gray where there are grays."""
        line = Image.new("L", (Wd, Ht), 0)
        ImageDraw.Draw(line).rounded_rectangle((0, 0, Wd - 1, Ht - 1), radius=r, outline=255, width=1)
        if self.bits >= 2:
            img.paste(0xCC, (X, Y), line)
            return
        px = line.load()
        for yy in range(Ht):
            for xx in range(Wd):
                if not px[xx, yy]:
                    continue
                edge_x, edge_y = min(xx, Wd - 1 - xx), min(yy, Ht - 1 - yy)
                if edge_x >= r and edge_y >= r:
                    continue
                straight = (edge_y == 0 and edge_x > r and xx % 4 == 0) or (edge_x == 0 and edge_y > r and yy % 4 == 0)
                corner = edge_x <= r and edge_y <= r and (edge_x, edge_y) in ((4, 1), (1, 4))
                if straight or corner:
                    img.putpixel((X + xx, Y + yy), 0)


# ---- a glyph: the SVG of an img's data: address ------------------------------------------------------------------

class _Svg(html.parser.HTMLParser):
    """The shapes of a small SVG, in order: (kind, numbers, fill?, stroke width, round caps?, more). kind: circle
    (cx, cy, r; more: its dashes and where they start, when it has stroke-dasharray) or line (points)."""

    def __init__(self):
        super().__init__()
        self.box, self.shapes, self.inherit, self.stretch, self.tones = (0.0, 0.0, 24.0, 24.0), [], [{}], False, []

    def handle_starttag(self, tag, attrs):
        a = {**self.inherit[-1], **{k: v for k, v in attrs if v is not None}}
        if tag == "svg":
            nums = [float(x) for x in re.findall(r"-?\d*\.?\d+", a.get("viewbox") or "")]
            if len(nums) == 4 and nums[2] > 0 and nums[3] > 0:
                self.box = tuple(nums)
            self.stretch = (a.get("preserveaspectratio") or "").strip() == "none"
        if tag in ("svg", "g"):
            self.inherit.append({k: v for k, v in a.items() if k in ("fill", "stroke", "stroke-width", "stroke-linecap")})
            return
        fill = a.get("fill", "#000") != "none"
        width = float(a.get("stroke-width") or 1) if a.get("stroke", "none") != "none" else 0.0
        # its ink: the fill's, or the stroke's where it has one and no fill of its own (a line's black fill covers nothing)
        tone, before = _tone(a.get("fill", "#000") if fill and not (width and "fill" not in a) else a.get("stroke", "#000")), len(self.shapes)
        caps = a.get("stroke-linecap") == "round"
        num = lambda k: float(a.get(k) or 0)  # noqa: E731
        try:
            if tag == "circle":
                dash = [float(x) for x in re.findall(r"\d*\.?\d+", a.get("stroke-dasharray") or "")]
                turn = re.match(r"\s*rotate\(\s*(-?\d*\.?\d+)", a.get("transform") or "")  # about the circle's own middle
                more = (dash, float(turn.group(1)) if turn else 0.0) if len(dash) >= 2 and sum(dash) > 0 else None
                self.shapes.append(("circle", [num("cx"), num("cy"), num("r")], fill, width, caps, more))
            elif tag == "rect":
                x, y, w, h = num("x"), num("y"), num("width"), num("height")
                if w > 0 and h > 0:
                    self.shapes.append(("line", [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)], fill, width, True, None))
            elif tag == "polygon":
                nums = [float(x) for x in re.findall(r"-?\d*\.?\d+", a.get("points") or "")]
                pts = list(zip(nums[0::2], nums[1::2]))
                if len(pts) > 2:
                    self.shapes.append(("line", pts + [pts[0]], fill, width, True, None))
            elif tag == "path":
                for line, closed in _path(a.get("d") or ""):
                    self.shapes.append(("line", line, fill, width, caps or closed, None))
        except ValueError:
            pass
        self.tones.extend([tone] * (len(self.shapes) - before))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in ("svg", "g"):
            self.inherit.pop()

    def handle_endtag(self, tag):
        if tag in ("svg", "g") and len(self.inherit) > 1:
            self.inherit.pop()


def _path(d: str) -> list:
    """An SVG path as lines of points [(points, closed)]: M L H V A Z and their relative forms; an arc becomes the
    points along it."""
    tokens = re.findall(r"[MmLlHhVvAaZz]|-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", d)
    out, pts, x, y, i, cmd = [], [], 0.0, 0.0, 0, ""

    def num():
        nonlocal i
        v = float(tokens[i])
        i += 1
        return v

    def flag():  # an arc's flags may stand together with what follows ("0 1 0-2.5", "10")
        t = tokens[i]
        if len(t) > 1 and t[0] in "01" and not t.startswith(("0.", "1.")):
            tokens[i] = t[1:]
            return float(t[0])
        return num()

    try:
        while i < len(tokens):
            if tokens[i].isalpha():
                cmd = tokens[i]
                i += 1
                if cmd in "Zz":
                    if pts:
                        out.append((pts + [pts[0]], True))
                        x, y = pts[0]
                        pts = [(x, y)]
                    continue
            rel = cmd.islower()
            if cmd in "Mm":
                if len(pts) > 1:
                    out.append((pts, False))
                x, y = (x + num(), y + num()) if rel else (num(), num())
                pts = [(x, y)]
                cmd = "l" if rel else "L"  # the pairs after a move are lines
            elif cmd in "Ll":
                x, y = (x + num(), y + num()) if rel else (num(), num())
                pts.append((x, y))
            elif cmd in "Hh":
                x = x + num() if rel else num()
                pts.append((x, y))
            elif cmd in "Vv":
                y = y + num() if rel else num()
                pts.append((x, y))
            elif cmd in "Aa":
                rx, ry, turn, large, sweep = num(), num(), num(), flag(), flag()
                ex, ey = (x + num(), y + num()) if rel else (num(), num())
                pts.extend(_arc(x, y, rx, ry, turn, bool(large), bool(sweep), ex, ey))
                x, y = ex, ey
            else:
                break
    except (IndexError, ValueError):
        pass
    if len(pts) > 1:
        out.append((pts, False))
    return out


def _arc(x1, y1, rx, ry, turn, large, sweep, x2, y2) -> list:
    """The points along an SVG arc from (x1, y1) to (x2, y2), the end included (SVG 1.1, F.6.5)."""
    if rx == 0 or ry == 0 or (x1, y1) == (x2, y2):
        return [(x2, y2)]
    phi = math.radians(turn)
    c, s_ = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    xp, yp = c * dx + s_ * dy, -s_ * dx + c * dy
    rx, ry = abs(rx), abs(ry)
    lam = xp * xp / (rx * rx) + yp * yp / (ry * ry)
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    top = max(0.0, rx * rx * ry * ry - rx * rx * yp * yp - ry * ry * xp * xp)
    k = (-1 if large == sweep else 1) * math.sqrt(top / (rx * rx * yp * yp + ry * ry * xp * xp))
    cxp, cyp = k * rx * yp / ry, -k * ry * xp / rx
    cx, cy = c * cxp - s_ * cyp + (x1 + x2) / 2, s_ * cxp + c * cyp + (y1 + y2) / 2
    a1 = math.atan2((yp - cyp) / ry, (xp - cxp) / rx)
    da = math.atan2((-yp - cyp) / ry, (-xp - cxp) / rx) - a1
    if sweep and da < 0:
        da += 2 * math.pi
    elif not sweep and da > 0:
        da -= 2 * math.pi
    steps = max(4, int(abs(da) / (math.pi / 24)))
    out = []
    for j in range(1, steps + 1):
        a = a1 + da * j / steps
        ex, ey = rx * math.cos(a), ry * math.sin(a)
        out.append((c * ex - s_ * ey + cx, s_ * ex + c * ey + cy))
    out[-1] = (x2, y2)
    return out


def _tone(color: str) -> str:
    """An SVG colour as the inks name it: the nearest of black, white and INKS."""
    c = str(color or "").strip().lower()
    named = {"black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0), "green": (0, 128, 0), "lime": (0, 255, 0),
             "blue": (0, 0, 255), "yellow": (255, 255, 0)}
    if c in named:
        rgb = named[c]
    else:
        m = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})", c)
        if not m:
            return "black"  # currentColor and the like: the ink of the text, black here
        h = m.group(1) if len(m.group(1)) == 6 else "".join(x * 2 for x in m.group(1))
        rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return min(TONES, key=lambda t: sum((a - b) ** 2 for a, b in zip(rgb, PALETTE[1 if t == "black" else 0 if t == "white" else 2 + INKS.index(t)])))


@functools.lru_cache(maxsize=256)
def glyph_inks(src: str, w: float, h: float, fill: bool = False, at=(0.0, 0.0)) -> tuple:
    """glyph() for a panel of inks: ((tone, mask), ...), one for each run of shapes of one colour, in their order."""
    m = re.match(r"data:image/svg\+xml;base64,(.*)", src or "", re.S)
    if not m:
        return ()
    try:
        text = base64.b64decode(m.group(1), validate=False).decode("utf-8", "replace")
    except ValueError:
        return ()
    p = _Svg()
    p.feed(text)
    runs, out = [], []
    for i, tone in enumerate(p.tones):
        if runs and runs[-1][0] == tone:
            runs[-1][1].append(i)
        else:
            runs.append((tone, [i]))
    for tone, which in runs:
        out.append((tone, _draw(p, w, h, fill, at, set(which))))
    return tuple(out)


@functools.lru_cache(maxsize=256)
def glyph(src: str, w: float, h: float, fill: bool = False, at=(0.0, 0.0)):
    """The ink of an img whose src is an SVG in a data: address, as a mask (None when it is not one): drawn eight
    times as large and brought down, so its edges are as soft as a browser's. w x h: the picture's box, which may
    lie between pixels (at: how far into the mask's first pixel it starts; the mask is as many whole pixels as hold
    it). The drawing keeps its proportions in the middle of the box; an SVG that gives them up
    (preserveAspectRatio="none") in an img that fills its box (fill: image--fill) is stretched over all of it, which
    is how a graph is as wide as its place."""
    m = re.match(r"data:image/svg\+xml;base64,(.*)", src or "", re.S)
    if not m:
        return None
    try:
        text = base64.b64decode(m.group(1), validate=False).decode("utf-8", "replace")
    except ValueError:
        return None
    p = _Svg()
    p.feed(text)
    return _draw(p, w, h, fill, at)


def _draw(p, w: float, h: float, fill: bool, at, which: set = None) -> Image.Image:
    """The shapes of a read SVG (all, or those whose places are in `which`) as one mask: see glyph()."""
    k = 8
    bx, by, bw, bh = p.box
    f = min(w / bw, h / bh) * k  # the whole drawing, in the middle (preserveAspectRatio's default)
    fx, fy = (w * k / bw, h * k / bh) if fill and p.stretch else (f, f)
    ox, oy = (w * k - bw * fx) / 2 - bx * fx + at[0] * k, (h * k - bh * fy) / 2 - by * fy + at[1] * k
    size = (math.ceil(at[0] + w - 1e-9), math.ceil(at[1] + h - 1e-9))
    big = Image.new("L", (size[0] * k, size[1] * k), 0)
    d = ImageDraw.Draw(big)
    at = lambda x, y: (x * fx + ox, y * fy + oy)  # noqa: E731
    for i, (kind, nums, inside, width, caps, more) in enumerate(p.shapes):
        if which is not None and i not in which:
            continue
        sw = width * f
        if kind == "circle":
            (cx, cy), r = at(nums[0], nums[1]), nums[2] * f
            if inside:
                d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
            if sw and more and nums[2] > 0:  # dashes along it, from three o'clock (turned by its transform), clockwise
                dash, turn = more
                dash = dash if len(dash) % 2 == 0 else dash * 2
                around, gone, i = 2 * math.pi * nums[2], 0.0, 0
                while gone < around:
                    if i % 2 == 0 and dash[i % len(dash)] > 0:
                        a0 = turn + 360 * gone / around
                        a1 = turn + 360 * min(around, gone + dash[i % len(dash)]) / around
                        d.arc((cx - r - sw / 2, cy - r - sw / 2, cx + r + sw / 2, cy + r + sw / 2), a0, a1, fill=255, width=max(1, round(sw)))
                        if caps:
                            for a in (a0, a1):
                                ex, ey = cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))
                                d.ellipse((ex - sw / 2, ey - sw / 2, ex + sw / 2, ey + sw / 2), fill=255)
                    gone += dash[i % len(dash)]
                    i += 1
            elif sw:
                d.ellipse((cx - r - sw / 2, cy - r - sw / 2, cx + r + sw / 2, cy + r + sw / 2), outline=255, width=max(1, round(sw)))
            continue
        pts = [at(x, y) for x, y in nums]
        if inside and len(set(pts)) > 2:
            d.polygon(pts, fill=255)
        if sw:
            d.line(pts, fill=255, width=max(1, round(sw)), joint="curve")
            if caps:
                for x, y in (pts[0], pts[-1]):
                    d.ellipse((x - sw / 2, y - sw / 2, x + sw / 2, y + sw / 2), fill=255)
    return big.resize(size, Image.LANCZOS)


def _r(v: float) -> int:
    """To a whole pixel as a browser snaps it: halves go up."""
    return math.floor(v + 0.5)


@functools.lru_cache(maxsize=512)
def _rounded(w: int, h: int, r: float, corners=(True, True, True, True)) -> Image.Image:
    """A rounded rectangle as a mask with soft edges (drawn four times as large), as a browser paints one."""
    if w <= 0 or h <= 0:
        return Image.new("L", (max(1, w), max(1, h)), 0)
    if r <= 0:
        return Image.new("L", (w, h), 255)
    k = 4
    big = Image.new("L", (w * k, h * k), 0)
    ImageDraw.Draw(big).rounded_rectangle((0, 0, w * k - 1, h * k - 1), radius=min(r, w / 2, h / 2) * k, fill=255, corners=corners)
    return big.resize((w, h), Image.BOX)


def _inset(mask: Image.Image, w: int, h: int, by: int) -> Image.Image:
    out = Image.new("L", (w, h), 0)
    out.paste(mask, (by, by))
    return out


def _radius(n: Node, s: float) -> float:
    if "title_bar" in n.cls:
        return s * (10 if (n.parent is not None and "view--full" in n.parent.cls) or n.st.foot else 7)
    return n.st.radius


def _corners(n: Node):
    if "title_bar" in n.cls and not (n.parent is not None and "view--full" in n.parent.cls):
        return (False, False, True, True)  # in a mashup the bar closes the view's rounded foot
    return (True, True, True, True)


@functools.lru_cache(maxsize=16)
def _tile(tone: str, bits: int) -> Image.Image:
    """The framework's 16x16 dither tiles (its generated tokens: gray-75 for surfaces, gray-45 for gray ink), as
    measured from its CSS for 1-bit and 2-bit screens; plain grays from 4 bits up."""
    t = Image.new("L", (16, 16), 255)
    if bits >= 4:
        t.paste(0xDD if tone == "light" else 0x77, (0, 0, 16, 16))
        return t
    px = t.load()
    for y in range(16):
        for x in range(16):
            if bits == 1 and tone == "light":
                on = (y % 4 == 0 and x % 4 == 3) or (y % 4 == 2 and x % 4 == 1)
                px[x, y] = 0 if on else 255
            elif bits == 1:
                on = (y % 2 == 0 and x % 2 == 0) or (y % 4 == 1 and x % 2 == 1) or (y % 4 == 3 and x % 4 != 2)
                px[x, y] = 0 if on else 255
            elif tone == "light":
                on = (y % 2 == 0 and x % 2 == 1) or (y % 4 == 1 and x % 4 == 0) or (y % 4 == 3 and x % 4 == 2)
                px[x, y] = 0xAA if on else 255
            else:
                on = (y % 2 == 0 and x % 2 == 0) or (y % 4 == 1 and x % 4 != 0) or (y % 4 == 3 and x % 4 != 2)
                px[x, y] = 0x55 if on else 0xAA
    return t


def inked(img: Image.Image) -> Image.Image:
    """A picture drawn with inks (Drawer(inks=True)) as the panel prints it: a palette picture of PALETTE, each
    pixel black, white or its ink."""
    lut = [1 if v < 128 else 0 for v in range(256)]
    for tone, v in INK.items():
        lut[v] = 2 + INKS.index(tone)
    out = Image.frombytes("P", img.size, img.point(lut).tobytes())
    out.putpalette([c for rgb in PALETTE for c in rgb])
    return out


def to_inks(img: Image.Image) -> Image.Image:
    """Any picture (a browser's) as a panel of PALETTE prints it: each pixel to the nearest ink, as TRMNL's firmware
    does (no dithering)."""
    pal = Image.new("P", (1, 1))
    pal.putpalette([c for rgb in PALETTE for c in rgb] + [0, 0, 0] * (256 - len(PALETTE)))
    return img.convert("RGB").quantize(palette=pal, dither=Image.Dither.NONE)


def quantize(img: Image.Image, bits: int) -> Image.Image:
    """To the grays the screen has (2, 4, 16 or 256), each pixel to the nearest: no dithering, the patterns are the
    grays."""
    if bits >= 8:
        return img
    levels = (1 << bits) - 1
    return img.point([round(round(v * levels / 255) * 255 / levels) for v in range(256)])


def png(img: Image.Image, bits: int) -> bytes:
    """A grayscale PNG of exactly `bits` a pixel (1, 2, 4 or 8), which is what TRMNL's firmware decodes (Pillow
    writes 1 and 8 only). A picture in inks (inked) goes as a PNG of its palette, 4 bits a pixel, which the
    firmware of a Spectra 6 panel reads colour by colour."""
    if img.mode == "P":
        out = io.BytesIO()
        img.save(out, "PNG", bits=4, optimize=True)
        return out.getvalue()
    bits = 1 if bits < 2 else 2 if bits < 4 else 4 if bits < 8 else 8
    w, h = img.size
    data = img.convert("L").tobytes()
    if bits == 1:
        packed, stride = img.convert("L").point(lambda v: 255 if v >= 128 else 0).convert("1").tobytes(), (w + 7) // 8
        rows = b"".join(b"\x00" + packed[y * stride:(y + 1) * stride] for y in range(h))
    elif bits == 8:
        rows = b"".join(b"\x00" + data[y * w:(y + 1) * w] for y in range(h))
    else:
        shift, per = 8 - bits, 8 // bits
        rows = bytearray()
        for y in range(h):
            rows.append(0)
            row = data[y * w:(y + 1) * w]
            for i in range(0, w, per):
                v = 0
                for j in range(per):
                    v = (v << bits) | ((row[i + j] >> shift) if i + j < w else 0)
                rows.append(v)
        rows = bytes(rows)

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, bits, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def same(a: Image.Image, b: Image.Image) -> float:
    """How much of two pictures differs, 0 to 1 (the tests' measure against Chromium's render)."""
    diff = ImageChops.difference(a.convert("L"), b.convert("L")).point(lambda v: 255 if v > 64 else 0)
    return sum(diff.histogram()[255:]) / (a.size[0] * a.size[1])
