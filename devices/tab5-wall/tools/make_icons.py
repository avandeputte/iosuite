#!/usr/bin/env python3
"""Draws the wall's weather icons (white on transparent, as LVGL A8 alpha masks the firmware tints) and writes them to
main/icons.c / main/icons.h. Run it again after a change here: python3 tools/make_icons.py (needs Pillow).

Each icon is drawn at four times its size and scaled down, so the edges come out smooth. Two sizes: BIG for the
current weather, SMALL for the hours and the days."""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent.parent / "main"
SIZES = {"big": 112, "small": 52}
SS = 4  # supersampling

KINDS = ["sun", "moon", "partly_day", "partly_night", "cloud", "rain", "thunder", "snow", "sleet", "fog", "wind"]


def sun(d, cx, cy, r, w):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    for i in range(8):
        a = i * math.pi / 4
        x1, y1 = cx + math.cos(a) * r * 1.45, cy + math.sin(a) * r * 1.45
        x2, y2 = cx + math.cos(a) * r * 1.9, cy + math.sin(a) * r * 1.9
        d.line((x1, y1, x2, y2), fill=255, width=w)


def moon(img, cx, cy, r):
    m = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(m)
    md.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    md.ellipse((cx - r * 0.35, cy - r * 1.15, cx + r * 1.45, cy + r * 0.65), fill=0)
    img.paste(255, (0, 0), m)


def cloud(img, x, y, s, cut=None):
    """A cloud whose box starts at (x, y), s wide; cut: a band around it cleared first, so it stands out from
    what is behind (the sun, the moon)."""
    m = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(m)
    h = s * 0.55
    parts = [(x + s * 0.08, y + h * 0.42, x + s * 0.50, y + h), (x + s * 0.25, y + h * 0.05, x + s * 0.70, y + h * 0.95),
             (x + s * 0.52, y + h * 0.30, x + s * 0.95, y + h)]
    for p in parts:
        md.ellipse(p, fill=255)
    md.rectangle((x + s * 0.29, y + h * 0.62, x + s * 0.74, y + h), fill=255)
    if cut:
        grown = m.filter(ImageFilter.MaxFilter(cut | 1))
        img.paste(0, (0, 0), grown)
    img.paste(255, (0, 0), m)


def drops(d, x, y, s, n=3, kind="rain"):
    for i in range(n):
        cx = x + s * (0.28 + i * 0.22)
        cy = y
        if kind == "rain":
            d.line((cx, cy, cx - s * 0.06, cy + s * 0.18), fill=255, width=max(2, int(s * 0.06)))
        elif kind == "snow":
            r = s * 0.06
            for k in range(3):
                a = k * math.pi / 3
                d.line((cx - math.cos(a) * r, cy + s * 0.08 - math.sin(a) * r, cx + math.cos(a) * r, cy + s * 0.08 + math.sin(a) * r),
                       fill=255, width=max(2, int(s * 0.035)))
        else:  # sleet: rain and snow by turns
            if i % 2:
                d.ellipse((cx - s * 0.04, cy + s * 0.05, cx + s * 0.04, cy + s * 0.13), fill=255)
            else:
                d.line((cx, cy, cx - s * 0.06, cy + s * 0.18), fill=255, width=max(2, int(s * 0.06)))


def draw(kind: str, size: int) -> Image.Image:
    S = size * SS
    img = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(img)
    w = max(2, int(S * 0.05))
    if kind == "sun":
        sun(d, S / 2, S / 2, S * 0.2, w)
    elif kind == "moon":
        moon(img, S / 2, S / 2, S * 0.32)
    elif kind in ("partly_day", "partly_night"):
        if kind == "partly_day":
            sun(d, S * 0.38, S * 0.36, S * 0.15, max(2, int(S * 0.04)))
        else:
            moon(img, S * 0.40, S * 0.36, S * 0.22)
        cloud(img, S * 0.18, S * 0.40, S * 0.78, cut=int(S * 0.06))
    elif kind == "cloud":
        cloud(img, S * 0.08, S * 0.24, S * 0.84)
    elif kind in ("rain", "snow", "sleet"):
        cloud(img, S * 0.08, S * 0.08, S * 0.84)
        drops(d, S * 0.08, S * 0.66, S * 0.84, 3, kind)
    elif kind == "thunder":
        cloud(img, S * 0.08, S * 0.06, S * 0.84)
        bolt = [(0.52, 0.52), (0.36, 0.76), (0.50, 0.76), (0.42, 0.96), (0.66, 0.68), (0.52, 0.68), (0.60, 0.52)]
        d.polygon([(x * S, y * S) for x, y in bolt], fill=255)
    elif kind == "fog":
        for i, (a, b) in enumerate([(0.18, 0.82), (0.10, 0.74), (0.24, 0.90), (0.14, 0.70)]):
            y = S * (0.30 + i * 0.13)
            d.line((S * a, y, S * b, y), fill=255, width=w)
    elif kind == "wind":
        for i, (l, r) in enumerate([(0.14, 0.70), (0.10, 0.82), (0.18, 0.60)]):
            y = S * (0.34 + i * 0.16)
            d.line((S * l, y, S * r, y), fill=255, width=w)
            d.arc((S * r - S * 0.08, y - S * 0.16, S * r + S * 0.08, y), 0, 270 if i != 1 else 90, fill=255, width=w)
    return img.resize((size, size), Image.LANCZOS)


