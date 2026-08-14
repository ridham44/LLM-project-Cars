"""Query understanding: turns raw user text (+ conversation context) into a
structured classification the orchestrator can route on.

The pipeline, in order:

    text
     -> nlp.normalize          deterministic: whitespace, abbreviations
                               ("hp" -> horsepower), high-confidence typo
                               correction, language hint
     -> nlp.extract_entities   typed entities (vehicle/component/measurement)
     -> follow-up detection    pronouns/ellipsis vs self-contained
     -> context resolution     rewrite into a canonical, self-contained query
     -> semantic_intent        embedding similarity vs intent examples  <-- PRIMARY
     -> LLM router             ONLY when the semantic layer is not decisive
     -> heuristics             last resort if both are unavailable
     -> complexity + task plan

Intent is decided by MEANING, not keywords: "how does the Chiron stack up
against the Jesko?" is COMPARE because its embedding sits next to the other
COMPARE example phrasings, not because any rule mentions "stack up". The one
remaining regex-ish layer (_heuristic_classify) exists solely for the case
where Ollama is unreachable and there is nothing semantic to consult.

Two-stage routing is a deliberate performance decision: embedding one short
query against a cached catalog costs tens of milliseconds, while an LLM
router call costs seconds. Escalating only ambiguous queries keeps the fast
path fast without giving up the LLM's flexibility where it actually matters.
"""

import json
import logging
import os
import re
import time

import config
import nlp
import ollama_client
import semantic_intent
import verify_detect
from context_store import SessionState
from intent_taxonomy import brands_for_entities

logger = logging.getLogger("research")

# Task intents the orchestrator can route on. The semantic taxonomy is richer
# (ANALYZE/RECOMMEND/CHITCHAT); this maps that richer set onto the routing
# vocabulary the pipeline already understands, so the taxonomy can grow
# without the orchestrator needing a new branch for every new intent.
# Ceiling for the router LLM call, and how long to stop trying after one fails.
# 8s is chosen against the measured facts: the router model is pre-warmed at
# startup (main.warm_models - it is the same model as the `fast` tier), so a
# real call is ~1-2s. Anything approaching 8s means the model was evicted or
# Ollama is busy, and in that case the embedding layer's answer - already
# correct for the large majority of queries - is worth far more than the wait.
ROUTER_TIMEOUT_SECONDS = int(os.environ.get("ROUTER_TIMEOUT_SECONDS", "8"))
ROUTER_BACKOFF_SECONDS = int(os.environ.get("ROUTER_BACKOFF_SECONDS", "60"))

VALID_INTENTS = {"FACTUAL", "RESEARCH", "COMPARE", "VERIFY", "SUMMARY", "FOLLOWUP"}
VALID_COMPLEXITY = {"LOW", "MEDIUM", "HIGH", "VERY_HIGH"}
VALID_RESPONSE_TYPES = {"SHORT_ANSWER", "RESEARCH_REPORT", "COMPARISON", "VERIFICATION"}

# Semantic intent -> routing intent. ANALYZE/RECOMMEND both need reasoning
# over evidence, which is what the RESEARCH tier provides.
_SEMANTIC_TO_ROUTING = {
    "FACTUAL": "FACTUAL",
    "RESEARCH": "RESEARCH",
    "COMPARE": "COMPARE",
    "ANALYZE": "RESEARCH",
    "SUMMARY": "SUMMARY",
    "VERIFY": "VERIFY",
    "RECOMMEND": "COMPARE",
    "CHITCHAT": "FACTUAL",
}

