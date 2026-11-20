"""The TRMNL screens drawn without a browser (app/trmnldraw.py), held against what TRMNL's own framework draws.

tests/trmnl_ref has the suite's screens as Chromium rendered them with TRMNL's framework (its plugins.css and
plugins.js, github.com/usetrmnl/trmnl-framework) from data.json: every screen in every size on a black-and-white
TRMNL (800 x 480), the full screens in 4 grays, the quadrants in 16 grays, and on the TRMNL X (1872 x 1404, where
the framework sets everything in Inter and the markup's lg: classes count) every full screen and a few of the other
sizes. The pictures drawn here may differ from those in a few pixels in a hundred: the edges of letters (a browser
blurs a letter that falls between two pixels, this sets it on whole ones), never where things are. No database is
needed.

To render the references again: each page with the framework's plugins.css and plugins.js in Chromium, the screen's
class screen--<bits>bit; for the TRMNL X also screen--v2 screen--lg screen--density-2x, in a window of 1872 x 1404
at a device scale of 1 (the framework magnifies the screen itself)."""
import io
import json
import os
import re

import pytest
from PIL import Image, ImageChops, ImageFilter

liquid = pytest.importorskip("liquid")

from app import trmnl, trmnldraw  # noqa: E402

REF = os.path.join(os.path.dirname(__file__), "trmnl_ref")
DATA = json.load(open(os.path.join(REF, "data.json"), encoding="utf-8"))
MASHUP = {"full": "full", "half_horizontal": "1Tx1B", "half_vertical": "1Lx1R", "quadrant": "2x2"}
ENV = liquid.Environment()


def page(screen: str, size: str) -> str:
    m = trmnl.markup(screen)
    return ENV.parse(m["shared"] + "\n" + m[size]).render(DATA[screen])


def drawn(screen: str, size: str, bits: int, scale: float = 1.0, dims=(None, None), inks: bool = False) -> Image.Image:
    """The screen in this size, with the other screens around it where it shares the display (as the references)."""
    others = [o for o in trmnl.SCREENS if o != screen]
    views = [page(screen, size)] + [page(o, size) for o in others[:3]]
    return trmnldraw.Drawer(scale, bits, inks=inks).screen(views, MASHUP[size], *dims)


def reference(name: str) -> Image.Image:
    return Image.open(os.path.join(REF, name + ".png")).convert("L")


def apart(a: Image.Image, b: Image.Image, reach: int = 1) -> float:
    """How much of the ink of two pictures is not within `reach` pixels of ink in the other, 0 to 1: what is in
    another place, not how a letter's edge fell."""
    ia, ib = (x.convert("L").point(lambda v: 255 if v < 160 else 0) for x in (a, b))
    k = 2 * reach + 1
    lost = ImageChops.subtract(ia, ib.filter(ImageFilter.MaxFilter(k))).histogram()[255] + ImageChops.subtract(ib, ia.filter(ImageFilter.MaxFilter(k))).histogram()[255]
    return lost / max(1, ia.histogram()[255] + ib.histogram()[255])


# (screen, size, bits, pixels that may differ, ink that may be elsewhere)
CASES = ([(s, z, 1, 0.02, 0.015) for s in trmnl.SCREENS for z in trmnl.SIZES]
         + [(s, "full", 2, 0.03, 0.015) for s in trmnl.SCREENS] + [(s, "quadrant", 4, 0.01, 0.005) for s in trmnl.SCREENS])
# the one place this differs from the framework on purpose: where a list goes on past the display, the framework
# leaves the next group's header standing alone above "and 3 more"; here the header goes with its group
ORPHAN = {("calendar", "half_vertical", 1), ("today", "half_vertical", 1)}


@pytest.mark.parametrize("screen,size,bits,most,elsewhere", CASES)
def test_as_trmnl_draws_it(screen, size, bits, most, elsewhere):
    img, ref = drawn(screen, size, bits), reference(f"{screen}-{size}-{bits}")
    assert img.size == (800, 480)
    assert trmnldraw.same(img, ref) <= most
    assert apart(img, ref) <= (0.04 if (screen, size, bits) in ORPHAN else elsewhere)


# on the TRMNL X: every full screen, health (the rings) and today (its list) in every size, and one of each other size
LARGER = ([(s, "full", 4, 0.02) for s in trmnl.SCREENS] + [("health", z, 4, 0.02) for z in trmnl.SIZES if z != "full"]
          + [("today", z, 4, 0.02) for z in trmnl.SIZES if z != "full"] + [("money", "half_vertical", 4, 0.02), ("weather", "half_vertical", 4, 0.02), ("calendar", "quadrant", 4, 0.02),
             ("tasks", "full", 1, 0.03)])


