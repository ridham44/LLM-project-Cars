import { formatSeconds } from "../utils/format";

export function ResultSummaryBar({ metrics, sourcesCount }) {
  if (!metrics) return null;

  const items = [
    { label: "Documents", value: metrics.documentsSearched },
    { label: "Evidence Chunks", value: metrics.evidenceChunks },
    { label: "Claims", value: metrics.claimsExtracted },
    { label: "Sources", value: sourcesCount },
    // A bucket label ("Moderate") rather than a bare percentage - see
    // confidence.py: the underlying signals don't support the precision a
    // number like "72%" implies.
    { label: "Confidence", value: metrics.confidenceLabel },
    { label: "Time", value: formatSeconds(metrics.executionTimeSeconds) },
  ].filter((item) => item.value !== undefined && item.value !== null);

  return (
    <dl className="result-summary-bar">
      {items.map((item) => (
        <div key={item.label} className="result-summary-bar__item">
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
