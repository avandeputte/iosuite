#!/usr/bin/env bash
# ioSuite LXC for Proxmox VE, in the community-scripts (ProxmoxVE) framework layout, as iopix:
# this is the ct/ script; proxmox/install/iosuite-install.sh runs inside the container.
#
# After the framework's own questions (resources, network) it asks about the app: the MariaDB server, database, user
# and password (the database is created when the user may), the shared accounts database, the web port,
# the public address and the admin account. It creates the container, then runs the app's own setup.sh inside with those answers, which installs the
# packages, writes the settings, creates the tables and the admin and starts the service.
#
# Until the scripts are merged upstream, the framework is pointed at this repository for the install script
# (COMMUNITY_SCRIPTS_URL below; the core engine still comes from community-scripts). Run on the Proxmox host as root:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/proxmox/ct/iosuite.sh)"
# Unattended: IOSUITE_DB=host:port/db:user:password IOSUITE_SHARED_DB=host:port/db:user:password
#   IOSUITE_ADMIN=name:password IOSUITE_PORT=8630
#   IOSUITE_PUBLIC_URL=https://home.example.com in the environment skip the questions.
export COMMUNITY_SCRIPTS_URL="${COMMUNITY_SCRIPTS_URL:-https://raw.githubusercontent.com/avandeputte/iosuite/main/proxmox}"
_cs_boot="${COMMUNITY_SCRIPTS_CORE_DIR:-$(dirname "${BASH_SOURCE[0]}")/../../core}/core/build.func"
source "$_cs_boot" 2>/dev/null || source <(curl -fsSL "${COMMUNITY_SCRIPTS_CORE_URL:-https://raw.githubusercontent.com/community-scripts/core/main}/core/build.func")
# Copyright (c) 2026 Alex Van de Putte
# License: MIT
# Source: https://github.com/avandeputte/iosuite

APP="iosuite"
var_tags="${var_tags:-dashboard;start-page}"
var_cpu="${var_cpu:-1}"
var_ram="${var_ram:-512}"
var_disk="${var_disk:-4}"
var_os="${var_os:-debian}"
var_version="${var_version:-13}"
var_arm64="${var_arm64:-yes}"
var_unprivileged="${var_unprivileged:-1}"

header_info "$APP"
variables
color
catch_errors

# ---- the app's own questions (whiptail on the host; IOSUITE_* in the environment skip them)
ask_app_settings() {
  local bt="ioSuite"
  if [[ -z "${IOSUITE_DB:-}" ]]; then
    local h p d u w
    h=$(whiptail --backtitle "$bt" --inputbox "MariaDB / MySQL host or IP (the start page keeps its settings there)" 9 70 "192.168.1.89" 3>&1 1>&2 2>&3) || exit 1
    p=$(whiptail --backtitle "$bt" --inputbox "Port" 9 60 "3306" 3>&1 1>&2 2>&3) || exit 1
    d=$(whiptail --backtitle "$bt" --inputbox "Database (created if the user may)" 9 60 "suite" 3>&1 1>&2 2>&3) || exit 1
    u=$(whiptail --backtitle "$bt" --inputbox "User" 9 60 "suite" 3>&1 1>&2 2>&3) || exit 1
    w=$(whiptail --backtitle "$bt" --passwordbox "Password" 9 60 3>&1 1>&2 2>&3) || exit 1
    IOSUITE_DB="$h:$p/$d:$u:$w"
  fi
  IOSUITE_SHARED_DB="${IOSUITE_SHARED_DB:-${IOSUITE_AUTH_DB:-}}"  # IOSUITE_AUTH_DB: its name before 0.3.1
  if [[ -z "${IOSUITE_SHARED_DB:-}" ]]; then
    local ah ap ad au aw2
    ah=$(whiptail --backtitle "$bt" --inputbox "Shared ioSuite database (accounts and suite-wide settings of the io apps): host" 9 70 "${IOSUITE_DB%%:*}" 3>&1 1>&2 2>&3) || exit 1
    ap=$(whiptail --backtitle "$bt" --inputbox "Port" 9 60 "3306" 3>&1 1>&2 2>&3) || exit 1
    ad=$(whiptail --backtitle "$bt" --inputbox "Database (the same one the other io apps use)" 9 70 "iosuite" 3>&1 1>&2 2>&3) || exit 1
    au=$(whiptail --backtitle "$bt" --inputbox "User" 9 60 "iosuite" 3>&1 1>&2 2>&3) || exit 1
    aw2=$(whiptail --backtitle "$bt" --passwordbox "Password" 9 60 3>&1 1>&2 2>&3) || exit 1
    IOSUITE_SHARED_DB="$ah:$ap/$ad:$au:$aw2"
  fi
  IOSUITE_PORT="${IOSUITE_PORT:-$(whiptail --backtitle "$bt" --inputbox "Web port" 9 70 "8630" 3>&1 1>&2 2>&3)}" || exit 1
  if [[ -z "${IOSUITE_PUBLIC_URL+x}" ]]; then
    IOSUITE_PUBLIC_URL=$(whiptail --backtitle "$bt" --inputbox "Public address behind your reverse proxy, e.g. https://home.example.com (empty: the address it is reached at)" 10 76 "" 3>&1 1>&2 2>&3) || exit 1
  fi
  if [[ -z "${IOSUITE_ADMIN+x}" ]]; then
    local an aw
    an=$(whiptail --backtitle "$bt" --inputbox "Admin user name" 9 70 "admin" 3>&1 1>&2 2>&3) || exit 1
    aw=$(whiptail --backtitle "$bt" --passwordbox "Admin password (8 characters or more; empty: make the admin in the browser on the first visit)" 10 72 3>&1 1>&2 2>&3) || exit 1
    [[ -n "$aw" ]] && IOSUITE_ADMIN="$an:$aw" || IOSUITE_ADMIN=""
  fi
}

