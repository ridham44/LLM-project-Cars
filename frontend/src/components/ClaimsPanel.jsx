import { useState } from "react";

// The specific, checkable statements the answer makes, with the evidence the
// answer model cited for each.
//
// This panel used to be titled "Claim Verification" and showed
// supported/contradicted badges with per-claim confidence. It no longer does,
// because nothing verifies claims on a normal request: that used to be two
// extra model calls (measured at 90.0s and 49.2s) and they were removed. A
// panel that kept saying "Supported" without a check behind it would be the
// worst possible outcome - the UI would be asserting something the system no
// longer knows.
//
// What is honest, and still useful, is whether a claim is TIED TO EVIDENCE: a
// number the model attributed to e3 can be checked by the reader in one click;
// an uncited assertion is exactly what deserves a second look. To have the
// claims actually re-examined, ask - "are you sure?" routes the whole question
// to the reasoning model.
export function ClaimsPanel({ claims, evidence }) {
  const [expandedIndex, setExpandedIndex] = useState(null);

  if (!claims || claims.length === 0) {
    return (
      <section className="panel" aria-label="Claims in this answer">
        <h2>Claims In This Answer</h2>
        <p className="muted">This answer didn't make specific checkable claims.</p>
      </section>
    );
  }

  const evidenceById = new Map((evidence || []).map((item) => [item.id, item]));
  const citedCount = claims.filter((claim) => claim.cited).length;

  return (
    <section className="panel" aria-label="Claims in this answer">
      <h2>Claims In This Answer</h2>
      <p className="muted claims-panel__note">
        {citedCount} of {claims.length} tied to specific evidence. Not independently verified — ask “are you sure?” to
        have a reasoning model re-examine the answer.
      </p>
      <ul className="claims-list">
        {claims.map((claim, index) => {
          const isExpanded = expandedIndex === index;
          const claimEvidence = (claim.evidenceIds || []).map((id) => evidenceById.get(id)).filter(Boolean);

          return (
            <li key={`${index}-${claim.text.slice(0, 24)}`} className="claim-item">
              <button
                type="button"
                className="claim-item__toggle"
                aria-expanded={isExpanded}
                disabled={claimEvidence.length === 0}
                onClick={() => setExpandedIndex(isExpanded ? null : index)}
              >
                <span className={`badge badge--${claim.cited ? "success" : "neutral"}`}>
                  {claim.cited ? "◆ Cited" : "○ Uncited"}
                </span>
                <span className="claim-item__text">{claim.text}</span>
              </button>
              {claimEvidence.length > 0 && (
                <div className="claim-item__meta">
                  <span>
                    {claimEvidence.length} evidence {claimEvidence.length === 1 ? "passage" : "passages"} cited
                  </span>
                </div>
              )}
              {isExpanded && claimEvidence.length > 0 && (
                <ul className="claim-item__evidence">
                  {claimEvidence.map((item) => (
                    <li key={item.id}>
                      <strong>{item.documentTitle}</strong>
                      {item.page ? ` · Page ${item.page}` : ""} — “{item.excerpt}”
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
