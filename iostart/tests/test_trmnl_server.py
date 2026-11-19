"""The TRMNL server inside the start page (app/trmnlserver.py): what a device running TRMNL's firmware asks, whose
screens it gets, and what its owner sets in Settings › TRMNL. The apps are stood in for as in tests/test_trmnl.py."""
import io
import os

import pytest
from PIL import Image

from iosuite_shared import apppasswords, credentials, users

from app import trmnldraw, trmnlserver

TZ = "America/New_York"
MAC = "AA:BB:CC:00:11:22"
X = {"Model": "x", "Width": "1872", "Height": "1404"}  # the larger TRMNL


def device(mac=MAC, key=None, **more):
    h = {"ID": mac, "FW-Version": "1.6.9", "Model": "og", "Width": "800", "Height": "480", "RSSI": "-61", "Battery-Voltage": "3.9", "Refresh-Rate": "900"}
    if key:
        h["Access-Token"] = key
    return {**h, **more}


def picture(client, url, headers=None) -> Image.Image:
    r = client.get(url, headers=headers or {})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png", r.text
    return Image.open(io.BytesIO(r.content))


def grays(img) -> int:
    return len(img.convert("L").getcolors())


@pytest.fixture()
def paired(client, apps_answer):
    """A device that asked for its key and that alex took: (the device's client, its key, its id)."""
    out = client.__class__(client.app)  # the device: no cookie of anyone's
    s = out.get("/api/setup", headers=device()).json()
    d = client.post("/api/trmnl/devices", json={"code": s["friendly_id"]}).json()
    client.put("/api/trmnl", json={"tz": TZ})
    return out, s["api_key"], d["id"]


def test_a_new_device_waits_with_a_code(client):
    out = client.__class__(client.app)
    assert out.get("/api/trmnl").status_code == 401  # sign-in is required: only what a device asks is open
    r = out.get("/api/setup", headers=device())
    s = r.json()
    assert r.status_code == 200 and s["status"] == 200 and len(s["api_key"]) >= 16 and len(s["friendly_id"]) == 6
    assert s["image_url"].startswith("http://testserver/api/trmnl/image/")
    assert picture(out, s["image_url"]).size == (800, 480)
    # its key is with the suite's keys and tokens, not in the table
    row = trmnlserver._by_mac(MAC)
    assert credentials.get("iostart", f"trmnl_device_{row['id']}") == s["api_key"] and s["api_key"] not in str(row)
    # it asks what to show: the code again, and it looks again soon
    d = out.get("/api/display", headers=device(key=s["api_key"])).json()
    assert d["status"] == 0 and d["refresh_rate"] == trmnlserver.PENDING_EVERY and d["filename"].startswith("screen-")
    assert out.get("/api/display", headers=device(key=s["api_key"])).json()["filename"] == d["filename"]  # the same picture: not fetched again
    assert out.get("/api/display", headers=device(key="x" * 20)).status_code == 404  # only its own key, even while it is nobody's
    assert out.get("/api/setup", headers={"ID": "nonsense"}).status_code == 404
    assert out.get("/api/display", headers=device(mac="AA:BB:CC:00:11:33")).status_code == 404  # never asked /api/setup, no key
    assert client.get("/api/trmnl").json()["devices"] == []  # nobody's: nobody sees it


def test_a_code_goes_with_the_key_of_the_device_that_shows_it(client):
    """A MAC address is no secret: someone else asking /api/setup with it must not end up with the key of a device
    another person then claims by the code on its screen."""
    out = client.__class__(client.app)
    first = out.get("/api/setup", headers=device()).json()
    second = out.get("/api/setup", headers=device()).json()  # asked again (by the device after a reset, or by someone else)
    assert second["api_key"] != first["api_key"] and second["friendly_id"] != first["friendly_id"]
    assert out.get("/api/display", headers=device(key=first["api_key"])).status_code == 404
    assert client.post("/api/trmnl/devices", json={"code": first["friendly_id"]}).status_code == 404  # the code the first one shows is void
    assert client.post("/api/trmnl/devices", json={"code": second["friendly_id"]}).status_code == 200
    assert out.get("/api/display", headers=device(key=second["api_key"])).json()["filename"].startswith("plugin-")
    # a device set up elsewhere brings its key: taken in as waiting, and only that key counts after
    moved = device(mac="AA:BB:CC:00:11:44", key="k" * 24)
    assert out.get("/api/display", headers=moved).json()["filename"].startswith("screen-")
    assert out.get("/api/display", headers=device(mac="AA:BB:CC:00:11:44", key="j" * 24)).status_code == 404
    assert out.get("/api/display", headers=device(mac="AA:BB:CC:00:11:45", key="short")).status_code == 404


