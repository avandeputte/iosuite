#!/bin/sh
# Turn on content search ("dog on a beach"), "More photos like this" and Detected content.
# Installs requirements-search.txt (fastembed, onnxruntime, numpy) into .venv and downloads
# a model from the Hugging Face hub into data/models. Everything runs locally afterwards.
#   ./enable-search.sh            CLIP ViT-B/32, about 600 MB (the default model)
#   ./enable-search.sh siglip2    SigLIP 2 base, about 1.5 GB; choose it under Settings > AI analysis,
#                                 the library is re-indexed in the background and search switches when done
# Restart the viewer when it finishes.
set -e
cd "$(dirname "$0")"
MODEL="${1:-clip}"
if command -v uv >/dev/null 2>&1; then uv pip install -p .venv/bin/python -r requirements-search.txt
else .venv/bin/python -m pip install -r requirements-search.txt; fi
# the viewer itself runs the hub library offline; downloading needs it online for this one command
HF_HUB_OFFLINE=0 .venv/bin/python -m app.models download "$MODEL"
