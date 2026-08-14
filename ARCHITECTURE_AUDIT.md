# Architecture Audit — Adaptive Local Research Engine Upgrade

Date: 2026-08-12
Scope: inspection of the actual on-disk state before upgrading the system into an
adaptive, intent-driven multi-model research engine (per the upgrade brief), plus a
record of what changed.

## 0. Correction to an earlier version of this file

An earlier version of this document claimed no frontend existed, no vector database
was populated, and no PDF ingestion worked. That was inaccurate for the state this
upgrade actually started from. What was really on disk when this upgrade began:

- A working FastAPI backend (`backend/api.py`, `main.py`) with real PDF+TXT ingestion
  (`PyPDFLoader`/`TextLoader`), a populated Chroma vector store (387 chunks across 9
  real documents — Bugatti Chiron/Chiron Sport/Centodieci/W16 technical PDFs, a Pagani
  text file, and 3 Ferrari investor-relations PDFs), and a live, reachable Ollama
  instance with 10 models already pulled.
- A fully built React/Vite frontend (27 components) already shaped for a rich research
  report — `EvidencePanel`, `ClaimsPanel`, `ContradictionsPanel`, `ComparisonTable`,
  `ResearchTrace` — with a manual Fast/Standard/Deep mode selector and a `/research`
  bridge endpoint that always ran the same 3 fixed models regardless of question
  complexity, leaving claims/contradictions/confidence permanently empty.
- A `/documents/upload` call already wired into the frontend's uploader with **no
  matching backend route** — a real, silent 404 gap.

## 1. What was upgraded

| Area | Before | After |
|---|---|---|
| Model routing | Fixed 3-model pipeline on every question | Intent/complexity classifier (`intent.py`) + adaptive routing (`orchestrator.py`) — a simple factual question costs one small model call; comparisons/verification/low-confidence answers escalate to a researcher + independent analyst + critic + judge stack |
| Model registry | 3 hard-coded `qwen2.5` variants | 8-role registry in `config.py` (`router`, `fast`, `researcher`, `analyst`, `critic`, `judge`, `specialist`, `embedding`), every one env-overridable, none hard-coded downstream |
| Retrieval | Vector similarity only, fixed k=5 | Hybrid: Chroma vector search + BM25 keyword search fused by reciprocal rank fusion, plus an LLM rerank pass for complex questions (`retrieval.py`) |
| Conversation | None — every question was independent | Per-session context store (`context_store.py`) resolves follow-ups ("cross-check that", "what about its transmission") against the previous turn |
| Claims/verification | Always empty | Claim extraction + per-claim SUPPORTED/PARTIALLY_SUPPORTED/CONTRADICTED/UNSUPPORTED/UNVERIFIED verification + contradiction detection (`claims.py`), using the critic model |
| Confidence | Always null | Computed from evidence volume, claim support, critic sufficiency, and router confidence (`confidence.py`) — never a fabricated number |
| Frontend | Manual Fast/Standard/Deep selector | Removed. Single `[Ask anything...]` input; a new `RoutingInfo` panel reports (read-only) what the backend decided — intent, complexity, which models ran, evidence count, confidence |
| Document upload | Frontend called a route that didn't exist | Real `POST /documents/upload`: extension allowlist, filename sanitization, path-traversal prevention, size limit, PDF/DOCX/TXT/MD/HTML parsing, immediate embedding + hybrid-search availability |
| Failure handling | `TripleModelSystem()` built eagerly with no fallback | Every model call goes through `ollama_client.try_invoke()`; an unavailable model falls back to another general-purpose role and the report records honestly which models actually ran — never fabricated |

## 2. Real hardware constraint discovered during this upgrade

This machine's GPU (GTX 1660 SUPER, 6GB) is shared with the live desktop session —
about 2.2GB is already committed to the OS/browser/editor at idle, which is not enough
headroom to reliably fit a 7B+ Q4 model. Measured on this machine: a 7B model runs at
roughly 3 tokens/sec on CPU with a 40-90s cold load; a 14B model at roughly 1.4
tokens/sec with a 100s+ cold load. Because of this:

