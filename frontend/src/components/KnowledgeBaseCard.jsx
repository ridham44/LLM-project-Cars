export function KnowledgeBaseCard({ knowledgeBase }) {
  const rows = [
    { label: "Documents", value: knowledgeBase.documents },
    { label: "Chunks", value: knowledgeBase.chunks },
    { label: "Sources", value: null },
    { label: "Manufacturers", value: null },
  ];

  return (
    <section className="sidebar-card" aria-label="Knowledge base">
      <h2>Knowledge Base</h2>
      <div className="sidebar-card__rows">
        {rows.map((row) => (
          <div className="sidebar-card__row" key={row.label}>
            <span>{row.label}</span>
            <span className="sidebar-card__row-value">
              {row.value === null || row.value === undefined ? "—" : row.value.toLocaleString()}
            </span>
          </div>
        ))}
      </div>
      {!knowledgeBase.ready && <p className="muted sidebar-card__note">No documents indexed yet.</p>}
    </section>
  );
}
