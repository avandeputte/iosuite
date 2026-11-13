#!/usr/bin/env bash

# Copyright (c) 2026 Alex Van de Putte
# License: GPL-3.0-or-later
# Source: https://github.com/avandeputte/iosuite (iostart/)
# ioStart: runs inside the LXC, driven by proxmox/ct/iostart.sh (community-scripts framework).
# This only installs the system packages and fetches the code; the ct script then runs the app's own
# setup.sh inside the container with the answers given on the host (database, ports, admin, service).

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
  mariadb-client \
  curl
msg_ok "Installed Dependencies"

msg_info "Fetching ioStart"
REPO="${IOSTART_REPO:-https://github.com/avandeputte/iosuite}"  # the suite's repository: this app in iostart/, the shared library in shared/
mkdir -p /opt/iostart
$STD git clone --depth 1 "$REPO" /tmp/iosuite-src
mkdir -p /opt/iostart/app
cp -a /tmp/iosuite-src/iostart/. /opt/iostart/app/
cp -a /tmp/iosuite-src/shared /opt/iostart/app/shared
cp /tmp/iosuite-src/LICENSE /opt/iostart/app/LICENSE
git -C /tmp/iosuite-src rev-parse HEAD > /opt/iostart/app/COMMIT
rm -rf /tmp/iosuite-src
msg_ok "Fetched ioStart"

motd_ssh
customize

msg_info "Cleaning up"
$STD apt-get -y autoremove
$STD apt-get -y autoclean
msg_ok "Cleaned"
