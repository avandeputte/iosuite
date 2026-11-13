#!/usr/bin/env bash
# ioContact LXC for Proxmox VE, in the community-scripts (ProxmoxVE) framework layout, as iopix:
# this is the ct/ script; proxmox/install/iocontact-install.sh runs inside the container.
#
# After the framework's own questions (resources, network) it asks about the app: the MariaDB server, database, user
# and password (the database is created when the user may), the Shared ioSuite database (the suite's accounts and
# settings, `iosuite` by default), the web and LDAP ports, the public address and the admin
# account. It creates the container, then runs the app's own setup.sh inside with those answers, which installs the
# packages, writes the settings, creates the tables and the admin and starts the service.
#
# Until the scripts are merged upstream, the framework is pointed at this repository for the install script
# (COMMUNITY_SCRIPTS_URL below; the core engine still comes from community-scripts). Run on the Proxmox host as root:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iocontact/proxmox/ct/iocontact.sh)"
# Unattended: IOCONTACT_DB=host:port/db:user:password IOCONTACT_SUITE_DB=host:port/iosuite:iosuite:password
#   IOCONTACT_ADMIN=name:password IOCONTACT_PORT=8640
#   IOCONTACT_LDAP_PORT=3890 IOCONTACT_PUBLIC_URL=https://contacts.example.com
#   IOCONTACT_COOKIE_DOMAIN=example.com in the environment skip the questions.
export COMMUNITY_SCRIPTS_URL="${COMMUNITY_SCRIPTS_URL:-https://raw.githubusercontent.com/avandeputte/iosuite/main/iocontact/proxmox}"
_cs_boot="${COMMUNITY_SCRIPTS_CORE_DIR:-$(dirname "${BASH_SOURCE[0]}")/../../core}/core/build.func"
source "$_cs_boot" 2>/dev/null || source <(curl -fsSL "${COMMUNITY_SCRIPTS_CORE_URL:-https://raw.githubusercontent.com/community-scripts/core/main}/core/build.func")
# Copyright (c) 2026 Alex Van de Putte
# License: GPL-3.0-or-later
# Source: https://github.com/avandeputte/iosuite (iocontact/)

APP="iocontact"
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

