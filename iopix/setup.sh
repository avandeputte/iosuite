#!/bin/sh
# digiKam Viewer setup: one interactive script that asks everything and does all the work.
#
#   ./setup.sh                 ask the questions, then install packages, download models,
#                              write the settings, create the admin and start the service
#   ./setup.sh --yes ...       no questions: defaults and the flags below
#
# Flags (each one skips its question): --photos DIR  --sqlite DIR | --mysql HOST:PORT/DB:USER:PASS
#   --features search,places,objects,ocr,captions  --search-model clip|siglip2  --port N
#   --admin NAME:PASSWORD | --no-admin   --service | --no-service   --data DIR   --python PATH
# Run it again at any time: it keeps what is installed and only adds what you choose.
set -e
cd "$(dirname "$0")"
APP="$(pwd)"
OS="$(uname -s)"
say() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
YES=0; PHOTOS=""; SQLITE=""; MYSQL=""; FEATURES=""; SEARCH_MODEL=""; PORT=""; ADMIN=""; NO_ADMIN=0; SERVICE=""; DATA=""; PY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --yes) YES=1; shift;; --photos) PHOTOS="$2"; shift 2;; --sqlite) SQLITE="$2"; shift 2;; --mysql) MYSQL="$2"; shift 2;;
    --features) FEATURES="$2"; shift 2;; --search-model) SEARCH_MODEL="$2"; shift 2;; --port) PORT="$2"; shift 2;;
    --admin) ADMIN="$2"; shift 2;; --no-admin) NO_ADMIN=1; shift;; --service) SERVICE=1; shift;; --no-service) SERVICE=0; shift;;
    --data) DATA="$2"; shift 2;; --python) PY="$2"; shift 2;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) die "unknown option $1 (try --help)";;
  esac
done
# questions are read from standard input: the terminal, or piped answers (one per line); --yes takes every default
if [ "$YES" = 1 ]; then TTY=""; else TTY=/dev/stdin; fi
ask() {  # ask VAR "question" "default"
  _v="$1"; _q="$2"; _d="$3"
  if [ "$YES" = 1 ] || [ -z "$TTY" ]; then eval "$_v=\"\$_d\""; return; fi
  printf '%s [%s]: ' "$_q" "$_d"; read -r _a < "$TTY" || _a=""
  [ -n "$_a" ] && eval "$_v=\"\$_a\"" || eval "$_v=\"\$_d\""
}
yesno() {  # yesno "question" y|n -> returns 0 for yes
  _d="$2"
  if [ "$YES" = 1 ] || [ -z "$TTY" ]; then [ "$_d" = y ]; return; fi
  printf '%s [%s]: ' "$1" "$([ "$_d" = y ] && echo Y/n || echo y/N)"; read -r _a < "$TTY" || _a=""
  case "${_a:-$_d}" in y|Y|yes|YES) return 0;; *) return 1;; esac
}
secret() {  # secret VAR "question"
  if [ -z "$TTY" ]; then eval "$1=\"\""; return; fi
  printf '%s: ' "$2"; stty -echo 2>/dev/null < "$TTY" || true; read -r _a < "$TTY" || _a=""; stty echo 2>/dev/null < "$TTY" || true; echo; eval "$1=\"\$_a\""
}

say "digiKam Viewer setup"
echo "This asks a few questions, installs the Python packages, downloads the AI models you choose, writes the"
echo "settings and starts the viewer as a service. Nothing in your photo library or digiKam database is changed."

# --- python ----------------------------------------------------------------------------------------
[ -n "$PY" ] || PY="$(command -v python3.12 || command -v python3.11 || command -v python3.10 || command -v python3 || true)"
[ -n "$PY" ] || die "python3 (3.10 or newer) is needed"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || die "python3 >= 3.10 is needed (found $("$PY" -V))"
for t in exiftool ffmpeg; do command -v $t >/dev/null 2>&1 || echo "note: $t is not installed; $([ $t = exiftool ] && echo 'metadata editing and the consistency checker' || echo 'video thumbnails') will be unavailable (macOS: brew install $t; Debian: apt install $([ $t = exiftool ] && echo libimage-exiftool-perl || echo ffmpeg))"; done

