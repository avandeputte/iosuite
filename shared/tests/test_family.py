"""The family: one list for the whole suite (iosuite_shared.family), changed by suite admins at /api/suite-admin/family."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from iosuite_shared import family, users
from iosuite_shared.fastapi import Auth


def make_app():
    auth = Auth("iocalendar", register=False)
    app = FastAPI()
    app.middleware("http")(auth.middleware(open_prefixes=("/api/auth/",)))
    app.include_router(auth.router())
    app.include_router(auth.admin_router())
    return app


def signed_in(app, name, password):
    c = TestClient(app, base_url="http://home.example.com")
    assert c.post("/api/auth/login", json={"name": name, "password": password}).status_code == 200
    return c


def test_initials():
    assert family.initials("Emma Smith") == "ES"
    assert family.initials("emma") == "E"
    assert family.initials("Jan van der Berg") == "JB"
    assert family.initials("") == "?"


def test_everyone_is_in_the_family_with_a_colour_of_their_own():
    family.forget()
    a = users.create("alex", "secret123", suite_admin=True, display_name="Alex")
    users.create("emma", "secret123", display_name="Emma Smith")
    users.service_account("iocalendar")  # an app's own account is never family
    fam = family.members()
    assert [m["name"] for m in fam] == ["alex", "emma"]
    assert [m["initials"] for m in fam] == ["A", "ES"]
    assert [m["color"] for m in fam] == family.PALETTE[:2]
    # a picked colour is kept; the others skip it
    family.update(a["id"], {"color": family.PALETTE[1]})
    fam = family.members()
    assert fam[0]["color"] == family.PALETTE[1] and fam[0]["colorPicked"] and fam[1]["color"] == family.PALETTE[0]
    family.update(a["id"], {"color": None})
    assert not family.get(a["id"])["colorPicked"]


def test_out_of_the_family_and_links():
    family.forget()
    users.create("alex", "secret123", suite_admin=True)
    admin = users.create("admin", "secret123")
    emma = users.create("emma", "secret123")
    family.update(admin["id"], {"inFamily": False})
    assert [m["name"] for m in family.members()] == ["alex", "emma"] and not family.in_family(admin["id"])
    assert family.get(admin["id"])["inFamily"] is False
    # the links are the values ioContact and ioPix keep for the account
    m = family.update(emma["id"], {"contactId": 12, "photoPerson": "7"})
    assert (m["contactId"], m["photoPerson"], m["hasFace"]) == (12, 7, True)
    assert users.get_value(emma["id"], "iocontact", "me_contact_id") == 12 and users.get_value(emma["id"], "iopix", "person") == 7
    m = family.update(emma["id"], {"contactId": None, "photoPerson": None})
    assert (m["contactId"], m["photoPerson"], m["hasFace"]) == (None, None, False)
    family.update(admin["id"], {"inFamily": True})
    assert family.in_family(admin["id"])


def test_routes():
    family.forget()
    users.create("alex", "secret123", suite_admin=True)
    emma = users.create("emma", "secret123")
    app = make_app()
    adm, kid = signed_in(app, "alex", "secret123"), signed_in(app, "emma", "secret123")
    items = kid.get("/api/auth/family").json()["items"]
    assert [m["name"] for m in items] == ["alex", "emma"] and set(items[0]) == {"id", "name", "displayName", "initials", "color", "hasFace"}
    assert kid.patch(f"/api/suite-admin/family/{emma['id']}", json={"color": "#112233"}).status_code == 403
    assert adm.patch(f"/api/suite-admin/family/{emma['id']}", json={"color": "red"}).status_code == 400
    assert adm.patch("/api/suite-admin/family/9999", json={"inFamily": False}).status_code == 404
    r = adm.patch(f"/api/suite-admin/family/{emma['id']}", json={"color": "#112233", "inFamily": False})
    assert r.status_code == 200 and r.json()["color"] == "#112233" and r.json()["inFamily"] is False
    body = adm.get("/api/suite-admin/family").json()
    assert [m["name"] for m in body["items"]] == ["alex", "emma"] and body["palette"] == family.PALETTE
    assert [m["name"] for m in kid.get("/api/auth/family").json()["items"]] == ["alex"]
    assert kid.get(f"/api/auth/family/{emma['id']}/face").status_code == 404  # no face linked
    assert adm.get("/api/suite-admin/family/contacts?q=x").json() == {"available": False, "items": []}  # no ioContact here
