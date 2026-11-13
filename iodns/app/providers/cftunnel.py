"""Cloudflare Tunnel: the public hostnames of your remotely managed tunnels (the ones set up in the dashboard,
Zero Trust › Networks › Tunnels, run with `cloudflared tunnel run --token …`), over the v4 API.

A public hostname is one TUNNEL record in the master list, in the view this entry answers for (External):
`calendar.example.com  TUNNEL  home|http://192.168.1.151:8620`, the tunnel's name and the service behind it. ioDNS
keeps both halves of it, as the dashboard does:

    the tunnel's ingress rule    GET / PUT /accounts/<account>/cfd_tunnel/<tunnel id>/configurations
                                 {config: {ingress: [{hostname, service, originRequest?}, …, {service: "http_status:404"}]}}
    its DNS record               a proxied CNAME to <tunnel id>.cfargotunnel.com in the hostname's zone

A rule with a path, the rules' origin settings and the catch-all at the end are kept as they are. Tunnels managed
with a config.yml on the machine (locally managed) cannot be changed through the API: they are listed, not read.

The API token needs Account › Cloudflare Tunnel › Edit and Zone › DNS › Edit (for the zones of the hostnames).
"""
from __future__ import annotations

from app.providers import ProviderError, Record, register, tunnel_value
from app.providers.cloudflare import API, TUNNEL_TARGET, Cloudflare

CATCH_ALL = {"service": "http_status:404"}


