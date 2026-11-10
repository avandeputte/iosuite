"""The job process: where the background jobs that load large models do their work.

A model that needs more memory than the server has used to take the web app down with it: the jobs ran on a thread
of the web app, and when the container's limit was reached the kernel killed the one process there was. Now such a
job hands its work to a second process (`jobs.offload(fn, *args)`), started when the first job needs it and ended
when the queue runs dry, which also gives every byte the models held back to the system. The web app watches that
process once a second (memwatch.py) and stops it

- when it holds more than its ceiling (JOBS_MEMORY_MB, by default 60% of the server's memory limit), or
- when the server as a whole has less than its reserve free (MEMORY_RESERVE_MB, by default 8% of the limit),

and no offloaded job starts while the server is below that reserve. Should the kernel get there first, the job
process is the one it picks (its oom_score_adj is raised), and the web app only sees that its job was lost.
jobs.py decides what happens to a job that was lost: once more, then held.

The web app's side of a call:

    web app                                   job process (python -m app.jobworker)
    ("run", module, name, args, baseline) ->  imports the module, sets every Progress as it is here, runs the function
    ("bump", name)                        ->  a Progress was cancelled or started here: the same there
                                          <-  ("progress", {name: fields}, applied)  whatever changed, a few times a second
                                          <-  ("emit", msg)      jobs.emit(msg) in the function: to the call's on_message
                                          <-  ("hook",)          a Progress.finish() that did something (jobs.finished_hook)
                                          <-  ("log", logger, level, text)           its log lines, written by the web app
                                          <-  ("done", error, traceback, result)
    ("exit",)                             ->  the queue is empty

Only what is in the function's own process is separate: it reads and writes the same databases and files. So a
function that is offloaded must be a module-level one, take arguments that pickle, and keep its results in the
database, in files, in its Progress or in what it emits, never in a module's variables.
"""
import atexit
import importlib
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from multiprocessing import Pipe

from app import config, jobs, memwatch

log = logging.getLogger("app.jobproc")
IN_WORKER = os.environ.get("IOPIX_JOB_WORKER") == "1"  # this is the job process itself (jobworker.py)
CHECK_EVERY = 1.0     # seconds between memory checks while a call runs
WAIT_EVERY = 10.0     # seconds between looks while waiting for memory to come free
RECYCLE_SHARE = 0.5   # a process already holding this share of its ceiling is replaced before the next call
START_MARGIN = 1.25   # no call starts below reserve * this: a job stopped at the reserve must not start right back up

_call_lock = threading.Lock()   # one call at a time
_state_lock = threading.Lock()  # guards _worker, _call and what is sent to the process
_worker = None    # {"proc": Popen, "conn": Connection, "rss": int}
_call = None      # the call in flight: {"bumps": {name: n}, "touched": {names the job process reported}}
_inline = None    # with no job process: the on_message of the call running here
_info = {"waiting": None, "lastStop": None, "peak": 0}
worker_emit = None  # in the job process: jobworker's sender


def enabled() -> bool:
    return config.JOBS_PROCESS and not IN_WORKER and os.name == "posix"


def status() -> dict:
    """For the status pages: the memory limit and what is in use, what the job process holds and may hold, whether
    the queue is waiting for memory, and the last time a job was stopped ({at, job, reason})."""
    b = memwatch.budget()
    w = _worker
    return {"process": enabled(), "limit": b["limit"], "used": b["used"], "reserve": b["reserve"], "ceiling": b["ceiling"],
            "worker": (w or {}).get("rss", 0) if w else 0, "waiting": _info["waiting"], "lastStop": _info["lastStop"]}


# ---- the web app's side ------------------------------------------------------------------------------------------

def _on_bump(name: str):
    """A Progress here was cancelled or started again (jobs.bump_hook): the job process's copy follows, and its
    reports for that name are ignored until it has (they would undo the cancel here)."""
    with _state_lock:
        if _call is None or _worker is None:
            return
        _call["bumps"][name] = _call["bumps"].get(name, 0) + 1
        try:
            _worker["conn"].send(("bump", name))
        except (OSError, ValueError):
            pass  # the process is gone: the call ends on its own


