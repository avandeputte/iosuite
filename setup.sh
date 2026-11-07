#!/bin/sh
# ioSuite setup: asks a few questions (or takes flags), then installs the Python packages, writes the settings,
# creates the tables and the admin account and, on Linux with systemd, installs and starts the service.
#
#   ./setup.sh                 ask the questions
#   ./setup.sh --yes ...       no questions: defaults and the flags below
#
# Flags (the same in every app of the suite):
#        --db HOST:PORT/DATABASE:USER:PASSWORD        (MariaDB / MySQL; default 127.0.0.1:3306/suite:suite:suite)
#        --suite-db HOST:PORT/DATABASE:USER:PASSWORD  (the Shared ioSuite database: accounts and suite-wide settings;
#                                                      default: the same server, iosuite:iosuite)
#        --admin NAME:PASSWORD | --no-admin   --port N (8630)   --public-url URL   --cookie-domain DOMAIN
#        --service | --no-service   --system-deps | --no-system-deps   --python PATH
#   --db-admin USER:PASSWORD      a MariaDB / MySQL administrator (root...): the databases and users above are created
#                                 for you, with the passwords you answered (IOSUITE_DB_ADMIN does the same; empty: they exist)
#        --also APP,APP | all | none   also install other apps of the suite here (iopix, ionotes, iocalendar, iocontacts,
#                                      iohealth), beside this one, with the same database server, Shared ioSuite
#                                      database, sign-in domain and admin: those questions are asked once
# Secrets can stay off the command line: IOSUITE_DB, IOSUITE_SUITE_DB and IOSUITE_ADMIN in the environment do what
# --db, --suite-db and --admin do (IOSUITE_ALSO what --also does). Run it again at any time: it keeps config.env and
# only changes what you answer.
set -e
cd "$(dirname "$0")"
APP="$(pwd)"
say() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
YES=0; DBS=""; ADBS=""; ADMIN=""; NO_ADMIN=0; PORT=""; PUBURL=""; COOKIE=""; SERVICE=""; SYSDEPS=""; PY=""; ALSO=""; DBADMIN=""
while [ $# -gt 0 ]; do
  case "$1" in
    --yes) YES=1; shift;; --db) DBS="$2"; shift 2;; --suite-db) ADBS="$2"; shift 2;; --admin) ADMIN="$2"; shift 2;; --no-admin) NO_ADMIN=1; shift;;
    --port) PORT="$2"; shift 2;; --public-url) PUBURL="$2"; shift 2;; --cookie-domain) COOKIE="$2"; shift 2;;
    --service) SERVICE=1; shift;; --no-service) SERVICE=0; shift;; --system-deps) SYSDEPS=1; shift;; --no-system-deps) SYSDEPS=0; shift;;
    --python) PY="$2"; shift 2;; --also) ALSO="$2"; shift 2;; --db-admin) DBADMIN="$2"; shift 2;;
    -h|--help) sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) die "unknown option $1 (try --help)";;
  esac
done
[ -n "$DBS" ] || DBS="${IOSUITE_DB:-}"
[ -n "$ADBS" ] || ADBS="${IOSUITE_SUITE_DB:-}"
[ -n "$ADMIN" ] || ADMIN="${IOSUITE_ADMIN:-}"
[ -n "$ALSO" ] || ALSO="${IOSUITE_ALSO:-}"
[ -n "$DBADMIN" ] || DBADMIN="${IOSUITE_DB_ADMIN:-}"
ask() { _v="$1"; _q="$2"; _d="$3"
  if [ "$YES" = 1 ] || [ ! -t 0 ]; then eval "$_v=\"\$_d\""; return; fi
  printf '%s [%s]: ' "$_q" "$_d"; read -r _a || _a=""; [ -n "$_a" ] && eval "$_v=\"\$_a\"" || eval "$_v=\"\$_d\""; }
