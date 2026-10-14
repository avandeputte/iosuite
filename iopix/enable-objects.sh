#!/bin/sh
# Turn on object detection (80 everyday object types with boxes; the Objects filter).
# Installs requirements-objects.txt (numpy, onnxruntime) into .venv and downloads YOLOX-S
# (35 MB, Apache-2.0) from the YOLOX project's GitHub releases into data/models.
# Runs locally. Restart the viewer when it finishes.
set -e
cd "$(dirname "$0")"
if command -v uv >/dev/null 2>&1; then uv pip install -p .venv/bin/python -r requirements-objects.txt
else .venv/bin/python -m pip install -r requirements-objects.txt; fi
exec .venv/bin/python -m app.models download yolox
