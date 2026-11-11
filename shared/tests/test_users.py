import pytest

from iosuite_shared import apppasswords, sessions, users


def test_create_authenticate_roles():
    assert not users.any_users()
    u = users.create("alex", "secret123", "admin", "iopix", email="Alex@Example.com", suite_admin=True)
    assert u["email"] == "alex@example.com" and u["suiteAdmin"] and u["role"] == "admin"
    assert users.any_users()
    assert users.authenticate("alex", "wrong") is None
    assert users.authenticate("alex", "secret123", "ionotes")["role"] == "admin"  # a suite admin everywhere
    assert users.authenticate("ALEX@example.com", "secret123")["id"] == u["id"]  # by email, case-insensitive
    v = users.create("kid", "", "viewer", "iopix")
    assert v["passwordless"] and v["role"] == "viewer"
    assert users.role_of(v, "ionotes") == "member"  # the default role
    users.db.set_setting("default_role", "none", "ionotes")
    assert users.role_of(v, "ionotes") == "none"
    with pytest.raises(ValueError):
        users.set_role(v["id"], "iopix", "bogus")
    with pytest.raises(ValueError):
        users.update(v["id"], role="editor", app="iopix")  # no password: member at most
    users.update(v["id"], role="member", app="iopix")  # a member is fine without one
    assert users.get(v["id"], "iopix")["role"] == "member"
    users.update(v["id"], password="longenough", role="editor", app="iopix")
    assert users.get(v["id"], "iopix")["role"] == "editor"
    assert users.get(v["id"], "ionotes")["role"] == "none"
    with pytest.raises(ValueError):
        users.update(v["id"], password="")  # an editor somewhere: keeps its password
    with pytest.raises(ValueError):
        users.create("Alex", "another12")  # names are unique, case-insensitively
    with pytest.raises(ValueError):
        users.delete(u["id"])  # the only suite admin
    assert [a["name"] for a in users.accounts("ionotes")] == ["alex"]  # kid has no access there
    assert {a["name"] for a in users.accounts("iopix")} == {"alex", "kid"}


def test_settings_and_data():
    u = users.create("alex", "secret123")
    assert users.get_settings(u["id"], "iopix") == {}
    out = users.set_settings(u["id"], "iopix", {"theme": "dark", "grid": 4, "x" * 65: "ignored"})
    assert out == {"theme": "dark", "grid": 4}
    assert users.set_settings(u["id"], "iopix", {"theme": None}) == {"grid": 4}
    assert users.get_settings(u["id"], "ionotes") == {}  # per app
    users.set_value(u["id"], "iopix", "person", 42)
    assert users.get_value(u["id"], "iopix", "person") == 42
    users.set_value(u["id"], "iopix", "person", None)
    assert users.get_value(u["id"], "iopix", "person") is None


def test_sessions():
    u = users.create("alex", "secret123", "editor", "iopix")
    tok = sessions.create(u["id"], "iopix", "password")
    got = sessions.user_from_token(tok, "ionotes")  # the same session serves another app, with the role there
    assert got["id"] == u["id"] and got["role"] == "member"
    users.update(u["id"], password="changed123")  # ends every session
    assert sessions.user_from_token(tok, "iopix") is None
    tok = sessions.create(u["id"], "iopix", "password")
    sessions.end_all(u["id"])
    assert sessions.user_from_token(tok, "iopix") is None
    assert sessions.user_from_token("garbage", "iopix") is None


def test_cookie_domain(monkeypatch):
    monkeypatch.setattr("iosuite_shared.config.COOKIE_DOMAIN", "example.com")
    assert sessions.cookie_domain("photo.example.com") == "example.com"
    assert sessions.cookie_domain("notes.example.com:8610") == "example.com"
    assert sessions.cookie_domain("192.168.1.5:8600") is None
    assert sessions.cookie_domain("evil-example.com") is None


def test_app_passwords():
    u = users.create("alex", "secret123", "editor", "iocontacts")
    pw = apppasswords.create(u["id"], "iocontacts", "Phone")
    assert pw.startswith("iocontacts-")
    assert apppasswords.authenticate("alex", pw, "iocontacts")["id"] == u["id"]
    assert apppasswords.authenticate(None, pw, "iocontacts")["id"] == u["id"]  # bearer: no name needed
    assert apppasswords.authenticate("alex", pw, "iopix") is None  # one app only
    assert apppasswords.authenticate("alex", "secret123", "iocontacts")["id"] == u["id"]  # the account password works too
    assert apppasswords.authenticate("alex", "nope", "iocontacts") is None
    assert len(apppasswords.list_for(u["id"], "iocontacts")) == 1
    apppasswords.delete(u["id"], apppasswords.list_for(u["id"], "iocontacts")[0]["id"])
    assert apppasswords.authenticate("alex", pw, "iocontacts") is None


def test_a_hash_with_other_parameters_or_scrypt_is_upgraded_and_the_old_format_refused():
    from argon2 import PasswordHasher
    from iosuite_shared import db
    from iosuite_shared.passwords import hash_password, needs_rehash
    import base64, hashlib, os
    salt = os.urandom(16)
    h = hashlib.scrypt(b"oldpass123", salt=salt, n=2 ** 13, r=8, p=1, dklen=32)
    scrypt2 = f"scrypt2$8192$8$1${base64.b64encode(salt).decode()}${base64.b64encode(h).decode()}"
    weaker = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("weakpass123")
    db.ex("INSERT INTO ios_users (name, hash, created_at) VALUES ('old', %s, 1), ('weak', %s, 1)", (scrypt2, weaker))
    assert needs_rehash(scrypt2) and needs_rehash(weaker) and not needs_rehash(hash_password("x"))
    for name, pw in (("old", "oldpass123"), ("weak", "weakpass123")):
        assert users.authenticate(name, "wrong-password") is None
        u = users.authenticate(name, pw)
        stored = db.one("SELECT hash FROM ios_users WHERE id = %s", (u["id"],))["hash"]
        assert stored.startswith("$argon2id$") and not needs_rehash(stored) and users.authenticate(name, pw)
    # the format from before the suite (scrypt$salt$hash) is not read
    legacy = f"scrypt${base64.b64encode(salt).decode()}${base64.b64encode(h).decode()}"
    db.ex("INSERT INTO ios_users (name, hash, created_at) VALUES ('older', %s, 1)", (legacy,))
    assert users.authenticate("older", "oldpass123") is None


