"""Startup warm-up plus the legacy /ask and /search bridge.

The name is historical: this used to call three models per question. It no
longer does, and neither does anything else - every real request goes through
orchestrator.run(), which selects exactly ONE answer model. /ask is kept
working for backward compatibility and answers with that same single model.
"""

import logging

import agents
import nlp_local
import ollama_client
import retrieval
import semantic_intent

logger = logging.getLogger("research")

GROUNDING_RULE = agents.GROUNDING_RULE

QUICK_PROMPT = GROUNDING_RULE + "\n\nContext:\n{context}\n\nQuick answer: {question}"


class TripleModelSystem:
    def __init__(self):
        self.retriever = retrieval.get_retriever()
        self.vector_store = self.retriever.vector_store  # exposed for api.py's health/KB-status checks

    def warm_models(self) -> None:
        """Pays every first-use cost at startup so no request pays it.

        Order matters, cheapest and most-used first:

        1. The local NLP stack (spaCy, the intent encoder, the cross-encoder).
           ~3.5s once, and it takes query understanding to ~40ms per request.
        2. The intent example catalog - loaded from its on-disk cache when the
           taxonomy hasn't changed, embedded and cached otherwise.
        3. The BM25 keyword index, built once from the persisted chunks. This
           used to be built lazily inside the first search.
        4. The `fast` model, which answers every LOW-complexity question. A
           cold load costs 21-94s on this machine depending on the model (see
           config.py's measured table) versus ~1s of generation, so an unwarmed
           model is the difference between a 2s answer and a 25s one.

        Deliberately does NOT warm the research/heavy/verify models: they are
        7B-class, only one model of consequence stays resident on a 6GB shared
        GPU, and warming them would evict the one that answers most questions.
        Each step is independent, so one failure never blocks the others or
        startup."""
        try:
            nlp_local.warm()
        except Exception as exc:
            logger.warning("local NLP warm-up failed: %s", exc)

        try:
            semantic_intent.warm()
        except Exception as exc:
            logger.warning("intent catalog warm-up failed: %s", exc)

        try:
            docs = self.retriever.hybrid_search("warm up", k=3)
            context = "\n\n".join(doc.page_content for doc in docs) or "No relevant documents were found."
        except Exception:
            context = "No relevant documents were found."

        # Warm `low` and `medium`. Not an arbitrary pair - these are the two
        # most valuable to pre-pay:
        #   * `low` (qwen2.5:1.5b, ~1GB) answers the most questions.
        #   * `medium` (gemma3:4b, ~2.7GB) has the WORST first load of any model
        #     measured here at 94s. Paying that at startup instead of inside a
        #     user's first MEDIUM question is the single biggest cold-start win
        #     available; after it, gemma3:4b reloads in ~3s.
        #
        # `high`, `very_high` and `verify` are deliberately not warmed. Four
        # answer models cannot be resident in 6GB shared with a desktop session
        # (qwen2.5:3b 2GB + mistral 4.4GB + deepseek 1.1GB on top of the above),
        # so warming them would just evict the two that matter most. They load on
        # first use and stay resident until something bigger displaces them.
        for role in ("low", "medium"):
            try:
                ollama_client.try_invoke(
                    role, QUICK_PROMPT.format(context=context, question="warm up"), num_predict=1, timeout_seconds=300
                )
            except Exception:
                pass

    def retrieve_context(self, question: str) -> str:
        docs = self.retriever.hybrid_search(question, k=5)
        return "\n\n".join(doc.page_content for doc in docs)

    def retrieve_with_scores(self, question: str):
        docs = self.retriever.hybrid_search(question, k=5)
        return [(doc, doc.metadata.get("relevance", 0.0)) for doc in docs]

    def ask(self, question: str) -> dict:
        """Legacy /ask. Answers with ONE model, like everything else now - the
        three separate model calls this used to make are exactly what the
        architecture removed. The response keeps its old shape so any existing
        caller doesn't break; `research` and `analysis` repeat the one answer
        rather than fabricating two more."""
        context = self.retrieve_context(question)
        effective_context = context or "No relevant documents were found."

        answer, _ = ollama_client.try_invoke("low", QUICK_PROMPT.format(context=effective_context, question=question))
        text = answer or "Model unavailable."

        return {
            "question": question,
            "research": text,
            "quick": text,
            "analysis": text,
            "context": effective_context,
        }

    def search(self, question: str) -> str:
        return self.retrieve_context(question)
