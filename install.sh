#!/usr/bin/env bash
# ioSuite on this server: install it, and run this again at any time to add, remove or reconfigure apps.
#
#   curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/install.sh | bash -s -- --add iotask,ionote
#
# The first time, on a server without ioSuite: fetches the suite, sets up one app (ioStart, the start page, unless
# --first APP) by asking its questions, then shows the list of apps to tick the others.
# Every other time: shows the apps that are here; tick one to add it, untick one to remove it, r and its number to
# change its settings. Removing an app keeps its database and its data unless you ask otherwise.
#
#   --into DIR            where the apps live, each in DIR/<app>/app (IOSUITE_BASE; default /opt as root, else ~/iosuite)
#   --first APP           the app set up first on a new server (default iostart)
#   --add APP,APP | all   add apps                    --remove APP,APP   remove apps (database and data stay)
#   --reconfigure APP,APP ask an installed app's questions again
#   --delete-data         with --remove: also drop the app's own database and delete its data folder (cannot be undone)
#   --list                only show what is installed
#   --service | --no-service   the apps you add run as a service (the default as root with systemd), or are started by hand
#   --db-admin USER:PASSWORD   a MariaDB administrator: the databases and users of the apps you add are created for you
# On a new server every other option goes to the first app's setup.sh, so an install without questions is e.g.
#   ... | bash -s -- --yes --db 127.0.0.1:3306/suite:suite:PASSWORD --admin alex:PASSWORD --db-admin root:PASSWORD --add all
# (see that app's `setup.sh --help`; the passwords can come from the environment instead, e.g. IOSTART_DB).
# The apps: iostart iocalendar iocontact ionote iohealth iotask iorecipe iopix iodns iobackup
set -euo pipefail
REPO="${IOSUITE_REPO:-https://github.com/avandeputte/iosuite}"
APPS="iostart iocalendar iocontact ionote iohealth iotask iorecipe iopix iodns iobackup"
say() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

main() {
  local base="${IOSUITE_BASE:-}" first="iostart" add="" dbadmin="" svc="" rest=() manage=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --into) base="$2"; shift 2;;
      --first) first="$2"; shift 2;;
      --add) add="$2"; manage+=(--add "$2"); shift 2;;
      --remove|--reconfigure) manage+=("$1" "$2"); shift 2;;
      --delete-data|--list) manage+=("$1"); shift;;
      --db-admin) dbadmin="$2"; shift 2;;
      --service|--no-service) manage+=("$1"); svc="$1"; shift;;
      -h|--help) sed -n '2,22p' "${BASH_SOURCE[0]:-/dev/null}" 2>/dev/null | sed 's/^# \{0,1\}//' || true
                 [ -n "${BASH_SOURCE[0]:-}" ] || echo "see the top of $REPO/blob/main/install.sh"; exit 0;;
      *) rest+=("$1"); shift;;
    esac
  done
  if [ -z "$base" ]; then if [ "$(id -u)" = 0 ]; then base=/opt; else base="$HOME/iosuite"; fi; fi
  case " $APPS " in *" $first "*) ;; *) die "--first $first: not one of the apps ($APPS)";; esac

  # piped from curl, the keyboard is not on standard input: the questions read the terminal
  if [ ! -t 0 ] && [ -t 1 ] && (exec </dev/tty) 2>/dev/null; then exec </dev/tty; fi

  # an app that is already here runs the list (ioStart when it is; any other otherwise)
  local a home=""
  for a in $APPS; do
    if [ -f "$base/$a/app/config.env" ] && [ -x "$base/$a/app/.venv/bin/iosuite-shared" ]; then home="$base/$a/app"; break; fi
  done
  if [ -n "$home" ]; then
    [ ${#rest[@]} -eq 0 ] || die "ioSuite is already on this server (in $base): ${rest[*]} is for a first install. To change an app's settings: --reconfigure APP"
    "$home/.venv/bin/iosuite-shared" apps --help >/dev/null 2>&1 || die "the apps in $base are older than this installer: update them first (Settings › Global settings › Updates, or $home/update.sh)"
    [ -z "$dbadmin" ] || { manage+=(--db-admin "${dbadmin%%:*}"); export DB_ADMIN_PASSWORD="${dbadmin#*:}"; }
    exec "$home/.venv/bin/iosuite-shared" --config "$home" apps --into "$base" ${manage[@]+"${manage[@]}"}
  fi

  # a new server: fetch the suite and set the first app up; its setup.sh ends with the list of the others
  case " ${manage[*]-} " in *" --remove "*|*" --reconfigure "*|*" --list "*) die "ioSuite is not on this server yet (nothing in $base): nothing to remove, reconfigure or list";; esac
  if ! command -v git >/dev/null 2>&1; then
    say "Installing git"
    if command -v apt-get >/dev/null 2>&1 && [ "$(id -u)" = 0 ]; then apt-get update -qq && apt-get install -y -qq git >/dev/null
    elif command -v dnf >/dev/null 2>&1 && [ "$(id -u)" = 0 ]; then dnf install -y -q git
    else die "install git, then run this again"; fi
  fi
  local src; src="$(mktemp -d)"; trap "rm -rf '$src'" EXIT
  say "Fetching ioSuite from $REPO"
  git clone -q --depth 1 "$REPO" "$src"
  [ -f "$src/$first/setup.sh" ] && [ -f "$src/shared/pyproject.toml" ] || die "$REPO has no $first/ folder with a setup.sh, or no shared/ folder"
  local target="$base/$first/app"
  mkdir -p "$target"
  cp -a "$src/$first/." "$target/"
  rm -rf "$target/shared"; cp -a "$src/shared" "$target/shared"
  git -C "$src" rev-parse HEAD > "$target/COMMIT"
  say "Setting up $first in $target"
  [ -z "$add" ] || rest+=(--also "$add")
  [ -z "$dbadmin" ] || rest+=(--db-admin "$dbadmin")
  [ -z "$svc" ] || rest+=("$svc")
  cd "$target"
  IOSUITE_REPO="$REPO" sh ./setup.sh ${rest[@]+"${rest[@]}"}
  say "ioSuite is installed in $base. Run this again at any time to add, remove or reconfigure apps."
}
main "$@"
