"""The downloadable models and data the viewer uses, in one place: what is
installed (and which revision), whether the source has changed since, and
re-downloading from Settings.

"Changed since" is answered per source. Hugging Face repositories have a
commit id; the one on disk is in the cache's refs/main and the hub's API
gives the current one. Plain downloads (YOLOX, GeoNames) are compared by
Last-Modified. The OCR package is compared with PyPI. None of this can say
whether a *different, better* model exists; the page link on each row is
where to look for that.

Downloads run in a child process with HF_HUB_OFFLINE=0 (the server itself
never talks to the model hub), one at a time. Afterwards the in-process
model objects are dropped so the next use loads the new files.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from importlib.metadata import PackageNotFoundError, version as package_version

from . import config

MODEL_DIR = config.DATA_DIR / "models"
RECORD = MODEL_DIR / "downloads.json"

REGISTRY = {
    "clip": {"label": "CLIP ViT-B/32", "kind": "hf", "repos": ["Qdrant/clip-ViT-B-32-vision", "Qdrant/clip-ViT-B-32-text"],
             "page": "https://huggingface.co/Qdrant/clip-ViT-B-32-vision", "what": "Content search and “Detected content” (the original search model).",
             "size": "~600 MB"},
    "siglip2": {"label": "SigLIP 2 base", "kind": "hf", "repos": ["onnx-community/siglip2-base-patch16-224-ONNX"],
                "page": "https://huggingface.co/onnx-community/siglip2-base-patch16-224-ONNX", "what": "Content search (the current search model).",
                "size": "~1.5 GB"},
    "blip": {"label": "BLIP base (captions)", "kind": "hf", "repos": ["Salesforce/blip-image-captioning-base"],
             "page": "https://huggingface.co/Salesforce/blip-image-captioning-base", "what": "Photo descriptions.", "size": "~950 MB"},
    "yolox": {"label": "YOLOX-S", "kind": "url", "url": "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s.onnx",
              "page": "https://github.com/Megvii-BaseDetection/YOLOX/releases", "what": "Object detection (people, balls, animals, vehicles…).", "size": "35 MB"},
    "sface": {"label": "SFace (face grouping)", "kind": "url", "url": "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
              "page": "https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface", "what": "Groups look-alike unnamed faces on the Faces page and suggests who they are, for one-click naming.", "size": "37 MB"},
    "geonames": {"label": "GeoNames places", "kind": "data", "url": "https://download.geonames.org/export/dump/cities1000.zip",
                 "page": "https://download.geonames.org/export/dump/", "what": "Offline reverse geocoding: town, region and country for each GPS position. GeoNames regenerates this export daily.",
                 "size": "~30 MB"},
    "ocr": {"label": "RapidOCR", "kind": "pip", "package": "rapidocr", "page": "https://pypi.org/project/rapidocr/",
            "what": "Text in photos (signs, jerseys, documents).", "size": "~60 MB"},
}

progress = {"running": None, "error": None, "finished": None, "log": ""}
_checked = {}
_lock = threading.Lock()


# --------------------------------------------------------------------------
# what is on disk
# --------------------------------------------------------------------------

def _record() -> dict:
    try:
        return json.loads(RECORD.read_text())
    except (OSError, ValueError):
        return {}


def _remember(key: str, revision):
    rec = _record()
    rec[key] = {"at": int(time.time()), "revision": revision}
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps(rec, indent=1))


def _hf_local(repo: str):
    """(commit id, downloaded time) of a cached repository, or (None, None)."""
    ref = MODEL_DIR / f"models--{repo.replace('/', '--')}" / "refs" / "main"
    try:
        sha = ref.read_text().strip()
        if not any((ref.parent.parent / "snapshots" / sha).iterdir()):
            return None, None
        return sha, int(ref.stat().st_mtime)
    except OSError:
        return None, None


def local(key: str) -> dict:
    """{installed, revision, at}: revision is a commit id, a date or a version."""
    m = REGISTRY[key]
    if m["kind"] == "hf":
        shas, ats = [], []
        for repo in m["repos"]:
            sha, at = _hf_local(repo)
            if sha is None:
                return {"installed": False}
            shas.append(sha[:7]); ats.append(at)
        return {"installed": True, "revision": "+".join(shas), "at": max(ats)}
    if m["kind"] in ("url", "data"):
        from . import detector, facevecs, places
        paths = [detector.MODEL] if key == "yolox" else [facevecs.MODEL] if key == "sface" else [places.DIR / f for f in places.FILES]
        if not all(p.exists() for p in paths):
            return {"installed": False}
        at = int(max(p.stat().st_mtime for p in paths))
        return {"installed": True, "revision": datetime.fromtimestamp(at).strftime("%Y-%m-%d"), "at": at}
    if m["kind"] == "pip":
        try:
            return {"installed": True, "revision": package_version(m["package"]), "at": _record().get(key, {}).get("at")}
        except PackageNotFoundError:
            return {"installed": False}
    return {"installed": False}


# --------------------------------------------------------------------------
# what the source has now
# --------------------------------------------------------------------------

def _get(url: str, head: bool = False):
    req = urllib.request.Request(url, method="HEAD" if head else "GET", headers={"User-Agent": "digikam-viewer"})
    return urllib.request.urlopen(req, timeout=20)


def check(key: str) -> dict:
    """Ask the source for its current revision and compare with what is installed."""
    m, loc = REGISTRY[key], local(key)
    out = {"key": key, "checked": int(time.time()), "status": "unknown", "remote": None}
    try:
        if m["kind"] == "hf":
            remote, changed = [], False
            for repo in m["repos"]:
                with _get(f"https://huggingface.co/api/models/{repo}") as r:
                    info = json.load(r)
                sha = info.get("sha", "")
                remote.append(sha[:7])
                mine, _ = _hf_local(repo)
                changed |= bool(mine) and sha != mine
                out["remote_at"] = info.get("lastModified")
            out["remote"] = "+".join(remote)
            out["status"] = "missing" if not loc["installed"] else ("update" if changed else "current")
        elif m["kind"] in ("url", "data"):
            with _get(m["url"], head=True) as r:
                lm = r.headers.get("Last-Modified")
            if lm:
                t = parsedate_to_datetime(lm)
                out["remote"] = t.astimezone(timezone.utc).strftime("%Y-%m-%d")
                out["remote_at"] = t.isoformat()
                if not loc["installed"]:
                    out["status"] = "missing"
                elif m["kind"] == "data":
                    out["status"] = "newer" if t.timestamp() > loc["at"] + 86400 else "current"
                else:
                    out["status"] = "update" if t.timestamp() > loc["at"] else "current"
        elif m["kind"] == "pip":
            with _get(f"https://pypi.org/pypi/{m['package']}/json") as r:
                info = json.load(r)
            out["remote"] = info["info"]["version"]
            out["status"] = "missing" if not loc["installed"] else ("update" if _vtuple(out["remote"]) > _vtuple(loc["revision"]) else "current")
    except Exception as e:
        out["status"] = "error"
        out["error"] = str(e)[:200]
    with _lock:
        _checked[key] = out
    return out


def _vtuple(v: str) -> tuple:
    return tuple(int(x) if x.isdigit() else 0 for x in str(v).split("."))


def check_all() -> list:
    return [check(k) for k in REGISTRY]


def listing() -> dict:
    with _lock:
        checked = dict(_checked)
    rows = []
    for k, m in REGISTRY.items():
        rows.append({"key": k, "label": m["label"], "what": m["what"], "page": m["page"], "size": m["size"], "kind": m["kind"],
                     **local(k), "check": checked.get(k)})
    return {"models": rows, "progress": dict(progress)}


# --------------------------------------------------------------------------
# downloading (child process; the server stays offline)
# --------------------------------------------------------------------------

def download(key: str):
    """Start the download in the background. Raises if one is already running."""
    if key not in REGISTRY:
        raise ValueError(key)
    with _lock:
        if progress["running"]:
            raise RuntimeError(f"Already downloading {REGISTRY[progress['running']]['label']}")
        progress.update(running=key, error=None, finished=None, log="")

    def work():
        env = dict(os.environ, HF_HUB_OFFLINE="0", PYTHONUNBUFFERED="1")
        try:
            res = subprocess.run([sys.executable, "-m", "app.models", "download", key], cwd=str(config.APP_DIR), env=env,
                                 capture_output=True, text=True, timeout=7200)
            progress["log"] = (res.stdout + res.stderr)[-2000:]
            if res.returncode != 0:
                raise RuntimeError((res.stderr or res.stdout).strip().splitlines()[-1][:300] if (res.stderr or res.stdout).strip() else f"exit code {res.returncode}")
            _remember(key, local(key).get("revision"))
            _reset(key)
            with _lock:
                _checked.pop(key, None)
        except Exception as e:
            progress["error"] = str(e)[:300]
        finally:
            progress.update(running=None, finished=key)

    threading.Thread(target=work, name="model-download", daemon=True).start()


def _reset(key: str):
    """Drop the loaded model objects so the next use reads the new files."""
    try:
        if key in ("clip", "siglip2"):
            from .semantic import semantic
            e = semantic.engines.get(key)
            if e is not None:
                e._image = e._text = None
                e._image_threads = 0
                e._text_cache.clear()
        elif key == "blip":
            from . import caption
            with caption._lock:
                caption._state.clear()
        elif key == "yolox":
            from . import detector
            with detector._lock:
                detector._instance = None
        elif key == "sface":
            from . import facevecs
            facevecs.reset_session()
        elif key == "geonames":
            from . import places
            places._geo = None  # loaded again from the new files on the next lookup
    except Exception:  # the download itself succeeded; the old objects simply stay until a restart
        traceback.print_exc()


def _download_here(key: str):
    """Runs in the child process, with the hub reachable."""
    m = REGISTRY[key]
    if m["kind"] == "hf" and key in ("clip", "siglip2"):
        from . import semantic
        semantic.download_models(key)
    elif key == "blip":
        from transformers import BlipForConditionalGeneration, BlipProcessor
        from . import caption
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        BlipProcessor.from_pretrained(caption.MODEL, cache_dir=str(MODEL_DIR))
        BlipForConditionalGeneration.from_pretrained(caption.MODEL, cache_dir=str(MODEL_DIR))
    elif key == "yolox":
        from . import detector
        detector.download()
    elif key == "sface":
        from . import facevecs
        facevecs.download()
    elif key == "geonames":
        from . import places
        places.fetch()
    elif key == "ocr":
        # a uv-created venv has no pip; try uv first, then pip (Docker image)
        uv = shutil.which("uv")
        cmd = [uv, "pip", "install", "--upgrade", "-p", sys.executable, "rapidocr"] if uv else [sys.executable, "-m", "pip", "install", "--upgrade", "rapidocr"]
        subprocess.run(cmd, check=True)
    print("done", key)


def auto_download(keys: list, on_done=None):
    """First start of a container or a fresh install: fetch the listed models that are
    missing, one after another, in the background; `on_done(installed_keys)` runs at the
    end so the server can start the jobs that need them. Unknown keys are ignored."""
    todo = [k for k in keys if k in REGISTRY and not local(k)["installed"]]
    if not todo:
        if on_done:
            on_done([])
        return []

    def work():
        got = []
        for key in todo:
            if key == "blip" and importlib.util.find_spec("torch") is None:
                continue  # captions need the optional PyTorch install
            try:
                download(key)
            except RuntimeError:
                time.sleep(5)  # another download is running (the user clicked one): wait for it
                while progress["running"]:
                    time.sleep(2)
                try:
                    download(key)
                except RuntimeError:
                    continue
            while progress["running"] == key:
                time.sleep(2)
            if not progress["error"] and local(key)["installed"]:
                got.append(key)
        if on_done:
            on_done(got)

    threading.Thread(target=work, name="auto-models", daemon=True).start()
    return todo


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "download":
        _download_here(sys.argv[2])
    elif len(sys.argv) == 2 and sys.argv[1] == "check":
        for row in check_all():
            print(row)
    else:
        print("usage: python -m app.models download <key> | check")
        sys.exit(2)
