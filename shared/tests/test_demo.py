"""The demo data's shared part (iosuite_shared.demo): the family's accounts, the switch, an app seeded once, and the
stack's --demo only on a new suite."""
from iosuite_shared import cli, db, demo, family, stack, users


def test_the_family_is_made_once_with_its_colours_and_roles():
    people = demo.ensure()
    assert [p["name"] for p in people.values()] == ["morgan", "riley", "ava", "theo"]
    assert demo.ensure()["ava"]["id"] == people["ava"]["id"] and len(users.list_users()) == 4  # again: nobody made twice
    assert users.authenticate("riley", demo.DEMO_PASSWORD)
    assert users.get(people["morgan"]["id"])["suiteAdmin"] and not users.get(people["riley"]["id"])["suiteAdmin"]
    fam = {m["name"]: m for m in family.members()}
    assert fam["theo"]["color"] == "#e8710a" and fam["ava"]["displayName"] == "Ava Calloway"
    demo.give_roles("iocalendar", people)
    assert users.roles_of(people["riley"]["id"]) == {"iocalendar": "admin"} and users.roles_of(people["theo"]["id"]) == {"iocalendar": "member"}


def test_an_app_is_seeded_once_while_the_switch_is_on():
    calls = []
    seed = lambda people: calls.append(sorted(people))  # noqa: E731
    demo.at_start("iotask", seed)
    assert calls == [] and not users.any_users()  # the switch is off: nothing at all
    demo.switch(True)
    demo.at_start("iotask", seed)
    demo.at_start("iotask", seed)
    assert calls == [["ava", "morgan", "riley", "theo"]] and demo.seeded("iotask")
    demo.at_start("iocalendar", lambda people: 1 / 0)  # a seed that fails is logged, never stops the app, and is not tried again
    assert demo.seeded("iocalendar")
    assert demo.run("iotask", seed, force=True) and len(calls) == 2


def test_the_stack_adds_the_demo_to_a_new_suite_only(monkeypatch):
    monkeypatch.setattr("iosuite_shared.config.ADMIN_USER", "admin")
    monkeypatch.setattr("iosuite_shared.config.ADMIN_PASSWORD", "long-enough-1")
    cli.main(["stack", "--demo"])
    assert demo.wanted() and sorted(u["name"] for u in users.list_users()) == ["admin", "ava", "morgan", "riley", "theo"]
    cli.main(["stack", "--demo"])  # every later `up`: nothing new
    assert len(users.list_users()) == 5
    # a suite that is used for real is left alone
    demo.switch(False)
    users.create("dana", "long-enough-2")
    db.settings_cache.clear()
    assert stack.demo_once(log=lambda *_: None) is False and not demo.wanted()


def test_the_command_turns_it_on_and_off(capsys):
    cli.main(["demo", "--no-restart"])
    assert demo.wanted() and len(users.list_users()) == 4
    assert "calloway" in capsys.readouterr().out
    cli.main(["demo", "--off"])
    assert not demo.wanted() and len(users.list_users()) == 4  # nothing removed


def test_a_picture_is_drawn():
    import io
    import pytest
    Image = pytest.importorskip("PIL.Image")  # the apps with pictures have Pillow; the library alone does not need it
    raw = demo.picture("Pancakes", "#e8a100", (300, 200))
    im = Image.open(io.BytesIO(raw))
    assert im.size == (300, 200) and im.format == "JPEG"
