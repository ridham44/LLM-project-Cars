import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DOCUMENTS_DIR = BASE_DIR / "documents"
CHROMA_DIR = BASE_DIR / "chroma_db"
COLLECTION_NAME = "research_docs"

OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")

# --- Model registry ---------------------------------------------------------
# ONE USER QUESTION = ONE ANSWER MODEL.
#
# This registry has one entry per *tier*, not per pipeline stage, because the
# pipeline no longer has stages after the answer. There is no critic, no claim
# extractor, no judge. model_router.select() picks exactly one of these from
# the classified intent + complexity, it answers, and the request is done.
#
# Why: on a 6GB shared GPU only one model of consequence stays resident, so
# every additional model in a request costs a 20-90s cold load - more than the
# answer itself. The previous multi-model pipeline measured 110.8s of "judge
# synthesis" to re-word an answer another model had already written, and 90s
# of "claim extraction" to list sentences. Neither improved accuracy enough to
# be worth minutes of the user's time; both are gone.
#
# MEASURED ON THIS MACHINE, every model installed, same RAG prompt (see
# ARCHITECTURE_AUDIT.md for the raw run). These numbers chose the defaults
# below; none of it is estimated:
#
#   model                        cold load   tok/s   400-token answer (warm)
#   qwen2.5:1.5b                     21.5s    44.2                    11.0s
#   deepseek-r1:1.5b                 39.2s    42.4                    11.3s
#   qwen2.5:3b                       32.1s    37.8                    13.1s
#   gemma3:4b                        94.2s    29.3                    16.6s
#   mistral:7b-instruct-q4_K_M       56-86s    7.8                   141.1s
#   deepseek-r1:7b                  98-111s    8.1                   150.5s
#   qwen2.5:7b                      98-115s    7.9                   168.3s
#   llama3.1:8b-instruct-q4_K_M     93-107s    5.7                   180.1s
#
# THE DECISIVE FINDING: every 7B+ model paid a FULL cold load again on a
# back-to-back second call (86-115s), while every model at 4B and under
# reloaded in 1.3-3.4s. They do not stay resident on a 6GB shared GPU. So a
# 7B tier does not cost "7B generation speed" - it costs a cold load plus 50s
# of generation, every single request. 150-180s per answer.
#
# That is why no tier below is a 7B model, and it is the reason the previous
# architecture was slow: it routed three of them into one request.
#
# NOT INSTALLED here: qwen3:8b, mistral-small3.1:24b. Both are supported as
# overrides (see .env.example), but neither can be a default on this evidence -
# a 24B model is strictly worse than the 7B rows above, and those already miss
# the 30s target by 5x. Pull one and set the env var if you would rather have
# the stronger answer than the latency target; that is a real trade, not a
# free upgrade.
ROUTER_MODEL = os.environ.get("ROUTER_MODEL", "qwen2.5:1.5b")

# --- One model per complexity level -----------------------------------------
# The tier IS the complexity. intent.py classifies LOW/MEDIUM/HIGH/VERY_HIGH,
# model_router maps that straight to one of these, and VERIFY overrides all of
# them. Nothing else influences model choice.
#
# Note that MEDIUM runs a LARGER model than HIGH, which is deliberate and not a
# mistake: gemma3:4b is a different family with stronger reading comprehension,
# and MEDIUM is where "explain / summarize / moderate research" questions land -
# the ones that most benefit from understanding the evidence well. HIGH gets
# qwen2.5:3b because HIGH questions are wider (9 evidence chunks) and Qwen is
# measurably faster (37.8 vs 29.3 tok/s), which is what keeps a bigger question
# inside a tighter budget.

# LOW - simple factual lookups, specifications, short answers.
LOW_MODEL = os.environ.get("LOW_MODEL", "qwen2.5:1.5b")

# MEDIUM - better understanding, moderate research, explanations, summaries.
# 29.3 tok/s. One caveat measured on this machine: gemma3:4b costs a 94s FIRST
# load (the largest cold start of any model here), then reloads in ~3s. It is
# pre-warmed at startup for exactly that reason - see main.warm_models.
MEDIUM_MODEL = os.environ.get("MEDIUM_MODEL", "gemma3:4b")

# HIGH - reasoning, analysis, comparisons. 37.8 tok/s, 32.1s cold load.
HIGH_MODEL = os.environ.get("HIGH_MODEL", "qwen2.5:3b")

