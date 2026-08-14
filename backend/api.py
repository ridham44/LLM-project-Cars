import json
import os
import re
import threading
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

import config
import jobs
import load_docs
import nlp_local
import orchestrator
from main import TripleModelSystem
from models import (
    AskRequest,
    AskResponse,
    DocumentUploadResponse,
    HealthResponse,
    KnowledgeBaseStatus,
    ModelStatus,
    OllamaStatus,
    ResearchRequest,
    SearchRequest,
    SearchResponse,
)

app = FastAPI(title="Local AI Research Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

system = TripleModelSystem()

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_filename(name: str) -> str:
    # os.path.basename() alone strips any ../ or absolute-path components -
    # the regex pass then narrows to a conservative safe character set.
    base = os.path.basename(name or "upload")
    base = _SAFE_FILENAME_RE.sub("_", base).strip("._") or "upload"
    return base[:200]


@app.on_event("startup")
def _warm_models_in_background():
    # Loading a model into Ollama takes tens of seconds on this machine. Do
    # it once here, off the request path, so the first real question
    # doesn't pay that cost - without blocking startup (the launcher polls
    # /health for readiness).
    threading.Thread(target=system.warm_models, daemon=True).start()


# Ollama runs on localhost. Windows' urllib consults the system/registry
# proxy configuration by default, and a proxy that doesn't cleanly bypass
# localhost can make a genuinely running Ollama look unreachable. Force
# no-proxy for this check.
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _configured_models() -> dict[str, str]:
    return {
        key: value
        for key, value in vars(config).items()
        if key.endswith("_MODEL") and isinstance(value, str)
    }


def _ollama_status() -> tuple[OllamaStatus, list[str]]:
    try:
        req = urllib.request.Request(f"{config.OLLAMA_BASE_URL}/api/tags")
        with _NO_PROXY_OPENER.open(req, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        available = [m.get("name", "") for m in data.get("models", [])]
        return OllamaStatus(reachable=True), available
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return OllamaStatus(reachable=False), []


def _model_available(model_name: str, available: list[str]) -> bool:
    base = model_name.split(":")[0]
    return any(a == model_name or a.split(":")[0] == base for a in available)


@app.get("/health", response_model=HealthResponse)
def health():
    ollama_status, available_models = _ollama_status()
    models_status = {
        var: ModelStatus(
            name=name,
            available=_model_available(name, available_models) if ollama_status.reachable else None,
        )
        for var, name in _configured_models().items()
    }
    kb_status = system.retriever.knowledge_base_status()
    return HealthResponse(
        status="ok",
        ollama=ollama_status,
        models=models_status,
        knowledge_base=KnowledgeBaseStatus(**kb_status),
        # Which local NLP layers are live (spaCy, the intent encoder, the
        # cross-encoder). Reported so a model that failed to download shows up
        # here instead of silently making classification blunter.
        nlp=nlp_local.status(),
    )


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")
    result = system.ask(request.question)
    return AskResponse(**result)


@app.post("/search", response_model=SearchResponse)
def search(request: SearchRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")
    results = system.search(request.question)
    return SearchResponse(results=results)


@app.post("/research")
def research(request: ResearchRequest):
    """The single entry point the frontend calls for every question. The
    backend alone decides intent, complexity, retrieval, which models (if
    any beyond the fast/router pass) are warranted, and how the answer
    should be shaped - see orchestrator.py. No mode/model/research_type is
    accepted from the client.

    Returns immediately with a job id rather than blocking for the full
    pipeline - a verified answer legitimately takes 50s+ on modest
    hardware (see README.md's "Hardware reality"), and a client that
    blocked for that made the fast tier feel broken even once it was
    fixed. The frontend polls GET /research/{id}, which starts returning a
    real (already evidence-grounded) answer as soon as orchestrator.run()'s
    on_progress hook fires, well before verification finishes."""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    job_id = jobs.create(request.question)

    def worker():
        def on_progress(partial_report):
            jobs.update(job_id, status="processing", report=partial_report)

        try:
            report = orchestrator.run(request.question, request.session_id, on_progress=on_progress)
            jobs.update(job_id, status=report.get("status", "completed"), report=report)
        except Exception as exc:  # pragma: no cover - defensive: report the failure, don't hang the poller forever
            jobs.update(job_id, status="error", report={"id": job_id, "question": request.question, "error": str(exc)})

    threading.Thread(target=worker, daemon=True).start()
    return {"id": job_id, "status": "processing"}


@app.get("/research/{job_id}")
def get_research(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="No research job with that id (it may have expired).")
    payload = dict(job["report"]) if job["report"] else {}
    payload["id"] = job_id
    payload["status"] = job["status"]
    return payload


@app.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...)):
    original_name = file.filename or "upload"
    suffix = Path(original_name).suffix.lower()
    if suffix not in load_docs.SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix or '(none)'}")

    body = await file.read()
    if not body:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).")

    config.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_filename(original_name)
    dest = config.DOCUMENTS_DIR / safe_name
    counter = 1
    while dest.exists():
        dest = config.DOCUMENTS_DIR / f"{Path(safe_name).stem}_{counter}{Path(safe_name).suffix}"
        counter += 1
    dest.write_bytes(body)

    try:
        chunks = load_docs.parse_and_chunk(dest)
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Could not parse document: {exc}") from exc

    if not chunks:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="No extractable text found in document.")

    system.retriever.add_documents(chunks)
    return DocumentUploadResponse(status="indexed", filename=dest.name, chunks_added=len(chunks))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
