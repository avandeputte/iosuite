"""Bring everything over from a running Homebox, through its REST API: the things with all their details, the places,
the labels with their colours, the own fields, the photos and attachments (manuals, receipts, warranties) and the
completed maintenance log. Homebox's CSV export has no files and no log; its API has them.

Homebox's API (sysadminsmedia/homebox, backend/app/api): POST /api/v1/users/login with the user name and password
gives a token ("Bearer ..."), sent as Authorization. Two shapes are read:
- up to v0.25: /v1/items (paged), /v1/items/{id}, /v1/locations/tree, /v1/labels, /v1/items/{id}/maintenance,
  /v1/items/{id}/attachments/{attachment}
- v0.26 on: the same under /v1/entities (places are entities too, entityType.isLocation) and /v1/tags.
Differences between versions that are handled: up to v0.14 the maintenance log is {entries: [...]} (later a list) and its
filter is not "status" (an unknown query key is a 500 there, so the log is asked for without one: every version then
gives all of it); an attachment's title is in "document" up to v0.14; some versions answer an attachment with a one-time
{token} for /attachments/download?token=, which is followed.

Running it again brings the same Homebox up to date instead of adding it twice: a thing it made remembers Homebox's id
(import_ref "homebox:<id>"); a thing from an earlier CSV import of the same Homebox is found by its name and place and
taken over. A file already kept with the thing (the same bytes) and a log line already there (the same day and title)
are not added again. Scheduled maintenance that was never done is not brought (ioThings' upkeep repeats; add it there).

It runs in the background (a few hundred things with their files take minutes): start() checks the address and the
sign-in, then a thread does the work and progress() says how far it got. One import at a time. Nothing about the
Homebox account is kept.
"""
import datetime as dt
import hashlib
import json
import logging
import threading
import urllib.error
import urllib.parse
import urllib.request

from iosuite_shared import outbound
from iosuite_shared.errors import Invalid

from app import config, db, files, model, upkeep

log = logging.getLogger("iothings")
TIMEOUT = 60
PAGE = 100
REF = "homebox:"
KINDS = {"photo": "photo", "manual": "manual", "receipt": "receipt", "warranty": "warranty", "attachment": "other"}

_lock = threading.Lock()
_job: dict = {"state": "idle"}


def _allowed(ip) -> bool:
    """Homebox is usually on the home network, often on this very server: anything but the link-local addresses (where
    cloud metadata services answer) and the unspecified one."""
    return not (ip.is_link_local or ip.is_unspecified or ip.is_multicast)


