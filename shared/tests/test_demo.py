"""The demo switch (iosuite_shared.demo) and the demo package it fetches (iosuite_demo, the repository's demo/): the
family's accounts, an app seeded once while the switch is on, a package that cannot be fetched tried again later, the
stack's --demo only on a new suite, and the command."""
import os
import shutil
import sys
import zipfile
from pathlib import Path

from iosuite_shared import cli, db, demo, family, stack, users


def test_the_package_is_found_and_dropped_again(tmp_path, monkeypatch):
    with demo.package():
        import iosuite_demo
        assert iosuite_demo.__file__.endswith("demo/iosuite_demo/__init__.py")
    assert "iosuite_demo" not in sys.modules and not any("demo" == p.rsplit("/", 1)[-1] for p in sys.path)
    zpath = tmp_path / "iosuite-demo.zip"  # the release's zip: imported straight from it, the download removed after
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("iosuite_demo/__init__.py", "WHERE = 'zip'\n")
    monkeypatch.setenv("DEMO_PACKAGE", zpath.as_uri())
    with demo.package():
        import iosuite_demo
        assert iosuite_demo.WHERE == "zip"
        fetched = iosuite_demo.__file__
    assert "iosuite_demo" not in sys.modules and not os.path.exists(fetched.split(".zip")[0] + ".zip")


def test_the_family_is_made_once_with_its_colours_and_roles():
    with demo.package():
        import iosuite_demo
        people = iosuite_demo.ensure()
        assert [p["name"] for p in people.values()] == list(demo.FAMILY_KEYS)
        assert iosuite_demo.ensure()["ava"]["id"] == people["ava"]["id"] and len(users.list_users()) == 4  # again: nobody made twice
        iosuite_demo.give_roles("iocalendar", people)
    assert users.authenticate("riley", demo.DEMO_PASSWORD)
    assert users.get(people["morgan"]["id"])["suiteAdmin"] and not users.get(people["riley"]["id"])["suiteAdmin"]
    fam = {m["name"]: m for m in family.members()}
    assert fam["theo"]["color"] == "#e8710a" and fam["ava"]["displayName"] == "Ava Calloway"
    assert users.roles_of(people["riley"]["id"]) == {"iocalendar": "admin"} and users.roles_of(people["theo"]["id"]) == {"iocalendar": "member"}


def test_an_app_is_seeded_once_while_the_switch_is_on(tmp_path, monkeypatch):
    pkg = tmp_path / "pkg" / "iosuite_demo"  # a stand-in package: its iotask seed counts its calls, iocalendar's fails
    pkg.mkdir(parents=True)
    shutil.copy(Path(__file__).resolve().parents[2] / "demo" / "iosuite_demo" / "__init__.py", pkg)  # the real family and run()
    (pkg / "iotask.py").write_text("import os\ndef seed(people):\n    open(os.environ['DEMO_CALLS'], 'a').write(','.join(sorted(people)) + '\\n')\n")
    (pkg / "iocalendar.py").write_text("def seed(people):\n    1 / 0\n")
    calls = tmp_path / "calls"
    monkeypatch.setenv("DEMO_CALLS", str(calls))
    monkeypatch.setenv("DEMO_PACKAGE", str(pkg.parent))
    demo.at_start("iotask")
    assert not calls.exists() and not users.any_users()  # the switch is off: nothing at all
    demo.switch(True)
    demo.at_start("iotask")
    demo.at_start("iotask")
    assert calls.read_text() == "ava,morgan,riley,theo\n" and demo.seeded("iotask")
    demo.at_start("iocalendar")  # a seed that fails is logged, never stops the app, and is not tried again
    assert demo.seeded("iocalendar")
    monkeypatch.setenv("DEMO_PACKAGE", "http://127.0.0.1:9/iosuite-demo.zip")  # no package to fetch: tried again at the next start
    demo.at_start("iothings")
    assert not demo.seeded("iothings")


def test_the_stack_adds_the_demo_to_a_new_suite_only(monkeypatch):
    monkeypatch.setattr("iosuite_shared.config.ADMIN_USER", "admin")
    monkeypatch.setattr("iosuite_shared.config.ADMIN_PASSWORD", "long-enough-1")
    cli.main(["stack", "--demo"])
    assert demo.wanted() and [u["name"] for u in users.list_users()] == ["admin"]  # the family comes with the first app's seed
    cli.main(["stack", "--demo"])  # every later `up`: nothing new
    assert demo.wanted()
    # a suite that is used for real is left alone
    demo.switch(False)
    users.create("dana", "long-enough-2")
    db.settings_cache.clear()
    assert stack.demo_once(log=lambda *_: None) is False and not demo.wanted()


def test_the_command_turns_it_on_and_off(capsys):
    cli.main(["demo", "--no-restart"])
    assert demo.wanted() and "calloway" in capsys.readouterr().out
    cli.main(["demo", "--off"])
    assert not demo.wanted()


def test_a_picture_is_drawn():
    import io
    import pytest
    Image = pytest.importorskip("PIL.Image")  # the apps with pictures have Pillow; the library alone does not need it
    with demo.package():
        import iosuite_demo
        raw = iosuite_demo.picture("Pancakes", "#e8a100", (300, 200))
    im = Image.open(io.BytesIO(raw))
    assert im.size == (300, 200) and im.format == "JPEG"
