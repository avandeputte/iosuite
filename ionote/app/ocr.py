"""Text in pictures for notes made in the web app (RapidOCR, an optional package: pip install -e '.[ocr]').

The Mac and iPhone apps read the text themselves with Apple's Vision framework and send it as ocrText, so the
server only does this for pictures added in the browser. One background thread works through a queue; the
text lands in notes.ocr_text, which MariaDB's full-text index covers.
"""
import io
import logging
import queue
import threading

from app import config, images, notes

log = logging.getLogger("app.ocr")
_q = queue.Queue()
_queued = set()  # ids waiting in _q: a note queued twice is read once
_qlock = threading.Lock()
_engine = None
_thread = None
_failed = None


def available() -> bool:
    if not config.OCR:
        return False
    import importlib.util
    return importlib.util.find_spec("rapidocr") is not None


def status() -> dict:
    return {"enabled": config.OCR, "installed": available(), "queued": _q.qsize(), "error": _failed}


def _read(data: bytes) -> str:
    global _engine
    import numpy as np
    from PIL import Image
    if _engine is None:
        from rapidocr import RapidOCR
        _engine = RapidOCR()
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((2400, 2400))
    res = _engine(np.array(img))
    txts = getattr(res, "txts", None)
    if txts is None and isinstance(res, tuple):  # older rapidocr: ([box, text, score], ...), elapsed
        txts = [r[1] for r in (res[0] or [])]
    return "\n".join(t for t in (txts or []) if t and t.strip())


def _work():
    global _failed
    while True:
        item = _q.get()
        with _qlock:
            _queued.discard(item)
        try:
            if isinstance(item, tuple):  # ("att", id): a picture attached to a note
                from app import attachments
                got = attachments.raw_for_ocr(item[1])
                if got:
                    text = _read(got[0])
                    if text:
                        attachments.set_text(item[1], text, got[1])
                        log.info("read %d characters of text in attachment %s", len(text), item[1])
            else:
                got = images.get(item)
                if got:
                    text = _read(got[0])
                    if text:
                        notes.set_ocr_text(item, text, got[2])
                        log.info("read %d characters of text in the picture of %s", len(text), item)
            _failed = None
        except Exception as e:
            _failed = f"{type(e).__name__}: {e}"[:300]
            log.warning("text recognition failed for %s: %s", item, _failed)
        finally:
            _q.task_done()


def _start():
    global _thread
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_work, name="ocr", daemon=True)
        _thread.start()


def _put(item) -> bool:
    if not available():
        return False
    _start()
    with _qlock:
        if item not in _queued:
            _queued.add(item)
            _q.put(item)
    return True


def enqueue_attachment(att_uid: str) -> bool:
    """Read the text in a picture attached to a note, in the background; False when RapidOCR is not installed."""
    return _put(("att", att_uid))


def enqueue(uid: str) -> bool:
    """Read the text in this note's picture in the background; False when RapidOCR is not installed."""
    return _put(uid)
