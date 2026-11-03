#!/bin/sh
# Start ionotes in the foreground. Usage: ./run.sh [--host 0.0.0.0] [--port 8610]
# The first run creates .venv (with uv when available, else python3 -m venv) and installs pyproject.toml.
# The settings setup.sh wrote to ionotes.env are loaded when the file exists (variables already in the
# environment win). Extra arguments are passed to uvicorn. The services setup.sh installs (launchd, systemd)
# and Docker run uvicorn directly instead.
set -e
cd "$(dirname "$0")"
if [ -f ionotes.env ]; then
  while IFS= read -r line; do
    case "$line" in ''|'#'*) continue;; *=*) ;; *) continue;; esac
    k="${line%%=*}"; case "$k" in ''|*[!A-Za-z0-9_]*) continue;; esac
    eval "[ -n \"\${$k+x}\" ]" || export "$line"
  done < ionotes.env
fi
if [ ! -x .venv/bin/python ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv .venv && uv pip install -p .venv/bin/python -e .
  else
    python3 -m venv .venv && .venv/bin/python -m pip install -e .
  fi
fi
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8610}" --proxy-headers "$@"
