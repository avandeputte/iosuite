"""The master list (entries and their records per view), the views, the DNS servers and the log."""
from __future__ import annotations

import json
import re

from iosuite_shared import credentials

from app import config, db, providers
from app.providers import norm_name, norm_value


class NotFound(Exception):
    pass


SLUG = re.compile(r"^[a-z][a-z0-9-]{0,31}$")


# ---------------------------------------------------------------- views

def views() -> list[dict]:
    rows = db.q("SELECT v.*, (SELECT count(*) FROM dns_servers s WHERE s.view_id = v.id) AS servers, "
                "(SELECT count(DISTINCT r.entry_id) FROM dns_records r WHERE r.view_id = v.id) AS entries "
                "FROM dns_views v ORDER BY position, id")
    return [{"id": r["id"], "slug": r["slug"], "name": r["name"], "description": r["description"] or "",
             "servers": r["servers"], "entries": r["entries"]} for r in rows]


def view(slug_or_id) -> dict:
    for v in views():
        if str(slug_or_id) in (v["slug"], str(v["id"])):
            return v
    raise NotFound(f"No view {slug_or_id!r}")


def save_view(body: dict, vid: int | None = None) -> dict:
    name = str(body.get("name") or "").strip()[:64]
    if vid is None:
        slug = str(body.get("slug") or name).strip().lower().replace(" ", "-")
        if not SLUG.match(slug):
            raise ValueError("A view's short name: letters, digits and dashes, starting with a letter")
        if not name:
            raise ValueError("A view needs a name")
        pos = (db.one("SELECT COALESCE(MAX(position), -1) + 1 AS p FROM dns_views") or {"p": 0})["p"]
        try:
            vid = db.ex("INSERT INTO dns_views (slug, name, description, position) VALUES (%s, %s, %s, %s)",
                        (slug, name, str(body.get("description") or "")[:255] or None, pos))
        except db.pymysql.err.IntegrityError:
            raise ValueError(f"There is a view {slug!r} already") from None
    else:
        view(vid)
        if name:
            db.ex("UPDATE dns_views SET name = %s WHERE id = %s", (name, vid))
        if "description" in body:
            db.ex("UPDATE dns_views SET description = %s WHERE id = %s", (str(body.get("description") or "")[:255] or None, vid))
    return view(vid)


def delete_view(vid: int) -> None:
    v = view(vid)
    if len(views()) <= 1:
        raise ValueError("The last view stays")
    db.ex("DELETE FROM dns_views WHERE id = %s", (v["id"],))
    db.ex("DELETE FROM dns_entries WHERE NOT EXISTS (SELECT 1 FROM dns_records r WHERE r.entry_id = dns_entries.id)")


# ---------------------------------------------------------------- entries (the master list)

def _entries(where: str = "", args=()) -> list[dict]:
    es = db.q(f"SELECT * FROM dns_entries {where} ORDER BY name", args)
    if not es:
        return []
    vs = {v["id"]: v["slug"] for v in views()}
    recs = db.q(f"SELECT * FROM dns_records WHERE entry_id IN ({db.marks(len(es))}) ORDER BY view_id, type, value", [e["id"] for e in es])
    by = {}
    for r in recs:
        by.setdefault(r["entry_id"], {}).setdefault(vs.get(r["view_id"], str(r["view_id"])), []).append(
            {"type": r["type"], "value": r["value"], "ttl": r["ttl"], "source": r["source"]})
    return [{"id": e["id"], "name": e["name"], "comment": e["comment"] or "", "records": by.get(e["id"], {}),
             "updatedAt": e["updated_at"].isoformat() if e["updated_at"] else None, "updatedBy": e["updated_by"]} for e in es]


def entries() -> list[dict]:
    return _entries()


def entry(name_or_id) -> dict:
    s = str(name_or_id)
    rows = _entries("WHERE id = %s", (int(s),)) if s.isdigit() else _entries("WHERE name = %s", (norm_name(s),))
    if not rows:
        raise NotFound(f"No entry {name_or_id!r}")
    return rows[0]


