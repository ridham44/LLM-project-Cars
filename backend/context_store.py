"""In-memory, per-session conversation state.

Holds just enough about the last turn for follow-up resolution ("cross-check
that", "what about its transmission", "compare it with Jesko") - not a full
transcript, and not persisted to disk. The frontend's local research history
(useHistory.js) already covers "show me past reports"; this store exists
purely so intent.py can resolve pronouns/ellipsis against what the
conversation was actually about.
"""

import threading
import time
from dataclasses import dataclass, field

import config


@dataclass
class SessionState:
    last_question: str | None = None
    last_resolved_question: str | None = None
    last_answer_summary: str | None = None
    last_report_id: str | None = None
    last_intent: list = field(default_factory=list)
    entities: list = field(default_factory=list)          # most recently discussed entities, most-recent-first
    active_comparison: list = field(default_factory=list)  # entities under active comparison, if any
    last_claims: list = field(default_factory=list)
    last_evidence: list = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)


_lock = threading.Lock()
_sessions: dict[str, SessionState] = {}


def _evict_expired(now: float) -> None:
    expired = [sid for sid, state in _sessions.items() if now - state.updated_at > config.SESSION_TTL_SECONDS]
    for sid in expired:
        del _sessions[sid]


def get(session_id: str | None) -> SessionState:
    """Never raises - an unknown or missing session id just behaves like the
    start of a new conversation."""
    now = time.time()
    with _lock:
        _evict_expired(now)
        if not session_id:
            return SessionState()
        return _sessions.get(session_id) or SessionState()


def update(session_id: str | None, **fields) -> None:
    if not session_id:
        return
    now = time.time()
    with _lock:
        _evict_expired(now)
        state = _sessions.get(session_id) or SessionState()
        for key, value in fields.items():
            setattr(state, key, value)
        state.updated_at = now
        _sessions[session_id] = state
