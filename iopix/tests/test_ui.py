"""Browser tests (Playwright, headless Chromium) for the behaviours a user
sees: the grid, the lightbox, face boxes following the Show-faces toggle,
the People rows and their menu, the person picker, read-only mode hiding
every editing control, and the Settings page.

A real uvicorn serves the scratch library on a free port, started once per
session from the same environment the API tests use.
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright  # noqa: E402

APP = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server(lib):
    """uvicorn on a free port, same env overrides as the API tests (set by conftest)."""
    port = _free_port()
    env = dict(os.environ, DATA_DIR=str(Path(os.environ["DATA_DIR"]).parent / "data-ui"))
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                            cwd=str(APP), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(300):
            try:
                with urllib.request.urlopen(url + "/api/status", timeout=1) as r:
                    import json
                    s = json.load(r)
                    if s.get("version"):
                        break
            except Exception:
                pass
            if proc.poll() is not None:
                raise RuntimeError("server died: " + proc.stderr.read().decode()[-800:])
            time.sleep(0.1)
        else:
            raise RuntimeError("server did not come up")
        yield url
    finally:
        proc.terminate()
        proc.wait(10)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture(autouse=True)
def _ui_no_users(server):
    """The browser tests' own server keeps its users in its own state.db: start each test in open mode."""
    import sqlite3
    db = Path(os.environ["DATA_DIR"]).parent / "data-ui" / "state.db"
    if db.exists():
        con = sqlite3.connect(db); con.execute("DELETE FROM users"); con.commit(); con.close()
    yield


@pytest.fixture
def page(browser, server):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.base = server
    pg.errors = errors
    yield pg
    ctx.close()
    assert not errors, "uncaught JS errors: " + "; ".join(errors)[:500]


def _open_photo(page, server, pid):
    page.goto(f"{server}/#/photos?p={pid}")
    page.wait_for_selector("#lightbox .lb-frame img, #lightbox .lb-frame video", timeout=15000)
    page.wait_for_timeout(300)


