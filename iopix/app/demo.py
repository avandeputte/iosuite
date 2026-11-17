"""Demo data (iosuite_shared.demo): the Calloways' photos. Drawn pictures (a gradient, a few shapes and cartoon faces:
no photo of anyone real) in folders of days out (the coast, a hike, a birthday, Christmas, a summer at Grandma's, the
science fair), each a JPEG with its date, camera and place in Exif and a sidecar with the people's faces, keywords,
a caption and a rating, as digiKam writes them. The file scanner then adds them to the library like any photo put in
the folder, and each account is linked to its person (the family's faces in every app).

Only when ioPix keeps its own library (no digiKam database, as in a Docker stack): a real digiKam library is never
added to. The photos go in "Calloway family (demo)" in the photos folder; delete that folder to remove them."""
import datetime as dt
import logging
import os
import random
from pathlib import Path

from iosuite_shared import demo

from app import config

log = logging.getLogger("app.demo")
FOLDER = "Calloway family (demo)"
FAMILY = ["Morgan Calloway", "Riley Calloway", "Ava Calloway", "Theo Calloway"]
SKIN = [(236, 200, 170), (198, 150, 112), (241, 214, 190), (172, 120, 90)]
CAMERAS = [("Apple", "iPhone 15", "iPhone 15 back camera 6.1mm f/1.6"), ("FUJIFILM", "X-T5", "XF23mmF2 R WR")]


def _events() -> list:
    """(folder, days ago, how many, who is in them, keywords, place (lat, lon) or None, caption)"""
    return [
        (f"{demo.day(-500).year}/Summer at Grandma's", 500, 9, FAMILY + ["Eleanor Calloway", "Walter Calloway"],
         ["Places/Oregon/Bend", "Events/Family visit"], (44.0582, -121.3153), "Lemonade on Eleanor and Walter's porch"),
        (f"{demo.day(-330).year}/Christmas", 330, 8, FAMILY + ["Grace Okafor", "Daniel Okafor"], ["Events/Christmas"],
         (demo.HOME["lat"], demo.HOME["lon"]), "Christmas morning at home"),
        (f"{demo.day(-200).year}/Coast weekend", 200, 12, FAMILY, ["Places/Oregon/Coast", "Holiday"], (45.8918, -123.9615),
         "Cannon Beach, Haystack Rock at low tide"),
        (f"{demo.day(-60).year}/Silver Creek hike", 60, 10, FAMILY, ["Places/Oregon/Silver Falls", "Hiking"], (44.8784, -122.6539),
         "Behind the waterfall"),
        (f"{demo.day(-30).year}/Theo's birthday", 30, 9, FAMILY + ["Lucas Raman", "Priya Raman"], ["Events/Birthday"],
         (demo.HOME["lat"], demo.HOME["lon"]), "Theo's rocket cake"),
        (f"{demo.day(-8).year}/Science fair", 8, 6, ["Ava Calloway", "Morgan Calloway", "Zoe Fischer"], ["Events/School"],
         (demo.HOME["lat"] + 0.01, demo.HOME["lon"] - 0.02), "Ava's plants and music project"),
    ]


