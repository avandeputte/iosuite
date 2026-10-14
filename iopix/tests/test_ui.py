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
        assert page.locator(".lb-info h4", has_text="Edit").count() == 0
        assert page.locator('[title^="Add a face"]').is_hidden()
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
    assert out["state"] == "activated"
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
    assert visitor.locator(".lb-info h4", has_text="Edit").count() == 0
    assert not visitor.locator("#topbar a.tool[href='#/maintenance']").is_visible()
    visitor.keyboard.press("Escape"); visitor.wait_for_timeout(400)  # the lightbox covers the top bar
    visitor.locator("#usermenu button").click()
    visitor.wait_for_selector(".modal h3:has-text('Sign in')", timeout=5000)
    visitor.locator(".modal input[placeholder='User name']").fill("alex"); visitor.locator(".modal input[type=password]").fill("wrong")
    visitor.locator(".modal button", has_text="Sign in").click(); visitor.wait_for_timeout(500)
    assert visitor.locator(".modal").count() == 1, "a wrong password keeps the dialog open"
    visitor.locator(".modal input[type=password]").fill("correct horse"); visitor.locator(".modal button", has_text="Sign in").click()
    visitor.wait_for_selector("#usermenu .avatar", timeout=5000); visitor.wait_for_timeout(800)
    visitor.goto(server + "/#/photos?p=" + str(json.load(urllib.request.urlopen(server + "/api/photos"))["id"][0]))
    visitor.wait_for_selector("#lightbox .lb-frame img, #lightbox .lb-frame video", timeout=15000); visitor.wait_for_timeout(600)
    assert visitor.locator(".lb-info h4", has_text="Edit").count() == 1, "the admin can edit"
    visitor.keyboard.press("Escape"); visitor.wait_for_timeout(300)
    # a display setting now lives on the server
    visitor.goto(server + "/#/settings"); visitor.wait_for_selector("h1:has-text('Settings')", timeout=10000)
    visitor.locator("input[type=checkbox]").first.uncheck(); visitor.wait_for_timeout(900)
    me = visitor.evaluate("async () => (await (await fetch('/api/auth/settings', {method:'POST', headers:{'content-type':'application/json'}, body:'{}'})).json())")
    assert me.get("badges") == "0"
    ctx.close()
    # leave the scratch server open again for the other tests
    urllib.request.urlopen(server + "/api/status").read()
