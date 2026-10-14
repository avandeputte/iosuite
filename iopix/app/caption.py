"""One-sentence descriptions of photos with BLIP base (Salesforce), run locally
through PyTorch (Apple GPU when available, else CPU). The model lives in
data/models (downloaded from the AI analysis page or `python -m app.models
download blip`) and is loaded offline; nothing leaves the machine."""
import logging
import threading

from . import config, jobs, thumbs

log = logging.getLogger(__name__)
MODEL = "Salesforce/blip-image-captioning-base"
MODEL_DIR = config.DATA_DIR / "models"
_lock = threading.Lock()
_state = {}  # model, processor, device and the torch module once loaded; models.py clears it after a re-download


def available() -> bool:
    """Whether the model files are on disk (the hub cache layout: models--org--name/snapshots/<rev>/)."""
    if not config.CAPTIONS:
        return False
    try:
        return any(MODEL_DIR.glob(f"models--{MODEL.replace('/', '--')}/snapshots/*/config.json"))
    except OSError:
        return False


def _load():
    with _lock:
        if "model" in _state:
            return _state
        import torch
        from transformers import BlipForConditionalGeneration, BlipProcessor
        proc = BlipProcessor.from_pretrained(MODEL, cache_dir=str(MODEL_DIR), local_files_only=True)
        model = BlipForConditionalGeneration.from_pretrained(MODEL, cache_dir=str(MODEL_DIR), local_files_only=True)
        torch.set_num_threads(jobs.threads())  # the CPU side of generation, and all of it without a GPU
        dev = "mps" if torch.backends.mps.is_available() else "cpu"
        _state.update(model=model.to(dev).eval(), proc=proc, dev=dev, torch=torch)
        return _state


def describe(paths: list) -> list:
    """One caption per path (None where the file could not be read)."""
    st = _load()
    images, keep = [], []
    for i, p in enumerate(paths):
        try:
            im, _ = thumbs._open_oriented(p, 640, 640)  # the processor resizes to 384 px anyway
            images.append(im.convert("RGB"))
            keep.append(i)
        except Exception as e:
            log.warning("captions: cannot read %s (%s)", p, e)
    out = [None] * len(paths)
    if not images:
        return out
    with st["torch"].no_grad():
        inputs = st["proc"](images=images, return_tensors="pt").to(st["dev"])
        gen = st["model"].generate(**inputs, max_new_tokens=40, num_beams=3, no_repeat_ngram_size=3, repetition_penalty=1.3)
    for i, g in zip(keep, gen):
        out[i] = st["proc"].decode(g, skip_special_tokens=True).strip()
    return out
