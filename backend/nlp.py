"""Deterministic, sub-millisecond text preprocessing that runs before any
model is consulted: normalization, abbreviation expansion, high-confidence
typo correction, typed entity extraction, and pronoun/ellipsis detection.

Deliberately NOT the intent classifier. Everything here is cheap, reversible
and explainable - the *meaning* of the request is decided semantically by
semantic_intent.py. This layer exists so that:
  - retrieval sees spec-sheet wording ("hp" -> "horsepower"),
  - a typo doesn't lose an entity ("Bugati" -> "Bugatti"),
  - the semantic classifier sees a clean sentence,
  - and the original text the user typed is never modified for display.

Two layers, cheapest first:

  * The domain vocabulary (KNOWN_ENTITIES) with RapidFuzz for typo repair.
    Exact and fast, and it is authoritative for the marques/models this corpus
    actually contains.
  * spaCy's linguistic pass (nlp_local.analyze) for everything a fixed
    vocabulary cannot know: entities it has never heard of, noun phrases,
    measurements and years. It runs in ~12ms and catches "the Rimac Nevera" or
    "a 1,600 hp quad-turbo" without either being listed anywhere.

spaCy is additive, never authoritative: a vocabulary hit wins over an NER
guess, because the vocabulary is curated and NER is statistical. When spaCy
isn't installed, extraction degrades to vocabulary-only rather than failing.
"""

import re
import unicodedata

import nlp_local
from intent_taxonomy import ABBREVIATIONS, KNOWN_COMPONENTS, KNOWN_ENTITIES

# Pronouns/elliptical references that mean "the thing we were just talking
# about" - their presence is what makes a question a follow-up needing
# context resolution rather than a self-contained query.
_PRONOUN_RE = re.compile(
    r"\b(it|its|it's|this|that|these|those|they|them|their|the former|the latter|"
    r"the first one|the second one|the other one|both|the two|same)\b",
    re.IGNORECASE,
)

# Openers that signal an elliptical follow-up even without a pronoun:
# "what about the transmission", "and the weight?"
_ELLIPSIS_RE = re.compile(
    r"^(what about|how about|and|but|also|then|what of|ok(?:ay)? (?:and|but))\b",
    re.IGNORECASE,
)

_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-\.]*")
_WS_RE = re.compile(r"\s+")


def _strip_accents(text: str) -> str:
    """Huracán -> Huracan, so accented and unaccented spellings match the
    same vocabulary entry. Applied only for MATCHING, never to the text
    shown back to the user."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def detect_language(text: str) -> str:
    """Coarse script/language hint. Not a full language detector - it exists
    so the pipeline can record what it saw and so a non-Latin-script query is
    flagged rather than silently mangled by the Latin-oriented normalization
    below. Returns an ISO-639-1-ish code or 'non-latin'."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "und"
    latin = sum(1 for c in letters if "LATIN" in unicodedata.name(c, ""))
    if latin / len(letters) < 0.5:
        return "non-latin"
    return "en"


def expand_abbreviations(text: str) -> tuple[str, list[str]]:
    """Expands domain shorthand token-by-token. Returns (text, expansions
    applied) so the routing debug panel can show exactly what changed."""
    applied = []

    def replace(match: re.Match) -> str:
        token = match.group(0)
        key = token.lower().strip(".")
        expansion = ABBREVIATIONS.get(key)
        if not expansion:
            return token
        applied.append(f"{token} -> {expansion}")
        return expansion

    return _WORD_RE.sub(replace, text), applied


# Single-word vocabulary entries only; multi-word names ("Bugatti Chiron") are
# matched as phrases in extract_entities. Built once - RapidFuzz is fast enough
# that the list comprehension is the expensive part otherwise.
_SINGLE_WORD_VOCAB = tuple(entry for entry in KNOWN_ENTITIES if " " not in entry)


def _best_vocab_match(word: str, vocabulary: tuple[str, ...]) -> tuple[str | None, float]:
    """Closest single-word vocabulary entry and its similarity ratio, via
    RapidFuzz (see nlp_local.fuzzy_best - it falls back to difflib when
    RapidFuzz isn't installed)."""
    match = nlp_local.fuzzy_best(_strip_accents(word).lower(), vocabulary, score_cutoff=0.0)
    return match if match else (None, 0.0)


