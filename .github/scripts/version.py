"""The suite's version, set on main by itself (.github/workflows/version.yml runs this after every push to main).

A pull request leaves the version line alone (shared/iosuite_shared/__init__.py), so two of them never meet on it.
Once one is merged, this looks at what main got since the version last changed:

  * something that reaches an install (anything but the docs, the workflows and the top-level text files): the version
    goes up by one, in a commit of its own on main ("ioSuite 3.19.2: <the pull request's title>"). The last number by
    default; the middle one when a merged pull request carries the label `feature`, the first with `major`;
  * nothing of the kind, or a pull request that set the version itself: main stays as it is.

Either way, when main's version has no release yet, this says so (released=false in $GITHUB_OUTPUT, with the version,
the title and notes.md), and the workflow makes the release and starts the image builds.

    python3 .github/scripts/version.py            on main, in the workflow
    python3 .github/scripts/version.py --dry-run  say what it would do; nothing is committed or pushed
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION_FILE = "shared/iosuite_shared/__init__.py"
VERSION_RE = re.compile(r'^__version__ = "(\d+)\.(\d+)\.(\d+)"', re.M)
QUIET = ("docs/", ".github/")                     # folders no install has
QUIET_FILES = re.compile(r"^[^/]+\.md$|^LICENSE$|^\.[^/]+$")  # README.md, LICENSE, .gitignore at the top
LABELS = {"major": 0, "feature": 1}              # the label on a pull request -> the number that goes up
PR = re.compile(r"^Merge pull request #(\d+) |\(#(\d+)\)$")
TRIES = 5


def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"git {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def version_in(text: str) -> tuple:
    m = VERSION_RE.search(text)
    if not m:
        raise SystemExit(f"no version line in {VERSION_FILE}")
    return tuple(int(x) for x in m.groups())


def raised(v: tuple, part: int) -> tuple:
    """v with one number up and the ones after it at 0: part 2 is the last number, 1 the middle, 0 the first."""
    return tuple(n + 1 if i == part else (n if i < part else 0) for i, n in enumerate(v))


def reaches_installs(path: str) -> bool:
    return not (path.startswith(QUIET) or QUIET_FILES.match(path))


def last_change() -> str:
    """The commit on main that last changed the version: one made here, or the merge of a pull request that set it."""
    return git("log", "--first-parent", "-m", "-1", "--format=%H", "-G", r'^__version__ = "', "--", VERSION_FILE)


def entry(sha: str) -> dict:
    """One commit of main: {sha, title, number, reaches}. A merge commit carries the pull request's title as the first
    line of its body; a squashed one as its subject. reaches: it changed something an install has."""
    subject, body = git("log", "-1", "--format=%s", sha), git("log", "-1", "--format=%b", sha)
    m = PR.search(subject)
    title = body.splitlines()[0] if subject.startswith("Merge pull request") and body else subject
    # the number GitHub adds to a squash, the words of a commit made here, a version the title was written for
    title = re.sub(r"\s*\(#\d+\)$", "", title)
    title = re.sub(r"^ioSuite v?\d+\.\d+\.\d+: ", "", title)
    title = re.sub(r"\s*(?:-\s*|\()v?\d+\.\d+\.\d+\)?$", "", title).strip()
    paths = git("diff-tree", "--no-commit-id", "--name-only", "-r", "-m", "--first-parent", sha).splitlines()
    return {"sha": sha, "title": title, "number": int(m.group(1) or m.group(2)) if m else None,
            "reaches": any(reaches_installs(x) for x in paths)}


def merged_since(commit: str) -> list:
    """What main got after `commit`, newest first."""
    return [entry(sha) for sha in git("log", "--first-parent", "--format=%H", f"{commit}..HEAD").split()]


def labels_of(number: int) -> list:
    """The labels of a pull request, asked of GitHub with the workflow's token; none when it cannot be asked."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo or not number:
        return []
    r = subprocess.run(["gh", "api", f"repos/{repo}/issues/{number}/labels"], capture_output=True, text=True)
    try:
        return [x["name"].lower() for x in json.loads(r.stdout)] if r.returncode == 0 else []
    except (ValueError, TypeError, KeyError):
        return []


def part_for(merged: list, labels=labels_of) -> int:
    return min([LABELS[x] for m in merged for x in labels(m["number"]) if x in LABELS], default=2)


def plan(labels=labels_of) -> dict:
    """What main needs now: {version (as it is), new (the version to set, or None), title, merged}."""
    now, last = version_in((ROOT / VERSION_FILE).read_text()), last_change()
    merged = [m for m in merged_since(last) if m["reaches"]]
    new = raised(now, part_for(merged, labels)) if merged else None
    return {"version": now, "new": new, "title": merged[0]["title"] if merged else "", "merged": merged}


def write(v: tuple) -> None:
    f = ROOT / VERSION_FILE
    f.write_text(VERSION_RE.sub('__version__ = "%d.%d.%d"' % v, f.read_text(), count=1))


def notes(merged: list) -> str:
    """The release's notes: the message of every pull request it holds, newest first."""
    return "\n\n".join(git("log", "-1", "--format=%B", m["sha"]) for m in merged)


def released(v: str) -> bool:
    return subprocess.run(["gh", "release", "view", f"v{v}"], cwd=ROOT, capture_output=True).returncode == 0


def main() -> int:
    dry = "--dry-run" in sys.argv[1:]
    for _ in range(TRIES):
        if not dry:
            git("fetch", "-q", "origin", "main")
            git("checkout", "-q", "-B", "main", "FETCH_HEAD")
        p = plan()
        if not p["new"]:
            # nothing to raise: the release (when there is none yet) is of the commit that set this version
            p["merged"] = [entry(last_change())]
            p["title"] = p["merged"][0]["title"]
            break
        new = "%d.%d.%d" % p["new"]
        print(f"{'.'.join(map(str, p['version']))} -> {new}: {p['title']}")
        if dry:
            return 0
        write(p["new"])
        lines = "\n".join(f"- {m['title']}" + (f" (#{m['number']})" if m["number"] else "") for m in p["merged"])
        git("-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "-q", "-m", f"ioSuite {new}: {p['title']}\n\n{lines}", "--", VERSION_FILE)
        if subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=ROOT).returncode == 0:
            break
        print("main moved on meanwhile; looking again")  # another pull request was merged: start over on the new main
    else:
        raise SystemExit(f"could not push the version to main in {TRIES} tries")
    v = "%d.%d.%d" % version_in((ROOT / VERSION_FILE).read_text())
    if dry:
        print(f"main stays at {v}; were it not released yet, the release would be: {p['title']}")
        return 0
    done = released(v)
    print(f"main is at {v}" + (", released already" if done else ", not released yet"))
    (ROOT / "notes.md").write_text(notes(p["merged"]) + "\n")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"version={v}\nreleased={'true' if done else 'false'}\nbumped={'true' if p['new'] else 'false'}\n"
                    f"title={p['title']}\nsha={git('rev-parse', 'HEAD')}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
