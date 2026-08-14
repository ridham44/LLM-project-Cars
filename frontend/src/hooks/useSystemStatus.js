import { useEffect, useRef, useState } from "react";
import { getSystemStatus } from "../services/system";

const POLL_INTERVAL_MS = 15000;

const initialState = {
  loading: true,
  backendReachable: false,
  ollamaReachable: false,
  models: {},
  knowledgeBase: { documents: null, chunks: null, ready: false },
};

// Polls the real /health endpoint so the sidebar cards reflect actual
// backend/Ollama/knowledge-base state instead of hard-coded values. Never
// fabricates a status - if the backend is unreachable, everything shows
// offline/unknown rather than a stale or invented "online".
export function useSystemStatus() {
  const [state, setState] = useState(initialState);
  const timerRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const health = await getSystemStatus();
        if (cancelled) return;
        setState({
          loading: false,
          backendReachable: true,
          ollamaReachable: Boolean(health.ollama?.reachable),
          models: health.models || {},
          knowledgeBase: health.knowledge_base || initialState.knowledgeBase,
        });
      } catch {
        if (cancelled) return;
        setState({ ...initialState, loading: false });
      } finally {
        if (!cancelled) {
          timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
        }
      }
    }

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timerRef.current);
    };
  }, []);

  return state;
}
