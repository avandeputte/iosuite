"""The files the suite's apps keep in their databases, written out as plain files beside the dump.

Several apps keep what people give them in the database itself (ioThings its photos, manuals and receipts, ioDocs its
scans, ioMoney its receipts, ioNote its pictures and attachments, ioRecipe its pictures, the start page its uploaded
bookmark icons), so one database backup holds everything. In the dump those bytes are hex inside INSERT statements:
safe, but nobody can open them without restoring the database first. So a backup also carries them as files, under
``files/<app>/...`` in the backup's tar, named after what they belong to (the thing, the document, the note) with their
own file name and extension, so a backup can be opened with any archive tool and browsed. The dump stays what a restore
reads; the files are a copy of the same bytes for people.

An app is recognised by its tables, in whichever database it is (the database names are each install's own), so a
database of another kind is left alone. The bytes are read after the dump, in one transaction per database (a file
is whole or not there), in chunks small enough for any server's max_allowed_packet.

Only the standard library and the mariadb client are used, like engine.py (app/offline.py runs without the web app).
"""

import hashlib
import mimetypes
import os
import re
import subprocess
import tempfile

ROOT = "files"
CHUNK = 4 << 20  # bytes per SELECT; halved again when the server's max_allowed_packet is small (hex is twice the size)


class FilesError(Exception):
    pass


def _q(name):
    return "`" + name.replace("`", "``") + "`"


def _lit(v):
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'"


# --------------------------------------------------------------------------
# names
# --------------------------------------------------------------------------

_BAD = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]+')
MAX_SEGMENT = 100


def clean(text, fallback="file"):
    """One path segment a person can read, that every file system takes (Windows' rules are the strictest)."""
    s = _BAD.sub("_", str(text or "")).strip().strip(".").strip()
    s = re.sub(r"\s+", " ", s)
    if len(s) > MAX_SEGMENT:
        root, ext = os.path.splitext(s)
        ext = ext if 0 < len(ext) <= 10 else ""
        s = root[:MAX_SEGMENT - len(ext)].rstrip() + ext
    if s.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "LPT1", "LPT2", "LPT3"}:
        s = "_" + s
    return s or fallback


def with_ext(name, mime):
    """The name with an extension that fits its type, when it has none."""
    name = clean(name)
    if os.path.splitext(name)[1]:
        return name
    ext = {"image/jpeg": ".jpg", "image/svg+xml": ".svg", "text/plain": ".txt"}.get(mime or "") \
        or mimetypes.guess_extension(mime or "") or ""
    return clean(name + ext)


class Names:
    """Hands out unique paths: a folder per thing (two things of the same name get "Name (2)"), a file name once per
    folder. Compared without case, since a Mac or Windows disk does not tell "Receipt.pdf" and "receipt.pdf" apart."""

    def __init__(self):
        self.dirs = {}     # (parent, ident) -> segment
        self.taken = {}    # parent -> set of lower-case names in it

    def _unique(self, parent, name):
        taken = self.taken.setdefault(parent, set())
        root, ext = os.path.splitext(name)
        if not ext or len(ext) > 10:
            root, ext = name, ""
        cand, n = name, 1
        while cand.lower() in taken:
            n += 1
            cand = "%s (%d)%s" % (root, n, ext)
        taken.add(cand.lower())
        return cand

    def path(self, app, dirs, name):
        """dirs: [(segment, ident)], ident telling apart two folders of the same name (None: one folder by name)."""
        parent = "/".join([ROOT, app])
        for seg, ident in dirs:
            seg = clean(seg, "Untitled")
            key = (parent.lower(), ident if ident is not None else seg.lower())
            if key not in self.dirs:
                self.dirs[key] = self._unique(parent.lower(), seg)
            parent = parent + "/" + self.dirs[key]
        return parent + "/" + self._unique(parent.lower(), clean(name))


# --------------------------------------------------------------------------
# what each app keeps
# --------------------------------------------------------------------------
# Each source: the app, the tables that tell it is that app's database, a query listing its files (in that database)
# and how to make a path of a row. A row of the query: key, size, then the source's own columns. Bytes are either in a
# column of the listed table (col) or in parts (parts: table, key column; parts numbered n from 0).

def _things(r, n, _people):
    item_id, item, kind, name, mime = r[2:7]
    name = with_ext(name, mime)
    if kind and kind not in ("photo", "other"):
        name = "%s - %s" % (kind.capitalize(), name)
    return [(item or "Thing", item_id)], name