@pytest.mark.parametrize("screen,size,bits,most", LARGER)
def test_the_larger_trmnl(screen, size, bits, most):
    img, ref = drawn(screen, size, bits, 1.8, (1872, 1404)), reference(f"{screen}-{size}-x{bits}")
    assert img.size == (1872, 1404)
    assert trmnldraw.same(img, ref) <= most
    # among the quadrants is the calendar's and among the halves standing side by side today's, where a header is
    # left alone (ORPHAN) on this screen
    assert apart(img, ref, 2) <= (0.05 if size in ("quadrant", "half_vertical") else 0.005)


# the reTerminal E1004 in its colours (a Spectra 6 panel of 1600 x 1200; the framework's screen--seeed_e1004 with
# screen--color-6a, Chromium's picture taken to the nearest ink): every full screen, health (the rings) and today (its
# list) in every size, and one of each other size
E1004 = ([(s, "full") for s in trmnl.SCREENS] + [(s, z) for s in ("health", "today") for z in trmnl.SIZES if z != "full"]
         + [("weather", "half_vertical"), ("money", "half_vertical"), ("calendar", "quadrant")])


def in_ink(img: Image.Image, rgb) -> Image.Image:
    """Where a picture has this ink (white there, black elsewhere)."""
    return ImageChops.difference(img.convert("RGB"), Image.new("RGB", img.size, rgb)).convert("L").point(lambda v: 255 if v == 0 else 0)


@pytest.mark.parametrize("screen,size", E1004)
def test_the_reterminal_e1004_in_color(screen, size):
    img, ref = drawn(screen, size, 1, 1.5385, (1600, 1200), inks=True), Image.open(os.path.join(REF, f"{screen}-{size}-e1004.png"))
    assert img.size == (1600, 1200) and img.mode == "P"
    full = size == "full"
    assert trmnldraw.same(img, ref) <= (0.025 if full else 0.035)  # the halves' title bars: the framework's pattern drifts at this scale
    assert apart(img, ref, 2) <= (0.005 if full else 0.02)  # (ORPHAN)
    for rgb in trmnldraw.PALETTE[2:]:  # each ink where the framework has it, to the pixel or two
        a, b = in_ink(img, rgb), in_ink(ref, rgb)
        na, nb = a.histogram()[255], b.histogram()[255]
        assert abs(na - nb) <= 0.08 * max(nb, 100), (rgb, na, nb)  # a bar of colour may be a pixel longer
        lost = ImageChops.subtract(a, b.filter(ImageFilter.MaxFilter(5))).histogram()[255] + ImageChops.subtract(b, a.filter(ImageFilter.MaxFilter(5))).histogram()[255]
        assert lost <= 0.01 * max(na + nb, 100), (rgb, lost)


def test_colors_stay_on_a_screen_of_inks():
    """A screen of grays keeps its look (the 1bit: 2bit: 4bit: classes give it back); a screen of inks has the colours,
    in a PNG of its palette that the firmware of a Spectra 6 panel reads pixel by pixel."""
    cls = {"label", "label--error", "1bit:label--inverted", "2bit:label--inverted", "hidden", "1bit:inline"}
    assert trmnldraw.classes(cls, True, 1) == {"label", "label--error", "label--inverted"}  # 1bit:inline shows what hidden hides
    assert trmnldraw.classes(cls, True, 4) == {"label", "label--error", "hidden"}
    assert trmnldraw.classes(cls, True, 1, inks=True) == {"label", "label--error", "hidden"}
    img = drawn("health", "full", 1, 1.5385, (1600, 1200), inks=True)
    assert {rgb for _, rgb in img.convert("RGB").getcolors(16)} == set(trmnldraw.PALETTE) - {(255, 255, 0)}  # the rings: red, green, blue
    back = Image.open(io.BytesIO(trmnldraw.png(img, 1)))
    assert back.mode == "P" and back.info.get("bits", 4) <= 4 and back.size == (1600, 1200)
    assert ImageChops.difference(back.convert("RGB"), img.convert("RGB")).getbbox() is None
    for screen in ("health", "today", "weather"):  # in black and white as before: no ink
        assert {rgb for _, rgb in drawn(screen, "full", 1, 1.5385, (1600, 1200)).convert("RGB").getcolors(16)} <= {(0, 0, 0), (255, 255, 255)}


