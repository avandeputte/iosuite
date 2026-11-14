"""What ioBackup keeps: the servers it backs up and restores onto, the destinations backups go to, and the jobs. Rows
in bkp_* (app/db.py); every password and Google key in the suite's keys and tokens (iosuite_shared.credentials), so
a suite admin sees them with the rest at Settings › Global settings › Keys and tokens, and nothing here returns one.

The engine (app/engine.py) and the destinations (app/destinations.py) take plain dicts: server(id) and
destination(id) put the row and its secrets together for them.
"""
from __future__ import annotations

import json
import os

from iosuite_shared import credentials
from iosuite_shared.errors import Invalid

from app import config, db, engine
from app.schedule import schedule_to_cron

APP = config.APP


class NotFound(Exception):
    pass


def _secret(kind: str, rid: int, what: str) -> str:
    return f"{kind}_{rid}_{what}"


def _str(v, n: int, label: str, required: bool = False) -> str:
    s = str(v if v is not None else "").strip()
    if required and not s:
        raise Invalid(f"Give the {label}")
    if len(s) > n:
        raise Invalid(f"The {label} is too long ({n} characters at most)")
    return s


# ---------------------------------------------------------------- servers


def _server_public(r: dict) -> dict:
    return {"id": r["id"], "name": r["name"], "host": r["host"], "port": r["port"], "socket": r["socket"],
            "user": r["user_name"], "tls": bool(r["tls"]),
            "passwordSet": credentials.is_set(APP, _secret("server", r["id"], "password"))}


def servers() -> list[dict]:
    return [_server_public(r) for r in db.q("SELECT * FROM bkp_servers ORDER BY name")]


def _server_row(sid: int) -> dict:
    r = db.one("SELECT * FROM bkp_servers WHERE id = %s", (sid,))
    if not r:
        raise NotFound("No such server")
    return r


def server(sid: int) -> dict:
    """The connection settings the engine takes (with the password)."""
    r = _server_row(sid)
    return {"id": r["id"], "name": r["name"], "host": r["host"], "port": r["port"], "socket": r["socket"],
            "user": r["user_name"], "ssl": bool(r["tls"]),
            "password": credentials.get(APP, _secret("server", r["id"], "password"))}


def clean_server(b: dict) -> dict:
    port = b.get("port")
    if port in ("", None):
        port = None
    else:
        try:
            port = int(port)
        except (TypeError, ValueError):
            raise Invalid("The port is a number") from None
        if not 0 < port < 65536:
            raise Invalid("The port is between 1 and 65535")
    out = {"name": _str(b.get("name"), 64, "server a name", True), "host": _str(b.get("host"), 253, "host"),
           "port": port, "socket": _str(b.get("socket"), 255, "socket"), "user": _str(b.get("user"), 80, "user"),
           "ssl": bool(b.get("tls"))}
    if not out["host"] and not out["socket"]:
        out["socket"] = ""  # the client's own default socket
    return out


def unsaved_server(b: dict) -> dict:
    """A server from the form, to test before saving it: no password typed in keeps the saved one of id."""
    s = clean_server({**b, "name": b.get("name") or "test"})
    s["password"] = b.get("password")
    if s["password"] is None and b.get("id"):
        s["password"] = credentials.get(APP, _secret("server", int(b["id"]), "password"))
    return s


def save_server(b: dict, by: str | None, sid: int | None = None) -> dict:
    s = clean_server(b)
    if db.one("SELECT id FROM bkp_servers WHERE name = %s AND id != %s", (s["name"], sid or 0)):
        raise Invalid(f"Another server is already called {s['name']}")
    args = (s["name"], s["host"], s["port"], s["socket"], s["user"], 1 if s["ssl"] else 0)
    if sid:
        _server_row(sid)
        db.ex("UPDATE bkp_servers SET name = %s, host = %s, port = %s, socket = %s, user_name = %s, tls = %s WHERE id = %s", (*args, sid))
    else:
        sid = db.ex("INSERT INTO bkp_servers (name, host, port, socket, user_name, tls) VALUES (%s, %s, %s, %s, %s, %s)", args)
    name = _secret("server", sid, "password")
    credentials.declare(APP, [{"name": name, "label": f"{s['name']} (MariaDB password)", "hint": "the password ioBackup signs in to this server with"}])
    if b.get("password") is not None:  # null or missing: unchanged
        credentials.put(APP, name, b.get("password") or "", by=by)
    return _server_public(_server_row(sid))


def delete_server(sid: int) -> None:
    _server_row(sid)
    used = [r["name"] for r in db.q("SELECT name FROM bkp_jobs WHERE server_id = %s", (sid,))]
    if used:
        raise Invalid("Used by the job(s) " + ", ".join(used))
    db.ex("DELETE FROM bkp_servers WHERE id = %s", (sid,))
    credentials.remove(APP, _secret("server", sid, "password"))


