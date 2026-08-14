function buildTraceLines(trace, metrics) {
  const entries = trace || [];
  const doneSteps = new Set(entries.filter((t) => t.status === "done").map((t) => t.step));
  const lines = [];

  if (doneSteps.has("Query Understanding")) lines.push("Query classified");
  if (doneSteps.has("Research Planning")) lines.push("Research plan generated");
  // A marque-scoped search covers part of the knowledge base, so reporting
  // the full document count for one would overstate what was read.
  const scope = entries.find((t) => t.step === "Document Scope");
  if (doneSteps.has("Document Retrieval") && metrics?.documentsSearched != null) {
    lines.push(
      scope?.brands?.length && !scope.relaxed
        ? `Search scoped to ${scope.brands.join(" + ")} documents`
        : `${metrics.documentsSearched} documents in the knowledge base searched`,
    );
  }
  if (scope?.relaxed) lines.push(`Widened to the whole knowledge base - ${scope.reason}`);
  if (doneSteps.has("Hybrid Search")) lines.push("Retrieval widened - initial evidence was weak");
  if (doneSteps.has("Evidence Ranking") && metrics?.evidenceChunks != null) {
    lines.push(`${metrics.evidenceChunks} evidence chunks selected`);
  }
  const selection = entries.find((t) => t.step === "Model Selection");
  if (selection?.model) lines.push(`${selection.model} selected (${selection.tier} tier)`);

  const answer = entries.find((t) => t.step === "Answer");
  if (answer) {
    lines.push(answer.ran === false ? `${answer.model} was unavailable` : `${answer.model} wrote the answer`);
  }
  if (metrics?.claimsExtracted) {
    lines.push(`${metrics.claimsExtracted} claims reported by the same model, in the same call`);
  }

  return lines;
}

export function ResearchTrace({ trace, metrics }) {
  const lines = buildTraceLines(trace, metrics);
  if (lines.length === 0) return null;

  // Real per-step durations measured by the backend (orchestrator's
  // _step_timings), in PIPELINE ORDER with a total. Order rather than
  // slowest-first: with one answer model the shape of a request is fixed
  // (understand -> select -> retrieve -> answer), so reading it in sequence
  // shows immediately which stage misbehaved. The 100ms floor is gone - the
  // whole point of the rework is that understanding now costs tens of
  // milliseconds, and a panel that hides anything under 100ms would hide the
  // evidence for that.
  const timings = metrics?.timings || [];
  const totalMs = timings.reduce((sum, t) => sum + t.durationMs, 0);

  return (
    <section className="panel research-trace" aria-label="Research trace">
      <h2>Research Trace</h2>
      <ul>
        {lines.map((line) => (
          <li key={line}>
            <span aria-hidden="true">✓</span> {line}
          </li>
        ))}
      </ul>
      {timings.length > 0 && (
        <>
          <h3 className="research-trace__subhead">Where the time went</h3>
          <ul className="research-trace__timings">
            {timings.map((t) => (
              <li key={t.step}>
                <span>{t.step}</span>
                <span className="muted">{(t.durationMs / 1000).toFixed(2)}s</span>
              </li>
            ))}
            <li className="research-trace__timings-total">
              <span>Total</span>
              <span>{(totalMs / 1000).toFixed(2)}s</span>
            </li>
          </ul>
        </>
      )}
    </section>
  );
}
