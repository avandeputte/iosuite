"""The TRMNL screens drawn without a browser (app/trmnldraw.py), held against what TRMNL's own framework draws.

tests/trmnl_ref has the suite's screens as Chromium rendered them with TRMNL's framework (its plugins.css and
plugins.js, github.com/usetrmnl/trmnl-framework) from data.json: every screen in every size on a black-and-white
TRMNL (800 x 480), the full screens in 4 grays, the quadrants in 16 grays, and a few on the TRMNL X (1872 x 1404,
where the framework sets everything in Inter). The pictures drawn here may differ from those in a few pixels in a
hundred: the edges of letters (a browser blurs a letter that falls between two pixels, this sets it on whole ones),
never where things are. No database is needed."""
import io
import json
import os

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


def drawn(screen: str, size: str, bits: int, scale: float = 1.0, dims=(None, None)) -> Image.Image:
    """The screen in this size, with the other screens around it where it shares the display (as the references)."""
    others = [o for o in trmnl.SCREENS if o != screen]
    views = [page(screen, size)] + [page(o, size) for o in others[:3]]
    return trmnldraw.Drawer(scale, bits).screen(views, MASHUP[size], *dims)


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


@pytest.mark.parametrize("screen,size,bits,most", [("today", "full", 4, 0.02), ("health", "full", 4, 0.02), ("calendar", "quadrant", 4, 0.02),
                                                   ("money", "half_vertical", 4, 0.02), ("tasks", "full", 1, 0.03)])
def test_the_larger_trmnl(screen, size, bits, most):
    img, ref = drawn(screen, size, bits, 1.8, (1872, 1404)), reference(f"{screen}-{size}-x{bits}")
    assert img.size == (1872, 1404)
    assert trmnldraw.same(img, ref) <= most
    assert apart(img, ref, 2) <= 0.005


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


def test_what_the_markup_uses_is_known():
    """Every class in the suite's markup is one the drawing knows (and was held against TRMNL's framework above): a
    new one has to be added to app/trmnldraw.py and to the references, or it is drawn as a plain box."""
    import re
    known = {"column", "columns", "content", "description", "fill", "flex", "flex--between", "flex--center", "flex--col", "flex--left", "flex--right", "flex--row",
             "gap", "gap--small", "gap--xsmall", "grid", "grid--cols-12", "group-header", "image", "instance", "item", "label", "label--gray", "label--inverted",
             "label--outline", "label--small", "label--underline", "layout", "layout--center", "layout--col", "layout--row", "layout--stretch-x", "layout--top",
             "meta", "progress-bar", "progress-bar--small", "progress-bar--xsmall", "title", "title--small", "title_bar", "track", "value", "value--large",
             "value--small", "value--tnums", "value--xlarge", "value--xxlarge", "w--full"}
    used = set()
    for screen in trmnl.SCREENS:
        m = trmnl.markup(screen)
        for part in m.values():
            for cls in re.findall(r'class="([^"]*)"', part):
                used |= {c for c in re.sub(r"\{[%{].*?[%}]\}", " ", cls).split() if not c.startswith("col--span-")}
    assert used <= known, sorted(used - known)
