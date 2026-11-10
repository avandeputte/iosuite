"""The job process (app/jobproc.py, app/jobworker.py): offloaded functions run in a second process, their Progress
stays in step both ways, a process that is lost or too large is reported and not fatal, and jobs.py retries a lost
job once and then holds it. Also memwatch's numbers."""
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from helpers import wait_for as _wait
from app import config, jobproc, jobs, memwatch
import jobproc_helpers as hp

pytestmark = pytest.mark.skipif(os.name != "posix" or not Path("/proc/self/statm").exists(), reason="the job process is watched through /proc")


@pytest.fixture
def proc(monkeypatch):
    """Offloading on for the test (the suite runs with it off), the helpers importable in the job process."""
    monkeypatch.setattr(config, "JOBS_PROCESS", True)
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(Path(__file__).parent), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep))
    jobs.release()
    yield
    jobproc.shutdown()
    jobs.release()
    hp.progress.update(running=False, done=0, total=0, error=None, note="")


def test_offload_runs_in_another_process_and_returns_the_result(proc):
    assert jobs.offload(hp.add, 2, 3) == 5
    pid, flag = jobs.offload(hp.where)
    assert pid != os.getpid() and flag == "1"
    assert jobs.offload(hp.where)[0] == pid  # the same process serves the next call
    jobproc.shutdown()
    assert jobs.offload(hp.where)[0] != pid  # and a new one after the queue ran dry


def test_without_the_job_process_the_function_runs_here(monkeypatch):
    monkeypatch.setattr(config, "JOBS_PROCESS", False)
    got = []
    assert jobs.offload(hp.steps, 3, on_message=got.append) == 3
    assert got == [0, 1, 2] and jobs.offload(hp.where)[0] == os.getpid()
    hp.progress.update(running=False, done=0, total=0, note="")


def test_progress_and_messages_reach_the_web_app(proc):
    got, hooks = [], []
    before, jobs.finished_hook = jobs.finished_hook, lambda: hooks.append(1)
    try:
        assert jobs.offload(hp.steps, 5, on_message=got.append) == 5
    finally:
        jobs.finished_hook = before
    assert got == [0, 1, 2, 3, 4]
    assert hp.progress["done"] == 5 and hp.progress["total"] == 5 and hp.progress["running"] is False and hp.progress["note"] == "counting"
    assert hooks == [1]  # the run did something: the web app folds the results in, once


def test_the_job_process_starts_from_the_web_apps_progress(proc):
    hp.progress.update(done=7, note="from the web app")
    gen = hp.progress.cancel()
    seen_gen, fields = jobs.offload(hp.gen_seen)
    assert seen_gen == gen and fields["done"] == 7 and fields["note"] == "from the web app"


def test_a_cancel_in_the_web_app_stops_the_function(proc):
    gen = hp.progress.cancel()
    out = {}
    t = threading.Thread(target=lambda: out.update(r=jobs.offload(hp.until_cancelled, gen)))
    t.start()
    assert _wait(lambda: hp.progress["running"])  # the function's own update arrived
    hp.progress.cancel()
    t.join(15)
    assert out.get("r") is True
    assert hp.progress["running"] is False  # a late report from the job process did not undo the cancel


def test_an_error_in_the_function_is_raised_here_and_the_process_lives_on(proc):
    pid = jobs.offload(hp.where)[0]
    with pytest.raises(jobs.RemoteError, match="ValueError: no good"):
        jobs.offload(hp.boom)
    assert jobs.offload(hp.where)[0] == pid


def test_a_function_that_is_not_module_level_is_refused(proc):
    with pytest.raises(TypeError):
        jobs.offload(lambda: 1)


def test_a_process_that_dies_is_a_lost_job_not_a_crash(proc):
    with pytest.raises(jobs.WorkerLost, match="exit code 3"):
        jobs.offload(hp.die)
    assert hp.progress["running"] is False and "Stopped" in hp.progress["error"]  # what it left running does not look alive
    assert jobproc.status()["lastStop"]["reason"]
    assert jobs.offload(hp.add, 1, 1) == 2  # the next call gets a new process
    with pytest.raises(jobs.WorkerLost, match="out of memory"):
        jobs.offload(hp.killed)