# ---------------------------------------------------------------- destinations

DEST_SECRETS = ("client_secret", "refresh_token", "service_account")


def _dest_row(did: int) -> dict:
    r = db.one("SELECT * FROM bkp_destinations WHERE id = %s", (did,))
    if not r:
        raise NotFound("No such destination")
    r["options"] = json.loads(r["options"] or "{}")
    return r


def _dest_public(r: dict) -> dict:
    o = r["options"]
    out = {"id": r["id"], "name": r["name"], "kind": r["kind"]}
    if r["kind"] == "local":
        out["path"] = o.get("path", "")
    else:
        has = {k: credentials.is_set(APP, _secret("destination", r["id"], k)) for k in DEST_SECRETS}
        sa = o.get("auth") == "service_account"
        out.update(auth=o.get("auth") or "oauth", folderName=o.get("folder_name") or "", folderId=o.get("folder_id") or "",
                   clientId=o.get("client_id") or "", account=o.get("account") or "",
                   clientSecretSet=has["client_secret"], serviceAccountSet=has["service_account"],
                   signedIn=has["service_account"] if sa else has["refresh_token"])
    return out


def destinations() -> list[dict]:
    return [_dest_public({**r, "options": json.loads(r["options"] or "{}")}) for r in db.q("SELECT * FROM bkp_destinations ORDER BY name")]


def destination_public(did: int) -> dict:
    return _dest_public(_dest_row(did))


def destination(did: int) -> dict:
    """The settings app/destinations.py takes (with the Google keys)."""
    r = _dest_row(did)
    d = {"id": r["id"], "name": r["name"], "type": r["kind"], **r["options"]}
    if r["kind"] == "gdrive":
        get = lambda k: credentials.get(APP, _secret("destination", r["id"], k)) or None  # noqa: E731
        d.update(client_secret=get("client_secret"), refresh_token=get("refresh_token"), sa_json=get("service_account"))
    return d


def save_destination(b: dict, by: str | None, did: int | None = None) -> dict:
    name = _str(b.get("name"), 64, "destination a name", True)
    kind = b.get("kind")
    old = _dest_row(did) if did else None
    if db.one("SELECT id FROM bkp_destinations WHERE name = %s AND id != %s", (name, did or 0)):
        raise Invalid(f"Another destination is already called {name}")
    secrets = {}
    if kind == "local":
        path = _str(b.get("path"), 1024, "folder", True)
        if not os.path.isabs(path):
            raise Invalid("The folder is an absolute path, like /var/backups/iobackup")
        opts = {"path": os.path.normpath(path)}
    elif kind == "gdrive":
        auth = "service_account" if b.get("auth") == "service_account" else "oauth"
        opts = {"auth": auth, "folder_name": _str(b.get("folderName"), 200, "folder name") or "ioBackup",
                "folder_id": _str(b.get("folderId"), 200, "folder ID"), "client_id": _str(b.get("clientId"), 300, "client ID")}
        if auth == "service_account" and not opts["folder_id"]:
            raise Invalid("A service account needs the ID of a folder in a Shared Drive")
        if auth == "oauth" and not opts["client_id"]:
            raise Invalid("Give the OAuth client ID")
        if b.get("serviceAccount"):
            try:
                if json.loads(b["serviceAccount"]).get("type") != "service_account":
                    raise ValueError
            except (ValueError, AttributeError):
                raise Invalid("The service account key is the JSON file Google gives (type service_account)") from None
        secrets = {"client_secret": b.get("clientSecret"), "service_account": b.get("serviceAccount")}
        oo = (old or {}).get("options", {}) if old and old["kind"] == "gdrive" else {}
        same_client = oo.get("client_id") == opts["client_id"] and oo.get("auth") == auth
        opts["account"] = oo.get("account") if same_client else None
        if old and not same_client:
            secrets["refresh_token"] = ""  # another Google client: sign in again
    else:
        raise Invalid("Pick a local folder or Google Drive")
    if did:
        db.ex("UPDATE bkp_destinations SET name = %s, kind = %s, options = %s WHERE id = %s", (name, kind, json.dumps(opts), did))
    else:
        did = db.ex("INSERT INTO bkp_destinations (name, kind, options) VALUES (%s, %s, %s)", (name, kind, json.dumps(opts)))
    if kind == "gdrive":
        credentials.declare(APP, [
            {"name": _secret("destination", did, "client_secret"), "label": f"{name} (Google OAuth client secret)"},
            {"name": _secret("destination", did, "refresh_token"), "label": f"{name} (Google sign-in)", "hint": "made by Sign in with Google"},
            {"name": _secret("destination", did, "service_account"), "label": f"{name} (Google service account key)"}])
        for k, v in secrets.items():
            if v is not None:  # null or missing: unchanged
                credentials.put(APP, _secret("destination", did, k), v, by=by)
    elif old and old["kind"] == "gdrive":
        for k in DEST_SECRETS:
            credentials.remove(APP, _secret("destination", did, k))
    from app import gdrive
    gdrive.forget_token(did)
    return destination_public(did)


