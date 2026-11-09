"""Pi-hole v6: Local DNS records and CNAME records (Settings › Local DNS), over the v6 REST API.

    POST   /api/auth {password}                     -> {session: {sid, csrf}}   (no password set: no session needed)
    GET    /api/config/dns/hosts                    -> {config: {dns: {hosts: ["192.168.1.10 nas.lan", ...]}}}
    PUT    /api/config/dns/hosts/<"ip name">        add one
    DELETE /api/config/dns/hosts/<"ip name">        remove one
    GET    /api/config/dns/cnameRecords             -> {config: {dns: {cnameRecords: ["alias,target[,ttl]", ...]}}}
    PUT / DELETE /api/config/dns/cnameRecords/<"alias,target">
    DELETE /api/auth                                 sign out (Pi-hole keeps a few sessions only)

The password is the web interface's, or better an app password (Settings › Web interface / API › Configure app
password). Pi-hole 5 has no API for local DNS: it is not supported.
"""
from urllib.parse import quote

from app.providers import Provider, Record, ProviderError, guess_type, record, register


@register
class PiHole(Provider):
    kind = "pihole"
    label = "Pi-hole (v6)"
    fields = [
        {"key": "url", "label": "Address", "type": "url", "hint": "http://192.168.1.3 (the web interface, without /admin)"},
        {"key": "secret", "label": "Password", "type": "password", "hint": "an app password (Settings › Web interface / API)"},
        {"key": "verifyTls", "label": "Check the HTTPS certificate", "type": "check", "default": False},
    ]

    sid = None

    def open(self) -> None:
        if not self.secret:
            return
        r = self.request("POST", "/api/auth", json={"password": self.secret}).json()
        s = r.get("session") or {}
        if not s.get("valid") and not s.get("sid"):
            raise ProviderError(f"{self.server.get('name') or self.url}: Pi-hole refused the password")
        self.sid = s.get("sid")

    def close(self) -> None:
        try:
            if self.sid:
                self.request("DELETE", "/api/auth", headers=self._h())
        finally:
            self.sid = None
            super().close()

    def _h(self) -> dict:
        return {"X-FTL-SID": self.sid} if self.sid else {}

    def _get(self, key: str) -> list:
        r = self.request("GET", f"/api/config/dns/{key}", headers=self._h()).json()
        return list(((r.get("config") or {}).get("dns") or {}).get(key) or [])

    def test(self) -> str:
        try:
            v = self.request("GET", "/api/info/version", headers=self._h()).json().get("version") or {}
            ver = ((v.get("core") or {}).get("local") or {}).get("version") or ""
        except (ProviderError, ValueError, AttributeError):
            ver = ""
        return f"Pi-hole {ver}, {len(self.list())} records".replace("  ", " ")

    def list(self) -> list[Record]:
        out = []
        for line in self._get("hosts"):
            parts = str(line).split()
            if len(parts) < 2:
                continue
            ip, names = parts[0], parts[1:]
            for n in names:
                try:
                    out.append(record(n, guess_type(ip), ip, ref=f"H\t{line}"))
                except ValueError:
                    continue
        for line in self._get("cnameRecords"):
            parts = [p.strip() for p in str(line).split(",")]
            if len(parts) < 2:
                continue
            ttl = int(parts[-1]) if len(parts) > 2 and parts[-1].isdigit() else None
            names = parts[:-2] if ttl is not None else parts[:-1]
            target = parts[-2] if ttl is not None else parts[-1]
            for n in names:
                try:
                    out.append(record(n, "CNAME", target, ttl, ref=f"C\t{line}"))
                except ValueError:
                    continue
        return out

    def add(self, r: Record) -> None:
        if r.type == "CNAME":
            entry = f"{r.name},{r.value}" + (f",{r.ttl}" if r.ttl else "")
            self.request("PUT", f"/api/config/dns/cnameRecords/{quote(entry, safe='')}", headers=self._h())
        else:
            self.request("PUT", f"/api/config/dns/hosts/{quote(f'{r.value} {r.name}', safe='')}", headers=self._h())

    def delete(self, r: Record) -> None:
        kind, line = (r.ref.split("\t", 1) if r.ref and "\t" in r.ref else ("C" if r.type == "CNAME" else "H", None))
        if line is None:
            line = f"{r.name},{r.value}" if r.type == "CNAME" else f"{r.value} {r.name}"
        key = "cnameRecords" if kind == "C" else "hosts"
        self.request("DELETE", f"/api/config/dns/{key}/{quote(line, safe='')}", headers=self._h())
        # a line can name several hosts ("192.168.1.10 nas nas.lan"): the others go back as lines of their own
        if kind == "H":
            parts = line.split()
            for n in parts[1:]:
                if n.lower().rstrip(".") != r.name:
                    self.request("PUT", f"/api/config/dns/hosts/{quote(f'{parts[0]} {n}', safe='')}", headers=self._h())
        else:
            parts = [p.strip() for p in line.split(",")]
            ttl = parts[-1] if len(parts) > 2 and parts[-1].isdigit() else None
            names = parts[:-2] if ttl else parts[:-1]
            target = parts[-2] if ttl else parts[-1]
            for n in names:
                if n.lower().rstrip(".") != r.name:
                    entry = f"{n},{target}" + (f",{ttl}" if ttl else "")
                    self.request("PUT", f"/api/config/dns/cnameRecords/{quote(entry, safe='')}", headers=self._h())

