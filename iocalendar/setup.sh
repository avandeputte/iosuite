#!/bin/sh
# ioCalendar setup: asks a few questions (or takes flags), then installs the Python packages, writes the settings,
# creates the tables and the admin account and, on Linux with systemd, installs and starts the service.
#
#   ./setup.sh                 ask the questions
#   ./setup.sh --yes ...       no questions: defaults and the flags below
#
# Flags: --db HOST:PORT/DATABASE:USER:PASSWORD        (MariaDB / MySQL; default 192.168.1.89:3306/calendar:calendar:calendar)
#        --iosuite-db HOST:PORT/DATABASE:USER:PASSWORD (the Shared ioSuite database: accounts and suite-wide settings;
#                                                       default: the same server, iosuite:iosuite; --auth-db still works)
#        --admin NAME:PASSWORD | --no-admin   --port N (8620)   --timezone ZONE   --public-url URL
#        --service | --no-service   --system-deps | --no-system-deps   --python PATH
# Secrets can stay off the command line: IOCALENDAR_DB, IOCALENDAR_IOSUITE_DB (or the older IOCALENDAR_AUTH_DB) and
# IOCALENDAR_ADMIN in the environment do what --db, --iosuite-db and --admin do. Run it again at any time: it keeps iocalendar.env and only changes what you answer.
set -e
cd "$(dirname "$0")"
APP="$(pwd)"
say() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
YES=0; DBS=""; ADBS=""; ADMIN=""; NO_ADMIN=0; PORT=""; TZONE=""; PUBURL=""; SERVICE=""; SYSDEPS=""; PY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --yes) YES=1; shift;; --db) DBS="$2"; shift 2;; --iosuite-db|--auth-db) ADBS="$2"; shift 2;; --admin) ADMIN="$2"; shift 2;; --no-admin) NO_ADMIN=1; shift;;
    --port) PORT="$2"; shift 2;; --timezone) TZONE="$2"; shift 2;; --public-url) PUBURL="$2"; shift 2;;
    --service) SERVICE=1; shift;; --no-service) SERVICE=0; shift;; --system-deps) SYSDEPS=1; shift;; --no-system-deps) SYSDEPS=0; shift;;
    --python) PY="$2"; shift 2;;
    -h|--help) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) die "unknown option $1 (try --help)";;
  esac
done
[ -n "$DBS" ] || DBS="${IOCALENDAR_DB:-}"
[ -n "$ADBS" ] || ADBS="${IOCALENDAR_IOSUITE_DB:-${IOCALENDAR_AUTH_DB:-}}"
[ -n "$ADMIN" ] || ADMIN="${IOCALENDAR_ADMIN:-}"
ask() { _v="$1"; _q="$2"; _d="$3"
  if [ "$YES" = 1 ] || [ ! -t 0 ]; then eval "$_v=\"\$_d\""; return; fi
  printf '%s [%s]: ' "$_q" "$_d"; read -r _a || _a=""; [ -n "$_a" ] && eval "$_v=\"\$_a\"" || eval "$_v=\"\$_d\""; }
asksecret() { _v="$1"; _q="$2"
  if [ "$YES" = 1 ] || [ ! -t 0 ]; then eval "$_v=''"; return; fi
  printf '%s: ' "$_q"; stty -echo 2>/dev/null; read -r _a || _a=""; stty echo 2>/dev/null; printf '\n'; eval "$_v=\"\$_a\""; }
getenv() { [ -f iocalendar.env ] && sed -n "s/^$1=//p" iocalendar.env | tail -n 1; true; }
getsuite() { for _p in IOSUITE_DB_ IOSUITE_SHARED_DB_ IOTHING_AUTH_DB_; do _g="$(getenv "$_p$1")"; [ -n "$_g" ] && break; done; printf '%s' "$_g"; }  # new name, else an older one
split() { # HOST:PORT/DATABASE:USER:PASSWORD into $1_HOST, $1_PORT, $1_NAME, $1_USER, $1_PASSWORD
  _p="$1"; _s="$2"; _h="${_s%%:*}"; _r="${_s#*:}"; _o="${_r%%/*}"; _r="${_r#*/}"; _n="${_r%%:*}"; _r="${_r#*:}"; _u="${_r%%:*}"; _w="${_r#*:}"
  eval "${_p}_HOST=\"\$_h\"; ${_p}_PORT=\"\$_o\"; ${_p}_NAME=\"\$_n\"; ${_p}_USER=\"\$_u\"; ${_p}_PASSWORD=\"\$_w\""; }

# ---- system packages (Python 3.10+ and venv)
if [ "$SYSDEPS" != 0 ] && ! python3 -c 'import sys, venv, ensurepip; assert sys.version_info >= (3, 10)' 2>/dev/null; then
  say "Installing Python"
  if command -v apt-get >/dev/null; then apt-get update -qq && apt-get install -y -qq python3 python3-venv python3-pip git >/dev/null
  elif command -v dnf >/dev/null; then dnf install -y -q python3 python3-pip git
  elif command -v brew >/dev/null; then brew install python
  else die "install Python 3.10 or newer with venv, then run this again"; fi
fi
command -v git >/dev/null || die "git is needed to install the suite's shared library (iothing-auth, from the iosuite-shared repository): install git, then run this again"
PY="${PY:-python3}"

