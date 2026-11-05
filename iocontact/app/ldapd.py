"""A read-only LDAP v3 directory (RFC 4511) of the contacts, for mail clients that look addresses up over LDAP:
Outlook, Thunderbird, Apple Mail / Contacts (LDAP server accounts), Evolution, Claws, mutt (via a query tool),
printers and phones with an LDAP phone book.

Clients bind with an ioContacts account: the bind DN "cn=<name>,ou=users,dc=iocontacts" (or just the name or the
email address) and the account's password or an app password. Anonymous searches see nothing. Each account sees the
contacts of the address books it can see, as inetOrgPerson entries (with Thunderbird's mozillaAbPersonAlpha
attributes) under ou=contacts,dc=iocontacts.

Only bind, search, unbind and abandon are served; every change is refused (unwillingToPerform) and StartTLS is
not offered: run it on the LAN, or behind a TLS proxy (stunnel, HAProxy, nginx stream) for ldaps://.
"""
import asyncio
import logging
import re

from app import config, model, users
from app.fold import fold

log = logging.getLogger("iocontacts.ldap")

# ------------------------------------------------------------------ BER


def _len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def tlv(tag: int, content: bytes) -> bytes:
    return bytes([tag]) + _len(len(content)) + content


def ber_int(v: int, tag: int = 0x02) -> bytes:
    n = max(1, (v.bit_length() + 8) // 8)
    return tlv(tag, v.to_bytes(n, "big", signed=True))


def ber_str(s, tag: int = 0x04) -> bytes:
    return tlv(tag, s if isinstance(s, bytes) else str(s).encode())


def seq(*items: bytes, tag: int = 0x30) -> bytes:
    return tlv(tag, b"".join(items))


def read_tlv(buf: bytes, i: int = 0):
    """(tag, content, next index) or None when the buffer holds less than one element."""
    if len(buf) < i + 2:
        return None
    tag = buf[i]
    ln = buf[i + 1]
    j = i + 2
    if ln & 0x80:
        k = ln & 0x7F
        if len(buf) < j + k:
            return None
        ln = int.from_bytes(buf[j:j + k], "big")
        j += k
    if len(buf) < j + ln:
        return None
    return tag, buf[j:j + ln], j + ln


def children(content: bytes) -> list:
    out, i = [], 0
    while i < len(content):
        t = read_tlv(content, i)
        if not t:
            break
        out.append((t[0], t[1]))
        i = t[2]
    return out


def as_int(b: bytes) -> int:
    return int.from_bytes(b, "big", signed=True) if b else 0


# ------------------------------------------------------------------ results

SUCCESS, OPERATIONS_ERROR, PROTOCOL_ERROR, SIZE_LIMIT, NO_SUCH_OBJECT, INVALID_CREDENTIALS = 0, 1, 2, 4, 32, 49
INSUFFICIENT_ACCESS, UNWILLING = 50, 53


def result(msgid: int, op_tag: int, code: int, msg: str = "", matched: str = "") -> bytes:
    return seq(ber_int(msgid), seq(ber_int(code, 0x0A), ber_str(matched), ber_str(msg), tag=op_tag))


# ------------------------------------------------------------------ the directory

def norm_dn(dn: str) -> str:
    return ",".join(p.strip().lower().replace(" =", "=").replace("= ", "=") for p in (dn or "").split(",") if p.strip())


def _esc_dn(v: str) -> str:
    return re.sub(r'([,+"\\<>;=#])', r"\\\1", v)


def base() -> str:
    return config.LDAP_BASE


def contact_entry(c: dict) -> tuple[str, dict]:
    nm = c.get("name") or {}
    a: dict[str, list] = {
        "objectClass": ["top", "person", "organizationalPerson", "inetOrgPerson", "mozillaAbPersonAlpha"],
        "uid": [c["uid"]], "cn": [c["fn"]], "displayName": [c["fn"]],
        "sn": [nm.get("family") or c["fn"]],
    }

    def put(k, v):
        if v:
            a.setdefault(k, []).append(str(v))
    put("givenName", nm.get("given"))
    put("initials", (nm.get("additional") or "")[:1])
    put("personalTitle", nm.get("prefix"))
    put("generationQualifier", nm.get("suffix"))
    put("mozillaNickName", c.get("nickname"))
    put("nickname", c.get("nickname"))
    put("o", c.get("org"))
    put("company", c.get("org"))
    put("ou", c.get("department"))
    put("department", c.get("department"))
    put("title", c.get("title"))
    put("description", (c.get("notes") or "")[:1024])
    for i, e in enumerate(c.get("emails") or []):
        put("mail", e["value"])
        if i == 1:
            put("mozillaSecondEmail", e["value"])
    for t in c.get("phones") or []:
        lab = (t.get("label") or "").lower()
        if lab in ("mobile", "iphone", "cell"):
            put("mobile", t["value"])
        elif lab == "home":
            put("homePhone", t["value"])
        elif "fax" in lab:
            put("facsimileTelephoneNumber", t["value"])
        elif lab == "pager":
            put("pager", t["value"])
        else:
            put("telephoneNumber", t["value"])
    for ad in c.get("addresses") or []:
        lab = (ad.get("label") or "").lower()
        lines = "$".join(x for x in (ad.get("street"), " ".join(x for x in (ad.get("postcode"), ad.get("city")) if x),
                                     ad.get("region"), ad.get("country")) if x)
        if lab == "home":
            put("homePostalAddress", lines)
            put("mozillaHomeStreet", ad.get("street"))
            put("mozillaHomeLocalityName", ad.get("city"))
            put("mozillaHomeState", ad.get("region"))
            put("mozillaHomePostalCode", ad.get("postcode"))
            put("mozillaHomeCountryName", ad.get("country"))
        if lab != "home" or "postalAddress" not in a:
            put("postalAddress", lines)
            put("street", ad.get("street"))
            put("l", ad.get("city"))
            put("st", ad.get("region"))
            put("postalCode", ad.get("postcode"))
            put("co", ad.get("country"))
            if ad.get("country") and len(ad["country"]) == 2:
                put("c", ad["country"].upper())
    for u in c.get("urls") or []:
        put("labeledURI", u["value"])
        put("mozillaWorkUrl" if (u.get("label") or "") == "work" else "mozillaHomeUrl", u["value"])
    for s in c.get("social") or []:
        from app.vcard import social_url
        put("labeledURI", f"{social_url(s['service'], s['value'])} {s['service']}")
    b = c.get("birthday")
    if b:
        put("birthyear", b.get("year"))
        put("birthmonth", f"{b['month']:02d}")
        put("birthday", f"{b['day']:02d}")
    if c.get("photoData"):
        a["jpegPhoto"] = [c["photoData"]["data"]]
    return f"uid={_esc_dn(c['uid'])},ou=contacts,{base()}", a


def directory(user: dict, want_photo: bool) -> list[tuple[str, dict]]:
    root = [(base(), {"objectClass": ["top", "dcObject", "organization"], "o": ["ioContacts"],
                      "dc": [base().split(",")[0].split("=")[-1]]}),
            (f"ou=contacts,{base()}", {"objectClass": ["top", "organizationalUnit"], "ou": ["contacts"]}),
            (f"ou=users,{base()}", {"objectClass": ["top", "organizationalUnit"], "ou": ["users"]})]
    ids = [b["id"] for b in model.books_for(user)]
    rows, _ = model.search(ids, limit=100000)
    return root + [contact_entry(model.full(r["id"], with_photo=want_photo)) for r in rows if r["kind"] != "group"]


def _attr(entry: dict, name: str) -> list:
    n = name.lower()
    for k, v in entry.items():
        if k.lower() == n:
            return v
    return []


def _s(v) -> str:
    return v.decode("utf-8", "replace") if isinstance(v, bytes) else str(v)


def _fold(s: str) -> str:
    return re.sub(r"\s+", " ", fold(s)).strip()


def match(f, entry: dict) -> bool:
    tag, content = f
    if tag == 0xA0:
        return all(match(x, entry) for x in children(content))
    if tag == 0xA1:
        return any(match(x, entry) for x in children(content))
    if tag == 0xA2:
        inner = children(content)
        return not match(inner[0], entry) if inner else True
    if tag == 0x87:
        name = content.decode("utf-8", "replace")
        return name.lower() == "objectclass" or bool(_attr(entry, name))
    if tag in (0xA3, 0xA5, 0xA6, 0xA8):
        parts = children(content)
        name, val = parts[0][1].decode("utf-8", "replace"), _fold(parts[1][1].decode("utf-8", "replace"))
        vals = [_fold(_s(v)) for v in _attr(entry, name) if not isinstance(v, bytes) or name.lower() != "jpegphoto"]
        if name.lower() in ("telephonenumber", "mobile", "homephone"):
            vals = [re.sub(r"\D", "", v) for v in vals]
            val = re.sub(r"\D", "", val)
        if tag == 0xA3:
            return val in vals
        if tag == 0xA8:
            return any(val in v for v in vals)
        if tag == 0xA5:
            return any(v >= val for v in vals)
        return any(v <= val for v in vals)
    if tag == 0xA4:
        parts = children(content)
        name = parts[0][1].decode("utf-8", "replace")
        subs = children(parts[1][1])
        vals = [_fold(_s(v)) for v in _attr(entry, name)]
        for v in vals:
            pos, ok = 0, True
            for st, sv in subs:
                s = _fold(sv.decode("utf-8", "replace"))
                if st == 0x80:
                    if not v.startswith(s):
                        ok = False
                        break
                    pos = len(s)
                elif st == 0x81:
                    k = v.find(s, pos)
                    if k < 0:
                        ok = False
                        break
                    pos = k + len(s)
                elif st == 0x82:
                    if not v[pos:].endswith(s):
                        ok = False
                        break
            if ok:
                return True
        return False
    if tag == 0xA9:  # extensible match: treat as equality on the attribute
        parts = {t: c for t, c in children(content)}
        name = (parts.get(0x82) or b"").decode()
        val = _fold((parts.get(0x83) or b"").decode())
        return any(_fold(_s(v)) == val for v in (_attr(entry, name) if name else sum(entry.values(), [])))
    return False


def in_scope(dn: str, base_dn: str, scope: int) -> bool:
    d, b = norm_dn(dn), norm_dn(base_dn)
    if scope == 0:
        return d == b
    if b and d != b and not d.endswith("," + b):
        return False
    if d == b:
        return scope == 2
    rest = d[: len(d) - len(b)].rstrip(",") if b else d
    return scope == 2 or rest.count(",") == 0


def entry_msg(msgid: int, dn: str, attrs: dict, wanted: list[str], types_only: bool) -> bytes:
    names = [w.lower() for w in wanted]
    all_user = not names or "*" in names
    if names == ["1.1"]:
        sel = {}
    else:
        sel = {k: v for k, v in attrs.items() if (all_user and k.lower() != "jpegphoto") or k.lower() in names
               or ("+" in names and False)}
        if all_user and "jpegphoto" in names:
            sel["jpegPhoto"] = attrs.get("jpegPhoto", [])
    al = b"".join(seq(ber_str(k), tlv(0x31, b"" if types_only else b"".join(ber_str(x if isinstance(x, bytes) else str(x)) for x in v)))
                  for k, v in sel.items() if v)
    return seq(ber_int(msgid), seq(ber_str(dn), seq(al), tag=0x64))


ROOT_DSE = {"objectClass": ["top"], "namingContexts": [], "supportedLDAPVersion": ["3"], "vendorName": ["iothing"],
            "vendorVersion": ["ioContacts"], "supportedExtension": [], "supportedControl": []}


# ------------------------------------------------------------------ the server

class Session:
    def __init__(self, reader, writer):
        self.r, self.w = reader, writer
        self.user = None
        self.peer = writer.get_extra_info("peername")

    async def run(self):
        buf = b""
        try:
            while True:
                chunk = await self.r.read(65536)
                if not chunk:
                    break
                buf += chunk
                if len(buf) > 1_000_000:
                    break
                while True:
                    t = read_tlv(buf)
                    if not t:
                        break
                    buf = buf[t[2]:]
                    if t[0] != 0x30:
                        return
                    if not await self.handle(t[1]):
                        return
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        except Exception:  # noqa: BLE001
            log.exception("LDAP session failed")
        finally:
            try:
                self.w.close()
            except Exception:  # noqa: BLE001
                pass

    async def send(self, data: bytes):
        self.w.write(data)
        await self.w.drain()

    async def handle(self, content: bytes) -> bool:
        parts = children(content)
        if len(parts) < 2:
            return False
        msgid = as_int(parts[0][1])
        op, body = parts[1]
        if op == 0x60:   # bind
            await self.bind(msgid, body)
        elif op == 0x42:  # unbind
            return False
        elif op == 0x63:  # search
            await self.search(msgid, body)
        elif op == 0x50:  # abandon
            pass
        elif op == 0x77:  # extended (StartTLS, whoami...)
            await self.send(seq(ber_int(msgid), seq(ber_int(PROTOCOL_ERROR, 0x0A), ber_str(""), ber_str("Not supported"), tag=0x78)))
        elif op in (0x66, 0x68, 0x4A, 0x6C, 0x6E):  # modify, add, delete, modDN, compare
            await self.send(result(msgid, op + 1 if op != 0x4A else 0x6B, UNWILLING, "ioContacts' LDAP directory is read-only"))
        else:
            await self.send(result(msgid, 0x65, PROTOCOL_ERROR, "Unsupported operation"))
        return True

    async def bind(self, msgid: int, body: bytes):
        parts = children(body)
        name = parts[1][1].decode("utf-8", "replace") if len(parts) > 1 else ""
        auth_tag, auth = parts[2] if len(parts) > 2 else (0x80, b"")
        if auth_tag != 0x80:
            await self.send(result(msgid, 0x61, 7, "Simple bind only"))  # authMethodNotSupported
            return
        pw = auth.decode("utf-8", "replace")
        if not name and not pw:
            self.user = None
            await self.send(result(msgid, 0x61, SUCCESS))
            return
        ident = name
        m = re.match(r"^\s*(?:cn|uid|mail)\s*=\s*([^,]+)", name, re.I)
        if m:
            ident = m.group(1).strip()
        u = await asyncio.get_running_loop().run_in_executor(None, users.authenticate, ident, pw)
        if not u or u["role"] == "none":  # no access to ioContacts: no directory either
            log.info("LDAP bind refused for %r from %s", name, self.peer)
            await self.send(result(msgid, 0x61, INVALID_CREDENTIALS, "Wrong name or password"))
            return
        self.user = u
        await self.send(result(msgid, 0x61, SUCCESS))

    async def search(self, msgid: int, body: bytes):
        parts = children(body)
        base_dn = parts[0][1].decode("utf-8", "replace")
        scope = as_int(parts[1][1])
        size_limit = as_int(parts[3][1])
        types_only = parts[5][1] != b"\x00"
        flt = parts[6]
        wanted = [c.decode("utf-8", "replace") for _t, c in children(parts[7][1])] if len(parts) > 7 else []
        if base_dn == "" and scope == 0:  # root DSE
            dse = dict(ROOT_DSE, namingContexts=[base()])
            await self.send(entry_msg(msgid, "", dse, wanted or ["*"], types_only))
            await self.send(result(msgid, 0x65, SUCCESS))
            return
        if not self.user:
            await self.send(result(msgid, 0x65, INSUFFICIENT_ACCESS, "Bind with your ioContacts account first"))
            return
        bd, root = norm_dn(base_dn), norm_dn(base())
        if base_dn and not (bd == root or bd.endswith("," + root) or root.endswith("," + bd)):
            await self.send(result(msgid, 0x65, NO_SUCH_OBJECT, "", base()))
            return
        want_photo = any(w.lower() == "jpegphoto" for w in wanted)
        entries = await asyncio.get_running_loop().run_in_executor(None, directory, self.user, want_photo)
        sent = 0
        for dn, attrs in entries:
            if not in_scope(dn, base_dn, scope) or not match(flt, attrs):
                continue
            if size_limit and sent >= size_limit:
                await self.send(result(msgid, 0x65, SIZE_LIMIT))
                return
            await self.send(entry_msg(msgid, dn, attrs, wanted, types_only))
            sent += 1
        if base_dn and scope == 0 and not sent and not any(norm_dn(dn) == norm_dn(base_dn) for dn, _ in entries):
            await self.send(result(msgid, 0x65, NO_SUCH_OBJECT, "", base()))
            return
        await self.send(result(msgid, 0x65, SUCCESS))


async def serve(host: str, port: int):
    async def handler(r, w):
        await Session(r, w).run()
    server = await asyncio.start_server(handler, host, port)
    log.info("LDAP directory on %s:%s (base %s)", host, port, base())
    return server
