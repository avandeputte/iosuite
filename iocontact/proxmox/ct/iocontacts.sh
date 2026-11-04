#!/usr/bin/env bash
# ioContacts LXC for Proxmox VE, in the community-scripts (ProxmoxVE) framework layout, as iopix:
# this is the ct/ script; proxmox/install/iocontacts-install.sh runs inside the container.
#
# After the framework's own questions (resources, network) it asks about the app: the MariaDB server, database, user
# and password (the database is created when the user may), the Shared ioSuite database (the suite's accounts and
# settings, `iosuite` by default), the web and LDAP ports, the public address and the admin
# account. It creates the container, then runs the app's own setup.sh inside with those answers, which installs the
# packages, writes the settings, creates the tables and the admin and starts the service.
#
# Until the scripts are merged upstream, the framework is pointed at this repository for the install script
# (COMMUNITY_SCRIPTS_URL below; the core engine still comes from community-scripts). Run on the Proxmox host as root:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iocontacts/main/proxmox/ct/iocontacts.sh)"
# Unattended: IOCONTACTS_DB=host:port/db:user:password IOCONTACTS_SUITE_DB=host:port/iosuite:iosuite:password
#   IOCONTACTS_ADMIN=name:password IOCONTACTS_PORT=8610
#   IOCONTACTS_LDAP_PORT=3890 IOCONTACTS_PUBLIC_URL=https://contacts.example.com in the environment skip the questions.
export COMMUNITY_SCRIPTS_URL="${COMMUNITY_SCRIPTS_URL:-https://raw.githubusercontent.com/avandeputte/iocontacts/main/proxmox}"
_cs_boot="${COMMUNITY_SCRIPTS_CORE_DIR:-$(dirname "${BASH_SOURCE[0]}")/../../core}/core/build.func"
source "$_cs_boot" 2>/dev/null || source <(curl -fsSL "${COMMUNITY_SCRIPTS_CORE_URL:-https://raw.githubusercontent.com/community-scripts/core/main}/core/build.func")
# Copyright (c) 2026 Alex Van de Putte
# License: MIT
# Source: https://github.com/avandeputte/iocontacts

APP="iocontacts"
var_tags="${var_tags:-contacts;carddav}"
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

# ---- the app's own questions (whiptail on the host; IOCONTACTS_* in the environment skip them)
ask_app_settings() {
  local bt="ioContacts"
  if [[ -z "${IOCONTACTS_DB:-}" ]]; then
    local h p d u w
    h=$(whiptail --backtitle "$bt" --inputbox "MariaDB / MySQL host or IP (the contacts are kept there)" 9 70 "192.168.1.89" 3>&1 1>&2 2>&3) || exit 1
    p=$(whiptail --backtitle "$bt" --inputbox "Port" 9 60 "3306" 3>&1 1>&2 2>&3) || exit 1
    d=$(whiptail --backtitle "$bt" --inputbox "Database (created if the user may)" 9 60 "contacts" 3>&1 1>&2 2>&3) || exit 1
    u=$(whiptail --backtitle "$bt" --inputbox "User" 9 60 "contacts" 3>&1 1>&2 2>&3) || exit 1
    w=$(whiptail --backtitle "$bt" --passwordbox "Password" 9 60 3>&1 1>&2 2>&3) || exit 1
    IOCONTACTS_DB="$h:$p/$d:$u:$w"
  fi
  if [[ -z "${IOCONTACTS_SUITE_DB:-}" ]]; then
    local sh sp sd su sw
    sh=$(whiptail --backtitle "$bt" --inputbox "Shared ioSuite database (accounts and settings shared by the ioThing apps): host or IP" 9 76 "${IOCONTACTS_DB%%:*}" 3>&1 1>&2 2>&3) || exit 1
    sp=$(whiptail --backtitle "$bt" --inputbox "Port" 9 60 "3306" 3>&1 1>&2 2>&3) || exit 1
    sd=$(whiptail --backtitle "$bt" --inputbox "Shared ioSuite database name" 9 60 "iosuite" 3>&1 1>&2 2>&3) || exit 1
    su=$(whiptail --backtitle "$bt" --inputbox "User" 9 60 "iosuite" 3>&1 1>&2 2>&3) || exit 1
    sw=$(whiptail --backtitle "$bt" --passwordbox "Password" 9 60 3>&1 1>&2 2>&3) || exit 1
    IOCONTACTS_SUITE_DB="$sh:$sp/$sd:$su:$sw"
  fi
  IOCONTACTS_PORT="${IOCONTACTS_PORT:-$(whiptail --backtitle "$bt" --inputbox "Web port (web app, CardDAV, REST API, calendar feed)" 9 70 "8610" 3>&1 1>&2 2>&3)}" || exit 1
  IOCONTACTS_LDAP_PORT="${IOCONTACTS_LDAP_PORT:-$(whiptail --backtitle "$bt" --inputbox "LDAP directory port for mail apps (389 is the standard one; 0 turns LDAP off)" 9 76 "389" 3>&1 1>&2 2>&3)}" || exit 1
  if [[ -z "${IOCONTACTS_PUBLIC_URL+x}" ]]; then
    IOCONTACTS_PUBLIC_URL=$(whiptail --backtitle "$bt" --inputbox "Public address behind your reverse proxy, e.g. https://contacts.example.com (empty: the address it is reached at)" 10 76 "" 3>&1 1>&2 2>&3) || exit 1
  fi
  if [[ -z "${IOCONTACTS_ADMIN+x}" ]]; then
    local an aw
    an=$(whiptail --backtitle "$bt" --inputbox "Admin user name" 9 70 "admin" 3>&1 1>&2 2>&3) || exit 1
    aw=$(whiptail --backtitle "$bt" --passwordbox "Admin password (8 characters or more; empty: make the admin in the browser on the first visit)" 10 72 3>&1 1>&2 2>&3) || exit 1
    [[ -n "$aw" ]] && IOCONTACTS_ADMIN="$an:$aw" || IOCONTACTS_ADMIN=""
  fi
}