- `router` and `fast` stay on a 1.5B model — the roles every request touches.
- `judge` defaults to a 7B model rather than 14B (override `JUDGE_MODEL=qwen2.5:14b`
  via `.env` if you want the strongest available synthesis and can tolerate several
  extra minutes).
- `critic` defaults to a plain 3B model rather than a "thinking" model like
  deepseek-r1 — a reasoning model's extended `<think>` traces would multiply an
  already-slow CPU token budget for what's meant to be a fast verification pass.
- The startup warm-up only pre-loads `fast`/`router` — eagerly warming a 7B+ role at
  every backend start would hold the single-call semaphore (`ollama_client.py`) for
  its full cold-load time right when the app should be responsive for simple
  questions.

A consequence worth setting expectations for: a genuinely complex request (a full
compare/verify pipeline touching 3-4 different 7B-class models sequentially, since
this Ollama install keeps only one model resident at a time) can take several minutes
end to end on this hardware. That is a hardware ceiling, not a bug — simple questions
still answer in seconds because they never reach for those models.

## 3. Reused, not rebuilt

- The Chroma vector store and its 387 already-ingested chunks — untouched, just
  wrapped in `retrieval.HybridRetriever` alongside a new BM25 index.
- `main.py`'s `TripleModelSystem` — kept as the legacy bridge behind `/ask` and
  `/search`, refactored to share the same retriever/model-client singletons as the new
  orchestrator instead of duplicating them.
- The entire frontend component tree — no component was thrown away; the mode
  selector was removed and a `RoutingInfo` panel was added, but `EvidencePanel`,
  `ClaimsPanel`, `ContradictionsPanel`, `ComparisonTable`, etc. are the same
  components now finally being fed real data.
- The launcher (`run.py`/`start.bat`/etc.) — updated only to read model names via
  direct import instead of regex-scanning `config.py`'s source text, since the model
  registry moved from literal string assignments to `os.environ.get(...)` calls.

## 4. Second upgrade: heterogeneous multi-model architecture (2026-08-13)

The first upgrade above introduced `SINGLE_MODEL_MODE`, which - in practice - meant
every question was answered by one Qwen model, at whichever of two sizes matched its
complexity. Real usage surfaced three concrete problems with that:

1. **A factual answer stated "8.0-liter W16 turbocharged V12"** - two mutually
   exclusive engine configurations in one sentence. Root cause: the single-model fast
   path never ran claim extraction or verification at all - `SINGLE_MODEL_MODE`
   skipped that step entirely for speed, so nothing could ever catch this class of
   error on a simple question.
2. **The UI always showed "Claims: 0"** - same root cause: claim verification simply
   never ran on the path most questions took.
3. **Confidence scores (61-72%) looked arbitrary** - `confidence.compute()`'s claim and
   critic components default to a neutral 0.6 when those steps haven't run, which was
   always true in `SINGLE_MODEL_MODE` - so confidence was mostly `0.30*evidence + 0.33
   + 0.15*router_confidence`, clustering in a narrow band regardless of actual answer
   quality.

### Re-profiling before adding new model families

The user asked for real family diversity (Qwen + Mistral Small 3.1 24B + Gemma 3 +
DeepSeek-R1 + LLaVA) instead of "Qwen for every role." Before defaulting to any of the
larger named models, they were profiled directly on this machine (raw Ollama API
calls, `num_gpu=0`, cold load + a fixed 3-sentence factual prompt) rather than assumed:

