#!/bin/sh
# Start digiKam Viewer. Usage: ./run.sh [--host 0.0.0.0] [--port 8600]
# The first run creates .venv (with uv when available, else python3 -m venv) and installs
# pyproject.toml (base set only; ./setup.sh installs the AI features). Extra arguments are passed to uvicorn. Also the entry point of the
# launchd agent (tools/com.alex.digikam-viewer.plist) and of nothing else: Docker runs uvicorn directly.
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv .venv && uv pip install -p .venv/bin/python -e .
  else
    python3 -m venv .venv && .venv/bin/python -m pip install -e .
  fi
fi
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8600 "$@"