def _is_decisive(semantic: dict) -> bool:
    """Whether the embedding layer settled the question well enough to skip the
    router LLM.

    The subtlety that matters: a narrow margin between two semantic intents is
    only an ambiguity if they lead to DIFFERENT decisions. RESEARCH vs ANALYZE
    scored 0.416/0.396 both map to the research tier and both produce a
    research report, so there is nothing for a router model to resolve -
    escalating it would spend a model call to pick between two identical
    outcomes. Checked here rather than in semantic_intent because this is where
    the semantic -> routing mapping lives.
    """
    if not semantic.get("confident"):
        return False
    if semantic["margin"] >= semantic_intent.MIN_DECISIVE_MARGIN:
        return True
    runner_up = semantic.get("runner_up_intent")
    if not runner_up:
        return True
    return _SEMANTIC_TO_ROUTING.get(semantic["primary_intent"]) == _SEMANTIC_TO_ROUTING.get(runner_up)


# Only unmistakable small talk may skip retrieval - answering ungrounded is
# the hallucination risk this whole system exists to prevent, so the bar for
# "no documents needed" stays deliberately high and deterministic.
_CHITCHAT_RE = re.compile(
    r"^(hi|hello|hey|hiya|yo|thanks|thank you|thx|ok|okay|good morning|good night|"
    r"good evening|bye|goodbye|see you|who are you|what can you do)\W*$",
    re.IGNORECASE,
)


# --- complexity ---------------------------------------------------------------

def _estimate_complexity(routing_intent: str, entities: list[dict], dimensions: list[str], text: str) -> str:
    """Complexity is independent of intent: "what is X's top speed" and
    "compare X and Y across five dimensions" can share an intent family but
    need very different pipelines. Driven by how many distinct things must be
    reasoned about, not by sentence length."""
    vehicles = [e for e in entities if e["type"] == "vehicle"]
    subject_count = len({v["value"] for v in vehicles})
    dimension_count = len(dimensions)
    conjunctions = len(re.findall(r"\b(and|plus|also|as well as)\b", text, re.IGNORECASE))

    if routing_intent == "FACTUAL":
        return "LOW" if dimension_count <= 1 and subject_count <= 1 else "MEDIUM"
    if routing_intent == "SUMMARY":
        return "MEDIUM"
    if routing_intent == "COMPARE":
        if subject_count >= 3 or dimension_count >= 3 or conjunctions >= 3:
            return "VERY_HIGH"
        return "HIGH"
    if routing_intent == "VERIFY":
        return "MEDIUM" if dimension_count <= 1 else "HIGH"
    # RESEARCH / ANALYZE
    if dimension_count >= 3 or conjunctions >= 3 or subject_count >= 3:
        return "VERY_HIGH"
    if dimension_count >= 1 or subject_count >= 2:
        return "HIGH"
    return "MEDIUM"


def _plan_tasks(routing_intent: str, entities: list[dict], dimensions: list[str]) -> list[str]:
    """Decomposes a complex request into the sub-questions the research
    pipeline should actually cover. Kept as plain strings: the value is in
    making the plan visible/loggable, and the pipeline consumes it as
    retrieval and prompt guidance rather than as executable steps."""
    vehicles = list(dict.fromkeys(e["value"] for e in entities if e["type"] == "vehicle"))
    components = list(dict.fromkeys(e["value"] for e in entities if e["type"] == "component"))
    subject = " and ".join(vehicles) if vehicles else "the subject"

    if routing_intent == "COMPARE" and len(vehicles) >= 2:
        aspects = dimensions or ["ENGINEERING", "PERFORMANCE"]
        tasks = [f"Compare {aspect.replace('_', ' ').lower()} across {subject}" for aspect in aspects]
        tasks.append(f"Identify the major differences between {subject}")
        tasks.append("Weigh the trade-offs and state a conclusion grounded in the evidence")
        return tasks
    if routing_intent == "RESEARCH":
        tasks = [f"Gather the key technical facts about {subject}"]
        for aspect in (dimensions or [])[:3]:
            tasks.append(f"Examine {aspect.replace('_', ' ').lower()} of {subject}")
        for component in components[:2]:
            tasks.append(f"Explain the {component} of {subject}")
        tasks.append("Synthesize the findings into a grounded summary")
        return tasks
    if routing_intent == "VERIFY":
        return [
            "Re-retrieve evidence for the claims under review",
            "Check each claim against the retrieved evidence",
            "Report supported, unsupported and contradicted claims",
        ]
    if routing_intent == "SUMMARY":
        return [f"Summarize the available evidence on {subject}"]
    return [f"Answer the question about {subject} from the evidence"]


