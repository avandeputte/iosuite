import asyncio
import threading
import time

import pytest

ldap3 = pytest.importorskip("ldap3")


def test_ldap_search(client, family_id):
    client.post(f"/api/contacts?book={family_id}", json={"fn": "Ann Lee", "name": {"given": "Ann", "family": "Lee"},
                "emails": [{"value": "ann@lee.org"}], "phones": [{"label": "mobile", "value": "+1 555 1234"}],
                "org": "Lee Co", "addresses": [{"label": "home", "street": "1 Elm", "city": "Paris", "country": "FR"}]})
    client.post(f"/api/contacts?book={family_id}", json={"fn": "Bob Ray", "emails": [{"value": "bob@ray.org"}], "birthday": {"year": 1975}})
    from app import ldapd
    loop = asyncio.new_event_loop()
    srv = loop.run_until_complete(ldapd.serve("127.0.0.1", 0))
    port = srv.sockets[0].getsockname()[1]
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    try:
        s = ldap3.Server("127.0.0.1", port=port, get_info=ldap3.NONE)
        anon = ldap3.Connection(s, auto_bind=True)
        anon.search("dc=iocontacts", "(mail=*)")
        assert anon.result["result"] == 50 and not anon.entries
        assert not ldap3.Connection(s, "cn=alex,ou=users,dc=iocontacts", "wrong").bind()
        # the directory is not encrypted: it takes an app password, never the account's own password
        refused = ldap3.Connection(s, "cn=alex,ou=users,dc=iocontacts", "secret123")
        assert not refused.bind() and "app password" in refused.result["message"]
        from app import users
        c = ldap3.Connection(s, "cn=alex,ou=users,dc=iocontacts", users.create_app_password(users.find("alex")["id"], "Mail"), auto_bind=True)
        c.search("dc=iocontacts", "(|(cn=*ann*)(mail=*ann*)(sn=*ann*))", attributes=["cn", "mail", "mobile", "o", "mozillaHomeLocalityName", "c"])
        assert len(c.entries) == 1
        e = c.entries[0]
        assert e.cn.value == "Ann Lee" and e.mail.value == "ann@lee.org" and e.o.value == "Lee Co"
        assert e.mozillaHomeLocalityName.value == "Paris" and e.c.value == "FR"
        c.search("ou=contacts,dc=iocontacts", "(&(objectClass=inetOrgPerson)(mail=bob@ray.org))", attributes=["*"])
        assert len(c.entries) == 1 and c.entries[0].sn.value == "Ray"
        assert c.entries[0].birthyear.value == "1975" and "birthmonth" not in c.entries[0]  # a year-only birthday
        c.search("dc=iocontacts", "(objectClass=*)", size_limit=1)
        assert len(c.entries) == 1
        c.search("dc=iocontacts", "(mobile=15551234)", attributes=["cn"])
        assert len(c.entries) == 1
        assert not c.add("cn=x,dc=iocontacts", "inetOrgPerson", {"sn": "x"})
        c.unbind()
    finally:
        loop.call_soon_threadsafe(srv.close)
        loop.call_soon_threadsafe(loop.stop)
        time.sleep(0.1)
