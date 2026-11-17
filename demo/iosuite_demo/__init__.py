"""The suite's demo data, kept apart from the apps: a made-up family of four, the Calloways, with something in every
app, to show the suite to someone or to try it out without one's own data.

This package is never part of an install: a real server or Docker image carries only an app's own folder and shared/.
While the suite's demo switch is on (iosuite_shared.demo), an app that starts and has not been seeded fetches this
package (iosuite-demo.zip, attached to the suite's release of its version by the release workflow; a git checkout uses
this folder), runs `seed(app)` from it and drops it again.

Everything here is invented: the people, their addresses, the email addresses (example.com, which is reserved for
this), the phone numbers (555-01xx, kept for fiction), the accounts and amounts. The pictures are drawn by the seeds,
except ioPix's photos: Wikimedia Commons and StockSnap pictures under Creative Commons or public domain (a download of
their own, see iopix.py) whose made-up people became the Calloways.

Each app has its module here (iotask.py, ...) with `seed(people)`, written with the app's own code (`from app import
...`: it runs inside the app), so it follows the app's tables as they change; the apps' tests run them. `ensure()` makes
the family's accounts when missing, `run(app, seed)` runs a seed once.

The dates are relative to the day the seed runs (the events are this week and the next, the health data ends
yesterday, the transactions run up to today), so a demo looks lived in on the day it is made.

The accounts sign in with the password DEMO_PASSWORD. Morgan is a suite admin; Riley an admin of every app; Ava and Theo
members.
"""
import datetime as dt
import logging
import time

from iosuite_shared.demo import DEMO_PASSWORD, FAMILY_KEYS, SEEDED, seeded  # noqa: F401 - the switch's side, in every install

log = logging.getLogger("iosuite_demo")
SURNAME = "Calloway"

# Address, phones and emails are all made up (555-01xx and example.com are kept for fiction and examples).
HOME = {"street": "42 Juniper Lane", "city": "Eugene", "region": "OR", "postcode": "97405", "country": "United States",
        "phone": "+1 541 555 0142", "lat": 44.0521, "lon": -123.0868, "tz": "America/Los_Angeles"}

FAMILY = [
    {"key": "morgan", "first": "Morgan", "born": (1984, 3, 12), "role": "admin", "suite_admin": True, "parent": True,
     "gender": "female", "color": "#1a73e8", "phone": "+1 541 555 0110", "job": "Landscape architect", "employer": "Greenline Studio"},
    {"key": "riley", "first": "Riley", "born": (1983, 7, 29), "role": "admin", "suite_admin": False, "parent": True,
     "gender": "male", "color": "#1e8e3e", "phone": "+1 541 555 0111", "job": "High school science teacher", "employer": "Juniper Hill High School"},
    {"key": "ava", "first": "Ava", "born": (2012, 5, 4), "role": "member", "suite_admin": False, "parent": False,
     "gender": "female", "color": "#e0426a", "phone": "+1 541 555 0112", "job": "", "employer": ""},
    {"key": "theo", "first": "Theo", "born": (2017, 10, 21), "role": "member", "suite_admin": False, "parent": False,
     "gender": "male", "color": "#e8710a", "phone": "+1 541 555 0113", "job": "", "employer": ""},
]
assert tuple(p["key"] for p in FAMILY) == FAMILY_KEYS
PET = {"name": "Biscuit", "kind": "dog", "breed": "Golden retriever", "born": (2020, 6, 1)}

# Friends and relatives the apps mention (ioContact cards, ioCalendar birthdays, ioPix people): all invented.
RELATIVES = [
    {"first": "Eleanor", "last": "Calloway", "born": (1956, 2, 17), "relation": "mother", "of": "riley", "phone": "+1 541 555 0120", "city": "Bend"},
    {"first": "Walter", "last": "Calloway", "born": (1954, 11, 3), "relation": "father", "of": "riley", "phone": "+1 541 555 0121", "city": "Bend"},
    {"first": "Grace", "last": "Okafor", "born": (1958, 9, 9), "relation": "mother", "of": "morgan", "phone": "+1 503 555 0122", "city": "Portland"},
    {"first": "Daniel", "last": "Okafor", "born": (1987, 1, 24), "relation": "brother", "of": "morgan", "phone": "+1 503 555 0123", "city": "Portland"},
    {"first": "Priya", "last": "Raman", "born": (1985, 12, 2), "relation": "friend", "of": "morgan", "phone": "+1 541 555 0124", "city": "Eugene"},
    {"first": "Sam", "last": "Becker", "born": (1982, 4, 15), "relation": "friend", "of": "riley", "phone": "+1 541 555 0125", "city": "Eugene"},
    {"first": "Lucas", "last": "Raman", "born": (2017, 8, 30), "relation": "friend", "of": "theo", "phone": "", "city": "Eugene"},
    {"first": "Zoe", "last": "Fischer", "born": (2012, 3, 19), "relation": "friend", "of": "ava", "phone": "", "city": "Eugene"},
]


