"""Updating the viewer itself: which commit is installed, whether GitHub's main branch is
newer, and running update.sh (next to setup.sh) from Maintenance. Docker installs are
updated by pulling the image, so there the check only reports."""
import json
import os
import subprocess
import threading
import time
import urllib.request

from . import config

REPO = os.environ.get("DIGIKAM_VIEWER_REPO", "avandeputte/digikam-viewer")
BRANCH = os.environ.get("DIGIKAM_VIEWER_BRANCH", "main")
progress = {"running": False, "log": "", "error": None, "finished": None}
_checked = {}


def in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def local_commit() -> str:
    git = config.APP_DIR / ".git"
    if git.exists():
        try:
            return subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(config.APP_DIR), capture_output=True, text=True, timeout=10).stdout.strip() or "unknown"
        except (OSError, subprocess.SubprocessError):
            return "unknown"
    try:
        return (config.APP_DIR / "COMMIT").read_text().strip() or "unknown"
    except OSError:
        return "unknown"


def _fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "digikam-viewer"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def check() -> dict:
    """{installed, remote, remoteDate, remoteMessage, status: current|update|error}"""
    out = {"installed": local_commit()[:7], "checked": int(time.time())}
    try:
        c = _fetch(f"https://api.github.com/repos/{REPO}/commits/{BRANCH}")
        out.update(remote=c["sha"][:7], remoteDate=c["commit"]["committer"]["date"][:10], remoteMessage=c["commit"]["message"].splitlines()[0][:100])
        out["status"] = "current" if c["sha"].startswith(local_commit()) and local_commit() != "unknown" else "update"
    except Exception as e:
        out.update(status="error", error=str(e)[:160])
    _checked.clear(); _checked.update(out)
    return out


def status() -> dict:
    return {"installed": local_commit()[:7], "docker": in_docker(), "canRun": (config.APP_DIR / "update.sh").exists() and not in_docker(),
            "check": dict(_checked) if _checked else None, "progress": dict(progress)}


def run():
    """update.sh in a child process; the service manager restarts the viewer when it finishes."""
    if in_docker():
        raise RuntimeError("In Docker, update by pulling the image: docker compose pull && docker compose up -d")
    if progress["running"]:
        raise RuntimeError("An update is already running")
    progress.update(running=True, log="", error=None, finished=None)

    def work():
        try:
            res = subprocess.run(["sh", str(config.APP_DIR / "update.sh")], cwd=str(config.APP_DIR), capture_output=True, text=True, timeout=1800)
            progress["log"] = (res.stdout + res.stderr)[-3000:]
            if res.returncode != 0:
                progress["error"] = (res.stderr or res.stdout).strip().splitlines()[-1][:300] if (res.stderr or res.stdout).strip() else f"exit {res.returncode}"
        except Exception as e:
            progress["error"] = str(e)[:300]
        finally:
            progress.update(running=False, finished=int(time.time()))
            _checked.clear()

    threading.Thread(target=work, name="self-update", daemon=True).start()
