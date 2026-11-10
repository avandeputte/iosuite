"""Housekeeping an app does on its own while it runs: purging what was deleted long ago, pruning a cache."""
import asyncio
import logging

from starlette.concurrency import run_in_threadpool

log = logging.getLogger("iosuite_shared.chores")


def start(fn, every_s: float = 86400, name: str = None, first_s: float = 5) -> asyncio.Task:
    """Run `fn` (blocking: it gets a thread) `first_s` seconds after the app started (after the start-up work, not in
    its way) and then every `every_s` seconds for as long as the app runs. A run that fails is logged and the next one
    still happens. Call it in the app's lifespan and cancel the task it returns at shutdown."""
    name = name or getattr(fn, "__name__", "chore")

    async def loop():
        await asyncio.sleep(first_s)
        while True:
            try:
                await run_in_threadpool(fn)
            except Exception:  # noqa: BLE001 - housekeeping never takes the app down
                log.exception("%s failed (tried again at the next run)", name)
            await asyncio.sleep(every_s)

    return asyncio.create_task(loop(), name=name)
