"""
Output-side guard: even if an injection slips past the input layer,
this catches the model trying to leak its system prompt or otherwise
echo suspicious instruction-like content back to the user.
"""
import re

_LEAK_MARKERS = [
    r"you are a helpful,? honest assistant",
    r"you must never reveal",
    r"ignore any user text",
]

_LEAK_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _LEAK_MARKERS]


def scrub_output(text: str, system_prompt: str) -> tuple[str, bool]:
    """Returns (possibly-redacted text, was_redacted)."""
    redacted = False

    # Direct substring leak of the actual system prompt
    if system_prompt and system_prompt.lower() in text.lower():
        text = text.replace(system_prompt, "[redacted]")
        redacted = True

    for pattern in _LEAK_PATTERNS:
        if pattern.search(text):
            text = pattern.sub("[redacted]", text)
            redacted = True

    return text, redacted