def test_other_screens(client, apps_answer):
    """A device that is not a TRMNL but runs its firmware: its own width and height, black and white."""
    out = client.__class__(client.app)
    other = device(mac="AA:BB:CC:00:11:55", Model="m5_papers3", Width="960", Height="540")
    s = out.get("/api/setup", headers=other).json()
    d = client.post("/api/trmnl/devices", json={"code": s["friendly_id"]}).json()
    assert d["model"] == "M5PaperS3" and (d["width"], d["height"]) == (960, 540)
    a = out.get("/api/display", headers={**other, "Access-Token": s["api_key"]}).json()
    assert picture(out, a["image_url"]).size == (960, 540)
    if os.environ.get("TRMNL_DUMP"):
        open(os.environ["TRMNL_DUMP"] + "/m5.png", "wb").write(out.get(a["image_url"]).content)


def test_waiting_devices_are_capped(client):
    from app import db
    out = client.__class__(client.app)
    for i in range(trmnlserver.PENDING_MAX + 4):
        assert out.get("/api/setup", headers=device(mac=f"AA:BB:CC:00:22:{i:02X}")).status_code == 200
    assert db.one("SELECT count(*) AS n FROM prt_trmnl_devices")["n"] == trmnlserver.PENDING_MAX
    assert len([k for k in credentials.listing("iostart") if k["name"].startswith("trmnl_device_")]) == trmnlserver.PENDING_MAX


def test_claim_and_show(client, paired):
    out, key, dev = paired
    alex = users.find("alex")
    s = client.get("/api/trmnl").json()
    d = s["devices"][0]
    assert d["id"] == dev and d["mac"] == MAC and d["model"] == "TRMNL" and d["battery"] == 82 and d["rssi"] == -61 and d["firmware"] == "1.6.9"
    assert [p["screens"] for p in d["playlist"]] == [[k] for k in ("today", "calendar", "tasks", "docs", "health", "money")]
    assert {x["key"] for x in s["layouts"]} == set(trmnldraw.LAYOUTS) and s["refreshes"][0] == 300
    assert [p["label"] for p in apppasswords.list_for(alex["id"], "iostart")] == ["TRMNL"]  # what its screens are read with
    assert client.post("/api/trmnl/devices", json={"code": "ZZZZZZ"}).status_code == 404
    # the playlist, one entry after the other; an unchanged picture keeps its name
    seen = []
    for _ in range(7):
        a = out.get("/api/display", headers=device(key=key, **{"Battery-Voltage": "3.6"})).json()
        assert a["status"] == 0 and a["refresh_rate"] == 900 and a["filename"].startswith("plugin-") and a["special_function"] == "sleep"
        seen.append(a["filename"])
        img = picture(out, a["image_url"], {"ID": MAC, "Access-Token": key})
        assert img.size == (800, 480) and img.mode == "1"
    assert len(set(seen[:6])) == 6 and seen[6] == seen[0]
    assert client.get("/api/trmnl").json()["devices"][0]["battery"] == 55
    # a picture's address is good for the answer that named it
    assert out.get(a["image_url"]).status_code == 200
    b = out.get("/api/display", headers=device(key=key)).json()
    assert out.get(a["image_url"]).status_code == 404 and out.get(b["image_url"]).status_code == 200
    trmnlserver._images.clear()  # a restart between the answer and the download: drawn again
    assert out.get(b["image_url"]).status_code == 200
    # the wrong key shows nothing of alex's
    assert out.get("/api/display", headers=device(key="y" * 20)).status_code == 404
    assert out.get("/api/display", headers=device()).status_code == 404