@register
class CloudflareTunnel(Cloudflare):
    kind = "cftunnel"
    label = "Cloudflare Tunnel"
    types = ("TUNNEL",)
    fields = [
        {"key": "secret", "label": "API token", "type": "password",
         "hint": "a token with Account › Cloudflare Tunnel › Edit and Zone › DNS › Edit"},
        {"key": "account", "label": "Account ID", "type": "text", "hint": "empty: the one account the token sees"},
        {"key": "zones", "label": "Zones", "type": "text", "hint": "example.com (empty: every zone the token can edit)"},
        {"key": "url", "label": "API address", "type": "url", "default": API, "hint": "leave as it is"},
    ]

    def __init__(self, server: dict, secret: str = ""):
        super().__init__(server, secret)
        self.account = str(self.options.get("account") or "").strip()
        self.tunnels: dict[str, dict] = {}  # name -> {id, name, status, remote}

    def _name(self) -> str:
        return self.server.get("name") or "Cloudflare Tunnel"

    def open(self) -> None:
        super().open()
        if not self.account:
            accounts = self._get("/accounts", per_page=50).get("result") or []
            if len(accounts) != 1:
                raise ProviderError(f"{self._name()}: the token sees {len(accounts)} accounts, give the account ID")
            self.account = accounts[0]["id"]
        page, found = 1, {}
        while True:
            r = self._get(f"/accounts/{self.account}/cfd_tunnel", is_deleted="false", page=page, per_page=100)
            for t in r.get("result") or []:
                if t.get("deleted_at"):
                    continue
                found[t["name"]] = {"id": t["id"], "name": t["name"], "status": t.get("status") or "",
                                    "remote": bool(t.get("remote_config")) or t.get("config_src") == "cloudflare"}
            info = r.get("result_info") or {}
            if page >= int(info.get("total_pages") or 1):
                break
            page += 1
        self.tunnels = found

    def tunnel_list(self) -> list[dict]:
        return sorted(self.tunnels.values(), key=lambda t: t["name"].lower())

    def _tunnel(self, name: str) -> dict:
        t = self.tunnels.get(name)
        if t is None:
            raise ProviderError(f"{self._name()}: no tunnel {name!r} (there are {', '.join(self.tunnels) or 'none'})")
        if not t["remote"]:
            raise ProviderError(f"{self._name()}: the tunnel {name!r} is managed with a config file on its machine, not from Cloudflare")
        return t

    def _cfg_path(self, tid: str) -> str:
        return f"/accounts/{self.account}/cfd_tunnel/{tid}/configurations"

    def _config(self, tid: str) -> dict:
        res = self._get(self._cfg_path(tid)).get("result") or {}
        cfg = dict(res.get("config") or {})
        cfg["ingress"] = list(cfg.get("ingress") or [])
        return cfg

    def _put(self, tid: str, cfg: dict) -> None:
        ingress = [r for r in cfg["ingress"] if r.get("hostname")]
        rest = [r for r in cfg["ingress"] if not r.get("hostname")]
        cfg["ingress"] = ingress + (rest[-1:] or [dict(CATCH_ALL)])  # the catch-all goes last, and there is one
        r = self.request("PUT", self._cfg_path(tid), headers=self._h(), json={"config": cfg}).json()
        if not r.get("success", True):
            raise ProviderError(f"Cloudflare: {r.get('errors')}")

    def test(self) -> str:
        local = [t["name"] for t in self.tunnel_list() if not t["remote"]]
        line = f"Cloudflare Tunnel: {len(self.tunnels)} tunnel(s) ({', '.join(t['name'] for t in self.tunnel_list()) or 'none'}), {len(self.list())} public hostnames"
        return line + (f"; managed on their machine, not read: {', '.join(local)}" if local else "")

    def list(self) -> list[Record]:
        out = []
        for t in self.tunnel_list():
            if not t["remote"]:
                continue
            for rule in self._config(t["id"])["ingress"]:
                if not rule.get("hostname") or rule.get("path"):
                    continue
                try:
                    out.append(Record(rule["hostname"].lower().rstrip("."), "TUNNEL", "|".join(tunnel_value(f"{t['name']}|{rule.get('service')}")),
                                      None, ref=t["id"]))
                except ValueError:
                    continue
        return out

    # ------------------------------------------------ the DNS half

    def _cname(self, name: str, target: str) -> None:
        """name a proxied CNAME to target, in its zone (a CNAME to elsewhere is changed; other records are an error)."""
        zid = self._zid(name)
        held = self.dns_records(name)
        others = [r for r in held if r.name == name and r.type != "CNAME"]
        if others:
            raise ProviderError(f"{name} has {', '.join(r.type + ' ' + r.value for r in others)} in Cloudflare DNS: a tunnel's name has no other records")
        mine = [r for r in held if r.name == name and r.type == "CNAME"]
        body = {"type": "CNAME", "name": name, "content": target, "ttl": 1, "proxied": True}
        if mine:
            if mine[0].value != target:
                z, rid = mine[0].ref.split("/", 1)
                self.request("PATCH", f"/zones/{z}/dns_records/{rid}", headers=self._h(), json={"content": target, "proxied": True})
        else:
            self.request("POST", f"/zones/{zid}/dns_records", headers=self._h(), json=body)

    def _uncname(self, name: str, target: str) -> None:
        if self._zone(name) is None:
            return
        for r in self.dns_records(name):
            if r.name == name and r.type == "CNAME" and r.value == target:
                z, rid = r.ref.split("/", 1)
                self.request("DELETE", f"/zones/{z}/dns_records/{rid}", headers=self._h())

    # ------------------------------------------------ records

    def add(self, r: Record) -> None:
        tname, service = tunnel_value(r.value)
        t = self._tunnel(tname)
        cfg = self._config(t["id"])
        rules = cfg["ingress"]
        for i, rule in enumerate(rules):
            if (rule.get("hostname") or "").lower() == r.name and not rule.get("path"):
                rules[i] = {**rule, "service": service}
                break
        else:
            rules.insert(0, {"hostname": r.name, "service": service})
        self._put(t["id"], cfg)
        self._cname(r.name, t["id"] + TUNNEL_TARGET)

    def delete(self, r: Record) -> None:
        tname, _ = tunnel_value(r.value)
        t = self._tunnel(tname)
        cfg = self._config(t["id"])
        keep = [x for x in cfg["ingress"] if not ((x.get("hostname") or "").lower() == r.name and not x.get("path"))]
        if len(keep) != len(cfg["ingress"]):
            cfg["ingress"] = keep
            self._put(t["id"], cfg)
        self._uncname(r.name, t["id"] + TUNNEL_TARGET)

    def replace(self, old: Record, new: Record) -> None:
        if tunnel_value(old.value)[0] == tunnel_value(new.value)[0]:
            self.add(new)  # the same tunnel: its rule changes service in place, the CNAME stays
        else:
            self.add(new)  # the other tunnel first: the CNAME moves to it, then the old rule goes
            t = self._tunnel(tunnel_value(old.value)[0])
            cfg = self._config(t["id"])
            cfg["ingress"] = [x for x in cfg["ingress"] if not ((x.get("hostname") or "").lower() == old.name and not x.get("path"))]
            self._put(t["id"], cfg)
