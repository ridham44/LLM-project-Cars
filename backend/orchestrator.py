"""The pipeline: understand -> select ONE model -> retrieve -> answer.

    USER -> normalize -> fast NLP/semantic -> intent + complexity
         -> model selection -> retrieval (if needed) -> ONE LLM -> answer

That is the whole thing. There is no critic after the answer, no claim
extractor, no judge, and no second opinion. `models_used` in the report has
exactly one entry for the answer (plus the tiny router model on the rare
ambiguous query, which classifies and never writes prose).

This replaced a researcher -> analyst -> critic -> judge chain that was
measured at 110.8s for judge synthesis and 90.0s for claim extraction on a
single question. Those stages didn't make answers more correct in proportion
to what they cost; the model that writes the answer now reports its own
findings and claims in the same call, and a user who doubts an answer gets a
different, reasoning-tuned model to look at it - as an ANSWER, not as a
post-processing pass.

The only stage that may run a second model is intent classification, and only
when the phrase and embedding layers were both inconclusive - see intent.py.
"""

import logging
import os
import time
import uuid

import agents
import claims as claims_module
import config
import confidence as confidence_module
import context_store
import intent as intent_module
import intent_taxonomy as taxonomy
import model_router
import retrieval

logger = logging.getLogger("research")


def _build_evidence_and_sources(docs):
    evidence, sources_by_path = [], {}
    for index, doc in enumerate(docs):
        source_path = doc.metadata.get("source") or "unknown"
        title = os.path.basename(source_path)
        page = doc.metadata.get("page")
        page = page + 1 if isinstance(page, int) else page
        evidence.append({
            "id": f"e{index + 1}",
            "sourceType": "other",
            "documentTitle": title,
            "manufacturer": None,
            "page": page,
            "excerpt": doc.page_content[:400],
            "score": doc.metadata.get("relevance", 0.0),
            "url": None,
        })
        if source_path not in sources_by_path:
            sources_by_path[source_path] = {
                "id": f"s{len(sources_by_path) + 1}",
                "manufacturer": None,
                "title": title,
                "type": "other",
                "date": None,
                "page": page,
                "url": None,
            }
    return evidence, list(sources_by_path.values())


def _avg_relevance(docs) -> float:
    scores = [d.metadata.get("relevance", 0.0) for d in docs]
    return sum(scores) / len(scores) if scores else 0.0


def _model_entry(role: str, model: str, ran: bool, *, reason: str | None = None) -> dict:
    return {
        "role": role,
        "model": model,
        "ran": ran,
        "status": "SUCCESS" if ran else "UNAVAILABLE",
        "purpose": config.MODEL_ROLE_DESCRIPTIONS.get(role),
        "reason": reason,
    }


def _routing_explanation(classification: dict, selection: dict, ran: bool) -> str:
    """One sentence naming the single model that answered and why it was
    picked. It can never imply cross-checking that didn't happen, because
    there is only ever one answer model to name."""
    intents_label = "/".join(classification["intent"])
    complexity = classification["complexity"]
    verb = "answered by" if ran else "could not be answered -"
    return (
        f"Classified as {intents_label} ({complexity} complexity) - {verb} "
        f"{selection['model']} alone. {selection['reason'].capitalize()}."
    )


def _step_timings(trace: list[dict]) -> list[dict]:
    """Real per-step durations from the cumulative trace marks, so "where did
    the time go" is answered from measurement rather than guessed at."""
    timings, previous = [], 0
    for entry in trace:
        elapsed = entry.get("elapsedMs")
        if elapsed is None:
            continue
        duration = elapsed - previous
        previous = elapsed
        if entry.get("status") == "skipped":
            continue
        timings.append({"step": entry["step"], "durationMs": max(0, duration)})
    return timings


def _empty_report(question, classification, trace, started_at, request_id):
    return {
        "id": request_id,
        "question": question,
        "status": "completed",
        "summary": "Insufficient evidence in the local knowledge base.",
        "findings": [],
        "comparison": None,
        "evidence": [],
        "claims": [],
        "contradictions": [],
        "sources": [],
        "metrics": {
            "documentsSearched": None,
            "documentsSelected": 0,
            "evidenceChunks": 0,
            "claimsExtracted": 0,
            "claimsVerified": 0,
            "contradictionsCount": 0,
            "confidence": 0.05,
            "confidenceLabel": confidence_module.label(0.05),
            "executionTimeSeconds": round(time.time() - started_at, 1),
            "timings": _step_timings(trace),
        },
        "trace": trace,
        "routing": {
            "intent": classification["intent"],
            "complexity": classification["complexity"],
            "modelsUsed": [],
            "distinctModelCount": 0,
            "explanation": "No evidence was found, so no model was asked to answer.",
            "evidenceCount": 0,
            "confidence": 0.05,
            "confidenceLabel": confidence_module.label(0.05),
            "documentScope": [],
            "documentScopeRelaxed": False,
        },
        "error": None,
    }


