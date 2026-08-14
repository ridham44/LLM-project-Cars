"""The single answer call. One user question, one model, one call.

There is deliberately no researcher/analyst/critic/judge split in here any
more. Whichever tier model_router picked produces the entire user-visible
result - prose answer, findings, the claims it relied on, and a comparison
table when the question asked for one - in ONE round trip. Nothing runs after
it.

EVERY tier answers in PROSE, not JSON. That is a measured decision, not a
simplification: asked for a JSON schema, qwen2.5:3b and deepseek-r1:1.5b both
returned the schema itself with the placeholder text still in it -

    {"answer": "the complete answer to the question, written for the user to
     read", "findings": [{"text": "a specific point grounded in the evidence"}]}

- which is a broken answer shown to the user. Models in the 1.5-3B class that
this hardware can run fast enough do not follow a multi-field schema reliably,
and the tiers that could are the 7B models that take 150s per answer here.

So the model writes an answer, and the structured extras the UI wants (the
claims list) are derived from that text by deterministic parsing in claims.py.
That costs nothing, cannot echo a schema back, and keeps the rule intact: one
model call per request.
"""

import re
from dataclasses import dataclass

import model_router
import ollama_client

GROUNDING_RULE = (
    "Answer using only the facts stated in the evidence below. Do not add names, "
    "models, numbers, or details that are not explicitly present in the evidence. "
    "Never blend two different specifications together - state exactly what the "
    "evidence says, nothing more. If the evidence does not contain enough "
    "information to answer, say so explicitly."
)


@dataclass
class AnswerResult:
    """The result of the one model call."""

    role: str
    model: str
    ran: bool
    summary: str | None = None
    error: str | None = None


def format_evidence(evidence: list[dict], max_excerpt_chars: int | None = None) -> str:
    if not evidence:
        return "No relevant documents were found in the knowledge base."
    lines = []
    for item in evidence:
        title = item.get("documentTitle", "unknown source")
        page = item.get("page")
        loc = f" (page {page})" if page else ""
        excerpt = item.get("excerpt", "")
        if max_excerpt_chars:
            excerpt = excerpt[:max_excerpt_chars]
        lines.append(f"[{item['id']}] {title}{loc}: {excerpt}")
    return "\n".join(lines)


_FAST_PROMPT = """Use only the evidence below. Don't add facts that are not stated in it. If the evidence doesn't answer the question, say so.

Evidence:
{evidence}

Question: {question}

Give a short, direct answer:"""


_ANSWER_PROMPT = """{grounding}

Evidence:
{evidence}

Question: {question}

{task}"""


_TASK_RESEARCH = (
    "Write a thorough but focused answer grounded in the evidence - a few solid paragraphs, not an "
    "exhaustive report. Cite the evidence you rely on inline like [e1]. If the evidence doesn't cover "
    "part of the question, say which part is missing rather than filling it in."
)

_TASK_COMPARE = (
    "Compare the subjects against each other using the evidence. Go category by category (engine, "
    "performance, weight, and any others the evidence covers), and for each one state what the evidence "
    "says about each subject. Cite evidence inline like [e1]. Where the evidence covers one subject but "
    "not the other, say so explicitly instead of guessing."
)

_TASK_VERIFY = """You are re-examining an answer the user has challenged. Here is the answer under review:

--- ANSWER UNDER REVIEW ---
{previous_answer}
--- END ---

Read the evidence above independently and decide whether that answer holds up. Go through its specific claims and, for each, say whether the evidence SUPPORTS it, does NOT MENTION it, or CONTRADICTS it - citing the evidence id like [e1]. Then give your verdict: if the answer was right, say so; if it was wrong or unsupported, give the corrected answer. Do not simply repeat the answer under review."""


def strip_reasoning(text: str) -> str:
    """Removes a reasoning model's <think> block from user-facing prose. The
    thinking is real work but it isn't the answer, and showing it as one reads
    as the model rambling."""
    if not text:
        return ""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    if "<think>" in cleaned:
        cleaned = cleaned.split("<think>", 1)[0]
    return cleaned.strip()


def run_answer(
    role: str,
    question: str,
    evidence: list[dict],
    *,
    want_comparison: bool = False,
    previous_answer: str | None = None,
) -> AnswerResult:
    """THE model call - the only one in a request. `role` is whatever
    model_router.select() returned."""
    model_name = ollama_client.model_name_for(role)
    num_predict = model_router.NUM_PREDICT.get(role, 400)
    timeout = model_router.TIMEOUT_SECONDS.get(role, 240)

    if role == "low":
        # Tighter prompt and shorter excerpts: the LOW tier exists to be fast,
        # and it answers one narrow question where a long prompt buys nothing.
        prompt = _FAST_PROMPT.format(
            evidence=format_evidence(evidence, max_excerpt_chars=320), question=question
        )
    else:
        if previous_answer:
            task = _TASK_VERIFY.format(previous_answer=previous_answer.strip()[:1500])
        elif want_comparison:
            task = _TASK_COMPARE
        else:
            task = _TASK_RESEARCH
        prompt = _ANSWER_PROMPT.format(
            grounding=GROUNDING_RULE,
            evidence=format_evidence(evidence),
            question=question,
            task=task,
        )

    text, error = ollama_client.try_invoke(role, prompt, num_predict=num_predict, timeout_seconds=timeout)
    if error:
        return AnswerResult(role=role, model=model_name, ran=False, error=str(error))

    return AnswerResult(role=role, model=model_name, ran=True, summary=strip_reasoning(text))
