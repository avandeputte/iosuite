#!/bin/sh
# ioContact setup: asks a few questions (or takes flags), then installs the Python packages, writes the settings,
# creates the tables and the admin account and, on Linux with systemd, installs and starts the service.
#
#   ./setup.sh                 ask the questions
#   ./setup.sh --yes ...       no questions: defaults and the flags below
#
# Flags (the same in every app of the suite):
#        --db HOST:PORT/DATABASE:USER:PASSWORD        (MariaDB / MySQL; default 127.0.0.1:3306/contacts:contacts:contacts)
#        --suite-db HOST:PORT/DATABASE:USER:PASSWORD  (the Shared ioSuite database: accounts and suite-wide settings;
#                                                      default: the same server, iosuite:iosuite)
#        --admin NAME:PASSWORD | --no-admin   --port N (8640)   --public-url URL   --cookie-domain DOMAIN
#        --service | --no-service   --system-deps | --no-system-deps   --python PATH
#   --db-admin USER:PASSWORD      a MariaDB / MySQL administrator (root...): the databases and users above are created
#                                 for you, with the passwords you answered (IOCONTACT_DB_ADMIN does the same; empty: they exist)
#   --also APP,APP | all        add other apps of the suite to this server, beside this one, with the same database
#                                 server (each app its own database), Shared ioSuite database, sign-in domain and
#                                 admin: those questions are asked once (IOCONTACT_ALSO does the same)
#   --remove APP,APP              take apps of the suite off this server: the service and the program files go, the
#                                 app's database and data stay (IOCONTACT_REMOVE does the same)
#   --reconfigure APP,APP         ask the setup questions of other apps that are already here again, the current
#                                 answers as the defaults (each app's own setup.sh)
#   --apps                        only that: show the apps that are here; tick or untick them, or pick one to
#                                 reconfigure (no other question). Without --yes, every run ends with this list
#        ioContact's own: --ldap-port N (3890; 0 turns LDAP off)
# Secrets can stay off the command line: IOCONTACT_DB, IOCONTACT_SUITE_DB and IOCONTACT_ADMIN in the environment do
# what --db, --suite-db and --admin do. Run it again at any time: it keeps config.env and only changes what you answer.
set -e
cd "$(dirname "$0")"
APP="$(pwd)"
say() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
YES=0; DBS=""; SDBS=""; ADMIN=""; NO_ADMIN=0; PORT=""; LDAP=""; PUBURL=""; COOKIE=""; SERVICE=""; SYSDEPS=""; PY=""; ALSO=""; DBADMIN=""; REMOVE=""; REDO=""; APPSONLY=0; NOAPPS=0
while [ $# -gt 0 ]; do
  case "$1" in
    --yes) YES=1; shift;; --db) DBS="$2"; shift 2;; --suite-db) SDBS="$2"; shift 2;; --admin) ADMIN="$2"; shift 2;; --no-admin) NO_ADMIN=1; shift;;
    --port) PORT="$2"; shift 2;; --ldap-port) LDAP="$2"; shift 2;; --public-url) PUBURL="$2"; shift 2;; --cookie-domain) COOKIE="$2"; shift 2;;
    --service) SERVICE=1; shift;; --no-service) SERVICE=0; shift;; --system-deps) SYSDEPS=1; shift;; --no-system-deps) SYSDEPS=0; shift;;
    --python) PY="$2"; shift 2;; --also) ALSO="$2"; shift 2;; --remove) REMOVE="$2"; shift 2;; --reconfigure) REDO="$2"; shift 2;; --apps) APPSONLY=1; shift;; --db-admin) DBADMIN="$2"; shift 2;;
    -h|--help) sed -n '2,27p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) die "unknown option $1 (try --help)";;
  esac
done
[ -n "$DBS" ] || DBS="${IOCONTACT_DB:-}"
[ -n "$SDBS" ] || SDBS="${IOCONTACT_SUITE_DB:-}"
[ -n "$ADMIN" ] || ADMIN="${IOCONTACT_ADMIN:-}"
[ -n "$ALSO" ] || ALSO="${IOCONTACT_ALSO:-}"
[ -n "$REMOVE" ] || REMOVE="${IOCONTACT_REMOVE:-}"
if [ "$APPSONLY" = 1 ]; then  # the apps on this server: what is here, tick and untick (iosuite-shared apps)
  [ -x "$APP/.venv/bin/iosuite-shared" ] || die "set this app up first: ./setup.sh"
  exec "$APP/.venv/bin/iosuite-shared" --config "$APP" apps --from iocontact
