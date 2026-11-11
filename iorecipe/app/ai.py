"""Reading a recipe with AI: where a web page has no recipe data and no list of ingredients ioRecipe can make out, the
page's text is given to Claude (Anthropic's API), which finds the recipe in it. Off until ANTHROPIC_API_KEY is set in
config.env; with it, the text of such a page (public, fetched from the web) goes to Anthropic, and nothing else does.
AI_MODEL picks the model.
"""
import json
import logging

from iosuite_shared.errors import Invalid

from app import config

log = logging.getLogger("iorecipe.ai")
MAX_CHARS = 400_000  # of a page's text: far more than a recipe page has
TIMEOUT = 120.0

SYSTEM = """You are given the text of a web page, as lines. Find the one recipe the page is about and return it.

Copy the recipe as the page gives it, in the page's own language: do not translate, convert units, improve or add anything. \
Leave out what is not the recipe: menus, the story around it, comments, advertisements, other recipes the page links to.

- title: the name of the dish.
- description: one or two sentences from the page about the dish, or "" when it has none.
- servings: what the recipe yields as the page says it ("6 portions", "24 cookies"), or "".
- prepMinutes, cookMinutes, totalMinutes: whole minutes when the page states them, otherwise 0.
- ingredients: one entry per ingredient with its amount, in the page's order. Where the page groups them ("For the sauce"), \
give the group's name as an entry of its own ending in a colon.
- steps: one entry per step, without its number. Only steps the page writes out: when the method is only in a video, return no steps.
- tags: up to five short tags the page itself gives (category, cuisine), or none.
- found: false when the page holds no recipe at all; then leave the rest empty."""

SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "servings": {"type": "string"},
        "prepMinutes": {"type": "integer"},
        "cookMinutes": {"type": "integer"},
        "totalMinutes": {"type": "integer"},
        "ingredients": {"type": "array", "items": {"type": "string"}},
        "steps": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["found", "title", "description", "servings", "prepMinutes", "cookMinutes", "totalMinutes", "ingredients", "steps", "tags"],
    "additionalProperties": False,
}


def available() -> bool:
    """Whether a page can be read with AI here: a key is set."""
    return bool(config.ANTHROPIC_API_KEY)


def _ask(text: str, url: str) -> dict | None:
    """Claude's answer as the schema's object; None when it gave none (a refusal, an answer cut short)."""
    import anthropic  # here: the app starts without a key, and without ever loading this

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=TIMEOUT, max_retries=1)
    try:
        r = client.messages.create(
            model=config.AI_MODEL, max_tokens=16000,
            system=SYSTEM,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": f"The page at {url}:\n\n{text}"}],
        )
    except anthropic.AuthenticationError as e:
        raise Invalid("The AI key in config.env (ANTHROPIC_API_KEY) was not accepted") from e
    except anthropic.PermissionDeniedError as e:
        raise Invalid("The AI key in config.env may not use that model") from e
    except anthropic.NotFoundError as e:
        raise Invalid(f"The AI model in config.env (AI_MODEL={config.AI_MODEL}) does not exist") from e
    except anthropic.RateLimitError as e:
        raise Invalid("The AI service is busy or the key's limit is reached: try again in a minute") from e
    except anthropic.APIStatusError as e:
        raise Invalid(f"The AI service answered {e.status_code}: try again later") from e
    except anthropic.APIConnectionError as e:
        raise Invalid("The AI service could not be reached from this server") from e
    if r.stop_reason != "end_turn":
        log.warning("AI reading of %s ended with %s", url, r.stop_reason)
        return None
    try:
        return json.loads(next(b.text for b in r.content if b.type == "text"))
    except (StopIteration, ValueError):
        return None


def recipe(text: str, url: str) -> dict | None:
    """The recipe in a page's text, as scrape's readers give one (without picture or source), or None when the page
    holds none. Invalid when the service cannot be asked."""
    if not available() or not text.strip():
        return None
    if len(text) > MAX_CHARS:
        raise Invalid("That page is too long to be read")
    d = _ask(text, url)
    if not isinstance(d, dict) or not d.get("found"):
        return None
    lines = lambda v: [x for x in (" ".join(str(i).split()) for i in (v if isinstance(v, list) else [])) if x][:400]  # noqa: E731
    mins = lambda v: v if isinstance(v, int) and 0 < v < 100_000 else None  # noqa: E731
    out = {"title": " ".join(str(d.get("title") or "").split()), "description": str(d.get("description") or "").strip() or None,
           "servings": str(d.get("servings") or "").strip()[:64] or None,
           "prepMinutes": mins(d.get("prepMinutes")), "cookMinutes": mins(d.get("cookMinutes")), "totalMinutes": mins(d.get("totalMinutes")),
           "ingredients": lines(d.get("ingredients")), "steps": lines(d.get("steps")),
           "tags": [t[:40] for t in lines(d.get("tags"))][:5]}
    return out if out["ingredients"] or out["steps"] else None