# --- the library ------------------------------------------------------------------------------------
say "Your library"
ask PHOTOS "Folder with the photos digiKam manages" "${PHOTOS:-$HOME/Pictures/photos}"
[ -d "$PHOTOS" ] || die "folder not found: $PHOTOS"
if [ -z "$MYSQL" ] && [ -z "$SQLITE" ]; then
  if yesno "Is digiKam's database on MySQL/MariaDB (no: SQLite file digikam4.db)?" n; then
    ask MH "MySQL host" "127.0.0.1"; ask MP "port" "3306"; ask MD "database" "digikam"; ask MU "user" "digikam"; secret MW "password"
    MYSQL="$MH:$MP/$MD:$MU:$MW"
  else
    ask SQLITE "Folder containing digikam4.db" "$HOME/Pictures/digikamDB"
  fi
fi
[ -z "$SQLITE" ] || [ -f "$SQLITE/digikam4.db" ] || die "digikam4.db not found in $SQLITE"
ask DATA "Folder for the viewer's own data (index, thumbnails, models, backups)" "${DATA:-$APP/data}"
ask PORT "Port" "${PORT:-8600}"

# --- features ---------------------------------------------------------------------------------------
say "Features (each one downloads a model into $DATA/models)"
if [ -z "$FEATURES" ]; then
  F=""
  yesno "Content search: find photos by what is in them (SigLIP 2, ~1.5 GB; or CLIP, ~600 MB)" y && F="$F,search"
  yesno "Places: town/region/country for GPS positions, offline (GeoNames, ~30 MB)" y && F="$F,places"
  yesno "Object detection: people, animals, vehicles... (YOLOX, 35 MB)" y && F="$F,objects"
  yesno "Text in photos: signs, jerseys, documents (RapidOCR, ~60 MB)" y && F="$F,ocr"
  yesno "Photo descriptions: one sentence per photo (BLIP + PyTorch, ~1.5 GB, slow without a GPU)" n && F="$F,captions"
  FEATURES="${F#,}"
fi
has() { case ",$FEATURES," in *",$1,"*) return 0;; *) return 1;; esac; }
if has search && [ -z "$SEARCH_MODEL" ]; then
  if yesno "Use SigLIP 2 for content search (slightly better; CLIP indexes 4x faster)?" y; then SEARCH_MODEL=siglip2; else SEARCH_MODEL=clip; fi
fi

# --- admin and service ------------------------------------------------------------------------------
say "Accounts and service"
if [ -z "$ADMIN" ] && [ "$NO_ADMIN" = 0 ]; then
  if yesno "Create an admin account now (visitors then browse read-only; editors and admins sign in)?" y; then
    ask AN "Admin user name" "admin"; secret AW "Admin password (8 characters or more)"
    [ -n "$AW" ] && ADMIN="$AN:$AW" || echo "no password given; skipping the admin account (Settings can create it later)"
  fi
fi
if [ -z "$SERVICE" ]; then
  case "$OS" in Darwin) SVC="a launchd login item";; *) SVC="a systemd service";; esac
  yesno "Start the viewer at login as $SVC?" y && SERVICE=1 || SERVICE=0
fi

# --- do the work ------------------------------------------------------------------------------------
say "Python environment"
VENV="$APP/.venv"
[ -x "$VENV/bin/python" ] || "$PY" -m venv "$VENV"
VPY="$VENV/bin/python"
pipi() { if command -v uv >/dev/null 2>&1; then uv pip install -q -p "$VPY" "$@"; else "$VPY" -m pip install -q "$@"; fi; }
"$VPY" -m pip --version >/dev/null 2>&1 || command -v uv >/dev/null 2>&1 || "$VPY" -m ensurepip -q
echo "installing the base packages"; pipi -r requirements.txt
has search  && { echo "installing content search";  pipi -r requirements-search.txt; }
has objects && { echo "installing object detection"; pipi -r requirements-objects.txt; }
has ocr     && { echo "installing text recognition"; pipi -r requirements-ocr.txt; }
has captions && { echo "installing PyTorch and transformers (large)"; pipi --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-captions.txt; }

