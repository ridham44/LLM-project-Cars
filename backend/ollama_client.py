"""Single entry point for every local model call in the system.

Every other module (agents, intent classifier, retrieval reranker, claim
verifier) calls models through here, by *role* (see config.MODEL_REGISTRY),
never by hard-coded model name. That keeps model choice fully centralized in
config.py and lets every caller degrade gracefully - see try_invoke() - so
one unavailable model never crashes the whole research request.
"""

import threading

from langchain_ollama import OllamaLLM

import config

# Ollama's default keep_alive (5 min) unloads a model between requests,
# forcing a full disk reload on the next call. keep_alive keeps it resident
# longer.
#
# GPU: an earlier version of this file forced num_gpu=0 (pure CPU) based on
# an assumption that the shared 6GB GPU never had enough free VRAM to be
# worth it. That assumption was WRONG and measurably so: with num_gpu
# unset (Ollama auto-detects how many layers fit in currently-free VRAM),
# qwen2.5:1.5b measured ~55 tok/s on this machine's real, current VRAM
# headroom, versus ~2 tok/s forced onto CPU - a ~27x difference. Ollama
# already handles the "not enough VRAM right now" case gracefully (it
# offloads however many layers fit and runs the rest on CPU, rather than
# failing outright), so leaving num_gpu unset lets it use the GPU whenever
# there's room and degrade automatically when another app (browser,
# desktop compositor) is using more of the shared 6GB at that moment.
#
# num_predict caps worst-case latency: without it, a model asked for a
# "thorough" answer can ramble for well past a thousand tokens. Even at
# GPU speeds that's real time for no benefit, and a CPU fallback (VRAM
# fully claimed by something else) still needs this cap - see config.py's
# model registry comment for the CPU-only numbers this was tuned against.
DEFAULT_NUM_PREDICT = 140
# A hung/stalled Ollama call previously blocked every future request forever
# (the single-call semaphore below never got released) - observed live, not
# hypothetical. Every call now has a hard timeout so a stuck request fails
# honestly and frees the semaphore instead of freezing the whole system.
# Short by default so a same-model call (fast/router/the LOW-tier's own
# verification) fails fast if genuinely stuck; call sites for the heavier
# roles (researcher/heavy_researcher/analyst/critic/judge) pass a longer
# one, both because those calls can legitimately take longer and as a
# safety margin for whenever VRAM is tight enough that a role falls back to
# CPU speeds for that particular call.
DEFAULT_TIMEOUT_SECONDS = 90
# keep_alive=-1 means "never unload this model". Cold-loading a model on
# this machine costs 70-120s (see config.py's measurements) - by far the
# largest single cost in a request - so paying it once at startup
# (main.warm_models) and never again is worth far more than any prompt or
# token-cap tuning. Ollama still bounds total residency via
# OLLAMA_MAX_LOADED_MODELS (default 3) and degrades to partial CPU offload
# under VRAM pressure rather than failing, so this is safe on a shared GPU.
# A long explicit duration rather than -1 ("forever"): observed live that a
# model loaded with keep_alive=-1 through this client was still evicted
# within a minute, so the sentinel wasn't surviving the trip to Ollama.
# "24h" is an unambiguous duration string that Ollama definitely honors, and
# is effectively "forever" for a local dev/research session.
LLM_KWARGS = {"base_url": config.OLLAMA_BASE_URL, "keep_alive": "24h"}

# Concurrent calls to *different* models thrash (unload/reload) rather than
# parallelizing on a single shared GPU, so every call is serialized through
# this semaphore. Raise MAX_CONCURRENT_OLLAMA_REQUESTS via env if
# OLLAMA_NUM_PARALLEL is configured higher on the target machine.
_SEMAPHORE = threading.Semaphore(config.MAX_CONCURRENT_OLLAMA_REQUESTS)

_cache_lock = threading.Lock()
_llm_cache: dict[tuple[str, int, int], OllamaLLM] = {}

_availability_lock = threading.Lock()
_available_models: set[str] | None = None


