#!/bin/sh
# ionotes setup: asks where the MariaDB/MySQL database is (and tests it), where the Shared ioSuite database is
# (the accounts and suite-wide settings shared by the ioThing apps), the port, an admin account, whether
# pictures added in the web app should have their text read (RapidOCR), and whether to start ionotes at login;
# then creates the Python environment, installs the packages, writes config.env, creates the tables and the
# admin, and starts the service (launchd on macOS, systemd on Linux). Run it again at any time; it keeps what
# is there.
#
#   ./setup.sh                       ask everything
#   ./setup.sh --yes --db db.example.lan:3306/notes:notes:secret --admin alex:secret
# Flags (the same in every app of the suite):
#   --db HOST:PORT/DB:USER:PASSWORD        the database (IONOTES_DB in the environment does the same, off the command line)
#   --suite-db HOST:PORT/DB:USER:PASSWORD  the Shared ioSuite database (IONOTES_SUITE_DB does the same; default
#                                          database and user: iosuite); kept as it is in config.env when not given
#   --admin NAME:PASS (or IONOTES_ADMIN) | --no-admin   --port 8610   --public-url URL   --cookie-domain DOMAIN
#   --service | --no-service   --python PATH   --system-deps | --no-system-deps   --yes
# ioNotes' own: --sqlite (a SQLite file in the data folder instead, a quick try)   --data DIR   --features ocr|none
set -e
cd "$(dirname "$0")"
APP="$(pwd)"
OS="$(uname -s)"
say() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
YES=0; MYSQL=""; SUITE=""; SQLITE=0; FEATURES=""; PORT=""; PUBURL=""; COOKIE=""; ADMIN=""; NO_ADMIN=0; SERVICE=""; DATA=""; PY=""; SYSDEPS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --yes) YES=1; shift;; --db) MYSQL="$2"; shift 2;; --suite-db) SUITE="$2"; shift 2;; --sqlite) SQLITE=1; shift;;
    --features) FEATURES="$2"; shift 2;; --port) PORT="$2"; shift 2;; --public-url) PUBURL="$2"; shift 2;; --cookie-domain) COOKIE="$2"; shift 2;;
    --admin) ADMIN="$2"; shift 2;; --no-admin) NO_ADMIN=1; shift;; --service) SERVICE=1; shift;; --no-service) SERVICE=0; shift;;
    --data) DATA="$2"; shift 2;; --python) PY="$2"; shift 2;; --system-deps) SYSDEPS=1; shift;; --no-system-deps) SYSDEPS=0; shift;;
    -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) die "unknown option $1 (try --help)";;
  esac
done
[ -n "$ADMIN" ] || ADMIN="${IONOTES_ADMIN:-}"
[ -n "$MYSQL" ] || MYSQL="${IONOTES_DB:-}"
[ -n "$SUITE" ] || SUITE="${IONOTES_SUITE_DB:-}"
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
  if [ -f "$APP/config.env" ] && grep -q '^DB_TYPE=mysql' "$APP/config.env" && ! yesno "config.env already names a database; change it?" n; then
    MYSQL="keep"
  elif yesno "Keep the notes in MariaDB/MySQL (no: a SQLite file in the data folder, for a quick try)?" y; then
    ask MH "MariaDB host" "127.0.0.1"; ask MP "port" "3306"; ask MD "database (created if the user may)" "notes"; ask MU "user" "notes"; secret MW "password"
    MYSQL="$MH:$MP/$MD:$MU:$MW"
  else
    SQLITE=1
  fi
fi
say "Shared ioSuite database"
echo "Accounts, sessions and the suite-wide settings live in the Shared ioSuite database (MariaDB), shared with"
echo "every app of the suite, so one sign-in serves them all."
SUITE_SET=0; [ -f "$APP/config.env" ] && grep -qE '^IOSUITE_DB_' "$APP/config.env" && SUITE_SET=1
if [ -z "$SUITE" ]; then
  if [ "$SUITE_SET" = 1 ] && ! yesno "config.env already names the Shared ioSuite database; change it?" n; then
    SUITE="keep"
  elif [ "$YES" = 1 ] || [ -z "$TTY" ]; then
    SUITE="keep"; [ "$SUITE_SET" = 1 ] || echo "not named: ionotes uses the defaults (the notes' server, database and user iosuite); set IOSUITE_DB_* in config.env"
  else
    case "$MYSQL" in ''|keep) SH="$(grep -E '^DB_HOST=' "$APP/config.env" 2>/dev/null | head -1 | cut -d= -f2-)"; SH="${SH:-127.0.0.1}";; *) SH="${MYSQL%%:*}"; SH="${SH%%/*}";; esac
    ask SH "Shared ioSuite database host" "$SH"; ask SP "port" "3306"; ask SD "database (created if the user may)" "iosuite"; ask SU "user" "iosuite"; secret SW "password"
    SUITE="$SH:$SP/$SD:$SU:$SW"
  fi
