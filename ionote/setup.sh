#!/bin/sh
# ionotes setup: asks where the MariaDB/MySQL database is (and tests it), the port, an admin account, whether
# pictures added in the web app should have their text read (RapidOCR), and whether to start ionotes at login;
# then creates the Python environment, installs the packages, writes ionotes.env, creates the tables and the
# admin, and starts the service (launchd on macOS, systemd on Linux). Run it again at any time; it keeps what
# is there. The same installer as iopix's, for ionotes.
#
#   ./setup.sh                       ask everything
#   ./setup.sh --yes --mysql 192.168.1.89:3306/notes:notes:secret --admin alex:secret
#   --mysql HOST:PORT/DB:USER:PASSWORD   the database (IONOTES_MYSQL in the environment does the same, off the command line)
#   --sqlite                         a SQLite file in the data folder instead (a quick try)
#   --port 8610   --data DIR   --admin NAME:PASS (or IONOTES_ADMIN)   --no-admin
#   --features ocr|none   --service | --no-service   --python PATH   --no-system-deps
set -e
cd "$(dirname "$0")"
APP="$(pwd)"
OS="$(uname -s)"
say() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
YES=0; MYSQL=""; SQLITE=0; FEATURES=""; PORT=""; ADMIN=""; NO_ADMIN=0; SERVICE=""; DATA=""; PY=""; SYSDEPS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --yes) YES=1; shift;; --mysql) MYSQL="$2"; shift 2;; --sqlite) SQLITE=1; shift;;
    --features) FEATURES="$2"; shift 2;; --port) PORT="$2"; shift 2;;
    --admin) ADMIN="$2"; shift 2;; --no-admin) NO_ADMIN=1; shift;; --service) SERVICE=1; shift;; --no-service) SERVICE=0; shift;;
    --data) DATA="$2"; shift 2;; --python) PY="$2"; shift 2;; --system-deps) SYSDEPS=1; shift;; --no-system-deps) SYSDEPS=0; shift;;
    -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) die "unknown option $1 (try --help)";;
  esac
done
[ -n "$ADMIN" ] || ADMIN="${IONOTES_ADMIN:-}"
[ -n "$MYSQL" ] || MYSQL="${IONOTES_MYSQL:-}"
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

say "ionotes setup"
echo "This asks a few questions, installs the Python packages, writes the settings, creates the tables in your"
echo "database and starts ionotes as a service."

pyok() { [ -n "$1" ] && "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; }
findpy() { for c in python3.13 python3.12 python3.11 python3.10 python3; do p="$(command -v $c 2>/dev/null || true)"; pyok "$p" && { echo "$p"; return 0; }; done; return 0; }
[ -n "$PY" ] || PY="$(findpy)"
if ! pyok "$PY"; then
  say "System packages"
  echo "Missing: python3 (3.10 or newer)"
  if [ -z "$SYSDEPS" ]; then yesno "Install it now?" y && SYSDEPS=1 || SYSDEPS=0; fi
  if [ "$SYSDEPS" = 1 ]; then
    SUDO=""; [ "$(id -u)" = 0 ] || SUDO="sudo"
    case "$OS" in
      Darwin) command -v brew >/dev/null 2>&1 || die "install Homebrew (https://brew.sh) or Python 3.10+ yourself, then run setup again"
              brew install python@3.12; PY=/opt/homebrew/opt/python@3.12/bin/python3.12; pyok "$PY" || PY="$(findpy)";;
      *) if command -v apt-get >/dev/null 2>&1; then $SUDO env DEBIAN_FRONTEND=noninteractive sh -c 'apt-get update -qq && apt-get install -y -qq --no-install-recommends python3 python3-venv python3-pip libheif1 libglib2.0-0 >/dev/null'
         elif command -v dnf >/dev/null 2>&1; then $SUDO dnf install -y -q python3 python3-pip libheif glib2 >/dev/null
         elif command -v zypper >/dev/null 2>&1; then $SUDO zypper -n -q install python3 python3-pip libheif1 >/dev/null
         elif command -v pacman >/dev/null 2>&1; then $SUDO pacman -Sy --noconfirm --needed python python-pip libheif >/dev/null
         else die "no known package manager; install python3 (3.10+) yourself, then run setup again"; fi
         PY="$(findpy)";;
    esac
  fi
