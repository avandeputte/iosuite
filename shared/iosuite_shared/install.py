"""`iosuite-shared install APP...`: put other apps of the suite on this machine, beside the one that is already here,
without asking the shared questions again.

Every app's setup.sh ends with "Also install other apps of the suite here?" (or takes `--also APP,APP`). The answer
comes here: with the calling app's config.env (`--config FOLDER`) this reads the answers that are the same for every
app and hands them to each companion's own setup.sh, which runs unattended (`--yes`):

  * the app database server: DB_HOST, DB_PORT, DB_USER and DB_PASSWORD are reused, each app gets its own database
    name, the app's own (iostart, iocalendar, ...; the app creates it when the user may);
  * the Shared ioSuite database: IOSUITE_DB_* as they are;
  * the sign-in domain (COOKIE_DOMAIN) and, with `--admin NAME` and ADMIN_PASSWORD in the environment, the admin
    account, made an admin of every companion too (the account already exists in the shared database).

Each companion is fetched from GitHub (its folder of the suite's repository, with the shared library beside it in
shared/) into BASE/<app>/app (BASE is the folder above the calling app's own
<name>/app, so /opt when the app is in /opt/iostart/app) with its commit in COMMIT, the layout the Proxmox installers
make and update.sh understands; then `sh setup.sh --yes ...` runs there and installs the packages, writes config.env,
creates the tables and (as root with systemd) the service. The passwords travel in the environment, never on a
command line. What differs per app is left to its defaults: the usual port, no public address (reached as is), the
system time zone. ioPix gets `--no-digikam` and a photos folder (`--photos DIR`, default /library/photos, created when
missing), and the AI models are left off (`--features none`) so the install stays small; both are changed later in
its Settings or by running its setup.sh again.

The same server, later: `iosuite-shared --config FOLDER apps` (what `./setup.sh --apps` runs, and the last step of
every setup.sh) shows the apps that are here and lets the person tick and untick them; `--add APP,APP` and
`--remove APP,APP` do the same without questions. An app is "here" when BASE/<app>/app/config.env exists.

Reconfiguring an app that is here (`r` and its number in the list, or `--reconfigure APP,APP`) runs that app's own
setup.sh in its folder, with the person at the keyboard: every question again, the current answer as the default, so
only what is answered differently changes (the port, the public address, the database, the app's own questions), and
the service is restarted. Nothing is fetched and no data is touched. Without questions, the app's setup.sh takes the
same answers as flags: `sh BASE/<app>/app/setup.sh --yes --port 8700`.

Removing an app (`remove`, or unticking it) stops its service and takes the service away, deletes its program files
(the code, the Python environment, config.env) and takes it out of the suite's list of apps, so the other apps stop
showing and calling it. What the person made stays: the app's database, its data folder, the photos, the backups.
Adding the app again finds them. Only `--delete-data` (asked apart, default no) also drops the app's own database and
deletes its data folder under BASE/<app>; never the Shared ioSuite database (the accounts, their roles and the keys
stay as they are), never a database another app here uses, never the photos or digiKam's own database (ioPix) or the
backups (ioBackup): the folders config.env names for them (KEPT) stay wherever they are, inside the app's folder too.
An app that looks to be running on another machine now (moved there, on the same database: see used_elsewhere)
keeps its database even with `--delete-data`, and stays in the suite's list of apps.
The app this runs from is removed by another app that stays; the last app here is not removed.

How the apps are reached (`a` in the list, or `apps --reach ports|one|one-proxy|proxy [--address URL]`) is one answer
for every app on the machine, written as HOST in each config.env (iosuite_shared.serve) and as the suite's one-address
switch in the Shared ioSuite database (iosuite_shared.suite.one_address; the start page passes each app's folder on):

  ports      each app on its own port, reachable from the network (how a new install starts)
  one        one address: the start page answers for every app (…/calendar/); the other apps listen on this
             machine only (HOST=127.0.0.1)
  one-proxy  the same behind a reverse proxy on this server (Caddy, nginx: HTTPS): the start page listens on this
             machine only too
  proxy      a reverse proxy on this server reaches each app on its own port: every app listens on this machine only

`--address URL` names where the suite is: the start page's PUBLIC_URL, and with `proxy` every other app's folder of it
too (https://home.example.com/calendar), for a proxy that serves one name with a folder per app. The apps whose
config.env changed are restarted; an app added later follows what the others do (with `proxy`, the address is kept
in BASE/iosuite-reach.env, so an app added while the start page is alone still gets its folder). ioContact's LDAP
directory, which is not HTTP and so passes through neither, stays where it listened. Going back undoes it: an
address the person had named for HOST (kept as HOST_BEFORE while the app listens on this machine only) comes back,
and a PUBLIC_URL that was only the app's folder of the proxy's address is taken out. Removing the start page while
it answers at the one address puts every app back on its own port first.
"""
import atexit
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

# the one repository of the suite: a folder per app, the shared library in shared/
REPO = "avandeputte/iosuite"
# name -> how to set it up (its folder in the repository has the same name, and so do its database and its database
# user by default: iothings). `env` is the prefix of the environment variables its setup.sh reads the secrets from (PFX_DB, PFX_SUITE_DB, PFX_ADMIN).
APPS = {
    "iostart": dict(label="ioStart", port=8630, env="IOSTART"),
    "iocalendar": dict(label="ioCalendar", port=8620, env="IOCALENDAR"),
    "iocontact": dict(label="ioContact", port=8640, env="IOCONTACT"),
    "ionote": dict(label="ioNote", port=8610, env="IONOTE", data=True),
    "iohealth": dict(label="ioHealth", port=8650, env="IOHEALTH"),
    "iotask": dict(label="ioTask", port=8670, env="IOTASK"),
    "iodns": dict(label="ioDNS", port=8660, env="IODNS"),
    "iobackup": dict(label="ioBackup", port=8680, env="IOBACKUP"),
    "iorecipe": dict(label="ioRecipe", port=8690, env="IORECIPE"),
    "iothings": dict(label="ioThings", port=8700, env="IOTHINGS"),
    "iomoney": dict(label="ioMoney", port=8710, env="IOMONEY"),
    "iopix": dict(label="ioPix", port=8600, env="IOPIX", data=True,
                  extra=["--no-digikam", "--features", "none"], photos=True, launchd="com.iopix"),
}
DEFAULT_PHOTOS = "/library/photos"
# What a person keeps that no removal deletes, by the config.env setting that names its folder: (setting, what it is)
KEPT = (("PHOTOS_ROOT", "photos"), ("BACKUP_DIR", "backups"), ("DIGIKAM_DB_DIR", "digiKam database"))
IDENT = re.compile(r"^[A-Za-z0-9_]+$")


def read_env_file(path):
    """config.env as a dict (KEY=VALUE lines; the last one wins; no quoting, as the apps' setup.sh write it)."""
    out = {}
    p = Path(path)
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def parse_apps(spec):
    """'iopix, ionote' / ['iopix,ionote'] -> ['iopix', 'ionote']; 'all' -> every app; 'none' / '' -> []."""
    if isinstance(spec, str):
        spec = [spec]
    names = []
    for part in spec:
        for n in part.replace(";", ",").replace(" ", ",").split(","):
            n = n.strip().lower()
            if not n or n == "none":
                continue
            if n == "all":
                names.extend(a for a in APPS if a not in names)
                continue
            if n not in APPS:
                raise SystemExit(f"error: unknown app {n!r} (one of: {', '.join(APPS)}, or all)")
            if n not in names:
                names.append(n)
    return names


def dsn(host, port, name, user, password):
    return f"{host}:{port}/{name}:{user}:{password}"