asksecret() { _v="$1"; _q="$2"
  if [ "$YES" = 1 ] || [ ! -t 0 ]; then eval "$_v=''"; return; fi
  printf '%s: ' "$_q"; stty -echo 2>/dev/null; read -r _a || _a=""; stty echo 2>/dev/null; printf '\n'; eval "$_v=\"\$_a\""; }
getenv() { [ -f config.env ] && sed -n "s/^$1=//p" config.env | tail -n 1; true; }
sharedenv() { getenv "IOSUITE_DB_$1"; }
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
command -v git >/dev/null || die "git is needed to install the suite's shared library (avandeputte/iosuite-shared): install git, then run this again"
PY="${PY:-python3}"

# ---- the answers
if [ -z "$DBS" ]; then
  say "The ioSuite database (MariaDB / MySQL; the start page keeps its settings there)"
  H="$(getenv DB_HOST)"; P="$(getenv DB_PORT)"; D="$(getenv DB_NAME)"; U="$(getenv DB_USER)"
  ask H "Host" "${H:-127.0.0.1}"; ask P "Port" "${P:-3306}"; ask D "Database" "${D:-suite}"; ask U "User" "${U:-suite}"
  asksecret W "Password (empty: keep the current one, or 'suite')"; [ -n "$W" ] || W="$(getenv DB_PASSWORD)"; [ -n "$W" ] || W=suite
  DBS="$H:$P/$D:$U:$W"
fi
split DB "$DBS"
if [ -z "$ADBS" ]; then
  say "The Shared ioSuite database: accounts and suite-wide settings, shared by every app of the suite"
  H="$(sharedenv HOST)"; P="$(sharedenv PORT)"; D="$(sharedenv NAME)"; U="$(sharedenv USER)"
  ask H "Host" "${H:-$DB_HOST}"; ask P "Port" "${P:-$DB_PORT}"; ask D "Database" "${D:-iosuite}"; ask U "User" "${U:-iosuite}"
  asksecret W "Password (empty: keep the current one, or 'iosuite')"; [ -n "$W" ] || W="$(sharedenv PASSWORD)"; [ -n "$W" ] || W=iosuite
  ADBS="$H:$P/$D:$U:$W"
fi
split SHARED "$ADBS"
[ -n "$PORT" ] || { P="$(getenv PORT)"; ask PORT "Web port" "${P:-8630}"; }
[ -n "$PUBURL" ] || { U2="$(getenv PUBLIC_URL)"; ask PUBURL "Public address, e.g. https://home.example.com (empty: as reached)" "$U2"; }
[ -n "$COOKIE" ] || { C2="$(getenv COOKIE_DOMAIN)"; ask COOKIE "Domain the sign-in is shared on, e.g. example.com (empty: this host only)" "$C2"; }
if [ -z "$ADMIN" ] && [ "$NO_ADMIN" = 0 ] && [ "$YES" = 0 ] && [ -t 0 ]; then
  ask AN "Admin user name (empty: an account from another io app, or make it in the browser on the first visit)" "admin"
  if [ -n "$AN" ]; then asksecret AW "Admin password (8 or more; empty for an existing account)"; [ -n "$AW" ] && ADMIN="$AN:$AW"; fi
fi
if [ -z "$DBADMIN" ] && [ "$YES" = 0 ]; then
  ask DAU "MariaDB administrator who may create the databases and users above, e.g. root (empty: they exist already)" ""
  if [ -n "$DAU" ]; then asksecret DAW "Password of $DAU"; DBADMIN="$DAU:$DAW"; fi
fi
if [ -z "$ALSO" ]; then
  say "The other apps of the suite can be installed here too, beside ioSuite, with the same database server (each app gets its own database), the same Shared ioSuite database, sign-in domain and admin"
  ask ALSO "Also install (iopix, ionotes, iocalendar, iocontacts, iohealth; comma-separated, 'all', or 'none')" "none"
fi

# ---- Python environment
say "Installing the Python packages"
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -e .

