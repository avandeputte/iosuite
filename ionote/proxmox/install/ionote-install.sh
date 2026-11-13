#!/usr/bin/env bash

# Copyright (c) 2026 Alex Van de Putte
# License: GPL-3.0-or-later
# Source: https://github.com/avandeputte/iosuite (ionote/)
# ionote: runs inside the LXC, driven by proxmox/ct/ionote.sh (community-scripts framework).
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

msg_info "Fetching ionote"
REPO="${IONOTE_REPO:-https://github.com/avandeputte/iosuite}"  # the suite's repository: this app in ionote/, the shared library in shared/
mkdir -p /opt/ionote /opt/ionote/data
$STD git clone --depth 1 "$REPO" /tmp/iosuite-src
mkdir -p /opt/ionote/app
cp -a /tmp/iosuite-src/ionote/. /opt/ionote/app/
cp -a /tmp/iosuite-src/shared /opt/ionote/app/shared
cp /tmp/iosuite-src/LICENSE /opt/ionote/app/LICENSE
git -C /tmp/iosuite-src rev-parse HEAD > /opt/ionote/app/COMMIT  # the installed commit, shown in Settings › ionote version
rm -rf /tmp/iosuite-src
msg_ok "Fetched ionote"

motd_ssh
customize

msg_info "Cleaning up"
$STD apt-get -y autoremove
$STD apt-get -y autoclean
msg_ok "Cleaned"
