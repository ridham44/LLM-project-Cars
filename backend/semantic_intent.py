"""Semantic intent classification by embedding similarity.

This is the PRIMARY intent mechanism. The query is embedded once and compared
against pre-embedded example phrasings for each intent (intent_taxonomy.py),
so "how does the Chiron stack up against the Jesko?" classifies as COMPARE
because of what it MEANS - the word "compare" never appears, and no rule
mentions "stack up".

Why embeddings rather than an LLM call for this:
  - The embedding model (nomic-embed-text) is already loaded and resident for
    retrieval, so classification costs one small embed call - tens of
    milliseconds - instead of a multi-second LLM generation.
  - It's deterministic and inspectable: every decision comes with the
    example it matched and a margin, which is what makes the debug panel
    useful and mis-routes fixable by adding one example phrase.

The LLM router is still used, but only when this layer is genuinely
uncertain (see intent.py's two-stage routing) - which is the difference
between paying for an LLM on every query and paying for it on the few that
need it.

Example embeddings are computed lazily on first use and cached for the
process lifetime; the taxonomy is static, so there's no invalidation to
manage.
"""

import hashlib
import json
import logging
import math
import threading
import time

import config
import nlp_local
from intent_taxonomy import DIMENSION_EXAMPLES, INTENT_EXAMPLES

logger = logging.getLogger("research")

_lock = threading.Lock()
_embedder = None
_intent_vectors: dict[str, list[tuple[str, list[float]]]] | None = None
_dimension_vectors: dict[str, list[tuple[str, list[float]]]] | None = None
_catalog_unavailable_until = 0.0

# The example catalog is static, so its embeddings are computed once and cached
# to disk. Recomputing them per process start was the single largest cost in
# the pipeline: the first query of a run paid for embedding ~140 example
# phrases, and if that call landed while Ollama was busy generating with a 7B
# model it queued behind it - the observed "Query Understanding: 149.8s".
# Cache key includes the embedding model and a hash of the phrases, so editing
# the taxonomy or switching models invalidates it automatically.
_CACHE_PATH = config.BASE_DIR / ".intent_vectors.json"

# Hard budget for the embedding round-trip on the request path. Query
# understanding must never cost more than the answer, so if the embedder is
# slow (busy Ollama, cold model) the request proceeds on the phrase/heuristic
# layer instead of waiting. Blown budgets are logged, not hidden.
EMBED_BUDGET_SECONDS = float(config.QUERY_UNDERSTANDING_BUDGET_MS) / 1000.0

# After a failure or a blown budget, stop trying for a while rather than
# paying the same stall on every subsequent request.
_BACKOFF_SECONDS = 60.0

# Thresholds are encoder-specific and these are MEASURED for
# all-MiniLM-L6-v2, not carried over from a different model. MiniLM's cosine
# scale sits much lower than nomic-embed-text's on this catalog - correctly
# classified queries land at 0.36-0.55 top similarity, where the previous
# nomic-tuned floor of 0.62 would have called every one of them uncertain and
# escalated it to the router LLM (a 21-90s cold load for a decision the
# embedding layer had already got right). Sampled across the intent set:
#
#   "What engine does the Chiron use?"          FACTUAL  0.547  margin 0.226
#   "Research the engineering behind X"         RESEARCH 0.416  margin 0.020
#   "Compare Chiron and Jesko"                  COMPARE  0.395  margin 0.213
#   "I think that answer is wrong"              VERIFY   0.392  margin 0.149
#   "How does the Chiron stack up against Y"    COMPARE  0.370  margin 0.104
#   "Summarize Ferrari Q2 2026 results"         SUMMARY  0.365  margin 0.081
#
# Below this the query genuinely doesn't resemble any known intent
# (out-of-domain phrasing, gibberish, an unsupported language).
MIN_CONFIDENT_SIMILARITY = 0.33
# Two intents this close are a real tie. NOTE: intent.py also treats a tie as
# decisive when both candidates map to the SAME model tier - "research the
# engineering" scoring RESEARCH 0.416 / ANALYZE 0.396 is not a routing
# ambiguity, because both route to the research model.
MIN_DECISIVE_MARGIN = 0.06
# A dimension is only reported when it clearly stands out; otherwise the
# question is about the subject generally, not one aspect of it. Same scale
# shift as above.
MIN_DIMENSION_SIMILARITY = 0.32


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Embeds with the LOCAL sentence-transformer first, falling back to the
    Ollama embedding model.

    The local encoder is the important path: it runs in-process on onnxruntime
    in ~20-30ms and never queues behind Ollama. Intent embeddings used to go
    through Ollama, which meant a query's classification waited behind whatever
    7B model was generating at that moment - the mechanism behind the observed
    "Query Understanding: 149.8s". Ollama remains the fallback so the semantic
    layer still works if the local model hasn't been downloaded."""
    local = nlp_local.embed(texts)
    if local:
        return local
    return _ollama_embedder().embed_documents(texts)