# --- context resolution -------------------------------------------------------

def _resolve_canonical_query(normalized: str, session: SessionState, entities: list[dict], is_followup: bool) -> tuple[str, bool]:
    """Rewrites a follow-up into a self-contained query using session context.

    Deterministic rather than LLM-driven, so a follow-up still resolves
    correctly when the router model is slow, unavailable, or returns
    unparseable JSON - the failure mode that previously made follow-ups lose
    their subject entirely. Returns (query, resolved_from_context)."""
    if not is_followup:
        return normalized, False

    known_subjects = list(dict.fromkeys(
        list(session.active_comparison or []) + list(session.entities or [])
    ))
    if not known_subjects:
        return normalized, False

    mentioned = {e["value"] for e in entities if e["type"] == "vehicle"}
    missing = [s for s in known_subjects if s not in mentioned]
    if not missing:
        return normalized, False

    # "which one/both/the two/they" refer to the whole active comparison set;
    # a bare "it/its/that" refers to the single most recent subject.
    plural = re.search(
        r"\b(both|the two|they|them|these|those|which one|each|either)\b", normalized, re.IGNORECASE
    )
    subjects = missing[:2] if plural else missing[:1]
    suffix = " and ".join(subjects)
    return f"{normalized} (regarding {suffix})", True


# --- layer 4: the router LLM (ambiguous queries only) --------------------------
# This model classifies. It never writes any part of the answer - that is one
# model's job and one model's only (see model_router). The schema below is
# deliberately small: every field it returns is a routing input, and it no
# longer asks how many models a question needs, because the answer is always
# exactly one.

_CLASSIFIER_PROMPT = """You are the intent router for a local research assistant over a private document knowledge base. Classify the CURRENT QUESTION by its MEANING, not by which words it uses. Reply with JSON only - no prose, no markdown fences.

Schema:
{{
  "intent": [one or more of "FACTUAL", "RESEARCH", "COMPARE", "VERIFY", "SUMMARY"],
  "complexity": "LOW" | "MEDIUM" | "HIGH" | "VERY_HIGH",
  "requires_retrieval": true | false,
  "requires_verification": true | false,
  "entities": [subject names mentioned or implied],
  "comparison_dimensions": [aspects being compared/analyzed, e.g. "performance", "engineering", "weight"],
  "response_type": "SHORT_ANSWER" | "RESEARCH_REPORT" | "COMPARISON" | "VERIFICATION",
  "resolved_question": "the question rewritten as a fully self-contained question, resolving pronouns using the conversation context below",
  "confidence": 0.0-1.0
}}

Meaning guide (these are illustrations, not word lists - judge intent semantically):
- FACTUAL = one narrow fact ("what engine does X use", "what's X packing") -> LOW, SHORT_ANSWER.
- RESEARCH = open investigation of ONE subject ("deep dive into X", "how was X engineered") -> HIGH, RESEARCH_REPORT.
- COMPARE = two or more subjects weighed against each other, however phrased ("how does X stack up against Y", "which one would win", "put them head to head") -> HIGH, COMPARISON.
- VERIFY = checking a previous answer or claim ("are you sure", "is that backed by the documents") -> requires_verification TRUE, VERIFICATION.
- SUMMARY = condense material -> MEDIUM, RESEARCH_REPORT.
- Set requires_retrieval FALSE only for pure small talk.

Conversation context (may be empty):
- Previous question: {previous_question}
- Previous resolved question: {previous_resolved_question}
- Entities discussed so far: {previous_entities}
- Active comparison (if any): {active_comparison}

CURRENT QUESTION: {question}

JSON:"""


def _safe_json(text: str):
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


_router_unavailable_until = 0.0


