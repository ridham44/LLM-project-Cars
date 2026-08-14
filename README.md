# Local AI Research Engine

A fully local research assistant that understands what you're asking, decides
how complex the question is, retrieves evidence from your documents, and routes
the request to **exactly one** local model chosen for that question. Everything
runs on this machine - Ollama for generation, spaCy / RapidFuzz / ONNX
sentence-transformers for language understanding. No cloud calls, no API keys.

There is no research-mode picker and no model picker in the UI. You ask a
question; the backend classifies intent and complexity, retrieves evidence,
picks the right model, and reports back exactly what it did.

**One question = one answer model.** Not a researcher followed by a critic
followed by a judge. That architecture was measured on this hardware and
abandoned - see "Why one model" below.

---

## How a question gets answered

```
question
   |
   v
[1] normalization                          ~0.1ms   regex + abbreviation dict
[2] verification-phrase match              ~0.02ms  verify_detect.py, no model
[3] spaCy + RapidFuzz                      ~12ms    entities, typos, units
[4] semantic intent (ONNX MiniLM)          ~25ms    embedding similarity
[5] router LLM (qwen2.5:1.5b)              ~1-2s    ONLY if 2-4 were unsure
   |
   v
intent + complexity + entities + resolved follow-up
   |
   v
MODEL SELECTION (model_router.py) - one tier, one model, latency-checked
   |
   v
retrieval, scoped to the marques the question names:
   local MiniLM embedding -> Chroma vector search  \
                                                    >- RRF -> cross-encoder
   BM25 keyword search                             /       -> top 4-9 chunks
   |
   v
ONE MODEL CALL -> the complete answer
   |
   v
claims parsed from that answer deterministically (no second model),
confidence from evidence volume + relevance + citation rate,
report + a routing panel naming the single model that answered
```

Measured on the reference machine, all models resident: **a factual question
takes 3.3s, a comparison 7.3s.** Query understanding is 0.02-0.10s.

Nothing runs after the answer. A backend restart never crashes if a model is
missing or Ollama is down - `/health` reports what's actually reachable, and
the router falls back down the tiers (reporting the substitution) rather than
failing. Every model call has a hard timeout so a stuck Ollama call fails and
recovers instead of freezing the app.