class Homebox:
    """A signed-in connection to one Homebox."""

    def __init__(self, url: str):
        url = (url or "").strip().rstrip("/")
        if url and "://" not in url:
            url = "https://" + url
        for tail in ("/api/v1", "/api"):
            if url.endswith(tail):
                url = url[: -len(tail)]
        outbound.check(url, _allowed)  # http(s), and a host the server may reach
        self.base = url
        self.token = ""
        self.attachment_token = ""
        self.shape = "items"
        self.version = ""
        self.log_problem = ""
        self._open = outbound.opener(_allowed).open

    def _req(self, path: str, params: dict | None = None, body=None, form: bool = False, auth: bool = True):
        url = f"{self.base}/api{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
        headers = {"Accept": "application/json", "User-Agent": "ioThings"}
        data = None
        if body is not None:
            data = urllib.parse.urlencode(body).encode() if form else json.dumps(body).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
        if auth and self.token:
            headers["Authorization"] = self.token
        return self._open(urllib.request.Request(url, data=data, headers=headers), timeout=TIMEOUT)

    def json(self, path: str, params: dict | None = None):
        with self._req(path, params) as r:
            return json.loads(r.read() or b"null")

    def login(self, user: str, password: str) -> None:
        if not user or not password:
            raise Invalid("Homebox's user name (an email address) and password, please")
        answer = None
        for form in (False, True):  # JSON, or a form for older versions
            try:
                with self._req("/v1/users/login", body={"username": user, "password": password, "stayLoggedIn": False},
                               form=form, auth=False) as r:
                    answer = json.loads(r.read() or b"{}")
                    break
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    raise Invalid("Homebox did not accept that user name and password") from e
                if form or e.code not in (400, 415, 422):
                    raise Invalid(f"Homebox answered {e.code} to the sign-in: is that its address?") from e
            except (urllib.error.URLError, OSError, ValueError) as e:
                raise Invalid(f"Homebox could not be reached at {self.base}: {getattr(e, 'reason', e)}") from e
        token = (answer or {}).get("token") or ""
        if not token:
            raise Invalid("Homebox's answer to the sign-in had no token: is that its address?")
        self.token = token if token.lower().startswith("bearer ") else f"Bearer {token}"
        self.attachment_token = (answer or {}).get("attachmentToken") or ""
        try:
            self.json("/v1/items", {"page": 1, "pageSize": 1})
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise Invalid(f"Homebox answered {e.code} when asked for its things") from e
            self.shape = "entities"
        try:
            self.version = str(((self.json("/v1/status") or {}).get("build") or {}).get("version") or "")[:40]
        except (urllib.error.URLError, OSError, ValueError, AttributeError):
            self.version = ""

    # ---- what there is
    def places(self) -> dict:
        """{place id: ["House", "Kitchen"]} from the tree of places."""
        tree = self.json("/v1/locations/tree" if self.shape == "items" else "/v1/entities/tree") or []
        out = {}

        def walk(nodes, path):
            for n in nodes or []:
                if (n.get("type") or "location") not in ("location", "") and self.shape == "items":
                    continue
                p = [*path, (n.get("name") or "").strip()]
                out[n.get("id")] = p
                walk(n.get("children"), p)
        walk(tree, [])
        return out

    def labels(self) -> list[dict]:
        return self.json("/v1/labels" if self.shape == "items" else "/v1/tags") or []

    def ids(self) -> list[tuple[str, str]]:
        """(id, name) of every thing, the archived ones too."""
        out, page = [], 1
        path = "/v1/items" if self.shape == "items" else "/v1/entities"
        while True:
            r = self.json(path, {"page": page, "pageSize": PAGE, "includeArchived": "true"}) or {}
            rows = r.get("items") or []
            for x in rows:
                if self.shape == "entities" and ((x.get("entityType") or {}).get("isLocation")):
                    continue
                out.append((x["id"], (x.get("name") or "").strip() or x["id"]))
            total = r.get("total") or 0
            if not rows or page * PAGE >= total or page > 1000:
                return out
            page += 1

    def thing(self, hid: str) -> dict:
        return self.json(f"/v1/{self.shape}/{hid}") or {}

    def maintenance(self, hid: str) -> list[dict]:
        """Every entry of one thing's maintenance log, done and scheduled. No filter is sent: with none, every version
        gives all of it, while a filter one version knows is a 500 in another."""
        try:
            r = self.json(f"/v1/{self.shape}/{hid}/maintenance")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            raise
        if isinstance(r, dict):  # up to v0.14: {itemId, costTotal, costAverage, entries}
            r = r.get("entries")
        return [m for m in r or [] if isinstance(m, dict)]

    def attachment(self, hid: str, aid: str) -> tuple[bytes, str]:
        """(bytes, type) of one attachment."""
        path = f"/v1/{self.shape}/{hid}/attachments/{aid}"
        try:
            r = self._req(path)
        except urllib.error.HTTPError as e:
            if e.code not in (401, 403) or not self.attachment_token:
                raise
            r = self._req(path, {"access_token": self.attachment_token}, auth=False)
        with r:
            kind = r.headers.get("Content-Type", "")
            raw = r.read(config.MAX_FILE_BYTES + 1)
        if kind.startswith("application/json") and len(raw) < 4096:  # older versions: a token to fetch it with
            try:
                tok = json.loads(raw).get("token")
            except (ValueError, AttributeError):
                tok = None
            if tok:
                with self._req(f"/v1/{self.shape}/{hid}/attachments/download", {"token": tok}, auth=False) as r2:
                    kind = r2.headers.get("Content-Type", "")
                    raw = r2.read(config.MAX_FILE_BYTES + 1)
        return raw, kind.split(";")[0].strip()


# ---- from Homebox's shapes to ioThings'

def _day(v) -> str | None:
    s = str(v or "")[:10]
    if not s or s.startswith("0001"):
        return None
    try:
        d = dt.date.fromisoformat(s)
    except ValueError:
        return None
    return d.isoformat() if 1900 <= d.year <= 2200 else None


def _amount(v):
    try:
        return None if v in (None, "") or float(v) == 0 else v
    except (TypeError, ValueError):
        return None


def _field(f: dict) -> dict | None:
    name = (f.get("name") or "").strip()
    kind = f.get("type") or ""
    if kind == "boolean":
        v = "yes" if (f.get("booleanValue") or f.get("boolean_value")) else "no"
    elif kind == "number":
        v = f.get("numberValue", f.get("number_value"))
        v = "" if v is None else str(v)
    elif kind == "time":
        v = _day(f.get("timeValue") or f.get("time_value")) or ""
    else:
        v = f.get("textValue") or f.get("text_value") or ""
    return {"name": name, "value": str(v)} if name and str(v).strip() else None


