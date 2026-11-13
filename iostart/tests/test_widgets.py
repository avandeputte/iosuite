"""The weather (AccuWeather mocked: no network, no key spent) and the bookmarks."""
import json

from app import weather

YAML = """
- Developer:
    - Github:
        - abbr: GH
          href: https://github.com/
- Social:
    - Reddit:
        - icon: reddit.png
          href: https://reddit.com/
          description: The front page of the internet
"""


def _fake_accuweather(calls):
    def get(path, **params):
        calls.append(path)
        if path.startswith("/locations/v1/cities/search"):
            return [{"Key": "349727", "LocalizedName": "New York", "AdministrativeArea": {"LocalizedName": "New York"}, "Country": {"LocalizedName": "United States"}}]
        if path.startswith("/currentconditions/v1/"):
            return [{"WeatherText": "Sunny", "WeatherIcon": 1, "IsDayTime": True, "RelativeHumidity": 40, "UVIndex": 3, "Link": "https://example.com",
                     "Temperature": {"Metric": {"Value": 20.0}, "Imperial": {"Value": 68.0}}, "RealFeelTemperature": {"Metric": {"Value": 21.0}, "Imperial": {"Value": 70.0}},
                     "Wind": {"Speed": {"Metric": {"Value": 10.0}, "Imperial": {"Value": 6.2}}}}]
        if path.startswith("/forecasts/v1/daily/5day/"):
            return {"Headline": {"Text": "Sunny week"}, "DailyForecasts": [
                {"Date": "2026-11-04T07:00:00-05:00", "Temperature": {"Minimum": {"Value": 10.0}, "Maximum": {"Value": 18.0}}, "Day": {"Icon": 2, "IconPhrase": "Mostly sunny", "PrecipitationProbability": 5}}]}
        if path.startswith("/forecasts/v1/hourly/12hour/"):
            return [{"DateTime": "2026-11-04T15:00:00-05:00", "WeatherIcon": 12, "IconPhrase": "Showers", "Temperature": {"Value": 14.0},
                     "PrecipitationProbability": 70, "HasPrecipitation": True, "PrecipitationType": "Rain"}]
        raise AssertionError(path)
    return get


def test_weather_off_until_set_up(client):
    assert client.get("/api/weather").json() == {"enabled": False}
    s = client.get("/api/weather/settings").json()
    assert s["hasKey"] is False and s["enabled"] is False and s["units"] == "metric"


def test_weather_setup_and_cache(client, monkeypatch):
    calls = []
    monkeypatch.setattr(weather, "_get", _fake_accuweather(calls))
    r = client.get("/api/weather/search?q=New York&key=abc")
    assert r.status_code == 400  # a key given on the request is tried directly against AccuWeather (not mocked here): refused or unreachable
    assert client.post("/api/weather/settings", json={"key": "abc", "units": "imperial"}).json()["hasKey"] is True
    found = client.get("/api/weather/search?q=New York").json()["items"]
    assert found == [{"key": "349727", "name": "New York", "region": "New York", "country": "United States"}]
    s = client.post("/api/weather/settings", json={"locationKey": "349727", "locationName": "New York, United States"}).json()
    assert s["enabled"] and s["locationName"] == "New York, United States"
    w = client.get("/api/weather").json()
    assert w["enabled"] and w["units"] == "imperial" and w["current"]["text"] == "Sunny" and w["current"]["temp"] == {"metric": 20.0, "imperial": 68.0}
    assert w["forecast"]["days"][0] == {"date": "2026-11-04", "min": 10.0, "max": 18.0, "icon": 2, "text": "Mostly sunny", "rain": 5}
    assert w["hourly"] == [{"t": "2026-11-04T15:00:00-05:00", "icon": 12, "text": "Showers", "temp": 14.0, "rain": 70, "wet": True, "kind": "Rain"}]
    n = len(calls)
    assert client.get("/api/weather").json()["current"]["text"] == "Sunny"
    assert len(calls) == n, "the second visit comes from the server's copy, not from AccuWeather"
    # a failing AccuWeather keeps the old reading, marked stale
    monkeypatch.setattr(weather, "_get", lambda *a, **k: (_ for _ in ()).throw(weather.WeatherError("down")))
    from app import db
    stale = json.loads(db.get_setting("weather_current"))
    db.set_setting("weather_current", json.dumps({**stale, "at": 0}))
    w = client.get("/api/weather").json()
    assert w["current"]["text"] == "Sunny" and w["stale"] and "down" in w["error"]
    # a viewer may read the weather, not the settings
    client.post("/api/users", json={"name": "kid", "password": "secret123", "role": "viewer"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "kid", "password": "secret123"})
    assert client.get("/api/weather").json()["enabled"]
    assert client.get("/api/weather/settings").status_code == 403