def email_of(key: str) -> str:
    return f"{key}@calloway.example.com"


def display_name(p: dict) -> str:
    return f"{p['first']} {SURNAME}"


def born(p: dict) -> dt.date:
    return dt.date(*p["born"])


def today() -> dt.date:
    return dt.date.today()


def day(offset: int) -> dt.date:
    """The date `offset` days from today (negative: in the past)."""
    return today() + dt.timedelta(days=offset)


def next_birthday(p: dict) -> dt.date:
    b, t = born(p), today()
    for y in (t.year, t.year + 1):
        try:
            d = b.replace(year=y)
        except ValueError:  # 29 February
            d = dt.date(y, 3, 1)
        if d >= t:
            return d
    return b


# ---- the family's accounts
def ensure() -> dict:
    """The four accounts (made when missing, in the family list with their colours): {key: person}, each person a dict
    of FAMILY's fields with `id`, `name` (the account name), `displayName` and `email` added. Several apps starting at
    the same moment make them once (a named lock on the Shared ioSuite database)."""
    from iosuite_shared import db, family, users
    out = {}
    with db.tx() as con:
        with con.cursor() as cur:
            cur.execute("SELECT GET_LOCK('iosuite_demo_family', 60) AS ok")
        try:
            for p in FAMILY:
                u = users.find(p["key"])
                if not u:
                    u = users.create(p["key"], DEMO_PASSWORD, email=email_of(p["key"]), display_name=display_name(p),
                                     suite_admin=p["suite_admin"])
                    users.set_value(u["id"], family.SUITE, family.KEY, {"color": p["color"]})
                out[p["key"]] = dict(p, id=u["id"], name=u["name"], displayName=display_name(p), email=email_of(p["key"]))
        finally:
            with con.cursor() as cur:
                cur.execute("SELECT RELEASE_LOCK('iosuite_demo_family')")
    users.invalidate()
    return out


def give_roles(app: str, people: dict) -> None:
    """Each person's role in the app (Riley an admin, the children members; Morgan, a suite admin, is admin anyway)."""
    from iosuite_shared import users
    if users._is_tool(app):  # an admin tool (ioDNS, ioBackup): suite admins only
        return
    for p in people.values():
        if not p["suite_admin"]:
            users.set_role(p["id"], app, p["role"])


# ---- running an app's seed
def run(app: str, seed, force: bool = False) -> bool:
    """Run the app's seed(people) once (again with force). Returns whether it ran."""
    from iosuite_shared import db
    if seeded(app) and not force:
        return False
    people = ensure()
    give_roles(app, people)
    db.set_setting(SEEDED, str(int(time.time())), app)  # first: a seed that fails half-way is not run again at every start
    t = time.time()
    seed(people)
    log.info("demo data added to %s in %.1f s", app, time.time() - t)
    return True


def seed(app: str, force: bool = False) -> bool:
    """Run the app's module of this package once (again with force); whether it ran."""
    import importlib
    return run(app, importlib.import_module(f"{__name__}.{app}").seed, force)


# ---- pictures for the demo, drawn (no photos of anything real); Pillow is needed (every app with pictures has it)
def picture(label: str, color: str = "#1a73e8", size: tuple = (1200, 800), shapes: int = 7, seed: int | None = None,
            fmt: str = "JPEG") -> bytes:
    """A made-up picture: a soft two-colour gradient, a few round shapes and the label written large; JPEG bytes."""
    import io
    import random
    from PIL import Image, ImageDraw, ImageFont
    rnd = random.Random(seed if seed is not None else label)
    w, h = size
    base = tuple(int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    other = tuple(min(255, int(c * 0.45 + 255 * 0.55)) for c in base)
    img = Image.new("RGB", (w, h), base)
    d = ImageDraw.Draw(img)
    for y in range(h):
        f = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(base[i] * (1 - f) + other[i] * f) for i in range(3)))
    for _ in range(shapes):
        r = rnd.randint(min(w, h) // 12, min(w, h) // 4)
        x, y = rnd.randint(0, w), rnd.randint(0, h)
        tint = tuple(min(255, max(0, c + rnd.randint(-70, 90))) for c in base)
        d.ellipse([x - r, y - r, x + r, y + r], fill=tint)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", max(18, w // 16))
    except OSError:
        try:
            font = ImageFont.load_default(size=max(18, w // 16))
        except TypeError:  # an old Pillow
            font = ImageFont.load_default()
    box = d.textbbox((0, 0), label, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    d.rounded_rectangle([(w - tw) / 2 - 24, (h - th) / 2 - 18, (w + tw) / 2 + 24, (h + th) / 2 + 26], radius=18, fill=(255, 255, 255))
    d.text(((w - tw) / 2, (h - th) / 2 - box[1] + 4), label, fill=base, font=font)
    out = io.BytesIO()
    img.save(out, fmt, quality=85)
    return out.getvalue()
