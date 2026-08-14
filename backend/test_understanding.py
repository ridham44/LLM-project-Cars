"""Automated paraphrase tests for the query-understanding layer.

Run directly:  python test_understanding.py

The point of these tests is specifically that NONE of the expected results
depend on the "obvious" keyword being present. Each group contains phrasings
that mean the same thing while sharing few or no words with each other
("compare X and Y" vs "put them head to head" vs "which one would win"), so a
keyword classifier fails them and a semantic one passes. That makes this file
the regression guard against sliding back into keyword matching.

Requires Ollama reachable with the embedding model available, since the
semantic layer is the thing under test.
"""

import sys

from context_store import SessionState

import intent


def _fresh() -> SessionState:
    return SessionState()


def _with_history(question="Compare the Chiron and the Jesko.", entities=None, answer="The Chiron uses a W16.") -> SessionState:
    session = _fresh()
    session.last_question = question
    session.last_resolved_question = question
    session.last_answer_summary = answer
    session.entities = entities or ["Bugatti Chiron", "Koenigsegg Jesko"]
    session.active_comparison = entities or ["Bugatti Chiron", "Koenigsegg Jesko"]
    return session


# (label, question, expected routing intent, session factory)
CASES = [
    # --- COMPARE: no shared keywords between these phrasings ---------------
    ("compare-explicit", "Compare the Chiron and the Jesko.", "COMPARE", _fresh),
    ("compare-vs", "Chiron vs Jesko?", "COMPARE", _fresh),
    ("compare-stackup", "How does the Chiron stack up against the Jesko?", "COMPARE", _fresh),
    ("compare-headtohead", "Put the Chiron and Jesko head to head.", "COMPARE", _fresh),
    ("compare-differ", "How are the Chiron and Jesko different?", "COMPARE", _fresh),
    ("compare-fare", "How does the Chiron fare against the Jesko?", "COMPARE", _fresh),
    ("compare-against", "Put the Chiron against the Jesko.", "COMPARE", _fresh),
    ("compare-followup-better", "Which one is better?", "COMPARE", _with_history),
    ("compare-followup-faster", "Which is faster?", "COMPARE", _with_history),
    ("compare-followup-lighter", "Which one is lighter?", "COMPARE", _with_history),

    # --- RESEARCH -----------------------------------------------------------
    ("research-explicit", "Research the Bugatti Chiron.", "RESEARCH", _fresh),
    ("research-lookinto", "Look into the engineering behind the Chiron.", "RESEARCH", _fresh),
    ("research-deepdive", "Do a deep dive into the Chiron.", "RESEARCH", _fresh),
    ("research-findout", "Find out how Bugatti engineered the Chiron.", "RESEARCH", _fresh),
    ("research-everything", "Tell me everything about how the Chiron was built.", "RESEARCH", _fresh),
    ("analyze-why", "Why does Bugatti use a W16 engine?", "RESEARCH", _fresh),
    ("analyze-breakdown", "Break down the engineering of the Chiron.", "RESEARCH", _fresh),
    ("analyze-tradeoffs", "What are the trade-offs of the Chiron's design?", "RESEARCH", _fresh),

    # --- FACTUAL ------------------------------------------------------------
    ("factual-engine", "What engine does the Bugatti Chiron use?", "FACTUAL", _fresh),
    ("factual-underhood", "What's under the hood of the Chiron?", "FACTUAL", _fresh),
    ("factual-topspeed", "What is the top speed of the Centodieci?", "FACTUAL", _fresh),
    ("factual-cylinders", "How many cylinders does the Chiron engine have?", "FACTUAL", _fresh),
    ("factual-spec", "Give me the Chiron's engine specification.", "FACTUAL", _fresh),

    # --- VERIFY (needs prior answer in session) -----------------------------
    ("verify-sure", "Are you sure?", "VERIFY", _with_history),
    ("verify-correct", "Is that correct?", "VERIFY", _with_history),
    ("verify-check", "Can you check that again?", "VERIFY", _with_history),
    ("verify-doublecheck", "Double-check those numbers.", "VERIFY", _with_history),
    ("verify-supported", "Is that actually supported by the documents?", "VERIFY", _with_history),
    ("verify-claims", "Verify whether the claims are supported by the retrieved documents.", "VERIFY", _with_history),

    # --- SUMMARY ------------------------------------------------------------
    ("summary-explicit", "Summarize the Chiron documents.", "SUMMARY", _fresh),
    ("summary-tldr", "Give me a tl;dr of the Chiron.", "SUMMARY", _fresh),
]