def test_what_changed_gets_a_new_name(client, paired, apps_answer):
    from app import wall, widgets
    out, key, dev = paired
    table = apps_answer[0]
    client.put(f"/api/trmnl/devices/{dev}", json={"playlist": [{"layout": "full", "screens": ["money"]}]})
    a = out.get("/api/display", headers=device(key=key)).json()
    assert out.get("/api/display", headers=device(key=key)).json()["filename"] == a["filename"]
    table[("iomoney", "/api/bills")]["items"][0]["merchant"] = "National Grid"
    widgets.forget(), wall.forget()
    b = out.get("/api/display", headers=device(key=key)).json()
    assert b["filename"] != a["filename"] and b["filename"][:14] == a["filename"][:14]  # the same place of the playlist, drawn later


def test_settings(client, paired):
    out, key, dev = paired
    r = client.put(f"/api/trmnl/devices/{dev}", json={"name": " Kitchen ", "refresh": 1800, "bits": 2,
                                                       "playlist": [{"layout": "1Lx1R", "screens": ["today", "tasks"]}, {"layout": "2x2", "screens": ["calendar", "tasks", "docs", "money"]}]})
    d = r.json()
    assert r.status_code == 200 and d["name"] == "Kitchen" and d["refresh"] == 1800 and d["bits"] == 2 and len(d["playlist"]) == 2
    a = out.get("/api/display", headers=device(key=key)).json()
    assert a["refresh_rate"] == 1800 and a["filename"].startswith("mashup-")
    img = picture(out, a["image_url"])
    assert img.size == (800, 480) and grays(img) == 4
    for bad in ({"refresh": 7}, {"bits": 4}, {"playlist": []}, {"playlist": [{"layout": "1Lx1R", "screens": ["today"]}]},
                {"playlist": [{"layout": "full", "screens": ["nothing"]}]}, {"playlist": [{"layout": "wide", "screens": ["today"]}]}):
        assert client.put(f"/api/trmnl/devices/{dev}", json=bad).status_code == 400, bad
    for at in (0, 1):
        assert picture(client, f"/api/trmnl/devices/{dev}/preview.png?at={at}").size == (800, 480)
    assert picture(client, f"/api/trmnl/devices/{dev}/preview.png?layout=2Tx1B&screens=health,money,today").size == (800, 480)  # while it is edited
    assert client.get(f"/api/trmnl/devices/{dev}/preview.png?layout=full&screens=today,tasks").status_code == 404


def test_a_bigger_screen(client, apps_answer):
    out = client.__class__(client.app)
    x = device(**X, **{"Percent-Charged": "64"})
    s = out.get("/api/setup", headers=x).json()
    d = client.post("/api/trmnl/devices", json={"code": s["friendly_id"].lower()}).json()
    assert d["model"] == "TRMNL X" and d["bits"] == 4 and d["canBits"] == [4, 2, 1] and d["battery"] == 64
    a = out.get("/api/display", headers={**x, "Access-Token": s["api_key"]}).json()
    img = picture(out, a["image_url"])
    assert img.size == (1872, 1404) and 4 < grays(img) <= 16


def test_only_its_owner(client, paired):
    from iosuite_shared import testing
    out, key, dev = paired
    testing.add_account(client, {"name": "kid", "password": "secret123", "role": "viewer"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "kid", "password": "secret123"})
    assert client.get("/api/trmnl").json()["devices"] == []
    assert client.put(f"/api/trmnl/devices/{dev}", json={"name": "Mine"}).status_code == 404
    assert client.get(f"/api/trmnl/devices/{dev}/preview.png").status_code == 404
    assert client.delete(f"/api/trmnl/devices/{dev}").status_code == 404
    assert client.post("/api/trmnl/devices", json={"code": trmnlserver.get(dev)["code"]}).status_code == 404  # taken


def test_pair_again(client, paired):
    out, key, dev = paired
    # a reset device asks for a key again: refused, anyone on the network could ask with its MAC address
    r = out.get("/api/setup", headers=device())
    assert r.status_code == 404 and r.json()["status"] == 404 and "Pair again" in r.json()["message"]
    assert client.put(f"/api/trmnl/devices/{dev}", json={"pair": True}).json()["pairing"] is True
    s = out.get("/api/setup", headers=device()).json()
    assert s["status"] == 200 and s["api_key"] != key
    assert out.get("/api/display", headers=device(key=key)).status_code == 404  # the old key is gone
    assert out.get("/api/display", headers=device(key=s["api_key"])).json()["filename"].startswith("plugin-")  # and it is still alex's
    assert client.get("/api/trmnl").json()["devices"][0]["pairing"] is False  # once
    assert out.get("/api/setup", headers=device()).status_code == 404


