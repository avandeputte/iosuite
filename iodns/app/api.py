"""The REST API the web app uses (and anyone with an app password: HTTP Basic or a bearer token). JSON in and out.
Who may call each route is on the route (app/access.py)."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool

from app import access, ddns, model, providers, sources, sync
from app.providers import ProviderError

router = APIRouter(prefix="/api")


def who(request: Request) -> str | None:
    u = request.state.user
    return u["name"] if u else None


async def body(request: Request) -> dict:
    if not (await request.body()).strip():
        return {}
    try:
        b = await request.json()
    except ValueError:
        raise ValueError("The body is not JSON") from None
    if not isinstance(b, dict):
        raise ValueError("The body is a JSON object")
    return b


# ---------------------------------------------------------------- overview

@router.get("/overview", dependencies=[access.signed_in])
def overview():
    """Everything the web app draws its frame from: the views, the servers (with their last check), the kinds of
    server ioDNS knows, the dynamic DNS state and how many entries the master list holds."""
    return {"views": model.views(), "servers": model.servers(), "providers": [c.describe() for c in providers.KINDS.values()],
            "ddns": ddns.settings(), "entries": len(model.entries()), "types": list(providers.TYPES)}


@router.get("/providers", dependencies=[access.signed_in])
def provider_kinds():
    return {"items": [c.describe() for c in providers.KINDS.values()]}


# ---------------------------------------------------------------- views

@router.get("/views", dependencies=[access.signed_in])
def list_views():
    return {"items": model.views()}


@router.post("/views", dependencies=[access.admin_write])
async def add_view(request: Request):
    return model.save_view(await body(request))


@router.patch("/views/{vid}", dependencies=[access.admin_write])
async def change_view(vid: int, request: Request):
    return model.save_view(await body(request), vid)


@router.delete("/views/{vid}", dependencies=[access.admin_write])
def remove_view(vid: int):
    model.delete_view(vid)
    return {"ok": True}


# ---------------------------------------------------------------- the master list

@router.get("/entries", dependencies=[access.signed_in])
def list_entries():
    return {"items": model.entries()}


@router.post("/entries", dependencies=[access.editor_write])
async def add_entry(request: Request):
    b = await body(request)
    return await run_in_threadpool(model.save_entry, b, who(request))


@router.get("/entries/{eid}", dependencies=[access.signed_in])
def get_entry(eid: int):
    return model.entry(eid)


@router.put("/entries/{eid}", dependencies=[access.editor_write])
async def change_entry(eid: int, request: Request):
    b = await body(request)
    return await run_in_threadpool(model.save_entry, {**b, "replaceAll": True}, who(request), eid)


@router.delete("/entries/{eid}", dependencies=[access.editor_write])
def remove_entry(eid: int, request: Request):
    model.delete_entry(eid, who(request))
    return {"ok": True}


@router.get("/export", dependencies=[access.signed_in])
def export():
    """The master list as JSON (views and entries), the shape POST /api/import/file takes back."""
    return model.export()


@router.post("/import/file", dependencies=[access.editor_write])
async def import_file(request: Request):
    """{data: <an export>, replace: bool}: entries added or replaced by name; replace: the others go."""
    b = await body(request)
    data = b.get("data")
    if not isinstance(data, dict):
        raise ValueError("data: an ioDNS export")
    return await run_in_threadpool(model.import_json, data, who(request), bool(b.get("replace")))


# ---------------------------------------------------------------- servers

@router.get("/servers", dependencies=[access.signed_in])
def list_servers():
    return {"items": model.servers()}


@router.post("/servers", dependencies=[access.admin_write])
async def add_server(request: Request):
    return model.save_server(await body(request), who(request))


@router.patch("/servers/{sid}", dependencies=[access.admin_write])
async def change_server(sid: int, request: Request):
    return model.save_server(await body(request), who(request), sid)


@router.delete("/servers/{sid}", dependencies=[access.admin_write])
def remove_server(sid: int, request: Request):
    model.delete_server(sid, who(request))
    return {"ok": True}


def _test(s: dict, secret: str) -> dict:
    cls = providers.get(s["kind"])
    try:
        with cls({**s, "options": dict(s.get("options") or {})}, secret) as p:
            return {"ok": True, "message": p.test()}
    except (ProviderError, ValueError) as e:
        return {"ok": False, "message": str(e)}


@router.post("/servers/test", dependencies=[access.admin_write])
async def test_unsaved(request: Request):
    """Try the server form before saving it: {kind, url, options, secret, id?} (no secret: the saved one of id)."""
    b = await body(request)
    secret = b.get("secret")
    if secret is None and b.get("id"):
        secret = model.secret(int(b["id"]))
    s = {"name": b.get("name") or b.get("kind"), "kind": str(b.get("kind") or ""), "url": str(b.get("url") or ""), "options": b.get("options") or {}}
    return await run_in_threadpool(_test, s, secret or "")


@router.post("/servers/{sid}/test", dependencies=[access.admin_write])
async def test_server(sid: int):
    s = model.server(sid)
    r = await run_in_threadpool(_test, s, model.secret(sid))
    model.record_check(sid, r["ok"], r["message"], s["check"]["differences"])
    return r


@router.post("/servers/{sid}/import", dependencies=[access.editor_write])
async def import_server(sid: int, request: Request):
    """The master list's records in the server's view, from it: {mode: merge | overwrite | replace}."""
    b = await body(request)
    return await run_in_threadpool(sync.import_from, sid, str(b.get("mode") or "merge"), who(request))


def _tailscale(sid: int):
    s = model.server(sid)
    if s["kind"] != "tailscale":
        raise ValueError(f"{s['name']} is not a Tailscale entry")
    return model.provider(s)


@router.get("/servers/{sid}/devices", dependencies=[access.signed_in])
def tailscale_devices(sid: int):
    """A Tailscale entry's devices, for the record form's device picker."""
    with _tailscale(sid) as p:
        return {"items": p.devices()}


@router.get("/servers/{sid}/tunnels", dependencies=[access.signed_in])
def cloudflare_tunnels(sid: int):
    """A Cloudflare Tunnel entry's tunnels, for the record form's tunnel picker."""
    s = model.server(sid)
    if s["kind"] != "cftunnel":
        raise ValueError(f"{s['name']} is not a Cloudflare Tunnel entry")
    with model.provider(s) as p:
        return {"items": p.tunnel_list()}


@router.get("/servers/{sid}/split-dns", dependencies=[access.admin])
def get_split_dns(sid: int):
    with _tailscale(sid) as p:
        return {"domains": p.split_dns()}


@router.put("/servers/{sid}/split-dns", dependencies=[access.admin_write])
async def put_split_dns(sid: int, request: Request):
    """{domain, nameservers: [address]} (none: stop sending the domain anywhere special)."""
    b = await body(request)

    def run():
        with _tailscale(sid) as p:
            out = p.set_split_dns(str(b.get("domain") or ""), b.get("nameservers") or [])
        model.log(who(request), "tailscale", sid, model.server(sid)["name"], f"split DNS {b.get('domain')} → {', '.join(b.get('nameservers') or []) or 'off'}")
        return {"domains": out}
    return await run_in_threadpool(run)


# ---------------------------------------------------------------- comparing and pushing

@router.get("/sync/{view}", dependencies=[access.signed_in])
async def compare(view: str, request: Request):
    """Every server of the view read and compared with the master list, name by name (sync.compare says how)."""
    return await run_in_threadpool(sync.status, view, True, who(request))


@router.post("/sync/{view}/apply", dependencies=[access.editor_write])
async def apply(view: str, request: Request):
    """{decisions: {name: master | server:<id> | delete | skip}, dryRun}: the master list first, then the servers."""
    b = await body(request)
    decisions = b.get("decisions") or {}
    if not isinstance(decisions, dict):
        raise ValueError("decisions: {name: action}")
    return await run_in_threadpool(sync.apply, view, {str(k): str(v) for k, v in decisions.items()}, who(request), bool(b.get("dryRun")))


@router.post("/sync/{view}/push", dependencies=[access.editor_write])
async def push(view: str, request: Request):
    """Every server of the view made to hold the master list: {prune: also remove names only the servers hold, dryRun}."""
    b = await body(request)
    return await run_in_threadpool(sync.push_all, view, who(request), bool(b.get("prune")), bool(b.get("dryRun")))


@router.post("/push", dependencies=[access.editor_write])
async def push_names(request: Request):
    """{names: [...] | null, dryRun}: the master list's word on those names pushed to every view's servers at once (what
    the web app offers right after an entry is saved or deleted; names null: everything that differs, after an import)."""
    b = await body(request)
    names = b.get("names")
    if names is not None and not isinstance(names, list):
        raise ValueError("names: a list of names, or null")
    return await run_in_threadpool(sync.push_names, names, who(request), bool(b.get("dryRun")))


@router.post("/sources/refresh", dependencies=[access.editor_write])
async def refresh_sources(request: Request):
    """Read the Tailscale device addresses and the public address again for the records that follow them."""
    return {"notes": await run_in_threadpool(sources.refresh, who(request))}


# ---------------------------------------------------------------- dynamic DNS

@router.get("/ddns", dependencies=[access.signed_in])
def get_ddns():
    return ddns.settings()


@router.put("/ddns", dependencies=[access.admin_write])
async def put_ddns(request: Request):
    """{detect: auto | unifi:<server id> | https://…, minutes}"""
    return ddns.save_settings(await body(request))


@router.post("/ddns/run", dependencies=[access.editor_write])
async def run_ddns(request: Request):
    """Find the public address now; {push: true} pushes the records that follow it even when it did not change."""
    b = await body(request)
    return await run_in_threadpool(ddns.run, who(request), bool(b.get("push")))


# ---------------------------------------------------------------- history (/api/log is the server log, iosuite-shared's)

@router.get("/history", dependencies=[access.signed_in])
def history(limit: int = 200):
    """What was changed where, and by whom: edits, pushes, imports, dynamic DNS."""
    return {"items": model.log_items(limit)}
