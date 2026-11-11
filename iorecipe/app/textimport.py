"""A recipe out of plain text: what somebody pasted from a message, a document or a web page, or what was read off a
photo of a recipe (app/ocr.py). Nothing clever: the title is the first line, "Ingredients" and "Instructions" (and
what other languages and cookbooks call them) start their parts, "Serves 4" and "Prep time: 15 min" are picked out,
and where the text has no such headings the lines that begin with an amount are the ingredients and the rest the
steps. The result is a draft: the web app opens it in the recipe form, to be read over before it is saved.
"""
import re

from iosuite_shared.errors import Invalid

MAX_TEXT = 200_000

HEADS = {
    "ingredients": r"ingredients?|what you(?:'ll| will)? need|you(?:'ll| will) need|shopping list|zutaten|ingr[ée]dients?|ingredi[ëe]nten|ingredientes|ingredienti|benodigdheden",
    "steps": r"instructions?|directions?|method|steps?|preparation|how to make(?: it)?|procedure|zubereitung|pr[ée]paration|bereiding(?:swijze)?|werkwijze|bereidingswijze|preparaci[óo]n|elaboraci[óo]n|preparazione|procedimento",
    "notes": r"notes?|tips?|cook'?s notes?|recipe notes?|notities|opmerkingen|remarques|astuces?|conseils?|hinweise|tipps?|notas",
}
_HEAD = {k: re.compile(rf"^(?:{v})\s*:?$", re.I) for k, v in HEADS.items()}
_BULLET = re.compile(r"^\s*(?:[-*•·‣▪▢□☐◦–—]+|\[\s?\]|\(\s?\))\s*")
_NUMBER = re.compile(r"^\s*(?:step\s*)?(\d{1,2})\s*[.):]\s*(?=\S)|^\s*step\s*(\d{1,2})\s*[:.]?\s*$", re.I)
_AMOUNT = re.compile(r"^(?:\d|[¼½¾⅓⅔⅛⅜⅝⅞]|an?\s|one\s|two\s|three\s|half\s|a\s(?:pinch|handful|few|dash|splash)|pinch|handful|salt\b|pepper\b|juice of|zest of)", re.I)
_SERVES = re.compile(r"^(?:serves|servings?|yields?|makes|portions?|for|voor|pour|f[üu]r|personen|aantal personen)\s*:?\s*(.+)$", re.I)
_TIME = re.compile(r"^(prep(?:aration)?|cook(?:ing)?|bak(?:e|ing)|total|ready in|active|voorbereiding(?:stijd)?|bereidingstijd|baktijd|kooktijd|totaal|pr[ée]paration|cuisson|temps total|zubereitungszeit|kochzeit|backzeit|gesamtzeit)(?:\s*time|\s*tijd)?\s*:?\s+(.+)$", re.I)
_PREP = re.compile(r"^(?:prep|voorbereiding|pr[ée]paration|zubereitungszeit|active)", re.I)
_TOTAL = re.compile(r"^(?:total|ready in|totaal|temps total|gesamtzeit)", re.I)


