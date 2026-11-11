"""Prompts an MCP client can offer its user ("/summarize_note" and the like): ready-made requests that use the tools."""
from app.mcp.base import server


@server.prompt(title="Summarise a note")
def summarize_note(note_id: str) -> str:
    """A short summary of one note, its picture's text and its files, with the notes related to it."""
    return (f"Read the ioNote note {note_id} with get_note (and read_attachment for any file it has, view_note_image for its "
            "picture if the text alone is unclear). Write a summary of at most five bullet points, then list its action items "
            "and open checklist items (lines starting with - [ ]), if any. Finish with related_notes: name the two or three most "
            "related notes and say in one line how each relates. Do not change anything.")


@server.prompt(title="Weekly review")
def weekly_review(since: str = "", until: str = "") -> str:
    """A digest of the notes of a period (the last seven days by default): themes, decisions, open to-dos."""
    period = f"from {since}" + (f" to {until}" if until else "") if since else "of the last seven days (work out the dates from today)"
    return (f"Make a review of my ioNote notes {period}. Use notes_digest (page through with more calls if needed). Group "
            "what you find by theme or project, list decisions and facts worth keeping, and gather every open checklist item "
            "(- [ ]) with a link to its note. Keep it to one screen. Do not change anything.")


@server.prompt(title="Tidy up unfiled notes")
def tidy_up() -> str:
    """Suggest folders and tags for notes that have none, then apply what the user approves."""
    return ("Help me tidy my ioNote. Call suggest_organization, then show the suggestions as a short table (note, suggested "
            "folder, suggested tags), merging near-duplicate tag names with list_tags in mind. Ask me which to apply, and only "
            "then apply them with organize_notes or update_note. Never create new folders or delete anything without asking.")
