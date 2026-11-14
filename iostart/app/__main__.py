"""`python -m app`: the server, as run.sh, the service and the container start it. HOST and PORT (config.env) say where
it listens (iosuite_shared.serve: every address, this machine only, or the addresses named); TLS_CERT_FILE and TLS_KEY_FILE serve HTTPS directly instead of behind a reverse proxy.

A stop (systemctl restart after an update, a reboot, docker stop) waits at most SHUTDOWN_GRACE seconds for open requests:
the Home card's event stream (/api/ha/events) stays open as long as a page or the wall display is showing, and without
a limit uvicorn waits for it forever, so systemd kills the server only after its own 90-second timeout and the page
is down meanwhile."""
from iosuite_shared import serve

from app import config

SHUTDOWN_GRACE = 3


def main():
    # the app reads X-Forwarded-* itself (iosuite-shared: from this machine and the reverse proxies listed under Settings › Security), so uvicorn must not rewrite the peer
    serve.run("app.main:app", config.HOST, config.PORT, proxy_headers=False, ssl_certfile=config.TLS_CERT_FILE or None,
                ssl_keyfile=config.TLS_KEY_FILE or None, timeout_graceful_shutdown=SHUTDOWN_GRACE)


if __name__ == "__main__":
    main()
