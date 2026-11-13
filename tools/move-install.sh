#!/bin/bash
# One-time move of a running install to the suite's single repository (avandeputte/iosuite, one folder per app, the
# shared library in shared/), and of the start page from the name iosuite to iostart. Run it once on each machine
# (or LXC container) that runs io apps installed from the old per-app repositories. Safe to run twice: it skips what
# is done. Docker installs need nothing: `docker compose pull && docker compose up -d` (the start page's image is now
# ghcr.io/avandeputte/iostart; take its new docker-compose.yml).
#
#   curl -fsSLO https://raw.githubusercontent.com/avandeputte/iosuite/main/tools/move-install.sh
#   sudo bash move-install.sh --dry-run  # only say what it would do
#   sudo bash move-install.sh            # do it
# (on macOS, without sudo: the launch agents are the user's own)
#
# Per app it finds (a systemd service, a launch agent, or /opt/<app>/app), it:
#   - the start page only: stops iosuite.service, moves /opt/iosuite to /opt/iostart, writes iostart.service (or the
#     net.iothing.iostart.server launch agent), renames data/iosuite.log* and the IOSUITE_* keys of config.env to
#     IOSTART_* (the Shared ioSuite database's IOSUITE_DB_* keys stay)
#   - drops a <APP>_REPO line of config.env (it named the old repository), and the old repository's .git folder
#   - points the Proxmox container's `update` command at the new address
#   - takes the app's new update.sh from the suite's repository and runs it: the app's code and the shared library
#     come from the same commit from then on; config.env, the data folder and the Python environment stay
# The databases are not touched; the start page's rows in the Shared ioSuite database move by themselves when the
# apps start on iosuite-shared 0.47.0.
set -euo pipefail
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
RAW="${IOSUITE_RAW:-https://raw.githubusercontent.com/avandeputte/iosuite/main}"
run() { if [ "$DRY" = 1 ]; then printf '  would run: %s\n' "$*"; else "$@"; fi; }
say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
found=0

app_dir() {  # $1 service name: where the app is installed, or nothing
  local unit="/etc/systemd/system/$1.service" pl="$HOME/Library/LaunchAgents/net.iothing.$1.server.plist" d=""
  if [ -f "$unit" ]; then d="$(sed -n 's/^WorkingDirectory=//p' "$unit")"
  elif [ "$(uname -s)" = Darwin ] && [ -f "$pl" ]; then d="$(/usr/libexec/PlistBuddy -c 'Print :WorkingDirectory' "$pl" 2>/dev/null || true)"
  elif [ -f "/opt/$1/app/update.sh" ]; then d="/opt/$1/app"; fi
  printf '%s' "$d"
}

rename_start() {  # the start page: iosuite -> iostart (service, folder, log, config keys)
  local unit="/etc/systemd/system/iosuite.service" pl="$HOME/Library/LaunchAgents/net.iothing.iosuite.server.plist" d c f
  d="$(app_dir iosuite)"; [ -n "$d" ] || return 0
  found=1; say "ioStart: the start page's service and folder take the name iostart"
  c="$d/config.env"
  if [ -f "$unit" ]; then
    run systemctl stop iosuite
    run systemctl disable -q iosuite || true
  elif [ -f "$pl" ]; then
    run launchctl bootout "gui/$(id -u)/net.iothing.iosuite.server" || true
  fi
  if [ -f "$c" ] && grep -E '^[# ]*IOSUITE_' "$c" | grep -vq 'IOSUITE_DB_'; then
    run sed -i.bak -E '/^[# ]*IOSUITE_DB_/!s/^([# ]*)IOSUITE_/\1IOSTART_/' "$c"; run rm -f "$c.bak"
  fi
  for f in "$d"/data/iosuite.log*; do [ -e "$f" ] && run mv "$f" "$d/data/iostart${f#"$d/data/iosuite"}"; done
  if [ -d /opt/iosuite ] && [ ! -e /opt/iostart ]; then run mv /opt/iosuite /opt/iostart; fi
  if [ -f "$unit" ]; then
    if [ "$DRY" = 1 ]; then echo "  would write /etc/systemd/system/iostart.service (paths /opt/iosuite -> /opt/iostart)"
    else sed -e "s#/opt/iosuite#/opt/iostart#g" -e "s/^Description=.*/Description=ioStart/" "$unit" > /etc/systemd/system/iostart.service; rm -f "$unit"; fi
    run systemctl daemon-reload
    run systemctl enable -q iostart
  elif [ -f "$pl" ]; then
    if [ "$DRY" = 1 ]; then echo "  would write the launch agent net.iothing.iostart.server"
    else sed "s/net\.iothing\.iosuite\.server/net.iothing.iostart.server/g" "$pl" > "${pl/iosuite.server/iostart.server}"; rm -f "$pl"
      launchctl bootstrap "gui/$(id -u)" "${pl/iosuite.server/iostart.server}"; fi
  fi
}

