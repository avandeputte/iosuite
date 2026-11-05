#!/usr/bin/env bash
# ionotes LXC for Proxmox VE, in the community-scripts (ProxmoxVE) framework layout, the same as iopix's:
# this is the ct/ script; proxmox/install/ionotes-install.sh runs inside the container.
#
# It asks about the app first: where the notes are kept (MariaDB/MySQL host, port, database, user, password, or a
# SQLite file in the container), where the Shared ioSuite database is (accounts and suite-wide settings, shared by
# the ioThing apps; database and user `iosuite` by default), whether pictures added in the web app get their text read (RapidOCR), and the
# admin account; then the framework's own questions (resources, network). It then creates the container and runs
# the app's own setup.sh inside with those answers, which installs the packages, writes the settings, creates the
# tables and the admin and starts the service on port 8610.
#
# Until the scripts are merged upstream, the framework is pointed at this repository for the
# install script (COMMUNITY_SCRIPTS_URL below; the core engine still comes from community-scripts).
# Run on the Proxmox host as root:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/ionotes/main/proxmox/ct/ionotes.sh)"
export COMMUNITY_SCRIPTS_URL="${COMMUNITY_SCRIPTS_URL:-https://raw.githubusercontent.com/avandeputte/ionotes/main/proxmox}"
_cs_boot="${COMMUNITY_SCRIPTS_CORE_DIR:-$(dirname "${BASH_SOURCE[0]}")/../../core}/core/build.func"
source "$_cs_boot" 2>/dev/null || source <(curl -fsSL "${COMMUNITY_SCRIPTS_CORE_URL:-https://raw.githubusercontent.com/community-scripts/core/main}/core/build.func")
# Copyright (c) 2026 Alex Van de Putte
# License: MIT
# Source: https://github.com/avandeputte/ionotes

APP="ionotes"
var_tags="${var_tags:-notes;productivity}"
var_cpu="${var_cpu:-2}"
var_ram="${var_ram:-2048}"
var_disk="${var_disk:-8}"
var_os="${var_os:-debian}"
var_version="${var_version:-13}"
var_arm64="${var_arm64:-yes}"
var_unprivileged="${var_unprivileged:-1}"

header_info "$APP"
variables
color
catch_errors

# ---- the app's own questions (whiptail on the host; env vars IONOTES_* skip them for unattended runs)
#   IONOTES_DB        sqlite, or host:port/db:user:pass (MariaDB/MySQL)
#   IONOTES_SUITE_DB  host:port/db:user:pass (the Shared ioSuite database, MariaDB)
#   IONOTES_FEATURES  ocr or none
#   IONOTES_ADMIN     name:password (empty: create the admin later in the web app)
ask_app_settings() {
  local bt="ionotes"
  if [[ -z "${IONOTES_DB:-}" ]]; then
    if whiptail --backtitle "$bt" --yesno "Keep the notes in MySQL/MariaDB?\n\nIt holds the notes, their pictures (as BLOBs), folders, tags, users and settings.\n\nNo: a SQLite file in the container's data folder (a quick try; the apps' sync works the same)." 14 76 3>&1 1>&2 2>&3; then
      local h p d u w
      h=$(whiptail --backtitle "$bt" --inputbox "MariaDB host or IP" 9 60 "192.168.1.89" 3>&1 1>&2 2>&3) || exit 1
      p=$(whiptail --backtitle "$bt" --inputbox "Port" 9 60 "3306" 3>&1 1>&2 2>&3) || exit 1
      d=$(whiptail --backtitle "$bt" --inputbox "Database (created if the user may)" 9 60 "notes" 3>&1 1>&2 2>&3) || exit 1
      u=$(whiptail --backtitle "$bt" --inputbox "User" 9 60 "notes" 3>&1 1>&2 2>&3) || exit 1
      w=$(whiptail --backtitle "$bt" --passwordbox "Password" 9 60 3>&1 1>&2 2>&3) || exit 1
      IONOTES_DB="$h:$p/$d:$u:$w"
    else
      IONOTES_DB="sqlite"
    fi
  fi
  if [[ -z "${IONOTES_SUITE_DB:-}" ]]; then
    local sh sp sd su sw
    sh="${IONOTES_DB%%/*}"; sh="${sh%%:*}"; [[ "$IONOTES_DB" == sqlite ]] && sh="192.168.1.89"
    sh=$(whiptail --backtitle "$bt" --inputbox "Shared ioSuite database: MariaDB host or IP\n\nAccounts, sessions and suite-wide settings, shared with the other ioThing apps (one sign-in for all)." 12 76 "$sh" 3>&1 1>&2 2>&3) || exit 1
    sp=$(whiptail --backtitle "$bt" --inputbox "Shared ioSuite database: port" 9 60 "3306" 3>&1 1>&2 2>&3) || exit 1
    sd=$(whiptail --backtitle "$bt" --inputbox "Shared ioSuite database: database (created if the user may)" 9 72 "iosuite" 3>&1 1>&2 2>&3) || exit 1
    su=$(whiptail --backtitle "$bt" --inputbox "Shared ioSuite database: user" 9 60 "iosuite" 3>&1 1>&2 2>&3) || exit 1
    sw=$(whiptail --backtitle "$bt" --passwordbox "Shared ioSuite database: password" 9 60 3>&1 1>&2 2>&3) || exit 1
    IONOTES_SUITE_DB="$sh:$sp/$sd:$su:$sw"
  fi
  if [[ -z "${IONOTES_FEATURES:-}" ]]; then
    if whiptail --backtitle "$bt" --yesno "Read the text in pictures added in the web app (RapidOCR, ~60 MB)?\n\nThe Mac and iPhone apps read text on the device; this is only for pictures uploaded in the browser." 12 76 3>&1 1>&2 2>&3; then IONOTES_FEATURES=ocr; else IONOTES_FEATURES=none; fi
  fi
  if [[ -z "${IONOTES_ADMIN+x}" ]]; then
    local an aw
    an=$(whiptail --backtitle "$bt" --inputbox "Admin user name" 9 72 "admin" 3>&1 1>&2 2>&3) || exit 1
    aw=$(whiptail --backtitle "$bt" --passwordbox "Admin password (8 characters or more; empty: create it later in the web app)" 9 72 3>&1 1>&2 2>&3) || exit 1
    [[ -n "$aw" ]] && IONOTES_ADMIN="$an:$aw" || IONOTES_ADMIN=""
  fi
}