def _clean_records(recs: dict, resolve) -> list[tuple]:
    """{view slug: [{type, value, ttl?, source?}]} into (view_id, type, value, ttl, source) rows, checked."""
    vs = {v["slug"]: v["id"] for v in views()}
    out, seen = [], set()
    for slug, items in (recs or {}).items():
        if slug not in vs:
            raise ValueError(f"No view {slug!r}")
        types = set()
        for it in items or []:
            t = str(it.get("type") or "").strip().upper()
            if t not in providers.TYPES:
                raise ValueError(f"Record type {t!r}: ioDNS keeps {', '.join(providers.TYPES)}")
            source = str(it.get("source") or "").strip() or None
            value = str(it.get("value") or "").strip()
            if source:
                value = resolve(source, t) or value
            if not value:
                continue
            value = norm_value(t, value)
            ttl = it.get("ttl")
            ttl = int(ttl) if ttl not in (None, "", 0, "0") else None
            if ttl is not None and not 0 < ttl <= 604800:
                raise ValueError("A TTL is between 1 second and a week")
            key = (vs[slug], t, value)
            if key in seen:
                continue
            seen.add(key)
            types.add(t)
            out.append((vs[slug], t, value, ttl, source))
        if "CNAME" in types and len(types) > 1:
            raise ValueError(f"{slug}: a name with a CNAME has no other records")
        if sum(1 for r in out if r[0] == vs[slug] and r[1] == "CNAME") > 1:
            raise ValueError(f"{slug}: one CNAME per name")
    return out


def save_entry(body: dict, by: str | None, eid: int | None = None, resolve=None) -> dict:
    """Make or change an entry: {name, comment, records: {view: [{type, value, ttl, source}]}}; the records given replace
    the entry's (a view left out keeps its records unless replaceAll)."""
    from app import sources
    resolve = resolve or sources.resolve
    name = norm_name(body.get("name") or (entry(eid)["name"] if eid else ""))
    rows = _clean_records(body.get("records") or {}, resolve)
    comment = str(body.get("comment") or "").strip()[:512] or None
    with db.tx():
        other = db.one("SELECT id FROM dns_entries WHERE name = %s", (name,))
        if eid is None:
            if other:
                raise ValueError(f"{name} is in the list already")
            eid = db.ex("INSERT INTO dns_entries (name, comment, updated_by) VALUES (%s, %s, %s)", (name, comment, by))
        else:
            old = entry(eid)
            if other and other["id"] != eid:
                raise ValueError(f"{name} is in the list already")
            db.ex("UPDATE dns_entries SET name = %s, comment = %s, updated_by = %s WHERE id = %s",
                  (name, comment if "comment" in body else (old["comment"] or None), by, eid))
        given = {v["id"] for v in views() if v["slug"] in (body.get("records") or {})}
        if body.get("replaceAll"):
            given = {v["id"] for v in views()}
        if given:
            db.ex(f"DELETE FROM dns_records WHERE entry_id = %s AND view_id IN ({db.marks(len(given))})", [eid, *given])
        for vid, t, value, ttl, source in rows:
            db.ex("INSERT INTO dns_records (entry_id, view_id, type, value, ttl, source) VALUES (%s, %s, %s, %s, %s, %s)",
                  (eid, vid, t, value, ttl, source))
        db.ex("UPDATE dns_entries SET updated_at = CURRENT_TIMESTAMP, updated_by = %s WHERE id = %s", (by, eid))
    e = entry(eid)
    log(by, "edit", detail=f"{e['name']}: {describe(e['records']) or 'no records'}")
    return e


def delete_entry(eid: int, by: str | None) -> None:
    e = entry(eid)
    db.ex("DELETE FROM dns_entries WHERE id = %s", (e["id"],))
    log(by, "delete", detail=e["name"])


def describe(records: dict) -> str:
    return "; ".join(f"{slug} {', '.join(r['type'] + ' ' + r['value'] for r in rs)}" for slug, rs in records.items() if rs)