def correct_typos(text: str, threshold: float = 0.86) -> tuple[str, list[str]]:
    """Fixes near-miss spellings of KNOWN entities only, and only above a
    high similarity threshold. Never touches a word that is already a known
    entity, and never "corrects" ordinary English - an unknown word is far
    more likely to be a real word this vocabulary doesn't list than a typo of
    something in it, so guessing would corrupt the query. Words shorter than
    5 characters are skipped entirely: at that length the ratio is too noisy
    to distinguish a typo from a different word."""
    known_lower = {_strip_accents(e).lower() for e in KNOWN_ENTITIES}
    corrections = []

    def replace(match: re.Match) -> str:
        word = match.group(0)
        if len(word) < 5:
            return word
        lowered = _strip_accents(word).lower()
        if lowered in known_lower:
            return word
        candidate, score = _best_vocab_match(word, _SINGLE_WORD_VOCAB)
        if candidate and score >= threshold:
            corrections.append(f"{word} -> {candidate}")
            return candidate
        return word

    return _WORD_RE.sub(replace, text), corrections


def normalize(text: str) -> dict:
    """Full deterministic normalization pass. Returns the normalized text
    plus a record of every transformation, so nothing the layer does is
    invisible (see the routing debug panel)."""
    original = text
    collapsed = _WS_RE.sub(" ", text).strip()
    expanded, expansions = expand_abbreviations(collapsed)
    corrected, corrections = correct_typos(expanded)
    return {
        "original": original,
        "normalized": corrected,
        "language": detect_language(collapsed),
        "expansions": expansions,
        "corrections": corrections,
    }


def extract_entities(text: str, known_extra: tuple[str, ...] = ()) -> list[dict]:
    """Typed entity extraction against the domain vocabulary, longest match
    first so "Bugatti Chiron" wins over "Bugatti". Vocabulary-based rather
    than statistical NER: for a fixed document corpus this is both more
    accurate and ~1000x faster than loading an NER model, and unknown-entity
    coverage is handled by the LLM router on the ambiguous path."""
    haystack = _strip_accents(text).lower()
    found: list[dict] = []
    claimed_spans: list[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(start < c_end and end > c_start for c_start, c_end in claimed_spans)

    vocab = sorted(set(KNOWN_ENTITIES + tuple(known_extra)), key=len, reverse=True)
    for entry in vocab:
        needle = _strip_accents(entry).lower()
        for match in re.finditer(rf"\b{re.escape(needle)}\b", haystack):
            if overlaps(match.start(), match.end()):
                continue
            claimed_spans.append((match.start(), match.end()))
            found.append({"type": "vehicle", "value": entry})
            break

    for component in KNOWN_COMPONENTS:
        if re.search(rf"\b{re.escape(component)}\b", haystack):
            found.append({"type": "component", "value": component})

    for match in re.finditer(r"\b\d[\d,\.]*\s*(?:km/h|mph|hp|bhp|ps|kw|nm|kg|lbs?|litre|liter|l|cc|sec(?:onds)?|s)\b", haystack):
        found.append({"type": "measurement", "value": match.group(0).strip()})

    # spaCy pass for what the vocabulary can't know. Added only where it
    # doesn't duplicate a vocabulary hit, and typed distinctly so downstream
    # code can tell a curated match from a statistical one - marque scoping
    # (retrieval.py) deliberately keys off "vehicle" only, so an NER guess
    # never silently narrows which documents get searched.
    linguistic = nlp_local.analyze(text)
    if linguistic["available"]:
        claimed_values = {f["value"].lower() for f in found}
        for entity in linguistic["entities"]:
            value = entity["text"].strip().lstrip("the ").strip()
            if len(value) < 3 or value.lower() in claimed_values:
                continue
            if any(value.lower() in existing for existing in claimed_values):
                continue
            found.append({"type": "named_entity", "value": value, "label": entity["label"]})
            claimed_values.add(value.lower())

        for measurement in linguistic["measurements"]:
            if measurement.lower() not in claimed_values:
                found.append({"type": "measurement", "value": measurement})
                claimed_values.add(measurement.lower())

        for year in linguistic["years"]:
            found.append({"type": "year", "value": year})

    return found


def looks_like_followup(text: str, has_history: bool) -> tuple[bool, str | None]:
    """Whether this turn depends on the previous one. Returns (is_followup,
    reason) - the reason is surfaced in the debug panel so a wrong context
    resolution is diagnosable rather than mysterious."""
    if not has_history:
        return False, None
    stripped = text.strip()
    if _ELLIPSIS_RE.match(stripped):
        return True, "starts with an elliptical opener"
    if _PRONOUN_RE.search(stripped):
        return True, "contains a pronoun/back-reference"
    # A very short question with no named entity is almost always a
    # continuation ("which is faster?", "and the weight?").
    if len(stripped.split()) <= 6 and not extract_entities(stripped):
        return True, "short question with no named subject"
    return False, None
