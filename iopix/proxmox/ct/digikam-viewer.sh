#!/usr/bin/env bash
# digiKam Viewer was renamed iopix. This file stays so old links, and the `update` command inside
# containers created before the rename, keep working: it runs proxmox/ct/iopix.sh.
source <(curl -fsSL https://raw.githubusercontent.com/avandeputte/iopix/main/proxmox/ct/iopix.sh)
