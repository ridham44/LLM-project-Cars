import { formatPercent, confidenceTone } from "../utils/format";

export function KeyFindings({ findings }) {
  if (!findings || findings.length === 0) return null;

  return (
    <section className="panel key-findings" aria-label="Key findings">
      <h2>Key Findings</h2>
      <ol className="key-findings__list">
        {findings.map((finding, index) => (
          <li key={finding.id} className="key-findings__item">
            <span className="key-findings__index">{String(index + 1).padStart(2, "0")}</span>
            <div className="key-findings__body">
              <p>{finding.text}</p>
              <div className="key-findings__meta">
                <span>Evidence · {finding.evidenceCount} sources</span>
                <span className={`badge badge--${confidenceTone(finding.confidence)}`}>
                  Confidence {formatPercent(finding.confidence)}
                </span>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
