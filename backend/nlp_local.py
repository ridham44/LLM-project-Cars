"""The local NLP stack: spaCy, RapidFuzz, a sentence-transformer encoder and a
cross-encoder reranker. All of it runs in-process, on this machine, with no API
key and no network call at inference time.

Layering is the point. Each layer is cheaper than the one below it, and a
request only descends as far as it has to:

    normalize (regex/dict)        ~0.1ms   always
    spaCy                        ~2-15ms   tokens, sentences, NER, noun chunks
    RapidFuzz                    ~0.5ms    typo repair against the entity dict
    sentence-transformer         ~5-20ms   semantic intent similarity
    cross-encoder rerank         ~150-500ms retrieval only, 25 candidates
    Qwen 1.5B router             ~1-2s     ONLY when the above are uncertain

Two deliberate engineering choices:

1. ONNX RUNTIME, NOT TORCH. The encoder and reranker run through
   onnxruntime, which is already a dependency (chromadb pulls it). Installing
   torch to run two 22M-parameter models would add ~2GB for no measurable
   quality gain on this hardware.

2. EVERY LAYER IS OPTIONAL AT RUNTIME. If spaCy's model isn't downloaded, or
   fastembed's ONNX weights aren't cached yet, that layer reports itself
   unavailable and the pipeline uses the layer above it. The system degrades to
   a slightly blunter classifier instead of failing, and `status()` reports
   exactly which layers are live - so a missing model is visible rather than
   silently changing behaviour.

The intent encoder here replaced an Ollama round-trip for query understanding.
That mattered more than any other change in this file: intent embeddings used
to queue behind whatever 7B model Ollama was generating with, which is how
"Query Understanding" reached 149.8 seconds. Nothing on the understanding path
touches Ollama any more.
"""

import logging
import threading
import time

logger = logging.getLogger("research")

# Sentence-transformer used for intent similarity. all-MiniLM-L6-v2 is the
# standard sentence-transformers baseline: 384 dims, 22M params, and quick
# enough on CPU that intent classification is not a measurable cost.
INTENT_ENCODER = "sentence-transformers/all-MiniLM-L6-v2"

# Cross-encoder for retrieval reranking. A cross-encoder scores (query, chunk)
# pairs jointly rather than comparing two independent embeddings, which is why
# it can reorder a candidate pool that vector similarity got roughly right.
# This is the LOCAL replacement for the LLM rerank pass that used to cost tens
# of seconds inside retrieval.
RERANK_ENCODER = "Xenova/ms-marco-MiniLM-L-6-v2"

_lock = threading.Lock()
_spacy_nlp = None
_spacy_state = "unloaded"
_encoder = None
_encoder_state = "unloaded"
_reranker = None
_reranker_state = "unloaded"


# --- spaCy --------------------------------------------------------------------

def spacy_nlp():
    """The spaCy pipeline, loaded once. Returns None when the model isn't
    installed, so callers fall back to the vocabulary matcher in nlp.py."""
    global _spacy_nlp, _spacy_state
    if _spacy_nlp is not None or _spacy_state == "unavailable":
        return _spacy_nlp
    with _lock:
        if _spacy_nlp is None and _spacy_state != "unavailable":
            try:
                import spacy

                started = time.time()
                # The parser is the expensive component and noun_chunks needs
                # it; the small English model keeps the whole pipeline in the
                # low milliseconds for query-length text.
                _spacy_nlp = spacy.load("en_core_web_sm", exclude=["lemmatizer"])
                _spacy_state = "ready"
                logger.info("spaCy en_core_web_sm loaded in %.2fs", time.time() - started)
            except Exception as exc:
                _spacy_state = "unavailable"
                logger.warning("spaCy unavailable (%s) - falling back to vocabulary matching", exc)
    return _spacy_nlp


# Units worth recognising in this domain, so "1600 hp" and "420 km/h" come out
# as measurements rather than as a number next to a word.
_UNIT_TOKENS = {
    "hp", "bhp", "ps", "kw", "nm", "lb-ft", "kg", "lbs", "lb", "km/h", "kmh", "mph",
    "litre", "liter", "l", "cc", "s", "sec", "secs", "seconds", "rpm", "bar", "mm", "cm", "m",
}


