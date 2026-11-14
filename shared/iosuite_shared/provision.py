"""`iosuite-shared --config FOLDER provision --admin USER`: with a MariaDB / MySQL administrator account (root, or any
account that may CREATE DATABASE, CREATE USER and GRANT), make what the app's config.env names: its own database and
user (DB_*), the Shared ioSuite database and user (IOSUITE_DB_*), and, with `--also APP,APP`, the companions'
databases for that same app user (`iosuite-shared install` does this part by itself when it is given `--db-admin`).

Every app's setup.sh asks for this account right after the database questions ("MariaDB administrator ... empty: the
databases and users exist already"); the password comes in through DB_ADMIN_PASSWORD in the environment, never on a
command line. Nothing is dropped: databases and users are created when missing, and each user gets all privileges on
its databases only. The app's own user gets the password answered (so a re-run with a new password works); the Shared
ioSuite user is only created when missing, because the other apps of the suite sign in with it too: when it exists
with another password, provision says so instead of changing it under them.
Users are made for this machine only: 'localhost' and '127.0.0.1' when the server is this machine, otherwise the
address this machine reaches the server from (or --client-host, e.g. a subnet like '192.168.1.%' for an LXC whose
address changes). A user for any host ('%') with a guessable password was the old default and is no longer made.
"""
import getpass
import os
import re
import socket

IDENT = re.compile(r"^[A-Za-z0-9_]+$")
LOOPBACK = ("127.0.0.1", "localhost", "::1")


def _ident(kind, value):
    if not value or not IDENT.match(value):
        raise SystemExit(f"error: the {kind} {value!r} must be letters, digits and _ only")
    return value


def own_address(host, port) -> str:
    """The address this machine reaches the database server from (no packet is sent: a UDP socket only picks the route)."""
    try:
        with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((host, int(port or 3306)))
            return s.getsockname()[0]
    except OSError as exc:
        raise SystemExit(f"error: cannot tell this machine's address towards {host}:{port} ({exc}); give it with --client-host")


def client_hosts(server, port, client=None, here=None) -> list:
    """The hosts the users are made for: this machine as the server sees it."""
    if client:
        return [client]
    if server.lower() in LOOPBACK:
        return ["localhost", "127.0.0.1"]
    return [(here or own_address)(server, port)]


def plan_sql(cfg, also=(), client=None, here=None):
    """What to run, per server: {(host, port): [(sql, args), ...]}. Pure but for `here` (this machine's address towards
    a remote server), for the tests and for --dry-run."""
    from iosuite_shared.install import APPS

    jobs = {}

    def add(host, port, db, user, password, shared=False):
        key = (host or "127.0.0.1", str(port or "3306"))
        stmts = jobs.setdefault(key, [])
        stmts.append((f"CREATE DATABASE IF NOT EXISTS `{_ident('database name', db)}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci", None))
        for h in client_hosts(key[0], key[1], client or cfg.get("DB_CLIENT_HOST"), here):
            if (f"CREATE USER IF NOT EXISTS `{_ident('user name', user)}`@%s IDENTIFIED BY %s", (h, password)) not in stmts:
                stmts.append((f"CREATE USER IF NOT EXISTS `{user}`@%s IDENTIFIED BY %s", (h, password)))
                if not shared:  # the Shared ioSuite user is the other apps' too: never re-passworded from here
                    stmts.append((f"ALTER USER `{user}`@%s IDENTIFIED BY %s", (h, password)))
            stmts.append((f"GRANT ALL PRIVILEGES ON `{db}`.* TO `{user}`@%s", (h,)))

    app_db = cfg.get("DB_HOST") and cfg.get("DB_USER") and cfg.get("DB_NAME") and cfg.get("DB_TYPE", "mysql") in ("mysql", "mariadb")
    if app_db:
        add(cfg["DB_HOST"], cfg.get("DB_PORT"), cfg["DB_NAME"], cfg["DB_USER"], cfg.get("DB_PASSWORD", ""))
    s_host = cfg.get("IOSUITE_DB_HOST") or cfg.get("DB_HOST")
    s_port = cfg.get("IOSUITE_DB_PORT") or cfg.get("DB_PORT")
    add(s_host, s_port, cfg.get("IOSUITE_DB_NAME") or "iosuite", cfg.get("IOSUITE_DB_USER") or "iosuite", cfg.get("IOSUITE_DB_PASSWORD", ""), shared=True)
    for name in also:
        a = APPS[name]
        if app_db:
            add(cfg["DB_HOST"], cfg.get("DB_PORT"), a["db"], cfg["DB_USER"], cfg.get("DB_PASSWORD", ""))
        else:  # the companions use the Shared ioSuite database's server and user (install.shared_answers does the same)
            add(s_host, s_port, a["db"], cfg.get("IOSUITE_DB_USER") or "iosuite", cfg.get("IOSUITE_DB_PASSWORD", ""), shared=True)
    for stmts in jobs.values():
        stmts.append(("FLUSH PRIVILEGES", None))
    return jobs


