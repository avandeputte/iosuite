#!/bin/sh
# ioContacts setup: asks a few questions (or takes flags), then installs the Python packages, writes the settings,
# creates the tables and the admin account and, on Linux with systemd, installs and starts the service.
#
#   ./setup.sh                 ask the questions
#   ./setup.sh --yes ...       no questions: defaults and the flags below
#
# Flags: --db HOST:PORT/DATABASE:USER:PASSWORD   (MariaDB / MySQL; default 127.0.0.1:3306/contacts:contacts:contacts)
#        --suite-db HOST:PORT/DATABASE:USER:PASSWORD   (the Shared ioSuite database: the suite's accounts and
#                                     settings; default: the same server, iosuite:iosuite:iosuite)
#        --admin NAME:PASSWORD | --no-admin   --port N (8610)   --ldap-port N (3890; 0 turns LDAP off)
#        --public-url URL   --service | --no-service   --system-deps | --no-system-deps   --python PATH
# Secrets can stay off the command line: IOCONTACTS_DB, IOCONTACTS_SUITE_DB and IOCONTACTS_ADMIN in the environment
# do what --db, --suite-db and --admin do. Run it again at any time: it keeps iocontacts.env and only changes what you answer.
set -e
cd "$(dirname "$0")"
APP="$(pwd)"
say() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
YES=0; DBS=""; SDBS=""; ADMIN=""; NO_ADMIN=0; PORT=""; LDAP=""; PUBURL=""; SERVICE=""; SYSDEPS=""; PY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --yes) YES=1; shift;; --db) DBS="$2"; shift 2;; --suite-db) SDBS="$2"; shift 2;; --admin) ADMIN="$2"; shift 2;; --no-admin) NO_ADMIN=1; shift;;
    --port) PORT="$2"; shift 2;; --ldap-port) LDAP="$2"; shift 2;; --public-url) PUBURL="$2"; shift 2;;
    --service) SERVICE=1; shift;; --no-service) SERVICE=0; shift;; --system-deps) SYSDEPS=1; shift;; --no-system-deps) SYSDEPS=0; shift;;
    --python) PY="$2"; shift 2;;
    -h|--help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) die "unknown option $1 (try --help)";;
  esac
done
[ -n "$DBS" ] || DBS="${IOCONTACTS_DB:-}"
[ -n "$SDBS" ] || SDBS="${IOCONTACTS_SUITE_DB:-}"
[ -n "$ADMIN" ] || ADMIN="${IOCONTACTS_ADMIN:-}"
ask() { _v="$1"; _q="$2"; _d="$3"
  if [ "$YES" = 1 ] || [ ! -t 0 ]; then eval "$_v=\"\$_d\""; return; fi
  printf '%s [%s]: ' "$_q" "$_d"; read -r _a || _a=""; [ -n "$_a" ] && eval "$_v=\"\$_a\"" || eval "$_v=\"\$_d\""; }
asksecret() { _v="$1"; _q="$2"
  if [ "$YES" = 1 ] || [ ! -t 0 ]; then eval "$_v=''"; return; fi
  printf '%s: ' "$_q"; stty -echo 2>/dev/null; read -r _a || _a=""; stty echo 2>/dev/null; printf '\n'; eval "$_v=\"\$_a\""; }
getenv() { [ -f iocontacts.env ] && sed -n "s/^$1=//p" iocontacts.env | tail -n 1; true; }

# ---- system packages (Python 3.10+ and venv)
if [ "$SYSDEPS" != 0 ] && ! python3 -c 'import sys, venv, ensurepip; assert sys.version_info >= (3, 10)' 2>/dev/null; then
  say "Installing Python"
  if command -v apt-get >/dev/null; then apt-get update -qq && apt-get install -y -qq python3 python3-venv python3-pip >/dev/null
  elif command -v dnf >/dev/null; then dnf install -y -q python3 python3-pip
  elif command -v brew >/dev/null; then brew install python
  else die "install Python 3.10 or newer with venv, then run this again"; fi
fi
PY="${PY:-python3}"

# ---- the answers
if [ -z "$DBS" ]; then
  H="$(getenv DB_HOST)"; P="$(getenv DB_PORT)"; D="$(getenv DB_NAME)"; U="$(getenv DB_USER)"
  ask H "MariaDB host" "${H:-127.0.0.1}"; ask P "Port" "${P:-3306}"; ask D "Database" "${D:-contacts}"; ask U "User" "${U:-contacts}"
  asksecret W "Password (empty: keep the current one, or 'contacts')"; [ -n "$W" ] || W="$(getenv DB_PASSWORD)"; [ -n "$W" ] || W=contacts
  DBS="$H:$P/$D:$U:$W"