fi
pyok "$PY" || die "python3 (3.10 or newer) is needed (found ${PY:-none})"
"$PY" -c 'import venv' 2>/dev/null || die "the python3 venv module is missing (Debian/Ubuntu: apt install python3-venv)"

say "Database"
ask DATA "Folder for ionotes' own files (session secret, log)" "${DATA:-$APP/data}"
if [ -z "$MYSQL" ] && [ "$SQLITE" = 0 ]; then
  if [ -f "$APP/ionotes.env" ] && grep -q '^DB_TYPE=mysql' "$APP/ionotes.env" && ! yesno "ionotes.env already names a database; change it?" n; then
    MYSQL="keep"
  elif yesno "Keep the notes in MariaDB/MySQL (no: a SQLite file in the data folder, for a quick try)?" y; then
    ask MH "MariaDB host" "192.168.1.89"; ask MP "port" "3306"; ask MD "database (created if the user may)" "notes"; ask MU "user" "notes"; secret MW "password"
    MYSQL="$MH:$MP/$MD:$MU:$MW"
  else
    SQLITE=1
  fi
fi
ask PORT "Port" "${PORT:-8610}"
if [ -z "$FEATURES" ]; then
  yesno "Read the text in pictures added in the web app (RapidOCR, ~60 MB; the Mac and iPhone apps read it themselves)?" y && FEATURES=ocr || FEATURES=none
fi
if [ -z "$ADMIN" ] && [ "$NO_ADMIN" = 0 ]; then
  if yesno "Create an admin account now (until one exists, anyone who can reach ionotes can read and change the notes)?" y; then
    ask AN "Admin user name" "admin"; secret AW "Admin password (8 characters or more)"
    [ -n "$AW" ] && ADMIN="$AN:$AW" || echo "no password given; skipping the admin account (the web app can create it later)"
  fi
fi
if [ -z "$SERVICE" ]; then
  case "$OS" in Darwin) SVC="a launchd login item";; *) SVC="a systemd service";; esac
  yesno "Start ionotes at login as $SVC?" y && SERVICE=1 || SERVICE=0
fi

say "Python environment"
VENV="$APP/.venv"
[ -x "$VENV/bin/python" ] || "$PY" -m venv "$VENV"
VPY="$VENV/bin/python"
pipi() { if command -v uv >/dev/null 2>&1; then uv pip install -q -p "$VPY" "$@"; else "$VPY" -m pip install -q "$@"; fi; }
"$VPY" -m pip --version >/dev/null 2>&1 || command -v uv >/dev/null 2>&1 || "$VPY" -m ensurepip -q
if [ "$FEATURES" = ocr ]; then echo "installing the packages (with RapidOCR)"; pipi -e ".[ocr]"; else echo "installing the packages"; pipi -e .; fi

say "Settings"
ENVF="$APP/ionotes.env"
umask 077  # the settings file holds the database password: private from the first byte
OLD=""; [ -f "$ENVF" ] && OLD="$(grep -E '^(DB_|AUTH_PROXY|CF_ACCESS|APP_URL|MCP)' "$ENVF" || true)"
{
  echo "# ionotes settings, written by setup.sh (variable names as in the README). Edit and restart the service."
  echo "DATA_DIR=$DATA"
  echo "PORT=$PORT"
  echo "OCR=$([ "$FEATURES" = ocr ] && echo 1 || echo 0)"
  if [ "$MYSQL" = keep ]; then
    echo "$OLD"
  else
    echo "$OLD" | grep -vE '^DB_' | grep -v '^$' || true
    if [ -n "$MYSQL" ]; then
      hp=${MYSQL%%/*}; rest=${MYSQL#*/}; db=${rest%%:*}; rest=${rest#*:}; us=${rest%%:*}; pw=${rest#*:}
      echo "DB_TYPE=mysql"; echo "DB_HOST=${hp%%:*}"; echo "DB_PORT=${hp##*:}"; echo "DB_DATABASE=$db"; echo "DB_USER=$us"; echo "DB_PASSWORD=$pw"
    else
      echo "DB_TYPE=sqlite"
    fi
  fi
} > "$ENVF"
chmod 600 "$ENVF"
mkdir -p "$DATA"
while IFS= read -r line; do k="${line%%=*}"; case "$line" in ''|'#'*) ;; *=*) case "$k" in ''|*[!A-Za-z0-9_]*) ;; *) export "$line";; esac;; esac; done < "$ENVF"
echo "wrote $ENVF"