def _picture(rnd: random.Random, w: int, h: int, faces: list):
    from PIL import Image, ImageDraw
    a = tuple(rnd.randrange(40, 220) for _ in range(3))
    b = tuple(rnd.randrange(40, 220) for _ in range(3))
    grad = Image.linear_gradient("L").resize((w, h))
    im = Image.composite(Image.new("RGB", (w, h), a), Image.new("RGB", (w, h), b), grad)
    d = ImageDraw.Draw(im)
    for _ in range(rnd.randrange(4, 9)):
        x, y, r = rnd.randrange(w), rnd.randrange(h), rnd.randrange(20, max(21, min(w, h) // 4))
        (d.ellipse if rnd.random() < .6 else d.rectangle)((x - r, y - r, x + r, y + r), fill=tuple(rnd.randrange(256) for _ in range(3)))
    for (x, y, fw, fh), skin in faces:
        d.ellipse((x, y, x + fw, y + fh), fill=skin)
        d.ellipse((x + fw * .28, y + fh * .35, x + fw * .38, y + fh * .45), fill=(40, 30, 30))
        d.ellipse((x + fw * .62, y + fh * .35, x + fw * .72, y + fh * .45), fill=(40, 30, 30))
        d.arc((x + fw * .3, y + fh * .45, x + fw * .7, y + fh * .78), 20, 160, fill=(120, 40, 40), width=max(2, fw // 30))
    return im


def _dms(v: float) -> tuple:
    v = abs(v)
    d = int(v); m = int((v - d) * 60); s = round(((v - d) * 60 - m) * 60, 4)
    return (d, m, s)


def _exif(when: dt.datetime, camera: tuple, gps):
    from PIL import Image
    from PIL.TiffImagePlugin import IFDRational
    ex = Image.Exif()
    ex[0x010F], ex[0x0110] = camera[:2]
    ex[0x0112] = 1
    ex[0x0132] = when.strftime("%Y:%m:%d %H:%M:%S")
    sub = ex.get_ifd(0x8769)
    sub[0x9003] = sub[0x9004] = when.strftime("%Y:%m:%d %H:%M:%S")
    sub[0xA434] = camera[2]
    if gps:
        g = ex.get_ifd(0x8825)
        g[1], g[2] = ("N" if gps[0] >= 0 else "S"), tuple(IFDRational(round(v * 10000), 10000) for v in _dms(gps[0]))
        g[3], g[4] = ("E" if gps[1] >= 0 else "W"), tuple(IFDRational(round(v * 10000), 10000) for v in _dms(gps[1]))
    return ex.tobytes()


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


def _sidecar(tags: list, regions: list, rating: int, caption: str, w: int, h: int) -> str:
    li = lambda items: "".join(f"<rdf:li>{_esc(x)}</rdf:li>" for x in items)  # noqa: E731
    faces = "".join(
        f'<rdf:li><rdf:Description mwg-rs:Name="{_esc(n)}" mwg-rs:Type="Face"><mwg-rs:Area stArea:x="{(x + fw / 2) / w:.6f}" '
        f'stArea:y="{(y + fh / 2) / h:.6f}" stArea:w="{fw / w:.6f}" stArea:h="{fh / h:.6f}" stArea:unit="normalized"/></rdf:Description></rdf:li>'
        for n, (x, y, fw, fh) in regions)
    return (
        '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>\n<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '<rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:digiKam="http://www.digikam.org/ns/1.0/" xmlns:lr="http://ns.adobe.com/lightroom/1.0/" xmlns:mwg-rs="http://www.metadataworkinggroup.com/schemas/regions/" '
        'xmlns:stArea="http://ns.adobe.com/xmp/sType/Area#" xmlns:stDim="http://ns.adobe.com/xap/1.0/sType/Dimensions#"'
        + (f' xmp:Rating="{rating}"' if rating > 0 else "") + '>\n'
        f'<digiKam:TagsList><rdf:Seq>{li(tags)}</rdf:Seq></digiKam:TagsList>\n'
        f'<lr:hierarchicalSubject><rdf:Bag>{li(t.replace("/", "|") for t in tags)}</rdf:Bag></lr:hierarchicalSubject>\n'
        f'<dc:subject><rdf:Bag>{li(t.rsplit("/", 1)[-1] for t in tags)}</rdf:Bag></dc:subject>\n'
        + (f'<dc:description><rdf:Alt><rdf:li xml:lang="x-default">{_esc(caption)}</rdf:li></rdf:Alt></dc:description>\n' if caption else "")
        + (f'<mwg-rs:Regions rdf:parseType="Resource"><mwg-rs:AppliedToDimensions stDim:w="{w}" stDim:h="{h}" stDim:unit="pixel"/>'
           f'<mwg-rs:RegionList><rdf:Bag>{faces}</rdf:Bag></mwg-rs:RegionList></mwg-rs:Regions>\n' if regions else "")
        + '</rdf:Description>\n</rdf:RDF>\n</x:xmpmeta>\n<?xpacket end="w"?>\n')


def write_photos(root: Path, seed: int = 20261117) -> int:
    """The demo's files under root/FOLDER; how many photos."""
    from app.photos.paths import sidecar_path
    rnd = random.Random(seed)
    skin = {n: SKIN[i % len(SKIN)] for i, n in enumerate(FAMILY + ["Eleanor Calloway", "Walter Calloway", "Grace Okafor",
                                                                   "Daniel Okafor", "Lucas Raman", "Priya Raman", "Zoe Fischer"])}
    n = 0
    for folder, ago, count, who, keywords, place, caption in _events():
        d = root / FOLDER / folder
        d.mkdir(parents=True, exist_ok=True)
        day0 = dt.datetime.combine(demo.day(-ago), dt.time(9, 30))
        for i in range(count):
            when = day0 + dt.timedelta(minutes=i * rnd.randint(9, 40))
            w, h = rnd.choice([(1600, 1200), (1200, 1600), (1600, 1067)])
            people = rnd.sample(who, k=min(len(who), rnd.choice([1, 2, 2, 3, 4]))) if i % 5 != 4 else []  # now and then: the view alone
            faces, regions = [], []
            for j, name in enumerate(people):
                fw = rnd.randrange(min(w, h) // 9, min(w, h) // 6)
                x = int((j + 0.5) * w / max(1, len(people)) - fw / 2 + rnd.randint(-fw // 3, fw // 3))
                y = rnd.randrange(h // 6, h // 2)
                faces.append(((x, y, fw, fw), skin[name]))
                regions.append((name, (x, y, fw, fw)))
            im = _picture(rnd, w, h, faces)
            path = d / f"IMG_{4000 + n}.jpg"
            gps = (place[0] + rnd.uniform(-0.002, 0.002), place[1] + rnd.uniform(-0.002, 0.002)) if place else None
            im.save(path, "JPEG", quality=82, exif=_exif(when, rnd.choice(CAMERAS), gps))
            os.utime(path, (when.timestamp(), when.timestamp()))
            tags = list(keywords) + [f"People/{p}" for p in people]
            rating = rnd.choice([0, 0, 3, 4, 5])
            Path(sidecar_path(str(path))).write_text(_sidecar(tags, regions, rating, caption if i == 0 else "", w, h), encoding="utf-8")
            n += 1
    return n


def seed(people: dict) -> None:
    from app.digikam import dkdb
    if not dkdb.no_digikam():
        log.info("demo: ioPix works on a digiKam library here; no demo photos are added to it")
        return
    root = Path(config.PHOTOS_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    n = write_photos(root)
    from app.photos import scanner
    res = scanner.scan(require_digikam_closed=False)
    log.info("demo: %d photos written, the scanner added %s", n, res.get("added"))
    from app.auth import set_person
    from app.digikam import library
    con = library.connect()
    try:
        top = con.execute("SELECT id FROM Tags WHERE name = 'People' AND pid = 0").fetchone()
        tags = {r[1]: r[0] for r in con.execute("SELECT id, name FROM Tags WHERE pid = ?", (top[0],))} if top else {}
    finally:
        con.close()
    for key, p in people.items():
        tid = tags.get(p["displayName"])
        if tid:
            set_person(p["id"], tid)