def _set_read_only(server, on: bool):
    req = urllib.request.Request(server + "/api/settings", data=b'{"read_only": %s}' % (b"true" if on else b"false"),
                                 headers={"content-type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=5).read()


def test_grid_renders_thumbnails(page, server, lib):
    page.goto(server + "/#/photos")
    page.wait_for_selector(".tile img", timeout=15000)
    assert page.locator(".tile").count() > 10


def test_face_boxes_follow_the_toggle(page, server, lib):
    pid = lib["with_faces"][0]
    _open_photo(page, server, pid)
    assert page.locator(".facebox:not(.objbox)").count() == 0, "boxes shown before the toggle"
    btn = page.locator('[title="Show faces (F)"]')
    btn.click()
    page.wait_for_timeout(200)
    assert page.locator(".facebox:not(.objbox)").count() > 0
    assert "on" in (btn.get_attribute("class") or "").split()
    page.keyboard.press("f")
    page.wait_for_timeout(200)
    assert page.locator(".facebox:not(.objbox)").count() == 0
    assert "on" not in (btn.get_attribute("class") or "").split()


def test_ignored_faces_are_not_drawn_or_listed(page, server, lib):
    import json
    for pid in lib["with_faces"]:
        with urllib.request.urlopen(f"{server}/api/photo/{pid}") as r:
            d = json.load(r)
        if any(f["kind"] == "ignored" for f in d.get("faces_other", [])):
            break
    else:
        pytest.skip("no ignored face in the scratch library")
    _open_photo(page, server, pid)
    page.keyboard.press("f")
    page.wait_for_timeout(200)
    assert page.locator(".facebox.face-ignored").count() == 0
    assert page.locator(".facerow:has-text('Ignored')").count() == 0


def test_people_rows_open_the_menu_and_picker(page, server, lib):
    pid = lib["with_faces"][0]
    _open_photo(page, server, pid)
    if page.locator(".lb-info").is_hidden():
        page.locator('[title^="Info"]').click()
    page.wait_for_selector(".facerow", timeout=10000)
    assert page.locator(".lb-info .ichips img").count() == 0, "the pill chips were removed; only rows remain"
    row = page.locator(".facerow").first
    row.click()
    page.wait_for_selector(".facemenu", timeout=5000)
    menu = page.locator(".facemenu")
    assert menu.is_visible()
    box = menu.bounding_box()
    assert box and box["x"] >= 0 and box["y"] >= 0, "menu must be positioned inside the viewport"
    # the menu paints on top: the element at its centre belongs to it
    on_top = page.evaluate("""() => { const m = document.querySelector('.facemenu'); const r = m.getBoundingClientRect();
        const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !!(e && e.closest('.facemenu')); }""")
    assert on_top
    item = menu.locator(".fmi", has_text="someone else").first if menu.locator(".fmi", has_text="someone else").count() else menu.locator(".fmi", has_text="Who is this").first
    item.click()
    page.wait_for_selector(".modal-back", timeout=5000)
    assert page.locator(".modal h3").inner_text().strip() == "Who is this?"
    assert page.locator(".modal .frow").count() > 0
    assert page.locator(".modal .frow .nm", has_text="People").count() == 0, "the People root must not be offered as a person"
    page.locator(".modal button", has_text="Cancel").click()
    assert page.locator(".modal-back").count() == 0


def test_face_menu_from_the_box_works_with_real_clicks(page, server, lib):
    pid = lib["with_faces"][0]
    _open_photo(page, server, pid)
    page.keyboard.press("f")
    page.wait_for_selector(".facebox:not(.objbox)", timeout=5000)
    page.locator(".facebox:not(.objbox)").first.click()
    page.wait_for_selector(".facemenu", timeout=5000)
    first = page.locator(".facemenu .fmi").first
    label = first.inner_text()
    first.click()  # a real pointer click: the stage must not capture it
    page.wait_for_timeout(400)
    assert page.locator(".facemenu").count() == 0, f"menu item {label!r} did not react to the click"


def test_read_only_hides_every_editing_control(page, server, lib):
    _set_read_only(server, True)
    try:
        pid = lib["with_faces"][0]
        _open_photo(page, server, pid)
        page.wait_for_timeout(1200)  # status poll picks up the flags
        page.reload()
        page.wait_for_selector("#lightbox .lb-frame img", timeout=15000)
        page.wait_for_timeout(500)
        assert page.locator(".lb-info input[placeholder='Title']").count() == 0
        page.wait_for_function("getComputedStyle(document.querySelector('[title^=\"Add a face\"]')).display === 'none'", timeout=5000)
        assert page.locator(".facerow .muted", has_text="options").count() == 0
        assert page.locator(".lb-info a", has_text="change").count() == 0
        page.goto(server + "/#/settings")
        page.wait_for_selector("h2", timeout=10000)
        heads = page.locator("h2").all_inner_texts()
        assert "Editing" not in heads and "Place tags" not in heads
        assert page.locator("b", has_text="Read-only mode").count() == 1
    finally:
        _set_read_only(server, False)


def test_settings_and_maintenance_pages(page, server):
    page.goto(server + "/#/settings")
    page.wait_for_selector("h1:has-text('Settings')", timeout=10000)
    heads = page.locator("h2").all_inner_texts()
    for h in ("Display", "Search and background work", "Editing", "Place tags", "Metadata templates"):
        assert h in heads, heads
    assert "Storage" not in heads and "Library" not in heads, "maintenance sections must not be on the Settings page"
    assert page.locator(".ajob select").count() >= 1, "the core budget selector lives in Settings"
    page.goto(server + "/#/maintenance")
    page.wait_for_selector("h1:has-text('Maintenance')", timeout=10000)  # a hash-only navigation re-renders in place
    heads = page.locator("h2").all_inner_texts()
    for h in ("Library", "AI analysis", "Models and data", "Metadata consistency", "Storage"):
        assert h in heads, heads
    assert "Display" not in heads and "Editing" not in heads
    assert page.locator("b", has_text="Background work").count() == 1
    assert page.locator("b", has_text="Restart the viewer").count() == 1
    assert page.locator("#nav a", has_text="Maintenance").count() == 0, "no longer in the main navigation"
    assert page.locator("#topbar a.tool[href='#/maintenance']").count() == 1 and page.locator("#topbar a.tool[href='#/settings']").count() == 1


def test_keyboard_navigation(page, server, lib):
    ids = [i for i in lib["ids"] if i not in lib["videos"]]
    _open_photo(page, server, ids[0])
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(300)
    assert page.url.endswith(f"p={ids[1]}") or f"p={ids[1]}" in page.url or page.url != f"{server}/#/photos?p={ids[0]}"
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert page.locator("#lightbox").is_hidden() or page.locator("#lightbox").count() == 0


def test_pasting_a_coordinate_pair_fills_both_fields(page, server, lib):
    pid = next(i for i in lib["ids"] if i not in lib["videos"])
    _open_photo(page, server, pid)
    if page.locator(".lb-info").is_hidden():
        page.locator('[title^="Info"]').click()
    page.wait_for_selector(".lb-info h4", timeout=10000)
    # open the location dialog from the info pane ("Set location" link or the Location heading's "change")
    link = page.locator(".lb-info a.lnk", has_text="Set location")
    if not link.count():
        link = page.locator(".lb-info a.lnk", has_text="change").last
    link.click()
    page.wait_for_selector(".modal input[placeholder='latitude']", timeout=5000)
    lat = page.locator(".modal input[placeholder='latitude']")
    lon = page.locator(".modal input[placeholder='longitude']")
    lat.focus()
    page.evaluate("""() => { const el = document.querySelector(".modal input[placeholder='latitude']");
        const dt = new DataTransfer(); dt.setData('text', '40.44414979347404, -79.96231586013303');
        el.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })); }""")
    assert lat.input_value().startswith("40.4441")
    assert lon.input_value().startswith("-79.9623")
    # a plain number pastes as usual
    page.evaluate("""() => { const el = document.querySelector(".modal input[placeholder='longitude']");
        const dt = new DataTransfer(); dt.setData('text', '12.5');
        el.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })); }""")
    assert lon.input_value().startswith("-79.9623"), "a single number is left to the browser's own paste"
    page.locator(".modal button", has_text="Cancel").click()


def test_pwa_service_worker_caches_the_shell(page, server):
    page.goto(server + "/#/photos")
    out = page.evaluate("""async () => { const r = await navigator.serviceWorker.ready; const c = await caches.open('dkv-shell-v1');
        return { state: r.active && r.active.state, cached: (await c.keys()).map((k) => new URL(k.url).pathname) }; }""")
    assert out["state"] in ("activating", "activated")  # ready resolves while the worker may still be activating for a tick
    assert {"/", "/app.js", "/app.css", "/manifest.webmanifest", "/icons/icon-192.png"} <= set(out["cached"])
    assert not any(p.startswith("/api") or p.startswith("/thumb") for p in out["cached"]), "photos and the API are never cached"


def test_users_flow_in_the_browser(page, server, browser):
    import json, urllib.request
    # open mode: the person icon offers to create the admin
    page.goto(server + "/#/settings")
    page.wait_for_selector("h1:has-text('Settings')", timeout=10000)
    assert page.locator("b", has_text="No users yet").count() == 1
    page.locator("#usermenu button").click()
    page.wait_for_selector(".modal h3", timeout=5000)
    assert page.locator(".modal h3").inner_text().startswith("Create the admin")
    page.locator(".modal input[placeholder^='Admin user name']").fill("alex")
    page.locator(".modal input[type=password]").fill("correct horse")
    page.locator(".modal button", has_text="Create").click()
    page.wait_for_selector("#usermenu .avatar", timeout=5000)
    page.goto(server + "/#/settings"); page.wait_for_selector("h2:has-text('Users')", timeout=10000)
    assert page.locator("#topbar a.tool[href='#/maintenance']").is_visible()
    # a visitor in a fresh context: read-only, no maintenance icon, sign-in dialog
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}); visitor = ctx.new_page()
    visitor.goto(server + "/#/photos?p=" + str(json.load(urllib.request.urlopen(server + "/api/photos"))["id"][0]))
    visitor.wait_for_selector("#lightbox .lb-frame img, #lightbox .lb-frame video", timeout=15000); visitor.wait_for_timeout(600)
    if visitor.locator(".lb-info").is_hidden():
        visitor.locator('[title^="Info"]').click(); visitor.wait_for_timeout(400)
    assert visitor.locator(".lb-info h4", has_text="People").count() == 1, "the panel is open"
    assert visitor.locator(".lb-info input[placeholder='Title']").count() == 0
    assert not visitor.locator("#topbar a.tool[href='#/maintenance']").is_visible()
    visitor.keyboard.press("Escape"); visitor.wait_for_timeout(400)  # the lightbox covers the top bar
    visitor.locator("#usermenu button").click()
    visitor.wait_for_selector(".modal .account", timeout=5000)
    visitor.locator(".modal .account", has_text="alex").click()  # a protected account: the tile reveals the password field
    visitor.locator(".modal input[type=password]").fill("wrong")
    visitor.locator(".modal button", has_text="Sign in").click(); visitor.wait_for_timeout(500)
    assert visitor.locator(".modal").count() == 1, "a wrong password keeps the dialog open"
    visitor.locator(".modal input[type=password]").fill("correct horse"); visitor.locator(".modal button", has_text="Sign in").click()
    visitor.wait_for_selector("#usermenu .avatar", timeout=5000); visitor.wait_for_timeout(800)
    visitor.goto(server + "/#/photos?p=" + str(json.load(urllib.request.urlopen(server + "/api/photos"))["id"][0]))
    visitor.wait_for_selector("#lightbox .lb-frame img, #lightbox .lb-frame video", timeout=15000); visitor.wait_for_timeout(600)
    if visitor.locator(".lb-info").is_hidden():
        visitor.locator('[title^="Info"]').click(); visitor.wait_for_timeout(400)
    assert visitor.locator(".lb-info input[placeholder='Title']").count() == 1, "the admin can edit"
    visitor.keyboard.press("Escape"); visitor.wait_for_timeout(300)
    # a display setting now lives on the server
    visitor.goto(server + "/#/settings"); visitor.wait_for_selector("h1:has-text('Settings')", timeout=10000)
    visitor.locator("input[type=checkbox]").first.uncheck(); visitor.wait_for_timeout(900)
    me = visitor.evaluate("async () => (await (await fetch('/api/auth/settings', {method:'POST', headers:{'content-type':'application/json'}, body:'{}'})).json())")
    assert me.get("badges") == "0"
    ctx.close()
    # leave the scratch server open again for the other tests
    urllib.request.urlopen(server + "/api/status").read()


