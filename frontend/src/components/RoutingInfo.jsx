import { humanizeIntent } from "../constants";
import { confidenceTone } from "../utils/format";

// Read-only explanation of what the backend decided for this question.
//
// ONE REQUEST = ONE ANSWER MODEL, so this panel names one model. It used to
// render a list of roles (researcher / analyst / critic / judge) which both
// described a pipeline that no longer exists and, worse, implied independent
// cross-checking as a routine feature. The only other model that can appear is
// the tiny router, on the rare ambiguous question - and it is labelled as
// having classified the question, never as having written any of the answer.
export function RoutingInfo({ routing, metrics }) {
  if (!routing) return null;

  const answerModel = routing.answerModel || routing.modelsUsed?.[0]?.model;
  const answerEntry = routing.modelsUsed?.find((m) => m.role === routing.answerTier) || routing.modelsUsed?.[0];
  const classifier = routing.modelsUsed?.find((m) => m.role === "router");
  const seconds = metrics?.executionTimeSeconds;

  return (
    <section className="panel routing-info" aria-label="AI routing">
      <h2>AI Routing</h2>
      <dl className="routing-info__grid">
        <div>
          <dt>Intent</dt>
          <dd>{humanizeIntent(routing.intent)}</dd>
        </div>
        <div>
          <dt>Complexity</dt>
          <dd>{routing.complexity}</dd>
        </div>
        <div>
          <dt>Model</dt>
          <dd>
            {answerModel ? (
              <span className={`badge badge--${answerEntry?.ran === false ? "danger" : "success"}`}>{answerModel}</span>
            ) : (
              <span className="muted">none needed</span>
            )}
          </dd>
        </div>
        <div>
          <dt>Evidence</dt>
          <dd>{routing.evidenceCount} passages</dd>
        </div>
        <div>
          <dt>Documents searched</dt>
          <dd>
            {routing.documentScope?.length ? routing.documentScope.join(" + ") : "Whole knowledge base"}
            {routing.documentScopeRelaxed && <span className="muted"> (no match - widened)</span>}
          </dd>
        </div>
        <div>
          <dt>Time</dt>
          <dd>{seconds != null ? `${seconds.toFixed(1)}s` : "—"}</dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd>
            <span className={`badge badge--${confidenceTone(routing.confidence)}`}>
              {routing.confidenceLabel || "—"}
            </span>
          </dd>
        </div>
      </dl>

      {answerEntry?.reason && <p className="muted routing-info__note">{answerEntry.reason}</p>}

      {classifier && (
        <p className="muted routing-info__note">
          {classifier.model} classified the question only - it wrote none of the answer.
        </p>
      )}

      {answerEntry?.ran === false && (
        <p className="muted routing-info__note">
          {answerModel} was unavailable, so this question was not answered.
        </p>
      )}
    </section>
  );
}
