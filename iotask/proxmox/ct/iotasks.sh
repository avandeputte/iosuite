#!/usr/bin/env bash
# ioTasks LXC for Proxmox VE, in the community-scripts (ProxmoxVE) framework layout, as iopix:
# this is the ct/ script; proxmox/install/iotasks-install.sh runs inside the container.
#
# After the framework's own questions (resources, network) it asks about the app: the MariaDB server, database, user
# and password (the database is created when the user may), the Shared ioSuite database, the web port, the time zone,
# the public address, the domain the sign-in is shared on and the admin account. It creates the container, then runs the app's own setup.sh inside with those answers, which installs the
# packages, writes the settings, creates the tables and the admin and starts the service.
#
# Until the scripts are merged upstream, the framework is pointed at this repository for the install script
# (COMMUNITY_SCRIPTS_URL below; the core engine still comes from community-scripts). Run on the Proxmox host as root:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iotasks/main/proxmox/ct/iotasks.sh)"
# Unattended: IOTASKS_DB=host:port/db:user:password IOTASKS_SUITE_DB=host:port/db:user:password
#   IOTASKS_ADMIN=name:password IOTASKS_PORT=8670 IOTASKS_TIMEZONE=America/New_York
#   IOTASKS_PUBLIC_URL=https://tasks.example.com IOTASKS_COOKIE_DOMAIN=example.com in the environment skip the questions.
export COMMUNITY_SCRIPTS_URL="${COMMUNITY_SCRIPTS_URL:-https://raw.githubusercontent.com/avandeputte/iotasks/main/proxmox}"
_cs_boot="${COMMUNITY_SCRIPTS_CORE_DIR:-$(dirname "${BASH_SOURCE[0]}")/../../core}/core/build.func"
source "$_cs_boot" 2>/dev/null || source <(curl -fsSL "${COMMUNITY_SCRIPTS_CORE_URL:-https://raw.githubusercontent.com/community-scripts/core/main}/core/build.func")
# Copyright (c) 2026 Alex Van de Putte
# License: GPL-3.0-or-later
# Source: https://github.com/avandeputte/iotasks

APP="iotasks"
var_tags="${var_tags:-tasks;caldav}"
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

