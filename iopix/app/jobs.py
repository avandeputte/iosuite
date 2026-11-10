"""One queue for the heavy background work, so only one job runs at a time
and the machine stays usable for the web app and everything else.

Thumbnails, sharpness/objects, content-search embeddings, text recognition
and captions each used to start their own thread the moment the library
changed and then compete for every core and the GPU. Now they line up in a
fixed order and run one after the other. A job submitted while it is already
queued simply keeps its place; while it is running, the job's own generation
check stops it at the next batch and the new submission runs afterwards.

How many cores a running job may use is `threads()`: the `bg_threads`
setting, else BG_THREADS from the environment, else half the cores.

The jobs that load large models do their work in a process of their own (jobproc.py):
`offload(fn, *args)` runs a module-level function there and waits for it, so a model
that needs more memory than the server has takes that process down and not the web
app. A job whose process was lost is tried once more; lost again, it is held (it
stops being run, and says why) until someone asks for it again or the server restarts.
"""
import logging
import threading
import time
import traceback

from app import config
from app.data import state

ORDER = ["thumbs", "pixels", "embeddings", "vision", "facedetect", "faces", "neardups", "captions", "looks", "ages", "jerseys", "clothing", "rotation", "videos", "filecheck"]

_lock = threading.Lock()
_wake = threading.Event()
_queue = {}          # key -> callable, at most one per key
_current = None      # key of the job running now
_started = None      # when it started
_thread = None
_last_submit = 0.0  # jobs submitted close together (a start, a library change) are picked in ORDER, not arrival order
GRACE = 3.0
MAX_SETTLE = 30.0  # a queue that never goes quiet (rebuild after rebuild) still gets its jobs run
_progress = {}       # name -> Progress, every background job that reports one
_strikes = {}        # key -> how often in a row the job's process was lost (a run that ends well clears it)
_held = {}           # key -> {"reason", "at"}: lost twice in a row, not run again until release()
_lost = None         # the WorkerLost of the job running now, noted by jobproc even when the job itself swallows it
HOLD_AFTER = 2
log = logging.getLogger("app.jobs")
# set by jobproc: called with a Progress's name when its generation moves, so the job process hears of a cancel
bump_hook = None
# in the job process only: {name: (fields, gen)} as the web app had them when the call began, and the cancels that
# arrived since; a Progress created during the call (a module imported late) starts from them, not from zero
baseline, bumped = {}, {}


class WorkerLost(Exception):
    """The job process ended without finishing its call: stopped for memory, killed by the system, crashed.
    `strike`: whether it counts against the job (not when the server was merely short of memory for a moment)."""

    def __init__(self, text: str, strike: bool = True):
        super().__init__(text)
        self.strike = strike


class Held(WorkerLost):
    """The job is held (lost twice in a row): nothing was started."""

    def __init__(self, text: str):
        super().__init__(text, strike=False)


class RemoteError(Exception):
    """The function run in the job process raised; the text is its exception, the traceback is in the log."""
# the most of an exception's text a status record keeps: the message that says what went wrong, not the
# traceback (that goes to the log); status pages and tool answers show it whole
ERROR_TEXT_MAX = 300
finished_hook = None  # called when any job's run ends (the index folds the results in once, then)
idle_hooks = []       # called once the queue has run dry: models are dropped so an idle server keeps its memory small


class Progress(dict):
    """What one background job reports: running, done, total, error and the job's own fields (added, found...).
    A dict, so the status endpoints serialise it as before; the methods keep the bookkeeping in one place.

    A run is `gen = progress.start(total, ...)`, `progress.step(n)` per batch, `progress.fail(e)` on an error and
    `progress.finish(gen)` at the end. `start()` and `cancel()` move the generation on, and a job checks
    `progress.cancelled(gen)` between batches, so a reset or a newer run stops the old one at its next batch.
    When the job keeps `started` or `finished` times, start() and finish() set them."""

    def __init__(self, name: str, **fields):
        super().__init__({"running": False, "done": 0, "total": 0, "error": None, **fields})
        self.name, self.gen = name, 0
        self._times = {k for k in ("started", "finished") if k in self}
        if name in baseline:  # the job process: as the web app has it, so a generation taken there means the same here
            self.update(baseline[name][0])
            self.gen = baseline[name][1] + bumped.get(name, 0)
            if bumped.get(name):
                self["running"] = False
        _progress[name] = self

    def start(self, total: int = 0, **fields) -> int:
        self.gen += 1
        if bump_hook:
            bump_hook(self.name)
        self.update(running=True, done=0, total=total, error=None)
        if "started" in self._times:
            self["started"] = int(time.time())
        if "finished" in self._times:
            self["finished"] = None
        self.update(fields)
        return self.gen

    def step(self, n: int = 1):
        self["done"] += n

    def fail(self, e):
        self["error"] = (e if isinstance(e, str) else str(e))[:ERROR_TEXT_MAX]

    def finish(self, gen: int = None):
        """The run is over; with `gen`, only if no newer run has replaced it (that one reports its own end)."""
        if gen is not None and gen != self.gen:
            return
        self["running"] = False
        if "finished" in self._times:
            self["finished"] = int(time.time())
        if finished_hook and self["done"]:  # a run that did something: the results are ready to be folded in
            try:
                finished_hook()
            except Exception:
                traceback.print_exc()

    def cancel(self) -> int:
        """Stop the running job at its next batch (a reset, a model switch). Returns the new generation. The run is
        no longer "running" from here on: the old run's finish(gen) is a no-op, and a start() that checks the flag
        must not take the dying run for a live one."""
        self.gen += 1
        self["running"] = False
        if bump_hook:
            bump_hook(self.name)
        return self.gen

    def cancelled(self, gen: int) -> bool:
        return gen != self.gen