fi
getenv() { [ -f "$APP/config.env" ] && sed -n "s/^$1=//p" "$APP/config.env" | tail -n 1; true; }
ask PORT "Port" "${PORT:-$(getenv PORT | grep . || echo 8610)}"
[ -n "$PUBURL" ] || ask PUBURL "Public address, e.g. https://notes.example.com (empty: as reached)" "$(getenv PUBLIC_URL)"
[ -n "$COOKIE" ] || ask COOKIE "Domain the sign-in is shared on, e.g. example.com (empty: this host only)" "$(getenv COOKIE_DOMAIN)"
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
ENVF="$APP/config.env"
umask 077  # the settings file holds the database password: private from the first byte
OLD=""; [ -f "$ENVF" ] && OLD="$(grep -vE '^(#|DATA_DIR=|PORT=|OCR=|PUBLIC_URL=|COOKIE_DOMAIN=|$)' "$ENVF" || true)"
{
  echo "# ionotes settings, written by setup.sh (config.env.example lists them all). Edit and restart the service."
  echo "DATA_DIR=$DATA"
  echo "PORT=$PORT"
  echo "PUBLIC_URL=$PUBURL"
  echo "COOKIE_DOMAIN=$COOKIE"
  echo "OCR=$([ "$FEATURES" = ocr ] && echo 1 || echo 0)"
  KEEP="$OLD"; [ "$SUITE" != keep ] && [ -n "$SUITE" ] && KEEP="$(echo "$OLD" | grep -vE '^IOSUITE_DB_' || true)"
  if [ "$MYSQL" = keep ]; then
    echo "$KEEP"
  else
    echo "$KEEP" | grep -vE '^DB_' | grep -v '^$' || true
    if [ -n "$MYSQL" ]; then
      hp=${MYSQL%%/*}; rest=${MYSQL#*/}; db=${rest%%:*}; rest=${rest#*:}; us=${rest%%:*}; pw=${rest#*:}
      echo "DB_TYPE=mysql"; echo "DB_HOST=${hp%%:*}"; echo "DB_PORT=${hp##*:}"; echo "DB_NAME=$db"; echo "DB_USER=$us"; echo "DB_PASSWORD=$pw"
    else
      echo "DB_TYPE=sqlite"
    fi
  fi
  if [ "$SUITE" != keep ] && [ -n "$SUITE" ]; then
    # the Shared ioSuite database
    hp=${SUITE%%/*}; rest=${SUITE#*/}; db=${rest%%:*}; rest=${rest#*:}; us=${rest%%:*}; pw=${rest#*:}
    echo "IOSUITE_DB_HOST=${hp%%:*}"; echo "IOSUITE_DB_PORT=${hp##*:}"; echo "IOSUITE_DB_NAME=$db"; echo "IOSUITE_DB_USER=$us"; echo "IOSUITE_DB_PASSWORD=$pw"
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

echo "testing the Shared ioSuite database, creating it if needed"
"$VPY" - <<'PYEOF' || printf '\033[1;33mwarning:\033[0m could not use the Shared ioSuite database (see above); ionotes needs it for sign-in. Run setup.sh again with --suite-db HOST:PORT/DB:USER:PASSWORD\n' >&2
import os
import pymysql
from iosuite_shared import config as sc  # the Shared ioSuite database's settings (IOSUITE_DB_*, or the defaults)
c = dict(host=sc.DB_HOST, port=sc.DB_PORT, user=sc.DB_USER, password=sc.DB_PASSWORD, connect_timeout=8)
name = sc.DB_NAME
try:
    pymysql.connect(database=name, **c).close()
except pymysql.err.OperationalError as x:
    if x.args[0] != 1049:
        raise SystemExit(f"  {c['user']}@{c['host']}:{c['port']}/{name}: {x}")
    con = pymysql.connect(**c)  # the database is not there yet: create it, if this user may
    try:
        con.cursor().execute(f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        print(f"  created the database {name}")
    except Exception as x2:
        raise SystemExit(f"  the database {name} does not exist and {c['user']} may not create it ({x2}); create it, then run setup.sh again")
    finally:
        con.close()
print(f"  OK: {c['user']}@{c['host']}:{c['port']}/{name}")
PYEOF

if [ -n "$ADMIN" ]; then
  say "Admin account"
  ADMIN_PASSWORD="${ADMIN#*:}" "$VENV/bin/iosuite-shared" --config "$APP" admin "${ADMIN%%:*}" --app ionotes
fi

say "Service"
if [ "$SERVICE" = 1 ] && [ "$OS" = Darwin ]; then
  PL="$HOME/Library/LaunchAgents/net.iothing.ionotes.server.plist"
  "$VPY" - "$PL" "$APP" "$VPY" "$DATA" <<'PYEOF'
import plistlib, sys, os
pl, app, vpy, data = sys.argv[1:5]
# the settings stay in config.env, which the app reads itself: the login item only starts `python -m app`
d = {"Label": "net.iothing.ionotes.server", "ProgramArguments": [vpy, "-m", "app"],
     "WorkingDirectory": app, "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 10,
     "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"},
     "StandardOutPath": os.path.join(data, "server.log"), "StandardErrorPath": os.path.join(data, "server.log")}
os.makedirs(os.path.dirname(pl), exist_ok=True)
with open(pl, "wb") as f: plistlib.dump(d, f)
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
ExecStart="$VPY" -m app
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
  echo "    cd \"$APP\" && ./run.sh"
fi
say "Done: http://localhost:$PORT   settings: $ENVF"