def shared_answers(cfg):
    """The answers every app shares, from the calling app's config.env: the app database server (its credentials;
    the database name differs per app), the Shared ioSuite database and the cookie domain. An app without a MariaDB
    of its own yet (ioPix, before its database is set up from its web page) lends the Shared ioSuite database's server and
    credentials for the companions' databases instead."""
    s_host = cfg.get("IOSUITE_DB_HOST") or cfg.get("DB_HOST") or "127.0.0.1"
    s_port = cfg.get("IOSUITE_DB_PORT") or cfg.get("DB_PORT") or "3306"
    s_name = cfg.get("IOSUITE_DB_NAME") or "iosuite"
    s_user = cfg.get("IOSUITE_DB_USER") or "iosuite"
    s_pw = cfg.get("IOSUITE_DB_PASSWORD") or ""
    if cfg.get("DB_HOST") and cfg.get("DB_USER") and cfg.get("DB_TYPE", "mysql") in ("mysql", "mariadb"):
        a_host, a_port, a_user, a_pw = cfg["DB_HOST"], cfg.get("DB_PORT") or "3306", cfg["DB_USER"], cfg.get("DB_PASSWORD") or ""
    else:
        a_host, a_port, a_user, a_pw = s_host, s_port, s_user, s_pw
    return dict(app_db=(a_host, a_port, a_user, a_pw), suite_db=dsn(s_host, s_port, s_name, s_user, s_pw),
                cookie_domain=cfg.get("COOKIE_DOMAIN", ""))


def base_dir(config_dir):
    """/opt/iostart/app -> /opt (the companions go to /opt/<app>/app); /srv/iostart -> /srv."""
    d = Path(config_dir).resolve()
    return d.parent.parent if d.name == "app" else d.parent


def plan(names, cfg, base, admin=None, service=None, photos=None, from_app=None, ask=False, db_admin=None):
    """One entry per app: where it goes, the setup.sh arguments and the environment with the secrets.

    With `ask` (somebody at the keyboard), each app's setup.sh asks its own questions instead (no --yes, no answers
    on its command line): `seed` holds what the apps already here answered, written where the app's setup.sh takes
    its defaults from, so each question shows it and Enter confirms it. The app's database is named after the app."""
    ans = shared_answers(cfg)
    a_host, a_port, a_user, a_pw = ans["app_db"]
    out = []
    for n in names:
        if n == from_app:
            continue
        a = APPS[n]
        target = Path(base) / n / "app"
        args = ["--yes", "--cookie-domain", ans["cookie_domain"], "--public-url", ""]
        if service is True:
            args.append("--service")
        elif service is False:
            args.append("--no-service")
        args += list(a.get("extra", []))
        if a.get("data"):
            args += ["--data", str(Path(base) / n / "data")]
        if a.get("photos"):
            args += ["--photos", photos or DEFAULT_PHOTOS]
        env = {f"{a['env']}_DB": dsn(a_host, a_port, n, a_user, a_pw), f"{a['env']}_SUITE_DB": ans["suite_db"]}
        if admin:
            env[f"{a['env']}_ADMIN"] = f"{admin}:{os.environ.get('ADMIN_PASSWORD', '')}"
        else:
            args.append("--no-admin")
        seed = None
        if ask:
            seed = defaults(n, cfg, base, photos=photos)
            args = ["--also", "none"] + [x for x in ("--service", "--no-service") if x in args]
            env = {f"{a['env']}_ADMIN": env[f"{a['env']}_ADMIN"]} if admin else {}
            if db_admin:  # the app's setup.sh creates its database and user, with the names the person answered
                env[f"{a['env']}_DB_ADMIN"] = f"{db_admin}:{os.environ.get('DB_ADMIN_PASSWORD', '')}"
        out.append(dict(name=n, label=a["label"], target=target, args=args, env=env, port=a["port"], seed=seed))
    return out


def defaults(name, cfg, base, photos=None):
    """The answers an app's questions start from when it is added beside others: the database server, user and
    password of the app already here with its own database named after the new app (iothings), the Shared ioSuite
    database, the sign-in domain, the time zone, the app's usual port and a public address made like the others'."""
    ans = shared_answers(cfg)
    a_host, a_port, a_user, a_pw = ans["app_db"]
    s = re.match(r"^(.*):(\d+)/([^:]*):([^:]*):(.*)$", ans["suite_db"])
    out = {"DB_HOST": a_host, "DB_PORT": a_port, "DB_NAME": name, "DB_USER": a_user, "DB_PASSWORD": a_pw,
           "IOSUITE_DB_HOST": s.group(1), "IOSUITE_DB_PORT": s.group(2), "IOSUITE_DB_NAME": s.group(3),
           "IOSUITE_DB_USER": s.group(4), "IOSUITE_DB_PASSWORD": s.group(5),
           "PORT": str(APPS[name]["port"]), "PUBLIC_URL": public_url_like_others(name, base),
           "COOKIE_DOMAIN": ans["cookie_domain"]}
    if cfg.get("TZ"):
        out["TZ"] = cfg["TZ"]
    if name == "iopix":
        out["DB_TYPE"] = "mysql"
        out["PHOTOS_ROOT"] = photos or DEFAULT_PHOTOS
    if APPS[name].get("data"):
        out["DATA_DIR"] = str(Path(base) / name / "data")
    return out


def public_url_like_others(name, base):
    """A public address for NAME made the way an app already here has its own: https://calendar.example.com ->
    https://things.example.com (the app's folder name, or its key when the other uses its key:
    https://iocalendar.example.com -> https://iothings.example.com), and https://home.example.com/calendar ->
    https://home.example.com/things. Empty when no app here names itself in its address (the start page's own
    address says nothing about the others')."""
    for other in APPS:
        if other == name:
            continue
        url = (read_env_file(Path(base) / other / "app" / "config.env").get("PUBLIC_URL") or "").rstrip("/")
        if not ADDRESS.match(url):
            continue
        scheme, rest = url.split("://", 1)
        host, _, path = rest.partition("/")
        label, dot, domain = host.partition(".")
        words = {other: name, folder_of(other): folder_of(name) or name}
        last = path.rsplit("/", 1)[-1]
        if path and last in words:
            return f"{scheme}://{host}/{path[:len(path) - len(last)]}{words[last]}"
        if not path and dot and label in words:
            return f"{scheme}://{words[label]}.{domain}"
    return ""


