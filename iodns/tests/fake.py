"""A DNS server in memory, for the tests: kind "fake", its records in SERVERS[url] (a list of Record)."""
from app.providers import AnsweredElsewhere, Provider, ProviderError, Record, register

SERVERS: dict[str, list[Record]] = {}
DOWN: set[str] = set()
LOCAL: dict[str, set[str]] = {}  # per server: names the server answers itself and refuses (as UniFi does a client's name)


@register
class Fake(Provider):
    kind = "fake"
    label = "Fake DNS"
    fields = [{"key": "url", "label": "Address", "type": "url"}, {"key": "secret", "label": "Password", "type": "password"},
              {"key": "zone", "label": "Zone", "type": "text"}]

    def open(self):
        if self.url in DOWN:
            raise ProviderError(f"{self.url}: down")
        if self.secret != "pw":
            raise ProviderError(f"{self.url}: wrong password")

    def covers(self):
        z = self.options.get("zone")
        return [z] if z else None

    def list(self):
        return [Record(r.name, r.type, r.value, r.ttl, ref=f"{r.name}|{r.type}|{r.value}") for r in SERVERS.setdefault(self.url, [])]

    def add(self, r):
        if r.name in LOCAL.get(self.url, ()):
            raise AnsweredElsewhere(f"{self.url} answers {r.name} itself", r.name)
        SERVERS.setdefault(self.url, []).append(Record(r.name, r.type, r.value, r.ttl))

    def delete(self, r):
        SERVERS[self.url] = [x for x in SERVERS.get(self.url, []) if x.key != r.key]
