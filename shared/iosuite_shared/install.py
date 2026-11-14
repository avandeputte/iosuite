"""`iosuite-shared install APP...`: put other apps of the suite on this machine, beside the one that is already here,
without asking the shared questions again.

Every app's setup.sh ends with "Also install other apps of the suite here?" (or takes `--also APP,APP`). The answer
comes here: with the calling app's config.env (`--config FOLDER`) this reads the answers that are the same for every
app and hands them to each companion's own setup.sh, which runs unattended (`--yes`):

  * the app database server: DB_HOST, DB_PORT, DB_USER and DB_PASSWORD are reused, each app gets its own database
    name (iostart -> suite, iocalendar -> calendar, ...; the app creates it when the user may);
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
stay as they are), never a database another app here uses, never the photos (ioPix) or the backups (ioBackup). The
app this runs from is removed by another app that stays; the last app here is not removed.
"""
import atexit
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# the one repository of the suite: a folder per app, the shared library in shared/
REPO = "avandeputte/iosuite"
# name -> how to set it up (its folder in the repository has the same name). `db` is the app's default database name; `env` the prefix of the environment
# variables its setup.sh reads the secrets from (PFX_DB, PFX_SUITE_DB, PFX_ADMIN).
APPS = {
    "iostart": dict(label="ioStart", db="suite", port=8630, env="IOSTART"),
    "iocalendar": dict(label="ioCalendar", db="calendar", port=8620, env="IOCALENDAR"),
    "iocontact": dict(label="ioContact", db="contacts", port=8640, env="IOCONTACT"),
    "ionote": dict(label="ioNote", db="notes", port=8610, env="IONOTE", data=True,
                    extra=["--features", "none"], launchd="net.iothing.ionote.server"),
    "iohealth": dict(label="ioHealth", db="health", port=8650, env="IOHEALTH"),
    "iotask": dict(label="ioTask", db="tasks", port=8670, env="IOTASK"),
    "iodns": dict(label="ioDNS", db="dns", port=8660, env="IODNS"),
    "iobackup": dict(label="ioBackup", db="backup", port=8680, env="IOBACKUP"),
    "iorecipe": dict(label="ioRecipe", db="recipe", port=8690, env="IORECIPE"),
    "iopix": dict(label="ioPix", db="iopix", port=8600, env="IOPIX", data=True,
                  extra=["--no-digikam", "--features", "none"], photos=True, launchd="com.iopix"),
}
DEFAULT_PHOTOS = "/library/photos"
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
    of its own (ioNote on SQLite, ioPix set up from its web page) lends the Shared ioSuite database's server and
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
    """/opt/iosuite/app -> /opt (the companions go to /opt/<app>/app); /srv/iosuite -> /srv."""
    d = Path(config_dir).resolve()
    return d.parent.parent if d.name == "app" else d.parent


def plan(names, cfg, base, admin=None, service=None, photos=None, from_app=None):
    """One entry per app: where it goes, the setup.sh arguments and the environment with the secrets."""
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
        env = {f"{a['env']}_DB": dsn(a_host, a_port, a["db"], a_user, a_pw), f"{a['env']}_SUITE_DB": ans["suite_db"]}
        if admin:
            env[f"{a['env']}_ADMIN"] = f"{admin}:{os.environ.get('ADMIN_PASSWORD', '')}"
        else:
            args.append("--no-admin")
        out.append(dict(name=n, label=a["label"], target=target, args=args, env=env, port=a["port"]))
    return out


