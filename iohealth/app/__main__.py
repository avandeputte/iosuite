"""`python -m app`: the server, as run.sh, the service and the container start it. HOST and PORT (config.env) say where
it listens (iosuite_shared.serve: every address, this machine only, or the addresses named); TLS_CERT_FILE and TLS_KEY_FILE serve HTTPS directly instead of behind a reverse proxy."""
from iosuite_shared import serve

from app import config


def main():
    # timeout_keep_alive: the phone sends an upload's batches over one connection, with pauses between them
    # the app reads X-Forwarded-* itself (iosuite-shared: from this machine and the reverse proxies listed under Settings › Security), so uvicorn must not rewrite the peer
    serve.run("app.main:app", config.HOST, config.PORT, proxy_headers=False, ssl_certfile=config.TLS_CERT_FILE or None,
                ssl_keyfile=config.TLS_KEY_FILE or None, timeout_keep_alive=120)


if __name__ == "__main__":
    main()
