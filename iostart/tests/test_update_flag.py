"""The tiles' update flag follows the rows the apps write (as Settings › Global settings › Updates does), so it goes
away as soon as an updated app starts again, and says when only the shared library is new."""
from iosuite_shared import suite, suiteupdates

from app import status


def test_the_update_flag_follows_the_apps_rows(client):
    for key in ("iopix", "ionote", "iocalendar"):
        suite.register(key, name=key, version="1.0.0")
    suiteupdates.publish("iopix", installed="1.0.0", latest="1.0.0", status="current")              # updated and started again
    suiteupdates.publish("ionote", installed="1.0.0", latest="1.1.0", shared="0.1.0", latest_shared="0.1.0", status="update")
    suiteupdates.publish("iocalendar", installed="1.0.0", latest="1.0.0", shared="0.1.0", latest_shared="0.2.0", status="update")
    asked = {k: {"ok": True, "version": "1.0.0", "update": "1.1.0", "why": None} for k in ("iopix", "ionote", "iocalendar", "iotask")}
    out = status._settled(asked)
    assert out["iopix"]["update"] is None
    assert out["ionote"]["update"] and out["ionote"]["note"] == "v1.1.0 is out (now v1.0.0)"
    assert out["iocalendar"]["update"] and "shared library v0.2.0" in out["iocalendar"]["note"]
    assert out["iotask"]["update"] == "1.1.0" and "note" not in out["iotask"]  # no row: what the app said