def test_log(client, paired):
    out, key, dev = paired
    body = {"logs": [{"creation_timestamp": 1763500000, "log_message": "Wi-Fi connect failed", "device_status_stamp": {"wifi_rssi_level": -80}}]}
    assert out.post("/api/log", headers=device(key=key), json=body).json() == {"status": 200}
    assert out.post("/api/log", headers=device(key="z" * 20), json=body).status_code == 404
    assert client.get("/api/trmnl").json()["devices"][0]["log"] == [{"at": 1763500000, "text": "Wi-Fi connect failed"}]
    for i in range(30):
        out.post("/api/log", headers=device(key=key), json={"logs": [{"log_message": f"line {i}"}]})
    assert len(client.get("/api/trmnl").json()["devices"][0]["log"]) == trmnlserver.LOG_KEEP
    assert out.get("/api/log").status_code == 401  # the server's own log stays the admins'


def test_the_app_password_revoked(client, paired):
    out, key, dev = paired
    alex = users.find("alex")
    client.delete(f"/api/auth/app-passwords/{apppasswords.list_for(alex['id'], 'iostart')[0]['id']}")
    apppasswords.forget()
    a = out.get("/api/display", headers=device(key=key)).json()  # the screen says so, where its owner looks
    assert a["status"] == 0 and picture(out, a["image_url"]).size == (800, 480)
    assert client.get(f"/api/trmnl/devices/{dev}/preview.png?layout=full&screens=today").status_code == 400
    client.put(f"/api/trmnl/devices/{dev}", json={"name": "Hall"})  # saving it makes a new one
    assert [p["label"] for p in apppasswords.list_for(alex["id"], "iostart")] == ["TRMNL"]
    assert out.get("/api/display", headers=device(key=key)).json()["filename"].startswith("plugin-")


def test_remove(client, paired):
    out, key, dev = paired
    alex = users.find("alex")
    assert client.delete(f"/api/trmnl/devices/{dev}").json() == {"ok": True}
    assert client.get("/api/trmnl").json()["devices"] == [] and not credentials.get("iostart", f"trmnl_device_{dev}")
    assert apppasswords.list_for(alex["id"], "iostart") == []  # nothing reads with it any more
    a = out.get("/api/display", headers=device(key=key)).json()  # it is nobody's again: a code
    assert a["filename"].startswith("screen-") and a["refresh_rate"] == trmnlserver.PENDING_EVERY


def test_the_app_password_stays_while_something_reads_with_it(client, paired, monkeypatch):
    from iosuite_shared import outbound
    from app import trmnlpush
    out, key, dev = paired
    alex = users.find("alex")
    monkeypatch.setattr(outbound, "check", lambda url, allowed=None: "203.0.113.5")
    hook = "https://trmnl.com/api/custom_plugins/0a1b2c3d-0000-4000-8000-123456789abc"
    client.put("/api/trmnl", json={"hooks": {"tasks": hook}})
    client.put("/api/trmnl", json={"hooks": {"tasks": ""}})
    assert len(apppasswords.list_for(alex["id"], "iostart")) == 1  # the device still reads with it
    client.put("/api/trmnl", json={"hooks": {"tasks": hook}})
    client.delete(f"/api/trmnl/devices/{dev}")
    assert len(apppasswords.list_for(alex["id"], "iostart")) == 1 and trmnlpush.hooks(alex["id"])  # the push still does


def test_deleting_a_person_takes_their_devices(client, paired):
    from app import persondata
    out, key, dev = paired
    alex = users.find("alex")
    assert {x["what"]: x["count"] for x in persondata.of(alex["id"], False)}["TRMNL devices"] == 1
    persondata.of(alex["id"], True)
    assert trmnlserver.get(dev) is None and not credentials.get("iostart", f"trmnl_device_{dev}")
    assert apppasswords.list_for(alex["id"], "iostart") == []


def test_the_address_for_a_device(monkeypatch):
    from iosuite_shared import suite
    monkeypatch.setattr(suite, "local_url", lambda app=None, **k: "http://192.168.1.20:8630")
    assert trmnlserver.address() == "http://192.168.1.20:8630"
    monkeypatch.setattr(suite, "local_url", lambda app=None, **k: "http://127.0.0.1:8630")
    assert trmnlserver.address() is None  # on this machine only: a device cannot reach it
    monkeypatch.setattr(suite, "local_url", lambda app=None, **k: None)
    assert trmnlserver.address() is None


