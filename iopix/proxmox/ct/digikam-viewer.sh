#!/usr/bin/env bash
# digiKam Viewer LXC for Proxmox VE, in the community-scripts (ProxmoxVE) framework layout:
# this is the ct/ script; proxmox/install/digikam-viewer-install.sh runs inside the container.
#
# Until the scripts are merged upstream, the framework is pointed at this repository for the
# install script (COMMUNITY_SCRIPTS_URL below; the core engine still comes from community-scripts).
# Run on the Proxmox host as root:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/digikam-viewer/main/proxmox/ct/digikam-viewer.sh)"
#
# The container mounts the digiKam database folder and the photo folder from the host
# (bind mounts you add after creation, see the end of the install), installs the viewer under
# /opt/digikam-viewer, downloads the models (SigLIP 2, YOLOX, GeoNames; ~1.6 GB) at install
# time and runs it as a systemd service on port 8600.
export COMMUNITY_SCRIPTS_URL="${COMMUNITY_SCRIPTS_URL:-https://raw.githubusercontent.com/avandeputte/digikam-viewer/main/proxmox}"
_cs_boot="${COMMUNITY_SCRIPTS_CORE_DIR:-$(dirname "${BASH_SOURCE[0]}")/../../core}/core/build.func"
source "$_cs_boot" 2>/dev/null || source <(curl -fsSL "${COMMUNITY_SCRIPTS_CORE_URL:-https://raw.githubusercontent.com/community-scripts/core/main}/core/build.func")
# Copyright (c) 2026 Alex Van de Putte
# License: MIT
# Source: https://github.com/avandeputte/digikam-viewer

APP="digiKam-Viewer"
var_tags="${var_tags:-photos;media}"
var_cpu="${var_cpu:-4}"
var_ram="${var_ram:-4096}"
var_disk="${var_disk:-16}"
var_os="${var_os:-debian}"
var_version="${var_version:-13}"
var_arm64="${var_arm64:-yes}"
var_unprivileged="${var_unprivileged:-1}"

header_info "$APP"
variables
color
catch_errors

function update_script() {
  header_info
  check_container_storage
  check_container_resources
  if [[ ! -d /opt/digikam-viewer/app ]]; then
    msg_error "No ${APP} Installation Found!"
    exit
  fi
  msg_info "Stopping Service"
  systemctl stop digikam-viewer
  msg_ok "Stopped Service"

  msg_info "Updating ${APP}"
  REPO="${DIGIKAM_VIEWER_REPO:-https://github.com/avandeputte/digikam-viewer}"
  rm -rf /opt/digikam-viewer/app.new
  $STD git clone --depth 1 "$REPO" /opt/digikam-viewer/app.new
  rm -rf /opt/digikam-viewer/app.new/.git /opt/digikam-viewer/app.new/data
  rm -rf /opt/digikam-viewer/app.old
  mv /opt/digikam-viewer/app /opt/digikam-viewer/app.old
  mv /opt/digikam-viewer/app.new /opt/digikam-viewer/app
  rm -rf /opt/digikam-viewer/app.old
  cd /opt/digikam-viewer/app
  $STD uv pip install --python /opt/digikam-viewer/venv/bin/python -e "/opt/digikam-viewer/app[ai]"
  msg_ok "Updated ${APP}"

  msg_info "Starting Service"
  systemctl start digikam-viewer
  msg_ok "Started Service"
  msg_ok "Updated successfully!"
  exit
}

start
build_container
description

msg_ok "Completed successfully!\n"
echo -e "${CREATING}${GN}${APP} setup has been successfully initialized!${CL}"
echo -e "${INFO}${YW}Access it using the following URL:${CL}"
echo -e "${GATEWAY}${BGN}http://${IP}:8600${CL}"
echo -e "${INFO}${YW}Now bind-mount the library into the container (on the host), then restart it:${CL}"
echo -e "  pct set ${CTID} -mp0 /path/to/digikamDB,mp=/library/digikamDB,ro=1 -mp1 /path/to/photos,mp=/library/photos,ro=1"
echo -e "  pct reboot ${CTID}"
echo -e "${INFO}${YW}Drop ro=1 from the photos mount to edit metadata, from the digikamDB mount for database writes (digiKam closed).${CL}"
