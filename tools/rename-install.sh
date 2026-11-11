#!/bin/bash
# One-time move of a running install from the old plural names to the singular ones:
#   ionotes -> ionote, iotasks -> iotask, iocontacts -> iocontact
# Run it once on each machine (or LXC container) that runs one of these apps, AFTER the app is updated to the
# renamed version (ioNote 1.39.0, ioTask 0.8.0, ioContact 0.45.0 or later). Safe to run twice: it skips what is done.
#
#   curl -fsSLO https://raw.githubusercontent.com/avandeputte/iosuite/main/tools/rename-install.sh
#   sudo bash rename-install.sh --dry-run  # only say what it would do
#   sudo bash rename-install.sh            # do it
# (on macOS, without sudo: the launch agents are the user's own)
#
# Per app it finds, it:
#   - Linux/systemd: stops <old>.service, moves /opt/<old> to /opt/<new>, writes <new>.service with the new paths,
#     removes <old>.service, starts <new>.service
#   - macOS/launchd: replaces the net.iothing.<old>.server launch agent with net.iothing.<new>.server
#   - in the app's data folder: <old>.log* -> <new>.log*, and ioNote's SQLite file ionotes.db -> ionote.db
#   - in config.env: IONOTES_* / IOTASKS_* / IOCONTACTS_* keys -> IONOTE_* / IOTASK_* / IOCONTACT_*
#   - Docker: prints the steps (container and volume names), it does not touch containers itself
# The databases (notes, tasks, contacts) and their tables are not touched; the shared tables move by themselves
# when the apps start on iosuite-shared 0.44.0.
set -euo pipefail
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
run() { if [ "$DRY" = 1 ]; then printf '  would run: %s\n' "$*"; else "$@"; fi; }
say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
found=0

move_data() {  # $1 app dir, $2 old, $3 new
  local d="$1/data"
  [ -d "$d" ] || return 0
  for f in "$d/$2".log*; do [ -e "$f" ] && run mv "$f" "$d/$3${f#"$d/$2"}"; done
  if [ -e "$d/$2.db" ] && [ ! -e "$d/$3.db" ]; then run mv "$d/$2.db" "$d/$3.db"; fi
  local c="$1/config.env" O N
  O="$(printf '%s' "$2" | tr '[:lower:]' '[:upper:]')"; N="$(printf '%s' "$3" | tr '[:lower:]' '[:upper:]')"
  if [ -f "$c" ] && grep -q "^[# ]*${O}_" "$c"; then run sed -i.bak -E "s/^([# ]*)${O}_/\1${N}_/" "$c"; fi
  if [ -f "$c" ] && grep -q "avandeputte/$2\b" "$c"; then run sed -i.bak -E "s#avandeputte/$2\b#avandeputte/$3#" "$c"; fi
  if [ -f "$c" ] && grep -q "dc=$2" "$c"; then run sed -i.bak "s/dc=$2/dc=$3/" "$c"; fi
}

for pair in ionotes:ionote iotasks:iotask iocontacts:iocontact; do
  old="${pair%%:*}"; new="${pair##*:}"

  # ---- Linux, systemd
  if [ -f "/etc/systemd/system/$old.service" ]; then
    found=1; say "$old -> $new (systemd)"
    unit="/etc/systemd/system/$old.service"
    run systemctl stop "$old"
    run systemctl disable -q "$old" || true
    if [ -d "/opt/$old" ] && [ ! -e "/opt/$new" ]; then run mv "/opt/$old" "/opt/$new"; fi
    appdir="$(sed -n 's/^WorkingDirectory=//p' "$unit")"; appdir="${appdir//\/opt\/$old/\/opt\/$new}"
    if [ "$DRY" = 1 ]; then echo "  would write /etc/systemd/system/$new.service (paths /opt/$old -> /opt/$new)"
    else sed -e "s#/opt/$old#/opt/$new#g" -e "s/^Description=.*/Description=$(sed -n 's/^Description=//p' "$unit" | sed 's/s$//')/" "$unit" > "/etc/systemd/system/$new.service"; fi
    run rm -f "$unit"
    if [ "$DRY" = 1 ]; then appdir="${appdir//\/opt\/$new/\/opt\/$old}"; fi
    [ -n "$appdir" ] && move_data "$appdir" "$old" "$new"
    run systemctl daemon-reload
    run systemctl enable -q --now "$new"
    [ "$DRY" = 1 ] || { sleep 2; systemctl is-active -q "$new" && echo "  $new is running" || echo "  $new did not start: journalctl -u $new -n 50"; }
  elif [ -d "/opt/$old" ]; then
    found=1; say "$old -> $new (no service: folder only)"
    [ -e "/opt/$new" ] || run mv "/opt/$old" "/opt/$new"
    if [ "$DRY" = 1 ]; then move_data "/opt/$old/app" "$old" "$new"; else move_data "/opt/$new/app" "$old" "$new"; fi
  fi

  # ---- macOS, launchd
  pl="$HOME/Library/LaunchAgents/net.iothing.$old.server.plist"
  if [ "$(uname -s)" = Darwin ] && [ -f "$pl" ]; then
    found=1; say "$old -> $new (launchd)"
    appdir="$(/usr/libexec/PlistBuddy -c 'Print :WorkingDirectory' "$pl" 2>/dev/null || true)"
    run launchctl bootout "gui/$(id -u)/net.iothing.$old.server" || true
    new_pl="$HOME/Library/LaunchAgents/net.iothing.$new.server.plist"
    if [ "$DRY" = 1 ]; then echo "  would write $new_pl"
    else sed "s/net\.iothing\.$old\.server/net.iothing.$new.server/g" "$pl" > "$new_pl"; rm -f "$pl"; fi
    [ -n "$appdir" ] && move_data "$appdir" "$old" "$new"
    run launchctl bootstrap "gui/$(id -u)" "$new_pl"
  fi

  # ---- Docker: only tell
  if command -v docker >/dev/null 2>&1 && docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "$old"; then
    found=1; say "$old -> $new (Docker container $old: by hand)"
    cat <<EOF
  In the folder with its docker-compose.yml, take the new file from the $new repository, then:
    docker compose down
    docker volume create ${new}-data && docker run --rm -v ${old}-data:/from -v ${new}-data:/to alpine cp -a /from/. /to/
    docker compose up -d        # image ghcr.io/avandeputte/$new, container $new
  and once it runs: docker volume rm ${old}-data
EOF
  fi
done

[ "$found" = 1 ] || echo "No ionotes, iotasks or iocontacts install found here: nothing to do."