def test_app_passwords_are_stored_as_sha256_and_scrypt_rows_move_over():
    from iosuite_shared import db
    from iosuite_shared.passwords import token_hash
    import base64, hashlib, os
    u = users.create("alex", "secret123", "editor", "iocontacts")
    pw = apppasswords.create(u["id"], "iocontacts", "Mac")
    assert db.one("SELECT hash FROM ios_app_passwords")["hash"] == token_hash(pw)
    assert apppasswords.authenticate(None, pw, "iocontacts")["id"] == u["id"]
    # a row from 0.24 (scrypt2) still signs in, and is rewritten to the SHA-256
    salt = os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 13, r=8, p=1, dklen=32)
    db.ex("UPDATE ios_app_passwords SET hash = %s", (f"scrypt2$8192$8$1${base64.b64encode(salt).decode()}${base64.b64encode(h).decode()}",))
    apppasswords.forget()
    assert apppasswords.authenticate(None, pw[:-1] + ("x" if pw[-1] != "x" else "y"), "iocontacts") is None
    assert apppasswords.authenticate(None, pw, "iocontacts")["id"] == u["id"]
    assert db.one("SELECT hash FROM ios_app_passwords")["hash"] == token_hash(pw)


def test_sign_in_by_name_never_picks_another_account_by_its_email():
    bob = users.create("bob", "secret123", "viewer", "iopix")
    users.create("alex@example.com", "other-pass", "viewer", "iopix")
    users.update(bob["id"], email="alex@example.com")
    assert users.authenticate("alex@example.com", "other-pass")["name"] == "alex@example.com"
    assert users.authenticate("alex@example.com", "secret123") is None  # the name wins; bob's email is not tried
    assert users.authenticate("bob", "secret123")["name"] == "bob"


def test_role_ladder_and_markers():
    users.create("alex", "secret123", suite_admin=True)
    v = users.create("vic", "secret123", "viewer", "iocalendar")
    m = users.create("meg", "secret123", "member", "iocalendar")
    e = users.create("ed", "secret123", "editor", "iocalendar")
    for u, member, writer in ((v, False, False), (m, True, False), (e, True, True)):
        u = users.get(u["id"], "iocalendar")
        assert users.is_signed_in(u) and users.is_member(u) is member and users.can_write(u) is writer
    assert users.role_of(users.get(v["id"]), "ionotes") == "member"  # no row: the default, member
    users.db.set_setting("default_role", "viewer", "ionotes")
    assert users.role_of(users.get(v["id"]), "ionotes") == "viewer"


def test_admin_tools_are_for_suite_admins_only():
    from iosuite_shared import admin, suite
    suite.register("iodns", name="ioDNS", admin_tool=True)
    suite.register("iocalendar", name="ioCalendar")
    boss = users.create("alex", "secret123", suite_admin=True)
    ed = users.create("ed", "secret123", "admin", "iodns")  # a row from before: ignored
    assert users.role_of(users.get(boss["id"]), "iodns") == "admin"
    assert users.role_of(users.get(ed["id"]), "iodns") == "none" and users.default_role("iodns") == "none"
    assert [a["app"] for a in suite.visible(users.get(ed["id"]))] == ["iocalendar"]
    assert {a["app"] for a in suite.visible(users.get(boss["id"]))} == {"iocalendar", "iodns"}
    with pytest.raises(ValueError):
        admin.set_roles(boss, ed["id"], {"iodns": "admin"})
    with pytest.raises(ValueError):
        admin.set_app("iodns", default_role="member")
    eff = {u["name"]: u["effective"] for u in admin.accounts()}
    assert eff["ed"]["iodns"] == "none" and eff["alex"]["iodns"] == "admin"
    svc = users.service_account("iosuite")
    users.set_role(svc["id"], "iodns", "viewer")  # an app reading an admin tool keeps the role links gave it
    assert users.role_of(users.get(svc["id"]), "iodns") == "viewer"


def test_viewers_become_members_once():
    from iosuite_shared import db, schema
    users.create("alex", "secret123", suite_admin=True)
    v = users.create("vic", "secret123", "viewer", "iocalendar")
    svc = users.service_account("iosuite")
    users.set_role(svc["id"], "iocalendar", "viewer")
    db.set_setting("default_role", "viewer", "iotasks")
    with db.tx() as con, con.cursor() as cur:
        cur.execute("DELETE FROM ios_schema_version WHERE version >= 6")
    db._ready = False
    db.init()
    assert users.roles_of(v["id"]) == {"iocalendar": "member"}
    assert users.roles_of(svc["id"]) == {"iocalendar": "viewer"}  # the apps' own accounts only read
    assert db.get_setting("default_role", "", "iotasks") == ""
    users.set_role(v["id"], "iocalendar", "viewer")  # a viewer set after the change stays one
    db._ready = False
    db.init()
    assert users.roles_of(v["id"]) == {"iocalendar": "viewer"}
    with db.tx() as con, con.cursor() as cur:
        assert schema.current_version(cur, db.PREFIX) == db.SCHEMA_VERSION