def test_a_process_over_its_ceiling_is_stopped(proc, monkeypatch):
    real = memwatch.budget
    monkeypatch.setattr(memwatch, "budget", lambda: {**real(), "ceiling": 150 * memwatch.MB, "reserve": None})
    monkeypatch.setattr(jobproc, "CHECK_EVERY", 0.1)
    t0 = time.time()
    with pytest.raises(jobs.WorkerLost, match="more memory than analysis may use") as e:
        jobs.offload(hp.hog, 400)
    assert e.value.strike and time.time() - t0 < 20
    assert hp.progress["running"] is False


def test_a_server_short_of_memory_stops_the_process_and_holds_the_next_call(proc, monkeypatch):
    state = {"free": 10_000 * memwatch.MB}
    monkeypatch.setattr(memwatch, "budget", lambda: {"limit": 16_000 * memwatch.MB, "used": 16_000 * memwatch.MB - state["free"], "free": state["free"],
                                                     "reserve": 1000 * memwatch.MB, "ceiling": 9000 * memwatch.MB})
    monkeypatch.setattr(jobproc, "CHECK_EVERY", 0.1)
    monkeypatch.setattr(jobproc, "WAIT_EVERY", 0.1)
    out = {}

    def run():
        try:
            jobs.offload(hp.hog, 20)
        except jobs.WorkerLost as e:
            out["e"] = e
    t = threading.Thread(target=run)
    t.start()
    assert _wait(lambda: hp.progress["running"])
    state["free"] = 500 * memwatch.MB  # something filled the server
    t.join(15)
    assert "running out of memory" in str(out["e"]) and out["e"].strike is False  # a 20 MB job is not what filled it
    # the next call waits until memory is free again
    t = threading.Thread(target=lambda: out.update(r=jobs.offload(hp.add, 1, 2)))
    t.start()
    assert _wait(lambda: jobproc.status()["waiting"] is not None)
    assert "r" not in out
    state["free"] = 5000 * memwatch.MB
    t.join(15)
    assert out["r"] == 3 and jobproc.status()["waiting"] is None


def _queue_idle():
    return jobs.status()["running"] is None and not jobs.status()["queued"]


def test_a_lost_job_is_tried_once_more_then_held(proc):
    runs = []

    def job():
        runs.append(1)
        jobs.offload(hp.die)
    jobs.submit("clothing", job)
    assert _wait(lambda: len(runs) == 2 and _queue_idle(), timeout=30)
    held = jobs.status()["held"]
    assert "clothing" in held and "exit code 3" in held["clothing"]["reason"]
    # held: a new start does not reach the job process
    seen = []

    def again():
        try:
            jobs.offload(hp.add, 1, 1)
        except jobs.Held as e:
            seen.append(str(e))
            raise
    jobs.submit("clothing", again)
    assert _wait(lambda: seen and _queue_idle(), timeout=10)
    assert "paused" in seen[0] and "clothing" in jobs.status()["held"]
    # asked for again: it runs
    jobs.release("clothing")
    ok = []
    jobs.submit("clothing", lambda: ok.append(jobs.offload(hp.add, 1, 1)))
    assert _wait(lambda: ok == [2] and _queue_idle(), timeout=10)
    assert not jobs.status()["held"]


def test_a_job_that_swallows_the_loss_is_still_counted(proc):
    runs = []

    def job():
        runs.append(1)
        try:
            jobs.offload(hp.die)
        except Exception:
            pass
    jobs.submit("clothing", job)
    assert _wait(lambda: len(runs) == 2 and _queue_idle(), timeout=30)
    assert "clothing" in jobs.status()["held"]


def test_a_run_that_ends_well_clears_the_count(proc):
    n = []

    def job():
        n.append(1)
        if len(n) == 1:
            jobs.offload(hp.die)
        else:
            jobs.offload(hp.add, 1, 1)
    jobs.submit("clothing", job)
    assert _wait(lambda: len(n) == 2 and _queue_idle(), timeout=30)
    assert not jobs.status()["held"] and not jobs._strikes


