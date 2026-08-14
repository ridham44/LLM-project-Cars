"""Layer-2 intent detection for verification/doubt language - no model calls.

VERIFY is the one intent that gets its own detector ahead of the semantic
layer, for two reasons:

  1. It routes to a DIFFERENT model (the reasoning tier), so getting it wrong
     is not a shade of meaning - it picks the wrong model for the whole
     request.
  2. It out-prioritizes every other intent. "Can you research that again and
     verify your previous answer?" is a VERIFY, not a RESEARCH, even though it
     says "research" - the user is challenging an answer, not asking for a new
     one. A single-primary-intent classifier scored on similarity gets this
     wrong regularly, because the sentence genuinely does look like both.

Matching is phrase-substring first (microseconds), then token-level fuzzy for
typos ("dobule check", "verfiy"). Phrases live in verification_phrases.json so
the vocabulary can grow without touching code.
"""

import json
import logging
import re
from difflib import SequenceMatcher
from pathlib import Path

logger = logging.getLogger("research")

PHRASES_PATH = Path(__file__).resolve().parent / "verification_phrases.json"

# A fuzzy hit needs to be this close to a dictionary phrase. High on purpose:
# "check" vs "cheap" is a 0.6 ratio and must NOT be a verification request.
_FUZZY_THRESHOLD = 0.88

# Single words that on their own are strong enough to mean verification, used
# for the fuzzy pass (multi-word phrases are matched as substrings instead).
_FUZZY_WORDS = (
    "verify",
    "validate",
    "recheck",
    "doublecheck",
    "factcheck",
    "reconsider",
    "reevaluate",
    "confirm",
)

_WORD_RE = re.compile(r"[a-z']+")


def _load_categories() -> dict[str, tuple[str, ...]]:
    try:
        raw = json.loads(PHRASES_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive: ship-blocking if it happens
        logger.error("could not load %s: %s - verification detection degraded", PHRASES_PATH.name, exc)
        return {}
    return {
        key: tuple(sorted((p.lower() for p in value), key=len, reverse=True))
        for key, value in raw.items()
        if not key.startswith("_") and isinstance(value, list)
    }


CATEGORIES = _load_categories()

# Longest-first across all categories, so "check your answer" is reported
# rather than the bare "check" it contains.
_ALL_PHRASES: tuple[tuple[str, str], ...] = tuple(
    sorted(
        ((phrase, category) for category, phrases in CATEGORIES.items() for phrase in phrases),
        key=lambda item: len(item[0]),
        reverse=True,
    )
)

# "check" and "make sure" also appear in perfectly ordinary questions, so the
# short generic phrases only count as verification when the turn is a
# follow-up (there is an answer on the table to be challenged). Without this,
# "what should I check before a track day" would route to the reasoning model.
_NEEDS_CONTEXT = frozenset({"check", "check this", "check that", "make sure", "confirm this", "try again", "validate"})


def detect(normalized_query: str, *, has_previous_answer: bool) -> dict | None:
    """Returns match details when the query is verification/doubt language,
    else None. Pure string work - no embeddings, no model, no network.

    `has_previous_answer` gates the ambiguous short phrases only; explicit
    language ("are you sure", "fact check that") is a verification request
    regardless, and the orchestrator handles "nothing to verify yet" as its
    own case rather than silently reclassifying it."""
    text = (normalized_query or "").lower().strip()
    if not text:
        return None

    for phrase, category in _ALL_PHRASES:
        if phrase not in text:
            continue
        if phrase in _NEEDS_CONTEXT and not has_previous_answer:
            continue
        return {"category": category, "matched": phrase, "how": "phrase"}

    # Fuzzy pass for typos, token by token. Only single strong words, and only
    # against words long enough for the ratio to mean something.
    for word in _WORD_RE.findall(text):
        if len(word) < 6:
            continue
        for candidate in _FUZZY_WORDS:
            if SequenceMatcher(None, word, candidate).ratio() >= _FUZZY_THRESHOLD:
                return {"category": "DIRECT_VERIFY", "matched": candidate, "how": f"fuzzy:{word}"}

    return None
