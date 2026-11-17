"""Demo data (iosuite_shared.demo): the Calloways' home network names. Entries for the house's devices and the suite
under home.calloway.example (internal addresses for the LAN, the public ones where the suite is reached from outside),
and a Pi-hole and an AdGuard Home server, turned off (no real server is behind them, so nothing is synced)."""
from app import model

ZONE = "home.calloway.example"
ENTRIES = [
    ("suite", "The suite's one address (the start page)", {"internal": [{"type": "A", "value": "192.168.20.10"}],
                                                           "external": [{"type": "CNAME", "value": "calloway-home.example.net"}]}),
    ("photos", "ioPix", {"internal": [{"type": "A", "value": "192.168.20.11"}]}),
    ("nas", "The storage box in the basement", {"internal": [{"type": "A", "value": "192.168.20.5"}]}),
    ("printer", "Office printer", {"internal": [{"type": "A", "value": "192.168.20.40"}]}),
    ("router", "The router", {"internal": [{"type": "A", "value": "192.168.20.1"}]}),
    ("homeassistant", "Home Assistant", {"internal": [{"type": "A", "value": "192.168.20.12"}]}),
    ("tv", "Living room TV", {"internal": [{"type": "A", "value": "192.168.20.61"}]}),
    ("pihole", "Ad blocker", {"internal": [{"type": "A", "value": "192.168.20.2"}]}),
    ("calendar", "ioCalendar, also from outside", {"internal": [{"type": "CNAME", "value": f"suite.{ZONE}"}],
                                                   "external": [{"type": "CNAME", "value": "calloway-home.example.net"}]}),
]


def seed(people: dict) -> None:
    by = people["morgan"]["name"]
    for name, comment, records in ENTRIES:
        model.save_entry({"name": f"{name}.{ZONE}", "comment": comment, "records": records}, by)
    model.save_server({"kind": "pihole", "name": "Pi-hole (basement)", "url": "http://192.168.20.2", "view": "internal", "enabled": False}, by)
    model.save_server({"kind": "adguard", "name": "AdGuard Home (backup)", "url": "http://192.168.20.3", "view": "internal", "enabled": False}, by)