def progress_all() -> dict:
    """Every job's progress, by name: one shape for a status page to render."""
    return {name: dict(p) for name, p in _progress.items()}


def threads() -> int:
    """Cores a background job may use right now."""
    n = config.cpu_count()
    try:
        v = int(state.get_setting("bg_threads") or 0)
    except (TypeError, ValueError):
        v = 0
    if v <= 0:
        v = config.BG_THREADS
    return max(1, min(v, max(1, n - 1)))


def batch_threads() -> int:
    """Worker threads for a job that runs the model per photo in a small pool (jerseys, clothing): the core budget,
    but at most 4, since the model itself is already multi-threaded and more workers only contend for it."""
    return max(1, min(4, threads()))


def submit(key: str, fn):
    """Queue a job; `fn` runs on the single worker thread. Keys run in ORDER."""
    global _thread
    if key not in ORDER:
        raise ValueError(key)
    global _last_submit
    with _lock:
        _queue[key] = fn
        _last_submit = time.time()
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_worker, name="jobs", daemon=True)
            _thread.start()
    _wake.set()


def status() -> dict:
    from app import jobproc
    with _lock:
        return {"running": _current, "queued": [k for k in ORDER if k in _queue], "threads": threads(),
                "cores": config.cpu_count(), "since": _started, "held": {k: dict(v) for k, v in _held.items()},
                "memory": jobproc.status()}


def current():
    """The key of the job running now, or None."""
    return _current


def held(key: str = None):
    """Why this job is held ({"reason", "at"}), or None; with no key, every held job."""
    with _lock:
        return dict(_held) if key is None else _held.get(key)


def release(key: str = None):
    """Run a held job again at its next start (all of them with no key): someone asked for it."""
    with _lock:
        for k in ([key] if key else list(_held) + list(_strikes)):
            _held.pop(k, None)
            _strikes.pop(k, None)


def offload(fn, *args, on_message=None):
    """Run the module-level function `fn(*args)` in the job process and wait for what it returns. Its Progress
    objects are the web app's (kept in step both ways), `emit(msg)` inside it reaches `on_message` here, and a
    cancel here is seen there. Raises WorkerLost when the process ended first, Held when the job is held, and
    RemoteError when `fn` raised. With JOBS_PROCESS=0 (and in the tests) it simply calls `fn` here."""
    from app import jobproc
    return jobproc.call(fn, args, on_message)


def emit(msg):
    """Inside an offloaded function: hand `msg` (anything that pickles) to the `on_message` of its offload()."""
    from app import jobproc
    jobproc.emit(msg)


def note_lost(e: WorkerLost):
    """jobproc: the running job's process was lost (kept even when the job's own code swallows the exception)."""
    global _lost
    _lost = e


def _after_loss(key: str, fn, e: WorkerLost):
    """Once more, then hold: what was recorded before the loss is kept, so the second run goes on from there, and a
    job that dies at the same place again stops costing the server a model load at every library change."""
    with _lock:
        _strikes[key] = _strikes.get(key, 0) + (1 if e.strike else 0.5)
        if _strikes[key] >= HOLD_AFTER:
            _held[key] = {"reason": str(e), "at": int(time.time())}
            _queue.pop(key, None)
            hold = True
        else:
            _queue.setdefault(key, fn)  # a newer submission keeps its place
            hold = False
    if hold:
        log.warning("job %s is paused: %s (twice in a row). Settings › AI runs it again.", key, e)
    else:
        log.warning("job %s: %s; trying once more", key, e)
    _wake.set()


def is_queued(key: str) -> bool:
    with _lock:
        return key in _queue


def _worker():
    global _current, _started
    while True:
        # wait until the queue has been quiet for GRACE seconds, so a burst of submissions
        # (startup, a library change) settles before the first job is picked by ORDER
        waited_since = time.time()
        while True:
            with _lock:
                settle = GRACE - (time.time() - _last_submit)
                if not _queue or settle <= 0 or time.time() - waited_since > MAX_SETTLE:
                    break
            _wake.wait(timeout=settle)
            _wake.clear()
        with _lock:
            key = next((k for k in ORDER if k in _queue), None)
            fn = _queue.pop(key) if key else None
            _current, _started = key, (time.time() if key else None)
        if fn is None:
            _wake.wait(timeout=30)
            _wake.clear()
            continue
        global _lost
        _lost = None
        try:
            fn()
        except WorkerLost as e:
            _lost = _lost or e
        except Exception:
            traceback.print_exc()
        if _lost is not None and not isinstance(_lost, Held):
            _after_loss(key, fn, _lost)
        elif _lost is None:
            with _lock:
                _strikes.pop(key, None)
        with _lock:
            _current = _started = None
            idle = not _queue
        if idle:
            for hook in list(idle_hooks):
                try:
                    hook()
                except Exception:
                    traceback.print_exc()
            import gc
            gc.collect()
