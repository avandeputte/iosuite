"""update.sh of every app, made from templates/update.sh: only the block "the app" (NAME, LABEL, ITEMS, groups,
after_install) is the app's own, and it is read from the app's update.sh as it stands.

    python3 shared/templates/render-update.py            write <app>/update.sh for every app folder of the repository
    python3 shared/templates/render-update.py --check    say which differ from the template, and fail when one does
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
TEMPLATE = (HERE / "update.sh").read_text()


def render(current: str) -> str:
    name = re.search(r"^NAME=(\S+)$", current, re.M).group(1)
    label = re.search(r"^LABEL=(\S+)$", current, re.M).group(1)
    items = re.search(r'^ITEMS="([^"]*)"$', current, re.M).group(1)
    groups = re.search(r"^groups\(\) \{\n(.*?)\n\}$", current, re.M | re.S).group(1)
    after = re.search(r"^after_install\(\) \{\n(.*?)\n\}$", current, re.M | re.S).group(1)
    return (TEMPLATE.replace("@@NAME@@", name).replace("@@LABEL@@", label).replace("@@UP@@", name.upper())
            .replace("@@ITEMS@@", items).replace("@@GROUPS@@", groups).replace("@@AFTER@@", after))


def main() -> int:
    check, differ = "--check" in sys.argv[1:], []
    for path in sorted(ROOT.glob("*/update.sh")):
        current = path.read_text()
        wanted = render(current)
        if current == wanted:
            continue
        differ.append(path.parent.name)
        if not check:
            path.write_text(wanted)
            path.chmod(0o755)
    if differ:
        print(("differ from shared/templates/update.sh (run shared/templates/render-update.py): " if check else "written: ") + ", ".join(differ))
    return 1 if check and differ else 0


if __name__ == "__main__":
    sys.exit(main())
