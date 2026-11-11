#!/usr/bin/env python3
"""Hold what the site says about the apps to the apps' own code.

    python3 tools/check-facts.py            # shallow-clones every app repository
    python3 tools/check-facts.py ../src     # or uses checkouts in ../src/<repo>

The pages here are written by hand, so this is what keeps them true. It reads
docs/ and landing/ and fails on:

  - a link to a file in an app repository (raw.githubusercontent.com/.../main/x,
    github.com/.../blob|tree/main/x) that is not in that repository's main;
  - a default port, next to an app's name, that is not the one in
    iosuite-shared's list of apps (iosuite_shared/install.py, APPS);
  - a Proxmox container size in docs/start/proxmox.md that is not the app's
    ct script default (var_cpu, var_ram, var_disk);
  - an image ghcr.io/avandeputte/<app> that the app's docker-compose.yml does
    not use.

The workflow runs it on every build and nightly, so a change in an app that
makes a page wrong fails the build here instead of shipping.
"""
import ast
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent.parent
OWNER = "avandeputte"
REPOS = ["iosuite-shared", "iopix", "ionote", "iocalendar", "iocontact", "iohealth", "iosuite", "iotask", "iorecipe",
         "ionote-apps", "iohealth-apps"]
LABELS = {"ioPix": "iopix", "ioNote": "ionote", "ioCalendar": "iocalendar", "ioSuite": "iosuite",
          "ioContact": "iocontact", "ioHealth": "iohealth", "ioTask": "iotask", "ioRecipe": "iorecipe"}

problems = []


def sources():
    if len(sys.argv) > 1:
        return pathlib.Path(sys.argv[1]).resolve(), None
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="iosuite-src-"))
    for r in REPOS:
        subprocess.run(["git", "clone", "-q", "--depth", "1", f"https://github.com/{OWNER}/{r}", str(tmp / r)], check=True)
    return tmp, tmp


def pages():
    for p in sorted((HERE / "docs").rglob("*.md")) + sorted((HERE / "landing").glob("*.html")):
        yield p, p.read_text()


def app_ports(src):
    """iosuite_shared/install.py's APPS, read without importing it."""
    tree = ast.parse((src / "iosuite-shared" / "iosuite_shared" / "install.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "APPS" for t in node.targets):
            apps = {}
            for k, v in zip(node.value.keys, node.value.values):
                kw = {x.arg: x.value for x in v.keywords}
                apps[k.value] = ast.literal_eval(kw["port"])
            return apps
    raise SystemExit("no APPS in iosuite_shared/install.py")


def main():
    src, tmp = sources()
    try:
        checked = 0
        # 1. links into the app repositories
        link = re.compile(r"https://(?:raw\.githubusercontent\.com/%s/([\w.-]+)/main/|github\.com/%s/([\w.-]+)/(?:blob|tree)/main/)([^\s\"')<>`#?]+)" % (OWNER, OWNER))
        for p, text in pages():
            for m in link.finditer(text):
                repo, path = m.group(1) or m.group(2), m.group(3).rstrip(".,")
                if repo not in REPOS:
                    continue
                checked += 1
                if not (src / repo / path).exists():
                    problems.append(f"{p.relative_to(HERE)}: {repo}/{path} is not in {repo}'s main")

        # 2. default ports next to an app's name
        ports = app_ports(src)
        near = re.compile(r"\b(ioPix|ioNote|ioCalendar|ioSuite|ioContact|ioHealth)\b(?:[^\n\d]{0,14}?)\b(8\d\d0)\b")
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
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
