"""Do the workflow files still read? GitHub refuses a workflow file that is not YAML or names a key twice, and says so
nowhere on the pull request: the workflow's checks just do not appear, every push after it sends a failure message,
and on main nothing of that app is tested or built. This reads every file in .github/workflows the way GitHub does and
fails on the first kind of thing it refuses.

    python3 .github/scripts/workflows.py
"""
import sys
from pathlib import Path

import yaml

FOLDER = Path(__file__).resolve().parent.parent / "workflows"


class Loader(yaml.SafeLoader):
    """SafeLoader, but a key named twice in one mapping is an error (PyYAML keeps the last one without a word)."""


def _mapping(loader, node, deep=False):
    seen = {}
    for key, _ in node.value:
        name = loader.construct_object(key, deep=deep)
        if name in seen:
            raise yaml.constructor.ConstructorError(
                None, None, f"'{name}' is there twice (first on line {seen[name]})", key.start_mark)
        seen[name] = key.start_mark.line + 1
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def problems(path: Path) -> list[str]:
    try:
        doc = yaml.load(path.read_text(), Loader)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f"line {mark.line + 1}: " if mark else ""
        return [where + (getattr(e, "problem", None) or str(e))]
    if not isinstance(doc, dict):
        return ["not a workflow: no keys"]
    out = []
    if "on" not in doc and True not in doc:  # YAML 1.1 reads a bare `on` as true
        out.append("no `on:`")
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        out.append("no `jobs:`")
    else:
        for name, job in jobs.items():
            if not isinstance(job, dict) or not ("uses" in job or ("runs-on" in job and job.get("steps"))):
                out.append(f"job `{name}` has no `runs-on:` and `steps:` (or `uses:`)")
    return out


def main() -> int:
    bad = 0
    for path in sorted([*FOLDER.glob("*.yml"), *FOLDER.glob("*.yaml")]):
        for p in problems(path):
            bad += 1
            print(f"::error file=.github/workflows/{path.name}::{path.name}: {p}")
    if not bad:
        print("Every workflow file reads.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
