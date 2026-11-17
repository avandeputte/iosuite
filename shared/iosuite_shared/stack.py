"""`iosuite-shared stack`: what a Docker stack of the suite needs done before its apps start, in one command that the
stack's first app runs at every start, ahead of itself: `iosuite-shared stack ... -- python -m app` (the compose file
builder on the website writes that command; any app's image can run it, since every image holds this library). The
other apps of the stack wait until that app is healthy. No container of its own, so none is left stopped when the
work is done:

  1. with `--db-admin USER` (its password in DB_ADMIN_PASSWORD): the databases named by `--databases a,b,c` for the
     apps' user (DB_USER / DB_PASSWORD), and the Shared ioSuite database and user (IOSUITE_DB_*), made when missing
     (iosuite_shared.provision: nothing is dropped, the Shared user's password is never changed). The server and the
     users come from the environment, as the apps of the stack get them; the users are made for `--client-host`
     ('%' by default: a container's address is not one the server can be told ahead of time).
  2. the tables of the Shared ioSuite database, and the first admin (ADMIN_USER / ADMIN_PASSWORD) when it holds no
     account yet: once, here, instead of in whichever app happens to start first.
  3. what the stack says about how the suite is reached, which lives in the Shared ioSuite database and not in any
     app's environment: `--one-address on|off` (the start page answers for every app, each in its folder) and
     `--proxies LIST` (the addresses the reverse proxies connect from: the start page's container for the other apps,
     a Caddy container, the proxy on the host). They are written when they differ from what this command wrote the
     last time, so a later `up` of the same file leaves alone what a suite admin has changed under Settings since; a
     stack file that says something new is applied.
  4. with `--demo`: the demo switch (iosuite_shared.demo), which has every app of the stack fetch the demo data (the
     made-up Calloway family) and add its share at its first start. Only on a suite with no accounts but the admin's
     yet, so a later `up` of a stack that has been used for real never adds it.

The database is waited for (a container that was only just started), a minute at most.

What follows `--` is the app: this process becomes it once the work is done (exec, so the app gets the container's
signals), without the two passwords only this command needs (DB_ADMIN_PASSWORD, ADMIN_PASSWORD) in its environment.
"""
import os
import sys
import time

DECLARED = "stack_declared"  # ios_settings, app '': what this command last wrote, as "one=1;proxies=a,b"
WAIT_S = 60
ONLY_HERE = ("DB_ADMIN_PASSWORD", "ADMIN_PASSWORD")  # not handed on to the app that is started after `--`


def add_parser(sub):
    p = sub.add_parser("stack", help="set a Docker stack up before its apps start: the databases, the first admin, how the suite is reached")
    p.add_argument("--db-admin", default=None, help="a MariaDB administrator (its password in DB_ADMIN_PASSWORD): creates the databases and the users")
    p.add_argument("--databases", default="", help="with --db-admin: the apps' databases, commas between them (iostart,iocalendar)")
    p.add_argument("--client-host", default="%", help="with --db-admin: the host the users are made for (default %%: any)")
    p.add_argument("--one-address", choices=("on", "off"), default=None, help="the start page answers for every app, each in its folder")
    p.add_argument("--demo", action="store_true", help="fill a new suite with demo data: a made-up family of four, something in every app")
    p.add_argument("--proxies", default=None, help="the addresses or networks the reverse proxies connect from, commas between them ('' for none)")
    p.add_argument("then", nargs="...", metavar="-- COMMAND", help="after --: the app to become once the work is done (python -m app)")
    return p


def then_command(a) -> list:
    """What follows `--` on the command line, without the `--`."""
    cmd = list(getattr(a, "then", None) or [])
    return cmd[1:] if cmd[:1] == ["--"] else cmd


def _names(spec) -> list:
    return [n.strip() for n in (spec or "").split(",") if n.strip()]


def _cfg(env) -> dict:
    keys = ("DB_TYPE", "DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "IOSUITE_DB_HOST", "IOSUITE_DB_PORT", "IOSUITE_DB_NAME",
            "IOSUITE_DB_USER", "IOSUITE_DB_PASSWORD")
    return {k: env[k] for k in keys if env.get(k)}