def prepare_local_databases(entries, cfg, log=print):
    """A MariaDB on this machine (DB_HOST loopback, as `setup.sh --db local` of ioPix or a Proxmox container with its own
    server make) usually grants the app's user its own database only; as root, over the socket, give that user each
    companion's database too, so their setup.sh can create the tables. Elsewhere nothing is done: the person's user
    needs rights on those names, as the question says."""
    host = (cfg.get("DB_HOST") or "").lower()
    if host not in ("127.0.0.1", "localhost", "::1") or not cfg.get("DB_USER") or os.geteuid() != 0 or not shutil.which("mariadb"):
        return
    user = cfg["DB_USER"].replace("'", "''")
    sql = "".join(f"CREATE DATABASE IF NOT EXISTS `{APPS[e['name']]['db']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
                  f"GRANT ALL PRIVILEGES ON `{APPS[e['name']]['db']}`.* TO '{user}'@'localhost', '{user}'@'127.0.0.1';\n" for e in entries) + "FLUSH PRIVILEGES;\n"
    try:
        r = subprocess.run(["mariadb"], input=sql, text=True, capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log(f"  note: could not prepare the databases on the local MariaDB ({exc}); each app creates its own when {cfg['DB_USER']} may")
        return
    if r.returncode == 0:
        log(f"  local MariaDB: the databases {', '.join(APPS[e['name']]['db'] for e in entries)} belong to {cfg['DB_USER']} too")
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


def install(names, config_dir, base=None, admin=None, service=None, photos=None, from_app=None, db_admin=None, fetcher=fetch, runner=run_setup, log=print):
    """Install every app in NAMES; returns the names that failed (empty when all went well)."""
    cfg = read_env_file(Path(config_dir) / "config.env") if config_dir else {}
    base = Path(base) if base else base_dir(config_dir or os.getcwd())
    entries = plan(names, cfg, base, admin=admin, service=service, photos=photos, from_app=from_app)
    if not entries:
        log("nothing to install")
        return []
    if any(APPS[e["name"]].get("photos") for e in entries):
        p = Path(photos or DEFAULT_PHOTOS)
        if not p.is_dir():
            p.mkdir(parents=True, exist_ok=True)
            log(f"  made the photos folder {p}: mount or copy your photos there (ioPix's Settings can add more folders)")
    fresh = [e for e in entries if not (e["target"] / "config.env").exists()]
    if db_admin and fresh:  # a MariaDB administrator was given: the companions' databases are made for the app user, wherever the server is
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
        rc = runner(e, log=log)
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


def _db_key(cfg, default_name=None):
    """(host, port, database) of an app's own MariaDB database, None when it has none (SQLite, or nothing set)."""
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
    key = _db_key(cfg, a["db"])
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
                if _db_key(ocfg, APPS[other]["db"]) == key:
                    kept = f"{APPS[other]['label']} uses it too"
                    break
    return dict(name=name, label=a["label"], root=root, target=target, cfg=cfg, data=data, data_inside=_inside(data, root),
                db=key, db_kept=kept, photos=cfg.get("PHOTOS_ROOT") or None, backups=cfg.get("BACKUP_DIR") or None)


def stop_service(name, target, log=print, run=subprocess.run):
    """Stop the app and take its service away: the systemd unit setup.sh wrote (only when it points at TARGET), or the
    login item on a Mac. Without either, the app was started by hand (run.sh) and the person stops it."""
    unit = Path(f"/etc/systemd/system/{name}.service")
    label = APPS[name].get("launchd")
    plist = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist" if label else None
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
    elif plist is not None and plist.is_file():
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


def drop_database(p, db_admin=None, connect=None, log=print):
    """--delete-data: drop the app's own database, as the administrator when one was given, else as the app's user."""
    host, port, dbname = p["db"]
    user, password = (db_admin, os.environ.get("DB_ADMIN_PASSWORD", "")) if db_admin else (p["cfg"].get("DB_USER", ""), p["cfg"].get("DB_PASSWORD", ""))
    try:
        if connect is None:
            import pymysql
            connect = lambda h, o, u, w: pymysql.connect(host=h, port=int(o), user=u, password=w, connect_timeout=10, autocommit=True)  # noqa: E731
        conn = connect(host, port, user, password)
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
           delegate=_delegate, log=print):
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
        forgetter(n, log=log)
        # the program files: everything in the app's folder but the data folder
        for child in sorted(p["target"].iterdir()):
            if _inside(p["data"], child):
                continue
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        log(f"  deleted the program files in {p['target']}")
        if delete_data:
            if p["db"] and not p["db_kept"]:
                if not dropper(p, db_admin=db_admin, log=log):
                    failed.append(n)
            elif p["db"]:
                log(f"  kept the database {p['db'][2]}: {p['db_kept']}")
            if p["data_inside"]:
                shutil.rmtree(p["root"], ignore_errors=True)
                log(f"  deleted {p['root']} with the app's data folder")
            else:
                shutil.rmtree(p["target"], ignore_errors=True)
                log(f"  kept the data folder {p['data']}: it is outside {p['root']}, delete it yourself if you want it gone")
        else:
            if p["db"]:
                log(f"  kept the database {p['db'][2]} on {p['db'][0]}:{p['db'][1]}")
            if p["data"].exists():
                log(f"  kept the data folder {p['data']}")
            log(f"  adding {a['label']} again later finds them")
        for what, where in (("photos", p["photos"]), ("backups", p["backups"])):
            if where:
                log(f"  the {what} in {where} are never touched")
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


