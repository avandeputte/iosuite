#!/bin/sh
# Turn on text recognition in photos (the portable engine, VISION_ENGINE=portable, the default).
# Installs requirements-ocr.txt (RapidOCR with its models bundled, onnxruntime, headless OpenCV;
# about 60 MB) into .venv. Nothing else is downloaded. Restart the viewer when it finishes.
set -e
cd "$(dirname "$0")"
if command -v uv >/dev/null 2>&1; then uv pip install -p .venv/bin/python -r requirements-ocr.txt
else .venv/bin/python -m pip install -r requirements-ocr.txt; fi