def _report(
    *, request_id, question, status, classification, selection, trace, started_at,
    summary, findings, comparison, evidence, sources, claim_records, models_used,
    confidence_score, brands, scope_relaxed, answer_ran,
):
    return {
        "id": request_id,
        "question": question,
        "status": status,
        "summary": summary,
        "findings": findings,
        "comparison": comparison,
        "evidence": evidence,
        "claims": claim_records,
        # Kept for the frontend's shape; nothing detects contradictions now
        # that no second model reviews the answer. An empty list is honest -
        # "no contradictions found" would not be.
        "contradictions": [],
        "sources": sources,
        "metrics": {
            "documentsSearched": retrieval.get_retriever().knowledge_base_status().get("documents")
            if classification["requires_retrieval"] else None,
            "documentsSelected": len(sources),
            "evidenceChunks": len(evidence),
            "claimsExtracted": len(claim_records),
            "claimsVerified": 0,
            "contradictionsCount": 0,
            "confidence": confidence_score,
            "confidenceLabel": confidence_module.label(confidence_score),
            "executionTimeSeconds": round(time.time() - started_at, 1),
            "timings": _step_timings(trace),
        },
        "trace": trace,
        "routing": {
            "intent": classification["intent"],
            "complexity": classification["complexity"],
            "modelsUsed": list(models_used),
            "distinctModelCount": len({m["model"] for m in models_used if m["ran"]}),
            "answerModel": selection["model"],
            "answerTier": selection["role"],
            "explanation": _routing_explanation(classification, selection, answer_ran),
            "evidenceCount": len(evidence),
            "confidence": confidence_score,
            "confidenceLabel": confidence_module.label(confidence_score),
            "documentScope": [taxonomy.BRAND_LABEL.get(b, b) for b in brands],
            "documentScopeRelaxed": scope_relaxed,
        },
        "error": None,
    }


