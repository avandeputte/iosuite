"""The FastAPI glue: one Auth object per app gives the middleware that works out who is asking, the route
dependencies that say who may call a route, and the routers with the sign-in and user-management API.

    auth = Auth("iopix")
    app.middleware("http")(auth.middleware(open_paths=..., open_prefixes=..., before=..., after=...))
    @router.get("/api/x", dependencies=[auth.access.admin])
    app.include_router(auth.router())        # /api/auth/* : login, accounts, logout, me, settings, password, setup
    app.include_router(auth.users_router())  # /api/users  : list, create, role here (admins of this app); the rest (suite admins)
    app.include_router(auth.admin_router())  # /api/suite-admin: every account, role, app password, session and app (suite admins)
    app.include_router(auth.status_router(updater, extra=...))   # GET /api/status, public, the same shape in every app
    app.include_router(auth.server_router(updater, log_file=...)) # GET/POST /api/server, GET /api/log (admins)
    auth.install(app, limit_for=...)         # 400 for bad input, the security headers, no-store on the API, the body cap

The API shapes are those of iopix (ionote copied them), so the apps' pages keep working.
"""
import base64
import json
import logging
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from iosuite_shared import apppasswords, db, routers, sessions, suite, users
from iosuite_shared.access import ACCESS_ROLES, UNCLAIMED, Access, BodyCap, TooLarge, content_type, json_body, public_user
from iosuite_shared.proxyauth import Forwarded, Proxy, authlog, peer_of, seen
from iosuite_shared.errors import Invalid

STATUS_PATH = routers.STATUS_PATH
MCP_PATH = "/mcp"  # where every app serves its MCP server (iosuite_shared.mcp.PATH)
__all__ = ["Auth", "Access", "ACCESS_ROLES", "BodyCap", "TooLarge", "content_type", "json_body", "public_user", "peer_of", "STATUS_PATH"]


