"""Overall report confidence from the signals this system actually computes.

Deliberately smaller than it used to be. The old version blended a "critic
component" and a "supported claims ratio" from a second model that reviewed
every answer - that model no longer runs, so scoring against it would be
inventing an input. What is left is real: how much relevant evidence was
retrieved, whether the answer tied its claims to specific evidence ids, and
how confident the classifier was about what was being asked.

Nothing here should be read as "this answer was verified". Verification is a
user-initiated request that routes to the reasoning model (see model_router);
on every other request this score describes the GROUNDING available to the
answer, not a check performed on it.
"""

import config


def label(score: float) -> str:
    """Buckets the numeric score into Low/Moderate/High/Very High. The UI
    leads with this label, not the bare percentage - a number like "72%"
    reads as more precise than a few blended heuristics actually support."""
    for threshold, name in config.CONFIDENCE_BANDS:
        if score < threshold:
            return name
    return config.CONFIDENCE_BAND_DEFAULT


def compute(
    *,
    evidence: list[dict],
    claims: list[dict],
    router_confidence: float,
) -> float:
    if not evidence:
        return 0.05

    # How much relevant material the answer had to work from, and how relevant
    # it actually was - a full set of weakly-matching chunks is not grounding.
    count_component = min(len(evidence) / 6.0, 1.0)
    scores = [item.get("score") or 0.0 for item in evidence]
    relevance_component = min(sum(scores) / len(scores) * 1.4, 1.0) if scores else 0.0
    evidence_component = 0.5 * count_component + 0.5 * relevance_component

    # Did the answer tie its claims to specific evidence ids? A model that
    # cites [e3] for a number is measurably more grounded than one that asserts
    # it freely. This is a property of the answer, not an external check.
    if claims:
        cited = sum(1 for claim in claims if claim.get("cited"))
        citation_component = cited / len(claims)
    else:
        citation_component = 0.5  # no checkable claims made - neither good nor bad

    score = (
        0.55 * evidence_component
        + 0.30 * citation_component
        + 0.15 * max(0.0, min(1.0, router_confidence))
    )
    return round(max(0.0, min(1.0, score)), 2)
