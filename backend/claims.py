"""Claims for the UI, with no model call of its own.

The old version of this module ran two extra LLM calls per request: one to
extract claims from an answer and one to verify them against the evidence.
They were measured at 90.0s and 49.2s respectively - together, most of a
request - so both are gone.

What replaces them:

  * The answer model reports its own claims in the SAME response as the answer
    (see agents.run_answer's JSON schema). That costs no extra call.
  * When the answer came back as plain prose (the fast tier, or a model that
    ignored the schema), claims are derived here by sentence-level parsing.

Neither path VERIFIES anything, and this module never pretends otherwise: a
claim carries `status: "stated"` and the evidence ids the model cited. The one
thing that does check an answer is a user-requested VERIFY, which routes the
whole request to the reasoning model - it is an answer, not a post-processing
pass.
"""

import re

import config

# A sentence is only worth showing as a claim if it asserts something
# checkable. Numbers, units and comparatives are what make a statement
# checkable; "the engine is impressive" is not a claim.
_CHECKABLE_RE = re.compile(
    r"(\d|\bfaster\b|\bslower\b|\bhigher\b|\blower\b|\bmore\b|\bless\b|\bheavier\b|\blighter\b|"
    r"\bmost\b|\bleast\b|\bonly\b|\bfirst\b|\bmaximum\b|\bminimum\b)",
    re.IGNORECASE,
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")

# Evidence-id citations the model may have left inline, e.g. "[e1]" or "[e2]".
_INLINE_ID_RE = re.compile(r"\[(e\d+)\]")


def claims_from_text(text: str, valid_ids: set[str], max_claims: int | None = None) -> list[dict]:
    """Lightweight fallback for prose answers. Deterministic and instant."""
    limit = max_claims or config.MAX_CLAIMS
    if not text:
        return []

    claims = []
    for sentence in _SENTENCE_SPLIT_RE.split(text.strip()):
        cleaned = sentence.strip()
        if len(cleaned) < 25 or not _CHECKABLE_RE.search(cleaned):
            continue
        cited = [i for i in _INLINE_ID_RE.findall(cleaned) if i in valid_ids]
        claims.append({"text": _INLINE_ID_RE.sub("", cleaned).strip(), "evidenceIds": cited})
        if len(claims) >= limit:
            break
    return claims


def to_records(claims: list[dict]) -> list[dict]:
    """Shapes claims for the report/UI.

    `status` is always "stated": these are the statements the answer makes,
    with the evidence the answer model cited for them. Calling them
    "supported" would imply an independent check that this architecture
    deliberately does not run on every request."""
    records = []
    for claim in claims:
        text = (claim.get("text") or "").strip()
        if not text:
            continue
        ids = claim.get("evidenceIds") or []
        records.append({
            "text": text,
            "status": "stated",
            "evidenceIds": ids,
            "cited": bool(ids),
        })
    return records
