"""AdGuard Home: DNS rewrites (Filters › DNS rewrites), over its HTTP API with the web interface's user and password.

    GET  /control/rewrite/list                -> [{domain, answer, enabled?}]
    POST /control/rewrite/add     {domain, answer}
    POST /control/rewrite/delete  {domain, answer}

An answer has no type: an IPv4 address is an A record, an IPv6 one AAAA, anything else a CNAME. The special answers
"A" and "AAAA" (keep the upstream's) and rules turned off (enabled: false, v0.107.56 and later) are left alone.
"""
from app.providers import Provider, ProviderError, Record, guess_type, record, register


@register
class AdGuardHome(Provider):
    kind = "adguard"
    label = "AdGuard Home"
    fields = [
        {"key": "url", "label": "Address", "type": "url", "hint": "http://192.168.1.2:3000 (the web interface)"},
        {"key": "username", "label": "User name", "type": "text"},
        {"key": "secret", "label": "Password", "type": "password"},
        {"key": "verifyTls", "label": "Check the HTTPS certificate", "type": "check", "default": False},
    ]

    @property
    def auth(self):
        u = str(self.options.get("username") or "")
        return (u, self.secret) if u or self.secret else None

    def test(self) -> str:
        st = self.request("GET", "/control/status", auth=self.auth).json()
        return f"AdGuard Home {st.get('version', '')}, {len(self.list())} rewrites".replace("  ", " ")

    def list(self) -> list[Record]:
        out = []
        for it in self.request("GET", "/control/rewrite/list", auth=self.auth).json() or []:
            domain, answer = str(it.get("domain") or ""), str(it.get("answer") or "")
            if it.get("enabled") is False or answer.upper() in ("A", "AAAA") or not domain or not answer:
                continue
            try:
                out.append(record(domain, guess_type(answer), answer, ref=f"{domain}\t{answer}"))
            except ValueError:  # something ioDNS cannot hold (a regexp-like domain): left alone
                continue
        return out

    def _raw(self, r: Record) -> dict:
        if r.ref and "\t" in r.ref:
            d, a = r.ref.split("\t", 1)
            return {"domain": d, "answer": a}
        return {"domain": r.name, "answer": r.value}

    def add(self, r: Record) -> None:
        self.request("POST", "/control/rewrite/add", auth=self.auth, json={"domain": r.name, "answer": r.value})

    def delete(self, r: Record) -> None:
        self.request("POST", "/control/rewrite/delete", auth=self.auth, json=self._raw(r))

    def replace(self, old: Record, new: Record) -> None:
        # one call (v0.107.30 and later), so the name never goes unanswered; older versions: delete then add
        try:
            self.request("PUT", "/control/rewrite/update", auth=self.auth,
                         json={"target": self._raw(old), "update": {"domain": new.name, "answer": new.value}})
        except ProviderError as e:
            if "HTTP 404" not in str(e) and "HTTP 405" not in str(e):
                raise
            super().replace(old, new)