def _llm_classify(question: str, session: SessionState) -> dict | None:
    global _router_unavailable_until
    if time.time() < _router_unavailable_until:
        return None

    prompt = _CLASSIFIER_PROMPT.format(
        previous_question=session.last_question or "(none)",
        previous_resolved_question=session.last_resolved_question or "(none)",
        previous_entities=", ".join(session.entities) or "(none)",
        active_comparison=", ".join(session.active_comparison) or "(none)",
        question=question,
    )
    # Hard-bounded, because this is the one place where understanding a
    # question can cost a model call. A cold 1.5B load is ~21s on this machine
    # and Ollama queues behind whatever else is generating, so an unbounded
    # router is how classification reached 149.8s. Past the timeout the caller
    # keeps the embedding layer's best guess, which is right the large majority
    # of the time - a slightly blunter route beats a minute of waiting.
    #
    # One attempt only: a retry doubles the worst case to fix a JSON parse
    # failure that the embedding fallback already covers.
    text, error = ollama_client.try_invoke(
        "router",
        prompt,
        num_predict=280,
        timeout_seconds=ROUTER_TIMEOUT_SECONDS,
        temperature=ollama_client.JSON_TEMPERATURE,
    )
    if error:
        # Circuit breaker. A router that just timed out will time out again on
        # the next request (a busy Ollama or an evicted model doesn't recover in
        # seconds), and paying the full timeout per request is precisely the
        # failure this rework exists to remove.
        _router_unavailable_until = time.time() + ROUTER_BACKOFF_SECONDS
        logger.info(
            "router LLM unavailable (%s) - keeping the semantic classification, backing off %ds",
            error, ROUTER_BACKOFF_SECONDS,
        )
        return None
    return _safe_json(text)


# --- heuristic last resort ----------------------------------------------------

def _heuristic_classify(text: str) -> str:
    """Absolute last resort: only reached when Ollama is unreachable, so
    neither embeddings nor the LLM router are available. Coarse on purpose -
    it picks a safe tier rather than pretending to understand the question."""
    lowered = text.lower()
    if re.search(r"\b(compar\w*|vs\.?|versus|difference|better|stack up|head to head|which (?:one|is))\b", lowered):
        return "COMPARE"
    if re.search(r"\b(verify|check|sure|correct|confirm|supported)\b", lowered):
        return "VERIFY"
    if re.search(r"\b(summar\w+|tl;?dr)\b", lowered):
        return "SUMMARY"
    if re.search(r"\b(research\w*|investigat\w*|deep dive|analy[sz]\w*|explain|why|how does)\b", lowered):
        return "RESEARCH"
    if len(lowered.split()) <= 12 and re.match(r"^(what|who|when|where|how (?:much|many|fast|quick))\b", lowered):
        return "FACTUAL"
    return "RESEARCH"


# --- main entry point ---------------------------------------------------------