Conversation follow-ups ("what about its transmission", "compare it with the
Centodieci") are resolved against the previous turn's topic and entities,
tracked per-session in `backend/context_store.py` - deterministically, so a
follow-up never needs a model call to be understood.

---

## Why one model

An earlier version of this system ran `researcher -> analyst -> critic ->
judge` for a comparison, and `answer -> claim extractor -> verifier` for
everything else. Measured per-stage timings from that version:

| Stage | Measured |
|---|---|
| Judge synthesis | 110.8s |
| Researcher model | 90.9s |
| Claim extraction | 90.0s |
| Query understanding | 149.8s |
| Follow-up retrieval | 52.9s |

Four things were wrong, and all four were structural rather than tuning
problems:

1. **Only one model of consequence stays resident on a 6GB shared GPU.** So
   every extra model in a request cost a 21-115s cold load - more than the
   answer itself. A four-model pipeline meant four cold loads.
2. **The judge re-worded an answer another model had already written.** That is
   not verification, it is 110 seconds of paraphrase.
3. **Claim extraction was a model call to list sentences.** It is now done by
   sentence parsing in `claims.py`, deterministically, in microseconds.
4. **Query understanding embedded ~140 intent examples through Ollama on the
   first request**, queueing behind whatever 7B model was generating. Those
   embeddings are now computed locally and cached to disk.

What replaced automatic verification: **verification on request.** If you doubt
an answer - "are you sure?", "check that against the documents", "I think that
answer is wrong" - the whole request routes to a reasoning model
(`deepseek-r1:1.5b`) that re-retrieves evidence and re-examines the answer
independently. That is one model call, it happens when it is actually wanted,
and it is a different model family from the one that wrote the answer.

The honest trade-off: answers are no longer automatically checked. `ClaimsPanel`
therefore reports whether each claim is **tied to specific evidence**, not
whether it was "Supported" - the UI never asserts a check the system didn't
perform.

---

## Hardware reality (read this before changing model defaults)

Reference machine: NVIDIA GTX 1660 SUPER (6GB, **shared with the desktop
session**), Intel Xeon E5-2680 v3, Ollama under WSL2 with CUDA passthrough.

Every installed model benchmarked on the same RAG prompt, via the Ollama API:

| Model | Cold load | tok/s | 400-token answer (warm) |
|---|---|---|---|
| qwen2.5:1.5b | 21.5s | 44.2 | **11.0s** |
| deepseek-r1:1.5b | 39.2s | 42.4 | **11.3s** |
| qwen2.5:3b | 32.1s | 37.8 | **13.1s** |
| gemma3:4b | 94.2s | 29.3 | **16.6s** |
| mistral:7b-instruct-q4_K_M | 56-86s | 7.8 | 141.1s |
| deepseek-r1:7b | 98-111s | 8.1 | 150.5s |
| qwen2.5:7b | 98-115s | 7.9 | 168.3s |
| llama3.1:8b-instruct-q4_K_M | 93-107s | 5.7 | 180.1s |

Three findings drive every model decision here:

**1. No 7B+ model stays resident.** Every model at 7B and above paid a *full*
cold load again on a back-to-back second call (86-115s), while every model at
4B and under reloaded in 1.3-3.4s. So a 7B tier does not cost "7B generation
speed" - it costs a reload plus ~50s of generation, on every single request.
That is why no tier default is a 7B model, and `mistral-small3.1:24b` /
`qwen3:8b` are opt-in overrides only. The router will actively refuse a model it
projects can't meet the tier's latency target (`ENFORCE_LATENCY_TARGETS`).

**2. Retrieval must not depend on Ollama.** Query embedding used to go through
Ollama's `nomic-embed-text`, which Ollama evicts to make room for an answer
model. Measured consequence: a question asked right after one that loaded the
verify model spent **33.17s** in "Candidate Search" reloading the embedder.
Retrieval now embeds in-process (ONNX MiniLM) - the same search costs **0.04s**,
and re-embedding the entire 399-chunk corpus takes 5.4s.

**3. GPU offload is worth ~27x, and was once accidentally disabled.** An earlier
`ollama_client.py` forced `num_gpu=0` on a wrong assumption about VRAM headroom,
making every model ~2 tok/s. If answers feel uniformly slow, check this first:
`ollama ps` should show a non-zero `size_vram`.

### The one remaining latency cliff

Steady state, models resident: factual **3.3s**, research/comparison **7.3s**.
But *switching* tiers costs a cold load, because the GPU holds one model at a
time by default. Measured: a research question right after a factual one took
42.3s (32s loading `qwen2.5:3b`); a factual question right after a verification
took 34.1s because `deepseek-r1:1.5b` had evicted `qwen2.5:1.5b`.

The three tier models total ~4.1GB and *can* coexist in 6GB. Set this in the
**Ollama server's** environment (for WSL, the service environment - not `.env`):

```
OLLAMA_MAX_LOADED_MODELS=3
```

With that set, tier switches stop reloading and every request stays in the 2-8s
range. Without it, expect one slow request after each tier change.

`main.warm_models()` pre-loads `fast` and `research` at startup, off the request
path, since between them they answer almost every question. `verify` is
deliberately *not* warmed - a third resident model risks evicting the two that
answer everything else, and verification is the rarer request.

---

## Model tiers

Every tier is defined in `backend/config.py`'s `MODEL_REGISTRY`, overridable by
environment variable (see `.env.example`). Exactly one of these answers any
given request.

| Tier | Default model | Family | When it's chosen | Measured (resident) |
|---|---|---|---|---|
| `fast` | `qwen2.5:1.5b` | Qwen | FACTUAL + LOW complexity | 3.3s |
| `research` | `qwen2.5:3b` | Qwen | research, analysis, comparisons, summaries | 7.3s |
| `heavy_research` | `qwen2.5:3b` | Qwen | VERY_HIGH complexity only | ~10-15s |
| `verify` | `deepseek-r1:1.5b` | **DeepSeek-R1** | user asked for a recheck | ~2s + load |
| `specialist` | `llava:7b` | LLaVA | registered; nothing routes to it yet | - |
| `router` | `qwen2.5:1.5b` | Qwen | classifies ambiguous questions only | ~1-2s |
| `embedding` | `nomic-embed-text` | Nomic | fallback only - retrieval embeds locally | - |

`heavy_research` defaults to the same model as `research` deliberately: on this
hardware nothing larger meets the latency target, so the tier differs by
*budget* (more evidence chunks, longer answer cap) rather than by model size.
Claiming a bigger model that takes 168s would be worse than admitting there
isn't one.

The `verify` tier is a different family from every answering tier on purpose:
when you challenge an answer, re-running the model that wrote it is the least
useful thing the system could do.

`router` is the only model that can run *besides* the answer model, it only runs
when the phrase and embedding layers were both inconclusive, and the routing
panel labels it as having classified the question and written none of the
answer.

---

## Model routing

Decision table, in priority order (`model_router.select()`):

| Condition | Tier | Example |
|---|---|---|
| explicit verification language | `verify` | "Are you sure? Check that against the documents." |
| FACTUAL / small talk + LOW | `fast` | "What engine does the Chiron use?" |
| VERY_HIGH complexity | `heavy_research` | "Do a very detailed investigation of the Chiron's engineering." |
| everything else | `research` | "Compare Chiron and Jesko." |

**VERIFY wins over everything.** "Can you research that again and verify your
previous answer?" is a VERIFY, not a RESEARCH, even though it says "research" -
the user is challenging an answer, not asking for a new one. This is decided by
phrase matching in `verify_detect.py` against `verification_phrases.json`
(categories: DIRECT_VERIFY, DOUBT, REQUEST_FOR_EVIDENCE, RECHECK,
ERROR_CHALLENGE, NATURAL_LANGUAGE_VARIANTS), before any model or embedding runs
- measured at 15-23ms. Add phrasings to the JSON file, not to code.

**COMPARE routes to `research`, not something heavier.** A comparison is a
harder question for one model, not a reason to run several. The evidence budget
widens for it instead.

**The router is hardware-aware.** Each tier has a latency target
(`TIER_LATENCY_TARGET_SECONDS`) and each model a measured throughput
(`MODEL_THROUGHPUT_TOK_S`). If the configured model is projected over its
target, the router drops to the next tier down and says so in the routing panel:

> a wide-ranging question needing more evidence and a longer answer;
> qwen2.5:7b would take ~63s against a 30s target, so qwen2.5:3b answered instead

Set `ENFORCE_LATENCY_TARGETS=false` to pin a large model regardless.

---

## The local NLP stack

All of it in-process, no API keys (`backend/nlp_local.py`). Steady-state
measurements on the reference machine:

| Layer | Library / model | Cost | Job |
|---|---|---|---|
| 1 | regex + abbreviation dict | ~0.1ms | normalization, unit expansion |
| 2 | `verify_detect.py` | ~0.02ms | verification/doubt phrase match |
| 3 | **spaCy** `en_core_web_sm` | ~12ms | tokens, sentences, NER, noun phrases, measurements, years |
| 3 | **RapidFuzz** | ~0.05ms | typo repair ("Bugati" → Bugatti at 0.92) |
| 4 | **sentence-transformers** `all-MiniLM-L6-v2` (ONNX) | ~25ms | semantic intent similarity |
| 5 | **cross-encoder** `ms-marco-MiniLM-L-6-v2` (ONNX) | ~110ms / 24 passages | retrieval reranking |
| 6 | `qwen2.5:1.5b` | ~1-2s | router LLM, ambiguous questions only |

Two engineering choices worth knowing:

**ONNX runtime, not torch.** The encoder and reranker run through
`onnxruntime`, which `chromadb` already depends on, via `fastembed`. Installing
torch to run two 22M-parameter models would add ~2GB for no measurable quality
gain here.

**Every layer is optional at runtime.** If spaCy's model isn't downloaded or
fastembed's weights aren't cached, that layer reports itself unavailable and the
pipeline uses the layer above it. `/health` exposes which layers are live, so a
missing model is visible rather than silently making classification blunter.

Intent thresholds are **measured for MiniLM**, not carried over from
`nomic-embed-text`: correctly classified queries land at 0.36-0.55 top
similarity on this catalog, where the previous nomic-tuned floor of 0.62 would
have called every one of them uncertain and escalated to the router LLM. A
near-tie is also treated as decisive when both candidates map to the *same*
tier - RESEARCH 0.416 vs ANALYZE 0.396 is not a routing ambiguity, so spending
a model call to pick between two identical outcomes is waste.

Example embeddings are computed once and cached to `.intent_vectors.json`, keyed
by a hash of the taxonomy plus the encoder name, so editing the examples or
switching encoders invalidates the cache automatically.

---

## Marque-scoped retrieval

A question naming only Bugatti searches Bugatti documents; naming a Bugatti and
a Ferrari searches both; naming nobody searches everything. Without this, BM25
returned Ferrari financial tables for Chiron questions purely because the
Ferrari filings dominate this corpus by page count - measured on the top 25
candidates for "top speed and horsepower of the Chiron Super Sport":

| | Bugatti | Pagani | Ferrari |
|---|---|---|---|
| unscoped | 8 | **15** | 2 |
| scoped | **25** | 0 | 0 |

A document whose filename identifies no marque is **never** filtered out (a
wrong exclusion silently hides evidence), and if a scope returns nothing the
search widens to everything and says so in the trace and the routing panel.

---

## Project structure

```
backend/
  api.py            FastAPI app: /health, /research, /documents/upload, /ask, /search (legacy)
  config.py         Tier registry, measured throughput table, latency targets (env-overridable)
  orchestrator.py   The pipeline - understand, select ONE model, retrieve, answer
  model_router.py   Picks THE model from intent + complexity, latency- and install-aware
  intent.py         Layered classifier: phrases -> spaCy/RapidFuzz -> embeddings -> router LLM
  verify_detect.py  Verification/doubt phrase matching, no model calls
  verification_phrases.json   The doubt/recheck vocabulary (edit this, not the code)
  nlp_local.py      spaCy + RapidFuzz + ONNX encoder + ONNX cross-encoder, all in-process
  semantic_intent.py  Intent similarity against the disk-cached example catalog
  intent_taxonomy.py  Intent/dimension examples, entity vocabulary, marque mappings
  retrieval.py      Chroma vector search + BM25 + RRF + local cross-encoder rerank
  agents.py         The single answer call (prose, one round trip)
  claims.py         Claims parsed from the answer text - no model call
  confidence.py     Report confidence from evidence volume, relevance and citation rate
  context_store.py  Per-session conversation memory for follow-up resolution
  ollama_client.py  Single entry point for every model call, by tier
  main.py           Startup warm-up + legacy /ask and /search bridge
  load_docs.py      Document parsing (PDF/DOCX/TXT/MD/HTML) + chunking + marque stamping
  models.py         Pydantic request/response schemas
  Documents/        Source documents (Bugatti technical PDFs, Ferrari filings, Pagani text)
  chroma_db/        Persisted vector store, namespaced per encoder
  .intent_vectors.json   Cached intent example embeddings

frontend/
  src/components/   ResearchWorkspace, ChatHistory, ResearchComposer, ResearchReportView,
                     EvidencePanel, ClaimsPanel, ComparisonTable,
                     RoutingInfo (the single model that answered), ResearchTrace, ...
  src/hooks/        useResearch, useChats, useSystemStatus
  src/utils/        chats.js (conversation persistence), format.js
  src/services/     api.js, research.js, documents.js, system.js

run.py / start.bat / setup.bat / stop.bat / restart.bat / start.sh
  Unified launcher - starts Ollama, backend, and frontend, with real health checks.
```

---

## Quick start

1. Run `setup.bat` once (creates the backend venv, installs frontend deps,
   creates `.env`, checks/pulls the models configured in `backend/config.py`).
2. Run `start.bat`.
3. The browser opens automatically once everything is actually healthy.

See **[RUNNING.md](RUNNING.md)** for flags, logs, and troubleshooting.

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

---

## API

The frontend sends only the question (and a session id for follow-up
resolution):

```
POST /research
{ "question": "Compare the Chiron and the Centodieci.", "session_id": "..." }
```

No `mode`, `model`, or `research_type` field exists - the backend decides all of
that. The response includes `summary`, `evidence`, `claims`, `sources`,
`metrics` (including `confidence`, `confidenceLabel` and per-stage `timings`),
`trace` (the steps actually executed), and `routing`:

- `answerModel` / `answerTier` - **the** model that answered
- `modelsUsed` - one entry for the answer, plus the router only if it ran
- `distinctModelCount` - so N calls to one model can never read as N-model verification
- `documentScope` / `documentScopeRelaxed` - which marques were searched
- `explanation` - one sentence naming the model and why it was picked
- `intent`, `complexity`, `evidenceCount`, `confidence`, `confidenceLabel`

`confidenceLabel` (Low/Moderate/High/Very High) is what the UI leads with; the
numeric `confidence` is supporting detail - see `confidence.py` for why a bare
percentage overstates the precision of the underlying signals. It describes the
**grounding available to the answer**, not a check performed on it.

For every request the log line records `selected_model=` and the per-stage
breakdown, e.g.:

```
research 4f2a…: intent=['FACTUAL'] complexity=LOW selected_model=qwen2.5:1.5b
evidence=4 total=3.3s (Query Understanding 0.1s, Model Selection 0.2s,
Candidate Search 0.0s, Reranking 0.3s, Answer 2.2s)
```

Other endpoints:
- `POST /documents/upload` - upload a PDF/DOCX/TXT/MD/HTML file; it's
  parsed, chunked, embedded, and immediately searchable.
- `GET /health` - Ollama reachability, per-tier model availability,
  knowledge-base status, and which local NLP layers are live (never faked;
  genuinely checked on each call).
- `POST /ask`, `POST /search` - legacy endpoints kept for backward
  compatibility. `/ask` answers with the single `fast` model; its response keeps
  the old three-field shape, repeating that one answer rather than fabricating
  two more.

---

## Configuration

Ports, Ollama host, and launcher behavior live in `.env` (copy from
`.env.example`). Tier model overrides live there too - see the commented
`*_MODEL` variables. Nothing needs editing in code to change which model
handles a tier.

The one setting outside `.env` worth changing is
`OLLAMA_MAX_LOADED_MODELS=3` in the **Ollama server's** environment - it removes
the tier-switch reload described under "Hardware reality".

---

## Dependencies

Backend (`backend/requirements.txt`): FastAPI, LangChain (+ Ollama/Chroma
integrations), ChromaDB, `rank_bm25` (keyword retrieval), `pypdf`,
`python-docx`, `beautifulsoup4` (document parsing), `python-multipart`
(file uploads), Pydantic.

Local NLP stack: **spaCy** (+ `en_core_web_sm`, installed separately by
`setup.bat` because it ships as a GitHub release asset, not on PyPI),
**RapidFuzz**, and **fastembed** - which runs the MiniLM encoder and the
ms-marco cross-encoder on `onnxruntime`. `numpy<2.0.0` is pinned because
fastembed's own resolver would otherwise pull numpy 2.x, which langchain 0.3.1
forbids.

Model weights are downloaded once and cached (`~/.cache/huggingface` for the
ONNX models). If they aren't present, those layers report themselves unavailable
in `/health` and the pipeline degrades to the layer above rather than failing.

Frontend (`frontend/package.json`): React + Vite, no other runtime
dependencies.

External: Python 3.10+, Node.js + npm, [Ollama](https://ollama.ai).

---

## Troubleshooting

See **[RUNNING.md](RUNNING.md)**. Logs live in `logs/` (`launcher.log`,
`backend.log`, `frontend.log`, `ollama.log`).

- **One slow request after a tier change is expected.** Switching from the fast
  model to the research model (or to the verify model) costs a 21-39s cold load
  on 6GB, then everything on that tier is fast again. Set
  `OLLAMA_MAX_LOADED_MODELS=3` on the Ollama server to remove it - see "Hardware
  reality".
- **Check the per-stage timings first.** `metrics.timings` and the "Where the
  time went" panel break every request into Query Understanding / Model
  Selection / Candidate Search / Reranking / Answer, with a total. If any stage
  other than `Answer` is above ~0.5s, that is the bug - understanding should be
  0.02-0.10s and retrieval 0.04-0.35s.
- **If query understanding is slow**, `/health`'s `nlp` block will show which
  layer is missing. A `spacy` or `intentEncoder` of `unavailable` means the
  pipeline fell back to the Ollama embedder, which queues behind generation.
  Re-run `python -m spacy download en_core_web_sm` in the backend venv.
- **If a question seems mis-routed**, the routing panel names the tier and the
  reason. Classification is decided by phrases → embeddings → (rarely) the
  router LLM; `source` in the log line says which layer decided. For a
  verification phrasing that wasn't recognised, add it to
  `backend/verification_phrases.json` - no code change needed.
- If a model call ever hangs it times out per tier (120-300s) and the app
  recovers, though a stuck request still delays whatever queues behind it.
- **If an answer states a number that isn't in the evidence panel**, note that
  answers are no longer automatically verified. Ask "are you sure? check that
  against the documents" - that routes the whole question to `deepseek-r1:1.5b`,
  which re-retrieves the evidence and re-examines the answer independently.
  `ClaimsPanel` shows which claims were tied to evidence, which is the fastest
  way to spot an uncited assertion.
- If the backend seems to be running old behavior after an edit, confirm
  which process actually owns port 8000
  (`Get-CimInstance Win32_Process -Filter "Name='python.exe'"` on Windows) -
  a previous instance that didn't fully exit will keep serving stale code.
