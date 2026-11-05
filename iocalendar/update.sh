#!/bin/sh
# Update an installed ioCalendar in place (a git checkout, /opt/iocalendar/app, or the Proxmox container; Docker users
# pull the image instead). Keeps config.env and .venv; the database is migrated by the app as it starts.
#
#   ./update.sh            fetch the latest code, refresh the packages, restart the service
#   ./update.sh --check    only say whether something newer exists
#   ./update.sh --force    reinstall and restart even when the installed commit is already the latest
#   IOCALENDAR_REF=<sha|branch> ./update.sh    install that commit instead of the tip of main
#   IOCALENDAR_RESULT=<file>   write the outcome ("ok: ..." or "error: ...") there before the restart, so the web app
#                              can show it afterwards (Settings › Server runs this same script)
#
# The order protects the install: the Python packages the new version asks for are installed first, and the code moves
# only once that succeeded, so a failed package install leaves the installed version running as it was; a failed swap
# puts the previous files back.
set -e
cd "$(dirname "$0")"
APP="$(pwd)"
REPO="${IOCALENDAR_REPO:-avandeputte/iocalendar}"
BRANCH="${IOCALENDAR_BRANCH:-main}"
REF="${IOCALENDAR_REF:-$BRANCH}"
RESULT="${IOCALENDAR_RESULT:-}"
case "$REF" in -*|*..*|*/*/*) printf 'error: bad ref: %s\n' "$REF" >&2; exit 1;; esac
FORCE=0; CHECK=0
for a in "$@"; do case "$a" in --force) FORCE=1;; --check) CHECK=1;; *) printf 'error: unknown option %s (--check, --force)\n' "$a" >&2; exit 2;; esac; done
TMP=""; NOTED=0; STAGE=""
cleanup() { rc=$?; [ -n "$TMP" ] && rm -rf "${TMP:?}"; [ $rc -ne 0 ] && [ "$NOTED" = 0 ] && [ -n "$RESULT" ] && printf 'error: update.sh failed (exit %s); see the log\n' "$rc" > "$RESULT" 2>/dev/null; true; }
trap cleanup EXIT
say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
note() { [ -n "$RESULT" ] && printf '%s\n' "$*" > "$RESULT" 2>/dev/null || true; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; note "error: $*"; NOTED=1; exit 1; }
local_commit() { if [ -d .git ]; then git rev-parse HEAD 2>/dev/null; elif [ -f COMMIT ]; then cat COMMIT; else echo unknown; fi; }
PYF="$(ls -d .venv/bin/python 2>/dev/null || command -v python3)"
fetch() { "$PYF" -c 'import sys, urllib.request
req = urllib.request.Request(sys.argv[1], headers={"User-Agent": "iocalendar-update"})
with urllib.request.urlopen(req, timeout=60) as r, open(sys.argv[2], "wb") as f:
    f.write(r.read())' "$1" "$2"; }
remote_commit() { "$PYF" -c 'import sys, json, urllib.request
req = urllib.request.Request(sys.argv[1], headers={"User-Agent": "iocalendar-update", "Accept": "application/vnd.github+json"})
with urllib.request.urlopen(req, timeout=30) as r:
    print(json.load(r)["sha"])' "https://api.github.com/repos/$REPO/commits/${1:-$BRANCH}" 2>/dev/null; }

if [ "$CHECK" = 1 ]; then
  L="$(local_commit)"; R="$(remote_commit "$REF")" || R=""
  [ -n "$R" ] || die "could not reach GitHub (api.github.com) from here, or no such commit: $REF"
  if [ "$L" = "$R" ]; then echo "up to date ($(echo "$L" | cut -c1-7))"; else echo "update available: $(echo "$R" | cut -c1-7) (installed $(echo "$L" | cut -c1-7))"; fi
  exit 0
fi

VPY="$APP/.venv/bin/python"
[ -x "$VPY" ] || die "no .venv here; run ./setup.sh first"
TMP="$(mktemp -d)"

say "Fetching the latest code"
if [ -d .git ]; then
  git fetch -q origin "$REF" || die "git fetch failed (could not reach GitHub?)"
  if [ "$FORCE" = 0 ] && [ "$(git rev-parse HEAD)" = "$(git rev-parse FETCH_HEAD)" ]; then
    say "Already up to date ($(local_commit | cut -c1-7)); nothing to do"; note "ok: already up to date ($(local_commit | cut -c1-7))"; exit 0
  fi
  git merge-base --is-ancestor HEAD FETCH_HEAD || die "this checkout has commits that are not on $REF (not a fast-forward); update it by hand"
  git diff --name-only HEAD -- | while IFS= read -r f; do
    [ -n "$f" ] && ! git diff --quiet HEAD FETCH_HEAD -- "$f" && { printf '  changed here and by the update: %s\n' "$f" >&2; exit 1; }
    :
  done || die "local changes to files the update also changes (git stash them first)"
  git show FETCH_HEAD:pyproject.toml > "$TMP/pyproject.toml" 2>/dev/null || die "the fetched commit has no pyproject.toml"
else
  R="$(remote_commit "$REF")" || R=""; [ -n "$R" ] || die "could not reach GitHub (or no such commit: $REF)"
  if [ "$FORCE" = 0 ] && [ "$R" = "$(local_commit)" ]; then
    say "Already up to date ($(echo "$R" | cut -c1-7)); nothing to do"; note "ok: already up to date ($(echo "$R" | cut -c1-7))"; exit 0
  fi
  fetch "https://github.com/$REPO/archive/$R.tar.gz" "$TMP/src.tgz" || die "download failed"
  tar xzf "$TMP/src.tgz" -C "$TMP"
  SRC="$(ls -d "$TMP"/*/ | head -1)"
  STAGE="$APP/.update-stage"; rm -rf "${STAGE:?}"; mkdir -p "$STAGE"
  for item in app static proxmox pyproject.toml README.md LICENSE setup.sh run.sh update.sh Dockerfile docker-compose.yml config.env.example; do
    [ -e "$SRC/$item" ] && cp -R "$SRC/$item" "$STAGE/$item"
  done
  [ -d "$STAGE/app" ] && [ -d "$STAGE/static" ] && [ -f "$STAGE/pyproject.toml" ] || { rm -rf "${STAGE:?}"; die "the downloaded archive looks incomplete"; }
  cp "$STAGE/pyproject.toml" "$TMP/pyproject.toml"