if [ "${DB_TYPE:-}" = mysql ]; then
  echo "testing the database, creating it if needed"
  "$VPY" - <<'PYEOF' || die "could not use that MariaDB/MySQL database (see above); run setup.sh again"
import os
from app import db
c = db.settings()
r = db.test({})
if not r["ok"] and ("1049" in r["error"] or "Unknown database" in r["error"]):
    import pymysql  # the database is not there yet: create it, if this user may
    con = pymysql.connect(host=c["host"], port=c["port"], user=c["user"], password=c["password"], connect_timeout=8)
    try:
        con.cursor().execute(f"CREATE DATABASE IF NOT EXISTS `{c['database']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        print(f"  created the database {c['database']}")
    except Exception as e:
        raise SystemExit(f"  the database {c['database']} does not exist and {c['user']} may not create it ({e}); create it, then run setup.sh again")
    finally:
        con.close()
    r = db.test({})
if not r["ok"]:
    raise SystemExit("  " + r["error"])
db.init()
print(f"  OK: {r['version']} at {c['host']}:{c['port']}/{c['database']}; tables are in place")
if r.get("warning"):
    print("  note: " + r["warning"])
PYEOF
fi

if [ -n "$ADMIN" ]; then
  say "Admin account"
  IONOTES_ADMIN_ACCOUNT="$ADMIN" "$VPY" -c "
import os; from app import db, users
db.init()
name, pw = os.environ['IONOTES_ADMIN_ACCOUNT'].split(':', 1)  # from the environment: the password is not in the process list
print('  created', users.create(name, pw, 'admin')['name']) if not users.any_users() else print('  accounts already exist; not touched')
"
fi

say "Service"
if [ "$SERVICE" = 1 ] && [ "$OS" = Darwin ]; then
  PL="$HOME/Library/LaunchAgents/net.iothing.ionotes.server.plist"
  "$VPY" - "$PL" "$APP" "$VPY" "$PORT" "$ENVF" <<'PYEOF'
import plistlib, sys, os
pl, app, vpy, port, envf = sys.argv[1:6]
env = {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"}
for line in open(envf):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); env[k] = v
d = {"Label": "net.iothing.ionotes.server", "ProgramArguments": [vpy, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(port), "--proxy-headers"],
     "WorkingDirectory": app, "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 10, "EnvironmentVariables": env,
     "StandardOutPath": os.path.join(env["DATA_DIR"], "server.log"), "StandardErrorPath": os.path.join(env["DATA_DIR"], "server.log")}
os.makedirs(os.path.dirname(pl), exist_ok=True)
with open(pl, "wb") as f: plistlib.dump(d, f)
os.chmod(pl, 0o600)  # it carries the settings, database password included
print("  wrote", pl)
PYEOF
  launchctl bootout "gui/$(id -u)/net.iothing.ionotes.server" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PL" || die "launchctl could not start the login item (see above)"
  echo "  started (login item)"
elif [ "$SERVICE" = 1 ] && command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  UNIT=/etc/systemd/system/ionotes.service
  if [ "$(id -u)" = 0 ]; then SUDO=""; else SUDO="sudo"; fi
  $SUDO sh -c "cat > $UNIT" <<UEOF
[Unit]
Description=ionotes
After=network.target

[Service]
Type=simple
User=$(id -un)
EnvironmentFile=$ENVF
WorkingDirectory=$APP
ExecStart="$VPY" -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UEOF
  $SUDO systemctl daemon-reload || die "systemctl daemon-reload failed"
  $SUDO systemctl enable --now ionotes || die "the ionotes service could not be started (see above; journalctl -u ionotes)"
  echo "  started (systemd)"
else
  echo "  not installed as a service. Start ionotes with:"
  echo "    cd \"$APP\" && ./run.sh --host 0.0.0.0 --port $PORT"
fi
say "Done: http://localhost:$PORT   settings: $ENVF"
