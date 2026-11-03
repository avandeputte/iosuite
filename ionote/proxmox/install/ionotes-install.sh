#!/usr/bin/env bash

# Copyright (c) 2026 Alex Van de Putte
# License: MIT
# Source: https://github.com/avandeputte/ionotes
# ionotes: runs inside the LXC, driven by proxmox/ct/ionotes.sh (community-scripts framework).
# This only installs the system packages and fetches the code; the ct script then runs the app's own
# setup.sh inside the container with the answers given on the host (database, OCR, admin, service).

source /dev/stdin <<<"$FUNCTIONS_FILE_PATH"
color
verb_ip6
catch_errors
setting_up_container
network_check
update_os

msg_info "Installing Dependencies"
$STD apt-get install -y \
  git \
  python3 \
  python3-venv \
  python3-pip \
  libheif1 \
  libglib2.0-0 \
  libgl1 \
  mariadb-client \
  curl
msg_ok "Installed Dependencies"

msg_info "Fetching ionotes"
REPO="${IONOTES_REPO:-https://github.com/avandeputte/ionotes}"
mkdir -p /opt/ionotes /opt/ionotes/data
$STD git clone --depth 1 "$REPO" /opt/ionotes/app
git -C /opt/ionotes/app rev-parse HEAD > /opt/ionotes/app/COMMIT  # the installed commit, shown in Settings › ionotes version
rm -rf /opt/ionotes/app/.git
msg_ok "Fetched ionotes"

motd_ssh
customize

msg_info "Cleaning up"
$STD apt-get -y autoremove
$STD apt-get -y autoclean
msg_ok "Cleaned"
