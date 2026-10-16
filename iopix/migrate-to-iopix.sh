#!/bin/bash
# Moves an install made under the old name (digiKam Viewer) to the new one, iopix:
#   /opt/digikam-viewer           -> /opt/iopix   (app, data, Python environment; a symlink stays behind)
#   app/digikam-viewer.env        -> app/iopix.env (paths inside updated)
#   digikam-viewer.service        -> iopix.service (same user, port and settings)
# and brings the code up to date first. Settings, users, favorites, edits, the library copy, AI
# results, thumbnails and models all live in the data folder and move with it unchanged.
#
# Run as root on the machine (or inside the Proxmox container) where the viewer runs:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iopix/main/migrate-to-iopix.sh)"
#   bash migrate-to-iopix.sh [OLD_DIR] [NEW_DIR]      (defaults /opt/digikam-viewer /opt/iopix)
# Safe to run twice: a finished migration is detected and left alone.
set -euo pipefail
OLD="${1:-/opt/digikam-viewer}"; NEW="${2:-/opt/iopix}"
say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || die "run this as root"
if [ -L "$OLD" ] && [ -d "$NEW/app" ]; then say "Already migrated: $NEW (with $OLD pointing to it)"; exit 0; fi
[ -d "$OLD/app" ] || die "no install found at $OLD/app"
[ -e "$NEW" ] && die "$NEW already exists; move it away first"
UNIT_OLD=/etc/systemd/system/digikam-viewer.service; UNIT_NEW=/etc/systemd/system/iopix.service
PORT=8600; [ -f "$UNIT_OLD" ] && PORT="$(sed -n 's/.*--port \([0-9]*\).*/\1/p' "$UNIT_OLD" | head -1)"; PORT="${PORT:-8600}"

say "Bringing the code up to date (the renamed version understands both layouts)"
IOPIX_REPO=avandeputte/iopix DIGIKAM_VIEWER_REPO=avandeputte/iopix sh "$OLD/app/update.sh" --force || die "update.sh failed; nothing was moved"

say "Stopping the old service"
systemctl stop digikam-viewer 2>/dev/null || true
for i in 1 2 3 4 5 6 7 8 9 10; do ss -ltn 2>/dev/null | grep -q ":$PORT " || break; sleep 1; done

say "Moving $OLD to $NEW"
mv "$OLD" "$NEW"
ln -s "$NEW" "$OLD"  # anything still naming the old path (scripts inside the Python environment) keeps working

say "Settings file"
if [ -f "$NEW/app/digikam-viewer.env" ]; then
  sed "s#$OLD#$NEW#g" "$NEW/app/digikam-viewer.env" > "$NEW/app/iopix.env"
  chmod 600 "$NEW/app/iopix.env"
  OWNER="$(stat -c %U "$NEW/app/digikam-viewer.env" 2>/dev/null || echo root)"; chown "$OWNER" "$NEW/app/iopix.env" 2>/dev/null || true
  mv "$NEW/app/digikam-viewer.env" "$NEW/app/digikam-viewer.env.before-rename"
  echo "  $NEW/app/iopix.env (the old file is kept as digikam-viewer.env.before-rename)"
fi
[ -f "$NEW/app/digikam-viewer.service" ] && rm -f "$NEW/app/digikam-viewer.service"

say "Service"
if [ -f "$UNIT_OLD" ]; then
  sed -e "s#$OLD#$NEW#g" -e "s#digikam-viewer\.env#iopix.env#g" -e "s#^Description=.*#Description=iopix#" "$UNIT_OLD" > "$UNIT_NEW"
  systemctl disable digikam-viewer 2>/dev/null || true
  rm -f "$UNIT_OLD"
else
  cat > "$UNIT_NEW" <<UEOF
[Unit]
Description=iopix
After=network.target

[Service]
Type=simple
User=root
EnvironmentFile=$NEW/app/iopix.env
WorkingDirectory=$NEW/app
ExecStart=$NEW/app/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=5
Nice=5

[Install]
WantedBy=multi-user.target
UEOF
fi
systemctl daemon-reload
systemctl enable --now iopix
echo "  iopix.service enabled and started"

# the Proxmox helper's `update` command inside the container points at the script it was created from
if [ -f /usr/bin/update ] && grep -q "digikam-viewer" /usr/bin/update; then
  sed -i -e "s#avandeputte/digikam-viewer#avandeputte/iopix#g" -e "s#ct/digikam-viewer\.sh#ct/iopix.sh#g" /usr/bin/update
  echo "  the container's update command now uses proxmox/ct/iopix.sh"
fi

say "Refreshing the Python package paths"
(cd "$NEW/app" && { if command -v uv >/dev/null 2>&1; then uv pip install -q -p .venv/bin/python --no-deps -e .; else .venv/bin/python -m pip install -q --no-deps -e .; fi; } ) \
  && systemctl restart iopix || echo "  skipped (the symlink at $OLD covers it)"

say "Waiting for the viewer"
for i in $(seq 1 60); do
  V="$("$NEW/app/.venv/bin/python" -c "import json,urllib.request; s=json.load(urllib.request.urlopen('http://127.0.0.1:$PORT/api/status', timeout=3)); print(s.get('appVersion',''), s.get('commit',''))" 2>/dev/null || true)"
  [ -n "$V" ] && { say "iopix $V is running on port $PORT from $NEW"; exit 0; }
  sleep 2
done
die "the service did not answer on port $PORT; see: journalctl -u iopix -n 50"