function update_script() {
  header_info
  check_container_storage
  check_container_resources
  if [[ ! -d /opt/iocontacts/app ]]; then
    msg_error "No ${APP} Installation Found!"
    exit
  fi
  msg_info "Updating ${APP}"
  # the app's own updater: latest code, same settings and data, service restarted
  if sh /opt/iocontacts/app/update.sh; then msg_ok "Updated successfully!"; else msg_error "update.sh failed; see the lines above"; exit 1; fi
  exit
}

if command -v pveversion >/dev/null 2>&1; then ask_app_settings; fi  # on the Proxmox host; inside the container `update` needs no answers
start
build_container
description

msg_info "Running the app's setup inside the container (packages, settings, tables, admin, service)"
# the answers with passwords go in as a root-only file (pushed, read into setup.sh's environment, removed), never as arguments
SECRETS="IOCONTACTS_DB=$(printf '%q' "$IOCONTACTS_DB")"$'\n'
[[ -n "${IOCONTACTS_SUITE_DB:-}" ]] && SECRETS+="IOCONTACTS_SUITE_DB=$(printf '%q' "$IOCONTACTS_SUITE_DB")"$'\n'
[[ -n "${IOCONTACTS_ADMIN:-}" ]] && SECRETS+="IOCONTACTS_ADMIN=$(printf '%q' "$IOCONTACTS_ADMIN")"$'\n'
SECF="$(mktemp)"; chmod 600 "$SECF"; printf '%s' "$SECRETS" > "$SECF"
pct push "$CTID" "$SECF" /opt/iocontacts/setup.env --perms 0600 --user 0 --group 0
rm -f "$SECF"
SETUP_CMD="cd /opt/iocontacts/app && sh ./setup.sh --yes --no-system-deps --service --port '${IOCONTACTS_PORT:-8610}' --ldap-port '${IOCONTACTS_LDAP_PORT:-389}' --public-url '${IOCONTACTS_PUBLIC_URL:-}'"
WRAPPED="set -a; . /opt/iocontacts/setup.env; set +a; rm -f /opt/iocontacts/setup.env; $SETUP_CMD > /opt/iocontacts/setup.log 2>&1"
if ! pct exec "$CTID" -- bash -c "$WRAPPED"; then
  msg_error "setup.sh failed inside the container; last lines of /opt/iocontacts/setup.log:"
  pct exec "$CTID" -- tail -n 40 /opt/iocontacts/setup.log || true
  msg_error "Fix the cause (often: the MariaDB user may not connect from the container's address), then run it again inside the container with IOCONTACTS_DB=host:port/db:user:password (and IOCONTACTS_ADMIN=name:password) in the environment: pct exec $CTID -- bash -c \"$SETUP_CMD\""
  exit 1
fi
msg_ok "Setup finished"

msg_ok "Completed successfully!\n"
echo -e "${CREATING}${GN}${APP} setup has been successfully initialized!${CL}"
echo -e "${INFO}${YW}Access it using the following URL:${CL}"
echo -e "${GATEWAY}${BGN}http://${IP}:${IOCONTACTS_PORT:-8610}${CL}"
echo -e "${INFO}${YW}CardDAV: http://${IP}:${IOCONTACTS_PORT:-8610}/dav/   LDAP: ${IP}:${IOCONTACTS_LDAP_PORT:-389} (base dc=iocontacts)${CL}"