fi
[ -n "$DBADMIN" ] || DBADMIN="${IOCONTACT_DB_ADMIN:-}"
ask() { _v="$1"; _q="$2"; _d="$3"
  if [ "$YES" = 1 ] || [ ! -t 0 ]; then eval "$_v=\"\$_d\""; return; fi
  printf '%s [%s]: ' "$_q" "$_d"; read -r _a || _a=""; [ -n "$_a" ] && eval "$_v=\"\$_a\"" || eval "$_v=\"\$_d\""; }
asksecret() { _v="$1"; _q="$2"
  if [ "$YES" = 1 ] || [ ! -t 0 ]; then eval "$_v=''"; return; fi
  printf '%s: ' "$_q"; stty -echo 2>/dev/null; read -r _a || _a=""; stty echo 2>/dev/null; printf '\n'; eval "$_v=\"\$_a\""; }
getenv() { [ -f config.env ] && sed -n "s/^$1=//p" config.env | tail -n 1; true; }

# ---- system packages (Python 3.10+ and venv)
if [ "$SYSDEPS" != 0 ] && ! python3 -c 'import sys, venv, ensurepip; assert sys.version_info >= (3, 10)' 2>/dev/null; then
  say "Installing Python"
  if command -v apt-get >/dev/null; then apt-get update -qq && apt-get install -y -qq python3 python3-venv python3-pip git >/dev/null
  elif command -v dnf >/dev/null; then dnf install -y -q python3 python3-pip git
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
# the Shared ioSuite database (accounts, sessions and settings shared by every app of the suite)
suiteenv() { getenv "IOSUITE_DB_$1"; }
if [ -z "$SDBS" ]; then
  SD0=iosuite; SU0=iosuite
  H="$(suiteenv HOST)"; P="$(suiteenv PORT)"; D="$(suiteenv NAME)"; U="$(suiteenv USER)"
  ask H "Shared ioSuite database: host" "${H:-$DB_HOST}"; ask P "Port" "${P:-$DB_PORT}"; ask D "Database" "${D:-$SD0}"; ask U "User" "${U:-$SU0}"
  asksecret W "Password (empty: keep the current one, or '$SU0')"; [ -n "$W" ] || W="$(suiteenv PASSWORD)"; [ -n "$W" ] || W="$SU0"
  SDBS="$H:$P/$D:$U:$W"
fi
SUITE_HOST="${SDBS%%:*}"; r="${SDBS#*:}"; SUITE_PORT="${r%%/*}"; r="${r#*/}"; SUITE_NAME="${r%%:*}"; r="${r#*:}"; SUITE_USER="${r%%:*}"; SUITE_PASSWORD="${r#*:}"
[ -n "$PORT" ] || { P="$(getenv PORT)"; ask PORT "Web port" "${P:-8640}"; }
[ -n "$LDAP" ] || { L="$(getenv LDAP_PORT)"; ask LDAP "LDAP directory port (0: off)" "${L:-3890}"; }
[ -n "$PUBURL" ] || { U2="$(getenv PUBLIC_URL)"; ask PUBURL "Public address, e.g. https://contacts.example.com (empty: as reached)" "$U2"; }
[ -n "$COOKIE" ] || { C2="$(getenv COOKIE_DOMAIN)"; ask COOKIE "Domain the sign-in is shared on, e.g. example.com (empty: this host only)" "$C2"; }
if [ -z "$ADMIN" ] && [ "$NO_ADMIN" = 0 ] && [ "$YES" = 0 ] && [ -t 0 ]; then
  ask AN "Admin user name (empty: make it in the browser on the first visit)" "admin"
  if [ -n "$AN" ]; then asksecret AW "Admin password (8 or more)"; [ -n "$AW" ] && ADMIN="$AN:$AW"; fi
fi
if [ -z "$DBADMIN" ] && [ "$YES" = 0 ]; then
  ask DAU "MariaDB administrator who may create the databases and users above, e.g. root (empty: they exist already)" ""
  if [ -n "$DAU" ]; then asksecret DAW "Password of $DAU"; DBADMIN="$DAU:$DAW"; fi
fi

# ---- Python environment
say "Installing the Python packages"
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
# the suite's shared library, from the same commit: shared/ inside an installed copy, beside this folder in a checkout of the repository
SHARED=shared; [ -f shared/pyproject.toml ] || SHARED=../shared
[ -f "$SHARED/pyproject.toml" ] || die "the suite's shared library is missing: this folder is part of the suite's repository (github.com/avandeputte/iosuite) and needs its shared/ folder beside it"
.venv/bin/python -m pip install -q -e "$SHARED"
.venv/bin/python -m pip install -q -e .

