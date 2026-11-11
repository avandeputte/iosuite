"""Import from the web: fetch a page somebody gave the address of and read the recipe on it.

Most recipe sites describe their recipe for search engines as schema.org Recipe data, as JSON-LD in a <script> or as
microdata (itemprop) on the page's own elements; that is what is read here, never the page's layout. The page is
fetched with iosuite-shared's outbound opener: only addresses on the internet, each redirect checked like the first.
"""
import gzip
import html
import json
import re
import urllib.error
import io
import urllib.parse
import urllib.request
import zlib
from html.parser import HTMLParser

from iosuite_shared import outbound
from iosuite_shared.errors import Invalid

from app import config

# a browser's name: many recipe sites answer anything else with an error page
AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
TIMEOUT = 15


def fetch(url: str, limit: int, accept: str = "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5", allowed=outbound.public) -> tuple[bytes, str, str]:
    """(body, content type, final address) of an http(s) address, at most `limit` bytes. Invalid when it cannot be had."""
    outbound.check(url, allowed)
    req = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": accept, "Accept-Language": "en,*;q=0.5", "Accept-Encoding": "gzip, deflate"})
    try:
        with outbound.opener(allowed).open(req, timeout=TIMEOUT) as r:
            raw = r.read(limit + 1)
            enc = (r.headers.get("Content-Encoding") or "").lower()
            ctype = r.headers.get("Content-Type") or ""
            final = r.geturl()
    except urllib.error.HTTPError as e:
        raise Invalid(f"The site answered {e.code} for that address") from e
    except Invalid:
        raise
    except (OSError, ValueError) as e:  # URLError, timeouts, TLS
        raise Invalid(f"That address could not be fetched: {getattr(e, 'reason', e)}") from e
    if len(raw) > limit:
        raise Invalid("That page is too large")
    try:
        if "gzip" in enc:
            raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read(limit + 1)
        elif "deflate" in enc:
            raw = zlib.decompressobj().decompress(raw, limit + 1)
    except (OSError, zlib.error, EOFError) as e:
        raise Invalid("That page could not be read") from e
    if len(raw) > limit:
        raise Invalid("That page is too large")
    return raw, ctype, final


