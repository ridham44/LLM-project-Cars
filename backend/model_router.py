"""Picks THE model for a request. Exactly one.

The architecture rule this module exists to enforce: one user question is
answered by one LLM. There is no critic after it, no judge over it, and no
second opinion beside it. Everything before this point (normalization, phrase
matching, embeddings, and only rarely a tiny router model) is classification;
everything after it is formatting.

Why that is the right trade on this hardware: a cold model load costs 20-90s
here and only one model of any size stays resident on a 6GB shared GPU, so
every extra model in a request costs more than the answer itself. The old
pipeline spent 110s on a judge to re-word an answer a model had already
written - which is not verification, just latency.

Selection is a pure function of (intent, complexity) plus what Ollama actually
has installed, so the same question always routes the same way and the choice
is explainable in one line to the user.
"""

import logging

import config
import ollama_client

logger = logging.getLogger("research")

# Answer length caps per tier. Generation is the dominant cost once a model is
# resident (a 400-token answer is ~9s at 44 tok/s, ~50s at 8 tok/s), so this is
# the main latency lever after model choice.
NUM_PREDICT = {
    "low": 120,
    "medium": 420,
    "high": 420,
    "very_high": 500,
    "verify": 600,  # reasoning models spend part of the budget on <think>
}

# Per-tier hard timeout. A stuck call fails honestly instead of hanging the
# request; these are generous enough for a cold load plus generation.
#
# very_high is 480s because Mistral 7B genuinely needs it here: 56-86s of model
# load plus ~64s of generation, with headroom for the load running slower when
# the desktop session is holding more VRAM. A timeout tighter than the tier's
# real cost would kill valid answers, which is worse than waiting. medium gets
# 300s for the same reason at a smaller scale - gemma3:4b's first load is 94s.
TIMEOUT_SECONDS = {
    "low": 120,
    "medium": 300,
    "high": 240,
    "very_high": 480,
    "verify": 300,
}


# Complexity -> (tier, why). The whole routing table.
_TIER_FOR_COMPLEXITY = {
    "LOW": ("low", "a simple factual question"),
    "MEDIUM": ("medium", "moderate research - needs to read the evidence carefully"),
    "HIGH": ("high", "reasoning, analysis and comparison over wider evidence"),
    "VERY_HIGH": ("very_high", "deep research and complex synthesis"),
}


def select(intent: str, complexity: str, *, is_verify_request: bool) -> dict:
    """Returns {role, model, reason} - the single model that will answer.

    Complexity picks the tier; VERIFY overrides it. That is the entire decision.

      VERIFY (explicit)  ->  verify      deepseek-r1:1.5b
      LOW                ->  low         qwen2.5:1.5b
      MEDIUM             ->  medium      gemma3:4b
      HIGH               ->  high        qwen2.5:3b
      VERY_HIGH          ->  very_high   mistral:7b-instruct-q4_K_M

    VERIFY wins over everything because a user challenging an answer wants a
    different KIND of thinking, not a longer version of the same answer - and it
    holds however the rest of the sentence reads, so "can you research that again
    and verify your previous answer" is a VERIFY, not a RESEARCH.

    Intent otherwise shapes only COMPLEXITY (intent._estimate_complexity), never
    model choice directly: a COMPARE is a harder question for one model, not a
    reason to run several, so it reaches a higher tier by scoring higher
    complexity rather than by having its own branch here.
    """
    if is_verify_request or intent == "VERIFY":
        return _resolve("verify", "you asked for this to be checked, so a reasoning model re-examined it")

    tier, reason = _TIER_FOR_COMPLEXITY.get(complexity, _TIER_FOR_COMPLEXITY["MEDIUM"])
    return _resolve(tier, reason)


def _projected_seconds(model: str, role: str) -> float | None:
    """How long this model would take to generate this tier's answer, from the
    measured rates in config. None when the model hasn't been benchmarked -
    unknown is not the same as slow, so an unmeasured model is allowed through
    rather than rejected on a guess."""
    rate = config.MODEL_THROUGHPUT_TOK_S.get(model)
    if not rate:
        return None
    return NUM_PREDICT.get(role, 400) / rate


def _resolve(role: str, reason: str) -> dict:
    """Picks the first tier in the fallback chain that is both installed AND
    fast enough on this hardware.

    Two independent reasons to fall back, both reported to the user rather than
    hidden:

      * the model isn't pulled - degrade instead of erroring;
      * the model is measurably too slow for the tier's latency target. This is
        the hardware-awareness rule: classifying a question as demanding must
        never on its own commit the user to a multi-minute wait. On this GPU
        every 7B model projects at 50-90s of generation against a 30s target.
    """
    # Chains step DOWN in cost, not in tier order: `medium` falls back to `high`
    # because qwen2.5:3b is both installed-or-not independent of gemma3:4b and
    # measurably faster, so it is a better substitute than dropping straight to
    # the 120-token `low` tier. `low` has nowhere to fall.
    fallbacks = {
        "very_high": ["very_high", "high", "medium", "low"],
        "high": ["high", "medium", "low"],
        "medium": ["medium", "high", "low"],
        "verify": ["verify", "high", "medium", "low"],
        "low": ["low"],
    }[role]

    requested_model = config.MODEL_REGISTRY.get(role)
    notes = []

    for candidate in fallbacks:
        model = config.MODEL_REGISTRY.get(candidate)
        if not model:
            continue

        installed = ollama_client.is_model_installed(model)
        # None = Ollama unreachable. Not the model's fault, so don't skip it -
        # the call itself will fail honestly if Ollama really is down.
        if installed is False:
            notes.append(f"{model} is not installed")
            logger.warning("model tier %s: %s not installed", candidate, model)
            continue

        if config.ENFORCE_LATENCY_TARGETS and candidate != fallbacks[-1]:
            projected = _projected_seconds(model, candidate)
            target = config.TIER_LATENCY_TARGET_SECONDS.get(candidate)
            if projected and target and projected > target:
                notes.append(f"{model} would take ~{projected:.0f}s against a {target}s target")
                logger.info("model tier %s: %s projected %.0fs > %ds target", candidate, model, projected, target)
                continue

        if candidate != role:
            reason = f"{reason}; {' and '.join(notes)}, so {model} answered instead"
        return {"role": candidate, "model": model, "reason": reason, "requestedModel": requested_model}

    # Nothing in the chain qualified - return the original so the failure is
    # reported against the model that was actually wanted.
    return {"role": role, "model": requested_model or "?", "reason": reason, "requestedModel": requested_model}


def evidence_count_for(complexity: str) -> int:
    if complexity == "LOW":
        return config.TOP_K_EVIDENCE_LOW
    if complexity in ("HIGH", "VERY_HIGH"):
        return config.TOP_K_EVIDENCE_HIGH
    return config.TOP_K_EVIDENCE_MEDIUM