def test_classes_for_the_large_screen():
    """lg:x counts on the TRMNL X alone, where it takes the place of the plain class of its group; lg:flex and
    lg:block show there what `hidden` hides elsewhere."""
    cls = {"title", "title--small", "lg:title--large", "lg:text--bold", "gap--small", "lg:gap--xlarge", "w--16", "lg:w--20", "h--8", "flex", "hidden", "lg:flex"}
    assert trmnldraw.classes(cls, False) == {"title", "title--small", "gap--small", "w--16", "h--8", "flex", "hidden"}
    assert trmnldraw.classes(cls, True) == {"title", "title--large", "text--bold", "gap--xlarge", "w--20", "h--8", "flex"}
    row = '<div class="layout layout--col layout--top"><span class="label">one</span><span class="label hidden lg:block">two</span></div>'
    ink = lambda img: sum(img.point(lambda v: 255 if v < 128 else 0).histogram()[255:])  # noqa: E731
    one = '<div class="layout layout--col layout--top"><span class="label">one</span></div>'
    small, large = (lambda m: trmnldraw.Drawer(1.0, 1).screen([m], "full")), (lambda m: trmnldraw.Drawer(1.8, 4).screen([m], "full", 1872, 1404))
    assert ink(small(row)) == ink(small(one)) and ink(large(row)) > ink(large(one)) * 1.5


def test_text_on_whole_pixels():
    """data-pixel-perfect: on a screen without grays a text set in the middle of its place is made as wide as that
    is even or odd, so its letters start on a whole pixel as the framework has them."""
    for text in ("Fri", "Sat", "12,880", "I"):
        d = trmnldraw.Drawer(1.0, 1)
        span = trmnldraw.Node("span", {"class": "label", "data-pixel-perfect": "true"})
        span.text = text
        span.st = trmnldraw._style(span, 1.0, 1, False)
        w = d.size(span, 64)[0]
        assert w == int(w) and w % 2 == 0, text
        assert d.size(span, 63)[0] % 2 == 1, text
        for other in (trmnldraw.Drawer(1.0, 4), trmnldraw.Drawer(1.8, 1)):  # with grays, or magnified: the text keeps its width
            span.st = trmnldraw._style(span, other.s, other.bits, other.dense)
            assert other.size(span, 63 * other.s)[0] == other.size(span, 64 * other.s)[0]


def test_progress_bar():
    """The framework's progress bar (no screen has one at the moment; the health screen had, before its rings)."""
    bar = lambda pct: (f'<div class="layout layout--col layout--top layout--stretch-x"><div class="progress-bar progress-bar--small"><div class="content">'  # noqa: E731
                       f'<span class="label label--small">Move</span><span class="label label--small">{pct}%</span></div><div class="track"><div class="fill" style="width: {pct}%"></div></div></div></div>')
    ink = lambda img: sum(img.point(lambda v: 255 if v < 128 else 0).histogram()[255:])  # noqa: E731
    low, high = (trmnldraw.Drawer(1.0, 1).screen([bar(p)], "full") for p in (20, 80))
    assert low.size == (800, 480) and ink(high) > ink(low) > 0


def test_every_layout_takes_its_screens():
    for layout, cells in trmnldraw.LAYOUTS.items():
        sizes = trmnldraw.sizes(layout)
        assert len(sizes) == len(cells) and set(sizes) <= set(trmnl.SIZES)
        views = [page(s, z) for s, z in zip(trmnl.SCREENS, sizes)]
        img = trmnldraw.Drawer(1.0, 1).screen(views, layout)
        assert img.size == (800, 480) and len(img.getcolors()) == 2


def test_grays():
    for bits, most in ((1, 2), (2, 4), (4, 16)):
        img = drawn("health", "full", bits)
        tones = sorted(v for _, v in img.getcolors())
        assert 2 <= len(tones) <= most and tones[0] == 0 and tones[-1] == 255
        step = 255 // (2 ** bits - 1)
        assert all(v % step == 0 for v in tones)  # only the grays a screen of this depth has


def test_png():
    for bits in (1, 2, 4):
        img = drawn("today", "full", bits)
        body = trmnldraw.png(img, bits)
        back = Image.open(io.BytesIO(body))
        assert back.size == img.size and trmnldraw.same(back, img) == 0
        assert body[24] == bits and body[25] == 0  # the depth a TRMNL's firmware reads, gray
    assert len(trmnldraw.png(drawn("today", "full", 1), 1)) < 20_000  # small enough for a device on a battery


