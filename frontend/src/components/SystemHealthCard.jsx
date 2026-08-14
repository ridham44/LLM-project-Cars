function Row({ label, online, detail }) {
  return (
    <div className="sidebar-card__row">
      <span>{label}</span>
      <span className={`status-dot ${online ? "status-dot--success" : "status-dot--neutral"}`} aria-hidden="true" />
      {detail && <span className="muted sidebar-card__row-detail">{detail}</span>}
    </div>
  );
}

export function SystemHealthCard({ systemStatus }) {
  const modelCount = Object.keys(systemStatus.models).length;
  const modelsReady = Object.values(systemStatus.models).filter((m) => m.available).length;

  return (
    <section className="sidebar-card" aria-label="System health">
      <h2>System Health</h2>
      <div className="sidebar-card__rows">
        <Row label="Ollama" online={systemStatus.ollamaReachable} />
        <Row label="Backend" online={systemStatus.backendReachable} />
        <Row label="Vector Database" online={systemStatus.knowledgeBase.ready} />
        <Row
          label="Models"
          online={modelCount > 0 && modelsReady === modelCount}
          detail={modelCount > 0 ? `${modelsReady} / ${modelCount}` : null}
        />
      </div>
    </section>
  );
}