def test_bookmarks(client):
    assert client.get("/api/bookmarks").json() == {"groups": []}
    g = client.post("/api/bookmarks/groups", json={"name": "Developer"}).json()
    r = client.post(f"/api/bookmarks/groups/{g['id']}/links", json={"name": "Hacker News", "href": "news.ycombinator.com"})
    assert r.status_code == 200, r.text
    l1 = r.json()
    assert l1["abbr"] == "HN" and l1["href"] == "https://news.ycombinator.com" and l1["description"] == "news.ycombinator.com"
    l2 = client.post(f"/api/bookmarks/groups/{g['id']}/links", json={"name": "Github", "href": "https://github.com/", "abbr": "GH", "description": "Code"}).json()
    assert l2["abbr"] == "GH" and l2["description"] == "Code"
    assert client.post(f"/api/bookmarks/groups/{g['id']}/links", json={"name": "Bad", "href": ""}).status_code == 400
    # order, rename, move between groups
    client.post(f"/api/bookmarks/groups/{g['id']}/order", json={"ids": [l2["id"], l1["id"]]})
    gs = client.get("/api/bookmarks").json()["groups"]
    assert [x["name"] for x in gs[0]["links"]] == ["Github", "Hacker News"]
    g2 = client.post("/api/bookmarks/groups", json={"name": "Social"}).json()
    client.post("/api/bookmarks/groups/order", json={"ids": [g2["id"], g["id"]]})
    assert client.patch(f"/api/bookmarks/links/{l1['id']}", json={"groupId": g2["id"], "name": "HN"}).json()["abbr"] == "HN"
    gs = client.get("/api/bookmarks").json()["groups"]
    assert [(x["name"], [y["name"] for y in x["links"]]) for x in gs] == [("Social", ["HN"]), ("Developer", ["Github"])]
    # import from homepage: Developer already exists and gets the link; Social gets Reddit
    r = client.post("/api/bookmarks/import", json={"yaml": YAML}).json()
    assert r == {"groups": 0, "links": 2}
    gs = client.get("/api/bookmarks").json()["groups"]
    reddit = next(y for x in gs for y in x["links"] if y["name"] == "Reddit")
    assert reddit["icon"] == "reddit.png" and reddit["description"] == "The front page of the internet"
    assert client.post("/api/bookmarks/import", json={"yaml": "not: [a list"}).status_code == 400
    assert client.post("/api/bookmarks/import", json={"yaml": "- Only:\n    - X:\n        - href: https://x.org\n", "replace": True}).json() == {"groups": 1, "links": 1}
    assert [x["name"] for x in client.get("/api/bookmarks").json()["groups"]] == ["Only"]
    client.delete(f"/api/bookmarks/groups/{client.get('/api/bookmarks').json()['groups'][0]['id']}")
    assert client.get("/api/bookmarks").json() == {"groups": []}


def test_viewer_reads_bookmarks_editor_changes_them(client):
    client.post("/api/users", json={"name": "kid", "password": "secret123", "role": "viewer"})
    client.post("/api/users", json={"name": "sam", "password": "secret123", "role": "editor"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "kid", "password": "secret123"})
    assert client.get("/api/bookmarks").status_code == 200
    assert client.post("/api/bookmarks/groups", json={"name": "X"}).status_code == 403
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "sam", "password": "secret123"})
    assert client.post("/api/bookmarks/groups", json={"name": "X"}).status_code == 200


SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" fill="#c33"/></svg>'


