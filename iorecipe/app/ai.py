"""Reading a recipe with AI, on this server: where a web page has no recipe data and no list of ingredients ioRecipe
can make out, the page's text is given to a small language model that runs inside the app (llama.cpp, through
llama-cpp-python), which finds the recipe in it. Nothing leaves the server: there is no AI service behind this.

The model is one file (GGUF, about 1 GB), fetched once into DATA_DIR/models when the app first starts with the
runtime installed. AI_MODEL names another: a file on this server, or the web address of one. AI=0 turns it off.
The model is loaded for a page and let go again, in a process of its own (`python -m app.ai`): a page takes a minute
or so of the server's processor, and a model the processor cannot run takes that process down, not the app.
"""
import importlib.util
import json
import logging
import os
import re
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

from iosuite_shared.errors import Invalid

from app import config

log = logging.getLogger("iorecipe.ai")
# Qwen2.5 1.5B Instruct, 4-bit (Apache 2.0): small enough for a home server's processor, and it reads the languages
# recipes here come in
DEFAULT_MODEL = "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
CONTEXT = 8192     # tokens the model looks at: the page's text and its answer
ANSWER = 1800      # tokens of the answer at most
_fetching = threading.Lock()
_failed = ""       # why the model could not be fetched, when it could not

SYSTEM = """You extract the recipe from the text of a web page. Answer with JSON only.

Copy the recipe exactly as the page gives it, in the page's own language. Do not translate, do not convert units, do not add or improve anything. \
Leave out menus, the story around the recipe, comments and advertisements.

- found: false when the page holds no recipe; then leave the rest empty.
- title: the name of the dish.
- servings: what the recipe yields as the page says it ("6 portions"), or "".
- prepMinutes, cookMinutes, totalMinutes: whole minutes when the page states them, otherwise 0.
- ingredients: one entry per ingredient with its amount, in the page's order.
- steps: one entry per step, without its number. Only steps the page writes out; none when the page has none."""

SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "title": {"type": "string"},
        "servings": {"type": "string"},
        "prepMinutes": {"type": "integer"},
        "cookMinutes": {"type": "integer"},
        "totalMinutes": {"type": "integer"},
        "ingredients": {"type": "array", "items": {"type": "string"}},
        "steps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["found", "title", "servings", "prepMinutes", "cookMinutes", "totalMinutes", "ingredients", "steps"],
}


def runtime() -> bool:
    """Whether llama-cpp-python is installed here."""
    return importlib.util.find_spec("llama_cpp") is not None


def model_file() -> Path:
    """Where the model is, or is to be: AI_MODEL as a file on this server, else DATA_DIR/models/<the name in its address>."""
    m = config.AI_MODEL or DEFAULT_MODEL
    if not re.match(r"https?://", m, re.I):
        return Path(m).expanduser()
    return config.DATA_DIR / "models" / (m.split("?")[0].rstrip("/").rsplit("/", 1)[-1] or "model.gguf")


def state() -> str:
    """"off" (AI=0, or the runtime is not installed), "ready", "fetching" (the model is on its way) or "missing"."""
    if not config.AI or not runtime():
        return "off"
    if model_file().is_file():
        return "ready"
    return "fetching" if _fetching.locked() else "missing"


def available() -> bool:
    return state() == "ready"


def why_not() -> str:
    """For somebody whose page was not read: what stands between this server and reading it with AI."""
    s = state()
    if s == "fetching":
        return "The AI model is still being fetched to this server: try again in a few minutes."
    if s == "missing":
        return f"The AI model could not be fetched to this server ({_failed or 'see the log'})."
    return ""


def fetch_model() -> None:
    """Fetches the model when it is not there yet (once, at the start, off the request path). The file appears under
    its name only when it is whole."""
    global _failed
    m = config.AI_MODEL or DEFAULT_MODEL
    dest = model_file()
    if state() == "off" or dest.is_file() or not re.match(r"https?://", m, re.I) or not _fetching.acquire(blocking=False):
        return
    part = dest.with_name(dest.name + ".part")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        log.info("Fetching the AI model %s (once; about 1 GB)", m)
        req = urllib.request.Request(m, headers={"User-Agent": "ioRecipe"})
        with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
            if r.read(4) != b"GGUF":
                raise ValueError("that address does not give a GGUF model")
            f.write(b"GGUF")
            while chunk := r.read(1 << 20):
                f.write(chunk)
        os.replace(part, dest)
        _failed = ""
        log.info("The AI model is in place: %s", dest)
    except (OSError, ValueError) as e:
        _failed = str(getattr(e, "reason", e))[:200]
        log.warning("The AI model could not be fetched (%s): pages are read without it", _failed)
        part.unlink(missing_ok=True)
    finally:
        _fetching.release()