def test_account_picker_one_click_sign_in(page, server, browser):
    import json, urllib.request
    # an admin and a passwordless viewer, made through the API in open mode
    req = lambda path, body: urllib.request.urlopen(urllib.request.Request(server + path, data=json.dumps(body).encode(), headers={"content-type": "application/json"}, method="POST")).read()
    req("/api/auth/setup", {"name": "alex", "password": "correct horse"})
    # the admin creates the passwordless viewer from the Users section
    page.goto(server + "/#/settings"); page.wait_for_selector("h1:has-text('Settings')", timeout=10000)
    page.locator("#usermenu button").click(); page.wait_for_selector(".modal h3:has-text('Sign in')", timeout=5000)
    page.locator(".modal .account", has_text="alex").click(); page.locator(".modal input[type=password]").fill("correct horse"); page.locator(".modal button", has_text="Sign in").click()
    page.wait_for_selector("#usermenu .avatar", timeout=5000)
    page.goto(server + "/#/settings"); page.wait_for_selector("h2:has-text('Users')", timeout=10000)
    page.locator("input[placeholder='User name']").last.fill("kid")
    page.locator("label:has-text('no password') input").check()
    page.locator("button", has_text="Add user").click(); page.wait_for_timeout(600)
    assert page.locator(".utable tr[data-user='kid']", has_text="none (one-click)").count() == 1
    # a visitor: two tiles, one click as kid
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}); v = ctx.new_page()
    v.goto(server + "/#/photos"); v.wait_for_selector(".tile img", timeout=15000)
    v.locator("#usermenu button").click(); v.wait_for_selector(".modal .account", timeout=5000)
    names = v.locator(".modal .account .nm").all_inner_texts()
    assert names == ["alex", "kid", "Other"]
    assert v.locator(".modal input[type=password]").is_hidden(), "no password field until a protected tile is picked"
    v.locator(".modal .account", has_text="kid").click()
    v.wait_for_selector("#usermenu .avatar", timeout=5000)
    assert v.evaluate("async () => (await (await fetch('/api/auth/me')).json()).user.name") == "kid"
    ctx.close()