class Auth:
    def __init__(self, app: str, read_only=None, read_only_message: str = None, app_label: str = None, basic_realm: str = None,
                 version: str = None, public_url: str = None, description: str = None, color: str = None,
                 register: bool = True, internal_url: str = None, admin_tool: bool = False):
        """version, public_url (the app's PUBLIC_URL; empty: the address it is reached at), description and color (the
        icon is suite.ICON, the same path in every app) and internal_url (where it is inside the network; None:
        suite.local_url(), from INTERNAL_URL or the LAN address and PORT) go into the suite's list of apps (iosuite_shared.suite) when the app first reaches the Shared ioSuite database; register=False
        keeps the app out of it. admin_tool=True: an app behind the scenes (ioDNS, ioBackup), for suite admins only:
        everybody else is none there, so it is on no one else's start page or app switcher."""
        self.app = app
        if admin_tool:
            suite.declare_admin_tool(app)
        self.suite_entry = dict(name=app_label or app, url=public_url or None, version=version, description=description,
                                color=color, internal_url=internal_url or suite.local_url(app), admin_tool=admin_tool) if register else None
        self._registered, self._retry_at = False, 0.0
        self.label = app_label or app
        self.proxy = Proxy(app)
        self.access = Access(read_only, read_only_message or f"{self.label} is in read-only mode; nothing can be changed.",
                             outside=self.outside)
        self.realm = basic_realm or self.label
        self.log = logging.getLogger(f"iosuite_shared.{app}")
        self.decorate = lambda user: user  # the app may add fields to the user dict it serves (iopix: the person tag)
        self.on_update = None  # on_update(user_id, body) after an admin changed an account: the app's own fields (iopix: the person tag)
        # the role `canWrite` in /api/auth/me stands for: "editor" where the app has things shared with everyone; an app
        # where everything is one's own (ioNote, ioHealth) sets "member", so its pages and native apps offer changes to members
        self.write_role = "editor"
        self.deny_exempt = ()  # path prefixes a denied proxy identity may still reach (iopix: /mcp, which signs in with its own token)
        # what a scoped app password may reach, by path prefix (apppasswords: 'dav', the app's sync protocols); anywhere
        # else it gets 403. An app without DAV sets it to {} so it offers no such passwords.
        self.scope_paths = {apppasswords.DAV: ("/dav", "/.well-known/caldav", "/.well-known/carddav")}
        # 'read' (apppasswords.READ, the apps' own service accounts) is the same everywhere: GET and HEAD, not MCP or DAV

    # ---- the suite's list of apps
    def register(self) -> None:
        """Write this app's row in the suite's list (once per start; the middleware calls it). Never fails a request."""
        if self._registered or self.suite_entry is None or time.time() < self._retry_at:
            return
        try:
            suite.register(self.app, **self.suite_entry)
            self._registered = True
        except ValueError as e:  # a PUBLIC_URL or INTERNAL_URL that is not an address: registered without it
            self.log.warning("suite registration: %s; registering without the address", e)
            entry = dict(self.suite_entry)
            for k in ("url", "internal_url"):
                try:
                    suite.clean_url(entry[k])
                except ValueError:
                    entry[k] = None
            suite.register(self.app, **entry)
            self._registered = True
        except Exception as e:  # noqa: BLE001 - the table is the suite's convenience, never a reason to fail
            self.log.warning("could not register %s in the suite's list of apps (tried again in a minute): %s", self.app, e)
            self._retry_at = time.time() + 60

    def note(self, request: Request, user=None) -> None:
        """Register (once), note that the app is up, and take the address the request reached it at when an admin
        asks (or, before the first account, someone inside the network): the Host header is whatever the client
        sends, so a visitor's is never recorded. resolve() calls it, so an app with its own middleware gets it too."""
        try:
            self.register()
            if self._registered:
                admin = bool(user and user.get("role") == "admin") if users.any_users() else not self.outside(request)
                suite.note_seen(self.app, request, take_address=admin)
        except Exception as e:  # noqa: BLE001
            self.log.debug("suite: %s", e)

    # ---- who is asking
    def current_user(self, request: Request):
        return getattr(request.state, "user", None)

    def outside(self, request: Request) -> bool:
        """Whether the request comes from outside the network (Proxy.external)."""
        return self.proxy.external(request.headers, peer_of(request))

    def unclaimed(self, request: Request) -> bool:
        """No account exists yet and the request comes from outside: nothing but the sign-in screen is served."""
        return not users.any_users() and self.outside(request)

    async def resolve(self, request: Request):
        """Who is asking: the session cookie, the proxy's identity, HTTP Basic or a bearer app password.
        Sets request.state.user, .via_proxy, .cookie_uid, .proxy_ident; returns a response to send instead when the
        proxy let in someone who has no account and that is denied."""
        session = request.cookies.get(sessions.COOKIE)
        request.state.origin = sessions.describe(request, self.proxy)
        user, renewed = (await run_in_threadpool(sessions.lookup, session, self.app, request.state.origin)) if session else (None, False)
        request.state.cookie_uid = user["id"] if user else None
        request.state.renew_cookie = renewed
        request.state.via_proxy = False
        request.state.proxy_ident = None
        request.state.app_password_scope = ""
        peer = peer_of(request)
        if "cf-access-jwt-assertion" in request.headers and time.time() - seen.get("at", 0) > 60:
            self.proxy.note(request.headers, peer)
        if self.proxy.mode() != "off":
            pu = await run_in_threadpool(self.proxy.user, request)
            if pu:
                user, request.state.via_proxy = pu, True
            elif request.state.proxy_ident and self.proxy.deny_unknown() and not request.url.path.startswith(tuple(self.deny_exempt) or ("\0",)):
                request.state.user = None
                return self.no_access(request, request.state.proxy_ident)
        if not user and "authorization" in request.headers:
            user = await run_in_threadpool(self._authorization, request)
            if isinstance(user, JSONResponse):  # throttled: too many wrong passwords
                request.state.user = None
                return user
        if user and not request.state.via_proxy and user.get("passwordless") and self.proxy.external(request.headers, peer):
            user = None  # a passwordless account's session (begun on the LAN) does not work from outside
        if self.suite_entry is not None:
            await run_in_threadpool(self.note, request, user)
        if user and user.get("role") == "none":
            request.state.user = None
            request.state.no_role_user = user
            return None
        request.state.user = self.decorate(user) if user else None
        return None

    def _authorization(self, request: Request):
        """HTTP Basic (name and an app password, or the account password) or a bearer app password. Wrong passwords are
        counted like sign-in attempts (users.attempt_*: by visitor and name) so neither an account nor the CPU can be
        hammered through this path; past the limit the answer is a 429 with Retry-After, before any hash is computed."""
        h = request.headers.get("authorization", "")
        if h.lower().startswith("basic "):
            try:
                name, _, pw = base64.b64decode(h[6:].strip()).decode("utf-8").partition(":")
            except (ValueError, UnicodeDecodeError):
                return None
        elif h.lower().startswith("bearer "):
            name, pw = "", h[7:].strip()
        else:
            return None
        visitor = self.proxy.visitor_of(request)
        wait = users.attempt_wait(visitor, name)
        if wait:
            authlog.warning("%s from %s refused: %d s to wait after repeated wrong passwords", "Basic sign-in as %r" % name if name else "bearer token", self.proxy.source(request), wait)
            return JSONResponse({"detail": f"Too many attempts; try again in {wait} seconds"}, status_code=429, headers={"Retry-After": str(wait)})
        user, scope = apppasswords.authenticate_scoped(name or None, pw, self.app)
        if not user and (request.url.path == MCP_PATH or request.url.path.startswith(MCP_PATH + "/")):
            # the suite's one MCP server: an ioStart app password reaches every app's /mcp (apppasswords.HUB)
            user, scope = apppasswords.authenticate_hub(name or None, pw, self.app), ""
        if not user:
            wait = users.attempt_failed(visitor, name)
            authlog.warning("wrong %s from %s%s", f"password for {name!r} (Basic)" if name else "bearer token", self.proxy.source(request), f"; {wait} s wait" if wait else "")
            return None
        users.attempt_succeeded(visitor, name)
        request.state.app_password_scope = scope or ""
        return user

    def scope_refusal(self, request: Request):
        """A 403 when the request signed in with a scoped app password and asks for something outside its scope."""
        scope = getattr(request.state, "app_password_scope", "")
        if not scope or not getattr(request.state, "user", None):
            return None
        if scope == apppasswords.READ:
            if request.method in ("GET", "HEAD") and not request.url.path.startswith(apppasswords.READ_NEVER):
                return None
            return JSONResponse({"detail": f"This app password may only read from {self.label} (no changes, no MCP, no sync)."},
                                status_code=403)
        if request.url.path.startswith(tuple(self.scope_paths.get(scope, ())) or ("\0",)):
            return None
        return JSONResponse({"detail": f"This app password is for {self.label}'s sync protocols only (CalDAV / CardDAV). "
                                       "Make one without that limit in Settings › Account."}, status_code=403)

    def finish(self, request: Request, response):
        """After the route: set the session cookie when a proxy sign-in needs one here too (so the same browser stays
        signed in on the home network, where requests reach the app directly without Cloudflare)."""
        user, path = getattr(request.state, "user", None), request.url.path
        if user and getattr(request.state, "renew_cookie", False) and request.state.cookie_uid == user["id"] and "set-cookie" not in response.headers:
            via = request.cookies.get(sessions.VIA_COOKIE) or "password"
            sessions.set_cookie(response, request.cookies.get(sessions.COOKIE), sessions.host_of(request), via, sessions.over_https(request))
        if request.state.via_proxy and user and request.state.cookie_uid != user["id"] and path != "/api/auth/logout":
            via = "cloudflare" if self.proxy.mode() == "cloudflare" else "proxy"
            tok = sessions.for_proxy(user["id"], self.app, via, getattr(request.state, "origin", None))
            sessions.set_cookie(response, tok, sessions.host_of(request), via, sessions.over_https(request))
        return response

    def cross_site(self, request: Request) -> bool:
        """A write from a page on another site (or another port) driving this one with the browser's cookies."""
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return False
        origin, site = request.headers.get("origin"), request.headers.get("sec-fetch-site")
        host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").lower()
        return site == "cross-site" or bool(origin and (origin == "null" or urlsplit(origin).netloc.lower() != host))

    def middleware(self, open_paths=(), open_prefixes=("/api/auth/",), is_open=None, before=None, after=None, api_prefix="/api/"):
        """A complete auth middleware: resolve, the require-sign-in rule (open_paths / open_prefixes, or whatever
        `is_open(path)` says, stay reachable; /api/auth/ and /api/status always are), the cross-site check on writes,
        and the cookie afterwards. `before(request)` runs once the user is known and may return a response (the app's own gates:
        MCP tokens...); `after(request, response)` runs at the end."""
        auth = self
        open_prefixes = tuple(open_prefixes) + ("/api/auth/",)
        open_paths = tuple(open_paths) + (STATUS_PATH,)  # the status answers everyone, as the sign-in routes do

        async def guard(request: Request, call_next):
            path = request.url.path
            if not await run_in_threadpool(db.available):  # the Shared ioSuite database is down: the shell and the open paths only, with a clear answer
                request.state.user, request.state.via_proxy = None, False
                if path in open_paths or (is_open and is_open(path)) or (path.startswith(open_prefixes) and not path.startswith("/api/auth/")):
                    return await call_next(request)
                return JSONResponse({"detail": f"The Shared ioSuite database cannot be reached ({db.error}); sign-in is unavailable until it is back."}, status_code=503)
            refused = await auth.resolve(request)
            if refused is None:
                refused = auth.scope_refusal(request)
            if refused is not None:
                return refused
            path = request.url.path
            if before:
                r = before(request)
                if hasattr(r, "__await__"):
                    r = await r
                if r is not None:
                    return r
            if request.state.user is None and path not in open_paths and not path.startswith(open_prefixes) and not (is_open and is_open(path)):
                # what a visitor who is not signed in may not reach: everything while sign-in is required, and
                # everything from outside the network while no account exists (the open rule is for the LAN)
                if await run_in_threadpool(auth.unclaimed, request):
                    return JSONResponse({"detail": UNCLAIMED, "unclaimed": True}, status_code=403)
                if await run_in_threadpool(users.require_login, auth.app):
                    if getattr(request.state, "no_role_user", None):
                        return auth.no_access(request, request.state.no_role_user["name"])
                    return JSONResponse({"detail": f"Sign in to use {auth.label}."}, status_code=401,
                                        headers={"WWW-Authenticate": f'Basic realm="{auth.realm}"'} if "authorization" in request.headers else {})
            if path.startswith(api_prefix) and auth.cross_site(request):
                return JSONResponse({"detail": "Requests from another site are refused"}, status_code=403)
            response = await call_next(request)
            auth.finish(request, response)
            if after:
                r = after(request, response)
                if hasattr(r, "__await__"):
                    await r
            return response
        return guard

    def no_access(self, request: Request, ident: str):
        msg = f"{ident} has no account on {self.label}. Ask its owner for access."
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": msg, "noAccess": True}, status_code=403)
        from html import escape
        out = "/cdn-cgi/access/logout" if self.proxy.external(request.headers, peer_of(request)) else None
        return HTMLResponse(f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>No access</title><style>body{{font:16px system-ui,sans-serif;max-width:520px;margin:15vh auto;padding:0 16px;color:#222;background:#fff}}
@media (prefers-color-scheme:dark){{body{{color:#eee;background:#111}}a{{color:#8ab4f8}}}}</style>
<h1>No access</h1><p>{escape(msg)}</p>{f'<p><a href="{out}">Sign in with another account</a></p>' if out else ''}""", status_code=403)

    # ---- sign-in helpers
    def sign_in(self, response, request: Request, user: dict, via: str):
        tok = sessions.create(user["id"], self.app, via, getattr(request.state, "origin", None) or sessions.describe(request, self.proxy))
        sessions.set_cookie(response, tok, sessions.host_of(request), via, sessions.over_https(request))

    def signed_in_by(self, request: Request, u):
        if not u:
            return None
        if getattr(request.state, "via_proxy", False):
            return "cloudflare" if self.proxy.mode() == "cloudflare" else "proxy"
        via = request.cookies.get(sessions.VIA_COOKIE)
        return via if via in ("cloudflare", "proxy", "password", "oneclick") else ("oneclick" if u.get("passwordless") else "password")

    def me(self, request: Request) -> dict:
        u = self.current_user(request)
        outside = self.outside(request)
        shut = outside and not users.any_users()  # no account yet, asked from outside: nothing is open (unclaimed)
        return {"user": u, "settings": users.get_settings(u["id"], self.app) if u else {}, "usersExist": users.any_users(),
                "isAdmin": users.is_admin(u) and not shut, "isSuiteAdmin": users.is_suite_admin(u) and not shut,
                "isMember": users.is_member(u) and not shut, "canWrite": users.at_least(u, self.write_role) and not shut, "signedIn": users.is_signed_in(u) and not shut,
                "requireLogin": shut or users.require_login(self.app), "unclaimed": shut,
                "viaProxy": bool(getattr(request.state, "via_proxy", False)), "signedInBy": self.signed_in_by(request, u),
                "throughCloudflare": outside, "app": self.app}

    # ---- the routers (iosuite_shared.routers)
    def router(self) -> APIRouter:
        """/api/auth/*: login, accounts, logout, me, settings, password, setup, sessions, app-passwords, proxy, suite."""
        return routers.auth_router(self)

    def users_router(self) -> APIRouter:
        """/api/users: the accounts as this app's admins see them."""
        return routers.users_router(self)

    def admin_router(self) -> APIRouter:
        """/api/suite-admin/*: everything in the Shared ioSuite database, for suite admins."""
        return routers.admin_router(self)

    def server_router(self, updater, log_file=None, info=None, apply=None) -> APIRouter:
        """Settings › Server: the panel (GET /api/server/ui.js), GET/POST /api/server, GET /api/log (admins)."""
        return routers.server_router(self, updater, log_file, info, apply)

    def status_router(self, updater=None, extra=None) -> APIRouter:
        """GET /api/status, open to everyone: the same shape in every app."""
        return routers.status_router(self, updater, extra)

    def profile_router(self, base_url) -> APIRouter:
        """The Apple profile downloads (iosuite_shared.appleprofile): /profile/<token>/<file> and the profile for all
        the apps that sync (/api/apple-profile/suite). base_url(request): the address this app is reached at."""
        from iosuite_shared import appleprofile
        return appleprofile.router(self, base_url)

    # ---- the MCP endpoint's gate
    def mcp_gate(self, enabled, path: str = MCP_PATH, on_user=None, on_request=None):
        """A `before` hook for middleware() (or something an app's own hook calls first): a request to the MCP endpoint
        is refused with 404 while the switch is off (`enabled()` is false), with 403 when a page in a browser sends it
        under a host name the app is not known by (suite.known_host: a page on another site that points its own name
        at this server; an MCP client is not a browser and is not asked), with 401 when nobody is signed in (MCP clients sign in with an app password: HTTP Basic, or a bearer token),
        and otherwise `on_user(user)` runs (an app sets its MCP context variable there), and `on_request(request)` (the
        start page keeps the sign-in it passes on to the other apps' MCP servers). Anything else passes."""
        auth = self

        def gate(request: Request):
            p = request.url.path
            if p != path and not p.startswith(path + "/"):
                return None
            if not enabled():
                return JSONResponse({"detail": "The MCP server is switched off (Settings › Server)."}, status_code=404)
            if "origin" in request.headers or "sec-fetch-site" in request.headers:  # sent by a page in a browser
                for name in ("host", "x-forwarded-host"):
                    if name in request.headers and not suite.known_host(auth.app, request.headers[name]):
                        return JSONResponse({"detail": f"{auth.label} is not known by the name {request.headers[name][:80]!r}. Set PUBLIC_URL in "
                                                       "config.env to the address it is reached at, or open it there once as an admin."}, status_code=403)
            user = auth.current_user(request)
            if not user:
                return JSONResponse({"detail": "Sign in with your user name and an app password (HTTP Basic), or send 'Authorization: Bearer "
                                               "<app password>'. Make one in Settings › Account."},
                                    status_code=401, headers={"WWW-Authenticate": f'Basic realm="{auth.realm}", Bearer realm="{auth.realm}"'})
            if on_user:
                on_user(user)
            if on_request:
                on_request(request)
            return None
        return gate

    # ---- what every app's FastAPI gets the same way
    def install(self, app, api_prefix: str = "/api/", body_limit: int = 4 << 20, limit_for=None, not_found=()) -> None:
        """The pieces every app of the suite adds to its FastAPI, once:
        - errors.Invalid (what the suite's validation raises) or malformed JSON out of a route is the client's mistake:
          a 400 that says so. Any other ValueError is answered 400 as well, and logged with its traceback, since it
          came from somewhere that did not mean to answer the client (a TypeError stays a 500);
          `not_found` names the app's own exception classes that mean 404;
        - the forwarded headers (proxyauth.Forwarded): the address the connection came from is kept for proxy sign-in
          and the throttles, and X-Forwarded-For / -Proto are believed from this machine and from the reverse proxies
          listed under Settings › Security (the app starts uvicorn with proxy_headers=False);
        - the headers: X-Content-Type-Options: nosniff, Referrer-Policy: same-origin, and X-Frame-Options: SAMEORIGIN
          with Content-Security-Policy: frame-ancestors 'self' (a page of another site cannot show the app in a frame;
          a <meta> policy cannot say that) on everything, Cache-Control: no-store on the API (api_prefix) and no-cache
          elsewhere, unless the route set its own;
        - the body cap: a request body larger than `limit_for(path, content_type)` bytes (`body_limit` by default) is
          refused with 413, by its Content-Length before it is read, and as it arrives when it comes chunked or longer
          than it said, so nothing large is ever held in memory."""
        log = self.log
        limit_for = limit_for or (lambda path, ctype: body_limit)

        def error(msg: str, status: int):
            return JSONResponse({"detail": msg}, status_code=status)

        for exc in not_found:
            @app.exception_handler(exc)
            async def _not_found(request: Request, e: Exception):
                return error(str(e) or "Not found", 404)

        @app.exception_handler(Invalid)
        @app.exception_handler(json.JSONDecodeError)
        async def _bad_input(request: Request, e: Exception):
            log.info("bad input on %s %s: %s", request.method, request.url.path, str(e)[:200])
            return error(f"Bad request: {str(e)[:200] or type(e).__name__}", 400)

        @app.exception_handler(ValueError)
        async def _value_error(request: Request, e: Exception):
            log.warning("a ValueError on %s %s that no validation raised (answered 400; a bug if the request was fine)",
                        request.method, request.url.path, exc_info=e)
            return error(f"Bad request: {str(e)[:200] or type(e).__name__}", 400)

        @app.middleware("http")
        async def _headers_and_limits(request: Request, call_next):
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                try:
                    size = int(request.headers.get("content-length") or 0)
                except ValueError:
                    return error("Bad Content-Length", 400)
                if size > limit_for(request.url.path, content_type(request.headers)):
                    return error("That request is too large", 413)
            response = await call_next(request)
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("Referrer-Policy", "same-origin")
            response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
            response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'self'")
            if "cache-control" not in response.headers:
                response.headers["Cache-Control"] = "no-store" if request.url.path.startswith(api_prefix) else "no-cache"
            return response

        app.add_middleware(BodyCap, limit_for=limit_for, error=error)
        app.add_middleware(Forwarded)  # added last: the outermost layer, so the peer is the real one

    def _delete(self, me, user_id: int):
        """DELETE /api/users/{id} (suite admins: an account is the whole suite's)."""
        if me and me["id"] == user_id:
            raise Invalid("You cannot delete your own account while signed in")
        users.delete(user_id)

    def _update(self, me, user_id: int, body: dict):
        """PATCH /api/users/{id}. An admin of this app sets the account's role here; the account itself (name, email,
        display name, password, listed, suiteAdmin, roles elsewhere) belongs to the whole suite, so only a suite admin
        changes it: sign-in at a proxy finds an account by its email and name, and a password opens every app."""
        target = users.get(user_id, self.app)
        suite = users.is_suite_admin(me)
        if not suite:
            same = {"name": target["name"], "email": target.get("email") or "", "displayName": target.get("displayName") or "",
                    "listed": bool(target.get("listed", True)), "suiteAdmin": bool(target["suiteAdmin"])}
            beyond = [k for k in ("name", "email", "displayName", "password", "listed", "suiteAdmin", "roles")
                      if body.get(k) is not None and (k not in same or body[k] != same[k])]  # a form that sends them unchanged is fine
            if beyond:
                raise PermissionError(f"Only a suite admin can change an account's {', '.join(beyond)} (Settings › Security)")
            if target["suiteAdmin"] and body.get("role") is not None:
                raise PermissionError("Only a suite admin can change a suite admin's role")
        role = body.get("role")
        if role is not None and me and me["id"] == user_id and role != "admin" and users.admins_of(self.app) <= 1:
            raise Invalid("That is the only admin; make someone else admin first")
        if suite:
            users.update(user_id, role=role, app=self.app, password=body.get("password"), name=body.get("name"), email=body.get("email"),
                         display_name=body.get("displayName"), listed=None if body.get("listed") is None else bool(body.get("listed")),
                         suite_admin=None if body.get("suiteAdmin") is None else bool(body.get("suiteAdmin")))
        elif role is not None:
            users.update(user_id, role=role, app=self.app)
        if suite and isinstance(body.get("roles"), dict):
            for a, rr in body["roles"].items():
                users.set_role(user_id, str(a)[:32], str(rr))
        if self.on_update:
            self.on_update(user_id, body)
        apppasswords.forget()
        from iosuite_shared import proxyauth
        proxyauth.forget_identities()