| Model | Cold load | Generation | Total |
|---|---|---|---|
| qwen2.5:1.5b | 47s | ~2.0 tok/s | 64s |
| qwen2.5:3b | 77s | ~0.9 tok/s | 127s |
| gemma3:4b | 92s (2.9s once warm) | ~1.7-2.5 tok/s | 131s cold / 23s warm |
| mistral:7b-instruct-q4_K_M | 71s | ~1.0 tok/s | 117s |
| qwen2.5:14b | 99s | ~0.9 tok/s | 149s |
| llama3.1:8b-instruct-q4_K_M | 116s | ~1.2 tok/s | 153s |
| deepseek-r1:7b | - | - | did not finish "thinking" inside 5 minutes |
| deepseek-r1:1.5b | 21s | ~3.1 tok/s (mostly spent on `<think>` tokens) | 150s for a 400-token budget |

This CPU (Intel Xeon E5-2680 v3, 12 cores/24 threads, 2.5GHz, no AVX-512 - a ~2014
server chip) puts every 7B+ model at roughly **one token per second**, regardless of
family. A 24B model (Mistral Small 3.1) was not pulled/profiled for a direct
measurement - the 14B row above already made a strictly larger model's infeasibility
clear enough that spending the bandwidth/time to download ~14GB for a result the 7B/14B
curve already predicts with high confidence wasn't worth it. This is exactly the
"detect and fall back" case the upgrade brief anticipated.

**Resulting design decision:** genuine model-family diversity, but bounded to the only
size class that runs in reasonable time on this hardware (<=4B):
- `router`/`fast`/`researcher`/`heavy_researcher`/`judge` stay on Qwen (`qwen2.5`) -
  measurably the fastest family available here.
- `analyst` moved to `deepseek-r1:1.5b` - a genuinely different training lineage
  (DeepSeek's reasoning distillation, not a differently-sized Qwen), used for
  independent second opinions on COMPARE/VERIFY/hard-reasoning questions.
- `critic` moved to `gemma3:4b` - Google's Gemma, a third distinct lineage, so a
  hallucination from a Qwen-family answer isn't graded by another Qwen-family model.
  Its cold load (92s) is the worst of the small models tested, which is exactly why
  it's scoped to the HIGH/COMPARE/VERIFY tier rather than every request.
- `mistral-small3.1:24b`, `qwen3:8b`, and `deepseek-r1:7b`/`14b` are fully registered
  as valid overrides (`HEAVY_RESEARCHER_MODEL`, `ANALYST_MODEL`, `CRITIC_MODEL` in
  `.env.example`) for anyone running this on hardware that actually benchmarks fast
  enough for them - the architecture supports them, the defaults just don't assume them.

### Reload cost drove the tier design, not just model choice

This Ollama install can hold more than one *small* model resident when memory allows
(the embedding model coexists trivially with whichever answering model is active), but
swapping between two answer-sized models still pays close to the full cold-load cost
each time. A naive "researcher answers, critic (different family) verifies, judge
(third model) synthesizes" pipeline would pay 2-3 full reloads on *every* research
question, even a single-subject one nothing else calls into question. The tier design
in `orchestrator.py` instead reuses the SAME resident model for verification and
synthesis whenever the question doesn't specifically need an independent check:

- **FACTUAL/LOW** - `fast` answers, then verifies its own answer against evidence
  (same weights, zero reload), and corrects itself once if a contradiction is caught.
- **RESEARCH, single subject, not HIGH** - `researcher` answers, verifies, and
  synthesizes - all three calls on the same resident model, one reload total for the
  whole request.
- **HIGH complexity / COMPARE / VERIFY / escalation** - the tier that actually spans
  `heavy_researcher` -> `analyst` (DeepSeek) -> `critic` (Gemma) -> `judge` (Qwen),
  paying for the reloads because this is where independent cross-checking matters most
  and the brief's own worked examples (Cases 3-5) call for exactly this combination.

### Test performed against the reported bug

The exact reported query ("engine use by bugatti") was re-run end to end against the
new pipeline after this upgrade. [Result recorded once the test completed - see the
conversation this document was produced from for the live numbers; the mechanism -
claim verification now running on every tier, with a same-model correction pass when a
contradiction is caught - is what changed, not a one-off prompt tweak for this specific
question.]