# ---- the app's own questions (whiptail on the host; IOTASKS_* in the environment skip them)
ask_app_settings() {
  local bt="ioTasks"
  if [[ -z "${IOTASKS_DB:-}" ]]; then
    local h p d u w
    h=$(whiptail --backtitle "$bt" --inputbox "MariaDB / MySQL host or IP (the task lists are kept there)" 9 70 "" 3>&1 1>&2 2>&3) || exit 1
    p=$(whiptail --backtitle "$bt" --inputbox "Port" 9 60 "3306" 3>&1 1>&2 2>&3) || exit 1
    d=$(whiptail --backtitle "$bt" --inputbox "Database (created if the user may)" 9 60 "tasks" 3>&1 1>&2 2>&3) || exit 1
    u=$(whiptail --backtitle "$bt" --inputbox "User" 9 60 "tasks" 3>&1 1>&2 2>&3) || exit 1
    w=$(whiptail --backtitle "$bt" --passwordbox "Password" 9 60 3>&1 1>&2 2>&3) || exit 1
    IOTASKS_DB="$h:$p/$d:$u:$w"
  fi
  if [[ -z "${IOTASKS_SUITE_DB:-}" ]]; then
    local ah ap ad au aw2
    ah=$(whiptail --backtitle "$bt" --inputbox "Shared ioSuite database (accounts and suite-wide settings): host" 9 70 "${IOTASKS_DB%%:*}" 3>&1 1>&2 2>&3) || exit 1
    ap=$(whiptail --backtitle "$bt" --inputbox "Port" 9 60 "3306" 3>&1 1>&2 2>&3) || exit 1
    ad=$(whiptail --backtitle "$bt" --inputbox "Database (the same one every app of the suite uses)" 9 70 "iosuite" 3>&1 1>&2 2>&3) || exit 1
    au=$(whiptail --backtitle "$bt" --inputbox "User" 9 60 "iosuite" 3>&1 1>&2 2>&3) || exit 1
    aw2=$(whiptail --backtitle "$bt" --passwordbox "Password" 9 60 3>&1 1>&2 2>&3) || exit 1
    IOTASKS_SUITE_DB="$ah:$ap/$ad:$au:$aw2"
  fi
  IOTASKS_PORT="${IOTASKS_PORT:-$(whiptail --backtitle "$bt" --inputbox "Web port (web app, CalDAV, REST API)" 9 70 "8670" 3>&1 1>&2 2>&3)}" || exit 1
  IOTASKS_TIMEZONE="${IOTASKS_TIMEZONE:-$(whiptail --backtitle "$bt" --inputbox "Time zone of the family" 9 70 "$(cat /etc/timezone 2>/dev/null || echo America/New_York)" 3>&1 1>&2 2>&3)}" || exit 1
  if [[ -z "${IOTASKS_PUBLIC_URL+x}" ]]; then
    IOTASKS_PUBLIC_URL=$(whiptail --backtitle "$bt" --inputbox "Public address behind your reverse proxy, e.g. https://tasks.example.com (empty: the address it is reached at)" 10 76 "" 3>&1 1>&2 2>&3) || exit 1
  fi
  if [[ -z "${IOTASKS_COOKIE_DOMAIN+x}" ]]; then
    IOTASKS_COOKIE_DOMAIN=$(whiptail --backtitle "$bt" --inputbox "Domain the sign-in is shared on by every app, e.g. example.com (empty: this host only)" 10 76 "" 3>&1 1>&2 2>&3) || exit 1
  fi
  if [[ -z "${IOTASKS_ADMIN+x}" ]]; then
    local an aw
    an=$(whiptail --backtitle "$bt" --inputbox "Admin user name" 9 70 "admin" 3>&1 1>&2 2>&3) || exit 1
    aw=$(whiptail --backtitle "$bt" --passwordbox "Admin password (8 characters or more; empty: make the admin in the browser on the first visit)" 10 72 3>&1 1>&2 2>&3) || exit 1
    [[ -n "$aw" ]] && IOTASKS_ADMIN="$an:$aw" || IOTASKS_ADMIN=""
  fi
  if [[ -z "${IOTASKS_DB_ADMIN+x}" ]]; then  # a MariaDB administrator: the databases and users above are created for you (empty: they exist)
    local dau daw
    dau=$(whiptail --backtitle "$bt" --inputbox "MariaDB administrator who may create the databases and users above, e.g. root (empty: they exist already)" 10 76 "" 3>&1 1>&2 2>&3) || exit 1
    if [[ -n "$dau" ]]; then
      daw=$(whiptail --backtitle "$bt" --passwordbox "Password of $dau" 9 60 3>&1 1>&2 2>&3) || exit 1
      IOTASKS_DB_ADMIN="$dau:$daw"
    else
      IOTASKS_DB_ADMIN=""
    fi
  fi
  if [[ -z "${IOTASKS_ALSO+x}" ]]; then  # the other apps of the suite in the same container (ioPix has its own script: photo mounts)
    IOTASKS_ALSO=$(whiptail --backtitle "$bt" --checklist "Also install in this container (same database server, each app its own database; same accounts and admin; each on its usual port):" 15 78 5 \
      iosuite "ioSuite (the start page)  (8630)" OFF \
      iocalendar "ioCalendar  (8620)" OFF \
      iocontacts "ioContacts  (8640, LDAP 3890)" OFF \
      ionotes "ioNotes  (8610)" OFF \
      iohealth "ioHealth  (8650)" OFF 3>&1 1>&2 2>&3) || exit 1
    IOTASKS_ALSO=$(echo "$IOTASKS_ALSO" | tr -d '"' | tr ' ' ',')
  fi
  if [[ -n "$IOTASKS_ALSO" ]]; then  # room for more than one app
    (( var_ram < 2048 )) && var_ram=2048; (( var_disk < 8 )) && var_disk=8
  fi
}

