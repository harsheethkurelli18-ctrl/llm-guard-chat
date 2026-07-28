"""
PromptGuard: a defense-in-depth layer against prompt injection and
jailbreak attempts.

Design notes (for README / interview talking points):
- Layer 1: fast heuristic pattern match (regex over known attack phrasings)
- Layer 2: structural/statistical signals (role-override language,
  delimiter smuggling, excessive imperative density, encoding tricks)
- Layer 3 (optional): a cheap LLM-as-judge classification call for
  borderline cases — only triggered when layers 1-2 are inconclusive,
  to keep latency/cost low on the common case.

This is intentionally NOT a silver bullet — no heuristic system is.
The point of the project is to demonstrate a layered, auditable
approach and to show the tradeoffs, not to claim perfect coverage.
"""
import re
from dataclasses import dataclass, field


@dataclass
class GuardResult:
    risk_score: float                  # 0.0 (safe) - 1.0 (high risk)
    blocked: bool
    reasons: list[str] = field(default_factory=list)


# Known jailbreak / injection phrasings. Grouped by weight so a single
# weak signal doesn't block a legitimate message, but signals stack.
_HIGH_RISK_PATTERNS = [
    r"ignore (all|any|the) (previous|prior|above) instructions",
    r"disregard (all|any|the) (previous|prior|above)",
    r"you are (now|no longer) (?:bound by|restricted by|following)",
    r"forget (everything|all) (you were|i) told",
    r"reveal (your|the) (system prompt|instructions|rules)",
    r"repeat (your|the) (system prompt|instructions) (verbatim|exactly)",
    r"what (are|is) your (system prompt|instructions|rules)",
    r"pretend (you are|to be) (?:an? )?(unrestricted|unfiltered|jailbroken)",
    r"act as (?:dan|jailbreak|do anything now)",
    r"\bdan mode\b",
    r"developer mode (enabled|on)",
    r"you have no (restrictions|guidelines|filters)",
]

_MEDIUM_RISK_PATTERNS = [
    r"from now on,? you (are|will|must)",
    r"new instructions?:",
    r"system\s*:\s*",
    r"\[system\]",
    r"<\|?system\|?>",
    r"override (your|the) (rules|guidelines|programming)",
    r"this is (a|an) (test|simulation) so (the )?rules don'?t apply",
    r"hypothetically,? (if you had no|ignore)",
    r"roleplay as .*(without|no) (restrictions|filters|limits)",
]

_LOW_RISK_PATTERNS = [
    r"\bas an ai\b.*\byou (should|must|will)\b",
    r"for (educational|research) purposes only",
    r"i am (a|the) (developer|admin|owner) of this (system|app)",
]

_HIGH = [re.compile(p, re.IGNORECASE) for p in _HIGH_RISK_PATTERNS]
_MED = [re.compile(p, re.IGNORECASE) for p in _MEDIUM_RISK_PATTERNS]
_LOW = [re.compile(p, re.IGNORECASE) for p in _LOW_RISK_PATTERNS]


def _structural_signals(text: str) -> tuple[float, list[str]]:
    """Non-keyword signals: delimiter smuggling, encoding tricks, etc."""
    score = 0.0
    reasons = []

    # Fake delimiter / role-tag smuggling (e.g. trying to inject a new
    # "message" boundary the backend would otherwise trust).
    if re.search(r"(-{3,}|={3,})\s*(end|begin)\s*(system|instructions)", text, re.I):
        score += 0.3
        reasons.append("delimiter smuggling attempt")

    # Excessive base64-looking payload (possible encoded instruction)
    b64_candidates = re.findall(r"[A-Za-z0-9+/]{40,}={0,2}", text)
    if b64_candidates:
        score += 0.15
        reasons.append("long base64-like payload")

    # Unicode homoglyph / zero-width smuggling
    if re.search(r"[\u200b\u200c\u200d\u2060]", text):
        score += 0.2
        reasons.append("zero-width character smuggling")

    # Very high density of imperative "you must / you will" statements
    imperatives = len(re.findall(r"\byou (must|will|shall|have to)\b", text, re.I))
    if imperatives >= 3:
        score += 0.15
        reasons.append("high imperative density")

    return min(score, 0.5), reasons


def analyze(text: str) -> GuardResult:
    reasons: list[str] = []
    score = 0.0

    for pattern in _HIGH:
        if pattern.search(text):
            score += 0.45
            reasons.append(f"high-risk phrase match: /{pattern.pattern}/")

    for pattern in _MED:
        if pattern.search(text):
            score += 0.25
            reasons.append(f"medium-risk phrase match: /{pattern.pattern}/")

    for pattern in _LOW:
        if pattern.search(text):
            score += 0.1
            reasons.append(f"low-risk phrase match: /{pattern.pattern}/")

    struct_score, struct_reasons = _structural_signals(text)
    score += struct_score
    reasons.extend(struct_reasons)

    score = min(score, 1.0)
    return GuardResult(risk_score=score, blocked=False, reasons=reasons)


def guard_input(text: str, threshold: float) -> GuardResult:
    result = analyze(text)
    result.blocked = result.risk_score >= threshold
    return result
