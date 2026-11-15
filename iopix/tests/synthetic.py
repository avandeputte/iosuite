"""A digiKam library made from scratch for the tests, so they run where no real library is at hand (CI).

`build(dst)` writes what tests/fixture.py cuts from a real library, in the same layout and with the same facts
returned: dst/db/digikam4.db with digiKam 8's own schema (tests/digikam_schema.sql: its tables, indices and
triggers), and dst/photos with the files it lists, made here: JPEG photos with Exif dates, cameras and GPS
positions, a few PNG and HEIC files, and short MP4 videos (when ffmpeg is installed). The database has what a
digiKam library holds for them: albums, sizes and dates, cameras, positions, ratings, captions, keyword tags in a
tree, the internal pick and colour labels, people with face regions, unnamed, suggested and ignored faces, and videos with
their duration. Everything is drawn from a fixed seed, so every run makes the same library.
"""
import hashlib
import os
import random
import shutil
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw

SCHEMA = Path(__file__).with_name("digikam_schema.sql")

ALBUMS = ["/Scans", "/2019/Summer", "/2021/Birthday", "/2022/Hiking", "/2023/Beach", "/2024/Family"]  # in the order they were taken
PEOPLE = ["Ann Lee", "Ben Ray", "Cleo Marsh", "Dan Fox"]
KEYWORDS = [("Places", None), ("France", "Places"), ("Paris", "France"), ("Events", None), ("Birthday", "Events"),
            ("Holiday", None), ("Beach", None), ("Mountains", None)]
KEYED = {"/2021/Birthday": ["Birthday"], "/2023/Beach": ["Beach", "Holiday"], "/2022/Hiking": ["Mountains"]}  # the keywords each album's photos have
PICK_TAGS = ["Pick Label None", "Pick Label Rejected", "Pick Label Pending", "Pick Label Accepted"]
COLOR_TAGS = [f"Color Label {n}" for n in ("None", "Red", "Orange", "Yellow", "Green", "Blue", "Magenta", "Gray", "Black", "White")]
CAMERAS = [("Apple", "iPhone 13", "iPhone 13 back dual wide camera 5.1mm f/1.6"), ("Canon", "Canon EOS R6", "RF24-105mm F4 L IS USM"),
           ("SONY", "ILCE-7M3", "FE 35mm F1.8"), ("FUJIFILM", "X-T4", "XF23mmF2 R WR")]
PLACES = [(48.8566, 2.3522), (45.9237, 6.8694), (43.2965, 5.3698), (40.7128, -74.0060), (51.5074, -0.1278)]


def unique_hash(path: Path) -> str:
    """digiKam's uniqueHash version 3 (DImg::createUniqueHashV3): the first 100 kB and five 25 kB blocks after it."""
    size = path.stat().st_size
    h = hashlib.md5()
    with open(path, "rb") as f:
        fsize = min(size, 100 * 1024)
        bsize = size - fsize
        block = min(bsize, 25 * 1024)
        step = (bsize - block) // 5 + 1
        for sp in range(6):
            rsize = fsize if sp == 0 else block
            f.seek(min(0 if sp == 0 else step * sp + fsize, size - rsize))
            h.update(f.read(rsize))
            if f.tell() >= size:
                break
    return h.hexdigest()


def _dms(v: float) -> tuple:
    v = abs(v)
    d = int(v); m = int((v - d) * 60); s = round(((v - d) * 60 - m) * 60, 4)
    return (d, m, s)