def test_uploaded_svg_icon(client):
    g = client.post("/api/bookmarks/groups", json={"name": "Dev"}).json()
    l = client.post(f"/api/bookmarks/groups/{g['id']}/links", json={"name": "Forge", "href": "https://forge.example", "icon": "github.png"}).json()
    assert l["iconUrl"] == ""
    r = client.put(f"/api/bookmarks/links/{l['id']}/icon", content=SVG, headers={"Content-Type": "image/svg+xml"})
    assert r.status_code == 200, r.text
    url = r.json()["iconUrl"]
    assert url.startswith(f"api/bookmarks/links/{l['id']}/icon.svg?v=") and r.json()["icon"] == "github.png"
    got = client.get("/" + url)
    assert got.status_code == 200 and got.headers["content-type"].startswith("image/svg+xml") and got.content == SVG
    assert "immutable" in got.headers["cache-control"]
    assert client.get("/api/bookmarks").json()["groups"][0]["links"][0]["iconUrl"] == url
    # replacing changes the address; the list follows
    r2 = client.put(f"/api/bookmarks/links/{l['id']}/icon", content=SVG.replace(b"#c33", b"#3c3"))
    assert r2.json()["iconUrl"] != url
    # what is refused
    for bad, why in [(b"<svg onload='alert(1)'/>", "handler"), (b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>", "script"),
                     (b"<html/>", "root"), (b"not xml <", "parse"), (b"", "empty"), (b"<svg/>" + b" " * (256 * 1024), "size")]:
        assert client.put(f"/api/bookmarks/links/{l['id']}/icon", content=bad).status_code == 400, why
    assert client.put("/api/bookmarks/links/9999/icon", content=SVG).status_code == 404
    # a PNG is taken too, and served inside an SVG of its size
    import base64 as b64
    png = b64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAIAAAADCAYAAAC56t6BAAAAEUlEQVR4nGM4ISf3H4QZMBgAoR8ME4Q16BEAAAAASUVORK5CYII=")
    rp = client.put(f"/api/bookmarks/links/{l['id']}/icon", content=png, headers={"Content-Type": "image/png"})
    assert rp.status_code == 200 and rp.json()["iconUrl"] not in ("", r2.json()["iconUrl"])
    got = client.get("/" + rp.json()["iconUrl"])
    assert got.headers["content-type"].startswith("image/svg+xml") and 'viewBox="0 0 2 3"' in got.text
    assert b64.b64encode(png).decode() in got.text and "img-src data:" in got.headers["content-security-policy"]
    for bad, why in ((png[:30], "cut short"), (b"\x89PNG\r\n\x1a\n" + b"x" * 300 * 1024, "too large"), (b"GIF89a" + b"0" * 50, "another kind")):
        assert client.put(f"/api/bookmarks/links/{l['id']}/icon", content=bad).status_code == 400, why
    assert client.delete(f"/api/bookmarks/links/{l['id']}/icon").json()["iconUrl"] == ""
    assert client.get(f"/api/bookmarks/links/{l['id']}/icon.svg").status_code == 404
    client.put(f"/api/bookmarks/links/{l['id']}/icon", content=SVG)
    client.delete(f"/api/bookmarks/links/{l['id']}")
    from app import db
    assert db.q("SELECT * FROM prt_bookmark_node_icons") == []
    # a viewer sees the icon of a shared link but cannot change it
    client.patch(f"/api/bookmarks/groups/{g['id']}", json={"shared": True})
    l2 = client.post(f"/api/bookmarks/groups/{g['id']}/links", json={"name": "Wiki", "href": "https://wiki.example"}).json()
    assert l2["shared"] is True
    client.put(f"/api/bookmarks/links/{l2['id']}/icon", content=SVG)
    client.post("/api/users", json={"name": "kid", "password": "secret123", "role": "viewer"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "kid", "password": "secret123"})
    assert client.get(f"/api/bookmarks/links/{l2['id']}/icon.svg").status_code == 200
    assert client.put(f"/api/bookmarks/links/{l2['id']}/icon", content=SVG).status_code == 403


def test_weather_without_hourly(client, monkeypatch):
    """A key or plan without the hourly forecast still shows the conditions and the days ahead."""
    fake = _fake_accuweather([])

    def get(path, **params):
        if "hourly" in path:
            raise weather.WeatherError("AccuWeather answered 403")
        return fake(path, **params)
    monkeypatch.setattr(weather, "_get", get)
    client.post("/api/weather/settings", json={"key": "abc", "locationKey": "349727", "locationName": "New York"})
    w = client.get("/api/weather").json()
    assert w["current"]["text"] == "Sunny" and w["hourly"] == [] and not w["stale"]
