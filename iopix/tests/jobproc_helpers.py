"""Functions the job-process tests offload (tests/test_jobproc.py): module-level, so the job process can import them."""
import os
import signal
import time

from app import jobs

progress = jobs.Progress("jobproc-test", note="")
other = jobs.Progress("jobproc-other")


def add(a, b):
    return a + b


def where():
    return os.getpid(), os.environ.get("IOPIX_JOB_WORKER")


def steps(n: int):
    """Counts to n in its Progress, emits each number, and finishes."""
    progress.update(running=True, done=0, total=n, note="counting")
    for i in range(n):
        time.sleep(0.02)
        progress.step()
        jobs.emit(i)
    progress.finish()
    return n


def until_cancelled(gen: int, limit: float = 20.0):
    """Runs until the web app cancels the Progress (or `limit` seconds pass); returns whether it was cancelled."""
    progress.update(running=True)
    end = time.time() + limit
    while time.time() < end:
        if progress.cancelled(gen):
            return True
        time.sleep(0.02)
    return False


def gen_seen():
    return progress.gen, dict(progress)


def boom():
    raise ValueError("no good")


def die():
    progress.update(running=True, done=3, total=9)
    time.sleep(0.6)  # long enough for the report to reach the web app
    os._exit(3)


def killed():
    time.sleep(0.2)
    os.kill(os.getpid(), signal.SIGKILL)


def hog(mb: int, seconds: float = 30.0):
    """Holds `mb` megabytes for a while: what a model that is too large does."""
    progress.update(running=True)
    block = bytearray(mb * 1024 * 1024)
    for i in range(0, len(block), 4096):
        block[i] = 1  # touched, so it is resident
    time.sleep(seconds)
    return len(block)
