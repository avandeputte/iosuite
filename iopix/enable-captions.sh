#!/bin/sh
# Turn on photo descriptions (a searchable one-sentence caption per photo).
# Installs requirements-captions.txt (PyTorch and transformers; torch alone is over 500 MB)
# into .venv and downloads BLIP base (Salesforce, about 950 MB) from the Hugging Face hub
# into data/models. Runs locally afterwards, on the Mac's GPU when available.
# Restart the viewer when it finishes. CAPTIONS=0 turns the job off again.
set -e
cd "$(dirname "$0")"
if command -v uv >/dev/null 2>&1; then uv pip install -p .venv/bin/python -r requirements-captions.txt
else .venv/bin/python -m pip install -r requirements-captions.txt; fi
# the viewer itself runs the hub library offline; downloading needs it online for this one command
HF_HUB_OFFLINE=0 .venv/bin/python -m app.models download blip
