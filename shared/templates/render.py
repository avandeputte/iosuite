"""Everything made from the apps' manifests (<app>/app.json, see iosuite_shared/catalog.py):

  * shared/iosuite_shared/apps.json, the manifests gathered, which the shared library reads (every install carries it);
  * the lists of apps between "suite:" marks in other files (install.sh, every Proxmox script, the Docker Compose
    builder), written whole from the manifests:

        # >>> suite: also
        ...made here; an edit is lost at the next run...
        # <<< suite: also

  * the files every app of the suite keeps alike, made from the templates in this folder: setup.sh, run.sh and the
    app's CI workflow (.github/workflows/<app>.yml).

A template names the app with @@NAME@@ (iocalendar), @@LABEL@@ (ioCalendar), @@UP@@ (IOCALENDAR), @@DB@@ (its database
and user: the app's name too) and @@PORT@@, from its manifest, and keeps room for what is the app's own in blocks:

    # >>> own: questions
    ...the app's own lines, read from the app's file as it stands...
    # <<< own: questions

A block the app's file does not have yet gets the template's lines (most are empty). Everything outside the blocks is
the template's: an edit there is lost at the next run, so it goes in the template (and then reaches every app).

    python3 shared/templates/render.py            write every such file
    python3 shared/templates/render.py --check    say which differ from the manifests and templates, and fail when one does

update.sh has its own renderer (render-update.py), kept for its older "the app" block.
"""
import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
# iosuite_shared/catalog.py on its own (the package's other modules need its dependencies; this needs none of them)
_spec = importlib.util.spec_from_file_location("catalog", HERE.parent / "iosuite_shared" / "catalog.py")
catalog = importlib.util.module_from_spec(_spec)
try:
    _spec.loader.exec_module(catalog)
except RuntimeError:  # no apps.json yet: it is about to be written
    pass
BLOCK = re.compile(r"^([ \t]*)# >>> own: (\S+)\n(.*?)^[ \t]*# <<< own: \2\n", re.M | re.S)
MADE = re.compile(r"^([ \t]*)(#|//) >>> suite: (\S+)([^\n]*)\n(.*?)^[ \t]*\2 <<< suite: \3\n", re.M | re.S)


def kinds(apps: list[dict]) -> dict:
    """template -> (the file it makes, relative to the repository, and the apps that have one made from it); an app
    whose manifest says keepsOwn keeps its own (ioPix its setup.sh: digiKam and the photo folders; ioNote and ioPix
    their workflow: the web app's scripts)."""
    def having(own):
        return [m["key"] for m in apps if own not in (m.get("keepsOwn") or [])]
    return {"setup.sh": ("{app}/setup.sh", having("setup")),
            "run.sh": ("{app}/run.sh", [m["key"] for m in apps]),
            "workflow.yml": (".github/workflows/{app}.yml", having("workflow"))}


def install_order(apps: list[dict]) -> list[dict]:
    return sorted(apps, key=lambda m: (bool(m.get("heavy")), m["order"]))


def made(apps: list[dict], app: str | None) -> dict:
    """The lists between "suite:" marks: name -> lines (without the marks), for the file of `app` (a Proxmox script) or
    of the whole repository (None)."""
    order = install_order(apps)
    out = {"apps": [f'APPS="{" ".join(m["key"] for m in order)}"']}
    out["apps-js"] = None  # the Docker Compose builder's: see js_lists
    out["ports"] = ['  case "$a" in ' + " ".join(f"{m['key']}) p={m['port']};;" for m in order) + ' *) p="";; esac']
    if app:
        up = catalog.env_of(app)
        mine = [m for m in order if m["key"] != app and (app == "iopix" or not m.get("heavy"))]
        n = len(mine)
        why = "" if app == "iopix" else " (ioPix has its own script: photo mounts)"
        lines = [f'  if [[ -z "${{{up}_ALSO+x}}" ]]; then  # the other apps of the suite in the same container{why}',
                 f'    {up}_ALSO=$(whiptail --backtitle "$bt" --checklist "Also install in this container (same database server, each app its own '
                 f'database; same accounts and admin; each on its usual port):" {n + 10} 78 {n} \\']
        for i, m in enumerate(mine):
            name = m["name"] + (f" ({m['aside']})" if m.get("aside") else "")
            port = ", ".join(x for x in (str(m["port"]), m.get("otherPorts"), "admin tool" if m.get("adminTool") else None) if x)
            end = " 3>&1 1>&2 2>&3) || exit 1" if i == n - 1 else " \\"
            lines.append(f'      {m["key"]} "{name}  ({port})" OFF{end}')
        lines += [f"    {up}_ALSO=$(echo \"${up}_ALSO\" | tr -d '\"' | tr ' ' ',')", "  fi"]
        out["also"] = lines
    return out


