"""The page every app serves at its root, its manifest and its static folder (iOStart and ioPix add their own)."""
from pathlib import Path

from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

STAMPED = ("static/app.js", "static/app.css", "static/js/theme.js", "api/auth/base.css")


class Static(StaticFiles):
    """/static, with the page's modules (static/js/*.js, imported by app.js without a version) marked no-cache: the
    browser and Cloudflare ask again each time (a 304 when unchanged), so an update never pairs a new app.js with
    modules kept from the version before."""

    async def get_response(self, path, scope):
        r = await super().get_response(path, scope)
        if path.replace("\\", "/").startswith("js/") and path.endswith(".js"):
            r.headers["Cache-Control"] = "no-cache"
        return r


def mount(app, static_dir: Path, version: str, service_worker: bool = False) -> None:
    """GET / (index.html with the version stamped on the script and stylesheets: after an update the browser, and
    Cloudflare, which caches .js and .css at the edge, fetch the new ones instead of what they kept), the manifest,
    /sw.js at the root when the app has one (its scope is then the whole app), and /static."""
    static_dir = Path(static_dir)

    @app.get("/", include_in_schema=False)
    def index():
        html = (static_dir / "index.html").read_text(encoding="utf-8")
        for f in STAMPED:
            html = html.replace(f'"{f}"', f'"{f}?v={version}"')
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest():
        return FileResponse(static_dir / "manifest.webmanifest", media_type="application/manifest+json")

    if service_worker:
        @app.get("/sw.js", include_in_schema=False)
        def sw():
            return FileResponse(static_dir / "sw.js", media_type="text/javascript")

    app.mount("/static", Static(directory=static_dir), name="static")