def run(question: str, session_id: str | None = None, on_progress=None) -> dict:
    started_at = time.time()
    request_id = str(uuid.uuid4())
    trace: list[dict] = []
    session = context_store.get(session_id)

    def note(step, status="done", **extra):
        trace.append({
            "step": step,
            "status": status,
            "elapsedMs": round((time.time() - started_at) * 1000),
            **{k: v for k, v in extra.items() if v is not None},
        })

    # --- 1. understand (no model call unless genuinely ambiguous) -----------
    classification = intent_module.classify(question, session)
    understanding = classification["understanding"]
    note(
        "Query Understanding",
        source=classification["source"],
        nlpMs=understanding["timings"]["nlpMs"],
        semanticMs=understanding["timings"]["semanticMs"],
        llmMs=understanding["timings"]["llmMs"],
    )

    intents = classification["intent"]
    is_verify = classification.get("target") == "PREVIOUS_ANSWER"
    is_comparison = classification.get("is_comparison", False)

    # --- 2. select THE model ------------------------------------------------
    selection = model_router.select(
        classification["intent"][0], classification["complexity"], is_verify_request=is_verify
    )
    role = selection["role"]
    note("Model Selection", model=selection["model"], tier=role, reason=selection["reason"])

    # --- 3. retrieve --------------------------------------------------------
    evidence, sources = [], []
    brands, scope_relaxed = [], False
    if classification["requires_retrieval"]:
        retriever = retrieval.get_retriever()
        base_query = (session.last_resolved_question or classification["resolved_question"]) if is_verify \
            else classification["resolved_question"]

        target_k = model_router.evidence_count_for(classification["complexity"])
        brands = list(classification.get("brands") or [])
        pool_size = max(config.TOP_K_VECTOR, config.TOP_K_KEYWORD)

        # Trace marks bracket the operations they measure. _step_timings
        # attributes the gap between consecutive marks to the LATER one, so a
        # mark placed after a slow call charges that call to the wrong step -
        # which is how an 8.9s vector+BM25 search was showing up as "Document
        # Scope: 8.89s" next to "Document Retrieval: 0.30s". The scope decision
        # itself is a dict lookup; it is recorded before the search runs.
        if brands:
            note(
                "Document Scope",
                brands=[taxonomy.BRAND_LABEL.get(b, b) for b in brands],
            )

        pool = retriever.hybrid_search(base_query, pool_size, brands=brands)
        if brands and not pool:
            scope_relaxed = True
            pool = retriever.hybrid_search(base_query, pool_size)
            note("Document Scope Widened", reason="no documents on file for that marque")
        note("Candidate Search", pool_size=len(pool))

        # Local cross-encoder reorders the fused pool down to the tier's
        # evidence count (~110ms for 25 candidates, in-process). The LLM rerank
        # pass that used to sit here made a follow-up's retrieval cost 52.9s.
        candidates, rank_method = retrieval.rerank(base_query, pool, target_k)

        # Thin evidence: widen once. A pure index operation, no model.
        if candidates and _avg_relevance(candidates) < config.EVIDENCE_SUFFICIENCY_THRESHOLD:
            wider = retriever.hybrid_search(base_query, config.TOP_K_VECTOR, brands=None if scope_relaxed else brands)
            candidates, rank_method = retrieval.rerank(base_query, wider, config.TOP_K_EVIDENCE_HIGH)
            note("Retrieval Widened", reason="initial evidence was weak")

        evidence, sources = _build_evidence_and_sources(candidates)
        note("Reranking", evidence_chunks=len(evidence), ranked_by=rank_method)

        if not evidence:
            logger.info("research %s: no evidence (intent=%s query=%r)", request_id, intents, base_query)
            return _empty_report(question, classification, trace, started_at, request_id)

        # Tell the client which stage we're at before the model call, which is
        # the only slow step left. There is no partial ANSWER to stream - one
        # model writes the whole thing in one call - so this reports progress,
        # not a draft.
        if on_progress:
            on_progress({
                "id": request_id, "question": question, "status": "processing", "summary": None,
                "findings": [], "comparison": None, "evidence": evidence, "claims": [],
                "contradictions": [], "sources": sources, "trace": list(trace), "error": None,
                "metrics": {"evidenceChunks": len(evidence), "timings": _step_timings(trace)},
                "routing": {
                    "intent": classification["intent"], "complexity": classification["complexity"],
                    "modelsUsed": [], "answerModel": selection["model"], "answerTier": role,
                    "explanation": f"Asking {selection['model']} for the answer.",
                    "evidenceCount": len(evidence), "confidence": None, "confidenceLabel": None,
                    "documentScope": [taxonomy.BRAND_LABEL.get(b, b) for b in brands],
                    "documentScopeRelaxed": scope_relaxed,
                },
            })

    # --- 4. THE one model call ---------------------------------------------
    answer = agents.run_answer(
        role,
        classification["resolved_question"],
        evidence,
        want_comparison=is_comparison,
        previous_answer=session.last_answer_summary if is_verify else None,
    )
    note("Answer", model=answer.model, ran=answer.ran)

    models_used = [_model_entry(role, answer.model, answer.ran, reason=selection["reason"])]
    if understanding["timings"]["llmMs"]:
        # The router model classified but wrote none of the answer. Listed so
        # the panel is complete, labelled so it can't read as a second author.
        models_used.append(_model_entry(
            "router", config.ROUTER_MODEL, True, reason="classified an ambiguous question; wrote none of the answer"
        ))

    if not answer.ran:
        summary = f"{answer.model} was unavailable, so this question has no answer. ({answer.error})"
        report = _report(
            request_id=request_id, question=question, status="completed", classification=classification,
            selection=selection, trace=trace, started_at=started_at, summary=summary, findings=[],
            comparison=None, evidence=evidence, sources=sources, claim_records=[], models_used=models_used,
            confidence_score=0.0, brands=brands, scope_relaxed=scope_relaxed, answer_ran=False,
        )
        return report

    # --- 5. assemble (no model calls past this point) -----------------------
    summary = answer.summary or "The model returned an empty answer."
    valid_ids = {item["id"] for item in evidence}
    # Claims are parsed out of the answer deterministically - no extra model.
    claim_records = claims_module.to_records(claims_module.claims_from_text(summary, valid_ids))

    confidence_score = confidence_module.compute(
        evidence=evidence,
        claims=claim_records,
        router_confidence=classification.get("confidence", 0.5),
    )

    note("Synthesis")

    report = _report(
        request_id=request_id, question=question, status="completed", classification=classification,
        selection=selection, trace=trace, started_at=started_at, summary=summary,
        findings=[], comparison=None, evidence=evidence, sources=sources,
        claim_records=claim_records, models_used=models_used, confidence_score=confidence_score,
        brands=brands, scope_relaxed=scope_relaxed, answer_ran=True,
    )

    context_store.update(
        session_id,
        last_question=question,
        last_resolved_question=classification["resolved_question"],
        last_answer_summary=summary,
        last_report_id=request_id,
        last_intent=intents,
        entities=(classification["entities"] or session.entities)[:5],
        active_comparison=classification["entities"] if is_comparison else session.active_comparison,
        last_claims=claim_records,
        last_evidence=evidence,
    )

    logger.info(
        "research %s: intent=%s complexity=%s selected_model=%s evidence=%d total=%.1fs (%s)",
        request_id, intents, classification["complexity"], answer.model, len(evidence),
        time.time() - started_at,
        ", ".join(f"{t['step']} {t['durationMs'] / 1000:.1f}s" for t in _step_timings(trace)),
    )
    return report
