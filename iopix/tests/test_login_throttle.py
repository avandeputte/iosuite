"""Sign-in attempts: after a few wrong passwords, each further try has to wait, longer every time."""
from iosuite_shared import users as shared_users
from app import users


def test_repeated_wrong_passwords_are_slowed_down(client, fresh):
    users.create("brute-probe", "longpassword1", "viewer")
    shared_users._attempts.clear()
    for _ in range(shared_users.LOCK_AFTER):
        assert client.post("/api/auth/login", json={"name": "brute-probe", "password": "nope"}).status_code == 401
    assert client.post("/api/auth/login", json={"name": "brute-probe", "password": "nope"}).status_code == 401, "the sixth failure starts the wait"
    r = client.post("/api/auth/login", json={"name": "brute-probe", "password": "longpassword1"})
    assert r.status_code == 429 and "try again" in r.json()["detail"] and int(r.headers["retry-after"]) >= shared_users.LOCK_BASE, "even the right password waits"
    assert client.post("/api/auth/login", json={"name": "someone-else", "password": "nope"}).status_code == 401, "another account is not held up"
    shared_users._attempts.clear()
    r = client.post("/api/auth/login", json={"name": "brute-probe", "password": "longpassword1"})
    assert r.status_code == 200
    client.post("/api/auth/logout", json={})
    assert shared_users.login_wait("x") == 0
