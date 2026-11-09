"""Comparing the master list with the DNS servers, and making them agree.

Everything is per view: the servers of a view are compared with the master list's records in that view, name by name.
For one name and one server the answer is one of

    same        the server holds exactly the master list's records for the name
    missing     the master list has records the server does not hold (and the server holds none for the name)
    extra       the server holds records for a name the master list has none for (in this view)
    different   both hold records for the name, and they differ (another address, A against CNAME…)

and a row (a name, across the servers) is ok when every server is `same`. Resolving a row is one decision:

    master          the servers are made to hold the master list's records (the default for missing and different)
    server:<id>     that server's records become the master list's, then every server is made to hold them
    delete          the name goes from the master list and from every server
    skip            nothing is changed (the default for extra: records made elsewhere are left alone unless asked)

`plan()` turns decisions into operations (per server: delete these, add those) without touching anything, `apply()`
carries them out. Only the record types a server keeps are compared (UniFi may hold an MX ioDNS does not know).
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from app import model, providers
from app.providers import AnsweredElsewhere, ProviderError, Record, excluded, under

_lock = threading.Lock()  # one push at a time


def _by_name(recs: list[Record]) -> dict[str, list[Record]]:
    out: dict[str, list[Record]] = {}
    for r in recs:
        out.setdefault(r.name, []).append(r)
    return out


def _keys(recs) -> set:
    return {r.key for r in recs or []}


def state(mine: list[Record] | None, theirs: list[Record] | None) -> str:
    a, b = _keys(mine), _keys(theirs)
    if a == b:
        return "same"
    if not b:
        return "missing"
    if not a:
        return "extra"
    return "different"


def compare(master: list[Record], snapshots: dict) -> dict:
    """The rows of the comparison. snapshots: {server id: {"ok": bool, "records": [Record], "types": [...], "error"}}."""
    m = _by_name(master)
    theirs = {sid: _by_name(s["records"]) for sid, s in snapshots.items() if s.get("ok")}
    names = sorted(set(m) | {n for t in theirs.values() for n in t}, key=lambda n: (n.split(".")[::-1], n))
    rows, counts = [], {sid: 0 for sid in snapshots}
    for name in names:
        cells, overall = {}, "ok"
        for sid, s in snapshots.items():
            if not s.get("ok"):
                cells[sid] = {"state": "unreachable", "records": []}
                continue
            if not under(name, s.get("covers")):
                cells[sid] = {"state": "outside", "records": []}  # not in the zones the server serves (Cloudflare)
                continue
            if excluded(name, s.get("excludes")):
                cells[sid] = {"state": "leftout", "records": []}  # one of the server's "Names to leave out"
                continue
            types = set(s.get("types") or ())
            mine = [r for r in m.get(name, []) if not types or r.type in types]
            got = theirs[sid].get(name, [])
            st = state(mine, got)
            cells[sid] = {"state": st, "records": [r.as_dict() for r in got]}
            if st != "same":
                counts[sid] += 1
        states = {c["state"] for c in cells.values()} - {"unreachable", "outside", "leftout"}
        if states - {"same"}:
            overall = ("different" if "different" in states or (len(states - {"same"}) > 1) else
                       "missing" if "missing" in states else "extra")
            # two servers that disagree with each other on a name the master list lacks: a conflict too
            if overall == "extra":
                held = {frozenset(_keys(theirs[sid].get(name))) for sid, c in cells.items() if c["state"] == "extra"}
                if len(held) > 1:
                    overall = "different"
        rows.append({"name": name, "state": overall, "master": [r.as_dict() for r in m.get(name, [])], "servers": cells,
                     "default": default_action(overall, m.get(name))})
    return {"rows": rows, "differences": counts}


def default_action(overall: str, mine) -> str:
    if overall in ("ok",):
        return "skip"
    if not mine:
        return "skip"  # extra: left alone unless asked
    return "master"


def plan(master: list[Record], snapshots: dict, decisions: dict[str, str]) -> dict:
    """What apply() would do: {"master": {name: [Record]}, "ops": {server id: [{"op": add|delete|update, "record", "old"}]}}.
    decisions: {name: action}; a name not named is skipped. A record that only changes its value (one A for another)
    is an update, so the server can change it in place (the name is never left unanswered, Cloudflare keeps its proxy)."""
    m = _by_name(master)
    theirs = {sid: _by_name(s["records"]) for sid, s in snapshots.items() if s.get("ok")}
    new_master: dict[str, list[Record]] = {}
    ops: dict = {sid: [] for sid in theirs}
    for name, action in decisions.items():
        if action in (None, "", "skip"):
            continue
        if action == "delete":
            desired = []
            if m.get(name):
                new_master[name] = []
        elif action == "master":
            desired = m.get(name, [])
        elif action.startswith("server:"):
            sid = int(action.split(":", 1)[1])
            if sid not in theirs:
                raise ValueError(f"{name}: that server could not be read")
            desired = [Record(r.name, r.type, r.value, r.ttl) for r in theirs[sid].get(name, [])]
            if _keys(desired) != _keys(m.get(name)):
                new_master[name] = desired
        else:
            raise ValueError(f"{name}: unknown decision {action!r}")
        for sid, held in theirs.items():
            if not _holds(snapshots[sid], name):
                continue
            types = set(snapshots[sid].get("types") or ())
            want = {r.key: r for r in desired if not types or r.type in types}
            have = {r.key: r for r in held.get(name, [])}
            gone = [r for k, r in have.items() if k not in want]
            new = [r for k, r in want.items() if k not in have]
            for t in {r.type for r in gone} & {r.type for r in new}:
                g, n = [r for r in gone if r.type == t], [r for r in new if r.type == t]
                if len(g) == 1 and len(n) == 1:
                    ops[sid].append({"op": "update", "record": n[0], "old": g[0]})
                    gone.remove(g[0])
                    new.remove(n[0])
            ops[sid] += [{"op": "delete", "record": r, "old": None} for r in gone] + [{"op": "add", "record": r, "old": None} for r in new]
    return {"master": new_master, "ops": {sid: o for sid, o in ops.items() if o}}


def _op(o: dict) -> dict:
    d = {"op": o["op"], **o["record"].as_dict()}
    if o.get("old") is not None:
        d["was"] = o["old"].value
    return d


# ---------------------------------------------------------------- against the real servers

def _holds(snap: dict, name: str) -> bool:
    """Whether a server (its snapshot) is compared on name: in its zones, and not one of the names it leaves out."""
    return under(name, snap.get("covers")) and not excluded(name, snap.get("excludes"))


def snapshot(servers: list[dict]) -> dict:
    """Read every server at once: {id: {"ok", "records", "types", "error"}}."""
    def read(s):
        try:
            with model.provider(s) as p:
                covers, excludes = p.covers(), p.excludes()
                recs = [r for r in p.list() if r.type in p.types and under(r.name, covers) and not excluded(r.name, excludes)]
                return s["id"], {"ok": True, "records": recs, "types": list(p.types), "covers": covers, "excludes": excludes, "error": None}
        except (ProviderError, ValueError, KeyError) as e:
            return s["id"], {"ok": False, "records": [], "types": [], "covers": None, "error": str(e)}
    if not servers:
        return {}
    with ThreadPoolExecutor(max_workers=min(8, len(servers))) as ex:
        return dict(ex.map(read, servers))


def _targets(view_id: int) -> list[dict]:
    return [s for s in model.servers(view_id, targets_only=True) if s["enabled"]]


def status(view_slug: str, refresh_sources: bool = True, by: str | None = None) -> dict:
    """The comparison of one view, as the web app draws it."""
    from app import sources
    v = model.view(view_slug)
    notes = sources.refresh(by) if refresh_sources else []
    targets = _targets(v["id"])
    snaps = snapshot(targets)
    out = compare(model.master(v["id"]), snaps)
    for s in targets:
        sn = snaps[s["id"]]
        model.record_check(s["id"], sn["ok"], sn["error"] or f"{len(sn['records'])} records", out["differences"].get(s["id"]) if sn["ok"] else None)
    out["view"] = v
    out["servers"] = [{"id": s["id"], "name": s["name"], "kind": s["kind"], "kindLabel": s["kindLabel"], "ok": snaps[s["id"]]["ok"],
                       "error": snaps[s["id"]]["error"], "count": len(snaps[s["id"]]["records"]), "types": snaps[s["id"]]["types"],
                       "differences": out["differences"].get(s["id"])} for s in targets]
    out["notes"] = notes
    for r in out["rows"]:
        r["servers"] = {str(k): c for k, c in r["servers"].items()}
    del out["differences"]
    return out


def apply(view_slug: str, decisions: dict, by: str | None, dry_run: bool = False) -> dict:
    """Carry out decisions ({name: action}) in one view: the master list first, then every server. Returns what was
    done, per server, with the errors."""
    v = model.view(view_slug)
    with _lock:
        targets = _targets(v["id"])
        snaps = snapshot(targets)
        p = plan(model.master(v["id"]), snaps, decisions)
        result = {"master": {n: [r.as_dict() for r in rs] for n, rs in p["master"].items()},
                  "servers": [], "dryRun": dry_run}
        if dry_run:
            names = {s["id"]: s["name"] for s in targets}
            result["servers"] = [{"id": sid, "name": names[sid], "ops": [_op(o) for o in ops], "errors": []} for sid, ops in p["ops"].items()]
            return result
        for name, recs in p["master"].items():
            model.set_view_records(v["id"], name, recs, by)
        if p["master"]:
            model.log(by, "resolve", detail=f"{v['name']}: " + "; ".join(f"{n} ← {', '.join(r.type + ' ' + r.value for r in rs) or 'removed'}"
                                                                    for n, rs in p["master"].items()))
        by_id = {s["id"]: s for s in targets}

        def run(sid):
            s, done, errors = by_id[sid], [], []
            try:
                with model.provider(s) as prov:
                    for o in sorted(p["ops"][sid], key=lambda x: x["op"] != "delete"):  # deletes first: a CNAME may replace an A
                        r = o["record"]
                        try:
                            if o["op"] == "delete":
                                prov.delete(r)
                            elif o["op"] == "update":
                                prov.replace(o["old"], r)
                            else:
                                prov.add(r)
                            done.append(_op(o))
                        except AnsweredElsewhere as e:
                            model.leave_out(sid, e.name, by)
                            errors.append(f"{o['op']} {r.name} {r.type} {r.value}: {e}")
                        except ProviderError as e:
                            errors.append(f"{o['op']} {r.name} {r.type} {r.value}: {e}")
            except ProviderError as e:
                errors.append(str(e))
            return {"id": sid, "name": s["name"], "ops": done, "errors": errors}

        # the DNS servers first, then the tunnels: a tunnel's hostname takes over its name's CNAME once the DNS server
        # has removed what it held for that name (the other way round, the DNS server would remove the tunnel's CNAME)
        tunnels = [sid for sid in p["ops"] if "TUNNEL" in providers.get(by_id[sid]["kind"]).types]
        for phase in ([sid for sid in p["ops"] if sid not in tunnels], tunnels):
            if phase:
                with ThreadPoolExecutor(max_workers=min(8, len(phase))) as ex:
                    result["servers"] += list(ex.map(run, phase))
        for r in result["servers"]:
            lines = [f"{o['op']} {o['name']} {o['type']} {o['value']}" + (f" (was {o['was']})" if o.get("was") else "") for o in r["ops"]]
            lines += [f"failed: {e}" for e in r["errors"]]
            model.log(by, "push", r["id"], r["name"], "\n".join(lines), ok=not r["errors"])
        return result


def push_all(view_slug: str, by: str | None, prune: bool = False, dry_run: bool = False) -> dict:
    """Every server of the view made to hold the master list (prune: also remove the names only the servers hold)."""
    v = model.view(view_slug)
    snaps = snapshot(_targets(v["id"]))
    rows = compare(model.master(v["id"]), snaps)["rows"]
    decisions = {}
    for r in rows:
        if r["state"] == "ok":
            continue
        decisions[r["name"]] = "master" if r["master"] else ("delete" if prune else "skip")
    return apply(view_slug, decisions, by, dry_run)


def push_names(names: list[str] | None, by: str | None, dry_run: bool = False) -> dict:
    """Push what the master list says about some names to every server of every view, right after they were added,
    changed or removed (a name the master list no longer holds is removed from the servers that hold it). names None:
    every difference of every view, without removing the extras (after an import). Returns {"views": [{"view", "name",
    "servers"}]}, only the views where something was (or would be) done."""
    out = []
    for v in model.views():
        if not _targets(v["id"]):
            continue
        if names is None:
            r = push_all(v["slug"], by, False, dry_run)
        else:
            r = apply(v["slug"], {model.norm_name(n): "master" for n in names if str(n or "").strip()}, by, dry_run)
        if any(s["ops"] or s["errors"] for s in r["servers"]):
            out.append({"view": v["slug"], "name": v["name"], "servers": r["servers"]})
    return {"views": out, "dryRun": dry_run}


def import_from(server_id: int, mode: str, by: str | None) -> dict:
    """The master list's records in the server's view, from that server:

        merge      names the master list lacks are added; where both hold a name, the master list's records stay
        overwrite  as merge, but where both hold a name, the server's records win
        replace    the master list's records in that view become exactly the server's
    """
    if mode not in ("merge", "overwrite", "replace"):
        raise ValueError("mode: merge, overwrite or replace")
    s = model.server(server_id)
    if not s["target"] or not s["viewId"]:
        raise ValueError(f"{s['name']} holds no records to import")
    snaps = snapshot([s])
    sn = snaps[s["id"]]
    if not sn["ok"]:
        raise ProviderError(sn["error"])
    theirs = _by_name(sn["records"])
    mine = {n: rs for n, rs in _by_name(model.master(s["viewId"])).items() if _holds(sn, n)}
    added = changed = removed = 0
    for name, recs in theirs.items():
        if name not in mine:
            model.set_view_records(s["viewId"], name, recs, by)
            added += 1
        elif mode in ("overwrite", "replace") and _keys(recs) != _keys(mine[name]):
            model.set_view_records(s["viewId"], name, recs, by)
            changed += 1
    if mode == "replace":
        for name, recs in mine.items():
            types = set(sn["types"])
            if name not in theirs and any(r.type in types for r in recs):
                model.set_view_records(s["viewId"], name, [r for r in recs if r.type not in types], by)
                removed += 1
    model.log(by, "import", s["id"], s["name"], f"{mode}: {added} added, {changed} changed, {removed} removed")
    return {"added": added, "changed": changed, "removed": removed, "records": len(sn["records"])}


# ---------------------------------------------------------------- the check in the background

def check_all() -> None:
    """Compare every view (the servers' dots and counts in the web app stay current)."""
    for v in model.views():
        if model.servers(v["id"], targets_only=True):
            status(v["slug"], refresh_sources=False)


def start_checks(minutes: int) -> None:
    if minutes <= 0:
        return
    import logging
    log = logging.getLogger("iodns")

    def loop():
        import time
        from app import sources
        time.sleep(60)
        while True:
            try:
                sources.refresh()
                check_all()
            except Exception:  # a database or a server away: next time
                log.exception("background check")
            time.sleep(minutes * 60)

    threading.Thread(target=loop, name="iodns-check", daemon=True).start()
