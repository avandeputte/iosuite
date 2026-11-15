"""The weather on the calendar: the start page's place, Open-Meteo's forecast, an event's place looked up once."""
import datetime as dt

import pytest

from app import weather

T0 = int(dt.datetime(2026, 11, 15, tzinfo=dt.timezone.utc).timestamp()) - 3600  # midnight in Brussels (UTC+1)
FORECAST = {
    "utc_offset_seconds": 3600,
    "daily": {"time": [T0 + i * 86400 for i in range(7)], "weather_code": [0, 2, 3, 61, 71, 95, 45],
              "temperature_2m_max": [12.4, 11, 10, 9, 2, 14, 8], "temperature_2m_min": [4, 5, 3, 2, -1, 7, 1],
              "precipitation_probability_max": [0, 10, 20, 80, 60, 70, 5]},
    "hourly": {"time": [T0 + i * 3600 for i in range(168)], "weather_code": [3] * 168,
               "temperature_2m": [float(i % 24) for i in range(168)], "precipitation_probability": [40] * 168},
}


@pytest.fixture()
def net(monkeypatch):
    """Open-Meteo and Nominatim answering from here, ioStart's place; what was asked."""
    weather.forget()
    asked = []
    place = {"name": "Gent, East Flanders, Belgium", "units": "metric"}

    def fetch(url, headers=None):
        asked.append(url)
        if "nominatim" in url:
            if "Nowhere" in url:
                return []
            return [{"lat": "51.0543", "lon": "3.7174", "display_name": "Gent, East Flanders, Belgium"}]
        return FORECAST
    monkeypatch.setattr(weather, "_fetch_json", fetch)
    monkeypatch.setattr(weather.links, "available", lambda app: app == "iostart")
    monkeypatch.setattr(weather.links, "json", lambda reader, app, path, timeout=15: place)
    monkeypatch.setattr(weather, "_last_geo", [0.0])
    yield asked, place
    weather.forget()


def test_the_next_days_at_the_start_pages_place(client, net):
    asked, _ = net
    r = client.get("/api/weather").json()
    assert r["enabled"] is True and r["place"] == "Gent" and r["units"] == "metric"
    assert [d["date"] for d in r["days"]][:2] == ["2026-11-15", "2026-11-16"]
    assert r["days"][0] == {"date": "2026-11-15", "code": 0, "max": 12.4, "min": 4, "rain": 0}
    assert len(asked) == 2  # the place once, the forecast once
    client.get("/api/weather")
    weather.forget()  # memory gone (a restart): the place is still known, only the forecast is asked again
    client.get("/api/weather")
    assert len([u for u in asked if "nominatim" in u]) == 1 and len(asked) == 3


def test_no_place_on_the_start_page_no_weather(client, net):
    _, place = net
    place["name"] = ""
    assert client.get("/api/weather").json() == {"enabled": False, "days": []}


def test_without_the_start_page_no_weather(client, net, monkeypatch):
    monkeypatch.setattr(weather.links, "available", lambda app: False)
    assert client.get("/api/weather").json()["enabled"] is False


def test_open_meteo_away_says_so(client, net, monkeypatch):
    def down(url, headers=None):
        if "nominatim" in url:
            return [{"lat": "51", "lon": "3.7"}]
        raise weather.WeatherError("Could not reach api.open-meteo.com")
    monkeypatch.setattr(weather, "_fetch_json", down)
    r = client.get("/api/weather").json()
    assert r["days"] == [] and "open-meteo" in r["error"]


def test_an_event_with_a_place_gets_the_weather_there(client, net, family_id):
    asked, _ = net
    e = client.post("/api/events", json={"calendarId": family_id, "title": "Market", "location": "Vrijdagmarkt, Gent",
                                         "start": "2026-11-17T09:30:00Z", "end": "2026-11-17T11:00:00Z"}).json()
    r = client.get(f"/api/events/{e['id']}/weather", params={"start": "2026-11-17T09:30:00Z"}).json()
    assert r["found"] is True and r["place"] == "Gent"
    assert r["hour"]["t"] in (T0 + 58 * 3600, T0 + 59 * 3600)  # 10:30 in Gent: the hour beside it
    assert r["day"]["date"] == "2026-11-17" and r["day"]["code"] == 3
    client.get(f"/api/events/{e['id']}/weather", params={"start": "2026-11-17T09:30:00Z"})
    assert len([u for u in asked if "Vrijdagmarkt" in u]) == 1  # looked up once
    assert all("Market" not in u for u in asked)  # only the place leaves the server
    # all day: the day's forecast
    a = client.post("/api/events", json={"calendarId": family_id, "title": "Trip", "location": "Gent", "allDay": True,
                                         "start": "2026-11-19", "end": "2026-11-20"}).json()
    r = client.get(f"/api/events/{a['id']}/weather", params={"start": "2026-11-19"}).json()
    assert r["day"]["code"] == 71 and "hour" not in r
    # outside the forecast: found, but nothing to show
    r = client.get(f"/api/events/{a['id']}/weather", params={"start": "2027-01-01"}).json()
    assert r["found"] is True and "day" not in r


def test_places_nobody_knows_and_events_without_one(client, net, family_id):
    asked, _ = net
    e = client.post("/api/events", json={"calendarId": family_id, "title": "x", "location": "Nowhere at all",
                                         "start": "2026-11-17T09:30:00Z", "end": "2026-11-17T11:00:00Z"}).json()
    assert client.get(f"/api/events/{e['id']}/weather", params={"start": "2026-11-17T09:30:00Z"}).json()["found"] is False
    client.get(f"/api/events/{e['id']}/weather", params={"start": "2026-11-17T09:30:00Z"})
    assert len([u for u in asked if "Nowhere" in u]) == 1  # a miss is kept too
    n = client.post("/api/events", json={"calendarId": family_id, "title": "y", "start": "2026-11-17T09:30:00Z",
                                         "end": "2026-11-17T11:00:00Z"}).json()
    assert client.get(f"/api/events/{n['id']}/weather", params={"start": "2026-11-17"}).json() == {"found": False}
    m = client.post("/api/events", json={"calendarId": family_id, "title": "z", "location": "https://meet.example.org/abc",
                                         "start": "2026-11-17T09:30:00Z", "end": "2026-11-17T11:00:00Z"}).json()
    assert client.get(f"/api/events/{m['id']}/weather", params={"start": "2026-11-17T09:30:00Z"}).json()["found"] is False
    assert not any("meet.example" in u for u in asked)  # a meeting link is not looked up
    assert client.get("/api/events/999999/weather", params={"start": "2026-11-17"}).status_code == 404