def _picture(rnd: random.Random, w: int, h: int, faces: list) -> Image.Image:
    """A picture of its own: a two-colour gradient, a few shapes, and a pale disc where each face region is."""
    a = tuple(rnd.randrange(30, 225) for _ in range(3)); b = tuple(rnd.randrange(30, 225) for _ in range(3))
    grad = Image.linear_gradient("L").resize((w, h))
    im = Image.composite(Image.new("RGB", (w, h), a), Image.new("RGB", (w, h), b), grad)
    d = ImageDraw.Draw(im)
    for _ in range(rnd.randrange(3, 8)):
        x, y = rnd.randrange(w), rnd.randrange(h); r = rnd.randrange(10, max(11, min(w, h) // 4))
        (d.ellipse if rnd.random() < .5 else d.rectangle)((x - r, y - r, x + r, y + r), fill=tuple(rnd.randrange(256) for _ in range(3)))
    for x, y, fw, fh in faces:
        d.ellipse((x, y, x + fw, y + fh), fill=(236, 200, 170))
        d.ellipse((x + fw * .28, y + fh * .35, x + fw * .38, y + fh * .45), fill=(40, 30, 30))
        d.ellipse((x + fw * .62, y + fh * .35, x + fw * .72, y + fh * .45), fill=(40, 30, 30))
    return im


def _exif(when: datetime, camera: tuple, gps: tuple | None, shot: dict) -> bytes:
    from PIL.TiffImagePlugin import IFDRational
    ex = Image.Exif()
    ex[0x010F], ex[0x0110] = camera[:2]  # Make, Model
    ex[0x0112] = 1  # Orientation
    ex[0x0132] = when.strftime("%Y:%m:%d %H:%M:%S")
    sub = ex.get_ifd(0x8769)
    sub[0x9003] = sub[0x9004] = when.strftime("%Y:%m:%d %H:%M:%S")  # DateTimeOriginal, DateTimeDigitized
    sub[0x829D] = IFDRational(round(shot["aperture"] * 10), 10)  # FNumber
    sub[0x920A] = IFDRational(round(shot["focal"]), 1)  # FocalLength
    sub[0x829A] = IFDRational(1, round(1 / shot["exposure"]))  # ExposureTime
    sub[0x8827] = shot["iso"]  # ISOSpeedRatings
    sub[0xA434] = shot["lens"]  # LensModel
    if gps:
        g = ex.get_ifd(0x8825)
        g[1], g[2] = ("N" if gps[0] >= 0 else "S"), tuple(IFDRational(round(v * 10000), 10000) for v in _dms(gps[0]))
        g[3], g[4] = ("E" if gps[1] >= 0 else "W"), tuple(IFDRational(round(v * 10000), 10000) for v in _dms(gps[1]))
    return ex.tobytes()


def _full(name: str) -> str:
    """A keyword's path in the tag tree (Places/France/Paris)."""
    parent = dict(KEYWORDS)[name]
    return f"{_full(parent)}/{name}" if parent else name


def _sidecar(tags: list, regions: list, rating: int, w: int, h: int) -> str:
    """The XMP sidecar digiKam writes: its tag paths, the keywords, the rating and the face regions (MWG, centre and size
    as fractions of the picture)."""
    li = lambda items: "".join(f"<rdf:li>{x}</rdf:li>" for x in items)  # noqa: E731
    faces = "".join(
        f'<rdf:li><rdf:Description mwg-rs:Name="{n}" mwg-rs:Type="Face"><mwg-rs:Area stArea:x="{(x + fw / 2) / w:.6f}" stArea:y="{(y + fh / 2) / h:.6f}" '
        f'stArea:w="{fw / w:.6f}" stArea:h="{fh / h:.6f}" stArea:unit="normalized"/></rdf:Description></rdf:li>' for n, (x, y, fw, fh) in regions)
    return (
        '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '<rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:digiKam="http://www.digikam.org/ns/1.0/" xmlns:lr="http://ns.adobe.com/lightroom/1.0/" xmlns:mwg-rs="http://www.metadataworkinggroup.com/schemas/regions/" '
        'xmlns:stArea="http://ns.adobe.com/xmp/sType/Area#" xmlns:stDim="http://ns.adobe.com/xap/1.0/sType/Dimensions#"'
        + (f' xmp:Rating="{rating}"' if rating >= 0 else "") + '>\n'
        f'<digiKam:TagsList><rdf:Seq>{li(tags)}</rdf:Seq></digiKam:TagsList>\n'
        f'<lr:hierarchicalSubject><rdf:Bag>{li(t.replace("/", "|") for t in tags)}</rdf:Bag></lr:hierarchicalSubject>\n'
        f'<dc:subject><rdf:Bag>{li(t.rsplit("/", 1)[-1] for t in tags)}</rdf:Bag></dc:subject>\n'
        + (f'<mwg-rs:Regions rdf:parseType="Resource"><mwg-rs:AppliedToDimensions stDim:w="{w}" stDim:h="{h}" stDim:unit="pixel"/>'
           f'<mwg-rs:RegionList><rdf:Bag>{faces}</rdf:Bag></mwg-rs:RegionList></mwg-rs:Regions>\n' if regions else "")
        + '</rdf:Description>\n</rdf:RDF>\n</x:xmpmeta>\n<?xpacket end="w"?>\n')


def _heif_ok() -> bool:
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
        return True
    except Exception:
        return False


def build(dst: Path, seed: int = 20261114) -> dict:
    rnd = random.Random(seed)
    dst = Path(dst)
    shutil.rmtree(dst, ignore_errors=True)
    (dst / "db").mkdir(parents=True)
    root = dst / "photos"
    root.mkdir()
    db = dst / "db" / "digikam4.db"
    con = sqlite3.connect(db)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    for k, v in (("DBVersion", "16"), ("DBVersionRequired", "16"), ("uniqueHashVersion", "3"), ("databaseImageFormats", "jpg;jpeg;png;heic;heif"),
                 ("databaseVideoFormats", "mp4;mov"), ("databaseUUID", "{8c1e0a52-5b8a-4f0b-9d1e-1a2b3c4d5e6f}")):
        con.execute("INSERT OR REPLACE INTO Settings (keyword, value) VALUES (?, ?)", (k, v))
    root_id = con.execute("INSERT INTO AlbumRoots (label, status, type, identifier, specificPath, caseSensitivity) VALUES (?,?,?,?,?,?)",
                          ("photos", 0, 1, "volumeid:?path=" + str(root), str(root), 2)).lastrowid

    def tag(name, pid=0, *props):
        tid = con.execute("INSERT INTO Tags (pid, name) VALUES (?, ?)", (pid, name)).lastrowid
        for p, v in props:
            con.execute("INSERT INTO TagProperties (tagid, property, value) VALUES (?, ?, ?)", (tid, p, v))
        return tid
    internal = tag("_Digikam_Internal_Tags_", 0, ("internalTag", None))
    labels = {n: tag(n, internal, ("internalTag", None)) for n in PICK_TAGS + COLOR_TAGS}
    people = tag("People")
    unknown = tag("Unknown", people, ("unknownPerson", None))
    unconfirmed = tag("Unconfirmed", people, ("unconfirmedPerson", None))
    ignored = tag("Ignored", people, ("ignoredPerson", None))
    person = {n: tag(n, people, ("person", n), ("faceEngineName", n)) for n in PEOPLE}
    kw = {}
    for name, parent in KEYWORDS:
        kw[name] = tag(name, kw[parent] if parent else 0)

    albums = {}
    start = datetime(2018, 5, 28, 10, 0, 0)
    # digiKam keeps a row for every folder of the root, the root itself and the year folders included
    for rel in sorted({"/"} | {"/" + "/".join(a.strip("/").split("/")[:k]) for a in ALBUMS for k in range(1, a.count("/"))}):
        con.execute("INSERT INTO Albums (albumRoot, relativePath, date, caption, collection) VALUES (?, ?, ?, NULL, NULL)", (root_id, rel, start.strftime("%Y-%m-%d")))
    for i, rel in enumerate(ALBUMS):
        (root / rel.lstrip("/")).mkdir(parents=True, exist_ok=True)
        albums[rel] = con.execute("INSERT INTO Albums (albumRoot, relativePath, date, caption, collection) VALUES (?, ?, ?, NULL, NULL)",
                                  (root_id, rel, (start + timedelta(days=400 * i)).strftime("%Y-%m-%d"))).lastrowid

    heif = _heif_ok()
    kinds = ["jpg"] * 76 + ["png"] * 6 + (["heic"] * 6 if heif else ["jpg"] * 6)
    rnd.shuffle(kinds)
    ids, with_faces, with_tags, with_gps, videos = [], [], [], [], []
    n = 0
    for i, kind in enumerate(kinds):
        rel = ALBUMS[i % len(ALBUMS)]
        when = start + timedelta(days=400 * (i % len(ALBUMS)) + i // len(ALBUMS) // 5, hours=rnd.randrange(0, 9), minutes=rnd.randrange(60))  # a few photos a day, as people take them
        w, h = rnd.choice([(1200, 800), (800, 1200), (1024, 768), (900, 900)])
        nfaces = 0 if rel == "/Scans" else rnd.choice([1, 2, 3]) if rel == "/2024/Family" else rnd.choice([0, 0, 1, 1, 2, 3])
        faces = []
        for _ in range(nfaces):
            fw = rnd.randrange(min(w, h) // 12, min(w, h) // 7)
            faces.append((rnd.randrange(0, w - 4 * fw), rnd.randrange(0, h - fw), fw, fw))
        gps = rnd.choice(PLACES) if i % 3 != 2 and kind != "png" else None
        camera = rnd.choice(CAMERAS)
        shot = {"aperture": rnd.choice([1.8, 2.8, 4.0, 5.6]), "focal": rnd.choice([26.0, 35.0, 50.0, 85.0]), "exposure": rnd.choice([1 / 60, 1 / 250, 1 / 1000]),
                "iso": rnd.choice([100, 200, 400, 1600]), "lens": camera[2]}
        im = _picture(rnd, w, h, faces)
        name = f"IMG_{1000 + i}.{kind}" if kind != "png" else f"Screenshot {i}.png"
        path = root / rel.lstrip("/") / name
        if kind == "jpg":
            im.save(path, "JPEG", quality=85, exif=_exif(when, camera, gps, shot))
        elif kind == "heic":
            im.save(path, "HEIF", quality=70, exif=_exif(when, camera, gps, shot))
        else:
            im.save(path, "PNG")
            camera, gps = (None, None, None), None
        stamp = when.strftime("%Y-%m-%dT%H:%M:%S.000")
        os.utime(path, (when.timestamp(), when.timestamp()))
        iid = con.execute("INSERT INTO Images (album, name, status, category, modificationDate, fileSize, uniqueHash) VALUES (?,?,1,1,?,?,?)",
                          (albums[rel], name, stamp, path.stat().st_size, unique_hash(path))).lastrowid
        con.execute("INSERT INTO ImageInformation (imageid, rating, creationDate, digitizationDate, orientation, width, height, format, colorDepth, colorModel) "
                    "VALUES (?,?,?,?,1,?,?,?,8,5)", (iid, rating := rnd.choice([-1, -1, 0, 1, 3, 4, 5]) if kind != "png" else -1, stamp, stamp, w, h, {"jpg": "JPG", "png": "PNG", "heic": "HEIF"}[kind]))
        if camera[0]:
            con.execute("INSERT INTO ImageMetadata (imageid, make, model, lens, aperture, focalLength, exposureTime, sensitivity, flash) VALUES (?,?,?,?,?,?,?,?,0)",
                        (iid, camera[0], camera[1], shot["lens"], shot["aperture"], shot["focal"], shot["exposure"], shot["iso"]))
        if gps:
            lat, lon = gps
            con.execute("INSERT INTO ImagePositions (imageid, latitude, latitudeNumber, longitude, longitudeNumber, altitude) VALUES (?,?,?,?,?,?)",
                        (iid, "%d,%.8f%s" % (int(abs(lat)), (abs(lat) % 1) * 60, "N" if lat >= 0 else "S"), lat,
                         "%d,%.8f%s" % (int(abs(lon)), (abs(lon) % 1) * 60, "E" if lon >= 0 else "W"), lon, float(rnd.randrange(0, 1500))))
            with_gps.append(iid)
        named, regions = 0, []
        for j, (x, y, fw, fh) in enumerate(faces):  # the rows digiKam's FaceTagsEditor writes (see app/faces/facemgr.py)
            region = f'<rect x="{x}" y="{y}" width="{fw}" height="{fh}"/>'
            who = PEOPLE[(i + j) % len(PEOPLE)]
            if j == 0 or j < len(faces) - 1 or rnd.random() < .5:  # confirmed: every photo with faces has a named one
                tid = person[who]
                con.execute("INSERT OR IGNORE INTO ImageTags (imageid, tagid) VALUES (?, ?)", (iid, tid))
                con.execute("INSERT INTO ImageTagProperties (imageid, tagid, property, value) VALUES (?, ?, 'tagRegion', ?)", (iid, tid, region))
                con.execute("INSERT INTO ImageTagProperties (imageid, tagid, property, value) VALUES (?, ?, 'faceToTrain', ?)", (iid, tid, region))
                named += 1
                regions.append((who, (x, y, fw, fh)))
            elif rnd.random() < .5:  # unknown: found, nobody named
                con.execute("INSERT INTO ImageTagProperties (imageid, tagid, property, value) VALUES (?, ?, 'autodetectedFace', ?)", (iid, unknown, region))
            else:  # suggested: recognition thinks it is someone
                con.execute("INSERT INTO ImageTagProperties (imageid, tagid, property, value) VALUES (?, ?, 'autodetectedFace', ?)", (iid, person[who], region))
                con.execute("INSERT INTO ImageTagProperties (imageid, tagid, property, value) VALUES (?, ?, 'autodetectedPerson', ?)",
                            (iid, unconfirmed, f"{person[who]},autodetectedFace,{region}"))
        if faces and i % 4 == 1:  # a face somebody told digiKam to ignore
            x, y, fw, fh = faces[0]
            con.execute("INSERT INTO ImageTagProperties (imageid, tagid, property, value) VALUES (?, ?, 'ignoredFace', ?)",
                        (iid, ignored, f'<rect x="{x + 2 * fw}" y="{y}" width="{fw}" height="{fh}"/>'))
        if faces:
            with_faces.append(iid)
        keys = list(KEYED.get(rel, []))
        if gps == PLACES[0]:
            keys.append("Paris")
        for k in keys:
            con.execute("INSERT OR IGNORE INTO ImageTags (imageid, tagid) VALUES (?, ?)", (iid, kw[k]))
        if i % 5 == 0:  # a colour label here and there, as digiKam keeps it: an internal tag
            con.execute("INSERT OR IGNORE INTO ImageTags (imageid, tagid) VALUES (?, ?)", (iid, labels[rnd.choice(COLOR_TAGS[1:6])]))
        if keys or named:
            with_tags.append(iid)
        if kind != "png":  # digiKam, set to write metadata to sidecars, keeps one beside every photo
            Path(str(path) + ".xmp").write_text(_sidecar([_full(k) for k in keys] + [f"People/{n}" for n, _ in regions], regions, rating, w, h), encoding="utf-8")
        if i % 7 == 0:
            con.execute("INSERT INTO ImageComments (imageid, type, language, comment) VALUES (?, 1, 'x-default', ?)",
                        (iid, f"{rel.rsplit('/', 1)[-1]}, a day to remember"))
        ids.append(iid)
        n += 1

    if shutil.which("ffmpeg"):
        for k, rel in enumerate(("/2021/Birthday", "/2023/Beach", "/2024/Family")):
            when = start + timedelta(days=400 * (ALBUMS.index(rel)), hours=k + 1)
            name = f"MOV_{2000 + k}.mp4"
            path = root / rel.lstrip("/") / name
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc=duration={2 + k}:size=320x240:rate=15",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-metadata", "creation_time=" + when.strftime("%Y-%m-%dT%H:%M:%SZ"), str(path)], check=True)
            stamp = when.strftime("%Y-%m-%dT%H:%M:%S.000")
            os.utime(path, (when.timestamp(), when.timestamp()))
            iid = con.execute("INSERT INTO Images (album, name, status, category, modificationDate, fileSize, uniqueHash) VALUES (?,?,1,2,?,?,?)",
                              (albums[rel], name, stamp, path.stat().st_size, unique_hash(path))).lastrowid
            con.execute("INSERT INTO ImageInformation (imageid, rating, creationDate, digitizationDate, orientation, width, height, format, colorDepth, colorModel) "
                        "VALUES (?,0,?,?,1,320,240,'MP4',8,5)", (iid, stamp, stamp))
            con.execute("INSERT INTO VideoMetadata (imageid, aspectRatio, duration, frameRate, videoCodec) VALUES (?, '4:3', ?, '15', 'h264')",
                        (iid, str((2 + k) * 1000)))
            ids.append(iid); videos.append(iid); n += 1
    con.commit()
    con.close()
    return {"db": db, "root": root, "ids": sorted(ids), "n": n, "albums": ALBUMS, "with_faces": with_faces,
            "with_tags": with_tags, "with_gps": with_gps, "videos": videos}


if __name__ == "__main__":
    import sys
    info = build(Path(sys.argv[1]))
    print({k: (v if not isinstance(v, list) else len(v)) for k, v in info.items()})