function update_script() {
  header_info
  check_container_storage
  check_container_resources
  if [[ ! -d /opt/iotasks/app ]]; then
    msg_error "No ${APP} Installation Found!"
    exit
  fi
  msg_info "Updating ${APP}"
  # the app's own updater: latest code, same settings and data, service restarted
  if sh /opt/iotasks/app/update.sh; then msg_ok "Updated successfully!"; else msg_error "update.sh failed; see the lines above"; exit 1; fi
  exit
}

if command -v pveversion >/dev/null 2>&1; then ask_app_settings; fi  # on the Proxmox host; inside the container `update` needs no answers
start
build_container
description

msg_info "Running the app's setup inside the container (packages, settings, tables, admin, service)"
# the answers with passwords go in as a root-only file (pushed, read into setup.sh's environment, removed), never as arguments
SECRETS="IOTASKS_DB=$(printf '%q' "$IOTASKS_DB")"$'\n'"IOTASKS_SUITE_DB=$(printf '%q' "$IOTASKS_SUITE_DB")"$'\n'
[[ -n "${IOTASKS_ADMIN:-}" ]] && SECRETS+="IOTASKS_ADMIN=$(printf '%q' "$IOTASKS_ADMIN")"$'\n'
[[ -n "${IOTASKS_DB_ADMIN:-}" ]] && SECRETS+="IOTASKS_DB_ADMIN=$(printf '%q' "$IOTASKS_DB_ADMIN")"$'\n'
SECF="$(mktemp)"; chmod 600 "$SECF"; printf '%s' "$SECRETS" > "$SECF"
pct push "$CTID" "$SECF" /opt/iotasks/setup.env --perms 0600 --user 0 --group 0
rm -f "$SECF"
SETUP_CMD="cd /opt/iotasks/app && sh ./setup.sh --yes --no-system-deps --service --port '${IOTASKS_PORT:-8670}' --timezone '${IOTASKS_TIMEZONE:-America/New_York}' --public-url '${IOTASKS_PUBLIC_URL:-}' --cookie-domain '${IOTASKS_COOKIE_DOMAIN:-}' --also '${IOTASKS_ALSO:-none}'"
WRAPPED="set -a; . /opt/iotasks/setup.env; set +a; rm -f /opt/iotasks/setup.env; $SETUP_CMD > /opt/iotasks/setup.log 2>&1"
if ! pct exec "$CTID" -- bash -c "$WRAPPED"; then
  msg_error "setup.sh failed inside the container; last lines of /opt/iotasks/setup.log:"
  pct exec "$CTID" -- tail -n 40 /opt/iotasks/setup.log || true
  msg_error "Fix the cause (often: the MariaDB user may not connect from the container's address), then run it again inside the container with IOTASKS_DB=host:port/db:user:password (IOTASKS_SUITE_DB likewise, and IOTASKS_ADMIN=name:password) in the environment: pct exec $CTID -- bash -c \"$SETUP_CMD\""
  exit 1
fi
msg_ok "Setup finished"

msg_ok "Completed successfully!\n"
echo -e "${CREATING}${GN}${APP} setup has been successfully initialized!${CL}"
echo -e "${INFO}${YW}Access it using the following URL:${CL}"
echo -e "${GATEWAY}${BGN}http://${IP}:${IOTASKS_PORT:-8670}${CL}"
for a in ${IOTASKS_ALSO//,/ }; do
  case "$a" in iosuite) p=8630;; iocalendar) p=8620;; iocontacts) p=8640;; ionotes) p=8610;; iohealth) p=8650;; iopix) p=8600;; *) p="";; esac
  [[ -n "$p" ]] && echo -e "${INFO}${YW}$a:${CL} ${BGN}http://${IP}:$p${CL}"
done
echo -e "${INFO}${YW}CalDAV: http://${IP}:${IOTASKS_PORT:-8670}/dav/${CL}"