def js_lists(apps: list[dict]) -> dict:
    """The Docker Compose builder's lists (docs/landing/compose/compose.js)."""
    rows = []
    for i, m in enumerate(apps):
        c = m.get("compose") or {}
        row = (f'    {{key:"{m["key"]}", name:"{m["name"]}", port:{m["port"]}, folder:"{m.get("folder") or ""}", '
               f'sub:"{c.get("name") or m["key"]}", what:"{c.get("what") or m["description"].lower()}"' + (", tool:true" if m.get("adminTool") else "") + "}")
        rows.append(row + ("," if i < len(apps) - 1 else ""))
    first = [m["key"] for m in install_order(apps)]
    return {"apps": ["  var APPS = ["] + rows + ["  ];"],
            "setup-first": ["  var SETUP_FIRST = [" + ", ".join(f'"{k}"' for k in first) + "];  // the smaller images first"]}


def fill(text: str, lists: dict, path: Path) -> str:
    def one(m):
        ind, mark, name, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        if name not in lists or lists[name] is None:
            raise SystemExit(f"{path}: no list called {name!r} to put between its suite: marks")
        body = "".join(line + "\n" for line in lists[name])
        return f"{ind}{mark} >>> suite: {name}{rest}\n{body}{ind}{mark} <<< suite: {name}\n"
    return MADE.sub(one, text)


def own_blocks(text: str) -> dict:
    return {m.group(2): m.group(3) for m in BLOCK.finditer(text)}


def render(template: str, app: str, a: dict, current: str) -> str:
    mine = own_blocks(current)
    out = (template.replace("@@NAME@@", app).replace("@@LABEL@@", a["label"]).replace("@@UP@@", a["env"])
           .replace("@@DB@@", app).replace("@@PORT@@", str(a["port"])))
    return BLOCK.sub(lambda m: f"{m.group(1)}# >>> own: {m.group(2)}\n{mine.get(m.group(2), m.group(3))}{m.group(1)}# <<< own: {m.group(2)}\n", out)


def main() -> int:
    check, differ = "--check" in sys.argv[1:], []
    apps = catalog.gather(ROOT)

    def put(path: Path, wanted: str):
        current = path.read_text() if path.exists() else ""
        if current == wanted:
            return
        differ.append(str(path.relative_to(ROOT)))
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(wanted)
            if path.suffix == ".sh":
                path.chmod(0o755)

    put(HERE.parent / "iosuite_shared" / "apps.json", catalog.dumps(apps))
    # the lists between suite: marks
    put(ROOT / "install.sh", fill((ROOT / "install.sh").read_text(), made(apps, None), ROOT / "install.sh"))
    compose = ROOT / "docs" / "landing" / "compose" / "compose.js"
    put(compose, fill(compose.read_text(), js_lists(apps), compose))
    for m in apps:
        ct = ROOT / m["key"] / "proxmox" / "ct" / f"{m['key']}.sh"
        if ct.exists():
            put(ct, fill(ct.read_text(), made(apps, m["key"]), ct))
    # the files kept alike
    reg = {m["key"]: {"label": m["name"], "env": catalog.env_of(m["key"]), "port": m["port"]} for m in apps}
    for name, (pattern, which) in kinds(apps).items():
        template = (HERE / name).read_text()
        for app in which:
            path = ROOT / pattern.format(app=app)
            current = path.read_text() if path.exists() else ""
            put(path, render(template, app, reg[app], current))
    if differ:
        print(("not as the manifests and templates in shared/templates say (run shared/templates/render.py): " if check else "written: ")
              + ", ".join(differ))
    return 1 if check and differ else 0


if __name__ == "__main__":
    sys.exit(main())