def analyze(text: str) -> dict:
    """spaCy pass over one query. Returns entities, noun phrases, measurements,
    sentences and years. Empty structures (not an error) when spaCy is absent.

    This is what replaced using an LLM for basic entity extraction: a proper
    NER pass costs single-digit milliseconds, and a model call to do the same
    job costs a thousand times that."""
    nlp = spacy_nlp()
    if nlp is None or not text:
        return {"available": False, "entities": [], "noun_phrases": [], "measurements": [], "sentences": [], "years": []}

    doc = nlp(text)

    entities = [
        {"text": ent.text, "label": ent.label_}
        for ent in doc.ents
        # PERSON/ORG/PRODUCT/GPE catch marque and model names; CARDINAL and
        # QUANTITY are handled as measurements below instead.
        if ent.label_ in ("ORG", "PRODUCT", "PERSON", "GPE", "WORK_OF_ART", "NORP", "FAC")
    ]

    measurements = []
    for token in doc:
        if not token.like_num:
            continue
        following = doc[token.i + 1] if token.i + 1 < len(doc) else None
        unit = following.text.lower() if following is not None else ""
        if unit in _UNIT_TOKENS:
            measurements.append(f"{token.text} {following.text}")
        elif token.text.isdigit() and len(token.text) == 4 and 1900 <= int(token.text) <= 2100:
            continue  # a year, collected separately
        elif any(char.isdigit() for char in token.text) and len(token.text) > 1:
            measurements.append(token.text)

    years = [t.text for t in doc if t.text.isdigit() and len(t.text) == 4 and 1900 <= int(t.text) <= 2100]

    return {
        "available": True,
        "entities": entities,
        "noun_phrases": [chunk.text for chunk in doc.noun_chunks],
        "measurements": measurements,
        "sentences": [sent.text.strip() for sent in doc.sents],
        "years": years,
    }


# --- RapidFuzz ----------------------------------------------------------------

def fuzzy_best(word: str, vocabulary, *, score_cutoff: float = 88.0):
    """Closest vocabulary entry to `word` above `score_cutoff`, or None.

    RapidFuzz rather than difflib: same idea, roughly 10-50x faster, and its
    WRatio handles the partial/token cases ("koenigsseg" -> "Koenigsegg") that
    a plain ratio scores too low. Falls back to difflib when RapidFuzz isn't
    installed, so typo repair never simply stops working."""
    if not word:
        return None
    try:
        from rapidfuzz import fuzz, process

        match = process.extractOne(word, vocabulary, scorer=fuzz.WRatio, score_cutoff=score_cutoff)
        return (match[0], match[1] / 100.0) if match else None
    except ImportError:
        from difflib import SequenceMatcher

        best, best_score = None, 0.0
        for entry in vocabulary:
            score = SequenceMatcher(None, word.lower(), entry.lower()).ratio()
            if score > best_score:
                best, best_score = entry, score
        if best and best_score >= score_cutoff / 100.0:
            return best, best_score
        return None


# --- Sentence-transformer encoder --------------------------------------------

def encoder():
    """The intent encoder, loaded once. None when unavailable."""
    global _encoder, _encoder_state
    if _encoder is not None or _encoder_state == "unavailable":
        return _encoder
    with _lock:
        if _encoder is None and _encoder_state != "unavailable":
            try:
                from fastembed import TextEmbedding

                started = time.time()
                _encoder = TextEmbedding(model_name=INTENT_ENCODER)
                _encoder_state = "ready"
                logger.info("intent encoder %s ready in %.2fs", INTENT_ENCODER, time.time() - started)
            except Exception as exc:
                _encoder_state = "unavailable"
                logger.warning("local intent encoder unavailable (%s) - will use the Ollama embedder", exc)
    return _encoder


def embed(texts: list[str]) -> list[list[float]] | None:
    """Embeds a batch locally. None when the encoder isn't available, so the
    caller can fall back to the Ollama embedding model."""
    model = encoder()
    if model is None or not texts:
        return None
    try:
        return [vector.tolist() for vector in model.embed(texts)]
    except Exception as exc:
        logger.warning("local embedding failed: %s", exc)
        return None


# --- Cross-encoder reranker ---------------------------------------------------

def reranker():
    global _reranker, _reranker_state
    if _reranker is not None or _reranker_state == "unavailable":
        return _reranker
    with _lock:
        if _reranker is None and _reranker_state != "unavailable":
            try:
                from fastembed.rerank.cross_encoder import TextCrossEncoder

                started = time.time()
                _reranker = TextCrossEncoder(model_name=RERANK_ENCODER)
                _reranker_state = "ready"
                logger.info("cross-encoder %s ready in %.2fs", RERANK_ENCODER, time.time() - started)
            except Exception as exc:
                _reranker_state = "unavailable"
                logger.warning("local reranker unavailable (%s) - using fusion order", exc)
    return _reranker


def rerank(query: str, passages: list[str]) -> list[float] | None:
    """Cross-encoder relevance scores, one per passage, in input order.

    None when the reranker isn't available - the caller then keeps the
    reciprocal-rank-fusion order, which is a real ranking rather than a
    fabricated one."""
    model = reranker()
    if model is None or not passages:
        return None
    try:
        return list(model.rerank(query, passages))
    except Exception as exc:
        logger.warning("cross-encoder rerank failed: %s", exc)
        return None


# --- status -------------------------------------------------------------------

def warm() -> dict:
    """Loads every layer up front so no request pays the first-use cost.
    Called from main.warm_models at startup, off the request path."""
    spacy_nlp()
    embed(["warm up"])
    rerank("warm up", ["warm up passage"])
    return status()


def status() -> dict:
    """Which layers are live. Surfaced by /health so a missing model is
    visible instead of silently changing how questions are classified."""
    return {
        "spacy": _spacy_state,
        "intentEncoder": _encoder_state,
        "reranker": _reranker_state,
        "intentEncoderModel": INTENT_ENCODER,
        "rerankerModel": RERANK_ENCODER,
    }