def _spawn() -> dict:
    here, there = Pipe()
    try:
        proc = subprocess.Popen([sys.executable, "-m", "app.jobworker", str(there.fileno())], pass_fds=[there.fileno()],
                                cwd=str(config.APP_DIR), env={**os.environ, "IOPIX_JOB_WORKER": "1"}, start_new_session=True)
    finally:
        there.close()
    log.info("job process started (pid %d)", proc.pid)
    return {"proc": proc, "conn": here, "rss": 0}


def _kill(w: dict):
    """End the process and whatever it started (ffmpeg, exiftool): it has its own process group."""
    try:
        os.killpg(w["proc"].pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            w["proc"].kill()
        except OSError:
            pass


def _discard(w: dict):
    global _worker
    with _state_lock:
        if _worker is w:
            _worker = None
    try:
        w["conn"].close()
    except OSError:
        pass
    _kill(w)
    try:
        w["proc"].wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def shutdown():
    """The queue ran dry (jobs.idle_hooks), or the web app is stopping: the job process goes, and its memory with it."""
    with _state_lock:
        w = _worker
    if w is None or _call is not None:
        return
    try:
        w["conn"].send(("exit",))
        w["proc"].wait(timeout=5)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    _discard(w)
    log.info("job process ended (the queue is empty)")


def _ensure() -> dict:
    """The job process, started when there is none, and replaced when the one there already holds much of its
    ceiling (the models of the jobs before): each job gets most of the room."""
    global _worker
    w = _worker
    if w is not None and w["proc"].poll() is None:
        ceiling = memwatch.budget()["ceiling"]
        if not ceiling or memwatch.tree(w["proc"].pid) < ceiling * RECYCLE_SHARE:
            return w
        shutdown()
    elif w is not None:
        _discard(w)
    w = _spawn()
    with _state_lock:
        _worker = w
    return w


def _wait_for_memory():
    """Hold the queue while the server is short of memory: a job started now would only be stopped again."""
    first = True
    while True:
        b = memwatch.budget()
        if not b["reserve"] or b["free"] is None or b["free"] >= b["reserve"] * START_MARGIN:
            break
        if first:
            shutdown()  # an idle job process is memory too
            log.warning("the jobs wait for memory: %s of %s in use", memwatch.gb(b["used"]), memwatch.gb(b["limit"]))
            first = False
        _info["waiting"] = {"since": _info["waiting"]["since"] if _info["waiting"] else int(time.time()), "used": b["used"], "limit": b["limit"]}
        time.sleep(WAIT_EVERY)
    if not first:
        log.info("the jobs go on: memory is free again")
    _info["waiting"] = None


def _over(w: dict):
    """A WorkerLost when the job process has to go now, else None."""
    b = memwatch.budget()
    rss = w["rss"] = memwatch.tree(w["proc"].pid)
    _info["peak"] = max(_info["peak"], rss)
    if b["ceiling"] and rss > b["ceiling"]:
        return jobs.WorkerLost(f"it needed more memory than analysis may use on this server ({memwatch.gb(rss)}, the most is {memwatch.gb(b['ceiling'])})")
    if b["reserve"] and b["free"] is not None and b["free"] < b["reserve"]:
        own = rss >= (b["ceiling"] or b["limit"] * memwatch.CEILING_SHARE) / 3  # a small job is not what filled the server
        return jobs.WorkerLost(f"the server was running out of memory ({memwatch.gb(b['used'])} of {memwatch.gb(b['limit'])} in use, {memwatch.gb(rss)} of it by this job)", strike=own)
    return None


def _died(w: dict):
    try:
        rc = w["proc"].wait(timeout=10)
    except subprocess.TimeoutExpired:
        rc = None
    if rc == -signal.SIGKILL:
        return jobs.WorkerLost("the system stopped it, most likely because the server ran out of memory")
    return jobs.WorkerLost(f"its process ended unexpectedly (exit code {rc})")


def _apply(call: dict, changed: dict, applied: dict):
    """The job process's Progress fields, into the ones here; not for a name cancelled here since (see _on_bump)."""
    for name, fields in changed.items():
        p = jobs._progress.get(name)
        if p is None or applied.get(name, 0) != call["bumps"].get(name, 0):
            continue
        dict.update(p, fields)
        call["touched"].add(name)


def _resolve(module: str, name: str):
    obj = importlib.import_module(module)
    for part in name.split("."):
        obj = getattr(obj, part)
    return obj


def call(fn, args: tuple, on_message=None):
    """jobs.offload: run fn(*args) in the job process and wait."""
    global _call, _inline
    key = jobs.current()
    hold = jobs.held(key) if key else None
    if hold:
        raise jobs.Held(f"paused: {hold['reason']}")
    if not enabled():
        before, _inline = _inline, on_message
        try:
            return fn(*args)
        finally:
            _inline = before
    try:
        same = _resolve(fn.__module__, fn.__qualname__) is fn
    except (AttributeError, ImportError):
        same = False
    if not same:
        raise TypeError(f"{fn.__module__}.{fn.__qualname__} cannot be offloaded: not a module-level function")
    with _call_lock:
        _wait_for_memory()
        w = _ensure()
        call_ = {"bumps": {}, "touched": set()}
        with _state_lock:  # a cancel from another thread is either in the baseline or sent after the run message, never lost between
            baseline = {name: (dict(p), p.gen) for name, p in jobs._progress.items()}
            _call = call_
            try:
                w["conn"].send(("run", fn.__module__, fn.__qualname__, args, baseline))
            except (OSError, ValueError):
                pass  # found dead below
        lost = done = None
        next_check = time.monotonic() + CHECK_EVERY
        try:
            while done is None:
                try:
                    ready = w["conn"].poll(0.2)
                except (OSError, EOFError):
                    ready = True
                if ready:
                    try:
                        msg = w["conn"].recv()
                    except (EOFError, OSError):
                        lost = lost or _died(w)
                        break
                    kind = msg[0]
                    if kind == "progress":
                        _apply(call_, msg[1], msg[2])
                    elif kind == "emit":
                        if on_message:
                            try:
                                on_message(msg[1])
                            except Exception:
                                log.exception("a job's message handler failed")
                    elif kind == "hook":
                        if jobs.finished_hook:
                            jobs.finished_hook()
                    elif kind == "log":
                        logging.getLogger(msg[1]).log(msg[2], "%s", msg[3])
                    elif kind == "done":
                        done = msg
                    continue
                if lost is None and time.monotonic() >= next_check:
                    next_check = time.monotonic() + CHECK_EVERY
                    lost = _over(w)
                    if lost is not None:
                        _kill(w)  # the pipe closes, and the loop ends at the EOF
                if w["proc"].poll() is not None and not w["conn"].poll(0):
                    lost = lost or _died(w)
                    break
        finally:
            with _state_lock:
                _call = None
        if done is None:
            _discard(w)
            for name in call_["touched"]:  # what the lost process left "running" would look alive for ever
                p = jobs._progress.get(name)
                if p is not None and p["running"] and call_["bumps"].get(name, 0) == 0:
                    p["running"] = False
                    p.fail(f"Stopped: {lost}")
            _info["lastStop"] = {"at": int(time.time()), "job": key, "reason": str(lost)}
            log.warning("job %s stopped: %s", key or fn.__qualname__, lost)
            jobs.note_lost(lost)
            raise lost
        _kind, error, tb, result = done
        if error is not None:
            log.error("job %s failed in the job process: %s\n%s", key or fn.__qualname__, error, tb)
            raise jobs.RemoteError(error)
        return result


def emit(msg):
    """jobs.emit: from the offloaded function to its call's on_message."""
    if IN_WORKER:
        if worker_emit:
            worker_emit(msg)
    elif _inline:
        _inline(msg)


if not IN_WORKER:
    jobs.bump_hook = _on_bump
    jobs.idle_hooks.append(shutdown)
    atexit.register(shutdown)
