"""Values that come from somewhere else, read when the entry is saved and again before every comparison, so the record
follows them:

    tailscale:<server id>:<device>   the tailnet address of that device (Tailscale's API)
    publicip / publicip6             the house's public IPv4 / IPv6 address (dynamic DNS, app/ddns.py)
"""
from __future__ import annotations

from app import db, model
from app.providers import ProviderError

PREFIX = "tailscale:"


def parse(source: str) -> tuple[int, str]:
    s = str(source or "")
    if not s.startswith(PREFIX):
        raise ValueError(f"Unknown source {source!r}")
    sid, _, device = s[len(PREFIX):].partition(":")
    if not sid.isdigit() or not device:
        raise ValueError(f"Unknown source {source!r}")
    return int(sid), device


def make(server_id: int, device: str) -> str:
    return f"{PREFIX}{int(server_id)}:{device}"


def _tailscale(sid: int) -> dict:
    s = model.server(sid)
    if s["kind"] != "tailscale":
        raise ValueError(f"{s['name']} is not a Tailscale entry")
    return s


def resolve(source: str, type_: str, cache: dict | None = None) -> str:
    """The address the source names now (ValueError when the device or the server is gone)."""
    from app import ddns
    if source in ddns.SOURCES:
        if ddns.SOURCES[source] != type_:
            raise ValueError(f"The public {'IPv6' if source == 'publicip6' else 'IPv4'} address goes in an {ddns.SOURCES[source]} record")
        addr = ddns.address(source)
        if not addr:
            ddns.run()
            addr = ddns.address(source)
        if not addr:
            raise ValueError("The public address could not be found (Settings › Dynamic DNS)")
        return addr
    sid, device = parse(source)
    if cache is not None and sid in cache:
        devices = cache[sid]
    else:
        s = _tailscale(sid)
        with model.provider(s) as p:
            devices = p.devices()
        if cache is not None:
            cache[sid] = devices
    from app.providers.tailscale import Tailscale
    addr = Tailscale.address(devices, device, type_)
    if not addr:
        raise ValueError(f"Tailscale has no {'IPv6' if type_ == 'AAAA' else 'IPv4'} address for {device!r}")
    return addr


def refresh(by: str | None = None) -> list[str]:
    """Every record with a source, read again: the lines of what changed (or could not be read)."""
    rows = db.q("SELECT r.id, r.type, r.value, r.source, e.name FROM dns_records r JOIN dns_entries e ON e.id = r.entry_id "
                "WHERE r.source IS NOT NULL")
    cache, notes = {}, []
    for r in rows:
        try:
            v = resolve(r["source"], r["type"], cache)
        except (ValueError, ProviderError, model.NotFound) as e:
            notes.append(f"{r['name']}: {e}")
            continue
        if v != r["value"]:
            try:
                db.ex("UPDATE dns_records SET value = %s WHERE id = %s", (v, r["id"]))
            except db.pymysql.err.IntegrityError:  # the same address is in that view already
                db.ex("DELETE FROM dns_records WHERE id = %s", (r["id"],))
            notes.append(f"{r['name']}: {r['value']} → {v} (Tailscale)")
    if any("→" in n for n in notes):
        model.log(by, "tailscale", detail="\n".join(notes))
    return notes
