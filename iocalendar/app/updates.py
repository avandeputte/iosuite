"""Updating ioCalendar itself: which commit is installed, whether GitHub's main branch has a newer version, and running
update.sh from Settings › Server (or the MCP update_server tool). Docker installs are updated by pulling the image, so
there the check only reports. The same design as iopix."""
import json
import os
import re
import subprocess
import threading
import time
import urllib.request

from app import APP_VERSION, config, db

ROOT = config.ROOT
RESULT_FILE = ROOT / ".update-result"  # update.sh writes its outcome here before the restart ends this process
DAILY = 24 * 3600

_run_lock = threading.Lock()
_checked: dict = {}
_commit = None
progress: dict = {"running": False, "error": None, "log": "", "started": None, "finished": None}


def forget_check() -> None:
    _checked.clear()


def in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def local_commit() -> str:
    """The installed commit (cached: it only changes through update.sh, which restarts the process)."""
    global _commit
    if _commit is None:
        found = _read_commit()
        if found == "unknown":
            return found
        _commit = found
    return _commit


def _read_commit() -> str:
    if (ROOT / ".git").exists():
        try:
            return subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True,
                                  timeout=10).stdout.strip() or "unknown"
        except (OSError, subprocess.SubprocessError):
            return "unknown"
    try:
        return (ROOT / "COMMIT").read_text().strip() or "unknown"
    except OSError:
        return "unknown"


def auto_check_enabled() -> bool:
    """Settings › Server › Check for updates daily: on unless switched off (UPDATE_CHECK=0 locks it off)."""
    if config.UPDATE_CHECK_LOCKED:
        return False
    try:
        return (db.get_setting("update_check", "1") or "1") == "1"
    except Exception:  # noqa: BLE001  the database is away: no check
        return False


def _get(url: str, accept: str = "application/vnd.github+json"):
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "iocalendar"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read()


def _remote_app_version(sha: str) -> str | None:
    """APP_VERSION at that commit, so a commit that only changes the docs or the workflow is not announced as new."""
    text = _get(f"https://raw.githubusercontent.com/{config.REPO}/{sha}/app/__init__.py", "text/plain").decode("utf-8", "replace")
    m = re.search(r'^APP_VERSION = "([^"]+)"', text, re.M)
    return m.group(1) if m else None


def _ver(v: str) -> tuple:
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.+-]", v or "0")[:3])


def check() -> dict:
    """{installed, version, remote, remoteDate, remoteMessage, remoteVersion, status: current | update | error, checked}"""
    mine = local_commit()
    out = {"installed": mine[:7], "version": APP_VERSION, "checked": int(time.time())}
    try:
        c = json.loads(_get(f"https://api.github.com/repos/{config.REPO}/commits/{config.BRANCH}"))
        out.update(remote=c["sha"][:7], remoteDate=c["commit"]["committer"]["date"][:10],
                   remoteMessage=c["commit"]["message"].splitlines()[0][:120])
        if mine != "unknown" and c["sha"].startswith(mine):
            out["status"] = "current"
        else:
            try:
                rv = _remote_app_version(c["sha"])
            except Exception:  # noqa: BLE001
                rv = None
            out["remoteVersion"] = rv
            # a newer build is one with a higher app version; the same version under another commit (docs, the
            # workflow) is nothing to install, and an older one means this install is ahead of main
            out["status"] = "update" if rv is None or _ver(rv) > _ver(APP_VERSION) else "current"
    except Exception as e:  # noqa: BLE001
        out.update(status="error", error=str(e)[:160])
    _checked.clear()
    _checked.update(out)
    return out


def available() -> dict | None:
    """What the banner needs, from the last check: {version, remote, message, date}, or None."""
    c = dict(_checked)
    if c.get("status") != "update":
        return None
    return {"remote": c.get("remote"), "version": c.get("remoteVersion"), "message": c.get("remoteMessage"), "date": c.get("remoteDate")}