function update_script() {
  header_info
  check_container_storage
  check_container_resources
  if [[ ! -d /opt/iosuite/app ]]; then
    msg_error "No ${APP} Installation Found!"
    exit
  fi
  msg_info "Updating ${APP}"
  # the app's own updater: latest code, same settings and data, service restarted
  if sh /opt/iosuite/app/update.sh; then msg_ok "Updated successfully!"; else msg_error "update.sh failed; see the lines above"; exit 1; fi
  exit
}

if command -v pveversion >/dev/null 2>&1; then ask_app_settings; fi  # on the Proxmox host; inside the container `update` needs no answers
start
build_container
description

msg_info "Running the app's setup inside the container (packages, settings, tables, admin, service)"
# the answers with passwords go in as a root-only file (pushed, read into setup.sh's environment, removed), never as arguments
SECRETS="IOSUITE_DB=$(printf '%q' "$IOSUITE_DB")"$'\n'"IOSUITE_SHARED_DB=$(printf '%q' "$IOSUITE_SHARED_DB")"$'\n'
[[ -n "${IOSUITE_ADMIN:-}" ]] && SECRETS+="IOSUITE_ADMIN=$(printf '%q' "$IOSUITE_ADMIN")"$'\n'
SECF="$(mktemp)"; chmod 600 "$SECF"; printf '%s' "$SECRETS" > "$SECF"
pct push "$CTID" "$SECF" /opt/iosuite/setup.env --perms 0600 --user 0 --group 0
rm -f "$SECF"
SETUP_CMD="cd /opt/iosuite/app && sh ./setup.sh --yes --no-system-deps --service --port '${IOSUITE_PORT:-8630}' --public-url '${IOSUITE_PUBLIC_URL:-}'"
WRAPPED="set -a; . /opt/iosuite/setup.env; set +a; rm -f /opt/iosuite/setup.env; $SETUP_CMD > /opt/iosuite/setup.log 2>&1"
if ! pct exec "$CTID" -- bash -c "$WRAPPED"; then
  msg_error "setup.sh failed inside the container; last lines of /opt/iosuite/setup.log:"
  pct exec "$CTID" -- tail -n 40 /opt/iosuite/setup.log || true
  msg_error "Fix the cause (often: the MariaDB user may not connect from the container's address), then run it again inside the container with IOSUITE_DB=host:port/db:user:password (IOSUITE_SHARED_DB likewise, and IOSUITE_ADMIN=name:password) in the environment: pct exec $CTID -- bash -c \"$SETUP_CMD\""
  exit 1
fi
msg_ok "Setup finished"

msg_ok "Completed successfully!\n"
echo -e "${CREATING}${GN}${APP} setup has been successfully initialized!${CL}"
echo -e "${INFO}${YW}Access it using the following URL:${CL}"
echo -e "${GATEWAY}${BGN}http://${IP}:${IOSUITE_PORT:-8630}${CL}"