def test_database_row_tests_a_connection(page, server, lib):
    page.goto(server + "/#/settings"); page.wait_for_selector("h1:has-text('Settings')", timeout=10000)
    row = page.locator(".srow", has=page.locator("b", has_text="digiKam database"))
    assert row.count() == 1
    assert row.locator("select").first.input_value() == "sqlite"
    from pathlib import Path
    assert Path(row.locator("input[placeholder='folder with digikam4.db']").input_value()).resolve() == lib["db"].parent.resolve()
    row.locator("button", has_text="Test connection").click()
    page.wait_for_selector(".srow .muted:has-text('OK:')", timeout=10000)
    assert f"{len(lib['ids'])} photos" in row.locator(".muted", has_text="OK:").inner_text()
    row.locator("select").first.select_option("mysql")
    assert row.locator("input[placeholder='host']").is_visible() and row.locator("input[placeholder='folder with digikam4.db']").is_hidden()


def test_container_mode_asks_before_a_database_write(page, server):
    """DIGIKAM_CHECK=ask (the browser tests' server runs that way): a write that needs digiKam closed
    shows one confirmation; accepting it vouches and the action goes through."""
    import json, sqlite3, urllib.request
    db = Path(os.environ["DATA_DIR"]).parent / "data-ui" / "state.db"
    con = sqlite3.connect(db); con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('digikam_closed_until', '0')"); con.commit(); con.close()
    assert json.load(urllib.request.urlopen(server + "/api/status"))["digikamCheck"] == "ask"
    dialogs = []
    def on_dialog(d):
        dialogs.append(d.type + ":" + d.message[:40])
        d.accept("zz-ui-vouch") if d.type == "prompt" else d.accept()
    page.on("dialog", on_dialog)
    page.goto(server + "/#/tags"); page.wait_for_selector("h1", timeout=10000)
    page.locator("button", has_text="Manage tags").first.click(); page.wait_for_timeout(300)
    page.locator("button", has_text="New top-level tag").first.click()
    page.wait_for_timeout(2500)
    assert any(t.startswith("prompt:") for t in dialogs), dialogs
    assert any(t.startswith("confirm:The viewer cannot see") for t in dialogs), "the container-mode confirmation must appear: " + str(dialogs)
    tags = json.load(urllib.request.urlopen(server + "/api/meta"))["tags"]
    assert any(t["name"] == "zz-ui-vouch" for t in tags), "after accepting, the tag is created"


