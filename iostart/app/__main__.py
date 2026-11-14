"""`python -m app`: the server, as run.sh, the service and the container start it (iosuite_shared.serve.app).

A stop (systemctl restart after an update, a reboot, docker stop) waits at most SHUTDOWN_GRACE seconds for open requests:
the Home card's event stream (/api/ha/events) stays open as long as a page or the wall display is showing, and without
a limit uvicorn waits for it forever, so systemd kills the server only after its own 90-second timeout and the page
is down meanwhile."""
from iosuite_shared import serve

from app import config

SHUTDOWN_GRACE = 3


def main():
    serve.app(config, timeout_graceful_shutdown=SHUTDOWN_GRACE)


if __name__ == "__main__":
    main()