def _data(x: dict, places: dict) -> tuple[dict, list[str]]:
    """(ioThings' fields, the place's path) of one Homebox thing."""
    loc = x.get("location") or {}
    if not loc and _parent_is_place(x, places):
        loc = x["parent"]
    path = places.get(loc.get("id")) or ([loc["name"]] if loc.get("name") else [])
    sold = _day(x.get("soldTime") or x.get("soldDate"))
    notes = x.get("notes") or ""
    parent = x.get("parent") or {}
    if parent.get("name") and parent.get("id") not in places:
        notes = (notes + "\n\n" if notes else "") + f"In Homebox, inside: {parent['name']}"
    aid = str(x.get("assetId") or "").strip()
    data = {
        "name": (x.get("name") or "").strip() or "(no name)", "description": x.get("description") or None,
        "quantity": max(1, int(float(x.get("quantity") or 1))),
        "manufacturer": x.get("manufacturer") or None, "modelNumber": x.get("modelNumber") or None,
        "serialNumber": x.get("serialNumber") or None, "assetId": aid if aid.strip("0-") else None,
        "purchaseDate": _day(x.get("purchaseTime") or x.get("purchaseDate")), "purchasePrice": _amount(x.get("purchasePrice")),
        "purchaseFrom": x.get("purchaseFrom") or None, "warrantyExpires": _day(x.get("warrantyExpires")),
        "lifetimeWarranty": bool(x.get("lifetimeWarranty")), "warrantyDetails": x.get("warrantyDetails") or None,
        "insured": bool(x.get("insured")), "archived": bool(x.get("archived")) or bool(sold),
        "soldDate": sold, "soldPrice": _amount(x.get("soldPrice")), "soldTo": x.get("soldTo") or None,
        "soldNotes": x.get("soldNotes") or None, "notes": notes or None,
        "fields": [f for f in (_field(f) for f in x.get("fields") or []) if f],
        "labels": [t["name"] for t in (x.get("labels") or x.get("tags") or []) if t.get("name")],
    }
    return data, [p for p in path if p]


def _parent_is_place(x: dict, places: dict) -> bool:
    p = x.get("parent") or {}
    return bool(p.get("id")) and p["id"] in places


def _match(hid: str, data: dict, path: list[str]) -> dict | None:
    """The thing an earlier import made of this one: by Homebox's id, else one from a CSV import with the same name in
    the same place (only when exactly one fits)."""
    row = db.one("SELECT id FROM thg_items WHERE import_ref = %s", (REF + hid,))
    if row:
        return model.get(row["id"])
    rows = db.q("SELECT id FROM thg_items WHERE import_ref IS NOT NULL AND import_ref NOT LIKE %s AND LOWER(name) = LOWER(%s)",
                (REF + "%", data["name"]))
    want = " / ".join(path).lower()
    fit = [r for r in rows if _path_of(r["id"]).lower() == want]
    return model.get(fit[0]["id"]) if len(fit) == 1 else None


def _path_of(item_id: int) -> str:
    it = db.one("SELECT location_id FROM thg_items WHERE id = %s", (item_id,))
    loc = next((x for x in model.locations() if x["id"] == (it or {}).get("location_id")), None)
    return loc["path"] if loc else ""


# ---- the job

def progress() -> dict:
    with _lock:
        return {k: (list(v) if isinstance(v, list) else v) for k, v in _job.items()}


def _set(**kw) -> None:
    with _lock:
        _job.update(kw)


def _note(msg: str) -> None:
    with _lock:
        if len(_job.setdefault("skipped", [])) < 300:
            _job["skipped"].append(msg)


def start(u: dict, url: str, user: str, password: str, background: bool = True) -> dict:
    """Sign in to Homebox (errors at once: a wrong address or password), then bring everything over in a thread."""
    model.need_edit_all(u, "everything at once (an import from a Homebox server)")
    with _lock:
        if _job.get("state") == "running":
            raise Invalid("An import from Homebox is running already")
    hb = Homebox(url)
    hb.login(user, password)
    with _lock:
        _job.clear()
        _job.update(state="running", source=hb.base, by=u.get("displayName") or u.get("name"), started=dt.datetime.now().isoformat(timespec="seconds"),
                    total=0, done=0, added=0, changed=0, failed=0, files=0, listed=0, log=0, skipped=[], error=None,
                    version=hb.version, step="Reading the places and labels")
    if background:
        threading.Thread(target=_run, args=(u, hb), name="homebox-import", daemon=True).start()
    else:
        _run(u, hb)
    return progress()


