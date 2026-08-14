"""In-memory async job store for progressive research results.

POST /research returns a job id immediately instead of blocking for the
full pipeline; a background thread keeps calling orchestrator.run()'s
on_progress hook as real checkpoints are reached (answer produced,
verification complete, ...), and GET /research/{id} always returns
whatever the job's latest state is. Not persisted - a backend restart
drops in-flight jobs, same as every other in-memory store in this app
(context_store.py).
"""

import threading
import time
import uuid

JOB_TTL_SECONDS = 60 * 30

_lock = threading.Lock()
_jobs: dict[str, dict] = {}


def _evict_expired(now: float) -> None:
    expired = [job_id for job_id, job in _jobs.items() if now - job["updated_at"] > JOB_TTL_SECONDS]
    for job_id in expired:
        del _jobs[job_id]


def create(question: str) -> str:
    job_id = str(uuid.uuid4())
    now = time.time()
    with _lock:
        _evict_expired(now)
        _jobs[job_id] = {"id": job_id, "question": question, "status": "processing", "report": None, "updated_at": now}
    return job_id


def update(job_id: str, *, status: str, report: dict | None) -> None:
    now = time.time()
    with _lock:
        if job_id not in _jobs:
            return
        _jobs[job_id]["status"] = status
        _jobs[job_id]["report"] = report
        _jobs[job_id]["updated_at"] = now


def get(job_id: str) -> dict | None:
    with _lock:
        _evict_expired(time.time())
        job = _jobs.get(job_id)
        return dict(job) if job else None