def _hhmm(hours: float) -> str:
    """The time of day `hours` from now in the tests' zone, as HH:MM."""
    import datetime as dt
    from zoneinfo import ZoneInfo
    return (dt.datetime.now(ZoneInfo(TZ)) + dt.timedelta(hours=hours)).strftime("%H:%M")


def test_quiet_hours(client, paired):
    """TRMNL's "sleep mode": in the quiet hours the device is told to sleep until they end, and keeps its picture."""
    out, key, dev = paired
    look = lambda why="timer": out.get("/api/display", headers=device(key=key, **{"Update-Source": why})).json()  # noqa: E731
    client.put(f"/api/trmnl/devices/{dev}", json={"playlist": [{"layout": "full", "screens": [k]} for k in ("today", "tasks", "calendar")]})
    first = look()
    assert first["refresh_rate"] == 900 and client.get("/api/trmnl").json()["devices"][0]["quiet"] is None
    r = client.put(f"/api/trmnl/devices/{dev}", json={"quiet": {"from": _hhmm(-1), "to": _hhmm(2)}})
    assert r.status_code == 200 and r.json()["quiet"]["show"] == "last" and r.json()["quietNow"] is True
    d = look()
    assert 7000 < d["refresh_rate"] <= 7300 and d["filename"] == first["filename"]  # asleep until the quiet ends, its screen as it was
    assert look()["filename"] == first["filename"]
    assert picture(out, d["image_url"]).size == (800, 480)
    # a press of its button shows the screen it is at, now, and it sleeps on until the morning
    b = look("button")
    assert b["filename"].startswith("plugin-") and b["filename"].split("-")[1] == first["filename"].split("-")[1] and 7000 < b["refresh_rate"] <= 7300
    # or a line that says until when
    assert client.put(f"/api/trmnl/devices/{dev}", json={"quiet": {"from": _hhmm(-1), "to": _hhmm(2), "show": "notice"}}).json()["quiet"]["show"] == "notice"
    n = look()
    assert n["filename"].startswith("screen-") and look()["filename"] == n["filename"] and 7000 < n["refresh_rate"] <= 7300
    assert grays(picture(out, look()["image_url"])) == 2
    # outside them, and without them, the playlist goes on where it was
    assert client.put(f"/api/trmnl/devices/{dev}", json={"quiet": {"from": _hhmm(3), "to": _hhmm(5)}}).json()["quietNow"] is False
    after = look()
    assert after["refresh_rate"] == 900 and after["filename"].startswith("plugin-") and after["filename"].split("-")[1] != first["filename"].split("-")[1]
    assert client.put(f"/api/trmnl/devices/{dev}", json={"quiet": None}).json()["quiet"] is None
    for bad in ({"from": "22:00"}, {"from": "25:00", "to": "07:00"}, {"from": "07:00", "to": "07:00"}, {"from": "22:00", "to": "07:00", "show": "loud"}, "night"):
        assert client.put(f"/api/trmnl/devices/{dev}", json={"quiet": bad}).status_code == 400, bad


def test_when_the_quiet_ends():
    import datetime as dt
    from zoneinfo import ZoneInfo
    z = ZoneInfo("UTC")
    d = {"owner": None, "settings": {"quiet": {"from": "22:00", "to": "07:00"}}}
    at = lambda h, m=0: dt.datetime(2026, 11, 19, h, m, tzinfo=z)  # noqa: E731
    assert trmnlserver.quiet_left(d, at(23, 30)) == 7.5 * 3600 + 30   # through midnight
    assert trmnlserver.quiet_left(d, at(6)) == 3600 + 30              # the quiet that began yesterday
    assert trmnlserver.quiet_left(d, at(7)) is None and trmnlserver.quiet_left(d, at(12)) is None and trmnlserver.quiet_left(d, at(21, 59)) is None
    assert trmnlserver.quiet_left(d, at(12), ahead=True) == 19 * 3600 + 30  # the button's sleep: until tomorrow morning
    day = {"owner": None, "settings": {"quiet": {"from": "13:00", "to": "15:00"}}}  # a nap
    assert trmnlserver.quiet_left(day, at(14)) == 3600 + 30 and trmnlserver.quiet_left(day, at(15)) is None and trmnlserver.quiet_left(day, at(12)) is None
    assert trmnlserver.quiet_left(day, at(16), ahead=True) == 23 * 3600 + 30
    assert trmnlserver.quiet_left({"owner": None, "settings": {}}, at(23)) is None


