"""Home Assistant's live feed: one websocket from this server to Home Assistant (/api/websocket), subscribed to
state_changed, so a light switched at the wall shows on the page within a second instead of at the next poll.

The thread keeps the connection up (it reconnects with a growing pause), primes the states with get_states when it
connects, and folds each event into app.homeassistant's copy of the states. Every change bumps `version`; the page's
event stream (GET /api/ha/events) sends the Home card anew when it sees the version move. While the feed is live the
copy never goes stale, so the REST polling stops; when it is down (Home Assistant restarting, no websockets package),
the page falls back to the REST copy, a few seconds old at most.
"""
import json
import logging
import threading
import time

log = logging.getLogger("app.ha_feed")

try:
    from websockets.sync.client import connect as _ws_connect
    from websockets.exceptions import WebSocketException
except ImportError:  # the package is in pyproject; an install from before it still runs, without the live feed
    _ws_connect = None
    WebSocketException = Exception


class Feed:
    def __init__(self, ha):
        self.ha = ha                   # app.homeassistant (the settings, the cache)
        self.version = 0               # bumped on every state change the page may care about
        self.live = False              # connected, authenticated and primed
        self.error = ""                # why it is not live, for Settings
        self.cond = threading.Condition()
        self._thread = None
        self._gen = 0                  # a restart retires the thread of the previous generation
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ control

    def ensure(self) -> None:
        """Starts the thread when Home Assistant is set up and it is not running (called from the requests)."""
        if _ws_connect is None or not self.ha.enabled() or not self.ha.config.HA_FEED:
            return
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._gen += 1
            self._thread = threading.Thread(target=self._run, args=(self._gen,), name="ha-feed", daemon=True)
            self._thread.start()

    def restart(self) -> None:
        """The address or token changed: the running connection is retired and a new one made on the next request."""
        with self._lock:
            self._gen += 1
            self.live = False
            self._thread = None

    def bump(self) -> None:
        with self.cond:
            self.version += 1
            self.cond.notify_all()

    def wait(self, seen: int, timeout: float) -> int:
        """Blocks until the version moves past `seen` (or the timeout); returns the version."""
        with self.cond:
            self.cond.wait_for(lambda: self.version != seen, timeout)
            return self.version

    # ------------------------------------------------------------------ the connection

    def _url(self) -> str:
        base = self.ha.url()
        return ("wss://" if base.startswith("https://") else "ws://") + base.split("://", 1)[-1] + "/api/websocket"

    def _run(self, gen: int) -> None:
        pause = 2
        while gen == self._gen:
            try:
                self._session(gen)
                pause = 2
            except (OSError, WebSocketException, ValueError, KeyError, TypeError) as e:
                self.error = str(e)[:160] or e.__class__.__name__
                log.warning("Home Assistant's live feed: %s (again in %ss)", self.error, pause)
            finally:
                if self.live:
                    self.live = False
                    self.ha.feed_down()
                    self.bump()
            if gen != self._gen:
                break
            time.sleep(pause)
            pause = min(pause * 2, 60)

    def _session(self, gen: int) -> None:
        tok = self.ha.token()
        with _ws_connect(self._url(), open_timeout=10, close_timeout=3, max_size=16 * 1024 * 1024) as ws:
            hello = json.loads(ws.recv(timeout=10))
            if hello.get("type") != "auth_required":
                raise ValueError(f"unexpected greeting: {hello.get('type')}")
            ws.send(json.dumps({"type": "auth", "access_token": tok}))
            ok = json.loads(ws.recv(timeout=10))
            if ok.get("type") != "auth_ok":
                raise ValueError("Home Assistant refused the token")
            ws.send(json.dumps({"id": 1, "type": "subscribe_events", "event_type": "state_changed"}))
            ws.send(json.dumps({"id": 2, "type": "get_states"}))
            nid = 3
            last = time.time()
            while gen == self._gen:
                try:
                    raw = ws.recv(timeout=30)
                except TimeoutError:
                    if time.time() - last > 90:
                        raise OSError("no answer from Home Assistant for 90 seconds")
                    ws.send(json.dumps({"id": nid, "type": "ping"}))
                    nid += 1
                    continue
                last = time.time()
                msg = json.loads(raw)
                t = msg.get("type")
                if t == "result" and msg.get("id") == 2 and msg.get("success") and isinstance(msg.get("result"), list):
                    self.ha.prime(msg["result"])
                    self.live, self.error = True, ""
                    log.info("Home Assistant's live feed is up (%d entities)", len(msg["result"]))
                    self.bump()
                elif t == "result" and msg.get("id") == 1 and not msg.get("success"):
                    raise ValueError(f"subscribe_events refused: {(msg.get('error') or {}).get('message')}")
                elif t == "event":
                    data = (msg.get("event") or {}).get("data") or {}
                    eid, new = data.get("entity_id"), data.get("new_state")
                    if eid and self.ha.apply(eid, new):
                        self.bump()