say "Settings"
ENVF="$APP/digikam-viewer.env"
{
  echo "# digiKam Viewer settings, written by setup.sh (variable names as in the README). Edit and restart the service."
  echo "PHOTOS_ROOT=$PHOTOS"
  if [ -n "$MYSQL" ]; then
    hp=${MYSQL%%/*}; rest=${MYSQL#*/}; db=${rest%%:*}; rest=${rest#*:}; us=${rest%%:*}; pw=${rest#*:}
    echo "DIGIKAM_DB_TYPE=mysql"; echo "DIGIKAM_DB_HOST=${hp%%:*}"; echo "DIGIKAM_DB_PORT=${hp##*:}"; echo "DIGIKAM_DB_NAME=$db"; echo "DIGIKAM_DB_USER=$us"; echo "DIGIKAM_DB_PASSWORD=$pw"
  else
    echo "DIGIKAM_DB_DIR=$SQLITE"
  fi
  echo "DATA_DIR=$DATA"
  echo "VISION_ENGINE=portable"
  echo "HF_HUB_OFFLINE=1"
  echo "CAPTIONS=$(has captions && echo 1 || echo 0)"
  M=""; has search && M="$M,$SEARCH_MODEL"; has objects && M="$M,yolox"; has places && M="$M,geonames"; has captions && M="$M,blip"
  echo "# models fetched when missing at start (setup downloads them now)"; echo "AUTO_MODELS=${M#,}"
} > "$ENVF"
chmod 600 "$ENVF"
mkdir -p "$DATA"
set -a; . "$ENVF"; set +a
echo "wrote $ENVF"
if [ -n "$MYSQL" ]; then
  echo "testing the database connection"
  "$VPY" -c "from app import dkdb; r = dkdb.test_connection(); print(f\"  OK: {r['images']} photos, {r['tags']} tags, DBVersion {r['dbVersion']}, root {r['roots']}\")" || die "could not connect to the database with those settings"
fi

say "Models"
for key in $(echo "$AUTO_MODELS" | tr ',' ' '); do
  echo "downloading $key"
  HF_HUB_OFFLINE=0 "$VPY" -m app.models download "$key" || echo "  download of $key failed; retry later from Maintenance > Models and data"
done
[ -n "$SEARCH_MODEL" ] && "$VPY" -c "from app import state; state.init(); state.set_setting('search_model', '$SEARCH_MODEL')"

if [ -n "$ADMIN" ]; then
  say "Admin account"
  "$VPY" -c "
import sys; from app import state, users
state.init(); users.init()
name, pw = sys.argv[1].split(':', 1)
print('  created', users.create(name, pw, 'admin')['name']) if not users.any_users() else print('  users already exist; not touched')
" "$ADMIN"
fi

say "Service"
if [ "$SERVICE" = 1 ] && [ "$OS" = Darwin ]; then
  PL="$HOME/Library/LaunchAgents/com.digikam-viewer.plist"
  "$VPY" - "$PL" "$APP" "$VPY" "$PORT" "$ENVF" <<'PYEOF'
import plistlib, sys, os
pl, app, vpy, port, envf = sys.argv[1:6]
env = {"PATH": "/opt/homebrew/bin:/opt/homebrew/opt/mysql-client/bin:/usr/local/bin:/usr/bin:/bin"}
for line in open(envf):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); env[k] = v
d = {"Label": "com.digikam-viewer", "ProgramArguments": [vpy, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(port)],
     "WorkingDirectory": app, "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 10, "EnvironmentVariables": env,
     "StandardOutPath": os.path.join(env["DATA_DIR"], "server.log"), "StandardErrorPath": os.path.join(env["DATA_DIR"], "server.log")}
os.makedirs(os.path.dirname(pl), exist_ok=True)
with open(pl, "wb") as f: plistlib.dump(d, f)
print("  wrote", pl)
PYEOF
  launchctl bootout "gui/$(id -u)/com.digikam-viewer" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PL" && echo "  started (login item)"
elif [ "$SERVICE" = 1 ] && command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  UNIT=/etc/systemd/system/digikam-viewer.service
  if [ "$(id -u)" = 0 ]; then SUDO=""; else SUDO="sudo"; fi
  $SUDO sh -c "cat > $UNIT" <<UEOF
[Unit]
Description=digiKam Viewer
After=network.target

[Service]
Type=simple
User=$(id -un)
EnvironmentFile=$ENVF
WorkingDirectory=$APP
ExecStart=$VPY -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=5
Nice=5

[Install]
WantedBy=multi-user.target
UEOF
  $SUDO systemctl daemon-reload && $SUDO systemctl enable --now digikam-viewer && echo "  started (systemd)"
else
  echo "  not installed as a service. Start the viewer with:"
  echo "    cd $APP && set -a && . $ENVF && set +a && $VPY -m uvicorn app.main:app --host 0.0.0.0 --port $PORT"
fi
say "Done: http://localhost:$PORT   settings: $ENVF   data: $DATA"