# ---- the answers
if [ -z "$DBS" ]; then
  say "The calendar database (MariaDB / MySQL)"
  H="$(getenv DB_HOST)"; P="$(getenv DB_PORT)"; D="$(getenv DB_NAME)"; U="$(getenv DB_USER)"
  ask H "Host" "${H:-192.168.1.89}"; ask P "Port" "${P:-3306}"; ask D "Database" "${D:-calendar}"; ask U "User" "${U:-calendar}"
  asksecret W "Password (empty: keep the current one, or 'calendar')"; [ -n "$W" ] || W="$(getenv DB_PASSWORD)"; [ -n "$W" ] || W=calendar
  DBS="$H:$P/$D:$U:$W"
fi
split DB "$DBS"
if [ -z "$ADBS" ]; then
  say "The Shared ioSuite database: accounts and suite-wide settings, shared by the io apps (ioPix, ioNotes, ioContacts, ioCalendar)"
  H="$(getsuite HOST)"; P="$(getsuite PORT)"; D="$(getsuite NAME)"; U="$(getsuite USER)"
  ask H "Host" "${H:-$DB_HOST}"; ask P "Port" "${P:-$DB_PORT}"; ask D "Database" "${D:-iosuite}"; ask U "User" "${U:-iosuite}"
  asksecret W "Password (empty: keep the current one, or 'iosuite')"; [ -n "$W" ] || W="$(getsuite PASSWORD)"; [ -n "$W" ] || W=iosuite
  ADBS="$H:$P/$D:$U:$W"
fi
split SUITE "$ADBS"
[ -n "$PORT" ] || { P="$(getenv PORT)"; ask PORT "Web port" "${P:-8620}"; }
if [ -z "$TZONE" ]; then
  T="$(getenv TIMEZONE)"; [ -n "$T" ] || T="$(cat /etc/timezone 2>/dev/null || timedatectl show -p Timezone --value 2>/dev/null || true)"
  ask TZONE "Time zone of the family (for times without one)" "${T:-America/New_York}"
fi
[ -n "$PUBURL" ] || { U2="$(getenv PUBLIC_URL)"; ask PUBURL "Public address, e.g. https://calendar.example.com (empty: as reached)" "$U2"; }
if [ -z "$ADMIN" ] && [ "$NO_ADMIN" = 0 ] && [ "$YES" = 0 ] && [ -t 0 ]; then
  ask AN "Admin user name (empty: an account from another io app, or make it in the browser on the first visit)" "admin"
  if [ -n "$AN" ]; then asksecret AW "Admin password (8 or more; empty for an existing account)"; [ -n "$AW" ] && ADMIN="$AN:$AW"; fi
fi

# ---- Python environment
say "Installing the Python packages"
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -e .

# ---- settings (kept between runs; passwords readable by the owner only)
say "Writing iocalendar.env"
touch iocalendar.env; chmod 600 iocalendar.env
setenv() { grep -v "^$1=" iocalendar.env > iocalendar.env.tmp || true; printf '%s=%s\n' "$1" "$2" >> iocalendar.env.tmp; mv iocalendar.env.tmp iocalendar.env; chmod 600 iocalendar.env; }
setenv DB_HOST "$DB_HOST"; setenv DB_PORT "$DB_PORT"; setenv DB_NAME "$DB_NAME"; setenv DB_USER "$DB_USER"; setenv DB_PASSWORD "$DB_PASSWORD"
# the Shared ioSuite database (iothing-auth 0.4.1+ reads IOSUITE_DB_*; older IOSUITE_SHARED_DB_* / IOTHING_AUTH_DB_* lines are moved over)
for _k in HOST PORT NAME USER PASSWORD; do grep -v -e "^IOTHING_AUTH_DB_$_k=" -e "^IOSUITE_SHARED_DB_$_k=" iocalendar.env > iocalendar.env.tmp || true; mv iocalendar.env.tmp iocalendar.env; done; chmod 600 iocalendar.env
setenv IOSUITE_DB_HOST "$SUITE_HOST"; setenv IOSUITE_DB_PORT "$SUITE_PORT"; setenv IOSUITE_DB_NAME "$SUITE_NAME"
setenv IOSUITE_DB_USER "$SUITE_USER"; setenv IOSUITE_DB_PASSWORD "$SUITE_PASSWORD"
setenv PORT "$PORT"; setenv TIMEZONE "$TZONE"
[ -n "$PUBURL" ] && setenv PUBLIC_URL "$PUBURL"

say "Checking the databases ($DB_HOST:$DB_PORT/$DB_NAME and $SUITE_HOST:$SUITE_PORT/$SUITE_NAME)"
.venv/bin/python -m app.cli check || die "could not reach a database: check the host, port, user and password (and that the user may connect from this machine)"
if [ -n "$ADMIN" ]; then
  IOCALENDAR_PASSWORD="${ADMIN#*:}" .venv/bin/python -m app.cli create-user "${ADMIN%%:*}" admin
fi

# ---- the service
if [ -z "$SERVICE" ]; then
  if command -v systemctl >/dev/null && [ "$(id -u)" = 0 ]; then SERVICE=1; else SERVICE=0; fi
fi
if [ "$SERVICE" = 1 ]; then
  say "Installing the iocalendar service"
  OWNER="$(stat -c %U "$APP" 2>/dev/null || echo root)"
  cat > /etc/systemd/system/iocalendar.service <<UNIT
[Unit]
Description=ioCalendar
After=network-online.target mariadb.service
Wants=network-online.target

[Service]
Type=simple
User=$OWNER
EnvironmentFile=$APP/iocalendar.env
WorkingDirectory=$APP
ExecStart=$APP/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips=*
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable -q iocalendar
  systemctl restart iocalendar
  sleep 2
  systemctl is-active -q iocalendar || die "the service did not start: journalctl -u iocalendar -n 50"
  say "ioCalendar runs on port $PORT"
else
  say "Done. Start it with ./run.sh (port $PORT)"
fi