def prepare_local_databases(entries, cfg, log=print):
    """A MariaDB on this machine (DB_HOST loopback, as `setup.sh --db local` of ioPix or a Proxmox container with its own
    server make) usually grants the app's user its own database only; as root, over the socket, give that user each
    companion's database too, so their setup.sh can create the tables. Elsewhere nothing is done: the person's user
    needs rights on those names, as the question says."""
    host = (cfg.get("DB_HOST") or "").lower()
    if host not in ("127.0.0.1", "localhost", "::1") or not cfg.get("DB_USER") or os.geteuid() != 0 or not shutil.which("mariadb"):
        return
    user = cfg["DB_USER"].replace("'", "''")
    sql = "".join(f"CREATE DATABASE IF NOT EXISTS `{e['name']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
                  f"GRANT ALL PRIVILEGES ON `{e['name']}`.* TO '{user}'@'localhost', '{user}'@'127.0.0.1';\n" for e in entries) + "FLUSH PRIVILEGES;\n"
    try:
        r = subprocess.run(["mariadb"], input=sql, text=True, capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log(f"  note: could not prepare the databases on the local MariaDB ({exc}); each app creates its own when {cfg['DB_USER']} may")
        return
    if r.returncode == 0:
        log(f"  local MariaDB: the databases {', '.join(e['name'] for e in entries)} belong to {cfg['DB_USER']} too")
    else:
        log(f"  note: could not prepare the databases on the local MariaDB ({r.stderr.strip()[:200]}); each app creates its own when {cfg['DB_USER']} may")


def say(msg):
    print(f"\n\033[1;34m==>\033[0m {msg}", flush=True)


_sources = {}  # repository address -> (a shallow clone of it, its commit): fetched once, however many apps are installed


def _source(url):
    if url not in _sources:
        tmp = Path(tempfile.mkdtemp(prefix="iosuite-src-"))
        atexit.register(shutil.rmtree, tmp, ignore_errors=True)
        subprocess.run(["git", "clone", "-q", "--depth", "1", url, str(tmp)], check=True)
        sha = subprocess.run(["git", "-C", str(tmp), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        _sources[url] = (tmp, sha)
    return _sources[url]


def fetch(name, target, log=print):
    """The app's folder of the suite's repository into TARGET, the shared library into TARGET/shared, COMMIT written:
    the layout the Proxmox installers make, which the app's update.sh keeps up to date."""
    a = APPS[name]
    url = os.environ.get(f"{a['env']}_REPO") or os.environ.get("IOSUITE_REPO") or f"https://github.com/{REPO}"
    if "://" not in url and not os.path.exists(url):
        url = f"https://github.com/{url}"  # owner/name, as update.sh and the Updater take it
    src, sha = _source(url)
    if not (src / name / "setup.sh").is_file() or not (src / "shared" / "pyproject.toml").is_file():
        raise RuntimeError(f"{url} has no {name}/ folder with a setup.sh, or no shared/ folder")
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src / name, target, symlinks=True, dirs_exist_ok=True)
    shutil.rmtree(target / "shared", ignore_errors=True)
    shutil.copytree(src / "shared", target / "shared", symlinks=True)
    (target / "COMMIT").write_text(sha + "\n")
    log(f"  fetched {a['label']} {sha[:7]} into {target}")


def run_setup(entry, log=print):
    env = dict(os.environ)
    env.update(entry["env"])
    cmd = ["sh", "./setup.sh"] + entry["args"]
    log("  sh ./setup.sh " + " ".join(a if a else "''" for a in entry["args"]))
    return subprocess.run(cmd, cwd=str(entry["target"]), env=env).returncode


def install(names, config_dir, base=None, admin=None, service=None, photos=None, from_app=None, db_admin=None, fetcher=fetch, runner=run_setup, log=print,
            reach=None, ask=False):
    """Install every app in NAMES; returns the names that failed (empty when all went well). A new app is reached
    the way the others here are (REACH; `reach`: the way that is about to be set). With `ask`, each app's setup.sh
    asks its questions, the answers of the apps already here as the defaults (plan)."""
    cfg = read_env_file(Path(config_dir) / "config.env") if config_dir else {}
    base = Path(base) if base else base_dir(config_dir or os.getcwd())
    entries = plan(names, cfg, base, admin=admin, service=service, photos=photos, from_app=from_app, ask=ask, db_admin=db_admin)
    if not entries:
        log("nothing to install")
        return []
    mode = reach or reach_now(base, config_dir)
    shared = shared_address(base, config_dir) if mode == "proxy" else None
    for e in entries:
        if shared and e["name"] != "iostart":  # the proxy serves one name, a folder per app: this one's folder of it
            if e["seed"] is not None:
                e["seed"]["PUBLIC_URL"] = f"{shared}/{folder_of(e['name'])}"
            else:
                e["args"][e["args"].index("--public-url") + 1] = f"{shared}/{folder_of(e['name'])}"
    if any(APPS[e["name"]].get("photos") for e in entries):
        p = Path(photos or DEFAULT_PHOTOS)
        if not p.is_dir():
            p.mkdir(parents=True, exist_ok=True)
            log(f"  made the photos folder {p}: mount or copy your photos there (ioPix's Settings can add more folders)")
    fresh = [e for e in entries if not (e["target"] / "config.env").exists()]
    if db_admin and fresh and not ask:  # a MariaDB administrator was given: the companions' databases are made for the app user, wherever the server is
        from iosuite_shared import provision
        provision.run(db_admin, os.environ.get("DB_ADMIN_PASSWORD", ""), cfg, also=[e["name"] for e in fresh], log=log)
    else:
        prepare_local_databases(fresh, cfg, log=log)
    failed = []
    for e in entries:
        say(f"Installing {e['label']} into {e['target']}")
        if (e["target"] / "config.env").exists():
            log(f"  {e['label']} is already set up in {e['target']}: left as it is (its own setup.sh or update.sh changes it)")
            continue
        try:
            fetcher(e["name"], e["target"], log=log)
        except Exception as exc:  # noqa: BLE001 - one failing app must not stop the others
            log(f"  could not fetch {e['label']}: {exc}")
            failed.append(e["name"])
            continue
        pre = _local_env(e["name"], {}) if _local_only(mode, e["name"]) else None
        if e["seed"] is not None:
            # its questions start from these answers: in config.env.failed, which a first setup takes its defaults
            # from (and leaves as a first install until it succeeds); ioPix reads them from config.env
            seed = dict(e["seed"], **(pre or {}))
            takes = "config.env.failed" in (e["target"] / "setup.sh").read_text(encoding="utf-8", errors="replace")
            write_env_file(e["target"] / ("config.env.failed" if takes else "config.env"), seed)
            say(f"{e['label']}'s questions: the answers of the apps already here are the defaults; Enter keeps one")
            if pre:
                log(f"  {e['label']} listens on this machine only, like the other apps here ({REACH[mode][0]})")
        elif pre:  # before it first starts: its setup.sh keeps what config.env already says
            write_env_file(e["target"] / "config.env", pre)
            log(f"  {e['label']} listens on this machine only, like the other apps here ({REACH[mode][0]})")
        rc = runner(e, log=log)
        cfg_file = e["target"] / "config.env"
        if rc != 0 and cfg_file.exists():
            # a first setup that failed is not an install (config.env is what makes an app "here"): its answers are
            # kept aside, and its setup.sh takes them as the defaults on the next run
            cfg_file.replace(e["target"] / "config.env.failed")
        if rc != 0:
            log(f"  {e['label']}'s setup.sh failed (exit {rc}); fix the cause and run `sh {e['target']}/setup.sh` yourself")
            failed.append(e["name"])
        else:
            log(f"  {e['label']} runs on port {e['port']}")
    return failed


# ---------------------------------------------------------------------------------------------------------------------
# what is here, and removing

def app_of(config_dir):
    """The app whose folder CONFIG_DIR is (/opt/iostart/app -> iostart, a checkout's iostart/ -> iostart), or None."""
    if not config_dir:
        return None
    d = Path(config_dir).resolve()
    n = d.parent.name if d.name == "app" else d.name
    return n if n in APPS else None


def installed(base, config_dir=None):
    """The apps on this machine, in APPS' order: the ones with BASE/<app>/app/config.env, and the calling app."""
    own = app_of(config_dir)
    return [n for n in APPS if n == own or (Path(base) / n / "app" / "config.env").is_file()]


def _inside(path, folder):
    path, folder = Path(path).resolve(), Path(folder).resolve()
    return path == folder or folder in path.parents


def _clear(folder, keep=()):
    """Delete what is in FOLDER, but never a path in KEEP: such a folder stays whole, with the folders that lead to it
    (their other contents go). A link is removed, never followed. Returns whether FOLDER is empty now."""
    folder = Path(folder)
    empty = True
    for child in sorted(folder.iterdir()):
        if child.is_symlink() or not child.is_dir():
            if any(_inside(k, child) for k in keep):  # a kept file, or a link to something kept
                empty = False
            else:
                child.unlink(missing_ok=True)
        elif any(Path(k).resolve() == child.resolve() for k in keep):
            empty = False
        elif any(_inside(k, child) for k in keep):
            if _clear(child, keep):
                child.rmdir()
            else:
                empty = False
        else:
            shutil.rmtree(child, ignore_errors=True)
            empty = empty and not child.exists()
    return empty


def _db_key(cfg, default_name=None):
    """(host, port, database) of an app's own MariaDB database, None when it has none (nothing set yet)."""
    if cfg.get("DB_TYPE", "mysql") not in ("mysql", "mariadb") or not cfg.get("DB_HOST"):
        return None
    name = cfg.get("DB_NAME") or default_name
    host = cfg["DB_HOST"].lower()
    return ("127.0.0.1" if host in ("localhost", "::1") else host, str(cfg.get("DB_PORT") or "3306"), name) if name else None


def _shared_key(cfg):
    host = (cfg.get("IOSUITE_DB_HOST") or cfg.get("DB_HOST") or "127.0.0.1").lower()
    return ("127.0.0.1" if host in ("localhost", "::1") else host, str(cfg.get("IOSUITE_DB_PORT") or cfg.get("DB_PORT") or "3306"),
            cfg.get("IOSUITE_DB_NAME") or "iosuite")


def removal_plan(name, base, caller_cfg=None, config_dir=None):
    """What removing NAME touches, without touching it: its folder, the data folder that stays (or goes with
    --delete-data), its database, and why the database may not be dropped (`db_kept`: the reason, or None)."""
    a = APPS[name]
    root = Path(base) / name
    target = root / "app"
    cfg = read_env_file(target / "config.env")
    data = Path(cfg.get("DATA_DIR") or (target / "data")).expanduser()
    if not data.is_absolute():
        data = target / data
    key = _db_key(cfg, name)
    kept = None
    if key:
        if not IDENT.match(key[2]):
            kept = "its name is not letters, digits and _ only"
        elif key == _shared_key(cfg) or (caller_cfg and key == _shared_key(caller_cfg)):
            kept = "it is the Shared ioSuite database"
        else:
            for other in installed(base, config_dir):
                if other == name:
                    continue
                ocfg = caller_cfg if other == app_of(config_dir) and caller_cfg is not None else read_env_file(Path(base) / other / "app" / "config.env")
                if _db_key(ocfg, other) == key:
                    kept = f"{APPS[other]['label']} uses it too"
                    break
    keep = []
    for setting, what in KEPT:
        if cfg.get(setting):
            where = Path(cfg[setting]).expanduser()
            keep.append((what, where if where.is_absolute() else target / where))
    return dict(name=name, label=a["label"], root=root, target=target, cfg=cfg, data=data, data_inside=_inside(data, root),
                db=key, db_kept=kept, keep=keep)


def launchd_label(name):
    """The login item setup.sh makes for NAME on a Mac: net.iothing.<name>.server (ioPix keeps its own)."""
    return APPS[name].get("launchd") or f"net.iothing.{name}.server"


def stop_service(name, target, log=print, run=subprocess.run):
    """Stop the app and take its service away: the systemd unit setup.sh wrote (only when it points at TARGET), or the
    login item on a Mac. Without either, the app was started by hand (run.sh) and the person stops it."""
    unit = Path(f"/etc/systemd/system/{name}.service")
    label = launchd_label(name)
    plist = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    if unit.is_file() and shutil.which("systemctl"):
        if str(target) not in unit.read_text(errors="replace"):
            log(f"  note: the service {name} runs from another folder, not {target}: left alone")
            return
        sudo = [] if os.geteuid() == 0 else ["sudo"]
        run(sudo + ["systemctl", "disable", "--now", name], capture_output=True)
        run(sudo + ["rm", "-f", str(unit)], capture_output=True)
        run(sudo + ["systemctl", "daemon-reload"], capture_output=True)
        run(sudo + ["systemctl", "reset-failed", name], capture_output=True)
        log(f"  stopped the service {name} and took it away")
    elif plist.is_file():
        run(["launchctl", "bootout", f"gui/{os.getuid()}/{label}"], capture_output=True)
        plist.unlink()
        log(f"  stopped the login item {label} and took it away")
    else:
        log(f"  no service for {APPS[name]['label']} here: if it runs from ./run.sh, stop it yourself")


def forget_app(name, log=print):
    """Out of the suite's list of apps (and its line on the Updates page), in the Shared ioSuite database the calling
    app's config.env names. The accounts' roles in the app stay: they count again when the app comes back."""
    try:
        from iosuite_shared import admin
        admin.forget_app(name)
        log(f"  taken out of the suite's list of apps: the other apps no longer show {APPS[name]['label']}")
    except Exception as exc:  # noqa: BLE001 - the app is gone from this machine whatever the database says
        log(f"  note: could not take {APPS[name]['label']} out of the suite's list of apps ({str(exc)[:160]}); a suite admin can, in Settings › Suite › Apps")


def _connect(h, o, u, w):
    import pymysql
    return pymysql.connect(host=h, port=int(o), user=u, password=w, connect_timeout=10, autocommit=True)


def _db_login(p, db_admin=None):
    """Who talks to the app's database server on a removal: the administrator when one was given, else the app's user."""
    if db_admin:
        return db_admin, os.environ.get("DB_ADMIN_PASSWORD", "")
    return p["cfg"].get("DB_USER", ""), p["cfg"].get("DB_PASSWORD", "")


def _my_addresses():
    """The names and addresses of this machine, as far as it can tell (loopback included)."""
    out = {"127.0.0.1", "::1", "localhost"}
    for n in (socket.gethostname, socket.getfqdn):
        try:
            out.add(n().lower())
        except OSError:
            pass
    try:
        out |= {i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None)}
    except OSError:
        pass
    try:  # the address the default route leaves from (nothing is sent)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            out.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        out |= set(subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=5).stdout.split())
    except (OSError, subprocess.SubprocessError):
        pass
    return out


def used_elsewhere(name, p, db_admin=None, connect=None, mine=None):
    """Why the app being removed looks to be running on another machine now (moved there), or None. Asked once its
    service here is stopped, so whatever still uses it is not this machine's:

      * the suite's list of apps (Shared ioSuite database) has it at an address inside the network (internal_url, which
        each app writes as it starts) that is not one of this machine's: the copy that started last is elsewhere;
      * its database has connections open (MariaDB's process list; the apps keep a few open while they run).

    Neither sees everything: an app elsewhere that is stopped right now, an internal address on loopback (behind a proxy
    on its own server, which says nothing about which server), or connections of another database user when the
    login used here may not see them (MariaDB shows a user its own, and an administrator all of them)."""
    mine = _my_addresses() if mine is None else mine
    label = APPS[name]["label"]
    try:
        from iosuite_shared import suite
        r = suite.get(name) or {}
    except Exception:  # noqa: BLE001 - no Shared ioSuite database to ask: the other signal still counts
        r = {}
    url = r.get("internalUrl") or ""
    host = (urlsplit(url).hostname or "").lower() if url else ""
    if host and host not in mine:
        return f"the suite's list of apps has {label} at {url}, which is not this machine"
    if p.get("db"):
        h, o, dbname = p["db"]
        try:
            conn = (connect or _connect)(h, o, *_db_login(p, db_admin))
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT HOST FROM information_schema.PROCESSLIST WHERE DB = %s AND ID != CONNECTION_ID()", (dbname,))
                    hosts = sorted({str(row[0] if not isinstance(row, dict) else row["HOST"]).rsplit(":", 1)[0] for row in cur.fetchall()})
            finally:
                conn.close()
        except Exception:  # noqa: BLE001 - the server does not answer this login: nothing to tell
            hosts = []
        if hosts:
            return f"its database {dbname} is in use from {', '.join(hosts)} although {label} is stopped here"
    return None


def drop_database(p, db_admin=None, connect=None, log=print):
    """--delete-data: drop the app's own database, as the administrator when one was given, else as the app's user."""
    host, port, dbname = p["db"]
    user, password = _db_login(p, db_admin)
    try:
        conn = (connect or _connect)(host, port, user, password)
        try:
            with conn.cursor() as cur:
                cur.execute(f"DROP DATABASE IF EXISTS `{dbname}`")
        finally:
            conn.close()
        log(f"  dropped the database {dbname} on {host}:{port}")
        return True
    except Exception as exc:  # noqa: BLE001
        log(f"  could not drop the database {dbname} on {host}:{port} as {user} ({str(exc)[:160]}): it is still there; "
            f"give a MariaDB administrator with --db-admin, or drop it yourself")
        return False


def _delegate(other, name, base, delete_data, db_admin):
    """`remove NAME`, run by the app OTHER on this machine."""
    home = Path(base) / other / "app"
    cmd = [str(home / ".venv" / "bin" / "iosuite-shared"), "--config", str(home), "remove", name, "--into", str(base)]
    cmd += (["--delete-data"] if delete_data else []) + (["--db-admin", db_admin] if db_admin else [])
    return subprocess.run(cmd).returncode


def remove(names, config_dir, base=None, delete_data=False, db_admin=None, stopper=stop_service, forgetter=forget_app, dropper=drop_database,
           delegate=_delegate, log=print, checker=None):
    """Remove every app in NAMES from this machine; returns the names where something could not be done.
    The database and the data stay unless DELETE_DATA."""
    cfg = read_env_file(Path(config_dir) / "config.env") if config_dir else {}
    base = Path(base) if base else base_dir(config_dir or os.getcwd())
    own = app_of(config_dir)
    failed = []
    for n in sorted(names, key=lambda x: x == own):  # the app this runs from goes last
        a = APPS[n]
        p = removal_plan(n, base, caller_cfg=cfg, config_dir=config_dir)
        say(f"Removing {a['label']} from {p['target']}")
        if n == own or (config_dir and p["target"].resolve() == Path(config_dir).resolve()):
            # the app this runs from: another app that stays does it (this one's Python environment is among what goes)
            other = next((o for o in installed(base, config_dir) if o != own and o not in names
                          and (Path(base) / o / "app" / ".venv" / "bin" / "iosuite-shared").is_file()), None)
            if not other:
                log(f"  {a['label']} is the last app here that can run this: not removed. To take ioSuite off this server altogether, "
                    f"stop its service and delete {p['root']} yourself")
                failed.append(n)
            elif delegate(other, n, base, delete_data, db_admin) != 0:
                failed.append(n)
            continue
        if not (p["target"] / "config.env").is_file():
            log(f"  {a['label']} is not installed here: nothing to do")
            continue
        stopper(n, p["target"], log=log)
        # moved to another machine (started there on the same database)? Then it stays in the suite's list and its
        # database is never dropped from here
        elsewhere = (checker or used_elsewhere)(n, p, db_admin=db_admin)
        if elsewhere:
            log(f"  {a['label']} looks to be running on another machine: {elsewhere}")
            log("  so it stays in the suite's list of apps" + (" and its database is kept" if delete_data and p["db"] else ""))
            p["db_kept"] = p["db_kept"] or "it is in use on another machine"
        else:
            forgetter(n, log=log)
        # the program files: everything in the app's folder but the data folder and what is never deleted (KEPT)
        kept = [where for _, where in p["keep"]]
        _clear(p["target"], [p["data"]] + kept)
        log(f"  deleted the program files in {p['target']}")
        if delete_data:
            if p["db"] and not p["db_kept"]:
                if not dropper(p, db_admin=db_admin, log=log):
                    failed.append(n)
            elif p["db"]:
                log(f"  kept the database {p['db'][2]}: {p['db_kept']}")
            # the data folder goes when it is under the app's own folder; one elsewhere is the person's to delete
            folder = p["root"] if p["data_inside"] else p["target"]
            if _clear(folder, kept):
                folder.rmdir()
            if p["data_inside"]:
                log(f"  deleted {p['root']} with the app's data folder" if not folder.exists() else
                    f"  deleted the app's data folder; {p['root']} stays for what is never deleted")
            else:
                log(f"  kept the data folder {p['data']}: it is outside {p['root']}, delete it yourself if you want it gone")
        else:
            if p["db"]:
                log(f"  kept the database {p['db'][2]} on {p['db'][0]}:{p['db'][1]}")
            if p["data"].exists():
                log(f"  kept the data folder {p['data']}")
            log(f"  adding {a['label']} again later finds them")
        for what, where in p["keep"]:
            log(f"  the {what} in {where} are never touched" if what.endswith("s") else f"  the {what} in {where} is never touched")
    return failed


def reconfigure(names, config_dir, base=None, runner=None, log=print):
    """Each app's own setup.sh again, in its folder, asking its questions with the current answers as the defaults
    (`--also none`: without the list of apps at its end). Returns the names that failed."""
    base = Path(base) if base else base_dir(config_dir or os.getcwd())
    own = app_of(config_dir)
    runner = runner or (lambda folder: subprocess.run(["sh", "./setup.sh", "--also", "none"], cwd=str(folder)).returncode)
    failed = []
    for n in names:
        folder = Path(config_dir) if n == own and config_dir else Path(base) / n / "app"
        say(f"Reconfiguring {APPS[n]['label']} in {folder}")
        if not (folder / "config.env").is_file() or not (folder / "setup.sh").is_file():
            log(f"  {APPS[n]['label']} is not installed here: add it first")
            failed.append(n)
            continue
        rc = runner(folder)
        if rc != 0:
            log(f"  {APPS[n]['label']}'s setup.sh failed (exit {rc}); its settings are in {folder}/config.env")
            failed.append(n)
    return failed


# ---------------------------------------------------------------------------------------------------------------------
# how the apps are reached: each on its own port, all at the start page's address, or behind a reverse proxy here

# mode -> (in a few words, the whole line of the menu)
REACH = {
    "ports": ("each app on its own port", "Each app on its own port, from anywhere on the network (http://this-server:8620 for ioCalendar, and so on)"),
    "one": ("one address, the start page answers for every app",
            "One address: the start page answers for every app (http://this-server:8630/calendar/, …/notes/). The other apps listen on this machine only"),
    "one-proxy": ("one address, behind a reverse proxy on this server",
                  "One address behind a reverse proxy on this server (Caddy, nginx…: HTTPS): as 2, and the start page listens on this machine only too"),
    "proxy": ("a reverse proxy on this server reaches each app",
              "A reverse proxy on this server reaches each app on its own port: every app listens on this machine only"),
}
LOCAL = "127.0.0.1"
ADDRESS = re.compile(r"^https?://[^/\s?#]+(/[^\s?#]*)?$")


def folder_of(name):
    from iosuite_shared import suite
    return suite.folder_of(name)


def write_env_file(path, changes):
    """Set (or, with None, take out) KEY=VALUE lines of a config.env; every other line stays as it is, and so do the
    file's owner and mode (a new file is the owner's alone: it will hold passwords)."""
    p = Path(path)
    new = not p.is_file()
    lines = [] if new else p.read_text(encoding="utf-8", errors="replace").splitlines()
    keep = [ln for ln in lines if ln.lstrip().startswith("#") or "=" not in ln or ln.split("=", 1)[0].strip() not in changes]
    keep += [f"{k}={v}" for k, v in changes.items() if v is not None]
    if new:
        p.touch(mode=0o600)
    p.write_text("\n".join(keep) + "\n", encoding="utf-8")


def _is_local(value):
    hosts = [h.strip("[]").lower() for h in re.split(r"[,\s]+", value or "") if h]
    return bool(hosts) and all(h in ("127.0.0.1", "localhost", "::1") for h in hosts)


def _local_only(mode, name):
    """Whether the app listens on this machine only in that mode."""
    return mode in ("proxy", "one-proxy") or (mode == "one" and name != "iostart")


def _local_env(name, cfg):
    """What makes an app listen on this machine only. An address the person named for HOST is kept as HOST_BEFORE,
    for the way back (_network_env). ioContact's LDAP directory listens where the web app does unless told
    otherwise: it is not HTTP, no proxy and no start page passes it on, so it stays where it was."""
    out = {"HOST": LOCAL}
    if cfg.get("HOST") and not _is_local(cfg["HOST"]) and "HOST_BEFORE" not in cfg:  # no line (every address) needs no note
        out["HOST_BEFORE"] = cfg["HOST"]
    if name == "iocontact" and not cfg.get("LDAP_HOST") and cfg.get("LDAP_PORT") != "0" and not _is_local(cfg.get("HOST")):
        out["LDAP_HOST"] = cfg.get("HOST") or "0.0.0.0"
    return out


def _network_env(name, cfg):
    """The way back to the network: HOST as it was before _local_env (no line: every address), and ioContact's
    LDAP directory pin taken out when it only kept the directory where the web app now listens again."""
    out = {}
    if cfg.get("HOST_BEFORE"):
        out["HOST"], out["HOST_BEFORE"] = cfg["HOST_BEFORE"], None
    elif _is_local(cfg.get("HOST")):  # an address the person named (one of several on this machine) stays
        out["HOST"] = None
    if name == "iocontact" and cfg.get("LDAP_HOST") in ("0.0.0.0", cfg.get("HOST_BEFORE") or "0.0.0.0"):
        out["LDAP_HOST"] = None
    return out


REACH_FILE = "iosuite-reach.env"  # in BASE: how the apps on this machine are reached, and the proxy's address


def stored_reach(base):
    return read_env_file(Path(base) / REACH_FILE) if base else {}


def _store_reach(base, mode, address):
    """Kept for an app added later: with proxy, its folder of that address (shared_address)."""
    p = Path(base) / REACH_FILE
    try:
        if mode == "proxy" and address:
            write_env_file(p, {"MODE": mode, "ADDRESS": address})
        elif p.is_file():
            p.unlink()
    except OSError:
        pass  # a base this cannot write (the tests' own folder, a read-only mount): inferred from config.env then


def _switch():
    """The suite's one-address switch, from the Shared ioSuite database the calling app's config.env names; off
    when it cannot be read."""
    try:
        from iosuite_shared import db, suite
        return db.get_setting(suite.ONE_ADDRESS, "", "") == "1"
    except Exception:  # noqa: BLE001 - no database to ask (yet)
        return False


def _set_switch(on):
    from iosuite_shared import suite
    suite.set_one_address(on)


def _folder(base, config_dir, name):
    return Path(config_dir) if name == app_of(config_dir) and config_dir else Path(base) / name / "app"


def reach_now(base, config_dir, switch=None):
    """How the apps here are reached now (a key of REACH), from the switch and each app's HOST."""
    here = installed(base, config_dir)
    local = {n: _is_local(read_env_file(_folder(base, config_dir, n) / "config.env").get("HOST")) for n in here}
    if (switch or _switch)() and "iostart" in here:
        return "one-proxy" if local["iostart"] else "one"
    return "proxy" if here and all(local.values()) else "ports"


def shared_address(base, config_dir):
    """The one address a proxy serves every app in a folder of (the start page's PUBLIC_URL), when another app here
    is set up as a folder of it; None otherwise (a name per app, or no public address)."""
    kept = stored_reach(base)
    if kept.get("MODE") == "proxy" and kept.get("ADDRESS"):
        return kept["ADDRESS"].rstrip("/")
    here = installed(base, config_dir)
    if "iostart" not in here:
        return None
    url = (read_env_file(_folder(base, config_dir, "iostart") / "config.env").get("PUBLIC_URL") or "").rstrip("/")
    if not url:
        return None
    for n in here:
        if n != "iostart" and (read_env_file(_folder(base, config_dir, n) / "config.env").get("PUBLIC_URL") or "").rstrip("/") == f"{url}/{folder_of(n)}":
            return url
    return None


def reach_plan(mode, base, config_dir, address=None):
    """[(app, its folder, {KEY: value, or None to take the line out})] for the apps whose config.env changes."""
    out = []
    was = shared_address(base, config_dir) if mode != "proxy" else None  # the folders a proxy served until now
    for n in installed(base, config_dir):
        folder = _folder(base, config_dir, n)
        cfg = read_env_file(folder / "config.env")
        ch = {}
        if _local_only(mode, n):
            ch.update(_local_env(n, cfg))
        else:
            ch.update(_network_env(n, cfg))
        if address and n == "iostart":
            ch["PUBLIC_URL"] = address
        elif address and mode == "proxy":
            ch["PUBLIC_URL"] = f"{address}/{folder_of(n)}"
        elif was and n != "iostart" and (cfg.get("PUBLIC_URL") or "").rstrip("/") == f"{was}/{folder_of(n)}":
            ch["PUBLIC_URL"] = None  # only its folder of the proxy's address: no longer how it is reached
        ch = {k: v for k, v in ch.items() if (cfg.get(k) or None) != v}
        if ch:
            out.append((n, folder, ch))
    return out


def restart_service(name, target, log=print, run=subprocess.run):
    """Start the app again so it reads its config.env: its systemd unit (only when it points at TARGET) or its login
    item on a Mac. Without either the app was started by hand, and the person does it."""
    unit = Path(f"/etc/systemd/system/{name}.service")
    label = launchd_label(name)
    plist = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    if unit.is_file() and shutil.which("systemctl") and str(target) in unit.read_text(errors="replace"):
        sudo = [] if os.geteuid() == 0 else ["sudo"]
        if run(sudo + ["systemctl", "restart", name], capture_output=True).returncode == 0:
            log(f"  restarted the service {name}")
            return True
        log(f"  could not restart the service {name}: journalctl -u {name} -n 50")
        return False
    if plist.is_file():
        run(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{label}"], capture_output=True)
        log(f"  restarted the login item {label}")
        return True
    log(f"  {APPS[name]['label']} is started by hand here: stop it and start it again (./run.sh) for this to count")
    return True


def set_reach(mode, config_dir, base=None, address=None, switcher=None, restarter=restart_service, log=print):
    """Make every app here reached that way (see the module's text). Returns True when everything was done."""
    base = Path(base) if base else base_dir(config_dir or os.getcwd())
    address = (address or "").rstrip("/") or None
    here = installed(base, config_dir)
    say(f"How the apps are reached: {REACH[mode][0]}")
    if mode in ("one", "one-proxy") and "iostart" not in here:
        log("  one address needs the start page (ioStart) on this server: it is the app that answers at the address. Add it first")
        return False
    if address and not ADDRESS.match(address):
        log(f"  {address}: not an address (https://home.example.com)")
        return False
    one = mode in ("one", "one-proxy")
    switcher = switcher or _set_switch
    ok = True
    if one:  # first: the start page passes the folders on before the apps stop answering the network themselves
        try:
            switcher(True)
            log("  the suite's one address is on (Settings › Global settings › Apps shows it)")
        except Exception as exc:  # noqa: BLE001
            log(f"  could not turn the suite's one address on in the Shared ioSuite database ({str(exc)[:160]}): nothing changed")
            return False
    for n, folder, ch in reach_plan(mode, base, config_dir, address):
        write_env_file(folder / "config.env", ch)
        what = ", ".join(f"{k}={v}" if v is not None else f"{k} taken out" for k, v in ch.items())
        log(f"  {APPS[n]['label']}: {what}")
        if "LDAP_HOST" in ch and ch["LDAP_HOST"]:
            log("    its LDAP directory is not HTTP and goes on listening where it did (LDAP_HOST in its config.env)")
        ok = restarter(n, folder, log=log) and ok
    if not one:
        try:
            switcher(False)
        except Exception as exc:  # noqa: BLE001
            log(f"  note: could not read or turn off the suite's one address in the Shared ioSuite database ({str(exc)[:160]}); "
                f"a suite admin can, in Settings › Global settings › Apps")
            ok = False
    if mode == "proxy":
        _store_reach(base, mode, address or shared_address(base, config_dir))
    else:
        _store_reach(base, mode, None)
    for line in _reach_notes(mode, base, config_dir, address):
        log(line)
    return ok


def _reach_notes(mode, base, config_dir, address):
    """What the person does next, and a Caddyfile for the two ways with a reverse proxy."""
    here = installed(base, config_dir)
    port = {n: read_env_file(_folder(base, config_dir, n) / "config.env").get("PORT") or APPS[n]["port"] for n in here}
    others = [n for n in here if n != "iostart"]
    start = address or (read_env_file(_folder(base, config_dir, "iostart") / "config.env").get("PUBLIC_URL") or "").rstrip("/") if "iostart" in here else address
    host = re.sub(r"^https?://", "", address or "").split("/")[0]
    out = [""]
    if mode == "ports":
        out.append("  Every app answers on its own port: " + ", ".join(f"{APPS[n]['label']} {port[n]}" for n in here))
    elif mode == "one":
        at = start or f"http://<this server>:{port['iostart']}"
        out.append(f"  The suite is at {at}: " + ", ".join(f"{at}/{folder_of(n)}/" for n in others[:3]) + (" and so on" if len(others) > 3 else ""))
        out.append("  Phones and apps that sync calendars, contacts, tasks or bookmarks need the new address of their account.")
    elif mode == "one-proxy":
        out.append(f"  Point the reverse proxy at 127.0.0.1:{port['iostart']} (the start page): it passes every app's folder on. For Caddy:")
        out += ["", f"      {host or 'home.example.com'} {{", f"          reverse_proxy 127.0.0.1:{port['iostart']}", "      }"]
        if not start:
            out += ["", "  Give the start page its address: run this again with --address https://…, or r and its number in the list."]
    else:
        if address and "iostart" in here:
            out += ["  For Caddy, one name with a folder per app:", "", f"      {host} {{"]
            for n in others:
                f = folder_of(n)
                out += [f"          redir /{f} /{f}/", f"          handle_path /{f}/* {{", f"              reverse_proxy 127.0.0.1:{port[n]}", "          }"]
            for wk, n in (("caldav", "iocalendar"), ("carddav", "iocontact")):
                if n in here:
                    out.append(f"          redir /.well-known/{wk} /{folder_of(n)}/dav/ 301")
            out += ["          handle {", f"              reverse_proxy 127.0.0.1:{port['iostart']}", "          }", "      }"]
        else:
            out.append("  Point the reverse proxy at each app: " + ", ".join(f"{APPS[n]['label']} 127.0.0.1:{port[n]}" for n in here))
            out.append("  Each app's public address is its own setting: r and its number in the list, or --reconfigure APP.")
    if mode in ("proxy", "one-proxy"):
        out.append("  The documentation has the same for nginx and the rest: Run › Reverse proxy and HTTPS.")
    return out


def ask_reach(base, config_dir, now, ask=input, log=print):
    """The menu: (mode, address) or None when the person leaves it as it is."""
    modes = list(REACH)
    log("\nHow the apps are reached:")
    for i, m in enumerate(modes, 1):
        log(f"  {i}  {REACH[m][1]}{'  (now)' if m == now else ''}")
    try:
        ans = ask("Number (Enter: leave it as it is): ").strip().lower()
        mode = modes[int(ans) - 1] if ans.isdigit() and 1 <= int(ans) <= len(modes) else ans if ans in REACH else None
        if not mode:
            return None
        address = ""
        if mode != "ports":
            q = ("The one address the proxy serves every app in a folder of, e.g. https://home.example.com (Enter: each app has a name of its own, or leave them as they are): "
                 if mode == "proxy" else "The address the suite is at, e.g. https://home.example.com (Enter: leave the start page's as it is): ")
            address = ask(q).strip().rstrip("/")
            while address and not ADDRESS.match(address):
                address = ask("An address starts with http:// or https:// (Enter: leave it): ").strip().rstrip("/")
    except EOFError:
        return None
    return mode, address or None


# ---------------------------------------------------------------------------------------------------------------------
# `apps`: what is here; tick and untick

def _table(base, config_dir, want=None, redo=()):
    here = installed(base, config_dir)
    own = app_of(config_dir)
    lines = []
    for i, n in enumerate(APPS, 1):
        on = n in want if want is not None else n in here
        note = "this app" if n == own else ("installed" if n in here else "")
        if want is not None and on != (n in here):
            note = "to add" if on else "to remove"
        elif n in redo:
            note = "to reconfigure"
        folder = Path(config_dir) if n == own and config_dir else Path(base) / n / "app"
        port = read_env_file(folder / "config.env").get("PORT") or APPS[n]["port"]  # the one it was given, else its usual one
        lines.append(f"  {i:>2} [{'x' if on else ' '}] {APPS[n]['label']:<11} {n:<11} port {port}  {note}".rstrip())
    return lines


def choose(base, config_dir, ask=input, log=print, reach=None):
    """The checklist: returns (add, remove, delete_data, reconfigure), or None when the person changes nothing or backs out.
    With `reach` (a dict), `a` asks how the apps are reached and leaves the answer there as mode and address."""
    here = installed(base, config_dir)
    want = list(here)
    redo = []
    names = list(APPS)
    now = reach_now(base, config_dir) if reach is not None else None
    while True:
        log("")
        for line in _table(base, config_dir, want, redo):
            log(line)
        if reach is not None:
            log(f"  Reached: {REACH[now][0]}" + (f"  (to change to: {REACH[reach['mode']][0]})" if reach.get("mode") and reach["mode"] != now else ""))
        try:
            ans = ask("Numbers or names to tick or untick (e.g. 3 5), r and a number to change an installed app's settings (e.g. r2), "
                      + ("a to change how the apps are reached, " if reach is not None else "") + "Enter when it is right: ").strip()
        except EOFError:
            return None
        if not ans:
            break
        if reach is not None and ans.lower() == "a":
            picked = ask_reach(base, config_dir, now, ask=ask, log=log)
            if picked and picked[0] in ("one", "one-proxy") and "iostart" not in want:
                log("  one address needs the start page: tick ioStart first")
            elif picked:
                reach.update(mode=picked[0], address=picked[1])
            continue
        for tok in re.sub(r"\b[rR]\s+(?=\S)", "r", ans.replace(",", " ")).split():
            again = tok[:1] in "rR" and tok.lower() not in APPS and len(tok) > 1
            if again:
                tok = tok[1:]
            n = names[int(tok) - 1] if tok.isdigit() and 1 <= int(tok) <= len(names) else tok.lower()
            if n not in APPS:
                log(f"  {tok}: not one of the apps")
            elif again:
                if n not in here:
                    log(f"  {APPS[n]['label']} is not installed here: tick it to add it")
                elif n in redo:
                    redo.remove(n)
                else:
                    redo.append(n)
            elif n in want:
                want.remove(n)
            else:
                want.append(n)
    add = [n for n in names if n in want and n not in here]
    rem = [n for n in names if n in here and n not in want]
    redo = [n for n in names if n in redo and n not in rem]
    if reach and reach.get("mode") == now and not reach.get("address"):
        reach.clear()
    if not add and not rem and not redo and not reach:
        log("nothing to change")
        return None
    delete = False
    if add:
        log(f"\nTo add: {', '.join(APPS[n]['label'] for n in add)}")
    if redo:
        log(f"\nTo reconfigure: {', '.join(APPS[n]['label'] for n in redo)} (its own questions again, the current answers as the defaults)")
    if reach:
        log(f"\nHow the apps are reached: {REACH[reach['mode']][0]}" + (f", at {reach['address']}" if reach.get("address") else "")
            + " (the apps whose settings change are restarted)")
    if rem:
        log(f"\nTo remove: {', '.join(APPS[n]['label'] for n in rem)}")
        log("Removing stops the app and deletes its program files. Its database and its data stay, so adding it again later brings everything back.")
        try:
            delete = ask("Delete the database and the data of the removed apps too? This cannot be undone. Type DELETE to do it, Enter to keep them: ").strip() == "DELETE"
            ok = ask("Go ahead? [y/N]: " if delete else "Go ahead? [Y/n]: ").strip().lower()
        except EOFError:
            return None
        if ok not in (("y", "yes") if delete else ("", "y", "yes")):
            log("nothing changed")
            return None
    return add, rem, delete, redo


def add_parser(sub):
    p = sub.add_parser("install", help="install other apps of the suite here, sharing the answers of the app in --config")
    p.add_argument("apps", nargs="+", help="iostart, iopix, ionote, iocalendar, iocontact, iotask, iorecipe, iothings, iomoney, iohealth, iodns, iobackup (comma-separated or several), or all")
    _install_options(p)
    r = sub.add_parser("remove", help="remove apps of the suite from this machine; their databases and data stay unless --delete-data")
    r.add_argument("apps", nargs="+", help="the apps to remove (comma-separated or several)")
    r.add_argument("--into", default=None, help="the folder the apps are under (default: beside the calling app)")
    r.add_argument("--delete-data", action="store_true", help="also drop each app's own database and delete its data folder (cannot be undone)")
    r.add_argument("--db-admin", default=None, help="a MariaDB administrator (password from DB_ADMIN_PASSWORD) to drop the databases with --delete-data")
    c = sub.add_parser("apps", help="show the apps of the suite on this machine; tick and untick them, or --add / --remove")
    c.add_argument("--add", default=None, help="apps to install (comma-separated, or all)")
    c.add_argument("--remove", default=None, help="apps to remove; their databases and data stay unless --delete-data")
    c.add_argument("--delete-data", action="store_true", help="with --remove: also drop each app's own database and delete its data folder (cannot be undone)")
    c.add_argument("--reconfigure", default=None, help="installed apps whose own setup questions are asked again (the current answers are the defaults)")
    c.add_argument("--list", action="store_true", help="only show what is installed")
    c.add_argument("--reach", choices=list(REACH), default=None,
                   help="how every app here is reached: " + "; ".join(f"{k}: {v[0]}" for k, v in REACH.items()))
    c.add_argument("--address", default=None, help="with --reach: the address the suite is at (https://home.example.com): the start page's public "
                                                    "address, and with --reach proxy every other app's folder of it too")
    _install_options(c)
    return p


def _install_options(p):
    p.add_argument("--into", default=None, help="the folder the apps go under, each as <folder>/<app>/app (default: beside the calling app, e.g. /opt)")
    p.add_argument("--admin", default=None, help="make this account an admin of every app too (its password from ADMIN_PASSWORD)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--service", dest="service", action="store_true", default=None, help="install and start each app's systemd service")
    g.add_argument("--no-service", dest="service", action="store_false", help="only install; start each with its run.sh")
    p.add_argument("--photos", default=None, help=f"ioPix: the folder with the photos (default {DEFAULT_PHOTOS})")
    p.add_argument("--from", dest="from_app", default=None, help="the app that is calling (never reinstalled, never removed)")
    p.add_argument("--db-admin", default=None, help="a MariaDB administrator (password from DB_ADMIN_PASSWORD): the companions' databases are created for the app user")
    p.add_argument("--yes", action="store_true", help="no questions: each app added takes the answers of the apps already here and its own defaults "
                                                      "(without it, and with somebody at the keyboard, each app's own setup questions are asked)")


def main(a):
    if a.cmd == "remove":
        return _report([], remove(parse_apps(a.apps), a.config, base=a.into, delete_data=a.delete_data, db_admin=a.db_admin))
    if a.cmd == "apps":
        return main_apps(a)
    names = parse_apps(a.apps)
    return _report(install(names, a.config, base=a.into, admin=a.admin, service=a.service, photos=a.photos, from_app=a.from_app, db_admin=a.db_admin,
                           ask=_asks(a)), [])


def _asks(a):
    """Whether each app added asks its own setup questions: somebody is at the keyboard and --yes was not given."""
    return not a.yes and sys.stdin.isatty()


def _report(not_installed, not_removed):
    if not_installed:
        print(f"\nerror: not installed: {', '.join(not_installed)}", file=sys.stderr)
    if not_removed:
        print(f"\nerror: not (fully) removed: {', '.join(not_removed)}", file=sys.stderr)
    return 1 if not_installed or not_removed else 0


def main_apps(a):
    base = Path(a.into) if a.into else base_dir(a.config or os.getcwd())
    add = parse_apps(a.add) if a.add else []
    rem = parse_apps(a.remove) if a.remove else []
    redo = parse_apps(a.reconfigure) if a.reconfigure else []
    delete = a.delete_data
    both = [n for n in add + redo if n in rem]
    if both:
        raise SystemExit(f"error: {', '.join(both)}: to remove and to add or reconfigure")
    if a.address and not a.reach:
        raise SystemExit("error: --address goes with --reach (ports, one, one-proxy or proxy)")
    reach = {"mode": a.reach, "address": a.address} if a.reach else {}
    if a.add is None and a.remove is None and a.reconfigure is None and not a.reach:
        say(f"The apps of the suite on this server (under {base})")
        if a.list or not sys.stdin.isatty():
            for line in _table(base, a.config):
                print(line)
            print(f"  Reached: {REACH[reach_now(base, a.config)][0]}")
            return 0
        picked = choose(base, a.config, reach=reach)
        if not picked:
            return 0
        add, rem, delete, redo = picked
    # what set_reach would refuse is refused before anything is installed or removed (an app installed for a way
    # that is then refused would listen on this machine only, with nothing to reach it through)
    after = (set(installed(base, a.config)) | set(add)) - set(rem)
    if reach.get("mode") in ("one", "one-proxy") and "iostart" not in after:
        raise SystemExit("error: one address needs the start page (ioStart) on this server: add it (--add iostart), or keep it")
    if reach.get("address") and not ADDRESS.match(reach["address"].rstrip("/")):
        raise SystemExit(f"error: {reach['address']}: not an address (https://home.example.com)")
    if "iostart" in rem and not reach.get("mode") and reach_now(base, a.config) in ("one", "one-proxy"):
        say("The start page answers at the one address: every app goes back on its own port before it is removed")
        reach = {"mode": "ports", "address": None}
        if not set_reach("ports", a.config, base=base):
            print("\nerror: the apps could not be put back on their own port; ioStart was not removed", file=sys.stderr)
            return 1
        reach = {}  # done
    own = app_of(a.config)
    not_removed = remove([n for n in rem if n != own], a.config, base=base, delete_data=delete, db_admin=a.db_admin) if rem else []
    service = a.service
    if service is None and own and Path(f"/etc/systemd/system/{own}.service").is_file():
        service = True  # the app this runs from is a service: so are the ones added beside it
    not_installed = install(add, a.config, base=base, admin=a.admin, service=service, photos=a.photos,
                            from_app=a.from_app or app_of(a.config), db_admin=a.db_admin, reach=reach.get("mode"), ask=_asks(a)) if add else []
    not_redone = reconfigure(redo, a.config, base=base) if redo else []
    reached = set_reach(reach["mode"], a.config, base=base, address=reach.get("address")) if reach.get("mode") else True
    if own in rem:  # last: another app that is here removes this one
        not_removed += remove([own], a.config, base=base, delete_data=delete, db_admin=a.db_admin)
    if not_redone:
        print(f"\nerror: not reconfigured: {', '.join(not_redone)}", file=sys.stderr)
    if not reached:
        print("\nerror: how the apps are reached was not (fully) changed; see the lines above", file=sys.stderr)
    return 1 if not_redone or not reached else _report(not_installed, not_removed)
