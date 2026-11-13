"""`python -m app.jobworker FD`: the job process (see jobproc.py for why there is one, and the messages).

Started by the web app with one end of a pipe, it runs the functions the web app's jobs hand it, one at a time, and
ends when told to or when the web app is gone. It reads the same configuration, databases and files as the web app;
what it holds in memory (the models, mostly) is its own and goes when it ends.
"""
import importlib
import logging
import os
import queue
import sys
import threading
import time
import traceback
from multiprocessing.connection import Connection

os.environ["IOPIX_JOB_WORKER"] = "1"  # before app.jobproc is imported: this is the job process, whoever started it

from app import jobs, jobproc  # noqa: E402

REPORT_EVERY = 0.25  # seconds between Progress reports

_send_lock = threading.Lock()
_lock = threading.Lock()   # guards the baseline, the cancels applied and what was last reported
_applied = {}              # name -> cancels from the web app applied during this call
_reported = {}             # name -> the fields last sent (or as the web app had them when the call began)
_runs = queue.Queue()
_conn = None


def _send(msg):
    with _send_lock:
        try:
            _conn.send(msg)
        except (OSError, ValueError):
            os._exit(0)  # the web app is gone
        except Exception as e:  # something that does not pickle: a programming error, said in the web app's log
            _conn.send(("log", "app.jobworker", logging.ERROR, f"a message could not be sent to the web app ({type(e).__name__}: {e})"))


class _ToWebApp(logging.Handler):
    """Log lines go to the web app, which writes them where its own go (one writer for the log file and its rotation)."""

    def emit(self, record):
        try:
            text = record.getMessage()
            if record.exc_info:
                text += "\n" + "".join(traceback.format_exception(*record.exc_info)).rstrip()
            _send(("log", record.name, record.levelno, text))
        except Exception:
            pass


def _begin(baseline: dict):
    """A call begins: every Progress as the web app has it, so a generation a job took there means the same here.
    Done by the thread that reads the pipe, in the order the messages came: a cancel sent after the run message is
    applied after this, never undone by it."""
    with _lock:
        jobs.baseline.clear()
        jobs.baseline.update(baseline)
        jobs.bumped.clear()
        _applied.clear()
        _reported.clear()
        for name, (fields, gen) in baseline.items():
            _reported[name] = dict(fields)
            p = jobs._progress.get(name)
            if p is not None:
                dict.clear(p)
                dict.update(p, fields)
                p.gen = gen


def _bump(name: str):
    with _lock:
        _applied[name] = _applied.get(name, 0) + 1
        jobs.bumped[name] = jobs.bumped.get(name, 0) + 1
        p = jobs._progress.get(name)
        if p is not None:
            p.gen += 1
            p["running"] = False


def _report():
    """What changed in any Progress since the last report, with the cancels applied so far (the web app ignores a
    report made before a cancel of its own arrived here)."""
    with _lock:
        changed = {}
        try:
            for name, p in list(jobs._progress.items()):
                cur = dict(p)
                if cur != _reported.get(name):
                    changed[name] = _reported[name] = cur
        except RuntimeError:  # a job thread changed a dict's size meanwhile: the next report has it
            return
        applied = dict(_applied)
    if changed:
        _send(("progress", changed, applied))


def _read():
    while True:
        try:
            msg = _conn.recv()
        except (EOFError, OSError):
            os._exit(0)  # the web app closed its end, or is gone: nothing here outlives it
        if msg[0] == "run":
            _begin(msg[4])
            _runs.put(msg)
        elif msg[0] == "bump":
            _bump(msg[1])
        elif msg[0] == "exit":
            os._exit(0)


def _reporter():
    while True:
        time.sleep(REPORT_EVERY)
        _report()


def _prefer_me_when_out_of_memory():
    """Should the kernel have to end a process for memory, it is this one, not the web app or the database."""
    try:
        with open("/proc/self/oom_score_adj", "w") as f:
            f.write("900")
    except OSError:
        pass


def main():
    global _conn
    _conn = Connection(int(sys.argv[1]))
    _prefer_me_when_out_of_memory()
    root = logging.getLogger()
    root.handlers[:] = [_ToWebApp()]
    root.setLevel(logging.INFO)
    jobproc.worker_emit = lambda msg: _send(("emit", msg))
    importlib.import_module("app.ai.analysis")  # it sets jobs.finished_hook for the web app: replaced just below
    jobs.finished_hook = lambda: _send(("hook",))  # a run that did something: the web app folds the results in
    threading.Thread(target=_read, name="jobworker-read", daemon=True).start()
    threading.Thread(target=_reporter, name="jobworker-report", daemon=True).start()
    while True:
        _kind, module, name, args, _baseline = _runs.get()
        error = tb = result = None
        try:
            fn = importlib.import_module(module)
            for part in name.split("."):
                fn = getattr(fn, part)
            result = fn(*args)
        except BaseException as e:  # reported, not fatal: the next call gets the same process
            error, tb = f"{type(e).__name__}: {e}", traceback.format_exc()
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                _send(("done", error, tb, None))
                raise
        _report()  # the last state before the answer: the web app reads its Progress right after
        _send(("done", error, tb, result))


if __name__ == "__main__":
    main()