def _decode(raw: bytes, ctype: str) -> str:
    m = re.search(r"charset=([\w-]+)", ctype, re.I) or re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", raw[:4096], re.I)
    name = (m.group(1).decode() if m and isinstance(m.group(1), bytes) else m.group(1)) if m else "utf-8"
    try:
        return raw.decode(name, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


# ---- reading the page

BLOCKS = {"p", "br", "li", "div", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}
VOID = {"meta", "link", "img", "br", "hr", "input", "source", "area", "base", "col", "embed", "track", "wbr"}


class _Page(HTMLParser):
    """Collects the JSON-LD scripts, the <meta> and <title> a page has, and its microdata Recipe (itemprop values)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ld: list[str] = []
        self.meta: dict[str, str] = {}
        self.title = ""
        self.props: dict[str, list[str]] = {}
        self._script = None      # collecting a JSON-LD script
        self._title = False
        self._stack: list = []   # open elements: [tag, itemprop or None, text parts]
        self._recipe = None      # depth of the element with itemtype Recipe

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "script":
            self._script = [] if "ld+json" in a.get("type", "").lower() else None
            return
        if tag == "title" and not self.title:
            self._title = True
        if tag == "meta":
            k = a.get("property") or a.get("name")
            if k and a.get("content") and k.lower() not in self.meta:
                self.meta[k.lower()] = a["content"]
        if "schema.org/recipe" in a.get("itemtype", "").lower() and self._recipe is None:
            self._recipe = len(self._stack)
        prop = a.get("itemprop") if self._recipe is not None else None
        if prop:
            v = a.get("content") or (a.get("src") if tag == "img" else None) or (a.get("datetime") if tag == "time" else None) \
                or (a.get("href") if tag in ("link", "a") and prop in ("image", "url") else None)
            if v:
                for p in prop.split():
                    self.props.setdefault(p, []).append(v)
                prop = None
        if tag in VOID:
            if tag == "br":
                self._text("\n")
            return
        self._stack.append([tag, prop, []])

    def handle_endtag(self, tag):
        if tag == "script":
            if self._script is not None:
                self.ld.append("".join(self._script))
            self._script = None
            return
        if tag == "title":
            self._title = False
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                for el in reversed(self._stack[i:]):
                    self._close(el)
                del self._stack[i:]
                if self._recipe is not None and i <= self._recipe:
                    self._recipe = None
                break

    def _close(self, el):
        tag, prop, parts = el
        text = "".join(parts)
        if prop:
            v = "\n".join(x for x in (re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in text.split("\n")) if x)
            if v:
                for p in prop.split():
                    self.props.setdefault(p, []).append(v)
        if tag in BLOCKS:
            text = "\n" + text + "\n"
        # the text belongs to the enclosing elements too
        idx = next((i for i, x in enumerate(self._stack) if x is el), None)
        if idx:
            self._stack[idx - 1][2].append(text)

    def finish(self):
        """The elements the page never closed."""
        for el in reversed(self._stack):
            self._close(el)
        self._stack = []

    def _text(self, data):
        if self._stack:
            self._stack[-1][2].append(data)

    def handle_data(self, data):
        if self._script is not None:
            self._script.append(data)
        elif self._title:
            self.title += data
        else:
            self._text(data)


def _types(o) -> list[str]:
    t = o.get("@type") if isinstance(o, dict) else None
    return [str(x).rsplit("/", 1)[-1] for x in (t if isinstance(t, list) else [t]) if x]


def _find_recipe(o, depth: int = 0):
    """The first schema.org Recipe in a JSON-LD value (an object, a list, an @graph, or nested in a page's mainEntity)."""
    if depth > 6:
        return None
    if isinstance(o, list):
        for x in o:
            r = _find_recipe(x, depth + 1)
            if r:
                return r
    elif isinstance(o, dict):
        if "Recipe" in _types(o):
            return o
        for k in ("@graph", "mainEntity", "mainEntityOfPage", "hasPart", "itemListElement", "item"):
            if k in o:
                r = _find_recipe(o[k], depth + 1)
                if r:
                    return r
    return None


def _plain(v) -> str:
    """Text out of a value that may hold HTML and entities (sites put both in their recipe data)."""
    if v is None:
        return ""
    if isinstance(v, dict):
        v = v.get("text") or v.get("name") or v.get("@value") or ""
    if isinstance(v, list):
        v = " ".join(_plain(x) for x in v)
    s = html.unescape(str(v))
    s = re.sub(r"(?i)<\s*(br|/p|/li|/div)\s*/?>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    return "\n".join(x for x in (re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in s.split("\n")) if x)


def _one_line(v) -> str:
    return re.sub(r"\s+", " ", _plain(v)).strip()


def minutes(v) -> int | None:
    """An ISO 8601 duration (PT1H30M, P1DT2H) or a number of minutes, as minutes."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return int(v) or None
    s = str(v).strip()
    m = re.fullmatch(r"P(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?", s, re.I)
    if m and any(m.groups()):
        d, h, mi, sec = (float(x) if x else 0 for x in m.groups())
        return int(round(d * 1440 + h * 60 + mi + sec / 60)) or None
    m = re.fullmatch(r"(\d+)\s*(?:m|min|mins|minutes)?", s, re.I)
    return int(m.group(1)) or None if m else None


def _image(v, base: str) -> str | None:
    """The address of the picture: a string, an ImageObject, or a list of either (the first, usually the largest)."""
    if isinstance(v, list):
        for x in v:
            u = _image(x, base)
            if u:
                return u
        return None
    if isinstance(v, dict):
        v = v.get("url") or v.get("contentUrl") or v.get("@id")
        if isinstance(v, (list, dict)):
            return _image(v, base)
    if not v or not isinstance(v, str):
        return None
    u = urllib.parse.urljoin(base, html.unescape(v.strip()))
    return u if u.lower().startswith(("http://", "https://")) else None


def _steps(v) -> list[str]:
    """recipeInstructions: one text, a list of texts, HowToSteps, or HowToSections of them (each a heading and its steps)."""
    out: list[str] = []
    if v is None:
        return out
    if isinstance(v, str):
        return [x for x in _plain(v).split("\n") if x]
    if isinstance(v, dict):
        v = [v]
    for x in v if isinstance(v, list) else []:
        if isinstance(x, dict) and ("HowToSection" in _types(x) or isinstance(x.get("itemListElement"), list)):
            name = _one_line(x.get("name"))
            if name:
                out.append(name.rstrip(":") + ":")
            out += _steps(x.get("itemListElement"))
        elif isinstance(x, dict):
            t = _plain(x.get("text") or x.get("description") or x.get("name"))
            out += [ln for ln in t.split("\n") if ln]
        else:
            out += [ln for ln in _plain(x).split("\n") if ln]
    return out


def _keywords(*vals) -> list[str]:
    out: list[str] = []
    for v in vals:
        for x in (v if isinstance(v, list) else [v]):
            for t in re.split(r"[,;]", _one_line(x)) if x else []:
                t = t.strip()
                if t and len(t) <= 40 and t.lower() not in [o.lower() for o in out]:
                    out.append(t)
    return out[:12]


def _servings(v) -> str | None:
    if isinstance(v, list):  # ["4", "4 servings"]: the one that says what
        texts = [_one_line(x) for x in v if x not in (None, "")]
        v = next((t for t in texts if not t.isdigit()), texts[0] if texts else None)
    s = _one_line(v) if v not in (None, "") else ""
    return s[:64] or None


def _ingredients(v) -> list[str]:
    if isinstance(v, list):
        return [x for x in (_one_line(i) for i in v) if x]
    return [x for x in _plain(v).split("\n") if x]


def _site(base: str) -> str:
    return re.sub(r"^www\.", "", urllib.parse.urlsplit(base).hostname or "")


def from_jsonld(r: dict, base: str) -> dict:
    author = r.get("author")
    author = author[0] if isinstance(author, list) and author else author
    pub = r.get("publisher")
    return {
        "title": _one_line(r.get("name") or r.get("headline")),
        "description": _plain(r.get("description")) or None,
        "servings": _servings(r.get("recipeYield")),
        "prepMinutes": minutes(r.get("prepTime")), "cookMinutes": minutes(r.get("cookTime")), "totalMinutes": minutes(r.get("totalTime")),
        "ingredients": _ingredients(r.get("recipeIngredient") or r.get("ingredients")),
        "steps": _steps(r.get("recipeInstructions")),
        "tags": _keywords(r.get("recipeCategory"), r.get("recipeCuisine"), r.get("keywords")),
        "sourceName": _one_line(pub.get("name") if isinstance(pub, dict) else None) or _one_line(author.get("name") if isinstance(author, dict) else author) or None,
        "image": _image(r.get("image"), base),
    }


def from_microdata(p: _Page, base: str) -> dict | None:
    g = p.props
    ing = g.get("recipeIngredient") or g.get("ingredients") or []
    if not ing and not g.get("recipeInstructions"):
        return None
    first = lambda k: (g.get(k) or [None])[0]  # noqa: E731
    steps: list[str] = []
    for s in g.get("recipeInstructions") or []:
        steps += [x for x in s.split("\n") if x]
    return {
        "title": _one_line(first("name")), "description": _plain(first("description")) or None,
        "servings": _servings(first("recipeYield")),
        "prepMinutes": minutes(first("prepTime")), "cookMinutes": minutes(first("cookTime")), "totalMinutes": minutes(first("totalTime")),
        "ingredients": [_one_line(x) for x in ing if _one_line(x)], "steps": steps,
        "tags": _keywords(g.get("recipeCategory"), g.get("recipeCuisine"), g.get("keywords")),
        "sourceName": None, "image": _image(first("image"), base),
    }


def parse(text: str, base: str) -> dict:
    """The recipe on a page, as the fields POST /api/recipes takes plus `image` (the picture's address, or None).
    Invalid when the page describes no recipe."""
    p = _Page()
    try:
        p.feed(text)
        p.close()
        p.finish()
    except Exception:  # noqa: BLE001 - a page too broken to walk: what was read so far still counts
        pass
    found = None
    for block in p.ld:
        try:
            found = _find_recipe(json.loads(block.strip().removeprefix("<!--").removesuffix("-->"), strict=False))
        except ValueError:
            continue
        if found:
            break
    out = from_jsonld(found, base) if found else from_microdata(p, base)
    if not out or not (out["ingredients"] or out["steps"]):
        raise Invalid("No recipe was found on that page: it does not describe one the way recipe sites do for search engines. Add it by hand instead.")
    out["title"] = out["title"] or _one_line(p.meta.get("og:title")) or _one_line(p.title) or "Recipe"
    out["title"] = out["title"][:255]
    out["description"] = (out["description"] or _plain(p.meta.get("og:description")) or None)
    if out["description"]:
        out["description"] = out["description"][:4000]
    out["image"] = out["image"] or _image(p.meta.get("og:image"), base)
    out["sourceName"] = (out["sourceName"] or _one_line(p.meta.get("og:site_name")) or _site(base))[:255] or None
    out["sourceUrl"] = base
    return out


def recipe_at(url: str, allowed=outbound.public) -> tuple[dict, bytes | None]:
    """(the recipe's fields, the bytes of its picture or None) from a web address."""
    url = (url or "").strip()
    if url and not re.match(r"[a-z][a-z0-9+.-]*://", url, re.I):
        url = "https://" + url
    raw, ctype, final = fetch(url, config.MAX_PAGE_BYTES, allowed=allowed)
    data = parse(_decode(raw, ctype), final)
    picture = None
    img = data.pop("image", None)
    if img:
        try:
            picture = fetch(img, config.MAX_PHOTO_BYTES, accept="image/*", allowed=allowed)[0]
        except Invalid:
            picture = None  # the recipe without its picture
    return data, picture
