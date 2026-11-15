"""The files every app of the suite keeps alike, made from the templates in this folder: setup.sh, run.sh and the app's
CI workflow (.github/workflows/<app>.yml). A template names the app with @@NAME@@ (iocalendar), @@LABEL@@
(ioCalendar), @@UP@@ (IOCALENDAR), @@DB@@ (its database and user: the app's name too) and @@PORT@@, all from the suite's list of apps
(APPS in iosuite_shared/install.py), and keeps room for what is the app's own in blocks:

    # >>> own: questions
    ...the app's own lines, read from the app's file as it stands...
    # <<< own: questions

A block the app's file does not have yet gets the template's lines (most are empty). Everything outside the blocks is
the template's: an edit there is lost at the next run, so it goes in the template (and then reaches every app).

    python3 shared/templates/render.py            write every such file
    python3 shared/templates/render.py --check    say which differ from their template, and fail when one does

update.sh has its own renderer (render-update.py), kept for its older "the app" block.
"""
import ast
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SIMPLE = ["iostart", "iocalendar", "iocontact", "iohealth", "iotask", "iodns", "iobackup", "iorecipe", "iothings", "iomoney"]
SETUP = SIMPLE + ["ionote"]
EVERY = SETUP + ["iopix"]
# template -> (the file it makes, relative to the repository, and the apps that have one made from it); ioPix keeps
# its own setup.sh (digiKam and the photo folders), ioNote and ioPix their own workflow (the web app's scripts)
KINDS = {
    "setup.sh": ("{app}/setup.sh", SETUP),
    "run.sh": ("{app}/run.sh", EVERY),
    "workflow.yml": (".github/workflows/{app}.yml", SIMPLE),
}
BLOCK = re.compile(r"^([ \t]*)# >>> own: (\S+)\n(.*?)^[ \t]*# <<< own: \2\n", re.M | re.S)


def apps() -> dict:
    """APPS of iosuite_shared/install.py, read without importing it: {name: {label, db, port, env, ...}}."""
    tree = ast.parse((HERE.parent / "iosuite_shared" / "install.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "APPS" for t in node.targets):
            return {ast.literal_eval(k): {kw.arg: ast.literal_eval(kw.value) for kw in v.keywords}
                    for k, v in zip(node.value.keys, node.value.values)}
    raise SystemExit("no APPS in iosuite_shared/install.py")


def own_blocks(text: str) -> dict:
    return {m.group(2): m.group(3) for m in BLOCK.finditer(text)}


def render(template: str, app: str, a: dict, current: str) -> str:
    mine = own_blocks(current)
    out = (template.replace("@@NAME@@", app).replace("@@LABEL@@", a["label"]).replace("@@UP@@", a["env"])
           .replace("@@DB@@", app).replace("@@PORT@@", str(a["port"])))
    return BLOCK.sub(lambda m: f"{m.group(1)}# >>> own: {m.group(2)}\n{mine.get(m.group(2), m.group(3))}{m.group(1)}# <<< own: {m.group(2)}\n", out)


def main() -> int:
    check, differ = "--check" in sys.argv[1:], []
    reg = apps()
    for name, (pattern, which) in KINDS.items():
        template = (HERE / name).read_text()
        for app in which:
            path = ROOT / pattern.format(app=app)
            current = path.read_text() if path.exists() else ""
            wanted = render(template, app, reg[app], current)
            if current == wanted:
                continue
            differ.append(str(path.relative_to(ROOT)))
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(wanted)
                if path.suffix == ".sh":
                    path.chmod(0o755)
    if differ:
        print(("differ from their template in shared/templates (run shared/templates/render.py): " if check else "written: ") + ", ".join(differ))
    return 1 if check and differ else 0


if __name__ == "__main__":
    sys.exit(main())