# Behaviours beyond intent that must hold.
def check_extras():
    failures = []

    # A VERIFY-sounding question with NO previous answer must not become a
    # verification of nothing.
    r = intent.classify("Are you sure?", _fresh())
    if r["target"] == "PREVIOUS_ANSWER":
        failures.append("verify-without-history: should not target PREVIOUS_ANSWER with no prior answer")

    # Follow-up must recover the subject from context.
    r = intent.classify("What about the transmission?", _with_history())
    u = r["understanding"]
    if not u["isFollowUp"]:
        failures.append("followup-detection: 'What about the transmission?' not detected as follow-up")
    if not u["resolvedFromContext"] and "Chiron" not in r["resolved_question"]:
        failures.append(f"followup-resolution: subject not recovered -> {r['resolved_question']!r}")

    # Abbreviation expansion.
    r = intent.classify("What's the hp and vmax of the Chiron?", _fresh())
    if not r["understanding"]["abbreviationsExpanded"]:
        failures.append("abbreviations: hp/vmax not expanded")

    # High-confidence typo correction.
    r = intent.classify("Research the Bugati Chiron.", _fresh())
    if not r["understanding"]["typoCorrections"]:
        failures.append("typos: 'Bugati' not corrected")

    # Ordinary English must NOT be "corrected" into the entity vocabulary.
    r = intent.classify("What are the engineering compromises involved?", _fresh())
    if r["understanding"]["typoCorrections"]:
        failures.append(f"typos: over-corrected ordinary words -> {r['understanding']['typoCorrections']}")

    # Comparison dimension extraction.
    r = intent.classify("Which of the Chiron and Jesko is faster?", _fresh())
    if "PERFORMANCE" not in r["comparison_dimensions"]:
        failures.append(f"dimensions: PERFORMANCE not detected -> {r['comparison_dimensions']}")

    # Complexity separates from intent.
    low = intent.classify("What is the top speed of the Chiron?", _fresh())
    high = intent.classify(
        "Compare the top speed, acceleration, braking and aerodynamics of the Chiron and the Jesko.", _fresh()
    )
    if low["complexity"] != "LOW":
        failures.append(f"complexity: simple factual should be LOW -> {low['complexity']}")
    if high["complexity"] not in ("HIGH", "VERY_HIGH"):
        failures.append(f"complexity: multi-dimension compare should be HIGH/VERY_HIGH -> {high['complexity']}")

    # Task decomposition for a real comparison.
    if len(high["task_plan"]) < 3:
        failures.append(f"task_plan: expected decomposition, got {high['task_plan']}")

    # Small talk must not trigger retrieval.
    r = intent.classify("hello", _fresh())
    if r["requires_retrieval"]:
        failures.append("chitchat: 'hello' should not require retrieval")

    # A real question must ALWAYS require retrieval (grounding guarantee).
    r = intent.classify("What engine does the Chiron use?", _fresh())
    if not r["requires_retrieval"]:
        failures.append("grounding: factual question must require retrieval")

    return failures


def main() -> int:
    passed, failed = 0, []
    for label, question, expected, session_factory in CASES:
        result = intent.classify(question, session_factory())
        actual = result["intent"][0]
        source = result["source"]
        if actual == expected:
            passed += 1
            print(f"  PASS  {label:28} {actual:9} conf={result['confidence']:.2f} src={source}")
        else:
            failed.append((label, question, expected, actual))
            print(f"  FAIL  {label:28} expected {expected}, got {actual} ({question!r}) src={source}")

    print()
    extra_failures = check_extras()
    for message in extra_failures:
        print(f"  FAIL  {message}")
    if not extra_failures:
        print("  PASS  behavioural checks (follow-ups, abbreviations, typos, dimensions, complexity, grounding)")

    total = len(CASES)
    print()
    print(f"intent cases: {passed}/{total} passed; behavioural failures: {len(extra_failures)}")
    return 0 if (passed == total and not extra_failures) else 1


if __name__ == "__main__":
    sys.exit(main())