def run(admin_user, admin_password, cfg, also=(), connect=None, log=print, client=None, here=None, check=None):
    """Create everything; returns the number of servers touched. Raises SystemExit with the reason on failure.
    `check(host, port, user, password, database)` signs in as the Shared ioSuite user afterwards (by default with a real
    connection when `connect` is the real one too): a user that already existed with another password is said here."""
    import pymysql

    if check is None and connect is None:
        check = lambda h, o, u, w, d: pymysql.connect(host=h, port=int(o), user=u, password=w, database=d, connect_timeout=10).close()  # noqa: E731
    connect = connect or (lambda host, port: pymysql.connect(host=host, port=int(port), user=admin_user, password=admin_password,
                                                             connect_timeout=10, autocommit=True))
    jobs = plan_sql(cfg, also, client, here)
    for (host, port), stmts in jobs.items():
        try:
            conn = connect(host, port)
        except Exception as exc:  # noqa: BLE001 - say what went wrong, in one line
            raise SystemExit(f"error: could not connect to {host}:{port} as {admin_user}: {exc}")
        try:
            with conn.cursor() as cur:
                for sql, args in stmts:
                    try:
                        cur.execute(sql, args)
                    except Exception as exc:  # noqa: BLE001
                        raise SystemExit(f"error: {host}:{port}: {sql.split(' ON ')[0].split(' IDENTIFIED')[0]}: {exc}")
        finally:
            conn.close()
        dbs = sorted({s.split("`")[1] for s, _ in stmts if s.startswith("CREATE DATABASE")})
        users = sorted({s.split("`")[1] for s, _ in stmts if s.startswith("CREATE USER")})
        log(f"  {host}:{port}: database(s) {', '.join(dbs)} and user(s) {', '.join(users)} ready")
    if check:
        s_host, s_port = cfg.get("IOSUITE_DB_HOST") or cfg.get("DB_HOST") or "127.0.0.1", cfg.get("IOSUITE_DB_PORT") or cfg.get("DB_PORT") or "3306"
        s_user, s_name = cfg.get("IOSUITE_DB_USER") or "iosuite", cfg.get("IOSUITE_DB_NAME") or "iosuite"
        try:
            check(s_host, s_port, s_user, cfg.get("IOSUITE_DB_PASSWORD", ""), s_name)
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"error: the Shared ioSuite user {s_user} cannot sign in with the password given ({exc}). It existed "
                             f"already, and the other apps of the suite use it: give its password (IOSUITE_DB_PASSWORD in another "
                             f"app's config.env), or change it on the server and in every app's config.env")
    return len(jobs)


def add_parser(sub):
    p = sub.add_parser("provision", help="create the app's database and user and the Shared ioSuite database and user with a MariaDB administrator account")
    p.add_argument("--admin", required=True, help="the administrator's user name (its password from DB_ADMIN_PASSWORD, else asked for)")
    p.add_argument("--also", default="", help="also the databases of these companion apps (iopix,ionote,... or all) for the same app user")
    p.add_argument("--client-host", default=None, help="the host the users are made for (default: this machine as the server sees it; e.g. '192.168.1.%%')")
    p.add_argument("--dry-run", action="store_true", help="only print what would be run (passwords hidden)")
    return p


def main(a):
    from iosuite_shared.install import parse_apps, read_env_file
    from pathlib import Path

    if not a.config:
        raise SystemExit("error: provision needs --config FOLDER (the app's folder with config.env)")
    cfg = read_env_file(Path(a.config) / "config.env")
    also = parse_apps(a.also) if a.also else []
    if a.dry_run:
        for (host, port), stmts in plan_sql(cfg, also, a.client_host).items():
            print(f"{host}:{port}")
            for sql, args in stmts:
                print("  " + sql + (f"   -- {args[0]}" if args else ""))
        return 0
    password = os.environ.get("DB_ADMIN_PASSWORD")
    if password is None:
        password = getpass.getpass(f"MariaDB password for {a.admin}: ")
    run(a.admin, password, cfg, also, client=a.client_host)
    return 0
