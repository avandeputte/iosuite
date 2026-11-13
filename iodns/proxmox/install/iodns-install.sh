#!/usr/bin/env bash

# Copyright (c) 2026 Alex Van de Putte
# License: GPL-3.0-or-later
# Source: https://github.com/avandeputte/iodns
# ioDNS: runs inside the LXC, driven by proxmox/ct/iodns.sh (community-scripts framework).
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

msg_info "Fetching ioDNS"
REPO="${IODNS_REPO:-https://github.com/avandeputte/iodns}"
mkdir -p /opt/iodns
$STD git clone --depth 1 "$REPO" /opt/iodns/app
git -C /opt/iodns/app rev-parse HEAD > /opt/iodns/app/COMMIT
rm -rf /opt/iodns/app/.git
msg_ok "Fetched ioDNS"

motd_ssh
customize

msg_info "Cleaning up"
$STD apt-get -y autoremove
$STD apt-get -y autoclean
msg_ok "Cleaned"