fi
DB_HOST="${DBS%%:*}"; r="${DBS#*:}"; DB_PORT="${r%%/*}"; r="${r#*/}"; DB_NAME="${r%%:*}"; r="${r#*:}"; DB_USER="${r%%:*}"; DB_PASSWORD="${r#*:}"
# the Shared ioSuite database (accounts, sessions and settings shared by the ioThing apps); an install from before
# 0.4.7 kept it as IOTHING_AUTH_DB_* (database and user `auth`): its values are the defaults, then written as IOSUITE_DB_*
suiteenv() { v="$(getenv "IOSUITE_DB_$1")"; [ -n "$v" ] || v="$(getenv "IOTHING_AUTH_DB_$1")"; printf '%s' "$v"; }
if [ -z "$SDBS" ]; then
  if [ -n "$(getenv IOTHING_AUTH_DB_HOST)$(getenv IOTHING_AUTH_DB_NAME)$(getenv IOTHING_AUTH_DB_USER)" ] && [ -z "$(getenv IOSUITE_DB_NAME)" ]; then
    SD0=auth; SU0=auth; else SD0=iosuite; SU0=iosuite; fi
  H="$(suiteenv HOST)"; P="$(suiteenv PORT)"; D="$(suiteenv NAME)"; U="$(suiteenv USER)"
  ask H "Shared ioSuite database: host" "${H:-$DB_HOST}"; ask P "Port" "${P:-$DB_PORT}"; ask D "Database" "${D:-$SD0}"; ask U "User" "${U:-$SU0}"
  asksecret W "Password (empty: keep the current one, or '$SU0')"; [ -n "$W" ] || W="$(suiteenv PASSWORD)"; [ -n "$W" ] || W="$SU0"
  SDBS="$H:$P/$D:$U:$W"
fi
SUITE_HOST="${SDBS%%:*}"; r="${SDBS#*:}"; SUITE_PORT="${r%%/*}"; r="${r#*/}"; SUITE_NAME="${r%%:*}"; r="${r#*:}"; SUITE_USER="${r%%:*}"; SUITE_PASSWORD="${r#*:}"
[ -n "$PORT" ] || { P="$(getenv PORT)"; ask PORT "Web port" "${P:-8610}"; }
[ -n "$LDAP" ] || { L="$(getenv LDAP_PORT)"; ask LDAP "LDAP directory port (0: off)" "${L:-3890}"; }
[ -n "$PUBURL" ] || { U2="$(getenv PUBLIC_URL)"; ask PUBURL "Public address, e.g. https://contacts.example.com (empty: as reached)" "$U2"; }
if [ -z "$ADMIN" ] && [ "$NO_ADMIN" = 0 ] && [ "$YES" = 0 ] && [ -t 0 ]; then
  ask AN "Admin user name (empty: make it in the browser on the first visit)" "admin"
  if [ -n "$AN" ]; then asksecret AW "Admin password (8 or more)"; [ -n "$AW" ] && ADMIN="$AN:$AW"; fi
fi

# ---- Python environment
say "Installing the Python packages"
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -e .

# ---- settings (kept between runs; passwords readable by the owner only)
say "Writing iocontacts.env"
touch iocontacts.env; chmod 600 iocontacts.env
setenv() { grep -v "^$1=" iocontacts.env > iocontacts.env.tmp || true; printf '%s=%s\n' "$1" "$2" >> iocontacts.env.tmp; mv iocontacts.env.tmp iocontacts.env; chmod 600 iocontacts.env; }
setenv DB_HOST "$DB_HOST"; setenv DB_PORT "$DB_PORT"; setenv DB_NAME "$DB_NAME"; setenv DB_USER "$DB_USER"; setenv DB_PASSWORD "$DB_PASSWORD"
setenv IOSUITE_DB_HOST "$SUITE_HOST"; setenv IOSUITE_DB_PORT "$SUITE_PORT"; setenv IOSUITE_DB_NAME "$SUITE_NAME"
setenv IOSUITE_DB_USER "$SUITE_USER"; setenv IOSUITE_DB_PASSWORD "$SUITE_PASSWORD"
grep -v '^IOTHING_AUTH_DB_' iocontacts.env > iocontacts.env.tmp || true; mv iocontacts.env.tmp iocontacts.env; chmod 600 iocontacts.env
setenv PORT "$PORT"; setenv LDAP_PORT "$LDAP"
[ -n "$PUBURL" ] && setenv PUBLIC_URL "$PUBURL"

say "Checking the database at $DB_HOST:$DB_PORT/$DB_NAME"
.venv/bin/python -m app.cli check || die "could not reach the database: check the host, port, user and password (and that the user may connect from this machine)"
if [ -n "$ADMIN" ]; then
  IOCONTACTS_PASSWORD="${ADMIN#*:}" .venv/bin/python -m app.cli create-user "${ADMIN%%:*}" admin
fi

# ---- the service
if [ -z "$SERVICE" ]; then
  if command -v systemctl >/dev/null && [ "$(id -u)" = 0 ]; then SERVICE=1; else SERVICE=0; fi
fi
if [ "$SERVICE" = 1 ]; then
  say "Installing the iocontacts service"
  OWNER="$(stat -c %U "$APP" 2>/dev/null || echo root)"
  cat > /etc/systemd/system/iocontacts.service <<UNIT
[Unit]
Description=ioContacts
After=network-online.target mariadb.service
Wants=network-online.target

[Service]
Type=simple
User=$OWNER
EnvironmentFile=$APP/iocontacts.env
WorkingDirectory=$APP
ExecStart=$APP/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips=*
AmbientCapabilities=CAP_NET_BIND_SERVICE
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable -q iocontacts
  systemctl restart iocontacts
  sleep 2
  systemctl is-active -q iocontacts || die "the service did not start: journalctl -u iocontacts -n 50"
  say "ioContacts runs on port $PORT (LDAP: ${LDAP})"
else
  say "Done. Start it with ./run.sh (port $PORT)"
fi
