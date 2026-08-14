import { useEffect, useState } from "react";
import { openResearchStream } from "../services/research";

// Optional live-update source for a research run, for backends that expose
// SSE at GET /research/{id}/stream. Not wired into useResearch by default --
// the backend currently only supports polling -- but a component can opt in
// once the backend adds streaming, without any other frontend changes.
export function useResearchStream(id, { enabled = false } = {}) {
  const [latestEvent, setLatestEvent] = useState(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!enabled || !id) return undefined;

    const close = openResearchStream(id, {
      onMessage: (event) => {
        setConnected(true);
        setLatestEvent(event);
      },
      onError: () => setConnected(false),
    });

    return close;
  }, [id, enabled]);

  return { latestEvent, connected };
}
