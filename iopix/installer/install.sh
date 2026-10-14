#!/bin/sh
# digiKam Viewer installer for Linux, version @VERSION@ (self-extracting; built by installer/make-installer.sh).
#
#   sh digikam-viewer-install.sh --photos /srv/photos --digikam-db /srv/digikamDB [options]
#
# Options
#   --photos DIR        the photo folder digiKam manages (required)
#   --digikam-db DIR    the folder containing digikam4.db (required unless --mysql)
#   --mysql HOST:PORT/DB:USER:PASSWORD   digiKam on MySQL/MariaDB instead of SQLite
#   --prefix DIR        install location            (default /opt/digikam-viewer)
#   --data DIR          the viewer's own data       (default PREFIX/data)
#   --port N            listen port                 (default 8600)
#   --host ADDR         listen address              (default 0.0.0.0)
#   --user NAME         service user                (default: digikam-viewer, created if missing)
#   --models LIST       models to download now      (default siglip2,yolox,geonames; "none" to skip)
#   --captions          also install PyTorch (CPU) + BLIP for photo descriptions (~1.5 GB more)
#   --read-only         lock the viewer to browsing (READ_ONLY=1)
#   --no-service        do not install/start the systemd unit (prints the run command)
#   --no-system-deps    do not touch the package manager (you install python3-venv, ffmpeg, exiftool, libheif)
#   --yes               no questions
#
# What it does: installs the system packages the viewer shells out to (ffmpeg, exiftool,
# libheif) with apt, dnf, zypper or pacman; unpacks the app under PREFIX/app; creates a
# Python venv in PREFIX/venv and installs the requirements; writes PREFIX/digikam-viewer.env;
# downloads the chosen models into DATA/models (install time, not first run); installs and
# starts a systemd service. Running it again upgrades the code and keeps DATA. The library is
# only ever read unless you edit metadata from the viewer, which backs every file up first.
set -e
PREFIX=/opt/digikam-viewer; DATA=""; PHOTOS=""; DKDB=""; MYSQL=""; PORT=8600; HOST=0.0.0.0; USER_NAME=digikam-viewer
MODELS="siglip2,yolox,geonames"; CAPTIONS=0; READ_ONLY=0; SERVICE=1; SYSDEPS=1; YES=0
say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
while [ $# -gt 0 ]; do
  case "$1" in
    --photos) PHOTOS="$2"; shift 2;; --digikam-db) DKDB="$2"; shift 2;; --mysql) MYSQL="$2"; shift 2;;
    --prefix) PREFIX="$2"; shift 2;; --data) DATA="$2"; shift 2;; --port) PORT="$2"; shift 2;; --host) HOST="$2"; shift 2;;
    --user) USER_NAME="$2"; shift 2;; --models) MODELS="$2"; shift 2;; --captions) CAPTIONS=1; shift;;
    --read-only) READ_ONLY=1; shift;; --no-service) SERVICE=0; shift;; --no-system-deps) SYSDEPS=0; shift;; --yes) YES=1; shift;;
    -h|--help) sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) die "unknown option $1 (try --help)";;
  esac
done
[ -n "$PHOTOS" ] || die "--photos DIR is required"
[ -d "$PHOTOS" ] || die "photo folder not found: $PHOTOS"
if [ -z "$MYSQL" ]; then
  [ -n "$DKDB" ] || die "--digikam-db DIR is required (the folder with digikam4.db), or --mysql"
  [ -f "$DKDB/digikam4.db" ] || die "digikam4.db not found in $DKDB"
fi
[ -n "$DATA" ] || DATA="$PREFIX/data"
[ "$(id -u)" = 0 ] || die "run as root (sudo); it installs packages and a system service"

# --- system packages -------------------------------------------------------------
if [ "$SYSDEPS" = 1 ]; then
  if command -v apt-get >/dev/null 2>&1; then
    say "Installing system packages with apt"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq --no-install-recommends python3 python3-venv python3-pip ffmpeg libimage-exiftool-perl libheif1 libglib2.0-0 ca-certificates curl >/dev/null
  elif command -v dnf >/dev/null 2>&1; then
    say "Installing system packages with dnf"
    dnf install -y -q python3 python3-pip perl-Image-ExifTool libheif glib2 ca-certificates curl >/dev/null
    # ffmpeg lives in RPM Fusion on Fedora/RHEL; the free build in Fedora's own repo is enough for thumbnails
    dnf install -y -q ffmpeg-free >/dev/null 2>&1 || dnf install -y -q ffmpeg >/dev/null 2>&1 || say "ffmpeg not installed (video thumbnails need it): enable RPM Fusion and install ffmpeg"
  elif command -v zypper >/dev/null 2>&1; then
    say "Installing system packages with zypper"
    zypper -n -q install python3 python3-pip ffmpeg exiftool libheif1 ca-certificates curl >/dev/null
  elif command -v pacman >/dev/null 2>&1; then
    say "Installing system packages with pacman"
    pacman -Sy --noconfirm --needed python python-pip ffmpeg perl-image-exiftool libheif ca-certificates curl >/dev/null
  else
    say "No known package manager; make sure python3 (3.10+) with venv, ffmpeg, exiftool and libheif are installed"
  fi
fi
PY=$(command -v python3) || die "python3 not found"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || die "python3 >= 3.10 is required (found $("$PY" -V))"
"$PY" -c 'import venv' 2>/dev/null || die "the python3 venv module is missing (apt: python3-venv)"
command -v exiftool >/dev/null 2>&1 || say "exiftool not found: metadata editing and the consistency checker will be unavailable"
command -v ffmpeg >/dev/null 2>&1 || say "ffmpeg not found: video thumbnails will be unavailable"

