"""`python -m app`: the server, as run.sh, the service and the container start it. HOST and PORT (config.env) say where
it listens; TLS_CERT_FILE and TLS_KEY_FILE serve HTTPS directly instead of behind a reverse proxy."""
import uvicorn

from app import config


def main():
    # the app reads X-Forwarded-* itself (iosuite-shared: from this machine and the reverse proxies listed under Settings › Security), so uvicorn must not rewrite the peer
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, proxy_headers=False, ssl_certfile=config.TLS_CERT_FILE or None,
                ssl_keyfile=config.TLS_KEY_FILE or None)


if __name__ == "__main__":
    main()
