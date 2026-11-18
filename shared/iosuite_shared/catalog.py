"""The suite's apps as they come: one manifest per app (<app>/app.json in the repository), gathered into apps.json here.

Every app's folder in the repository holds its app.json: its key, its name, its default port, its folder on the suite's
one address, its colour, how the suite installer sets it up, the kinds of items it has (what the linked-items panel
and the start page's search box find in it) and the notifications it sends. Nothing else in the suite keeps a list
of the apps: the default ports (suite.PORTS), the folders (suite.FOLDERS), the installer (install.APPS), the
notifications (push.KINDS), the linked items (related.KINDS), the files every app keeps alike, the Proxmox scripts'
"Also install" lists, install.sh and the Docker Compose builder are all read from here or made from it.

The shared library goes with every app that is installed, on its own too (BASE/<app>/app holds the app's folder and
shared/ beside it, no other app's folder), so the manifests are gathered into apps.json in this package, which every
install carries: an app installed alone still knows the others' ports and folders, for when they are added beside it.
An app that is not installed is simply not in the suite's list of apps (suite.visible): nothing here makes it show.

    python3 shared/templates/render.py            gather the manifests into apps.json and write every file made from them
    python3 shared/templates/render.py --check    fail when one of them is not as the manifests say (CI runs it)

A new app: its folder, its app.json (copy one), then render.py. The manifest's fields:

  key, name, description   the folder and the app's key (iocalendar), its name (ioCalendar), a word or two for the
                           suite's list of apps ("Calendar"); tag: one line for the website
  color                    its colour (#963522)
  port, folder             its default port, its folder on the suite's one address (none for the start page)
  order                    where it comes in lists (the website, the builder, the installer)
  adminTool                for suite admins only (ioDNS, ioBackup)
  heavy                    installed last (ioPix: a large image, the AI models)
  aside, otherPorts        what the installer's lists add after its name ("the start page") and port ("LDAP 3890")
  keepsOwn                 which of the files kept alike it has its own of: setup, workflow
  compose                  the Docker Compose builder: name (its sub-domain by default), what (one word)
  install                  the suite installer: data (gets a data folder), extra (setup.sh arguments), photos (ioPix's
                           photos folder), launchd (its launchd label on a Mac)
  items                    [{kind, label, plural, href, id}]: the kinds of items it has; href opens one in the app
                           ("#/event/{id}"); id "uuid" for UUIDs (default: a number)
  notifications            [{kind, label, hint, admin}]: what Account › Notifications offers from it
  start                    the start page: rank (where its tile comes; none: after those that have one, by name),
                           tile (it answers /api/suite/tile), find {head, rank} (it answers /api/suite/search: the
                           search box's section for it), searchUrl (its own search, "#/search/{q}": the "Search in" row)
                           See iosuite_shared.suiteitems for the endpoints; an app with items answers
                           /api/suite/items/{kind}/{id} for them.
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILE = HERE / "apps.json"
MANIFEST = "app.json"
KEY = re.compile(r"^io[a-z]{2,20}$")
KIND = re.compile(r"^[a-z_]{2,30}$")
COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def validate(apps: list[dict]) -> list[dict]:
    """The manifests, checked and in their order; ValueError on the first that is wrong."""
    seen_port, seen_folder, seen_kind, seen_note = {}, {}, {}, {}
    for m in apps:
        k = m.get("key")
        if not isinstance(k, str) or not KEY.fullmatch(k):
            raise ValueError(f"{MANIFEST}: key {k!r} is not io + a few letters")
        for f in ("name", "description", "color", "port", "order"):
            if m.get(f) in (None, ""):
                raise ValueError(f"{k}/{MANIFEST}: no {f}")
        if not COLOR.fullmatch(str(m["color"])):
            raise ValueError(f"{k}/{MANIFEST}: color {m['color']!r} is not #rrggbb")
        if not isinstance(m["port"], int) or not 1024 <= m["port"] < 65536:
            raise ValueError(f"{k}/{MANIFEST}: port {m['port']!r}")
        if m["port"] in seen_port:
            raise ValueError(f"{k}/{MANIFEST}: port {m['port']} is {seen_port[m['port']]}'s already")
        seen_port[m["port"]] = k
        f = m.get("folder")
        if f is not None:
            if not re.fullmatch(r"[a-z0-9-]{2,30}", str(f)):
                raise ValueError(f"{k}/{MANIFEST}: folder {f!r}")
            if f in seen_folder:
                raise ValueError(f"{k}/{MANIFEST}: folder {f} is {seen_folder[f]}'s already")
            seen_folder[f] = k
        for it in m.get("items") or []:
            if not KIND.fullmatch(str(it.get("kind"))) or not it.get("label") or not it.get("plural") or "{id}" not in str(it.get("href")):
                raise ValueError(f"{k}/{MANIFEST}: an item needs kind, label, plural and an href with {{id}}: {it}")
            if it["kind"] in seen_kind:
                raise ValueError(f"{k}/{MANIFEST}: item kind {it['kind']} is {seen_kind[it['kind']]}'s already")
            seen_kind[it["kind"]] = k
        for n in m.get("notifications") or []:
            if not KIND.fullmatch(str(n.get("kind"))) or not n.get("label") or not n.get("hint"):
                raise ValueError(f"{k}/{MANIFEST}: a notification needs kind, label and hint: {n}")
            if n["kind"] in seen_note:
                raise ValueError(f"{k}/{MANIFEST}: notification {n['kind']} is {seen_note[n['kind']]}'s already")
            seen_note[n["kind"]] = k
        st = m.get("start") or {}
        if st.get("searchUrl") and "{q}" not in st["searchUrl"]:
            raise ValueError(f"{k}/{MANIFEST}: start.searchUrl needs {{q}}")
        if st.get("find") and not (st["find"].get("head") and isinstance(st["find"].get("rank"), int)):
            raise ValueError(f"{k}/{MANIFEST}: start.find needs head and rank")
        for own in m.get("keepsOwn") or []:
            if own not in ("setup", "workflow"):
                raise ValueError(f"{k}/{MANIFEST}: keepsOwn {own!r} (setup or workflow)")
    return sorted(apps, key=lambda m: (m["order"], m["key"]))


def gather(root) -> list[dict]:
    """Every <app>/app.json in the repository at root, checked and in order."""
    found = []
    for p in sorted(Path(root).glob(f"io*/{MANIFEST}")):
        m = json.loads(p.read_text(encoding="utf-8"))
        if m.get("key") != p.parent.name:
            raise ValueError(f"{p}: key {m.get('key')!r} is not its folder's name")
        found.append(m)
    return validate(found)


def dumps(apps: list[dict]) -> str:
    """apps.json as render.py writes it."""
    return json.dumps({"_": "Made by shared/templates/render.py from every app's app.json: change those, not this.",
                       "apps": apps}, indent=1, ensure_ascii=False) + "\n"


def env_of(app: str) -> str:
    """The prefix of the environment variables its setup.sh reads its secrets from: IOCALENDAR."""
    return app.upper()


def install_order() -> list[str]:
    """The apps in the order the installer lists and installs them: the heavy ones (ioPix) last."""
    return sorted(APPS, key=lambda k: (bool(APPS[k].get("heavy")), APPS[k]["order"]))


def name_of(app: str) -> str:
    return (APPS.get(app) or {}).get("name") or app


def _load() -> list[dict]:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))["apps"]
    except (OSError, ValueError, KeyError) as e:
        raise RuntimeError(f"{FILE} is missing or broken ({e}); run shared/templates/render.py") from None


LIST = _load()
APPS = {m["key"]: m for m in LIST}                                    # key -> manifest, in order
PORTS = {k: m["port"] for k, m in APPS.items()}                         # key -> default port
FOLDERS = {k: m["folder"] for k, m in APPS.items() if m.get("folder")}  # key -> folder on the suite's one address
# kind of item -> {app, label, plural, href, id}
ITEMS = {it["kind"]: {"app": k, **{f: v for f, v in it.items() if f != "kind"}} for k, m in APPS.items() for it in m.get("items") or []}
NOTIFICATIONS = [{"app": k, **n} for k, m in APPS.items() for n in m.get("notifications") or []]