def test_appearance_setting_switches_the_theme(page, server):
    """Settings > Display > Appearance: Light and Dark fix the palette (data-theme on <html>, the
    page background follows, the choice is remembered), System follows the device again."""
    page.goto(server + "/#/settings")
    page.wait_for_selector("#themeseg", timeout=10000)
    page.click("#themeseg [data-theme=dark]")
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(23, 24, 27)"
    page.reload()
    page.wait_for_selector("#themeseg", timeout=10000)
    assert page.evaluate("document.documentElement.dataset.theme") == "dark", "remembered across loads, applied before the first paint"
    page.click("#themeseg [data-theme=light]")
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(255, 255, 255)"
    page.click("#themeseg [data-theme=system]")
    assert page.evaluate("document.documentElement.dataset.theme") is None
    assert page.evaluate("localStorage.getItem('theme')") == "system"


def test_explore_summary_cards_link_to_their_views(page, server, lib):
    page.goto(server + "/#/explore")
    page.wait_for_selector(".stats .stat", timeout=10000)
    cards = page.locator(".stats .stat")
    assert cards.count() == 6
    labels = page.locator(".stats .stat div > span").all_inner_texts()
    assert labels == ["photos", "videos", "people", "folders", "with location", "on disk"], labels
    assert page.locator(".stats a.stat").count() == 5, "all but 'on disk' open a view"
    assert page.locator(".stats .stat .sic .ic svg").count() == 6, "each card has an icon"
    page.click(".stats a.stat:has-text('people')")
    page.wait_for_selector("#nav a[data-v=people].on", timeout=5000)


