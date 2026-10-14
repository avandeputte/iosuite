#!/usr/bin/env bash

# Copyright (c) 2026 Alex Van de Putte
# License: MIT
# Source: https://github.com/avandeputte/digikam-viewer
# digiKam Viewer: runs inside the LXC, driven by proxmox/ct/digikam-viewer.sh (community-scripts framework).
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
  libglib2.0-0
msg_ok "Installed Dependencies"

msg_info "Fetching digiKam Viewer"
REPO="${DIGIKAM_VIEWER_REPO:-https://github.com/avandeputte/digikam-viewer}"
mkdir -p /opt/digikam-viewer /opt/digikam-viewer/data /library
$STD git clone --depth 1 "$REPO" /opt/digikam-viewer/app
git -C /opt/digikam-viewer/app rev-parse HEAD > /opt/digikam-viewer/app/COMMIT  # the installed commit, shown in Maintenance
rm -rf /opt/digikam-viewer/app/.git
msg_ok "Fetched digiKam Viewer"

motd_ssh
customize

msg_info "Cleaning up"
$STD apt-get -y autoremove
$STD apt-get -y autoclean
msg_ok "Cleaned"