fi

say "Refreshing the Python packages (the new version's, before the code moves)"
"$VPY" - "$TMP/pyproject.toml" > "$TMP/requirements.txt" <<'PYEOF' || die "could not read the fetched pyproject.toml"
import re, sys
try:
    import tomllib
    with open(sys.argv[1], "rb") as f:
        deps = tomllib.load(f).get("project", {}).get("dependencies", [])
except ImportError:  # Python 3.10
    text = open(sys.argv[1], encoding="utf-8").read()
    m = re.search(r'^\s*dependencies\s*=\s*\[((?:[^\]"]|"[^"]*")*)\]', text, re.M)
    deps = re.findall(r'"([^"]+)"', m.group(1)) if m else []
print("\n".join(deps))
PYEOF
"$VPY" -m pip install -q --disable-pip-version-check -r "$TMP/requirements.txt" || { [ -n "$STAGE" ] && rm -rf "${STAGE:?}"; die "installing the Python packages failed; the installed version is unchanged"; }

say "Installing the new code"
if [ -d .git ]; then
  git merge -q --ff-only FETCH_HEAD || die "git merge failed (local changes?); the packages were refreshed, the code is unchanged"
else
  MOVED=""
  swap_back() { for item in $MOVED; do rm -rf "${APP:?}/${item:?}"; [ -e "$APP/$item.old" ] && mv "$APP/$item.old" "$APP/$item"; done; rm -rf "${STAGE:?}"; }
  for item in app static proxmox pyproject.toml README.md LICENSE setup.sh run.sh update.sh Dockerfile docker-compose.yml config.env.example; do
    [ -e "$STAGE/$item" ] || continue
    rm -rf "${APP:?}/${item:?}.old"
    if [ -e "$APP/$item" ]; then mv "$APP/$item" "$APP/$item.old" || { swap_back; die "could not set $item aside; the previous files are back"; }; fi
    MOVED="$MOVED $item"
    mv "$STAGE/$item" "$APP/$item" || { swap_back; die "could not install $item; the previous files are back"; }
  done
  for item in $MOVED; do rm -rf "${APP:?}/${item:?}.old"; done
  rm -rf "${STAGE:?}"
  echo "$R" > COMMIT
fi
chmod 755 setup.sh update.sh run.sh 2>/dev/null || true
"$VPY" -m pip install -q --disable-pip-version-check --no-deps -e . 2>/dev/null || echo "  note: the package metadata could not be refreshed; ioCalendar runs regardless"
"$VPY" -m app.cli migrate >/dev/null 2>&1 || echo "  note: the database could not be updated now; ioCalendar does it when it starts"

NEWV="$(sed -n 's/^__version__ = "\([^"]*\)".*/\1/p' app/__init__.py)"
# the outcome goes to the result file now: the restart below also ends this script when the web app started it
note "ok: updated to v$NEWV on $(date '+%Y-%m-%d %H:%M')"

say "Restarting the service"
restart_unit() { if [ "$(id -u)" != 0 ] && command -v sudo >/dev/null 2>&1; then sudo -n systemctl restart "$1"; else systemctl restart "$1"; fi; }
if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet iocalendar 2>/dev/null; then
  if restart_unit iocalendar 2>/dev/null; then echo "  systemd: restarted iocalendar"
  elif [ -n "$RESULT" ]; then echo "  the web app restarts itself (systemd starts it again)"
  else echo "  could not restart it from here; run: sudo systemctl restart iocalendar"; fi
elif [ "$(uname -s)" = Darwin ] && L="$(launchctl list 2>/dev/null | grep -o 'com\.[a-z.]*iocalendar' | head -1)" && [ -n "$L" ]; then
  launchctl kickstart -k "gui/$(id -u)/$L" && echo "  launchd: restarted $L"
else
  echo "  no service found; restart ioCalendar yourself"
fi
say "Updated to v$NEWV ($(local_commit | cut -c1-7))"