def test_the_button(client, paired, monkeypatch):
    """The firmware's special functions: the answer names the one a double press runs; asked with a
    special_function header (true: the one set; a name: the TRMNL X's menu), it carries the action the firmware
    checks for."""
    out, key, dev = paired
    told = []
    monkeypatch.setattr(trmnlserver.push, "notify", lambda uid, kind, title, body="", **kw: told.append((kind, title, kw.get("url"))) or 1)
    ask = lambda fn=None: out.get("/api/display", headers=device(key=key, **({"special_function": fn} if fn else {}))).json()  # noqa: E731
    which = lambda d: d["filename"].split("-")[1]  # noqa: E731
    client.put(f"/api/trmnl/devices/{dev}", json={"playlist": [{"layout": "full", "screens": [k]} for k in ("today", "tasks", "calendar")]})
    one = ask()
    assert one["special_function"] == "sleep" and "action" not in one and client.get("/api/trmnl").json()["buttons"][0] == "sleep"
    # sleep (the default): the screen stays, for eight hours, or until the quiet hours end when there are some
    s = ask("true")
    assert s["action"] == "sleep" and s["refresh_rate"] == trmnlserver.SLEEP_FOR and s["filename"] == one["filename"]
    client.put(f"/api/trmnl/devices/{dev}", json={"quiet": {"from": _hhmm(3), "to": _hhmm(5)}})
    assert 17900 < ask("sleep")["refresh_rate"] <= 18100
    client.put(f"/api/trmnl/devices/{dev}", json={"quiet": None})
    # identify: which screen this is, by its name
    assert client.put(f"/api/trmnl/devices/{dev}", json={"button": "identify", "name": "Kitchen"}).json()["button"] == "identify"
    i = ask("true")
    assert i["special_function"] == "identify" and i["action"] == "identify" and i["filename"].startswith("screen-")
    assert picture(out, i["image_url"]).size == (800, 480) and ask("identify")["filename"] != i["filename"]  # drawn again every time
    two = ask()
    assert which(two) not in (which(one), which(i))  # the playlist went on from where it was
    # by name, whatever the button is set to: start again, one back, hold
    r = ask("restart_playlist")
    assert r["action"] == "restart_playlist" and which(r) == which(one)
    ask()
    assert ask("rewind")["action"] == "rewind" and which(ask()) == which(two)  # the device showed the one before; the next is the one it was at
    h = ask("guest_mode")
    assert h["action"] == "guest_mode" and which(h) == which(two) and client.get("/api/trmnl").json()["devices"][0]["hold"] is True
    assert which(ask()) == which(two) and which(ask()) == which(two)  # held: it stays
    assert ask("toggle_hold")["action"] == "guest_mode" and client.get("/api/trmnl").json()["devices"][0]["hold"] is False
    assert which(ask()) != which(two)
    assert client.put(f"/api/trmnl/devices/{dev}", json={"hold": True}).json()["hold"] is True  # or from Settings
    assert client.put(f"/api/trmnl/devices/{dev}", json={"hold": False}).json()["hold"] is False
    # send to me: a notification that opens the picture; add Wi-Fi: the device does that itself
    assert ask("send_to_me")["action"] == "send_to_me" and told and told[-1][0] == "trmnl" and told[-1][1].startswith("Kitchen: ")
    assert f"api/trmnl/devices/{dev}/preview.png" in (told[-1][2] or f"api/trmnl/devices/{dev}/preview.png")
    assert ask("add_wifi")["action"] == "add_wifi"
    # none: nothing is armed, and a press is an ordinary look
    client.put(f"/api/trmnl/devices/{dev}", json={"button": "none"})
    n = ask("true")
    assert n["special_function"] == "none" and "action" not in n
    assert client.put(f"/api/trmnl/devices/{dev}", json={"button": "fireworks"}).status_code == 400
    assert "action" not in ask("fireworks")  # a function this server does not know: an ordinary look