def start() -> None:
    """At the app's start: the model on its way in the background, where it is wanted and not there."""
    if state() == "missing":
        threading.Thread(target=fetch_model, name="ai-model", daemon=True).start()


def _ask(text: str, url: str) -> dict | None:
    """The model's answer as the schema's object, from a process of its own; None when it gave none."""
    try:
        p = subprocess.run([sys.executable, "-m", "app.ai", str(model_file())], input=json.dumps({"text": text, "url": url}).encode(),
                           capture_output=True, timeout=config.AI_TIMEOUT, cwd=str(config.APP_DIR))
    except subprocess.TimeoutExpired as e:
        raise Invalid("Reading that page with AI took too long on this server") from e
    except OSError as e:
        raise Invalid("The AI model could not be started on this server") from e
    if p.returncode != 0:
        log.warning("The AI model stopped with %s: %s", p.returncode, p.stderr.decode("utf-8", "replace")[-400:])
        return None
    try:
        return json.loads(p.stdout.decode("utf-8", "replace").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


def _words(s: str) -> list[str]:
    return re.findall(r"[^\W_]+", s.lower())


def _grounded(line: str, page: set[str]) -> bool:
    """Whether a line is the page's: a small model sometimes writes what a recipe usually says, not what this one does."""
    w = _words(line)
    return bool(w) and sum(1 for x in w if x in page) >= 0.8 * len(w)


def recipe(text: str, url: str) -> dict | None:
    """The recipe in a page's text, as scrape's readers give one (without picture or source), or None when the page
    holds none. Only lines whose words are on the page are kept. Invalid when the model cannot be asked."""
    if not available() or not text.strip():
        return None
    d = _ask(text, url)
    if not isinstance(d, dict) or not d.get("found"):
        return None
    page = set(_words(text))
    lines = lambda v: [x for x in (" ".join(str(i).split()) for i in (v if isinstance(v, list) else [])) if x and _grounded(x, page)][:400]  # noqa: E731
    mins = lambda v: v if isinstance(v, int) and not isinstance(v, bool) and 0 < v < 100_000 else None  # noqa: E731
    title = " ".join(str(d.get("title") or "").split())
    servings = str(d.get("servings") or "").strip()[:64]
    out = {"title": title if _grounded(title, page) else "", "description": None,
           "servings": servings if servings and _grounded(servings, page) else None,
           "prepMinutes": mins(d.get("prepMinutes")), "cookMinutes": mins(d.get("cookMinutes")), "totalMinutes": mins(d.get("totalMinutes")),
           "ingredients": lines(d.get("ingredients")), "steps": lines(d.get("steps")), "tags": []}
    return out if len(out["ingredients"]) >= 2 else None


# ---- the process that holds the model: `python -m app.ai <model file>`, the page as JSON on stdin, the answer on stdout

def _window(lines: list[str], count, budget: int) -> str:
    """The part of a page the model can take in: all of it when it fits, else from a little before its "Ingredients"
    (or from the top), as many lines as fit."""
    if count("\n".join(lines)) <= budget:
        return "\n".join(lines)
    from app import textimport
    start = next((i for i, ln in enumerate(lines) if re.match(rf"^(?:{textimport.HEADS['ingredients']})\b", ln.lstrip("# *_"), re.I)), 0)
    out: list[str] = []
    used = 0
    for ln in lines[max(0, start - 25):]:
        used += count(ln) + 1
        if used > budget:
            break
        out.append(ln)
    return "\n".join(out)


def main() -> None:
    from llama_cpp import Llama

    ask = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    llm = Llama(model_path=sys.argv[1], n_ctx=CONTEXT, n_threads=max(1, (os.cpu_count() or 2) - 1), verbose=False)
    count = lambda s: len(llm.tokenize(s.encode("utf-8"), add_bos=False))  # noqa: E731
    text = _window(ask["text"].split("\n"), count, CONTEXT - ANSWER - count(SYSTEM) - 200)
    r = llm.create_chat_completion(
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"The page at {ask['url']}:\n\n{text}"}],
        response_format={"type": "json_object", "schema": SCHEMA}, temperature=0, max_tokens=ANSWER)
    sys.stdout.write("\n" + json.dumps(json.loads(r["choices"][0]["message"]["content"])) + "\n")


if __name__ == "__main__":
    main()
