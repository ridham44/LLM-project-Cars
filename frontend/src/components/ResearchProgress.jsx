import { PIPELINE_STEPS } from "../constants";

const PHASE_REACHED_INDEX = {
  idle: -1,
  submitting: 0,
  planning: 1,
  retrieving: 2,
  analyzing: 5,
  verifying: 6,
  synthesizing: 7,
  completed: 7,
  error: -1,
};

const STATUS_ICON = { done: "✓", active: "●", pending: "○" };

// Prefers real backend trace events (report.trace) when present; falls back
// to a coarse phase->step mapping so the panel still shows meaningful
// progress if the backend only reports a single status string. Never
// invents completion for steps the backend hasn't confirmed.
function resolveStepStatuses(phase, trace) {
  if (Array.isArray(trace) && trace.length > 0) {
    const byName = new Map(trace.map((entry) => [entry.step, entry.status]));
    return PIPELINE_STEPS.map((step) => byName.get(step) || "pending");
  }

  const reachedIndex = PHASE_REACHED_INDEX[phase] ?? -1;
  return PIPELINE_STEPS.map((_, index) => {
    if (index < reachedIndex) return "done";
    if (index === reachedIndex) return "active";
    return "pending";
  });
}

export function ResearchProgress({ phase, report, error, onCancel }) {
  if (phase === "error") {
    return (
      <section className="research-status research-status--error" role="alert">
        <h2>Research Failed</h2>
        <p>Unable to complete the research request.</p>
        {error && <p className="research-status__reason">Reason: {error.detail || error.message}</p>}
      </section>
    );
  }

  const stepStatuses = resolveStepStatuses(phase, report?.trace);
  const metrics = report?.metrics;

  return (
    <section className="research-status" aria-live="polite">
      <div className="research-status__header">
        <h2>Researching</h2>
        {onCancel && (
          <button type="button" className="text-button" onClick={onCancel}>
            Stop
          </button>
        )}
      </div>
      <ol className="pipeline-steps">
        {PIPELINE_STEPS.map((step, index) => (
          <li key={step} className={`pipeline-steps__item pipeline-steps__item--${stepStatuses[index]}`}>
            <span className="pipeline-steps__icon" aria-hidden="true">
              {STATUS_ICON[stepStatuses[index]]}
            </span>
            <span>{step}</span>
          </li>
        ))}
      </ol>
      {metrics && (metrics.documentsSearched != null || metrics.evidenceChunks != null) && (
        <div className="research-status__metrics muted">
          {metrics.documentsSearched != null && <span>Documents searched: {metrics.documentsSearched}</span>}
          {metrics.evidenceChunks != null && <span>Evidence chunks: {metrics.evidenceChunks}</span>}
        </div>
      )}
    </section>
  );
}
