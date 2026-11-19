"""TRMNL screens as pictures: the image a TRMNL device shows, drawn here from the same markup TRMNL's cloud renders
(app/trmnl_markup, TRMNL's design framework), without a browser. For the TRMNL server inside the start page
(app/trmnlserver.py): a device asks for a picture, not a page.

What TRMNL's framework does with CSS and its plugins.js, this does for the part of the framework the suite's screens
use, to the pixel where it could be measured against Chromium (tests/test_trmnl_draw.py lists what is covered):

    view, layout (row/col, top, center, stretch-x), grid + col--span-N, flex (row/col, left/center/right/between),
    gap, w--full, item/meta/content, columns with data-overflow (columns filled in turn, a group's header repeated
    in gray where the group goes on, "and N more"), progress-bar, title_bar, value/title/label/description in the
    sizes used, label--gray/--inverted/--outline/--underline, data-clamp, data-fit-value, and the mashup layouts.

The fonts are the framework's own (app/trmnl_fonts: TRMNL12/16/21 and Inter, SIL Open Font License), the grays are
its dither patterns for 1-bit and 2-bit screens and plain grays from 4 bits up. A denser screen (the TRMNL X: 1.8 of
its pixels to one of the framework's) is laid out at the framework's size and drawn larger, in Inter throughout, as
the framework does there. A class this does not know is laid out as a plain box, so markup using more of the
framework needs it added here (the test compares every screen).
"""
import functools
import html.parser
import math
import os
import struct
import zlib

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, features

RAQM = features.check("raqm")  # for tabular figures (value--tnums); without it the figures keep their own widths
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
        n.text = " ".join(n.text.split())
    return p.root.kids


def _walk(n):
    yield n
    for k in n.kids:
        yield from _walk(k)


# ---- fonts and text ----------------------------------------------------------------------------------------------

@functools.lru_cache(maxsize=256)
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
    **TEXT, "value--small": ("Inter", 26, 29, 475),
    "title": ("Inter", 21, 25.2, 400), "title--small": ("Inter", 16, 19.2, 700),
    "label": ("Inter", 16, 20, 500), "label--small": ("Inter", 13, 13, 500), "label--small-bold": ("Inter", 13, 13, 500),
    "description": ("Inter", 13, 15.6, 400), "bar": ("Inter", 16, 22, 700),
}


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
        self.color = "black"    # black | white | gray
        self.bg = None          # light | dark | black | white
        self.radius = 0.0
        self.border = 0
        self.underline = False
        self.clamp = 0
        self.fit = False
        self.align = "left"
        self.halo = False
        self.hidden = False
        self.line = 0           # the border's gray
        self.foot = False       # a title bar with the rounder foot it has where there are grays
        self.feat = None        # font features (tabular figures)
        self.kind = "box"       # box | text | icon | columns | grid | track | fill


def _style(n: Node, s: float, bits: int = 1, dense: bool = False) -> Style:
    st = Style()
    c, p = n.cls, n.parent
    px = lambda v: v * s  # noqa: E731
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
                    sized = [k for k in TEXT if k.startswith(base + "--") and k in c]
                    st.text = sized[0] if sized else base
                    break
            else:
                st.text = "label"
        in_item = n.up("item") is not None
        if st.text in ("label--small", "label--small-bold"):
            st.pt, st.pb = (px(2), px(1)) if in_item else (px(1), px(1))
        if st.text == "description":
            st.pt = px(1)
        if st.text == "label--small" and bits >= 2 and p is not None and "content" in p.cls and p.parent is not None and "progress-bar" in p.parent.cls:
            st.text = "label--small-bold"
        if "label--gray" in c:
            st.color = "gray"
        if "label" in c and in_item and bits >= 2:  # where there are grays, what stands under an item's title is dark gray
            st.color = "dim"
        if "label--inverted" in c:
            st.color, st.bg, st.radius, st.pl, st.pr = "white", "black", px(4), px(5), px(5)
        if "label--outline" in c:
            st.border, st.radius, st.pl, st.pr, st.pt = 1, px(4), px(2), px(2), 0
        if "label--underline" in c:
            st.underline = True
        if "group-header" in c:
            st.full = True
        try:
            st.clamp = max(0, int(n.attrs.get("data-clamp") or 0))
        except ValueError:
            st.clamp = 0
        st.fit = n.attrs.get("data-fit-value") == "true"
        if "value--tnums" in c and RAQM:
            st.feat = ["tnum"]
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
    for g, v in (("gap--xsmall", 5), ("gap--small", 7), ("gap--medium", 16), ("gap--large", 20), ("gap--none", 0)):
        if g in c and st.kind in ("box", "grid", "columns"):
            st.gap = px(v)
    if "w--full" in c:
        st.full = True
    return st