# ---- the app's own questions (whiptail on the host; IOCONTACT_* in the environment skip them)
ask_app_settings() {
  local bt="ioContact"
  if [[ -z "${IOCONTACT_DB:-}" ]]; then
    local h p d u w
    h=$(whiptail --backtitle "$bt" --inputbox "MariaDB / MySQL host or IP (the contacts are kept there)" 9 70 "" 3>&1 1>&2 2>&3) || exit 1
    p=$(whiptail --backtitle "$bt" --inputbox "Port" 9 60 "3306" 3>&1 1>&2 2>&3) || exit 1
    d=$(whiptail --backtitle "$bt" --inputbox "Database (created if the user may)" 9 60 "contacts" 3>&1 1>&2 2>&3) || exit 1
    u=$(whiptail --backtitle "$bt" --inputbox "User" 9 60 "contacts" 3>&1 1>&2 2>&3) || exit 1
    w=$(whiptail --backtitle "$bt" --passwordbox "Password" 9 60 3>&1 1>&2 2>&3) || exit 1
    IOCONTACT_DB="$h:$p/$d:$u:$w"
  fi
  if [[ -z "${IOCONTACT_SUITE_DB:-}" ]]; then
    local sh sp sd su sw
    sh=$(whiptail --backtitle "$bt" --inputbox "Shared ioSuite database (accounts and settings shared by every app of the suite): host or IP" 9 76 "${IOCONTACT_DB%%:*}" 3>&1 1>&2 2>&3) || exit 1
    sp=$(whiptail --backtitle "$bt" --inputbox "Port" 9 60 "3306" 3>&1 1>&2 2>&3) || exit 1
    sd=$(whiptail --backtitle "$bt" --inputbox "Shared ioSuite database name" 9 60 "iosuite" 3>&1 1>&2 2>&3) || exit 1
    su=$(whiptail --backtitle "$bt" --inputbox "User" 9 60 "iosuite" 3>&1 1>&2 2>&3) || exit 1
    sw=$(whiptail --backtitle "$bt" --passwordbox "Password" 9 60 3>&1 1>&2 2>&3) || exit 1
    IOCONTACT_SUITE_DB="$sh:$sp/$sd:$su:$sw"
  fi
  IOCONTACT_PORT="${IOCONTACT_PORT:-$(whiptail --backtitle "$bt" --inputbox "Web port (web app, CardDAV, REST API, calendar feed)" 9 70 "8640" 3>&1 1>&2 2>&3)}" || exit 1
  IOCONTACT_LDAP_PORT="${IOCONTACT_LDAP_PORT:-$(whiptail --backtitle "$bt" --inputbox "LDAP directory port for mail apps (389 is the standard one; 0 turns LDAP off)" 9 76 "389" 3>&1 1>&2 2>&3)}" || exit 1
  if [[ -z "${IOCONTACT_PUBLIC_URL+x}" ]]; then
    IOCONTACT_PUBLIC_URL=$(whiptail --backtitle "$bt" --inputbox "Public address behind your reverse proxy, e.g. https://contacts.example.com (empty: the address it is reached at)" 10 76 "" 3>&1 1>&2 2>&3) || exit 1
  fi
  if [[ -z "${IOCONTACT_COOKIE_DOMAIN+x}" ]]; then
    IOCONTACT_COOKIE_DOMAIN=$(whiptail --backtitle "$bt" --inputbox "Domain the sign-in is shared on by every app, e.g. example.com (empty: this host only)" 10 76 "" 3>&1 1>&2 2>&3) || exit 1
  fi
  if [[ -z "${IOCONTACT_ADMIN+x}" ]]; then
    local an aw
    an=$(whiptail --backtitle "$bt" --inputbox "Admin user name" 9 70 "admin" 3>&1 1>&2 2>&3) || exit 1
    aw=$(whiptail --backtitle "$bt" --passwordbox "Admin password (8 characters or more; empty: make the admin in the browser on the first visit)" 10 72 3>&1 1>&2 2>&3) || exit 1
    [[ -n "$aw" ]] && IOCONTACT_ADMIN="$an:$aw" || IOCONTACT_ADMIN=""
  fi
  if [[ -z "${IOCONTACT_DB_ADMIN+x}" ]]; then  # a MariaDB administrator: the databases and users above are created for you (empty: they exist)
    local dau daw
    dau=$(whiptail --backtitle "$bt" --inputbox "MariaDB administrator who may create the databases and users above, e.g. root (empty: they exist already)" 10 76 "" 3>&1 1>&2 2>&3) || exit 1
    if [[ -n "$dau" ]]; then
      daw=$(whiptail --backtitle "$bt" --passwordbox "Password of $dau" 9 60 3>&1 1>&2 2>&3) || exit 1
      IOCONTACT_DB_ADMIN="$dau:$daw"
    else
      IOCONTACT_DB_ADMIN=""
    fi
  fi
  if [[ -z "${IOCONTACT_ALSO+x}" ]]; then  # the other apps of the suite in the same container (ioPix has its own script: photo mounts)
    IOCONTACT_ALSO=$(whiptail --backtitle "$bt" --checklist "Also install in this container (same database server, each app its own database; same accounts and admin; each on its usual port):" 14 78 4 \
      iosuite "ioSuite (the start page)  (8630)" OFF \
      iocalendar "ioCalendar  (8620)" OFF \
      ionote "ionote  (8610)" OFF \
      iohealth "ioHealth  (8650)" OFF 3>&1 1>&2 2>&3) || exit 1
    IOCONTACT_ALSO=$(echo "$IOCONTACT_ALSO" | tr -d '"' | tr ' ' ',')
  fi
  if [[ -n "$IOCONTACT_ALSO" ]]; then  # room for more than one app
    (( var_ram < 2048 )) && var_ram=2048; (( var_disk < 8 )) && var_disk=8
  fi
}

