"""Tailscale: not a DNS server ioDNS pushes to, but a source of addresses, and the place split DNS is set up.

Tailscale's MagicDNS answers for device names only (nas.tailXXXX.ts.net) and holds no records of your own. So the
Tailscale view's answers live on a DNS server reachable over the tailnet (a Pi-hole or AdGuard Home), and Tailscale
sends the domain's queries there (split DNS). ioDNS helps on both ends:

- **Device addresses**: a master entry's Tailscale value can name a device ("the tailnet address of nas") instead of
  an address; ioDNS reads the devices from the API before every sync, so the record follows the device.
- **Split DNS**: Settings › Servers › (the Tailscale entry) › Split DNS points a domain at the tailnet DNS server.

    GET   https://api.tailscale.com/api/v2/tailnet/<tailnet>/devices    -> {devices: [{id, name, hostname, addresses}]}
    GET   https://api.tailscale.com/api/v2/tailnet/<tailnet>/dns/split-dns   -> {domain: [nameserver, ...]}
    PATCH https://api.tailscale.com/api/v2/tailnet/<tailnet>/dns/split-dns   {domain: [nameserver, ...] | null}

The key is an API access token (Admin console › Settings › Keys › Generate access token), or an OAuth client's
secret with the devices:read and dns scopes, sent as a bearer token; "-" names the key's own tailnet.
"""
import ipaddress
from urllib.parse import quote

from app.providers import Provider, ProviderError, register, norm_name

API = "https://api.tailscale.com/api/v2"


@register
class Tailscale(Provider):
    kind = "tailscale"
    label = "Tailscale (device addresses, split DNS)"
    target = False   # nothing is pushed to it: it is read for addresses
    fields = [
        {"key": "tailnet", "label": "Tailnet", "type": "text", "default": "-", "hint": "- (the key's own), or example.com / you@github"},
        {"key": "secret", "label": "API access token", "type": "password", "hint": "tskey-api-… (Settings › Keys), or an OAuth client secret"},
        {"key": "url", "label": "API address", "type": "url", "default": API, "hint": "leave as it is (Headscale and tests change it)"},
    ]

    def __init__(self, server: dict, secret: str = ""):
        super().__init__(server, secret)
        self.url = self.url or API
        self.tailnet = quote(str(self.options.get("tailnet") or "-").strip() or "-", safe="@.-_")
        self.options.setdefault("verifyTls", True)

    def _h(self) -> dict:
        if not self.secret:
            raise ProviderError(f"{self.server.get('name') or 'Tailscale'}: no API access token")
        return {"Authorization": f"Bearer {self.secret}", "Accept": "application/json"}

    def devices(self) -> list[dict]:
        """Every device of the tailnet: {id, name (short), fqdn, ipv4, ipv6, os, online}."""
        r = self.request("GET", f"/tailnet/{self.tailnet}/devices", headers=self._h()).json()
        out = []
        for d in r.get("devices") or []:
            fqdn = str(d.get("name") or "").rstrip(".")
            v4 = v6 = None
            for a in d.get("addresses") or []:
                try:
                    ip = ipaddress.ip_address(a)
                except ValueError:
                    continue
                if ip.version == 4 and not v4:
                    v4 = str(ip)
                elif ip.version == 6 and not v6:
                    v6 = str(ip)
            out.append({"id": str(d.get("id") or d.get("nodeId") or ""), "name": fqdn.split(".")[0] or str(d.get("hostname") or ""),
                        "fqdn": fqdn, "hostname": d.get("hostname"), "ipv4": v4, "ipv6": v6, "os": d.get("os"),
                        "online": d.get("connectedToControl")})
        return sorted(out, key=lambda d: d["name"].lower())

    @staticmethod
    def address(devices: list[dict], device: str, type_: str) -> str | None:
        """The tailnet address of a device (of devices()), named by its id, short name or full name (None: no such device)."""
        want = str(device or "").strip().lower().rstrip(".")
        for d in devices:
            if want in (d["id"].lower(), d["name"].lower(), d["fqdn"].lower(), str(d.get("hostname") or "").lower()):
                return d["ipv6"] if type_ == "AAAA" else d["ipv4"]
        return None

    def split_dns(self) -> dict:
        return self.request("GET", f"/tailnet/{self.tailnet}/dns/split-dns", headers=self._h()).json() or {}

    def set_split_dns(self, domain: str, nameservers: list[str] | None) -> dict:
        """Point a domain at nameservers on the tailnet (None or []: stop)."""
        domain = norm_name(domain)
        ns = []
        for n in nameservers or []:
            try:
                ns.append(str(ipaddress.ip_address(str(n).strip())))
            except ValueError:
                raise ValueError(f"Not an address: {n!r}") from None
        return self.request("PATCH", f"/tailnet/{self.tailnet}/dns/split-dns", headers=self._h(),
                            json={domain: ns or None}).json() or {}

    def test(self) -> str:
        n = len(self.devices())
        try:
            sd = self.split_dns()
            split = "; ".join(f"{d} → {', '.join(v)}" for d, v in sd.items() if v) or "no split DNS"
        except ProviderError:
            split = "split DNS not readable with this key"
        return f"Tailscale: {n} devices, {split}"

    def list(self):
        return []