# VERY_HIGH complexity only - "do a very detailed investigation of X", a
# comparison across three or more subjects or dimensions. Mistral 7B: the
# strongest reasoning available locally, and a different family from every other
# tier.
#
# THIS TIER DELIBERATELY TRADES LATENCY FOR DEPTH, and the cost is real and
# measured: 7.8 tok/s, and it does not stay resident on a 6GB shared GPU, so a
# VERY_HIGH question costs roughly 56-86s of model load plus ~64s of generation
# - about 2-2.5 minutes. Its own latency target below is raised to match, so the
# hardware-aware guard permits it here (it still protects every other tier).
#
# Two consequences worth knowing:
#   - Loading Mistral (~4.4GB) evicts the small resident models on a 6GB card,
#     so the NEXT question - whatever tier - pays a reload too.
#   - This is why VERY_HIGH is a narrow gate (see intent._estimate_complexity):
#     three-plus subjects/dimensions, not merely "HIGH". Ordinary research and
#     comparisons stay on the HIGH tier at 13-19s.
#
# Set VERY_HIGH_MODEL=qwen2.5:3b to make this tier as fast as HIGH again, at the
# cost of the deeper answer.
VERY_HIGH_MODEL = os.environ.get("VERY_HIGH_MODEL", "mistral:7b-instruct-q4_K_M")

# VERIFY / recheck / doubt. DeepSeek-R1 lineage - reasoning-distilled, and
# deliberately a different family from every answering tier: when the user
# challenges an answer, re-running the model that wrote it is the least useful
# thing the system could do. This is the ONLY model for such a request; it
# re-retrieves evidence and reconsiders independently, and nothing grades its
# output afterwards.
#
# The 1.5B distill, not the 7B, on measurement: deepseek-r1:7b takes 150.5s per
# answer on this GPU (it never stays resident), while deepseek-r1:1.5b runs at
# 42.4 tok/s for an 11.3s answer - and a reasoning model that returns in 11s is
# worth more than one that returns in two and a half minutes. Set
# VERIFY_MODEL=deepseek-r1:7b if you accept that cost.
VERIFY_MODEL = os.environ.get("VERIFY_MODEL", "deepseek-r1:1.5b")

# Optional vision/document-image tier. Registered so routing has a slot; no
# question currently routes to it.
SPECIALIST_MODEL = os.environ.get("SPECIALIST_MODEL", "llava:7b")

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "nomic-embed-text")

# Tier -> model. model_router.select() returns one of these keys, and exactly
# one entry from it runs per request.
MODEL_REGISTRY = {
    "router": ROUTER_MODEL,
    "low": LOW_MODEL,
    "medium": MEDIUM_MODEL,
    "high": HIGH_MODEL,
    "very_high": VERY_HIGH_MODEL,
    "verify": VERIFY_MODEL,
    "specialist": SPECIALIST_MODEL,
}

# Human-readable purpose strings, surfaced by /health and the frontend's
# "AI Routing" panel so the UI can explain why this model was chosen.
MODEL_ROLE_DESCRIPTIONS = {
    "router": "Classifies intent only when the fast layers are ambiguous (not per request)",
    "low": "Fast factual and simple questions - the whole answer",
    "medium": "Better understanding and moderate research - the whole answer",
    "high": "Reasoning, analysis and comparison - the whole answer",
    "very_high": "Deep research and complex synthesis - the whole answer",
    "verify": "Rechecks an answer the user challenged - the whole answer",
    "specialist": "Optional vision/document-image understanding (not auto-invoked)",
}

# --- Hardware-aware routing ---------------------------------------------------
# Measured generation rates (tokens/sec, warm) from the benchmark above. The
# router uses these to project how long a model would actually take for a
# tier's answer length, so "this question is HIGH complexity" can never on its
# own commit the user to a 3-minute wait. See model_router._resolve.
MODEL_THROUGHPUT_TOK_S = {
    "qwen2.5:1.5b": 44.2,
    "deepseek-r1:1.5b": 42.4,
    "qwen2.5:3b": 37.8,
    "gemma3:4b": 29.3,
    "mistral:7b-instruct-q4_K_M": 7.8,
    "qwen2.5:7b": 7.9,
    "deepseek-r1:7b": 8.1,
    "llama3.1:8b-instruct-q4_K_M": 5.7,
}