function update_script() {
  header_info
  check_container_storage
  check_container_resources
  if [[ ! -d /opt/iocontact/app ]]; then
    msg_error "No ${APP} Installation Found!"
    exit
  fi
  msg_info "Updating ${APP}"
  # the app's own updater: latest code, same settings and data, service restarted
  if sh /opt/iocontact/app/update.sh; then msg_ok "Updated successfully!"; else msg_error "update.sh failed; see the lines above"; exit 1; fi
  exit
}

if command -v pveversion >/dev/null 2>&1; then ask_app_settings; fi  # on the Proxmox host; inside the container `update` needs no answers
start
build_container
description

msg_info "Running the app's setup inside the container (packages, settings, tables, admin, service)"
# the answers with passwords go in as a root-only file (pushed, read into setup.sh's environment, removed), never as arguments
SECRETS="IOCONTACT_DB=$(printf '%q' "$IOCONTACT_DB")"$'\n'
[[ -n "${IOCONTACT_SUITE_DB:-}" ]] && SECRETS+="IOCONTACT_SUITE_DB=$(printf '%q' "$IOCONTACT_SUITE_DB")"$'\n'
[[ -n "${IOCONTACT_ADMIN:-}" ]] && SECRETS+="IOCONTACT_ADMIN=$(printf '%q' "$IOCONTACT_ADMIN")"$'\n'
[[ -n "${IOCONTACT_DB_ADMIN:-}" ]] && SECRETS+="IOCONTACT_DB_ADMIN=$(printf '%q' "$IOCONTACT_DB_ADMIN")"$'\n'
SECF="$(mktemp)"; chmod 600 "$SECF"; printf '%s' "$SECRETS" > "$SECF"
pct push "$CTID" "$SECF" /opt/iocontact/setup.env --perms 0600 --user 0 --group 0
rm -f "$SECF"
SETUP_CMD="cd /opt/iocontact/app && sh ./setup.sh --yes --no-system-deps --service --port '${IOCONTACT_PORT:-8640}' --ldap-port '${IOCONTACT_LDAP_PORT:-389}' --public-url '${IOCONTACT_PUBLIC_URL:-}' --cookie-domain '${IOCONTACT_COOKIE_DOMAIN:-}' --also '${IOCONTACT_ALSO:-none}'"
WRAPPED="set -a; . /opt/iocontact/setup.env; set +a; rm -f /opt/iocontact/setup.env; $SETUP_CMD > /opt/iocontact/setup.log 2>&1"
if ! pct exec "$CTID" -- bash -c "$WRAPPED"; then
  msg_error "setup.sh failed inside the container; last lines of /opt/iocontact/setup.log:"
  pct exec "$CTID" -- tail -n 40 /opt/iocontact/setup.log || true
  msg_error "Fix the cause (often: the MariaDB user may not connect from the container's address), then run it again inside the container with IOCONTACT_DB=host:port/db:user:password (and IOCONTACT_ADMIN=name:password) in the environment: pct exec $CTID -- bash -c \"$SETUP_CMD\""
  exit 1
fi
msg_ok "Setup finished"

msg_ok "Completed successfully!\n"
echo -e "${CREATING}${GN}${APP} setup has been successfully initialized!${CL}"
echo -e "${INFO}${YW}Access it using the following URL:${CL}"
echo -e "${GATEWAY}${BGN}http://${IP}:${IOCONTACT_PORT:-8640}${CL}"
for a in ${IOCONTACT_ALSO//,/ }; do
  case "$a" in iosuite) p=8630;; iocalendar) p=8620;; iocontact) p=8640;; ionote) p=8610;; iohealth) p=8650;; iopix) p=8600;; *) p="";; esac
  [[ -n "$p" ]] && echo -e "${INFO}${YW}$a:${CL} ${BGN}http://${IP}:$p${CL}"
done
echo -e "${INFO}${YW}CardDAV: http://${IP}:${IOCONTACT_PORT:-8640}/dav/   LDAP: ${IP}:${IOCONTACT_LDAP_PORT:-389} (base dc=iocontact)${CL}"