def test_lightbox_film_strip_and_remembered_info_panel(page, server, lib):
    """The film strip along the bottom of the lightbox shows the neighbours, marks the current
    photo, jumps on click, and slides up when the mouse reaches the bottom edge. The info panel
    reopens the way it was last left."""
    page.goto(server + "/#/photos")
    page.wait_for_selector(".tile img", timeout=15000)
    page.locator(".tile").first.click()
    page.wait_for_selector("#lightbox .lb-frame img, #lightbox .lb-frame video", timeout=15000)
    page.wait_for_selector("#lightbox .lb-strip .reel img.cur", timeout=5000)
    reel = page.locator("#lightbox .lb-strip .reel img")
    assert reel.count() >= 2 and page.locator("#lightbox .lb-strip .reel img.cur").get_attribute("data-i") == "0"
    strip = page.locator("#lightbox .lb-strip")
    assert "show" not in (strip.get_attribute("class") or ""), "parked until the pointer comes near the bottom edge"
    box = page.locator("#lightbox .lb-stage").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] - 20)
    page.wait_for_selector("#lightbox .lb-strip.show", timeout=3000)
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 200)
    page.wait_for_selector("#lightbox .lb-strip:not(.show)", timeout=3000)
    # hovering another thumbnail previews it over the stage; leaving the strip restores the view
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] - 20)
    page.wait_for_selector("#lightbox .lb-strip.show", timeout=3000)
    reel.nth(1).hover(force=True)
    page.wait_for_selector("#lightbox .lb-peek", timeout=3000)
    assert page.locator("#lightbox .lb-peek").get_attribute("data-id") == reel.nth(1).get_attribute("src").split("/")[-1]
    assert page.locator("#lightbox .lb-strip .reel img.cur").get_attribute("data-i") == "0", "peeking does not move"
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 200)
    page.wait_for_selector("#lightbox .lb-peek", state="detached", timeout=3000)
    reel.nth(1).click(force=True)
    page.wait_for_function("document.querySelector('#lightbox .lb-strip .reel img.cur')?.dataset.i === '1'", timeout=5000)
    assert page.locator("#lightbox .lb-peek").count() == 0
    assert "p=" in page.url
    # the info panel: open it, leave, come back
    page.keyboard.press("i")
    page.wait_for_selector("#lightbox .lb-info:not([hidden])", timeout=3000)
    page.keyboard.press("Escape")
    page.wait_for_selector("#lightbox", state="hidden", timeout=5000)
    page.locator(".tile").first.click()
    page.wait_for_selector("#lightbox .lb-frame img, #lightbox .lb-frame video", timeout=15000)
    assert page.locator("#lightbox .lb-info").is_visible(), "reopens with the info panel as it was left"
    page.keyboard.press("i")
    page.keyboard.press("Escape")
    page.wait_for_selector("#lightbox", state="hidden", timeout=5000)
    page.locator(".tile").first.click()
    page.wait_for_selector("#lightbox .lb-frame img, #lightbox .lb-frame video", timeout=15000)
    assert page.locator("#lightbox .lb-info").is_hidden()
    page.keyboard.press("Escape")