def test_text_that_does_not_fit():
    long = "A very long title that cannot possibly fit on one line of a quadrant of the display"
    view = f'<div class="layout layout--col"><span class="title title--small" data-clamp="1">{long}</span></div><div class="title_bar"><img class="image" src=""><span class="title">{long}</span><span class="instance">{long}</span></div>'
    d = trmnldraw.Drawer(1.0, 1)
    img = d.screen([view] * 4, "2x2")
    assert img.size == (800, 480)
    one = trmnldraw.parse(view)
    assert one[0].kids[0].text == long  # the markup is read as written; what is cut is cut when drawn


def test_glyphs():
    """An img whose src is an SVG in a data: address (the weather's glyphs) is drawn from the SVG itself: the part of
    SVG they are written in, and nothing when it is something else."""
    import base64
    svg = lambda body: "data:image/svg+xml;base64," + base64.b64encode(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>'.encode()).decode()  # noqa: E731
    ink = lambda m: sum(m.point(lambda v: 255 if v >= 128 else 0).histogram()[255:])  # noqa: E731
    disc = trmnldraw.glyph(svg('<circle cx="12" cy="12" r="6"/>'), 48, 48)
    assert disc.size == (48, 48) and abs(ink(disc) - 3.14159 * 12 * 12) < 12 and disc.getpixel((24, 24)) == 255 and disc.getpixel((2, 2)) < 10
    # an arc drawn as a path covers what the circle covers; relative and absolute commands meet
    arcs = trmnldraw.glyph(svg('<path d="M6 12a6 6 0 1 0 12 0A6 6 0 1 0 6 12z"/>'), 48, 48)
    assert trmnldraw.same(arcs, disc) < 0.01
    square = trmnldraw.glyph(svg('<path d="M4 4h16v16H4z"/>'), 24, 24)
    assert abs(ink(square) - 256) <= 2
    # a stroke has its width and round ends; fill="none" leaves the inside open
    line = trmnldraw.glyph(svg('<g fill="none" stroke="#000" stroke-width="2" stroke-linecap="round"><path d="M4 12h16"/></g>'), 24, 24)
    assert line.getpixel((12, 12)) == 255 and line.getpixel((12, 8)) < 10 and line.getpixel((3, 12)) > 100 and abs(ink(line) - (32 + 3.14159)) < 6
    ring = trmnldraw.glyph(svg('<g fill="none" stroke="#000" stroke-width="2"><path d="M4 4h16v16H4z"/></g>'), 24, 24)
    assert ring.getpixel((12, 12)) < 10 and ring.getpixel((12, 4)) == 255
    assert trmnldraw.glyph("https://example.com/x.png", 24, 24) is None and trmnldraw.glyph("", 24, 24) is None
    # what the graphs are written in: bars (rect), a band (polygon), and a ring's arc (a circle's stroke in one dash
    # from the top, turned there by rotate)
    bars = trmnldraw.glyph(svg('<rect x="0" y="12" width="12" height="12"/><polygon points="12,0 24,0 24,24 12,24"/>'), 24, 24)
    assert abs(ink(bars) - (144 + 288)) <= 4 and bars.getpixel((6, 6)) < 10 and bars.getpixel((6, 18)) == 255 and bars.getpixel((18, 6)) == 255
    arc = lambda dash: trmnldraw.glyph(svg(f'<g fill="none" stroke="#000"><circle cx="12" cy="12" r="8" stroke-width="4" stroke-dasharray="{dash} 400" transform="rotate(-90 12 12)"/></g>'), 96, 96)  # noqa: E731
    quarter, half = arc(12.566), arc(25.133)
    assert abs(ink(half) / ink(quarter) - 2) < 0.1
    assert quarter.getpixel((48 + 23, 48 - 23)) == 255 and quarter.getpixel((48 - 23, 48 - 23)) < 10 and quarter.getpixel((48 + 23, 48 + 23)) < 10  # from twelve o'clock to three
    assert half.getpixel((48 + 23, 48 + 23)) == 255 and half.getpixel((48 - 23, 48 + 23)) < 10
    # a graph gives its proportions up and is stretched over an img that fills its place; elsewhere it keeps them
    wide = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10" preserveAspectRatio="none"><rect x="0" y="0" width="10" height="10"/></svg>'
    wide = "data:image/svg+xml;base64," + base64.b64encode(wide.encode()).decode()
    assert ink(trmnldraw.glyph(wide, 80, 20, True)) == 1600 and abs(ink(trmnldraw.glyph(wide, 80, 20)) - 400) <= 4
    # a picture that starts between two pixels (a dense screen): a pixel more, the ink shared between the two at its edges
    off = trmnldraw.glyph(wide, 20, 20, True, (0.5, 0.0))
    assert off.size == (21, 20) and 90 < off.getpixel((0, 10)) < 190 and off.getpixel((10, 10)) == 255 and 90 < off.getpixel((20, 10)) < 190
    # every glyph of the weather is drawn, each its own, and they are the start page's (static/app.js)
    m = trmnl.markup("weather")["shared"]
    parts = re.search(r"\{%- capture wx_all -%\}(.*?)\{%- endcapture -%\}", m, re.S).group(1).split("|")
    assert len(parts) == len(trmnl.WX)
    js = open(os.path.join(os.path.dirname(__file__), "..", "static", "app.js"), encoding="utf-8").read()
    for name, body in zip(trmnl.WX, parts):
        assert f"  {name}: '{body.replace('#000', 'currentColor')}'," in js, name
    drawn = [trmnldraw.glyph(svg(b), 64, 64) for b in parts]
    assert all(ink(g) > 300 for g in drawn)
    assert all(trmnldraw.same(a, b) > 0.02 for i, a in enumerate(drawn) for b in drawn[i + 1:])
    assert {int(k) for k in re.findall(r"(\d+): '\w+'", js[js.index("const WX_MAP"):js.index("const wxIcon")])} == set(trmnl.WX_MAP)


def test_what_the_markup_uses_is_known():
    """Every class in the suite's markup is one the drawing knows (and was held against TRMNL's framework above): a
    new one has to be added to app/trmnldraw.py and to the references, or it is drawn as a plain box."""
    known = {"block", "column", "columns", "content", "description", "description--xlarge", "description--xxlarge", "flex", "flex--between", "flex--center",
             "flex--col", "flex--left", "flex--right", "flex--row", "flex--top", "gap", "gap--base", "gap--large", "gap--medium", "gap--none", "gap--small",
             "gap--xlarge", "gap--xsmall", "grid", "grid--cols-12", "group-header", "hidden", "image", "image--fill", "instance", "item", "label", "label--base",
             "label--gray", "label--inverted", "label--large", "label--outline", "label--small", "label--underline", "label--xlarge", "layout", "layout--center",
             "layout--col", "layout--row", "layout--stretch-x", "layout--top", "meta", "text--bold", "text--xlarge", "text--xxlarge", "title", "title--base",
             "title--large", "title--small", "title--xlarge", "title_bar", "value", "value--base", "value--large", "value--small", "value--tnums", "value--xlarge",
             "value--xxlarge", "value--xxxlarge", "w--full"}
    known |= {"h--full", "inline", "label--error", "label--primary"} | {f"bg--{t}" for t in trmnldraw.INKS}  # the colours of a screen of inks
    large = {"block", "flex"}  # what may follow lg: (the classes for the TRMNL X): these two, a size of text, a gap, a width, a height
    grays = {"hidden", "inline", "label--inverted"}  # what may follow 1bit: 2bit: 4bit: (a screen of grays given back its look)
    used = set()
    for screen in trmnl.SCREENS:
        m = trmnl.markup(screen)
        said = dict(re.findall(r'\{%-? assign (\w+) = "([^"{}]*)" -?%\}', "".join(m.values())))  # classes kept in a name (on_grays)
        for part in m.values():
            for cls in re.findall(r'class="([^"]*)"', part):
                cls = re.sub(r"\{\{ (\w+) \}\}", lambda k: said.get(k.group(1), k.group(0)), cls)
                cls = re.sub(r"bg--\{\{ \w+\.ink \}\}", " ".join(f"bg--{t}" for t in trmnldraw.INKS), cls)  # app/trmnl.py's ink()
                used |= {c for c in re.sub(r"\{[%{].*?[%}]\}", " ", cls).split() if not c.startswith("col--span-") and not re.fullmatch(r"(lg:)?[wh]--\d+|gap--\[\d+px\]", c)}
    plain = {c for c in used if ":" not in c}
    sized = {c[3:] for c in used if c.startswith("lg:")}
    bits = {c[5:] for c in used if re.match(r"[124]bit:", c)}
    assert all(c.startswith(("lg:", "1bit:", "2bit:", "4bit:")) for c in used - plain), sorted(used - plain)  # no sm: or md:, which the drawing does not read
    assert plain | sized | bits <= known, sorted((plain | sized | bits) - known)
    assert bits <= grays, sorted(bits - grays)
    assert {f"{b}bit:{c}" for b in (1, 2, 4) for c in bits} <= used  # a screen of grays of each depth is given its look back
    assert all(c in large or trmnldraw._family(c) or c == "text--bold" for c in sized), sorted(sized)