def main():
    c = ['/* Made by tools/make_icons.py: do not edit; run it again instead. */', '#include "icons.h"', ""]
    h = ['/* Made by tools/make_icons.py: do not edit. */', "#pragma once", '#include "lvgl.h"', "",
         "typedef enum {" + ", ".join(f"ICON_{k.upper()}" for k in KINDS) + ", ICON_COUNT} icon_kind_t;", ""]
    for size_name, size in SIZES.items():
        for k in KINDS:
            img = draw(k, size)
            data = img.tobytes()
            name = f"icon_{k}_{size_name}"
            rows = [", ".join(f"0x{b:02x}" for b in data[i:i + 24]) for i in range(0, len(data), 24)]
            c.append(f"static const uint8_t {name}_map[] = {{\n    " + ",\n    ".join(rows) + "\n};")
            c.append(f"const lv_image_dsc_t {name} = {{\n    .header = {{.magic = LV_IMAGE_HEADER_MAGIC, .cf = LV_COLOR_FORMAT_A8, "
                     f".w = {size}, .h = {size}, .stride = {size}}},\n    .data_size = sizeof({name}_map),\n    .data = {name}_map,\n}};\n")
            h.append(f"extern const lv_image_dsc_t {name};")
        c.append(f"const lv_image_dsc_t *const icons_{size_name}[ICON_COUNT] = {{" + ", ".join(f"&icon_{k}_{size_name}" for k in KINDS) + "};\n")
        h.append(f"extern const lv_image_dsc_t *const icons_{size_name}[ICON_COUNT];")
    h += ["", "/** The icon for an AccuWeather icon number (1-44); day says which of sun/moon when the number does not. */",
          "icon_kind_t icon_for_accuweather(int n, bool day);", ""]
    c.append('''icon_kind_t icon_for_accuweather(int n, bool day)
{
    switch (n) {
    case 1: case 2: case 30: return ICON_SUN;
    case 3: case 4: case 5: case 6: return ICON_PARTLY_DAY;
    case 7: case 8: return ICON_CLOUD;
    case 11: return ICON_FOG;
    case 12: case 13: case 14: case 18: case 39: case 40: return ICON_RAIN;
    case 15: case 16: case 17: case 41: case 42: return ICON_THUNDER;
    case 19: case 20: case 21: case 22: case 23: case 31: case 43: case 44: return ICON_SNOW;
    case 24: case 25: case 26: case 29: return ICON_SLEET;
    case 32: return ICON_WIND;
    case 33: case 34: return ICON_MOON;
    case 35: case 36: case 37: case 38: return ICON_PARTLY_NIGHT;
    default: return day ? ICON_SUN : ICON_MOON;
    }
}
''')
    (HERE / "icons.c").write_text("\n".join(c))
    (HERE / "icons.h").write_text("\n".join(h) + "\n")
    sheet = Image.new("L", (len(KINDS) * SIZES["big"], SIZES["big"] + SIZES["small"]), 40)
    for i, k in enumerate(KINDS):
        sheet.paste(draw(k, SIZES["big"]), (i * SIZES["big"], 0))
        sheet.paste(draw(k, SIZES["small"]), (i * SIZES["big"], SIZES["big"]))
    return sheet


if __name__ == "__main__":
    import sys
    s = main()
    if len(sys.argv) > 1:
        s.save(sys.argv[1])