def test_grid_select_all_toggles_and_groups_by_month(page, server, lib):
    page.goto(server + "/#/photos")
    page.wait_for_selector(".tile img", timeout=15000)
    page.wait_for_selector(".gbar .selall", timeout=5000)
    assert page.locator(".gbar .selall").is_visible() and page.locator(".gbar .selnone").is_hidden()
    page.click(".gbar .selall")
    page.wait_for_selector("#selbar", timeout=5000)
    assert page.locator(".gbar .selall").is_hidden() and page.locator(".gbar .selnone").is_visible(), "everything selected: only Deselect all"
    page.click(".gbar .selnone")
    page.wait_for_selector("#selbar", state="detached", timeout=5000)
    assert page.locator(".gbar .selall").is_visible() and page.locator(".gbar .selnone").is_hidden()
    # grouping: the scratch library spans several days in a month, so months make fewer sections
    page.locator("#main").evaluate("m => m.scrollTop = 0")
    page.wait_for_timeout(300)
    grid_h = page.evaluate("document.getElementById('grid').style.height")
    days = page.locator(".ghead").count()
    page.select_option(".gbar .groupsel", "month")
    page.wait_for_function(f"document.getElementById('grid').style.height !== '{grid_h}'", timeout=5000)
    page.wait_for_timeout(300)
    months = page.locator(".ghead").count()
    assert 0 < months < days, (days, months)
    head = page.locator(".ghead").first.inner_text()
    assert any(m in head for m in ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")) and "," not in head, head
    assert page.evaluate("localStorage.getItem('group')") == "month"
    page.select_option(".gbar .groupsel", "day")


def test_lightbox_bar_has_close_and_share_menu(page, server, lib):
    page.goto(server + "/#/photos")
    page.wait_for_selector(".tile img", timeout=15000)
    page.locator(".tile").first.click()
    page.wait_for_selector("#lightbox .lb-frame img, #lightbox .lb-frame video", timeout=15000)
    assert page.locator("#lightbox .lb-top button[title^='Close']").count() == 1
    page.click("#lightbox .lb-top button[title='Share']")
    page.wait_for_selector("#lightbox .sharemenu", timeout=3000)
    labels = page.locator("#lightbox .sharemenu .fmi").all_inner_texts()
    assert any(l.startswith("Copy link") for l in labels) and any(l.startswith("Download original") for l in labels) and any(l.startswith("Email") for l in labels), labels
    assert page.locator("#lightbox .sharemenu a[href$='?dl=1']").count() >= 1
    page.locator("#lightbox .lb-stage").click(position={"x": 60, "y": 400})
    page.wait_for_selector("#lightbox .sharemenu", state="detached", timeout=3000)
    page.click("#lightbox .lb-top button[title^='Close']")
    page.wait_for_selector("#lightbox", state="hidden", timeout=5000)
    assert page.locator(".tile img").count() > 0, "back to the grid it came from"


def test_share_button_opens_the_device_share_sheet_with_the_picture(page, server, lib):
    """Where the browser has a share sheet, the share button hands it the photo as a JPEG named
    after the file (the fallback menu is for browsers without one, tested above)."""
    page.add_init_script("""
      window.__shared = [];
      navigator.share = async (d) => { window.__shared.push({ title: d.title, url: d.url, files: (d.files || []).map((f) => [f.name, f.type, f.size]) }); };
      navigator.canShare = () => true;
    """)
    page.goto(server + "/#/photos")
    page.wait_for_selector(".tile img", timeout=15000)
    page.locator(".tile").first.click()
    page.wait_for_selector("#lightbox .lb-frame img, #lightbox .lb-frame video", timeout=15000)
    page.wait_for_timeout(1500)  # the picture for sharing is fetched once the photo is shown
    page.click("#lightbox .lb-top button[title='Share']")
    page.wait_for_function("window.__shared.length === 1", timeout=5000)
    shared = page.evaluate("window.__shared[0]")
    assert page.locator("#lightbox .sharemenu").count() == 0, "the sheet, not the menu"
    if page.locator("#lightbox .lb-frame video").count():
        assert shared["url"]
    else:
        assert shared["files"] and shared["files"][0][0].endswith(".jpg") and shared["files"][0][1] == "image/jpeg" and shared["files"][0][2] > 1000, shared
    page.keyboard.press("Escape")


def test_on_this_day_is_a_justified_gallery_without_scrollbars(page, server, lib):
    page.goto(server + "/#/explore")
    page.wait_for_selector(".stats .stat", timeout=10000)
    page.wait_for_timeout(1500)
    if page.locator(".jrows .tile").count() == 0:
        pytest.skip("no photo in the scratch library was taken on today's date")
    g = page.locator(".jrows")
    assert page.evaluate("(e) => e.scrollWidth <= e.clientWidth", g.element_handle()), "nothing to scroll sideways"
    box = g.bounding_box()
    tiles = page.locator(".jrows .tile")
    for i in range(tiles.count()):
        b = tiles.nth(i).bounding_box()
        assert b["x"] >= box["x"] - 1 and b["x"] + b["width"] <= box["x"] + box["width"] + 1, "tiles wrap within the page width"


def test_require_sign_in_shows_only_the_login_dialog(page, server, browser):
    """With Require sign-in on, a visitor loading the app sees the sign-in dialog and nothing of
    the library; signing in from it loads the library in place."""
    accounts = page.request.get(server + "/api/auth/accounts").json()["accounts"]
    if any(a["name"] == "alex" for a in accounts):
        assert page.request.post(server + "/api/auth/login", data={"name": "alex", "password": "correct horse"}).ok
    else:
        assert page.request.post(server + "/api/auth/setup", data={"name": "alex", "password": "correct horse"}).ok
    assert page.request.post(server + "/api/settings", data={"require_login": True}).ok
    try:
        ctx = browser.new_context(viewport={"width": 1280, "height": 900}); visitor = ctx.new_page()
        visitor.goto(server + "/#/photos")
        visitor.wait_for_selector(".modal-back.required .modal h3:has-text('Sign in')", timeout=10000)
        visitor.wait_for_timeout(800)
        assert visitor.locator(".tile").count() == 0 and visitor.locator("#main").is_hidden(), "nothing of the library before sign-in"
        assert visitor.locator(".modal button", has_text="Cancel").count() == 0
        visitor.mouse.click(5, 5)  # the backdrop does not dismiss it
        assert visitor.locator(".modal-back.required").count() == 1
        visitor.locator(".modal .account", has_text="alex").click()
        visitor.locator(".modal input[type=password]").fill("correct horse")
        visitor.locator(".modal button", has_text="Sign in").click()
        visitor.wait_for_selector(".tile img", timeout=15000)
        assert visitor.locator(".modal-back").count() == 0 and visitor.locator("#main").is_visible()
        # the setting is on the Settings page and sign-out goes back to the dialog
        visitor.goto(server + "/#/settings"); visitor.wait_for_selector("#reqlogin", timeout=10000)
        assert visitor.locator("#reqlogin").is_checked()
        ctx.close()
    finally:
        assert page.request.post(server + "/api/settings", data={"require_login": False}).ok


def test_set_location_for_a_selection(page, server, lib):
    """Select several photos: the selection bar offers Set location, and the dialog addresses them all."""
    page.goto(server + "/#/photos")
    page.wait_for_selector(".tile img", timeout=15000)
    page.wait_for_timeout(1200)  # editing flags arrive with the status poll
    page.locator(".tile .tcheck").nth(0).click(force=True)
    page.locator(".tile .tcheck").nth(1).click(force=True)
    page.wait_for_selector("#selbar", timeout=5000)
    assert "2 selected" in page.locator("#selbar .n").inner_text()
    page.locator("#selbar button[title='Set location']").click()
    page.wait_for_selector(".modal h3:has-text('Set location for 2 photos')", timeout=5000)
    assert "all 2 selected photos" in page.locator(".modal p").first.inner_text()
    page.locator(".modal button", has_text="Cancel").click()
    page.keyboard.press("Escape")


def test_folders_and_albums_are_separate_pages(page, server, lib):
    """Folders are digiKam's folders on disk (with New folder and Upload for editors); Albums are
    the viewer's own groupings. An upload through the page lands in the folder."""
    page.goto(server + "/#/folders")
    page.wait_for_selector("h1:has-text('Folders')", timeout=10000)
    page.wait_for_timeout(1200)
    assert page.locator("#nav a[data-v=folders]").count() == 1 and page.locator("#nav a[data-v=albums]").count() == 1
    assert page.locator(".card").count() >= 1
    assert page.locator("h2.sub .more", has_text="Upload photos").count() >= 1, "editors can upload"
    assert page.locator("h2.sub .more", has_text="New folder").count() >= 1
    # upload one JPEG from the library into the first top-level folder
    src = next(p for p in lib["root"].rglob("*") if p.suffix.lower() in (".jpg", ".jpeg") and "zz-" not in str(p))
    page.on("dialog", lambda d: d.accept())  # "is digiKam closed?" (the UI server runs with DIGIKAM_CHECK=ask)
    with page.expect_file_chooser() as fc:
        page.locator("h2.sub .more", has_text="Upload photos").first.click()
    fc.value.set_files(str(src))
    page.wait_for_function("document.querySelector('#toast') && !document.querySelector('#toast').hidden && /added to|error|not|failed|running/i.test(document.querySelector('#toast').textContent)", timeout=20000)
    text = page.locator("#toast").inner_text()
    assert "added to" in text, text
    # Albums: only the viewer's own
    page.goto(server + "/#/albums")
    page.wait_for_selector("h1:has-text('Albums')", timeout=10000)
    assert page.locator(".card .nm", has_text="New album").count() == 1
    assert page.locator("h2.sub").count() == 0, "no digiKam folders on the Albums page"
    assert page.locator("a.lnk", has_text="Folders").count() == 1


def test_multi_edit_offers_title_caption_and_deselect_all(page, server, lib):
    page.goto(server + "/#/photos")
    page.wait_for_selector(".tile img", timeout=15000)
    page.wait_for_timeout(1200)
    page.locator(".tile .tcheck").nth(0).click(force=True)
    page.locator(".tile .tcheck").nth(1).click(force=True)
    page.wait_for_selector("#selbar", timeout=5000)
    assert page.locator(".gbar .selnone").is_visible() and page.locator(".gbar .selall").is_visible(), "partly selected: both links"
    page.locator("#selbar button[title='Edit']").click()
    page.wait_for_selector(".modal h3:has-text('Edit 2 items')", timeout=5000)
    for ph in ("Title for all", "Caption for all"):
        assert page.locator(f".modal [placeholder='{ph}']").count() == 1
    assert page.locator(".modal .stars button").count() >= 5 and page.locator(".modal .erow .el", has_text="Add tag").count() == 1
    page.locator(".modal button", has_text="Done").click()
    page.click(".gbar .selnone")
    page.wait_for_selector("#selbar", state="detached", timeout=5000)
    assert page.locator(".gbar .selnone").is_hidden()