def _docs(r, n, _people):
    doc_id, title, archived, name, mime = r[2:7]
    dirs = [("Archived", None)] if archived == "1" else []
    return dirs + [(title or "Document", doc_id)], with_ext(name, mime)


def _money(r, n, _people):
    day, merchant, amount, name, mime = r[2:7]
    day = day or ""
    label = "%s %s %s" % (day, merchant or "Transaction", amount or "")
    return [(day[:4] or "Undated", None)], "%s - %s" % (clean(label.strip()), with_ext(name, mime))


def _note_title(title, body):
    t = (title or "").strip()
    if not t:
        for line in (body or "").splitlines():
            line = line.strip().lstrip("#").strip()
            if line:
                t = line[:80]
                break
    return t or "Untitled note"


def _person(people, uid):
    return people.get(str(uid)) or ("Person %s" % uid)


def _note_picture(r, n, people):
    note, title, body, uid, mime = r[2:7]
    return [(_person(people, uid), "u%s" % uid), (_note_title(title, body), note)], with_ext("Picture", mime)


def _note_attachment(r, n, people):
    note, title, body, uid, name, mime = r[2:8]
    return [(_person(people, uid), "u%s" % uid), (_note_title(title, body), note)], with_ext(name, mime)


def _recipes(r, n, _people):
    recipe_id, title, step = r[2:5]
    if step not in (None, "NULL", ""):
        name = "Step %d.jpg" % (int(step) + 1)
    else:
        name = "Photo %d.jpg" % (n + 1)
    return [(title or "Recipe", recipe_id)], name


def _icons(r, n, _people):
    name = r[2]
    return [("Bookmark icons", None)], with_ext(name or "Bookmark", "image/svg+xml")


SOURCES = [
    {"app": "ioThings", "needs": {"thg_items", "thg_files", "thg_file_parts"},
     "list": "SELECT f.id, f.size, i.id, i.name, f.kind, f.name, f.mime FROM thg_files f "
             "JOIN thg_items i ON i.id = f.item_id ORDER BY i.name, i.id, f.position, f.id",
     "parts": ("thg_file_parts", "file_id"), "path": _things},
    {"app": "ioDocs", "needs": {"doc_documents", "doc_files", "doc_file_parts"},
     "list": "SELECT f.id, f.size, d.id, d.title, d.archived, f.name, f.mime FROM doc_files f "
             "JOIN doc_documents d ON d.id = f.doc_id ORDER BY d.archived, d.title, d.id, f.position, f.id",
     "parts": ("doc_file_parts", "file_id"), "path": _docs},
    {"app": "ioMoney", "needs": {"mny_transactions", "mny_receipts", "mny_receipt_parts"},
     "list": "SELECT r.id, r.size, t.day, COALESCE(NULLIF(t.merchant, ''), NULLIF(t.description, '')), t.amount, "
             "r.name, r.mime FROM mny_receipts r JOIN mny_transactions t ON t.id = r.transaction_id "
             "ORDER BY t.day, t.id, r.id",
     "parts": ("mny_receipt_parts", "receipt_id"), "path": _money},
    {"app": "ioNote", "needs": {"nts_notes", "nts_note_images"}, "people": True,
     "list": "SELECT i.uuid, LENGTH(i.data), n.uuid, n.title, LEFT(n.body, 400), n.user_id, i.mime "
             "FROM nts_note_images i JOIN nts_notes n ON n.uuid = i.uuid WHERE n.deleted = 0 "
             "ORDER BY n.user_id, n.created_at, n.uuid",
     "table": "nts_note_images", "key": "uuid", "col": "data", "path": _note_picture},
    {"app": "ioNote", "needs": {"nts_notes", "nts_attachments"}, "people": True,
     "list": "SELECT a.uuid, LENGTH(a.data), n.uuid, n.title, LEFT(n.body, 400), n.user_id, a.name, a.mime "
             "FROM nts_attachments a JOIN nts_notes n ON n.uuid = a.note_uuid WHERE n.deleted = 0 "
             "ORDER BY n.user_id, n.created_at, n.uuid, a.created_at, a.uuid",
     "table": "nts_attachments", "key": "uuid", "col": "data", "path": _note_attachment},
    {"app": "ioRecipe", "needs": {"rcp_recipes", "rcp_photos"},
     "list": "SELECT p.id, LENGTH(p.picture), r.id, r.title, p.step FROM rcp_photos p "
             "JOIN rcp_recipes r ON r.id = p.recipe_id ORDER BY r.title, r.id, p.step IS NOT NULL, p.step, p.position, p.id",
     "table": "rcp_photos", "key": "id", "col": "picture", "path": _recipes},
    {"app": "ioStart", "needs": {"prt_bookmark_nodes", "prt_bookmark_node_icons"},
     "list": "SELECT c.node_id, LENGTH(c.svg), b.name FROM prt_bookmark_node_icons c "
             "JOIN prt_bookmark_nodes b ON b.id = c.node_id ORDER BY b.name, b.id",
     "table": "prt_bookmark_node_icons", "key": "node_id", "col": "svg", "path": _icons},
]
INT_KEYS = {"id", "node_id"}


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------

