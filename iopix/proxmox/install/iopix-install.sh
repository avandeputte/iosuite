#!/usr/bin/env bash

# Copyright (c) 2026 Alex Van de Putte
# License: MIT
# Source: https://github.com/avandeputte/iopix
# iopix: runs inside the LXC, driven by proxmox/ct/iopix.sh (community-scripts framework).
# This only installs the system packages and fetches the code; the ct script then runs the app's own
# setup.sh inside the container with the answers given on the host (features, models, admin, service).

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
  ffmpeg \
  libimage-exiftool-perl \
  libheif1 \
  libglib2.0-0 \
  mariadb-client \
  curl
msg_ok "Installed Dependencies"

msg_info "Fetching iopix"
REPO="${IOPIX_REPO:-https://github.com/avandeputte/iopix}"
mkdir -p /opt/iopix /opt/iopix/data /library
$STD git clone --depth 1 "$REPO" /opt/iopix/app
git -C /opt/iopix/app rev-parse HEAD > /opt/iopix/app/COMMIT  # the installed commit, shown in Maintenance
rm -rf /opt/iopix/app/.git
msg_ok "Fetched iopix"

motd_ssh
customize

msg_info "Cleaning up"
$STD apt-get -y autoremove
$STD apt-get -y autoclean
msg_ok "Cleaned"
