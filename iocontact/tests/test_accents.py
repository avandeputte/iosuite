"""Searches ignore accents and case: "celia" finds "Célia", wherever search is offered."""
import asyncio
import threading
import time
import unicodedata

import pytest

from app import users
from app.fold import fold
from tests.test_carddav import dav
from tests.test_mcp import app_password, call


def test_fold():
    assert fold("Célia") == "celia"
    assert fold(unicodedata.normalize("NFD", "Zoé")) == "zoe"
    assert fold("Ørsted Łukasz Đorđe Strauß Æsa") == "orsted lukasz dorde strauss aesa"


def _people(client, book):
    for n in ("Célia Dupont", unicodedata.normalize("NFD", "Zoé Martin"), "Søren Ørsted", "Bob Ray"):
        client.post(f"/api/contacts?book={book}", json={"fn": n})


def names(client, q):
    return [x["fn"] for x in client.get("/api/contacts", params={"q": q}).json()["items"]]


def test_rest_search_ignores_accents(client, family_id):
    _people(client, family_id)
    assert names(client, "celia") == ["Célia Dupont"]
    assert names(client, "CÉLIA") == ["Célia Dupont"]
    assert names(client, "celia dupont") == ["Célia Dupont"]
    assert [unicodedata.normalize("NFC", n) for n in names(client, "zoe")] == ["Zoé Martin"]
    assert names(client, "orsted") == ["Søren Ørsted"]
    assert names(client, "célia") == ["Célia Dupont"] and names(client, "rây") == ["Bob Ray"]


def test_mcp_search_ignores_accents(client, family_id):
    _people(client, family_id)
    auth, _ = app_password(client)
    client.post("/api/server", json={"mcpEnabled": True})
    found = call(client, auth, "search_contacts", text="celia")
    assert found["total"] == 1 and found["contacts"][0]["name"] == "Célia Dupont"
    assert call(client, auth, "get_contact", contact="celia dupont")["fn"] == "Célia Dupont"


def test_carddav_text_match_ignores_accents(client, family_id):
    _people(client, family_id)
    qy = """<card:addressbook-query xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav"><d:prop><d:getetag/><card:address-data/></d:prop>
    <card:filter><card:prop-filter name="FN"><card:text-match match-type="starts-with">celia</card:text-match></card:prop-filter></card:filter>
    </card:addressbook-query>"""
    r = dav(client, "REPORT", "/dav/addressbooks/alex/family/", qy)
    assert "Célia Dupont" in r.text and "Bob Ray" not in r.text


def test_ldap_search_ignores_accents(client, family_id):
    ldap3 = pytest.importorskip("ldap3")
    _people(client, family_id)
    from app import ldapd
    loop = asyncio.new_event_loop()
    srv = loop.run_until_complete(ldapd.serve("127.0.0.1", 0))
    port = srv.sockets[0].getsockname()[1]
    threading.Thread(target=loop.run_forever, daemon=True).start()
    try:
        c = ldap3.Connection(ldap3.Server("127.0.0.1", port=port, get_info=ldap3.NONE),
                             "cn=alex,ou=users,dc=iocontact", users.create_app_password(users.find("alex")["id"], "Mail"), auto_bind=True)
        c.search("dc=iocontact", "(cn=*celia*)", attributes=["cn"])
        assert [e.cn.value for e in c.entries] == ["Célia Dupont"]
        c.search("dc=iocontact", "(cn=soren orsted)", attributes=["cn"])
        assert [e.cn.value for e in c.entries] == ["Søren Ørsted"]
        c.unbind()
    finally:
        loop.call_soon_threadsafe(srv.close)
        loop.call_soon_threadsafe(loop.stop)
        time.sleep(0.1)
