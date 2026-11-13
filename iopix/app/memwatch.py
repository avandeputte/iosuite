"""How much memory this server may use, how much is in use, and how much a process tree holds.

The background jobs load models that take gigabytes, and a server that runs in a container has a hard limit:
past it the kernel kills a process, and when that process is the web app the site is gone. The job queue
(jobs.py, jobproc.py) asks here before it starts a job and while one runs, so a job is stopped by the app, with
a message, before the kernel has to choose.

Everything is read from /proc and the cgroup files (Linux); anywhere else, or when they cannot be read, the
answers are None and the callers simply do not limit anything.

- limit():  the smallest memory limit that applies to this process: its cgroups' memory.max, walking up to the
            container's root, else the machine's (or the container's, through lxcfs) MemTotal.
- used():   what counts against that limit, without the file cache and the reclaimable kernel caches (the kernel
            gives those back under pressure).
- tree(pid): resident memory of a process and its children (a job's ffmpeg or exiftool count as the job's).
- budget(): the numbers the queue acts on, with the two settings applied (config.MEMORY_RESERVE_MB, JOBS_MEMORY_MB).
"""
import os
from pathlib import Path

from app import config

CGROUP = Path("/sys/fs/cgroup")
MB = 1024 * 1024
RESERVE_SHARE, RESERVE_MIN = 0.08, 256 * MB   # free memory the queue keeps: 8% of the limit, at least 256 MB
CEILING_SHARE = 0.6                             # what the job process itself may hold: 60% of the limit


def _int(path: Path):
    try:
        text = path.read_text().strip()
    except OSError:
        return None
    return int(text) if text.isdigit() else None  # "max": no limit at this level


def _meminfo() -> dict:
    out = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, _, rest = line.partition(":")
            v = rest.split()
            if v and v[0].isdigit():
                out[k] = int(v[0]) * 1024
    except OSError:
        pass
    return out


def _cgroup_dirs() -> list:
    """This process's cgroup (v2) and its parents, innermost first; empty where there is none to read."""
    try:
        line = next(ln for ln in Path("/proc/self/cgroup").read_text().splitlines() if ln.startswith("0::"))
    except (OSError, StopIteration):
        return []
    d = CGROUP / line[3:].strip().lstrip("/")
    out = []
    while True:
        out.append(d)
        if d == CGROUP or CGROUP not in d.parents:
            break
        d = d.parent
    return out


def _limited_cgroup():
    """(directory, limit) of the cgroup with the smallest memory.max above this process, or (None, None)."""
    best = (None, None)
    for d in _cgroup_dirs():
        n = _int(d / "memory.max")
        if n is not None and (best[1] is None or n < best[1]):
            best = (d, n)
    return best


def limit():
    """Bytes this server may use, or None when that cannot be told."""
    total = _meminfo().get("MemTotal")
    _d, n = _limited_cgroup()
    if n is not None and total is not None:
        return min(n, total)
    return n if n is not None else total


def used():
    """Bytes in use against limit(), the file cache left out; None when that cannot be told."""
    d, n = _limited_cgroup()
    mi = _meminfo()
    total = mi.get("MemTotal")
    if d is not None and (total is None or n <= total):
        cur = _int(d / "memory.current")
        if cur is not None:
            cache = 0
            try:
                for line in (d / "memory.stat").read_text().splitlines():
                    k, _, v = line.partition(" ")
                    if k in ("inactive_file", "active_file", "slab_reclaimable"):
                        cache += int(v)
            except (OSError, ValueError):
                cache = 0
            return max(0, cur - cache)
    if total is not None and "MemAvailable" in mi:
        return max(0, total - mi["MemAvailable"])
    return None


_PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") and "SC_PAGE_SIZE" in os.sysconf_names else 4096


def _rss(pid: int) -> int:
    try:
        return int(Path(f"/proc/{pid}/statm").read_text().split()[1]) * _PAGE
    except (OSError, ValueError, IndexError):
        return 0


def _children(pid: int) -> list:
    out = []
    try:
        for task in Path(f"/proc/{pid}/task").iterdir():
            out += [int(c) for c in (task / "children").read_text().split()]
    except (OSError, ValueError):
        pass
    return out


def tree(pid: int) -> int:
    """Resident bytes of `pid` and every process under it (0 when it is gone, or off Linux)."""
    seen, todo, total = set(), [pid], 0
    while todo and len(seen) < 500:
        p = todo.pop()
        if p in seen:
            continue
        seen.add(p)
        total += _rss(p)
        todo += _children(p)
    return total


def budget() -> dict:
    """{limit, used, free, reserve, ceiling} in bytes; all None where memory cannot be read (nothing is limited then).
    reserve: the free memory below which no job starts and the job process is stopped. ceiling: the most the job
    process may hold itself. Both are a share of the limit unless set (MEMORY_RESERVE_MB, JOBS_MEMORY_MB; 0 turns
    the one off)."""
    lim, use = limit(), used()
    if lim is None or use is None:
        return {"limit": lim, "used": use, "free": None, "reserve": None, "ceiling": None}
    reserve = config.MEMORY_RESERVE_MB * MB if config.MEMORY_RESERVE_MB >= 0 else max(RESERVE_MIN, int(lim * RESERVE_SHARE))
    ceiling = config.JOBS_MEMORY_MB * MB if config.JOBS_MEMORY_MB >= 0 else int(lim * CEILING_SHARE)
    return {"limit": lim, "used": use, "free": max(0, lim - use), "reserve": min(reserve, lim // 2) or None, "ceiling": ceiling or None}


def gb(n) -> str:
    """Bytes as the status texts show them: "3.2 GB"."""
    return f"{n / (1024 ** 3):.1f} GB"
