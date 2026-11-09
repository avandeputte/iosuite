"""UniFi: the gateway's local DNS records (Network › Settings › Policy Table › DNS, "DNS Records" on older versions),
over the Network application's API. Two ways in, picked per server:

- **API key** (UniFi Network 9.3 and later; Network › Settings › Control Plane › Integrations › Create API key): the
  official integration API, its DNS policies.

      GET    /proxy/network/integration/v1/sites                         -> {data: [{id, internalReference, name}]}
      GET    /proxy/network/integration/v1/sites/<site>/dns/policies     -> {data: [{id, type, domain, ipv4Address, ...}], totalCount}
      POST   /proxy/network/integration/v1/sites/<site>/dns/policies     {type: A_RECORD, enabled, domain, ipv4Address, ttlSeconds}
      DELETE /proxy/network/integration/v1/sites/<site>/dns/policies/<id>

- **Local account** (a UniFi OS local admin, for gateways without the integration API): the web app's own static DNS.

      POST   /api/auth/login {username, password}                        a session cookie, and X-CSRF-Token for changes
      GET    /proxy/network/v2/api/site/<site>/static-dns                -> [{_id, key, value, record_type, enabled, ttl}]
      POST   /proxy/network/v2/api/site/<site>/static-dns                {key, value, record_type, enabled, ttl}
      DELETE /proxy/network/v2/api/site/<site>/static-dns/<_id>

The gateway's certificate is its own unless you replaced it, so it is not checked unless asked.
"""
from app.providers import Provider, ProviderError, Record, record, register

INTEGRATION = "/proxy/network/integration/v1"
# the integration API's policy types; older Network versions answer "A", "AAAA", "CNAME"
TO_POLICY = {"A": "A_RECORD", "AAAA": "AAAA_RECORD", "CNAME": "CNAME_RECORD"}
FROM_POLICY = {"A_RECORD": "A", "AAAA_RECORD": "AAAA", "CNAME_RECORD": "CNAME", "A": "A", "AAAA": "AAAA", "CNAME": "CNAME"}
VALUE_FIELD = {"A": "ipv4Address", "AAAA": "ipv6Address", "CNAME": "targetDomain"}


@register
class UniFi(Provider):
    kind = "unifi"
    label = "UniFi gateway"
    fields = [
        {"key": "url", "label": "Address", "type": "url", "hint": "https://192.168.1.1 (the gateway or UniFi OS console)"},
        {"key": "mode", "label": "Sign in with", "type": "select", "default": "apikey",
         "options": [["apikey", "An API key (Network 9.3 and later)"], ["login", "A local admin account"]]},
        {"key": "username", "label": "User name", "type": "text", "hint": "local admin account only", "when": {"mode": "login"}},
        {"key": "secret", "label": "API key or password", "type": "password"},
        {"key": "site", "label": "Site", "type": "text", "default": "default", "hint": "default, unless you run several sites"},
        {"key": "verifyTls", "label": "Check the HTTPS certificate", "type": "check", "default": False},
    ]

    site_id = None
    csrf = None

    @property
    def mode(self) -> str:
        return "login" if self.options.get("mode") == "login" else "apikey"

    @property
    def site(self) -> str:
        return str(self.options.get("site") or "default").strip() or "default"

    def _h(self, write: bool = False) -> dict:
        h = {"Accept": "application/json"}
        if self.mode == "apikey":
            h["X-API-KEY"] = self.secret
        elif write and self.csrf:
            h["X-CSRF-Token"] = self.csrf
        return h

    def open(self) -> None:
        if self.mode == "login":
            r = self.request("POST", "/api/auth/login", json={"username": str(self.options.get("username") or ""), "password": self.secret,
                                                              "remember": False})
            self.csrf = r.headers.get("x-csrf-token") or r.headers.get("x-updated-csrf-token")
            return
        if not self.secret:
            raise ProviderError(f"{self.server.get('name') or self.url}: no API key")
        sites = self.request("GET", f"{INTEGRATION}/sites", params={"limit": 200}, headers=self._h()).json()
        for s in sites.get("data") or []:
            if self.site in (s.get("id"), s.get("internalReference"), s.get("name")):
                self.site_id = s["id"]
                return
        names = ", ".join(str(s.get("internalReference") or s.get("name")) for s in sites.get("data") or [])
        raise ProviderError(f"{self.server.get('name') or self.url}: no site {self.site!r} (there are: {names or 'none'})")

    def close(self) -> None:
        try:
            if self.mode == "login" and self.csrf is not None:
                self.request("POST", "/api/auth/logout", headers=self._h(True))
        finally:
            self.csrf = None
            super().close()

    # ---- the integration API (API key)
    def _policies(self) -> str:
        return f"{INTEGRATION}/sites/{self.site_id}/dns/policies"

    def _list_policies(self) -> list[Record]:
        out, offset = [], 0
        while True:
            page = self.request("GET", self._policies(), params={"offset": offset, "limit": 200}, headers=self._h()).json()
            items = page.get("data") or []
            for p in items:
                t = FROM_POLICY.get(str(p.get("type") or "").upper())
                if not t or p.get("enabled") is False:
                    continue
                try:
                    out.append(record(p.get("domain"), t, p.get(VALUE_FIELD[t]), p.get("ttlSeconds") or None, ref=str(p.get("id"))))
                except ValueError:
                    continue
            offset += len(items)
            if not items or offset >= int(page.get("totalCount") or 0):
                return out

    # ---- the web app's static DNS (local account)
    def _static(self) -> str:
        return f"/proxy/network/v2/api/site/{self.site}/static-dns"

    def _list_static(self) -> list[Record]:
        out = []
        for p in self.request("GET", self._static(), headers=self._h()).json() or []:
            t = str(p.get("record_type") or "").upper()
            if t not in VALUE_FIELD or p.get("enabled") is False:
                continue
            try:
                out.append(record(p.get("key"), t, p.get("value"), p.get("ttl") or None, ref=str(p.get("_id"))))
            except ValueError:
                continue
        return out

    def test(self) -> str:
        how = "API key" if self.mode == "apikey" else "local account"
        return f"UniFi ({how}, site {self.site}), {len(self.list())} DNS records"

    def list(self) -> list[Record]:
        return self._list_policies() if self.mode == "apikey" else self._list_static()

    def add(self, r: Record) -> None:
        if self.mode == "apikey":
            body = {"type": TO_POLICY[r.type], "enabled": True, "domain": r.name, VALUE_FIELD[r.type]: r.value, "ttlSeconds": r.ttl or 0}
            self.request("POST", self._policies(), json=body, headers=self._h(True))
        else:
            body = {"key": r.name, "value": r.value, "record_type": r.type, "enabled": True, "ttl": r.ttl or 0}
            self.request("POST", self._static(), json=body, headers=self._h(True))

    def delete(self, r: Record) -> None:
        if not r.ref:
            match = [x for x in self.list() if x.key == r.key]
            if not match:
                return
            r = match[0]
        path = f"{self._policies()}/{r.ref}" if self.mode == "apikey" else f"{self._static()}/{r.ref}"
        self.request("DELETE", path, headers=self._h(True))
