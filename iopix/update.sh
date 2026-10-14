#!/bin/sh
# Update an installed digiKam Viewer in place (standalone checkout, the Linux installer's
# /opt/digikam-viewer/app, or the Proxmox container; Docker users pull the image instead).
#
#   ./update.sh            fetch the latest code, refresh the packages, restart the service
#   ./update.sh --check    only say whether something newer exists
#
# Keeps digikam-viewer.env, the data folder and the Python environment. A git checkout is
# pulled; an installed copy (no .git) is replaced from the GitHub tarball of the main branch.
# Maintenance > Viewer version runs this same script from the web app.
set -e
cd "$(dirname "$0")"
APP="$(pwd)"
REPO="${DIGIKAM_VIEWER_REPO:-avandeputte/digikam-viewer}"
BRANCH="${DIGIKAM_VIEWER_BRANCH:-main}"
say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
local_commit() { if [ -d .git ]; then git rev-parse HEAD 2>/dev/null; elif [ -f COMMIT ]; then cat COMMIT; else echo unknown; fi; }
remote_commit() { curl -fsSL -H "Accept: application/vnd.github+json" "https://api.github.com/repos/$REPO/commits/$BRANCH" 2>/dev/null | sed -n 's/^  "sha": "\([0-9a-f]*\)",$/\1/p' | head -1; }
if [ "$1" = "--check" ]; then
  L="$(local_commit)"; R="$(remote_commit)"
  [ -n "$R" ] || die "could not reach GitHub"
  if [ "$L" = "$R" ]; then echo "up to date ($(echo "$L" | cut -c1-7))"; else echo "update available: $(echo "$R" | cut -c1-7) (installed $(echo "$L" | cut -c1-7))"; fi
  exit 0
fi

say "Fetching the latest code"
if [ -d .git ]; then
  git pull -q --ff-only origin "$BRANCH" || die "git pull failed (local changes?)"
else
  TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
  # the archive is fetched by commit id, so the code and the recorded COMMIT always match
  R="$(remote_commit)"; [ -n "$R" ] || die "could not reach GitHub"
  curl -fsSL "https://github.com/$REPO/archive/$R.tar.gz" -o "$TMP/src.tgz" || die "download failed"
  tar xzf "$TMP/src.tgz" -C "$TMP"
  SRC="$(ls -d "$TMP"/*/ | head -1)"
  # stage everything first, then swap, so a failure never leaves a half-updated install;
  # keep settings, data and the environment (they live outside these items)
  STAGE="$APP/.update-stage"; rm -rf "$STAGE"; mkdir -p "$STAGE"
  for item in app static pyproject.toml README.md setup.sh run.sh update.sh installer/digikam-viewer.service; do
    [ -e "$SRC/$item" ] && { mkdir -p "$STAGE/$(dirname "$item")"; cp -R "$SRC/$item" "$STAGE/$item"; }
  done
  [ -d "$STAGE/app" ] && [ -d "$STAGE/static" ] || die "the downloaded tarball looks incomplete"
  for item in app static pyproject.toml README.md setup.sh run.sh update.sh; do
    [ -e "$STAGE/$item" ] || continue
    rm -rf "$APP/$item.old"; [ -e "$APP/$item" ] && mv "$APP/$item" "$APP/$item.old"
    mv "$STAGE/$item" "$APP/$item"; rm -rf "$APP/$item.old"
  done
  [ -f "$STAGE/installer/digikam-viewer.service" ] && cp "$STAGE/installer/digikam-viewer.service" "$APP/digikam-viewer.service"
  rm -rf "$STAGE"
  echo "$R" > COMMIT
fi
chmod 755 setup.sh update.sh run.sh 2>/dev/null || true

say "Refreshing the Python packages"
VPY="$APP/.venv/bin/python"
[ -x "$VPY" ] || die "no .venv here; run ./setup.sh first"
G=""
"$VPY" -c "import fastembed" 2>/dev/null && G="$G,search"
"$VPY" -c "import rapidocr" 2>/dev/null && G="$G,ocr"
"$VPY" -c "import onnxruntime" 2>/dev/null && G="$G,objects"
"$VPY" -c "import torch, transformers" 2>/dev/null && G="$G,captions"
G="${G#,}"
pipi() { if command -v uv >/dev/null 2>&1; then uv pip install -q -p "$VPY" "$@"; else "$VPY" -m pip install -q "$@"; fi; }
if [ -n "$G" ]; then pipi -e ".[$G]"; else pipi -e .; fi

say "Restarting the service"
if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet digikam-viewer 2>/dev/null; then
  systemctl restart digikam-viewer && echo "  systemd: restarted"
elif [ "$(uname -s)" = Darwin ]; then
  L="$(launchctl list 2>/dev/null | grep -o 'com\.[a-z.]*digikam-viewer' | head -1)"
  if [ -n "$L" ]; then launchctl kickstart -k "gui/$(id -u)/$L" && echo "  launchd: restarted $L"; else echo "  no service found; restart the viewer yourself"; fi
else
  echo "  no service found; restart the viewer yourself"
fi
say "Updated to v$(sed -n 's/^__version__ = "\([^"]*\)".*/\1/p' app/__init__.py) ($(local_commit | cut -c1-7))"