def _wait(what, attempt, log, wait_s=WAIT_S, sleep=time.sleep):
    """Run attempt() until it stops raising SystemExit / an exception that says the server is not there yet."""
    until = time.time() + wait_s
    while True:
        try:
            return attempt()
        except SystemExit as exc:
            msg = str(exc)
            if "could not connect" not in msg or time.time() >= until:
                raise
        except Exception as exc:  # noqa: BLE001 - whatever the driver says while the server starts
            msg = str(exc)
            if time.time() >= until:
                raise SystemExit(f"error: {what}: {msg[:300]}")
        log(f"  waiting for the database ({msg[:120]})")
        sleep(3)


def provision_from_env(admin, databases, client, env=None, log=print, run=None, wait_s=WAIT_S, sleep=time.sleep):
    """Step 1. `run` is provision.run (the tests pass their own)."""
    from iosuite_shared import provision
    env = os.environ if env is None else env
    names = _names(databases)
    if not names:
        raise SystemExit("error: --db-admin needs --databases (the apps' databases: iostart,iocalendar)")
    for n in names:
        provision._ident("database name", n)
    cfg = dict(_cfg(env), DB_NAME=names[0])
    if not cfg.get("DB_HOST") or not cfg.get("DB_USER"):
        raise SystemExit("error: DB_HOST and DB_USER (the apps' database server and user) are not in the environment")
    password = env.get("DB_ADMIN_PASSWORD") or ""
    run = run or provision.run
    return _wait("the databases", lambda: run(admin, password, cfg, names[1:], client=client or "%", log=log), log, wait_s, sleep)


def declare(one_address=None, proxies=None, log=print):
    """Step 3. Returns what was written: a dict with the keys that changed."""
    from iosuite_shared import db, proxyauth, suite
    last = dict(p.split("=", 1) for p in (db.get_setting(DECLARED, "", "") or "").split(";") if "=" in p)
    now = dict(last)
    wrote = {}
    if one_address is not None:
        now["one"] = "1" if one_address == "on" else "0"
        if last.get("one") != now["one"]:
            suite.set_one_address(one_address == "on")
            wrote["one"] = now["one"]
            log("  the suite's one address is " + ("on: the start page answers for every app" if one_address == "on" else "off: each app at its own address"))
    if proxies is not None:
        now["proxies"] = ",".join(_names(proxies))
        if last.get("proxies") != now["proxies"]:
            proxyauth.save_suite({"AUTH_PROXY_TRUSTED": ", ".join(_names(proxies))})
            wrote["proxies"] = now["proxies"]
            log("  reverse proxy addresses: " + (now["proxies"] or "none"))
    if wrote:
        db.set_setting(DECLARED, ";".join(f"{k}={v}" for k, v in sorted(now.items())), "")
    return wrote


def demo_once(log=print) -> bool:
    """Step 4: the demo on a new suite (no account but the first admin) or one that has it already."""
    from iosuite_shared import demo, users
    people = [u for u in users.list_users() if u["name"] not in demo.FAMILY_KEYS]
    if not demo.wanted() and len(people) > 1:
        log("  demo data: not added, this suite has accounts of its own")
        return False
    if not demo.wanted():
        demo.switch(True)
        log(f"  demo data: the Calloway family ({', '.join(demo.FAMILY_KEYS)}; password {demo.DEMO_PASSWORD}); every app fetches the demo data and adds its own at its first start")
    return True


def main(a, log=print):
    if a.db_admin:
        provision_from_env(a.db_admin, a.databases, a.client_host, log=log)
    from iosuite_shared import db, users

    def tables():
        if not users.init():  # makes the first admin too (ADMIN_USER / ADMIN_PASSWORD) when there is no account yet
            raise RuntimeError(db.error or "the Shared ioSuite database cannot be reached")
    _wait("the Shared ioSuite database", tables, log)
    log(f"  the Shared ioSuite database is ready: {len(users.list_users())} account(s)")
    declare(a.one_address, a.proxies, log=log)
    if getattr(a, "demo", False):
        demo_once(log=log)
    log("ok")
    sys.stdout.flush()
    cmd = then_command(a)
    if cmd:
        for k in ONLY_HERE:
            os.environ.pop(k, None)
        os.execvp(cmd[0], cmd)  # does not return: this process is the app from here on
    return 0
