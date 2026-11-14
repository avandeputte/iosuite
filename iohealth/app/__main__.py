"""`python -m app`: the server, as run.sh, the service and the container start it (iosuite_shared.serve.app)."""
from iosuite_shared import serve

from app import config


def main():
    serve.app(config, timeout_keep_alive=120)  # the phone sends an upload's batches over one connection, with pauses between them


if __name__ == "__main__":
    main()