function update_script() {
  header_info
  check_container_storage
  check_container_resources
  if [[ ! -d /opt/ionotes/app/app ]]; then
    msg_error "No ${APP} Installation Found!"
    exit
  fi
  msg_info "Updating ${APP}"
  # the app's own updater: latest code, same settings, data and packages, service restarted; its output is shown
  if sh /opt/ionotes/app/update.sh; then msg_ok "Updated successfully!"; else msg_error "update.sh failed; see the lines above"; exit 1; fi
  exit
}

if command -v pveversion >/dev/null 2>&1; then ask_app_settings; fi  # on the Proxmox host; inside the container `update` needs no answers
start
build_container
description

# ---- the app's own setup with the answers
msg_info "Running the app's setup inside the container (packages, settings, tables, admin, service)"
SECRETS=""  # setup.sh reads IONOTES_MYSQL, IONOTES_SUITE_DB and IONOTES_ADMIN from its environment: the passwords stay off every command line
if [[ "${IONOTES_DB:-sqlite}" == sqlite ]]; then
  DBARG="--sqlite"
else
  DBARG=""; SECRETS+="IONOTES_MYSQL=$(printf '%q' "$IONOTES_DB")"$'\n'
fi
if [[ -n "${IONOTES_SUITE_DB:-}" ]]; then SECRETS+="IONOTES_SUITE_DB=$(printf '%q' "$IONOTES_SUITE_DB")"$'\n'; fi
if [[ -n "${IONOTES_ADMIN:-}" ]]; then SECRETS+="IONOTES_ADMIN=$(printf '%q' "$IONOTES_ADMIN")"$'\n'; ADMINARG=""; else ADMINARG="--no-admin"; fi
# the answers with passwords go in as a root-only file (pushed, read into setup.sh's environment, removed), never as arguments
SECF="$(mktemp)"; chmod 600 "$SECF"; printf '%s' "$SECRETS" > "$SECF"
pct push "$CTID" "$SECF" /opt/ionotes/setup.env --perms 0600 --user 0 --group 0
rm -f "$SECF"
SETUP_CMD="cd /opt/ionotes/app && sh ./setup.sh --yes $DBARG $ADMINARG --data /opt/ionotes/data --features '${IONOTES_FEATURES:-none}' --service --no-system-deps --port 8610"
WRAPPED="set -a; . /opt/ionotes/setup.env; set +a; rm -f /opt/ionotes/setup.env; $SETUP_CMD > /opt/ionotes/setup.log 2>&1"
# the setup's output is kept in the container; on failure the last lines are shown here
if ! pct exec "$CTID" -- bash -c "$WRAPPED"; then
  msg_error "setup.sh failed inside the container; last lines of /opt/ionotes/setup.log:"
  pct exec "$CTID" -- tail -n 40 /opt/ionotes/setup.log || true
  msg_error "Fix the cause, then run it again inside the container with IONOTES_ADMIN=name:password (and IONOTES_MYSQL=host:port/db:user:password for MariaDB, IONOTES_SUITE_DB=host:port/db:user:password for the Shared ioSuite database) in the environment: pct exec $CTID -- bash -c \"$SETUP_CMD\""
  exit 1
fi
msg_ok "Setup finished"

msg_ok "Completed successfully!\n"
echo -e "${CREATING}${GN}${APP} setup has been successfully initialized!${CL}"
echo -e "${INFO}${YW}Access it using the following URL:${CL}"
echo -e "${GATEWAY}${BGN}http://${IP}:8610${CL}"
[[ -z "${IONOTES_ADMIN:-}" ]] && echo -e "${INFO}${YW}No admin yet: open the URL and choose Settings › Create the admin account.${CL}"
echo -e "${INFO}${YW}Put it behind an HTTPS reverse proxy (Caddy, Nginx Proxy Manager, a Cloudflare tunnel) before the apps use it from outside your network.${CL}"
