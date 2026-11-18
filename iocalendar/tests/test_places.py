"""Place suggestions while typing an event's place: Google Places with the suite's Google key, kept on the server."""
import pytest

from app import places
from iosuite_shared import credentials

ANSWER = {"suggestions": [
    {"placePrediction": {"text": {"text": "Ghent Airport, Gent, Belgium"},
                         "structuredFormat": {"mainText": {"text": "Ghent Airport"}, "secondaryText": {"text": "Gent, Belgium"}}}},
    {"placePrediction": {"text": {"text": "Gentbrugge, Gent, Belgium"}}},
    {"queryPrediction": {"text": {"text": "gent restaurants"}}},  # a search, not a place: left out
]}


@pytest.fixture()
def google(monkeypatch):
    places.forget()
    asked = []

    def post(body, k):
        asked.append((body, k))
        return ANSWER
    monkeypatch.setattr(places, "_post", post)
    monkeypatch.setattr(places, "_near", lambda: (51.05, 3.72))
    yield asked
    credentials.put("iopix", "google_server_key", "")
    credentials.put("iopix", "google_maps_key", "")
    places.forget()


def test_no_google_key_no_suggestions(client, google):
    assert client.get("/api/status").json()["places"] is False
    assert client.get("/api/places?q=Ghent").json() == {"enabled": False, "items": []}
    assert google == []


def test_suggestions_with_the_suite_key(client, google):
    credentials.put("iopix", "google_maps_key", "browser-key")
    assert client.get("/api/status").json()["places"] is True
    r = client.get("/api/places?q=Ghent%20Air&session=abc").json()
    assert r == {"enabled": True, "items": [
        {"text": "Ghent Airport, Gent, Belgium", "main": "Ghent Airport", "secondary": "Gent, Belgium"},
        {"text": "Gentbrugge, Gent, Belgium", "main": "Gentbrugge, Gent, Belgium", "secondary": ""}]}
    body, k = google[0]
    assert k == "browser-key" and body["input"] == "Ghent Air" and body["sessionToken"] == "abc"
    assert body["locationBias"]["circle"]["center"] == {"latitude": 51.05, "longitude": 3.72}
    client.get("/api/places?q=ghent%20air")  # the same text again: from memory
    assert len(google) == 1


def test_server_key_first_and_short_text_not_asked(client, google):
    credentials.put("iopix", "google_maps_key", "browser-key")
    credentials.put("iopix", "google_server_key", "server-key")
    assert client.get("/api/places?q=Gh").json() == {"enabled": True, "items": []}
    assert client.get("/api/places?q=https://meet.example.com/x").json()["items"] == []
    assert google == []
    client.get("/api/places?q=Kerkstraat")
    assert google[0][1] == "server-key"


def test_google_refusing_is_shown(client, google, monkeypatch):
    credentials.put("iopix", "google_maps_key", "browser-key")

    def refuse(body, k):
        raise places.PlacesError("Google Places answered 403: Places API (New) has not been used in project 1")
    monkeypatch.setattr(places, "_post", refuse)
    r = client.get("/api/places?q=Kerkstraat").json()
    assert r["items"] == [] and "Places API (New)" in r["error"]


def test_signed_in_only(client, google):
    client.cookies.clear()
    assert client.get("/api/places?q=Ghent").status_code == 401