def test_asking_for_a_job_lets_a_paused_one_run_again(monkeypatch):
    """Run again, Try again and "Check new and changed photos" (and the MCP tool) are someone asking: the hold goes."""
    from app.routes import tools
    monkeypatch.setattr(tools, "start_prewarm", lambda: None)
    monkeypatch.setattr(tools.events, "kick", lambda: None)
    why = {"reason": "it needed more memory than analysis may use on this server", "at": 1}
    with jobs._lock:
        jobs._held.update(pixels=dict(why), captions=dict(why))
        jobs._strikes.update(pixels=2, captions=2)
    try:
        tools.start_analysis("quality")  # a row of Settings › AI: sharpness shares the "pixels" pass
        assert set(jobs.held()) == {"captions"} and "pixels" not in jobs._strikes
        tools.start_analysis("all")
        assert not jobs.held() and not jobs._strikes
    finally:
        jobs.release()


def test_a_held_job_does_not_stay_running(monkeypatch):
    """A held job that is started (a library change starts every job) ends at once and does not look alive."""
    from app.ai import rotation
    monkeypatch.setattr(config, "JOBS_PROCESS", True)
    monkeypatch.setattr(rotation, "available", lambda: True)
    monkeypatch.setattr(rotation, "_engine", lambda: type("E", (), {"name": "none", "load": lambda self: None})())
    monkeypatch.setattr(jobs, "_current", "rotation")
    with jobs._lock:
        jobs._held["rotation"] = {"reason": "the server was running out of memory", "at": 1}
    try:
        gen = rotation.progress.start()
        with pytest.raises(jobs.Held):
            rotation._job(gen)
        assert not rotation.progress["running"]
    finally:
        jobs.release()
        rotation.progress.cancel()


def test_memwatch_reads_this_machine():
    b = memwatch.budget()
    assert b["limit"] and b["used"] is not None and 0 < b["reserve"] < b["limit"] and b["reserve"] < b["ceiling"] <= b["limit"]
    assert memwatch.tree(os.getpid()) > 10 * memwatch.MB
    assert memwatch.tree(2 ** 30) == 0  # no such process


def test_memwatch_settings(monkeypatch):
    monkeypatch.setattr(config, "MEMORY_RESERVE_MB", 0)
    monkeypatch.setattr(config, "JOBS_MEMORY_MB", 2048)
    b = memwatch.budget()
    assert b["reserve"] is None and b["ceiling"] == 2048 * memwatch.MB


def test_memwatch_takes_the_smallest_cgroup_limit(tmp_path, monkeypatch):
    root = tmp_path / "cg"
    leaf = root / "lxc" / "system.slice" / "iopix.service"
    leaf.mkdir(parents=True)
    (leaf / "memory.max").write_text("max\n")
    (root / "lxc" / "memory.max").write_text(str(2 * 1024 ** 3) + "\n")
    (root / "lxc" / "memory.current").write_text(str(1024 ** 3) + "\n")
    (root / "lxc" / "memory.stat").write_text(f"anon 1\ninactive_file {200 * memwatch.MB}\nactive_file {100 * memwatch.MB}\nslab_reclaimable {24 * memwatch.MB}\n")
    monkeypatch.setattr(memwatch, "CGROUP", root)
    monkeypatch.setattr(memwatch, "_cgroup_dirs", lambda: [leaf, leaf.parent, root / "lxc", root])
    monkeypatch.setattr(memwatch, "_meminfo", lambda: {"MemTotal": 64 * 1024 ** 3, "MemAvailable": 60 * 1024 ** 3})
    assert memwatch.limit() == 2 * 1024 ** 3
    assert memwatch.used() == 1024 ** 3 - 324 * memwatch.MB  # the file cache and reclaimable slab are not "in use"
    assert sys.platform  # (keeps the import used on every platform)
