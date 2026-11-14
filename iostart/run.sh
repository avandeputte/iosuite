#!/bin/sh
# Start ioStart in the foreground, with the settings in config.env (HOST and PORT there say where it listens; the
# default port is 8630). The first run creates .venv (with uv when available, else python3 -m venv) and installs the
# app; ./setup.sh does that too and also writes config.env. The service setup.sh installs and the container run the
# same `python -m app`.
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  # the suite's shared library first, from the same commit (shared/ inside an installed copy, beside this folder in a
  # checkout): installed after the app, pip would look for iosuite-shared on PyPI, where anyone can take that name
  SHARED=shared; [ -f shared/pyproject.toml ] || SHARED=../shared
  [ -f "$SHARED/pyproject.toml" ] || { echo "the suite's shared library is missing: this folder needs the shared/ folder of the suite's repository beside it" >&2; exit 1; }
  if command -v uv >/dev/null 2>&1; then
    uv venv .venv && uv pip install -p .venv/bin/python -e "$SHARED" && uv pip install -p .venv/bin/python -e .
  else
    python3 -m venv .venv && .venv/bin/python -m pip install -e "$SHARED" && .venv/bin/python -m pip install -e .
  fi
fi
exec .venv/bin/python -m app "$@"