def _ollama_embedder():
    global _embedder
    if _embedder is None:
        with _lock:
            if _embedder is None:
                from langchain_ollama import OllamaEmbeddings

                _embedder = OllamaEmbeddings(model=config.EMBEDDING_MODEL, base_url=config.OLLAMA_BASE_URL)
    return _embedder


def encoder_name() -> str:
    """Which encoder the cached vectors belong to. Part of the cache key: a
    MiniLM vector and a nomic vector are not comparable, so switching encoders
    has to invalidate the catalog."""
    return nlp_local.INTENT_ENCODER if nlp_local.encoder() is not None else config.EMBEDDING_MODEL


def _catalog_fingerprint() -> str:
    payload = json.dumps(
        {"model": encoder_name(), "intents": INTENT_EXAMPLES, "dimensions": DIMENSION_EXAMPLES},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _load_cache(fingerprint: str):
    try:
        raw = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    if raw.get("fingerprint") != fingerprint:
        return None
    try:
        intents = {label: [(p, v) for p, v in pairs] for label, pairs in raw["intents"].items()}
        dimensions = {label: [(p, v) for p, v in pairs] for label, pairs in raw["dimensions"].items()}
    except Exception:
        return None
    return intents, dimensions


def _write_cache(fingerprint: str, intents, dimensions) -> None:
    try:
        _CACHE_PATH.write_text(
            json.dumps({"fingerprint": fingerprint, "intents": intents, "dimensions": dimensions}),
            encoding="utf-8",
        )
    except Exception as exc:  # pragma: no cover - a cache that can't be written is not fatal
        logger.warning("could not write intent vector cache: %s", exc)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def _embed_catalog(catalog: dict[str, list[str]]) -> dict[str, list[tuple[str, list[float]]]]:
    """Embeds every example phrase once, in a single batched call per
    catalog - one pass instead of ~100."""
    labels, phrases = [], []
    for label, examples in catalog.items():
        for phrase in examples:
            labels.append(label)
            phrases.append(phrase)
    vectors = _embed_texts(phrases)
    out: dict[str, list[tuple[str, list[float]]]] = {}
    for label, phrase, vector in zip(labels, phrases, vectors):
        out.setdefault(label, []).append((phrase, vector))
    return out


def warm() -> bool:
    """Makes the example embeddings available - from the on-disk cache when
    possible, otherwise by embedding them once and caching the result.

    Called at startup (main.warm_models) so no request ever pays for it. On
    the request path it is a dict check plus, at worst, a cache read."""
    global _intent_vectors, _dimension_vectors, _catalog_unavailable_until
    if _intent_vectors is not None and _dimension_vectors is not None:
        return True
    if time.time() < _catalog_unavailable_until:
        return False

    with _lock:
        if _intent_vectors is not None and _dimension_vectors is not None:
            return True

        fingerprint = _catalog_fingerprint()
        cached = _load_cache(fingerprint)
        if cached:
            _intent_vectors, _dimension_vectors = cached
            logger.info("intent vectors loaded from cache (%s)", _CACHE_PATH.name)
            return True

        started = time.time()
        try:
            intents = _embed_catalog(INTENT_EXAMPLES)
            dimensions = _embed_catalog(DIMENSION_EXAMPLES)
        except Exception as exc:
            # Embeddings unavailable (Ollama down, model not pulled) -
            # intent.py falls back to the phrase/heuristic layer rather than
            # failing the request. Backed off so every following request
            # doesn't retry the same stall.
            logger.warning("semantic intent catalog unavailable: %s", exc)
            _catalog_unavailable_until = time.time() + _BACKOFF_SECONDS
            return False

        _intent_vectors, _dimension_vectors = intents, dimensions
        logger.info("intent vectors computed in %.1fs, caching", time.time() - started)
        _write_cache(fingerprint, intents, dimensions)
    return True


def _score_against(catalog: dict[str, list[tuple[str, list[float]]]], query_vector: list[float]) -> list[tuple[str, float, str]]:
    """(label, best similarity, the example phrase that matched) per label,
    best first. Max-pooling over examples rather than averaging: a query only
    has to resemble ONE way of phrasing an intent, and averaging would
    penalise intents whose example list deliberately spans very different
    registers (formal + slang)."""
    scored = []
    for label, examples in catalog.items():
        best_phrase, best_score = "", -1.0
        for phrase, vector in examples:
            score = _cosine(query_vector, vector)
            if score > best_score:
                best_phrase, best_score = phrase, score
        scored.append((label, best_score, best_phrase))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored


def classify(query: str) -> dict | None:
    """Semantic classification of a single (already normalized) query.

    Returns None when embeddings are unavailable, so the caller can fall
    back rather than treating "no result" as "no intent". Otherwise returns
    the ranked intents, the matched example, a confidence derived from the
    actual similarity/margin, and whether that confidence is high enough to
    skip the LLM router."""
    global _catalog_unavailable_until
    if not warm():
        return None

    started = time.time()
    try:
        query_vector = _embed_texts([query])[0]
    except Exception as exc:
        logger.warning("semantic intent embed failed: %s", exc)
        _catalog_unavailable_until = time.time() + _BACKOFF_SECONDS
        return None

    elapsed = time.time() - started
    if elapsed > EMBED_BUDGET_SECONDS:
        # The result is still usable this time, but something is wrong (Ollama
        # busy, embedding model evicted). Say so loudly and skip the embedder
        # for the next minute so the next request isn't held up the same way.
        logger.warning(
            "query embedding took %.1fs (budget %.1fs) - backing off the semantic layer for %.0fs",
            elapsed, EMBED_BUDGET_SECONDS, _BACKOFF_SECONDS,
        )
        _catalog_unavailable_until = time.time() + _BACKOFF_SECONDS

    intent_scores = _score_against(_intent_vectors, query_vector)
    top_intent, top_score, top_example = intent_scores[0]
    runner_up_score = intent_scores[1][1] if len(intent_scores) > 1 else 0.0
    margin = top_score - runner_up_score

    # Secondary intents: other intents that scored nearly as well as the
    # winner are genuinely also present ("which is better engineered and
    # why" is COMPARE and ANALYZE), not noise.
    secondary = [label for label, score, _ in intent_scores[1:] if score >= top_score - 0.06][:2]

    dimension_scores = _score_against(_dimension_vectors, query_vector)
    dimensions = [label for label, score, _ in dimension_scores if score >= MIN_DIMENSION_SIMILARITY][:3]

    # Confidence blends "how well does this match anything" with "how
    # clearly does it match ONE thing" - a query near two intents is less
    # trustworthy than one sitting squarely on a single intent, even if both
    # have a high top similarity.
    # Scaled to MiniLM's range (see the thresholds above): a 0.5 top score is
    # a strong match on this catalog, not a weak one.
    confidence = max(0.0, min(1.0, 0.65 * min(top_score / 0.55, 1.0) + 0.35 * min(margin / 0.15, 1.0)))
    confident = top_score >= MIN_CONFIDENT_SIMILARITY
    decisive = confident and margin >= MIN_DECISIVE_MARGIN

    return {
        "primary_intent": top_intent,
        "runner_up_intent": intent_scores[1][0] if len(intent_scores) > 1 else None,
        "confident": confident,
        "secondary_intents": secondary,
        "dimensions": dimensions,
        "similarity": round(top_score, 4),
        "margin": round(margin, 4),
        "matched_example": top_example,
        "confidence": round(confidence, 3),
        "decisive": decisive,
        "ranked": [(label, round(score, 4)) for label, score, _ in intent_scores[:4]],
    }