def set_view_records(view_id: int, name: str, recs: list[providers.Record], by: str | None, comment: str | None = None) -> None:
    """One name's records in one view, as given (an empty list: none in that view; the entry goes when it has none left)."""
    name = norm_name(name)
    with db.tx():
        e = db.one("SELECT id FROM dns_entries WHERE name = %s", (name,))
        if e is None:
            if not recs:
                return
            eid = db.ex("INSERT INTO dns_entries (name, comment, updated_by) VALUES (%s, %s, %s)", (name, comment, by))
        else:
            eid = e["id"]
        keep = {(r["type"], r["value"]): r["source"] for r in
                db.q("SELECT type, value, source FROM dns_records WHERE entry_id = %s AND view_id = %s", (eid, view_id))}
        db.ex("DELETE FROM dns_records WHERE entry_id = %s AND view_id = %s", (eid, view_id))
        for r in {r.key: r for r in recs}.values():
            db.ex("INSERT INTO dns_records (entry_id, view_id, type, value, ttl, source) VALUES (%s, %s, %s, %s, %s, %s)",
                  (eid, view_id, r.type, r.value, r.ttl, keep.get((r.type, r.value))))
        if not db.one("SELECT 1 AS x FROM dns_records WHERE entry_id = %s", (eid,)):
            db.ex("DELETE FROM dns_entries WHERE id = %s", (eid,))
        else:
            db.ex("UPDATE dns_entries SET updated_at = CURRENT_TIMESTAMP, updated_by = %s WHERE id = %s", (by, eid))


def master(view_id: int, types=None) -> list[providers.Record]:
    """The master list's records in one view, as providers.Record (only the types a server keeps, when given)."""
    rows = db.q("SELECT e.name, r.type, r.value, r.ttl FROM dns_records r JOIN dns_entries e ON e.id = r.entry_id "
                "WHERE r.view_id = %s ORDER BY e.name, r.type, r.value", (view_id,))
    return [providers.Record(r["name"], r["type"], r["value"], r["ttl"]) for r in rows if types is None or r["type"] in types]


def export() -> dict:
    return {"app": "iodns", "views": [{"slug": v["slug"], "name": v["name"], "description": v["description"]} for v in views()],
            "entries": [{"name": e["name"], "comment": e["comment"], "records": e["records"]} for e in entries()]}


def import_json(data: dict, by: str | None, replace: bool = False) -> dict:
    """An export (above) back in: new views are made, entries are added or (same name) replaced; replace: the entries
    not in the file go."""
    known = {v["slug"] for v in views()}
    for v in data.get("views") or []:
        if v.get("slug") and v["slug"] not in known:
            save_view(v)
    names, n = set(), 0
    for e in data.get("entries") or []:
        name = norm_name(e.get("name"))
        names.add(name)
        body = {"name": name, "comment": e.get("comment") or "", "records": e.get("records") or {}, "replaceAll": True}
        try:
            cur = entry(name)
        except NotFound:
            cur = None
        save_entry(body, by, cur["id"] if cur else None, resolve=lambda s, t: None)
        n += 1
    gone = 0
    if replace:
        for e in entries():
            if e["name"] not in names:
                db.ex("DELETE FROM dns_entries WHERE id = %s", (e["id"],))
                gone += 1
    log(by, "import", detail=f"{n} entries from a file" + (f", {gone} removed" if gone else ""))
    return {"entries": n, "removed": gone}


# ---------------------------------------------------------------- servers

def _secret_name(sid: int) -> str:
    return f"server_{sid}"


def secret(sid: int) -> str:
    return credentials.get(config.APP, _secret_name(sid))


def _server(r: dict, vs: dict) -> dict:
    cls = providers.KINDS.get(r["kind"])
    opts = json.loads(r["options"] or "{}")
    return {"id": r["id"], "name": r["name"], "kind": r["kind"], "kindLabel": cls.label if cls else r["kind"],
            "target": bool(cls and cls.target), "url": r["url"], "view": vs.get(r["view_id"]), "viewId": r["view_id"],
            "options": opts, "enabled": bool(r["enabled"]), "secretSet": credentials.is_set(config.APP, _secret_name(r["id"])),
            "check": {"at": r["checked_at"].isoformat() if r["checked_at"] else None, "ok": None if r["check_ok"] is None else bool(r["check_ok"]),
                      "message": r["check_message"], "differences": r["differences"]}}


def servers(view_id: int | None = None, targets_only: bool = False) -> list[dict]:
    vs = {v["id"]: v["slug"] for v in views()}
    rows = db.q("SELECT * FROM dns_servers ORDER BY position, id")
    out = [_server(r, vs) for r in rows]
    if view_id is not None:
        out = [s for s in out if s["viewId"] == view_id]
    if targets_only:
        out = [s for s in out if s["target"]]
    return out