def _tables(conn, databases):
    if not databases:
        return {}
    rows = conn.query("SELECT TABLE_SCHEMA, TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA IN (%s)"
                      % ", ".join(_lit(d) for d in databases))
    out = {}
    for schema, table in rows:
        out.setdefault(schema, set()).add(table)
    return out


def _people(conn, databases, log):
    """Account id -> the name people know them by, from the Shared ioSuite database (the one with ios_users): one in
    the backup if there is one, otherwise any on the server. Empty when there is none or it cannot be read."""
    try:
        found = [r[0] for r in conn.query("SELECT TABLE_SCHEMA FROM information_schema.TABLES WHERE TABLE_NAME = 'ios_users'")]
    except Exception:
        return {}
    found.sort(key=lambda s: s not in databases)
    for schema in found:
        try:
            return {r[0]: r[1] for r in conn.query(
                "SELECT id, COALESCE(NULLIF(display_name, ''), name) FROM %s.ios_users" % _q(schema))}
        except Exception as e:
            log("  files: could not read the people's names from %s (%s); notes go under the account numbers" % (schema, e))
    return {}


def plan(conn, databases, log=lambda m: None):
    """[(database, app, [file]), ...]: what each database holds, a file being {path, size, reads}; reads: the
    (sql, offset) pieces that give its bytes, in order."""
    tables = _tables(conn, databases)
    packet = 0
    try:
        packet = int(conn.scalar("SELECT @@max_allowed_packet") or 0)
    except Exception:
        pass
    chunk = CHUNK if not packet else min(CHUNK, max(64 << 10, packet // 2 - (64 << 10)))
    names, people, out = Names(), None, []
    apps_in = {}
    for db in databases:
        for src in SOURCES:
            if src["needs"] <= tables.get(db, set()):
                apps_in.setdefault(src["app"], set()).add(db)
    for db in databases:
        have = tables.get(db, set())
        for src in SOURCES:
            if not src["needs"] <= have:
                continue
            if src.get("people") and people is None:
                people = _people(conn, databases, log)
            app = src["app"] if len(apps_in[src["app"]]) == 1 else "%s (%s)" % (src["app"], clean(db))
            rows = conn.query("USE %s; %s" % (_q(db), src["list"]), timeout=600)
            parts = {}
            if "parts" in src:
                ptable, pkey = src["parts"]
                for k, n, size in conn.query("SELECT %s, n, LENGTH(data) FROM %s.%s ORDER BY %s, n"
                                             % (_q(pkey), _q(db), _q(ptable), _q(pkey)), timeout=600):
                    parts.setdefault(k, []).append((int(n), int(size or 0)))
            files, per_dir = [], {}
            for r in rows:
                key = r[0]
                dirs, name = src["path"](r, per_dir.get(r[2], 0), people or {})
                per_dir[r[2]] = per_dir.get(r[2], 0) + 1
                reads = []
                if "parts" in src:
                    ptable, pkey = src["parts"]
                    size = 0
                    for n, plen in parts.get(key, []):
                        for off in range(0, plen, chunk):
                            reads.append(("SELECT HEX(SUBSTRING(data, %d, %d)) FROM %s.%s WHERE %s = %s AND n = %d"
                                          % (off + 1, chunk, _q(db), _q(ptable), _q(pkey), int(key), n)))
                        size += plen
                else:
                    size = int(r[1] or 0)
                    kv = int(key) if src["key"] in INT_KEYS else key
                    for off in range(0, size, chunk):
                        reads.append("SELECT HEX(SUBSTRING(%s, %d, %d)) FROM %s.%s WHERE %s = %s"
                                     % (_q(src["col"]), off + 1, chunk, _q(db), _q(src["table"]), _q(src["key"]), _lit(kv)))
                files.append({"path": names.path(app, dirs, name), "size": size, "reads": reads, "app": app})
            if files:
                out.append((db, app, files))
    return out


def export(conn, databases, stage, log=lambda m: None, cancel=None):
    """Write the files of the given databases into ``stage`` (under files/). Returns the manifest's "files" entry:
    {count, bytes, apps: {app: count}, items: [{file, bytes, sha256}]}. A database whose files cannot be read is named
    in the log and left out; the backup itself does not fail for it."""
    from app.engine import Cancelled
    items, apps, per = [], {}, {}
    for db, app, files in plan(conn, databases, log):
        if cancel is not None and cancel.is_set():
            raise Cancelled("Cancelled")
        try:
            done = _read(conn, db, files, stage, cancel)
        except FilesError as e:
            if cancel is not None and cancel.is_set():
                raise Cancelled("Cancelled")
            log("  warning: the files of %s (%s) could not all be written out: %s" % (app, db, e))
            done = e.args[1] if len(e.args) > 1 else []
        items += done
        apps[app] = apps.get(app, 0) + len(done)
        got, of = per.get((db, app), (0, 0))
        per[(db, app)] = (got + len(done), of + len(files))
    for (db, app), (got, of) in per.items():
        log("  files: %d of %s (%s)%s" % (got, app, db, ", %d left out (changed while they were read)" % (of - got)
                                          if of > got else ""))
    return {"root": ROOT, "count": len(items), "bytes": sum(i["bytes"] for i in items), "apps": apps, "items": items}


def _read(conn, db, files, stage, cancel):
    """Read every file of one database in one transaction of one client session, streamed: a script of SELECTs, each
    row tagged with its file and piece so a row that went missing (a file deleted meanwhile) shows."""
    fd, script = tempfile.mkstemp(prefix="iobackup-files-", suffix=".sql", dir=stage)
    done = []
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;\n"
                    "START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;\n")
            for i, fl in enumerate(files):
                for c, sql in enumerate(fl["reads"]):
                    f.write(sql.replace("SELECT HEX(", "SELECT '%d:%d', HEX(" % (i, c), 1) + ";\n")
            f.write("COMMIT;\n")
        cmd = conn._base(conn.client) + ["--batch", "--skip-column-names", "--quick", "--connect-timeout=10",
                                         "--max-allowed-packet=1G", "--default-character-set=utf8mb4"]
        errf = tempfile.TemporaryFile()
        with open(script, "rb") as stdin:
            proc = subprocess.Popen(cmd, stdin=stdin, stdout=subprocess.PIPE, stderr=errf)
        st = {"i": None, "c": 0, "out": None, "sha": None, "size": 0}

        def finish():
            i = st["i"]
            if i is None:
                return
            fl = files[i]
            st["out"].close()
            full = os.path.join(stage, fl["path"])
            if st["c"] == len(fl["reads"]) and st["size"] == fl["size"]:
                done.append({"file": fl["path"], "bytes": st["size"], "sha256": st["sha"].hexdigest()})
            else:
                os.unlink(full)
            st.update(i=None, c=0, out=None, sha=None, size=0)

        def start(i):
            full = os.path.join(stage, files[i]["path"])
            os.makedirs(os.path.dirname(full), exist_ok=True)
            st.update(i=i, c=0, out=open(full, "wb"), sha=hashlib.sha256(), size=0)

        try:
            n = 0
            for line in proc.stdout:
                n += 1
                if cancel is not None and n % 50 == 0 and cancel.is_set():
                    raise FilesError("cancelled", done)
                tag, _, hexed = line.rstrip(b"\n").partition(b"\t")
                try:
                    i, c = (int(x) for x in tag.split(b":"))
                except ValueError:
                    continue
                if hexed == b"NULL":
                    continue
                if st["i"] != i:
                    finish()
                    start(i)
                if c != st["c"]:  # a piece missing: this file is not whole
                    st["c"] = -1
                    continue
                data = bytes.fromhex(hexed.decode("ascii"))
                st["out"].write(data)
                st["sha"].update(data)
                st["size"] += len(data)
                st["c"] += 1
            finish()
            # the files with no bytes at all (nothing to SELECT)
            for i, fl in enumerate(files):
                if not fl["reads"] and fl["size"] == 0:
                    start(i)
                    finish()
        finally:
            if st["out"] is not None:
                st["out"].close()
                os.unlink(os.path.join(stage, files[st["i"]]["path"]))
            if proc.poll() is None:
                proc.kill()
            proc.stdout.close()
            rc = proc.wait()
        if rc != 0:
            errf.seek(0)
            raise FilesError(errf.read().decode("utf-8", "replace").strip() or "the client stopped (exit %d)" % rc, done)
        return done
    finally:
        try:
            os.unlink(script)
        except OSError:
            pass
