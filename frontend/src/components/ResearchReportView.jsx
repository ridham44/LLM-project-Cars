import { ResultSummaryBar } from "./ResultSummaryBar";
import { RoutingInfo } from "./RoutingInfo";
import { ExecutiveSummary } from "./ExecutiveSummary";
import { KeyFindings } from "./KeyFindings";
import { ComparisonTable } from "./ComparisonTable";
import { EvidencePanel } from "./EvidencePanel";
import { ClaimsPanel } from "./ClaimsPanel";
import { SourcesPanel } from "./SourcesPanel";
import { ResearchTrace } from "./ResearchTrace";

export function ResearchReportView({ report, isVerifying, onCancel }) {
  return (
    <div className="research-report">
      {report.isExample && (
        <div className="example-banner" role="note">
          <span className="example-banner__tag">Example</span>
          <span>The backend research pipeline isn't built yet — this illustrates the intended report.</span>
        </div>
      )}

      {/* One model writes the whole answer in one call, so there is no
          verification pass to wait on - this only appears while that call is
          still running. */}
      {isVerifying && (
        <div className="verifying-banner" role="status" aria-live="polite">
          <span className="verifying-banner__spinner" aria-hidden="true" />
          <span>
            {report.routing?.answerModel ? `${report.routing.answerModel} is writing the answer…` : "Writing the answer…"}
          </span>
          {onCancel && (
            <button type="button" className="text-button" onClick={onCancel}>
              Stop
            </button>
          )}
        </div>
      )}

      <header className="research-report__header">
        <span className="research-report__eyebrow">{isVerifying ? "Answering" : "Research Complete"}</span>
        <h1>{report.question}</h1>
      </header>

      <ResultSummaryBar metrics={report.metrics} sourcesCount={report.sources?.length} />
      <RoutingInfo routing={report.routing} metrics={report.metrics} />
      <ExecutiveSummary summary={report.summary} />
      <KeyFindings findings={report.findings} />
      <ComparisonTable comparison={report.comparison} evidence={report.evidence} />
      <EvidencePanel evidence={report.evidence} />
      <ClaimsPanel claims={report.claims} evidence={report.evidence} />
      <SourcesPanel sources={report.sources} />
      <ResearchTrace trace={report.trace} metrics={report.metrics} />
    </div>
  );
}