def _fetch_installed_models() -> set[str] | None:
    """Asks Ollama what is actually installed (GET /api/tags). Returns None
    if Ollama can't be reached at all - which is different from "reached it
    and the model isn't there", and callers must not treat an unreachable
    Ollama as proof a model is missing."""
    import json
    import urllib.request

    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request(f"{config.OLLAMA_BASE_URL}/api/tags")
        with opener.open(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    return {m.get("name", "") for m in data.get("models", [])}


def installed_models(refresh: bool = False) -> set[str] | None:
    """Cached view of what Ollama has installed. Cached because routing
    consults it per request and the answer only changes when someone pulls
    or removes a model; pass refresh=True after a known change."""
    global _available_models
    with _availability_lock:
        if _available_models is None or refresh:
            _available_models = _fetch_installed_models()
        return _available_models


def is_model_installed(model_name: str) -> bool | None:
    """True/False if Ollama was reachable, None if it wasn't (unknown, not
    "missing") - so the caller can report honestly instead of blaming a
    model for an Ollama outage. Matches on the exact tag or the base name,
    since `ollama list` reports e.g. "qwen2.5:7b" and a config value might
    omit the tag."""
    available = installed_models()
    if available is None:
        return None
    base = model_name.split(":")[0]
    return any(a == model_name or a.split(":")[0] == base for a in available)


class ModelUnavailableError(RuntimeError):
    def __init__(self, role: str, model_name: str, cause: Exception):
        super().__init__(f"Model role '{role}' ({model_name}) failed: {cause}")
        self.role = role
        self.model_name = model_name
        self.cause = cause


def model_name_for(role: str) -> str:
    name = config.MODEL_REGISTRY.get(role)
    if not name:
        raise ValueError(f"Unknown model role: {role}")
    return name


# Ollama's default temperature (~0.8) is tuned for varied free-text
# generation, not for reliably reproducing an exact JSON schema - observed
# live: the same verification prompt to the same small model sometimes
# returns clean JSON and sometimes adds extra unrequested keys or drifts
# from the schema, purely from sampling variance. Structured-output callers
# (intent classification, claim extraction/verification) pass this instead.
JSON_TEMPERATURE = 0.15


def _llm_for(model_name: str, num_predict: int, timeout_seconds: int, temperature: float | None) -> OllamaLLM:
    key = (model_name, num_predict, timeout_seconds, temperature)
    with _cache_lock:
        llm = _llm_cache.get(key)
        if llm is None:
            kwargs = dict(LLM_KWARGS)
            if temperature is not None:
                kwargs["temperature"] = temperature
            llm = OllamaLLM(
                model=model_name,
                num_predict=num_predict,
                client_kwargs={"timeout": timeout_seconds},
                **kwargs,
            )
            _llm_cache[key] = llm
        return llm


def invoke(
    role: str,
    prompt: str,
    *,
    num_predict: int = DEFAULT_NUM_PREDICT,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    temperature: float | None = None,
) -> str:
    """Call the model registered for `role`. Raises ModelUnavailableError on
    any failure (unreachable Ollama, model not pulled, a stuck call that hit
    `timeout_seconds`, etc) - callers that can degrade gracefully should use
    try_invoke() instead. `num_predict` lets a caller ask for more headroom
    (e.g. a JSON response that needs to stay intact); `timeout_seconds`
    lets a caller in the slower adaptive multi-model path ask for more time
    than the default before being treated as stuck; `temperature` overrides
    Ollama's default sampling temperature (see JSON_TEMPERATURE above)."""
    model_name = model_name_for(role)
    llm = _llm_for(model_name, num_predict, timeout_seconds, temperature)
    try:
        with _SEMAPHORE:
            return llm.invoke(prompt)
    except Exception as exc:
        raise ModelUnavailableError(role, model_name, exc) from exc


def try_invoke(
    role: str,
    prompt: str,
    *,
    num_predict: int = DEFAULT_NUM_PREDICT,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    temperature: float | None = None,
) -> tuple[str | None, ModelUnavailableError | None]:
    """Never raises. Returns (text, None) on success or (None, error) on
    failure, so a step that couldn't run is recorded as skipped rather than
    crashing the whole research request or silently fabricating output."""
    try:
        return invoke(role, prompt, num_predict=num_predict, timeout_seconds=timeout_seconds, temperature=temperature), None
    except ModelUnavailableError as exc:
        return None, exc
    except Exception as exc:  # pragma: no cover - defensive: an unknown role, etc.
        return None, ModelUnavailableError(role, config.MODEL_REGISTRY.get(role, "?"), exc)