def server(sid: int) -> dict:
    for s in servers():
        if s["id"] == int(sid):
            return s
    raise NotFound(f"No server {sid}")


def save_server(body: dict, by: str | None, sid: int | None = None) -> dict:
    cur = server(sid) if sid is not None else None
    kind = str(body.get("kind") or (cur or {}).get("kind") or "")
    cls = providers.get(kind)
    name = str(body.get("name") if body.get("name") is not None else (cur or {}).get("name") or "").strip()[:64]
    if not name:
        raise ValueError("A server needs a name")
    url = str(body.get("url") if body.get("url") is not None else (cur or {}).get("url") or "").strip().rstrip("/")
    if url and not re.match(r"^https?://[^\s/]+", url):
        raise ValueError("The address starts with http:// or https://")
    if not url and cls.target:
        raise ValueError("A server needs its address")
    opts = dict((cur or {}).get("options") or {})
    known = {f["key"] for f in cls.fields} - {"url", "secret"}
    for k, v in (body.get("options") or {}).items():
        if k in known:
            opts[k] = v
    view_id = None
    if cls.target:
        v = body.get("view", (cur or {}).get("view") or "internal")
        view_id = view(v)["id"] if v else None
    enabled = 1 if body.get("enabled", (cur or {}).get("enabled", True)) else 0
    if cur is None:
        pos = (db.one("SELECT COALESCE(MAX(position), -1) + 1 AS p FROM dns_servers") or {"p": 0})["p"]
        sid = db.ex("INSERT INTO dns_servers (name, kind, url, view_id, options, enabled, position) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (name, kind, url, view_id, json.dumps(opts), enabled, pos))
    else:
        db.ex("UPDATE dns_servers SET name = %s, url = %s, view_id = %s, options = %s, enabled = %s WHERE id = %s",
              (name, url, view_id, json.dumps(opts), enabled, sid))
    credentials.declare(config.APP, [{"name": _secret_name(sid), "label": f"{name} ({cls.label})",
                                      "hint": "the DNS server's password or API key (Settings › Servers in ioDNS)"}])
    if body.get("secret") is not None:
        credentials.put(config.APP, _secret_name(sid), body.get("secret") or "", by=by)
    log(by, "server", sid, name, "added" if cur is None else "changed")
    return server(sid)


def delete_server(sid: int, by: str | None) -> None:
    s = server(sid)
    db.ex("DELETE FROM dns_servers WHERE id = %s", (s["id"],))
    credentials.remove(config.APP, _secret_name(s["id"]))
    log(by, "server", s["id"], s["name"], "removed")


def record_check(sid: int, ok: bool, message: str, differences: int | None = None) -> None:
    db.ex("UPDATE dns_servers SET checked_at = CURRENT_TIMESTAMP, check_ok = %s, check_message = %s, differences = %s WHERE id = %s",
          (1 if ok else 0, str(message or "")[:512], differences, sid))


def provider(s: dict) -> providers.Provider:
    """The server's provider, with its secret, ready for `with`."""
    cls = providers.get(s["kind"])
    return cls({**s, "options": dict(s.get("options") or {})}, secret(s["id"]))


# ---------------------------------------------------------------- log

def log(by: str | None, action: str, server_id: int | None = None, server_name: str | None = None, detail: str = "", ok: bool = True) -> None:
    db.ex("INSERT INTO dns_log (user_name, action, server_id, server_name, detail, ok) VALUES (%s, %s, %s, %s, %s, %s)",
          (by, action, server_id, server_name, str(detail or "")[:20000], 1 if ok else 0))


def log_items(limit: int = 200) -> list[dict]:
    rows = db.q("SELECT * FROM dns_log ORDER BY id DESC LIMIT %s", (max(1, min(int(limit), 1000)),))
    return [{"id": r["id"], "at": r["at"].isoformat(), "user": r["user_name"], "action": r["action"], "serverId": r["server_id"],
             "server": r["server_name"], "detail": r["detail"] or "", "ok": bool(r["ok"])} for r in rows]
