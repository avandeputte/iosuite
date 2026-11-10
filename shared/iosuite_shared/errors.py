"""What the suite's own validation raises."""


class Invalid(ValueError):
    """Input that cannot be accepted, with a message for the person who sent it: a 400 carrying that message
    (Auth.install). It is a ValueError, so code that catches ValueError around a parse still catches it; a plain
    ValueError that reaches the handler was raised by something else (int(), a library) and is logged with its
    traceback, because it may be a bug and not the caller's mistake."""