class Drawer:
    def __init__(self, scale: float = 1.0, bits: int = 1, dense: bool = None):
        self.s = scale
        self.bits = bits
        self.dense = scale >= 1.5 if dense is None else dense  # the framework's own rule: from 1.5 device pixels to one of its own
        self.T = TEXT_DENSE if self.dense else TEXT

    # -- text ----
    def font(self, n: Node, shrink: int = 0):
        name, size, lh, weight = self.T[n.st.text]
        size, lh = size - shrink, lh - shrink
        # where the baseline is in a line, worked out at the framework's own size as a browser does (whole pixels
        # there), then scaled: on a denser screen the page is laid out first and magnified after
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
            while width(text) > aw and self.T[st.text][1] - shrink > 8:
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
        elif st.kind == "icon":
            return st.w, st.h
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
            cw = max([w for w, _ in sz], default=0)
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
        colw = round((inner - n.st.gap * (cols - 1)) / cols)  # whole pixels a column, the gap takes the rest
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
        try:
            most = max(1, int(n.attrs.get("data-overflow-max-cols") or 1))
        except ValueError:
            most = 1
        if n.attrs.get("data-overflow") != "true":
            most, budget = max(1, len([c for c in n.kids if "column" in c.cls])), INF
        gap = self.s * GAP
        head = lambda k: "group-header" in k.cls  # noqa: E731
        best = None
        for count in range(1, most + 1):
            colw = round((inner - gap * (count - 1)) / count)
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
            n.budget = ih
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
                if st.ai == "stretch" and k.st.h is None:
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

    def fill(self, img: Image.Image, mask: Image.Image, at, tone: str, origin: int = 0):
        """Paints `tone` (black, white, light, dark) through a mask placed at `at`; the grays are the framework's
        dither patterns, starting at the element's own corner (inside its border: origin) as a CSS background does."""
        if tone in ("black", "white"):
            img.paste(0 if tone == "black" else 255, at, mask)
            return
        t = self.tile(tone)
        pat = Image.new("L", mask.size)
        for ty in range(origin % 16 - 16 if origin % 16 else 0, mask.size[1], 16):
            for tx in range(origin % 16 - 16 if origin % 16 else 0, mask.size[0], 16):
                pat.paste(t, (tx, ty))
        img.paste(pat, at, mask)

    def paint(self, img: Image.Image, n: Node):
        st = n.st
        if st.hidden or n.box is None:
            return
        x, y, w, h = n.box
        X, Y = _r(x), _r(y)
        Wd, Ht = max(0, _r(x + w) - X), max(0, _r(y + h) - Y)
        if st.bg and Wd and Ht and st.kind != "fill":
            self.fill(img, _rounded(Wd, Ht, _radius(n, self.s), _corners(n)), (X, Y), st.bg, st.border)
        if st.border and Wd and Ht:
            ring = ImageChops.subtract(_rounded(Wd, Ht, st.radius), _inset(_rounded(Wd - 2 * st.border, Ht - 2 * st.border, max(0, st.radius - st.border)), Wd, Ht, st.border))
            img.paste(st.line, (X, Y), ring)
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
            if st.color == "gray" and self.bits < 4:
                mask = Image.new("L", (Wd, Ht), 0)
                ImageDraw.Draw(mask).text((pos[0] - X, pos[1] - Y), line, font=font, fill=255, anchor="ls", features=st.feat)
                self.fill(img, mask, (X, Y), "dark")
                continue
            d = ImageDraw.Draw(img)
            if st.halo:  # white around the letters, so they stand out from the bar's pattern
                d.text(pos, line, font=font, fill=255, anchor="ls", stroke_width=max(1, round((1 if self.dense else 2) * self.s)), stroke_fill=255, features=st.feat)
            d.text(pos, line, font=font, fill={"black": 0, "white": 255, "gray": 0x77, "dim": 0x55}[st.color], anchor="ls", features=st.feat)

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
            img.paste(255, (X - r, Y - r), wide.filter(ImageFilter.MaxFilter(2 * r + 1)))
        img.paste(0, (X, Y), mask)

    # -- a whole screen ----
    def view(self, markup: str, size: str, w: float, h: float) -> Image.Image:
        """One view (the markup of one screen in one size), w x h of the framework's pixels, as its own picture."""
        s = self.s
        root = Node("div", {"class": "view view--" + size})
        root.kids = parse(markup)
        for k in root.kids:
            k.parent = root
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
            img.paste(pic, (X, Y), _rounded(Wd, Ht, r))
            self._frame(img, X, Y, Wd, Ht, r)
        return quantize(img, self.bits)

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


def quantize(img: Image.Image, bits: int) -> Image.Image:
    """To the grays the screen has (2, 4, 16 or 256), each pixel to the nearest: no dithering, the patterns are the
    grays."""
    if bits >= 8:
        return img
    levels = (1 << bits) - 1
    return img.point([round(round(v * levels / 255) * 255 / levels) for v in range(256)])


def png(img: Image.Image, bits: int) -> bytes:
    """A grayscale PNG of exactly `bits` a pixel (1, 2, 4 or 8), which is what TRMNL's firmware decodes (Pillow
    writes 1 and 8 only)."""
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
