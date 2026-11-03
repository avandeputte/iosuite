#!/bin/sh
# Start ioCalendar in the foreground with the settings in iocalendar.env. ./setup.sh first.
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "run ./setup.sh first" >&2; exit 1; }
PORT="$(sed -n 's/^PORT=//p' iocalendar.env 2>/dev/null | tail -n 1)"
exec .venv/bin/python -m uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8620}" --proxy-headers "$@"
