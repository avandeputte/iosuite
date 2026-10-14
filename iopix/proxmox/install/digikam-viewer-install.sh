#!/usr/bin/env bash

# Copyright (c) 2026 Alex Van de Putte
# License: MIT
# Source: https://github.com/avandeputte/digikam-viewer
# digiKam Viewer: runs inside the LXC, driven by proxmox/ct/digikam-viewer.sh (community-scripts framework).

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
  ffmpeg \
  libimage-exiftool-perl \
  libheif1 \
  libglib2.0-0
msg_ok "Installed Dependencies"

PYTHON_VERSION="3.12" setup_uv

msg_info "Installing digiKam Viewer"
REPO="${DIGIKAM_VIEWER_REPO:-https://github.com/avandeputte/digikam-viewer}"
mkdir -p /opt/digikam-viewer /opt/digikam-viewer/data /library
$STD git clone --depth 1 "$REPO" /opt/digikam-viewer/app
rm -rf /opt/digikam-viewer/app/.git
cd /opt/digikam-viewer/app
$STD uv venv /opt/digikam-viewer/venv --python 3.12
$STD uv pip install --python /opt/digikam-viewer/venv/bin/python -e "/opt/digikam-viewer/app[ai]"
msg_ok "Installed digiKam Viewer"

msg_info "Writing configuration"
cat <<EOF >/opt/digikam-viewer/digikam-viewer.env
# digiKam Viewer settings (variable names as in the README). The library is bind-mounted from
# the Proxmox host at /library (see the end of the install). Edit and: systemctl restart digikam-viewer
DIGIKAM_DB_DIR=/library/digikamDB
PHOTOS_ROOT=/library/photos
DATA_DIR=/opt/digikam-viewer/data
HF_HUB_OFFLINE=1
# the container cannot see digiKam's process on the host: confirm it is closed before database writes
DIGIKAM_CHECK=ask
# models fetched when missing at start (also downloaded below, at install time)
AUTO_MODELS=${AUTO_MODELS:-siglip2,yolox,geonames}
EOF
msg_ok "Wrote configuration"

msg_info "Downloading models (SigLIP 2, YOLOX, GeoNames; about 1.6 GB, patience)"
for key in $(echo "${AUTO_MODELS:-siglip2,yolox,geonames}" | tr ',' ' '); do
  $STD env DATA_DIR=/opt/digikam-viewer/data HF_HUB_OFFLINE=0 /opt/digikam-viewer/venv/bin/python -m app.models download "$key"
done
msg_ok "Downloaded models"

msg_info "Creating Service"
cat <<EOF >/etc/systemd/system/digikam-viewer.service
[Unit]
Description=digiKam Viewer
After=network.target

[Service]
Type=simple
EnvironmentFile=/opt/digikam-viewer/digikam-viewer.env
WorkingDirectory=/opt/digikam-viewer/app
ExecStart=/opt/digikam-viewer/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8600
Restart=always
RestartSec=5
Nice=5

[Install]
WantedBy=multi-user.target
EOF
systemctl enable -q --now digikam-viewer
msg_ok "Created Service"

motd_ssh
customize

msg_info "Cleaning up"
$STD apt-get -y autoremove
$STD apt-get -y autoclean
msg_ok "Cleaned"