def start_daily() -> None:
    """Ask GitHub once a day (the first time a minute after start) whether main has moved on, while the setting is on.
    Only the public commit is fetched; nothing about this install is sent."""
    def loop():
        time.sleep(60)
        while True:
            try:
                if auto_check_enabled():
                    check()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(DAILY)
    threading.Thread(target=loop, name="update-check", daemon=True).start()


def last_result() -> dict | None:
    """The outcome of the last update.sh run, from the file it writes before the restart: {ok, text, at}."""
    try:
        text = RESULT_FILE.read_text().strip()
    except OSError:
        return None
    if not text:
        return None
    return {"ok": text.startswith("ok:"), "text": text.split(":", 1)[-1].strip()[:300], "at": int(RESULT_FILE.stat().st_mtime)}


def _writable() -> bool:
    paths = [ROOT] + [p for p in (ROOT / ".venv", ROOT / ".git") if p.exists()]
    return all(os.access(str(p), os.W_OK) for p in paths)


def can_run() -> bool:
    return (ROOT / "update.sh").exists() and (ROOT / ".venv").exists() and not in_docker() and _writable()


def status() -> dict:
    return {"version": APP_VERSION, "installed": local_commit()[:7], "docker": in_docker(), "canRun": can_run(),
            "repo": config.REPO, "branch": config.BRANCH, "check": dict(_checked) or None, "progress": dict(progress),
            "lastUpdate": last_result(), "autoCheck": auto_check_enabled(), "autoCheckLocked": config.UPDATE_CHECK_LOCKED}


def run(ref: str = "") -> None:
    """update.sh in a child process; the service manager starts ioCalendar again when it finishes.
    ref: a commit or branch to install instead of the tip of main."""
    if in_docker():
        raise RuntimeError("In Docker, update by pulling the image: docker compose pull && docker compose up -d")
    if not can_run():
        raise RuntimeError("This install cannot update itself (no update.sh or .venv next to the app, or the folder is not writable "
                           "by the service). Run ./update.sh in the app folder.")
    ref = (ref or "").strip()[:80]
    if ref and not re.fullmatch(r"[0-9a-f]{7,40}|[A-Za-z0-9][A-Za-z0-9._-]*", ref):
        raise RuntimeError("ref must be a commit id or a branch name")
    with _run_lock:
        if progress["running"]:
            raise RuntimeError("An update is already running")
        progress.update(running=True, error=None, log="", started=int(time.time()), finished=None)
    env = dict(os.environ, IOCALENDAR_RESULT=str(RESULT_FILE), IOCALENDAR_REPO=config.REPO, IOCALENDAR_BRANCH=config.BRANCH)
    if ref:
        env["IOCALENDAR_REF"] = ref
    try:
        RESULT_FILE.unlink()
    except OSError:
        pass

    def work():
        try:
            res = subprocess.run(["sh", str(ROOT / "update.sh")], cwd=str(ROOT), capture_output=True, text=True, timeout=1800, env=env)
            progress["log"] = (res.stdout + res.stderr)[-3000:]
            if res.returncode != 0:
                tail = re.sub(r"\x1b\[[0-9;]*m", "", (res.stderr or res.stdout)).strip()
                progress["error"] = tail.splitlines()[-1] if tail else f"exit {res.returncode}"
            elif os.environ.get("INVOCATION_ID") and "updated to" in (last_result() or {}).get("text", ""):
                # still running after a successful update: the service could not be restarted from here (it runs as
                # an account without sudo), so this process ends and systemd (Restart=always) starts the new version
                threading.Timer(1.5, lambda: os._exit(0)).start()
        except Exception as e:  # noqa: BLE001
            progress["error"] = str(e)[:300]
        finally:
            progress.update(running=False, finished=int(time.time()))
            _checked.clear()

    threading.Thread(target=work, name="self-update", daemon=True).start()