# What each tier is allowed to cost in GENERATION time (model load is on top).
# A model projected over its tier's budget is dropped for the next tier down,
# and the substitution is reported to the user rather than hidden.
#
# very_high is 90s by deliberate choice, not by oversight: that tier runs Mistral
# 7B for genuinely demanding questions and is expected to take ~2 minutes end to
# end. The guard still does real work there - it would reject llama3.1:8b (500
# tokens / 5.7 tok/s = 88s, borderline) and anything slower - and it protects the
# other tiers strictly.
TIER_LATENCY_TARGET_SECONDS = {
    "low": 10,
    "medium": 20,
    "high": 25,
    "very_high": 90,
    "verify": 20,
}

# Set false to let a deliberately-pinned large model run however long it takes
# (e.g. you pulled qwen3:8b and want it regardless).
ENFORCE_LATENCY_TARGETS = os.environ.get("ENFORCE_LATENCY_TARGETS", "true").strip().lower() in ("1", "true", "yes", "on")

# --- Query understanding ------------------------------------------------------
# Understanding a question must never cost more than answering it. The layers
# are: normalization (regex/dict, sub-ms) -> verification phrase match
# (verify_detect.py, sub-ms) -> embedding similarity against a disk-cached
# example catalog (~50-200ms) -> the router LLM, only when all of the above
# were inconclusive.
#
# Budget for the ONE embedding round-trip on the request path. Past this,
# semantic_intent logs it and backs off so the next request uses the phrase
# layer instead of stalling again - see semantic_intent.EMBED_BUDGET_SECONDS.
QUERY_UNDERSTANDING_BUDGET_MS = int(os.environ.get("QUERY_UNDERSTANDING_BUDGET_MS", "1500"))

# The router LLM is the only model that can run *besides* the answer model,
# and only for genuinely ambiguous phrasing. It is a 1.5B model on a short
# prompt (~1-2s warm), and it is skipped entirely when the phrase or embedding
# layer was decisive. Set false to never call it - classification then falls
# back to the embedding layer's best guess, which is right the large majority
# of the time.
ROUTER_LLM_ENABLED = os.environ.get("ROUTER_LLM_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")

# --- Retrieval ---------------------------------------------------------------
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# Wide candidate pool so hybrid fusion (vector + BM25) has enough to choose
# from before being cut to the tier's evidence count below. Fusion IS the
# rerank now: the previous LLM rerank pass was a second model call inside
# "Document Retrieval" (it is what made a follow-up's retrieval cost 52.9s)
# and has been removed. RRF over two independent signals is free and
# deterministic.
TOP_K_VECTOR = 25         # candidates pulled from the vector index
TOP_K_KEYWORD = 25        # candidates pulled from the BM25 keyword index
RRF_K = 60                # reciprocal-rank-fusion constant

# Evidence chunks actually handed to the model, by complexity tier. Prompt
# length is a real cost multiplier, and a 5-chunk prompt that answers the
# question beats a 25-chunk prompt that buries it.
TOP_K_EVIDENCE_LOW = 4
TOP_K_EVIDENCE_MEDIUM = 6
TOP_K_EVIDENCE_HIGH = 9

# Below this average relevance the evidence is too thin to answer from, and
# retrieval widens once (a pure index operation - no model involved).
EVIDENCE_SUFFICIENCY_THRESHOLD = 0.4

# Cap on the claims the answer model reports alongside its answer. These come
# back in the SAME response as the answer - there is no separate extraction
# call - so this only bounds output length.
MAX_CLAIMS = 6

# --- Confidence ---------------------------------------------------------------
# Reported to the UI as a bucket label primarily, with the number as
# supporting detail: a bare percentage reads as more precise than the
# underlying signals support. See confidence.py.
CONFIDENCE_BANDS = (
    (0.4, "Low"),
    (0.7, "Moderate"),
    (0.85, "High"),
)
CONFIDENCE_BAND_DEFAULT = "Very High"

# --- Runtime ------------------------------------------------------------------
# Concurrent Ollama calls this process will issue at once. Ollama keeps one
# model of consequence resident here, so >1 concurrent call across different
# models thrashes rather than parallelizing.
MAX_CONCURRENT_OLLAMA_REQUESTS = int(os.environ.get("MAX_CONCURRENT_OLLAMA_REQUESTS", "1"))

# How long a conversation session's context (previous question/answer/
# entities) is kept in memory before eviction. See context_store.py.
SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_SECONDS", str(60 * 60 * 2)))

NUM_FAKE_DOCUMENTS = 50