def test_the_rest_of_what_the_firmware_reads(client, paired, monkeypatch):
    out, key, dev = paired
    told = []
    monkeypatch.setattr(trmnlserver.push, "notify", lambda uid, kind, title, body="", **kw: told.append(title) or 1)
    ask = lambda **h: out.get("/api/display", headers=device(key=key, **h)).json()  # noqa: E731
    d = ask()
    assert d["maximum_compatibility"] is False and d["verbose_logging"] == "info" and d["reset_firmware"] is False and d["update_firmware"] is False
    r = client.put(f"/api/trmnl/devices/{dev}", json={"clean": True, "verbose": True, "refresh": 86400}).json()
    assert r["clean"] is True and r["verbose"] is True and r["refresh"] == 86400
    d = ask()
    assert d["maximum_compatibility"] is True and d["verbose_logging"] == "debug" and d["refresh_rate"] == 86400
    # what it shows now, for a client that only looks: the same picture, and the playlist stays
    c = out.get("/api/current_screen", headers=device(key=key))
    assert c.status_code == 200 and c.json()["status"] == 200 and c.json()["filename"] == d["filename"]
    assert out.get("/api/current_screen", headers=device(key=key)).json()["filename"] == d["filename"]
    assert picture(out, c.json()["image_url"]).size == (800, 480)
    assert out.get("/api/current_screen", headers=device(key="x" * 20)).status_code == 404
    # charging, and a battery that runs low: told once, and again only after it was charged
    ask(**{"Battery-Charging": "1", "USB-Connected": "true"})
    assert client.get("/api/trmnl").json()["devices"][0]["charging"] is True and not told
    ask(**{"Battery-Voltage": "3.1", "Battery-Charging": "0"})
    ask(**{"Battery-Voltage": "3.08", "Battery-Charging": "0"})
    assert len(told) == 1 and "battery at 9%" in told[0]
    ask(**{"Battery-Voltage": "4.0", "Battery-Charging": "0"})
    ask(**{"Battery-Voltage": "3.1", "Battery-Charging": "0"})
    assert len(told) == 2
    # reset: once, at its next look; it may then come back for a new key
    assert client.put(f"/api/trmnl/devices/{dev}", json={"reset": True}).json()["resetting"] is True
    assert ask()["reset_firmware"] is True and ask()["reset_firmware"] is False
    after = client.get("/api/trmnl").json()["devices"][0]
    assert after["resetting"] is False and after["pairing"] is True
    again = out.get("/api/setup", headers=device())
    assert again.status_code == 200 and again.json()["api_key"] != key


def test_pictures_to_look_at(client, apps_answer):
    """TRMNL_DUMP=<folder>: what devices get, written there to look at (the README's pictures)."""
    where = os.environ.get("TRMNL_DUMP")
    if not where:
        pytest.skip("TRMNL_DUMP=<folder> writes what a device gets, to look at")
    out = client.__class__(client.app)
    s = out.get("/api/setup", headers=device()).json()
    open(f"{where}/waiting.png", "wb").write(out.get(s["image_url"]).content)
    small = client.post("/api/trmnl/devices", json={"code": s["friendly_id"]}).json()
    big = client.post("/api/trmnl/devices", json={"code": out.get("/api/setup", headers=device(mac="AA:BB:CC:00:11:99", **X)).json()["friendly_id"]}).json()
    client.put("/api/trmnl", json={"tz": TZ})
    for layout, screens in (("full", "today"), ("1Lx1R", "today,tasks"), ("2x2", "calendar,tasks,docs,money"), ("1Tx2B", "calendar,health,money"), ("1Lx2R", "today,docs,health")):
        for bits, dev in ((1, small), (2, small), (4, big)):
            client.put(f"/api/trmnl/devices/{dev['id']}", json={"bits": bits})
            r = client.get(f"/api/trmnl/devices/{dev['id']}/preview.png?layout={layout}&screens={screens}")
            open(f"{where}/{layout}-{dev['model'].replace(' ', '')}-{bits}.png", "wb").write(r.content)
    alex = users.find("alex")
    client.delete(f"/api/auth/app-passwords/{apppasswords.list_for(alex['id'], 'iostart')[0]['id']}")
    apppasswords.forget()
    a = out.get("/api/display", headers=device(key=s["api_key"])).json()
    open(f"{where}/revoked.png", "wb").write(out.get(a["image_url"]).content)