def set_google_account(did: int, refresh_token: str | None, account: str | None, by: str | None) -> None:
    r = _dest_row(did)
    if refresh_token:
        credentials.put(APP, _secret("destination", did, "refresh_token"), refresh_token, by=by)
    r["options"]["account"] = account
    db.ex("UPDATE bkp_destinations SET options = %s WHERE id = %s", (json.dumps(r["options"]), did))


def delete_destination(did: int) -> None:
    _dest_row(did)
    used = [r["name"] for r in db.q("SELECT name FROM bkp_jobs WHERE destination_id = %s", (did,))]
    if used:
        raise Invalid("Used by the job(s) " + ", ".join(used))
    db.ex("DELETE FROM bkp_destinations WHERE id = %s", (did,))
    for k in DEST_SECRETS:
        credentials.remove(APP, _secret("destination", did, k))


# ---------------------------------------------------------------- jobs

def _job_public(r: dict) -> dict:
    return {"id": r["id"], "name": r["name"], "serverId": r["server_id"], "destinationId": r["destination_id"],
            "databases": json.loads(r["databases_json"]), "includeUsers": bool(r["include_users"]), "keep": r["keep_count"],
            "schedule": json.loads(r["schedule_json"]), "cron": r["cron"], "enabled": bool(r["enabled"]),
            "desync": bool(r["desync"]), "lockAll": bool(r["lock_all"]), "compressLevel": r["compress_level"]}


def jobs() -> list[dict]:
    return [_job_public(r) for r in db.q("SELECT * FROM bkp_jobs ORDER BY name")]


def job(jid: int) -> dict:
    r = db.one("SELECT * FROM bkp_jobs WHERE id = %s", (jid,))
    if not r:
        raise NotFound("No such job")
    return _job_public(r)


def save_job(b: dict, jid: int | None = None) -> dict:
    name = _str(b.get("name"), 64, "job a name", True)
    dbs = b.get("databases")
    include_users = bool(b.get("includeUsers", True))
    if dbs != "all":
        if not isinstance(dbs, list) or not all(isinstance(x, str) and x for x in dbs):
            raise Invalid("Pick the databases, or all of them")
        if not dbs and not include_users:
            raise Invalid("Pick at least one database, or the users")
    try:
        keep = int(b.get("keep") if b.get("keep") is not None else 7)
        level = int(b.get("compressLevel") or 6)
        server_id, dest_id = int(b.get("serverId") or 0), int(b.get("destinationId") or 0)
    except (TypeError, ValueError):
        raise Invalid("Keep, compression, server and destination are numbers") from None
    if not 0 <= keep <= 10000:
        raise Invalid("Keep is between 0 (keep them all) and 10000")
    try:
        cron = schedule_to_cron(b.get("schedule"))
    except (ValueError, TypeError) as e:
        raise Invalid(f"Schedule: {e}") from None
    if not db.one("SELECT id FROM bkp_servers WHERE id = %s", (server_id,)):
        raise Invalid("Pick a server")
    if not db.one("SELECT id FROM bkp_destinations WHERE id = %s", (dest_id,)):
        raise Invalid("Pick a destination")
    label = engine.slug(name)
    for r in db.q("SELECT id, name FROM bkp_jobs WHERE id != %s", (jid or 0,)):
        if engine.slug(r["name"]) == label:
            raise Invalid(f"Another job is already called {r['name']}: the names differ, because retention tells the backups apart by them")
    args = (name, server_id, dest_id, json.dumps(dbs), 1 if include_users else 0, keep,
            json.dumps(b.get("schedule") or {"mode": "manual"}), cron, 1 if b.get("enabled", True) else 0,
            1 if b.get("desync") else 0, 1 if b.get("lockAll") else 0, max(1, min(9, level)))
    cols = "name, server_id, destination_id, databases_json, include_users, keep_count, schedule_json, cron, enabled, desync, lock_all, compress_level"
    if jid:
        job(jid)
        db.ex("UPDATE bkp_jobs SET " + ", ".join(f"{c.strip()} = %s" for c in cols.split(",")) + " WHERE id = %s", (*args, jid))
    else:
        jid = db.ex(f"INSERT INTO bkp_jobs ({cols}) VALUES ({db.marks(len(args))})", args)
    return job(jid)


def delete_job(jid: int) -> None:
    job(jid)
    db.ex("DELETE FROM bkp_jobs WHERE id = %s", (jid,))