def duration(text: str) -> int | None:
    """Minutes out of '1 h 30', '1 hour 15 minutes', '45 min', '1:30', '1½ hours', '90'."""
    s = (text or "").lower().replace("½", ".5").replace("¼", ".25").replace("¾", ".75").replace(",", ".")
    m = re.match(r"^\s*(\d+):(\d{2})\b", s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    total, found = 0.0, False
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(days?|d\b|hours?|hrs?|h\b|uur|uren|u\b|heures?|stunden?|std|minutes?|mins?|m\b|minuten|min)", s):
        found = True
        n = float(num)
        total += n * 1440 if unit.startswith("d") else n * 60 if unit[0] in "hus" else n
    m = re.search(r"\b(?:h|hrs?|hours?|uur|u)\s*(\d{1,2})\s*$", s)  # "1 h 30"
    if found and m:
        total += int(m.group(1))
    if not found:
        m = re.match(r"^\s*(\d+)\s*$", s)
        if m:
            total, found = float(m.group(1)), True
    return int(round(total)) or None if found else None


def _clean(line: str) -> str:
    return re.sub(r"\s+", " ", _BULLET.sub("", line.replace("\xa0", " "))).strip()


def _steps(lines: list[str]) -> list[str]:
    """The steps out of their lines ('' is an empty line). Numbered: a line without a number goes on with the step
    before it. Not numbered: a paragraph is a step when the text has empty lines, else a line is."""
    numbered = sum(1 for ln in lines if _NUMBER.match(ln)) >= 2
    paragraphs = "" in lines[:-1] if not numbered else False
    out: list[str] = []
    fresh = True
    for raw in lines:
        if not raw:
            fresh = True
            continue
        m = _NUMBER.match(raw)
        text = _clean(raw[m.end():] if m else raw)
        if m and not text:
            fresh = True
            continue
        heading = text.endswith(":") and len(text) < 60
        if numbered:
            if m or heading or not out or out[-1].endswith(":"):
                out.append(text)
            else:
                out[-1] += " " + text
        elif paragraphs:
            if fresh or heading or not out or out[-1].endswith(":"):
                out.append(text)
            else:
                out[-1] += " " + text
        else:
            out.append(text)
        fresh = heading
    return [s for s in out if s]


def _ingredients(lines: list[str]) -> list[str]:
    out = []
    for raw in lines:
        t = _clean(raw)
        if not t:
            continue
        if re.match(r"^for (?:the )?[\w' -]{2,40}$", t, re.I) and not t.endswith(":"):
            t += ":"  # "For the icing"
        out.append(t)
    return out


def parse(text: str) -> dict:
    """The fields POST /api/recipes takes, as far as the text gives them. Invalid when there is nothing to read."""
    if not isinstance(text, str) or not text.strip():
        raise Invalid("Some text, please: paste the recipe")
    if len(text) > MAX_TEXT:
        raise Invalid("That is too much text for one recipe")
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    parts: dict[str, list[str]] = {"top": [], "ingredients": [], "steps": [], "notes": []}
    facts: dict = {}
    where = "top"
    for raw in lines:
        t = _clean(raw)
        head = next((k for k, rx in _HEAD.items() if t and rx.match(t.strip("#*_ ").strip())), None)
        if head:
            where = head
            continue
        m = _TIME.match(t)
        if m and where != "steps":
            mins = duration(m.group(2))
            if mins:
                key = "prepMinutes" if _PREP.match(m.group(1)) else "totalMinutes" if _TOTAL.match(m.group(1)) else "cookMinutes"
                facts.setdefault(key, mins)
                continue
        m = _SERVES.match(t)
        if m and where != "steps" and len(t) < 60 and re.search(r"\d", m.group(1)) and "servings" not in facts:
            facts["servings"] = re.sub(r"\s*(?:servings?|portions?|personen|personnes)\s*$", "", m.group(1), flags=re.I).strip()[:64] or m.group(1)[:64]
            continue
        parts[where].append(raw.strip() if where == "steps" else t)
    top = [t for t in parts["top"] if t]
    title = top[0].strip("#*_ ").strip() if top else ""
    rest = top[1:]
    ingredients, steps = _ingredients(parts["ingredients"]), _steps(parts["steps"])
    if not ingredients and not steps:
        # no headings: the first run of lines that begin with an amount are the ingredients, what follows the steps
        start = next((i for i, t in enumerate(rest) if _AMOUNT.match(t)), None)
        if start is not None:
            end = start
            while end < len(rest) and (_AMOUNT.match(rest[end]) or (rest[end].endswith(":") and len(rest[end]) < 60) or len(rest[end]) < 40):
                end += 1
            ingredients, steps = _ingredients(rest[start:end]), _steps(rest[end:])
            rest = rest[:start]
        else:
            steps, rest = _steps(rest), []
    elif not ingredients:
        start = next((i for i, t in enumerate(rest) if _AMOUNT.match(t)), None)
        if start is not None:
            ingredients, rest = _ingredients(rest[start:]), rest[:start]
    if not title and not ingredients and not steps:
        raise Invalid("No recipe could be made out in that text")
    notes = "\n".join(t for t in (_clean(x) for x in parts["notes"]) if t)
    return {"title": title[:255] or "Recipe", "description": " ".join(rest)[:4000] or None, "ingredients": ingredients, "steps": steps,
            "notes": notes[:20000] or None, "tags": [], **facts}
