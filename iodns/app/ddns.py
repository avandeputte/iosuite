"""Dynamic DNS: records whose value is the house's public address.

A record's source "publicip" holds the public IPv4 address (an A record), "publicip6" the IPv6 one (AAAA). Every few
minutes (Settings › Dynamic DNS) ioDNS finds the public address; when it changed, those records take the new one and
every server holding them (Cloudflare…) is brought up to date at once, without anyone looking.

Where the address comes from (the setting ddns_detect):

    auto           an address-echo service: api.ipify.org / api64.ipify.org, then icanhazip.com, then ifconfig.co
    unifi:<id>     the WAN address the UniFi gateway reports (its health page), so nothing outside the house is asked
    <https URL>    any page that answers with the address alone
"""
from __future__ import annotations

import ipaddress
import logging
import threading
import time

import httpx

from app import db, model

log = logging.getLogger("iodns")

SOURCES = {"publicip": "A", "publicip6": "AAAA"}
ECHO = {4: ["https://api.ipify.org", "https://ipv4.icanhazip.com", "https://ifconfig.co/ip"],
        6: ["https://api64.ipify.org", "https://ipv6.icanhazip.com"]}
_lock = threading.Lock()
_here = threading.local()


def settings() -> dict:
    return {"detect": db.get_setting("ddns_detect", "auto") or "auto",
            "minutes": int(db.get_setting("ddns_minutes", "5") or 5),
            "ipv4": db.get_setting("public_ipv4") or None, "ipv6": db.get_setting("public_ipv6") or None,
            "checkedAt": db.get_setting("public_checked_at") or None, "error": db.get_setting("public_error") or None,
            "records": db.one("SELECT count(*) AS n FROM dns_records WHERE source IN ('publicip', 'publicip6')")["n"]}


def save_settings(body: dict) -> dict:
    if "detect" in body:
        d = str(body["detect"] or "auto").strip()
        if d != "auto" and not d.startswith("unifi:") and not d.startswith("https://") and not d.startswith("http://"):
            raise ValueError("detect: auto, unifi:<server id>, or the address of a page that answers with the IP")
        if d.startswith("unifi:"):
            s = model.server(int(d.split(":", 1)[1]))
            if s["kind"] != "unifi":
                raise ValueError(f"{s['name']} is not a UniFi gateway")
        db.set_setting("ddns_detect", d)
    if "minutes" in body:
        m = int(body["minutes"])
        if not 0 <= m <= 1440:
            raise ValueError("Every 1 to 1440 minutes (0: never on its own)")
        db.set_setting("ddns_minutes", str(m))
    return settings()


def _valid(text: str, version: int) -> str | None:
    try:
        ip = ipaddress.ip_address(str(text or "").strip())
    except ValueError:
        return None
    if ip.version != version or ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified:
        return None
    return str(ip)


def _echo(urls: list[str], version: int) -> str | None:
    for u in urls:
        try:
            r = httpx.get(u, timeout=8, headers={"User-Agent": "iodns", "Accept": "text/plain"})
            ip = _valid(r.text, version) if r.status_code == 200 else None
            if ip:
                return ip
        except httpx.HTTPError:
            continue
    return None


def _unifi_wan(sid: int) -> str | None:
    s = model.server(sid)
    with model.provider(s) as p:
        site = p.site
        r = p.request("GET", f"/proxy/network/api/s/{site}/stat/health", headers=p._h()).json()
    for sub in r.get("data") or []:
        if sub.get("subsystem") == "wan" and _valid(sub.get("wan_ip"), 4):
            return sub["wan_ip"]
    return None


def detect() -> dict:
    """The public addresses now: {ipv4, ipv6} (None where there is none)."""
    how = settings()["detect"]
    v4 = v6 = None
    if how.startswith("unifi:"):
        v4 = _unifi_wan(int(how.split(":", 1)[1]))
    elif how.startswith("http"):
        v4 = _echo([how], 4)
        v6 = _echo([how], 6)
    if not v4:
        v4 = _echo(ECHO[4], 4)
    if not v6:
        v6 = _echo(ECHO[6], 6)
    return {"ipv4": v4, "ipv6": v6}


def address(source: str) -> str | None:
    """The public address a source stands for, as last found (None: not found yet)."""
    if source == "publicip":
        return db.get_setting("public_ipv4") or None
    if source == "publicip6":
        return db.get_setting("public_ipv6") or None
    return None


def run(by: str | None = None, force_push: bool = False) -> dict:
    """Find the public address; when it changed (or force_push), the publicip records take it and their servers are
    updated. Returns {ipv4, ipv6, changed, pushed: [view results]}."""
    with _lock:
        _here.running = True  # sources.resolve looks here: it must not start a second run from inside this one
        try:
            return _run(by, force_push)
        finally:
            _here.running = False


def running() -> bool:
    """Is this thread inside run()? (Its lock is not one to take twice.)"""
    return getattr(_here, "running", False)


def _run(by: str | None, force_push: bool) -> dict:
    from app import sources, sync
    before = (db.get_setting("public_ipv4"), db.get_setting("public_ipv6"))
    try:
        now = detect()
    except Exception as e:  # a gateway away, no network: try again next time
        db.set_setting("public_error", str(e)[:500])
        raise
    db.set_setting("public_checked_at", str(int(time.time())))
    if not now["ipv4"] and not now["ipv6"]:
        db.set_setting("public_error", "No public address found")
        return {**now, "changed": False, "pushed": []}
    db.set_setting("public_error", None)
    if now["ipv4"]:
        db.set_setting("public_ipv4", now["ipv4"])
    if now["ipv6"]:
        db.set_setting("public_ipv6", now["ipv6"])
    changed = (now["ipv4"] or before[0], now["ipv6"] or before[1]) != before
    pushed = []
    if changed:
        model.log(by, "ddns", detail=f"public address {before[0] or '-'} → {now['ipv4'] or before[0] or '-'}"
                  + (f", {before[1] or '-'} → {now['ipv6']}" if now["ipv6"] and now["ipv6"] != before[1] else ""))
    if changed or force_push:
        sources.refresh(by)
        rows = db.q("SELECT DISTINCT e.name, v.slug FROM dns_records r JOIN dns_entries e ON e.id = r.entry_id "
                    "JOIN dns_views v ON v.id = r.view_id WHERE r.source IN ('publicip', 'publicip6')")
        per_view: dict = {}
        for r in rows:
            per_view.setdefault(r["slug"], {})[r["name"]] = "master"
        for slug, decisions in per_view.items():
            pushed.append({"view": slug, **sync.apply(slug, decisions, by or "dynamic DNS")})
    return {**now, "changed": changed, "pushed": pushed}


def start() -> None:
    def loop():
        time.sleep(20)
        while True:
            minutes = 5
            try:
                minutes = settings()["minutes"]
                if minutes and settings()["records"]:
                    run()
            except Exception:
                log.exception("dynamic DNS")
            time.sleep(max(1, minutes or 5) * 60)

    threading.Thread(target=loop, name="iodns-ddns", daemon=True).start()
