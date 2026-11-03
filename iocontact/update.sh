#!/bin/sh
# Update an installed ioContacts in place (a git checkout, /opt/iocontacts/app, or the Proxmox container; Docker users
# pull the image instead). Keeps iocontacts.env and .venv; the database is migrated by the app at start.
#   ./update.sh          latest code from the main branch, packages refreshed, service restarted
#   IOCONTACTS_REF=<sha|branch> ./update.sh
set -e
cd "$(dirname "$0")"
APP="$(pwd)"
REPO="${IOCONTACTS_REPO:-avandeputte/iocontacts}"
REF="${IOCONTACTS_REF:-main}"
case "$REF" in -*|*..*|*/*/*) echo "bad ref: $REF" >&2; exit 1;; esac
say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
[ -x .venv/bin/python ] || { echo "no .venv here; run ./setup.sh first" >&2; exit 1; }
if [ -d .git ]; then
  say "Pulling $REF"
  git fetch -q origin "$REF" && git checkout -q FETCH_HEAD
else
  say "Downloading $REPO@$REF"
  TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
  .venv/bin/python -c 'import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' \
    "https://codeload.github.com/$REPO/tar.gz/$REF" "$TMP/src.tgz"
  mkdir "$TMP/src"; tar -xzf "$TMP/src.tgz" -C "$TMP/src" --strip-components=1
  for d in app static proxmox tests; do rm -rf "${APP:?}/$d"; [ -d "$TMP/src/$d" ] && cp -a "$TMP/src/$d" "$APP/$d"; done
  for f in pyproject.toml README.md setup.sh update.sh run.sh Dockerfile docker-compose.yml; do [ -f "$TMP/src/$f" ] && cp -a "$TMP/src/$f" "$APP/$f"; done
fi
say "Refreshing the Python packages"
.venv/bin/python -m pip install -q -e .
.venv/bin/python -m app.cli migrate
if command -v systemctl >/dev/null && systemctl list-unit-files iocontacts.service >/dev/null 2>&1 && systemctl is-enabled -q iocontacts 2>/dev/null; then
  say "Restarting the service"; systemctl restart iocontacts
fi
say "Updated"
