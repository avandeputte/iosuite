"""The demo data (app/demo.py, iosuite_shared.demo) goes into a fresh database with the app's own code, once, and the
family signs in to see it."""
from iosuite_shared import demo

from app import config, db, demo as app_demo


def test_the_demo_data_goes_in_once(client):
    assert demo.run(config.APP, app_demo.seed)
    assert db.one("SELECT count(*) AS n FROM mny_transactions")["n"] > 200
    assert not demo.run(config.APP, app_demo.seed)  # once
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": "riley", "password": demo.DEMO_PASSWORD}).status_code == 200
