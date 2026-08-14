export function ExecutiveSummary({ summary }) {
  if (!summary) return null;

  return (
    <section className="panel executive-summary" aria-label="Executive summary">
      <h2>Executive Summary</h2>
      <p>{summary}</p>
    </section>
  );
}