def classify(question: str, session: SessionState) -> dict:
    started = time.time()
    prep = nlp.normalize(question)
    normalized = prep["normalized"]
    has_history = bool(session.last_question)

    entities = nlp.extract_entities(normalized, known_extra=tuple(session.entities or ()))
    is_followup, followup_reason = nlp.looks_like_followup(normalized, has_history)
    canonical, resolved_from_context = _resolve_canonical_query(normalized, session, entities, is_followup)
    # Entities named only via context still belong in the entity list.
    if resolved_from_context:
        entities = nlp.extract_entities(canonical, known_extra=tuple(session.entities or ()))

    nlp_ms = round((time.time() - started) * 1000)

    # --- layer 2: verification language (no model call) ---------------------
    # Checked FIRST and allowed to short-circuit everything after it. A user
    # challenging an answer routes to a different model entirely, so this
    # decision must not depend on an embedding round-trip - and it must not be
    # overridden by a sentence that also happens to say "research" or
    # "compare". Costs microseconds; see verify_detect.py.
    verify_match = verify_detect.detect(canonical, has_previous_answer=bool(session.last_answer_summary))

    semantic = None
    semantic_ms = 0
    source = "semantic"
    llm_ms = 0
    llm_parsed = None
    dimensions: list[str] = []
    confidence = 0.4
    semantic_primary = None
    routing_intent = "RESEARCH"
    secondary: list[str] = []

    if verify_match:
        source = f"verify_phrase:{verify_match['category']}"
        routing_intent = "VERIFY"
        secondary = []
        semantic_primary = "VERIFY"
        # A phrase match is an explicit request, not an inference - report it
        # as high confidence so nothing downstream escalates it to the router.
        confidence = 0.95
    else:
        # --- layer 3: embedding similarity ----------------------------------
        semantic_started = time.time()
        semantic = semantic_intent.classify(canonical)
        semantic_ms = round((time.time() - semantic_started) * 1000)

    if verify_match:
        pass
    elif semantic:
        semantic_primary = semantic["primary_intent"]
        routing_intent = _SEMANTIC_TO_ROUTING.get(semantic_primary, "RESEARCH")
        secondary = [_SEMANTIC_TO_ROUTING.get(s, s) for s in semantic["secondary_intents"]]
        dimensions = semantic["dimensions"]
        confidence = semantic["confidence"]

        # --- layer 4: the router LLM, ONLY when layer 3 wasn't decisive -----
        # This is the one model that may run besides the answer model, and only
        # for genuinely ambiguous phrasing. Everything decisive stops above.
        #
        # Follow-ups are excluded outright. "What about its transmission?" is
        # inherently short and vague, so it never looks decisive to the
        # embedding layer - but its context has ALREADY been resolved
        # deterministically above (_resolve_canonical_query), which is the part
        # a router model could have helped with. Escalating anyway measured 8s
        # on a question the pipeline had already understood.
        if not is_followup and not _is_decisive(semantic) and config.ROUTER_LLM_ENABLED:
            llm_started = time.time()
            llm_parsed = _llm_classify(canonical, session)
            llm_ms = round((time.time() - llm_started) * 1000)
            if llm_parsed:
                source = "semantic+llm"
    else:
        # Embeddings unavailable. The heuristic layer is tried FIRST here now:
        # it is free and correct for most phrasings, and the whole point of the
        # rework is that understanding a question must not cost a model call
        # when it doesn't have to.
        routing_intent = _heuristic_classify(canonical)
        secondary = []
        semantic_primary = routing_intent
        source = "heuristic"
        if config.ROUTER_LLM_ENABLED:
            llm_started = time.time()
            llm_parsed = _llm_classify(canonical, session)
            llm_ms = round((time.time() - llm_started) * 1000)
            if llm_parsed:
                source = "heuristic+llm"

    if llm_parsed:
        llm_intents = llm_parsed.get("intent")
        if isinstance(llm_intents, str):
            llm_intents = [llm_intents]
        llm_intents = [i for i in (llm_intents or []) if i in VALID_INTENTS]
        if llm_intents:
            # The LLM only overrides when stage 1 was NOT decisive, so this is
            # a genuine tie-break rather than second-guessing a confident
            # semantic match.
            routing_intent = llm_intents[0]
            secondary = llm_intents[1:3]
        llm_dims = [d.upper().replace(" ", "_") for d in (llm_parsed.get("comparison_dimensions") or []) if isinstance(d, str)]
        dimensions = list(dict.fromkeys(dimensions + llm_dims))[:3]
        for name in (llm_parsed.get("entities") or []):
            if isinstance(name, str) and name.strip() and not any(e["value"].lower() == name.strip().lower() for e in entities):
                entities.append({"type": "vehicle", "value": name.strip()})
        try:
            confidence = max(confidence, min(1.0, max(0.0, float(llm_parsed.get("confidence")))))
        except (TypeError, ValueError):
            pass
        resolved = llm_parsed.get("resolved_question")
        if isinstance(resolved, str) and resolved.strip() and len(resolved.strip()) > 3:
            canonical = resolved.strip()

    # --- VERIFY against a previous answer -----------------------------------
    # Only a real verification when there IS a previous answer to check;
    # otherwise it's a normal question that happened to sound like one.
    target = None
    if routing_intent == "VERIFY":
        if session.last_answer_summary:
            target = "PREVIOUS_ANSWER"
        else:
            routing_intent = "RESEARCH"

    # dict.fromkeys dedupes: several semantic intents map onto one routing
    # intent (ANALYZE and RESEARCH both -> RESEARCH), so a raw concatenation
    # could list the same intent twice.
    intents = list(dict.fromkeys(
        [routing_intent] + [s for s in secondary if s != routing_intent and s in VALID_INTENTS]
    ))
    if is_followup and "FOLLOWUP" not in intents:
        intents.append("FOLLOWUP")

    is_chitchat = bool(_CHITCHAT_RE.match(normalized.strip()))
    complexity = _estimate_complexity(routing_intent, entities, dimensions, canonical)
    vehicles = {e["value"] for e in entities if e["type"] == "vehicle"}

    # A comparison needs two subjects to compare. This used to also set
    # `requires_multiple_models`, which no longer exists: one question is
    # answered by one model, and a comparison is a harder question for that
    # model, not a reason to run several.
    is_comparison = routing_intent == "COMPARE" and len(vehicles) >= 2

    response_type = (
        "COMPARISON" if routing_intent == "COMPARE" else
        "VERIFICATION" if routing_intent == "VERIFY" else
        "SHORT_ANSWER" if routing_intent == "FACTUAL" else
        "RESEARCH_REPORT"
    )

    result = {
        "intent": intents,
        "complexity": complexity,
        "requires_retrieval": not is_chitchat,
        "requires_verification": routing_intent == "VERIFY",
        "is_comparison": is_comparison,
        "entities": [e["value"] for e in entities if e["type"] == "vehicle"] or [e["value"] for e in entities][:3],
        "typed_entities": entities,
        # Which marques' documents this question is about, so retrieval can be
        # scoped to them instead of searching the whole corpus. Empty means
        # "no marque named" - search everything.
        "brands": brands_for_entities(sorted(vehicles, key=lambda v: canonical.lower().find(v.lower()))),
        "comparison_dimensions": dimensions,
        "response_type": response_type,
        "resolved_question": canonical,
        "confidence": round(confidence, 3),
        "source": source,
        "target": target,
        "task_plan": _plan_tasks(routing_intent, entities, dimensions),
        # Everything the routing debug panel needs to explain this decision.
        "understanding": {
            "originalQuery": prep["original"],
            "normalizedQuery": normalized,
            "canonicalQuery": canonical,
            "language": prep["language"],
            "abbreviationsExpanded": prep["expansions"],
            "typoCorrections": prep["corrections"],
            "isFollowUp": is_followup,
            "followUpReason": followup_reason,
            "verifyPhrase": verify_match["matched"] if verify_match else None,
            "verifyCategory": verify_match["category"] if verify_match else None,
            "verifyMatchedBy": verify_match["how"] if verify_match else None,
            "resolvedFromContext": resolved_from_context,
            "semanticPrimary": semantic["primary_intent"] if semantic else None,
            "semanticRanked": semantic["ranked"] if semantic else [],
            "semanticSimilarity": semantic["similarity"] if semantic else None,
            "semanticMargin": semantic["margin"] if semantic else None,
            "matchedExample": semantic["matched_example"] if semantic else None,
            "semanticDecisive": semantic["decisive"] if semantic else None,
            "escalatedToLLM": bool(llm_parsed),
            "timings": {"nlpMs": nlp_ms, "semanticMs": semantic_ms, "llmMs": llm_ms},
        },
    }

    logger.info(
        "query understanding: %r -> intent=%s complexity=%s dims=%s entities=%s source=%s "
        "conf=%.2f followup=%s (nlp=%dms semantic=%dms llm=%dms)",
        question, intents, complexity, dimensions, result["entities"], source,
        confidence, is_followup, nlp_ms, semantic_ms, llm_ms,
    )
    return result
