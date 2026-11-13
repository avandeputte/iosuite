"""Cloudflare DNS: the records of your zones, over the v4 API with an API token (My Profile › API Tokens › Create
Token › "Edit zone DNS", for the zones ioDNS keeps).

    GET    /client/v4/zones?name=<zone>                          -> {result: [{id, name}]}
    GET    /client/v4/zones/<zone id>/dns_records?page=&per_page= -> {result: [{id, type, name, content, ttl, proxied}], result_info}
    POST   /client/v4/zones/<zone id>/dns_records                 {type, name, content, ttl, proxied}
    PATCH  /client/v4/zones/<zone id>/dns_records/<id>            {content, ttl}   (a change keeps the record, its proxy and its comment)
    DELETE /client/v4/zones/<zone id>/dns_records/<id>

Only the names under the zones listed are compared (empty: every zone the token sees). New records are proxied or not
as the server's setting says; a record that changes keeps what it had. A TTL of 1 is Cloudflare's "automatic".

The CNAMEs of Cloudflare Tunnel public hostnames (<tunnel id>.cfargotunnel.com) belong to the Cloudflare Tunnel entry
(app/providers/cftunnel.py), which makes and removes them with the hostname: they are left out here unless asked.
"""
from __future__ import annotations

from app.providers import DNS_TYPES, Provider, ProviderError, Record, norm_name, record, register

API = "https://api.cloudflare.com/client/v4"
TUNNEL_TARGET = ".cfargotunnel.com"


@register
class Cloudflare(Provider):
    kind = "cloudflare"
    label = "Cloudflare DNS"
    fields = [
        {"key": "secret", "label": "API token", "type": "password", "hint": "a token with Zone › DNS › Edit for these zones"},
        {"key": "zones", "label": "Zones", "type": "text", "hint": "example.com, example.net (empty: every zone the token can edit)"},
        {"key": "proxied", "label": "Proxy new records through Cloudflare (orange cloud)", "type": "check", "default": False},
        {"key": "tunnels", "label": "Leave the tunnels' CNAMEs (….cfargotunnel.com) to the Cloudflare Tunnel entry", "type": "check",
         "default": True},
        {"key": "url", "label": "API address", "type": "url", "default": API, "hint": "leave as it is"},
    ]

    def __init__(self, server: dict, secret: str = ""):
        super().__init__(server, secret)
        self.url = self.url or API
        self.options.setdefault("verifyTls", True)
        self.zone_ids: dict[str, str] = {}

    @property
    def zones(self) -> list[str] | None:
        z = [norm_name(x) for x in str(self.options.get("zones") or "").replace(";", ",").split(",") if x.strip()]
        return z or None

    def _h(self) -> dict:
        if not self.secret:
            raise ProviderError(f"{self.server.get('name') or 'Cloudflare'}: no API token")
        return {"Authorization": f"Bearer {self.secret}", "Accept": "application/json"}

    def _get(self, path: str, **params) -> dict:
        r = self.request("GET", path, headers=self._h(), params=params).json()
        if not r.get("success", True):
            raise ProviderError(f"Cloudflare: {r.get('errors')}")
        return r

    def open(self) -> None:
        page, found = 1, {}
        while True:
            r = self._get("/zones", page=page, per_page=50)
            for z in r.get("result") or []:
                found[z["name"].lower()] = z["id"]
            info = r.get("result_info") or {}
            if page >= int(info.get("total_pages") or 1):
                break
            page += 1
        want = self.zones
        if want:
            missing = [z for z in want if z not in found]
            if missing:
                raise ProviderError(f"{self.server.get('name') or 'Cloudflare'}: the token cannot see {', '.join(missing)}")
            self.zone_ids = {z: found[z] for z in want}
        else:
            self.zone_ids = found

    def covers(self) -> list[str] | None:
        return self.zones or sorted(self.zone_ids)

    def _zone(self, name: str) -> str | None:
        best = None
        for z in self.zone_ids:
            if (name == z or name.endswith("." + z)) and (best is None or len(z) > len(best)):
                best = z
        return best

    def test(self) -> str:
        return f"Cloudflare: {len(self.zone_ids)} zone(s) ({', '.join(sorted(self.zone_ids)) or 'none'}), {len(self.list())} records"

    def list(self) -> list[Record]:
        skip = self.options.get("tunnels", True) is not False
        return [r for r in self.dns_records() if not (skip and r.type == "CNAME" and r.value.endswith(TUNNEL_TARGET))]

    def dns_records(self, name: str | None = None) -> list[Record]:
        out = []
        for z, zid in self.zone_ids.items():
            if name is not None and self._zone(name) != z:
                continue
            page = 1
            while True:
                r = self._get(f"/zones/{zid}/dns_records", page=page, per_page=1000, **({"name": name} if name else {}))
                for it in r.get("result") or []:
                    if it.get("type") not in DNS_TYPES:
                        continue
                    ttl = it.get("ttl")
                    try:
                        out.append(record(it["name"], it["type"], it["content"], ttl if ttl and ttl != 1 else None, ref=f"{zid}/{it['id']}"))
                    except ValueError:
                        continue
                info = r.get("result_info") or {}
                if page >= int(info.get("total_pages") or 1):
                    break
                page += 1
        return out

    def _zid(self, name: str) -> str:
        z = self._zone(name)
        if z is None:
            raise ProviderError(f"{name} is in none of the zones of {self.server.get('name') or 'Cloudflare'}")
        return self.zone_ids[z]

    def add(self, r: Record) -> None:
        tunnel = r.type == "CNAME" and r.value.endswith(TUNNEL_TARGET)  # a tunnel only answers through the proxy
        body = {"type": r.type, "name": r.name, "content": r.value, "ttl": r.ttl or 1,
                "proxied": tunnel or (bool(self.options.get("proxied")) and r.type in ("A", "AAAA", "CNAME"))}
        self.request("POST", f"/zones/{self._zid(r.name)}/dns_records", headers=self._h(), json=body)

    def delete(self, r: Record) -> None:
        ref = r.ref or ""
        if "/" not in ref:
            match = [x for x in self.list() if x.key == r.key]
            if not match:
                return
            ref = match[0].ref
        zid, rid = ref.split("/", 1)
        self.request("DELETE", f"/zones/{zid}/dns_records/{rid}", headers=self._h())

    def replace(self, old: Record, new: Record) -> None:
        if old.ref and "/" in old.ref and old.type == new.type:
            zid, rid = old.ref.split("/", 1)
            self.request("PATCH", f"/zones/{zid}/dns_records/{rid}", headers=self._h(), json={"content": new.value, "ttl": new.ttl or 1})
        else:
            super().replace(old, new)