def _run(u: dict, hb: Homebox) -> None:
    try:
        places = hb.places()
        cache: dict = {}
        for path in places.values():  # every place, the empty ones too
            if path:
                model.location_by_path(path, cache)
        for t in hb.labels():
            if t.get("name"):
                model.save_label(u, {"name": t["name"], **({"color": t["color"]} if model.COLOR.fullmatch(str(t.get("color") or "")) else {})})
        _set(step="Listing the things")
        ids = hb.ids()
        _set(total=len(ids), step="Bringing the things over")
        first = None
        for hid, name in ids:
            try:
                _one(u, hb, hid, places, cache)
            except Exception as e:  # one thing that fails does not stop the rest
                log.warning("Homebox import: %s (%s): %s", name, hid, e)
                _note(f"{name}: {_why(e)}")
                first = first or e
                with _lock:
                    _job["failed"] += 1
            with _lock:
                _job["done"] += 1
        now = dt.datetime.now().isoformat(timespec="seconds")
        if ids and _job["failed"] == len(ids):  # nothing came over: that is a failure, not "done"
            _set(state="failed", step=None, finished=now, error=f"not one of the {len(ids)} things came over: {_why(first)}")
        else:
            _set(state="done", step=None, finished=now)
    except Exception as e:
        log.exception("Homebox import failed")
        _set(state="failed", error=_why(e), finished=dt.datetime.now().isoformat(timespec="seconds"))


def _why(e) -> str:
    """An error in words: which Homebox answer it was, for an HTTP error."""
    if isinstance(e, urllib.error.HTTPError):
        return f"Homebox answered {e.code} ({e.reason}) to {urllib.parse.urlsplit(e.url or '').path or 'a request'}"
    return str(e) or e.__class__.__name__


def _one(u: dict, hb: Homebox, hid: str, places: dict, cache: dict) -> None:
    x = hb.thing(hid)
    data, path = _data(x, places)
    data["locationId"] = model.location_by_path(path, cache)
    it = _match(hid, data, path)
    if it:
        it = model.update(u, it, data)
        db.ex("UPDATE thg_items SET import_ref = %s, updated_at = updated_at WHERE id = %s", (REF + hid, it["id"]))
        with _lock:
            _job["changed"] += 1
    else:
        it = model.create(u, data, import_ref=REF + hid)
        with _lock:
            _job["added"] += 1
    item = model.get(it["id"])
    have = {r["sha256"] for r in db.q("SELECT sha256 FROM thg_files WHERE item_id = %s", (item["id"],))}
    atts = sorted(x.get("attachments") or [], key=lambda a: (not a.get("primary"), a.get("type") != "photo", a.get("createdAt") or ""))
    for a in atts:
        kind = KINDS.get(a.get("type") or "attachment")
        if not kind or not a.get("id"):  # Homebox's own small pictures
            continue
        with _lock:
            _job["listed"] += 1
        doc = a.get("document") or {}  # up to v0.14
        name = (a.get("title") or doc.get("title") or a.get("path") or doc.get("path") or "").rsplit("/", 1)[-1] or "file"
        try:
            raw, mime = hb.attachment(hid, a["id"])
        except (urllib.error.URLError, OSError) as e:
            _note(f"{data['name']}: {name}: not fetched ({_why(e)})")
            continue
        if len(raw) > config.MAX_FILE_BYTES:
            _note(f"{data['name']}: {name}: larger than {config.MAX_FILE_BYTES // 1048576} MB")
            continue
        if hashlib.sha256(raw).hexdigest() in have:
            continue
        try:
            files.add(u, item, raw, name, a.get("mimeType") or mime, kind)
        except Invalid as e:
            if kind == "photo":  # a picture this server cannot read: kept as a file all the same
                try:
                    files.add(u, item, raw, name, a.get("mimeType") or mime, "other")
                except Invalid as e2:
                    _note(f"{data['name']}: {name}: {e2}")
                    continue
            else:
                _note(f"{data['name']}: {name}: {e}")
                continue
        have.add(hashlib.sha256(raw).hexdigest())
        with _lock:
            _job["files"] += 1
    logged = {(str(r["done_on"]), r["title"].lower()) for r in db.q("SELECT done_on, title FROM thg_maintenance WHERE item_id = %s", (item["id"],))}
    later = 0
    entries = []
    if not hb.log_problem:
        try:
            entries = hb.maintenance(hid)
        except (urllib.error.URLError, OSError, ValueError) as e:  # the thing and its files came over all the same
            hb.log_problem = _why(e)
            _note(f"The maintenance log could not be read ({hb.log_problem}), so no log lines were brought; the rest was")
    for m in entries:
        day = _day(m.get("completedDate"))
        title = (m.get("name") or "").strip() or "Maintenance"
        if not day:
            later += 1
            continue
        if (day, title.lower()) in logged:
            continue
        upkeep.log_add(u, item["id"], {"date": day, "title": title[:255], "notes": m.get("description") or None, "cost": _amount(m.get("cost"))})
        logged.add((day, title.lower()))
        with _lock:
            _job["log"] += 1
    if later:
        _note(f"{data['name']}: {later} scheduled maintenance not brought (add it as upkeep)")
