import { apiGet, apiPost } from "./api";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const POLL_INTERVAL_MS = 1500;
const POLL_TIMEOUT_MS = 10 * 60 * 1000;

// Submits a research request. The backend alone decides intent, complexity,
// retrieval and model routing (see backend/orchestrator.py) - the frontend
// sends only the question and a session id for follow-up resolution, never
// a mode/model choice. If the backend answers synchronously with a
// completed report, that is returned directly. If it answers with
// {id, status: "processing"|...}, the caller should poll pollResearch(id)
// for progress until status is "completed" or "error".
export function submitResearch({ question, sessionId }) {
  return apiPost("/research", { question, session_id: sessionId });
}

export function getResearch(id) {
  return apiGet(`/research/${id}`);
}

export function getResearchHistory() {
  return apiGet("/research/history");
}

// Polls GET /research/{id} until the backend reports completion, invoking
// onUpdate with every intermediate payload so the trace/status panel can
// reflect real backend progress. This is the fallback path for when the
// backend has not implemented SSE/WebSocket streaming yet (see
// useResearchStream, which prefers a live stream when available).
export async function pollResearch(id, { onUpdate, signal } = {}) {
  const startedAt = Date.now();

  while (true) {
    if (signal?.aborted) {
      throw new DOMException("Research polling aborted", "AbortError");
    }
    if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
      throw new Error("Research timed out waiting for the backend to finish.");
    }

    const result = await getResearch(id);
    onUpdate?.(result);

    if (result.status === "completed" || result.status === "error") {
      return result;
    }

    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }
}

// Opens a live event stream for a research run's trace/status updates, for
// backends that implement SSE at GET /research/{id}/stream. Not currently
// used by useResearch (the backend doesn't emit SSE yet) -- this exists so
// the streaming architecture is ready to swap in without a redesign; see
// hooks/useResearchStream.js. Returns a cleanup function.
export function openResearchStream(id, { onMessage, onError } = {}) {
  const source = new EventSource(`${API_BASE_URL}/research/${id}/stream`);

  source.onmessage = (event) => {
    try {
      onMessage?.(JSON.parse(event.data));
    } catch (err) {
      onError?.(err);
    }
  };

  source.onerror = (event) => {
    onError?.(event);
    source.close();
  };

  return () => source.close();
}