def choose(base, config_dir, ask=input, log=print):
    """The checklist: returns (add, remove, delete_data, reconfigure), or None when the person changes nothing or backs out."""
    here = installed(base, config_dir)
    own = app_of(config_dir)
    want = list(here)
    redo = []
    names = list(APPS)
    while True:
        log("")
        for line in _table(base, config_dir, want, redo):
            log(line)
        try:
            ans = ask("Numbers or names to tick or untick (e.g. 3 5), r and a number to change an installed app's settings (e.g. r2), Enter when it is right: ").strip()
        except EOFError:
            return None
        if not ans:
            break
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
    if not add and not rem and not redo:
        log("nothing to change")
        return None
    delete = False
    if add:
        log(f"\nTo add: {', '.join(APPS[n]['label'] for n in add)}")
    if redo:
        log(f"\nTo reconfigure: {', '.join(APPS[n]['label'] for n in redo)} (its own questions again, the current answers as the defaults)")
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
    p.add_argument("apps", nargs="+", help="iosuite, iopix, ionote, iocalendar, iocontact, iotask, iorecipe, iohealth, iodns, iobackup (comma-separated or several), or all")
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


def main(a):
    if a.cmd == "remove":
        return _report([], remove(parse_apps(a.apps), a.config, base=a.into, delete_data=a.delete_data, db_admin=a.db_admin))
    if a.cmd == "apps":
        return main_apps(a)
    names = parse_apps(a.apps)
    return _report(install(names, a.config, base=a.into, admin=a.admin, service=a.service, photos=a.photos, from_app=a.from_app, db_admin=a.db_admin), [])


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
    if a.add is None and a.remove is None and a.reconfigure is None:
        say(f"The apps of the suite on this server (under {base})")
        if a.list or not sys.stdin.isatty():
            for line in _table(base, a.config):
                print(line)
            return 0
        picked = choose(base, a.config)
        if not picked:
            return 0
        add, rem, delete, redo = picked
    own = app_of(a.config)
    not_removed = remove([n for n in rem if n != own], a.config, base=base, delete_data=delete, db_admin=a.db_admin) if rem else []
    service = a.service
    if service is None and own and Path(f"/etc/systemd/system/{own}.service").is_file():
        service = True  # the app this runs from is a service: so are the ones added beside it
    not_installed = install(add, a.config, base=base, admin=a.admin, service=service, photos=a.photos,
                            from_app=a.from_app or app_of(a.config), db_admin=a.db_admin) if add else []
    not_redone = reconfigure(redo, a.config, base=base) if redo else []
    if own in rem:  # last: another app that is here removes this one
        not_removed += remove([own], a.config, base=base, delete_data=delete, db_admin=a.db_admin)
    if not_redone:
        print(f"\nerror: not reconfigured: {', '.join(not_redone)}", file=sys.stderr)
    return 1 if not_redone else _report(not_installed, not_removed)
