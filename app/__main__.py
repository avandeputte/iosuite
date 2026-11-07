"""`python -m app`: the server, as run.sh, the service and the container start it. HOST and PORT (config.env) say where
it listens; TLS_CERT_FILE and TLS_KEY_FILE serve HTTPS directly instead of behind a reverse proxy, and
FORWARDED_ALLOW_IPS says which addresses may tell it the visitor's address and scheme (X-Forwarded-*).

A stop (systemctl restart after an update, a reboot, docker stop) waits at most SHUTDOWN_GRACE seconds for open requests:
the Home card's event stream (/api/ha/events) stays open as long as a page or the wall display is showing, and without
a limit uvicorn waits for it forever, so systemd kills the server only after its own 90-second timeout and the page
is down meanwhile."""
import uvicorn

from app import config

SHUTDOWN_GRACE = 3


def main():
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, proxy_headers=True,
                forwarded_allow_ips=config.FORWARDED_ALLOW_IPS, ssl_certfile=config.TLS_CERT_FILE or None,
                ssl_keyfile=config.TLS_KEY_FILE or None, timeout_graceful_shutdown=SHUTDOWN_GRACE)


if __name__ == "__main__":
    main()
