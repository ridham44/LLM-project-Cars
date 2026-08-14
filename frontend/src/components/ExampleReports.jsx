import { EXAMPLE_REPORT } from "../data/exampleReport";
import { formatPercent } from "../utils/format";

// Only ever shows the one example report we actually have real fixture
// data for (clearly labeled EXAMPLE) - additional topics belong in
// SuggestedQuestions, which trigger real research instead of displaying
// invented stats for reports that don't exist.
export function ExampleReports({ onOpen }) {
  return (
    <section className="sidebar-card" aria-label="Example reports">
      <h2>Example Reports</h2>
      <button type="button" className="example-report-card" onClick={() => onOpen(EXAMPLE_REPORT)}>
        <span className="badge badge--neutral example-report-card__badge">Example</span>
        <span className="example-report-card__title">Bugatti vs Koenigsegg</span>
        <span className="muted example-report-card__subtitle">Engineering Comparison</span>
        <span className="example-report-card__excerpt">{EXAMPLE_REPORT.summary}</span>
        <span className="example-report-card__stats">
          <span>{EXAMPLE_REPORT.sources.length} Sources</span>
          <span>{formatPercent(EXAMPLE_REPORT.metrics.confidence)} Confidence</span>
        </span>
        <span className="text-button example-report-card__link">Open Report →</span>
      </button>
    </section>
  );
}