# --- unpack ------------------------------------------------------------------------
say "Installing into $PREFIX"
mkdir -p "$PREFIX" "$DATA"
LINE=$(grep -a -n '^__PAYLOAD_BELOW__$' "$0" | head -1 | cut -d: -f1)  # -a: the file ends in a binary payload
[ -n "$LINE" ] || die "payload missing: build this file with installer/make-installer.sh"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
tail -n +$((LINE + 1)) "$0" | tar xzf - -C "$TMP"
rm -rf "$PREFIX/app.new"; mv "$TMP/digikam-viewer" "$PREFIX/app.new"
if [ -d "$PREFIX/app" ]; then rm -rf "$PREFIX/app.old"; mv "$PREFIX/app" "$PREFIX/app.old"; fi
mv "$PREFIX/app.new" "$PREFIX/app"; rm -rf "$PREFIX/app.old"
VERSION=$(cat "$PREFIX/app/VERSION")

# --- python environment --------------------------------------------------------------
if [ ! -x "$PREFIX/venv/bin/python" ]; then say "Creating the Python environment"; "$PY" -m venv "$PREFIX/venv"; fi
VPY="$PREFIX/venv/bin/python"
say "Installing Python packages (this takes a few minutes the first time)"
"$VPY" -m pip install -q --upgrade pip >/dev/null
"$VPY" -m pip install -q -r "$PREFIX/app/requirements.txt" -r "$PREFIX/app/requirements-search.txt" -r "$PREFIX/app/requirements-ocr.txt" -r "$PREFIX/app/requirements-objects.txt"
if [ "$CAPTIONS" = 1 ]; then
  say "Installing PyTorch (CPU) and transformers for photo descriptions"
  "$VPY" -m pip install -q --extra-index-url https://download.pytorch.org/whl/cpu -r "$PREFIX/app/requirements-captions.txt"
fi

# --- service user and permissions ------------------------------------------------------
if ! id "$USER_NAME" >/dev/null 2>&1; then
  say "Creating user $USER_NAME"
  useradd --system --home-dir "$PREFIX" --shell /usr/sbin/nologin "$USER_NAME" 2>/dev/null || useradd -r -d "$PREFIX" -s /bin/false "$USER_NAME"
fi
chown -R "$USER_NAME" "$DATA"

# --- configuration ---------------------------------------------------------------------
ENVF="$PREFIX/digikam-viewer.env"
if [ ! -f "$ENVF" ]; then
  say "Writing $ENVF"
  {
    echo "# digiKam Viewer settings (variable names as in the README). Edit and restart the service."
    echo "PHOTOS_ROOT=$PHOTOS"
    if [ -n "$MYSQL" ]; then
      hostport=${MYSQL%%/*}; rest=${MYSQL#*/}; dbname=${rest%%:*}; rest=${rest#*:}; user=${rest%%:*}; pass=${rest#*:}
      echo "DIGIKAM_DB_TYPE=mysql"; echo "DIGIKAM_DB_HOST=${hostport%%:*}"; echo "DIGIKAM_DB_PORT=${hostport##*:}"
      echo "DIGIKAM_DB_NAME=$dbname"; echo "DIGIKAM_DB_USER=$user"; echo "DIGIKAM_DB_PASSWORD=$pass"
    else
      echo "DIGIKAM_DB_DIR=$DKDB"
    fi
    echo "DATA_DIR=$DATA"
    echo "VISION_ENGINE=portable"
    echo "HF_HUB_OFFLINE=1"
    echo "CAPTIONS=$CAPTIONS"
    echo "READ_ONLY=$READ_ONLY"
    echo "# models fetched when missing at start (the installer already downloaded them)"
    echo "AUTO_MODELS=$( [ "$MODELS" = none ] && echo "" || echo "$MODELS" )"
  } > "$ENVF"
  chmod 640 "$ENVF"; chown root:"$USER_NAME" "$ENVF" 2>/dev/null || true
else
  say "Keeping the existing $ENVF"
fi

# --- models (install time) ------------------------------------------------------------
if [ "$MODELS" != none ]; then
  say "Downloading models into $DATA/models: $MODELS"
  for key in $(echo "$MODELS" | tr ',' ' '); do
    if [ "$key" = blip ] && [ "$CAPTIONS" != 1 ]; then say "skipping blip (needs --captions)"; continue; fi
    ( cd "$PREFIX/app" && env DATA_DIR="$DATA" HF_HUB_OFFLINE=0 "$VPY" -m app.models download "$key" ) || say "download of $key failed; retry later from Maintenance > Models and data"
  done
  chown -R "$USER_NAME" "$DATA"
fi

# --- service ---------------------------------------------------------------------------
if [ "$SERVICE" = 1 ] && command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  say "Installing the systemd service"
  sed -e "s|@PREFIX@|$PREFIX|g" -e "s|@USER@|$USER_NAME|g" -e "s|@HOST@|$HOST|g" -e "s|@PORT@|$PORT|g" "$PREFIX/app/digikam-viewer.service" > /etc/systemd/system/digikam-viewer.service
  systemctl daemon-reload
  systemctl enable --now digikam-viewer.service
  sleep 2
  systemctl is-active --quiet digikam-viewer.service && say "digiKam Viewer $VERSION is running at http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo localhost):$PORT" || say "the service did not start; see: journalctl -u digikam-viewer"
else
  say "digiKam Viewer $VERSION installed. Start it with:"
  echo "  cd $PREFIX/app && set -a && . $ENVF && set +a && $VPY -m uvicorn app.main:app --host $HOST --port $PORT"
fi
say "Settings: $ENVF   Data: $DATA   Logs: journalctl -u digikam-viewer"
exit 0
