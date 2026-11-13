#!/usr/bin/env python3
"""Hold what the site says about the apps to the apps' own code.

    python3 tools/check-facts.py

The pages here are written by hand, so this is what keeps them true. The apps are the folders beside docs/ in this
repository. It reads docs/ and landing/ and fails on:

  - a link to a file in this repository (raw.githubusercontent.com/.../iosuite/main/x,
    github.com/.../iosuite/blob|tree/main/x) that is not there;
  - a default port, next to an app's name, that is not the one in the shared library's list of apps
    (shared/iosuite_shared/install.py, APPS);
  - a Proxmox container size in docs/start/proxmox.md that is not the app's ct script default (var_cpu, var_ram,
    var_disk);
  - an image ghcr.io/avandeputte/<app> that the app's docker-compose.yml does not use.

The docs workflow runs it whenever a page or an app changes, so a change in an app that makes a page wrong fails in
the same pull request.
"""
import ast
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
SRC = HERE.parent
OWNER = "avandeputte"
REPO = "iosuite"
LABELS = {"ioPix": "iopix", "ioNote": "ionote", "ioCalendar": "iocalendar", "ioStart": "iostart", "ioContact": "iocontact",
          "ioHealth": "iohealth", "ioTask": "iotask", "ioRecipe": "iorecipe", "ioDNS": "iodns", "ioBackup": "iobackup"}

problems = []


def pages():
    for p in sorted((HERE / "docs").rglob("*.md")) + sorted((HERE / "landing").glob("*.html")):
        yield p, p.read_text()


def app_ports(src):
    """shared/iosuite_shared/install.py's APPS, read without importing it."""
    tree = ast.parse((src / "shared" / "iosuite_shared" / "install.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "APPS" for t in node.targets):
            apps = {}
            for k, v in zip(node.value.keys, node.value.values):
                kw = {x.arg: x.value for x in v.keywords}
                apps[k.value] = ast.literal_eval(kw["port"])
            return apps
    raise SystemExit("no APPS in iosuite_shared/install.py")


def main():
    src = SRC
    if True:
        checked = 0
        # 1. links into the repository
        link = re.compile(r"https://(?:raw\.githubusercontent\.com/%s/([\w.-]+)/main/|github\.com/%s/([\w.-]+)/(?:blob|tree)/main/)([^\s\"')<>`#?]+)" % (OWNER, OWNER))
        for p, text in pages():
            for m in link.finditer(text):
                repo, path = m.group(1) or m.group(2), m.group(3).rstrip(".,")
                if repo != REPO:
                    continue
                checked += 1
                if not (src / path).exists():
                    problems.append(f"{p.relative_to(HERE)}: {path} is not in the repository")

        # 2. default ports next to an app's name
        ports = app_ports(src)
        near = re.compile(r"\b(ioPix|ioNote|ioCalendar|ioStart|ioContact|ioHealth|ioTask|ioRecipe|ioDNS|ioBackup)\b(?:[^\n\d]{0,14}?)\b(8\d\d0)\b")
        js = re.compile(r'name:"(io\w+)",\s*port:(\d+)')
        for p, text in pages():
            for m in list(near.finditer(text)) + list(js.finditer(text)):
                app, port = LABELS.get(m.group(1)), int(m.group(2))
                if not app:
                    continue
                checked += 1
                if ports.get(app) != port:
                    problems.append(f"{p.relative_to(HERE)}: {m.group(1)} on {port}, but its default port is {ports.get(app)}")
        for app, port in ports.items():
            if not any(str(port) in t for _, t in pages()):
                problems.append(f"{app}'s port {port} is not mentioned anywhere")

        # 3. Proxmox container sizes
        size = re.compile(r"^\| (io\w+) \| `bash -c .*\| (\d+) CPU, (\d+) (GB|MB), (\d+) GB \|$", re.M)
        text = (HERE / "docs" / "start" / "proxmox.md").read_text()
        for m in size.finditer(text):
            app = LABELS[m.group(1)]
            ct = (src / app / "proxmox" / "ct" / f"{app}.sh").read_text()
            var = {k: int(re.search(r'var_%s="\$\{var_%s:-(\d+)\}"' % (k, k), ct).group(1)) for k in ("cpu", "ram", "disk")}
            ram = int(m.group(3)) * (1024 if m.group(4) == "GB" else 1)
            checked += 1
            if (int(m.group(2)), ram, int(m.group(5))) != (var["cpu"], var["ram"], var["disk"]):
                problems.append(f"docs/start/proxmox.md: {m.group(1)} {m.group(2)} CPU, {m.group(3)} {m.group(4)}, {m.group(5)} GB; "
                                f"its ct script says {var['cpu']} CPU, {var['ram']} MB, {var['disk']} GB")

        # 4. images
        for p, text in pages():
            for m in re.finditer(r"ghcr\.io/%s/([\w-]+)" % OWNER, text):
                app = m.group(1)
                compose = src / app / "docker-compose.yml"
                checked += 1
                if not compose.exists() or f"ghcr.io/{OWNER}/{app}" not in compose.read_text():
                    problems.append(f"{p.relative_to(HERE)}: ghcr.io/{OWNER}/{app} is not the image in {app}/docker-compose.yml")

        print(f"checked {checked} claims about the apps against their code")
        if problems:
            print(f"\n{len(problems)} wrong:")
            for x in dict.fromkeys(problems):
                print("  - " + x)
            sys.exit(1)
        print("every checked claim holds")


if __name__ == "__main__":
    main()