move_app() {  # $1 app (its folder in the repository, its service), $2 the repository it was installed from
  local app="$1" old="$2" d c UP owner
  d="$(app_dir "$app")"; [ -n "$d" ] && [ -d "$d" ] || return 0
  found=1
  if [ -d "$d/shared/iosuite_shared" ] && [ ! -e "$d/.git" ]; then say "$app: already from the suite's repository ($d)"; return 0; fi
  say "$app: $d moves to the suite's repository"
  c="$d/config.env"; UP="$(printf '%s' "$app" | tr '[:lower:]' '[:upper:]')"
  if [ -f "$c" ] && grep -Eq "^${UP}_REPO=" "$c"; then run sed -i.bak -E "/^${UP}_REPO=/d" "$c"; run rm -f "$c.bak"; fi
  if [ -e "$d/.git" ]; then
    if [ -n "$(git -C "$d" status --porcelain --untracked-files=no 2>/dev/null)" ]; then
      echo "  the old checkout has local changes: its .git is kept as .git-old-repository"; run mv "$d/.git" "$d/.git-old-repository"
    else run rm -rf "$d/.git"; fi
    run rm -rf "$d/.github" "$d/.dockerignore" "$d/docker" "$d/tools" "$d/iosuite.egg-info"  # of the old repository's root; an app's folder has none
  fi
  if [ -f /usr/bin/update ] && grep -q "avandeputte/$old/main/" /usr/bin/update; then
    run sed -i "s#avandeputte/$old/main/#avandeputte/iosuite/main/$app/#g" /usr/bin/update
  fi
  owner="$(stat -c %U "$d" 2>/dev/null || stat -f %Su "$d")"
  if [ "$DRY" = 1 ]; then echo "  would fetch $RAW/$app/update.sh and run it in $d as $owner"; return 0; fi
  curl -fsSL "$RAW/$app/update.sh" -o "$d/update.sh.new" && mv "$d/update.sh.new" "$d/update.sh" && chmod 755 "$d/update.sh"
  if [ "$owner" = "$(id -un)" ]; then ( cd "$d" && sh ./update.sh --force )
  else chown "$owner" "$d/update.sh"; su -s /bin/sh "$owner" -c "cd '$d' && sh ./update.sh --force"; fi
  if [ -f "/etc/systemd/system/$app.service" ]; then
    systemctl restart "$app"; sleep 2
    if systemctl is-active -q "$app"; then echo "  $app is running"; else echo "  $app did not start: journalctl -u $app -n 50"; fi
  fi
}

rename_start
for pair in iostart:iosuite iopix:iopix ionote:ionote iocalendar:iocalendar iocontact:iocontact iohealth:iohealth \
            iotask:iotask iorecipe:iorecipe iodns:iodns iobackup:iobackup; do
  if [ "$DRY" = 1 ] && [ "${pair%%:*}" = iostart ] && [ -z "$(app_dir iostart)" ] && [ -n "$(app_dir iosuite)" ]; then
    say "iostart: $(app_dir iosuite) moves to the suite's repository"; echo "  would fetch $RAW/iostart/update.sh and run it there"; continue
  fi
  move_app "${pair%%:*}" "${pair##*:}"
done

[ "$found" = 1 ] || echo "No io app installed from the old repositories found here: nothing to do."