# ---- settings (kept between runs; passwords readable by the owner only)
say "Writing config.env"
touch config.env; chmod 600 config.env
setenv() { grep -v "^$1=" config.env > config.env.tmp || true; printf '%s=%s\n' "$1" "$2" >> config.env.tmp; mv config.env.tmp config.env; chmod 600 config.env; }
setenv DB_HOST "$DB_HOST"; setenv DB_PORT "$DB_PORT"; setenv DB_NAME "$DB_NAME"; setenv DB_USER "$DB_USER"; setenv DB_PASSWORD "$DB_PASSWORD"
setenv IOSUITE_DB_HOST "$SUITE_HOST"; setenv IOSUITE_DB_PORT "$SUITE_PORT"; setenv IOSUITE_DB_NAME "$SUITE_NAME"
setenv IOSUITE_DB_USER "$SUITE_USER"; setenv IOSUITE_DB_PASSWORD "$SUITE_PASSWORD"
setenv PORT "$PORT"; setenv LDAP_PORT "$LDAP"; setenv PUBLIC_URL "$PUBURL"; setenv COOKIE_DOMAIN "$COOKIE"

say "Checking the databases ($DB_HOST:$DB_PORT/$DB_NAME and $SUITE_HOST:$SUITE_PORT/$SUITE_NAME)"
if [ -n "$DBADMIN" ]; then
  say "Creating the databases and users as ${DBADMIN%%:*}"
  DB_ADMIN_PASSWORD="${DBADMIN#*:}" .venv/bin/iosuite-shared --config "$APP" provision --admin "${DBADMIN%%:*}" || die "could not create the databases and users (see above): check the administrator's name and password"
fi
.venv/bin/python -m app.cli check || die "could not reach a database: check the host, port, user and password (and that the user may connect from this machine)"
if [ -n "$ADMIN" ]; then
  ADMIN_PASSWORD="${ADMIN#*:}" .venv/bin/iosuite-shared --config . admin "${ADMIN%%:*}" --app iocontact
fi

# ---- the service
if [ -z "$SERVICE" ]; then
  if command -v systemctl >/dev/null && [ -d /run/systemd/system ] && [ "$(id -u)" = 0 ]; then SERVICE=1; else SERVICE=0; fi
fi
if [ "$SERVICE" = 1 ]; then
  say "Installing the iocontact service"
  OWNER="$(stat -c %U "$APP" 2>/dev/null || echo root)"
  cat > /etc/systemd/system/iocontact.service <<UNIT
[Unit]
Description=ioContact
After=network-online.target mariadb.service
Wants=network-online.target

[Service]
Type=simple
User=$OWNER
EnvironmentFile=$APP/config.env
WorkingDirectory=$APP
ExecStart=$APP/.venv/bin/python -m app
AmbientCapabilities=CAP_NET_BIND_SERVICE
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable -q iocontact
  systemctl restart iocontact
  sleep 2
  systemctl is-active -q iocontact || die "the service did not start: journalctl -u iocontact -n 50"
  say "ioContact runs on port $PORT (LDAP: ${LDAP})"
else
  say "Done. Start it with ./run.sh (port $PORT)"
fi

# ---- the other apps of the suite on this server (iosuite-shared apps): --also adds, --remove removes, --reconfigure
# asks an app's questions again; with none of them and somebody at the keyboard, the list of what is here, to tick and untick
case "$ALSO" in none|no) ALSO=""; NOAPPS=1;; esac  # --also none: no list either (how the list itself runs a setup.sh)
case "$REMOVE" in none|no) REMOVE="";; esac
if [ -n "$ALSO$REMOVE$REDO" ] || { [ "$YES" = 0 ] && [ "$NOAPPS" = 0 ] && [ -t 0 ]; }; then
  if [ "$SERVICE" = 1 ]; then set -- --service; else set -- --no-service; fi
  [ -z "$ALSO" ] || set -- "$@" --add "$ALSO"
  [ -z "$REMOVE" ] || set -- "$@" --remove "$REMOVE"
  [ -z "$REDO" ] || set -- "$@" --reconfigure "$REDO"
  [ -z "$DBADMIN" ] || { set -- "$@" --db-admin "${DBADMIN%%:*}"; DB_ADMIN_PASSWORD="${DBADMIN#*:}"; export DB_ADMIN_PASSWORD; }
  [ -z "$ADMIN" ] || { set -- "$@" --admin "${ADMIN%%:*}"; ADMIN_PASSWORD="${ADMIN#*:}"; export ADMIN_PASSWORD; }
  "$APP/.venv/bin/iosuite-shared" --config "$APP" apps --from iocontact "$@" || die "not every app could be added or removed; see the lines above (./setup.sh --apps shows what is here)"
fi