# ---- settings (kept between runs; passwords readable by the owner only)
say "Writing config.env"
touch config.env; chmod 600 config.env
setenv() { grep -v "^$1=" config.env > config.env.tmp || true; printf '%s=%s\n' "$1" "$2" >> config.env.tmp; mv config.env.tmp config.env; chmod 600 config.env; }
setenv DB_HOST "$DB_HOST"; setenv DB_PORT "$DB_PORT"; setenv DB_NAME "$DB_NAME"; setenv DB_USER "$DB_USER"; setenv DB_PASSWORD "$DB_PASSWORD"
setenv IOSUITE_DB_HOST "$SHARED_HOST"; setenv IOSUITE_DB_PORT "$SHARED_PORT"; setenv IOSUITE_DB_NAME "$SHARED_NAME"
setenv IOSUITE_DB_USER "$SHARED_USER"; setenv IOSUITE_DB_PASSWORD "$SHARED_PASSWORD"
setenv PORT "$PORT"; setenv PUBLIC_URL "$PUBURL"; setenv COOKIE_DOMAIN "$COOKIE"

say "Checking the databases ($DB_HOST:$DB_PORT/$DB_NAME and $SHARED_HOST:$SHARED_PORT/$SHARED_NAME)"
if [ -n "$DBADMIN" ]; then
  say "Creating the databases and users as ${DBADMIN%%:*}"
  DB_ADMIN_PASSWORD="${DBADMIN#*:}" .venv/bin/iosuite-shared --config "$APP" provision --admin "${DBADMIN%%:*}" || die "could not create the databases and users (see above): check the administrator's name and password"
fi
.venv/bin/python -m app.cli check || die "could not reach a database: check the host, port, user and password (and that the user may connect from this machine)"
if [ -n "$ADMIN" ]; then
  ADMIN_PASSWORD="${ADMIN#*:}" .venv/bin/iosuite-shared --config . admin "${ADMIN%%:*}" --app iosuite
fi

# ---- the service
if [ -z "$SERVICE" ]; then
  if command -v systemctl >/dev/null && [ "$(id -u)" = 0 ]; then SERVICE=1; else SERVICE=0; fi
fi
if [ "$SERVICE" = 1 ]; then
  say "Installing the iosuite service"
  OWNER="$(stat -c %U "$APP" 2>/dev/null || echo root)"
  cat > /etc/systemd/system/iosuite.service <<UNIT
[Unit]
Description=ioSuite
After=network-online.target mariadb.service
Wants=network-online.target

[Service]
Type=simple
User=$OWNER
EnvironmentFile=$APP/config.env
WorkingDirectory=$APP
ExecStart=$APP/.venv/bin/python -m app
Restart=always
RestartSec=5
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable -q iosuite
  systemctl restart iosuite
  sleep 2
  systemctl is-active -q iosuite || die "the service did not start: journalctl -u iosuite -n 50"
  say "ioSuite runs on port $PORT"
else
  say "Done. Start it with ./run.sh (port $PORT)"
fi

# ---- the other apps of the suite, beside this one (iosuite-shared install: the shared answers from config.env)
case "$ALSO" in ''|none|no) ;;
  *) say "Installing the other apps: $ALSO"
     if [ "$SERVICE" = 1 ]; then SVC="--service"; else SVC="--no-service"; fi
     DBA=""; [ -z "$DBADMIN" ] || { DBA="--db-admin ${DBADMIN%%:*}"; DB_ADMIN_PASSWORD="${DBADMIN#*:}"; export DB_ADMIN_PASSWORD; }
     if [ -n "$ADMIN" ]; then
       ADMIN_PASSWORD="${ADMIN#*:}" .venv/bin/iosuite-shared --config "$APP" install "$ALSO" --admin "${ADMIN%%:*}" --from iosuite $SVC $DBA
     else
       .venv/bin/iosuite-shared --config "$APP" install "$ALSO" --from iosuite $SVC $DBA
     fi || die "not every app could be installed; see the lines above (each one can be set up again with its own setup.sh)";;
esac
